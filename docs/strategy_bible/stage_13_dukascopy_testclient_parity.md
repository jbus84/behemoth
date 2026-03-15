# Stage 13 - Dukascopy TestClient Parity

## Objective
Certify that canonical Dukascopy parquet ticks reproduce Stage 12-approved Python-runtime behavior when replayed through the in-process FastAPI `TestClient`.

## Required Inputs
- `data/analysis/backtest_reconcile/*_stage12_api_parity_summary.csv`
- `data/analysis/backtest_reconcile/*_dukascopy_testclient_replay_summary.csv`
- `docs/analysis/stage13_dukascopy_testclient_report.md`

## Process
- Treat Stage 12 as a prerequisite, not a substitute for Stage 13.
- Treat the local JForex surrogate as a Java-side prerequisite, not a substitute for Stage 13.
- Replay canonical Dukascopy parquet ticks from `/Users/danielfisher/Desktop/dukascopy_ticks`.
- Drive the Python runtime in-process through the FastAPI `TestClient` harness.
- Validate governed signal parity and execution parity on the same certification window used by Stage 12.
- Treat this as the official credential-free broker-source gate before any JForex runtime certification work.

## Hard Gates
- `stage12_api_parity_pass=true`
- `dukascopy_testclient_signal_parity_pass=true`
- `dukascopy_testclient_execution_parity_pass=true`

Stage 13 passes only when all three are green.

## Failure Interpretation
- If Stage 12 is red, do not trust any Dukascopy replay result.
- If Dukascopy TestClient signal parity is red, broker-source replay is not reproducing governed selection timing.
- If Dukascopy TestClient execution parity is red, the Python runtime diverges after nominally matched signals.

## Canonical Commands
```bash
make dukascopy-testclient-parity \
  SYMBOL=GBPUSD \
  START_TS=2025-07-07T00:00:00Z \
  END_TS=2025-07-09T00:00:00Z

make stage13-dukascopy-cert
```

## Outputs
- `data/analysis/backtest_reconcile/stage13_dukascopy_testclient_summary.csv`
- `data/analysis/backtest_reconcile/stage13_dukascopy_testclient_checks.csv`
- `docs/analysis/stage13_dukascopy_testclient_report.md`
- `docs/strategy_bible/generated/stage_13_snapshot.md`

## Traceability
- `scripts/replay_dukascopy_testclient.py`
- `scripts/validate_stage13_dukascopy_testclient.py`
- `docs/strategy_bible/stage_12_api_parity.md`

### Auto Snapshot - Stage 13
<!-- GENERATED:STAGE_13:START -->
### Auto Snapshot - Stage 13

- generated_at: `pending`
- Stage 13 is a hard gate for Dukascopy source parity via the FastAPI `TestClient`.
- Stage 12 parity, Dukascopy TestClient signal parity, and Dukascopy TestClient execution parity must all be green.

#### Key Results
_pending_
<!-- GENERATED:STAGE_13:END -->
