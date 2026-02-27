# USDJPY OCO Reduced-Core Rolling Selection

## Setup
- family_keep: `oco_first_touch_clean`
- barrier_keep: `[2.0, 3.0]`
- horizon_keep: `[5, 6]`
- locked_quantile: `0.9`
- selection_mode: `auto`
- execution_mode: `stop_limit`
- stop_limit_detail_csv: `data/analysis/tick_opportunity_mining/stop_limit_tickfill_fullcap/USDJPY_stop_limit_tickfill_detail.csv`
- stop_limit_cap_pips: `1.2`
- stop_limit_slippage_mode: `full_overshoot`
- stop_limit_match_rate: `0.998859`
- stop_limit_fill_rate_selected: `0.986725`
- state_train_months: `3`
- min_train_months: `3`
- overlap_corr_max: `0.85`
- overlap_divergence_max: `0.4`
- max_state_churn: `0.45`
- max_top_state_share: `0.35`
- max_state_hhi: `0.25`
- enforce_state_stability_gates: `False`
- max_states/min_states: `12/4`
- strict_gate_only: `True`

## Summary
| symbol   |   locked_quantile | selection_mode   | execution_mode   |   state_train_months |   months_total |   months_scored |   rows_total |   signal_rows_total |   mean_gross_pips |   monthly_mean_gross_pips |   lb95_month_mean_gross_pips |   mean_signal_pips |   monthly_mean_signal_pips |   lb95_month_mean_signal_pips |   positive_months |   positive_months_signal |   avg_month_rows |   avg_month_signal_rows |   fill_rate_overall |   annualized_rows |   capacity_floor_monthly |   capacity_floor_annual | capacity_pass_monthly_or_annual   |   max_state_churn |   max_top_state_share |   max_state_hhi |   stability_months_pass |
|:---------|------------------:|:-----------------|:-----------------|---------------------:|---------------:|----------------:|-------------:|--------------------:|------------------:|--------------------------:|-----------------------------:|-------------------:|---------------------------:|------------------------------:|------------------:|-------------------------:|-----------------:|------------------------:|--------------------:|------------------:|-------------------------:|------------------------:|:----------------------------------|------------------:|----------------------:|----------------:|------------------------:|
| USDJPY   |               0.9 | auto             | stop_limit       |                    3 |              9 |               6 |         2258 |                2280 |           3.00368 |                   2.98447 |                      2.54229 |            2.97469 |                    2.95373 |                       2.49917 |                 6 |                        6 |          376.333 |                     380 |            0.990351 |              4516 |                     3000 |                    5000 | False                             |              0.45 |                  0.35 |            0.25 |                       0 |

## Reduced State Universe
| symbol   |   bar_ticks |   horizon | state_id                                  | family                |   barrier_pips | regime_desc                |
|:---------|------------:|----------:|:------------------------------------------|:----------------------|---------------:|:---------------------------|
| USDJPY   |         100 |         5 | oco_first_touch_clean__asia__k2           | oco_first_touch_clean |              2 | asia;barrier=2.0           |
| USDJPY   |         100 |         6 | oco_first_touch_clean__asia__k2           | oco_first_touch_clean |              2 | asia;barrier=2.0           |
| USDJPY   |         100 |         6 | oco_first_touch_clean__high_range_q70__k2 | oco_first_touch_clean |              2 | high_range_q70;barrier=2.0 |
| USDJPY   |         100 |         6 | oco_first_touch_clean__london__k2         | oco_first_touch_clean |              2 | london;barrier=2.0         |
| USDJPY   |         100 |         6 | oco_first_touch_clean__low_cost_q30__k2   | oco_first_touch_clean |              2 | low_cost_q30;barrier=2.0   |
| USDJPY   |         100 |         6 | oco_first_touch_clean__low_cost_q50__k2   | oco_first_touch_clean |              2 | low_cost_q50;barrier=2.0   |

