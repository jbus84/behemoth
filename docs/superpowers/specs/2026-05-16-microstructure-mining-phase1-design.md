# Microstructure Signal Enrichment for Opportunity Mining — Design Spec

> **Status:** Approved by jbus84 (2026-05-16)  
> **Scope:** Phase 1 — Mining-Only (no CatBoost schema change yet)  
> **Plan:** `docs/superpowers/plans/YYYY-MM-DD-microstructure-mining-phase1.md`

---

## 1. Goal

Augment the Stage 02 Opportunity Mining pipeline with microstructure-derived regime filters so that candidates are mined only during favorable tick-level states (event intensity, signed flow persistence, volatility clustering, session). Phase 1 does **not** change the CatBoost feature schema — it enriches candidate selection only. Signals that prove valuable here will be promoted into the model feature vector in Phase 2.

## 2. Background

The OCO candidate mining pipeline currently emits one family (`oco_first_touch`) across regimes (`all`, `low_cost_q30`, `high_range_q70`, `london`, `ny_overlap`, `asia`). These regimes are based on cost, range, velocity, and session — but they do not exploit market microstructure dynamics (order flow, self-excitation, volatility clustering) that are known to drive short-horizon FX price formation.

Research at the 100–1000 tick horizon shows that:
- **Self-excitation / Hawkes effects** (clustered arrivals, trade cascades)
- **Signed trade flow persistence** (long-memory sign autocorrelation)
- **Regime / session structure** (London open, NY overlap, rollover)
- **Volatility clustering / rough volatility** (burst persistence)

dominate directional prediction at these horizons. The mining pipeline currently ignores these signals.

## 3. Constraints

- **No look-ahead.** Every signal must be computable at decision time from historical bars only.
- **Additive only.** New regimes are additional candidate rows; existing regimes (`all`, etc.) must continue to be mined.
- **Library-agnostic.** Same regime definitions apply to both OCO and directional libraries.
- **No model change.** CatBoost feature schema stays at 16 features for Phase 1. New columns flow through to the ML parquet but are not consumed by the model.
- **Empirical validation.** New regimes must produce candidates with comparable or better train mean gross than the `all` baseline.

## 4. Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│  LAYER 3: MICROSTRUCTURE REGIMES (NEW)                            │
│  New candidate families filtered by signal state                     │
│  e.g., oco_first_touch__high_intensity__k5                         │
│  e.g., directional__persistent_flow__k5                             │
└──────────────────┬────────────────────────────────────────────────┘
                   │
┌──────────────────┴────────────────────────────────────────────────┐
│  LAYER 2: MICROSTRUCTURE SIGNALS (NEW)                          │
│  Added as columns to the velocity dataset                         │
│  Computed causally, fully lagged, no forward info                 │
│  Signals: event_intensity, signed_flow, session_state, vol_cluster│
└──────────────────┬────────────────────────────────────────────────┘
                   │
