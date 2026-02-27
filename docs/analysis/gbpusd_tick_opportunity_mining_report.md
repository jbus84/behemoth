# Tick Opportunity Mining Report

## Setup
- symbol: `GBPUSD`
- bar_ticks_grid: `100,1000,2000`
- horizons: `1,2,3,4,5,6`
- train_years: `2022,2023,2024`
- test_year: `2025`
- min_annual_fills: `5000.0`
- inclusion_metric: `mean`

## Directional Top
|   bar_ticks |   horizon | family       | state_id                      | quality_tier   |   annualized_test_fills |   mean_gross_pips_test |   median_gross_pips_test |   gross_std_test |   hit_rate_gross_test | selection_pass   |
|------------:|----------:|:-------------|:------------------------------|:---------------|------------------------:|-----------------------:|-------------------------:|-----------------:|----------------------:|:-----------------|
|         100 |         4 | path_follow  | path_follow__all              | C              |                 99012.1 |              0.0436739 |                      0   |          4.19732 |              0.498444 | True             |
|         100 |         6 | path_follow  | path_follow__all              | C              |                 99012.1 |              0.0392275 |                      0   |          5.10467 |              0.499437 | True             |
|         100 |         5 | path_follow  | path_follow__all              | C              |                 99012.1 |              0.0387785 |                      0   |          4.68203 |              0.498951 | True             |
|         100 |         3 | path_follow  | path_follow__all              | C              |                 99012.1 |              0.0294954 |                      0   |          3.6421  |              0.497725 | True             |
|         100 |         2 | path_follow  | path_follow__all              | C              |                 99012.1 |              0.0234647 |                      0   |          2.9684  |              0.496914 | True             |
|         100 |         1 | path_follow  | path_follow__all              | C              |                 99012.1 |              0.0135339 |                      0   |          2.12004 |              0.491309 | True             |
|         100 |         4 | path_follow  | path_follow__high_abs_vel_q70 | C              |                 82419.6 |              0.0473536 |                      0   |          4.36296 |              0.497486 | True             |
|         100 |         6 | path_follow  | path_follow__high_abs_vel_q70 | C              |                 82419.6 |              0.0465999 |                      0   |          5.29099 |              0.499178 | True             |
|         100 |         5 | path_follow  | path_follow__high_abs_vel_q70 | C              |                 82419.6 |              0.0435729 |                      0   |          4.84985 |              0.498241 | True             |
|         100 |         3 | path_follow  | path_follow__high_abs_vel_q70 | C              |                 82419.6 |              0.0309513 |                      0   |          3.79398 |              0.497449 | True             |
|         100 |         2 | path_follow  | path_follow__high_abs_vel_q70 | C              |                 82419.6 |              0.023608  |                      0   |          3.09265 |              0.497327 | True             |
|         100 |         1 | path_follow  | path_follow__high_abs_vel_q70 | C              |                 82419.6 |              0.0134009 |                      0   |          2.20377 |              0.490898 | True             |
|         100 |         4 | path_follow  | path_follow__low_cost_q50     | C              |                 81369.9 |              0.0361975 |                      0   |          4.23799 |              0.497675 | True             |
|         100 |         5 | path_follow  | path_follow__low_cost_q50     | C              |                 81369.9 |              0.0356844 |                      0   |          4.71983 |              0.49902  | True             |
|         100 |         6 | path_follow  | path_follow__low_cost_q50     | C              |                 81369.9 |              0.0354822 |                      0   |          5.15559 |              0.499673 | True             |
|         100 |         3 | path_follow  | path_follow__low_cost_q50     | C              |                 81369.9 |              0.0255602 |                      0   |          3.66831 |              0.497478 | True             |
|         100 |         2 | path_follow  | path_follow__low_cost_q50     | C              |                 81369.9 |              0.0174685 |                      0   |          2.99503 |              0.496417 | True             |
|         100 |         1 | path_follow  | path_follow__low_cost_q50     | C              |                 81369.9 |              0.0109024 |                      0   |          2.14047 |              0.490917 | True             |
|         100 |         4 | shock_revert | shock_revert__all             | C              |                 74336.1 |              0.0690391 |                      0.1 |          4.25676 |              0.500041 | True             |
|         100 |         6 | shock_revert | shock_revert__all             | C              |                 74336.1 |              0.0644491 |                      0.1 |          5.16908 |              0.501823 | True             |

