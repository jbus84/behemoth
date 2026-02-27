# Tick Opportunity Mining Report

## Setup
- symbol: `USDJPY`
- bar_ticks_grid: `100,1000,2000`
- horizons: `1,2,3,4,5,6`
- train_years: `2022,2023,2024`
- test_year: `2025`
- min_annual_fills: `5000.0`
- inclusion_metric: `mean`

## Directional Top
|   bar_ticks |   horizon | family       | state_id                       | quality_tier   |   annualized_test_fills |   mean_gross_pips_test |   median_gross_pips_test |   gross_std_test |   hit_rate_gross_test | selection_pass   |
|------------:|----------:|:-------------|:-------------------------------|:---------------|------------------------:|-----------------------:|-------------------------:|-----------------:|----------------------:|:-----------------|
|         100 |         6 | path_follow  | path_follow__all               | C              |                  141106 |              0.0414742 |                      0.1 |          6.30214 |              0.500068 | True             |
|         100 |         5 | path_follow  | path_follow__all               | C              |                  141104 |              0.0403823 |                      0   |          5.77718 |              0.499324 | True             |
|         100 |         4 | path_follow  | path_follow__all               | C              |                  141104 |              0.0306459 |                      0   |          5.17722 |              0.49872  | True             |
|         100 |         3 | path_follow  | path_follow__all               | C              |                  141104 |              0.0274329 |                      0.1 |          4.49338 |              0.500398 | True             |
|         100 |         2 | path_follow  | path_follow__all               | C              |                  141104 |              0.0217479 |                      0   |          3.72173 |              0.497938 | True             |
|         100 |         1 | path_follow  | path_follow__all               | C              |                  141103 |              0.0141718 |                      0   |          2.69057 |              0.496234 | True             |
|         100 |         6 | path_follow  | path_follow__high_abs_vel_q70  | C              |                  125148 |              0.0407182 |                      0   |          6.401   |              0.499238 | True             |
|         100 |         5 | path_follow  | path_follow__high_abs_vel_q70  | C              |                  125146 |              0.0409688 |                      0   |          5.87252 |              0.498649 | True             |
|         100 |         4 | path_follow  | path_follow__high_abs_vel_q70  | C              |                  125146 |              0.0302613 |                      0   |          5.2714  |              0.497807 | True             |
|         100 |         3 | path_follow  | path_follow__high_abs_vel_q70  | C              |                  125146 |              0.0237958 |                      0   |          4.57189 |              0.499619 | True             |
|         100 |         2 | path_follow  | path_follow__high_abs_vel_q70  | C              |                  125146 |              0.0217349 |                      0   |          3.79969 |              0.497462 | True             |
|         100 |         1 | path_follow  | path_follow__high_abs_vel_q70  | C              |                  125146 |              0.0147305 |                      0   |          2.75027 |              0.496323 | True             |
|         100 |         6 | shock_revert | shock_revert__all              | C              |                  106522 |              0.0650611 |                      0.1 |          6.38177 |              0.501512 | True             |
|         100 |         5 | shock_revert | shock_revert__all              | C              |                  106520 |              0.0697038 |                      0.1 |          5.86446 |              0.501639 | True             |
|         100 |         4 | shock_revert | shock_revert__all              | C              |                  106520 |              0.0640468 |                      0.1 |          5.26374 |              0.500707 | True             |
|         100 |         3 | shock_revert | shock_revert__all              | C              |                  106520 |              0.0522854 |                      0.1 |          4.5678  |              0.503297 | True             |
|         100 |         2 | shock_revert | shock_revert__all              | C              |                  106520 |              0.0364251 |                      0.1 |          3.80165 |              0.500528 | True             |
|         100 |         1 | shock_revert | shock_revert__all              | C              |                  106520 |              0.0238818 |                      0   |          2.76244 |              0.499001 | True             |
|         100 |         6 | shock_revert | shock_revert__high_abs_vel_q70 | C              |                  101625 |              0.0591818 |                      0   |          6.44993 |              0.49999  | True             |
|         100 |         5 | shock_revert | shock_revert__high_abs_vel_q70 | C              |                  101623 |              0.0667829 |                      0.1 |          5.92737 |              0.500123 | True             |

