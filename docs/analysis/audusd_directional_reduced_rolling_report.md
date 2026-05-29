# AUDUSD OCO Reduced-Core Rolling Selection

## Setup
- family_keep: `directional`
- barrier_keep: `[]`
- horizon_keep: `[5, 6]`
- locked_quantile: `0.9`
- selection_mode: `auto`
- execution_mode: `gross`
- state_train_months: `2`
- min_train_months: `1`
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
| AUDUSD   |               0.9 | auto             | gross            |                    2 |             16 |               3 |          202 |                 202 |          0.019802 |                 -0.557089 |                     -1.27146 |           0.019802 |                  -0.557089 |                      -1.27146 |                 1 |                        1 |          67.3333 |                 67.3333 |                   1 |               808 |                      200 |                     500 | True                              |              0.45 |                  0.35 |            0.25 |                       0 |

## Reduced State Universe
| symbol   |   bar_ticks |   horizon | state_id                          | family      |   barrier_pips | regime_desc      |
|:---------|------------:|----------:|:----------------------------------|:------------|---------------:|:-----------------|
| AUDUSD   |         100 |         6 | directional__asia__h6             | directional |              0 | asia             |
| AUDUSD   |        1000 |         6 | directional__high_vol_cluster__h6 | directional |              0 | high_vol_cluster |
| AUDUSD   |        1000 |         6 | directional__ny_overlap__h6       | directional |              0 | ny_overlap       |
| AUDUSD   |        2000 |         6 | directional__high_vol_cluster__h6 | directional |              0 | high_vol_cluster |

## Monthly Portfolio
| symbol   | test_month   | train_months    |   states_selected |   rows |   signal_rows |   fill_rate |   mean_gross_pips |   mean_signal_pips |   median_gross_pips |   pos_rate |   state_churn_rate |   top_state_share |   state_hhi |   stability_pass | status         |
|:---------|:-------------|:----------------|------------------:|-------:|--------------:|------------:|------------------:|-------------------:|--------------------:|-----------:|-------------------:|------------------:|------------:|-----------------:|:---------------|
| AUDUSD   | 2025-01      |                 |                 0 |      0 |             0 |         nan |       nan         |        nan         |              nan    | nan        |                nan |               nan |         nan |              nan | warmup_skip    |
| AUDUSD   | 2025-02      | 2025-01         |                 0 |      0 |             0 |         nan |       nan         |        nan         |              nan    | nan        |                nan |               nan |         nan |              nan | no_gate_states |
| AUDUSD   | 2025-03      | 2025-01,2025-02 |                 0 |      0 |             0 |         nan |       nan         |        nan         |              nan    | nan        |                nan |               nan |         nan |              nan | no_gate_states |
| AUDUSD   | 2025-04      | 2025-02,2025-03 |                 1 |    150 |           150 |           1 |         0.265333  |          0.265333  |                0.15 |   0.513333 |                  0 |                 1 |           1 |                0 | ok             |
| AUDUSD   | 2025-05      | 2025-03,2025-04 |                 1 |      0 |             0 |         nan |       nan         |        nan         |              nan    | nan        |                  1 |               nan |         nan |                0 | no_test_rows   |
| AUDUSD   | 2025-06      | 2025-04,2025-05 |                 0 |      0 |             0 |         nan |       nan         |        nan         |              nan    | nan        |                nan |               nan |         nan |              nan | no_gate_states |
| AUDUSD   | 2025-07      | 2025-05,2025-06 |                 0 |      0 |             0 |         nan |       nan         |        nan         |              nan    | nan        |                nan |               nan |         nan |              nan | no_gate_states |
| AUDUSD   | 2025-08      | 2025-06,2025-07 |                 0 |      0 |             0 |         nan |       nan         |        nan         |              nan    | nan        |                nan |               nan |         nan |              nan | no_gate_states |
| AUDUSD   | 2025-09      | 2025-07,2025-08 |                 1 |     34 |            34 |           1 |        -0.0588235 |         -0.0588235 |               -1.5  |   0.441176 |                  1 |                 1 |           1 |                0 | ok             |
| AUDUSD   | 2025-10      | 2025-08,2025-09 |                 0 |      0 |             0 |         nan |       nan         |        nan         |              nan    | nan        |                nan |               nan |         nan |              nan | no_gate_states |
| AUDUSD   | 2025-11      | 2025-09,2025-10 |                 1 |     18 |            18 |           1 |        -1.87778   |         -1.87778   |               -0.55 |   0.388889 |                  1 |                 1 |           1 |                0 | ok             |
| AUDUSD   | 2025-12      | 2025-10,2025-11 |                 0 |      0 |             0 |         nan |       nan         |        nan         |              nan    | nan        |                nan |               nan |         nan |              nan | no_gate_states |
| AUDUSD   | 2026-01      | 2025-11,2025-12 |                 0 |      0 |             0 |         nan |       nan         |        nan         |              nan    | nan        |                nan |               nan |         nan |              nan | no_gate_states |
| AUDUSD   | 2026-02      | 2025-12,2026-01 |                 0 |      0 |             0 |         nan |       nan         |        nan         |              nan    | nan        |                nan |               nan |         nan |              nan | no_gate_states |
| AUDUSD   | 2026-03      | 2026-01,2026-02 |                 0 |      0 |             0 |         nan |       nan         |        nan         |              nan    | nan        |                nan |               nan |         nan |              nan | no_gate_states |
| AUDUSD   | 2026-04      | 2026-02,2026-03 |                 0 |      0 |             0 |         nan |       nan         |        nan         |              nan    | nan        |                nan |               nan |         nan |              nan | no_gate_states |

