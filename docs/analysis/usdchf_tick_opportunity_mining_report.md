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
|         100 |         6 | path_follow  | path_follow__all              | C              |                 71356.8 |              0.035576  |                      0.1 |          4.40043 |              0.502074 | True             |
|         100 |         5 | path_follow  | path_follow__all              | C              |                 71356.8 |              0.0244659 |                      0.1 |          4.01523 |              0.500218 | True             |
|         100 |         2 | path_follow  | path_follow__all              | C              |                 71356.2 |              0.0199002 |                      0   |          2.54774 |              0.494755 | True             |
|         100 |         1 | path_follow  | path_follow__all              | C              |                 71356.2 |              0.017705  |                      0   |          1.84378 |              0.489256 | True             |
|         100 |         3 | path_follow  | path_follow__all              | C              |                 71355.5 |              0.0183113 |                      0   |          3.11299 |              0.496519 | True             |
|         100 |         4 | path_follow  | path_follow__all              | C              |                 71355.1 |              0.0275243 |                      0   |          3.60633 |              0.498298 | True             |
|         100 |         6 | path_follow  | path_follow__high_abs_vel_q70 | C              |                 57272.5 |              0.036277  |                      0.1 |          4.58683 |              0.502821 | True             |
|         100 |         5 | path_follow  | path_follow__high_abs_vel_q70 | C              |                 57272.5 |              0.0246426 |                      0.1 |          4.18379 |              0.501507 | True             |
|         100 |         2 | path_follow  | path_follow__high_abs_vel_q70 | C              |                 57271.8 |              0.0183814 |                      0   |          2.66112 |              0.494796 | True             |
|         100 |         1 | path_follow  | path_follow__high_abs_vel_q70 | C              |                 57271.8 |              0.0155184 |                      0   |          1.92966 |              0.490206 | True             |
|         100 |         3 | path_follow  | path_follow__high_abs_vel_q70 | C              |                 57271.8 |              0.0153257 |                      0   |          3.24802 |              0.496303 | True             |
|         100 |         4 | path_follow  | path_follow__high_abs_vel_q70 | C              |                 57271.3 |              0.0269322 |                      0   |          3.75846 |              0.499816 | True             |
|         100 |         6 | shock_revert | shock_revert__all             | C              |                 53445.1 |              0.0521875 |                      0.1 |          4.47159 |              0.503737 | True             |
|         100 |         5 | shock_revert | shock_revert__all             | C              |                 53445.1 |              0.0378629 |                      0.1 |          4.06976 |              0.503079 | True             |
|         100 |         2 | shock_revert | shock_revert__all             | C              |                 53444.6 |              0.0284491 |                      0   |          2.59983 |              0.496414 | True             |
|         100 |         3 | shock_revert | shock_revert__all             | C              |                 53444.6 |              0.0271949 |                      0   |          3.17117 |              0.497033 | True             |
|         100 |         1 | shock_revert | shock_revert__all             | C              |                 53444.6 |              0.0264363 |                      0   |          1.88997 |              0.490312 | True             |
|         100 |         4 | shock_revert | shock_revert__all             | C              |                 53444.1 |              0.037419  |                      0.1 |          3.66036 |              0.500685 | True             |
|         100 |         2 | path_follow  | path_follow__low_cost_q50     | C              |                 52417.6 |              0.0288975 |                      0   |          2.36977 |              0.495407 | True             |
|         100 |         1 | path_follow  | path_follow__low_cost_q50     | C              |                 52417.6 |              0.0229388 |                      0   |          1.71989 |              0.489442 | True             |

