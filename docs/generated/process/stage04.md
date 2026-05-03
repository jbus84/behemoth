# Stage 04 Stop-Limit Realism

Stage ID: `stage04`

Applies Stop-Limit Realism analysis to scored opportunities using overshoot, fill, cost, and no-touch execution semantics.

## Canonical Commands

- `make onboard-symbol`

## Required Inputs

- `data/analysis/tick_opportunity_mining/wfo_m3to1_oco_fullcap_${symbol}/${SYMBOL}_oco_monthly_predictions.parquet`
- `data/analysis/tick_velocity/${SYMBOL}_{100,1000,2000}tick_velocity.parquet`

## Produced Evidence

- `data/analysis/tick_opportunity_mining/stop_limit_tickfill_fullcap/${SYMBOL}_oco_stop_limit_tickfill_summary.csv`
- `docs/analysis/oco_stop_limit_tickfill_fullcap_report.md`

## Gates

- `stop_limit_realism_pass`: `PASS_FAIL`, severity `critical`

## Implementation Scope

- `Makefile` (registry)
- `scripts/analyze_oco_stop_limit_tickfill.py` (registry)
- `scripts/onboard_symbol.py` (registry)

## Tests

- `tests/test_oco_precompute_spread.py`
