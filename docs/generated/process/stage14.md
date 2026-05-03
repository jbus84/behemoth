# Stage 14 JForex Runtime Certification

Stage ID: `stage14`

Certifies runtime parity for the JForex adapter. Local JForex surrogate outcome parity is the hard runtime gate; real JForex historical outcome parity is broker-feed drift monitor evidence.

## Canonical Commands

- `make full-stage14-cert`
- `make stage14-jforex-cert`

## Required Inputs

- `data/analysis/backtest_reconcile/stage12_stage13_certification_summary.csv`
- `data/analysis/backtest_reconcile/local_jforex_outcome_parity_summary.csv`
- `data/analysis/backtest_reconcile/local_jforex_surrogate_summary.csv`
- `data/analysis/backtest_reconcile/jforex_outcome_parity_summary.csv`

## Produced Evidence

- `data/analysis/backtest_reconcile/stage14_jforex_runtime_certification_checks.csv`
- `data/analysis/backtest_reconcile/stage14_jforex_runtime_certification_summary.csv`
- `docs/analysis/stage14_jforex_runtime_certification_report.md`
- `docs/strategy_bible/generated/stage_14_snapshot.md`

## Gates

- `stage13_dukascopy_testclient_pass`: `PASS_FAIL`, severity `critical`
- `local_jforex_surrogate_pass`: `PASS_FAIL`, severity `critical`
- `jforex_signal_parity_pass`: `PASS_FAIL`, severity `critical`
- `jforex_execution_parity_pass`: `PASS_FAIL`, severity `critical`
- `jforex_execution_lifecycle_pass`: `PASS_FAIL`, severity `critical`
- `jforex_operational_ready_pass`: `PASS_FAIL`, severity `critical`
- `jforex_outcome_parity_pass`: `MONITOR_ONLY`, severity `monitor`

## Implementation Scope

- `Makefile` (registry)
- `scripts/audit_runtime_parity.py` (registry)
- `scripts/reconcile_jforex_outcomes.py` (registry)
- `scripts/run_jforex_dukascopy_matrix.py` (registry)
- `scripts/run_local_jforex_surrogate_matrix.py` (registry)
- `scripts/validate_local_jforex_surrogate.py` (registry)
- `scripts/validate_stage14_jforex_runtime_certification.py` (registry)
- `src/jforex/src/main/java/com/behemoth/jforex/BehemothJForexStrategy.java` (registry)
- `src/jforex/src/main/java/com/behemoth/jforex/JForexTesterRunner.java` (registry)
- `src/jforex/src/main/java/com/behemoth/jforex/LocalJForexTesterRunner.java` (registry)

## Tests

- `tests/test_reconcile_jforex_outcomes.py`
- `tests/test_validate_local_jforex_surrogate.py`
- `tests/test_validate_stage14_jforex_runtime_certification.py`
- `tests/test_run_jforex_dukascopy_matrix.py`
- `tests/test_run_local_jforex_surrogate_matrix.py`
