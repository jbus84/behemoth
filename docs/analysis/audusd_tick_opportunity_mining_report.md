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
|         100 |         6 | oco_first_touch       | oco_first_touch__all__k2                | C              |                  154467 |              0.05657   |             -2.20268e-13 |          3.47559 |              0.498925 | True             |
|         100 |         5 | oco_first_touch       | oco_first_touch__all__k2                | C              |                  148846 |              0.0652793 |              8.89955e-13 |          3.13723 |              0.500405 | True             |
|         100 |         4 | oco_first_touch       | oco_first_touch__all__k2                | C              |                  139803 |              0.0739539 |              8.89955e-13 |          2.77254 |              0.501805 | True             |
|         100 |         6 | oco_first_touch       | oco_first_touch__low_cost_q50__k2       | C              |                  137250 |              0.0353517 |             -2.20268e-13 |          3.25324 |              0.497357 | True             |
|         100 |         5 | oco_first_touch       | oco_first_touch__low_cost_q50__k2       | C              |                  131914 |              0.0426928 |             -2.20268e-13 |          2.9311  |              0.498517 | True             |
|         100 |         5 | oco_first_touch_clean | oco_first_touch_clean__all__k2          | B              |                  128169 |              0.7445    |              0.4         |          2.55726 |              0.573732 | True             |
|         100 |         6 | oco_first_touch_clean | oco_first_touch_clean__all__k2          | A              |                  127045 |              0.963093  |              0.6         |          2.7731  |              0.594519 | True             |
|         100 |         4 | oco_first_touch_clean | oco_first_touch_clean__all__k2          | B              |                  125995 |              0.53909   |              0.3         |          2.31709 |              0.552685 | True             |
|         100 |         3 | oco_first_touch       | oco_first_touch__all__k2                | C              |                  124971 |              0.0789525 |              8.89955e-13 |          2.37374 |              0.503341 | True             |
|         100 |         4 | oco_first_touch       | oco_first_touch__low_cost_q50__k2       | C              |                  123367 |              0.0536614 |              8.89955e-13 |          2.5849  |              0.500439 | True             |
|         100 |         6 | oco_first_touch       | oco_first_touch__all__k3                | C              |                  119295 |              0.0651956 |              7.79821e-13 |          3.33654 |              0.501485 | True             |
|         100 |         3 | oco_first_touch_clean | oco_first_touch_clean__all__k2          | C              |                  117471 |              0.354112  |              0.2         |          2.04912 |              0.533622 | True             |
|         100 |         6 | oco_first_touch       | oco_first_touch__low_cost_q30__k2       | C              |                  115592 |              0.0296392 |             -2.20268e-13 |          3.12946 |              0.496832 | True             |
|         100 |         5 | oco_first_touch_clean | oco_first_touch_clean__low_cost_q50__k2 | B              |                  115198 |              0.646806  |              0.3         |          2.40849 |              0.565207 | True             |
|         100 |         6 | oco_first_touch_clean | oco_first_touch_clean__low_cost_q50__k2 | A              |                  114640 |              0.852691  |              0.5         |          2.61761 |              0.58586  | True             |
|         100 |         6 | oco_first_touch_clean | oco_first_touch_clean__all__k3          | B              |                  113082 |              0.415961  |              0.2         |          2.89672 |              0.527282 | True             |
|         100 |         4 | oco_first_touch_clean | oco_first_touch_clean__low_cost_q50__k2 | B              |                  112497 |              0.458896  |              0.2         |          2.18163 |              0.545697 | True             |
|         100 |         5 | oco_first_touch       | oco_first_touch__low_cost_q30__k2       | C              |                  110726 |              0.0380563 |             -2.20268e-13 |          2.82146 |              0.498308 | True             |
|         100 |         3 | oco_first_touch       | oco_first_touch__low_cost_q50__k2       | C              |                  109480 |              0.0609779 |              8.89955e-13 |          2.20592 |              0.50231  | True             |
|         100 |         5 | oco_first_touch       | oco_first_touch__all__k3                | C              |                  107594 |              0.0784308 |              7.79821e-13 |          3.04014 |              0.503741 | True             |

## Selection Summary
| library     |   rows_total |   rows_pass |   pass_rate |   mean_annualized_fills_all |   mean_annualized_fills_pass |   mean_gross_all |   mean_gross_pass |   tier_a_rows |   tier_b_rows |   tier_c_rows |
|:------------|-------------:|------------:|------------:|----------------------------:|-----------------------------:|-----------------:|------------------:|--------------:|--------------:|--------------:|
| directional |         2088 |         309 |    0.147989 |                     8039.46 |                     22797.3  |         0.103316 |         0.0494254 |             0 |             6 |           303 |
| oco         |         2160 |        1689 |    0.781944 |                     8139.9  |                      9258.53 |         1.62251  |         2.08392   |            24 |            80 |          1585 |