## State Stability
| symbol   | test_month   |   states_selected |   state_churn_rate |   top_state_share |   state_hhi |   stability_pass | status         |
|:---------|:-------------|------------------:|-------------------:|------------------:|------------:|-----------------:|:---------------|
| AUDUSD   | 2025-01      |                 0 |                nan |               nan |         nan |              nan | warmup_skip    |
| AUDUSD   | 2025-02      |                 0 |                nan |               nan |         nan |              nan | no_gate_states |
| AUDUSD   | 2025-03      |                 0 |                nan |               nan |         nan |              nan | no_gate_states |
| AUDUSD   | 2025-04      |                 1 |                  0 |                 1 |           1 |                0 | ok             |
| AUDUSD   | 2025-05      |                 1 |                  1 |               nan |         nan |                0 | no_test_rows   |
| AUDUSD   | 2025-06      |                 0 |                nan |               nan |         nan |              nan | no_gate_states |
| AUDUSD   | 2025-07      |                 0 |                nan |               nan |         nan |              nan | no_gate_states |
| AUDUSD   | 2025-08      |                 0 |                nan |               nan |         nan |              nan | no_gate_states |
| AUDUSD   | 2025-09      |                 1 |                  1 |                 1 |           1 |                0 | ok             |
| AUDUSD   | 2025-10      |                 0 |                nan |               nan |         nan |              nan | no_gate_states |
| AUDUSD   | 2025-11      |                 1 |                  1 |                 1 |           1 |                0 | ok             |
| AUDUSD   | 2025-12      |                 0 |                nan |               nan |         nan |              nan | no_gate_states |
| AUDUSD   | 2026-01      |                 0 |                nan |               nan |         nan |              nan | no_gate_states |
| AUDUSD   | 2026-02      |                 0 |                nan |               nan |         nan |              nan | no_gate_states |
| AUDUSD   | 2026-03      |                 0 |                nan |               nan |         nan |              nan | no_gate_states |
| AUDUSD   | 2026-04      |                 0 |                nan |               nan |         nan |              nan | no_gate_states |

## State Schedule (Top Rows)
| symbol   | test_month   | train_months    |   selected_rank | state_id                          | state_key                                |   bar_ticks |   horizon | family      | regime_desc      |   barrier_pips |   overlap_corr_max |   overlap_div_max |   train_rows |   train_months_count |   train_avg_month_rows |   train_mean_gross_pips |   train_mean_signal_pips |   train_lb95_trade_mean_gross_pips |   train_lb95_month_mean_gross_pips |   train_positive_months |   train_fill_rate | gate_pass   |
|:---------|:-------------|:----------------|----------------:|:----------------------------------|:-----------------------------------------|------------:|----------:|:------------|:-----------------|---------------:|-------------------:|------------------:|-------------:|---------------------:|-----------------------:|------------------------:|-------------------------:|-----------------------------------:|-----------------------------------:|------------------------:|------------------:|:------------|
| AUDUSD   | 2025-04      | 2025-02,2025-03 |               1 | directional__asia__h6             | directional__asia__h6|100|6              |         100 |         6 | directional | asia             |              0 |                  0 |                 0 |           29 |                    1 |                   29   |                 1.27241 |                  1.27241 |                          0.244138  |                            1.27241 |                       1 |                 1 | True        |
| AUDUSD   | 2025-05      | 2025-03,2025-04 |               1 | directional__high_vol_cluster__h6 | directional__high_vol_cluster__h6|1000|6 |        1000 |         6 | directional | high_vol_cluster |              0 |                  0 |                 0 |           48 |                    1 |                   48   |                 2.43125 |                  2.43125 |                          0.137396  |                            2.43125 |                       1 |                 1 | True        |
| AUDUSD   | 2025-09      | 2025-07,2025-08 |               1 | directional__ny_overlap__h6       | directional__ny_overlap__h6|1000|6       |        1000 |         6 | directional | ny_overlap       |              0 |                  0 |                 0 |           26 |                    1 |                   26   |                 3.3     |                  3.3     |                          1.22981   |                            3.3     |                       1 |                 1 | True        |
| AUDUSD   | 2025-11      | 2025-09,2025-10 |               1 | directional__high_vol_cluster__h6 | directional__high_vol_cluster__h6|2000|6 |        2000 |         6 | directional | high_vol_cluster |              0 |                  0 |                 0 |          107 |                    2 |                   53.5 |                 2.14206 |                  2.14206 |                          0.0993458 |                            1.81207 |                       2 |                 1 | True        |
