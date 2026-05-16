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
|   bar_ticks |   horizon | family       | state_id                      | quality_tier   |   annualized_test_fills |   mean_gross_pips_test |   median_gross_pips_test |   gross_std_test |   hit_rate_gross_test | selection_pass   |
|------------:|----------:|:-------------|:------------------------------|:---------------|------------------------:|-----------------------:|-------------------------:|-----------------:|----------------------:|:-----------------|
|         100 |         6 | path_follow  | path_follow__all              | C              |                  139617 |              0.0515392 |                      0   |          6.27853 |              0.499925 | True             |
|         100 |         6 | path_follow  | path_follow__high_intensity   | C              |                  139617 |              0.0515392 |                      0   |          6.27853 |              0.499925 | True             |
|         100 |         4 | path_follow  | path_follow__all              | C              |                  139615 |              0.0539807 |                      0.1 |          5.15238 |              0.500018 | True             |
|         100 |         4 | path_follow  | path_follow__high_intensity   | C              |                  139615 |              0.0539807 |                      0.1 |          5.15238 |              0.500018 | True             |
|         100 |         3 | path_follow  | path_follow__all              | C              |                  139615 |              0.0483257 |                      0.1 |          4.49436 |              0.50009  | True             |
|         100 |         3 | path_follow  | path_follow__high_intensity   | C              |                  139615 |              0.0483257 |                      0.1 |          4.49436 |              0.50009  | True             |
|         100 |         2 | path_follow  | path_follow__all              | C              |                  139615 |              0.0322418 |                      0   |          3.68755 |              0.499975 | True             |
|         100 |         2 | path_follow  | path_follow__high_intensity   | C              |                  139615 |              0.0322418 |                      0   |          3.68755 |              0.499975 | True             |
|         100 |         1 | path_follow  | path_follow__all              | C              |                  139615 |              0.0248904 |                      0   |          2.65284 |              0.498757 | True             |
|         100 |         1 | path_follow  | path_follow__high_intensity   | C              |                  139615 |              0.0248904 |                      0   |          2.65284 |              0.498757 | True             |
|         100 |         5 | path_follow  | path_follow__all              | C              |                  139615 |              0.0547696 |                      0   |          5.73716 |              0.499403 | True             |
|         100 |         5 | path_follow  | path_follow__high_intensity   | C              |                  139615 |              0.0547696 |                      0   |          5.73716 |              0.499403 | True             |
|         100 |         6 | path_follow  | path_follow__high_abs_vel_q70 | C              |                  124294 |              0.0552238 |                      0   |          6.38503 |              0.499281 | True             |
|         100 |         5 | path_follow  | path_follow__high_abs_vel_q70 | C              |                  124293 |              0.0611278 |                      0   |          5.83094 |              0.499059 | True             |
|         100 |         4 | path_follow  | path_follow__high_abs_vel_q70 | C              |                  124293 |              0.0585256 |                      0   |          5.23746 |              0.499382 | True             |
|         100 |         3 | path_follow  | path_follow__high_abs_vel_q70 | C              |                  124293 |              0.0505276 |                      0   |          4.56302 |              0.499568 | True             |
|         100 |         2 | path_follow  | path_follow__high_abs_vel_q70 | C              |                  124293 |              0.0341967 |                      0   |          3.73595 |              0.499689 | True             |
|         100 |         1 | path_follow  | path_follow__high_abs_vel_q70 | C              |                  124293 |              0.0284392 |                      0   |          2.6715  |              0.499398 | True             |
|         100 |         6 | shock_revert | shock_revert__all             | C              |                  104878 |              0.0676226 |                      0.1 |          6.35036 |              0.501962 | True             |
|         100 |         6 | shock_revert | shock_revert__high_intensity  | C              |                  104878 |              0.0676226 |                      0.1 |          6.35036 |              0.501962 | True             |

