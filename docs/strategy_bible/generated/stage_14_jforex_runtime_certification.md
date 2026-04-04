# Stage 14 JForex Runtime Certification

## Purpose

Stage 14 is the final operator-facing gate for the JForex runtime path. It does not re-prove barrier logic correctness. Python already owns barrier state transitions and action selection. Stage 14 proves the Java runtime executed those actions cleanly and left deterministic evidence behind.

## Required Checks

Stage 14 is green only when these checks pass for the symbol under review:

- `stage13_dukascopy_testclient_pass`
- `jforex_signal_parity_pass`
- `jforex_execution_parity_pass`
- `execution_lifecycle_pass`
- `operational_ready_pass`
- `jforex_outcome_parity_pass`
- `local_jforex_surrogate_pass`

## Execution Lifecycle Gate

`execution_lifecycle_pass` is the Stage 14 barrier-manager execution gate.

It passes only when all of the following are true:

- `submit_failures == 0`
- `blocked_orders == 0`
- `close_anomalies == 0`
- `success_actions > 0`

The lifecycle summary is written to:

- `data/analysis/backtest_reconcile/<SYMBOL>_jforex_execution_lifecycle_summary.csv`

The lifecycle gate fails on these operator-relevant event classes:

- `market_order_submit_failure`
- `market_order_blocked`
- `barrier_close_failure`

`barrier_close_failure` covers close anomalies including missing or unknown broker position references.

## Deterministic Runtime Evidence

Do not treat derived summaries as sufficient by themselves. Stage 14 requires the canonical runtime evidence files to exist:

- `data/analysis/backtest_reconcile/<SYMBOL>_jforex_runtime_events.csv`
- `data/analysis/backtest_reconcile/<SYMBOL>_local_jforex_runtime_events.csv`

These files back the outcome-parity and local-surrogate certification inputs. If either required file is missing, Stage 14 must fail even if its derived summary CSV exists.

## Review Paths

Primary outputs:

- `docs/analysis/stage14_jforex_runtime_certification_report.md`
- `docs/strategy_bible/generated/stage_14_snapshot.md`

Symbol drill-down:

- `data/analysis/backtest_reconcile/<SYMBOL>_jforex_runtime_events.csv`
- `data/analysis/backtest_reconcile/<SYMBOL>_jforex_signal_parity_summary.csv`
- `data/analysis/backtest_reconcile/<SYMBOL>_jforex_execution_parity_summary.csv`
- `data/analysis/backtest_reconcile/<SYMBOL>_jforex_execution_lifecycle_summary.csv`
- `data/analysis/backtest_reconcile/<SYMBOL>_jforex_operational_ready_summary.csv`

Interpret a red Stage 14 as an execution-path blocker for live-demo rollout until the failing artifact and event trail are reviewed.
