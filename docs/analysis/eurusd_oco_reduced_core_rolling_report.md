# EURUSD OCO Reduced-Core Rolling Selection

## Setup
- family_keep: `oco_first_touch_clean`
- barrier_keep: `[2.0, 3.0]`
- horizon_keep: `[5, 6]`
- locked_quantile: `0.9`
- selection_mode: `auto`
- execution_mode: `stop_limit`
- stop_limit_detail_csv: `data/analysis/tick_opportunity_mining/stop_limit_tickfill_eurusd_fixed/EURUSD_stop_limit_tickfill_detail.csv`
- stop_limit_cap_pips: `1.2`
- stop_limit_slippage_mode: `full_overshoot`
- stop_limit_match_rate: `0.999183`
- stop_limit_fill_rate_selected: `0.990249`
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
| EURUSD   |               0.9 | auto             | stop_limit       |                    3 |              9 |               3 |          661 |                 667 |           2.76929 |                   2.64718 |                      2.30087 |            2.74438 |                    2.62025 |                        2.2724 |                 3 |                        3 |          220.333 |                 222.333 |            0.991004 |              2644 |                     3000 |                    5000 | False                             |              0.45 |                  0.35 |            0.25 |                       0 |

## Reduced State Universe
| symbol   |   bar_ticks |   horizon | state_id                                    | family                |   barrier_pips | regime_desc                  |
|:---------|------------:|----------:|:--------------------------------------------|:----------------------|---------------:|:-----------------------------|
| EURUSD   |         100 |         5 | oco_first_touch_clean__high_range_q70__k2   | oco_first_touch_clean |              2 | high_range_q70;barrier=2.0   |
| EURUSD   |         100 |         6 | oco_first_touch_clean__high_abs_vel_q80__k2 | oco_first_touch_clean |              2 | high_abs_vel_q80;barrier=2.0 |
| EURUSD   |         100 |         6 | oco_first_touch_clean__high_range_q70__k2   | oco_first_touch_clean |              2 | high_range_q70;barrier=2.0   |
| EURUSD   |         100 |         6 | oco_first_touch_clean__high_range_q80__k2   | oco_first_touch_clean |              2 | high_range_q80;barrier=2.0   |

## Monthly Portfolio
| symbol   | test_month   | train_months            |   states_selected |   rows |   signal_rows |   fill_rate |   mean_gross_pips |   mean_signal_pips |   median_gross_pips |   pos_rate |   state_churn_rate |   top_state_share |   state_hhi |   stability_pass | status         |
|:---------|:-------------|:------------------------|------------------:|-------:|--------------:|------------:|------------------:|-------------------:|--------------------:|-----------:|-------------------:|------------------:|------------:|-----------------:|:---------------|
| EURUSD   | 2025-04      |                         |                 0 |      0 |             0 |  nan        |         nan       |          nan       |              nan    | nan        |              nan   |        nan        |  nan        |              nan | warmup_skip    |
| EURUSD   | 2025-05      | 2025-04                 |                 0 |      0 |             0 |  nan        |         nan       |          nan       |              nan    | nan        |              nan   |        nan        |  nan        |              nan | warmup_skip    |
| EURUSD   | 2025-06      | 2025-04,2025-05         |                 0 |      0 |             0 |  nan        |         nan       |          nan       |              nan    | nan        |              nan   |        nan        |  nan        |              nan | warmup_skip    |
| EURUSD   | 2025-07      | 2025-04,2025-05,2025-06 |                 2 |    292 |           295 |    0.989831 |           3.27603 |            3.24271 |                2.8  |   0.722034 |                0   |          0.610169 |    0.524275 |                0 | ok             |
| EURUSD   | 2025-08      | 2025-05,2025-06,2025-07 |                 2 |    253 |           254 |    0.996063 |           2.42846 |            2.4189  |                2    |   0.704724 |                1   |          0.590551 |    0.516399 |                0 | ok             |
| EURUSD   | 2025-09      | 2025-06,2025-07,2025-08 |                 1 |    116 |           118 |    0.983051 |           2.23707 |            2.19915 |                2.15 |   0.652542 |                0.5 |          1        |    1        |                0 | ok             |
| EURUSD   | 2025-10      | 2025-07,2025-08,2025-09 |                 0 |      0 |             0 |  nan        |         nan       |          nan       |              nan    | nan        |              nan   |        nan        |  nan        |              nan | no_gate_states |
| EURUSD   | 2025-11      | 2025-08,2025-09,2025-10 |                 0 |      0 |             0 |  nan        |         nan       |          nan       |              nan    | nan        |              nan   |        nan        |  nan        |              nan | no_gate_states |
| EURUSD   | 2025-12      | 2025-09,2025-10,2025-11 |                 0 |      0 |             0 |  nan        |         nan       |          nan       |              nan    | nan        |              nan   |        nan        |  nan        |              nan | no_gate_states |

