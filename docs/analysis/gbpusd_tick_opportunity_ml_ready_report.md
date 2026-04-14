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
| directional | 4373210 |          120 |      2400000 |     1973210 |                0.0839113 |          0.501953 |
| oco         | 3854786 |          120 |      2385951 |     1468835 |                1.62394   |          0.529072 |

## Directional Sample
| split   |   bar_ticks |   horizon | family       | state_id                       | quality_tier   |   target_gross_pips |   target_gross_pos |
|:--------|------------:|----------:|:-------------|:-------------------------------|:---------------|--------------------:|-------------------:|
| test    |        1000 |         5 | path_follow  | path_follow__all               | B              |               124.1 |                  1 |
| test    |        1000 |         5 | shock_revert | shock_revert__all              | B              |               124.1 |                  1 |
| test    |        1000 |         5 | path_follow  | path_follow__high_abs_vel_q70  | B              |               124.1 |                  1 |
| test    |        1000 |         5 | shock_revert | shock_revert__high_abs_vel_q70 | B              |               124.1 |                  1 |
| test    |        1000 |         5 | path_follow  | path_follow__high_range_q70    | B              |               124.1 |                  1 |
| test    |        1000 |         6 | path_follow  | path_follow__all               | B              |               120.2 |                  1 |
| test    |        1000 |         6 | shock_revert | shock_revert__all              | B              |               120.2 |                  1 |
| test    |        1000 |         6 | path_follow  | path_follow__high_abs_vel_q70  | B              |               120.2 |                  1 |
| test    |        1000 |         6 | shock_revert | shock_revert__high_abs_vel_q70 | B              |               120.2 |                  1 |
| test    |        1000 |         6 | path_follow  | path_follow__high_range_q70    | B              |               120.2 |                  1 |
| test    |        1000 |         4 | path_follow  | path_follow__all               | B              |              -112.1 |                  0 |
| test    |        1000 |         4 | path_follow  | path_follow__high_range_q70    | B              |              -112.1 |                  0 |
| test    |        1000 |         5 | path_follow  | path_follow__all               | B              |              -111.3 |                  0 |
| test    |        1000 |         5 | path_follow  | path_follow__high_range_q70    | B              |              -111.3 |                  0 |
| test    |        1000 |         3 | path_follow  | path_follow__all               | B              |               109.9 |                  1 |
| test    |        1000 |         3 | shock_revert | shock_revert__all              | B              |               109.9 |                  1 |
| test    |        1000 |         3 | path_follow  | path_follow__high_abs_vel_q70  | B              |               109.9 |                  1 |
| test    |        1000 |         3 | shock_revert | shock_revert__high_abs_vel_q70 | B              |               109.9 |                  1 |
| test    |        1000 |         3 | path_follow  | path_follow__high_range_q70    | B              |               109.9 |                  1 |
| test    |        1000 |         4 | path_follow  | path_follow__all               | B              |               107.3 |                  1 |

## OCO Sample
| split   |   bar_ticks |   horizon | family                | state_id                              | quality_tier   |   target_gross_pips |   target_gross_pos |
|:--------|------------:|----------:|:----------------------|:--------------------------------------|:---------------|--------------------:|-------------------:|
| test    |        1000 |         4 | oco_first_touch_clean | oco_first_touch_clean__all__k5        | A              |               111   |                  1 |
| test    |        1000 |         4 | oco_first_touch_clean | oco_first_touch_clean__all__k5        | A              |               111   |                  1 |
| test    |        1000 |         5 | oco_first_touch_clean | oco_first_touch_clean__all__k8        | A              |               110.5 |                  1 |
| test    |        1000 |         5 | oco_first_touch_clean | oco_first_touch_clean__all__k5        | A              |               110.5 |                  1 |
| test    |        1000 |         5 | oco_first_touch_clean | oco_first_touch_clean__all__k5        | A              |               110.5 |                  1 |
| test    |        1000 |         5 | oco_first_touch_clean | oco_first_touch_clean__all__k8        | A              |              -100.7 |                  0 |
| test    |        1000 |         6 | oco_first_touch_clean | oco_first_touch_clean__all__k8        | A              |                93.2 |                  1 |
| test    |        1000 |         6 | oco_first_touch_clean | oco_first_touch_clean__all__k8        | A              |                91.9 |                  1 |
| test    |        1000 |         6 | oco_first_touch_clean | oco_first_touch_clean__all__k5        | A              |                91.9 |                  1 |
| test    |        1000 |         6 | oco_first_touch_clean | oco_first_touch_clean__all__k5        | A              |                91.9 |                  1 |
| test    |        1000 |         6 | oco_first_touch_clean | oco_first_touch_clean__all__k8        | A              |                91.4 |                  1 |
| test    |        1000 |         6 | oco_first_touch_clean | oco_first_touch_clean__all__k5        | A              |                91.4 |                  1 |
| test    |        1000 |         6 | oco_first_touch_clean | oco_first_touch_clean__all__k5        | A              |                91.4 |                  1 |
| test    |         100 |         6 | oco_first_touch_clean | oco_first_touch_clean__ny_overlap__k2 | A              |                88.8 |                  1 |
| test    |        1000 |         5 | oco_first_touch_clean | oco_first_touch_clean__all__k8        | A              |               -88.8 |                  0 |
| test    |        1000 |         6 | oco_first_touch_clean | oco_first_touch_clean__all__k8        | A              |                88.7 |                  1 |
| test    |        1000 |         6 | oco_first_touch_clean | oco_first_touch_clean__all__k5        | A              |                88.7 |                  1 |
| test    |        1000 |         4 | oco_first_touch_clean | oco_first_touch_clean__all__k5        | A              |               -88.4 |                  0 |
| test    |        1000 |         5 | oco_first_touch_clean | oco_first_touch_clean__all__k8        | A              |               -88.3 |                  0 |
| test    |        1000 |         5 | oco_first_touch_clean | oco_first_touch_clean__all__k8        | A              |                86.6 |                  1 |
