# Tick Opportunity Mining Report

## Setup
- symbol: `AUDUSD`
- bar_ticks_grid: `100,1000,2000`
- horizons: `1,2,3,4,5,6`
- train_years: `2022,2023,2024`
- test_year: `2025`
- min_annual_fills: `5000.0`
- inclusion_metric: `mean`

## Directional Top
|   bar_ticks |   horizon | family      | state_id                      | quality_tier   |   annualized_test_fills |   mean_gross_pips_test |   median_gross_pips_test |   gross_std_test |   hit_rate_gross_test | selection_pass   |
|------------:|----------:|:------------|:------------------------------|:---------------|------------------------:|-----------------------:|-------------------------:|-----------------:|----------------------:|:-----------------|
|         100 |         6 | path_follow | path_follow__all              | C              |                 66236.2 |             0.021686   |                        0 |          3.98046 |              0.497629 | True             |
|         100 |         5 | path_follow | path_follow__all              | C              |                 66236.2 |             0.018374   |                        0 |          3.65084 |              0.497099 | True             |
|         100 |         4 | path_follow | path_follow__all              | C              |                 66236.2 |             0.0172316  |                        0 |          3.27873 |              0.496235 | True             |
|         100 |         2 | path_follow | path_follow__all              | C              |                 66236.2 |             0.00797261 |                        0 |          2.33619 |              0.491977 | True             |
|         100 |         3 | path_follow | path_follow__all              | C              |                 66236.2 |             0.00667717 |                        0 |          2.85748 |              0.494811 | True             |
|         100 |         1 | path_follow | path_follow__all              | C              |                 66236.2 |             0.00286359 |                        0 |          1.68425 |              0.486993 | True             |
|         100 |         6 | path_follow | path_follow__low_cost_q50     | C              |                 58450.5 |             0.0319335  |                        0 |          3.81683 |              0.498601 | True             |
|         100 |         4 | path_follow | path_follow__low_cost_q50     | C              |                 58450.5 |             0.0300946  |                        0 |          3.13496 |              0.497382 | True             |
|         100 |         5 | path_follow | path_follow__low_cost_q50     | C              |                 58450.5 |             0.02988    |                        0 |          3.49715 |              0.49836  | True             |
|         100 |         3 | path_follow | path_follow__low_cost_q50     | C              |                 58450.5 |             0.0155727  |                        0 |          2.72907 |              0.49515  | True             |
|         100 |         2 | path_follow | path_follow__low_cost_q50     | C              |                 58450.5 |             0.0111859  |                        0 |          2.23565 |              0.491527 | True             |
|         100 |         1 | path_follow | path_follow__low_cost_q50     | C              |                 58450.5 |             0.00874096 |                        0 |          1.59818 |              0.486822 | True             |
|         100 |         6 | path_follow | path_follow__high_abs_vel_q70 | C              |                 50440.8 |             0.0213574  |                        0 |          4.15369 |              0.498597 | True             |
|         100 |         5 | path_follow | path_follow__high_abs_vel_q70 | C              |                 50440.8 |             0.0183629  |                        0 |          3.80178 |              0.497403 | True             |
|         100 |         4 | path_follow | path_follow__high_abs_vel_q70 | C              |                 50440.8 |             0.012732   |                        0 |          3.41233 |              0.496329 | True             |
|         100 |         2 | path_follow | path_follow__high_abs_vel_q70 | C              |                 50440.8 |             0.00779363 |                        0 |          2.44424 |              0.49227  | True             |
|         100 |         3 | path_follow | path_follow__high_abs_vel_q70 | C              |                 50440.8 |             0.00727034 |                        0 |          2.9666  |              0.494658 | True             |
|         100 |         1 | path_follow | path_follow__high_abs_vel_q70 | C              |                 50440.8 |             0.00307607 |                        0 |          1.75666 |              0.488669 | True             |
|         100 |         6 | path_follow | path_follow__low_cost_q30     | C              |                 49747.8 |             0.0469859  |                        0 |          3.68735 |              0.499142 | True             |
|         100 |         5 | path_follow | path_follow__low_cost_q30     | C              |                 49747.8 |             0.0416382  |                        0 |          3.38572 |              0.497789 | True             |

