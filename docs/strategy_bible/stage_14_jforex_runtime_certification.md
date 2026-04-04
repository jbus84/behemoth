# Stage 14 - JForex Runtime Certification

## Objective
Certify that the Dukascopy JForex adapter faithfully executes barrier manager actions after the local JForex surrogate and Stage 13 have already proven source/runtime parity against Stage 12 truth.

## Inputs
- `data/analysis/backtest_reconcile/stage13_dukascopy_testclient_summary.csv`
- `data/analysis/backtest_reconcile/*_jforex_signal_parity_summary.csv`
- `data/analysis/backtest_reconcile/*_jforex_execution_parity_summary.csv`
- `data/analysis/backtest_reconcile/*_jforex_execution_lifecycle_summary.csv`
- `data/analysis/backtest_reconcile/*_jforex_operational_ready_summary.csv`
- `data/analysis/backtest_reconcile/jforex_outcome_parity_summary.csv`
- `data/analysis/backtest_reconcile/local_jforex_surrogate_summary.csv`
- `data/analysis/backtest_reconcile/<SYMBOL>_jforex_runtime_events.csv`
- `data/analysis/backtest_reconcile/<SYMBOL>_local_jforex_runtime_events.csv`
- `docs/analysis/stage14_jforex_runtime_certification_report.md`

## Exact Calculations
- [Placeholder] Parity is calculated via direct event-log comparison.

## Causality / Leakage Controls
- [Placeholder] JForex tester client isolation.

## Failure Modes
- Order submission failures on OPEN_MARKET actions.
- Blocked market orders during windows expected to be executable.
- Barrier close failures caused by missing or unknown broker position references.
- Missing deterministic runtime evidence files even when derived summaries exist.

## Interpretation Guide
- [Placeholder] Review parity results.

## Validation Gates
- Stage 14 is green only when all 7 checks below are green for the symbol under review.

## Operator Decision Tree
- [Placeholder] If partial fill, check risk state.

## How To Run
- See canonical command.

## How To Interpret Outputs
- [Placeholder] Review JForex operational logs.

## What To Do If It Fails
- [Placeholder] Check API parity.

## Reproduction Commands
- See canonical command.

## Process
- Treat Stage 13 as a prerequisite, not a substitute for Stage 14.
- Treat the local parquet-driven JForex surrogate as a prerequisite debug gate before Stage 14.
- Do not treat derived summaries as sufficient by themselves. Stage 14 requires both canonical runtime evidence files:
  - `data/analysis/backtest_reconcile/<SYMBOL>_jforex_runtime_events.csv`
  - `data/analysis/backtest_reconcile/<SYMBOL>_local_jforex_runtime_events.csv`
- Outcome parity is not trusted unless the canonical JForex runtime events file exists.
- Local surrogate certification is not trusted unless the canonical local-surrogate runtime events file exists.
- When running the Python API in `historical_auto`, scope the certification surface with `BEHEMOTH_SYMBOLS`.
- Historical Stage 14 replay should use tolerant locked-prediction matching so broker-side timestamp drift does not suppress otherwise valid locked selections.
- Run the Java JForex tester path against the same governed truth window used for certification.
- Treat `ITesterClient` as the official broker-certification harness for Stage 14.
- Confirm the adapter faithfully executes barrier manager actions:
  - OPEN_MARKET actions result in submitted market orders,
  - CLOSE_MARKET actions result in position closes,
  - no dropped or mishandled actions during the certification window.
- Confirm demo-session readiness separately from tester parity:
  - authentication,
  - subscriptions,
  - account snapshot publication,
  - reservation lifecycle,
  - metrics/logging path from both Python and JForex Prometheus endpoints.

## Hard Gates
- `stage13_dukascopy_testclient_pass=true`
- `jforex_signal_parity_pass=true`
- `jforex_execution_parity_pass=true`
- `execution_lifecycle_pass=true`
- `operational_ready_pass=true`
- `jforex_outcome_parity_pass=true`
- `local_jforex_surrogate_pass=true`

Stage 14 passes only when all seven are green.

`execution_lifecycle_pass` fails if any of the following are present:

- `market_order_submit_failure`
- `market_order_blocked`
- `barrier_close_failure`

The lifecycle summary is written to `data/analysis/backtest_reconcile/<SYMBOL>_jforex_execution_lifecycle_summary.csv` and must report:

- `submit_failures == 0`
- `blocked_orders == 0`
- `close_anomalies == 0`
- `success_actions > 0`

## Failure Interpretation
- If Stage 13 is red, do not trust any JForex tester/demo result.
- If JForex signal parity is red, the adapter is not reproducing research-approved selection timing.
- If JForex execution parity is red, the adapter lifecycle diverges after nominally matched signals.
- If execution lifecycle is red, the adapter failed to execute barrier manager actions without blocked opens, submit failures, or close anomalies.
- If operational readiness is red, the adapter is not deployable even if tester parity is green.
- If outcome parity is red, inspect `data/analysis/backtest_reconcile/<SYMBOL>_jforex_runtime_events.csv` before trusting the summary.
- If local surrogate is red, inspect `data/analysis/backtest_reconcile/<SYMBOL>_local_jforex_runtime_events.csv` before trusting the summary.

## Canonical Command
```bash
make stage14-jforex-cert
```

## Outputs
- `data/analysis/backtest_reconcile/stage14_jforex_runtime_certification_summary.csv`
- `data/analysis/backtest_reconcile/stage14_jforex_runtime_certification_checks.csv`
- `docs/analysis/stage14_jforex_runtime_certification_report.md`
- `docs/strategy_bible/generated/stage_14_snapshot.md`
- `docs/strategy_bible/generated/stage_14_jforex_runtime_certification.md`

## Traceability
- `src/jforex/`
- `scripts/validate_stage14_jforex_runtime_certification.py`
- `docs/strategy_bible/stage_13_dukascopy_testclient_parity.md`

### Auto Snapshot - Stage 14
<!-- GENERATED:STAGE_14:START -->
### Auto Snapshot - Stage 14

- generated_at: `pending`
- Stage 14 is a hard gate for the Dukascopy JForex adapter.
- Stage 13 Dukascopy TestClient parity, JForex tester parity, execution lifecycle correctness, deterministic runtime evidence, and operational readiness must all be green.

#### Key Results
_pending_
<!-- GENERATED:STAGE_14:END -->