## OCO Top
|   bar_ticks |   horizon | family          | state_id                            | quality_tier   |   annualized_test_fills |   mean_gross_pips_test |   median_gross_pips_test |   gross_std_test |   hit_rate_gross_test | selection_pass   |
|------------:|----------:|:----------------|:------------------------------------|:---------------|------------------------:|-----------------------:|-------------------------:|-----------------:|----------------------:|:-----------------|
|         100 |         6 | oco_first_touch | oco_first_touch__all__k0            | D              |                  341597 |              -0.663392 |                     -0.7 |          6.1403  |              0.444986 | False            |
|         100 |         6 | oco_first_touch | oco_first_touch__high_intensity__k0 | D              |                  341597 |              -0.663392 |                     -0.7 |          6.1403  |              0.444986 | False            |
|         100 |         5 | oco_first_touch | oco_first_touch__all__k0            | D              |                  341576 |              -0.666053 |                     -0.7 |          5.62926 |              0.440536 | False            |
|         100 |         5 | oco_first_touch | oco_first_touch__high_intensity__k0 | D              |                  341576 |              -0.666053 |                     -0.7 |          5.62926 |              0.440536 | False            |
|         100 |         4 | oco_first_touch | oco_first_touch__all__k0            | D              |                  341533 |              -0.66408  |                     -0.7 |          5.04041 |              0.434127 | False            |
|         100 |         4 | oco_first_touch | oco_first_touch__high_intensity__k0 | D              |                  341533 |              -0.66408  |                     -0.7 |          5.04041 |              0.434127 | False            |
|         100 |         3 | oco_first_touch | oco_first_touch__all__k0            | D              |                  341462 |              -0.668757 |                     -0.7 |          4.3818  |              0.42383  | False            |
|         100 |         3 | oco_first_touch | oco_first_touch__high_intensity__k0 | D              |                  341462 |              -0.668757 |                     -0.7 |          4.3818  |              0.42383  | False            |
|         100 |         2 | oco_first_touch | oco_first_touch__all__k0            | D              |                  341274 |              -0.660982 |                     -0.6 |          3.59273 |              0.408682 | False            |
|         100 |         2 | oco_first_touch | oco_first_touch__high_intensity__k0 | D              |                  341274 |              -0.660982 |                     -0.6 |          3.59273 |              0.408682 | False            |
|         100 |         6 | oco_first_touch | oco_first_touch__all__k1            | D              |                  340940 |              -0.663304 |                     -0.7 |          6.13361 |              0.445426 | False            |
|         100 |         6 | oco_first_touch | oco_first_touch__high_intensity__k1 | D              |                  340940 |              -0.663304 |                     -0.7 |          6.13361 |              0.445426 | False            |
|         100 |         5 | oco_first_touch | oco_first_touch__all__k1            | D              |                  340748 |              -0.662995 |                     -0.7 |          5.62607 |              0.440608 | False            |
|         100 |         5 | oco_first_touch | oco_first_touch__high_intensity__k1 | D              |                  340748 |              -0.662995 |                     -0.7 |          5.62607 |              0.440608 | False            |
|         100 |         4 | oco_first_touch | oco_first_touch__all__k1            | D              |                  340460 |              -0.665971 |                     -0.7 |          5.03175 |              0.433845 | False            |
|         100 |         4 | oco_first_touch | oco_first_touch__high_intensity__k1 | D              |                  340460 |              -0.665971 |                     -0.7 |          5.03175 |              0.433845 | False            |
|         100 |         1 | oco_first_touch | oco_first_touch__all__k0            | D              |                  340201 |              -0.657716 |                     -0.6 |          2.58931 |              0.37441  | False            |
|         100 |         1 | oco_first_touch | oco_first_touch__high_intensity__k0 | D              |                  340201 |              -0.657716 |                     -0.6 |          2.58931 |              0.37441  | False            |
|         100 |         3 | oco_first_touch | oco_first_touch__all__k1            | D              |                  339932 |              -0.661087 |                     -0.7 |          4.38464 |              0.424478 | False            |
|         100 |         3 | oco_first_touch | oco_first_touch__high_intensity__k1 | D              |                  339932 |              -0.661087 |                     -0.7 |          4.38464 |              0.424478 | False            |

## Selection Summary
| library     |   rows_total |   rows_pass |   pass_rate |   mean_annualized_fills_all |   mean_annualized_fills_pass |   mean_gross_all |   mean_gross_pass |   tier_a_rows |   tier_b_rows |   tier_c_rows |
|:------------|-------------:|------------:|------------:|----------------------------:|-----------------------------:|-----------------:|------------------:|--------------:|--------------:|--------------:|
| directional |         2988 |         587 |    0.196452 |                     16019.3 |                      35277.5 |        0.0277788 |          0.118064 |             4 |           100 |           483 |
| oco         |         2142 |           0 |    0        |                     31951.9 |                        nan   |       -0.656859  |        nan        |             0 |             0 |             0 |
