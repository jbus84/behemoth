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
|         100 |         6 | path_follow  | path_follow__all              | C              |                 98049.7 |              0.0481679 |                      0.1 |          5.10623 |              0.501484 | True             |
|         100 |         4 | path_follow  | path_follow__all              | C              |                 98049.7 |              0.0475108 |                      0   |          4.20802 |              0.498598 | True             |
|         100 |         5 | path_follow  | path_follow__all              | C              |                 98049.7 |              0.039818  |                      0.1 |          4.6867  |              0.500184 | True             |
|         100 |         3 | path_follow  | path_follow__all              | C              |                 98049.7 |              0.030373  |                      0   |          3.68094 |              0.497236 | True             |
|         100 |         2 | path_follow  | path_follow__all              | C              |                 98049.7 |              0.0266003 |                      0   |          2.99936 |              0.496725 | True             |
|         100 |         1 | path_follow  | path_follow__all              | C              |                 98049.7 |              0.0105535 |                      0   |          2.12657 |              0.491208 | True             |
|         100 |         6 | path_follow  | path_follow__high_abs_vel_q70 | C              |                 82079.7 |              0.0625732 |                      0.1 |          5.28318 |              0.502476 | True             |
|         100 |         4 | path_follow  | path_follow__high_abs_vel_q70 | C              |                 82079.7 |              0.0553185 |                      0   |          4.35264 |              0.498282 | True             |
|         100 |         5 | path_follow  | path_follow__high_abs_vel_q70 | C              |                 82079.7 |              0.0506267 |                      0.1 |          4.84746 |              0.500532 | True             |
|         100 |         3 | path_follow  | path_follow__high_abs_vel_q70 | C              |                 82079.7 |              0.0416833 |                      0   |          3.81104 |              0.498417 | True             |
|         100 |         2 | path_follow  | path_follow__high_abs_vel_q70 | C              |                 82079.7 |              0.0330016 |                      0   |          3.11702 |              0.497927 | True             |
|         100 |         1 | path_follow  | path_follow__high_abs_vel_q70 | C              |                 82079.7 |              0.0134836 |                      0   |          2.20728 |              0.491361 | True             |
|         100 |         6 | path_follow  | path_follow__low_cost_q50     | C              |                 80879.8 |              0.0478193 |                      0.1 |          5.15726 |              0.501656 | True             |
|         100 |         4 | path_follow  | path_follow__low_cost_q50     | C              |                 80879.8 |              0.0462298 |                      0   |          4.24373 |              0.498368 | True             |
|         100 |         5 | path_follow  | path_follow__low_cost_q50     | C              |                 80879.8 |              0.0426017 |                      0.1 |          4.72407 |              0.500937 | True             |
|         100 |         3 | path_follow  | path_follow__low_cost_q50     | C              |                 80879.8 |              0.030551  |                      0   |          3.70701 |              0.497673 | True             |
|         100 |         2 | path_follow  | path_follow__low_cost_q50     | C              |                 80879.8 |              0.0258844 |                      0   |          3.0283  |              0.497115 | True             |
|         100 |         1 | path_follow  | path_follow__low_cost_q50     | C              |                 80879.8 |              0.0121288 |                      0   |          2.13937 |              0.490874 | True             |
|         100 |         6 | shock_revert | shock_revert__all             | C              |                 73167.6 |              0.0679428 |                      0.1 |          5.1688  |              0.505041 | True             |
|         100 |         4 | shock_revert | shock_revert__all             | C              |                 73167.6 |              0.0648386 |                      0.1 |          4.26306 |              0.500336 | True             |

