# Tick Opportunity Mining Report

## Setup
- symbol: `USDCAD`
- bar_ticks_grid: `100,1000,2000,5000,10000`
- horizons: `1,3,6`
- train_years: `2022,2023,2024`
- test_year: `2025`
- min_annual_fills: `5000.0`
- inclusion_metric: `mean`

## Directional Top
|   bar_ticks |   horizon | family              | state_id                                      | quality_tier   |   annualized_test_fills |   mean_gross_pips_test |   median_gross_pips_test |   gross_std_test |   hit_rate_gross_test | selection_pass   |
|------------:|----------:|:--------------------|:----------------------------------------------|:---------------|------------------------:|-----------------------:|-------------------------:|-----------------:|----------------------:|:-----------------|
|         100 |         1 | directional_inverse | directional_inverse__all__h1                  | C              |                 90988.1 |             0.00680703 |                      0   |          2.09859 |              0.485381 | True             |
|         100 |         1 | directional_inverse | directional_inverse__high_intensity__h1       | C              |                 90988.1 |             0.00680703 |                      0   |          2.09859 |              0.485381 | True             |
|         100 |         3 | directional_inverse | directional_inverse__all__h3                  | C              |                 90986.2 |             0.0377086  |                      0   |          3.41867 |              0.496719 | True             |
|         100 |         3 | directional_inverse | directional_inverse__high_intensity__h3       | C              |                 90986.2 |             0.0377086  |                      0   |          3.41867 |              0.496719 | True             |
|         100 |         6 | directional_inverse | directional_inverse__all__h6                  | C              |                 90985.6 |             0.0495346  |                      0.1 |          4.73573 |              0.501434 | True             |
|         100 |         6 | directional_inverse | directional_inverse__high_intensity__h6       | C              |                 90985.6 |             0.0495346  |                      0.1 |          4.73573 |              0.501434 | True             |
|         100 |         1 | directional_inverse | directional_inverse__high_vol_cluster__h1     | C              |                 66818.9 |             0.0112111  |                      0   |          2.16019 |              0.485447 | True             |
|         100 |         3 | directional_inverse | directional_inverse__high_vol_cluster__h3     | C              |                 66816.9 |             0.0470188  |                      0   |          3.4548  |              0.497462 | True             |
|         100 |         6 | directional_inverse | directional_inverse__high_vol_cluster__h6     | C              |                 66816.3 |             0.0610892  |                      0.1 |          4.74437 |              0.503852 | True             |
|         100 |         6 | directional_inverse | directional_inverse__high_abs_vel_q70__h6     | C              |                 57211.9 |             0.0814296  |                      0.1 |          5.30827 |              0.506595 | True             |
|         100 |         3 | directional_inverse | directional_inverse__high_abs_vel_q70__h3     | C              |                 57210.4 |             0.0543562  |                      0.1 |          3.84907 |              0.500026 | True             |
|         100 |         1 | directional_inverse | directional_inverse__high_abs_vel_q70__h1     | C              |                 57210.4 |             0.0115925  |                      0   |          2.39611 |              0.486906 | True             |
|         100 |         3 | directional_run     | directional_run__all__n2_reversion            | C              |                 56178   |             0.0245083  |                      0   |          3.39246 |              0.496365 | True             |
|         100 |         3 | directional_run     | directional_run__high_intensity__n2_reversion | C              |                 56178   |             0.0245083  |                      0   |          3.39246 |              0.496365 | True             |
|         100 |         1 | directional_run     | directional_run__all__n2_reversion            | C              |                 56178   |             0.0115128  |                      0   |          2.02626 |              0.487308 | True             |
|         100 |         1 | directional_run     | directional_run__high_intensity__n2_reversion | C              |                 56178   |             0.0115128  |                      0   |          2.02626 |              0.487308 | True             |
|         100 |         6 | directional_run     | directional_run__all__n2_reversion            | C              |                 56177.4 |             0.0427724  |                      0.1 |          4.67907 |              0.502019 | True             |
|         100 |         6 | directional_run     | directional_run__high_intensity__n2_reversion | C              |                 56177.4 |             0.0427724  |                      0.1 |          4.67907 |              0.502019 | True             |
|         100 |         6 | directional_inverse | directional_inverse__high_range_q70__h6       | C              |                 39869.7 |             0.0881245  |                      0.1 |          5.86731 |              0.50628  | True             |
|         100 |         3 | directional_inverse | directional_inverse__high_range_q70__h3       | C              |                 39869   |             0.0623534  |                      0.1 |          4.28027 |              0.500705 | True             |

