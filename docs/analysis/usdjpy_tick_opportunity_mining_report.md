# Tick Opportunity Mining Report

## Setup
- symbol: `USDJPY`
- bar_ticks_grid: `100,1000,2000,5000,10000`
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
|   bar_ticks |   horizon | family          | state_id                                               | quality_tier   |   annualized_test_fills |   mean_gross_pips_test |   median_gross_pips_test |   gross_std_test |   hit_rate_gross_test | selection_pass   |
|------------:|----------:|:----------------|:-------------------------------------------------------|:---------------|------------------------:|-----------------------:|-------------------------:|-----------------:|----------------------:|:-----------------|
|        5000 |         6 | oco_first_touch | oco_first_touch__low_cost_q30__k8                      | C              |                 4942.13 |               0.283749 |                    -0.3  |          43.5017 |              0.494864 | True             |
|        5000 |         5 | oco_first_touch | oco_first_touch__low_cost_q30__k8                      | C              |                 4934.97 |               0.425092 |                     0.15 |          39.4218 |              0.502201 | True             |
|        5000 |         4 | oco_first_touch | oco_first_touch__low_cost_q30__k8                      | C              |                 4929.99 |               0.397946 |                     0.3  |          35.2056 |              0.505503 | True             |
|       10000 |         6 | oco_first_touch | oco_first_touch__all__k10                              | C              |                 3411.79 |              -1.10396  |                    -0.05 |          62.4688 |              0.498522 | True             |
|       10000 |         6 | oco_first_touch | oco_first_touch__high_intensity__k10                   | C              |                 3411.79 |              -1.10396  |                    -0.05 |          62.4688 |              0.498522 | True             |
|        5000 |         6 | oco_first_touch | oco_first_touch__high_range_q70__k10                   | C              |                 3009.31 |              -0.375469 |                     0    |          44.9259 |              0.499331 | True             |
|       10000 |         6 | oco_first_touch | oco_first_touch__low_cost_q50__k8                      | C              |                 2525.61 |              -0.819636 |                    -0.6  |          64.85   |              0.497143 | True             |
|       10000 |         6 | oco_first_touch | oco_first_touch__low_cost_q50__k10                     | C              |                 2522.98 |              -0.491472 |                    -0.6  |          64.9516 |              0.49714  | True             |
|       10000 |         4 | oco_first_touch | oco_first_touch__low_cost_q50__k10                     | C              |                 2521.94 |              -0.61594  |                    -0.15 |          51.9727 |              0.498962 | True             |
|       10000 |         5 | oco_first_touch | oco_first_touch__low_cost_q50__k10                     | C              |                 2521.62 |              -0.441164 |                    -0.55 |          58.875  |              0.497401 | True             |
|       10000 |         5 | oco_first_touch | oco_first_touch__low_cost_q30__k8                      | C              |                 2460.25 |              -0.856492 |                    -1.9  |          57.638  |              0.486712 | True             |
|       10000 |         6 | oco_first_touch | oco_first_touch__low_cost_q30__k5                      | C              |                 2460.23 |               0.99635  |                     1.1  |          63.4009 |              0.508745 | True             |
|       10000 |         6 | oco_first_touch | oco_first_touch__low_cost_q30__k8                      | C              |                 2460.23 |              -0.373916 |                    -0.2  |          63.362  |              0.49962  | True             |
|       10000 |         6 | oco_first_touch | oco_first_touch__low_cost_q30__k10                     | C              |                 2456.49 |              -0.881417 |                    -1.1  |          63.5427 |              0.494288 | True             |
|       10000 |         4 | oco_first_touch | oco_first_touch__low_cost_q30__k10                     | C              |                 2455.19 |              -1.33055  |                    -0.65 |          50.955  |              0.492401 | True             |
|       10000 |         5 | oco_first_touch | oco_first_touch__low_cost_q30__k10                     | C              |                 2454.64 |              -1.39604  |                    -2.3  |          57.7977 |              0.480974 | True             |
|        5000 |         5 | oco_first_touch | oco_first_touch__low_cost_q30_and_high_abs_vel_q70__k8 | C              |                 2346.19 |               1.20509  |                     0.25 |          39.7156 |              0.506173 | True             |
|        5000 |         4 | oco_first_touch | oco_first_touch__low_cost_q30_and_high_abs_vel_q70__k8 | C              |                 2346.19 |               0.69784  |                     0.6  |          36.1769 |              0.508488 | True             |
|        5000 |         6 | oco_first_touch | oco_first_touch__high_vol_cluster__k10                 | C              |                 2086    |               0.923177 |                     0.5  |          44.1786 |              0.504587 | True             |
|        5000 |         6 | oco_first_touch | oco_first_touch__low_cost_q30_and_high_range_q70__k8   | C              |                 2055.2  |              -0.187721 |                     0    |          43.8914 |              0.499117 | True             |

## Selection Summary
| library     |   rows_total |   rows_pass |   pass_rate |   mean_annualized_fills_all |   mean_annualized_fills_pass |   mean_gross_all |   mean_gross_pass |   tier_a_rows |   tier_b_rows |   tier_c_rows |
|:------------|-------------:|------------:|------------:|----------------------------:|-----------------------------:|-----------------:|------------------:|--------------:|--------------:|--------------:|
| directional |         4968 |         587 |   0.118156  |                     9925.26 |                      35277.5 |       -0.0361679 |          0.118064 |             4 |           100 |           483 |
| oco         |         3570 |          92 |   0.0257703 |                    20001.8  |                       1530   |       -0.833904  |         -1.32871  |             0 |             0 |            92 |
