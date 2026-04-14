# USDCHF OCO Reduced-Core Rolling Selection

## Setup
- family_keep: `oco_first_touch_clean`
- barrier_keep: `[2.0, 3.0]`
- horizon_keep: `[5, 6]`
- locked_quantile: `0.9`
- selection_mode: `auto`
- execution_mode: `stop_limit`
- stop_limit_detail_csv: `data/analysis/tick_opportunity_mining/stop_limit_tickfill_fullcap/USDCHF_stop_limit_tickfill_detail.csv`
- stop_limit_cap_pips: `1.2`
- stop_limit_slippage_mode: `full_overshoot`
- stop_limit_match_rate: `0.999648`
- stop_limit_fill_rate_selected: `0.982848`
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
| USDCHF   |               0.9 | auto             | stop_limit       |                    3 |             16 |               6 |         1710 |                1773 |            5.9738 |                   5.74226 |                      4.69595 |            5.76153 |                    5.55772 |                       4.63292 |                 6 |                        6 |              285 |                   295.5 |            0.964467 |              3420 |                     3000 |                    3000 | True                              |              0.45 |                  0.35 |            0.25 |                       0 |

## Reduced State Universe
| symbol   |   bar_ticks |   horizon | state_id                       | family                |   barrier_pips | regime_desc     |
|:---------|------------:|----------:|:-------------------------------|:----------------------|---------------:|:----------------|
| USDCHF   |        1000 |         5 | oco_first_touch_clean__all__k3 | oco_first_touch_clean |              3 | all;barrier=3.0 |
| USDCHF   |        1000 |         6 | oco_first_touch_clean__all__k2 | oco_first_touch_clean |              2 | all;barrier=2.0 |
| USDCHF   |        1000 |         6 | oco_first_touch_clean__all__k3 | oco_first_touch_clean |              3 | all;barrier=3.0 |

## Monthly Portfolio
| symbol   | test_month   | train_months            |   states_selected |   rows |   signal_rows |   fill_rate |   mean_gross_pips |   mean_signal_pips |   median_gross_pips |   pos_rate |   state_churn_rate |   top_state_share |   state_hhi |   stability_pass | status         |
|:---------|:-------------|:------------------------|------------------:|-------:|--------------:|------------:|------------------:|-------------------:|--------------------:|-----------:|-------------------:|------------------:|------------:|-----------------:|:---------------|
| USDCHF   | 2025-01      |                         |                 0 |      0 |             0 |  nan        |         nan       |          nan       |              nan    | nan        |              nan   |        nan        |  nan        |              nan | warmup_skip    |
| USDCHF   | 2025-02      | 2025-01                 |                 0 |      0 |             0 |  nan        |         nan       |          nan       |              nan    | nan        |              nan   |        nan        |  nan        |              nan | warmup_skip    |
| USDCHF   | 2025-03      | 2025-01,2025-02         |                 0 |      0 |             0 |  nan        |         nan       |          nan       |              nan    | nan        |              nan   |        nan        |  nan        |              nan | warmup_skip    |
| USDCHF   | 2025-04      | 2025-01,2025-02,2025-03 |                 1 |    422 |           472 |    0.894068 |           7.86303 |            7.03008 |                5.05 |   0.542373 |                0   |          1        |    1        |                0 | ok             |
| USDCHF   | 2025-05      | 2025-02,2025-03,2025-04 |                 2 |    519 |           526 |    0.986692 |           5.83314 |            5.75551 |                5.3  |   0.69962  |                1   |          0.593156 |    0.517356 |                0 | ok             |
| USDCHF   | 2025-06      | 2025-03,2025-04,2025-05 |                 1 |    156 |           157 |    0.993631 |           5.97821 |            5.94013 |                4.5  |   0.738854 |                0.5 |          1        |    1        |                0 | ok             |
| USDCHF   | 2025-07      | 2025-04,2025-05,2025-06 |                 1 |    120 |           122 |    0.983607 |           6.67917 |            6.56967 |                6.75 |   0.729508 |                0   |          1        |    1        |                0 | ok             |
| USDCHF   | 2025-08      | 2025-05,2025-06,2025-07 |                 2 |    331 |           333 |    0.993994 |           4.8716  |            4.84234 |                3.9  |   0.657658 |                1   |          0.51952  |    0.500762 |                0 | ok             |
| USDCHF   | 2025-09      | 2025-06,2025-07,2025-08 |                 1 |    162 |           163 |    0.993865 |           3.2284  |            3.20859 |                2.45 |   0.631902 |                0.5 |          1        |    1        |                0 | ok             |
| USDCHF   | 2025-10      | 2025-07,2025-08,2025-09 |                 0 |      0 |             0 |  nan        |         nan       |          nan       |              nan    | nan        |              nan   |        nan        |  nan        |              nan | no_gate_states |
| USDCHF   | 2025-11      | 2025-08,2025-09,2025-10 |                 0 |      0 |             0 |  nan        |         nan       |          nan       |              nan    | nan        |              nan   |        nan        |  nan        |              nan | no_gate_states |
| USDCHF   | 2025-12      | 2025-09,2025-10,2025-11 |                 0 |      0 |             0 |  nan        |         nan       |          nan       |              nan    | nan        |              nan   |        nan        |  nan        |              nan | no_gate_states |
| USDCHF   | 2026-01      | 2025-10,2025-11,2025-12 |                 0 |      0 |             0 |  nan        |         nan       |          nan       |              nan    | nan        |              nan   |        nan        |  nan        |              nan | no_gate_states |
| USDCHF   | 2026-02      | 2025-11,2025-12,2026-01 |                 0 |      0 |             0 |  nan        |         nan       |          nan       |              nan    | nan        |              nan   |        nan        |  nan        |              nan | no_gate_states |
| USDCHF   | 2026-03      | 2025-12,2026-01,2026-02 |                 0 |      0 |             0 |  nan        |         nan       |          nan       |              nan    | nan        |              nan   |        nan        |  nan        |              nan | no_gate_states |
| USDCHF   | 2026-04      | 2026-01,2026-02,2026-03 |                 1 |      0 |             0 |  nan        |         nan       |          nan       |              nan    | nan        |                1   |        nan        |  nan        |                0 | no_test_rows   |

