# Rolling Threshold Equivalence Design

## Summary

The live system's rolling 90th percentile threshold does not match the WFO backtesting computation. WFO uses only training predictions in the rolling pool, while live seeding replays recent market data through the model — a different population. Additionally, WFO does not accumulate prior test-day predictions into the rolling pool, causing the threshold to degrade to a static fallback midway through the test month. This design aligns the two systems so they produce identical thresholds.

## Problem Statement

Three structural mismatches exist between WFO and live threshold computation:

1. **WFO rolling pool degrades.** The 20-day lookback window slides forward with each test day but only collects from training predictions. By ~20 days into the test month, the window has moved entirely past the training boundary and falls back to the full training set quantile. This means the threshold is not truly "rolling" for most of the month.

2. **Live seeding uses the wrong population.** The `/state/seed_audit_history` endpoint replays 20 days of Dukascopy parquet through the model to populate `audit_logs`. These are predictions on recent market data, not on the training set. The resulting 90th percentile may differ from what WFO computed.

3. **Stage 14 does not validate threshold parity.** It certifies signal and execution parity but never checks whether the live threshold matches WFO.

## Goals

- Make WFO and live produce identical rolling thresholds for the same test day, given the same prediction history.
- Eliminate information leakage: no prediction may influence its own acceptance threshold.
- Ensure the live system can bridge data gaps (restart mid-month) without breaking threshold parity.
- Extend stage 14 to certify threshold parity.

## Non-Goals

- No changes to the CatBoost model, feature pipeline, or parquet schema.
- No changes to the trade execution or OCO lifecycle.
- No changes to the monthly retrain cadence or promotion flow.
- The `threshold_schedule` continues to be exported. Its role changes from primary threshold source to validation reference for stage 14.

## Design

### 1. WFO Change: Accumulate Test-Day Predictions

Modify `_rolling_day_threshold_vector()` in `scripts/run_tick_opportunity_monthly_wfo.py` so that after computing the threshold for test day D, the test predictions from day D are added to the rolling pool before processing day D+1.

Current behavior (lines 345-364): the loop iterates over test days but only ever collects from `train_items`. Test predictions are never added.

New behavior:

```
for each test_day D in sorted order:
    1. window = [D - 20 days, D)
    2. collect from pool where day in window
    3. if count < min_history: use full training fallback
    4. threshold[D] = quantile(collected, 0.9)
    5. ADD test predictions from day D to pool   ← new step
```

The causal constraint is preserved: day D's predictions are added *after* day D's threshold is computed, so they only influence day D+1 and beyond.

This keeps the rolling window populated throughout the entire test month instead of degrading to a static fallback. The `threshold_schedule` export continues to work as before — it captures the threshold for each test day — but the values will now reflect the accumulating pool.

The `threshold_exec` scalar (median of all schedule values) and `train_fallback` path remain as they are. The only change is that prior test-day predictions enter the rolling pool.

### 2. Export Training Predictions as Artifact

Add a new artifact to the WFO model export: the training predictions used to initialize the rolling pool.

File: `models/oco/{SYMBOL}_train_predictions_{YYYY-MM}.parquet`

Schema:

| Column | Type | Description |
|--------|------|-------------|
| `day` | `date` | Calendar day (floored from `close_ts`) |
| `pred_prob` | `float64` | Model prediction on training row |

This artifact is exported alongside the existing `.cbm` and `.json` files during WFO model export (lines 461-519 of the WFO script). It contains all finite training predictions grouped by day — the same data that `train_by_day` holds in the current code.

The live lock JSON (`artifacts` section) gains a new field:

```json
{
  "artifacts": {
    "train_predictions_path": "models/oco/EURUSD_train_predictions_2026-03.parquet",
    "train_predictions_sha256": "..."
  }
}
```

### 3. Two-Phase Live Seeding

Replace the current single-phase seeding (parquet replay) with two phases:

**Phase 1 — Training seed.** Load the exported training predictions parquet and write to `audit_logs`. This gives the rolling window the same starting pool that WFO had on test day 1.

**Phase 2 — Gap replay.** Replay test-month parquet data from day 1 of the test month up to the current timestamp. This fills in the predictions that would have accumulated if the system had been running since the start of the month. These predictions enter `audit_logs` and become part of the rolling pool, matching the WFO accumulation behavior.

On a fresh start at the beginning of the month, phase 2 produces nothing (no test-month data yet). On a mid-month restart, phase 2 bridges the gap. The 90th percentile over 20 days of predictions is robust to minor tick-level differences between parquet replay and live feed.

The seeding endpoint (`/state/seed_audit_history`) needs to accept the training predictions artifact path and distinguish between the two phases. The existing `days_back` parameter is replaced by explicit phase control.

