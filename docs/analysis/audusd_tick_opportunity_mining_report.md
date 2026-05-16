# Tick Opportunity Mining Report

## Setup
- symbol: `AUDUSD`
- bar_ticks_grid: `100,1000,2000,5000,10000`
- horizons: `1,2,3,4,5,6`
- train_years: `2022,2023,2024`
- test_year: `2025`
- min_annual_fills: `5000.0`
- inclusion_metric: `mean`

## Directional Top
|   bar_ticks |   horizon | family      | state_id                      | quality_tier   |   annualized_test_fills |   mean_gross_pips_test |   median_gross_pips_test |   gross_std_test |   hit_rate_gross_test | selection_pass   |
|------------:|----------:|:------------|:------------------------------|:---------------|------------------------:|-----------------------:|-------------------------:|-----------------:|----------------------:|:-----------------|
|         100 |         6 | path_follow | path_follow__all              | C              |                 66236.2 |             0.021686   |                        0 |          3.98046 |              0.497629 | True             |
|         100 |         6 | path_follow | path_follow__high_intensity   | C              |                 66236.2 |             0.021686   |                        0 |          3.98046 |              0.497629 | True             |
|         100 |         5 | path_follow | path_follow__all              | C              |                 66236.2 |             0.018374   |                        0 |          3.65084 |              0.497099 | True             |
|         100 |         5 | path_follow | path_follow__high_intensity   | C              |                 66236.2 |             0.018374   |                        0 |          3.65084 |              0.497099 | True             |
|         100 |         4 | path_follow | path_follow__all              | C              |                 66236.2 |             0.0172316  |                        0 |          3.27873 |              0.496235 | True             |
|         100 |         4 | path_follow | path_follow__high_intensity   | C              |                 66236.2 |             0.0172316  |                        0 |          3.27873 |              0.496235 | True             |
|         100 |         2 | path_follow | path_follow__all              | C              |                 66236.2 |             0.00797261 |                        0 |          2.33619 |              0.491977 | True             |
|         100 |         2 | path_follow | path_follow__high_intensity   | C              |                 66236.2 |             0.00797261 |                        0 |          2.33619 |              0.491977 | True             |
|         100 |         3 | path_follow | path_follow__all              | C              |                 66236.2 |             0.00667717 |                        0 |          2.85748 |              0.494811 | True             |
|         100 |         3 | path_follow | path_follow__high_intensity   | C              |                 66236.2 |             0.00667717 |                        0 |          2.85748 |              0.494811 | True             |
|         100 |         1 | path_follow | path_follow__all              | C              |                 66236.2 |             0.00286359 |                        0 |          1.68425 |              0.486993 | True             |
|         100 |         1 | path_follow | path_follow__high_intensity   | C              |                 66236.2 |             0.00286359 |                        0 |          1.68425 |              0.486993 | True             |
|         100 |         6 | path_follow | path_follow__low_cost_q50     | C              |                 58450.5 |             0.0319335  |                        0 |          3.81683 |              0.498601 | True             |
|         100 |         4 | path_follow | path_follow__low_cost_q50     | C              |                 58450.5 |             0.0300946  |                        0 |          3.13496 |              0.497382 | True             |
|         100 |         5 | path_follow | path_follow__low_cost_q50     | C              |                 58450.5 |             0.02988    |                        0 |          3.49715 |              0.49836  | True             |
|         100 |         3 | path_follow | path_follow__low_cost_q50     | C              |                 58450.5 |             0.0155727  |                        0 |          2.72907 |              0.49515  | True             |
|         100 |         2 | path_follow | path_follow__low_cost_q50     | C              |                 58450.5 |             0.0111859  |                        0 |          2.23565 |              0.491527 | True             |
|         100 |         1 | path_follow | path_follow__low_cost_q50     | C              |                 58450.5 |             0.00874096 |                        0 |          1.59818 |              0.486822 | True             |
|         100 |         6 | path_follow | path_follow__high_abs_vel_q70 | C              |                 50440.8 |             0.0213574  |                        0 |          4.15369 |              0.498597 | True             |
|         100 |         5 | path_follow | path_follow__high_abs_vel_q70 | C              |                 50440.8 |             0.0183629  |                        0 |          3.80178 |              0.497403 | True             |