## Monthly Portfolio
| symbol   | test_month   | train_months            |   states_selected |   rows |   signal_rows |   fill_rate |   mean_gross_pips |   mean_signal_pips |   median_gross_pips |   pos_rate |   state_churn_rate |   top_state_share |   state_hhi |   stability_pass | status      |
|:---------|:-------------|:------------------------|------------------:|-------:|--------------:|------------:|------------------:|-------------------:|--------------------:|-----------:|-------------------:|------------------:|------------:|-----------------:|:------------|
| USDJPY   | 2025-04      |                         |                 0 |      0 |             0 |  nan        |         nan       |          nan       |               nan   | nan        |         nan        |        nan        |  nan        |              nan | warmup_skip |
| USDJPY   | 2025-05      | 2025-04                 |                 0 |      0 |             0 |  nan        |         nan       |          nan       |               nan   | nan        |         nan        |        nan        |  nan        |              nan | warmup_skip |
| USDJPY   | 2025-06      | 2025-04,2025-05         |                 0 |      0 |             0 |  nan        |         nan       |          nan       |               nan   | nan        |         nan        |        nan        |  nan        |              nan | warmup_skip |
| USDJPY   | 2025-07      | 2025-04,2025-05,2025-06 |                 2 |    356 |           358 |    0.994413 |           3.35197 |            3.33324 |                 2.8 |   0.726257 |           0        |          0.614525 |    0.526232 |                0 | ok          |
| USDJPY   | 2025-08      | 2025-05,2025-06,2025-07 |                 2 |    330 |           339 |    0.973451 |           3.77697 |            3.6767  |                 2.9 |   0.758112 |           0.666667 |          0.522124 |    0.500979 |                0 | ok          |
| USDJPY   | 2025-09      | 2025-06,2025-07,2025-08 |                 1 |    280 |           280 |    1        |           2.43893 |            2.43893 |                 1.8 |   0.710714 |           1        |          1        |    1        |                0 | ok          |
| USDJPY   | 2025-10      | 2025-07,2025-08,2025-09 |                 2 |    458 |           461 |    0.993492 |           3.85895 |            3.83384 |                 3.1 |   0.746204 |           0.5      |          0.605206 |    0.522137 |                0 | ok          |
| USDJPY   | 2025-11      | 2025-08,2025-09,2025-10 |                 1 |    313 |           315 |    0.993651 |           2.12396 |            2.11048 |                 1.7 |   0.650794 |           1        |          1        |    1        |                0 | ok          |
| USDJPY   | 2025-12      | 2025-09,2025-10,2025-11 |                 2 |    521 |           527 |    0.988615 |           2.35605 |            2.32922 |                 2.1 |   0.681214 |           1        |          0.639469 |    0.538903 |                0 | ok          |

## State Stability
| symbol   | test_month   |   states_selected |   state_churn_rate |   top_state_share |   state_hhi |   stability_pass | status      |
|:---------|:-------------|------------------:|-------------------:|------------------:|------------:|-----------------:|:------------|
| USDJPY   | 2025-04      |                 0 |         nan        |        nan        |  nan        |              nan | warmup_skip |
| USDJPY   | 2025-05      |                 0 |         nan        |        nan        |  nan        |              nan | warmup_skip |
| USDJPY   | 2025-06      |                 0 |         nan        |        nan        |  nan        |              nan | warmup_skip |
| USDJPY   | 2025-07      |                 2 |           0        |          0.614525 |    0.526232 |                0 | ok          |
| USDJPY   | 2025-08      |                 2 |           0.666667 |          0.522124 |    0.500979 |                0 | ok          |
| USDJPY   | 2025-09      |                 1 |           1        |          1        |    1        |                0 | ok          |
| USDJPY   | 2025-10      |                 2 |           0.5      |          0.605206 |    0.522137 |                0 | ok          |
| USDJPY   | 2025-11      |                 1 |           1        |          1        |    1        |                0 | ok          |
| USDJPY   | 2025-12      |                 2 |           1        |          0.639469 |    0.538903 |                0 | ok          |

