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
|   bar_ticks |   horizon | family                | state_id                          | quality_tier   |   annualized_test_fills |   mean_gross_pips_test |   median_gross_pips_test |   gross_std_test |   hit_rate_gross_test | selection_pass   |
|------------:|----------:|:----------------------|:----------------------------------|:---------------|------------------------:|-----------------------:|-------------------------:|-----------------:|----------------------:|:-----------------|
|         100 |         6 | oco_first_touch       | oco_first_touch__all__k2          | C              |                213713   |              0.113403  |              0.1         |          4.30665 |              0.502975 | True             |
|         100 |         5 | oco_first_touch       | oco_first_touch__all__k2          | C              |                206660   |              0.12552   |              0.1         |          3.91894 |              0.506587 | True             |
|         100 |         4 | oco_first_touch       | oco_first_touch__all__k2          | C              |                195387   |              0.129781  |              0.1         |          3.50192 |              0.508246 | True             |
|         100 |         3 | oco_first_touch       | oco_first_touch__all__k2          | C              |                177033   |              0.138418  |              0.1         |          3.05178 |              0.511411 | True             |
|         100 |         6 | oco_first_touch       | oco_first_touch__all__k3          | C              |                171292   |              0.122833  |              0.1         |          4.29382 |              0.505712 | True             |
|         100 |         5 | oco_first_touch_clean | oco_first_touch_clean__all__k2    | A              |                170362   |              1.04674   |              0.6         |          2.9753  |              0.598222 | True             |
|         100 |         4 | oco_first_touch_clean | oco_first_touch_clean__all__k2    | B              |                169074   |              0.810525  |              0.4         |          2.70609 |              0.577372 | True             |
|         100 |         6 | oco_first_touch_clean | oco_first_touch_clean__all__k2    | A              |                168145   |              1.27852   |              0.7         |          3.22859 |              0.615387 | True             |
|         100 |         3 | oco_first_touch_clean | oco_first_touch_clean__all__k2    | B              |                160709   |              0.590009  |              0.3         |          2.43081 |              0.55814  | True             |
|         100 |         6 | oco_first_touch_clean | oco_first_touch_clean__all__k3    | B              |                157067   |              0.702829  |              0.3         |          3.41083 |              0.546177 | True             |
|         100 |         5 | oco_first_touch       | oco_first_touch__all__k3          | C              |                156965   |              0.138865  |              0.1         |          3.95271 |              0.507809 | True             |
|         100 |         5 | oco_first_touch_clean | oco_first_touch_clean__all__k3    | B              |                146895   |              0.580814  |              0.2         |          3.17969 |              0.538635 | True             |
|         100 |         2 | oco_first_touch       | oco_first_touch__all__k2          | C              |                144921   |              0.150174  |              0.1         |          2.55473 |              0.517408 | True             |
|         100 |         4 | oco_first_touch       | oco_first_touch__all__k3          | C              |                138000   |              0.152484  |              0.1         |          3.59152 |              0.511093 | True             |
|         100 |         2 | oco_first_touch_clean | oco_first_touch_clean__all__k2    | C              |                137549   |              0.401299  |              0.2         |          2.06785 |              0.542712 | True             |
|         100 |         4 | oco_first_touch_clean | oco_first_touch_clean__all__k3    | B              |                131620   |              0.469423  |              0.2         |          2.93505 |              0.533001 | True             |
|         100 |         3 | oco_first_touch       | oco_first_touch__all__k3          | C              |                112555   |              0.170312  |              0.1         |          3.2249  |              0.517216 | True             |
|         100 |         3 | oco_first_touch_clean | oco_first_touch_clean__all__k3    | C              |                109069   |              0.384866  |              0.1         |          2.67893 |              0.531848 | True             |
|         100 |         6 | oco_first_touch       | oco_first_touch__low_cost_q50__k2 | C              |                 86997.8 |              0.0670834 |              2.00018e-12 |          3.48564 |              0.500081 | True             |
|         100 |         6 | oco_first_touch       | oco_first_touch__all__k5          | C              |                 86330.2 |              0.143228  |              0.1         |          4.80536 |              0.505481 | True             |

## Selection Summary
| library     |   rows_total |   rows_pass |   pass_rate |   mean_annualized_fills_all |   mean_annualized_fills_pass |   mean_gross_all |   mean_gross_pass |   tier_a_rows |   tier_b_rows |   tier_c_rows |
|:------------|-------------:|------------:|------------:|----------------------------:|-----------------------------:|-----------------:|------------------:|--------------:|--------------:|--------------:|
| directional |         2088 |         328 |    0.157088 |                     7491.48 |                      20621.8 |         0.142565 |         0.0726413 |             0 |            18 |           310 |
| oco         |         2160 |        1483 |    0.686574 |                     8402.29 |                      10493.9 |         1.7541   |         2.68522   |            43 |            99 |          1341 |