## State Stability
| symbol   | test_month   |   states_selected |   state_churn_rate |   top_state_share |   state_hhi |   stability_pass | status         |
|:---------|:-------------|------------------:|-------------------:|------------------:|------------:|-----------------:|:---------------|
| USDCHF   | 2025-01      |                 0 |              nan   |        nan        |  nan        |              nan | warmup_skip    |
| USDCHF   | 2025-02      |                 0 |              nan   |        nan        |  nan        |              nan | warmup_skip    |
| USDCHF   | 2025-03      |                 0 |              nan   |        nan        |  nan        |              nan | warmup_skip    |
| USDCHF   | 2025-04      |                 1 |                0   |          1        |    1        |                0 | ok             |
| USDCHF   | 2025-05      |                 2 |                1   |          0.593156 |    0.517356 |                0 | ok             |
| USDCHF   | 2025-06      |                 1 |                0.5 |          1        |    1        |                0 | ok             |
| USDCHF   | 2025-07      |                 1 |                0   |          1        |    1        |                0 | ok             |
| USDCHF   | 2025-08      |                 2 |                1   |          0.51952  |    0.500762 |                0 | ok             |
| USDCHF   | 2025-09      |                 1 |                0.5 |          1        |    1        |                0 | ok             |
| USDCHF   | 2025-10      |                 0 |              nan   |        nan        |  nan        |              nan | no_gate_states |
| USDCHF   | 2025-11      |                 0 |              nan   |        nan        |  nan        |              nan | no_gate_states |
| USDCHF   | 2025-12      |                 0 |              nan   |        nan        |  nan        |              nan | no_gate_states |
| USDCHF   | 2026-01      |                 0 |              nan   |        nan        |  nan        |              nan | no_gate_states |
| USDCHF   | 2026-02      |                 0 |              nan   |        nan        |  nan        |              nan | no_gate_states |
| USDCHF   | 2026-03      |                 0 |              nan   |        nan        |  nan        |              nan | no_gate_states |
| USDCHF   | 2026-04      |                 1 |                1   |        nan        |  nan        |                0 | no_test_rows   |

