# GBPUSD OCO Reduced-Core Rolling Selection

## Setup
- family_keep: `oco_first_touch_clean`
- barrier_keep: `[2.0, 3.0]`
- horizon_keep: `[5, 6]`
- locked_quantile: `0.9`
- selection_mode: `auto`
- execution_mode: `stop_limit`
- stop_limit_detail_csv: `data/analysis/tick_opportunity_mining/stop_limit_tickfill_fullcap/GBPUSD_stop_limit_tickfill_detail.csv`
- stop_limit_cap_pips: `1.2`
- stop_limit_slippage_mode: `full_overshoot`
- stop_limit_match_rate: `0.999256`
- stop_limit_fill_rate_selected: `0.994546`
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
| GBPUSD   |               0.9 | auto             | stop_limit       |                    3 |              9 |               6 |         1916 |                1924 |           2.07056 |                   2.13763 |                      1.80556 |            2.06195 |                    2.13105 |                       1.85362 |                 6 |                        6 |          319.333 |                 320.667 |            0.995842 |              3832 |                     3000 |                    5000 | False                             |              0.45 |                  0.35 |            0.25 |                       0 |

## Reduced State Universe
| symbol   |   bar_ticks |   horizon | state_id                                  | family                |   barrier_pips | regime_desc                |
|:---------|------------:|----------:|:------------------------------------------|:----------------------|---------------:|:---------------------------|
| GBPUSD   |         100 |         6 | oco_first_touch_clean__asia__k2           | oco_first_touch_clean |              2 | asia;barrier=2.0           |
| GBPUSD   |         100 |         6 | oco_first_touch_clean__high_range_q70__k2 | oco_first_touch_clean |              2 | high_range_q70;barrier=2.0 |
| GBPUSD   |         100 |         6 | oco_first_touch_clean__london__k2         | oco_first_touch_clean |              2 | london;barrier=2.0         |
| GBPUSD   |         100 |         6 | oco_first_touch_clean__low_cost_q50__k2   | oco_first_touch_clean |              2 | low_cost_q50;barrier=2.0   |

## Monthly Portfolio
| symbol   | test_month   | train_months            |   states_selected |   rows |   signal_rows |   fill_rate |   mean_gross_pips |   mean_signal_pips |   median_gross_pips |   pos_rate |   state_churn_rate |   top_state_share |   state_hhi |   stability_pass | status      |
|:---------|:-------------|:------------------------|------------------:|-------:|--------------:|------------:|------------------:|-------------------:|--------------------:|-----------:|-------------------:|------------------:|------------:|-----------------:|:------------|
| GBPUSD   | 2025-04      |                         |                 0 |      0 |             0 |  nan        |         nan       |          nan       |              nan    | nan        |              nan   |        nan        |  nan        |              nan | warmup_skip |
| GBPUSD   | 2025-05      | 2025-04                 |                 0 |      0 |             0 |  nan        |         nan       |          nan       |              nan    | nan        |              nan   |        nan        |  nan        |              nan | warmup_skip |
| GBPUSD   | 2025-06      | 2025-04,2025-05         |                 0 |      0 |             0 |  nan        |         nan       |          nan       |              nan    | nan        |              nan   |        nan        |  nan        |              nan | warmup_skip |
| GBPUSD   | 2025-07      | 2025-04,2025-05,2025-06 |                 1 |    294 |           296 |    0.993243 |           2.34762 |            2.33176 |                1.85 |   0.648649 |                0   |          1        |    1        |                0 | ok          |
| GBPUSD   | 2025-08      | 2025-05,2025-06,2025-07 |                 2 |    283 |           283 |    1        |           2.28799 |            2.28799 |                2.3  |   0.685512 |                0.5 |          0.5053   |    0.500056 |                0 | ok          |
| GBPUSD   | 2025-09      | 2025-06,2025-07,2025-08 |                 1 |    309 |           309 |    1        |           2.28997 |            2.28997 |                2    |   0.71521  |                1   |          1        |    1        |                0 | ok          |
| GBPUSD   | 2025-10      | 2025-07,2025-08,2025-09 |                 2 |    482 |           486 |    0.99177  |           1.97303 |            1.95679 |                1.5  |   0.652263 |                0.5 |          0.54321  |    0.503734 |                0 | ok          |
| GBPUSD   | 2025-11      | 2025-08,2025-09,2025-10 |                 1 |    192 |           192 |    1        |           2.60469 |            2.60469 |                2.25 |   0.708333 |                0.5 |          1        |    1        |                0 | ok          |
| GBPUSD   | 2025-12      | 2025-09,2025-10,2025-11 |                 2 |    356 |           358 |    0.994413 |           1.32247 |            1.31508 |                1    |   0.611732 |                0.5 |          0.530726 |    0.501888 |                0 | ok          |

## State Stability
| symbol   | test_month   |   states_selected |   state_churn_rate |   top_state_share |   state_hhi |   stability_pass | status      |
|:---------|:-------------|------------------:|-------------------:|------------------:|------------:|-----------------:|:------------|
| GBPUSD   | 2025-04      |                 0 |              nan   |        nan        |  nan        |              nan | warmup_skip |
| GBPUSD   | 2025-05      |                 0 |              nan   |        nan        |  nan        |              nan | warmup_skip |
| GBPUSD   | 2025-06      |                 0 |              nan   |        nan        |  nan        |              nan | warmup_skip |
| GBPUSD   | 2025-07      |                 1 |                0   |          1        |    1        |                0 | ok          |
| GBPUSD   | 2025-08      |                 2 |                0.5 |          0.5053   |    0.500056 |                0 | ok          |
| GBPUSD   | 2025-09      |                 1 |                1   |          1        |    1        |                0 | ok          |
| GBPUSD   | 2025-10      |                 2 |                0.5 |          0.54321  |    0.503734 |                0 | ok          |
| GBPUSD   | 2025-11      |                 1 |                0.5 |          1        |    1        |                0 | ok          |
| GBPUSD   | 2025-12      |                 2 |                0.5 |          0.530726 |    0.501888 |                0 | ok          |

