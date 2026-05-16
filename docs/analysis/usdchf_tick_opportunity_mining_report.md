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
|         100 |         6 | path_follow  | path_follow__high_intensity   | C              |                 70839.1 |              0.0231183 |                      0   |          4.38283 |              0.499341 | True             |
|         100 |         5 | path_follow  | path_follow__all              | C              |                 70839.1 |              0.0191942 |                      0   |          4.00879 |              0.496961 | True             |
|         100 |         5 | path_follow  | path_follow__high_intensity   | C              |                 70839.1 |              0.0191942 |                      0   |          4.00879 |              0.496961 | True             |
|         100 |         3 | path_follow  | path_follow__all              | C              |                 70835.5 |              0.027035  |                      0   |          3.12608 |              0.496543 | True             |
|         100 |         3 | path_follow  | path_follow__high_intensity   | C              |                 70835.5 |              0.027035  |                      0   |          3.12608 |              0.496543 | True             |
|         100 |         4 | path_follow  | path_follow__all              | C              |                 70835.5 |              0.0244666 |                      0   |          3.593   |              0.497804 | True             |
|         100 |         4 | path_follow  | path_follow__high_intensity   | C              |                 70835.5 |              0.0244666 |                      0   |          3.593   |              0.497804 | True             |
|         100 |         2 | path_follow  | path_follow__all              | C              |                 70835.4 |              0.0221912 |                      0   |          2.56579 |              0.495091 | True             |
|         100 |         2 | path_follow  | path_follow__high_intensity   | C              |                 70835.4 |              0.0221912 |                      0   |          2.56579 |              0.495091 | True             |
|         100 |         1 | path_follow  | path_follow__all              | C              |                 70835.4 |              0.0187078 |                      0   |          1.84448 |              0.488873 | True             |
|         100 |         1 | path_follow  | path_follow__high_intensity   | C              |                 70835.4 |              0.0187078 |                      0   |          1.84448 |              0.488873 | True             |
|         100 |         6 | path_follow  | path_follow__high_abs_vel_q70 | C              |                 57404.7 |              0.0278102 |                      0.1 |          4.57754 |              0.500664 | True             |
|         100 |         5 | path_follow  | path_follow__high_abs_vel_q70 | C              |                 57404.7 |              0.0254379 |                      0   |          4.18795 |              0.499056 | True             |
|         100 |         2 | path_follow  | path_follow__high_abs_vel_q70 | C              |                 57402.1 |              0.0277148 |                      0   |          2.68522 |              0.496242 | True             |
|         100 |         1 | path_follow  | path_follow__high_abs_vel_q70 | C              |                 57402.1 |              0.021252  |                      0   |          1.93094 |              0.489896 | True             |
|         100 |         3 | path_follow  | path_follow__high_abs_vel_q70 | C              |                 57401.9 |              0.0341905 |                      0   |          3.26861 |              0.498977 | True             |
|         100 |         4 | path_follow  | path_follow__high_abs_vel_q70 | C              |                 57401.9 |              0.0330647 |                      0.1 |          3.75481 |              0.500184 | True             |
|         100 |         6 | shock_revert | shock_revert__all             | C              |                 52860.6 |              0.0460151 |                      0.1 |          4.44835 |              0.502164 | True             |
|         100 |         6 | shock_revert | shock_revert__high_intensity  | C              |                 52860.6 |              0.0460151 |                      0.1 |          4.44835 |              0.502164 | True             |

