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
| directional | 4133585 |          120 |      2400000 |     1733585 |                 0.106304 |          0.503093 |
| oco         | 3911086 |          120 |      2400000 |     1511086 |                 2.62802  |          0.56584  |

## Directional Sample
| split   |   bar_ticks |   horizon | family      | state_id         | quality_tier   |   target_gross_pips |   target_gross_pos |
|:--------|------------:|----------:|:------------|:-----------------|:---------------|--------------------:|-------------------:|
| test    |        1000 |         5 | path_follow | path_follow__all | A              |              -181.9 |                  0 |
| test    |        1000 |         4 | path_follow | path_follow__all | A              |               177.2 |                  1 |
| test    |        1000 |         5 | path_follow | path_follow__all | A              |               170   |                  1 |
| test    |        1000 |         5 | path_follow | path_follow__all | A              |               168   |                  1 |
| test    |        1000 |         4 | path_follow | path_follow__all | A              |               157.9 |                  1 |
| test    |        1000 |         4 | path_follow | path_follow__all | A              |              -149.8 |                  0 |
| test    |        1000 |         5 | path_follow | path_follow__all | A              |              -141.6 |                  0 |
| test    |        1000 |         5 | path_follow | path_follow__all | A              |               141.3 |                  1 |
| test    |        1000 |         5 | path_follow | path_follow__all | A              |               134.6 |                  1 |
| test    |        1000 |         5 | path_follow | path_follow__all | A              |               133.3 |                  1 |
| test    |        1000 |         5 | path_follow | path_follow__all | A              |               132.4 |                  1 |
| test    |        1000 |         4 | path_follow | path_follow__all | A              |               129.8 |                  1 |
| test    |        1000 |         4 | path_follow | path_follow__all | A              |               129.2 |                  1 |
| test    |        1000 |         4 | path_follow | path_follow__all | A              |              -123.6 |                  0 |
| test    |        1000 |         5 | path_follow | path_follow__all | A              |              -123.5 |                  0 |
| test    |        1000 |         4 | path_follow | path_follow__all | A              |              -119.3 |                  0 |
| test    |        1000 |         5 | path_follow | path_follow__all | A              |               118.6 |                  1 |
| test    |        1000 |         4 | path_follow | path_follow__all | A              |               118.4 |                  1 |
| test    |        1000 |         5 | path_follow | path_follow__all | A              |               114.9 |                  1 |
| test    |        1000 |         5 | path_follow | path_follow__all | A              |              -108.2 |                  0 |

## OCO Sample
| split   |   bar_ticks |   horizon | family                | state_id                                 | quality_tier   |   target_gross_pips |   target_gross_pos |
|:--------|------------:|----------:|:----------------------|:-----------------------------------------|:---------------|--------------------:|-------------------:|
| test    |        2000 |         6 | oco_first_touch_clean | oco_first_touch_clean__all__k10          | A              |              -211.7 |                  0 |
| test    |        1000 |         3 | oco_first_touch_clean | oco_first_touch_clean__all__k5           | A              |              -203.2 |                  0 |
| test    |        1000 |         3 | oco_first_touch_clean | oco_first_touch_clean__all__k5           | A              |              -203.2 |                  0 |
| test    |        1000 |         3 | oco_first_touch_clean | oco_first_touch_clean__low_cost_q50__k5  | A              |              -203.2 |                  0 |
| test    |        1000 |         3 | oco_first_touch_clean | oco_first_touch_clean__low_cost_q50__k5  | A              |              -203.2 |                  0 |
| test    |        1000 |         3 | oco_first_touch_clean | oco_first_touch_clean__low_cost_q50__k5  | A              |              -203.2 |                  0 |
| test    |        2000 |         4 | oco_first_touch_clean | oco_first_touch_clean__all__k10          | A              |              -201.9 |                  0 |
| test    |        2000 |         4 | oco_first_touch_clean | oco_first_touch_clean__all__k8           | A              |              -201.9 |                  0 |
| test    |        1000 |         6 | oco_first_touch_clean | oco_first_touch_clean__all__k8           | A              |              -190.9 |                  0 |
| test    |        1000 |         6 | oco_first_touch_clean | oco_first_touch_clean__all__k5           | A              |              -190.9 |                  0 |
| test    |        1000 |         6 | oco_first_touch_clean | oco_first_touch_clean__low_cost_q50__k8  | A              |              -190.9 |                  0 |
| test    |        1000 |         6 | oco_first_touch_clean | oco_first_touch_clean__low_cost_q50__k10 | A              |              -190.9 |                  0 |
| test    |        2000 |         5 | oco_first_touch_clean | oco_first_touch_clean__all__k10          | A              |               190.7 |                  1 |
| test    |        2000 |         5 | oco_first_touch_clean | oco_first_touch_clean__all__k10          | A              |               190.7 |                  1 |
| test    |        1000 |         6 | oco_first_touch_clean | oco_first_touch_clean__all__k10          | A              |               189.8 |                  1 |
| test    |        1000 |         6 | oco_first_touch_clean | oco_first_touch_clean__all__k8           | A              |               189.8 |                  1 |
| test    |        1000 |         6 | oco_first_touch_clean | oco_first_touch_clean__low_cost_q50__k8  | A              |               189.8 |                  1 |
| test    |        1000 |         6 | oco_first_touch_clean | oco_first_touch_clean__low_cost_q50__k10 | A              |               189.8 |                  1 |
| test    |        2000 |         3 | oco_first_touch_clean | oco_first_touch_clean__all__k10          | A              |               189.8 |                  1 |
| test    |        2000 |         3 | oco_first_touch_clean | oco_first_touch_clean__all__k8           | A              |               189.8 |                  1 |