┌──────────────────┴────────────────────────────────────────────────┐
│  LAYER 1: BAR BUILDER (EXTENDED)                                 │
│  Existing: hl_first, hl_pos_frac, spread, tick_volume           │
│  New: intra-bar directional skew, quote revision rate             │
└──────────────────────────────────────────────────────────────────┘
```

## 5. Signals

### 5.1 Bar-level Pre-Aggregates (computed in `build_global_tick_bars.py`)

| Column | Definition | Why |
|--------|------------|-----|
| `bar_return_sign` | `+1` if close_bid[t] > close_bid[t-1], `-1` if <, `0` if equal | Per-bar directional tick rule proxy |
| `tick_burst` | `tick_volume / rolling_24_median(tick_volume)` | How many ticks this bar vs recent baseline |
| `quote_revisions` | Count of quote direction changes within the bar | Dealer hedging / inventory adjustment proxy |
| `intra_bar_momentum` | `hl_first * (range_pips / rolling_24_median(range_pips))` | Weighted intra-bar direction |

### 5.2 Velocity Dataset Signals (computed in `build_tick_velocity_dataset.py`)

All rolling windows are **strictly lagged** (`shift(1)` after the rolling mean).

| Column | Formula | Interpretation |
|--------|---------|----------------|
| `tick_burst_score` | `(tick_burst - rolling_24_mean(tick_burst)) / rolling_24_std(tick_burst)` | Z-score: is this bar abnormally active? |
| `quote_revision_rate_z` | `(quote_revisions - rolling_24_mean) / rolling_24_std` | Z-score: are quote revisions elevated? |
| `directional_persistence_8` | Rolling sum of `bar_return_sign` over 8 bars | How persistent is the recent flow? (+8 = all up, -8 = all down) |
| `signed_flow_24` | Rolling sum of `bar_return_sign` over 24 bars | Cumulative directional pressure |
| `vol_cluster_score` | `abs(vel_pips_h1) / rolling_24_mean(abs(vel_pips_h1))` | Is current volatility elevated vs recent? |

`vel_pips_h1` is the close-to-close pip return. It is used in place of an
open-to-close `ret1_pips`: the bars frame does not reliably carry that column,
and a close-to-close magnitude is an equally valid volatility-clustering proxy.
| `session_marker` | Categorical: `tokyo`, `london`, `ny`, `overlap`, `rollover` | Which FX session is active? |

## 6. New Regime Filters

Applied in `run_tick_opportunity_mining.py` alongside existing regimes.

| Regime | Condition | Rationale |
|--------|-----------|-----------|
| `high_intensity` | `tick_burst_score >= train_q70` | Above-baseline activity often precedes directional moves |
| `high_activity` | `quote_revision_rate_z >= train_q70` | Elevated quote revisions signal dealer hedging |
| `persistent_flow` | `directional_persistence_8 >= 6` | Strong persistent order flow creates short-term drift |
| `negative_flow` | `directional_persistence_8 <= -6` | Strong persistent sell pressure |
| `high_vol_cluster` | `vol_cluster_score >= train_q70` | Vol clustering predicts continued activity |

All conditions use **lagged** signals only. The regime mask for bar `t` is computed from bars `<= t-1`.

**Threshold derivation.** `high_intensity`, `high_activity` and `high_vol_cluster`
use a **train-derived q70 cut** — `train[signal].quantile(0.70)`, computed in
`_quantiles(train)` and applied to both the train and test frames. This is
consistent with the cost/range/vel regimes (`cost_q30`, `rng_q70`, `vel_q70`)
and means each regime selects a stable ~top-30% of bars regardless of how the
signal distribution varies across symbols or volatility regimes. The threshold
is never recomputed on the test frame, so there is no test leakage.

`persistent_flow` / `negative_flow` keep a **fixed +/-6 cut**: `directional_persistence_8`
is a bounded integer count over 8 bars (range `[-8, +8]`), so `>= 6` / `<= -6`
is interpretable (at least 6 of the last 8 bars agree in direction) and
distribution-independent — a quantile cut would add no value.

## 7. Candidate Metadata Enrichment

Each candidate row gains new per-candidate train statistics:

| New Column | Description |
|------------|-------------|
| `mean_tick_burst_train` | Mean `tick_burst_score` over train events |
| `mean_flow_persistence_train` | Mean `directional_persistence_8` over train events |
| `mean_vol_cluster_train` | Mean `vol_cluster_score` over train events |
| `session_coverage` | Fraction of train events in each session |

## 8. Data Flow

### Build time

```
Raw ticks (bid/ask)
    │
    ▼
[build_global_tick_bars.py] ──► Tick bars with new microstructure columns
    │
    ▼
[build_tick_velocity_dataset.py] ──► Velocity dataset with new signal columns
    │
    ▼
[run_tick_opportunity_mining.py]
    • For each (horizon, barrier, regime, library):
      - Apply regime mask (causal, lagged)
      - Precompute outcomes on masked bars
      - Compute train/test metrics
      - Assign quality tier
      - Emit candidate row
    │
    ▼
[build_tick_opportunity_ml_dataset.py]
    • Join candidates with velocity features
    • Emit ML event parquet (new columns present but not consumed by model)
```

### Mining time (production inference)

```
Live ticks
    │
    ▼
[bar_alignment.py] ──► Real-time tick bars with same new columns
    │
    ▼
[compute_feature_matrix_from_bars] ──► Feature vector (16 features, unchanged)
    │
    ▼
