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
| directional | 4148064 |          120 |      2394669 |     1753395 |                0.0377881 |          0.498355 |
| oco         | 4370947 |          120 |      2392202 |     1978745 |                1.06167   |          0.543762 |

## Directional Sample
| split   |   bar_ticks |   horizon | family               | state_id                      | quality_tier   |   target_gross_pips |   target_gross_pos |
|:--------|------------:|----------:|:---------------------|:------------------------------|:---------------|--------------------:|-------------------:|
| test    |        1000 |         1 | path_follow          | path_follow__all              | B              |                77.8 |                  1 |
| test    |        1000 |         1 | shock_revert         | shock_revert__all             | B              |                77.8 |                  1 |
| test    |        1000 |         1 | path_follow          | path_follow__high_abs_vel_q70 | B              |                77.8 |                  1 |
| test    |        1000 |         1 | path_follow          | path_follow__high_range_q70   | B              |                77.8 |                  1 |
| test    |        1000 |         1 | shock_revert         | shock_revert__high_range_q70  | B              |                77.8 |                  1 |
| test    |         100 |         6 | path_persist_24      | path_persist_24__london       | B              |                63.6 |                  1 |
| test    |        1000 |         1 | path_follow          | path_follow__all              | B              |               -61.1 |                  0 |
| test    |        1000 |         1 | path_follow          | path_follow__high_abs_vel_q70 | B              |               -61.1 |                  0 |
| test    |        1000 |         1 | path_follow          | path_follow__high_range_q70   | B              |               -61.1 |                  0 |
| test    |         100 |         6 | shock_extreme_revert | shock_extreme_revert__london  | B              |                60.7 |                  1 |
| test    |         100 |         6 | path_persist_24      | path_persist_24__london       | B              |                60.7 |                  1 |
| test    |         100 |         5 | path_persist_24      | path_persist_24__london       | B              |                59.2 |                  1 |
| test    |         100 |         5 | path_persist_24      | path_persist_24__london       | B              |                57   |                  1 |
| test    |         100 |         4 | path_persist_24      | path_persist_24__london       | B              |                55.5 |                  1 |
| test    |         100 |         6 | path_persist_24      | path_persist_24__london       | B              |                54.5 |                  1 |
| test    |        1000 |         1 | path_follow          | path_follow__all              | B              |                53.5 |                  1 |
| test    |        1000 |         1 | shock_revert         | shock_revert__all             | B              |                53.5 |                  1 |
| test    |        1000 |         1 | path_follow          | path_follow__high_abs_vel_q70 | B              |                53.5 |                  1 |
| test    |        1000 |         1 | path_follow          | path_follow__high_range_q70   | B              |                53.5 |                  1 |
| test    |        1000 |         1 | shock_revert         | shock_revert__high_range_q70  | B              |                53.5 |                  1 |

## OCO Sample
| split   |   bar_ticks |   horizon | family                | state_id                                  | quality_tier   |   target_gross_pips |   target_gross_pos |
|:--------|------------:|----------:|:----------------------|:------------------------------------------|:---------------|--------------------:|-------------------:|
| test    |        1000 |         5 | oco_first_touch_clean | oco_first_touch_clean__all__k5            | A              |               119.1 |                  1 |
| test    |        1000 |         4 | oco_first_touch_clean | oco_first_touch_clean__all__k5            | A              |               118.9 |                  1 |
| test    |        1000 |         5 | oco_first_touch_clean | oco_first_touch_clean__all__k5            | A              |               118.7 |                  1 |
| test    |         100 |         6 | oco_first_touch_clean | oco_first_touch_clean__ny_overlap__k2     | A              |               117.9 |                  1 |
| test    |         100 |         6 | oco_first_touch_clean | oco_first_touch_clean__ny_overlap__k2     | A              |               117.1 |                  1 |
| test    |         100 |         6 | oco_first_touch_clean | oco_first_touch_clean__ny_overlap__k2     | A              |               116.4 |                  1 |
| test    |        1000 |         5 | oco_first_touch_clean | oco_first_touch_clean__all__k8            | A              |               116.1 |                  1 |
| test    |         100 |         4 | oco_first_touch_clean | oco_first_touch_clean__high_range_q70__k2 | A              |               115.8 |                  1 |
| test    |         100 |         4 | oco_first_touch_clean | oco_first_touch_clean__high_range_q80__k2 | A              |               115.8 |                  1 |
| test    |         100 |         4 | oco_first_touch_clean | oco_first_touch_clean__ny_overlap__k2     | A              |               115.8 |                  1 |
| test    |        1000 |         5 | oco_first_touch_clean | oco_first_touch_clean__all__k8            | A              |               115.7 |                  1 |
| test    |         100 |         6 | oco_first_touch_clean | oco_first_touch_clean__ny_overlap__k2     | A              |               114.6 |                  1 |
| test    |        1000 |         3 | oco_first_touch_clean | oco_first_touch_clean__all__k5            | A              |              -113.9 |                  0 |
| test    |        1000 |         4 | oco_first_touch_clean | oco_first_touch_clean__all__k3            | A              |               113.7 |                  1 |
| test    |         100 |         5 | oco_first_touch_clean | oco_first_touch_clean__ny_overlap__k2     | A              |               113.5 |                  1 |
| test    |         100 |         5 | oco_first_touch_clean | oco_first_touch_clean__ny_overlap__k2     | A              |               112.8 |                  1 |
| test    |        1000 |         3 | oco_first_touch_clean | oco_first_touch_clean__all__k5            | A              |              -112.4 |                  0 |
| test    |        1000 |         6 | oco_first_touch_clean | oco_first_touch_clean__all__k5            | A              |               112.3 |                  1 |
| test    |        1000 |         3 | oco_first_touch_clean | oco_first_touch_clean__all__k3            | A              |              -111.9 |                  0 |
| test    |         100 |         5 | oco_first_touch_clean | oco_first_touch_clean__ny_overlap__k2     | A              |               111.8 |                  1 |
