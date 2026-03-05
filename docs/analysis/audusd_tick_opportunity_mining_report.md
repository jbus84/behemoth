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
|   bar_ticks |   horizon | family       | state_id                      | quality_tier   |   annualized_test_fills |   mean_gross_pips_test |   median_gross_pips_test |   gross_std_test |   hit_rate_gross_test | selection_pass   |
|------------:|----------:|:-------------|:------------------------------|:---------------|------------------------:|-----------------------:|-------------------------:|-----------------:|----------------------:|:-----------------|
|         100 |         6 | path_follow  | path_follow__all              | C              |                 67162.6 |             0.020717   |                        0 |          3.98136 |              0.498244 | True             |
|         100 |         4 | path_follow  | path_follow__all              | C              |                 67162.6 |             0.0146591  |                        0 |          3.27989 |              0.496317 | True             |
|         100 |         5 | path_follow  | path_follow__all              | C              |                 67162.6 |             0.0145067  |                        0 |          3.64785 |              0.496391 | True             |
|         100 |         3 | path_follow  | path_follow__all              | C              |                 67162.6 |             0.00853693 |                        0 |          2.84568 |              0.495061 | True             |
|         100 |         2 | path_follow  | path_follow__all              | C              |                 67162.6 |             0.00748644 |                        0 |          2.34189 |              0.49158  | True             |
|         100 |         1 | path_follow  | path_follow__all              | C              |                 67162.6 |             0.00334872 |                        0 |          1.68419 |              0.48768  | True             |
|         100 |         6 | path_follow  | path_follow__low_cost_q50     | C              |                 59155.8 |             0.0297694  |                        0 |          3.82756 |              0.499313 | True             |
|         100 |         4 | path_follow  | path_follow__low_cost_q50     | C              |                 59155.8 |             0.0281034  |                        0 |          3.14261 |              0.498024 | True             |
|         100 |         5 | path_follow  | path_follow__low_cost_q50     | C              |                 59155.8 |             0.0256298  |                        0 |          3.50116 |              0.497498 | True             |
|         100 |         3 | path_follow  | path_follow__low_cost_q50     | C              |                 59155.8 |             0.0183364  |                        0 |          2.72356 |              0.496259 | True             |
|         100 |         2 | path_follow  | path_follow__low_cost_q50     | C              |                 59155.8 |             0.00996386 |                        0 |          2.24082 |              0.490677 | True             |
|         100 |         1 | path_follow  | path_follow__low_cost_q50     | C              |                 59155.8 |             0.0087135  |                        0 |          1.60033 |              0.48798  | True             |
|         100 |         6 | path_follow  | path_follow__high_abs_vel_q70 | C              |                 50605   |             0.0275668  |                        0 |          4.15854 |              0.499375 | True             |
|         100 |         5 | path_follow  | path_follow__high_abs_vel_q70 | C              |                 50605   |             0.0166253  |                        0 |          3.81484 |              0.496936 | True             |
|         100 |         4 | path_follow  | path_follow__high_abs_vel_q70 | C              |                 50605   |             0.0111774  |                        0 |          3.43147 |              0.496956 | True             |
|         100 |         2 | path_follow  | path_follow__high_abs_vel_q70 | C              |                 50605   |             0.00465066 |                        0 |          2.45769 |              0.492513 | True             |
|         100 |         3 | path_follow  | path_follow__high_abs_vel_q70 | C              |                 50605   |             0.00398033 |                        0 |          2.98356 |              0.494278 | True             |
|         100 |         1 | path_follow  | path_follow__high_abs_vel_q70 | C              |                 50605   |            -0.00149138 |                        0 |          1.76384 |              0.489142 | True             |
|         100 |         6 | shock_revert | shock_revert__all             | C              |                 50343.1 |             0.0266437  |                        0 |          4.03272 |              0.499242 | True             |
|         100 |         5 | shock_revert | shock_revert__all             | C              |                 50343.1 |             0.0214246  |                        0 |          3.70459 |              0.497349 | True             |

