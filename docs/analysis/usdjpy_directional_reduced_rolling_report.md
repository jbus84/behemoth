# USDJPY OCO Reduced-Core Rolling Selection

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
| USDJPY   |               0.9 | auto             | gross            |                    2 |             16 |               3 |          114 |                 114 |        -0.0631579 |                 -0.289641 |                     -1.07952 |         -0.0631579 |                  -0.289641 |                      -1.07952 |                 1 |                        1 |               38 |                      38 |                   1 |               456 |                      200 |                     500 | False                             |              0.45 |                  0.35 |            0.25 |                       0 |

## Reduced State Universe
| symbol   |   bar_ticks |   horizon | state_id                                         | family      |   barrier_pips | regime_desc                     |
|:---------|------------:|----------:|:-------------------------------------------------|:------------|---------------:|:--------------------------------|
| USDJPY   |         100 |         6 | directional__low_cost_q30__h6                    | directional |              0 | low_cost_q30                    |
| USDJPY   |         100 |         6 | directional__low_cost_q30_and_high_range_q70__h6 | directional |              0 | low_cost_q30_and_high_range_q70 |
| USDJPY   |         100 |         6 | directional__negative_flow__h6                   | directional |              0 | negative_flow                   |
| USDJPY   |         100 |         6 | directional__persistent_flow__h6                 | directional |              0 | persistent_flow                 |

## Monthly Portfolio
| symbol   | test_month   | train_months    |   states_selected |   rows |   signal_rows |   fill_rate |   mean_gross_pips |   mean_signal_pips |   median_gross_pips |   pos_rate |   state_churn_rate |   top_state_share |   state_hhi |   stability_pass | status         |
|:---------|:-------------|:----------------|------------------:|-------:|--------------:|------------:|------------------:|-------------------:|--------------------:|-----------:|-------------------:|------------------:|------------:|-----------------:|:---------------|
| USDJPY   | 2025-01      |                 |                 0 |      0 |             0 |         nan |       nan         |        nan         |               nan   | nan        |         nan        |               nan |         nan |              nan | warmup_skip    |
| USDJPY   | 2025-02      | 2025-01         |                 1 |     62 |            62 |           1 |         0.772581  |          0.772581  |                 0.9 |   0.532258 |           0        |                 1 |           1 |                0 | ok             |
| USDJPY   | 2025-03      | 2025-01,2025-02 |                 3 |     34 |            34 |           1 |        -1.59706   |         -1.59706   |                -1.8 |   0.382353 |           0.666667 |                 1 |           1 |                0 | ok             |
| USDJPY   | 2025-04      | 2025-02,2025-03 |                 2 |     18 |            18 |           1 |        -0.0444444 |         -0.0444444 |                 0.9 |   0.5      |           0.75     |                 1 |           1 |                0 | ok             |
| USDJPY   | 2025-05      | 2025-03,2025-04 |                 0 |      0 |             0 |         nan |       nan         |        nan         |               nan   | nan        |         nan        |               nan |         nan |              nan | no_gate_states |
| USDJPY   | 2025-06      | 2025-04,2025-05 |                 0 |      0 |             0 |         nan |       nan         |        nan         |               nan   | nan        |         nan        |               nan |         nan |              nan | no_gate_states |
| USDJPY   | 2025-07      | 2025-05,2025-06 |                 0 |      0 |             0 |         nan |       nan         |        nan         |               nan   | nan        |         nan        |               nan |         nan |              nan | no_gate_states |
| USDJPY   | 2025-08      | 2025-06,2025-07 |                 0 |      0 |             0 |         nan |       nan         |        nan         |               nan   | nan        |         nan        |               nan |         nan |              nan | no_gate_states |
| USDJPY   | 2025-09      | 2025-07,2025-08 |                 0 |      0 |             0 |         nan |       nan         |        nan         |               nan   | nan        |         nan        |               nan |         nan |              nan | no_gate_states |
| USDJPY   | 2025-10      | 2025-08,2025-09 |                 0 |      0 |             0 |         nan |       nan         |        nan         |               nan   | nan        |         nan        |               nan |         nan |              nan | no_gate_states |
| USDJPY   | 2025-11      | 2025-09,2025-10 |                 0 |      0 |             0 |         nan |       nan         |        nan         |               nan   | nan        |         nan        |               nan |         nan |              nan | no_gate_states |
| USDJPY   | 2025-12      | 2025-10,2025-11 |                 0 |      0 |             0 |         nan |       nan         |        nan         |               nan   | nan        |         nan        |               nan |         nan |              nan | no_gate_states |
| USDJPY   | 2026-01      | 2025-11,2025-12 |                 0 |      0 |             0 |         nan |       nan         |        nan         |               nan   | nan        |         nan        |               nan |         nan |              nan | no_gate_states |
| USDJPY   | 2026-02      | 2025-12,2026-01 |                 0 |      0 |             0 |         nan |       nan         |        nan         |               nan   | nan        |         nan        |               nan |         nan |              nan | no_gate_states |
| USDJPY   | 2026-03      | 2026-01,2026-02 |                 0 |      0 |             0 |         nan |       nan         |        nan         |               nan   | nan        |         nan        |               nan |         nan |              nan | no_gate_states |
| USDJPY   | 2026-04      | 2026-02,2026-03 |                 0 |      0 |             0 |         nan |       nan         |        nan         |               nan   | nan        |         nan        |               nan |         nan |              nan | no_gate_states |