## OCO Top
|   bar_ticks |   horizon | family          | state_id                              | quality_tier   |   annualized_test_fills |   mean_gross_pips_test |   median_gross_pips_test |   gross_std_test |   hit_rate_gross_test | selection_pass   |
|------------:|----------:|:----------------|:--------------------------------------|:---------------|------------------------:|-----------------------:|-------------------------:|-----------------:|----------------------:|:-----------------|
|         100 |         6 | oco_first_touch | oco_first_touch__all__k1              | D              |                230597   |               -1.4473  |                     -1.5 |          4.65137 |              0.336883 | False            |
|         100 |         6 | oco_first_touch | oco_first_touch__high_intensity__k1   | D              |                230597   |               -1.4473  |                     -1.5 |          4.65137 |              0.336883 | False            |
|         100 |         3 | oco_first_touch | oco_first_touch__all__k1              | D              |                226044   |               -1.43804 |                     -1.4 |          3.35944 |              0.286697 | False            |
|         100 |         3 | oco_first_touch | oco_first_touch__high_intensity__k1   | D              |                226044   |               -1.43804 |                     -1.4 |          3.35944 |              0.286697 | False            |
|         100 |         1 | oco_first_touch | oco_first_touch__all__k1              | D              |                187787   |               -1.43923 |                     -1.4 |          2.11525 |              0.184982 | False            |
|         100 |         1 | oco_first_touch | oco_first_touch__high_intensity__k1   | D              |                187787   |               -1.43923 |                     -1.4 |          2.11525 |              0.184982 | False            |
|         100 |         6 | oco_first_touch | oco_first_touch__all__k3              | D              |                170485   |               -1.50015 |                     -1.5 |          5.10475 |              0.345359 | False            |
|         100 |         6 | oco_first_touch | oco_first_touch__high_intensity__k3   | D              |                170485   |               -1.50015 |                     -1.5 |          5.10475 |              0.345359 | False            |
|         100 |         3 | oco_first_touch | oco_first_touch__all__k3              | D              |                111777   |               -1.51609 |                     -1.5 |          4.02146 |              0.304002 | False            |
|         100 |         3 | oco_first_touch | oco_first_touch__high_intensity__k3   | D              |                111777   |               -1.51609 |                     -1.5 |          4.02146 |              0.304002 | False            |
|         100 |         6 | oco_first_touch | oco_first_touch__low_cost_q50__k1     | D              |                 95841.7 |               -1.38292 |                     -1.4 |          3.91213 |              0.330457 | False            |
|         100 |         3 | oco_first_touch | oco_first_touch__low_cost_q50__k1     | D              |                 93470   |               -1.36308 |                     -1.3 |          2.84314 |              0.278803 | False            |
|         100 |         1 | oco_first_touch | oco_first_touch__low_cost_q50__k1     | D              |                 74201.4 |               -1.35715 |                     -1.3 |          1.80985 |              0.178015 | False            |
|         100 |         6 | oco_first_touch | oco_first_touch__high_activity__k1    | D              |                 69065.3 |               -1.48878 |                     -1.5 |          4.87843 |              0.335992 | False            |
|         100 |         6 | oco_first_touch | oco_first_touch__high_vol_cluster__k1 | D              |                 69057.4 |               -1.47676 |                     -1.5 |          4.74779 |              0.336259 | False            |
|         100 |         3 | oco_first_touch | oco_first_touch__high_vol_cluster__k1 | D              |                 67916.4 |               -1.46155 |                     -1.4 |          3.52683 |              0.287017 | False            |
|         100 |         3 | oco_first_touch | oco_first_touch__high_activity__k1    | D              |                 67785.8 |               -1.48106 |                     -1.4 |          3.51903 |              0.285664 | False            |
|         100 |         6 | oco_first_touch | oco_first_touch__ny_overlap__k1       | D              |                 67706.3 |               -1.26802 |                     -1.3 |          4.91742 |              0.375223 | False            |
|         100 |         3 | oco_first_touch | oco_first_touch__ny_overlap__k1       | D              |                 67332.2 |               -1.26539 |                     -1.2 |          3.49375 |              0.32815  | False            |
|         100 |         6 | oco_first_touch | oco_first_touch__low_cost_q50__k3     | D              |                 65771.1 |               -1.47396 |                     -1.5 |          4.28576 |              0.331304 | False            |

## No-Touch Top
_empty_

## Selection Summary
| library     |   rows_total |   rows_pass |   pass_rate |   mean_gross_all |   mean_baseline_z |
|:------------|-------------:|------------:|------------:|-----------------:|------------------:|
| directional |         6426 |         696 |     0.10831 |         -1.12538 |        -0.0875267 |
| oco         |          459 |           0 |     0       |         -1.61905 |        -0.195963  |
