# ERA 100-tick scalping discovery — design

- Status: Proposed
- Date: 2026-05-30
- Relates to: ADR 0005 (dispersion ERA, `scripts/era/`), the ERA-faithful loop
  (Nature 2026 / arXiv 2509.06503). This applies the *same* search engine to a
  new, single-symbol, directional problem.

## Goal

Use the ERA loop (PUCT forest + qwen3-coder-next program writer + repo-metric
judge) to discover a **causally valid, net-of-cost directional scalping signal on
100-tick bars** for the USD majors, grounded in modern microstructure research.
The judge is the governed evaluation ladder, never the LLM.

## Why 100-tick scalping is the opposite problem to dispersion

Feasibility on EURUSD 100-tick (2018–2026, 2.2M bars, ~725 bars/day):

| quantity | value |
|---|---|
| median `cost_est_pips` | 0.44 |
| median `spread_pips` | 0.31 |
| median \|`y_fwd_pips_h1/h2/h3`\| | 0.90 / 1.30 / 1.60 |
| P(\|move\| > cost) h1/h2/h3 | 0.73 / 0.81 / 0.84 |

Fills are abundant (the dispersion track's binding constraint is gone). The move
usually clears the spread, so the hard part is **predicting the sign of `y_fwd`**,
and the dominant risk is **overfitting on a huge, autocorrelated sample** — handled
by embargoed splits + BH-FDR (below).

## Architecture (Approach A — reuse the engine)

The ERA search engine is signal-agnostic; only the context, harness, and seeds are
dispersion-specific. We add a focused package `scripts/era_scalp/` that **reuses the
engine by import** and leaves `scripts/era/` untouched.

- **Reused from `scripts/era/` (import, no copy):** `puct.py` (PUCT forest),
  `select.py` (`bh_fdr`, `holdout_pvalue`), `llm.py` (`propose_program`,
  `recombine_program` — a scalping prompt is passed in), and `sandbox.static_check`.
- **New in `scripts/era_scalp/`:** `context.py`, `sandbox.py`, `harness.py`,
  `seeds.py`, `load_splits.py`, `run_era_scalp.py`, plus `prompt.py` (scalping
  `_RULES`) — or the rules live in `seeds.py`/`llm` call site, decided in the plan.

## Components

### FeatureContext (`context.py`)

```text
FeatureContext:
  X: (n_bars, n_features) float32, time-ordered, CAUSAL features only
  names: list[str]            # feature column names, order matches X columns
  hour: np.ndarray            # hour_utc convenience (also present in X)
  # close_ts is held by the split (for embargo), NOT exposed as a feature
  accessors: col(name)->1d, X, n_bars, names
```

Programs define **`signal(ctx) -> np.ndarray`** (length n_bars): a per-bar directional
score where `sign` = predicted direction of `y_fwd`, magnitude = conviction, and
`np.nan` = no-trade (self-gating; the scorer drops non-finite entries).

**Causal feature whitelist** (verified backward/`.shift(1)` in
`scripts/build_tick_velocity_dataset.py`):

```text
spread_pips, spread_z, tick_volume, tick_rate_hz, tick_rate_z,
tick_burst, tick_burst_score, high_pos_tick, low_pos_tick, hl_pos_delta_tick,
bar_return_sign, vel_pips_h1, vel_pips_h2, vel_pips_h5, vel_pips_h10,
vel_z_h1, vel_z_h2, vel_z_h5, vel_z_h10, accel_pips, hour_utc
```

**Excluded:** `y_fwd_*` (forward labels), raw OHLC `open/high/low/close_bid/ask`
(non-stationary, and entry is at next-bar open), `cost_est_pips` (harness-side label),
`close_ts`, `bar_ticks`.

**Leakage gate (plan-time audit, MANDATORY):** the causality probe perturbs future
*rows* and so catches a program that *reads* the future — but it cannot catch leakage
*baked into a column* (a forward-looking feature value stored at row k). Therefore the
whitelist is the safety mechanism: each `*_z`/rolling column MUST be confirmed
rolling+`.shift(1)` (not full-sample) against the builder before inclusion. `vel_*_hN`
are backward (`close[k]-close[k-h]`) and `y_fwd_*` are forward (`close[k+h]-open[k+1]`),
already confirmed.

### Directional harness (`harness.py`)

```text
s    = signal / robust_scale(finite signal)   # scale only; NO mean-centering
side = sign(signal)                            # program owns direction (fade = negative)
entry= isfinite(s) & isfinite(y_fwd) & isfinite(cost) & (|s| >= threshold)
net  = side * y_fwd_pips_h - cost_est_pips     # enter next-open; single cost
```

Deliberate difference from the dispersion harness: we scale but do **not** subtract the
mean, so the program's directional sign is preserved (centering would move the decision
boundary near zero for a directional score). Robust scale = **MAD-based**:
`1.4826 * median(|signal − median(signal)|)` over finite values (resists the heavy tails
of microstructure scores; fixed post-hoc transform applied uniformly; the
embargoed-holdout + BH-FDR is the real verdict, exactly as in dispersion).

