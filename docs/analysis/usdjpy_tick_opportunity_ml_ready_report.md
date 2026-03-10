# Tick Opportunity ML Dataset Build

## Setup
- symbol: `USDJPY`
- train_years: `2022,2023,2024`
- test_year: `2025`
- selection_required: `True`
- min_quality_tier: `C`
- max_candidates_per_library: `120`
- max_events_per_candidate: `20000`
- oco_hold_mode: `from_touch`
- oco_include_no_touch: `True`

## Summary
| library     |    rows |   candidates |   train_rows |   test_rows |   mean_target_gross_pips |   target_pos_rate |
|:------------|--------:|-------------:|-------------:|------------:|-------------------------:|------------------:|
| directional | 4209513 |          120 |      2400000 |     1809513 |                0.0914834 |          0.502782 |
| oco         | 4776128 |          120 |      2400000 |     2376128 |                2.37575   |          0.60109  |

## Directional Sample
| split   |   bar_ticks |   horizon | family               | state_id                               | quality_tier   |   target_gross_pips |   target_gross_pos |
|:--------|------------:|----------:|:---------------------|:---------------------------------------|:---------------|--------------------:|-------------------:|
| test    |        1000 |         3 | path_follow          | path_follow__all                       | B              |               202.4 |                  1 |
| test    |        1000 |         3 | shock_revert         | shock_revert__all                      | B              |               202.4 |                  1 |
| test    |        1000 |         3 | path_follow          | path_follow__high_abs_vel_q70          | B              |               202.4 |                  1 |
| test    |        1000 |         3 | shock_revert         | shock_revert__high_abs_vel_q70         | B              |               202.4 |                  1 |
| test    |        1000 |         3 | path_follow          | path_follow__high_range_q70            | B              |               202.4 |                  1 |
| test    |        1000 |         3 | shock_extreme_revert | shock_extreme_revert__all              | B              |               202.4 |                  1 |
| test    |        1000 |         3 | path_follow          | path_follow__low_cost_q50              | B              |               202.4 |                  1 |
| test    |        1000 |         3 | path_follow          | path_follow__high_abs_vel_q80          | B              |               202.4 |                  1 |
| test    |        1000 |         3 | shock_extreme_revert | shock_extreme_revert__high_abs_vel_q70 | B              |               202.4 |                  1 |
| test    |        1000 |         3 | shock_revert         | shock_revert__high_range_q70           | B              |               202.4 |                  1 |
| test    |        1000 |         2 | path_follow          | path_follow__all                       | B              |              -196.5 |                  0 |
| test    |        1000 |         2 | path_follow          | path_follow__high_abs_vel_q70          | B              |              -196.5 |                  0 |
| test    |        1000 |         2 | path_follow          | path_follow__low_cost_q50              | B              |              -196.5 |                  0 |
| test    |        1000 |         2 | path_follow          | path_follow__high_abs_vel_q80          | B              |              -196.5 |                  0 |
| test    |        2000 |         4 | path_follow          | path_follow__all                       | B              |               190.9 |                  1 |
| test    |        1000 |         6 | path_follow          | path_follow__all                       | B              |               189.8 |                  1 |
| test    |        1000 |         6 | shock_revert         | shock_revert__all                      | B              |               189.8 |                  1 |
| test    |        1000 |         6 | path_follow          | path_follow__high_abs_vel_q70          | B              |               189.8 |                  1 |
| test    |        1000 |         6 | shock_revert         | shock_revert__high_abs_vel_q70         | B              |               189.8 |                  1 |
| test    |        1000 |         6 | path_follow          | path_follow__high_range_q70            | B              |               189.8 |                  1 |

## OCO Sample
| split   |   bar_ticks |   horizon | family                | state_id                                    | quality_tier   |   target_gross_pips |   target_gross_pos |
|:--------|------------:|----------:|:----------------------|:--------------------------------------------|:---------------|--------------------:|-------------------:|
| test    |        1000 |         3 | oco_first_touch_clean | oco_first_touch_clean__all__k10             | A              |              -203.5 |                  0 |
| test    |        1000 |         3 | oco_first_touch_clean | oco_first_touch_clean__all__k10             | A              |              -202.4 |                  0 |
| test    |        1000 |         3 | oco_first_touch_clean | oco_first_touch_clean__all__k8              | A              |              -201.5 |                  0 |
| test    |        1000 |         3 | oco_first_touch_clean | oco_first_touch_clean__all__k8              | A              |              -200.4 |                  0 |
| test    |        1000 |         2 | oco_first_touch_clean | oco_first_touch_clean__all__k3              | A              |               199.6 |                  1 |
| test    |        1000 |         3 | oco_first_touch_clean | oco_first_touch_clean__all__k8              | A              |              -199.6 |                  0 |
| test    |        1000 |         3 | oco_first_touch_clean | oco_first_touch_clean__all__k5              | A              |              -198.5 |                  0 |
| test    |        1000 |         3 | oco_first_touch_clean | oco_first_touch_clean__low_cost_q50__k5     | A              |              -198.5 |                  0 |
| test    |        1000 |         2 | oco_first_touch_clean | oco_first_touch_clean__all__k5              | A              |               197.6 |                  1 |
| test    |        1000 |         2 | oco_first_touch_clean | oco_first_touch_clean__low_cost_q50__k5     | A              |               197.6 |                  1 |
| test    |        1000 |         3 | oco_first_touch_clean | oco_first_touch_clean__all__k5              | A              |              -197.4 |                  0 |
| test    |        1000 |         3 | oco_first_touch_clean | oco_first_touch_clean__low_cost_q50__k5     | A              |              -197.4 |                  0 |
| test    |        1000 |         3 | oco_first_touch_clean | oco_first_touch_clean__all__k5              | A              |              -196.6 |                  0 |
| test    |        1000 |         3 | oco_first_touch_clean | oco_first_touch_clean__low_cost_q50__k5     | A              |              -196.6 |                  0 |
| test    |        1000 |         3 | oco_first_touch_clean | oco_first_touch_clean__all__k3              | A              |              -196.5 |                  0 |
| test    |         100 |         5 | oco_first_touch_clean | oco_first_touch_clean__low_cost_q30__k2     | A              |              -196.1 |                  0 |
| test    |         100 |         6 | oco_first_touch_clean | oco_first_touch_clean__high_abs_vel_q70__k2 | A              |               196   |                  1 |
| test    |         100 |         4 | oco_first_touch_clean | oco_first_touch_clean__low_cost_q50__k2     | A              |              -194.8 |                  0 |
| test    |        1000 |         2 | oco_first_touch_clean | oco_first_touch_clean__all__k8              | A              |               194.6 |                  1 |
| test    |        1000 |         1 | oco_first_touch_clean | oco_first_touch_clean__all__k3              | A              |               193.5 |                  1 |