## OCO Top
|   bar_ticks |   horizon | family                | state_id                                | quality_tier   |   annualized_test_fills |   mean_gross_pips_test |   median_gross_pips_test |   gross_std_test |   hit_rate_gross_test | selection_pass   |
|------------:|----------:|:----------------------|:----------------------------------------|:---------------|------------------------:|-----------------------:|-------------------------:|-----------------:|----------------------:|:-----------------|
|         100 |         6 | oco_first_touch       | oco_first_touch__all__k2                | C              |                163436   |              0.0775729 |              8.89955e-13 |          3.85589 |              0.500114 | True             |
|         100 |         5 | oco_first_touch       | oco_first_touch__all__k2                | C              |                158826   |              0.0734725 |              8.89955e-13 |          3.48775 |              0.500411 | True             |
|         100 |         4 | oco_first_touch       | oco_first_touch__all__k2                | C              |                151073   |              0.0842742 |              8.89955e-13 |          3.08256 |              0.503796 | True             |
|         100 |         3 | oco_first_touch       | oco_first_touch__all__k2                | C              |                137695   |              0.0861039 |              0.1         |          2.6449  |              0.505313 | True             |
|         100 |         6 | oco_first_touch       | oco_first_touch__all__k3                | C              |                132752   |              0.073765  |              7.79821e-13 |          3.70346 |              0.504577 | True             |
|         100 |         4 | oco_first_touch_clean | oco_first_touch_clean__all__k2          | B              |                130868   |              0.735728  |              0.4         |          2.511   |              0.573093 | True             |
|         100 |         5 | oco_first_touch_clean | oco_first_touch_clean__all__k2          | A              |                130624   |              0.982476  |              0.6         |          2.78482 |              0.593926 | True             |
|         100 |         6 | oco_first_touch_clean | oco_first_touch_clean__all__k2          | A              |                127733   |              1.24751   |              0.8         |          3.03128 |              0.617468 | True             |
|         100 |         3 | oco_first_touch_clean | oco_first_touch_clean__all__k2          | B              |                125500   |              0.497735  |              0.2         |          2.22006 |              0.55016  | True             |
|         100 |         6 | oco_first_touch_clean | oco_first_touch_clean__all__k3          | B              |                122410   |              0.602762  |              0.3         |          3.12263 |              0.543417 | True             |
|         100 |         5 | oco_first_touch       | oco_first_touch__all__k3                | C              |                121836   |              0.0787027 |              7.79821e-13 |          3.37058 |              0.504851 | True             |
|         100 |         6 | oco_first_touch       | oco_first_touch__low_cost_q50__k2       | C              |                120879   |              0.0566681 |              8.89955e-13 |          3.45181 |              0.501119 | True             |
|         100 |         5 | oco_first_touch       | oco_first_touch__low_cost_q50__k2       | C              |                117038   |              0.0594284 |              8.89955e-13 |          3.11792 |              0.501533 | True             |
|         100 |         5 | oco_first_touch_clean | oco_first_touch_clean__all__k3          | B              |                114740   |              0.468248  |              0.2         |          2.89375 |              0.533653 | True             |
|         100 |         2 | oco_first_touch       | oco_first_touch__all__k2                | C              |                113337   |              0.0900713 |              0.1         |          2.16227 |              0.509283 | True             |
|         100 |         4 | oco_first_touch       | oco_first_touch__low_cost_q50__k2       | C              |                110503   |              0.069865  |              0.1         |          2.75569 |              0.504157 | True             |
|         100 |         2 | oco_first_touch_clean | oco_first_touch_clean__all__k2          | C              |                108108   |              0.29995   |              0.1         |          1.8801  |              0.532178 | True             |
|         100 |         4 | oco_first_touch       | oco_first_touch__all__k3                | C              |                107157   |              0.0890443 |              0.1         |          3.01486 |              0.508901 | True             |
|         100 |         4 | oco_first_touch_clean | oco_first_touch_clean__all__k3          | C              |                102836   |              0.356618  |              0.1         |          2.63577 |              0.52867  | True             |
|         100 |         5 | oco_first_touch_clean | oco_first_touch_clean__low_cost_q50__k2 | B              |                 99370.3 |              0.792587  |              0.5         |          2.52477 |              0.581284 | True             |

## Selection Summary
| library     |   rows_total |   rows_pass |   pass_rate |   mean_annualized_fills_all |   mean_annualized_fills_pass |   mean_gross_all |   mean_gross_pass |   tier_a_rows |   tier_b_rows |   tier_c_rows |
|:------------|-------------:|------------:|------------:|----------------------------:|-----------------------------:|-----------------:|------------------:|--------------:|--------------:|--------------:|
| directional |         2088 |         285 |    0.136494 |                     8272.98 |                      24829.6 |        0.0230459 |         0.0494542 |             0 |            27 |           258 |
| oco         |         2160 |        1489 |    0.689352 |                     8747.38 |                      10884.3 |        1.65323   |         2.58074   |            31 |           105 |          1353 |
