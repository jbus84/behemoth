# AUDUSD OCO Reduced-Core Rolling Selection

## Setup
- family_keep: `oco_first_touch_clean`
- barrier_keep: `[2.0, 3.0]`
- horizon_keep: `[5, 6]`
- locked_quantile: `0.9`
- selection_mode: `auto`
- execution_mode: `stop_limit`
- stop_limit_detail_csv: `data/analysis/tick_opportunity_mining/stop_limit_tickfill_fullcap/AUDUSD_stop_limit_tickfill_detail.csv`
- stop_limit_cap_pips: `1.2`
- stop_limit_slippage_mode: `full_overshoot`
- stop_limit_match_rate: `0.998080`
- stop_limit_fill_rate_selected: `0.979048`
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
| AUDUSD   |               0.9 | auto             | stop_limit       |                    3 |             16 |               7 |         2305 |                2388 |           5.62386 |                   5.76455 |                       5.3192 |            5.42839 |                    5.65578 |                       5.18907 |                 7 |                        7 |          329.286 |                 341.143 |            0.965243 |           3951.43 |                     3000 |                    3000 | True                              |              0.45 |                  0.35 |            0.25 |                       0 |

## Reduced State Universe
| symbol   |   bar_ticks |   horizon | state_id                       | family                |   barrier_pips | regime_desc     |
|:---------|------------:|----------:|:-------------------------------|:----------------------|---------------:|:----------------|
| AUDUSD   |        1000 |         5 | oco_first_touch_clean__all__k2 | oco_first_touch_clean |              2 | all;barrier=2.0 |
| AUDUSD   |        1000 |         5 | oco_first_touch_clean__all__k3 | oco_first_touch_clean |              3 | all;barrier=3.0 |
| AUDUSD   |        1000 |         6 | oco_first_touch_clean__all__k2 | oco_first_touch_clean |              2 | all;barrier=2.0 |
| AUDUSD   |        1000 |         6 | oco_first_touch_clean__all__k3 | oco_first_touch_clean |              3 | all;barrier=3.0 |

## Monthly Portfolio
| symbol   | test_month   | train_months            |   states_selected |   rows |   signal_rows |   fill_rate |   mean_gross_pips |   mean_signal_pips |   median_gross_pips |   pos_rate |   state_churn_rate |   top_state_share |   state_hhi |   stability_pass | status         |
|:---------|:-------------|:------------------------|------------------:|-------:|--------------:|------------:|------------------:|-------------------:|--------------------:|-----------:|-------------------:|------------------:|------------:|-----------------:|:---------------|
| AUDUSD   | 2025-01      |                         |                 0 |      0 |             0 |  nan        |         nan       |          nan       |              nan    | nan        |         nan        |        nan        |  nan        |              nan | warmup_skip    |
| AUDUSD   | 2025-02      | 2025-01                 |                 0 |      0 |             0 |  nan        |         nan       |          nan       |              nan    | nan        |         nan        |        nan        |  nan        |              nan | warmup_skip    |
| AUDUSD   | 2025-03      | 2025-01,2025-02         |                 0 |      0 |             0 |  nan        |         nan       |          nan       |              nan    | nan        |         nan        |        nan        |  nan        |              nan | warmup_skip    |
| AUDUSD   | 2025-04      | 2025-01,2025-02,2025-03 |                 2 |    662 |           734 |    0.901907 |           5.46012 |            4.92452 |                3.5  |   0.544959 |           0        |          0.517711 |    0.500627 |                0 | ok             |
| AUDUSD   | 2025-05      | 2025-02,2025-03,2025-04 |                 1 |    195 |           195 |    1        |           7.13949 |            7.13949 |                5.4  |   0.779487 |           0.5      |          1        |    1        |                0 | ok             |
| AUDUSD   | 2025-06      | 2025-03,2025-04,2025-05 |                 2 |    432 |           436 |    0.990826 |           5.84792 |            5.79427 |                5.4  |   0.713303 |           0.5      |          0.545872 |    0.504208 |                0 | ok             |
| AUDUSD   | 2025-07      | 2025-04,2025-05,2025-06 |                 2 |    432 |           434 |    0.995392 |           4.98403 |            4.96106 |                3.7  |   0.68894  |           0.666667 |          0.589862 |    0.51615  |                0 | ok             |
| AUDUSD   | 2025-08      | 2025-05,2025-06,2025-07 |                 2 |    206 |           208 |    0.990385 |           5.45728 |            5.40481 |                4.85 |   0.735577 |           0        |          0.581731 |    0.51336  |                0 | ok             |
| AUDUSD   | 2025-09      | 2025-06,2025-07,2025-08 |                 1 |    197 |           198 |    0.994949 |           4.86193 |            4.83737 |                4.5  |   0.707071 |           0.5      |          1        |    1        |                0 | ok             |
| AUDUSD   | 2025-10      | 2025-07,2025-08,2025-09 |                 0 |      0 |             0 |  nan        |         nan       |          nan       |              nan    | nan        |         nan        |        nan        |  nan        |              nan | no_gate_states |
| AUDUSD   | 2025-11      | 2025-08,2025-09,2025-10 |                 0 |      0 |             0 |  nan        |         nan       |          nan       |              nan    | nan        |         nan        |        nan        |  nan        |              nan | no_gate_states |
| AUDUSD   | 2025-12      | 2025-09,2025-10,2025-11 |                 0 |      0 |             0 |  nan        |         nan       |          nan       |              nan    | nan        |         nan        |        nan        |  nan        |              nan | no_gate_states |
| AUDUSD   | 2026-01      | 2025-10,2025-11,2025-12 |                 1 |    181 |           183 |    0.989071 |           6.6011  |            6.52896 |                5.6  |   0.726776 |           0        |          1        |    1        |                0 | ok             |
| AUDUSD   | 2026-02      | 2025-11,2025-12,2026-01 |                 0 |      0 |             0 |  nan        |         nan       |          nan       |              nan    | nan        |         nan        |        nan        |  nan        |              nan | no_gate_states |
| AUDUSD   | 2026-03      | 2025-12,2026-01,2026-02 |                 0 |      0 |             0 |  nan        |         nan       |          nan       |              nan    | nan        |         nan        |        nan        |  nan        |              nan | no_gate_states |
| AUDUSD   | 2026-04      | 2026-01,2026-02,2026-03 |                 1 |      0 |             0 |  nan        |         nan       |          nan       |              nan    | nan        |           0        |        nan        |  nan        |                1 | no_test_rows   |

