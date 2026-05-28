# AUDUSD Tick Opportunity Monthly WFO (3M->1M)

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
| cost_est_pips             |          15.5153  |
| signed_flow_24            |           8.91849 |
| tick_rate_z               |           8.82883 |
| hl_pos_frac_mean_24       |           8.30316 |
| spread_z                  |           8.13136 |
| quote_revision_rate_z     |           7.01875 |
| range_pips                |           6.96475 |
| directional_persistence_8 |           5.5926  |
| hour_utc                  |           5.58679 |
| vol_cluster_score         |           4.75752 |
| hl_first_mean_24          |           3.94256 |
| vel_abs_cost_units_h1     |           3.22348 |
| vel_cost_units_h1         |           3.17175 |
| ret_abs_z                 |           3.15024 |
| ret_z                     |           3.06233 |
| ret1_pips                 |           2.5604  |
| hl_first                  |           1.27167 |
| bar_ticks                 |           0       |
| horizon                   |           0       |
| tick_burst_score          |           0       |

## Monthly Metrics
| library     | test_month   | train_start   | train_end   | test_start   | test_end   |   train_rows |   test_rows |   train_candidates |   test_candidates |   base_pos_rate |      auc |    brier |
|:------------|:-------------|:--------------|:------------|:-------------|:-----------|-------------:|------------:|-------------------:|------------------:|----------------:|---------:|---------:|
| directional | 2025-01      | 2024-10-01    | 2025-01-01  | 2025-01-01   | 2025-02-01 |         2079 |         791 |                  6 |                 6 |        0.420986 | 0.532931 | 0.309536 |
| directional | 2025-03      | 2024-12-01    | 2025-03-01  | 2025-03-01   | 2025-04-01 |         1051 |         330 |                  3 |                 3 |        0.39697  | 0.461736 | 0.349071 |

## Threshold Outcomes
| library     | test_month   |   quantile | threshold_mode   |   threshold_median |   threshold_min |   threshold_max |   coverage |   mean_gross_pips |   median_gross_pips |   pos_rate |   selected_rows |
|:------------|:-------------|-----------:|:-----------------|-------------------:|----------------:|----------------:|-----------:|------------------:|--------------------:|-----------:|----------------:|
| directional | 2025-01      |       0.5  | rolling_days     |          0.304042  |       0.219967  |       0.493392  | 0.529709   |          -2.59045 |               -2.1  |   0.463007 |             419 |
| directional | 2025-01      |       0.6  | rolling_days     |          0.453473  |       0.355472  |       0.956032  | 0.412137   |          -3.5135  |               -4.4  |   0.447853 |             326 |
| directional | 2025-01      |       0.7  | rolling_days     |          0.577119  |       0.473997  |       0.962958  | 0.351454   |          -5.51978 |               -6.7  |   0.417266 |             278 |
| directional | 2025-01      |       0.8  | rolling_days     |          0.751331  |       0.594767  |       0.972538  | 0.198483   |          -5.71656 |               -6.9  |   0.452229 |             157 |
| directional | 2025-01      |       0.9  | rolling_days     |          0.96188   |       0.720911  |       0.98592   | 0.130215   |         -11.7223  |              -10.6  |   0.339806 |             103 |
| directional | 2025-01      |       0.95 | rolling_days     |          0.981035  |       0.755576  |       0.991297  | 0.117573   |         -10.9871  |              -10.6  |   0.333333 |              93 |
| directional | 2025-03      |       0.5  | rolling_days     |          0.0682245 |       0.0682245 |       0.0682245 | 0.9        |          -1.5     |               -1.4  |   0.390572 |             297 |
| directional | 2025-03      |       0.6  | rolling_days     |          0.940228  |       0.940228  |       0.940228  | 0.0181818  |          17.95    |               17.95 |   0.5      |               6 |
| directional | 2025-03      |       0.7  | rolling_days     |          0.959876  |       0.959876  |       0.959876  | 0.0181818  |          17.95    |               17.95 |   0.5      |               6 |
| directional | 2025-03      |       0.8  | rolling_days     |          0.970936  |       0.970936  |       0.970936  | 0.00909091 |          37.2     |               37.2  |   1        |               3 |
