# Stage 14 JForex Runtime Certification

- generated_at: `2026-03-16T19:04:54Z`
- summary_csv: `tmp/stage14_fix_check_summary.csv`
- checks_csv: `tmp/stage14_fix_check_checks.csv`

## Summary
| symbol   | stage13_dukascopy_testclient_pass   | jforex_signal_parity_pass   | jforex_execution_parity_pass   | oco_lifecycle_pass   | operational_ready_pass   | stage14_jforex_cert_pass   |   missing_inputs | verdict   | evaluated_at_utc     |
|:---------|:------------------------------------|:----------------------------|:-------------------------------|:---------------------|:-------------------------|:---------------------------|-----------------:|:----------|:---------------------|
| GBPUSD   | False                               | True                        | False                          | True                 | True                     | False                      |                1 | red       | 2026-03-16T19:04:54Z |

## Checks
| symbol   | check_id                          | status   | severity   | metric_name                       |   metric_value |   expected | details                | source_path                                                                  | evaluated_at_utc     |
|:---------|:----------------------------------|:---------|:-----------|:----------------------------------|---------------:|-----------:|:-----------------------|:-----------------------------------------------------------------------------|:---------------------|
| GBPUSD   | STAGE13_DUKASCOPY_TESTCLIENT_PASS | fail     | critical   | stage13_dukascopy_testclient_pass |              0 |          1 | missing input artifact |                                                                              | 2026-03-16T19:04:54Z |
| GBPUSD   | JFOREX_SIGNAL_PARITY_PASS         | pass     | critical   | jforex_signal_parity_pass         |              1 |          1 |                        | data/analysis/backtest_reconcile/GBPUSD_jforex_signal_parity_summary.csv     | 2026-03-16T19:04:54Z |
| GBPUSD   | JFOREX_EXECUTION_PARITY_PASS      | fail     | critical   | jforex_execution_parity_pass      |              0 |          1 |                        | data/analysis/backtest_reconcile/GBPUSD_jforex_execution_parity_summary.csv  | 2026-03-16T19:04:54Z |
| GBPUSD   | OCO_LIFECYCLE_PASS                | pass     | critical   | oco_lifecycle_pass                |              1 |          1 |                        | data/analysis/backtest_reconcile/GBPUSD_jforex_oco_lifecycle_summary.csv     | 2026-03-16T19:04:54Z |
| GBPUSD   | OPERATIONAL_READY_PASS            | pass     | high       | operational_ready_pass            |              1 |          1 |                        | data/analysis/backtest_reconcile/GBPUSD_jforex_operational_ready_summary.csv | 2026-03-16T19:04:54Z |

## Interpretation
- Stage 14 is green only when Stage 13 remains green and all JForex-specific certification checks pass.
- Missing JForex tester/demo artifacts are treated as certification failures until the adapter path is exercised.
