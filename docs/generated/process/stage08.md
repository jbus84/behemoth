# Stage 08 Robustness And Stress

Stage ID: `stage08`

Applies the Robustness Filter and stress checks to Monthly WFO evidence before governance locking.

## Canonical Commands

- `make onboard-symbol`

## Required Inputs

- `data/analysis/tick_opportunity_mining/wfo_m3to1_oco_fullcap_${symbol}/${SYMBOL}_oco_monthly_predictions.parquet`
- `data/analysis/tick_opportunity_mining/reduced_core_rolling/${SYMBOL}_oco_reduced_state_schedule.csv`

## Produced Evidence

- `data/analysis/tick_opportunity_mining/robustness/${SYMBOL}_oco_monthly_wfo_robustness_summary.csv`
- `docs/analysis/${symbol}_oco_monthly_wfo_robustness_fullcap_report.md`

## Gates

- `robustness_filter_pass`: `PASS_FAIL`, severity `critical`

## Implementation Scope

- `Makefile` (registry)
- `scripts/analyze_oco_monthly_wfo_robustness.py` (registry)
- `scripts/onboard_symbol.py` (registry)

## Tests

- `tests/test_oco_monthly_wfo_robustness.py`