## State Stability
| symbol   | test_month   |   states_selected |   state_churn_rate |   top_state_share |   state_hhi |   stability_pass | status         |
|:---------|:-------------|------------------:|-------------------:|------------------:|------------:|-----------------:|:---------------|
| USDJPY   | 2025-01      |                 0 |         nan        |               nan |         nan |              nan | warmup_skip    |
| USDJPY   | 2025-02      |                 1 |           0        |                 1 |           1 |                0 | ok             |
| USDJPY   | 2025-03      |                 3 |           0.666667 |                 1 |           1 |                0 | ok             |
| USDJPY   | 2025-04      |                 2 |           0.75     |                 1 |           1 |                0 | ok             |
| USDJPY   | 2025-05      |                 0 |         nan        |               nan |         nan |              nan | no_gate_states |
| USDJPY   | 2025-06      |                 0 |         nan        |               nan |         nan |              nan | no_gate_states |
| USDJPY   | 2025-07      |                 0 |         nan        |               nan |         nan |              nan | no_gate_states |
| USDJPY   | 2025-08      |                 0 |         nan        |               nan |         nan |              nan | no_gate_states |
| USDJPY   | 2025-09      |                 0 |         nan        |               nan |         nan |              nan | no_gate_states |
| USDJPY   | 2025-10      |                 0 |         nan        |               nan |         nan |              nan | no_gate_states |
| USDJPY   | 2025-11      |                 0 |         nan        |               nan |         nan |              nan | no_gate_states |
| USDJPY   | 2025-12      |                 0 |         nan        |               nan |         nan |              nan | no_gate_states |
| USDJPY   | 2026-01      |                 0 |         nan        |               nan |         nan |              nan | no_gate_states |
| USDJPY   | 2026-02      |                 0 |         nan        |               nan |         nan |              nan | no_gate_states |
| USDJPY   | 2026-03      |                 0 |         nan        |               nan |         nan |              nan | no_gate_states |
| USDJPY   | 2026-04      |                 0 |         nan        |               nan |         nan |              nan | no_gate_states |

## State Schedule (Top Rows)
| symbol   | test_month   | train_months    |   selected_rank | state_id                                         | state_key                                              |   bar_ticks |   horizon | family      | regime_desc                     |   barrier_pips |   overlap_corr_max |   overlap_div_max |   train_rows |   train_months_count |   train_avg_month_rows |   train_mean_gross_pips |   train_mean_signal_pips |   train_lb95_trade_mean_gross_pips |   train_lb95_month_mean_gross_pips |   train_positive_months |   train_fill_rate | gate_pass   |
|:---------|:-------------|:----------------|----------------:|:-------------------------------------------------|:-------------------------------------------------------|------------:|----------:|:------------|:--------------------------------|---------------:|-------------------:|------------------:|-------------:|---------------------:|-----------------------:|------------------------:|-------------------------:|-----------------------------------:|-----------------------------------:|------------------------:|------------------:|:------------|
| USDJPY   | 2025-02      | 2025-01         |               1 | directional__negative_flow__h6                   | directional__negative_flow__h6|100|6                   |         100 |         6 | directional | negative_flow                   |              0 |                  0 |                 0 |           44 |                    1 |                     44 |                1.86818  |                 1.86818  |                         0.00704545 |                           1.86818  |                       1 |                 1 | True        |
| USDJPY   | 2025-03      | 2025-01,2025-02 |               1 | directional__low_cost_q30_and_high_range_q70__h6 | directional__low_cost_q30_and_high_range_q70__h6|100|6 |         100 |         6 | directional | low_cost_q30_and_high_range_q70 |              0 |                  0 |                 0 |           95 |                    1 |                     95 |                0.875789 |                 0.875789 |                         0.00615789 |                           0.875789 |                       1 |                 1 | True        |
| USDJPY   | 2025-03      | 2025-01,2025-02 |               2 | directional__negative_flow__h6                   | directional__negative_flow__h6|100|6                   |         100 |         6 | directional | negative_flow                   |              0 |                  0 |                 0 |          106 |                    2 |                     53 |                1.22736  |                 1.22736  |                         0.308396   |                           0.772581 |                       2 |                 1 | True        |
| USDJPY   | 2025-03      | 2025-01,2025-02 |               3 | directional__low_cost_q30__h6                    | directional__low_cost_q30__h6|100|6                    |         100 |         6 | directional | low_cost_q30                    |              0 |                  0 |                 0 |          132 |                    1 |                    132 |                0.731818 |                 0.731818 |                         0.0195455  |                           0.731818 |                       1 |                 1 | True        |
| USDJPY   | 2025-04      | 2025-02,2025-03 |               1 | directional__persistent_flow__h6                 | directional__persistent_flow__h6|100|6                 |         100 |         6 | directional | persistent_flow                 |              0 |                  0 |                 0 |           71 |                    1 |                     71 |                1.12394  |                 1.12394  |                         0.143451   |                           1.12394  |                       1 |                 1 | True        |
| USDJPY   | 2025-04      | 2025-02,2025-03 |               2 | directional__low_cost_q30__h6                    | directional__low_cost_q30__h6|100|6                    |         100 |         6 | directional | low_cost_q30                    |              0 |                  0 |                 0 |          132 |                    1 |                    132 |                0.731818 |                 0.731818 |                         0.00375    |                           0.731818 |                       1 |                 1 | True        |
