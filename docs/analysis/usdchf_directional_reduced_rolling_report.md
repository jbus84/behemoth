# USDCHF OCO Reduced-Core Rolling Selection

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
| USDCHF   |               0.9 | auto             | gross            |                    2 |             16 |               1 |           17 |                  17 |         -0.588235 |                 -0.588235 |                    -0.588235 |          -0.588235 |                  -0.588235 |                     -0.588235 |                 0 |                        0 |               17 |                      17 |                   1 |               204 |                      200 |                     500 | False                             |              0.45 |                  0.35 |            0.25 |                       0 |

## Reduced State Universe
| symbol   |   bar_ticks |   horizon | state_id                       | family      |   barrier_pips | regime_desc   |
|:---------|------------:|----------:|:-------------------------------|:------------|---------------:|:--------------|
| USDCHF   |         100 |         6 | directional__negative_flow__h6 | directional |              0 | negative_flow |
| USDCHF   |        1000 |         6 | directional__asia__h6          | directional |              0 | asia          |

## Monthly Portfolio
| symbol   | test_month   | train_months    |   states_selected |   rows |   signal_rows |   fill_rate |   mean_gross_pips |   mean_signal_pips |   median_gross_pips |   pos_rate |   state_churn_rate |   top_state_share |   state_hhi |   stability_pass | status         |
|:---------|:-------------|:----------------|------------------:|-------:|--------------:|------------:|------------------:|-------------------:|--------------------:|-----------:|-------------------:|------------------:|------------:|-----------------:|:---------------|
| USDCHF   | 2025-01      |                 |                 0 |      0 |             0 |         nan |        nan        |         nan        |               nan   | nan        |              nan   |               nan |         nan |              nan | warmup_skip    |
| USDCHF   | 2025-02      | 2025-01         |                 0 |      0 |             0 |         nan |        nan        |         nan        |               nan   | nan        |              nan   |               nan |         nan |              nan | no_gate_states |
| USDCHF   | 2025-03      | 2025-01,2025-02 |                 0 |      0 |             0 |         nan |        nan        |         nan        |               nan   | nan        |              nan   |               nan |         nan |              nan | no_gate_states |
| USDCHF   | 2025-04      | 2025-02,2025-03 |                 0 |      0 |             0 |         nan |        nan        |         nan        |               nan   | nan        |              nan   |               nan |         nan |              nan | no_gate_states |
| USDCHF   | 2025-05      | 2025-03,2025-04 |                 0 |      0 |             0 |         nan |        nan        |         nan        |               nan   | nan        |              nan   |               nan |         nan |              nan | no_gate_states |
| USDCHF   | 2025-06      | 2025-04,2025-05 |                 1 |      0 |             0 |         nan |        nan        |         nan        |               nan   | nan        |                0   |               nan |         nan |                1 | no_test_rows   |
| USDCHF   | 2025-07      | 2025-05,2025-06 |                 2 |     17 |            17 |           1 |         -0.588235 |          -0.588235 |                -0.7 |   0.411765 |                0.5 |                 1 |           1 |                0 | ok             |
| USDCHF   | 2025-08      | 2025-06,2025-07 |                 0 |      0 |             0 |         nan |        nan        |         nan        |               nan   | nan        |              nan   |               nan |         nan |              nan | no_gate_states |
| USDCHF   | 2025-09      | 2025-07,2025-08 |                 0 |      0 |             0 |         nan |        nan        |         nan        |               nan   | nan        |              nan   |               nan |         nan |              nan | no_gate_states |
| USDCHF   | 2025-10      | 2025-08,2025-09 |                 0 |      0 |             0 |         nan |        nan        |         nan        |               nan   | nan        |              nan   |               nan |         nan |              nan | no_gate_states |
| USDCHF   | 2025-11      | 2025-09,2025-10 |                 0 |      0 |             0 |         nan |        nan        |         nan        |               nan   | nan        |              nan   |               nan |         nan |              nan | no_gate_states |
| USDCHF   | 2025-12      | 2025-10,2025-11 |                 0 |      0 |             0 |         nan |        nan        |         nan        |               nan   | nan        |              nan   |               nan |         nan |              nan | no_gate_states |
| USDCHF   | 2026-01      | 2025-11,2025-12 |                 0 |      0 |             0 |         nan |        nan        |         nan        |               nan   | nan        |              nan   |               nan |         nan |              nan | no_gate_states |
| USDCHF   | 2026-02      | 2025-12,2026-01 |                 0 |      0 |             0 |         nan |        nan        |         nan        |               nan   | nan        |              nan   |               nan |         nan |              nan | no_gate_states |
| USDCHF   | 2026-03      | 2026-01,2026-02 |                 0 |      0 |             0 |         nan |        nan        |         nan        |               nan   | nan        |              nan   |               nan |         nan |              nan | no_gate_states |
| USDCHF   | 2026-04      | 2026-02,2026-03 |                 0 |      0 |             0 |         nan |        nan        |         nan        |               nan   | nan        |              nan   |               nan |         nan |              nan | no_gate_states |