## State Schedule (Top Rows)
| symbol   | test_month   | train_months            |   selected_rank | state_id                                  | state_key                                       |   bar_ticks |   horizon | family                | regime_desc                |   barrier_pips |   overlap_corr_max |   overlap_div_max |   train_rows |   train_months_count |   train_avg_month_rows |   train_mean_gross_pips |   train_mean_signal_pips |   train_lb95_trade_mean_gross_pips |   train_lb95_month_mean_gross_pips |   train_positive_months |   train_fill_rate | gate_pass   |
|:---------|:-------------|:------------------------|----------------:|:------------------------------------------|:------------------------------------------------|------------:|----------:|:----------------------|:---------------------------|---------------:|-------------------:|------------------:|-------------:|---------------------:|-----------------------:|------------------------:|-------------------------:|-----------------------------------:|-----------------------------------:|------------------------:|------------------:|:------------|
| USDJPY   | 2025-07      | 2025-04,2025-05,2025-06 |               1 | oco_first_touch_clean__high_range_q70__k2 | oco_first_touch_clean__high_range_q70__k2|100|6 |         100 |         6 | oco_first_touch_clean | high_range_q70;barrier=2.0 |              2 |           0        |          0        |          998 |                    3 |                325.333 |                 4.00645 |                  3.91814 |                            3.58464 |                            3.71706 |                       3 |          0.977956 | True        |
| USDJPY   | 2025-07      | 2025-04,2025-05,2025-06 |               2 | oco_first_touch_clean__asia__k2           | oco_first_touch_clean__asia__k2|100|6           |         100 |         6 | oco_first_touch_clean | asia;barrier=2.0           |              2 |           0.557568 |          0.380503 |          813 |                    3 |                270     |                 3.43815 |                  3.42546 |                            3.10921 |                            2.84266 |                       3 |          0.99631  | True        |
| USDJPY   | 2025-08      | 2025-05,2025-06,2025-07 |               1 | oco_first_touch_clean__high_range_q70__k2 | oco_first_touch_clean__high_range_q70__k2|100|6 |         100 |         6 | oco_first_touch_clean | high_range_q70;barrier=2.0 |              2 |           0        |          0        |          799 |                    3 |                263     |                 3.87529 |                  3.82678 |                            3.48722 |                            3.71706 |                       3 |          0.987484 | True        |
| USDJPY   | 2025-08      | 2025-05,2025-06,2025-07 |               2 | oco_first_touch_clean__london__k2         | oco_first_touch_clean__london__k2|100|6         |         100 |         6 | oco_first_touch_clean | london;barrier=2.0         |              2 |           0.582788 |          0.381381 |          677 |                    3 |                223.667 |                 2.97854 |                  2.95214 |                            2.59434 |                            2.76274 |                       3 |          0.991137 | True        |
| USDJPY   | 2025-09      | 2025-06,2025-07,2025-08 |               1 | oco_first_touch_clean__low_cost_q30__k2   | oco_first_touch_clean__low_cost_q30__k2|100|6   |         100 |         6 | oco_first_touch_clean | low_cost_q30;barrier=2.0   |              2 |           0        |          0        |         1017 |                    3 |                333.333 |                 3.1056  |                  3.05369 |                            2.75133 |                            2.97876 |                       3 |          0.983284 | True        |
| USDJPY   | 2025-10      | 2025-07,2025-08,2025-09 |               1 | oco_first_touch_clean__low_cost_q30__k2   | oco_first_touch_clean__low_cost_q30__k2|100|6   |         100 |         6 | oco_first_touch_clean | low_cost_q30;barrier=2.0   |              2 |           0        |          0        |          978 |                    3 |                322.667 |                 2.94793 |                  2.91779 |                            2.62794 |                            2.6509  |                       3 |          0.989775 | True        |
| USDJPY   | 2025-10      | 2025-07,2025-08,2025-09 |               2 | oco_first_touch_clean__low_cost_q50__k2   | oco_first_touch_clean__low_cost_q50__k2|100|6   |         100 |         6 | oco_first_touch_clean | low_cost_q50;barrier=2.0   |              2 |           0.785547 |          0.208459 |          697 |                    3 |                228     |                 2.48582 |                  2.43945 |                            2.11846 |                            2.17559 |                       3 |          0.981349 | True        |
| USDJPY   | 2025-11      | 2025-08,2025-09,2025-10 |               1 | oco_first_touch_clean__asia__k2           | oco_first_touch_clean__asia__k2|100|6           |         100 |         6 | oco_first_touch_clean | asia;barrier=2.0           |              2 |           0        |          0        |          613 |                    3 |                203.333 |                 3.1659  |                  3.15041 |                            2.82536 |                            2.69181 |                       3 |          0.995106 | True        |
| USDJPY   | 2025-12      | 2025-09,2025-10,2025-11 |               1 | oco_first_touch_clean__low_cost_q30__k2   | oco_first_touch_clean__low_cost_q30__k2|100|6   |         100 |         6 | oco_first_touch_clean | low_cost_q30;barrier=2.0   |              2 |           0        |          0        |          866 |                    3 |                286.667 |                 2.87279 |                  2.85289 |                            2.56886 |                            2.43882 |                       3 |          0.993072 | True        |
| USDJPY   | 2025-12      | 2025-09,2025-10,2025-11 |               2 | oco_first_touch_clean__asia__k2           | oco_first_touch_clean__asia__k2|100|5           |         100 |         5 | oco_first_touch_clean | asia;barrier=2.0           |              2 |           0.491096 |          0.201507 |          603 |                    3 |                200     |                 1.89183 |                  1.88242 |                            1.58019 |                            1.71941 |                       3 |          0.995025 | True        |
