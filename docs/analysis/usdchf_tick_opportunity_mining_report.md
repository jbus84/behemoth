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
|   bar_ticks |   horizon | family                | state_id                          | quality_tier   |   annualized_test_fills |   mean_gross_pips_test |   median_gross_pips_test |   gross_std_test |   hit_rate_gross_test | selection_pass   |
|------------:|----------:|:----------------------|:----------------------------------|:---------------|------------------------:|-----------------------:|-------------------------:|-----------------:|----------------------:|:-----------------|
|         100 |         6 | oco_first_touch       | oco_first_touch__all__k2          | C              |                163459   |              0.0742746 |             -2.20268e-13 |          3.853   |              0.49949  | True             |
|         100 |         5 | oco_first_touch       | oco_first_touch__all__k2          | C              |                158924   |              0.0702903 |             -2.20268e-13 |          3.48265 |              0.499678 | True             |
|         100 |         4 | oco_first_touch       | oco_first_touch__all__k2          | C              |                151276   |              0.0767108 |              8.89955e-13 |          3.08073 |              0.501864 | True             |
|         100 |         3 | oco_first_touch       | oco_first_touch__all__k2          | C              |                137939   |              0.0855134 |              8.89955e-13 |          2.64148 |              0.504001 | True             |
|         100 |         6 | oco_first_touch       | oco_first_touch__all__k3          | C              |                132603   |              0.0683952 |              7.79821e-13 |          3.70553 |              0.504673 | True             |
|         100 |         4 | oco_first_touch_clean | oco_first_touch_clean__all__k2    | B              |                131005   |              0.731397  |              0.4         |          2.50214 |              0.571628 | True             |
|         100 |         5 | oco_first_touch_clean | oco_first_touch_clean__all__k2    | A              |                130570   |              0.982327  |              0.6         |          2.77582 |              0.594055 | True             |
|         100 |         6 | oco_first_touch_clean | oco_first_touch_clean__all__k2    | A              |                127474   |              1.25105   |              0.8         |          3.02597 |              0.617871 | True             |
|         100 |         3 | oco_first_touch_clean | oco_first_touch_clean__all__k2    | B              |                125760   |              0.496333  |              0.2         |          2.20855 |              0.548813 | True             |
|         100 |         6 | oco_first_touch_clean | oco_first_touch_clean__all__k3    | B              |                122197   |              0.600501  |              0.3         |          3.12211 |              0.543949 | True             |
|         100 |         5 | oco_first_touch       | oco_first_touch__all__k3          | C              |                121762   |              0.0710553 |              7.79821e-13 |          3.37166 |              0.50546  | True             |
|         100 |         6 | oco_first_touch       | oco_first_touch__low_cost_q50__k2 | C              |                121384   |              0.064796  |              8.89955e-13 |          3.4706  |              0.501454 | True             |
|         100 |         5 | oco_first_touch       | oco_first_touch__low_cost_q50__k2 | C              |                117598   |              0.0615089 |              8.89955e-13 |          3.1321  |              0.501218 | True             |
|         100 |         5 | oco_first_touch_clean | oco_first_touch_clean__all__k3    | B              |                114564   |              0.467221  |              0.2         |          2.88643 |              0.534827 | True             |
|         100 |         2 | oco_first_touch       | oco_first_touch__all__k2          | C              |                113481   |              0.0968821 |              0.1         |          2.14874 |              0.510863 | True             |
|         100 |         4 | oco_first_touch       | oco_first_touch__low_cost_q50__k2 | C              |                111143   |              0.0638983 |              8.89955e-13 |          2.77    |              0.502293 | True             |
|         100 |         2 | oco_first_touch_clean | oco_first_touch_clean__all__k2    | C              |                108273   |              0.303811  |              0.1         |          1.86163 |              0.533524 | True             |
|         100 |         4 | oco_first_touch       | oco_first_touch__all__k3          | C              |                107161   |              0.0818733 |              0.1         |          3.01651 |              0.508835 | True             |
|         100 |         4 | oco_first_touch_clean | oco_first_touch_clean__all__k3    | C              |                102785   |              0.352651  |              0.1         |          2.62676 |              0.528953 | True             |
|         100 |         3 | oco_first_touch       | oco_first_touch__low_cost_q50__k2 | C              |                 99949.9 |              0.0694819 |              8.89955e-13 |          2.3781  |              0.503857 | True             |

## Selection Summary
| library     |   rows_total |   rows_pass |   pass_rate |   mean_annualized_fills_all |   mean_annualized_fills_pass |   mean_gross_all |   mean_gross_pass |   tier_a_rows |   tier_b_rows |   tier_c_rows |
|:------------|-------------:|------------:|------------:|----------------------------:|-----------------------------:|-----------------:|------------------:|--------------:|--------------:|--------------:|
| directional |         2088 |         287 |    0.137452 |                     8293.21 |                      24386.8 |        0.0635043 |         0.0514666 |             0 |            16 |           271 |
| oco         |         2160 |        1481 |    0.685648 |                     8683.53 |                      10828.9 |        1.6661    |         2.56006   |            30 |            82 |          1369 |