## State Stability
| symbol   | test_month   |   states_selected |   state_churn_rate |   top_state_share |   state_hhi |   stability_pass | status         |
|:---------|:-------------|------------------:|-------------------:|------------------:|------------:|-----------------:|:---------------|
| USDCHF   | 2025-01      |                 0 |              nan   |               nan |         nan |              nan | warmup_skip    |
| USDCHF   | 2025-02      |                 0 |              nan   |               nan |         nan |              nan | no_gate_states |
| USDCHF   | 2025-03      |                 0 |              nan   |               nan |         nan |              nan | no_gate_states |
| USDCHF   | 2025-04      |                 0 |              nan   |               nan |         nan |              nan | no_gate_states |
| USDCHF   | 2025-05      |                 0 |              nan   |               nan |         nan |              nan | no_gate_states |
| USDCHF   | 2025-06      |                 1 |                0   |               nan |         nan |                1 | no_test_rows   |
| USDCHF   | 2025-07      |                 2 |                0.5 |                 1 |           1 |                0 | ok             |
| USDCHF   | 2025-08      |                 0 |              nan   |               nan |         nan |              nan | no_gate_states |
| USDCHF   | 2025-09      |                 0 |              nan   |               nan |         nan |              nan | no_gate_states |
| USDCHF   | 2025-10      |                 0 |              nan   |               nan |         nan |              nan | no_gate_states |
| USDCHF   | 2025-11      |                 0 |              nan   |               nan |         nan |              nan | no_gate_states |
| USDCHF   | 2025-12      |                 0 |              nan   |               nan |         nan |              nan | no_gate_states |
| USDCHF   | 2026-01      |                 0 |              nan   |               nan |         nan |              nan | no_gate_states |
| USDCHF   | 2026-02      |                 0 |              nan   |               nan |         nan |              nan | no_gate_states |
| USDCHF   | 2026-03      |                 0 |              nan   |               nan |         nan |              nan | no_gate_states |
| USDCHF   | 2026-04      |                 0 |              nan   |               nan |         nan |              nan | no_gate_states |

## State Schedule (Top Rows)
| symbol   | test_month   | train_months    |   selected_rank | state_id                       | state_key                            |   bar_ticks |   horizon | family      | regime_desc   |   barrier_pips |   overlap_corr_max |   overlap_div_max |   train_rows |   train_months_count |   train_avg_month_rows |   train_mean_gross_pips |   train_mean_signal_pips |   train_lb95_trade_mean_gross_pips |   train_lb95_month_mean_gross_pips |   train_positive_months |   train_fill_rate | gate_pass   |
|:---------|:-------------|:----------------|----------------:|:-------------------------------|:-------------------------------------|------------:|----------:|:------------|:--------------|---------------:|-------------------:|------------------:|-------------:|---------------------:|-----------------------:|------------------------:|-------------------------:|-----------------------------------:|-----------------------------------:|------------------------:|------------------:|:------------|
| USDCHF   | 2025-06      | 2025-04,2025-05 |               1 | directional__asia__h6          | directional__asia__h6|1000|6         |        1000 |         6 | directional | asia          |              0 |                  0 |                 0 |           32 |                    1 |                   32   |                 3.22188 |                  3.22188 |                           0.429375 |                           3.22188  |                       1 |                 1 | True        |
| USDCHF   | 2025-07      | 2025-05,2025-06 |               1 | directional__asia__h6          | directional__asia__h6|1000|6         |        1000 |         6 | directional | asia          |              0 |                  0 |                 0 |           32 |                    1 |                   32   |                 3.22188 |                  3.22188 |                           0.214375 |                           3.22188  |                       1 |                 1 | True        |
| USDCHF   | 2025-07      | 2025-05,2025-06 |               2 | directional__negative_flow__h6 | directional__negative_flow__h6|100|6 |         100 |         6 | directional | negative_flow |              0 |                  0 |                 0 |           67 |                    2 |                   33.5 |                 1.94179 |                  1.94179 |                           0.61791  |                           0.687097 |                       2 |                 1 | True        |
