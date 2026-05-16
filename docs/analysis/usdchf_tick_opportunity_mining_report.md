# Tick Opportunity Mining Report

## Setup
- symbol: `USDCHF`
- bar_ticks_grid: `100,1000,2000,5000,10000`
- horizons: `1,2,3,4,5,6`
- train_years: `2022,2023,2024`
- test_year: `2025`
- min_annual_fills: `5000.0`
- inclusion_metric: `mean`

## Directional Top
|   bar_ticks |   horizon | family       | state_id                      | quality_tier   |   annualized_test_fills |   mean_gross_pips_test |   median_gross_pips_test |   gross_std_test |   hit_rate_gross_test | selection_pass   |
|------------:|----------:|:-------------|:------------------------------|:---------------|------------------------:|-----------------------:|-------------------------:|-----------------:|----------------------:|:-----------------|
|         100 |         6 | path_follow  | path_follow__all              | C              |                 70839.1 |              0.0231183 |                      0   |          4.38283 |              0.499341 | True             |
|         100 |         6 | path_follow  | path_follow__high_intensity   | C              |                 70839.1 |              0.0231183 |                      0   |          4.38283 |              0.499341 | True             |
|         100 |         5 | path_follow  | path_follow__all              | C              |                 70839.1 |              0.0191942 |                      0   |          4.00879 |              0.496961 | True             |
|         100 |         5 | path_follow  | path_follow__high_intensity   | C              |                 70839.1 |              0.0191942 |                      0   |          4.00879 |              0.496961 | True             |
|         100 |         3 | path_follow  | path_follow__all              | C              |                 70835.5 |              0.027035  |                      0   |          3.12608 |              0.496543 | True             |
|         100 |         3 | path_follow  | path_follow__high_intensity   | C              |                 70835.5 |              0.027035  |                      0   |          3.12608 |              0.496543 | True             |
|         100 |         4 | path_follow  | path_follow__all              | C              |                 70835.5 |              0.0244666 |                      0   |          3.593   |              0.497804 | True             |
|         100 |         4 | path_follow  | path_follow__high_intensity   | C              |                 70835.5 |              0.0244666 |                      0   |          3.593   |              0.497804 | True             |
|         100 |         2 | path_follow  | path_follow__all              | C              |                 70835.4 |              0.0221912 |                      0   |          2.56579 |              0.495091 | True             |
|         100 |         2 | path_follow  | path_follow__high_intensity   | C              |                 70835.4 |              0.0221912 |                      0   |          2.56579 |              0.495091 | True             |
|         100 |         1 | path_follow  | path_follow__all              | C              |                 70835.4 |              0.0187078 |                      0   |          1.84448 |              0.488873 | True             |
|         100 |         1 | path_follow  | path_follow__high_intensity   | C              |                 70835.4 |              0.0187078 |                      0   |          1.84448 |              0.488873 | True             |
|         100 |         6 | path_follow  | path_follow__high_abs_vel_q70 | C              |                 57404.7 |              0.0278102 |                      0.1 |          4.57754 |              0.500664 | True             |
|         100 |         5 | path_follow  | path_follow__high_abs_vel_q70 | C              |                 57404.7 |              0.0254379 |                      0   |          4.18795 |              0.499056 | True             |
|         100 |         2 | path_follow  | path_follow__high_abs_vel_q70 | C              |                 57402.1 |              0.0277148 |                      0   |          2.68522 |              0.496242 | True             |
|         100 |         1 | path_follow  | path_follow__high_abs_vel_q70 | C              |                 57402.1 |              0.021252  |                      0   |          1.93094 |              0.489896 | True             |
|         100 |         3 | path_follow  | path_follow__high_abs_vel_q70 | C              |                 57401.9 |              0.0341905 |                      0   |          3.26861 |              0.498977 | True             |
|         100 |         4 | path_follow  | path_follow__high_abs_vel_q70 | C              |                 57401.9 |              0.0330647 |                      0.1 |          3.75481 |              0.500184 | True             |
|         100 |         6 | shock_revert | shock_revert__all             | C              |                 52860.6 |              0.0460151 |                      0.1 |          4.44835 |              0.502164 | True             |
|         100 |         6 | shock_revert | shock_revert__high_intensity  | C              |                 52860.6 |              0.0460151 |                      0.1 |          4.44835 |              0.502164 | True             |

