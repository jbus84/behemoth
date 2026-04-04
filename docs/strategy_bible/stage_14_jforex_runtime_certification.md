# Stage 14 - JForex Runtime Certification

## Objective
Certify that the Dukascopy JForex adapter reproduces the governed OCO execution contract after the local JForex surrogate and Stage 13 have already proven source/runtime parity against Stage 12 truth.

## Inputs
- `data/analysis/backtest_reconcile/stage13_dukascopy_testclient_summary.csv`
- `data/analysis/backtest_reconcile/*_jforex_signal_parity_summary.csv`
- `data/analysis/backtest_reconcile/*_jforex_execution_parity_summary.csv`
- `data/analysis/backtest_reconcile/*_jforex_oco_lifecycle_summary.csv`
- `data/analysis/backtest_reconcile/*_jforex_operational_ready_summary.csv`
- `docs/analysis/stage14_jforex_runtime_certification_report.md`

## Exact Calculations
- [Placeholder] Parity is calculated via direct event-log comparison.

## Causality / Leakage Controls
- [Placeholder] JForex tester client isolation.

## Failure Modes
- [Placeholder] Order submission delay, cancellation fail.

## Interpretation Guide
- [Placeholder] Review parity results.

## Validation Gates
- [Placeholder] All 6 gates must be green.

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
- Treat the local parquet-driven JForex surrogate as a prerequisite debug gate before Stage 14 tester/demo certification.
- Do not use `*_local_jforex_*` surrogate summaries as Stage 14 evidence; Stage 14 consumes only real JForex tester/demo artifacts.
- When running the Python API in `historical_auto`, scope the certification surface with `BEHEMOTH_SYMBOLS`.
- Historical Stage 14 replay should use tolerant locked-prediction matching so broker-side timestamp drift does not suppress otherwise valid locked selections.
- Run the Java JForex tester path against the same governed truth window used for certification.
- Treat `ITesterClient` as the official broker-certification harness for Stage 14.
- Confirm the adapter reproduces the OCO contract:
  - paired opposite stop-limit entries,
  - one fill cancels the sibling leg,
  - no double-live-leg drift after partial fill, cancel, reconnect, or replay recovery.
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
- `oco_lifecycle_pass=true`
- `local_jforex_surrogate_pass=true`
- `operational_ready_pass=true`

Stage 14 passes only when all six are green.

## Failure Interpretation
- If Stage 13 is red, do not trust any JForex tester/demo result.
- If JForex signal parity is red, the adapter is not reproducing research-approved selection timing.
- If JForex execution parity is red, the adapter lifecycle diverges after nominally matched signals.
- If OCO lifecycle is red, the adapter cannot safely enforce the paired stop-limit contract.
- If the local JForex surrogate is red, the shared Java strategy core is not validated before Stage 14 tester/demo certification.
- If operational readiness is red, the adapter is not deployable even if tester parity is green.

## Canonical Command
```bash
make stage14-jforex-cert
```

## Outputs
- `data/analysis/backtest_reconcile/stage14_jforex_runtime_certification_summary.csv`
- `data/analysis/backtest_reconcile/stage14_jforex_runtime_certification_checks.csv`
- `docs/analysis/stage14_jforex_runtime_certification_report.md`
- `docs/strategy_bible/generated/stage_14_snapshot.md`

## Traceability
- `src/jforex/`
- `scripts/validate_stage14_jforex_runtime_certification.py`
- `docs/strategy_bible/stage_13_dukascopy_testclient_parity.md`

### Auto Snapshot - Stage 14
<!-- GENERATED:STAGE_14:START -->
### Auto Snapshot - Stage 14

- generated_at: `pending`
- Stage 14 is a hard gate for the Dukascopy JForex adapter.
- Stage 13 Dukascopy TestClient parity, JForex tester parity, local JForex surrogate readiness, OCO lifecycle correctness, and operational readiness must all be green.

#### Key Results
_pending_
<!-- GENERATED:STAGE_14:END -->
