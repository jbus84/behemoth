# EURUSD OCO Reduced-Core Rolling Selection

## Setup
- family_keep: `oco_first_touch_clean`
- barrier_keep: `[2.0, 3.0]`
- horizon_keep: `[5, 6]`
- locked_quantile: `0.9`
- selection_mode: `auto`
- execution_mode: `stop_limit`
- stop_limit_detail_csv: `data/analysis/tick_opportunity_mining/stop_limit_tickfill_fullcap/EURUSD_stop_limit_tickfill_detail.csv`
- stop_limit_cap_pips: `1.2`
- stop_limit_slippage_mode: `full_overshoot`
- stop_limit_match_rate: `0.998775`
- stop_limit_fill_rate_selected: `0.991670`
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
| EURUSD   |               0.9 | auto             | stop_limit       |                    3 |              9 |               6 |         4898 |                4923 |           1.59847 |                   1.67778 |                      1.30417 |            1.59035 |                    1.66784 |                       1.31058 |                 6 |                        6 |          816.333 |                   820.5 |            0.994922 |              9796 |                     3000 |                    5000 | True                              |              0.45 |                  0.35 |            0.25 |                       0 |

## Reduced State Universe
| symbol   |   bar_ticks |   horizon | state_id                                    | family                |   barrier_pips | regime_desc                  |
|:---------|------------:|----------:|:--------------------------------------------|:----------------------|---------------:|:-----------------------------|
| EURUSD   |         100 |         6 | oco_first_touch_clean__asia__k2             | oco_first_touch_clean |              2 | asia;barrier=2.0             |
| EURUSD   |         100 |         6 | oco_first_touch_clean__high_abs_vel_q70__k2 | oco_first_touch_clean |              2 | high_abs_vel_q70;barrier=2.0 |
| EURUSD   |         100 |         6 | oco_first_touch_clean__high_abs_vel_q80__k2 | oco_first_touch_clean |              2 | high_abs_vel_q80;barrier=2.0 |
| EURUSD   |         100 |         6 | oco_first_touch_clean__high_range_q80__k2   | oco_first_touch_clean |              2 | high_range_q80;barrier=2.0   |
| EURUSD   |         100 |         6 | oco_first_touch_clean__ny_overlap__k2       | oco_first_touch_clean |              2 | ny_overlap;barrier=2.0       |

## Monthly Portfolio
| symbol   | test_month   | train_months            |   states_selected |   rows |   signal_rows |   fill_rate |   mean_gross_pips |   mean_signal_pips |   median_gross_pips |   pos_rate |   state_churn_rate |   top_state_share |   state_hhi |   stability_pass | status      |
|:---------|:-------------|:------------------------|------------------:|-------:|--------------:|------------:|------------------:|-------------------:|--------------------:|-----------:|-------------------:|------------------:|------------:|-----------------:|:------------|
| EURUSD   | 2025-04      |                         |                 0 |      0 |             0 |  nan        |         nan       |          nan       |               nan   | nan        |         nan        |        nan        |  nan        |              nan | warmup_skip |
| EURUSD   | 2025-05      | 2025-04                 |                 0 |      0 |             0 |  nan        |         nan       |          nan       |               nan   | nan        |         nan        |        nan        |  nan        |              nan | warmup_skip |
| EURUSD   | 2025-06      | 2025-04,2025-05         |                 0 |      0 |             0 |  nan        |         nan       |          nan       |               nan   | nan        |         nan        |        nan        |  nan        |              nan | warmup_skip |
| EURUSD   | 2025-07      | 2025-04,2025-05,2025-06 |                 1 |    659 |           667 |    0.988006 |           1.98346 |            1.95967 |                 1.6 |   0.664168 |           0        |          1        |    1        |                0 | ok          |
| EURUSD   | 2025-08      | 2025-05,2025-06,2025-07 |                 1 |    610 |           613 |    0.995106 |           2.80049 |            2.78679 |                 2.2 |   0.709625 |           1        |          1        |    1        |                0 | ok          |
| EURUSD   | 2025-09      | 2025-06,2025-07,2025-08 |                 2 |    793 |           799 |    0.992491 |           1.65813 |            1.64568 |                 1   |   0.609512 |           0.5      |          0.538173 |    0.502914 |                0 | ok          |
| EURUSD   | 2025-10      | 2025-07,2025-08,2025-09 |                 2 |   1220 |          1224 |    0.996732 |           1.4041  |            1.39951 |                 1.2 |   0.622549 |           1        |          0.591503 |    0.516746 |                0 | ok          |
| EURUSD   | 2025-11      | 2025-08,2025-09,2025-10 |                 2 |    724 |           725 |    0.998621 |           1.15898 |            1.15738 |                 1.1 |   0.606897 |           0.666667 |          0.508966 |    0.500161 |                0 | ok          |
| EURUSD   | 2025-12      | 2025-09,2025-10,2025-11 |                 2 |    892 |           895 |    0.996648 |           1.06155 |            1.05799 |                 0.7 |   0.591061 |           0.666667 |          0.598883 |    0.519556 |                0 | ok          |

