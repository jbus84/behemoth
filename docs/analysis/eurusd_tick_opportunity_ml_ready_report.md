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
| directional | 4373712 |          120 |      2400000 |     1973712 |                0.0602388 |          0.498692 |
| oco         | 3598835 |          120 |      2392343 |     1206492 |                1.24805   |          0.529674 |

## Directional Sample
| split   |   bar_ticks |   horizon | family       | state_id                       | quality_tier   |   target_gross_pips |   target_gross_pos |
|:--------|------------:|----------:|:-------------|:-------------------------------|:---------------|--------------------:|-------------------:|
| test    |        1000 |         6 | path_follow  | path_follow__all               | B              |               125.3 |                  1 |
| test    |        1000 |         4 | path_follow  | path_follow__all               | B              |               116.2 |                  1 |
| test    |        1000 |         5 | path_follow  | path_follow__all               | B              |               115.6 |                  1 |
| test    |        1000 |         5 | shock_revert | shock_revert__all              | B              |               115.6 |                  1 |
| test    |        1000 |         5 | path_follow  | path_follow__high_abs_vel_q70  | B              |               115.6 |                  1 |
| test    |        1000 |         5 | shock_revert | shock_revert__high_abs_vel_q70 | B              |               115.6 |                  1 |
| test    |        1000 |         6 | path_follow  | path_follow__all               | B              |               113   |                  1 |
| test    |        1000 |         6 | shock_revert | shock_revert__all              | B              |               113   |                  1 |
| test    |        1000 |         6 | path_follow  | path_follow__high_abs_vel_q70  | B              |               113   |                  1 |
| test    |        1000 |         6 | shock_revert | shock_revert__high_abs_vel_q70 | B              |               113   |                  1 |
| test    |        1000 |         5 | path_follow  | path_follow__all               | B              |               110.5 |                  1 |
| test    |        1000 |         5 | shock_revert | shock_revert__all              | B              |               110.5 |                  1 |
| test    |        1000 |         5 | path_follow  | path_follow__high_abs_vel_q70  | B              |               110.5 |                  1 |
| test    |        1000 |         5 | shock_revert | shock_revert__high_abs_vel_q70 | B              |               110.5 |                  1 |
| test    |        1000 |         4 | path_follow  | path_follow__all               | B              |               110.2 |                  1 |
| test    |        1000 |         4 | shock_revert | shock_revert__all              | B              |               110.2 |                  1 |
| test    |        1000 |         4 | path_follow  | path_follow__high_abs_vel_q70  | B              |               110.2 |                  1 |
| test    |        1000 |         4 | shock_revert | shock_revert__high_abs_vel_q70 | B              |               110.2 |                  1 |
| test    |        1000 |         5 | path_follow  | path_follow__all               | B              |               109.6 |                  1 |
| test    |        1000 |         6 | path_follow  | path_follow__all               | B              |              -106.6 |                  0 |

## OCO Sample
| split   |   bar_ticks |   horizon | family                | state_id                       | quality_tier   |   target_gross_pips |   target_gross_pos |
|:--------|------------:|----------:|:----------------------|:-------------------------------|:---------------|--------------------:|-------------------:|
| test    |        1000 |         5 | oco_first_touch_clean | oco_first_touch_clean__all__k5 | A              |               112.6 |                  1 |
| test    |        1000 |         5 | oco_first_touch_clean | oco_first_touch_clean__all__k3 | A              |               112.6 |                  1 |
| test    |        1000 |         4 | oco_first_touch_clean | oco_first_touch_clean__all__k5 | A              |              -110.8 |                  0 |
| test    |        1000 |         4 | oco_first_touch_clean | oco_first_touch_clean__all__k3 | A              |              -110.8 |                  0 |
| test    |        1000 |         3 | oco_first_touch_clean | oco_first_touch_clean__all__k3 | A              |               109.6 |                  1 |
| test    |        1000 |         4 | oco_first_touch_clean | oco_first_touch_clean__all__k5 | A              |               108   |                  1 |
| test    |        1000 |         4 | oco_first_touch_clean | oco_first_touch_clean__all__k5 | A              |               107.6 |                  1 |
| test    |        1000 |         4 | oco_first_touch_clean | oco_first_touch_clean__all__k3 | A              |               107.6 |                  1 |
| test    |        1000 |         6 | oco_first_touch_clean | oco_first_touch_clean__all__k8 | A              |               105.3 |                  1 |
| test    |        1000 |         6 | oco_first_touch_clean | oco_first_touch_clean__all__k5 | A              |               105.3 |                  1 |
| test    |        1000 |         3 | oco_first_touch_clean | oco_first_touch_clean__all__k3 | A              |                97.5 |                  1 |
| test    |        1000 |         6 | oco_first_touch_clean | oco_first_touch_clean__all__k5 | A              |                94.6 |                  1 |
| test    |        1000 |         3 | oco_first_touch_clean | oco_first_touch_clean__all__k3 | A              |                91.8 |                  1 |
| test    |        1000 |         5 | oco_first_touch_clean | oco_first_touch_clean__all__k5 | A              |                83.3 |                  1 |
| test    |        1000 |         6 | oco_first_touch_clean | oco_first_touch_clean__all__k8 | A              |                82.4 |                  1 |
| test    |        1000 |         6 | oco_first_touch_clean | oco_first_touch_clean__all__k8 | A              |                82.4 |                  1 |
| test    |        1000 |         4 | oco_first_touch_clean | oco_first_touch_clean__all__k5 | A              |                81.9 |                  1 |
| test    |        1000 |         6 | oco_first_touch_clean | oco_first_touch_clean__all__k8 | A              |               -81.4 |                  0 |
| test    |        1000 |         6 | oco_first_touch_clean | oco_first_touch_clean__all__k5 | A              |                80.9 |                  1 |
| test    |        1000 |         6 | oco_first_touch_clean | oco_first_touch_clean__all__k8 | A              |                75.8 |                  1 |