## State Stability
| symbol   | test_month   |   states_selected |   state_churn_rate |   top_state_share |   state_hhi |   stability_pass | status         |
|:---------|:-------------|------------------:|-------------------:|------------------:|------------:|-----------------:|:---------------|
| AUDUSD   | 2025-01      |                 0 |         nan        |        nan        |  nan        |              nan | warmup_skip    |
| AUDUSD   | 2025-02      |                 0 |         nan        |        nan        |  nan        |              nan | warmup_skip    |
| AUDUSD   | 2025-03      |                 0 |         nan        |        nan        |  nan        |              nan | warmup_skip    |
| AUDUSD   | 2025-04      |                 2 |           0        |          0.517711 |    0.500627 |                0 | ok             |
| AUDUSD   | 2025-05      |                 1 |           0.5      |          1        |    1        |                0 | ok             |
| AUDUSD   | 2025-06      |                 2 |           0.5      |          0.545872 |    0.504208 |                0 | ok             |
| AUDUSD   | 2025-07      |                 2 |           0.666667 |          0.589862 |    0.51615  |                0 | ok             |
| AUDUSD   | 2025-08      |                 2 |           0        |          0.581731 |    0.51336  |                0 | ok             |
| AUDUSD   | 2025-09      |                 1 |           0.5      |          1        |    1        |                0 | ok             |
| AUDUSD   | 2025-10      |                 0 |         nan        |        nan        |  nan        |              nan | no_gate_states |
| AUDUSD   | 2025-11      |                 0 |         nan        |        nan        |  nan        |              nan | no_gate_states |
| AUDUSD   | 2025-12      |                 0 |         nan        |        nan        |  nan        |              nan | no_gate_states |
| AUDUSD   | 2026-01      |                 1 |           0        |          1        |    1        |                0 | ok             |
| AUDUSD   | 2026-02      |                 0 |         nan        |        nan        |  nan        |              nan | no_gate_states |
| AUDUSD   | 2026-03      |                 0 |         nan        |        nan        |  nan        |              nan | no_gate_states |
| AUDUSD   | 2026-04      |                 1 |           0        |        nan        |  nan        |                1 | no_test_rows   |

