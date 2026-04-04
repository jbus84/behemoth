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
| directional | 4568445 |          120 |      2400000 |     2168445 |                0.0816457 |          0.50224  |
| oco         | 4577776 |          120 |      2400000 |     2177776 |                1.32472   |          0.546294 |

## Directional Sample
| split   |   bar_ticks |   horizon | family       | state_id                      | quality_tier   |   target_gross_pips |   target_gross_pos |
|:--------|------------:|----------:|:-------------|:------------------------------|:---------------|--------------------:|-------------------:|
| test    |        1000 |         4 | path_follow  | path_follow__all              | B              |               213.6 |                  1 |
| test    |        1000 |         4 | path_follow  | path_follow__high_abs_vel_q70 | B              |               213.6 |                  1 |
| test    |        1000 |         5 | path_follow  | path_follow__all              | B              |               207.4 |                  1 |
| test    |        1000 |         5 | path_follow  | path_follow__high_abs_vel_q70 | B              |               207.4 |                  1 |
| test    |        1000 |         3 | path_follow  | path_follow__all              | B              |              -201.7 |                  0 |
| test    |        1000 |         3 | path_follow  | path_follow__high_abs_vel_q70 | B              |              -201.7 |                  0 |
| test    |        1000 |         3 | path_follow  | path_follow__all              | B              |               200.7 |                  1 |
| test    |        1000 |         3 | path_follow  | path_follow__high_abs_vel_q70 | B              |               200.7 |                  1 |
| test    |        1000 |         4 | path_follow  | path_follow__all              | B              |              -195.5 |                  0 |
| test    |        1000 |         4 | path_follow  | path_follow__high_abs_vel_q70 | B              |              -195.5 |                  0 |
| test    |        1000 |         5 | path_follow  | path_follow__all              | B              |              -188.9 |                  0 |
| test    |        1000 |         5 | shock_revert | shock_revert__all             | B              |              -188.9 |                  0 |
| test    |        1000 |         5 | path_follow  | path_follow__high_abs_vel_q70 | B              |              -188.9 |                  0 |
| test    |        1000 |         2 | path_follow  | path_follow__all              | B              |              -188.8 |                  0 |
| test    |        1000 |         2 | path_follow  | path_follow__high_abs_vel_q70 | B              |              -188.8 |                  0 |
| test    |        1000 |         6 | path_follow  | path_follow__all              | B              |               183.7 |                  1 |
| test    |        1000 |         6 | path_follow  | path_follow__high_abs_vel_q70 | B              |               183.7 |                  1 |
| test    |        1000 |         6 | path_follow  | path_follow__all              | B              |              -182.6 |                  0 |
| test    |        1000 |         6 | path_follow  | path_follow__high_abs_vel_q70 | B              |              -182.6 |                  0 |
| test    |        1000 |         4 | path_follow  | path_follow__all              | B              |              -181.3 |                  0 |

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
