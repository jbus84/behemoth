# Tick Opportunity ML Dataset Build

## Setup
- symbol: `AUDUSD`
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
| directional | 4627331 |          120 |      2369126 |     2258205 |                0.0357567 |          0.497791 |
| oco         | 4401172 |          120 |      2373137 |     2028035 |                1.56301   |          0.517971 |

## Directional Sample
| split   |   bar_ticks |   horizon | family       | state_id                      | quality_tier   |   target_gross_pips |   target_gross_pos |
|:--------|------------:|----------:|:-------------|:------------------------------|:---------------|--------------------:|-------------------:|
| test    |        1000 |         2 | path_follow  | path_follow__all              | B              |                97.1 |                  1 |
| test    |        1000 |         2 | path_follow  | path_follow__high_abs_vel_q70 | B              |                97.1 |                  1 |
| test    |        1000 |         2 | shock_revert | shock_revert__all             | B              |                97.1 |                  1 |
| test    |        1000 |         2 | path_follow  | path_follow__all              | B              |               -58.7 |                  0 |
| test    |        1000 |         2 | path_follow  | path_follow__all              | B              |               -58.7 |                  0 |
| test    |        1000 |         2 | path_follow  | path_follow__low_cost_q50     | B              |               -58.7 |                  0 |
| test    |        1000 |         2 | path_follow  | path_follow__low_cost_q30     | B              |               -58.7 |                  0 |
| test    |        1000 |         2 | path_follow  | path_follow__high_abs_vel_q70 | B              |               -58.7 |                  0 |
| test    |        1000 |         2 | path_follow  | path_follow__high_abs_vel_q70 | B              |               -58.7 |                  0 |
| test    |        1000 |         2 | shock_revert | shock_revert__all             | B              |               -58.7 |                  0 |
| test    |        1000 |         2 | shock_revert | shock_revert__all             | B              |               -58.7 |                  0 |
| test    |        1000 |         2 | path_follow  | path_follow__all              | B              |                58.5 |                  1 |
| test    |        1000 |         2 | path_follow  | path_follow__low_cost_q50     | B              |                58.5 |                  1 |
| test    |        1000 |         2 | path_follow  | path_follow__high_abs_vel_q70 | B              |                58.5 |                  1 |
| test    |        1000 |         2 | path_follow  | path_follow__all              | B              |                53.6 |                  1 |
| test    |        1000 |         2 | path_follow  | path_follow__low_cost_q50     | B              |                53.6 |                  1 |
| test    |        1000 |         2 | path_follow  | path_follow__high_abs_vel_q70 | B              |                53.6 |                  1 |
| test    |        1000 |         2 | shock_revert | shock_revert__all             | B              |               -53.6 |                  0 |
| test    |        1000 |         1 | path_follow  | path_follow__all              | B              |               -52.4 |                  0 |
| test    |        1000 |         1 | shock_revert | shock_revert__all             | B              |               -52.4 |                  0 |

## OCO Sample
| split   |   bar_ticks |   horizon | family                | state_id                                | quality_tier   |   target_gross_pips |   target_gross_pos |
|:--------|------------:|----------:|:----------------------|:----------------------------------------|:---------------|--------------------:|-------------------:|
| test    |        1000 |         6 | oco_first_touch_clean | oco_first_touch_clean__all__k5          | A              |               100   |                  1 |
| test    |        1000 |         6 | oco_first_touch_clean | oco_first_touch_clean__low_cost_q50__k5 | A              |               100   |                  1 |
| test    |        1000 |         2 | oco_first_touch_clean | oco_first_touch_clean__all__k3          | A              |                99.8 |                  1 |
| test    |        1000 |         6 | oco_first_touch_clean | oco_first_touch_clean__all__k5          | A              |                95.9 |                  1 |
| test    |        1000 |         6 | oco_first_touch_clean | oco_first_touch_clean__low_cost_q50__k5 | A              |                95.9 |                  1 |
| test    |        1000 |         1 | oco_first_touch_clean | oco_first_touch_clean__all__k2          | A              |                94.5 |                  1 |
| test    |        1000 |         4 | oco_first_touch_clean | oco_first_touch_clean__all__k5          | A              |                93.9 |                  1 |
| test    |        1000 |         4 | oco_first_touch_clean | oco_first_touch_clean__low_cost_q50__k5 | A              |                93.9 |                  1 |
| test    |        1000 |         5 | oco_first_touch_clean | oco_first_touch_clean__all__k5          | A              |                89.6 |                  1 |
| test    |        1000 |         5 | oco_first_touch_clean | oco_first_touch_clean__low_cost_q50__k5 | A              |                89.6 |                  1 |
| test    |        1000 |         3 | oco_first_touch_clean | oco_first_touch_clean__all__k5          | A              |                87.6 |                  1 |
| test    |        1000 |         3 | oco_first_touch_clean | oco_first_touch_clean__low_cost_q50__k5 | A              |                87.6 |                  1 |
| test    |        1000 |         6 | oco_first_touch_clean | oco_first_touch_clean__all__k5          | A              |                73.5 |                  1 |
| test    |        1000 |         6 | oco_first_touch_clean | oco_first_touch_clean__low_cost_q50__k5 | A              |                73.5 |                  1 |
| test    |        1000 |         4 | oco_first_touch_clean | oco_first_touch_clean__all__k5          | A              |                70.6 |                  1 |
| test    |        1000 |         4 | oco_first_touch_clean | oco_first_touch_clean__low_cost_q50__k5 | A              |                70.6 |                  1 |
| test    |        1000 |         6 | oco_first_touch_clean | oco_first_touch_clean__all__k5          | A              |                66.2 |                  1 |
| test    |        1000 |         6 | oco_first_touch_clean | oco_first_touch_clean__low_cost_q50__k5 | A              |                66.2 |                  1 |
| test    |        1000 |         6 | oco_first_touch_clean | oco_first_touch_clean__all__k5          | A              |                66.1 |                  1 |
| test    |        1000 |         6 | oco_first_touch_clean | oco_first_touch_clean__low_cost_q50__k5 | A              |                66.1 |                  1 |
