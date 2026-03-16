# Stage 13 Dukascopy TestClient Parity

- generated_at: `2026-03-16T12:58:44Z`
- summary_csv: `data/analysis/backtest_reconcile/stage13_dukascopy_testclient_summary.csv`
- checks_csv: `data/analysis/backtest_reconcile/stage13_dukascopy_testclient_checks.csv`

## Summary
| symbol   | stage12_api_parity_pass   | dukascopy_testclient_signal_parity_pass   | dukascopy_testclient_execution_parity_pass   | stage13_dukascopy_testclient_pass   |   missing_inputs | verdict   | evaluated_at_utc     |
|:---------|:--------------------------|:------------------------------------------|:---------------------------------------------|:------------------------------------|-----------------:|:----------|:---------------------|
| AUDUSD   | True                      | True                                      | True                                         | True                                |                0 | green     | 2026-03-16T12:58:44Z |
| EURUSD   | True                      | True                                      | True                                         | True                                |                0 | green     | 2026-03-16T12:58:44Z |
| GBPUSD   | True                      | True                                      | True                                         | True                                |                0 | green     | 2026-03-16T12:58:44Z |
| USDCAD   | True                      | True                                      | True                                         | True                                |                0 | green     | 2026-03-16T12:58:44Z |
| USDCHF   | True                      | True                                      | True                                         | True                                |                0 | green     | 2026-03-16T12:58:44Z |
| USDJPY   | True                      | True                                      | True                                         | True                                |                0 | green     | 2026-03-16T12:58:44Z |