## State Schedule (Top Rows)
| symbol   | test_month   | train_months            |   selected_rank | state_id                                  | state_key                                       |   bar_ticks |   horizon | family                | regime_desc                |   barrier_pips |   overlap_corr_max |   overlap_div_max |   train_rows |   train_months_count |   train_avg_month_rows |   train_mean_gross_pips |   train_mean_signal_pips |   train_lb95_trade_mean_gross_pips |   train_lb95_month_mean_gross_pips |   train_positive_months |   train_fill_rate | gate_pass   |
|:---------|:-------------|:------------------------|----------------:|:------------------------------------------|:------------------------------------------------|------------:|----------:|:----------------------|:---------------------------|---------------:|-------------------:|------------------:|-------------:|---------------------:|-----------------------:|------------------------:|-------------------------:|-----------------------------------:|-----------------------------------:|------------------------:|------------------:|:------------|
| GBPUSD   | 2025-07      | 2025-04,2025-05,2025-06 |               1 | oco_first_touch_clean__high_range_q70__k2 | oco_first_touch_clean__high_range_q70__k2|100|6 |         100 |         6 | oco_first_touch_clean | high_range_q70;barrier=2.0 |              2 |           0        |          0        |          800 |                    3 |                264.667 |                 3.1102  |                  3.08687 |                            2.80631 |                            2.93    |                       3 |          0.9925   | True        |
| GBPUSD   | 2025-08      | 2025-05,2025-06,2025-07 |               1 | oco_first_touch_clean__high_range_q70__k2 | oco_first_touch_clean__high_range_q70__k2|100|6 |         100 |         6 | oco_first_touch_clean | high_range_q70;barrier=2.0 |              2 |           0        |          0        |          758 |                    3 |                250.667 |                 2.77048 |                  2.74855 |                            2.47536 |                            2.53117 |                       3 |          0.992084 | True        |
| GBPUSD   | 2025-08      | 2025-05,2025-06,2025-07 |               2 | oco_first_touch_clean__low_cost_q50__k2   | oco_first_touch_clean__low_cost_q50__k2|100|6   |         100 |         6 | oco_first_touch_clean | low_cost_q50;barrier=2.0   |              2 |           0.724696 |          0.159456 |          740 |                    3 |                245     |                 2.47537 |                  2.45865 |                            2.16316 |                            2.37283 |                       3 |          0.993243 | True        |
| GBPUSD   | 2025-09      | 2025-06,2025-07,2025-08 |               1 | oco_first_touch_clean__london__k2         | oco_first_touch_clean__london__k2|100|6         |         100 |         6 | oco_first_touch_clean | london;barrier=2.0         |              2 |           0        |          0        |          836 |                    3 |                278     |                 2.82698 |                  2.82022 |                            2.49176 |                            2.65931 |                       3 |          0.997608 | True        |
| GBPUSD   | 2025-10      | 2025-07,2025-08,2025-09 |               1 | oco_first_touch_clean__london__k2         | oco_first_touch_clean__london__k2|100|6         |         100 |         6 | oco_first_touch_clean | london;barrier=2.0         |              2 |           0        |          0        |          900 |                    3 |                299.333 |                 2.70223 |                  2.69622 |                            2.41071 |                            2.448   |                       3 |          0.997778 | True        |
| GBPUSD   | 2025-10      | 2025-07,2025-08,2025-09 |               2 | oco_first_touch_clean__low_cost_q50__k2   | oco_first_touch_clean__low_cost_q50__k2|100|6   |         100 |         6 | oco_first_touch_clean | low_cost_q50;barrier=2.0   |              2 |           0.573158 |          0.378121 |          712 |                    3 |                236     |                 2.09986 |                  2.08806 |                            1.80624 |                            1.83213 |                       3 |          0.994382 | True        |
| GBPUSD   | 2025-11      | 2025-08,2025-09,2025-10 |               1 | oco_first_touch_clean__london__k2         | oco_first_touch_clean__london__k2|100|6         |         100 |         6 | oco_first_touch_clean | london;barrier=2.0         |              2 |           0        |          0        |          829 |                    3 |                275.667 |                 2.40919 |                  2.40338 |                            2.13253 |                            2.2209  |                       3 |          0.997587 | True        |
| GBPUSD   | 2025-12      | 2025-09,2025-10,2025-11 |               1 | oco_first_touch_clean__london__k2         | oco_first_touch_clean__london__k2|100|6         |         100 |         6 | oco_first_touch_clean | london;barrier=2.0         |              2 |           0        |          0        |          765 |                    3 |                254.667 |                 2.33626 |                  2.3332  |                            2.05803 |                            2.2209  |                       3 |          0.998693 | True        |
| GBPUSD   | 2025-12      | 2025-09,2025-10,2025-11 |               2 | oco_first_touch_clean__asia__k2           | oco_first_touch_clean__asia__k2|100|6           |         100 |         6 | oco_first_touch_clean | asia;barrier=2.0           |              2 |           0.566032 |          0.167101 |          744 |                    3 |                247.333 |                 2.09218 |                  2.08656 |                            1.81352 |                            1.7172  |                       3 |          0.997312 | True        |