`task_score(df)` = reused continuous signal
`net_LB95 * (0.25 + 0.75*month_weight) * n_weight` (NEVER a hard in-search gate).

`entry_diagnostics(...)` returns: `n_entries`, `fills_per_day`, **`hit_rate` =
P(side·y_fwd > 0)**, `mean_net`, `mean_cost`, `month_hit_rate`.

Threshold grid `[0.5, 1.0, 1.5, 2.0]`; horizon grid `h1/h2/h3`.

### Sandbox (`sandbox.py`)

Reuses `scripts/era/sandbox.static_check`, generalized with a backward-compatible
`required_fn: str = "residual"` parameter (scalping passes `"signal"`); all other checks
(no imports/dunders/forbidden builtins) are unchanged and shared. New subprocess worker
rebuilds a `FeatureContext` from the npz payload.
A generalized `causality_probe(src, ctx, clean_signal, n_cuts=2)` perturbs future rows of
`X` (and `hour`) with finite noise and rejects any program whose `signal[:k+1]` changes.

### Seeds (`seeds.py`) — modern, multi-stream, all causal & numpy-only

```text
# A. Order-flow imbalance / price impact (Cont-Kukanov-Stoikov 2014; Kolm-Turiel-Westray 2023)
ofi_flow            signed-flow proxy (bar_return_sign * tick_volume), EWMA-smoothed; side=sign(flow)
ofi_multihorizon    weighted stack of vel_z_h1/h2/h5/h10 + tick imbalance (multi-horizon OFI alpha)

# B. OU mean-reversion (Avellaneda-Lee 2010 s-score; Leung-Li 2015; Bertram 2010)
ou_sscore           trailing-window AR(1) on cumulative-return deviation -> theta/sigma_eq;
                    emit -s_score (fade); window ~ half-life; entry band searchable
roll_bounce_fade    fade sub-spread over-extension: -sign(vel_pips_h1) gated by |vel| < k*spread (Roll 1984)

# C. Hawkes self-exciting bursts (Bacry-Mastromatteo-Muzy 2015; Volume Clock 2012)
hawkes_cont         EWMA-decayed tick-arrival intensity (tick_rate_z/tick_burst); when elevated,
                    continuation in recent-move direction, scaled by intensity

# Regime gate seed
spread_gated_flow   any directional core, traded only when spread_z is low (tradeable regime)
```

`RESEARCH_IDEAS` strings name the mechanisms and papers (OU optimal bands, Hawkes
intensity, multi-horizon OFI, Sirignano-Cont universal flow→return map transferred to a
stateful EWMA formula, rough-vol/queue-reactive regime gates, path signatures as an
optional stretch). The prompt tells the writer it has the full causal time axis
(trailing/expanding/EWMA, bounded) and that a probe rejects any future read.

### Splits + embargo (`load_splits.py`)

Read the single-symbol parquet, build `X` from the whitelist, keep `close_ts`,
`y_fwd_pips_h{h}`, `cost_est_pips`. Splits by calendar:

