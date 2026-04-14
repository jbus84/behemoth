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
| directional | 4696396 |          120 |      2400000 |     2296396 |                0.0440113 |          0.499451 |
| oco         | 2277132 |          120 |      1653691 |      623441 |                1.86126   |          0.543054 |

## Directional Sample
| split   |   bar_ticks |   horizon | family      | state_id         | quality_tier   |   target_gross_pips |   target_gross_pos |
|:--------|------------:|----------:|:------------|:-----------------|:---------------|--------------------:|-------------------:|
| test    |        1000 |         3 | path_follow | path_follow__all | B              |               103   |                  1 |
| test    |        1000 |         2 | path_follow | path_follow__all | B              |                96.5 |                  1 |
| test    |        1000 |         6 | path_follow | path_follow__all | B              |               -94.4 |                  0 |
| test    |        1000 |         6 | path_follow | path_follow__all | B              |                81.7 |                  1 |
| test    |        1000 |         6 | path_follow | path_follow__all | B              |                73   |                  1 |
| test    |        1000 |         6 | path_follow | path_follow__all | B              |               -73   |                  0 |
| test    |        1000 |         5 | path_follow | path_follow__all | B              |                72.9 |                  1 |
| test    |        1000 |         5 | path_follow | path_follow__all | B              |                71.7 |                  1 |
| test    |        1000 |         4 | path_follow | path_follow__all | B              |                68.9 |                  1 |
| test    |        1000 |         6 | path_follow | path_follow__all | B              |               -66.1 |                  0 |
| test    |        1000 |         6 | path_follow | path_follow__all | B              |                66   |                  1 |
| test    |        1000 |         4 | path_follow | path_follow__all | B              |                65.4 |                  1 |
| test    |        1000 |         5 | path_follow | path_follow__all | B              |               -65.1 |                  0 |
| test    |        1000 |         3 | path_follow | path_follow__all | B              |                63.6 |                  1 |
| test    |        1000 |         4 | path_follow | path_follow__all | B              |                62.9 |                  1 |
| test    |        1000 |         6 | path_follow | path_follow__all | B              |               -62.8 |                  0 |
| test    |        1000 |         5 | path_follow | path_follow__all | B              |                61.7 |                  1 |
| test    |        1000 |         3 | path_follow | path_follow__all | B              |                61.4 |                  1 |
| test    |        1000 |         4 | path_follow | path_follow__all | B              |                60.9 |                  1 |
| test    |        1000 |         6 | path_follow | path_follow__all | B              |                60.7 |                  1 |

## OCO Sample
| split   |   bar_ticks |   horizon | family                | state_id                       | quality_tier   |   target_gross_pips |   target_gross_pos |
|:--------|------------:|----------:|:----------------------|:-------------------------------|:---------------|--------------------:|-------------------:|
| test    |        1000 |         6 | oco_first_touch_clean | oco_first_touch_clean__all__k5 | A              |                93.2 |                  1 |
| test    |        1000 |         6 | oco_first_touch_clean | oco_first_touch_clean__all__k5 | A              |                72   |                  1 |
| test    |        1000 |         6 | oco_first_touch_clean | oco_first_touch_clean__all__k5 | A              |                70.1 |                  1 |
| test    |        1000 |         5 | oco_first_touch_clean | oco_first_touch_clean__all__k5 | A              |                69.8 |                  1 |
| test    |        1000 |         6 | oco_first_touch_clean | oco_first_touch_clean__all__k5 | A              |                65.1 |                  1 |
| test    |        1000 |         6 | oco_first_touch_clean | oco_first_touch_clean__all__k5 | A              |                64.8 |                  1 |
| test    |        1000 |         6 | oco_first_touch_clean | oco_first_touch_clean__all__k5 | A              |                64.1 |                  1 |
| test    |        1000 |         5 | oco_first_touch_clean | oco_first_touch_clean__all__k5 | A              |                64   |                  1 |
| test    |        1000 |         6 | oco_first_touch_clean | oco_first_touch_clean__all__k5 | A              |                61.6 |                  1 |
| test    |        1000 |         5 | oco_first_touch_clean | oco_first_touch_clean__all__k5 | A              |                60.6 |                  1 |
| test    |        1000 |         6 | oco_first_touch_clean | oco_first_touch_clean__all__k5 | A              |                58.3 |                  1 |
| test    |        1000 |         6 | oco_first_touch_clean | oco_first_touch_clean__all__k5 | A              |                57.1 |                  1 |
| test    |        1000 |         6 | oco_first_touch_clean | oco_first_touch_clean__all__k5 | A              |                56.5 |                  1 |
| test    |        1000 |         5 | oco_first_touch_clean | oco_first_touch_clean__all__k5 | A              |                56.3 |                  1 |
| test    |        1000 |         5 | oco_first_touch_clean | oco_first_touch_clean__all__k5 | A              |                55.3 |                  1 |
| test    |        1000 |         5 | oco_first_touch_clean | oco_first_touch_clean__all__k5 | A              |                54.6 |                  1 |
| test    |        1000 |         5 | oco_first_touch_clean | oco_first_touch_clean__all__k5 | A              |                54.4 |                  1 |
| test    |        1000 |         6 | oco_first_touch_clean | oco_first_touch_clean__all__k5 | A              |                53.8 |                  1 |
| test    |        1000 |         6 | oco_first_touch_clean | oco_first_touch_clean__all__k5 | A              |                53.3 |                  1 |
| test    |        1000 |         5 | oco_first_touch_clean | oco_first_touch_clean__all__k5 | A              |                52.9 |                  1 |
