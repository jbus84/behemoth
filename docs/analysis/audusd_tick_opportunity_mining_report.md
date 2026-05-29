# Tick Opportunity Mining Report

## Setup
- symbol: `AUDUSD`
- bar_ticks_grid: `100,1000,2000,5000,10000`
- horizons: `1,3,6`
- train_years: `2022,2023,2024`
- test_year: `2025`
- min_annual_fills: `5000.0`
- inclusion_metric: `mean`

## Directional Top
|   bar_ticks |   horizon | family              | state_id                                      | quality_tier   |   annualized_test_fills |   mean_gross_pips_test |   median_gross_pips_test |   gross_std_test |   hit_rate_gross_test | selection_pass   |
|------------:|----------:|:--------------------|:----------------------------------------------|:---------------|------------------------:|-----------------------:|-------------------------:|-----------------:|----------------------:|:-----------------|
|         100 |         6 | directional_inverse | directional_inverse__all__h6                  | C              |                 66236.2 |            0.010862    |                        0 |          3.98051 |              0.495311 | True             |
|         100 |         6 | directional_inverse | directional_inverse__high_intensity__h6       | C              |                 66236.2 |            0.010862    |                        0 |          3.98051 |              0.495311 | True             |
|         100 |         1 | directional_inverse | directional_inverse__all__h1                  | C              |                 66236.2 |            0.00326359  |                        0 |          1.68425 |              0.486871 | True             |
|         100 |         1 | directional_inverse | directional_inverse__high_intensity__h1       | C              |                 66236.2 |            0.00326359  |                        0 |          1.68425 |              0.486871 | True             |
|         100 |         3 | directional_inverse | directional_inverse__all__h3                  | C              |                 66236.2 |            0.000198482 |                        0 |          2.85749 |              0.492659 | True             |
|         100 |         3 | directional_inverse | directional_inverse__high_intensity__h3       | C              |                 66236.2 |            0.000198482 |                        0 |          2.85749 |              0.492659 | True             |
|         100 |         6 | directional_inverse | directional_inverse__low_cost_q50__h6         | C              |                 58450.5 |            0.0188606   |                        0 |          3.81692 |              0.495802 | True             |
|         100 |         1 | directional_inverse | directional_inverse__low_cost_q50__h1         | C              |                 58450.5 |            0.0062617   |                        0 |          1.59819 |              0.486204 | True             |
|         100 |         3 | directional_inverse | directional_inverse__low_cost_q50__h3         | C              |                 58450.5 |            0.00572086  |                        0 |          2.72911 |              0.49242  | True             |
|         100 |         6 | directional_inverse | directional_inverse__high_abs_vel_q70__h6     | C              |                 50440.8 |            0.0203784   |                        0 |          4.1537  |              0.498    | True             |
|         100 |         1 | directional_inverse | directional_inverse__high_abs_vel_q70__h1     | C              |                 50440.8 |            0.00649038  |                        0 |          1.75665 |              0.489484 | True             |
|         100 |         3 | directional_inverse | directional_inverse__high_abs_vel_q70__h3     | C              |                 50440.8 |            0.00423009  |                        0 |          2.96661 |              0.493524 | True             |
|         100 |         6 | directional_inverse | directional_inverse__low_cost_q30__h6         | C              |                 49747.8 |            0.0192459   |                        0 |          3.6876  |              0.494941 | True             |
|         100 |         1 | directional_inverse | directional_inverse__low_cost_q30__h1         | C              |                 49747.8 |            0.00432579  |                        0 |          1.54738 |              0.48553  | True             |
|         100 |         3 | directional_inverse | directional_inverse__low_cost_q30__h3         | C              |                 49747.8 |            0.00199931  |                        0 |          2.64515 |              0.490983 | True             |
|         100 |         6 | directional_inverse | directional_inverse__high_vol_cluster__h6     | C              |                 48920.7 |            0.0246682   |                        0 |          3.98639 |              0.498595 | True             |
|         100 |         3 | directional_inverse | directional_inverse__high_vol_cluster__h3     | C              |                 48920.7 |            0.0115125   |                        0 |          2.84652 |              0.494307 | True             |
|         100 |         1 | directional_inverse | directional_inverse__high_vol_cluster__h1     | C              |                 48920.7 |            0.00781176  |                        0 |          1.69038 |              0.48961  | True             |
|         100 |         3 | directional_run     | directional_run__all__n2_reversion            | C              |                 40813.6 |            0.0322424   |                        0 |          2.75219 |              0.498303 | True             |
|         100 |         3 | directional_run     | directional_run__high_intensity__n2_reversion | C              |                 40813.6 |            0.0322424   |                        0 |          2.75219 |              0.498303 | True             |

