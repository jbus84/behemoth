# Tick Opportunity Mining Report

## Setup
- symbol: `GBPUSD`
- bar_ticks_grid: `100,1000,2000`
- horizons: `1,2,3,4,5,6`
- train_years: `2022,2023,2024`
- test_year: `2025`
- min_annual_fills: `5000.0`
- inclusion_metric: `mean`

## Directional Top
|   bar_ticks |   horizon | family      | state_id                      | quality_tier   |   annualized_test_fills |   mean_gross_pips_test |   median_gross_pips_test |   gross_std_test |   hit_rate_gross_test | selection_pass   |
|------------:|----------:|:------------|:------------------------------|:---------------|------------------------:|-----------------------:|-------------------------:|-----------------:|----------------------:|:-----------------|
|         100 |         6 | path_follow | path_follow__all              | C              |                 98049.7 |              0.0481679 |                      0.1 |          5.10623 |              0.501484 | True             |
|         100 |         6 | path_follow | path_follow__high_intensity   | C              |                 98049.7 |              0.0481679 |                      0.1 |          5.10623 |              0.501484 | True             |
|         100 |         4 | path_follow | path_follow__all              | C              |                 98049.7 |              0.0475108 |                      0   |          4.20802 |              0.498598 | True             |
|         100 |         4 | path_follow | path_follow__high_intensity   | C              |                 98049.7 |              0.0475108 |                      0   |          4.20802 |              0.498598 | True             |
|         100 |         5 | path_follow | path_follow__all              | C              |                 98049.7 |              0.039818  |                      0.1 |          4.6867  |              0.500184 | True             |
|         100 |         5 | path_follow | path_follow__high_intensity   | C              |                 98049.7 |              0.039818  |                      0.1 |          4.6867  |              0.500184 | True             |
|         100 |         3 | path_follow | path_follow__all              | C              |                 98049.7 |              0.030373  |                      0   |          3.68094 |              0.497236 | True             |
|         100 |         3 | path_follow | path_follow__high_intensity   | C              |                 98049.7 |              0.030373  |                      0   |          3.68094 |              0.497236 | True             |
|         100 |         2 | path_follow | path_follow__all              | C              |                 98049.7 |              0.0266003 |                      0   |          2.99936 |              0.496725 | True             |
|         100 |         2 | path_follow | path_follow__high_intensity   | C              |                 98049.7 |              0.0266003 |                      0   |          2.99936 |              0.496725 | True             |
|         100 |         1 | path_follow | path_follow__all              | C              |                 98049.7 |              0.0105535 |                      0   |          2.12657 |              0.491208 | True             |
|         100 |         1 | path_follow | path_follow__high_intensity   | C              |                 98049.7 |              0.0105535 |                      0   |          2.12657 |              0.491208 | True             |
|         100 |         6 | path_follow | path_follow__high_abs_vel_q70 | C              |                 82079.7 |              0.0625732 |                      0.1 |          5.28318 |              0.502476 | True             |
|         100 |         4 | path_follow | path_follow__high_abs_vel_q70 | C              |                 82079.7 |              0.0553185 |                      0   |          4.35264 |              0.498282 | True             |
|         100 |         5 | path_follow | path_follow__high_abs_vel_q70 | C              |                 82079.7 |              0.0506267 |                      0.1 |          4.84746 |              0.500532 | True             |
|         100 |         3 | path_follow | path_follow__high_abs_vel_q70 | C              |                 82079.7 |              0.0416833 |                      0   |          3.81104 |              0.498417 | True             |
|         100 |         2 | path_follow | path_follow__high_abs_vel_q70 | C              |                 82079.7 |              0.0330016 |                      0   |          3.11702 |              0.497927 | True             |
|         100 |         1 | path_follow | path_follow__high_abs_vel_q70 | C              |                 82079.7 |              0.0134836 |                      0   |          2.20728 |              0.491361 | True             |
|         100 |         6 | path_follow | path_follow__low_cost_q50     | C              |                 80879.8 |              0.0478193 |                      0.1 |          5.15726 |              0.501656 | True             |
|         100 |         4 | path_follow | path_follow__low_cost_q50     | C              |                 80879.8 |              0.0462298 |                      0   |          4.24373 |              0.498368 | True             |

