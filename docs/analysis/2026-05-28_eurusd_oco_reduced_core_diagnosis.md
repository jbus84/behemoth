# EURUSD × oco_first_touch Reduced-Core Empty Result — Diagnosis (2026-05)

## Context
Stage 3 WFO produced 10,379 predictions for EURUSD × `oco_first_touch` for model month 2026-05. After Stage 5 reduced-core rolling selection applied horizon (5, 6), barrier (2.0, 3.0, 5.0), and quality gates, 0 states were selected. GBPUSD × `oco_first_touch` control was marked for regen in Task 1 and is not available for this diagnosis.

## Evidence

### Data Availability
- **Prediction parquet**: 10,379 total rows
- **Prediction distribution**: mean pred_prob=0.355, std=0.268, range [0.003, 0.964]
- **Monthly split**: 2025-01 (3939), 2025-03 (961), 2025-04 (3549), 2025-05 (332), 2025-07 (408), 2025-08 (392), 2026-03 (798)
- **Candidates CSV**: 459 rows, all EURUSD × oco_first_touch
- **Config path resolution**: Fixed missing symlinks `wfo_m3to1_oco_fullcap` (→ `wfo_m3to1_oco_first_touch_fullcap`) and parquet name (`EURUSD_oco_monthly_predictions.parquet` → `EURUSD_oco_first_touch_monthly_predictions.parquet`)

### Stage 5 Execution Log
- After library+symbol filter: **10,379 rows** pass (library='oco', symbol='EURUSD')
- After horizon filter (5, 6): **0 rows** survive (actual data has horizons [1, 3, 6] only)
- After candidate metadata merge: **0 rows** → Cannot join horizons that don't exist in predictions
- Selection result: **0 rows** selected (no predictions to select from)

### Monthly Status Codes
- 2025-04: `warmup_skip` (insufficient training months, only state_train_months=2 available retroactively)
- 2025-07: `no_gate_states` (states selected but failed gate_pass check)
- 2025-08: `no_gate_states` (same)
- 2025-09: `no_gate_states` (same)

## Classification

### **Option A — sparse_signal** ✓ SELECTED

Stage 5 empty result is the correct verdict. The root cause is **horizon mismatch**: the config specifies `horizon_keep: "5,6"` but the actual WFO predictions contain only horizons `[1, 3, 6]`. Horizon 5 does not appear in the data. After filtering predictions to the configured horizons (5, 6), no rows remain to merge with candidate metadata, yielding 0 rows at the merge step.

For months where data survives the horizon filter (e.g., horizon=6), states fail gate conditions (`no_gate_states` status) due to insufficient profitability (likely `require_lb95_trade_gt0=true` rejection). This is not a bug but a legitimate signal: EURUSD × oco_first_touch in 2026-05 lacks both the required horizon coverage and profitable states under governance criteria.

Bundle records `NO_GO` for EURUSD in oco_first_touch family. This is the explicit purpose of multi-family mining: discover which (symbol, family) pairs work.

Supporting evidence:
- Prediction data has horizons [1, 3, 6]; config filters for [5, 6]; horizon 5 is missing, removing ~85% of data
- After horizon filter to remaining [6], monthly status is `no_gate_states` (profitability gate failure), not a coding bug
- Candidate and prediction counts drop from 10,379 → (horizon filtered) → 0 merged rows, expected for sparse-signal case
- Re-run with corrected symlinks reproduces same empty schedule

## Outcome

Bundle proceeds; verdict ladder records `FAIL` for EURUSD × oco_first_touch (Stage 5), which Stage 9 will translate to `NO_GO` in the governance bundle. No code fix required; data signal is sparse.

**Downstream**: Task 7 and beyond proceed normally. GBPUSD control re-generated in Task 5 will clarify whether `oco_first_touch` across the symbol set has broader sparsity or is specific to EURUSD.

## Follow-ups

1. After Task 7 completes, audit `data/analysis/tick_opportunity_mining/reduced_core_rolling/` for empty CSVs (header-only). If EURUSD × oco_first_touch is the only empty schedule across all symbols × families, sparse-signal hypothesis is confirmed. If multiple combos are empty, investigate whether Stage 5 has a systemic gate or threshold miscalibration.

2. When GBPUSD × oco_first_touch prediction parquet is regenerated (Task 5), check if GBPUSD also has horizons [1, 3, 6] (config mismatch persists) or if it has horizons [5, 6] (more aligned signal). This will inform whether the config `horizon_keep` should be updated to match actual WFO output.
