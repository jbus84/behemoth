# Tick Opportunity ML Dataset Build

## Setup
- symbol: `EURUSD`
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
| directional | 4330248 |          120 |      2400000 |     1930248 |                0.0619051 |          0.49917  |
| oco         | 4619651 |          120 |      2400000 |     2219651 |                1.1175    |          0.527955 |

## Directional Sample
| split   |   bar_ticks |   horizon | family       | state_id                       | quality_tier   |   target_gross_pips |   target_gross_pos |
|:--------|------------:|----------:|:-------------|:-------------------------------|:---------------|--------------------:|-------------------:|
| test    |        1000 |         5 | path_follow  | path_follow__all               | B              |               124.1 |                  1 |
| test    |        1000 |         5 | shock_revert | shock_revert__all              | B              |               124.1 |                  1 |
| test    |        1000 |         5 | path_follow  | path_follow__high_abs_vel_q70  | B              |               124.1 |                  1 |
| test    |        1000 |         5 | shock_revert | shock_revert__high_abs_vel_q70 | B              |               124.1 |                  1 |
| test    |        1000 |         6 | path_follow  | path_follow__all               | B              |              -124.1 |                  0 |
| test    |        1000 |         6 | shock_revert | shock_revert__all              | B              |              -124.1 |                  0 |
| test    |        1000 |         6 | path_follow  | path_follow__high_abs_vel_q70  | B              |              -124.1 |                  0 |
| test    |        1000 |         6 | shock_revert | shock_revert__high_abs_vel_q70 | B              |              -124.1 |                  0 |
| test    |        1000 |         6 | path_follow  | path_follow__all               | B              |               123.9 |                  1 |
| test    |        1000 |         6 | shock_revert | shock_revert__all              | B              |               123.9 |                  1 |
| test    |        1000 |         6 | path_follow  | path_follow__high_abs_vel_q70  | B              |               123.9 |                  1 |
| test    |        1000 |         6 | shock_revert | shock_revert__high_abs_vel_q70 | B              |               123.9 |                  1 |
| test    |        1000 |         3 | path_follow  | path_follow__all               | B              |               118   |                  1 |
| test    |        1000 |         3 | shock_revert | shock_revert__all              | B              |               118   |                  1 |
| test    |        1000 |         3 | path_follow  | path_follow__high_abs_vel_q70  | B              |               118   |                  1 |
| test    |        1000 |         3 | shock_revert | shock_revert__high_abs_vel_q70 | B              |               118   |                  1 |
| test    |        1000 |         5 | path_follow  | path_follow__all               | B              |               114.1 |                  1 |
| test    |        1000 |         5 | shock_revert | shock_revert__all              | B              |               114.1 |                  1 |
| test    |        1000 |         5 | path_follow  | path_follow__high_abs_vel_q70  | B              |               114.1 |                  1 |
| test    |        1000 |         5 | shock_revert | shock_revert__high_abs_vel_q70 | B              |               114.1 |                  1 |

## OCO Sample
| split   |   bar_ticks |   horizon | family                | state_id                                  | quality_tier   |   target_gross_pips |   target_gross_pos |
|:--------|------------:|----------:|:----------------------|:------------------------------------------|:---------------|--------------------:|-------------------:|
| test    |        1000 |         6 | oco_first_touch_clean | oco_first_touch_clean__all__k10           | A              |               123.5 |                  1 |
| test    |        1000 |         5 | oco_first_touch_clean | oco_first_touch_clean__all__k5            | A              |               119.1 |                  1 |
| test    |        1000 |         4 | oco_first_touch_clean | oco_first_touch_clean__all__k5            | A              |               118.9 |                  1 |
| test    |        1000 |         5 | oco_first_touch_clean | oco_first_touch_clean__all__k5            | A              |               118.7 |                  1 |
| test    |        1000 |         5 | oco_first_touch_clean | oco_first_touch_clean__all__k8            | A              |               116.1 |                  1 |
| test    |        1000 |         4 | oco_first_touch_clean | oco_first_touch_clean__all__k8            | A              |               115.9 |                  1 |
| test    |         100 |         4 | oco_first_touch_clean | oco_first_touch_clean__high_range_q70__k2 | A              |               115.8 |                  1 |
| test    |         100 |         4 | oco_first_touch_clean | oco_first_touch_clean__high_range_q80__k2 | A              |               115.8 |                  1 |
| test    |        1000 |         5 | oco_first_touch_clean | oco_first_touch_clean__all__k8            | A              |               115.7 |                  1 |
| test    |        1000 |         5 | oco_first_touch_clean | oco_first_touch_clean__all__k10           | A              |               114.1 |                  1 |
| test    |        1000 |         3 | oco_first_touch_clean | oco_first_touch_clean__all__k5            | A              |              -113.9 |                  0 |
| test    |        1000 |         5 | oco_first_touch_clean | oco_first_touch_clean__all__k10           | A              |               113.7 |                  1 |
| test    |        1000 |         4 | oco_first_touch_clean | oco_first_touch_clean__all__k3            | A              |               113.7 |                  1 |
| test    |        1000 |         3 | oco_first_touch_clean | oco_first_touch_clean__all__k5            | A              |              -112.4 |                  0 |
| test    |        1000 |         6 | oco_first_touch_clean | oco_first_touch_clean__all__k5            | A              |               112.3 |                  1 |
| test    |        1000 |         3 | oco_first_touch_clean | oco_first_touch_clean__all__k3            | A              |              -111.9 |                  0 |
| test    |        1000 |         4 | oco_first_touch_clean | oco_first_touch_clean__all__k5            | A              |               111.7 |                  1 |
| test    |        1000 |         2 | oco_first_touch_clean | oco_first_touch_clean__all__k2            | A              |               111.5 |                  1 |
| test    |        1000 |         2 | oco_first_touch_clean | oco_first_touch_clean__all__k3            | A              |               110.5 |                  1 |
| test    |        1000 |         6 | oco_first_touch_clean | oco_first_touch_clean__all__k8            | A              |               109.3 |                  1 |
