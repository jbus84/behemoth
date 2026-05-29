# USDCAD Tick Opportunity Monthly WFO (3M->1M)

## Setup
- library: `directional`
- families: `pullback`
- train_years_for_state_fit: `2022,2023,2024`
- eval_window: `2025-01` .. `2026-03`
- min_candidate_train_count: `2000`
- max_candidates_per_library: `300`
- rolling_train_months: `3`
- oco_include_no_touch: `False`
- threshold_mode: `rolling_days`
- rolling_threshold_days: `20`
- rolling_threshold_min_history: `300`
- execution_quantile: `0.9`
- oco_hold_mode: `from_touch`

## Feature Importance
| feature                   |   mean_importance |
|:--------------------------|------------------:|
| cost_est_pips             |         15.8881   |
| tick_rate_z               |          9.42148  |
| spread_z                  |          8.94781  |
| hl_pos_frac_mean_24       |          8.59387  |
| quote_revision_rate_z     |          7.27601  |
| range_pips                |          7.00332  |
| signed_flow_24            |          6.39476  |
| directional_persistence_8 |          6.21157  |
| hl_first_mean_24          |          4.40189  |
| vel_abs_cost_units_h1     |          4.39531  |
| vol_cluster_score         |          4.10705  |
| hour_utc                  |          3.76195  |
| ret_abs_z                 |          3.54194  |
| vel_cost_units_h1         |          3.33106  |
| ret_z                     |          3.29176  |
| ret1_pips                 |          2.74269  |
| hl_first                  |          0.689358 |
| bar_ticks                 |          0        |
| horizon                   |          0        |
| tick_burst_score          |          0        |

## Monthly Metrics
| library     | test_month   | train_start   | train_end   | test_start   | test_end   |   train_rows |   test_rows |   train_candidates |   test_candidates |   base_pos_rate |      auc |    brier |
|:------------|:-------------|:--------------|:------------|:-------------|:-----------|-------------:|------------:|-------------------:|------------------:|----------------:|---------:|---------:|
| directional | 2025-01      | 2024-10-01    | 2025-01-01  | 2025-01-01   | 2025-02-01 |         1319 |         669 |                  3 |                 3 |        0.585949 | 0.545918 | 0.324877 |
| directional | 2025-02      | 2024-11-01    | 2025-02-01  | 2025-02-01   | 2025-03-01 |         1515 |         545 |                  3 |                 3 |        0.407339 | 0.467297 | 0.341155 |

## Threshold Outcomes
| library     | test_month   |   quantile | threshold_mode   |   threshold_median |   threshold_min |   threshold_max |   coverage |   mean_gross_pips |   median_gross_pips |   pos_rate |   selected_rows |
|:------------|:-------------|-----------:|:-----------------|-------------------:|----------------:|----------------:|-----------:|------------------:|--------------------:|-----------:|----------------:|
| directional | 2025-01      |       0.5  | rolling_days     |           0.907148 |        0.830948 |        0.939732 |  0.529148  |          1.00028  |                4.5  |   0.615819 |             354 |
| directional | 2025-01      |       0.6  | rolling_days     |           0.938431 |        0.889154 |        0.966345 |  0.41704   |          0.976703 |                4.9  |   0.620072 |             279 |
| directional | 2025-01      |       0.7  | rolling_days     |           0.959597 |        0.936528 |        0.97574  |  0.300448  |          0.339303 |                5.1  |   0.626866 |             201 |
| directional | 2025-01      |       0.8  | rolling_days     |           0.973158 |        0.959254 |        0.983593 |  0.219731  |          1.38912  |                5.4  |   0.632653 |             147 |
| directional | 2025-01      |       0.9  | rolling_days     |           0.983536 |        0.979341 |        0.985916 |  0.103139  |          2.04638  |                6.3  |   0.565217 |              69 |
| directional | 2025-01      |       0.95 | rolling_days     |           0.988875 |        0.984896 |        0.991038 |  0.0493274 |          3.97879  |                6.3  |   0.545455 |              33 |
| directional | 2025-02      |       0.5  | rolling_days     |           0.639368 |        0.515474 |        0.903456 |  0.398165  |         -1.87097  |               -4.7  |   0.428571 |             217 |
| directional | 2025-02      |       0.6  | rolling_days     |           0.724884 |        0.607468 |        0.929285 |  0.227523  |         -0.239516 |               -3.6  |   0.459677 |             124 |
| directional | 2025-02      |       0.7  | rolling_days     |           0.856552 |        0.691913 |        0.942826 |  0.165138  |         -1.46     |               -4.15 |   0.4      |              90 |
| directional | 2025-02      |       0.8  | rolling_days     |           0.918999 |        0.770586 |        0.955539 |  0.0880734 |         -3.5625   |               -7.3  |   0.4375   |              48 |
| directional | 2025-02      |       0.9  | rolling_days     |           0.943235 |        0.892044 |        0.96857  |  0.0330275 |          4.46667  |               11.15 |   0.666667 |              18 |
| directional | 2025-02      |       0.95 | rolling_days     |           0.956949 |        0.931189 |        0.97658  |  0.0165138 |          1.73333  |                6.9  |   0.666667 |               9 |
