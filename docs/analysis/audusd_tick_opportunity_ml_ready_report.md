# Tick Opportunity ML Dataset Build

## Setup
- symbol: `AUDUSD`
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
| directional | 4734100 |          120 |      2400000 |     2334100 |                0.0355652 |          0.498359 |
| oco         | 4512938 |          120 |      2400000 |     2112938 |                1.25058   |          0.524664 |

## Directional Sample
| split   |   bar_ticks |   horizon | family      | state_id         | quality_tier   |   target_gross_pips |   target_gross_pos |
|:--------|------------:|----------:|:------------|:-----------------|:---------------|--------------------:|-------------------:|
| test    |        1000 |         3 | path_follow | path_follow__all | B              |               103.4 |                  1 |
| test    |        1000 |         2 | path_follow | path_follow__all | B              |                97.1 |                  1 |
| test    |        1000 |         5 | path_follow | path_follow__all | B              |                73.2 |                  1 |
| test    |        1000 |         5 | path_follow | path_follow__all | B              |                71.9 |                  1 |
| test    |        1000 |         4 | path_follow | path_follow__all | B              |                68.9 |                  1 |
| test    |        1000 |         4 | path_follow | path_follow__all | B              |                65.1 |                  1 |
| test    |        1000 |         3 | path_follow | path_follow__all | B              |                64.1 |                  1 |
| test    |        1000 |         3 | path_follow | path_follow__all | B              |                63.7 |                  1 |
| test    |        1000 |         4 | path_follow | path_follow__all | B              |                63.1 |                  1 |
| test    |        1000 |         3 | path_follow | path_follow__all | B              |                61.7 |                  1 |
| test    |        1000 |         4 | path_follow | path_follow__all | B              |                61.6 |                  1 |
| test    |        1000 |         5 | path_follow | path_follow__all | B              |                60.8 |                  1 |
| test    |        1000 |         5 | path_follow | path_follow__all | B              |                59.4 |                  1 |
| test    |        1000 |         3 | path_follow | path_follow__all | B              |                58.8 |                  1 |
| test    |        1000 |         4 | path_follow | path_follow__all | B              |               -58.7 |                  0 |
| test    |        1000 |         2 | path_follow | path_follow__all | B              |               -58.7 |                  0 |
| test    |        1000 |         2 | path_follow | path_follow__all | B              |               -58.7 |                  0 |
| test    |        1000 |         2 | path_follow | path_follow__all | B              |                58.5 |                  1 |
| test    |        1000 |         3 | path_follow | path_follow__all | B              |                58.2 |                  1 |
| test    |        1000 |         5 | path_follow | path_follow__all | B              |               -58.2 |                  0 |

## OCO Sample
| split   |   bar_ticks |   horizon | family                | state_id                        | quality_tier   |   target_gross_pips |   target_gross_pos |
|:--------|------------:|----------:|:----------------------|:--------------------------------|:---------------|--------------------:|-------------------:|
| test    |        1000 |         6 | oco_first_touch_clean | oco_first_touch_clean__all__k5  | A              |               100   |                  1 |
| test    |        1000 |         2 | oco_first_touch_clean | oco_first_touch_clean__all__k3  | A              |                99.8 |                  1 |
| test    |        1000 |         2 | oco_first_touch_clean | oco_first_touch_clean__all__k5  | A              |                97.8 |                  1 |
| test    |        1000 |         6 | oco_first_touch_clean | oco_first_touch_clean__all__k8  | A              |                97   |                  1 |
| test    |        1000 |         6 | oco_first_touch_clean | oco_first_touch_clean__all__k5  | A              |                95.9 |                  1 |
| test    |        1000 |         6 | oco_first_touch_clean | oco_first_touch_clean__all__k10 | A              |                95   |                  1 |
| test    |        1000 |         1 | oco_first_touch_clean | oco_first_touch_clean__all__k2  | A              |                94.5 |                  1 |
| test    |        1000 |         4 | oco_first_touch_clean | oco_first_touch_clean__all__k5  | A              |                93.9 |                  1 |
| test    |        1000 |         1 | oco_first_touch_clean | oco_first_touch_clean__all__k3  | A              |                93.5 |                  1 |
| test    |        1000 |         4 | oco_first_touch_clean | oco_first_touch_clean__all__k8  | A              |                92.9 |                  1 |
| test    |        1000 |         4 | oco_first_touch_clean | oco_first_touch_clean__all__k8  | A              |                90.9 |                  1 |
| test    |        1000 |         5 | oco_first_touch_clean | oco_first_touch_clean__all__k5  | A              |                89.6 |                  1 |
| test    |        1000 |         4 | oco_first_touch_clean | oco_first_touch_clean__all__k8  | A              |                88.9 |                  1 |
| test    |        1000 |         3 | oco_first_touch_clean | oco_first_touch_clean__all__k5  | A              |                87.6 |                  1 |
| test    |        1000 |         5 | oco_first_touch_clean | oco_first_touch_clean__all__k8  | A              |                74   |                  1 |
| test    |        1000 |         6 | oco_first_touch_clean | oco_first_touch_clean__all__k5  | A              |                73.5 |                  1 |
| test    |        1000 |         5 | oco_first_touch_clean | oco_first_touch_clean__all__k8  | A              |               -71.3 |                  0 |
| test    |        1000 |         4 | oco_first_touch_clean | oco_first_touch_clean__all__k5  | A              |                70.6 |                  1 |
| test    |        1000 |         6 | oco_first_touch_clean | oco_first_touch_clean__all__k8  | A              |                70.5 |                  1 |
| test    |        1000 |         6 | oco_first_touch_clean | oco_first_touch_clean__all__k10 | A              |                68.5 |                  1 |