## OCO Top
|   bar_ticks |   horizon | family          | state_id                                               | quality_tier   |   annualized_test_fills |   mean_gross_pips_test |   median_gross_pips_test |   gross_std_test |   hit_rate_gross_test | selection_pass   |
|------------:|----------:|:----------------|:-------------------------------------------------------|:---------------|------------------------:|-----------------------:|-------------------------:|-----------------:|----------------------:|:-----------------|
|       10000 |         4 | oco_first_touch | oco_first_touch__low_cost_q50__k1                      | C              |                1235.33  |              0.533933  |                     1.4  |          33.5164 |              0.524121 | True             |
|       10000 |         4 | oco_first_touch | oco_first_touch__low_cost_q50__k2                      | C              |                1235.33  |              0.193949  |                     1.3  |          33.5382 |              0.524939 | True             |
|       10000 |         4 | oco_first_touch | oco_first_touch__low_cost_q30__k1                      | C              |                1225.23  |              0.477246  |                     1.2  |          33.5404 |              0.523495 | True             |
|       10000 |         4 | oco_first_touch | oco_first_touch__low_cost_q30__k2                      | C              |                1225.23  |              0.0178071 |                     1.2  |          33.566  |              0.522671 | True             |
|       10000 |         4 | oco_first_touch | oco_first_touch__low_cost_q30__k0                      | C              |                1225.23  |             -0.514427  |                     0.9  |          33.5598 |              0.515251 | True             |
|        5000 |         4 | oco_first_touch | oco_first_touch__low_cost_q30_and_high_abs_vel_q70__k3 | C              |                 697.113 |             -0.652168  |                    -1.6  |          22.4259 |              0.465318 | True             |
|        5000 |         6 | oco_first_touch | oco_first_touch__low_cost_q30_and_high_abs_vel_q70__k3 | C              |                 696.465 |             -1.33029   |                    -0.5  |          27.3536 |              0.484058 | True             |
|        5000 |         5 | oco_first_touch | oco_first_touch__low_cost_q30_and_high_abs_vel_q70__k3 | C              |                 696.223 |             -0.786686  |                    -1.5  |          24.9188 |              0.468886 | True             |
|        5000 |         5 | oco_first_touch | oco_first_touch__low_cost_q30_and_high_abs_vel_q70__k5 | C              |                 696.223 |             -1.00984   |                    -1.5  |          24.9323 |              0.470333 | True             |
|       10000 |         5 | oco_first_touch | oco_first_touch__high_vol_cluster__k2                  | C              |                 534.992 |              0.539238  |                    -0.1  |          39.4674 |              0.499048 | True             |
|       10000 |         4 | oco_first_touch | oco_first_touch__high_vol_cluster__k2                  | C              |                 532.647 |              0.410247  |                     2.2  |          34.9557 |              0.533207 | True             |
|       10000 |         4 | oco_first_touch | oco_first_touch__high_vol_cluster__k3                  | C              |                 532.647 |             -0.533207  |                     1.2  |          35.0043 |              0.514231 | True             |
|       10000 |         6 | oco_first_touch | oco_first_touch__high_activity__k5                     | C              |                 531.535 |              1.96622   |                     0.5  |          39.5431 |              0.506718 | True             |
|       10000 |         6 | oco_first_touch | oco_first_touch__high_activity__k1                     | C              |                 531.535 |             -0.465067  |                     0.1  |          39.5229 |              0.50096  | True             |
|       10000 |         4 | oco_first_touch | oco_first_touch__high_activity__k2                     | C              |                 529.276 |              1.60631   |                     2.4  |          32.9933 |              0.543021 | True             |
|       10000 |         4 | oco_first_touch | oco_first_touch__high_activity__k1                     | C              |                 529.276 |              0.470363  |                     1.4  |          33.0655 |              0.521989 | True             |
|       10000 |         4 | oco_first_touch | oco_first_touch__high_activity__k0                     | C              |                 529.276 |              0.445124  |                     2.1  |          33.0521 |              0.533461 | True             |
|       10000 |         5 | oco_first_touch | oco_first_touch__high_activity__k2                     | C              |                 528.538 |              1.32854   |                     0.65 |          36.3926 |              0.517241 | True             |
|       10000 |         5 | oco_first_touch | oco_first_touch__high_activity__k1                     | C              |                 528.538 |              0.377778  |                     0.05 |          36.451  |              0.5      | True             |
|       10000 |         5 | oco_first_touch | oco_first_touch__high_activity__k0                     | C              |                 528.538 |             -0.172031  |                     0.3  |          36.4681 |              0.503831 | True             |

## Selection Summary
| library     |   rows_total |   rows_pass |   pass_rate |   mean_annualized_fills_all |   mean_annualized_fills_pass |   mean_gross_all |   mean_gross_pass |   tier_a_rows |   tier_b_rows |   tier_c_rows |
|:------------|-------------:|------------:|------------:|----------------------------:|-----------------------------:|-----------------:|------------------:|--------------:|--------------:|--------------:|
| directional |         4968 |         389 |  0.0783011  |                     4780.33 |                    24386.1   |        0.0954871 |         0.0425829 |             0 |            22 |           367 |
| oco         |         3570 |          30 |  0.00840336 |                     8330.61 |                      649.127 |       -0.999814  |         0.156359  |             0 |             0 |            30 |
