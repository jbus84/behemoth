# Tick Opportunity Mining Report

## Setup
- symbol: `EURUSD`
- bar_ticks_grid: `100,1000,2000`
- horizons: `1,2,3,4,5,6`
- train_years: `2022,2023,2024`
- test_year: `2025`
- min_annual_fills: `5000.0`
- inclusion_metric: `mean`

## Directional Top
|   bar_ticks |   horizon | family       | state_id                    | quality_tier   |   annualized_test_fills |   mean_gross_pips_test |   median_gross_pips_test |   gross_std_test |   hit_rate_gross_test | selection_pass   |
|------------:|----------:|:-------------|:----------------------------|:---------------|------------------------:|-----------------------:|-------------------------:|-----------------:|----------------------:|:-----------------|
|         100 |         6 | path_follow  | path_follow__all            | C              |                 94487.7 |            0.0333542   |                      0   |          4.86805 |              0.497393 | True             |
|         100 |         4 | path_follow  | path_follow__all            | C              |                 94487.7 |            0.0247098   |                      0   |          3.99937 |              0.494227 | True             |
|         100 |         5 | path_follow  | path_follow__all            | C              |                 94487.7 |            0.0203637   |                      0   |          4.44513 |              0.493176 | True             |
|         100 |         3 | path_follow  | path_follow__all            | C              |                 94487.7 |            0.00512145  |                      0   |          3.47591 |              0.492443 | True             |
|         100 |         2 | path_follow  | path_follow__all            | C              |                 94487.7 |            0.00272641  |                      0   |          2.83791 |              0.491955 | True             |
|         100 |         1 | path_follow  | path_follow__all            | C              |                 94487.7 |           -0.000405723 |                      0   |          2.00718 |              0.484934 | True             |
|         100 |         6 | path_follow  | path_follow__high_range_q70 | C              |                 71080.8 |            0.0420774   |                      0   |          5.12532 |              0.498059 | True             |
|         100 |         4 | path_follow  | path_follow__high_range_q70 | C              |                 71080.8 |            0.0256124   |                      0   |          4.21617 |              0.494515 | True             |
|         100 |         5 | path_follow  | path_follow__high_range_q70 | C              |                 71080.8 |            0.0235257   |                      0   |          4.685   |              0.494388 | True             |
|         100 |         3 | path_follow  | path_follow__high_range_q70 | C              |                 71080.8 |            0.00681359  |                      0   |          3.6639  |              0.492341 | True             |
|         100 |         2 | path_follow  | path_follow__high_range_q70 | C              |                 71080.8 |            0.00406895  |                      0   |          3.00262 |              0.492341 | True             |
|         100 |         1 | path_follow  | path_follow__high_range_q70 | C              |                 71080.8 |            0.00390094  |                      0   |          2.13668 |              0.486665 | True             |
|         100 |         6 | shock_revert | shock_revert__all           | C              |                 70909.2 |            0.0407569   |                      0   |          4.89122 |              0.498726 | True             |
|         100 |         4 | shock_revert | shock_revert__all           | C              |                 70909.2 |            0.0316242   |                      0   |          4.02598 |              0.495471 | True             |
|         100 |         5 | shock_revert | shock_revert__all           | C              |                 70909.2 |            0.0293725   |                      0   |          4.47313 |              0.494608 | True             |
|         100 |         3 | shock_revert | shock_revert__all           | C              |                 70909.2 |            0.0138611   |                      0   |          3.49245 |              0.492598 | True             |
|         100 |         1 | shock_revert | shock_revert__all           | C              |                 70909.2 |            0.00541765  |                      0   |          2.03794 |              0.48531  | True             |
|         100 |         2 | shock_revert | shock_revert__all           | C              |                 70909.2 |            0.00482606  |                      0   |          2.85712 |              0.492485 | True             |
|         100 |         3 | path_follow  | path_follow__low_cost_q30   | C              |                 68760   |            0.125432    |                      0.1 |          3.30001 |              0.503303 | True             |
|         100 |         2 | path_follow  | path_follow__low_cost_q30   | C              |                 68760   |            0.11372     |                      0.1 |          2.70826 |              0.510925 | True             |

