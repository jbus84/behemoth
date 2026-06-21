# Conditional Path-Distribution → Execution-Geometry Optimization — Design

Date: 2026-06-21
Status: Design (approved in brainstorming, pending spec review)
Scope: FX research — execution geometry for the two validated edges
  (2h momentum tail-long, 2-3d short-horizon reversion)

---

## 1. Motivation & honest framing

The idea: simulate / enumerate many potential future paths for a given condition to get a
probability distribution of outcomes, and use it to make better trading decisions.

**Honest premise (decides everything):** a distribution of future paths is only as
informative as the generative process behind it. A simulator calibrated to historical FX
dynamics will reproduce the **unconditional, near-random-walk** distribution — a fan of paths
that is not tradeable. Value appears *only* if the **condition** shifts the path distribution
away from unconditional. Spot FX conditional *drift* edge is tiny and mostly sub-cost (this
project's recurring finding). Therefore this work is **not an alpha source** — it is an
**execution-geometry / risk tool** for edges we have already validated.

**Decision chosen (brainstorm):** *Execution geometry for known edges* — use the conditional
path distribution to optimize take-profit / stop-loss brackets, sizing, and hold for the
already-validated edges. Not new-alpha discovery.

**Generative engine chosen:** *Empirical first, simulator only if needed* — the least-overfit
"distribution" is the **empirical conditional path ensemble** (the actual historical 1-minute
intra-hold paths that followed similar conditions). Add bootstrap / PF path augmentation only
if the empirical tails prove too thin (Phase C).

**Edges:** *Both in parallel*, but via ONE shared engine; each edge is a config.

**Sharp prior hypothesis (keeps the search honest):** the tail-long edge's mechanism is
payoff-asymmetry ("monetize the big moves"). A **take-profit caps the right tail the edge
lives in** → expected to HURT (consistent with Phase-1 dynamic-exit cutting winners). A
**stop-loss truncates the left tail** (which has killed net in prior directional work) → may
help. If the optimizer instead "discovers" a tight TP is great, treat it as an overfit red
flag, not a win.

---

## 2. Architecture — three small, independently-testable units

### (a) Conditional path ensemble builder
For an edge's entries (existing causal selection — ridge q95 for 2h tail-long; tail-decile
fade for 2-3d reversion), collect the **1-minute intra-hold mid paths** following each entry,
anchored at the entry (bar-close) mid and vol-normalized (÷σ, the panel `sigma_h`) so paths
are comparable across pairs and time. This ensemble IS the conditional distribution.
Reuses `pf_paths.build_minute_index` / `hold_path`. The 2-3d reversion edge requires a
multi-day extension of `hold_path` (the only new path machinery).

### (b) Unconditional reference ensemble
The same 1-minute path construction at **random non-signal entry times**, matched by pair and
by hour/session. This is the null fan — the random-walk baseline the conditional must beat.

### (c) Bracket evaluator
Walk each 1-minute path step-by-step. Given geometry `(stop = s·σ, take_profit = tp·σ,
max_hold)`, return realized net bps: exit at the first minute the mid crosses SL or TP, else
at `max_hold`. Per-minute data is **mid only** (no sub-minute high/low), so when a single
minute's gap straddles both levels, assume the **stop hits first** (conservative). Cost
(`reg_signal_hunt.COST_BPS[sym]`) charged once per round-trip.

Each unit has a clean interface and is testable on synthetic paths with known crossings.

---

## 3. Geometry optimizer, decision metric, anti-mirage discipline

**Coarse grid (few DOF on purpose):**
- `stop ∈ {none, 1σ, 1.5σ, 2σ, 3σ}`
- `take_profit ∈ {none, 2σ, 3σ, 4σ}`
- `max_hold ∈ {edge native horizon, 2× native}`

The native fixed-horizon exit (`none / none / native`) is always in the grid as the
**baseline cell** every other cell must beat.

**Causal selection, OOS evaluation.** Geometry is chosen on an **expanding/rolling PAST
window** (best train cell by net bps) and applied to the next OOS block — never full-sample
(same regime as the causal decile thresholds).

**Decision metric & gates** (decompose gross vs cost vs significance): net bps after real
cost, **day-clustered t**, **year-block bootstrap 95% CI clearing zero**, **positive-years**,
and **pooled across pairs** (breadth, not per-pair cherry-pick). Reported as baseline cell →
best-OOS-geometry cell, isolating the marginal improvement.

**Multiplicity controls.** Two edges × the grid is a multiple-comparison problem:
- **BH-FDR** across all geometry cells.
- Headline = the **selected-OOS** result (which already pays the selection cost), NOT the
  best in-sample cell.
- **Shuffled-label null:** geometry optimized on randomized entries must not beat baseline.

---

## 4. Falsifiability gates (run in order; stop at first failure)

1. **Distribution-shift gate.** Does the conditional ensemble (2a) differ from the
   unconditional null fan (2b)? Test the **terminal-return** distribution AND the **path
   shape** — specifically max-favorable-excursion (MFE) vs max-adverse-excursion (MAE)
   profiles — via two-sample tests (e.g. KS / bootstrap on terminal bps and on MFE/MAE).
   **If the conditional fan is statistically indistinguishable from random-walk, STOP** — no
   geometry can help, learned cheaply.
2. **Geometry-beats-baseline gate.** Does any OOS-selected geometry cell beat the
   fixed-horizon baseline net of cost, with day-clustered significance and bootstrap CI
   clearing zero, pooled across pairs?
3. **Null gate.** The shuffled-label optimizer must NOT beat baseline, AND the selected
   geometry must survive BH-FDR.

GO requires all three. A plausible honest outcome (given Phase-1): gate 1 passes weakly,
gate 2 shows "stop helps a little, TP hurts," net marginal — a real documented finding either
way.

---

## 5. Phasing & reuse

- **Phase A** — engine: path ensemble (2a) + unconditional null (2b) + bracket evaluator (2c),
  unit-tested on synthetic paths. Run **gate 1 only** for both edges. Decision point.
- **Phase B** — optimizer + causal OOS + multiplicity; run gates 2–3. Both edges share the
  engine; each is a config (entries, horizon, σ source). The 2-3d reversion multi-day
  `hold_path` extension is the one new piece.
- **Phase C** (conditional) — add bootstrap / PF path augmentation ONLY if Phase A/B show the
  tails are too thin to estimate geometry ("simulator only if needed").

Reuses Phase-1: `pf_paths`, the panel/ridge pipeline (`reg_signal_hunt`, `tail_wfo`),
`day_clustered_tstat`, the year-block bootstrap, and the gauntlet-report style. New modules
under `scripts/fx_coint/` (`path_geometry_*.py`). Each phase = its own spec → plan → PR off
`main` in a worktree.

---

## 6. Out of scope (YAGNI)

- New-alpha discovery from path simulation (explicitly rejected — not the purpose).
- A full parametric simulator up front (deferred to Phase C, evidence-gated).
- Maker-fill modeling (these are taker stops/TP; maker fills are a separate, already-burned
  illusion — see prior FX range-band finding).
- Sub-minute / true tick-exact bracket ordering (1-minute mid with conservative
  stop-first tie-breaking is the resolution; revisit only if a GO survives this far).
- New timeframes or instruments beyond the six majors already in the pipeline.
