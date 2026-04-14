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
| directional | 4696027 |          120 |      2400000 |     2296027 |                0.0614833 |          0.502035 |
| oco         | 2285242 |          120 |      1601279 |      683963 |                1.81418   |          0.530632 |

## Directional Sample
| split   |   bar_ticks |   horizon | family      | state_id         | quality_tier   |   target_gross_pips |   target_gross_pos |
|:--------|------------:|----------:|:------------|:-----------------|:---------------|--------------------:|-------------------:|
| test    |        1000 |         6 | path_follow | path_follow__all | B              |               114.6 |                  1 |
| test    |        1000 |         5 | path_follow | path_follow__all | B              |               111.1 |                  1 |
| test    |        1000 |         4 | path_follow | path_follow__all | B              |               111.1 |                  1 |
| test    |        1000 |         5 | path_follow | path_follow__all | B              |              -103.2 |                  0 |
| test    |        1000 |         3 | path_follow | path_follow__all | B              |               -99.7 |                  0 |
| test    |        1000 |         4 | path_follow | path_follow__all | B              |               -99.7 |                  0 |
| test    |        1000 |         5 | path_follow | path_follow__all | B              |                95.3 |                  1 |
| test    |        1000 |         6 | path_follow | path_follow__all | B              |                95.3 |                  1 |
| test    |        1000 |         4 | path_follow | path_follow__all | B              |               -91.5 |                  0 |
| test    |        1000 |         6 | path_follow | path_follow__all | B              |               -90   |                  0 |
| test    |        1000 |         6 | path_follow | path_follow__all | B              |                89.9 |                  1 |
| test    |        1000 |         3 | path_follow | path_follow__all | B              |               -88.1 |                  0 |
| test    |        1000 |         3 | path_follow | path_follow__all | B              |               -88   |                  0 |
| test    |        1000 |         2 | path_follow | path_follow__all | B              |               -88   |                  0 |
| test    |        1000 |         6 | path_follow | path_follow__all | B              |               -80.2 |                  0 |
| test    |        1000 |         4 | path_follow | path_follow__all | B              |                78.5 |                  1 |
| test    |        1000 |         6 | path_follow | path_follow__all | B              |               -76.1 |                  0 |
| test    |        1000 |         5 | path_follow | path_follow__all | B              |                75.2 |                  1 |
| test    |        1000 |         6 | path_follow | path_follow__all | B              |                74.3 |                  1 |
| test    |        1000 |         6 | path_follow | path_follow__all | B              |               -73.9 |                  0 |

## OCO Sample
| split   |   bar_ticks |   horizon | family                | state_id                       | quality_tier   |   target_gross_pips |   target_gross_pos |
|:--------|------------:|----------:|:----------------------|:-------------------------------|:---------------|--------------------:|-------------------:|
| test    |        1000 |         4 | oco_first_touch_clean | oco_first_touch_clean__all__k5 | A              |               -84.2 |                  0 |
| test    |        1000 |         4 | oco_first_touch_clean | oco_first_touch_clean__all__k5 | A              |               -80.6 |                  0 |
| test    |        1000 |         4 | oco_first_touch_clean | oco_first_touch_clean__all__k5 | A              |               -67.8 |                  0 |
| test    |        1000 |         4 | oco_first_touch_clean | oco_first_touch_clean__all__k5 | A              |                66.3 |                  1 |
| test    |        1000 |         4 | oco_first_touch_clean | oco_first_touch_clean__all__k5 | A              |                60.1 |                  1 |
| test    |        1000 |         4 | oco_first_touch_clean | oco_first_touch_clean__all__k5 | A              |                55.1 |                  1 |
| test    |        1000 |         4 | oco_first_touch_clean | oco_first_touch_clean__all__k5 | A              |                52.5 |                  1 |
| test    |        1000 |         4 | oco_first_touch_clean | oco_first_touch_clean__all__k5 | A              |                49.3 |                  1 |
| test    |        1000 |         4 | oco_first_touch_clean | oco_first_touch_clean__all__k5 | A              |                48.5 |                  1 |
| test    |        1000 |         4 | oco_first_touch_clean | oco_first_touch_clean__all__k5 | A              |                48.4 |                  1 |
| test    |        1000 |         4 | oco_first_touch_clean | oco_first_touch_clean__all__k5 | A              |                47   |                  1 |
| test    |        1000 |         4 | oco_first_touch_clean | oco_first_touch_clean__all__k5 | A              |                45.6 |                  1 |
| test    |        1000 |         4 | oco_first_touch_clean | oco_first_touch_clean__all__k5 | A              |                44.5 |                  1 |
| test    |        1000 |         4 | oco_first_touch_clean | oco_first_touch_clean__all__k5 | A              |                44.5 |                  1 |
| test    |        1000 |         4 | oco_first_touch_clean | oco_first_touch_clean__all__k5 | A              |                44.5 |                  1 |
| test    |        1000 |         4 | oco_first_touch_clean | oco_first_touch_clean__all__k5 | A              |                43.8 |                  1 |
| test    |        1000 |         4 | oco_first_touch_clean | oco_first_touch_clean__all__k5 | A              |                43.8 |                  1 |
| test    |        1000 |         4 | oco_first_touch_clean | oco_first_touch_clean__all__k5 | A              |                43.4 |                  1 |
| test    |        1000 |         4 | oco_first_touch_clean | oco_first_touch_clean__all__k5 | A              |                43.2 |                  1 |
| test    |        1000 |         4 | oco_first_touch_clean | oco_first_touch_clean__all__k5 | A              |                42.7 |                  1 |
