# FX Scalp Discovery — Staged Funnel Design

**Date:** 2026-06-20
**Status:** Draft — awaiting implementation plan
**Scope:** Discover a <30 min-horizon FX scalp edge at retail cost (Pepperstone Razor), using four untested signal families in a three-phase staged funnel.

---

## 1. Context

- Existing validated edges:
  - **2h tail-long momentum** (net +0.93 recent half, 5/5 positive years, day-clustered p=0.027) — strongest short-horizon edge.
  - **2–3 d mean-reversion** (+5.77 t2.47) — daily+ only.
- Everything at ≤1 h has been sub-cost or artifactual (100-tick scalping, hourly flow, fair-fade, ERA tick assessor).
- Key gap: ~15 computed microstructure columns exist in velocity dataset but never systematically evaluated at short horizons.
- Lesson: flow at hourly is a price echo; orthogonalized flow failed at hourly but untested at tick scale.
- Lesson: stale-bar artifacts from resampling tick-count bars → time bars can entirely explain a false edge. Use **true raw-tick time bars only**.

---

## 2. Goal

Find a <30 min standalone scalp signal that clears Pepperstone Razor retail cost, or determine conclusive NO-GO for all four families.

---

## 3. Architecture

Three-phase staged funnel:

```
Phase 0: Ridge-IC Sandbox  ──►  Phase 1: ERA Deep-Dive  ──►  Phase 2: Composite Overlay
(cheap, kills losers fast)         (top 2 families)            (merge winners)
```

### Phase 0: Ridge-IC Sandbox

- EURUSD 2024 data (true raw-tick time bars — **not** tick-count resampled).
- One script per family.
- Ridge regression + tail-selection grid.
- Evaluation: `net = gross − cost` using Pepperstone Razor `DEFAULT_COST_BPS`.
- Rank by `net_lb95` after cost.

### Phase 1: ERA Deep-Dive

- Dedicated seed set per surviving family (max 2).
- PUCT forest + LLM writer + repo-metric judge.
- Embargo: 2018–23 train / 2024 val / 2025–26 holdout.
- BH-FDR at α=0.10.
- `task_score` unchanged (net_lb95 × month_weight × n_weight).

### Phase 2: Composite Overlay

- Merge winning Phase-1 seeds into multi-family scalp program.
- Cross-val on 6 pairs × full history.
- Two deployment modes:
  - (a) **Standalone scalp** if net clears cost independently.
  - (b) **Timing overlay on 2h tail-long** to tighten entry / reduce adverse selection.

---

## 4. Phase 0 — Four Signal Families

### Family A: Tick-Scale Flow Orthogonalization

**Hypothesis:** The price-correlated part of flow predicts continuation; the orthogonal residual may predict reversion. At tick scale the residual may carry microstructure alpha invisible at hourly.

**Feature recipe:**
1. Compute `flow_tick` (Lee-Ready) and `flow_ofi` (Cont-style) on raw ticks via `scripts/fx_coint/flow_proxies.py`.
2. Causal rolling regression: `flow = β₀ + β₁ · mid_ret + residual` over trailing window (e.g., 5 min ≈ 500 ticks at typical EURUSD rate).
   — Fit β on `flow_tick` and `mid_ret` within each 5-min bar, using only bars ≤ t−1.
3. Signal = `flow_resid`.
4. Target = forward `mid_ret` at horizon h ∈ {1, 3, 5, 10} min.
5. Entry gate: top-decile |`flow_resid|` using causal expanding quantile.

**Kill criteria:** `net_lb95 ≤ 0` **or** entries < 20 / day.

**Near-miss criteria:** `0 > net_lb95 ≥ −cost_bps` AND (gross IC > 0.03, t > 2.0 OR decile spread ≥ 2× cost OR strong sign stability).

### Family B: Quote-Revision Continuation

**Hypothesis:** Sequences of same-side quote revisions (bid↑ or ask↓) indicate informed flow. High `quote_revision_rate_z` predicts continuation when combined with directional persistence.

**Feature recipe:**
1. Use `quote_revisions` count per bar from velocity dataset; normalize to `quote_revision_rate_z`.
2. Combine with `directional_persistence_8` (same-side quote streak length).
3. Signal = `quote_revision_rate_z × sign(directional_persistence_8)`.
4. Gate: `quote_revision_rate_z > 1.0` AND `directional_persistence_8` above causal expanding median.
5. Target = forward `mid_ret` at h ∈ {1, 3, 5} min.