## OCO Top
|   bar_ticks |   horizon | family          | state_id                              | quality_tier   |   annualized_test_fills |   mean_gross_pips_test |   median_gross_pips_test |   gross_std_test |   hit_rate_gross_test | selection_pass   |
|------------:|----------:|:----------------|:--------------------------------------|:---------------|------------------------:|-----------------------:|-------------------------:|-----------------:|----------------------:|:-----------------|
|         100 |         6 | oco_first_touch | oco_first_touch__all__k1              | D              |                166541   |               -1.05562 |                     -1.1 |          3.91069 |              0.370319 | False            |
|         100 |         6 | oco_first_touch | oco_first_touch__high_intensity__k1   | D              |                166541   |               -1.05562 |                     -1.1 |          3.91069 |              0.370319 | False            |
|         100 |         3 | oco_first_touch | oco_first_touch__all__k1              | D              |                163982   |               -1.04825 |                     -1   |          2.80658 |              0.326214 | False            |
|         100 |         3 | oco_first_touch | oco_first_touch__high_intensity__k1   | D              |                163982   |               -1.04825 |                     -1   |          2.80658 |              0.326214 | False            |
|         100 |         6 | oco_first_touch | oco_first_touch__low_cost_q50__k1     | D              |                147558   |               -1.03756 |                     -1   |          3.72545 |              0.371479 | False            |
|         100 |         3 | oco_first_touch | oco_first_touch__low_cost_q50__k1     | D              |                145738   |               -1.03162 |                     -1   |          2.67306 |              0.325984 | False            |
|         100 |         1 | oco_first_touch | oco_first_touch__all__k1              | D              |                137429   |               -1.05255 |                     -1   |          1.70082 |              0.228148 | False            |
|         100 |         1 | oco_first_touch | oco_first_touch__high_intensity__k1   | D              |                137429   |               -1.05255 |                     -1   |          1.70082 |              0.228148 | False            |
|         100 |         6 | oco_first_touch | oco_first_touch__low_cost_q30__k1     | D              |                125216   |               -1.03087 |                     -1   |          3.60912 |              0.369284 | False            |
|         100 |         3 | oco_first_touch | oco_first_touch__low_cost_q30__k1     | D              |                123504   |               -1.01788 |                     -1   |          2.59399 |              0.323846 | False            |
|         100 |         1 | oco_first_touch | oco_first_touch__low_cost_q50__k1     | D              |                121192   |               -1.03032 |                     -1   |          1.6153  |              0.225486 | False            |
|         100 |         6 | oco_first_touch | oco_first_touch__all__k3              | D              |                119283   |               -1.12109 |                     -1.1 |          4.17793 |              0.374803 | False            |
|         100 |         6 | oco_first_touch | oco_first_touch__high_intensity__k3   | D              |                119283   |               -1.12109 |                     -1.1 |          4.17793 |              0.374803 | False            |
|         100 |         6 | oco_first_touch | oco_first_touch__low_cost_q50__k3     | D              |                104145   |               -1.11639 |                     -1.1 |          3.94374 |              0.372089 | False            |
|         100 |         1 | oco_first_touch | oco_first_touch__low_cost_q30__k1     | D              |                101330   |               -1.01752 |                     -1   |          1.56891 |              0.222163 | False            |
|         100 |         6 | oco_first_touch | oco_first_touch__low_cost_q30__k3     | D              |                 86090.9 |               -1.12448 |                     -1.1 |          3.81962 |              0.367591 | False            |
|         100 |         3 | oco_first_touch | oco_first_touch__all__k3              | D              |                 72673.2 |               -1.11663 |                     -1.1 |          3.17812 |              0.333283 | False            |
|         100 |         3 | oco_first_touch | oco_first_touch__high_intensity__k3   | D              |                 72673.2 |               -1.11663 |                     -1.1 |          3.17812 |              0.333283 | False            |
|         100 |         3 | oco_first_touch | oco_first_touch__low_cost_q50__k3     | D              |                 61660.5 |               -1.10616 |                     -1.1 |          2.97468 |              0.330425 | False            |
|         100 |         6 | oco_first_touch | oco_first_touch__high_abs_vel_q70__k1 | D              |                 52485.2 |               -1.05694 |                     -1   |          4.21642 |              0.382152 | False            |

## No-Touch Top
_empty_

## Selection Summary
| library     |   rows_total |   rows_pass |   pass_rate |   mean_gross_all |   mean_baseline_z |
|:------------|-------------:|------------:|------------:|-----------------:|------------------:|
| directional |         6426 |         696 |     0.10831 |        -0.833821 |          0.236039 |
| oco         |          459 |           0 |     0       |        -1.19507  |          0.274855 |
