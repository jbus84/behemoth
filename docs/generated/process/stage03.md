# Stage 03 Monthly WFO

Stage ID: `stage03`

Performs Monthly WFO Model Fit and Threshold Fit, producing causally scored predictions for each Test Month.

## Canonical Commands

- `make onboard-symbol`

## Required Inputs

- `data/analysis/tick_opportunity_mining/${SYMBOL}_oco_candidate_universe.csv`
- `configs/research/experiments/${symbol}_tick_opportunity_monthly_wfo_oco_fullcap.yaml`

## Produced Evidence

- `data/analysis/tick_opportunity_mining/wfo_m3to1_oco_fullcap_${symbol}/${SYMBOL}_oco_monthly_predictions.parquet`
- `data/analysis/tick_opportunity_mining/wfo_m3to1_oco_fullcap_${symbol}/${SYMBOL}_oco_monthly_metrics.csv`
- `docs/analysis/${symbol}_tick_opportunity_monthly_wfo_oco_fullcap_report.md`

## Gates

- `monthly_wfo_pass`: `PASS_FAIL`, severity `critical`
- `threshold_causality_pass`: `PASS_FAIL`, severity `critical`

## Implementation Scope

- `Makefile` (registry)
- `scripts/onboard_symbol.py` (registry)
- `scripts/run_tick_opportunity_monthly_wfo.py` (registry)

## Tests

- `tests/test_monthly_wfo_threshold_causality.py`
