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
|   bar_ticks |   horizon | family          | state_id                            | quality_tier   |   annualized_test_fills |   mean_gross_pips_test |   median_gross_pips_test |   gross_std_test |   hit_rate_gross_test | selection_pass   |
|------------:|----------:|:----------------|:------------------------------------|:---------------|------------------------:|-----------------------:|-------------------------:|-----------------:|----------------------:|:-----------------|
|         100 |         6 | oco_first_touch | oco_first_touch__all__k0            | D              |                  168467 |               -1.06097 |                     -1.1 |          3.88243 |              0.36653  | False            |
|         100 |         6 | oco_first_touch | oco_first_touch__high_intensity__k0 | D              |                  168467 |               -1.06097 |                     -1.1 |          3.88243 |              0.36653  | False            |
|         100 |         5 | oco_first_touch | oco_first_touch__all__k0            | D              |                  168378 |               -1.06115 |                     -1.1 |          3.55138 |              0.355183 | False            |
|         100 |         5 | oco_first_touch | oco_first_touch__high_intensity__k0 | D              |                  168378 |               -1.06115 |                     -1.1 |          3.55138 |              0.355183 | False            |
|         100 |         4 | oco_first_touch | oco_first_touch__all__k0            | D              |                  168237 |               -1.05285 |                     -1.1 |          3.19174 |              0.342052 | False            |
|         100 |         4 | oco_first_touch | oco_first_touch__high_intensity__k0 | D              |                  168237 |               -1.05285 |                     -1.1 |          3.19174 |              0.342052 | False            |
|         100 |         3 | oco_first_touch | oco_first_touch__all__k0            | D              |                  168046 |               -1.05015 |                     -1.1 |          2.77215 |              0.321734 | False            |
|         100 |         3 | oco_first_touch | oco_first_touch__high_intensity__k0 | D              |                  168046 |               -1.05015 |                     -1.1 |          2.77215 |              0.321734 | False            |
|         100 |         2 | oco_first_touch | oco_first_touch__all__k0            | D              |                  167618 |               -1.0522  |                     -1   |          2.28378 |              0.288575 | False            |
|         100 |         2 | oco_first_touch | oco_first_touch__high_intensity__k0 | D              |                  167618 |               -1.0522  |                     -1   |          2.28378 |              0.288575 | False            |
|         100 |         6 | oco_first_touch | oco_first_touch__all__k1            | D              |                  166541 |               -1.05562 |                     -1.1 |          3.91069 |              0.370319 | False            |
|         100 |         6 | oco_first_touch | oco_first_touch__high_intensity__k1 | D              |                  166541 |               -1.05562 |                     -1.1 |          3.91069 |              0.370319 | False            |
|         100 |         5 | oco_first_touch | oco_first_touch__all__k1            | D              |                  166160 |               -1.0547  |                     -1   |          3.58127 |              0.359157 | False            |
|         100 |         5 | oco_first_touch | oco_first_touch__high_intensity__k1 | D              |                  166160 |               -1.0547  |                     -1   |          3.58127 |              0.359157 | False            |
|         100 |         1 | oco_first_touch | oco_first_touch__all__k0            | D              |                  165942 |               -1.05006 |                     -1   |          1.64791 |              0.221284 | False            |
|         100 |         1 | oco_first_touch | oco_first_touch__high_intensity__k0 | D              |                  165942 |               -1.05006 |                     -1   |          1.64791 |              0.221284 | False            |
|         100 |         4 | oco_first_touch | oco_first_touch__all__k1            | D              |                  165492 |               -1.05175 |                     -1.1 |          3.22691 |              0.345413 | False            |
|         100 |         4 | oco_first_touch | oco_first_touch__high_intensity__k1 | D              |                  165492 |               -1.05175 |                     -1.1 |          3.22691 |              0.345413 | False            |
|         100 |         3 | oco_first_touch | oco_first_touch__all__k1            | D              |                  163982 |               -1.04825 |                     -1   |          2.80658 |              0.326214 | False            |
|         100 |         3 | oco_first_touch | oco_first_touch__high_intensity__k1 | D              |                  163982 |               -1.04825 |                     -1   |          2.80658 |              0.326214 | False            |

## Selection Summary
| library     |   rows_total |   rows_pass |   pass_rate |   mean_annualized_fills_all |   mean_annualized_fills_pass |   mean_gross_all |   mean_gross_pass |   tier_a_rows |   tier_b_rows |   tier_c_rows |
|:------------|-------------:|------------:|------------:|----------------------------:|-----------------------------:|-----------------:|------------------:|--------------:|--------------:|--------------:|
| directional |         2988 |         415 |    0.138889 |                     7435.71 |                      22674.7 |        0.0518825 |         0.0619948 |             0 |            14 |           401 |
| oco         |         2142 |           0 |    0        |                    12763.5  |                        nan   |       -1.21746   |       nan         |             0 |             0 |             0 |
