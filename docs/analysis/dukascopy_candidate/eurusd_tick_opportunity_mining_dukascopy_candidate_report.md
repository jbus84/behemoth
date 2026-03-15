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
|         100 |         6 | path_follow  | path_follow__all            | C              |                 94589.1 |             0.0308655  |                      0   |          4.85209 |              0.49721  | True             |
|         100 |         4 | path_follow  | path_follow__all            | C              |                 94589.1 |             0.0280232  |                      0   |          3.97899 |              0.494876 | True             |
|         100 |         5 | path_follow  | path_follow__all            | C              |                 94589.1 |             0.0249549  |                      0   |          4.43633 |              0.493666 | True             |
|         100 |         3 | path_follow  | path_follow__all            | C              |                 94589.1 |             0.00962293 |                      0   |          3.45626 |              0.492319 | True             |
|         100 |         2 | path_follow  | path_follow__all            | C              |                 94589.1 |             0.00335689 |                      0   |          2.83184 |              0.49147  | True             |
|         100 |         1 | path_follow  | path_follow__all            | C              |                 94582.3 |            -0.00161371 |                      0   |          2.00462 |              0.486499 | True             |
|         100 |         3 | path_follow  | path_follow__low_cost_q30   | C              |                 71375.5 |             0.11792    |                      0.1 |          3.24071 |              0.507213 | True             |
|         100 |         2 | path_follow  | path_follow__low_cost_q30   | C              |                 71375.5 |             0.103392   |                      0.1 |          2.68467 |              0.512275 | True             |
|         100 |         4 | path_follow  | path_follow__low_cost_q30   | C              |                 71375.5 |             0.090205   |                      0.1 |          3.6894  |              0.501898 | True             |
|         100 |         5 | path_follow  | path_follow__low_cost_q30   | C              |                 71375.5 |             0.0445457  |                      0   |          4.13685 |              0.498355 | True             |
|         100 |         6 | path_follow  | path_follow__low_cost_q30   | C              |                 71375.5 |             0.0351303  |                      0   |          4.52501 |              0.499873 | True             |
|         100 |         1 | path_follow  | path_follow__low_cost_q30   | C              |                 71375.5 |             0.0295115  |                      0   |          1.84205 |              0.49633  | True             |
|         100 |         6 | path_follow  | path_follow__high_range_q70 | C              |                 71050.7 |             0.0418975  |                      0   |          5.11949 |              0.49858  | True             |
|         100 |         4 | path_follow  | path_follow__high_range_q70 | C              |                 71050.7 |             0.0297292  |                      0   |          4.21032 |              0.495304 | True             |
|         100 |         5 | path_follow  | path_follow__high_range_q70 | C              |                 71050.7 |             0.0272094  |                      0   |          4.68326 |              0.494555 | True             |
|         100 |         3 | path_follow  | path_follow__high_range_q70 | C              |                 71050.7 |             0.0145511  |                      0   |          3.66388 |              0.493227 | True             |
|         100 |         2 | path_follow  | path_follow__high_range_q70 | C              |                 71050.7 |             0.00734897 |                      0   |          3.01091 |              0.492366 | True             |
|         100 |         1 | path_follow  | path_follow__high_range_q70 | C              |                 71050.7 |             0.0048673  |                      0   |          2.13948 |              0.489258 | True             |
|         100 |         6 | shock_revert | shock_revert__all           | C              |                 70775.7 |             0.0450082  |                      0   |          4.90958 |              0.499752 | True             |
|         100 |         4 | shock_revert | shock_revert__all           | C              |                 70775.7 |             0.0354257  |                      0   |          4.02305 |              0.496448 | True             |

