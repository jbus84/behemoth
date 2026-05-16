# Tick Opportunity Mining Report

## Setup
- symbol: `USDCAD`
- bar_ticks_grid: `100,1000,2000,5000,10000`
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
|   bar_ticks |   horizon | family          | state_id                               | quality_tier   |   annualized_test_fills |   mean_gross_pips_test |   median_gross_pips_test |   gross_std_test |   hit_rate_gross_test | selection_pass   |
|------------:|----------:|:----------------|:---------------------------------------|:---------------|------------------------:|-----------------------:|-------------------------:|-----------------:|----------------------:|:-----------------|
|       10000 |         4 | oco_first_touch | oco_first_touch__high_activity__k2     | C              |                 710.713 |              1.5478    |                     2.3  |          34.8858 |              0.530583 | True             |
|       10000 |         3 | oco_first_touch | oco_first_touch__high_vol_cluster__k10 | C              |                 709.709 |              1.11207   |                     0.1  |          30.0416 |              0.504261 | True             |
|       10000 |         6 | oco_first_touch | oco_first_touch__high_activity__k10    | C              |                 706.67  |             -0.233763  |                    -0.3  |          43.9338 |              0.496423 | True             |
|       10000 |         4 | oco_first_touch | oco_first_touch__high_activity__k8     | C              |                 704.648 |              0.38924   |                    -0.2  |          35.1864 |              0.499283 | True             |
|       10000 |         5 | oco_first_touch | oco_first_touch__high_activity__k10    | C              |                 702.626 |             -1.08331   |                    -1.2  |          40.223  |              0.480576 | True             |
|       10000 |         4 | oco_first_touch | oco_first_touch__high_activity__k10    | C              |                 696.56  |             -0.257329  |                     0.1  |          35.3538 |              0.500726 | True             |
|       10000 |         4 | oco_first_touch | oco_first_touch__ny_overlap__k10       | C              |                 678.816 |              0.365676  |                    -1    |          32.0575 |              0.491828 | True             |
|       10000 |         5 | oco_first_touch | oco_first_touch__ny_overlap__k10       | C              |                 678.722 |             -0.716841  |                     0.5  |          36.3657 |              0.502235 | True             |
|       10000 |         4 | oco_first_touch | oco_first_touch__high_abs_vel_q70__k10 | C              |                 580.945 |              2.36372   |                     0.8  |          37.5434 |              0.510417 | True             |
|       10000 |         3 | oco_first_touch | oco_first_touch__high_abs_vel_q70__k10 | C              |                 580.945 |              1.84757   |                    -0.1  |          32.7584 |              0.498264 | True             |
|       10000 |         4 | oco_first_touch | oco_first_touch__high_range_q70__k10   | C              |                 548.958 |              3.24457   |                     2.5  |          41.3979 |              0.532228 | True             |
|       10000 |         3 | oco_first_touch | oco_first_touch__high_range_q70__k10   | C              |                 548.958 |              2.47532   |                     2    |          37.446  |              0.524862 | True             |
|       10000 |         6 | oco_first_touch | oco_first_touch__asia__k0              | C              |                 459.083 |              0.927692  |                     0.1  |          42.4763 |              0.501099 | True             |
|       10000 |         5 | oco_first_touch | oco_first_touch__asia__k0              | C              |                 459.083 |             -0.0162637 |                    -1.5  |          39.3392 |              0.472527 | True             |
|       10000 |         4 | oco_first_touch | oco_first_touch__high_range_q80__k10   | C              |                 393.066 |              4.51349   |                     4.6  |          43.1053 |              0.537037 | True             |
|       10000 |         3 | oco_first_touch | oco_first_touch__high_range_q80__k10   | C              |                 393.066 |              4.18228   |                     4.9  |          38.3277 |              0.55291  | True             |
|       10000 |         4 | oco_first_touch | oco_first_touch__high_range_q80__k8    | C              |                 393.066 |              3.84656   |                     1.4  |          43.2516 |              0.526455 | True             |
|       10000 |         3 | oco_first_touch | oco_first_touch__high_range_q80__k8    | C              |                 393.066 |              3.60212   |                     2.75 |          38.6391 |              0.539683 | True             |
|       10000 |         5 | oco_first_touch | oco_first_touch__high_range_q80__k10   | C              |                 393.066 |              3.12963   |                     2    |          49.4574 |              0.52381  | True             |
|       10000 |         5 | oco_first_touch | oco_first_touch__high_range_q80__k8    | C              |                 393.066 |              2.42963   |                     0.05 |          49.7111 |              0.5      | True             |

## Selection Summary
| library     |   rows_total |   rows_pass |   pass_rate |   mean_annualized_fills_all |   mean_annualized_fills_pass |   mean_gross_all |   mean_gross_pass |   tier_a_rows |   tier_b_rows |   tier_c_rows |
|:------------|-------------:|------------:|------------:|----------------------------:|-----------------------------:|-----------------:|------------------:|--------------:|--------------:|--------------:|
| directional |         4968 |         435 |   0.0875604 |                     4749.74 |                    23070     |         0.249495 |         0.0723435 |             0 |            36 |           399 |
| oco         |         3570 |          41 |   0.0114846 |                     8836.53 |                      397.366 |        -1.58306  |         1.27184   |             0 |             0 |            41 |