## State Stability
| symbol   | test_month   |   states_selected |   state_churn_rate |   top_state_share |   state_hhi |   stability_pass | status         |
|:---------|:-------------|------------------:|-------------------:|------------------:|------------:|-----------------:|:---------------|
| EURUSD   | 2025-04      |                 0 |              nan   |        nan        |  nan        |              nan | warmup_skip    |
| EURUSD   | 2025-05      |                 0 |              nan   |        nan        |  nan        |              nan | warmup_skip    |
| EURUSD   | 2025-06      |                 0 |              nan   |        nan        |  nan        |              nan | warmup_skip    |
| EURUSD   | 2025-07      |                 2 |                0   |          0.610169 |    0.524275 |                0 | ok             |
| EURUSD   | 2025-08      |                 2 |                1   |          0.590551 |    0.516399 |                0 | ok             |
| EURUSD   | 2025-09      |                 1 |                0.5 |          1        |    1        |                0 | ok             |
| EURUSD   | 2025-10      |                 0 |              nan   |        nan        |  nan        |              nan | no_gate_states |
| EURUSD   | 2025-11      |                 0 |              nan   |        nan        |  nan        |              nan | no_gate_states |
| EURUSD   | 2025-12      |                 0 |              nan   |        nan        |  nan        |              nan | no_gate_states |

## State Schedule (Top Rows)
| symbol   | test_month   | train_months            |   selected_rank | state_id                                    | state_key                                         |   bar_ticks |   horizon | family                | regime_desc                  |   barrier_pips |   overlap_corr_max |   overlap_div_max |   train_rows |   train_months_count |   train_avg_month_rows |   train_mean_gross_pips |   train_mean_signal_pips |   train_lb95_trade_mean_gross_pips |   train_lb95_month_mean_gross_pips |   train_positive_months |   train_fill_rate | gate_pass   |
|:---------|:-------------|:------------------------|----------------:|:--------------------------------------------|:--------------------------------------------------|------------:|----------:|:----------------------|:-----------------------------|---------------:|-------------------:|------------------:|-------------:|---------------------:|-----------------------:|------------------------:|-------------------------:|-----------------------------------:|-----------------------------------:|------------------------:|------------------:|:------------|
| EURUSD   | 2025-07      | 2025-04,2025-05,2025-06 |               1 | oco_first_touch_clean__high_abs_vel_q80__k2 | oco_first_touch_clean__high_abs_vel_q80__k2|100|6 |         100 |         6 | oco_first_touch_clean | high_abs_vel_q80;barrier=2.0 |              2 |           0        |         0         |          688 |                    3 |                225.667 |                 3.01256 |                  2.96439 |                            2.60931 |                            2.05405 |                       3 |          0.984012 | True        |
| EURUSD   | 2025-07      | 2025-04,2025-05,2025-06 |               2 | oco_first_touch_clean__high_range_q70__k2   | oco_first_touch_clean__high_range_q70__k2|100|5   |         100 |         5 | oco_first_touch_clean | high_range_q70;barrier=2.0   |              2 |           0.706742 |         0.285911  |          703 |                    3 |                233.333 |                 2.13943 |                  2.1303  |                            1.84963 |                            1.51986 |                       3 |          0.995733 | True        |
| EURUSD   | 2025-08      | 2025-05,2025-06,2025-07 |               1 | oco_first_touch_clean__high_range_q80__k2   | oco_first_touch_clean__high_range_q80__k2|100|6   |         100 |         6 | oco_first_touch_clean | high_range_q80;barrier=2.0   |              2 |           0        |         0         |          669 |                    3 |                222.333 |                 2.08906 |                  2.08281 |                            1.7662  |                            1.73237 |                       3 |          0.99701  | True        |
| EURUSD   | 2025-08      | 2025-05,2025-06,2025-07 |               2 | oco_first_touch_clean__high_range_q70__k2   | oco_first_touch_clean__high_range_q70__k2|100|6   |         100 |         6 | oco_first_touch_clean | high_range_q70;barrier=2.0   |              2 |           0.846504 |         0.0454604 |          609 |                    3 |                201.333 |                 1.92252 |                  1.90673 |                            1.58911 |                            1.41387 |                       3 |          0.99179  | True        |
| EURUSD   | 2025-09      | 2025-06,2025-07,2025-08 |               1 | oco_first_touch_clean__high_range_q80__k2   | oco_first_touch_clean__high_range_q80__k2|100|6   |         100 |         6 | oco_first_touch_clean | high_range_q80;barrier=2.0   |              2 |           0        |         0         |          611 |                    3 |                202.667 |                 2.30214 |                  2.29083 |                            1.97149 |                            1.98197 |                       3 |          0.99509  | True        |
