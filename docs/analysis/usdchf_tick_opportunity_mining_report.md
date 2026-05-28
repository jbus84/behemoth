# Tick Opportunity Mining Report

## Setup
- symbol: `USDCHF`
- bar_ticks_grid: `100,1000,2000,5000,10000`
- horizons: `1,3,6`
- train_years: `2022,2023,2024`
- test_year: `2025`
- min_annual_fills: `5000.0`
- inclusion_metric: `mean`

## Directional Top
|   bar_ticks |   horizon | family              | state_id                                      | quality_tier   |   annualized_test_fills |   mean_gross_pips_test |   median_gross_pips_test |   gross_std_test |   hit_rate_gross_test | selection_pass   |
|------------:|----------:|:--------------------|:----------------------------------------------|:---------------|------------------------:|-----------------------:|-------------------------:|-----------------:|----------------------:|:-----------------|
|         100 |         6 | directional_inverse | directional_inverse__all__h6                  | C              |                 70839.1 |             0.0206534  |                      0   |          4.38284 |              0.499044 | True             |
|         100 |         6 | directional_inverse | directional_inverse__high_intensity__h6       | C              |                 70839.1 |             0.0206534  |                      0   |          4.38284 |              0.499044 | True             |
|         100 |         3 | directional_inverse | directional_inverse__all__h3                  | C              |                 70835.5 |             0.0310129  |                      0   |          3.12605 |              0.497039 | True             |
|         100 |         3 | directional_inverse | directional_inverse__high_intensity__h3       | C              |                 70835.5 |             0.0310129  |                      0   |          3.12605 |              0.497039 | True             |
|         100 |         1 | directional_inverse | directional_inverse__all__h1                  | C              |                 70835.4 |             0.0256463  |                      0   |          1.8444  |              0.489057 | True             |
|         100 |         1 | directional_inverse | directional_inverse__high_intensity__h1       | C              |                 70835.4 |             0.0256463  |                      0   |          1.8444  |              0.489057 | True             |
|         100 |         6 | directional_inverse | directional_inverse__high_abs_vel_q70__h6     | C              |                 57404.7 |             0.0288312  |                      0.1 |          4.57753 |              0.500385 | True             |
|         100 |         1 | directional_inverse | directional_inverse__high_abs_vel_q70__h1     | C              |                 57402.1 |             0.0276921  |                      0   |          1.93086 |              0.489773 | True             |
|         100 |         3 | directional_inverse | directional_inverse__high_abs_vel_q70__h3     | C              |                 57401.9 |             0.0384281  |                      0   |          3.26857 |              0.49875  | True             |
|         100 |         6 | directional_inverse | directional_inverse__low_cost_q50__h6         | C              |                 52375.3 |             0.0430773  |                      0   |          4.03702 |              0.499376 | True             |
|         100 |         1 | directional_inverse | directional_inverse__low_cost_q50__h1         | C              |                 52373.1 |             0.0245724  |                      0   |          1.72292 |              0.488244 | True             |
|         100 |         3 | directional_inverse | directional_inverse__low_cost_q50__h3         | C              |                 52372.9 |             0.0435679  |                      0   |          2.90078 |              0.49737  | True             |
|         100 |         6 | directional_inverse | directional_inverse__high_vol_cluster__h6     | C              |                 50994   |             0.0395757  |                      0.1 |          4.36306 |              0.501437 | True             |
|         100 |         3 | directional_inverse | directional_inverse__high_vol_cluster__h3     | C              |                 50991.7 |             0.0418833  |                      0.1 |          3.11839 |              0.50123  | True             |
|         100 |         1 | directional_inverse | directional_inverse__high_vol_cluster__h1     | C              |                 50991.7 |             0.0346354  |                      0   |          1.84172 |              0.491804 | True             |
|         100 |         6 | directional_run     | directional_run__all__n2_reversion            | C              |                 42179.9 |             0.0279106  |                      0   |          4.23113 |              0.498156 | True             |
|         100 |         6 | directional_run     | directional_run__high_intensity__n2_reversion | C              |                 42179.9 |             0.0279106  |                      0   |          4.23113 |              0.498156 | True             |
|         100 |         1 | directional_run     | directional_run__all__n2_reversion            | C              |                 42178.4 |             0.00982893 |                      0   |          1.76373 |              0.486878 | True             |
|         100 |         1 | directional_run     | directional_run__high_intensity__n2_reversion | C              |                 42178.4 |             0.00982893 |                      0   |          1.76373 |              0.486878 | True             |
|         100 |         3 | directional_run     | directional_run__all__n2_reversion            | C              |                 42178.1 |             0.0323261  |                      0   |          3.01709 |              0.495789 | True             |