## OCO Top
|   bar_ticks |   horizon | family                | state_id                          | quality_tier   |   annualized_test_fills |   mean_gross_pips_test |   median_gross_pips_test |   gross_std_test |   hit_rate_gross_test | selection_pass   |
|------------:|----------:|:----------------------|:----------------------------------|:---------------|------------------------:|-----------------------:|-------------------------:|-----------------:|----------------------:|:-----------------|
|         100 |         6 | oco_first_touch       | oco_first_touch__all__k2          | C              |                  234196 |               0.114319 |                      0.1 |          4.61895 |              0.503694 | True             |
|         100 |         5 | oco_first_touch       | oco_first_touch__all__k2          | C              |                  230474 |               0.11132  |                      0.1 |          4.17726 |              0.504293 | True             |
|         100 |         4 | oco_first_touch       | oco_first_touch__all__k2          | C              |                  224015 |               0.117424 |                      0.1 |          3.69123 |              0.506531 | True             |
|         100 |         3 | oco_first_touch       | oco_first_touch__all__k2          | C              |                  211347 |               0.120675 |                      0.1 |          3.15089 |              0.507654 | True             |
|         100 |         6 | oco_first_touch       | oco_first_touch__all__k3          | C              |                  207544 |               0.111327 |                      0.1 |          4.38058 |              0.505691 | True             |
|         100 |         6 | oco_first_touch       | oco_first_touch__low_cost_q50__k2 | C              |                  196104 |               0.115074 |                      0.1 |          4.60727 |              0.504355 | True             |
|         100 |         5 | oco_first_touch       | oco_first_touch__all__k3          | C              |                  195793 |               0.111323 |                      0.1 |          3.96935 |              0.507303 | True             |
|         100 |         5 | oco_first_touch       | oco_first_touch__low_cost_q50__k2 | C              |                  193180 |               0.110652 |                      0.1 |          4.16363 |              0.504628 | True             |
|         100 |         4 | oco_first_touch       | oco_first_touch__low_cost_q50__k2 | C              |                  187972 |               0.114134 |                      0.1 |          3.67589 |              0.506529 | True             |
|         100 |         2 | oco_first_touch       | oco_first_touch__all__k2          | C              |                  184644 |               0.129803 |                      0.1 |          2.52579 |              0.511595 | True             |
|         100 |         3 | oco_first_touch_clean | oco_first_touch_clean__all__k2    | B              |                  182872 |               0.799084 |                      0.4 |          2.53822 |              0.580066 | True             |
|         100 |         6 | oco_first_touch_clean | oco_first_touch_clean__all__k3    | A              |                  182238 |               0.99166  |                      0.5 |          3.58002 |              0.570061 | True             |
|         100 |         4 | oco_first_touch_clean | oco_first_touch_clean__all__k2    | A              |                  180186 |               1.16843  |                      0.7 |          2.88569 |              0.614332 | True             |
|         100 |         4 | oco_first_touch       | oco_first_touch__all__k3          | C              |                  178590 |               0.125566 |                      0.1 |          3.52434 |              0.509022 | True             |
|         100 |         5 | oco_first_touch_clean | oco_first_touch_clean__all__k3    | B              |                  177829 |               0.759504 |                      0.4 |          3.30125 |              0.555082 | True             |
|         100 |         3 | oco_first_touch       | oco_first_touch__low_cost_q50__k2 | C              |                  177634 |               0.116397 |                      0.1 |          3.13074 |              0.507253 | True             |
|         100 |         6 | oco_first_touch       | oco_first_touch__low_cost_q50__k3 | C              |                  174622 |               0.106844 |                      0.1 |          4.35577 |              0.504537 | True             |
|         100 |         5 | oco_first_touch_clean | oco_first_touch_clean__all__k2    | A              |                  172690 |               1.54322  |                      1   |          3.19534 |              0.645015 | True             |
|         100 |         2 | oco_first_touch_clean | oco_first_touch_clean__all__k2    | B              |                  171524 |               0.468103 |                      0.2 |          2.1152  |              0.548672 | True             |
|         100 |         4 | oco_first_touch_clean | oco_first_touch_clean__all__k3    | B              |                  167496 |               0.556549 |                      0.3 |          3.0057  |              0.541042 | True             |

## Selection Summary
| library     |   rows_total |   rows_pass |   pass_rate |   mean_annualized_fills_all |   mean_annualized_fills_pass |   mean_gross_all |   mean_gross_pass |   tier_a_rows |   tier_b_rows |   tier_c_rows |
|:------------|-------------:|------------:|------------:|----------------------------:|-----------------------------:|-----------------:|------------------:|--------------:|--------------:|--------------:|
| directional |         2088 |         396 |    0.189655 |                     12381.6 |                      28632.5 |        0.0386883 |         0.0713929 |             0 |            34 |           362 |
| oco         |         2160 |        1685 |    0.780093 |                     15204.7 |                      17592.5 |        2.43932   |         3.30005   |            70 |           218 |          1397 |
