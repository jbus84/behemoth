# Stage 05 Reduced-Core Rolling

Stage ID: `stage05`

Converts Candidate State evidence into a leakage-safe rolling Shortlist and monthly Allowed State schedule.

## Canonical Commands

- `make onboard-symbol`

## Required Inputs

- `data/analysis/tick_opportunity_mining/wfo_m3to1_oco_fullcap_${symbol}/${SYMBOL}_oco_monthly_predictions.parquet`
- `data/analysis/tick_opportunity_mining/stop_limit_tickfill_fullcap/${SYMBOL}_oco_stop_limit_tickfill_detail.csv`
- `configs/research/experiments/${symbol}_oco_reduced_core_rolling.yaml`

## Produced Evidence

- `data/analysis/tick_opportunity_mining/reduced_core_rolling/${SYMBOL}_oco_reduced_core_rolling_summary.csv`
- `data/analysis/tick_opportunity_mining/reduced_core_rolling/${SYMBOL}_oco_reduced_state_schedule.csv`
- `docs/analysis/${symbol}_oco_reduced_core_rolling_report.md`

## Gates

- `reduced_core_rolling_pass`: `PASS_FAIL`, severity `critical`

## Implementation Scope

- `Makefile` (registry)
- `scripts/legacy/select_oco_reduced_core_rolling.py` (registry)
- `scripts/onboard_symbol.py` (registry)

## Tests

- `tests/test_oco_reduced_core_rolling.py`
