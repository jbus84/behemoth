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
|         100 |         6 | path_follow  | path_follow__all               | C              |                  139859 |              0.0537666 |                      0.1 |          6.28685 |              0.500979 | True             |
|         100 |         5 | path_follow  | path_follow__all               | C              |                  139859 |              0.0538695 |                      0.1 |          5.75334 |              0.500316 | True             |
|         100 |         4 | path_follow  | path_follow__all               | C              |                  139859 |              0.0529145 |                      0.1 |          5.16093 |              0.500502 | True             |
|         100 |         3 | path_follow  | path_follow__all               | C              |                  139859 |              0.0494281 |                      0.1 |          4.49097 |              0.500179 | True             |
|         100 |         2 | path_follow  | path_follow__all               | C              |                  139859 |              0.0328165 |                      0   |          3.68952 |              0.498852 | True             |
|         100 |         1 | path_follow  | path_follow__all               | C              |                  139858 |              0.0239236 |                      0   |          2.6167  |              0.497708 | True             |
|         100 |         6 | path_follow  | path_follow__high_abs_vel_q70  | C              |                  124254 |              0.0639796 |                      0.1 |          6.39703 |              0.500905 | True             |
|         100 |         5 | path_follow  | path_follow__high_abs_vel_q70  | C              |                  124253 |              0.0622112 |                      0.1 |          5.84794 |              0.500424 | True             |
|         100 |         4 | path_follow  | path_follow__high_abs_vel_q70  | C              |                  124253 |              0.060037  |                      0.1 |          5.24112 |              0.500311 | True             |
|         100 |         3 | path_follow  | path_follow__high_abs_vel_q70  | C              |                  124253 |              0.0539918 |                      0   |          4.57755 |              0.499931 | True             |
|         100 |         2 | path_follow  | path_follow__high_abs_vel_q70  | C              |                  124253 |              0.0368407 |                      0   |          3.77051 |              0.499003 | True             |
|         100 |         1 | path_follow  | path_follow__high_abs_vel_q70  | C              |                  124253 |              0.02811   |                      0   |          2.67538 |              0.499099 | True             |
|         100 |         6 | shock_revert | shock_revert__all              | C              |                  104944 |              0.0702161 |                      0.1 |          6.34935 |              0.501664 | True             |
|         100 |         5 | shock_revert | shock_revert__all              | C              |                  104936 |              0.067469  |                      0.1 |          5.8044  |              0.501066 | True             |
|         100 |         4 | shock_revert | shock_revert__all              | C              |                  104936 |              0.0628951 |                      0.1 |          5.20959 |              0.501611 | True             |
|         100 |         3 | shock_revert | shock_revert__all              | C              |                  104936 |              0.0537549 |                      0.1 |          4.55571 |              0.500693 | True             |
|         100 |         2 | shock_revert | shock_revert__all              | C              |                  104936 |              0.0358312 |                      0.1 |          3.76425 |              0.500617 | True             |
|         100 |         1 | shock_revert | shock_revert__all              | C              |                  104936 |              0.0266183 |                      0   |          2.67856 |              0.499326 | True             |
|         100 |         6 | shock_revert | shock_revert__high_abs_vel_q70 | C              |                  100160 |              0.0742267 |                      0.1 |          6.41729 |              0.501308 | True             |
|         100 |         5 | shock_revert | shock_revert__high_abs_vel_q70 | C              |                  100153 |              0.0718062 |                      0.1 |          5.86398 |              0.500661 | True             |