## OCO Top
|   bar_ticks |   horizon | family          | state_id                            | quality_tier   |   annualized_test_fills |   mean_gross_pips_test |   median_gross_pips_test |   gross_std_test |   hit_rate_gross_test | selection_pass   |
|------------:|----------:|:----------------|:------------------------------------|:---------------|------------------------:|-----------------------:|-------------------------:|-----------------:|----------------------:|:-----------------|
|         100 |         6 | oco_first_touch | oco_first_touch__all__k0            | D              |                  244671 |              -0.927256 |                     -1   |          4.99374 |              0.404236 | False            |
|         100 |         6 | oco_first_touch | oco_first_touch__high_intensity__k0 | D              |                  244671 |              -0.927256 |                     -1   |          4.99374 |              0.404236 | False            |
|         100 |         5 | oco_first_touch | oco_first_touch__all__k0            | D              |                  244601 |              -0.925297 |                     -1   |          4.57558 |              0.396802 | False            |
|         100 |         5 | oco_first_touch | oco_first_touch__high_intensity__k0 | D              |                  244601 |              -0.925297 |                     -1   |          4.57558 |              0.396802 | False            |
|         100 |         4 | oco_first_touch | oco_first_touch__all__k0            | D              |                  244471 |              -0.922419 |                     -1   |          4.11467 |              0.388066 | False            |
|         100 |         4 | oco_first_touch | oco_first_touch__high_intensity__k0 | D              |                  244471 |              -0.922419 |                     -1   |          4.11467 |              0.388066 | False            |
|         100 |         3 | oco_first_touch | oco_first_touch__all__k0            | D              |                  244256 |              -0.927359 |                     -1   |          3.59041 |              0.372283 | False            |
|         100 |         3 | oco_first_touch | oco_first_touch__high_intensity__k0 | D              |                  244256 |              -0.927359 |                     -1   |          3.59041 |              0.372283 | False            |
|         100 |         2 | oco_first_touch | oco_first_touch__all__k0            | D              |                  243787 |              -0.925579 |                     -0.9 |          2.96614 |              0.347854 | False            |
|         100 |         2 | oco_first_touch | oco_first_touch__high_intensity__k0 | D              |                  243787 |              -0.925579 |                     -0.9 |          2.96614 |              0.347854 | False            |
|         100 |         6 | oco_first_touch | oco_first_touch__all__k1            | D              |                  242984 |              -0.903654 |                     -1   |          5.01534 |              0.407947 | False            |
|         100 |         6 | oco_first_touch | oco_first_touch__high_intensity__k1 | D              |                  242984 |              -0.903654 |                     -1   |          5.01534 |              0.407947 | False            |
|         100 |         5 | oco_first_touch | oco_first_touch__all__k1            | D              |                  242531 |              -0.904818 |                     -0.9 |          4.59839 |              0.401116 | False            |
|         100 |         5 | oco_first_touch | oco_first_touch__high_intensity__k1 | D              |                  242531 |              -0.904818 |                     -0.9 |          4.59839 |              0.401116 | False            |
|         100 |         4 | oco_first_touch | oco_first_touch__all__k1            | D              |                  241810 |              -0.906678 |                     -0.9 |          4.13857 |              0.391858 | False            |
|         100 |         4 | oco_first_touch | oco_first_touch__high_intensity__k1 | D              |                  241810 |              -0.906678 |                     -0.9 |          4.13857 |              0.391858 | False            |
|         100 |         1 | oco_first_touch | oco_first_touch__all__k0            | D              |                  241264 |              -0.913569 |                     -0.9 |          2.1661  |              0.300276 | False            |
|         100 |         1 | oco_first_touch | oco_first_touch__high_intensity__k0 | D              |                  241264 |              -0.913569 |                     -0.9 |          2.1661  |              0.300276 | False            |
|         100 |         3 | oco_first_touch | oco_first_touch__all__k1            | D              |                  240499 |              -0.902836 |                     -0.9 |          3.61592 |              0.377361 | False            |
|         100 |         3 | oco_first_touch | oco_first_touch__high_intensity__k1 | D              |                  240499 |              -0.902836 |                     -0.9 |          3.61592 |              0.377361 | False            |

## Selection Summary
| library     |   rows_total |   rows_pass |   pass_rate |   mean_annualized_fills_all |   mean_annualized_fills_pass |   mean_gross_all |   mean_gross_pass |   tier_a_rows |   tier_b_rows |   tier_c_rows |
|:------------|-------------:|------------:|------------:|----------------------------:|-----------------------------:|-----------------:|------------------:|--------------:|--------------:|--------------:|
| directional |         2982 |         549 |    0.184105 |                     11415.7 |                      27744.6 |        0.0353346 |          0.103038 |             0 |            67 |           482 |
| oco         |         2142 |           0 |    0        |                     21290   |                        nan   |       -0.998145  |        nan        |             0 |             0 |             0 |