## OCO Top
|   bar_ticks |   horizon | family                | state_id                          | quality_tier   |   annualized_test_fills |   mean_gross_pips_test |   median_gross_pips_test |   gross_std_test |   hit_rate_gross_test | selection_pass   |
|------------:|----------:|:----------------------|:----------------------------------|:---------------|------------------------:|-----------------------:|-------------------------:|-----------------:|----------------------:|:-----------------|
|         100 |         6 | oco_first_touch       | oco_first_touch__all__k2          | C              |                  336978 |               0.205285 |                      0.2 |          5.78766 |              0.51776  | True             |
|         100 |         5 | oco_first_touch       | oco_first_touch__all__k2          | C              |                  334769 |               0.210905 |                      0.2 |          5.23775 |              0.519362 | True             |
|         100 |         4 | oco_first_touch       | oco_first_touch__all__k2          | C              |                  330216 |               0.216374 |                      0.2 |          4.62845 |              0.52239  | True             |
|         100 |         3 | oco_first_touch       | oco_first_touch__all__k2          | C              |                  319522 |               0.219353 |                      0.2 |          3.94228 |              0.528444 | True             |
|         100 |         6 | oco_first_touch       | oco_first_touch__all__k3          | C              |                  318290 |               0.176796 |                      0.2 |          5.51449 |              0.520781 | True             |
|         100 |         5 | oco_first_touch       | oco_first_touch__all__k3          | C              |                  307297 |               0.185418 |                      0.1 |          4.989   |              0.522707 | True             |
|         100 |         2 | oco_first_touch       | oco_first_touch__all__k2          | C              |                  291875 |               0.220044 |                      0.2 |          3.16364 |              0.539128 | True             |
|         100 |         4 | oco_first_touch       | oco_first_touch__all__k3          | C              |                  289434 |               0.191413 |                      0.1 |          4.42464 |              0.526871 | True             |
|         100 |         5 | oco_first_touch_clean | oco_first_touch_clean__all__k3    | A              |                  262934 |               1.28773  |                      0.7 |          3.94258 |              0.602161 | True             |
|         100 |         2 | oco_first_touch_clean | oco_first_touch_clean__all__k2    | B              |                  260298 |               0.782092 |                      0.4 |          2.54581 |              0.599669 | True             |
|         100 |         6 | oco_first_touch_clean | oco_first_touch_clean__all__k3    | A              |                  259709 |               1.6433   |                      1   |          4.27739 |              0.624333 | True             |
|         100 |         4 | oco_first_touch_clean | oco_first_touch_clean__all__k3    | B              |                  259535 |               0.948903 |                      0.5 |          3.5853  |              0.582728 | True             |
|         100 |         3 | oco_first_touch_clean | oco_first_touch_clean__all__k2    | A              |                  259311 |               1.27619  |                      0.8 |          3.05844 |              0.635772 | True             |
|         100 |         3 | oco_first_touch       | oco_first_touch__all__k3          | C              |                  258968 |               0.202262 |                      0.2 |          3.80838 |              0.535229 | True             |
|         100 |         4 | oco_first_touch_clean | oco_first_touch_clean__all__k2    | A              |                  244303 |               1.80621  |                      1.2 |          3.51513 |              0.674227 | True             |
|         100 |         3 | oco_first_touch_clean | oco_first_touch_clean__all__k3    | B              |                  242265 |               0.661908 |                      0.3 |          3.16304 |              0.569694 | True             |
|         100 |         5 | oco_first_touch_clean | oco_first_touch_clean__all__k2    | A              |                  227419 |               2.33898  |                      1.7 |          3.89781 |              0.709991 | True             |
|         100 |         6 | oco_first_touch       | oco_first_touch__all__k5          | C              |                  222807 |               0.234618 |                      0.2 |          5.29409 |              0.524872 | True             |
|         100 |         6 | oco_first_touch       | oco_first_touch__low_cost_q50__k2 | C              |                  220474 |               0.201168 |                      0.2 |          5.65515 |              0.518456 | True             |
|         100 |         5 | oco_first_touch       | oco_first_touch__low_cost_q50__k2 | C              |                  219035 |               0.208226 |                      0.2 |          5.10913 |              0.519673 | True             |

## Selection Summary
| library     |   rows_total |   rows_pass |   pass_rate |   mean_annualized_fills_all |   mean_annualized_fills_pass |   mean_gross_all |   mean_gross_pass |   tier_a_rows |   tier_b_rows |   tier_c_rows |
|:------------|-------------:|------------:|------------:|----------------------------:|-----------------------------:|-----------------:|------------------:|--------------:|--------------:|--------------:|
| directional |         2088 |         490 |    0.234674 |                     17586   |                      33033.7 |        0.0599562 |          0.135158 |             0 |            49 |           441 |
| oco         |         2160 |         995 |    0.460648 |                     24050.3 |                      45048   |        3.28519   |          1.92264  |           146 |           408 |           441 |
