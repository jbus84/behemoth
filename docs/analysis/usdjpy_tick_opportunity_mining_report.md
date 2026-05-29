# Tick Opportunity Mining Report

## Setup
- symbol: `USDJPY`
- bar_ticks_grid: `100,1000,2000,5000,10000`
- horizons: `1,3,6`
- train_years: `2022,2023,2024`
- test_year: `2025`
- min_annual_fills: `5000.0`
- inclusion_metric: `mean`

## Directional Top
|   bar_ticks |   horizon | family              | state_id                                  | quality_tier   |   annualized_test_fills |   mean_gross_pips_test |   median_gross_pips_test |   gross_std_test |   hit_rate_gross_test | selection_pass   |
|------------:|----------:|:--------------------|:------------------------------------------|:---------------|------------------------:|-----------------------:|-------------------------:|-----------------:|----------------------:|:-----------------|
|         100 |         6 | directional_inverse | directional_inverse__all__h6              | C              |                139617   |              0.050027  |                      0.1 |          6.27855 |              0.500392 | True             |
|         100 |         6 | directional_inverse | directional_inverse__high_intensity__h6   | C              |                139617   |              0.050027  |                      0.1 |          6.27855 |              0.500392 | True             |
|         100 |         3 | directional_inverse | directional_inverse__all__h3              | C              |                139615   |              0.0498911 |                      0.1 |          4.49435 |              0.500794 | True             |
|         100 |         3 | directional_inverse | directional_inverse__high_intensity__h3   | C              |                139615   |              0.0498911 |                      0.1 |          4.49435 |              0.500794 | True             |
|         100 |         1 | directional_inverse | directional_inverse__all__h1              | C              |                139615   |              0.0282986 |                      0   |          2.6528  |              0.498972 | True             |
|         100 |         1 | directional_inverse | directional_inverse__high_intensity__h1   | C              |                139615   |              0.0282986 |                      0   |          2.6528  |              0.498972 | True             |
|         100 |         6 | directional_inverse | directional_inverse__high_abs_vel_q70__h6 | C              |                124294   |              0.0589943 |                      0   |          6.385   |              0.499992 | True             |
|         100 |         3 | directional_inverse | directional_inverse__high_abs_vel_q70__h3 | C              |                124293   |              0.0534859 |                      0.1 |          4.56298 |              0.500359 | True             |
|         100 |         1 | directional_inverse | directional_inverse__high_abs_vel_q70__h1 | C              |                124293   |              0.0296019 |                      0   |          2.67149 |              0.499818 | True             |
|         100 |         6 | directional_inverse | directional_inverse__high_vol_cluster__h6 | C              |                100664   |              0.0654518 |                      0.1 |          6.28932 |              0.5017   | True             |
|         100 |         1 | directional_inverse | directional_inverse__high_vol_cluster__h1 | C              |                100664   |              0.0345801 |                      0.1 |          2.69206 |              0.501087 | True             |
|         100 |         3 | directional_inverse | directional_inverse__high_vol_cluster__h3 | C              |                100664   |              0.0585758 |                      0.1 |          4.50763 |              0.501959 | True             |
|         100 |         6 | directional_inverse | directional_inverse__high_abs_vel_q80__h6 | C              |                100118   |              0.0748439 |                      0.1 |          6.46615 |              0.501007 | True             |
|         100 |         3 | directional_inverse | directional_inverse__high_abs_vel_q80__h3 | C              |                100118   |              0.062547  |                      0.1 |          4.62319 |              0.500777 | True             |
|         100 |         1 | directional_inverse | directional_inverse__high_abs_vel_q80__h1 | C              |                100118   |              0.0358242 |                      0.1 |          2.73935 |              0.501088 | True             |
|         100 |         6 | directional_inverse | directional_inverse__high_range_q70__h6   | C              |                 99526.2 |              0.0685743 |                      0.1 |          6.61691 |              0.500081 | True             |
|         100 |         3 | directional_inverse | directional_inverse__high_range_q70__h3   | C              |                 99526.2 |              0.0674571 |                      0.1 |          4.73385 |              0.502077 | True             |
|         100 |         1 | directional_inverse | directional_inverse__high_range_q70__h1   | C              |                 99526.2 |              0.0338082 |                      0.1 |          2.84414 |              0.501633 | True             |
|         100 |         6 | directional_inverse | directional_inverse__low_cost_q50__h6     | C              |                 91455   |              0.0435534 |                      0   |          6.09352 |              0.499587 | True             |
|         100 |         1 | directional_inverse | directional_inverse__low_cost_q50__h1     | C              |                 91454.9 |              0.0296355 |                      0   |          2.51483 |              0.498986 | True             |

