# Stage 12 API Parity

Stage ID: `stage12`

Certifies that the authoritative Python API reproduces locked governance predictions for each active symbol over the certification window.

## Canonical Commands

- `make stage12-stage13-cert-artifacts`

## Required Inputs

- `data/analysis/tick_opportunity_mining/wfo_m3to1_oco_fullcap/${SYMBOL}_oco_monthly_predictions.parquet`
- `models/oco/${SYMBOL}_model_${MODEL_MONTH}.json`

## Produced Evidence

- `data/analysis/backtest_reconcile/${SYMBOL}_stage12_api_parity_summary.csv`
- `data/analysis/backtest_reconcile/stage12_stage13_certification_summary.csv`

## Gates

- `stage12_api_parity_pass`: `PASS_FAIL`, severity `critical`

## Implementation Scope

- `scripts/run_stage12_stage13_certification.py` (registry)
- `scripts/validate_api_parity.py` (registry)
- `src/behemoth/api/server.py` (graphify)

## Tests

- `tests/test_api_server.py`
- `tests/test_api_server_historical.py`
