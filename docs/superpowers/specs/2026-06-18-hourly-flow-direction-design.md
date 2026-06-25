# Hourly FX flow → next-bar direction (aeon TS models)

**Date:** 2026-06-18
**Status:** Design approved, pending spec review
**Scripts area:** `scripts/fx_coint/`

## Context

Hourly EURUSD **next-bar direction is dead on price-only features**: dirAcc 0.489–0.504
across MRHydra + QUANT + RDST × single/5-seed/15-stack on the drift-immune rolling-tercile
label (see memory `project_fx_hourly_nextbar_direction`). The earlier "+0.75 Sharpe" was
bias × the 2024-H2 EUR downtrend, not skill. The magnitude axis is predictable (QUANT
balAcc 0.41) but unmonetizable (variance risk premium ≈ 0; straddle net −0.62 bps).

Every panel so far **excluded order-flow** (`flow_tick`, `flow_ofi`, `n_ticks`, `rvol_bps`,
`spread_bps` are in the shared `EXCLUDE` set). Price reflects what already happened; flow
reflects pressure about to move price. Flow is the one untested input class that could carry
short-horizon direction. The aeon TS models (QUANT quantile features, MRHydra convolutions,
RDST shapelets) are the chosen learners.

## Hypothesis

Order-flow carries **price-independent** next-k-bar directional information that price-only
features lack.

## Decision gate

Flow "works" only if, on held-out WFO trades, a horizon cell shows **either**:
- pooled **dirAcc 95% CI excludes 0.50**, OR
- pooled **signed-return net 95% CI excludes 0** (net of cost),

**after multiplicity correction** across the {horizon} × {feature-arm} grid (Šidák/BH).
Significance uses the pooled-trade block-bootstrap from `hourly_pooled_decomp`
(`moving_block_bootstrap_ci`) — NOT averaging per-window t-stats (that metric was shown to
be noise this session: KS↔Sharpe correlation flipped sign −0.95 → +0.66 on n=6).

## Approach: staged (B)

Phase 1 (single-pair EURUSD, full grid, gate) → Phase 2 (cross-sectional, only if a cell
clears).

## Section 2 — Feature set (all causal)

**Raw channels** (un-exclude, causal rolling-z normalised, shifted):
`flow_tick`, `flow_ofi`, `n_ticks`, `rvol_bps`, `spread_bps`.

**Engineered channels** (microstructure priors, all causal):
- **Cumulative/persistent flow** — rolling signed sum of `flow_tick` and `flow_ofi` over k bars.
- **Flow momentum** — Δflow (change in `flow_ofi`/`flow_tick`).
- **OFI z-score** — causal rolling z of `flow_ofi`.
- **Activity-weighted flow** — `flow_tick × n_ticks`.
- **Flow–price divergence (key channel)** — `flow_ofi` orthogonalised to the *contemporaneous*
  return via causal rolling regression residual. Isolates flow pressure NOT already in price
  — the only part that can predict the next move. Directly targets the prior trap
  (`project_fx_flow_factor_deviation`: "the only flow signal was the part echoing price").

**Feature-set arms** (for attribution):
`price_only` (control, = 0.50 baseline) · `+raw_flow` · `+engineered` · `+both`.

## Section 3 — Label, harness, controls

**Label:** generalise `label_next_bar_tercile` to horizon h — forward h-bar return, rolling
causal terciles (W=500). Preserves balance (33/33/33), stationarity, and drift-immunity at
every h. One label per horizon.

**Harness:** reuse `hourly_nextbar_eval` WFO (6mo train / 1mo test). Pooled metrics: dirAcc,
balAcc, directional precision (+1/−1), signed-return net (pred × fwd_bps − cost) with
block-bootstrap CI, positive-month %. Grid = {1,3,6h} × {4 arms}. **QUANT-led** (best
magnitude skill, only graded predict_proba); MRHydra + RDST as cross-checks.

**Controls (non-negotiable):**
1. Causality audit — flow at t known at close of t; predict t+1..t+h. No forward leakage in
   any rolling/orthogonalisation op (use `.shift(1)` on all trailing stats).
2. **Multiplicity** — Šidák/BH correction across the 12-cell grid before declaring any cell sig.
3. **Price-only control arm must stay ≈ 0.50** — proves the harness isn't leaking; flow lift
   is measured relative to it.
4. **Orthogonalised-flow attribution** — if `+both` beats `+raw_flow`, the divergence channel
   carries it (price-independent signal); if not, flow is just echoing price again.

## Section 4 — Phases & exit

- **Phase 1:** EURUSD, full grid, apply gate. No cell clears → documented NO-GO (flow does
  not rescue hourly direction); stop and record in memory.
- **Phase 2 (only if a cell clears):** cross-sectional flow (EURUSD flow − USD-basket mean
  flow per bar) added as channels; re-run at winning horizon; confirm OOS across pairs and
  out-of-year.

## Out of scope (YAGNI)

- Monetisation/execution modelling (gate is signal-level; cost included only as a net check).
- New model families beyond the three aeon classifiers.
- Sub-hourly bars or new data builds (use existing `data/tick_bars/<SYM>_1h_flow.parquet`).

## Deliverables

- `hourly_flow_features.py` — engineered flow channel builder (causal).
- generalised horizon-h tercile labeler (extend `hourly_nextbar_label.py`).
- `hourly_flow_direction_eval.py` — grid WFO harness + pooled gate + multiplicity.
- Results write-up + memory update (GO/NO-GO).