## State Stability
| symbol   | test_month   |   states_selected |   state_churn_rate |   top_state_share |   state_hhi |   stability_pass | status      |
|:---------|:-------------|------------------:|-------------------:|------------------:|------------:|-----------------:|:------------|
| EURUSD   | 2025-04      |                 0 |         nan        |        nan        |  nan        |              nan | warmup_skip |
| EURUSD   | 2025-05      |                 0 |         nan        |        nan        |  nan        |              nan | warmup_skip |
| EURUSD   | 2025-06      |                 0 |         nan        |        nan        |  nan        |              nan | warmup_skip |
| EURUSD   | 2025-07      |                 1 |           0        |          1        |    1        |                0 | ok          |
| EURUSD   | 2025-08      |                 1 |           1        |          1        |    1        |                0 | ok          |
| EURUSD   | 2025-09      |                 2 |           0.5      |          0.538173 |    0.502914 |                0 | ok          |
| EURUSD   | 2025-10      |                 2 |           1        |          0.591503 |    0.516746 |                0 | ok          |
| EURUSD   | 2025-11      |                 2 |           0.666667 |          0.508966 |    0.500161 |                0 | ok          |
| EURUSD   | 2025-12      |                 2 |           0.666667 |          0.598883 |    0.519556 |                0 | ok          |

