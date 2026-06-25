# Task 4 Report: Three Decision-Rule Net Economics

## Status
COMPLETE

## Commit
`8a26ca2a` — feat(fx_coint): three decision-rule net economics

## Test Summary
- `test_eval_rules_cost_gating`: PASSED
- All 5 tests in `test_reg_signal_hunt.py`: PASSED

## Implementation Details

Added `eval_rules(pred_bps, actual_bps, cost_bps, size_cap=3.0) -> dict` to `scripts/fx_coint/reg_signal_hunt.py`:

- **Rule A (always-trade)**: `netA = mean(sign(pred)*actual) - cost`
- **Rule B (TP-sized)**: `netB = mean(w*actual) - mean(|w|)*cost`, where `w = clip(pred/median(|pred|), -cap, cap)`
- **Rule C (cost-gated)**: `netC = mean over trades where |pred|>cost of (sign(pred)*actual - cost)`

Returns dict with keys: `netA`, `netB`, `netC`, `n_trades_C`, `n_bars`.

Test covers:
1. Perfect predictor: all predictions exceed cost, netA matches expected mean absolute movement minus cost
2. Cost-gating: sub-cost predictions correctly excluded from Rule C trade count

## Concerns
None. Implementation matches brief exactly; test passes; all existing tests still pass.