**Kill / near-miss criteria:** same as Family A.

### Family C: Temporal Lead-Lag (Peer Returns)

**Hypothesis:** During London/NY overlap, price discovery flows from liquid peers (EURUSD, GBPUSD) to laggards (USDCAD, AUDUSD). Lagged peer returns predict target return.

**Feature recipe:**
1. Pool 6 majors; for each target, use leave-one-out peer returns lagged 1–3 **1-min bars**.
2. Causal rolling ridge on peer panel → fitted value.
3. Signal = fitted peer-return contribution.
4. Gate: `vol_cluster_score > 1` (high-vol cluster periods).

**Kill / near-miss criteria:** same as Family A.

### Family D: Microstructure Cocktail

**Hypothesis:** Untapped velocity columns carry combinatorial edge when screened together.

**Feature recipe:**
1. Feed all `WHITELIST` columns from `scripts/era_scalp/load_splits.py` into Ridge classifier:
   `spread_pips`, `spread_z`, `tick_volume`, `tick_rate_hz`, `tick_rate_z`, `tick_burst`, `tick_burst_score`, `high_pos_tick`, `low_pos_tick`, `hl_pos_delta_tick`, `bar_return_sign`, `vel_pips_h1`, `vel_pips_h2`, `vel_pips_h5`, `vel_pips_h10`, `vel_z_h1`, `vel_z_h2`, `vel_z_h5`, `vel_z_h10`, `accel_pips`, `hour_utc`, `range_pips`, `signed_flow_24`, `directional_persistence_8`, `intra_bar_momentum`, `quote_revision_rate_z`, `vol_cluster_score`, `slip_proxy_pips`, `hl_pos_frac`.
2. Target = `sign(fwd_ret)` at h ∈ {1, 3, 5} min; use class weights.
3. Entry = bars where `abs(prob - 0.5)` is in top decile (causal expanding); side = `sign(prob - 0.5)`.

**Kill / near-miss criteria:** same as Family A.

---

## 5. Phase 0 Evaluation Metric

All families use identical scoring:

```python
cost_frac = cost_bps / 10_000                   # Pepperstone Razor round-trip per trade
net = side * fwd_ret - cost_frac
net_lb95 = mean(net) - 1.645 * std(net) / sqrt(N)
survival = net_lb95 > 0 and N_entries >= 20 / day
near_miss = (0 > net_lb95 >= -cost_frac) and any([
    gross_IC > 0.03 and t_stat > 2.0,
    extreme_decile_spread >= 2 * cost_frac,
    same_sign_IC > 0.02 across {1, 3, 5} min,
    time_of_day_lift >= 2.0,
])
```

**Near-miss tier rules:**
- A family qualifies as near-miss if **net is sub-cost but gross structure is predictive**.
- Advancement rule: near-miss families enter Phase 1 **only if fewer than 2 families PASS outright**.

---

## 6. Phase 1 — ERA Deep-Dive

### Data

- Raw-tick time bars, 6 pairs, 2018–2026.
- Horizons: {1, 3, 5} min.
- Cost: Pepperstone Razor `DEFAULT_COST_BPS` per symbol.

### Seeds

Hand-crafted kernels + top ridge coefficients from Phase 0. Example for Family B:

```python
SEEDS = {
    "qr_raw":        "qr_z * sign(dp_8)",
    "qr_momentum":   "ewma(qr_z, 5) * ewma(dp_8, 3)",
    "qr_volgate":    "qr_z * sign(dp_8) where vol_cluster > 1",
    "qr_spreadgate": "qr_z * sign(dp_8) where spread_z < -0.5",
    ...
}
```

### Harness Adaptations

- `evaluate_residual`: `cost_bps` injected per-symbol.
- `task_score`: unchanged formula (net_lb95 × month_weight × n_weight).
- `thresholds` grid: expanded for min-horizon signals.
- BH-FDR multiplicity: α = 0.10 (relaxed vs 0.05 for faint scalp signals).
- Šidák correction for program-count multiplicity.

### Causality Probe

Re-use existing `causality_probe` in `scripts/era/sandbox.py`; ensure all rolling/ewm features end at `t-1`.

---

