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
| directional | 4465510 |          120 |      2317981 |     2147529 |                0.0658895 |          0.502774 |
| oco         | 4568742 |          120 |      2374818 |     2193924 |                1.27186   |          0.52532  |

## Directional Sample
| split   |   bar_ticks |   horizon | family               | state_id                             | quality_tier   |   target_gross_pips |   target_gross_pos |
|:--------|------------:|----------:|:---------------------|:-------------------------------------|:---------------|--------------------:|-------------------:|
| test    |         100 |         6 | shock_extreme_revert | shock_extreme_revert__high_range_q80 | B              |                64.7 |                  1 |
| test    |         100 |         6 | liquidity_revert     | liquidity_revert__all                | B              |                64.7 |                  1 |
| test    |         100 |         6 | shock_extreme_revert | shock_extreme_revert__high_range_q70 | B              |               -63.5 |                  0 |
| test    |         100 |         6 | shock_extreme_revert | shock_extreme_revert__high_range_q80 | B              |               -63.5 |                  0 |
| test    |         100 |         6 | liquidity_revert     | liquidity_revert__all                | B              |               -63.5 |                  0 |
| test    |         100 |         5 | liquidity_revert     | liquidity_revert__all                | B              |                58.3 |                  1 |
| test    |        1000 |         1 | path_follow          | path_follow__high_abs_vel_q70        | B              |               -58.3 |                  0 |
| test    |        1000 |         1 | shock_revert         | shock_revert__all                    | B              |               -58.3 |                  0 |
| test    |        1000 |         1 | shock_revert         | shock_revert__high_abs_vel_q70       | B              |               -58.3 |                  0 |
| test    |         100 |         6 | shock_extreme_revert | shock_extreme_revert__high_range_q70 | B              |               -56.7 |                  0 |
| test    |         100 |         6 | shock_extreme_revert | shock_extreme_revert__high_range_q80 | B              |               -56.7 |                  0 |
| test    |        1000 |         2 | path_follow          | path_follow__low_cost_q50            | B              |                56.7 |                  1 |
| test    |         100 |         6 | liquidity_revert     | liquidity_revert__all                | B              |               -55.6 |                  0 |
| test    |         100 |         6 | shock_extreme_revert | shock_extreme_revert__high_range_q70 | B              |               -53.7 |                  0 |
| test    |         100 |         6 | shock_extreme_revert | shock_extreme_revert__high_range_q80 | B              |               -53.7 |                  0 |
| test    |        1000 |         1 | path_follow          | path_follow__high_abs_vel_q70        | B              |               -52.7 |                  0 |
| test    |        1000 |         1 | shock_revert         | shock_revert__all                    | B              |               -52.7 |                  0 |
| test    |        1000 |         1 | shock_revert         | shock_revert__high_abs_vel_q70       | B              |               -52.7 |                  0 |
| test    |         100 |         5 | liquidity_revert     | liquidity_revert__all                | B              |               -52.5 |                  0 |
| test    |         100 |         6 | shock_extreme_revert | shock_extreme_revert__high_range_q70 | B              |                52.4 |                  1 |

## OCO Sample
| split   |   bar_ticks |   horizon | family                | state_id                       | quality_tier   |   target_gross_pips |   target_gross_pos |
|:--------|------------:|----------:|:----------------------|:-------------------------------|:---------------|--------------------:|-------------------:|
| test    |        1000 |         5 | oco_first_touch_clean | oco_first_touch_clean__all__k5 | A              |               109.9 |                  1 |
| test    |        1000 |         4 | oco_first_touch_clean | oco_first_touch_clean__all__k5 | A              |               107   |                  1 |
| test    |        1000 |         3 | oco_first_touch_clean | oco_first_touch_clean__all__k5 | A              |               105.2 |                  1 |
| test    |        1000 |         4 | oco_first_touch_clean | oco_first_touch_clean__all__k5 | A              |                98.5 |                  1 |
| test    |        1000 |         2 | oco_first_touch_clean | oco_first_touch_clean__all__k3 | A              |                95.8 |                  1 |
| test    |        1000 |         3 | oco_first_touch_clean | oco_first_touch_clean__all__k5 | A              |                95.6 |                  1 |
| test    |        1000 |         6 | oco_first_touch_clean | oco_first_touch_clean__all__k5 | A              |                93.3 |                  1 |
| test    |        1000 |         6 | oco_first_touch_clean | oco_first_touch_clean__all__k8 | A              |                90.3 |                  1 |
| test    |        1000 |         6 | oco_first_touch_clean | oco_first_touch_clean__all__k5 | A              |                89.6 |                  1 |
| test    |        1000 |         5 | oco_first_touch_clean | oco_first_touch_clean__all__k5 | A              |                89   |                  1 |
| test    |        1000 |         6 | oco_first_touch_clean | oco_first_touch_clean__all__k8 | A              |               -86.8 |                  0 |
| test    |        1000 |         6 | oco_first_touch_clean | oco_first_touch_clean__all__k8 | A              |                86.6 |                  1 |
| test    |        1000 |         6 | oco_first_touch_clean | oco_first_touch_clean__all__k8 | A              |                84.4 |                  1 |
| test    |        1000 |         6 | oco_first_touch_clean | oco_first_touch_clean__all__k5 | A              |                84   |                  1 |
| test    |        1000 |         4 | oco_first_touch_clean | oco_first_touch_clean__all__k5 | A              |                81.2 |                  1 |
| test    |        1000 |         6 | oco_first_touch_clean | oco_first_touch_clean__all__k8 | A              |                81   |                  1 |
| test    |        1000 |         5 | oco_first_touch_clean | oco_first_touch_clean__all__k5 | A              |                80.7 |                  1 |
| test    |        1000 |         6 | oco_first_touch_clean | oco_first_touch_clean__all__k5 | A              |                78.7 |                  1 |
| test    |        1000 |         6 | oco_first_touch_clean | oco_first_touch_clean__all__k8 | A              |                78.6 |                  1 |
| test    |        1000 |         4 | oco_first_touch_clean | oco_first_touch_clean__all__k5 | A              |                78.6 |                  1 |
