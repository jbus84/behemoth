# Tick Opportunity Mining Report

## Setup
- symbol: `GBPUSD`
- bar_ticks_grid: `100,1000,2000,5000,10000`
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
|   bar_ticks |   horizon | family          | state_id                                                | quality_tier   |   annualized_test_fills |   mean_gross_pips_test |   median_gross_pips_test |   gross_std_test |   hit_rate_gross_test | selection_pass   |
|------------:|----------:|:----------------|:--------------------------------------------------------|:---------------|------------------------:|-----------------------:|-------------------------:|-----------------:|----------------------:|:-----------------|
|       10000 |         6 | oco_first_touch | oco_first_touch__low_cost_q30__k10                      | C              |                1860.99  |              0.228677  |                     0    |          46.4853 |              0.499664 | True             |
|       10000 |         4 | oco_first_touch | oco_first_touch__low_cost_q30__k8                       | C              |                1860.16  |             -1.4132    |                    -1.3  |          38.3888 |              0.487936 | True             |
|       10000 |         5 | oco_first_touch | oco_first_touch__low_cost_q30__k10                      | C              |                1859.06  |              0.0273826 |                     0    |          42.5501 |              0.498658 | True             |
|       10000 |         4 | oco_first_touch | oco_first_touch__low_cost_q30__k10                      | C              |                1857.67  |             -0.831611  |                    -0.8  |          38.3485 |              0.493289 | True             |
|       10000 |         1 | oco_first_touch | oco_first_touch__low_cost_q30__k10                      | C              |                1781.89  |             -0.548117  |                    -0.1  |          19.7103 |              0.496513 | True             |
|        5000 |         3 | oco_first_touch | oco_first_touch__low_cost_q30_and_high_abs_vel_q70__k10 | C              |                1526.44  |              0.813813  |                     0.45 |          24.1677 |              0.504847 | True             |
|        5000 |         6 | oco_first_touch | oco_first_touch__london__k1                             | C              |                1171.02  |              0.273557  |                     1.3  |          36.0835 |              0.51938  | True             |
|        5000 |         6 | oco_first_touch | oco_first_touch__london__k2                             | C              |                1171.02  |             -0.760896  |                     0.6  |          36.1045 |              0.507321 | True             |
|        5000 |         5 | oco_first_touch | oco_first_touch__asia__k0                               | C              |                 935.623 |             -1.50151   |                    -0.2  |          31.7181 |              0.495699 | True             |
|        5000 |         5 | oco_first_touch | oco_first_touch__asia__k1                               | C              |                 935.623 |             -1.96419   |                    -0.95 |          31.7067 |              0.489247 | True             |
|       10000 |         4 | oco_first_touch | oco_first_touch__high_abs_vel_q70__k2                   | C              |                 933.584 |              0.888553  |                     0.7  |          37.4161 |              0.507559 | True             |
|       10000 |         4 | oco_first_touch | oco_first_touch__high_abs_vel_q70__k0                   | C              |                 933.584 |             -0.313175  |                    -0.6  |          37.4841 |              0.492441 | True             |
|       10000 |         1 | oco_first_touch | oco_first_touch__high_abs_vel_q70__k8                   | C              |                 929.055 |             -0.970238  |                    -0.9  |          20.7521 |              0.479437 | True             |
|       10000 |         5 | oco_first_touch | oco_first_touch__high_activity__k2                      | C              |                 752.156 |              1.16922   |                     1.1  |          41.1238 |              0.513441 | True             |
|       10000 |         5 | oco_first_touch | oco_first_touch__high_activity__k1                      | C              |                 752.156 |              0.618952  |                     0.7  |          41.1814 |              0.508065 | True             |
|       10000 |         5 | oco_first_touch | oco_first_touch__high_activity__k0                      | C              |                 752.156 |              0.120296  |                     0.65 |          41.1998 |              0.50672  | True             |
|       10000 |         6 | oco_first_touch | oco_first_touch__high_activity__k2                      | C              |                 752.156 |             -0.771237  |                    -1.4  |          44.7863 |              0.486559 | True             |
|       10000 |         6 | oco_first_touch | oco_first_touch__high_activity__k0                      | C              |                 752.156 |             -1.61465   |                    -1.85 |          44.791  |              0.482527 | True             |
|       10000 |         6 | oco_first_touch | oco_first_touch__high_activity__k1                      | C              |                 752.156 |             -1.75309   |                    -1.15 |          44.7812 |              0.487903 | True             |
|       10000 |         2 | oco_first_touch | oco_first_touch__low_cost_q30_and_high_abs_vel_q70__k0  | C              |                 751.794 |             -0.264345  |                     0.3  |          29.447  |              0.502488 | True             |

## Selection Summary
| library     |   rows_total |   rows_pass |   pass_rate |   mean_annualized_fills_all |   mean_annualized_fills_pass |   mean_gross_all |   mean_gross_pass |   tier_a_rows |   tier_b_rows |   tier_c_rows |
|:------------|-------------:|------------:|------------:|----------------------------:|-----------------------------:|-----------------:|------------------:|--------------:|--------------:|--------------:|
| directional |         4962 |         549 |    0.110641 |                     7057.99 |                    27744.6   |        -0.190927 |          0.103038 |             0 |            67 |           482 |
| oco         |         3570 |         152 |    0.042577 |                    13339.6  |                      623.975 |        -0.760342 |         -0.241703 |             0 |             0 |           152 |