## OCO Top
|   bar_ticks |   horizon | family                | state_id                                | quality_tier   |   annualized_test_fills |   mean_gross_pips_test |   median_gross_pips_test |   gross_std_test |   hit_rate_gross_test | selection_pass   |
|------------:|----------:|:----------------------|:----------------------------------------|:---------------|------------------------:|-----------------------:|-------------------------:|-----------------:|----------------------:|:-----------------|
|        1000 |         6 | oco_first_touch_clean | oco_first_touch_clean__all__k8          | C              |                12606.4  |              0.0222514 |                     -0.2 |         11.2007  |              0.489085 | True             |
|        1000 |         4 | oco_first_touch_clean | oco_first_touch_clean__all__k5          | B              |                12216.2  |              0.681325  |                      0.5 |          8.79981 |              0.518001 | True             |
|        1000 |         5 | oco_first_touch_clean | oco_first_touch_clean__all__k5          | A              |                11514.4  |              1.54699   |                      1.1 |          9.53568 |              0.546572 | True             |
|        1000 |         6 | oco_first_touch_clean | oco_first_touch_clean__low_cost_q50__k8 | B              |                11248.6  |             -0.22842   |                     -0.4 |         10.9025  |              0.478214 | True             |
|        1000 |         4 | oco_first_touch_clean | oco_first_touch_clean__low_cost_q50__k5 | B              |                11047.4  |              0.495664  |                      0.2 |          8.6553  |              0.508544 | True             |
|        1000 |         6 | oco_first_touch_clean | oco_first_touch_clean__all__k5          | A              |                10789.8  |              2.51034   |                      2.1 |         10.2191  |              0.582092 | True             |
|        1000 |         5 | oco_first_touch_clean | oco_first_touch_clean__low_cost_q50__k5 | B              |                10436.9  |              1.34763   |                      0.9 |          9.36711 |              0.538054 | True             |
|        1000 |         6 | oco_first_touch_clean | oco_first_touch_clean__low_cost_q30__k8 | C              |                10153.8  |             -0.446884  |                     -0.6 |         10.674   |              0.473393 | True             |
|        1000 |         4 | oco_first_touch_clean | oco_first_touch_clean__low_cost_q30__k5 | C              |                10064.4  |              0.368453  |                      0.2 |          8.49279 |              0.50434  | True             |
|        1000 |         6 | oco_first_touch_clean | oco_first_touch_clean__low_cost_q50__k5 | B              |                 9796.57 |              2.29323   |                      1.9 |          9.96901 |              0.573655 | True             |
|        1000 |         3 | oco_first_touch_clean | oco_first_touch_clean__all__k3          | B              |                 9769.7  |              1.16195   |                      0.8 |          7.43507 |              0.547688 | True             |
|        1000 |         5 | oco_first_touch_clean | oco_first_touch_clean__low_cost_q30__k5 | C              |                 9526.02 |              1.17577   |                      0.8 |          9.17924 |              0.534261 | True             |
|        1000 |         6 | oco_first_touch_clean | oco_first_touch_clean__low_cost_q30__k5 | C              |                 8939.94 |              2.07979   |                      1.7 |          9.74668 |              0.569086 | True             |
|        1000 |         3 | oco_first_touch_clean | oco_first_touch_clean__low_cost_q50__k3 | C              |                 8864.02 |              1.07821   |                      0.8 |          7.23482 |              0.545877 | True             |
|        1000 |         4 | oco_first_touch_clean | oco_first_touch_clean__all__k3          | B              |                 8558.19 |              2.41592   |                      1.9 |          8.08143 |              0.597208 | True             |
|        1000 |         2 | oco_first_touch_clean | oco_first_touch_clean__all__k2          | C              |                 8383.65 |              0.162472  |                     -0.1 |          6.34241 |              0.489881 | True             |
|        1000 |         3 | oco_first_touch_clean | oco_first_touch_clean__low_cost_q30__k3 | C              |                 8102.93 |              1.01482   |                      0.8 |          7.08608 |              0.544362 | True             |
|        1000 |         4 | oco_first_touch_clean | oco_first_touch_clean__low_cost_q50__k3 | C              |                 7738.82 |              2.32125   |                      1.8 |          7.94154 |              0.595692 | True             |
|        1000 |         5 | oco_first_touch_clean | oco_first_touch_clean__all__k3          | B              |                 7692.32 |              3.61501   |                      2.9 |          8.76885 |              0.640731 | True             |
|        1000 |         2 | oco_first_touch_clean | oco_first_touch_clean__low_cost_q50__k2 | C              |                 7561.45 |              0.144145  |                     -0.1 |          6.12236 |              0.491237 | True             |

## Selection Summary
| library     |   rows_total |   rows_pass |   pass_rate |   mean_annualized_fills_all |   mean_annualized_fills_pass |   mean_gross_all |   mean_gross_pass |   tier_a_rows |   tier_b_rows |   tier_c_rows |
|:------------|-------------:|------------:|------------:|----------------------------:|-----------------------------:|-----------------:|------------------:|--------------:|--------------:|--------------:|
| directional |         2088 |         315 |    0.150862 |                     8047.24 |                     22424.3  |        0.0886358 |         0.0522503 |             0 |             8 |           307 |
| oco         |         2160 |         429 |    0.198611 |                     8157.39 |                      2391.01 |       -0.403107  |         2.98069   |             2 |            17 |           410 |
