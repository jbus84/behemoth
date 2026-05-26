# Tick Opportunity Mining Report

## Setup
- symbol: `GBPUSD`
- bar_ticks_grid: `100,1000,2000,5000,10000`
- horizons: `1,3,6`
- train_years: `2022,2023,2024`
- test_year: `2025`
- min_annual_fills: `5000.0`
- inclusion_metric: `mean`

## Directional Top
|   bar_ticks |   horizon | family              | state_id                                  | quality_tier   |   annualized_test_fills |   mean_gross_pips_test |   median_gross_pips_test |   gross_std_test |   hit_rate_gross_test | selection_pass   |
|------------:|----------:|:--------------------|:------------------------------------------|:---------------|------------------------:|-----------------------:|-------------------------:|-----------------:|----------------------:|:-----------------|
|         100 |         6 | directional_inverse | directional_inverse__all__h6              | C              |                 98049.7 |              0.0658564 |                      0.1 |          5.10603 |              0.503142 | True             |
|         100 |         6 | directional_inverse | directional_inverse__high_intensity__h6   | C              |                 98049.7 |              0.0658564 |                      0.1 |          5.10603 |              0.503142 | True             |
|         100 |         3 | directional_inverse | directional_inverse__all__h3              | C              |                 98049.7 |              0.0413083 |                      0   |          3.68083 |              0.498209 | True             |
|         100 |         3 | directional_inverse | directional_inverse__high_intensity__h3   | C              |                 98049.7 |              0.0413083 |                      0   |          3.68083 |              0.498209 | True             |
|         100 |         1 | directional_inverse | directional_inverse__all__h1              | C              |                 98049.7 |              0.0174172 |                      0   |          2.12652 |              0.491576 | True             |
|         100 |         1 | directional_inverse | directional_inverse__high_intensity__h1   | C              |                 98049.7 |              0.0174172 |                      0   |          2.12652 |              0.491576 | True             |
|         100 |         6 | directional_inverse | directional_inverse__high_abs_vel_q70__h6 | C              |                 82079.7 |              0.0683423 |                      0.1 |          5.28311 |              0.502855 | True             |
|         100 |         3 | directional_inverse | directional_inverse__high_abs_vel_q70__h3 | C              |                 82079.7 |              0.0468654 |                      0   |          3.81098 |              0.49838  | True             |
|         100 |         1 | directional_inverse | directional_inverse__high_abs_vel_q70__h1 | C              |                 82079.7 |              0.0183918 |                      0   |          2.20724 |              0.491985 | True             |
|         100 |         6 | directional_inverse | directional_inverse__low_cost_q50__h6     | C              |                 80879.8 |              0.0553659 |                      0.1 |          5.15718 |              0.502413 | True             |
|         100 |         3 | directional_inverse | directional_inverse__low_cost_q50__h3     | C              |                 80879.8 |              0.0361992 |                      0   |          3.70696 |              0.497413 | True             |
|         100 |         1 | directional_inverse | directional_inverse__low_cost_q50__h1     | C              |                 80879.8 |              0.0174668 |                      0   |          2.13934 |              0.49106  | True             |
|         100 |         6 | directional_inverse | directional_inverse__high_vol_cluster__h6 | C              |                 71288.1 |              0.0696037 |                      0.1 |          5.1097  |              0.505089 | True             |
|         100 |         3 | directional_inverse | directional_inverse__high_vol_cluster__h3 | C              |                 71288.1 |              0.0526712 |                      0   |          3.70066 |              0.499078 | True             |
|         100 |         1 | directional_inverse | directional_inverse__high_vol_cluster__h1 | C              |                 71288.1 |              0.0249905 |                      0   |          2.13731 |              0.493982 | True             |
|         100 |         6 | directional_inverse | directional_inverse__high_abs_vel_q80__h6 | C              |                 62269.9 |              0.0629305 |                      0.1 |          5.44057 |              0.502555 | True             |
|         100 |         3 | directional_inverse | directional_inverse__high_abs_vel_q80__h3 | C              |                 62269.9 |              0.0493916 |                      0   |          3.95302 |              0.4983   | True             |
|         100 |         1 | directional_inverse | directional_inverse__high_abs_vel_q80__h1 | C              |                 62269.9 |              0.0147366 |                      0   |          2.29124 |              0.49074  | True             |
|         100 |         6 | directional_inverse | directional_inverse__low_cost_q30__h6     | C              |                 59532.2 |              0.0563994 |                      0.1 |          5.09286 |              0.502516 | True             |
|         100 |         3 | directional_inverse | directional_inverse__low_cost_q30__h3     | C              |                 59532.2 |              0.0359111 |                      0   |          3.66235 |              0.496724 | True             |

