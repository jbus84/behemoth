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
|   bar_ticks |   horizon | family                | state_id                          | quality_tier   |   annualized_test_fills |   mean_gross_pips_test |   median_gross_pips_test |   gross_std_test |   hit_rate_gross_test | selection_pass   |
|------------:|----------:|:----------------------|:----------------------------------|:---------------|------------------------:|-----------------------:|-------------------------:|-----------------:|----------------------:|:-----------------|
|         100 |         6 | oco_first_touch       | oco_first_touch__all__k2          | C              |                  227200 |              0.12092   |                      0.1 |          4.36942 |              0.508108 | True             |
|         100 |         5 | oco_first_touch       | oco_first_touch__all__k2          | C              |                  222554 |              0.123482  |                      0.1 |          3.94602 |              0.508991 | True             |
|         100 |         4 | oco_first_touch       | oco_first_touch__all__k2          | C              |                  214499 |              0.132482  |                      0.1 |          3.48392 |              0.510113 | True             |
|         100 |         3 | oco_first_touch       | oco_first_touch__all__k2          | C              |                  199178 |              0.133849  |                      0.1 |          2.97616 |              0.511916 | True             |
|         100 |         6 | oco_first_touch       | oco_first_touch__all__k3          | C              |                  194764 |              0.133198  |                      0.1 |          4.16765 |              0.510063 | True             |
|         100 |         5 | oco_first_touch       | oco_first_touch__all__k3          | C              |                  181312 |              0.13716   |                      0.1 |          3.78671 |              0.511419 | True             |
|         100 |         4 | oco_first_touch_clean | oco_first_touch_clean__all__k2    | B              |                  180039 |              0.966854  |                      0.6 |          2.78345 |              0.596977 | True             |
|         100 |         3 | oco_first_touch_clean | oco_first_touch_clean__all__k2    | B              |                  177756 |              0.66182   |                      0.3 |          2.45976 |              0.568598 | True             |
|         100 |         6 | oco_first_touch_clean | oco_first_touch_clean__all__k3    | B              |                  176154 |              0.818938  |                      0.4 |          3.47234 |              0.559888 | True             |
|         100 |         5 | oco_first_touch_clean | oco_first_touch_clean__all__k2    | B              |                  175588 |              1.2855    |                      0.8 |          3.08069 |              0.626116 | True             |
|         100 |         2 | oco_first_touch       | oco_first_touch__all__k2          | C              |                  168991 |              0.139814  |                      0.1 |          2.39965 |              0.516137 | True             |
|         100 |         6 | oco_first_touch_clean | oco_first_touch_clean__all__k2    | A              |                  168952 |              1.61355   |                      1.1 |          3.36737 |              0.652264 | True             |
|         100 |         5 | oco_first_touch_clean | oco_first_touch_clean__all__k3    | B              |                  168421 |              0.636736  |                      0.3 |          3.21397 |              0.548006 | True             |
|         100 |         6 | oco_first_touch       | oco_first_touch__low_cost_q30__k2 | C              |                  164327 |              0.102392  |                      0.1 |          4.24605 |              0.508451 | True             |
|         100 |         4 | oco_first_touch       | oco_first_touch__all__k3          | C              |                  162573 |              0.143838  |                      0.1 |          3.38293 |              0.511942 | True             |
|         100 |         5 | oco_first_touch       | oco_first_touch__low_cost_q30__k2 | C              |                  159663 |              0.0918162 |                      0.1 |          3.82856 |              0.51116  | True             |
|         100 |         2 | oco_first_touch_clean | oco_first_touch_clean__all__k2    | C              |                  159599 |              0.400163  |                      0.2 |          2.05666 |              0.544811 | True             |
|         100 |         4 | oco_first_touch_clean | oco_first_touch_clean__all__k3    | C              |                  154728 |              0.477617  |                      0.2 |          2.9353  |              0.53627  | True             |
|         100 |         4 | oco_first_touch       | oco_first_touch__low_cost_q30__k2 | C              |                  152274 |              0.0793163 |                      0.1 |          3.38785 |              0.506137 | True             |
|         100 |         3 | oco_first_touch       | oco_first_touch__low_cost_q30__k2 | C              |                  138352 |              0.104419  |                      0.1 |          2.93739 |              0.510354 | True             |

## Selection Summary
| library     |   rows_total |   rows_pass |   pass_rate |   mean_annualized_fills_all |   mean_annualized_fills_pass |   mean_gross_all |   mean_gross_pass |   tier_a_rows |   tier_b_rows |   tier_c_rows |
|:------------|-------------:|------------:|------------:|----------------------------:|-----------------------------:|-----------------:|------------------:|--------------:|--------------:|--------------:|
| directional |         2088 |         427 |    0.204502 |                     11083.8 |                      24309.3 |      -0.00997117 |         0.0667092 |             0 |            24 |           403 |
| oco         |         2160 |        1790 |    0.828704 |                     12674.2 |                      14106   |       2.12895    |         2.6611    |            30 |           125 |          1635 |