## State Schedule (Top Rows)
| symbol   | test_month   | train_months            |   selected_rank | state_id                                    | state_key                                         |   bar_ticks |   horizon | family                | regime_desc                  |   barrier_pips |   overlap_corr_max |   overlap_div_max |   train_rows |   train_months_count |   train_avg_month_rows |   train_mean_gross_pips |   train_mean_signal_pips |   train_lb95_trade_mean_gross_pips |   train_lb95_month_mean_gross_pips |   train_positive_months |   train_fill_rate | gate_pass   |
|:---------|:-------------|:------------------------|----------------:|:--------------------------------------------|:--------------------------------------------------|------------:|----------:|:----------------------|:-----------------------------|---------------:|-------------------:|------------------:|-------------:|---------------------:|-----------------------:|------------------------:|-------------------------:|-----------------------------------:|-----------------------------------:|------------------------:|------------------:|:------------|
| EURUSD   | 2025-07      | 2025-04,2025-05,2025-06 |               1 | oco_first_touch_clean__ny_overlap__k2       | oco_first_touch_clean__ny_overlap__k2|100|6       |         100 |         6 | oco_first_touch_clean | ny_overlap;barrier=2.0       |              2 |           0        |         0         |         1970 |                    3 |                649     |                 3.16179 |                  3.12487 |                            2.88115 |                            2.11007 |                       3 |          0.988325 | True        |
| EURUSD   | 2025-08      | 2025-05,2025-06,2025-07 |               1 | oco_first_touch_clean__high_range_q80__k2   | oco_first_touch_clean__high_range_q80__k2|100|6   |         100 |         6 | oco_first_touch_clean | high_range_q80;barrier=2.0   |              2 |           0        |         0         |         2921 |                    3 |                968     |                 2.25379 |                  2.24067 |                            2.08988 |                            2.00555 |                       3 |          0.99418  | True        |
| EURUSD   | 2025-09      | 2025-06,2025-07,2025-08 |               1 | oco_first_touch_clean__high_range_q80__k2   | oco_first_touch_clean__high_range_q80__k2|100|6   |         100 |         6 | oco_first_touch_clean | high_range_q80;barrier=2.0   |              2 |           0        |         0         |         2359 |                    3 |                783     |                 2.45785 |                  2.44744 |                            2.27083 |                            2.21244 |                       3 |          0.995761 | True        |
| EURUSD   | 2025-09      | 2025-06,2025-07,2025-08 |               2 | oco_first_touch_clean__ny_overlap__k2       | oco_first_touch_clean__ny_overlap__k2|100|6       |         100 |         6 | oco_first_touch_clean | ny_overlap;barrier=2.0       |              2 |           0.74624  |         0.302299  |         1578 |                    3 |                520.333 |                 1.83466 |                  1.81489 |                            1.64333 |                            1.62789 |                       3 |          0.989227 | True        |
| EURUSD   | 2025-10      | 2025-07,2025-08,2025-09 |               1 | oco_first_touch_clean__high_abs_vel_q70__k2 | oco_first_touch_clean__high_abs_vel_q70__k2|100|6 |         100 |         6 | oco_first_touch_clean | high_abs_vel_q70;barrier=2.0 |              2 |           0        |         0         |         1752 |                    3 |                580.333 |                 2.55135 |                  2.53533 |                            2.34137 |                            2.28561 |                       3 |          0.993721 | True        |
| EURUSD   | 2025-10      | 2025-07,2025-08,2025-09 |               2 | oco_first_touch_clean__asia__k2             | oco_first_touch_clean__asia__k2|100|6             |         100 |         6 | oco_first_touch_clean | asia;barrier=2.0             |              2 |           0.805431 |         0.359968  |         1098 |                    3 |                365     |                 1.63689 |                  1.63242 |                            1.43358 |                            1.48682 |                       3 |          0.997268 | True        |
| EURUSD   | 2025-11      | 2025-08,2025-09,2025-10 |               1 | oco_first_touch_clean__high_abs_vel_q80__k2 | oco_first_touch_clean__high_abs_vel_q80__k2|100|6 |         100 |         6 | oco_first_touch_clean | high_abs_vel_q80;barrier=2.0 |              2 |           0        |         0         |         1519 |                    3 |                500.333 |                 2.20973 |                  2.18354 |                            1.98544 |                            1.75059 |                       3 |          0.98815  | True        |
| EURUSD   | 2025-11      | 2025-08,2025-09,2025-10 |               2 | oco_first_touch_clean__high_abs_vel_q70__k2 | oco_first_touch_clean__high_abs_vel_q70__k2|100|6 |         100 |         6 | oco_first_touch_clean | high_abs_vel_q70;barrier=2.0 |              2 |           0.826792 |         0.0199501 |         1554 |                    3 |                514.667 |                 2.12753 |                  2.11384 |                            1.8965  |                            1.59332 |                       3 |          0.993565 | True        |
| EURUSD   | 2025-12      | 2025-09,2025-10,2025-11 |               1 | oco_first_touch_clean__high_range_q80__k2   | oco_first_touch_clean__high_range_q80__k2|100|6   |         100 |         6 | oco_first_touch_clean | high_range_q80;barrier=2.0   |              2 |           0        |         0         |         1165 |                    3 |                386     |                 1.66028 |                  1.6503  |                            1.47009 |                            1.50991 |                       3 |          0.993991 | True        |
| EURUSD   | 2025-12      | 2025-09,2025-10,2025-11 |               2 | oco_first_touch_clean__high_abs_vel_q80__k2 | oco_first_touch_clean__high_abs_vel_q80__k2|100|6 |         100 |         6 | oco_first_touch_clean | high_abs_vel_q80;barrier=2.0 |              2 |           0.709815 |         0.161082  |         1271 |                    3 |                419.333 |                 1.59618 |                  1.57986 |                            1.39635 |                            1.34312 |                       3 |          0.989772 | True        |