## OCO Top
|   bar_ticks |   horizon | family          | state_id                              | quality_tier   |   annualized_test_fills |   mean_gross_pips_test |   median_gross_pips_test |   gross_std_test |   hit_rate_gross_test | selection_pass   |
|------------:|----------:|:----------------|:--------------------------------------|:---------------|------------------------:|-----------------------:|-------------------------:|-----------------:|----------------------:|:-----------------|
|       10000 |         5 | oco_first_touch | oco_first_touch__all__k5              | C              |                1681.7   |              -0.930691 |                    -1.3  |          33.2957 |              0.483483 | True             |
|       10000 |         5 | oco_first_touch | oco_first_touch__high_intensity__k5   | C              |                1681.7   |              -0.930691 |                    -1.3  |          33.2957 |              0.483483 | True             |
|       10000 |         4 | oco_first_touch | oco_first_touch__all__k5              | C              |                1679.68  |              -1.03538  |                    -0.9  |          30.0849 |              0.487087 | True             |
|       10000 |         4 | oco_first_touch | oco_first_touch__high_intensity__k5   | C              |                1679.68  |              -1.03538  |                    -0.9  |          30.0849 |              0.487087 | True             |
|       10000 |         4 | oco_first_touch | oco_first_touch__low_cost_q50__k5     | C              |                1564.67  |              -0.980658 |                    -0.8  |          30.1207 |              0.490006 | True             |
|       10000 |         4 | oco_first_touch | oco_first_touch__low_cost_q30__k3     | C              |                1397.21  |              -0.166209 |                     0.8  |          30.1485 |              0.508303 | True             |
|       10000 |         3 | oco_first_touch | oco_first_touch__low_cost_q30__k5     | C              |                1396.21  |              -0.915657 |                    -1.1  |          26.3967 |              0.484127 | True             |
|       10000 |         4 | oco_first_touch | oco_first_touch__low_cost_q30__k5     | C              |                1396.2   |              -0.862645 |                    -0.5  |          30.1268 |              0.492775 | True             |
|       10000 |         5 | oco_first_touch | oco_first_touch__low_cost_q30__k5     | C              |                1395.86  |              -0.444356 |                    -0.85 |          33.4359 |              0.48987  | True             |
|       10000 |         4 | oco_first_touch | oco_first_touch__low_cost_q30__k8     | C              |                1391.16  |              -1.07426  |                    -0.8  |          30.3472 |              0.489485 | True             |
|       10000 |         4 | oco_first_touch | oco_first_touch__low_cost_q30__k10    | C              |                1389.14  |              -0.948511 |                    -1.4  |          30.3433 |              0.48366  | True             |
|       10000 |         3 | oco_first_touch | oco_first_touch__low_cost_q30__k8     | C              |                1388.15  |              -1.25929  |                    -1.2  |          26.4937 |              0.484035 | True             |
|       10000 |         5 | oco_first_touch | oco_first_touch__high_activity__k2    | C              |                 550.682 |              -0.522099 |                    -0.8  |          33.6976 |              0.493554 | True             |
|       10000 |         6 | oco_first_touch | oco_first_touch__high_activity__k2    | C              |                 550.682 |              -1.2116   |                    -1.3  |          36.5466 |              0.484346 | True             |
|       10000 |         4 | oco_first_touch | oco_first_touch__high_activity__k5    | C              |                 547.64  |              -0.179259 |                     2.2  |          30.196  |              0.52037  | True             |
|       10000 |         5 | oco_first_touch | oco_first_touch__high_activity__k5    | C              |                 547.64  |              -0.262407 |                     0.5  |          33.8007 |              0.505556 | True             |
|       10000 |         6 | oco_first_touch | oco_first_touch__high_abs_vel_q70__k2 | C              |                 541.922 |               2.15914  |                     2.35 |          41.3248 |              0.527985 | True             |
|       10000 |         5 | oco_first_touch | oco_first_touch__high_abs_vel_q70__k2 | C              |                 541.922 |               2.03806  |                     2.2  |          36.8623 |              0.529851 | True             |
|       10000 |         4 | oco_first_touch | oco_first_touch__high_abs_vel_q70__k2 | C              |                 541.922 |               1.63937  |                     2.05 |          33.1547 |              0.526119 | True             |
|       10000 |         5 | oco_first_touch | oco_first_touch__high_abs_vel_q70__k1 | C              |                 541.922 |               0.566045 |                     1.1  |          36.9499 |              0.518657 | True             |

## Selection Summary
| library     |   rows_total |   rows_pass |   pass_rate |   mean_annualized_fills_all |   mean_annualized_fills_pass |   mean_gross_all |   mean_gross_pass |   tier_a_rows |   tier_b_rows |   tier_c_rows |
|:------------|-------------:|------------:|------------:|----------------------------:|-----------------------------:|-----------------:|------------------:|--------------:|--------------:|--------------:|
| directional |         4962 |         415 |   0.0836356 |                     4603.05 |                    22674.7   |        -0.119071 |         0.0619948 |             0 |            14 |           401 |
| oco         |         3570 |         118 |   0.0330532 |                     8040.51 |                      542.409 |        -0.923852 |        -0.218029  |             0 |             0 |           118 |