[PredictionOrchestrator]
    • Resolve candidates from registry
    • Check regime membership (is current bar in candidate's regime?)
    • Run CatBoost inference (unchanged)
    • Apply threshold + regime gate
    • Return predictions
```

## 9. Error Handling & Safety

| Risk | Mitigation |
|------|------------|
| Look-ahead in microstructure signals | All signals use `rolling().mean().shift(1)` — strictly lagged |
| Regime mask uses future information | Regime thresholds computed from train frame only |
| New regimes break existing candidates | `all` regime always mined; new regimes are additive |
| Signal computation raises on edge cases | NaN/inf replaced with 0; insufficient history returns neutral value |
| Candidate explosion | Max 5 new regimes per library; governed by contract test |

## 10. Testing Strategy

| Test | What it verifies |
|------|------------------|
| `test_microstructure_signals_are_causal` | Perturbing a future bar leaves every earlier-bar signal unchanged (real velocity-builder run) |
| `test_regime_thresholds_are_train_derived` | Microstructure q70 thresholds come from the train frame, never the frame the mask is applied to |
| `test_high_intensity_regime_is_a_train_q70_subset` | `high_intensity` selects the train-q70 top-~30% and is a strict subset of `all` |
| `test_directional_persistence_regimes_stay_fixed` | `persistent_flow` / `negative_flow` keep the fixed +/-6 cut, not a quantile |
| `test_new_regimes_are_additive` | Mining still produces `all` regime candidates; new regimes are extra rows |
| `test_microstructure_candidate_quality_vs_baseline` | Each new regime mines a finite train mean gross comparable against the `all` baseline |
| `test_directional_and_oco_both_mine_new_regimes` | Both libraries produce candidates for each new regime |
| `test_ml_dataset_includes_microstructure_columns` | ML parquet contains new columns even though model doesn't consume them |

The spec's >=60%-beats-baseline success criterion (Section 13) is validated on
real mined data by `scripts/run_microstructure_diagnostics.py`, not by a unit
test — synthetic random signals cannot establish a quality edge.

## 11. Files Changed

| File | Change |
|------|--------|
| `scripts/build_global_tick_bars.py` | Add `bar_return_sign`, `tick_burst`, `quote_revisions`, `intra_bar_momentum` |
| `scripts/build_tick_velocity_dataset.py` | Add `tick_burst_score`, `quote_revision_rate_z`, `directional_persistence_8`, `signed_flow_24`, `vol_cluster_score`, `session_marker` |
| `scripts/run_tick_opportunity_mining.py` | Add 5 new regime masks; compute per-regime microstructure stats in candidate rows |
| `scripts/build_tick_opportunity_ml_dataset.py` | Pass new columns through to ML parquet |
| `src/behemoth/core/features.py` | Add signal computation helpers (shared with runtime) |
| `src/behemoth/runtime/bar_alignment.py` | Compute same new bar columns at runtime |
| `tests/test_microstructure_regimes.py` | (new) Contract tests for causality and quality |
| `scripts/run_microstructure_diagnostics.py` | (new) Post-mining diagnostic report |

## 12. Out of Scope (Phase 2)

- Changing the CatBoost feature schema from 16 features
- Adding microstructure signals as model inputs
- Hyperparameter re-optimization
- Threshold recalibration (`W13_threshold_fragility`)
- Ensemble models or alternative architectures
- Online learning or incremental updates

## 13. Success Criteria

1. All existing regimes continue to mine successfully (additive only)
2. New regime candidates have `train_mean_gross_pips >= all_regime_baseline` for at least 60% of (symbol, horizon, barrier) combinations
3. Full test suite passes (no regressions)
4. `make quality` passes
5. Diagnostic report confirms new regimes are active and have non-trivial coverage

## 14. After Phase 1

Phase 2 (future project) will:
1. Review the diagnostic report to identify the top 3-4 validated microstructure signals
2. Promote them into the canonical 16-feature CatBoost schema
3. Retrain models with the expanded feature set
4. Benchmark against the Phase 1 baseline

---

*Design approved: 2026-05-16*
*Next step: Write implementation plan via `/superpowers:writing-plans`*
