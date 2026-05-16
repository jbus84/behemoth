# Tick Opportunity Mining Report

## Setup
- symbol: `USDCAD`
- bar_ticks_grid: `100,1000,2000`
- horizons: `1,2,3,4,5,6`
- train_years: `2022,2023,2024`
- test_year: `2025`
- min_annual_fills: `5000.0`
- inclusion_metric: `mean`

## Directional Top
|   bar_ticks |   horizon | family       | state_id                     | quality_tier   |   annualized_test_fills |   mean_gross_pips_test |   median_gross_pips_test |   gross_std_test |   hit_rate_gross_test | selection_pass   |
|------------:|----------:|:-------------|:-----------------------------|:---------------|------------------------:|-----------------------:|-------------------------:|-----------------:|----------------------:|:-----------------|
|         100 |         1 | path_follow  | path_follow__all             | C              |                 90988.1 |              0.0105745 |                      0   |          2.09857 |              0.486319 | True             |
|         100 |         1 | path_follow  | path_follow__high_intensity  | C              |                 90988.1 |              0.0105745 |                      0   |          2.09857 |              0.486319 | True             |
|         100 |         2 | path_follow  | path_follow__all             | C              |                 90987.1 |              0.0302437 |                      0   |          2.85064 |              0.496195 | True             |
|         100 |         2 | path_follow  | path_follow__high_intensity  | C              |                 90987.1 |              0.0302437 |                      0   |          2.85064 |              0.496195 | True             |
|         100 |         3 | path_follow  | path_follow__all             | C              |                 90986.2 |              0.04186   |                      0   |          3.41862 |              0.498097 | True             |
|         100 |         3 | path_follow  | path_follow__high_intensity  | C              |                 90986.2 |              0.04186   |                      0   |          3.41862 |              0.498097 | True             |
|         100 |         5 | path_follow  | path_follow__all             | C              |                 90985.6 |              0.0619932 |                      0.1 |          4.34952 |              0.50311  | True             |
|         100 |         5 | path_follow  | path_follow__high_intensity  | C              |                 90985.6 |              0.0619932 |                      0.1 |          4.34952 |              0.50311  | True             |
|         100 |         6 | path_follow  | path_follow__all             | C              |                 90985.6 |              0.0574403 |                      0.1 |          4.73565 |              0.503893 | True             |
|         100 |         6 | path_follow  | path_follow__high_intensity  | C              |                 90985.6 |              0.0574403 |                      0.1 |          4.73565 |              0.503893 | True             |
|         100 |         4 | path_follow  | path_follow__all             | C              |                 90985.6 |              0.051136  |                      0   |          3.91966 |              0.499283 | True             |
|         100 |         4 | path_follow  | path_follow__high_intensity  | C              |                 90985.6 |              0.051136  |                      0   |          3.91966 |              0.499283 | True             |
|         100 |         2 | shock_revert | shock_revert__all            | C              |                 68194.7 |              0.0376105 |                      0   |          2.9545  |              0.497373 | True             |
|         100 |         2 | shock_revert | shock_revert__high_intensity | C              |                 68194.7 |              0.0376105 |                      0   |          2.9545  |              0.497373 | True             |
|         100 |         1 | shock_revert | shock_revert__all            | C              |                 68194.7 |              0.0126845 |                      0   |          2.19722 |              0.486528 | True             |
|         100 |         1 | shock_revert | shock_revert__high_intensity | C              |                 68194.7 |              0.0126845 |                      0   |          2.19722 |              0.486528 | True             |
|         100 |         5 | shock_revert | shock_revert__all            | C              |                 68194   |              0.0640483 |                      0.1 |          4.4615  |              0.503157 | True             |
|         100 |         5 | shock_revert | shock_revert__high_intensity | C              |                 68194   |              0.0640483 |                      0.1 |          4.4615  |              0.503157 | True             |
|         100 |         6 | shock_revert | shock_revert__all            | C              |                 68194   |              0.0594629 |                      0.1 |          4.84127 |              0.504599 | True             |
|         100 |         6 | shock_revert | shock_revert__high_intensity | C              |                 68194   |              0.0594629 |                      0.1 |          4.84127 |              0.504599 | True             |