## OCO Top
|   bar_ticks |   horizon | family                | state_id                          | quality_tier   |   annualized_test_fills |   mean_gross_pips_test |   median_gross_pips_test |   gross_std_test |   hit_rate_gross_test | selection_pass   |
|------------:|----------:|:----------------------|:----------------------------------|:---------------|------------------------:|-----------------------:|-------------------------:|-----------------:|----------------------:|:-----------------|
|         100 |         6 | oco_first_touch       | oco_first_touch__all__k2          | C              |                  234217 |               0.116378 |                      0.1 |          4.61315 |              0.504098 | True             |
|         100 |         5 | oco_first_touch       | oco_first_touch__all__k2          | C              |                  230529 |               0.112714 |                      0.1 |          4.17064 |              0.504871 | True             |
|         100 |         4 | oco_first_touch       | oco_first_touch__all__k2          | C              |                  224128 |               0.120221 |                      0.1 |          3.68401 |              0.505241 | True             |
|         100 |         3 | oco_first_touch       | oco_first_touch__all__k2          | C              |                  211419 |               0.123636 |                      0.1 |          3.14266 |              0.507452 | True             |
|         100 |         6 | oco_first_touch       | oco_first_touch__all__k3          | C              |                  207575 |               0.105381 |                      0.1 |          4.37918 |              0.505182 | True             |
|         100 |         5 | oco_first_touch       | oco_first_touch__all__k3          | C              |                  195867 |               0.1042   |                      0.1 |          3.96723 |              0.505689 | True             |
|         100 |         6 | oco_first_touch       | oco_first_touch__low_cost_q50__k2 | C              |                  195833 |               0.121293 |                      0.1 |          4.59855 |              0.504671 | True             |
|         100 |         5 | oco_first_touch       | oco_first_touch__low_cost_q50__k2 | C              |                  192932 |               0.116058 |                      0.1 |          4.15362 |              0.505053 | True             |
|         100 |         4 | oco_first_touch       | oco_first_touch__low_cost_q50__k2 | C              |                  187738 |               0.120537 |                      0.1 |          3.66466 |              0.5057   | True             |
|         100 |         2 | oco_first_touch       | oco_first_touch__all__k2          | C              |                  184712 |               0.126258 |                      0.1 |          2.52356 |              0.51209  | True             |
|         100 |         3 | oco_first_touch_clean | oco_first_touch_clean__all__k2    | B              |                  182959 |               0.799944 |                      0.4 |          2.53698 |              0.579358 | True             |
|         100 |         6 | oco_first_touch_clean | oco_first_touch_clean__all__k3    | B              |                  182171 |               0.988982 |                      0.5 |          3.56423 |              0.569732 | True             |
|         100 |         4 | oco_first_touch_clean | oco_first_touch_clean__all__k2    | A              |                  180455 |               1.16316  |                      0.7 |          2.8929  |              0.611735 | True             |
|         100 |         4 | oco_first_touch       | oco_first_touch__all__k3          | C              |                  178697 |               0.114216 |                      0.1 |          3.52675 |              0.509083 | True             |
|         100 |         5 | oco_first_touch_clean | oco_first_touch_clean__all__k3    | B              |                  177814 |               0.754743 |                      0.4 |          3.28215 |              0.553575 | True             |
|         100 |         3 | oco_first_touch       | oco_first_touch__low_cost_q50__k2 | C              |                  177272 |               0.123359 |                      0.1 |          3.11814 |              0.507413 | True             |
|         100 |         6 | oco_first_touch       | oco_first_touch__low_cost_q50__k3 | C              |                  174243 |               0.104439 |                      0.1 |          4.35335 |              0.504999 | True             |
|         100 |         5 | oco_first_touch_clean | oco_first_touch_clean__all__k2    | A              |                  173003 |               1.54224  |                      1   |          3.20349 |              0.645364 | True             |
|         100 |         2 | oco_first_touch_clean | oco_first_touch_clean__all__k2    | B              |                  171469 |               0.468359 |                      0.2 |          2.11366 |              0.549498 | True             |
|         100 |         4 | oco_first_touch_clean | oco_first_touch_clean__all__k3    | B              |                  167439 |               0.550232 |                      0.3 |          2.9939  |              0.541466 | True             |

## Selection Summary
| library     |   rows_total |   rows_pass |   pass_rate |   mean_annualized_fills_all |   mean_annualized_fills_pass |   mean_gross_all |   mean_gross_pass |   tier_a_rows |   tier_b_rows |   tier_c_rows |
|:------------|-------------:|------------:|------------:|----------------------------:|-----------------------------:|-----------------:|------------------:|--------------:|--------------:|--------------:|
| directional |         2088 |         364 |    0.17433  |                     12329.1 |                      30166   |        0.0820814 |         0.0820426 |             0 |            13 |           351 |
| oco         |         2160 |         762 |    0.352778 |                     15257.2 |                      35552.8 |        2.44101   |         1.22153   |            82 |           201 |           479 |
