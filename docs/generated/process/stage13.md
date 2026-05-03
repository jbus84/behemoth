# Stage 13 Dukascopy TestClient Certification

Stage ID: `stage13`

Certifies that Dukascopy-source TestClient evidence is available and agrees with the Stage 12 API parity outputs for deployment decisions.

## Canonical Commands

- `make stage13-dukascopy-cert`

## Required Inputs

- `data/analysis/backtest_reconcile/${SYMBOL}_stage12_api_parity_summary.csv`
- `data/analysis/backtest_reconcile/stage13_dukascopy_testclient_summary.csv`

## Produced Evidence

- `data/analysis/backtest_reconcile/stage12_stage13_certification_summary.csv`
- `docs/analysis/stage13_dukascopy_testclient_report.md`

## Gates

- `stage13_dukascopy_testclient_pass`: `PASS_FAIL`, severity `critical`

## Implementation Scope

- `scripts/generate_dukascopy_testclient_artifacts.py` (registry)
- `scripts/run_stage12_stage13_certification.py` (registry)
- `scripts/validate_stage13_dukascopy_testclient.py` (registry)

## Tests

- `tests/test_generate_dukascopy_testclient_artifacts.py`