## OCO Top
|   bar_ticks |   horizon | family          | state_id                            | quality_tier   |   annualized_test_fills |   mean_gross_pips_test |   median_gross_pips_test |   gross_std_test |   hit_rate_gross_test | selection_pass   |
|------------:|----------:|:----------------|:------------------------------------|:---------------|------------------------:|-----------------------:|-------------------------:|-----------------:|----------------------:|:-----------------|
|         100 |         6 | oco_first_touch | oco_first_touch__all__k1            | D              |                  340940 |              -0.663304 |                     -0.7 |          6.13361 |              0.445426 | False            |
|         100 |         6 | oco_first_touch | oco_first_touch__high_intensity__k1 | D              |                  340940 |              -0.663304 |                     -0.7 |          6.13361 |              0.445426 | False            |
|         100 |         3 | oco_first_touch | oco_first_touch__all__k1            | D              |                  339932 |              -0.661087 |                     -0.7 |          4.38464 |              0.424478 | False            |
|         100 |         3 | oco_first_touch | oco_first_touch__high_intensity__k1 | D              |                  339932 |              -0.661087 |                     -0.7 |          4.38464 |              0.424478 | False            |
|         100 |         1 | oco_first_touch | oco_first_touch__all__k1            | D              |                  324971 |              -0.651169 |                     -0.6 |          2.60581 |              0.376821 | False            |
|         100 |         1 | oco_first_touch | oco_first_touch__high_intensity__k1 | D              |                  324971 |              -0.651169 |                     -0.6 |          2.60581 |              0.376821 | False            |
|         100 |         6 | oco_first_touch | oco_first_touch__all__k3            | D              |                  317715 |              -0.707336 |                     -0.7 |          6.26931 |              0.446904 | False            |
|         100 |         6 | oco_first_touch | oco_first_touch__high_intensity__k3 | D              |                  317715 |              -0.707336 |                     -0.7 |          6.26931 |              0.446904 | False            |
|         100 |         3 | oco_first_touch | oco_first_touch__all__k3            | D              |                  258608 |              -0.702443 |                     -0.7 |          4.59182 |              0.426672 | False            |
|         100 |         3 | oco_first_touch | oco_first_touch__high_intensity__k3 | D              |                  258608 |              -0.702443 |                     -0.7 |          4.59182 |              0.426672 | False            |
|         100 |         6 | oco_first_touch | oco_first_touch__low_cost_q50__k1   | D              |                  221609 |              -0.579103 |                     -0.6 |          5.97492 |              0.45207  | False            |
|         100 |         3 | oco_first_touch | oco_first_touch__low_cost_q50__k1   | D              |                  221247 |              -0.568104 |                     -0.6 |          4.25009 |              0.433449 | False            |
|         100 |         1 | oco_first_touch | oco_first_touch__low_cost_q50__k1   | D              |                  211813 |              -0.55491  |                     -0.5 |          2.51084 |              0.390696 | False            |
|         100 |         6 | oco_first_touch | oco_first_touch__low_cost_q50__k3   | D              |                  206704 |              -0.62069  |                     -0.6 |          6.06117 |              0.452275 | False            |
|         100 |         3 | oco_first_touch | oco_first_touch__low_cost_q50__k3   | D              |                  166169 |              -0.601163 |                     -0.6 |          4.41984 |              0.434006 | False            |
|         100 |         6 | oco_first_touch | oco_first_touch__low_cost_q30__k1   | D              |                  147299 |              -0.528577 |                     -0.5 |          5.95191 |              0.455391 | False            |
|         100 |         3 | oco_first_touch | oco_first_touch__low_cost_q30__k1   | D              |                  147003 |              -0.513322 |                     -0.5 |          4.23661 |              0.439738 | False            |
|         100 |         6 | oco_first_touch | oco_first_touch__high_range_q70__k1 | D              |                  146574 |              -0.703165 |                     -0.7 |          6.74522 |              0.451538 | False            |
|         100 |         3 | oco_first_touch | oco_first_touch__high_range_q70__k1 | D              |                  146497 |              -0.697228 |                     -0.7 |          4.83636 |              0.430182 | False            |
|         100 |         1 | oco_first_touch | oco_first_touch__high_range_q70__k1 | D              |                  143247 |              -0.684085 |                     -0.6 |          2.8887  |              0.386476 | False            |

## No-Touch Top
_empty_

## Selection Summary
| library     |   rows_total |   rows_pass |   pass_rate |   mean_gross_all |   mean_baseline_z |
|:------------|-------------:|------------:|------------:|-----------------:|------------------:|
| directional |         6426 |         798 |    0.124183 |        -0.492167 |          0.695679 |
| oco         |          459 |           0 |    0        |        -0.645129 |          1.0441   |