## OCO Top
|   bar_ticks |   horizon | family          | state_id                            | quality_tier   |   annualized_test_fills |   mean_gross_pips_test |   median_gross_pips_test |   gross_std_test |   hit_rate_gross_test | selection_pass   |
|------------:|----------:|:----------------|:------------------------------------|:---------------|------------------------:|-----------------------:|-------------------------:|-----------------:|----------------------:|:-----------------|
|         100 |         6 | oco_first_touch | oco_first_touch__all__k1            | D              |                242984   |              -0.903654 |                     -1   |          5.01534 |              0.407947 | False            |
|         100 |         6 | oco_first_touch | oco_first_touch__high_intensity__k1 | D              |                242984   |              -0.903654 |                     -1   |          5.01534 |              0.407947 | False            |
|         100 |         3 | oco_first_touch | oco_first_touch__all__k1            | D              |                240499   |              -0.902836 |                     -0.9 |          3.61592 |              0.377361 | False            |
|         100 |         3 | oco_first_touch | oco_first_touch__high_intensity__k1 | D              |                240499   |              -0.902836 |                     -0.9 |          3.61592 |              0.377361 | False            |
|         100 |         1 | oco_first_touch | oco_first_touch__all__k1            | D              |                218846   |              -0.884214 |                     -0.9 |          2.20537 |              0.310742 | False            |
|         100 |         1 | oco_first_touch | oco_first_touch__high_intensity__k1 | D              |                218846   |              -0.884214 |                     -0.9 |          2.20537 |              0.310742 | False            |
|         100 |         6 | oco_first_touch | oco_first_touch__all__k3            | D              |                206728   |              -0.937097 |                     -0.9 |          5.24299 |              0.415116 | False            |
|         100 |         6 | oco_first_touch | oco_first_touch__high_intensity__k3 | D              |                206728   |              -0.937097 |                     -0.9 |          5.24299 |              0.415116 | False            |
|         100 |         6 | oco_first_touch | oco_first_touch__low_cost_q50__k1   | D              |                200694   |              -0.844744 |                     -0.9 |          5.04079 |              0.416718 | False            |
|         100 |         3 | oco_first_touch | oco_first_touch__low_cost_q50__k1   | D              |                199497   |              -0.853986 |                     -0.8 |          3.62031 |              0.385774 | False            |
|         100 |         1 | oco_first_touch | oco_first_touch__low_cost_q50__k1   | D              |                182786   |              -0.840055 |                     -0.8 |          2.19459 |              0.319429 | False            |
|         100 |         6 | oco_first_touch | oco_first_touch__low_cost_q50__k3   | D              |                173892   |              -0.894582 |                     -0.9 |          5.22992 |              0.417415 | False            |
|         100 |         3 | oco_first_touch | oco_first_touch__all__k3            | D              |                152235   |              -0.927457 |                     -0.9 |          3.94367 |              0.387558 | False            |
|         100 |         3 | oco_first_touch | oco_first_touch__high_intensity__k3 | D              |                152235   |              -0.927457 |                     -0.9 |          3.94367 |              0.387558 | False            |
|         100 |         6 | oco_first_touch | oco_first_touch__low_cost_q30__k1   | D              |                148528   |              -0.823399 |                     -0.8 |          4.98151 |              0.419362 | False            |
|         100 |         3 | oco_first_touch | oco_first_touch__low_cost_q30__k1   | D              |                147650   |              -0.83137  |                     -0.8 |          3.59224 |              0.389248 | False            |
|         100 |         1 | oco_first_touch | oco_first_touch__low_cost_q30__k1   | D              |                135168   |              -0.816725 |                     -0.8 |          2.19134 |              0.325208 | False            |
|         100 |         6 | oco_first_touch | oco_first_touch__low_cost_q30__k3   | D              |                128885   |              -0.889815 |                     -0.9 |          5.16032 |              0.418069 | False            |
|         100 |         3 | oco_first_touch | oco_first_touch__low_cost_q50__k3   | D              |                128131   |              -0.891112 |                     -0.9 |          3.92448 |              0.391381 | False            |
|         100 |         3 | oco_first_touch | oco_first_touch__low_cost_q30__k3   | D              |                 94806.5 |              -0.873188 |                     -0.8 |          3.89114 |              0.393973 | False            |

## No-Touch Top
_empty_

## Selection Summary
| library     |   rows_total |   rows_pass |   pass_rate |   mean_gross_all |   mean_baseline_z |
|:------------|-------------:|------------:|------------:|-----------------:|------------------:|
| directional |         6426 |         745 |    0.115935 |        -0.701275 |          0.545052 |
| oco         |          459 |           0 |    0        |        -1.01669  |          0.886262 |