## State Schedule (Top Rows)
| symbol   | test_month   | train_months            |   selected_rank | state_id                       | state_key                             |   bar_ticks |   horizon | family                | regime_desc     |   barrier_pips |   overlap_corr_max |   overlap_div_max |   train_rows |   train_months_count |   train_avg_month_rows |   train_mean_gross_pips |   train_mean_signal_pips |   train_lb95_trade_mean_gross_pips |   train_lb95_month_mean_gross_pips |   train_positive_months |   train_fill_rate | gate_pass   |
|:---------|:-------------|:------------------------|----------------:|:-------------------------------|:--------------------------------------|------------:|----------:|:----------------------|:----------------|---------------:|-------------------:|------------------:|-------------:|---------------------:|-----------------------:|------------------------:|-------------------------:|-----------------------------------:|-----------------------------------:|------------------------:|------------------:|:------------|
| AUDUSD   | 2025-04      | 2025-01,2025-02,2025-03 |               1 | oco_first_touch_clean__all__k2 | oco_first_touch_clean__all__k2|1000|6 |        1000 |         6 | oco_first_touch_clean | all;barrier=2.0 |              2 |           0        |          0        |          654 |                    3 |                216.333 |                 5.56749 |                  5.52492 |                            4.97135 |                            5.3923  |                       3 |          0.992355 | True        |
| AUDUSD   | 2025-04      | 2025-01,2025-02,2025-03 |               2 | oco_first_touch_clean__all__k3 | oco_first_touch_clean__all__k3|1000|5 |        1000 |         5 | oco_first_touch_clean | all;barrier=3.0 |              3 |           0.822327 |          0.147532 |          608 |                    3 |                200.667 |                 3.83106 |                  3.79326 |                            3.19352 |                            3.51351 |                       3 |          0.990132 | True        |
| AUDUSD   | 2025-05      | 2025-02,2025-03,2025-04 |               1 | oco_first_touch_clean__all__k2 | oco_first_touch_clean__all__k2|1000|6 |        1000 |         6 | oco_first_touch_clean | all;barrier=2.0 |              2 |           0        |          0        |          759 |                    3 |                246     |                 5.71504 |                  5.55692 |                            4.90343 |                            5.48457 |                       3 |          0.972332 | True        |
| AUDUSD   | 2025-06      | 2025-03,2025-04,2025-05 |               1 | oco_first_touch_clean__all__k2 | oco_first_touch_clean__all__k2|1000|6 |        1000 |         6 | oco_first_touch_clean | all;barrier=2.0 |              2 |           0        |          0        |          740 |                    3 |                239.667 |                 6.11586 |                  5.9423  |                            5.3048  |                            5.52609 |                       3 |          0.971622 | True        |
| AUDUSD   | 2025-06      | 2025-03,2025-04,2025-05 |               2 | oco_first_touch_clean__all__k2 | oco_first_touch_clean__all__k2|1000|5 |        1000 |         5 | oco_first_touch_clean | all;barrier=2.0 |              2 |           0.633519 |          0.365341 |          643 |                    3 |                205.333 |                 4.61932 |                  4.42535 |                            3.82436 |                            4.30936 |                       3 |          0.958009 | True        |
| AUDUSD   | 2025-07      | 2025-04,2025-05,2025-06 |               1 | oco_first_touch_clean__all__k2 | oco_first_touch_clean__all__k2|1000|6 |        1000 |         6 | oco_first_touch_clean | all;barrier=2.0 |              2 |           0        |          0        |          813 |                    3 |                263.333 |                 6.32595 |                  6.14699 |                            5.52137 |                            5.77464 |                       3 |          0.97171  | True        |
| AUDUSD   | 2025-07      | 2025-04,2025-05,2025-06 |               2 | oco_first_touch_clean__all__k3 | oco_first_touch_clean__all__k3|1000|6 |        1000 |         6 | oco_first_touch_clean | all;barrier=3.0 |              3 |           0.717342 |          0.152433 |          983 |                    3 |                309     |                 5.87573 |                  5.541   |                            4.99673 |                            5.29867 |                       3 |          0.943032 | True        |
| AUDUSD   | 2025-08      | 2025-05,2025-06,2025-07 |               1 | oco_first_touch_clean__all__k2 | oco_first_touch_clean__all__k2|1000|6 |        1000 |         6 | oco_first_touch_clean | all;barrier=2.0 |              2 |           0        |          0        |          611 |                    3 |                202.333 |                 6.4626  |                  6.42029 |                            5.78337 |                            5.83016 |                       3 |          0.993453 | True        |
| AUDUSD   | 2025-08      | 2025-05,2025-06,2025-07 |               2 | oco_first_touch_clean__all__k3 | oco_first_touch_clean__all__k3|1000|6 |        1000 |         6 | oco_first_touch_clean | all;barrier=3.0 |              3 |           0.817881 |          0.146487 |          837 |                    3 |                278     |                 5.4693  |                  5.4497  |                            4.89625 |                            4.94468 |                       3 |          0.996416 | True        |
| AUDUSD   | 2025-09      | 2025-06,2025-07,2025-08 |               1 | oco_first_touch_clean__all__k3 | oco_first_touch_clean__all__k3|1000|6 |        1000 |         6 | oco_first_touch_clean | all;barrier=3.0 |              3 |           0        |          0        |          699 |                    3 |                231.667 |                 5.33827 |                  5.30773 |                            4.74308 |                            4.73958 |                       3 |          0.994278 | True        |
| AUDUSD   | 2026-01      | 2025-10,2025-11,2025-12 |               1 | oco_first_touch_clean__all__k3 | oco_first_touch_clean__all__k3|1000|6 |        1000 |         6 | oco_first_touch_clean | all;barrier=3.0 |              3 |           0        |          0        |          625 |                    3 |                202.667 |                 3.34128 |                  3.2504  |                            2.72259 |                            2.4145  |                       3 |          0.9728   | True        |
| AUDUSD   | 2026-04      | 2026-01,2026-02,2026-03 |               1 | oco_first_touch_clean__all__k3 | oco_first_touch_clean__all__k3|1000|6 |        1000 |         6 | oco_first_touch_clean | all;barrier=3.0 |              3 |           0        |          0        |          667 |                    3 |                221.667 |                 6.20421 |                  6.18561 |                            5.41857 |                            6.05661 |                       3 |          0.997001 | True        |