## OCO Top
|   bar_ticks |   horizon | family          | state_id                            | quality_tier   |   annualized_test_fills |   mean_gross_pips_test |   median_gross_pips_test |   gross_std_test |   hit_rate_gross_test | selection_pass   |
|------------:|----------:|:----------------|:------------------------------------|:---------------|------------------------:|-----------------------:|-------------------------:|-----------------:|----------------------:|:-----------------|
|         100 |         6 | oco_first_touch | oco_first_touch__all__k0            | D              |                  175160 |               -1.15842 |                     -1.2 |          4.31463 |              0.370911 | False            |
|         100 |         6 | oco_first_touch | oco_first_touch__high_intensity__k0 | D              |                  175160 |               -1.15842 |                     -1.2 |          4.31463 |              0.370911 | False            |
|         100 |         5 | oco_first_touch | oco_first_touch__all__k0            | D              |                  175107 |               -1.16507 |                     -1.2 |          3.97088 |              0.360755 | False            |
|         100 |         5 | oco_first_touch | oco_first_touch__high_intensity__k0 | D              |                  175107 |               -1.16507 |                     -1.2 |          3.97088 |              0.360755 | False            |
|         100 |         4 | oco_first_touch | oco_first_touch__all__k0            | D              |                  175021 |               -1.15653 |                     -1.2 |          3.58586 |              0.349019 | False            |
|         100 |         4 | oco_first_touch | oco_first_touch__high_intensity__k0 | D              |                  175021 |               -1.15653 |                     -1.2 |          3.58586 |              0.349019 | False            |
|         100 |         3 | oco_first_touch | oco_first_touch__all__k0            | D              |                  174841 |               -1.15842 |                     -1.1 |          3.16598 |              0.331349 | False            |
|         100 |         3 | oco_first_touch | oco_first_touch__high_intensity__k0 | D              |                  174841 |               -1.15842 |                     -1.1 |          3.16598 |              0.331349 | False            |
|         100 |         2 | oco_first_touch | oco_first_touch__all__k0            | D              |                  174418 |               -1.14519 |                     -1.1 |          2.66986 |              0.303974 | False            |
|         100 |         2 | oco_first_touch | oco_first_touch__high_intensity__k0 | D              |                  174418 |               -1.14519 |                     -1.1 |          2.66986 |              0.303974 | False            |
|         100 |         6 | oco_first_touch | oco_first_touch__all__k1            | D              |                  173673 |               -1.14364 |                     -1.2 |          4.33823 |              0.374357 | False            |
|         100 |         6 | oco_first_touch | oco_first_touch__high_intensity__k1 | D              |                  173673 |               -1.14364 |                     -1.2 |          4.33823 |              0.374357 | False            |
|         100 |         5 | oco_first_touch | oco_first_touch__all__k1            | D              |                  173280 |               -1.14316 |                     -1.1 |          3.99699 |              0.3656   | False            |
|         100 |         5 | oco_first_touch | oco_first_touch__high_intensity__k1 | D              |                  173280 |               -1.14316 |                     -1.1 |          3.99699 |              0.3656   | False            |
|         100 |         1 | oco_first_touch | oco_first_touch__all__k0            | D              |                  172684 |               -1.1422  |                     -1   |          2.05622 |              0.244299 | False            |
|         100 |         1 | oco_first_touch | oco_first_touch__high_intensity__k0 | D              |                  172684 |               -1.1422  |                     -1   |          2.05622 |              0.244299 | False            |
|         100 |         4 | oco_first_touch | oco_first_touch__all__k1            | D              |                  172569 |               -1.13906 |                     -1.1 |          3.61816 |              0.354042 | False            |
|         100 |         4 | oco_first_touch | oco_first_touch__high_intensity__k1 | D              |                  172569 |               -1.13906 |                     -1.1 |          3.61816 |              0.354042 | False            |
|         100 |         3 | oco_first_touch | oco_first_touch__all__k1            | D              |                  171204 |               -1.14093 |                     -1.1 |          3.19658 |              0.336987 | False            |
|         100 |         3 | oco_first_touch | oco_first_touch__high_intensity__k1 | D              |                  171204 |               -1.14093 |                     -1.1 |          3.19658 |              0.336987 | False            |

## Selection Summary
| library     |   rows_total |   rows_pass |   pass_rate |   mean_annualized_fills_all |   mean_annualized_fills_pass |   mean_gross_all |   mean_gross_pass |   tier_a_rows |   tier_b_rows |   tier_c_rows |
|:------------|-------------:|------------:|------------:|----------------------------:|-----------------------------:|-----------------:|------------------:|--------------:|--------------:|--------------:|
| directional |         2988 |         389 |    0.130187 |                     7736.62 |                      24386.1 |        0.0881139 |         0.0425829 |             0 |            22 |           367 |
| oco         |         2142 |           0 |    0        |                    13256.4  |                        nan   |       -1.3057    |       nan         |             0 |             0 |             0 |