## 7. Phase 2 — Composite Overlay

### (a) Standalone Scalp

If Phase 1 yields `holdout net_lb95 > 0` independently:
- Deploy as new ERA program.
- Cross-val on 6 pairs × full history.

### (b) Timing Overlay on 2h Tail-Long

If standalone is marginal:
- Scalp signal narrows entry timing *within* validated 2h trades.
- Example: 2h model says "go long at 14:00"; scalp overlay says "wait 5–15 min for quote-revision + flow-alignment."
- Expected benefit: reduces adverse selection by ~20–30% of entries.

**Mechanism:** Logistic ensemble of family residuals + regime gate.

---

## 8. Look-Ahead Guards

Hard rules for all phases:

1. **No `bfill` on flow** — proved lookahead in `demonstrate_bfill_lookahead*.py`.
2. Close/mid/ask are from the **previous bar** (`.shift(1)`).
3. Forward returns computed from `mid[t+h]` with `mid[t]` as base only.
4. Any `rolling`/`ewm` window ends at `t-1`.
5. ERA `causality_probe` validates each generated program statically.

---

## 9. Cost Model

Import directly from `scripts/fx_coint/hourly_triple_barrier.py`:

```python
DEFAULT_COST_BPS = {
    "EURUSD": 0.64,
    "GBPUSD": 0.80,
    "AUDUSD": 0.88,
    "USDJPY": 0.72,
    "USDCHF": 0.88,
    "USDCAD": 0.88,
}
```

At <30 min horizons we assume **taker fills** (crossing spread). If any family approaches break-even, sensitivity to maker-assumption can be tested, but baseline is taker-only.

---

## 10. Success Criteria & Stopping Rules

| Outcome | Definition |
|---------|-----------|
| **PASS** | Any family: holdout `net_lb95 > 0`, N ≥ 20 / day, 6 pairs, pooled p < 0.05 |
| **PARK** | Near miss: gross IC clears cost, net sub-cost after spread; needs regime gate or model complexity |
| **NO-GO** | All families dead at Phase 0; 0 near-miss; conclusively sub-cost |

**Budget caps:**
- Phase 0: 4 scripts × ~30 min = ~2 hrs wall-clock.
- Phase 1: max 2 families × ERA overnight = ~16–24 hrs.
- Total: ~1–2 days.
- **Kill switch:** If Phase 0 yields 0 PASS **and** ≤ 1 NEAR MISS, stop. Do not burn ERA budget.

---

## 11. Deliverables

1. `scripts/fx_coint/phase0_scalp_funnel.py` — master runner; executes all 4 families; emits `phase0_results.json`
2. `scripts/fx_coint/phase0_family_a.py` — Tick-Scale Flow Orthogonalization
3. `scripts/fx_coint/phase0_family_b.py` — Quote-Revision Continuation
4. `scripts/fx_coint/phase0_family_c.py` — Temporal Lead-Lag (Peer Returns)
5. `scripts/fx_coint/phase0_family_d.py` — Microstructure Cocktail
6. `docs/superpowers/specs/2026-06-20-fx-scalp-discovery-design.md` — this document
7. Per-surviving-family PR (Phase 1) or composite PR (Phase 2)

---

## 12. Risks & Mitigations

| Risk | Likelihood | Mitigation |
|------|-----------|------------|
| Stale-bar artifact on flow features | Medium | Enforce true raw-tick time bars; never resample tick-count → time bars |
| Lookahead via `bfill` or `rolling(center=True)` | Medium | Static `causality_probe`; code review for `.shift(1)` on all norm features |
| Overfitting at tick scale (N huge, p-values deceptive) | High | Non-overlap IC sampling; BH-FDR; Šidák; block-bootstrap CIs |
| One dead family poisons composite | Low | Phase 0 kills losers; Phase 2 only merges verified winners |
| Near-miss bias (interpreting noise as structure) | Medium | Hard near-miss thresholds; automatic advancement rules (not subjective) |

---

## 13. Open Questions

1. Do raw-tick 1-min time bars already exist for EURUSD 2024, or must we run `build_rawtick_timebars.py`?
2. Should the 2h tail-long overlay integration happen in the same PR or a follow-up?
3. If 0 families pass but 2+ are near-miss, do we advance the top 2 anyway, or reserve ERA for a different experiment?

These should be resolved before Phase 1 begins.
