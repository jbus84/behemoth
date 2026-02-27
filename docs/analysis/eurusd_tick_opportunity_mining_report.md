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
|         100 |         6 | path_follow  | path_follow__all            | C              |                 95688.6 |            0.0323782   |                      0   |          4.83813 |              0.497126 | True             |
|         100 |         5 | path_follow  | path_follow__all            | C              |                 95688.6 |            0.0215778   |                      0   |          4.42293 |              0.494662 | True             |
|         100 |         4 | path_follow  | path_follow__all            | C              |                 95685.1 |            0.0200212   |                      0   |          3.96718 |              0.495653 | True             |
|         100 |         2 | path_revert  | path_revert__all            | C              |                 95685.1 |            0.0022297   |                      0   |          2.80702 |              0.492297 | True             |
|         100 |         1 | path_follow  | path_follow__all            | C              |                 95685.1 |            0.000972218 |                      0   |          1.98687 |              0.485815 | True             |
|         100 |         3 | path_follow  | path_follow__all            | C              |                 95685.1 |            0.000298902 |                      0   |          3.43388 |              0.492706 | True             |
|         100 |         6 | shock_revert | shock_revert__all           | C              |                 71644   |            0.0235583   |                      0   |          4.881   |              0.497261 | True             |
|         100 |         4 | shock_revert | shock_revert__all           | C              |                 71644   |            0.0159534   |                      0   |          4.01449 |              0.496253 | True             |
|         100 |         5 | shock_revert | shock_revert__all           | C              |                 71644   |            0.00851392  |                      0   |          4.46198 |              0.49544  | True             |
|         100 |         2 | shock_follow | shock_follow__all           | C              |                 71644   |            0.00465478  |                      0   |          2.85293 |              0.492485 | True             |
|         100 |         3 | shock_follow | shock_follow__all           | C              |                 71644   |            0.00334365  |                      0   |          3.4705  |              0.494012 | True             |
|         100 |         1 | shock_revert | shock_revert__all           | C              |                 71644   |            0.00141478  |                      0   |          2.02966 |              0.486419 | True             |
|         100 |         6 | path_follow  | path_follow__high_range_q70 | C              |                 67804.4 |            0.0476326   |                      0   |          5.14607 |              0.499697 | True             |
|         100 |         5 | path_follow  | path_follow__high_range_q70 | C              |                 67804.4 |            0.0325874   |                      0   |          4.70327 |              0.497032 | True             |
|         100 |         4 | path_follow  | path_follow__high_range_q70 | C              |                 67804.4 |            0.0317925   |                      0   |          4.22822 |              0.499134 | True             |
|         100 |         1 | path_follow  | path_follow__high_range_q70 | C              |                 67804.4 |            0.00720957  |                      0   |          2.12423 |              0.488655 | True             |
|         100 |         3 | path_follow  | path_follow__high_range_q70 | C              |                 67804.4 |            0.00629783  |                      0   |          3.66125 |              0.494664 | True             |
|         100 |         2 | path_follow  | path_follow__high_range_q70 | C              |                 67804.4 |            0.00363661  |                      0   |          3.00264 |              0.492829 | True             |
|         100 |         3 | path_follow  | path_follow__low_cost_q30   | C              |                 67353.8 |            0.0864284   |                      0.1 |          3.32292 |              0.503628 | True             |
|         100 |         4 | path_follow  | path_follow__low_cost_q30   | C              |                 67353.8 |            0.061892    |                      0.1 |          3.85004 |              0.505241 | True             |

