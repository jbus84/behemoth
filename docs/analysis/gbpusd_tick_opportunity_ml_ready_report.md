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
| directional | 4629653 |          120 |      2397485 |     2232168 |                0.0528908 |          0.501169 |
| oco         | 4758882 |          120 |      2400000 |     2358882 |                1.70294   |          0.573638 |

## Directional Sample
| split   |   bar_ticks |   horizon | family               | state_id                         | quality_tier   |   target_gross_pips |   target_gross_pos |
|:--------|------------:|----------:|:---------------------|:---------------------------------|:---------------|--------------------:|-------------------:|
| test    |         100 |         6 | path_follow          | path_follow__ny_overlap          | B              |               -80.4 |                  0 |
| test    |         100 |         5 | shock_revert         | shock_revert__ny_overlap         | B              |               -78.9 |                  0 |
| test    |         100 |         4 | shock_revert         | shock_revert__ny_overlap         | B              |               -78.2 |                  0 |
| test    |         100 |         6 | path_follow          | path_follow__ny_overlap          | B              |               -75.5 |                  0 |
| test    |         100 |         6 | shock_revert         | shock_revert__ny_overlap         | B              |               -75.5 |                  0 |
| test    |         100 |         6 | shock_extreme_revert | shock_extreme_revert__ny_overlap | B              |               -75.5 |                  0 |
| test    |         100 |         4 | shock_revert         | shock_revert__ny_overlap         | B              |                68.7 |                  1 |
| test    |         100 |         5 | shock_revert         | shock_revert__ny_overlap         | B              |                67.4 |                  1 |
| test    |        1000 |         1 | path_follow          | path_follow__all                 | B              |               -63.9 |                  0 |
| test    |         100 |         6 | path_follow          | path_follow__ny_overlap          | B              |                63.6 |                  1 |
| test    |         100 |         6 | shock_revert         | shock_revert__ny_overlap         | B              |                63.6 |                  1 |
| test    |         100 |         6 | shock_extreme_revert | shock_extreme_revert__ny_overlap | B              |                63.6 |                  1 |
| test    |        1000 |         1 | path_follow          | path_follow__all                 | B              |                62.9 |                  1 |
| test    |        1000 |         1 | path_follow          | path_follow__low_cost_q50        | B              |                62.9 |                  1 |
| test    |        1000 |         1 | path_follow          | path_follow__all                 | B              |               -60.5 |                  0 |
| test    |        1000 |         1 | path_follow          | path_follow__all                 | B              |                60.2 |                  1 |
| test    |        1000 |         1 | path_follow          | path_follow__low_cost_q50        | B              |                60.2 |                  1 |
| test    |         100 |         5 | shock_revert         | shock_revert__ny_overlap         | B              |                59.3 |                  1 |
| test    |         100 |         4 | shock_revert         | shock_revert__ny_overlap         | B              |                58   |                  1 |
| test    |         100 |         6 | path_follow          | path_follow__ny_overlap          | B              |                56.9 |                  1 |

## OCO Sample
| split   |   bar_ticks |   horizon | family                | state_id                                 | quality_tier   |   target_gross_pips |   target_gross_pos |
|:--------|------------:|----------:|:----------------------|:-----------------------------------------|:---------------|--------------------:|-------------------:|
| test    |        1000 |         6 | oco_first_touch_clean | oco_first_touch_clean__all__k5           | A              |               139.3 |                  1 |
| test    |        1000 |         6 | oco_first_touch_clean | oco_first_touch_clean__low_cost_q50__k5  | A              |               139.3 |                  1 |
| test    |        1000 |         6 | oco_first_touch_clean | oco_first_touch_clean__all__k8           | A              |               136.3 |                  1 |
| test    |        1000 |         6 | oco_first_touch_clean | oco_first_touch_clean__low_cost_q50__k8  | A              |               136.3 |                  1 |
| test    |        1000 |         6 | oco_first_touch_clean | oco_first_touch_clean__low_cost_q30__k8  | A              |               136.3 |                  1 |
| test    |        1000 |         6 | oco_first_touch_clean | oco_first_touch_clean__all__k10          | A              |               134.3 |                  1 |
| test    |        1000 |         6 | oco_first_touch_clean | oco_first_touch_clean__low_cost_q50__k10 | A              |               134.3 |                  1 |
| test    |        1000 |         5 | oco_first_touch_clean | oco_first_touch_clean__all__k5           | A              |               125.6 |                  1 |
| test    |        1000 |         5 | oco_first_touch_clean | oco_first_touch_clean__low_cost_q50__k5  | A              |               125.6 |                  1 |
| test    |        1000 |         5 | oco_first_touch_clean | oco_first_touch_clean__all__k8           | A              |               122.6 |                  1 |
| test    |        1000 |         5 | oco_first_touch_clean | oco_first_touch_clean__low_cost_q50__k8  | A              |               122.6 |                  1 |
| test    |        1000 |         5 | oco_first_touch_clean | oco_first_touch_clean__low_cost_q30__k8  | A              |               122.6 |                  1 |
| test    |        1000 |         4 | oco_first_touch_clean | oco_first_touch_clean__all__k5           | A              |               118.1 |                  1 |
| test    |        1000 |         4 | oco_first_touch_clean | oco_first_touch_clean__low_cost_q50__k5  | A              |               118.1 |                  1 |
| test    |        1000 |         4 | oco_first_touch_clean | oco_first_touch_clean__low_cost_q30__k5  | A              |               118.1 |                  1 |
| test    |        1000 |         3 | oco_first_touch_clean | oco_first_touch_clean__all__k3           | A              |               115.1 |                  1 |
| test    |        1000 |         4 | oco_first_touch_clean | oco_first_touch_clean__all__k8           | A              |               115.1 |                  1 |
| test    |        1000 |         4 | oco_first_touch_clean | oco_first_touch_clean__low_cost_q50__k8  | A              |               115.1 |                  1 |
| test    |        1000 |         4 | oco_first_touch_clean | oco_first_touch_clean__low_cost_q30__k8  | A              |               115.1 |                  1 |
| test    |        1000 |         3 | oco_first_touch_clean | oco_first_touch_clean__all__k5           | A              |               114   |                  1 |
