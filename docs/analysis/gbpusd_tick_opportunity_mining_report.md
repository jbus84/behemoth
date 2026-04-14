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
|   bar_ticks |   horizon | family       | state_id                      | quality_tier   |   annualized_test_fills |   mean_gross_pips_test |   median_gross_pips_test |   gross_std_test |   hit_rate_gross_test | selection_pass   |
|------------:|----------:|:-------------|:------------------------------|:---------------|------------------------:|-----------------------:|-------------------------:|-----------------:|----------------------:|:-----------------|
|         100 |         6 | path_follow  | path_follow__all              | C              |                 98049.7 |              0.0481679 |                      0.1 |          5.10623 |              0.501484 | True             |
|         100 |         4 | path_follow  | path_follow__all              | C              |                 98049.7 |              0.0475108 |                      0   |          4.20802 |              0.498598 | True             |
|         100 |         5 | path_follow  | path_follow__all              | C              |                 98049.7 |              0.039818  |                      0.1 |          4.6867  |              0.500184 | True             |
|         100 |         3 | path_follow  | path_follow__all              | C              |                 98049.7 |              0.030373  |                      0   |          3.68094 |              0.497236 | True             |
|         100 |         2 | path_follow  | path_follow__all              | C              |                 98049.7 |              0.0266003 |                      0   |          2.99936 |              0.496725 | True             |
|         100 |         1 | path_follow  | path_follow__all              | C              |                 98049.7 |              0.0105535 |                      0   |          2.12657 |              0.491208 | True             |
|         100 |         6 | path_follow  | path_follow__high_abs_vel_q70 | C              |                 82079.7 |              0.0625732 |                      0.1 |          5.28318 |              0.502476 | True             |
|         100 |         4 | path_follow  | path_follow__high_abs_vel_q70 | C              |                 82079.7 |              0.0553185 |                      0   |          4.35264 |              0.498282 | True             |
|         100 |         5 | path_follow  | path_follow__high_abs_vel_q70 | C              |                 82079.7 |              0.0506267 |                      0.1 |          4.84746 |              0.500532 | True             |
|         100 |         3 | path_follow  | path_follow__high_abs_vel_q70 | C              |                 82079.7 |              0.0416833 |                      0   |          3.81104 |              0.498417 | True             |
|         100 |         2 | path_follow  | path_follow__high_abs_vel_q70 | C              |                 82079.7 |              0.0330016 |                      0   |          3.11702 |              0.497927 | True             |
|         100 |         1 | path_follow  | path_follow__high_abs_vel_q70 | C              |                 82079.7 |              0.0134836 |                      0   |          2.20728 |              0.491361 | True             |
|         100 |         6 | path_follow  | path_follow__low_cost_q50     | C              |                 80879.8 |              0.0478193 |                      0.1 |          5.15726 |              0.501656 | True             |
|         100 |         4 | path_follow  | path_follow__low_cost_q50     | C              |                 80879.8 |              0.0462298 |                      0   |          4.24373 |              0.498368 | True             |
|         100 |         5 | path_follow  | path_follow__low_cost_q50     | C              |                 80879.8 |              0.0426017 |                      0.1 |          4.72407 |              0.500937 | True             |
|         100 |         3 | path_follow  | path_follow__low_cost_q50     | C              |                 80879.8 |              0.030551  |                      0   |          3.70701 |              0.497673 | True             |
|         100 |         2 | path_follow  | path_follow__low_cost_q50     | C              |                 80879.8 |              0.0258844 |                      0   |          3.0283  |              0.497115 | True             |
|         100 |         1 | path_follow  | path_follow__low_cost_q50     | C              |                 80879.8 |              0.0121288 |                      0   |          2.13937 |              0.490874 | True             |
|         100 |         6 | shock_revert | shock_revert__all             | C              |                 73167.6 |              0.0679428 |                      0.1 |          5.1688  |              0.505041 | True             |
|         100 |         4 | shock_revert | shock_revert__all             | C              |                 73167.6 |              0.0648386 |                      0.1 |          4.26306 |              0.500336 | True             |

