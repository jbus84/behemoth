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
|   bar_ticks |   horizon | family                | state_id                          | quality_tier   |   annualized_test_fills |   mean_gross_pips_test |   median_gross_pips_test |   gross_std_test |   hit_rate_gross_test | selection_pass   |
|------------:|----------:|:----------------------|:----------------------------------|:---------------|------------------------:|-----------------------:|-------------------------:|-----------------:|----------------------:|:-----------------|
|         100 |         6 | oco_first_touch       | oco_first_touch__all__k2          | C              |                  336961 |               0.197831 |                      0.2 |          5.7837  |              0.515721 | True             |
|         100 |         5 | oco_first_touch       | oco_first_touch__all__k2          | C              |                  334796 |               0.199487 |                      0.2 |          5.2349  |              0.517727 | True             |
|         100 |         4 | oco_first_touch       | oco_first_touch__all__k2          | C              |                  330103 |               0.20832  |                      0.2 |          4.62593 |              0.52189  | True             |
|         100 |         3 | oco_first_touch       | oco_first_touch__all__k2          | C              |                  319427 |               0.219862 |                      0.2 |          3.9405  |              0.52772  | True             |
|         100 |         6 | oco_first_touch       | oco_first_touch__all__k3          | C              |                  318106 |               0.174835 |                      0.2 |          5.50987 |              0.519823 | True             |
|         100 |         5 | oco_first_touch       | oco_first_touch__all__k3          | C              |                  307076 |               0.183027 |                      0.1 |          4.9845  |              0.522256 | True             |
|         100 |         2 | oco_first_touch       | oco_first_touch__all__k2          | C              |                  291915 |               0.226975 |                      0.2 |          3.15219 |              0.539594 | True             |
|         100 |         4 | oco_first_touch       | oco_first_touch__all__k3          | C              |                  289110 |               0.193245 |                      0.1 |          4.41821 |              0.526729 | True             |
|         100 |         5 | oco_first_touch_clean | oco_first_touch_clean__all__k3    | A              |                  262571 |               1.28805  |                      0.7 |          3.96229 |              0.602185 | True             |
|         100 |         2 | oco_first_touch_clean | oco_first_touch_clean__all__k2    | B              |                  260662 |               0.780444 |                      0.4 |          2.57815 |              0.599232 | True             |
|         100 |         6 | oco_first_touch_clean | oco_first_touch_clean__all__k3    | A              |                  259573 |               1.64003  |                      1   |          4.29304 |              0.622807 | True             |
|         100 |         3 | oco_first_touch_clean | oco_first_touch_clean__all__k2    | A              |                  259329 |               1.27589  |                      0.8 |          3.08151 |              0.634843 | True             |
|         100 |         3 | oco_first_touch       | oco_first_touch__all__k3          | C              |                  259013 |               0.204601 |                      0.2 |          3.80339 |              0.534492 | True             |
|         100 |         4 | oco_first_touch_clean | oco_first_touch_clean__all__k3    | B              |                  259007 |               0.953429 |                      0.5 |          3.59816 |              0.583187 | True             |
|         100 |         4 | oco_first_touch_clean | oco_first_touch_clean__all__k2    | A              |                  244336 |               1.79929  |                      1.2 |          3.52673 |              0.673939 | True             |
|         100 |         3 | oco_first_touch_clean | oco_first_touch_clean__all__k3    | B              |                  242301 |               0.66184  |                      0.3 |          3.18261 |              0.568922 | True             |
|         100 |         5 | oco_first_touch_clean | oco_first_touch_clean__all__k2    | A              |                  227512 |               2.33111  |                      1.7 |          3.91473 |              0.708478 | True             |
|         100 |         6 | oco_first_touch       | oco_first_touch__all__k5          | C              |                  222862 |               0.226532 |                      0.2 |          5.28993 |              0.525319 | True             |
|         100 |         6 | oco_first_touch       | oco_first_touch__low_cost_q50__k2 | C              |                  219821 |               0.177731 |                      0.2 |          5.6256  |              0.515465 | True             |
|         100 |         5 | oco_first_touch       | oco_first_touch__low_cost_q50__k2 | C              |                  218378 |               0.184392 |                      0.2 |          5.08481 |              0.517992 | True             |

## Selection Summary
| library     |   rows_total |   rows_pass |   pass_rate |   mean_annualized_fills_all |   mean_annualized_fills_pass |   mean_gross_all |   mean_gross_pass |   tier_a_rows |   tier_b_rows |   tier_c_rows |
|:------------|-------------:|------------:|------------:|----------------------------:|-----------------------------:|-----------------:|------------------:|--------------:|--------------:|--------------:|
| directional |         2088 |         422 |    0.202107 |                     17355.4 |                      36473.4 |        0.0550739 |         0.0915233 |             0 |            53 |           369 |
| oco         |         2160 |        1742 |    0.806481 |                     23794.4 |                      27228.7 |        3.25548   |         4.32458   |           109 |           372 |          1261 |
