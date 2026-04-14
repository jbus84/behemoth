# Tick Opportunity Mining Report

## Setup
- symbol: `USDJPY`
- bar_ticks_grid: `100,1000,2000`
- horizons: `1,2,3,4,5,6`
- train_years: `2022,2023,2024`
- test_year: `2025`
- min_annual_fills: `5000.0`
- inclusion_metric: `mean`

## Directional Top
|   bar_ticks |   horizon | family       | state_id                       | quality_tier   |   annualized_test_fills |   mean_gross_pips_test |   median_gross_pips_test |   gross_std_test |   hit_rate_gross_test | selection_pass   |
|------------:|----------:|:-------------|:-------------------------------|:---------------|------------------------:|-----------------------:|-------------------------:|-----------------:|----------------------:|:-----------------|
|         100 |         6 | path_follow  | path_follow__all               | C              |                  139617 |              0.0515392 |                      0   |          6.27853 |              0.499925 | True             |
|         100 |         4 | path_follow  | path_follow__all               | C              |                  139615 |              0.0539807 |                      0.1 |          5.15238 |              0.500018 | True             |
|         100 |         3 | path_follow  | path_follow__all               | C              |                  139615 |              0.0483257 |                      0.1 |          4.49436 |              0.50009  | True             |
|         100 |         2 | path_follow  | path_follow__all               | C              |                  139615 |              0.0322418 |                      0   |          3.68755 |              0.499975 | True             |
|         100 |         1 | path_follow  | path_follow__all               | C              |                  139615 |              0.0248904 |                      0   |          2.65284 |              0.498757 | True             |
|         100 |         5 | path_follow  | path_follow__all               | C              |                  139615 |              0.0547696 |                      0   |          5.73716 |              0.499403 | True             |
|         100 |         6 | path_follow  | path_follow__high_abs_vel_q70  | C              |                  124294 |              0.0552238 |                      0   |          6.38503 |              0.499281 | True             |
|         100 |         5 | path_follow  | path_follow__high_abs_vel_q70  | C              |                  124293 |              0.0611278 |                      0   |          5.83094 |              0.499059 | True             |
|         100 |         4 | path_follow  | path_follow__high_abs_vel_q70  | C              |                  124293 |              0.0585256 |                      0   |          5.23746 |              0.499382 | True             |
|         100 |         3 | path_follow  | path_follow__high_abs_vel_q70  | C              |                  124293 |              0.0505276 |                      0   |          4.56302 |              0.499568 | True             |
|         100 |         2 | path_follow  | path_follow__high_abs_vel_q70  | C              |                  124293 |              0.0341967 |                      0   |          3.73595 |              0.499689 | True             |
|         100 |         1 | path_follow  | path_follow__high_abs_vel_q70  | C              |                  124293 |              0.0284392 |                      0   |          2.6715  |              0.499398 | True             |
|         100 |         6 | shock_revert | shock_revert__all              | C              |                  104878 |              0.0676226 |                      0.1 |          6.35036 |              0.501962 | True             |
|         100 |         5 | shock_revert | shock_revert__all              | C              |                  104877 |              0.0665713 |                      0.1 |          5.80995 |              0.500263 | True             |
|         100 |         4 | shock_revert | shock_revert__all              | C              |                  104877 |              0.0620109 |                      0.1 |          5.23129 |              0.501957 | True             |
|         100 |         3 | shock_revert | shock_revert__all              | C              |                  104877 |              0.0535179 |                      0.1 |          4.54927 |              0.501497 | True             |
|         100 |         2 | shock_revert | shock_revert__all              | C              |                  104877 |              0.0369758 |                      0.1 |          3.77041 |              0.501823 | True             |
|         100 |         1 | shock_revert | shock_revert__all              | C              |                  104877 |              0.0268522 |                      0.1 |          2.71905 |              0.500139 | True             |
|         100 |         6 | shock_revert | shock_revert__high_abs_vel_q70 | C              |                  100332 |              0.0678199 |                      0.1 |          6.39794 |              0.5004   | True             |
|         100 |         5 | shock_revert | shock_revert__high_abs_vel_q70 | C              |                  100331 |              0.0683344 |                      0   |          5.84837 |              0.499055 | True             |