## OCO Top
|   bar_ticks |   horizon | family                | state_id                                                     | quality_tier   |   annualized_test_fills |   mean_gross_pips_test |   median_gross_pips_test |   gross_std_test |   hit_rate_gross_test | selection_pass   |
|------------:|----------:|:----------------------|:-------------------------------------------------------------|:---------------|------------------------:|-----------------------:|-------------------------:|-----------------:|----------------------:|:-----------------|
|         100 |         4 | oco_first_touch_clean | oco_first_touch_clean__all__k2                               | C              |                179051   |               0.132435 |                      0   |          3.57802 |              0.495908 | True             |
|         100 |         5 | oco_first_touch_clean | oco_first_touch_clean__all__k2                               | C              |                174761   |               0.425776 |                      0.2 |          3.87826 |              0.523168 | True             |
|         100 |         6 | oco_first_touch_clean | oco_first_touch_clean__all__k2                               | B              |                168125   |               0.722463 |                      0.5 |          4.13225 |              0.548225 | True             |
|         100 |         5 | oco_first_touch_clean | oco_first_touch_clean__low_cost_q30__k2                      | C              |                133373   |               0.353661 |                      0.3 |          3.64584 |              0.527701 | True             |
|         100 |         6 | oco_first_touch_clean | oco_first_touch_clean__low_cost_q30__k2                      | C              |                130089   |               0.594427 |                      0.4 |          3.98021 |              0.542366 | True             |
|         100 |         6 | oco_first_touch_clean | oco_first_touch_clean__high_range_q70__k3                    | C              |                 85184.6 |               0.254132 |                      0.1 |          4.84347 |              0.501314 | True             |
|         100 |         4 | oco_first_touch_clean | oco_first_touch_clean__high_range_q70__k2                    | C              |                 83537   |               0.31044  |                      0.2 |          3.84679 |              0.514398 | True             |
|         100 |         5 | oco_first_touch_clean | oco_first_touch_clean__high_range_q70__k2                    | B              |                 79561.9 |               0.680325 |                      0.5 |          4.16164 |              0.545523 | True             |
|         100 |         6 | oco_first_touch_clean | oco_first_touch_clean__high_range_q70__k2                    | B              |                 75345.5 |               1.04119  |                      0.8 |          4.43725 |              0.573105 | True             |
|         100 |         4 | oco_first_touch_clean | oco_first_touch_clean__low_cost_q30_and_high_abs_vel_q70__k2 | C              |                 61904.2 |               0.216455 |                      0.2 |          3.45171 |              0.516794 | True             |
|         100 |         5 | oco_first_touch_clean | oco_first_touch_clean__low_cost_q30_and_high_abs_vel_q70__k2 | C              |                 60855.8 |               0.453775 |                      0.4 |          3.7356  |              0.542349 | True             |
|         100 |         6 | oco_first_touch_clean | oco_first_touch_clean__high_range_q80__k3                    | C              |                 59158.8 |               0.357451 |                      0.1 |          5.00885 |              0.508075 | True             |
|         100 |         6 | oco_first_touch_clean | oco_first_touch_clean__low_cost_q30_and_high_abs_vel_q70__k2 | B              |                 59073.7 |               0.724667 |                      0.6 |          3.98435 |              0.557527 | True             |
|         100 |         5 | oco_first_touch_clean | oco_first_touch_clean__high_range_q80__k3                    | C              |                 58400.4 |               0.112234 |                     -0.1 |          4.69037 |              0.488985 | True             |
|         100 |         4 | oco_first_touch_clean | oco_first_touch_clean__high_range_q80__k2                    | C              |                 57291.4 |               0.380216 |                      0.2 |          3.97025 |              0.520329 | True             |
|         100 |         5 | oco_first_touch_clean | oco_first_touch_clean__high_range_q80__k2                    | B              |                 54274.6 |               0.772011 |                      0.6 |          4.28631 |              0.552634 | True             |
|         100 |         6 | oco_first_touch_clean | oco_first_touch_clean__ny_overlap__k3                        | C              |                 51695   |               0.19584  |                      0.1 |          4.60486 |              0.502724 | True             |
|         100 |         4 | oco_first_touch_clean | oco_first_touch_clean__ny_overlap__k2                        | C              |                 51325.2 |               0.273477 |                      0.2 |          3.66827 |              0.513149 | True             |
|         100 |         6 | oco_first_touch_clean | oco_first_touch_clean__high_range_q80__k2                    | B              |                 51195.4 |               1.16558  |                      0.9 |          4.57387 |              0.581028 | True             |
|         100 |         5 | oco_first_touch_clean | oco_first_touch_clean__ny_overlap__k2                        | B              |                 49261.4 |               0.621878 |                      0.5 |          3.97644 |              0.545917 | True             |

## Selection Summary
| library     |   rows_total |   rows_pass |   pass_rate |   mean_annualized_fills_all |   mean_annualized_fills_pass |   mean_gross_all |   mean_gross_pass |   tier_a_rows |   tier_b_rows |   tier_c_rows |
|:------------|-------------:|------------:|------------:|----------------------------:|-----------------------------:|-----------------:|------------------:|--------------:|--------------:|--------------:|
| directional |         2088 |         427 |    0.204502 |                     11086.1 |                     24309.7  |       -0.0851661 |          0.105971 |             0 |            20 |           407 |
| oco         |         2160 |         556 |    0.257407 |                     12729.5 |                      7827.01 |        0.543808  |          3.64659  |             7 |            44 |           505 |
