# Tick Opportunity ML Dataset Build

## Setup
- symbol: `USDCAD`
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
| directional | 4564377 |          120 |      2400000 |     2164377 |                 0.081258 |          0.501994 |
| oco         | 2684263 |          120 |      1889393 |      794870 |                 1.656    |          0.514825 |

## Directional Sample
| split   |   bar_ticks |   horizon | family       | state_id                      | quality_tier   |   target_gross_pips |   target_gross_pos |
|:--------|------------:|----------:|:-------------|:------------------------------|:---------------|--------------------:|-------------------:|
| test    |        1000 |         6 | path_follow  | path_follow__all              | B              |              -198.5 |                  0 |
| test    |        1000 |         6 | shock_revert | shock_revert__all             | B              |              -198.5 |                  0 |
| test    |        1000 |         6 | path_follow  | path_follow__high_abs_vel_q70 | B              |              -198.5 |                  0 |
| test    |        1000 |         3 | path_follow  | path_follow__all              | B              |              -196.1 |                  0 |
| test    |        1000 |         3 | shock_revert | shock_revert__all             | B              |              -196.1 |                  0 |
| test    |        1000 |         3 | path_follow  | path_follow__high_abs_vel_q70 | B              |              -196.1 |                  0 |
| test    |        1000 |         5 | path_follow  | path_follow__all              | B              |              -188.6 |                  0 |
| test    |        1000 |         5 | shock_revert | shock_revert__all             | B              |              -188.6 |                  0 |
| test    |        1000 |         5 | path_follow  | path_follow__high_abs_vel_q70 | B              |              -188.6 |                  0 |
| test    |        1000 |         2 | path_follow  | path_follow__all              | B              |              -186.2 |                  0 |
| test    |        1000 |         2 | shock_revert | shock_revert__all             | B              |              -186.2 |                  0 |
| test    |        1000 |         2 | path_follow  | path_follow__high_abs_vel_q70 | B              |              -186.2 |                  0 |
| test    |        1000 |         4 | path_follow  | path_follow__all              | B              |              -183.5 |                  0 |
| test    |        1000 |         4 | shock_revert | shock_revert__all             | B              |              -183.5 |                  0 |
| test    |        1000 |         4 | path_follow  | path_follow__high_abs_vel_q70 | B              |              -183.5 |                  0 |
| test    |        1000 |         6 | path_follow  | path_follow__all              | B              |              -178.7 |                  0 |
| test    |        1000 |         6 | shock_revert | shock_revert__all             | B              |              -178.7 |                  0 |
| test    |        1000 |         6 | path_follow  | path_follow__high_abs_vel_q70 | B              |              -178.7 |                  0 |
| test    |        1000 |         5 | path_follow  | path_follow__all              | B              |              -160.8 |                  0 |
| test    |        1000 |         5 | shock_revert | shock_revert__all             | B              |              -160.8 |                  0 |

## OCO Sample
| split   |   bar_ticks |   horizon | family                | state_id                       | quality_tier   |   target_gross_pips |   target_gross_pos |
|:--------|------------:|----------:|:----------------------|:-------------------------------|:---------------|--------------------:|-------------------:|
| test    |        1000 |         6 | oco_first_touch_clean | oco_first_touch_clean__all__k5 | A              |               213.4 |                  1 |
| test    |        1000 |         6 | oco_first_touch_clean | oco_first_touch_clean__all__k5 | A              |               213.4 |                  1 |
| test    |        1000 |         6 | oco_first_touch_clean | oco_first_touch_clean__all__k8 | A              |               208.5 |                  1 |
| test    |        1000 |         6 | oco_first_touch_clean | oco_first_touch_clean__all__k5 | A              |               208.5 |                  1 |
| test    |        1000 |         5 | oco_first_touch_clean | oco_first_touch_clean__all__k5 | A              |               207.1 |                  1 |
| test    |        1000 |         5 | oco_first_touch_clean | oco_first_touch_clean__all__k5 | A              |               179.6 |                  1 |
| test    |        1000 |         5 | oco_first_touch_clean | oco_first_touch_clean__all__k5 | A              |               179.6 |                  1 |
| test    |        1000 |         6 | oco_first_touch_clean | oco_first_touch_clean__all__k8 | A              |               176.3 |                  1 |
| test    |        1000 |         6 | oco_first_touch_clean | oco_first_touch_clean__all__k8 | A              |              -175.9 |                  0 |
| test    |        1000 |         6 | oco_first_touch_clean | oco_first_touch_clean__all__k8 | A              |              -175.9 |                  0 |
| test    |        1000 |         6 | oco_first_touch_clean | oco_first_touch_clean__all__k5 | A              |              -175.9 |                  0 |
| test    |        1000 |         4 | oco_first_touch_clean | oco_first_touch_clean__all__k5 | A              |               173.3 |                  1 |
| test    |        1000 |         6 | oco_first_touch_clean | oco_first_touch_clean__all__k8 | A              |               167.6 |                  1 |
| test    |        1000 |         6 | oco_first_touch_clean | oco_first_touch_clean__all__k8 | A              |               167.6 |                  1 |
| test    |        1000 |         6 | oco_first_touch_clean | oco_first_touch_clean__all__k8 | A              |               167.6 |                  1 |
| test    |        1000 |         6 | oco_first_touch_clean | oco_first_touch_clean__all__k5 | A              |               167.6 |                  1 |
| test    |        1000 |         4 | oco_first_touch_clean | oco_first_touch_clean__all__k5 | A              |               164.1 |                  1 |
| test    |        1000 |         4 | oco_first_touch_clean | oco_first_touch_clean__all__k5 | A              |               164.1 |                  1 |
| test    |        1000 |         6 | oco_first_touch_clean | oco_first_touch_clean__all__k8 | A              |              -152.3 |                  0 |
| test    |        1000 |         5 | oco_first_touch_clean | oco_first_touch_clean__all__k5 | A              |               142   |                  1 |