## Checks
| symbol   | check_id                                   | status   | severity   | metric_name                                |   metric_value |   expected | details   | source_path                                                                     | evaluated_at_utc     |
|:---------|:-------------------------------------------|:---------|:-----------|:-------------------------------------------|---------------:|-----------:|:----------|:--------------------------------------------------------------------------------|:---------------------|
| AUDUSD   | STAGE12_API_PARITY_PASS                    | pass     | critical   | stage12_api_parity_pass                    |              1 |          1 |           | data/analysis/backtest_reconcile/AUDUSD_stage12_api_parity_summary.csv          | 2026-03-16T12:58:44Z |
| AUDUSD   | DUKASCOPY_TESTCLIENT_SIGNAL_PARITY_PASS    | pass     | critical   | dukascopy_testclient_signal_parity_pass    |              1 |          1 |           | data/analysis/backtest_reconcile/AUDUSD_dukascopy_testclient_replay_summary.csv | 2026-03-16T12:58:44Z |
| AUDUSD   | DUKASCOPY_TESTCLIENT_EXECUTION_PARITY_PASS | pass     | critical   | dukascopy_testclient_execution_parity_pass |              1 |          1 |           | data/analysis/backtest_reconcile/AUDUSD_dukascopy_testclient_replay_summary.csv | 2026-03-16T12:58:44Z |
| EURUSD   | STAGE12_API_PARITY_PASS                    | pass     | critical   | stage12_api_parity_pass                    |              1 |          1 |           | data/analysis/backtest_reconcile/EURUSD_stage12_api_parity_summary.csv          | 2026-03-16T12:58:44Z |
| EURUSD   | DUKASCOPY_TESTCLIENT_SIGNAL_PARITY_PASS    | pass     | critical   | dukascopy_testclient_signal_parity_pass    |              1 |          1 |           | data/analysis/backtest_reconcile/EURUSD_dukascopy_testclient_replay_summary.csv | 2026-03-16T12:58:44Z |
| EURUSD   | DUKASCOPY_TESTCLIENT_EXECUTION_PARITY_PASS | pass     | critical   | dukascopy_testclient_execution_parity_pass |              1 |          1 |           | data/analysis/backtest_reconcile/EURUSD_dukascopy_testclient_replay_summary.csv | 2026-03-16T12:58:44Z |
| GBPUSD   | STAGE12_API_PARITY_PASS                    | pass     | critical   | stage12_api_parity_pass                    |              1 |          1 |           | data/analysis/backtest_reconcile/GBPUSD_stage12_api_parity_summary.csv          | 2026-03-16T12:58:44Z |
| GBPUSD   | DUKASCOPY_TESTCLIENT_SIGNAL_PARITY_PASS    | pass     | critical   | dukascopy_testclient_signal_parity_pass    |              1 |          1 |           | data/analysis/backtest_reconcile/GBPUSD_dukascopy_testclient_replay_summary.csv | 2026-03-16T12:58:44Z |
| GBPUSD   | DUKASCOPY_TESTCLIENT_EXECUTION_PARITY_PASS | pass     | critical   | dukascopy_testclient_execution_parity_pass |              1 |          1 |           | data/analysis/backtest_reconcile/GBPUSD_dukascopy_testclient_replay_summary.csv | 2026-03-16T12:58:44Z |
| USDCAD   | STAGE12_API_PARITY_PASS                    | pass     | critical   | stage12_api_parity_pass                    |              1 |          1 |           | data/analysis/backtest_reconcile/USDCAD_stage12_api_parity_summary.csv          | 2026-03-16T12:58:44Z |
| USDCAD   | DUKASCOPY_TESTCLIENT_SIGNAL_PARITY_PASS    | pass     | critical   | dukascopy_testclient_signal_parity_pass    |              1 |          1 |           | data/analysis/backtest_reconcile/USDCAD_dukascopy_testclient_replay_summary.csv | 2026-03-16T12:58:44Z |
| USDCAD   | DUKASCOPY_TESTCLIENT_EXECUTION_PARITY_PASS | pass     | critical   | dukascopy_testclient_execution_parity_pass |              1 |          1 |           | data/analysis/backtest_reconcile/USDCAD_dukascopy_testclient_replay_summary.csv | 2026-03-16T12:58:44Z |
| USDCHF   | STAGE12_API_PARITY_PASS                    | pass     | critical   | stage12_api_parity_pass                    |              1 |          1 |           | data/analysis/backtest_reconcile/USDCHF_stage12_api_parity_summary.csv          | 2026-03-16T12:58:44Z |
| USDCHF   | DUKASCOPY_TESTCLIENT_SIGNAL_PARITY_PASS    | pass     | critical   | dukascopy_testclient_signal_parity_pass    |              1 |          1 |           | data/analysis/backtest_reconcile/USDCHF_dukascopy_testclient_replay_summary.csv | 2026-03-16T12:58:44Z |
| USDCHF   | DUKASCOPY_TESTCLIENT_EXECUTION_PARITY_PASS | pass     | critical   | dukascopy_testclient_execution_parity_pass |              1 |          1 |           | data/analysis/backtest_reconcile/USDCHF_dukascopy_testclient_replay_summary.csv | 2026-03-16T12:58:44Z |
| USDJPY   | STAGE12_API_PARITY_PASS                    | pass     | critical   | stage12_api_parity_pass                    |              1 |          1 |           | data/analysis/backtest_reconcile/USDJPY_stage12_api_parity_summary.csv          | 2026-03-16T12:58:44Z |
| USDJPY   | DUKASCOPY_TESTCLIENT_SIGNAL_PARITY_PASS    | pass     | critical   | dukascopy_testclient_signal_parity_pass    |              1 |          1 |           | data/analysis/backtest_reconcile/USDJPY_dukascopy_testclient_replay_summary.csv | 2026-03-16T12:58:44Z |
| USDJPY   | DUKASCOPY_TESTCLIENT_EXECUTION_PARITY_PASS | pass     | critical   | dukascopy_testclient_execution_parity_pass |              1 |          1 |           | data/analysis/backtest_reconcile/USDJPY_dukascopy_testclient_replay_summary.csv | 2026-03-16T12:58:44Z |

## Interpretation
- Stage 13 is green only when Stage 12 parity remains green and Dukascopy TestClient signal and execution parity are both green.
- Missing Dukascopy TestClient replay artifacts are treated as certification failures until the replay path is exercised.
