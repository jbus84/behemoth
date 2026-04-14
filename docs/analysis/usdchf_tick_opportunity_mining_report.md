# Tick Opportunity Mining Report

## Setup
- symbol: `USDCHF`
- bar_ticks_grid: `100,1000,2000`
- horizons: `1,2,3,4,5,6`
- train_years: `2022,2023,2024`
- test_year: `2025`
- min_annual_fills: `5000.0`
- inclusion_metric: `mean`

## Directional Top
|   bar_ticks |   horizon | family       | state_id                      | quality_tier   |   annualized_test_fills |   mean_gross_pips_test |   median_gross_pips_test |   gross_std_test |   hit_rate_gross_test | selection_pass   |
|------------:|----------:|:-------------|:------------------------------|:---------------|------------------------:|-----------------------:|-------------------------:|-----------------:|----------------------:|:-----------------|
|         100 |         6 | path_follow  | path_follow__all              | C              |                 70839.1 |              0.0231183 |                      0   |          4.38283 |              0.499341 | True             |
|         100 |         5 | path_follow  | path_follow__all              | C              |                 70839.1 |              0.0191942 |                      0   |          4.00879 |              0.496961 | True             |
|         100 |         3 | path_follow  | path_follow__all              | C              |                 70835.5 |              0.027035  |                      0   |          3.12608 |              0.496543 | True             |
|         100 |         4 | path_follow  | path_follow__all              | C              |                 70835.5 |              0.0244666 |                      0   |          3.593   |              0.497804 | True             |
|         100 |         2 | path_follow  | path_follow__all              | C              |                 70835.4 |              0.0221912 |                      0   |          2.56579 |              0.495091 | True             |
|         100 |         1 | path_follow  | path_follow__all              | C              |                 70835.4 |              0.0187078 |                      0   |          1.84448 |              0.488873 | True             |
|         100 |         6 | path_follow  | path_follow__high_abs_vel_q70 | C              |                 57404.7 |              0.0278102 |                      0.1 |          4.57754 |              0.500664 | True             |
|         100 |         5 | path_follow  | path_follow__high_abs_vel_q70 | C              |                 57404.7 |              0.0254379 |                      0   |          4.18795 |              0.499056 | True             |
|         100 |         2 | path_follow  | path_follow__high_abs_vel_q70 | C              |                 57402.1 |              0.0277148 |                      0   |          2.68522 |              0.496242 | True             |
|         100 |         1 | path_follow  | path_follow__high_abs_vel_q70 | C              |                 57402.1 |              0.021252  |                      0   |          1.93094 |              0.489896 | True             |
|         100 |         3 | path_follow  | path_follow__high_abs_vel_q70 | C              |                 57401.9 |              0.0341905 |                      0   |          3.26861 |              0.498977 | True             |
|         100 |         4 | path_follow  | path_follow__high_abs_vel_q70 | C              |                 57401.9 |              0.0330647 |                      0.1 |          3.75481 |              0.500184 | True             |
|         100 |         6 | shock_revert | shock_revert__all             | C              |                 52860.6 |              0.0460151 |                      0.1 |          4.44835 |              0.502164 | True             |
|         100 |         5 | shock_revert | shock_revert__all             | C              |                 52860.6 |              0.0391351 |                      0.1 |          4.06726 |              0.500626 | True             |
|         100 |         2 | shock_revert | shock_revert__all             | C              |                 52858.4 |              0.0470955 |                      0   |          2.61666 |              0.499943 | True             |
|         100 |         1 | shock_revert | shock_revert__all             | C              |                 52858.4 |              0.0344236 |                      0   |          1.88813 |              0.49216  | True             |
|         100 |         3 | shock_revert | shock_revert__all             | C              |                 52858.2 |              0.0467186 |                      0.1 |          3.1768  |              0.501357 | True             |
|         100 |         4 | shock_revert | shock_revert__all             | C              |                 52858.2 |              0.0450308 |                      0.1 |          3.64959 |              0.501547 | True             |
|         100 |         6 | path_follow  | path_follow__low_cost_q50     | C              |                 52375.3 |              0.0420562 |                      0   |          4.03703 |              0.499952 | True             |
|         100 |         5 | path_follow  | path_follow__low_cost_q50     | C              |                 52375.3 |              0.0330384 |                      0   |          3.69585 |              0.498186 | True             |

