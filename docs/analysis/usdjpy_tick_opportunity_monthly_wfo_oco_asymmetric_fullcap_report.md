# USDJPY Tick Opportunity Monthly WFO (3M->1M)

## Setup
- library: `oco_asymmetric`
- families: `oco_asymmetric`
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
| spread_z                  |           9.62365 |
| cost_est_pips             |           9.31692 |
| quote_revision_rate_z     |           9.23257 |
| hl_pos_frac_mean_24       |           9.14183 |
| range_pips                |           9.08726 |
| tick_rate_z               |           8.50844 |
| signed_flow_24            |           5.51973 |
| ret_abs_z                 |           5.40095 |
| hour_utc                  |           4.9865  |
| vol_cluster_score         |           4.8493  |
| directional_persistence_8 |           4.64441 |
| ret1_pips                 |           4.25408 |
| ret_z                     |           3.89878 |
| vel_abs_cost_units_h1     |           3.66263 |
| hl_first_mean_24          |           3.29475 |
| vel_cost_units_h1         |           3.19656 |
| hl_first                  |           1.38163 |
| bar_ticks                 |           0       |
| horizon                   |           0       |
| tick_burst_score          |           0       |

## Monthly Metrics
| library        | test_month   | train_start   | train_end   | test_start   | test_end   |   train_rows |   test_rows |   train_candidates |   test_candidates |   base_pos_rate |      auc |    brier |
|:---------------|:-------------|:--------------|:------------|:-------------|:-----------|-------------:|------------:|-------------------:|------------------:|----------------:|---------:|---------:|
| oco_asymmetric | 2025-01      | 2024-10-01    | 2025-01-01  | 2025-01-01   | 2025-02-01 |         1354 |         390 |                  1 |                 1 |        0.489744 | 0.478623 | 0.286037 |
| oco_asymmetric | 2025-03      | 2024-12-01    | 2025-03-01  | 2025-03-01   | 2025-04-01 |         1111 |         425 |                  1 |                 1 |        0.489412 | 0.492467 | 0.273562 |

## Threshold Outcomes
| library        | test_month   |   quantile | threshold_mode   |   threshold_median |   threshold_min |   threshold_max |   coverage |   mean_gross_pips |   median_gross_pips |   pos_rate |   selected_rows |
|:---------------|:-------------|-----------:|:-----------------|-------------------:|----------------:|----------------:|-----------:|------------------:|--------------------:|-----------:|----------------:|
| oco_asymmetric | 2025-01      |       0.5  | rolling_days     |           0.507006 |        0.507006 |        0.507006 |  0.284615  |        -4.76036   |               -0.4  |   0.486486 |             111 |
| oco_asymmetric | 2025-01      |       0.6  | rolling_days     |           0.642086 |        0.642086 |        0.642086 |  0.117949  |        -5.19783   |               -0.25 |   0.478261 |              46 |
| oco_asymmetric | 2025-01      |       0.7  | rolling_days     |           0.703395 |        0.703395 |        0.703395 |  0.0538462 |        -7.9619    |               -5.6  |   0.428571 |              21 |
| oco_asymmetric | 2025-01      |       0.8  | rolling_days     |           0.756364 |        0.756364 |        0.756364 |  0.0333333 |        -2.39231   |               -0.4  |   0.461538 |              13 |
| oco_asymmetric | 2025-01      |       0.9  | rolling_days     |           0.815409 |        0.815409 |        0.815409 |  0.0128205 |        13.04      |                7.2  |   0.8      |               5 |
| oco_asymmetric | 2025-01      |       0.95 | rolling_days     |           0.852406 |        0.852406 |        0.852406 |  0.0025641 |         7.2       |                7.2  |   1        |               1 |
| oco_asymmetric | 2025-03      |       0.5  | rolling_days     |           0.477017 |        0.477017 |        0.552597 |  0.583529  |        -0.0870968 |               -1.95 |   0.475806 |             248 |
| oco_asymmetric | 2025-03      |       0.6  | rolling_days     |           0.665821 |        0.569921 |        0.665821 |  0.270588  |         0.82      |               -0.1  |   0.495652 |             115 |
| oco_asymmetric | 2025-03      |       0.7  | rolling_days     |           0.74006  |        0.614078 |        0.74006  |  0.141176  |         2.15333   |                0    |   0.5      |              60 |
| oco_asymmetric | 2025-03      |       0.8  | rolling_days     |           0.78556  |        0.663307 |        0.78556  |  0.0729412 |        -1.24516   |               -0.1  |   0.483871 |              31 |
| oco_asymmetric | 2025-03      |       0.9  | rolling_days     |           0.826714 |        0.72237  |        0.826714 |  0.0282353 |        -2.675     |               -0.8  |   0.416667 |              12 |
| oco_asymmetric | 2025-03      |       0.95 | rolling_days     |           0.866078 |        0.774674 |        0.866078 |  0.0117647 |         1.14      |               -0.1  |   0.4      |               5 |