## OCO Top
|   bar_ticks |   horizon | family                | state_id                          | quality_tier   |   annualized_test_fills |   mean_gross_pips_test |   median_gross_pips_test |   gross_std_test |   hit_rate_gross_test | selection_pass   |
|------------:|----------:|:----------------------|:----------------------------------|:---------------|------------------------:|-----------------------:|-------------------------:|-----------------:|----------------------:|:-----------------|
|         100 |         6 | oco_first_touch       | oco_first_touch__all__k2          | C              |                  227224 |              0.124003  |                      0.1 |          4.36468 |              0.508301 | True             |
|         100 |         5 | oco_first_touch       | oco_first_touch__all__k2          | C              |                  222644 |              0.125107  |                      0.1 |          3.94234 |              0.508938 | True             |
|         100 |         4 | oco_first_touch       | oco_first_touch__all__k2          | C              |                  214501 |              0.131956  |                      0.1 |          3.48338 |              0.509811 | True             |
|         100 |         3 | oco_first_touch       | oco_first_touch__all__k2          | C              |                  199184 |              0.13319   |                      0.1 |          2.97582 |              0.512238 | True             |
|         100 |         6 | oco_first_touch       | oco_first_touch__all__k3          | C              |                  194677 |              0.135391  |                      0.1 |          4.16345 |              0.510418 | True             |
|         100 |         5 | oco_first_touch       | oco_first_touch__all__k3          | C              |                  181352 |              0.135347  |                      0.1 |          3.78509 |              0.511358 | True             |
|         100 |         4 | oco_first_touch_clean | oco_first_touch_clean__all__k2    | B              |                  179967 |              0.968473  |                      0.6 |          2.78025 |              0.596993 | True             |
|         100 |         3 | oco_first_touch_clean | oco_first_touch_clean__all__k2    | B              |                  177749 |              0.662607  |                      0.3 |          2.44591 |              0.568836 | True             |
|         100 |         6 | oco_first_touch_clean | oco_first_touch_clean__all__k3    | B              |                  176130 |              0.816781  |                      0.4 |          3.46837 |              0.560042 | True             |
|         100 |         5 | oco_first_touch_clean | oco_first_touch_clean__all__k2    | A              |                  175745 |              1.28469   |                      0.8 |          3.08676 |              0.625621 | True             |
|         100 |         6 | oco_first_touch_clean | oco_first_touch_clean__all__k2    | A              |                  168977 |              1.61596   |                      1.1 |          3.37351 |              0.652977 | True             |
|         100 |         2 | oco_first_touch       | oco_first_touch__all__k2          | C              |                  168857 |              0.131986  |                      0.1 |          2.4066  |              0.51527  | True             |
|         100 |         5 | oco_first_touch_clean | oco_first_touch_clean__all__k3    | B              |                  168514 |              0.633312  |                      0.3 |          3.20421 |              0.547762 | True             |
|         100 |         4 | oco_first_touch       | oco_first_touch__all__k3          | C              |                  162326 |              0.142132  |                      0.1 |          3.38725 |              0.512943 | True             |
|         100 |         6 | oco_first_touch       | oco_first_touch__low_cost_q30__k2 | C              |                  160530 |              0.0643227 |                      0.1 |          4.2405  |              0.506649 | True             |
|         100 |         2 | oco_first_touch_clean | oco_first_touch_clean__all__k2    | C              |                  159375 |              0.397901  |                      0.2 |          2.05673 |              0.544333 | True             |
|         100 |         5 | oco_first_touch       | oco_first_touch__low_cost_q30__k2 | C              |                  156028 |              0.0579478 |                      0.1 |          3.8299  |              0.506899 | True             |
|         100 |         4 | oco_first_touch_clean | oco_first_touch_clean__all__k3    | B              |                  154448 |              0.479034  |                      0.2 |          2.9258  |              0.537624 | True             |
|         100 |         4 | oco_first_touch       | oco_first_touch__low_cost_q30__k2 | C              |                  148036 |              0.0342051 |                      0.1 |          3.41984 |              0.506538 | True             |
|         100 |         3 | oco_first_touch       | oco_first_touch__all__k3          | C              |                  135461 |              0.143527  |                      0.1 |          2.95825 |              0.515943 | True             |

## Selection Summary
| library     |   rows_total |   rows_pass |   pass_rate |   mean_annualized_fills_all |   mean_annualized_fills_pass |   mean_gross_all |   mean_gross_pass |   tier_a_rows |   tier_b_rows |   tier_c_rows |
|:------------|-------------:|------------:|------------:|----------------------------:|-----------------------------:|-----------------:|------------------:|--------------:|--------------:|--------------:|
| directional |         2088 |         362 |    0.173372 |                     10758.3 |                      26566.4 |        0.0750059 |           0.11125 |             0 |            34 |           328 |
| oco         |         2160 |         737 |    0.341204 |                     12567.5 |                      29530.1 |        2.20345   |           1.19563 |            56 |           252 |           429 |
