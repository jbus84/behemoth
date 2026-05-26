# Tick Opportunity Mining Report

## Setup
- symbol: `EURUSD`
- bar_ticks_grid: `100,1000,2000`
- horizons: `1,3,6`
- train_years: `2022,2023,2024`
- test_year: `2025`
- min_annual_fills: `5000.0`
- inclusion_metric: `mean`

## Directional Top
|   bar_ticks |   horizon | family              | state_id                                                   | quality_tier   |   annualized_test_fills |   mean_gross_pips_test |   median_gross_pips_test |   gross_std_test |   hit_rate_gross_test | selection_pass   |
|------------:|----------:|:--------------------|:-----------------------------------------------------------|:---------------|------------------------:|-----------------------:|-------------------------:|-----------------:|----------------------:|:-----------------|
|         100 |         6 | directional_inverse | directional_inverse__all__h6                               | C              |                 94487.7 |             0.0291292  |                     0    |          4.86808 |              0.497424 | True             |
|         100 |         6 | directional_inverse | directional_inverse__high_intensity__h6                    | C              |                 94487.7 |             0.0291292  |                     0    |          4.86808 |              0.497424 | True             |
|         100 |         3 | directional_inverse | directional_inverse__all__h3                               | C              |                 94487.7 |             0.00553567 |                     0    |          3.47591 |              0.492167 | True             |
|         100 |         3 | directional_inverse | directional_inverse__high_intensity__h3                    | C              |                 94487.7 |             0.00553567 |                     0    |          3.47591 |              0.492167 | True             |
|         100 |         1 | directional_inverse | directional_inverse__all__h1                               | C              |                 94487.7 |            -0.00158465 |                     0    |          2.00718 |              0.484669 | True             |
|         100 |         1 | directional_inverse | directional_inverse__high_intensity__h1                    | C              |                 94487.7 |            -0.00158465 |                     0    |          2.00718 |              0.484669 | True             |
|         100 |         6 | directional_inverse | directional_inverse__high_range_q70__h6                    | C              |                 71080.8 |             0.0323752  |                     0    |          5.12539 |              0.49868  | True             |
|         100 |         3 | directional_inverse | directional_inverse__high_range_q70__h3                    | C              |                 71080.8 |             0.00926457 |                     0    |          3.6639  |              0.493343 | True             |
|         100 |         1 | directional_inverse | directional_inverse__high_range_q70__h1                    | C              |                 71080.8 |             0.00360728 |                     0    |          2.13668 |              0.487258 | True             |
|         100 |         6 | directional_inverse | directional_inverse__high_vol_cluster__h6                  | C              |                 68970.3 |             0.0403297  |                     0    |          4.83731 |              0.498894 | True             |
|         100 |         3 | directional_inverse | directional_inverse__high_vol_cluster__h3                  | C              |                 68970.3 |             0.0177255  |                     0    |          3.45742 |              0.493467 | True             |
|         100 |         1 | directional_inverse | directional_inverse__high_vol_cluster__h1                  | C              |                 68970.3 |             0.0090126  |                     0    |          2.01789 |              0.486046 | True             |
|         100 |         3 | directional_inverse | directional_inverse__low_cost_q30__h3                      | C              |                 68760   |             0.102312   |                     0.05 |          3.30081 |              0.5      | True             |
|         100 |         1 | directional_inverse | directional_inverse__low_cost_q30__h1                      | C              |                 68760   |             0.0555132  |                     0.1  |          1.87802 |              0.511941 | True             |
|         100 |         6 | directional_inverse | directional_inverse__low_cost_q30__h6                      | C              |                 68760   |             0.00637703 |                     0    |          4.60558 |              0.495173 | True             |
|         100 |         3 | directional_inverse | directional_inverse__low_cost_q30_and_high_abs_vel_q70__h3 | C              |                 66558.8 |             0.109475   |                     0.1  |          3.32694 |              0.501312 | True             |
|         100 |         1 | directional_inverse | directional_inverse__low_cost_q30_and_high_abs_vel_q70__h1 | C              |                 66558.8 |             0.0545407  |                     0.1  |          1.89003 |              0.511811 | True             |
|         100 |         6 | directional_inverse | directional_inverse__low_cost_q30_and_high_abs_vel_q70__h6 | C              |                 66558.8 |             0.00304462 |                     0    |          4.63584 |              0.495538 | True             |
|         100 |         6 | directional_run     | directional_run__all__n2_reversion                         | C              |                 57059.8 |             0.0121731  |                     0    |          4.73419 |              0.496403 | True             |
|         100 |         6 | directional_run     | directional_run__high_intensity__n2_reversion              | C              |                 57059.8 |             0.0121731  |                     0    |          4.73419 |              0.496403 | True             |

