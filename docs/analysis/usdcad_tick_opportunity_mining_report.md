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
|   bar_ticks |   horizon | family       | state_id                       | quality_tier   |   annualized_test_fills |   mean_gross_pips_test |   median_gross_pips_test |   gross_std_test |   hit_rate_gross_test | selection_pass   |
|------------:|----------:|:-------------|:-------------------------------|:---------------|------------------------:|-----------------------:|-------------------------:|-----------------:|----------------------:|:-----------------|
|         100 |         1 | path_follow  | path_follow__all               | C              |                 90988.1 |              0.0105745 |                      0   |          2.09857 |              0.486319 | True             |
|         100 |         2 | path_follow  | path_follow__all               | C              |                 90987.1 |              0.0302437 |                      0   |          2.85064 |              0.496195 | True             |
|         100 |         3 | path_follow  | path_follow__all               | C              |                 90986.2 |              0.04186   |                      0   |          3.41862 |              0.498097 | True             |
|         100 |         5 | path_follow  | path_follow__all               | C              |                 90985.6 |              0.0619932 |                      0.1 |          4.34952 |              0.50311  | True             |
|         100 |         6 | path_follow  | path_follow__all               | C              |                 90985.6 |              0.0574403 |                      0.1 |          4.73565 |              0.503893 | True             |
|         100 |         4 | path_follow  | path_follow__all               | C              |                 90985.6 |              0.051136  |                      0   |          3.91966 |              0.499283 | True             |
|         100 |         2 | shock_revert | shock_revert__all              | C              |                 68194.7 |              0.0376105 |                      0   |          2.9545  |              0.497373 | True             |
|         100 |         1 | shock_revert | shock_revert__all              | C              |                 68194.7 |              0.0126845 |                      0   |          2.19722 |              0.486528 | True             |
|         100 |         5 | shock_revert | shock_revert__all              | C              |                 68194   |              0.0640483 |                      0.1 |          4.4615  |              0.503157 | True             |
|         100 |         6 | shock_revert | shock_revert__all              | C              |                 68194   |              0.0594629 |                      0.1 |          4.84127 |              0.504599 | True             |
|         100 |         4 | shock_revert | shock_revert__all              | C              |                 68194   |              0.0546288 |                      0.1 |          4.03478 |              0.500478 | True             |
|         100 |         3 | shock_revert | shock_revert__all              | C              |                 68193.7 |              0.0496763 |                      0   |          3.52492 |              0.498646 | True             |
|         100 |         6 | path_follow  | path_follow__high_abs_vel_q70  | C              |                 57211.9 |              0.0819102 |                      0.1 |          5.30826 |              0.506929 | True             |
|         100 |         5 | path_follow  | path_follow__high_abs_vel_q70  | C              |                 57211.9 |              0.0811717 |                      0.1 |          4.8849  |              0.504701 | True             |
|         100 |         4 | path_follow  | path_follow__high_abs_vel_q70  | C              |                 57211.9 |              0.0659972 |                      0.1 |          4.41321 |              0.501982 | True             |
|         100 |         3 | path_follow  | path_follow__high_abs_vel_q70  | C              |                 57210.4 |              0.0563768 |                      0   |          3.84904 |              0.499956 | True             |
|         100 |         2 | path_follow  | path_follow__high_abs_vel_q70  | C              |                 57210.4 |              0.0381032 |                      0   |          3.2225  |              0.497465 | True             |
|         100 |         1 | path_follow  | path_follow__high_abs_vel_q70  | C              |                 57210.4 |              0.0115083 |                      0   |          2.39611 |              0.486555 | True             |
|         100 |         5 | shock_revert | shock_revert__high_abs_vel_q70 | C              |                 51957.4 |              0.0834917 |                      0.1 |          4.82681 |              0.505196 | True             |
|         100 |         6 | shock_revert | shock_revert__high_abs_vel_q70 | C              |                 51957.4 |              0.0798277 |                      0.1 |          5.22497 |              0.507262 | True             |