### 4. Live Threshold: Rolling Computation as Authority

The rolling 90th percentile from `audit_logs` becomes the sole threshold source in live/governance mode. The priority order changes from:

```
Current:  threshold_schedule → rolling fallback → block
New:      rolling computation → block
```

The `threshold_schedule` is retained in the model JSON as a validation reference but is no longer used for live threshold lookup. The `get_rolling_threshold()` query in `state.py` remains unchanged — it already computes the 90th percentile over the last 20 days of `audit_logs`, which now contains the correct population (training predictions + accumulated test-day predictions).

The existing `min_history` guard (block if fewer than 1000 predictions in the window) provides operational safety. If the seeding failed or `audit_logs` is corrupted, the system blocks rather than trading with an unreliable threshold.

### 5. Stage 14 Extension: Threshold Parity Check

Add a new critical check to stage 14: `THRESHOLD_PARITY_PASS`.

The check:

1. Load the `threshold_schedule` from the model JSON (these are now WFO values computed with the accumulating pool).
2. For each date in the schedule, query the live system's rolling threshold via the API or by recomputing from the seeded `audit_logs`.
3. Compare. Pass if all values match within a tolerance of `1e-6` (accounting for float precision differences between NumPy and DuckDB quantile implementations).

This check runs as part of the existing stage 14 certification flow in `scripts/validate_stage14_jforex_runtime_certification.py`. It uses the schedule as a reference to verify the live rolling computation produces equivalent results.

### 6. Operational Guard: Month Expiry

If the current date is beyond the last date in the `threshold_schedule` AND the rolling window's `min_history` threshold is not met, the system blocks trading. This is already the existing behavior via the `min_history` guard — when the model expires and no retrain has occurred, the training predictions age out of the 20-day window, the rolling pool eventually falls below 1000, and trading halts.

To make this explicit rather than relying on natural decay:

- Add a `model_valid_through` date to the lock JSON (last date in threshold_schedule + 1 day grace).
- The prediction endpoint checks this date. If `now > model_valid_through`, block immediately with reason `MODEL_EXPIRED` rather than waiting for the rolling pool to decay.

## Error Handling

- If the training predictions artifact is missing at seeding time, seeding fails loudly. The system cannot start without it.
- If phase 2 (gap replay) fails, log the error and continue with phase 1 data only. The rolling pool may be slightly stale but will self-correct as live predictions accumulate.
- If the DuckDB quantile and NumPy quantile diverge beyond tolerance for the stage 14 check, investigate the interpolation method before widening tolerance.

## Testing Strategy

Required coverage:

- **WFO accumulation correctness:** Verify that adding test-day predictions to the pool changes the threshold for subsequent days compared to the old behavior. Use synthetic data where the difference is observable.
- **Causal boundary:** Verify day D's predictions never influence day D's threshold.
- **Training predictions export:** Verify the exported parquet matches `train_by_day` in the WFO pipeline.
- **Two-phase seeding:** Verify that seeding with training predictions + gap replay produces `audit_logs` content that yields the same rolling threshold as WFO's schedule.
- **Stage 14 threshold parity:** Verify the new check passes when thresholds match and fails when they diverge.
- **Month expiry block:** Verify the system blocks trading after `model_valid_through`.

Use synthetic timestamps, predictions, and small temporary parquet fixtures. No live network access required.

## File Changes

| File | Change |
|------|--------|
| `scripts/run_tick_opportunity_monthly_wfo.py` | Accumulate test-day predictions in rolling loop; export training predictions parquet |
| `src/behemoth/api/server.py` | Remove schedule-first threshold lookup in live mode; update seeding endpoint for two-phase flow |
| `src/behemoth/runtime/state.py` | Add `seed_training_predictions()` method for phase 1 loading |
| `scripts/validate_stage14_jforex_runtime_certification.py` | Add `THRESHOLD_PARITY_PASS` check |
| `scripts/run_jforex_live.py` | Pass training predictions path to seeding endpoint |
| Lock JSON schema | Add `train_predictions_path`, `train_predictions_sha256`, `model_valid_through` |

## Risks

- Changing the WFO rolling behavior will produce different `threshold_schedule` values for the same model. All downstream artifacts that depend on these values (locked predictions, reduced-core selection) must be regenerated. This is handled by the normal monthly retrain/recert cycle.
- The DuckDB `quantile()` function may use a different interpolation method than NumPy's `np.quantile()`. The stage 14 tolerance must account for this. If the divergence is systematic, align the interpolation methods explicitly.
- Adding test-day predictions to the WFO rolling pool changes the backtesting results. Existing backtest metrics will shift. This should be validated as an improvement (threshold stays responsive) rather than a regression.