```text
train      2018..2023
validation 2024
holdout    2025..2026
```

**Embargo (López de Prado 2018):** drop the first `h` bars of each split adjacent to the
previous split's tail (the `y_fwd_h{h}` label window length), so overlapping labels cannot
leak across train/validation/holdout. This makes the BH-FDR holdout verdict honest rather
than autocorrelation-inflated.

### Driver (`run_era_scalp.py`)

Mirrors `run_era.py`: `build_splits` → `run_search` (seed forest + qwen mutate/recombine,
scored on validation) → sort → re-score top-N on the **embargoed holdout** → `entry_diagnostics`
+ `bh_fdr(holdout_pvalue)` → markdown report. Flags: `--symbol --horizon --budget
--no-baseline-seeds --holdout-top`. A `BASELINE_SEED_NAMES` subset supports the rediscovery
tracer.

## Evaluation plan

Fast loop (this project): per-program validation `task_score`; final selection = embargoed
holdout + BH-FDR over the explored set. Report the directional **hit-rate**, fills/day,
mean net, and month hit-rate per top program. A discovered signal is **not** deployable
until it survives the real governance ladder (Stage 2/3 Monthly WFO → Reduced-Core Rolling
→ Tick-Exact → Robustness) on more symbols/horizons — out of scope here, same posture as
the dispersion SP3 note.

## Literature foundations

- **OFI / price impact:** Kyle (1985); Lee & Ready (1991); Cont, Kukanov & Stoikov (2014);
  Easley, López de Prado & O'Hara (2012, VPIN); Sirignano & Cont (2019); Kolm, Turiel &
  Westray (2023); Zhang, Zohren & Roberts (2019, DeepLOB).
- **OU mean-reversion:** Avellaneda & Lee (2010); Leung & Li (2015); Bertram (2010);
  Cartea, Jaimungal & Penalva (2015); Roll (1984).
- **Hawkes / bursts:** Bacry, Mastromatteo & Muzy (2015); Easley, López de Prado & O'Hara
  (2012, The Volume Clock).
- **Regime / methodology:** Gatheral, Jaisson & Rosenbaum (2018, rough vol); Huang, Lehalle
  & Rosenbaum (2015, queue-reactive); **López de Prado (2018), Advances in Financial ML**
  (purged & embargoed CV — the honest-evaluation backbone; triple-barrier/meta-labeling as
  future options).
- *Deep-learning constraint:* the sandbox synthesizes causal numpy formulas, not neural
  nets, so DeepLOB/deep-OFI contribute *mechanisms* (multi-horizon stacked OFI, stateful
  EWMA flow→return maps), not architectures.
- Full citations with links to be added to the spec references at plan time (verified, not
  fabricated).

## Testing

- `test_context` — accessors; whitelist excludes `y_fwd_*`/raw prices; X shape matches names.
- `test_harness` — directional side/entry/net; hit-rate diagnostic; TaskScore continuity.
- `test_causality` — probe accepts a causal signal, rejects a forward-looking one; **all seeds causal**.
- `test_seeds` — each family seed present, runs, causal; OU s-score numeric sanity vs a reference.
- `test_load_splits` — embargo removes boundary-overlap bars; no leakage columns in `names`; splits non-empty.
- `test_integration` — `select_seed_programs` ablation; `finalize_selection` BH-FDR; mocked-writer end-to-end.
- Reuse `scripts/era/` `select`/`puct`/`llm` tests by reference (engine unchanged).

## Consequences

- A second, focused ERA application; the dispersion loop is untouched and the engine is shared.
- The causal whitelist (not just the probe) is the leakage gate for baked-in column leakage.
- Honest evaluation under dense overlapping labels via embargo + BH-FDR; abundant fills mean
  the binding risk is overfitting, which these controls target.
- Likely first outcome (per the dispersion precedent): the loop reaches the modern catalogue
  and rediscovers baselines; whether a *certifiable* net-of-cost edge survives the embargoed
  holdout is the open empirical question — which is exactly what this is built to answer.
```
