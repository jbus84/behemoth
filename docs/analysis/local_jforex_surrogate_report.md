# Local JForex Surrogate Certification

- generated_at: `2026-03-16T12:41:02Z`
- summary_csv: `data/analysis/backtest_reconcile/local_jforex_surrogate_summary.csv`
- checks_csv: `data/analysis/backtest_reconcile/local_jforex_surrogate_checks.csv`

## Summary
| symbol   | stage12_api_parity_pass   | local_signal_parity_pass   | local_execution_parity_pass   | local_lifecycle_pass   | local_operational_ready_pass   | local_jforex_surrogate_pass   |   missing_inputs | verdict   | evaluated_at_utc     |
|:---------|:--------------------------|:---------------------------|:------------------------------|:-----------------------|:-------------------------------|:------------------------------|-----------------:|:----------|:---------------------|
| AUDUSD   | True                      | True                       | True                          | True                   | True                           | True                          |                0 | green     | 2026-03-16T12:41:02Z |
| EURUSD   | True                      | True                       | True                          | True                   | True                           | True                          |                0 | green     | 2026-03-16T12:41:02Z |
| GBPUSD   | True                      | True                       | True                          | True                   | True                           | True                          |                0 | green     | 2026-03-16T12:41:02Z |
| USDCAD   | True                      | True                       | True                          | True                   | True                           | True                          |                0 | green     | 2026-03-16T12:41:02Z |
| USDCHF   | True                      | True                       | True                          | True                   | True                           | True                          |                0 | green     | 2026-03-16T12:41:02Z |
| USDJPY   | True                      | True                       | True                          | True                   | True                           | True                          |                0 | green     | 2026-03-16T12:41:02Z |