## OCO Top
|   bar_ticks |   horizon | family                | state_id                          | quality_tier   |   annualized_test_fills |   mean_gross_pips_test |   median_gross_pips_test |   gross_std_test |   hit_rate_gross_test | selection_pass   |
|------------:|----------:|:----------------------|:----------------------------------|:---------------|------------------------:|-----------------------:|-------------------------:|-----------------:|----------------------:|:-----------------|
|         100 |         6 | oco_first_touch       | oco_first_touch__all__k2          | C              |                  227217 |              0.121586  |                      0.1 |          4.36959 |              0.507994 | True             |
|         100 |         5 | oco_first_touch       | oco_first_touch__all__k2          | C              |                  222638 |              0.125724  |                      0.1 |          3.94479 |              0.509153 | True             |
|         100 |         4 | oco_first_touch       | oco_first_touch__all__k2          | C              |                  214432 |              0.132258  |                      0.1 |          3.4861  |              0.510521 | True             |
|         100 |         3 | oco_first_touch       | oco_first_touch__all__k2          | C              |                  199194 |              0.135009  |                      0.1 |          2.97612 |              0.512777 | True             |
|         100 |         6 | oco_first_touch       | oco_first_touch__all__k3          | C              |                  194940 |              0.131099  |                      0.1 |          4.16741 |              0.509359 | True             |
|         100 |         5 | oco_first_touch       | oco_first_touch__all__k3          | C              |                  181463 |              0.135636  |                      0.1 |          3.78661 |              0.511077 | True             |
|         100 |         4 | oco_first_touch_clean | oco_first_touch_clean__all__k2    | B              |                  179933 |              0.969007  |                      0.6 |          2.78432 |              0.597611 | True             |
|         100 |         3 | oco_first_touch_clean | oco_first_touch_clean__all__k2    | B              |                  177774 |              0.663188  |                      0.3 |          2.46033 |              0.569537 | True             |
|         100 |         6 | oco_first_touch_clean | oco_first_touch_clean__all__k3    | B              |                  176271 |              0.816338  |                      0.4 |          3.46968 |              0.559122 | True             |
|         100 |         5 | oco_first_touch_clean | oco_first_touch_clean__all__k2    | B              |                  175628 |              1.28808   |                      0.8 |          3.09155 |              0.626156 | True             |
|         100 |         6 | oco_first_touch       | oco_first_touch__low_cost_q30__k2 | C              |                  171774 |              0.0857413 |                      0.1 |          4.24254 |              0.508833 | True             |
|         100 |         6 | oco_first_touch_clean | oco_first_touch_clean__all__k2    | A              |                  169041 |              1.61379   |                      1.1 |          3.37671 |              0.652027 | True             |
|         100 |         2 | oco_first_touch       | oco_first_touch__all__k2          | C              |                  168922 |              0.139304  |                      0.1 |          2.40135 |              0.516794 | True             |
|         100 |         5 | oco_first_touch_clean | oco_first_touch_clean__all__k3    | B              |                  168540 |              0.635033  |                      0.3 |          3.21077 |              0.547597 | True             |
|         100 |         5 | oco_first_touch       | oco_first_touch__low_cost_q30__k2 | C              |                  167095 |              0.0687169 |                      0.1 |          3.83053 |              0.509891 | True             |
|         100 |         4 | oco_first_touch       | oco_first_touch__all__k3          | C              |                  162601 |              0.142148  |                      0.1 |          3.38576 |              0.512298 | True             |
|         100 |         2 | oco_first_touch_clean | oco_first_touch_clean__all__k2    | C              |                  159523 |              0.400954  |                      0.2 |          2.05625 |              0.545663 | True             |
|         100 |         4 | oco_first_touch       | oco_first_touch__low_cost_q30__k2 | C              |                  159166 |              0.06532   |                      0.1 |          3.39712 |              0.506241 | True             |
|         100 |         4 | oco_first_touch_clean | oco_first_touch_clean__all__k3    | C              |                  154720 |              0.477535  |                      0.2 |          2.93179 |              0.536817 | True             |
|         100 |         3 | oco_first_touch       | oco_first_touch__low_cost_q30__k2 | C              |                  144246 |              0.104195  |                      0.1 |          2.94331 |              0.513023 | True             |

## Selection Summary
| library     |   rows_total |   rows_pass |   pass_rate |   mean_annualized_fills_all |   mean_annualized_fills_pass |   mean_gross_all |   mean_gross_pass |   tier_a_rows |   tier_b_rows |   tier_c_rows |
|:------------|-------------:|------------:|------------:|----------------------------:|-----------------------------:|-----------------:|------------------:|--------------:|--------------:|--------------:|
| directional |         2088 |         414 |    0.198276 |                     11256.4 |                      24926.3 |        -0.162666 |           0.16649 |             0 |            24 |           390 |
| oco         |         2160 |        1697 |    0.785648 |                     13014.9 |                      14939   |         2.20712  |           2.90498 |            30 |           109 |          1558 |