## OCO Top
|   bar_ticks |   horizon | family                | state_id                          | quality_tier   |   annualized_test_fills |   mean_gross_pips_test |   median_gross_pips_test |   gross_std_test |   hit_rate_gross_test | selection_pass   |
|------------:|----------:|:----------------------|:----------------------------------|:---------------|------------------------:|-----------------------:|-------------------------:|-----------------:|----------------------:|:-----------------|
|         100 |         6 | oco_first_touch       | oco_first_touch__all__k2          | C              |                  337031 |               0.202245 |                      0.2 |          5.78931 |              0.517037 | True             |
|         100 |         5 | oco_first_touch       | oco_first_touch__all__k2          | C              |                  334852 |               0.205954 |                      0.2 |          5.24041 |              0.518602 | True             |
|         100 |         4 | oco_first_touch       | oco_first_touch__all__k2          | C              |                  330270 |               0.211485 |                      0.2 |          4.63255 |              0.522207 | True             |
|         100 |         3 | oco_first_touch       | oco_first_touch__all__k2          | C              |                  319618 |               0.220952 |                      0.2 |          3.9487  |              0.528342 | True             |
|         100 |         6 | oco_first_touch       | oco_first_touch__all__k3          | C              |                  318188 |               0.176308 |                      0.2 |          5.51685 |              0.519673 | True             |
|         100 |         5 | oco_first_touch       | oco_first_touch__all__k3          | C              |                  307232 |               0.18842  |                      0.2 |          4.98936 |              0.52349  | True             |
|         100 |         2 | oco_first_touch       | oco_first_touch__all__k2          | C              |                  292054 |               0.226491 |                      0.2 |          3.16072 |              0.539482 | True             |
|         100 |         4 | oco_first_touch       | oco_first_touch__all__k3          | C              |                  289304 |               0.196763 |                      0.2 |          4.42481 |              0.527606 | True             |
|         100 |         5 | oco_first_touch_clean | oco_first_touch_clean__all__k3    | A              |                  262905 |               1.28777  |                      0.7 |          3.96619 |              0.602908 | True             |
|         100 |         2 | oco_first_touch_clean | oco_first_touch_clean__all__k2    | B              |                  260841 |               0.781391 |                      0.4 |          2.56746 |              0.599167 | True             |
|         100 |         6 | oco_first_touch_clean | oco_first_touch_clean__all__k3    | A              |                  259717 |               1.64134  |                      1   |          4.29717 |              0.622494 | True             |
|         100 |         3 | oco_first_touch_clean | oco_first_touch_clean__all__k2    | A              |                  259495 |               1.27845  |                      0.8 |          3.08158 |              0.635892 | True             |
|         100 |         4 | oco_first_touch_clean | oco_first_touch_clean__all__k3    | B              |                  259386 |               0.953462 |                      0.5 |          3.604   |              0.58365  | True             |
|         100 |         3 | oco_first_touch       | oco_first_touch__all__k3          | C              |                  258915 |               0.208013 |                      0.2 |          3.81448 |              0.535209 | True             |
|         100 |         4 | oco_first_touch_clean | oco_first_touch_clean__all__k2    | A              |                  244433 |               1.80511  |                      1.2 |          3.52541 |              0.674413 | True             |
|         100 |         3 | oco_first_touch_clean | oco_first_touch_clean__all__k3    | B              |                  242287 |               0.664264 |                      0.3 |          3.19275 |              0.569559 | True             |
|         100 |         5 | oco_first_touch_clean | oco_first_touch_clean__all__k2    | A              |                  227604 |               2.33496  |                      1.7 |          3.9151  |              0.709461 | True             |
|         100 |         6 | oco_first_touch       | oco_first_touch__all__k5          | C              |                  222897 |               0.228308 |                      0.2 |          5.29989 |              0.525704 | True             |
|         100 |         6 | oco_first_touch       | oco_first_touch__low_cost_q50__k2 | C              |                  218250 |               0.18381  |                      0.2 |          5.64383 |              0.517191 | True             |
|         100 |         5 | oco_first_touch       | oco_first_touch__low_cost_q50__k2 | C              |                  216847 |               0.18975  |                      0.2 |          5.10192 |              0.518958 | True             |

## Selection Summary
| library     |   rows_total |   rows_pass |   pass_rate |   mean_annualized_fills_all |   mean_annualized_fills_pass |   mean_gross_all |   mean_gross_pass |   tier_a_rows |   tier_b_rows |   tier_c_rows |
|:------------|-------------:|------------:|------------:|----------------------------:|-----------------------------:|-----------------:|------------------:|--------------:|--------------:|--------------:|
| directional |         2088 |         429 |     0.20546 |                     17318.2 |                      35908.1 |        0.0245308 |           0.12552 |             2 |            61 |           366 |
| oco         |         2160 |        1738 |     0.80463 |                     23842   |                      27336.2 |        3.36066   |           4.43222 |           112 |           368 |          1258 |