## State Schedule (Top Rows)
| symbol   | test_month   | train_months            |   selected_rank | state_id                       | state_key                             |   bar_ticks |   horizon | family                | regime_desc     |   barrier_pips |   overlap_corr_max |   overlap_div_max |   train_rows |   train_months_count |   train_avg_month_rows |   train_mean_gross_pips |   train_mean_signal_pips |   train_lb95_trade_mean_gross_pips |   train_lb95_month_mean_gross_pips |   train_positive_months |   train_fill_rate | gate_pass   |
|:---------|:-------------|:------------------------|----------------:|:-------------------------------|:--------------------------------------|------------:|----------:|:----------------------|:----------------|---------------:|-------------------:|------------------:|-------------:|---------------------:|-----------------------:|------------------------:|-------------------------:|-----------------------------------:|-----------------------------------:|------------------------:|------------------:|:------------|
| USDCHF   | 2025-04      | 2025-01,2025-02,2025-03 |               1 | oco_first_touch_clean__all__k3 | oco_first_touch_clean__all__k3|1000|6 |        1000 |         6 | oco_first_touch_clean | all;barrier=3.0 |              3 |           0        |          0        |          603 |                    3 |                200     |                 4.68083 |                  4.65755 |                            4.07352 |                            4.3922  |                       3 |          0.995025 | True        |
| USDCHF   | 2025-05      | 2025-02,2025-03,2025-04 |               1 | oco_first_touch_clean__all__k2 | oco_first_touch_clean__all__k2|1000|6 |        1000 |         6 | oco_first_touch_clean | all;barrier=2.0 |              2 |           0        |          0        |          729 |                    3 |                236.667 |                 6.63099 |                  6.45816 |                            5.72969 |                            5.42854 |                       3 |          0.973937 | True        |
| USDCHF   | 2025-05      | 2025-02,2025-03,2025-04 |               2 | oco_first_touch_clean__all__k3 | oco_first_touch_clean__all__k3|1000|5 |        1000 |         5 | oco_first_touch_clean | all;barrier=3.0 |              3 |           0.759585 |          0.224292 |          668 |                    3 |                208     |                 5.51154 |                  5.1485  |                            4.38815 |                            4.28302 |                       3 |          0.934132 | True        |
| USDCHF   | 2025-06      | 2025-03,2025-04,2025-05 |               1 | oco_first_touch_clean__all__k2 | oco_first_touch_clean__all__k2|1000|6 |        1000 |         6 | oco_first_touch_clean | all;barrier=2.0 |              2 |           0        |          0        |          737 |                    3 |                238     |                 7.20434 |                  6.97951 |                            6.25602 |                            6.3666  |                       3 |          0.968792 | True        |
| USDCHF   | 2025-07      | 2025-04,2025-05,2025-06 |               1 | oco_first_touch_clean__all__k2 | oco_first_touch_clean__all__k2|1000|6 |        1000 |         6 | oco_first_touch_clean | all;barrier=2.0 |              2 |           0        |          0        |          725 |                    3 |                234     |                 7.19373 |                  6.96552 |                            6.17761 |                            6.27737 |                       3 |          0.968276 | True        |
| USDCHF   | 2025-08      | 2025-05,2025-06,2025-07 |               1 | oco_first_touch_clean__all__k3 | oco_first_touch_clean__all__k3|1000|6 |        1000 |         6 | oco_first_touch_clean | all;barrier=3.0 |              3 |           0        |          0        |          763 |                    3 |                251.333 |                 6.06936 |                  5.99777 |                            5.38528 |                            5.32165 |                       3 |          0.988204 | True        |
| USDCHF   | 2025-08      | 2025-05,2025-06,2025-07 |               2 | oco_first_touch_clean__all__k3 | oco_first_touch_clean__all__k3|1000|5 |        1000 |         5 | oco_first_touch_clean | all;barrier=3.0 |              3 |           0.721292 |          0.270045 |          789 |                    3 |                260     |                 4.57615 |                  4.52395 |                            3.96463 |                            4.01399 |                       3 |          0.988593 | True        |
| USDCHF   | 2025-09      | 2025-06,2025-07,2025-08 |               1 | oco_first_touch_clean__all__k3 | oco_first_touch_clean__all__k3|1000|5 |        1000 |         5 | oco_first_touch_clean | all;barrier=3.0 |              3 |           0        |          0        |          650 |                    3 |                214.333 |                 4.32566 |                  4.27908 |                            3.67517 |                            3.81737 |                       3 |          0.989231 | True        |
| USDCHF   | 2026-04      | 2026-01,2026-02,2026-03 |               1 | oco_first_touch_clean__all__k3 | oco_first_touch_clean__all__k3|1000|6 |        1000 |         6 | oco_first_touch_clean | all;barrier=3.0 |              3 |           0        |          0        |          719 |                    3 |                237.667 |                 6.63689 |                  6.5815  |                            5.91299 |                            5.86236 |                       3 |          0.991655 | True        |