## OCO Top
|   bar_ticks |   horizon | family                | state_id                                    | quality_tier   |   annualized_test_fills |   mean_gross_pips_test |   median_gross_pips_test |   gross_std_test |   hit_rate_gross_test | selection_pass   |
|------------:|----------:|:----------------------|:--------------------------------------------|:---------------|------------------------:|-----------------------:|-------------------------:|-----------------:|----------------------:|:-----------------|
|         100 |         6 | oco_first_touch_clean | oco_first_touch_clean__all__k3              | C              |                258620   |               0.517735 |                      0.3 |          5.46032 |              0.519298 | True             |
|         100 |         4 | oco_first_touch_clean | oco_first_touch_clean__all__k2              | C              |                243702   |               0.479903 |                      0.3 |          4.40528 |              0.523841 | True             |
|         100 |         5 | oco_first_touch_clean | oco_first_touch_clean__all__k2              | B              |                226823   |               0.974515 |                      0.7 |          4.78599 |              0.562167 | True             |
|         100 |         6 | oco_first_touch_clean | oco_first_touch_clean__all__k2              | B              |                211523   |               1.45634  |                      1.1 |          5.07549 |              0.594455 | True             |
|         100 |         5 | oco_first_touch_clean | oco_first_touch_clean__low_cost_q50__k2     | C              |                150531   |               0.99205  |                      0.7 |          4.6891  |              0.566332 | True             |
|         100 |         6 | oco_first_touch_clean | oco_first_touch_clean__low_cost_q50__k2     | B              |                140457   |               1.45582  |                      1.1 |          4.97098 |              0.598769 | True             |
|         100 |         5 | oco_first_touch_clean | oco_first_touch_clean__high_range_q70__k3   | C              |                112335   |               0.437105 |                      0.2 |          5.46032 |              0.515205 | True             |
|         100 |         5 | oco_first_touch_clean | oco_first_touch_clean__high_abs_vel_q70__k3 | C              |                110455   |               0.336999 |                      0.1 |          5.25938 |              0.508146 | True             |
|         100 |         6 | oco_first_touch_clean | oco_first_touch_clean__high_range_q70__k3   | B              |                109159   |               0.828362 |                      0.6 |          5.83817 |              0.539137 | True             |
|         100 |         3 | oco_first_touch_clean | oco_first_touch_clean__high_range_q70__k2   | C              |                108689   |               0.179305 |                      0   |          4.29473 |              0.498527 | True             |
|         100 |         6 | oco_first_touch_clean | oco_first_touch_clean__high_abs_vel_q70__k3 | C              |                108437   |               0.692726 |                      0.4 |          5.62651 |              0.532014 | True             |
|         100 |         4 | oco_first_touch_clean | oco_first_touch_clean__high_abs_vel_q70__k2 | C              |                100716   |               0.633175 |                      0.4 |          4.53585 |              0.539066 | True             |
|         100 |         5 | oco_first_touch_clean | oco_first_touch_clean__low_cost_q30__k2     | C              |                100221   |               1.03688  |                      0.8 |          4.71187 |              0.570809 | True             |
|         100 |         4 | oco_first_touch_clean | oco_first_touch_clean__high_range_q70__k2   | B              |                100010   |               0.732173 |                      0.5 |          4.75779 |              0.545913 | True             |
|         100 |         6 | oco_first_touch_clean | oco_first_touch_clean__low_cost_q30__k2     | C              |                 93514.7 |               1.49459  |                      1.2 |          4.94967 |              0.603296 | True             |
|         100 |         5 | oco_first_touch_clean | oco_first_touch_clean__high_abs_vel_q70__k2 | B              |                 93176.4 |               1.16766  |                      0.9 |          4.90904 |              0.579318 | True             |
|         100 |         5 | oco_first_touch_clean | oco_first_touch_clean__high_range_q70__k2   | A              |                 91868   |               1.31492  |                      1   |          5.11932 |              0.587413 | True             |
|         100 |         6 | oco_first_touch_clean | oco_first_touch_clean__high_abs_vel_q70__k2 | A              |                 86482.4 |               1.6844   |                      1.4 |          5.23703 |              0.613146 | True             |
|         100 |         6 | oco_first_touch_clean | oco_first_touch_clean__high_range_q70__k2   | A              |                 85034.7 |               1.86484  |                      1.5 |          5.4576  |              0.621293 | True             |
|         100 |         5 | oco_first_touch_clean | oco_first_touch_clean__high_abs_vel_q80__k3 | C              |                 81467.1 |               0.377494 |                      0.2 |          5.31926 |              0.511839 | True             |

## Selection Summary
| library     |   rows_total |   rows_pass |   pass_rate |   mean_annualized_fills_all |   mean_annualized_fills_pass |   mean_gross_all |   mean_gross_pass |   tier_a_rows |   tier_b_rows |   tier_c_rows |
|:------------|-------------:|------------:|------------:|----------------------------:|-----------------------------:|-----------------:|------------------:|--------------:|--------------:|--------------:|
| directional |         2088 |         428 |    0.204981 |                     17313.2 |                      36010   |        0.0166109 |          0.117598 |             2 |            63 |           363 |
| oco         |         2160 |         614 |    0.284259 |                     23734   |                      11745.7 |        1.16861   |          5.76644  |            28 |           102 |           484 |