## OCO Top
|   bar_ticks |   horizon | family                | state_id                                | quality_tier   |   annualized_test_fills |   mean_gross_pips_test |   median_gross_pips_test |   gross_std_test |   hit_rate_gross_test | selection_pass   |
|------------:|----------:|:----------------------|:----------------------------------------|:---------------|------------------------:|-----------------------:|-------------------------:|-----------------:|----------------------:|:-----------------|
|         100 |         6 | oco_first_touch       | oco_first_touch__all__k2                | C              |                  154531 |              0.0595546 |             -2.20268e-13 |          3.47395 |              0.499107 | True             |
|         100 |         5 | oco_first_touch       | oco_first_touch__all__k2                | C              |                  148948 |              0.0651381 |              8.89955e-13 |          3.1367  |              0.500236 | True             |
|         100 |         4 | oco_first_touch       | oco_first_touch__all__k2                | C              |                  139919 |              0.0732727 |              8.89955e-13 |          2.77238 |              0.50179  | True             |
|         100 |         6 | oco_first_touch       | oco_first_touch__low_cost_q50__k2       | C              |                  137050 |              0.036372  |             -2.20268e-13 |          3.25356 |              0.497049 | True             |
|         100 |         5 | oco_first_touch       | oco_first_touch__low_cost_q50__k2       | C              |                  131766 |              0.0414443 |             -2.20268e-13 |          2.93173 |              0.498001 | True             |
|         100 |         5 | oco_first_touch_clean | oco_first_touch_clean__all__k2          | B              |                  128266 |              0.744033  |              0.4         |          2.55864 |              0.573672 | True             |
|         100 |         6 | oco_first_touch_clean | oco_first_touch_clean__all__k2          | A              |                  127152 |              0.962463  |              0.6         |          2.77475 |              0.594467 | True             |
|         100 |         4 | oco_first_touch_clean | oco_first_touch_clean__all__k2          | B              |                  126104 |              0.538509  |              0.3         |          2.31776 |              0.552712 | True             |
|         100 |         3 | oco_first_touch       | oco_first_touch__all__k2                | C              |                  124960 |              0.0782247 |              8.89955e-13 |          2.37601 |              0.504268 | True             |
|         100 |         4 | oco_first_touch       | oco_first_touch__low_cost_q50__k2       | C              |                  123225 |              0.0533896 |              8.89955e-13 |          2.58511 |              0.500147 | True             |
|         100 |         6 | oco_first_touch       | oco_first_touch__all__k3                | C              |                  119382 |              0.0632973 |              7.79821e-13 |          3.33772 |              0.501455 | True             |
|         100 |         3 | oco_first_touch_clean | oco_first_touch_clean__all__k2          | C              |                  117416 |              0.354683  |              0.2         |          2.05085 |              0.534761 | True             |
|         100 |         5 | oco_first_touch_clean | oco_first_touch_clean__low_cost_q50__k2 | B              |                  115105 |              0.645385  |              0.3         |          2.41089 |              0.564745 | True             |
|         100 |         6 | oco_first_touch_clean | oco_first_touch_clean__low_cost_q50__k2 | A              |                  114568 |              0.850713  |              0.5         |          2.62153 |              0.585231 | True             |
|         100 |         6 | oco_first_touch_clean | oco_first_touch_clean__all__k3          | B              |                  113172 |              0.413775  |              0.2         |          2.90013 |              0.527313 | True             |
|         100 |         6 | oco_first_touch       | oco_first_touch__low_cost_q30__k2       | C              |                  112867 |              0.0357907 |             -2.20268e-13 |          3.12902 |              0.496813 | True             |
|         100 |         4 | oco_first_touch_clean | oco_first_touch_clean__low_cost_q50__k2 | B              |                  112411 |              0.4576    |              0.2         |          2.18417 |              0.545268 | True             |
|         100 |         3 | oco_first_touch       | oco_first_touch__low_cost_q50__k2       | C              |                  109244 |              0.06028   |              8.89955e-13 |          2.20914 |              0.502972 | True             |
|         100 |         5 | oco_first_touch       | oco_first_touch__low_cost_q30__k2       | C              |                  108114 |              0.0422633 |             -2.20268e-13 |          2.81843 |              0.497895 | True             |
|         100 |         5 | oco_first_touch       | oco_first_touch__all__k3                | C              |                  107647 |              0.0756637 |              7.79821e-13 |          3.0423  |              0.503231 | True             |

## Selection Summary
| library     |   rows_total |   rows_pass |   pass_rate |   mean_annualized_fills_all |   mean_annualized_fills_pass |   mean_gross_all |   mean_gross_pass |   tier_a_rows |   tier_b_rows |   tier_c_rows |
|:------------|-------------:|------------:|------------:|----------------------------:|-----------------------------:|-----------------:|------------------:|--------------:|--------------:|--------------:|
| directional |         2088 |         317 |    0.15182  |                     8099.84 |                     22675    |         0.101082 |         0.0463529 |             0 |             4 |           313 |
| oco         |         2160 |        1672 |    0.774074 |                     8131.08 |                      9337.75 |         1.58702  |         2.1009    |            25 |            86 |          1561 |
