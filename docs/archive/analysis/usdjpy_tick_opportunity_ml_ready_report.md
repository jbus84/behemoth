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
| directional | 4220190 |          120 |      2282325 |     1937865 |                0.0642312 |          0.50327  |
| oco         | 4748117 |          120 |      2400000 |     2348117 |                2.32774   |          0.599269 |

## Directional Sample
| split   |   bar_ticks |   horizon | family               | state_id                               | quality_tier   |   target_gross_pips |   target_gross_pos |
|:--------|------------:|----------:|:---------------------|:---------------------------------------|:---------------|--------------------:|-------------------:|
| test    |         100 |         5 | shock_extreme_revert | shock_extreme_revert__high_abs_vel_q80 | B              |               197.2 |                  1 |
| test    |         100 |         5 | shock_extreme_revert | shock_extreme_revert__high_range_q70   | B              |               197.2 |                  1 |
| test    |         100 |         5 | shock_revert         | shock_revert__ny_overlap               | B              |               197.2 |                  1 |
| test    |         100 |         5 | shock_extreme_revert | shock_extreme_revert__ny_overlap       | B              |               197.2 |                  1 |
| test    |         100 |         5 | path_persist_24      | path_persist_24__ny_overlap            | B              |              -197.2 |                  0 |
| test    |         100 |         4 | shock_revert         | shock_revert__ny_overlap               | B              |               196.4 |                  1 |
| test    |         100 |         4 | shock_extreme_revert | shock_extreme_revert__ny_overlap       | B              |               196.4 |                  1 |
| test    |         100 |         3 | shock_extreme_revert | shock_extreme_revert__ny_overlap       | B              |               195   |                  1 |
| test    |         100 |         6 | shock_extreme_revert | shock_extreme_revert__all              | B              |               192.2 |                  1 |
| test    |         100 |         6 | shock_revert         | shock_revert__ny_overlap               | B              |               192.2 |                  1 |
| test    |         100 |         6 | shock_extreme_revert | shock_extreme_revert__ny_overlap       | B              |               192.2 |                  1 |
| test    |         100 |         6 | path_persist_24      | path_persist_24__ny_overlap            | B              |              -192.2 |                  0 |
| test    |         100 |         5 | shock_extreme_revert | shock_extreme_revert__all              | B              |               150.9 |                  1 |
| test    |         100 |         5 | shock_revert         | shock_revert__ny_overlap               | B              |               150.9 |                  1 |
| test    |         100 |         5 | shock_extreme_revert | shock_extreme_revert__ny_overlap       | B              |               150.9 |                  1 |
| test    |         100 |         6 | shock_revert         | shock_revert__ny_overlap               | B              |               146.1 |                  1 |
| test    |         100 |         6 | shock_extreme_revert | shock_extreme_revert__ny_overlap       | B              |               146.1 |                  1 |
| test    |         100 |         3 | shock_extreme_revert | shock_extreme_revert__ny_overlap       | B              |               146   |                  1 |
| test    |         100 |         4 | shock_extreme_revert | shock_extreme_revert__all              | B              |               145   |                  1 |
| test    |         100 |         4 | shock_revert         | shock_revert__ny_overlap               | B              |               145   |                  1 |

## OCO Sample
| split   |   bar_ticks |   horizon | family                | state_id                                | quality_tier   |   target_gross_pips |   target_gross_pos |
|:--------|------------:|----------:|:----------------------|:----------------------------------------|:---------------|--------------------:|-------------------:|
| test    |        1000 |         3 | oco_first_touch_clean | oco_first_touch_clean__all__k8          | A              |              -201.5 |                  0 |
| test    |        1000 |         3 | oco_first_touch_clean | oco_first_touch_clean__low_cost_q50__k8 | A              |              -201.5 |                  0 |
| test    |        1000 |         3 | oco_first_touch_clean | oco_first_touch_clean__low_cost_q30__k8 | A              |              -201.5 |                  0 |
| test    |        1000 |         3 | oco_first_touch_clean | oco_first_touch_clean__all__k8          | A              |              -200.4 |                  0 |
| test    |        1000 |         3 | oco_first_touch_clean | oco_first_touch_clean__low_cost_q50__k8 | A              |              -200.4 |                  0 |
| test    |        1000 |         3 | oco_first_touch_clean | oco_first_touch_clean__low_cost_q30__k8 | A              |              -200.4 |                  0 |
| test    |        1000 |         2 | oco_first_touch_clean | oco_first_touch_clean__all__k3          | A              |               199.6 |                  1 |
| test    |        1000 |         2 | oco_first_touch_clean | oco_first_touch_clean__low_cost_q50__k3 | A              |               199.6 |                  1 |
| test    |        1000 |         3 | oco_first_touch_clean | oco_first_touch_clean__all__k8          | A              |              -199.6 |                  0 |
| test    |        1000 |         3 | oco_first_touch_clean | oco_first_touch_clean__low_cost_q50__k8 | A              |              -199.6 |                  0 |
| test    |        1000 |         3 | oco_first_touch_clean | oco_first_touch_clean__low_cost_q30__k8 | A              |              -199.6 |                  0 |
| test    |        1000 |         3 | oco_first_touch_clean | oco_first_touch_clean__all__k5          | A              |              -198.5 |                  0 |
| test    |        1000 |         3 | oco_first_touch_clean | oco_first_touch_clean__low_cost_q50__k5 | A              |              -198.5 |                  0 |
| test    |        1000 |         2 | oco_first_touch_clean | oco_first_touch_clean__all__k5          | A              |               197.6 |                  1 |
| test    |        1000 |         2 | oco_first_touch_clean | oco_first_touch_clean__low_cost_q50__k5 | A              |               197.6 |                  1 |
| test    |        1000 |         2 | oco_first_touch_clean | oco_first_touch_clean__low_cost_q30__k5 | A              |               197.6 |                  1 |
| test    |        1000 |         3 | oco_first_touch_clean | oco_first_touch_clean__all__k5          | A              |              -197.4 |                  0 |
| test    |        1000 |         3 | oco_first_touch_clean | oco_first_touch_clean__low_cost_q50__k5 | A              |              -197.4 |                  0 |
| test    |        1000 |         3 | oco_first_touch_clean | oco_first_touch_clean__all__k5          | A              |              -196.6 |                  0 |
| test    |        1000 |         3 | oco_first_touch_clean | oco_first_touch_clean__low_cost_q50__k5 | A              |              -196.6 |                  0 |