## OCO Top
|   bar_ticks |   horizon | family          | state_id                                               | quality_tier   |   annualized_test_fills |   mean_gross_pips_test |   median_gross_pips_test |   gross_std_test |   hit_rate_gross_test | selection_pass   |
|------------:|----------:|:----------------|:-------------------------------------------------------|:---------------|------------------------:|-----------------------:|-------------------------:|-----------------:|----------------------:|:-----------------|
|        2000 |         3 | oco_first_touch | oco_first_touch__persistent_flow__k2                   | C              |                 404.321 |              -0.234336 |                      0   |         14.98    |              0.496241 | True             |
|         100 |         6 | oco_first_touch | oco_first_touch__all__k2                               | D              |              226804     |              -0.517541 |                     -0.5 |          4.84541 |              0.446796 | False            |
|         100 |         6 | oco_first_touch | oco_first_touch__high_intensity__k2                    | D              |              226804     |              -0.517541 |                     -0.5 |          4.84541 |              0.446796 | False            |
|         100 |         3 | oco_first_touch | oco_first_touch__all__k2                               | D              |              198612     |              -0.494912 |                     -0.5 |          3.51159 |              0.430578 | False            |
|         100 |         3 | oco_first_touch | oco_first_touch__high_intensity__k2                    | D              |              198612     |              -0.494912 |                     -0.5 |          3.51159 |              0.430578 | False            |
|         100 |         6 | oco_first_touch | oco_first_touch__low_cost_q30__k2                      | D              |              164292     |              -0.354641 |                     -0.4 |          4.72974 |              0.458905 | False            |
|         100 |         3 | oco_first_touch | oco_first_touch__low_cost_q30__k2                      | D              |              138666     |              -0.370068 |                     -0.3 |          3.45176 |              0.444822 | False            |
|         100 |         6 | oco_first_touch | oco_first_touch__high_range_q70__k2                    | D              |              108788     |              -0.536406 |                     -0.5 |          5.29491 |              0.450046 | False            |
|         100 |         6 | oco_first_touch | oco_first_touch__all__k5                               | D              |              106795     |              -0.583949 |                     -0.6 |          5.38683 |              0.447107 | False            |
|         100 |         6 | oco_first_touch | oco_first_touch__high_intensity__k5                    | D              |              106795     |              -0.583949 |                     -0.6 |          5.38683 |              0.447107 | False            |
|         100 |         1 | oco_first_touch | oco_first_touch__all__k2                               | D              |              104124     |              -0.504184 |                     -0.5 |          2.20423 |              0.386221 | False            |
|         100 |         1 | oco_first_touch | oco_first_touch__high_intensity__k2                    | D              |              104124     |              -0.504184 |                     -0.5 |          2.20423 |              0.386221 | False            |
|         100 |         3 | oco_first_touch | oco_first_touch__high_range_q70__k2                    | D              |               99599.8   |              -0.518539 |                     -0.5 |          3.83463 |              0.434244 | False            |
|         100 |         6 | oco_first_touch | oco_first_touch__low_cost_q30_and_high_abs_vel_q70__k2 | D              |               76097.2   |              -0.367769 |                     -0.3 |          4.87593 |              0.467401 | False            |
|         100 |         6 | oco_first_touch | oco_first_touch__high_range_q80__k2                    | D              |               75814.2   |              -0.549171 |                     -0.5 |          5.53125 |              0.451088 | False            |
|         100 |         3 | oco_first_touch | oco_first_touch__high_range_q80__k2                    | D              |               70225.5   |              -0.53887  |                     -0.5 |          4.01035 |              0.434378 | False            |
|         100 |         6 | oco_first_touch | oco_first_touch__high_vol_cluster__k2                  | D              |               68411.8   |              -0.530373 |                     -0.5 |          4.89952 |              0.443052 | False            |
|         100 |         3 | oco_first_touch | oco_first_touch__low_cost_q30_and_high_abs_vel_q70__k2 | D              |               65947.4   |              -0.41494  |                     -0.3 |          3.53986 |              0.448212 | False            |
|         100 |         6 | oco_first_touch | oco_first_touch__high_activity__k2                     | D              |               65507.4   |              -0.528987 |                     -0.5 |          4.95612 |              0.445144 | False            |
|         100 |         6 | oco_first_touch | oco_first_touch__ny_overlap__k2                        | D              |               65438.4   |              -0.455133 |                     -0.4 |          5.00654 |              0.458249 | False            |

## No-Touch Top
_empty_

## Selection Summary
| library     |   rows_total |   rows_pass |   pass_rate |   mean_gross_all |   mean_baseline_z |
|:------------|-------------:|------------:|------------:|-----------------:|------------------:|
| directional |         6426 |         733 |  0.114068   |        -0.419657 |          0.173233 |
| oco         |          459 |           1 |  0.00217865 |        -0.608513 |          0.206525 |
