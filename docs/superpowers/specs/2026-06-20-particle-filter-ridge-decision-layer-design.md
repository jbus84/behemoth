# Particle-Filter Decision Layer over the Frozen Ridge Edges — Design

Date: 2026-06-20
Status: Design (approved in brainstorming, pending spec review)
Scope: FX research — momentum tail (2h) and short-horizon reversion (2–3d)

---

## 1. Motivation

Two FX edges have survived the full causal / day-clustered / multi-year gauntlet:

- **2h momentum tail** (`scripts/fx_coint/tail_wfo.py`): Ridge fits a vol-normalized
  forward return on momentum features → `test_pred`; enter when `test_pred ≥ train q95`,
  hold a **fixed 2h horizon**, exit on the clock.
- **2–3d reversion** (`scripts/fx_coint/validate_reversion_cell.py`): fade the past-10d
  vol-normalized move when in the causal tail decile, hold 2–3 days non-overlapping, exit
  on the clock.

Both share one shape: **rank a signal → enter on an extreme → hold a fixed horizon →
exit on the clock.** There is no online estimation of the price path during the hold.
Entries sit on a coarse grid; exits are time-based, not state-based.

The goal: use a particle filter (PF) to produce an online posterior over a latent state
at each bar, and read that single posterior four ways — **smarter exits, smarter entries,
confidence sizing, and (deferred) denoising** — without disturbing the proven ridge signal.

### Prior constraint (from track record)
Every modeling lever tried so far (GAMLSS upper-quantile, Student-t loc-scale, Huber/median,
boosting, MultiRocketHydra TSER) came in **below plain Ridge** — the edge is a near-linear
monotone momentum tilt that lives in the **tail moves**, and complexity overfit it. A PF must
therefore beat the dumb fixed-horizon baseline under the *same* rigor, or it is cut.

### Prior art
`scripts/fx_coint/pf_15m_reversal.py` already implements `BetaPF`: a bootstrap PF tracking a
**drifting predictive coefficient `β_t`** (random-walk) with **Student-t** observation
likelihood, at 15m. Two notes:
1. Its framing (time-varying coefficient) is *complementary* to this design's framing
   (latent drift + regime). It will be kept as a comparison baseline.
2. Its Student-t obs noise is exactly the tail-robustification this design argues **against**
   (see §2) — a key hypothesis to test head-to-head.

---

## 2. The state-space model (Approach A: decision layer over a frozen ridge)

Per bar `t`, on the strategy's own clock (2h for momentum, 1d for reversion). Latent state:

```
s_t  ∈ {trend, revert}    discrete regime, Markov with sticky 2×2 transition matrix P
μ_t  ∈ ℝ                   latent vol-normalized drift
σ_t  > 0                   latent vol (slow random walk in log-space)
```

**Transition**
- `s_t ~ Markov(P)`, diagonal-dominant so regimes persist; stickiness is what makes
  early-exit meaningful rather than jittery.
- `μ_t = φ_{s_t} · μ_{t-1} + ridge_tilt_t · 1[s_t = trend] + ε`
  - `φ_trend ≈ 0.9` (drift persists in trend), `φ_revert < 0` (overshoot reverts).
  - `ridge_tilt_t` injects the **frozen** ridge prediction as a regime-conditional nudge —
    the ridge only "speaks" while the trend regime is active.
- `σ_t`: log random walk.

**Observation**
- `r_t = μ_t · σ_t + noise`, with **light-tailed (Gaussian) obs noise by default.**
  All non-Gaussianity comes from the regime switch and `μ`, so the filter never discounts
  the tail moves the edge depends on (the GAMLSS-t lesson). The Student-t variant from
  `BetaPF` is tested as an explicit alternative hypothesis, not the default.

**Filter**
- Rao-Blackwellized PF: particles carry discrete `s_t` (and `σ_t`); `μ_t` is Kalman-updated
  analytically per particle. Fewer particles, faster, avoids the noisy/slow PF failure mode.
- Systematic resampling on low ESS.

---

## 3. Online discipline (non-negotiable)

- Filter runs **strictly causally**: at bar `t` it sees only data ≤ `t`. No smoothing /
  backward pass.
- All PF hyperparameters (`P`, `φ`, noise scales) fit on an **expanding/rolling PAST window
  only** — same regime as the existing causal decile thresholds. Never full-sample.
- The ridge stays **frozen** and walk-forward exactly as validated. The PF is bolted on
  *after* the ridge prediction exists, so it cannot leak into the ridge fit.

---

## 4. The four decision rules (all read the same posterior)

At each bar the RBPF yields `P(s_t = trend | data ≤ t)`, posterior mean `μ̂_t`, and posterior
variance `Var(μ_t)`.

1. **Entry confirm.** Ridge flags the candidate bar (q95 / tail-decile, unchanged). Enter
   only if `P(trend) > π_enter` AND `sign(μ̂)` matches the trade AND
   `|μ̂| − cost > κ·√Var(μ̂)` (edge clears cost by a confidence margin). Else skip.
2. **Dynamic exit.** Exit when `P(trend) < π_exit`, OR `μ̂` flips sign, OR `μ̂` decays below
   cost. Keep the original fixed horizon as a hard **max-hold cap.**
3. **Sizing.** position ∝ `clip(μ̂ / Var(μ̂), 0, cap)` (Kelly-flavored). Diffuse → small/zero;
   sharp → full. Must be evaluated with costs (turnover interaction).
4. **Denoise (deferred, Phase 3).** Feed `μ̂_t` back as a ridge feature/target and refit.
   Only if Phases 1–2 already pay — this is the one change that touches the proven signal.

---

## 5. Validation gauntlet (per phase, or it does not ship)

Each phase must **beat the frozen fixed-horizon baseline** under:
- Net of real Razor/commission cost; **causal** PF params (past-only).
- **Day-clustered** t-stat + **year-block bootstrap 95% CI clearing zero.**
- **Positive-years** count (target ≥4/5) and **per-pair generalization**
  (EUR/GBP/JPY, then OOS pairs).
- **Ablation attribution**: baseline → +dynamic-exit → +entry-confirm → +sizing; each lever's
  marginal contribution isolated. A lever that does not beat baseline is cut (YAGNI).
- **Null check**: a PF fed a **randomized regime posterior** must NOT beat baseline (guards
  against the filter being a fancy turnover knob).
- **Head-to-head**: Gaussian-obs regime PF vs the `BetaPF` Student-t drifting-coefficient PF,
  to confirm the tail-light obs hypothesis.

---

## 6. Build order

- **Phase 1** — dynamic-exit only (biggest, cleanest lever; max-hold cap retained).
- **Phase 2** — entry-confirm + confidence sizing from the same posterior.
- **Phase 3** — denoise-into-ridge, only if earned.

Each phase: its own spec → plan → PR off `main` in this worktree (`feat-pf-15m`). Applied
first to the **2h momentum** edge (most validated), then ported to the **2–3d reversion** edge.

---

## 7. Out of scope (YAGNI)

- Full end-to-end state-space replacement of the strategy (Approach B) — discarded:
  highest overfit risk, worst attribution, throws away the proven edge.
- New timeframes/instruments. The 15m reversal exploration (`pf_15m_reversal.py`) stays a
  prior-art baseline; it is not a deployment target (15m scalping is a prior NO-GO).
- Any non-causal/full-sample fitting.