## OCO Top
|   bar_ticks |   horizon | family                | state_id                                    | quality_tier   |   annualized_test_fills |   mean_gross_pips_test |   median_gross_pips_test |   gross_std_test |   hit_rate_gross_test | selection_pass   |
|------------:|----------:|:----------------------|:--------------------------------------------|:---------------|------------------------:|-----------------------:|-------------------------:|-----------------:|----------------------:|:-----------------|
|         100 |         6 | oco_first_touch_clean | oco_first_touch_clean__ny_overlap__k2       | C              |                48813.5  |             -0.0235953 |                     -0.3 |          4.15824 |              0.462038 | True             |
|         100 |         6 | oco_first_touch_clean | oco_first_touch_clean__high_abs_vel_q70__k2 | C              |                42028.9  |             -0.185537  |                     -0.5 |          4.37851 |              0.439995 | True             |
|         100 |         6 | oco_first_touch_clean | oco_first_touch_clean__high_range_q70__k2   | C              |                35734.6  |              0.0798248 |                     -0.3 |          4.86708 |              0.46307  | True             |
|         100 |         6 | oco_first_touch_clean | oco_first_touch_clean__high_abs_vel_q80__k2 | C              |                26254    |             -0.0957112 |                     -0.4 |          4.56912 |              0.448033 | True             |
|         100 |         6 | oco_first_touch_clean | oco_first_touch_clean__high_range_q80__k2   | C              |                23304.5  |              0.231113  |                     -0.2 |          5.20849 |              0.474076 | True             |
|        1000 |         3 | oco_first_touch_clean | oco_first_touch_clean__all__k5              | C              |                16675.5  |             -0.161745  |                     -0.5 |          9.2506  |              0.469215 | True             |
|        1000 |         6 | oco_first_touch_clean | oco_first_touch_clean__all__k8              | A              |                16584.9  |              0.641626  |                     -0.1 |         13.2673  |              0.496701 | True             |
|        1000 |         5 | oco_first_touch_clean | oco_first_touch_clean__all__k8              | C              |                16192.8  |              0.0316595 |                     -0.5 |         12.5757  |              0.477466 | True             |
|        1000 |         4 | oco_first_touch_clean | oco_first_touch_clean__all__k5              | A              |                16079.5  |              0.79397   |                      0.2 |         10.131   |              0.509863 | True             |
|        1000 |         5 | oco_first_touch_clean | oco_first_touch_clean__all__k5              | A              |                15296.4  |              1.64033   |                      0.9 |         11.1848  |              0.537078 | True             |
|        1000 |         6 | oco_first_touch_clean | oco_first_touch_clean__all__k5              | A              |                14427.5  |              2.66514   |                      1.6 |         12.0173  |              0.568884 | True             |
|        1000 |         3 | oco_first_touch_clean | oco_first_touch_clean__all__k3              | B              |                12999.2  |              0.97324   |                      0.3 |          8.48761 |              0.517217 | True             |
|        1000 |         4 | oco_first_touch_clean | oco_first_touch_clean__all__k3              | B              |                11522.6  |              2.2133    |                      1.3 |          9.45844 |              0.571864 | True             |
|        1000 |         2 | oco_first_touch_clean | oco_first_touch_clean__all__k2              | C              |                11223.4  |             -0.0557871 |                     -0.4 |          7.12056 |              0.467621 | True             |
|        1000 |         5 | oco_first_touch_clean | oco_first_touch_clean__all__k3              | B              |                10400.7  |              3.3535    |                      2.3 |         10.475   |              0.616157 | True             |
|        1000 |         6 | oco_first_touch_clean | oco_first_touch_clean__all__k3              | B              |                 9489.61 |              4.53727   |                      3.2 |         11.2469  |              0.648185 | True             |
|        1000 |         3 | oco_first_touch_clean | oco_first_touch_clean__all__k2              | B              |                 9237.77 |              1.38682   |                      0.6 |          8.2534  |              0.539448 | True             |
|        2000 |         6 | oco_first_touch_clean | oco_first_touch_clean__all__k10             | B              |                 8386.17 |              2.23226   |                      1   |         17.802   |              0.526953 | True             |
|        2000 |         5 | oco_first_touch_clean | oco_first_touch_clean__all__k10             | B              |                 8366.59 |              1.33602   |                      0.3 |         16.3374  |              0.507685 | True             |
|        2000 |         4 | oco_first_touch_clean | oco_first_touch_clean__all__k8              | B              |                 8326.48 |              1.22763   |                      0.3 |         14.6787  |              0.510913 | True             |

## Selection Summary
| library     |   rows_total |   rows_pass |   pass_rate |   mean_annualized_fills_all |   mean_annualized_fills_pass |   mean_gross_all |   mean_gross_pass |   tier_a_rows |   tier_b_rows |   tier_c_rows |
|:------------|-------------:|------------:|------------:|----------------------------:|-----------------------------:|-----------------:|------------------:|--------------:|--------------:|--------------:|
| directional |         2088 |         328 |    0.157088 |                     7491.48 |                     20621.8  |         0.142565 |         0.0726413 |             0 |            18 |           310 |
| oco         |         2160 |         455 |    0.210648 |                     8351.73 |                      2717.67 |        -0.748305 |         2.73781   |             4 |            16 |           435 |