## OCO Top
|   bar_ticks |   horizon | family          | state_id                            | quality_tier   |   annualized_test_fills |   mean_gross_pips_test |   median_gross_pips_test |   gross_std_test |   hit_rate_gross_test | selection_pass   |
|------------:|----------:|:----------------|:------------------------------------|:---------------|------------------------:|-----------------------:|-------------------------:|-----------------:|----------------------:|:-----------------|
|         100 |         6 | oco_first_touch | oco_first_touch__all__k0            | D              |                  232113 |               -1.44506 |                     -1.5 |          4.63404 |              0.336031 | False            |
|         100 |         6 | oco_first_touch | oco_first_touch__high_intensity__k0 | D              |                  232113 |               -1.44506 |                     -1.5 |          4.63404 |              0.336031 | False            |
|         100 |         5 | oco_first_touch | oco_first_touch__all__k0            | D              |                  232051 |               -1.44987 |                     -1.4 |          4.24454 |              0.323481 | False            |
|         100 |         5 | oco_first_touch | oco_first_touch__high_intensity__k0 | D              |                  232051 |               -1.44987 |                     -1.4 |          4.24454 |              0.323481 | False            |
|         100 |         4 | oco_first_touch | oco_first_touch__all__k0            | D              |                  231919 |               -1.44649 |                     -1.4 |          3.81159 |              0.306633 | False            |
|         100 |         4 | oco_first_touch | oco_first_touch__high_intensity__k0 | D              |                  231919 |               -1.44649 |                     -1.4 |          3.81159 |              0.306633 | False            |
|         100 |         3 | oco_first_touch | oco_first_touch__all__k0            | D              |                  231645 |               -1.44391 |                     -1.4 |          3.32739 |              0.282546 | False            |
|         100 |         3 | oco_first_touch | oco_first_touch__high_intensity__k0 | D              |                  231645 |               -1.44391 |                     -1.4 |          3.32739 |              0.282546 | False            |
|         100 |         2 | oco_first_touch | oco_first_touch__all__k0            | D              |                  230785 |               -1.44199 |                     -1.4 |          2.74719 |              0.245334 | False            |
|         100 |         2 | oco_first_touch | oco_first_touch__high_intensity__k0 | D              |                  230785 |               -1.44199 |                     -1.4 |          2.74719 |              0.245334 | False            |
|         100 |         6 | oco_first_touch | oco_first_touch__all__k1            | D              |                  230597 |               -1.4473  |                     -1.5 |          4.65137 |              0.336883 | False            |
|         100 |         6 | oco_first_touch | oco_first_touch__high_intensity__k1 | D              |                  230597 |               -1.4473  |                     -1.5 |          4.65137 |              0.336883 | False            |
|         100 |         5 | oco_first_touch | oco_first_touch__all__k1            | D              |                  229972 |               -1.45188 |                     -1.4 |          4.26426 |              0.325175 | False            |
|         100 |         5 | oco_first_touch | oco_first_touch__high_intensity__k1 | D              |                  229972 |               -1.45188 |                     -1.4 |          4.26426 |              0.325175 | False            |
|         100 |         4 | oco_first_touch | oco_first_touch__all__k1            | D              |                  228775 |               -1.44113 |                     -1.4 |          3.83734 |              0.309568 | False            |
|         100 |         4 | oco_first_touch | oco_first_touch__high_intensity__k1 | D              |                  228775 |               -1.44113 |                     -1.4 |          3.83734 |              0.309568 | False            |
|         100 |         3 | oco_first_touch | oco_first_touch__all__k1            | D              |                  226044 |               -1.43804 |                     -1.4 |          3.35944 |              0.286697 | False            |
|         100 |         3 | oco_first_touch | oco_first_touch__high_intensity__k1 | D              |                  226044 |               -1.43804 |                     -1.4 |          3.35944 |              0.286697 | False            |
|         100 |         1 | oco_first_touch | oco_first_touch__all__k0            | D              |                  224962 |               -1.44213 |                     -1.4 |          2.02154 |              0.174736 | False            |
|         100 |         1 | oco_first_touch | oco_first_touch__high_intensity__k0 | D              |                  224962 |               -1.44213 |                     -1.4 |          2.02154 |              0.174736 | False            |

## Selection Summary
| library     |   rows_total |   rows_pass |   pass_rate |   mean_annualized_fills_all |   mean_annualized_fills_pass |   mean_gross_all |   mean_gross_pass |   tier_a_rows |   tier_b_rows |   tier_c_rows |
|:------------|-------------:|------------:|------------:|----------------------------:|-----------------------------:|-----------------:|------------------:|--------------:|--------------:|--------------:|
| directional |         2988 |         435 |    0.145582 |                     7699.16 |                        23070 |         0.113018 |         0.0723435 |             0 |            36 |           399 |
| oco         |         2142 |           0 |    0        |                    14075.7  |                          nan |        -1.63434  |       nan         |             0 |             0 |             0 |
