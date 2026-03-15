# OCO Logical Audit (All Active Symbols)

## Outputs
- checks_csv: `data/analysis/tick_opportunity_mining_dukascopy_candidate/oco_logical_audit_checks.csv`
- issues_csv: `data/analysis/tick_opportunity_mining_dukascopy_candidate/oco_logical_audit_issues.csv`

## Severity Counts
_empty_

## Check Status By Symbol
| symbol   |   pass |
|:---------|-------:|
| AUDUSD   |     10 |
| EURUSD   |     10 |
| GBPUSD   |     10 |
| USDCAD   |     10 |
| USDCHF   |     10 |
| USDJPY   |     10 |

## Failed Issues
_empty_

## All Checks
| symbol   | check_id   | status   | severity_if_fail   | component               | metric_name                  |   metric_value | threshold                                                                                                    |
|:---------|:-----------|:---------|:-------------------|:------------------------|:-----------------------------|---------------:|:-------------------------------------------------------------------------------------------------------------|
| EURUSD   | C01        | pass     | critical           | threshold_timing        | selected_consistency         |    1           | pred_prob >= threshold_exec for selected rows; month mismatch=0; threshold_days>=1                           |
| EURUSD   | C02        | pass     | high               | threshold_timing        | unstable_group_rate          |    0           | 0                                                                                                            |
| EURUSD   | C03        | pass     | high               | state_selection         | selected_non_gate_states     |    0           | 0                                                                                                            |
| EURUSD   | C04        | pass     | medium             | overlap_diversification | median_abs_corr_diff         |    0.136587    | <=0.40                                                                                                       |
| EURUSD   | C05        | pass     | high               | stop_limit_join         | min_month_match_rate         |    1           | >=0.995 and duplicate_keys=0                                                                                 |
| EURUSD   | C06        | pass     | high               | stop_limit_model        | monotonicity_violations      |    0           | 0                                                                                                            |
| EURUSD   | C07        | pass     | critical           | metrics_semantics       | rows_total_diff              |    0           | 0 (and signal diff=0, fill diff<=1e-9)                                                                       |
| EURUSD   | C08        | pass     | medium             | wfo_windowing           | warmup_count                 |    3           | ==3, missing_months=0, unexpected_non_ok=0 (allowed=['no_gate_states', 'no_test_rows', 'ok', 'warmup_skip']) |
| EURUSD   | C09        | pass     | high               | robustness_metric       | lb95_gross_abs_diff          |    0           | <=1e-8 (and signal diff<=1e-8)                                                                               |
| EURUSD   | C10        | pass     | critical           | timestamp_causality     | max_timestamp_violation_rate |    0           | 0 (and touch_order=0, touch_month_mismatch=0)                                                                |
| GBPUSD   | C01        | pass     | critical           | threshold_timing        | selected_consistency         |    1           | pred_prob >= threshold_exec for selected rows; month mismatch=0; threshold_days>=1                           |
| GBPUSD   | C02        | pass     | high               | threshold_timing        | unstable_group_rate          |    0           | 0                                                                                                            |
| GBPUSD   | C03        | pass     | high               | state_selection         | selected_non_gate_states     |    0           | 0                                                                                                            |
| GBPUSD   | C04        | pass     | medium             | overlap_diversification | median_abs_corr_diff         |    0.306673    | <=0.40                                                                                                       |
| GBPUSD   | C05        | pass     | high               | stop_limit_join         | min_month_match_rate         |    1           | >=0.995 and duplicate_keys=0                                                                                 |
| GBPUSD   | C06        | pass     | high               | stop_limit_model        | monotonicity_violations      |    0           | 0                                                                                                            |
| GBPUSD   | C07        | pass     | critical           | metrics_semantics       | rows_total_diff              |    0           | 0 (and signal diff=0, fill diff<=1e-9)                                                                       |
| GBPUSD   | C08        | pass     | medium             | wfo_windowing           | warmup_count                 |    3           | ==3, missing_months=0, unexpected_non_ok=0 (allowed=['no_gate_states', 'no_test_rows', 'ok', 'warmup_skip']) |
| GBPUSD   | C09        | pass     | high               | robustness_metric       | lb95_gross_abs_diff          |    4.44089e-16 | <=1e-8 (and signal diff<=1e-8)                                                                               |
| GBPUSD   | C10        | pass     | critical           | timestamp_causality     | max_timestamp_violation_rate |    0           | 0 (and touch_order=0, touch_month_mismatch=0)                                                                |
| USDJPY   | C01        | pass     | critical           | threshold_timing        | selected_consistency         |    1           | pred_prob >= threshold_exec for selected rows; month mismatch=0; threshold_days>=1                           |
| USDJPY   | C02        | pass     | high               | threshold_timing        | unstable_group_rate          |    0           | 0                                                                                                            |
| USDJPY   | C03        | pass     | high               | state_selection         | selected_non_gate_states     |    0           | 0                                                                                                            |
| USDJPY   | C04        | pass     | medium             | overlap_diversification | median_abs_corr_diff         |    0.230812    | <=0.40                                                                                                       |
| USDJPY   | C05        | pass     | high               | stop_limit_join         | min_month_match_rate         |    1           | >=0.995 and duplicate_keys=0                                                                                 |
| USDJPY   | C06        | pass     | high               | stop_limit_model        | monotonicity_violations      |    0           | 0                                                                                                            |
| USDJPY   | C07        | pass     | critical           | metrics_semantics       | rows_total_diff              |    0           | 0 (and signal diff=0, fill diff<=1e-9)                                                                       |
| USDJPY   | C08        | pass     | medium             | wfo_windowing           | warmup_count                 |    3           | ==3, missing_months=0, unexpected_non_ok=0 (allowed=['no_gate_states', 'no_test_rows', 'ok', 'warmup_skip']) |
| USDJPY   | C09        | pass     | high               | robustness_metric       | lb95_gross_abs_diff          |    0           | <=1e-8 (and signal diff<=1e-8)                                                                               |
| USDJPY   | C10        | pass     | critical           | timestamp_causality     | max_timestamp_violation_rate |    0           | 0 (and touch_order=0, touch_month_mismatch=0)                                                                |
| USDCHF   | C01        | pass     | critical           | threshold_timing        | selected_consistency         |    1           | pred_prob >= threshold_exec for selected rows; month mismatch=0; threshold_days>=1                           |
| USDCHF   | C02        | pass     | high               | threshold_timing        | unstable_group_rate          |    0           | 0                                                                                                            |
| USDCHF   | C03        | pass     | high               | state_selection         | selected_non_gate_states     |    0           | 0                                                                                                            |
| USDCHF   | C04        | pass     | medium             | overlap_diversification | median_abs_corr_diff         |    0.249949    | <=0.40                                                                                                       |
| USDCHF   | C05        | pass     | high               | stop_limit_join         | min_month_match_rate         |    1           | >=0.995 and duplicate_keys=0                                                                                 |
| USDCHF   | C06        | pass     | high               | stop_limit_model        | monotonicity_violations      |    0           | 0                                                                                                            |
| USDCHF   | C07        | pass     | critical           | metrics_semantics       | rows_total_diff              |    0           | 0 (and signal diff=0, fill diff<=1e-9)                                                                       |
| USDCHF   | C08        | pass     | medium             | wfo_windowing           | warmup_count                 |    3           | ==3, missing_months=0, unexpected_non_ok=0 (allowed=['no_gate_states', 'no_test_rows', 'ok', 'warmup_skip']) |
| USDCHF   | C09        | pass     | high               | robustness_metric       | lb95_gross_abs_diff          |    2.22045e-16 | <=1e-8 (and signal diff<=1e-8)                                                                               |
| USDCHF   | C10        | pass     | critical           | timestamp_causality     | max_timestamp_violation_rate |    0           | 0 (and touch_order=0, touch_month_mismatch=0)                                                                |
| AUDUSD   | C01        | pass     | critical           | threshold_timing        | selected_consistency         |    1           | pred_prob >= threshold_exec for selected rows; month mismatch=0; threshold_days>=1                           |
| AUDUSD   | C02        | pass     | high               | threshold_timing        | unstable_group_rate          |    0           | 0                                                                                                            |
| AUDUSD   | C03        | pass     | high               | state_selection         | selected_non_gate_states     |    0           | 0                                                                                                            |
| AUDUSD   | C04        | pass     | medium             | overlap_diversification | median_abs_corr_diff         |    0.185987    | <=0.40                                                                                                       |
| AUDUSD   | C05        | pass     | high               | stop_limit_join         | min_month_match_rate         |    1           | >=0.995 and duplicate_keys=0                                                                                 |
| AUDUSD   | C06        | pass     | high               | stop_limit_model        | monotonicity_violations      |    0           | 0                                                                                                            |
| AUDUSD   | C07        | pass     | critical           | metrics_semantics       | rows_total_diff              |    0           | 0 (and signal diff=0, fill diff<=1e-9)                                                                       |
| AUDUSD   | C08        | pass     | medium             | wfo_windowing           | warmup_count                 |    3           | ==3, missing_months=0, unexpected_non_ok=0 (allowed=['no_gate_states', 'no_test_rows', 'ok', 'warmup_skip']) |
| AUDUSD   | C09        | pass     | high               | robustness_metric       | lb95_gross_abs_diff          |    0           | <=1e-8 (and signal diff<=1e-8)                                                                               |
| AUDUSD   | C10        | pass     | critical           | timestamp_causality     | max_timestamp_violation_rate |    0           | 0 (and touch_order=0, touch_month_mismatch=0)                                                                |
| USDCAD   | C01        | pass     | critical           | threshold_timing        | selected_consistency         |    1           | pred_prob >= threshold_exec for selected rows; month mismatch=0; threshold_days>=1                           |
| USDCAD   | C02        | pass     | high               | threshold_timing        | unstable_group_rate          |    0           | 0                                                                                                            |
| USDCAD   | C03        | pass     | high               | state_selection         | selected_non_gate_states     |    0           | 0                                                                                                            |
| USDCAD   | C04        | pass     | medium             | overlap_diversification | median_abs_corr_diff         |    0.176921    | <=0.40                                                                                                       |
| USDCAD   | C05        | pass     | high               | stop_limit_join         | min_month_match_rate         |    1           | >=0.995 and duplicate_keys=0                                                                                 |
| USDCAD   | C06        | pass     | high               | stop_limit_model        | monotonicity_violations      |    0           | 0                                                                                                            |
| USDCAD   | C07        | pass     | critical           | metrics_semantics       | rows_total_diff              |    0           | 0 (and signal diff=0, fill diff<=1e-9)                                                                       |
| USDCAD   | C08        | pass     | medium             | wfo_windowing           | warmup_count                 |    3           | ==3, missing_months=0, unexpected_non_ok=0 (allowed=['no_gate_states', 'no_test_rows', 'ok', 'warmup_skip']) |
| USDCAD   | C09        | pass     | high               | robustness_metric       | lb95_gross_abs_diff          |    2.22045e-16 | <=1e-8 (and signal diff<=1e-8)                                                                               |
| USDCAD   | C10        | pass     | critical           | timestamp_causality     | max_timestamp_violation_rate |    0           | 0 (and touch_order=0, touch_month_mismatch=0)                                                                |
