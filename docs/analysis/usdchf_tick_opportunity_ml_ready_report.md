# Tick Opportunity ML Dataset Build

## Setup
- symbol: `USDCHF`
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
| directional | 4688767 |          120 |      2400000 |     2288767 |                0.0639806 |          0.502411 |
| oco         | 4740359 |          120 |      2400000 |     2340359 |                1.04142   |          0.522447 |

## Directional Sample
| split   |   bar_ticks |   horizon | family      | state_id         | quality_tier   |   target_gross_pips |   target_gross_pos |
|:--------|------------:|----------:|:------------|:-----------------|:---------------|--------------------:|-------------------:|
| test    |        1000 |         6 | path_follow | path_follow__all | B              |               114.7 |                  1 |
| test    |        1000 |         5 | path_follow | path_follow__all | B              |               111.8 |                  1 |
| test    |        1000 |         4 | path_follow | path_follow__all | B              |               110   |                  1 |
| test    |        1000 |         5 | path_follow | path_follow__all | B              |              -103.8 |                  0 |
| test    |        1000 |         4 | path_follow | path_follow__all | B              |              -100.9 |                  0 |
| test    |        1000 |         3 | path_follow | path_follow__all | B              |               -99.1 |                  0 |
| test    |        1000 |         6 | path_follow | path_follow__all | B              |                96.6 |                  1 |
| test    |        1000 |         5 | path_follow | path_follow__all | B              |                94.8 |                  1 |
| test    |        1000 |         6 | path_follow | path_follow__all | B              |                93.9 |                  1 |
| test    |        1000 |         6 | path_follow | path_follow__all | B              |               -83.6 |                  0 |
| test    |        1000 |         6 | path_follow | path_follow__all | B              |                81.3 |                  1 |
| test    |        1000 |         5 | path_follow | path_follow__all | B              |                80.7 |                  1 |
| test    |        1000 |         5 | path_follow | path_follow__all | B              |                78.5 |                  1 |
| test    |        1000 |         4 | path_follow | path_follow__all | B              |                78.1 |                  1 |
| test    |        1000 |         6 | path_follow | path_follow__all | B              |               -77.9 |                  0 |
| test    |        1000 |         6 | path_follow | path_follow__all | B              |                77.1 |                  1 |
| test    |        1000 |         6 | path_follow | path_follow__all | B              |                76.8 |                  1 |
| test    |        1000 |         4 | path_follow | path_follow__all | B              |               -75.7 |                  0 |
| test    |        1000 |         5 | path_follow | path_follow__all | B              |                74.5 |                  1 |
| test    |        1000 |         4 | path_follow | path_follow__all | B              |                74.2 |                  1 |

## OCO Sample
| split   |   bar_ticks |   horizon | family                | state_id                        | quality_tier   |   target_gross_pips |   target_gross_pos |
|:--------|------------:|----------:|:----------------------|:--------------------------------|:---------------|--------------------:|-------------------:|
| test    |        1000 |         4 | oco_first_touch_clean | oco_first_touch_clean__all__k5  | A              |               107   |                  1 |
| test    |        1000 |         5 | oco_first_touch_clean | oco_first_touch_clean__all__k8  | A              |               106.9 |                  1 |
| test    |        1000 |         3 | oco_first_touch_clean | oco_first_touch_clean__all__k5  | A              |               105.2 |                  1 |
| test    |        1000 |         4 | oco_first_touch_clean | oco_first_touch_clean__all__k8  | A              |               104   |                  1 |
| test    |        1000 |         4 | oco_first_touch_clean | oco_first_touch_clean__all__k5  | A              |                98.5 |                  1 |
| test    |        1000 |         3 | oco_first_touch_clean | oco_first_touch_clean__all__k5  | A              |                95.6 |                  1 |
| test    |        1000 |         4 | oco_first_touch_clean | oco_first_touch_clean__all__k8  | A              |                95.5 |                  1 |
| test    |        1000 |         2 | oco_first_touch_clean | oco_first_touch_clean__all__k5  | A              |                93.8 |                  1 |
| test    |        1000 |         6 | oco_first_touch_clean | oco_first_touch_clean__all__k8  | A              |                90.3 |                  1 |
| test    |        1000 |         6 | oco_first_touch_clean | oco_first_touch_clean__all__k10 | A              |                88.3 |                  1 |
| test    |        1000 |         6 | oco_first_touch_clean | oco_first_touch_clean__all__k8  | A              |               -86.8 |                  0 |
| test    |        1000 |         6 | oco_first_touch_clean | oco_first_touch_clean__all__k8  | A              |                86.6 |                  1 |
| test    |        1000 |         5 | oco_first_touch_clean | oco_first_touch_clean__all__k8  | A              |                86   |                  1 |
| test    |        1000 |         6 | oco_first_touch_clean | oco_first_touch_clean__all__k10 | A              |                84.6 |                  1 |
| test    |        1000 |         6 | oco_first_touch_clean | oco_first_touch_clean__all__k8  | A              |                84.4 |                  1 |
| test    |        1000 |         4 | oco_first_touch_clean | oco_first_touch_clean__all__k8  | A              |               -83.8 |                  0 |
| test    |        1000 |         6 | oco_first_touch_clean | oco_first_touch_clean__all__k10 | A              |                82.4 |                  1 |
| test    |        1000 |         6 | oco_first_touch_clean | oco_first_touch_clean__all__k10 | A              |                81.4 |                  1 |
| test    |        1000 |         4 | oco_first_touch_clean | oco_first_touch_clean__all__k5  | A              |                81.2 |                  1 |
| test    |        1000 |         6 | oco_first_touch_clean | oco_first_touch_clean__all__k8  | A              |                81   |                  1 |