## OCO Top
|   bar_ticks |   horizon | family          | state_id                              | quality_tier   |   annualized_test_fills |   mean_gross_pips_test |   median_gross_pips_test |   gross_std_test |   hit_rate_gross_test | selection_pass   |
|------------:|----------:|:----------------|:--------------------------------------|:---------------|------------------------:|-----------------------:|-------------------------:|-----------------:|----------------------:|:-----------------|
|         100 |         6 | oco_first_touch | oco_first_touch__all__k1              | D              |                173673   |               -1.14364 |                     -1.2 |          4.33823 |              0.374357 | False            |
|         100 |         6 | oco_first_touch | oco_first_touch__high_intensity__k1   | D              |                173673   |               -1.14364 |                     -1.2 |          4.33823 |              0.374357 | False            |
|         100 |         3 | oco_first_touch | oco_first_touch__all__k1              | D              |                171204   |               -1.14093 |                     -1.1 |          3.19658 |              0.336987 | False            |
|         100 |         3 | oco_first_touch | oco_first_touch__high_intensity__k1   | D              |                171204   |               -1.14093 |                     -1.1 |          3.19658 |              0.336987 | False            |
|         100 |         1 | oco_first_touch | oco_first_touch__all__k1              | D              |                147947   |               -1.12456 |                     -1   |          2.1151  |              0.255509 | False            |
|         100 |         1 | oco_first_touch | oco_first_touch__high_intensity__k1   | D              |                147947   |               -1.12456 |                     -1   |          2.1151  |              0.255509 | False            |
|         100 |         6 | oco_first_touch | oco_first_touch__all__k3              | D              |                132263   |               -1.21007 |                     -1.1 |          4.67404 |              0.381665 | False            |
|         100 |         6 | oco_first_touch | oco_first_touch__high_intensity__k3   | D              |                132263   |               -1.21007 |                     -1.1 |          4.67404 |              0.381665 | False            |
|         100 |         6 | oco_first_touch | oco_first_touch__low_cost_q50__k1     | D              |                128602   |               -1.06762 |                     -1   |          3.9906  |              0.377887 | False            |
|         100 |         3 | oco_first_touch | oco_first_touch__low_cost_q50__k1     | D              |                126964   |               -1.06239 |                     -1   |          2.94389 |              0.339531 | False            |
|         100 |         1 | oco_first_touch | oco_first_touch__low_cost_q50__k1     | D              |                107796   |               -1.04718 |                     -1   |          1.94553 |              0.254945 | False            |
|         100 |         6 | oco_first_touch | oco_first_touch__low_cost_q30__k1     | D              |                101931   |               -1.05871 |                     -1   |          3.88362 |              0.37675  | False            |
|         100 |         3 | oco_first_touch | oco_first_touch__low_cost_q30__k1     | D              |                100517   |               -1.05201 |                     -1   |          2.87315 |              0.337578 | False            |
|         100 |         6 | oco_first_touch | oco_first_touch__low_cost_q50__k3     | D              |                 95624.6 |               -1.18394 |                     -1.1 |          4.26003 |              0.376804 | False            |
|         100 |         3 | oco_first_touch | oco_first_touch__all__k3              | D              |                 87097.7 |               -1.23478 |                     -1.1 |          3.64671 |              0.348892 | False            |
|         100 |         3 | oco_first_touch | oco_first_touch__high_intensity__k3   | D              |                 87097.7 |               -1.23478 |                     -1.1 |          3.64671 |              0.348892 | False            |
|         100 |         1 | oco_first_touch | oco_first_touch__low_cost_q30__k1     | D              |                 84527   |               -1.03672 |                     -0.9 |          1.9043  |              0.254011 | False            |
|         100 |         6 | oco_first_touch | oco_first_touch__low_cost_q30__k3     | D              |                 74414   |               -1.18522 |                     -1.1 |          4.13575 |              0.375662 | False            |
|         100 |         6 | oco_first_touch | oco_first_touch__high_abs_vel_q70__k1 | D              |                 60864.4 |               -1.07251 |                     -1   |          4.65558 |              0.392679 | False            |
|         100 |         3 | oco_first_touch | oco_first_touch__high_abs_vel_q70__k1 | D              |                 60566.8 |               -1.09942 |                     -1   |          3.42091 |              0.354465 | False            |

## No-Touch Top
_empty_

## Selection Summary
| library     |   rows_total |   rows_pass |   pass_rate |   mean_gross_all |   mean_baseline_z |
|:------------|-------------:|------------:|------------:|-----------------:|------------------:|
| directional |         6426 |         674 |    0.104886 |        -0.888905 |          0.625536 |
| oco         |          459 |           0 |    0        |        -1.30942  |          0.661364 |