## OCO Top
|   bar_ticks |   horizon | family                | state_id                                                     | quality_tier   |   annualized_test_fills |   mean_gross_pips_test |   median_gross_pips_test |   gross_std_test |   hit_rate_gross_test | selection_pass   |
|------------:|----------:|:----------------------|:-------------------------------------------------------------|:---------------|------------------------:|-----------------------:|-------------------------:|-----------------:|----------------------:|:-----------------|
|         100 |         5 | oco_first_touch_clean | oco_first_touch_clean__all__k2                               | C              |                171705   |              0.22905   |                      0   |          4.04866 |              0.494307 | True             |
|         100 |         6 | oco_first_touch_clean | oco_first_touch_clean__all__k2                               | C              |                163563   |              0.570863  |                      0.3 |          4.32222 |              0.525153 | True             |
|         100 |         5 | oco_first_touch_clean | oco_first_touch_clean__low_cost_q50__k2                      | C              |                143636   |              0.274591  |                      0   |          4.04516 |              0.499815 | True             |
|         100 |         6 | oco_first_touch_clean | oco_first_touch_clean__low_cost_q50__k2                      | B              |                136535   |              0.625929  |                      0.3 |          4.3244  |              0.53083  | True             |
|         100 |         5 | oco_first_touch_clean | oco_first_touch_clean__low_cost_q30__k2                      | C              |                106517   |              0.28262   |                      0.1 |          4.00777 |              0.502623 | True             |
|         100 |         6 | oco_first_touch_clean | oco_first_touch_clean__low_cost_q30__k2                      | B              |                101142   |              0.633625  |                      0.4 |          4.28968 |              0.533845 | True             |
|         100 |         5 | oco_first_touch_clean | oco_first_touch_clean__high_abs_vel_q70__k2                  | C              |                 63008.3 |              0.438887  |                      0.2 |          4.19918 |              0.518247 | True             |
|         100 |         6 | oco_first_touch_clean | oco_first_touch_clean__high_abs_vel_q70__k2                  | B              |                 59359   |              0.823046  |                      0.6 |          4.50985 |              0.549955 | True             |
|         100 |         6 | oco_first_touch_clean | oco_first_touch_clean__high_range_q70__k3                    | C              |                 58113.7 |              0.0902387 |                     -0.1 |          5.10631 |              0.484664 | True             |
|         100 |         4 | oco_first_touch_clean | oco_first_touch_clean__high_range_q70__k2                    | C              |                 54648   |              0.118384  |                      0   |          4.0842  |              0.490891 | True             |
|         100 |         6 | oco_first_touch_clean | oco_first_touch_clean__ny_overlap__k3                        | C              |                 53166.3 |             -0.0203961 |                     -0.2 |          4.89652 |              0.480166 | True             |
|         100 |         5 | oco_first_touch_clean | oco_first_touch_clean__high_range_q70__k2                    | B              |                 50928.8 |              0.581883  |                      0.3 |          4.40203 |              0.530858 | True             |
|         100 |         4 | oco_first_touch_clean | oco_first_touch_clean__ny_overlap__k2                        | C              |                 50790.7 |              0.100319  |                      0   |          3.88543 |              0.488584 | True             |
|         100 |         5 | oco_first_touch_clean | oco_first_touch_clean__ny_overlap__k2                        | B              |                 47766.5 |              0.506146  |                      0.3 |          4.22605 |              0.527435 | True             |
|         100 |         6 | oco_first_touch_clean | oco_first_touch_clean__high_range_q70__k2                    | B              |                 47660.2 |              1.01043   |                      0.7 |          4.71682 |              0.564212 | True             |
|         100 |         4 | oco_first_touch_clean | oco_first_touch_clean__high_abs_vel_q80__k2                  | C              |                 47286.3 |              0.0723373 |                     -0.1 |          3.96971 |              0.484718 | True             |
|         100 |         6 | oco_first_touch_clean | oco_first_touch_clean__ny_overlap__k2                        | A              |                 44759.3 |              0.902164  |                      0.7 |          4.51884 |              0.558849 | True             |
|         100 |         5 | oco_first_touch_clean | oco_first_touch_clean__high_abs_vel_q80__k2                  | B              |                 44383.7 |              0.500744  |                      0.3 |          4.26508 |              0.522297 | True             |
|         100 |         5 | oco_first_touch_clean | oco_first_touch_clean__low_cost_q30_and_high_abs_vel_q70__k2 | C              |                 43150.9 |              0.441666  |                      0.2 |          4.14717 |              0.521117 | True             |
|         100 |         6 | oco_first_touch_clean | oco_first_touch_clean__high_abs_vel_q80__k2                  | B              |                 41692.9 |              0.892364  |                      0.6 |          4.58787 |              0.555259 | True             |

## Selection Summary
| library     |   rows_total |   rows_pass |   pass_rate |   mean_annualized_fills_all |   mean_annualized_fills_pass |   mean_gross_all |   mean_gross_pass |   tier_a_rows |   tier_b_rows |   tier_c_rows |
|:------------|-------------:|------------:|------------:|----------------------------:|-----------------------------:|-----------------:|------------------:|--------------:|--------------:|--------------:|
| directional |         2082 |         408 |    0.195965 |                     12429.2 |                     27921.3  |        0.0359331 |         0.0934831 |             0 |            34 |           374 |
| oco         |         2160 |         548 |    0.253704 |                     15166.2 |                      6812.81 |        0.344199  |         4.28487   |             8 |            59 |           481 |