## OCO Top
|   bar_ticks |   horizon | family                | state_id                                                   | quality_tier   |   annualized_test_fills |   mean_gross_pips_test |   median_gross_pips_test |   gross_std_test |   hit_rate_gross_test | selection_pass   |
|------------:|----------:|:----------------------|:-----------------------------------------------------------|:---------------|------------------------:|-----------------------:|-------------------------:|-----------------:|----------------------:|:-----------------|
|         100 |         6 | oco_first_touch_clean | oco_first_touch_clean__high_abs_vel_q70__k2                | C              |                44051.6  |              0.0719575 |                     -0.1 |          3.96812 |              0.478593 | True             |
|         100 |         6 | oco_first_touch_clean | oco_first_touch_clean__ny_overlap__k2                      | C              |                36959.4  |              0.160953  |                     -0.1 |          3.8731  |              0.486612 | True             |
|         100 |         6 | oco_first_touch_clean | oco_first_touch_clean__high_range_q70__k2                  | C              |                34611.5  |              0.245341  |                      0   |          4.33231 |              0.492474 | True             |
|         100 |         6 | oco_first_touch_clean | oco_first_touch_clean__high_abs_vel_q80__k2                | C              |                29961.4  |              0.119455  |                     -0.1 |          4.05909 |              0.483433 | True             |
|         100 |         6 | oco_first_touch_clean | oco_first_touch_clean__high_range_q80__k2                  | C              |                21593.4  |              0.319774  |                      0   |          4.57932 |              0.499954 | True             |
|         100 |         6 | oco_first_touch_clean | oco_first_touch_clean__low_cost_q30_and_high_range_q70__k2 | C              |                16610    |             -0.160683  |                     -0.3 |          3.81311 |              0.46104  | True             |
|        1000 |         6 | oco_first_touch_clean | oco_first_touch_clean__all__k8                             | C              |                12817.2  |              0.97444   |                      0.3 |         12.301   |              0.510343 | True             |
|        1000 |         3 | oco_first_touch_clean | oco_first_touch_clean__all__k5                             | C              |                12626.2  |              0.256346  |                      0   |          8.66228 |              0.496183 | True             |
|        1000 |         4 | oco_first_touch_clean | oco_first_touch_clean__all__k5                             | A              |                11999.6  |              1.19858   |                      0.8 |          9.5388  |              0.532095 | True             |
|        1000 |         5 | oco_first_touch_clean | oco_first_touch_clean__all__k5                             | B              |                11197.9  |              2.27416   |                      1.7 |         10.3173  |              0.570404 | True             |
|        1000 |         6 | oco_first_touch_clean | oco_first_touch_clean__all__k5                             | B              |                10442    |              3.37318   |                      2.5 |         11.0368  |              0.596518 | True             |
|        1000 |         6 | oco_first_touch_clean | oco_first_touch_clean__low_cost_q50__k8                    | C              |                 9652.45 |              0.363264  |                     -0.1 |         11.1233  |              0.493639 | True             |
|        1000 |         3 | oco_first_touch_clean | oco_first_touch_clean__all__k3                             | B              |                 9437.02 |              1.42626   |                      1.1 |          7.91709 |              0.555012 | True             |
|        1000 |         4 | oco_first_touch_clean | oco_first_touch_clean__low_cost_q50__k5                    | B              |                 9169.48 |              0.72531   |                      0.5 |          8.70184 |              0.520909 | True             |
|        1000 |         5 | oco_first_touch_clean | oco_first_touch_clean__low_cost_q50__k5                    | C              |                 8604.4  |              1.71351   |                      1.4 |          9.42995 |              0.562405 | True             |
|        1000 |         4 | oco_first_touch_clean | oco_first_touch_clean__all__k3                             | B              |                 8249.8  |              2.72739   |                      2.1 |          8.86493 |              0.601096 | True             |
|        1000 |         2 | oco_first_touch_clean | oco_first_touch_clean__all__k2                             | C              |                 8103.98 |              0.228922  |                     -0.1 |          6.81519 |              0.492937 | True             |
|        1000 |         6 | oco_first_touch_clean | oco_first_touch_clean__low_cost_q50__k5                    | C              |                 8033.98 |              2.74223   |                      2.3 |         10.0245  |              0.589827 | True             |
|        1000 |         6 | oco_first_touch_clean | oco_first_touch_clean__low_cost_q30__k8                    | C              |                 7702.5  |              0.276573  |                     -0.1 |         10.9558  |              0.491903 | True             |
|        1000 |         5 | oco_first_touch_clean | oco_first_touch_clean__all__k3                             | B              |                 7400.66 |              3.94689   |                      3.1 |          9.62789 |              0.6374   | True             |

## Selection Summary
| library     |   rows_total |   rows_pass |   pass_rate |   mean_annualized_fills_all |   mean_annualized_fills_pass |   mean_gross_all |   mean_gross_pass |   tier_a_rows |   tier_b_rows |   tier_c_rows |
|:------------|-------------:|------------:|------------:|----------------------------:|-----------------------------:|-----------------:|------------------:|--------------:|--------------:|--------------:|
| directional |         2088 |         293 |    0.140326 |                     8285.99 |                     23982.2  |        0.0918751 |         0.0425022 |             0 |            16 |           277 |
| oco         |         2160 |         435 |    0.201389 |                     8608.48 |                      2605.89 |       -0.33251   |         3.65539   |             1 |            12 |           422 |
