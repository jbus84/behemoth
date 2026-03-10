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
| directional | 4411310 |          120 |      2400000 |     2011310 |                0.0892027 |          0.503369 |
| oco         | 4703102 |          120 |      2400000 |     2303102 |                1.01416   |          0.529796 |

## Directional Sample
| split   |   bar_ticks |   horizon | family               | state_id                             | quality_tier   |   target_gross_pips |   target_gross_pos |
|:--------|------------:|----------:|:---------------------|:-------------------------------------|:---------------|--------------------:|-------------------:|
| test    |         100 |         6 | shock_extreme_revert | shock_extreme_revert__high_range_q80 | B              |               215.1 |                  1 |
| test    |         100 |         6 | path_persist_24      | path_persist_24__high_abs_vel_q70    | B              |              -215.1 |                  0 |
| test    |         100 |         6 | path_persist_24      | path_persist_24__high_range_q70      | B              |              -215.1 |                  0 |
| test    |         100 |         6 | path_persist_24      | path_persist_24__high_abs_vel_q80    | B              |              -215.1 |                  0 |
| test    |         100 |         6 | path_persist_24      | path_persist_24__high_range_q80      | B              |              -215.1 |                  0 |
| test    |         100 |         5 | shock_extreme_revert | shock_extreme_revert__high_range_q80 | B              |               214.1 |                  1 |
| test    |         100 |         5 | path_persist_24      | path_persist_24__high_abs_vel_q70    | B              |              -214.1 |                  0 |
| test    |         100 |         5 | path_persist_24      | path_persist_24__high_range_q70      | B              |              -214.1 |                  0 |
| test    |         100 |         5 | path_persist_24      | path_persist_24__high_abs_vel_q80    | B              |              -214.1 |                  0 |
| test    |         100 |         5 | path_persist_24      | path_persist_24__high_range_q80      | B              |              -214.1 |                  0 |
| test    |        1000 |         4 | path_follow          | path_follow__all                     | B              |               213.6 |                  1 |
| test    |        1000 |         4 | path_follow          | path_follow__high_abs_vel_q70        | B              |               213.6 |                  1 |
| test    |        1000 |         5 | path_follow          | path_follow__all                     | B              |               207.4 |                  1 |
| test    |        1000 |         5 | path_follow          | path_follow__high_abs_vel_q70        | B              |               207.4 |                  1 |
| test    |         100 |         4 | path_persist_24      | path_persist_24__high_range_q70      | B              |              -204.6 |                  0 |
| test    |         100 |         4 | path_persist_24      | path_persist_24__high_range_q80      | B              |              -204.6 |                  0 |
| test    |        1000 |         3 | path_follow          | path_follow__all                     | B              |              -201.7 |                  0 |
| test    |        1000 |         3 | path_follow          | path_follow__high_abs_vel_q70        | B              |              -201.7 |                  0 |
| test    |        1000 |         3 | path_follow          | path_follow__all                     | B              |               200.7 |                  1 |
| test    |        1000 |         3 | path_follow          | path_follow__high_abs_vel_q70        | B              |               200.7 |                  1 |

## OCO Sample
| split   |   bar_ticks |   horizon | family                | state_id                        | quality_tier   |   target_gross_pips |   target_gross_pos |
|:--------|------------:|----------:|:----------------------|:--------------------------------|:---------------|--------------------:|-------------------:|
| test    |        1000 |         5 | oco_first_touch_clean | oco_first_touch_clean__all__k5  | A              |               197.8 |                  1 |
| test    |        1000 |         5 | oco_first_touch_clean | oco_first_touch_clean__all__k5  | A              |               196.3 |                  1 |
| test    |        1000 |         5 | oco_first_touch_clean | oco_first_touch_clean__all__k5  | A              |               196.2 |                  1 |
| test    |        1000 |         5 | oco_first_touch_clean | oco_first_touch_clean__all__k8  | A              |               194.8 |                  1 |
| test    |        1000 |         5 | oco_first_touch_clean | oco_first_touch_clean__all__k8  | A              |               193.3 |                  1 |
| test    |        1000 |         5 | oco_first_touch_clean | oco_first_touch_clean__all__k8  | A              |               193.2 |                  1 |
| test    |        1000 |         5 | oco_first_touch_clean | oco_first_touch_clean__all__k10 | A              |               192.8 |                  1 |
| test    |        1000 |         5 | oco_first_touch_clean | oco_first_touch_clean__all__k10 | A              |               191.3 |                  1 |
| test    |        1000 |         5 | oco_first_touch_clean | oco_first_touch_clean__all__k10 | A              |               191.2 |                  1 |
| test    |        1000 |         4 | oco_first_touch_clean | oco_first_touch_clean__all__k5  | A              |               190.2 |                  1 |
| test    |        1000 |         4 | oco_first_touch_clean | oco_first_touch_clean__all__k5  | A              |               188.7 |                  1 |
| test    |        1000 |         4 | oco_first_touch_clean | oco_first_touch_clean__all__k5  | A              |               188.6 |                  1 |
| test    |        1000 |         4 | oco_first_touch_clean | oco_first_touch_clean__all__k8  | A              |               187.2 |                  1 |
| test    |        1000 |         4 | oco_first_touch_clean | oco_first_touch_clean__all__k8  | A              |               185.7 |                  1 |
| test    |        1000 |         4 | oco_first_touch_clean | oco_first_touch_clean__all__k8  | A              |               185.6 |                  1 |
| test    |        1000 |         6 | oco_first_touch_clean | oco_first_touch_clean__all__k10 | A              |               184.5 |                  1 |
| test    |        1000 |         4 | oco_first_touch_clean | oco_first_touch_clean__all__k8  | A              |               180.9 |                  1 |
| test    |        1000 |         6 | oco_first_touch_clean | oco_first_touch_clean__all__k5  | A              |               173.9 |                  1 |
| test    |        1000 |         5 | oco_first_touch_clean | oco_first_touch_clean__all__k10 | A              |               173.7 |                  1 |
| test    |        1000 |         3 | oco_first_touch_clean | oco_first_touch_clean__all__k8  | A              |               173.3 |                  1 |