## Checks
| symbol   | check_id                     | status   | severity   | metric_name                  |   metric_value |   expected | details   | source_path                                                                        | evaluated_at_utc     |
|:---------|:-----------------------------|:---------|:-----------|:-----------------------------|---------------:|-----------:|:----------|:-----------------------------------------------------------------------------------|:---------------------|
| AUDUSD   | STAGE12_API_PARITY_PASS      | pass     | critical   | stage12_api_parity_pass      |              1 |          1 |           | data/analysis/backtest_reconcile/AUDUSD_stage12_api_parity_summary.csv             | 2026-03-16T12:41:02Z |
| AUDUSD   | LOCAL_SIGNAL_PARITY_PASS     | pass     | critical   | local_signal_parity_pass     |              1 |          1 |           | data/analysis/backtest_reconcile/AUDUSD_local_jforex_signal_parity_summary.csv     | 2026-03-16T12:41:02Z |
| AUDUSD   | LOCAL_EXECUTION_PARITY_PASS  | pass     | critical   | local_execution_parity_pass  |              1 |          1 |           | data/analysis/backtest_reconcile/AUDUSD_local_jforex_execution_parity_summary.csv  | 2026-03-16T12:41:02Z |
| AUDUSD   | LOCAL_LIFECYCLE_PASS         | pass     | critical   | local_lifecycle_pass         |              1 |          1 |           | data/analysis/backtest_reconcile/AUDUSD_local_jforex_oco_lifecycle_summary.csv     | 2026-03-16T12:41:02Z |
| AUDUSD   | LOCAL_OPERATIONAL_READY_PASS | pass     | critical   | local_operational_ready_pass |              1 |          1 |           | data/analysis/backtest_reconcile/AUDUSD_local_jforex_operational_ready_summary.csv | 2026-03-16T12:41:02Z |
| EURUSD   | STAGE12_API_PARITY_PASS      | pass     | critical   | stage12_api_parity_pass      |              1 |          1 |           | data/analysis/backtest_reconcile/EURUSD_stage12_api_parity_summary.csv             | 2026-03-16T12:41:02Z |
| EURUSD   | LOCAL_SIGNAL_PARITY_PASS     | pass     | critical   | local_signal_parity_pass     |              1 |          1 |           | data/analysis/backtest_reconcile/EURUSD_local_jforex_signal_parity_summary.csv     | 2026-03-16T12:41:02Z |
| EURUSD   | LOCAL_EXECUTION_PARITY_PASS  | pass     | critical   | local_execution_parity_pass  |              1 |          1 |           | data/analysis/backtest_reconcile/EURUSD_local_jforex_execution_parity_summary.csv  | 2026-03-16T12:41:02Z |
| EURUSD   | LOCAL_LIFECYCLE_PASS         | pass     | critical   | local_lifecycle_pass         |              1 |          1 |           | data/analysis/backtest_reconcile/EURUSD_local_jforex_oco_lifecycle_summary.csv     | 2026-03-16T12:41:02Z |
| EURUSD   | LOCAL_OPERATIONAL_READY_PASS | pass     | critical   | local_operational_ready_pass |              1 |          1 |           | data/analysis/backtest_reconcile/EURUSD_local_jforex_operational_ready_summary.csv | 2026-03-16T12:41:02Z |
| GBPUSD   | STAGE12_API_PARITY_PASS      | pass     | critical   | stage12_api_parity_pass      |              1 |          1 |           | data/analysis/backtest_reconcile/GBPUSD_stage12_api_parity_summary.csv             | 2026-03-16T12:41:02Z |
| GBPUSD   | LOCAL_SIGNAL_PARITY_PASS     | pass     | critical   | local_signal_parity_pass     |              1 |          1 |           | data/analysis/backtest_reconcile/GBPUSD_local_jforex_signal_parity_summary.csv     | 2026-03-16T12:41:02Z |
| GBPUSD   | LOCAL_EXECUTION_PARITY_PASS  | pass     | critical   | local_execution_parity_pass  |              1 |          1 |           | data/analysis/backtest_reconcile/GBPUSD_local_jforex_execution_parity_summary.csv  | 2026-03-16T12:41:02Z |
| GBPUSD   | LOCAL_LIFECYCLE_PASS         | pass     | critical   | local_lifecycle_pass         |              1 |          1 |           | data/analysis/backtest_reconcile/GBPUSD_local_jforex_oco_lifecycle_summary.csv     | 2026-03-16T12:41:02Z |
| GBPUSD   | LOCAL_OPERATIONAL_READY_PASS | pass     | critical   | local_operational_ready_pass |              1 |          1 |           | data/analysis/backtest_reconcile/GBPUSD_local_jforex_operational_ready_summary.csv | 2026-03-16T12:41:02Z |
| USDCAD   | STAGE12_API_PARITY_PASS      | pass     | critical   | stage12_api_parity_pass      |              1 |          1 |           | data/analysis/backtest_reconcile/USDCAD_stage12_api_parity_summary.csv             | 2026-03-16T12:41:02Z |
| USDCAD   | LOCAL_SIGNAL_PARITY_PASS     | pass     | critical   | local_signal_parity_pass     |              1 |          1 |           | data/analysis/backtest_reconcile/USDCAD_local_jforex_signal_parity_summary.csv     | 2026-03-16T12:41:02Z |
| USDCAD   | LOCAL_EXECUTION_PARITY_PASS  | pass     | critical   | local_execution_parity_pass  |              1 |          1 |           | data/analysis/backtest_reconcile/USDCAD_local_jforex_execution_parity_summary.csv  | 2026-03-16T12:41:02Z |
| USDCAD   | LOCAL_LIFECYCLE_PASS         | pass     | critical   | local_lifecycle_pass         |              1 |          1 |           | data/analysis/backtest_reconcile/USDCAD_local_jforex_oco_lifecycle_summary.csv     | 2026-03-16T12:41:02Z |
| USDCAD   | LOCAL_OPERATIONAL_READY_PASS | pass     | critical   | local_operational_ready_pass |              1 |          1 |           | data/analysis/backtest_reconcile/USDCAD_local_jforex_operational_ready_summary.csv | 2026-03-16T12:41:02Z |
| USDCHF   | STAGE12_API_PARITY_PASS      | pass     | critical   | stage12_api_parity_pass      |              1 |          1 |           | data/analysis/backtest_reconcile/USDCHF_stage12_api_parity_summary.csv             | 2026-03-16T12:41:02Z |
| USDCHF   | LOCAL_SIGNAL_PARITY_PASS     | pass     | critical   | local_signal_parity_pass     |              1 |          1 |           | data/analysis/backtest_reconcile/USDCHF_local_jforex_signal_parity_summary.csv     | 2026-03-16T12:41:02Z |
| USDCHF   | LOCAL_EXECUTION_PARITY_PASS  | pass     | critical   | local_execution_parity_pass  |              1 |          1 |           | data/analysis/backtest_reconcile/USDCHF_local_jforex_execution_parity_summary.csv  | 2026-03-16T12:41:02Z |
| USDCHF   | LOCAL_LIFECYCLE_PASS         | pass     | critical   | local_lifecycle_pass         |              1 |          1 |           | data/analysis/backtest_reconcile/USDCHF_local_jforex_oco_lifecycle_summary.csv     | 2026-03-16T12:41:02Z |
| USDCHF   | LOCAL_OPERATIONAL_READY_PASS | pass     | critical   | local_operational_ready_pass |              1 |          1 |           | data/analysis/backtest_reconcile/USDCHF_local_jforex_operational_ready_summary.csv | 2026-03-16T12:41:02Z |
| USDJPY   | STAGE12_API_PARITY_PASS      | pass     | critical   | stage12_api_parity_pass      |              1 |          1 |           | data/analysis/backtest_reconcile/USDJPY_stage12_api_parity_summary.csv             | 2026-03-16T12:41:02Z |
| USDJPY   | LOCAL_SIGNAL_PARITY_PASS     | pass     | critical   | local_signal_parity_pass     |              1 |          1 |           | data/analysis/backtest_reconcile/USDJPY_local_jforex_signal_parity_summary.csv     | 2026-03-16T12:41:02Z |
| USDJPY   | LOCAL_EXECUTION_PARITY_PASS  | pass     | critical   | local_execution_parity_pass  |              1 |          1 |           | data/analysis/backtest_reconcile/USDJPY_local_jforex_execution_parity_summary.csv  | 2026-03-16T12:41:02Z |
| USDJPY   | LOCAL_LIFECYCLE_PASS         | pass     | critical   | local_lifecycle_pass         |              1 |          1 |           | data/analysis/backtest_reconcile/USDJPY_local_jforex_oco_lifecycle_summary.csv     | 2026-03-16T12:41:02Z |
| USDJPY   | LOCAL_OPERATIONAL_READY_PASS | pass     | critical   | local_operational_ready_pass |              1 |          1 |           | data/analysis/backtest_reconcile/USDJPY_local_jforex_operational_ready_summary.csv | 2026-03-16T12:41:02Z |

## Interpretation
- This is a pre-Stage diagnostic for the shared Java strategy core.
- Green here does not replace real Dukascopy JForex tester certification.
