# Tick Opportunity ML Dataset Build

## Setup
- symbol: `GBPUSD`
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
| directional | 4372693 |          120 |      2400000 |     1972693 |                0.0693453 |          0.501397 |
| oco         | 4800000 |          120 |      2400000 |     2400000 |                1.37803   |          0.575091 |

## Directional Sample
| split   |   bar_ticks |   horizon | family       | state_id                       | quality_tier   |   target_gross_pips |   target_gross_pos |
|:--------|------------:|----------:|:-------------|:-------------------------------|:---------------|--------------------:|-------------------:|
| test    |        1000 |         6 | path_follow  | path_follow__all               | B              |               130.7 |                  1 |
| test    |        1000 |         6 | shock_revert | shock_revert__all              | B              |               130.7 |                  1 |
| test    |        1000 |         6 | path_follow  | path_follow__high_abs_vel_q70  | B              |               130.7 |                  1 |
| test    |        1000 |         6 | shock_revert | shock_revert__high_abs_vel_q70 | B              |               130.7 |                  1 |
| test    |        1000 |         6 | path_follow  | path_follow__high_range_q70    | B              |               130.7 |                  1 |
| test    |        1000 |         5 | path_follow  | path_follow__all               | B              |               123.2 |                  1 |
| test    |        1000 |         5 | shock_revert | shock_revert__all              | B              |               123.2 |                  1 |
| test    |        1000 |         5 | path_follow  | path_follow__high_abs_vel_q70  | B              |               123.2 |                  1 |
| test    |        1000 |         5 | shock_revert | shock_revert__high_abs_vel_q70 | B              |               123.2 |                  1 |
| test    |        1000 |         5 | path_follow  | path_follow__high_range_q70    | B              |               123.2 |                  1 |
| test    |        1000 |         4 | path_follow  | path_follow__all               | B              |               119.1 |                  1 |
| test    |        1000 |         4 | shock_revert | shock_revert__all              | B              |               119.1 |                  1 |
| test    |        1000 |         4 | path_follow  | path_follow__high_abs_vel_q70  | B              |               119.1 |                  1 |
| test    |        1000 |         4 | shock_revert | shock_revert__high_abs_vel_q70 | B              |               119.1 |                  1 |
| test    |        1000 |         4 | path_follow  | path_follow__high_range_q70    | B              |               119.1 |                  1 |
| test    |        1000 |         4 | path_follow  | path_follow__all               | B              |               118.2 |                  1 |
| test    |        1000 |         4 | shock_revert | shock_revert__all              | B              |               118.2 |                  1 |
| test    |        1000 |         4 | path_follow  | path_follow__high_abs_vel_q70  | B              |               118.2 |                  1 |
| test    |        1000 |         4 | shock_revert | shock_revert__high_abs_vel_q70 | B              |               118.2 |                  1 |
| test    |        1000 |         5 | path_follow  | path_follow__all               | B              |              -110.8 |                  0 |

## OCO Sample
| split   |   bar_ticks |   horizon | family                | state_id                        | quality_tier   |   target_gross_pips |   target_gross_pos |
|:--------|------------:|----------:|:----------------------|:--------------------------------|:---------------|--------------------:|-------------------:|
| test    |        1000 |         6 | oco_first_touch_clean | oco_first_touch_clean__all__k5  | A              |               139.3 |                  1 |
| test    |        1000 |         6 | oco_first_touch_clean | oco_first_touch_clean__all__k8  | A              |               136.3 |                  1 |
| test    |        1000 |         6 | oco_first_touch_clean | oco_first_touch_clean__all__k10 | A              |               134.3 |                  1 |
| test    |        1000 |         5 | oco_first_touch_clean | oco_first_touch_clean__all__k5  | A              |               125.6 |                  1 |
| test    |        1000 |         5 | oco_first_touch_clean | oco_first_touch_clean__all__k8  | A              |               122.6 |                  1 |
| test    |        1000 |         5 | oco_first_touch_clean | oco_first_touch_clean__all__k10 | A              |               120.6 |                  1 |
| test    |        1000 |         4 | oco_first_touch_clean | oco_first_touch_clean__all__k5  | A              |               118.1 |                  1 |
| test    |        1000 |         3 | oco_first_touch_clean | oco_first_touch_clean__all__k3  | A              |               115.1 |                  1 |
| test    |        1000 |         4 | oco_first_touch_clean | oco_first_touch_clean__all__k8  | A              |               115.1 |                  1 |
| test    |        1000 |         3 | oco_first_touch_clean | oco_first_touch_clean__all__k5  | A              |               114   |                  1 |
| test    |        1000 |         3 | oco_first_touch_clean | oco_first_touch_clean__all__k5  | A              |               113.1 |                  1 |
| test    |        1000 |         4 | oco_first_touch_clean | oco_first_touch_clean__all__k10 | A              |               113.1 |                  1 |
| test    |        1000 |         5 | oco_first_touch_clean | oco_first_touch_clean__all__k5  | A              |               113   |                  1 |
| test    |        1000 |         5 | oco_first_touch_clean | oco_first_touch_clean__all__k5  | A              |               112.9 |                  1 |
| test    |        1000 |         4 | oco_first_touch_clean | oco_first_touch_clean__all__k8  | A              |              -111.2 |                  0 |
| test    |        1000 |         3 | oco_first_touch_clean | oco_first_touch_clean__all__k8  | A              |               111   |                  1 |
| test    |        1000 |         3 | oco_first_touch_clean | oco_first_touch_clean__all__k8  | A              |               110.1 |                  1 |
| test    |        1000 |         3 | oco_first_touch_clean | oco_first_touch_clean__all__k8  | A              |               109.9 |                  1 |
| test    |        1000 |         3 | oco_first_touch_clean | oco_first_touch_clean__all__k8  | A              |              -107.6 |                  0 |
| test    |        1000 |         2 | oco_first_touch_clean | oco_first_touch_clean__all__k3  | A              |               104.7 |                  1 |
