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
| directional | 4202796 |          120 |      2357980 |     1844816 |                 0.083805 |          0.50439  |
| oco         | 4786556 |          120 |      2400000 |     2386556 |                 0.744015 |          0.529713 |

## Directional Sample
| split   |   bar_ticks |   horizon | family               | state_id                             | quality_tier   |   target_gross_pips |   target_gross_pos |
|:--------|------------:|----------:|:---------------------|:-------------------------------------|:---------------|--------------------:|-------------------:|
| test    |         100 |         6 | shock_revert         | shock_revert__high_range_q70         | B              |               215.1 |                  1 |
| test    |         100 |         6 | shock_extreme_revert | shock_extreme_revert__high_range_q70 | B              |               215.1 |                  1 |
| test    |         100 |         6 | path_follow          | path_follow__high_range_q80          | B              |               215.1 |                  1 |
| test    |         100 |         6 | shock_revert         | shock_revert__high_range_q80         | B              |               215.1 |                  1 |
| test    |         100 |         6 | shock_extreme_revert | shock_extreme_revert__high_range_q80 | B              |               215.1 |                  1 |
| test    |         100 |         6 | path_persist_24      | path_persist_24__high_range_q70      | B              |              -215.1 |                  0 |
| test    |         100 |         6 | path_persist_24      | path_persist_24__high_abs_vel_q80    | B              |              -215.1 |                  0 |
| test    |         100 |         6 | shock_revert         | shock_revert__ny_overlap             | B              |               215.1 |                  1 |
| test    |         100 |         6 | path_persist_24      | path_persist_24__high_range_q80      | B              |              -215.1 |                  0 |
| test    |         100 |         6 | shock_extreme_revert | shock_extreme_revert__ny_overlap     | B              |               215.1 |                  1 |
| test    |         100 |         6 | liquidity_revert     | liquidity_revert__all                | B              |               215.1 |                  1 |
| test    |         100 |         6 | liquidity_revert     | liquidity_revert__high_abs_vel_q70   | B              |               215.1 |                  1 |
| test    |         100 |         5 | shock_revert         | shock_revert__high_range_q70         | B              |               214.1 |                  1 |
| test    |         100 |         5 | shock_extreme_revert | shock_extreme_revert__high_range_q70 | B              |               214.1 |                  1 |
| test    |         100 |         5 | shock_revert         | shock_revert__high_range_q80         | B              |               214.1 |                  1 |
| test    |         100 |         5 | shock_extreme_revert | shock_extreme_revert__high_range_q80 | B              |               214.1 |                  1 |
| test    |         100 |         5 | shock_revert         | shock_revert__ny_overlap             | B              |               214.1 |                  1 |
| test    |         100 |         5 | shock_extreme_revert | shock_extreme_revert__ny_overlap     | B              |               214.1 |                  1 |
| test    |         100 |         5 | liquidity_revert     | liquidity_revert__all                | B              |               214.1 |                  1 |
| test    |         100 |         5 | liquidity_revert     | liquidity_revert__high_abs_vel_q70   | B              |               214.1 |                  1 |

## OCO Sample
| split   |   bar_ticks |   horizon | family                | state_id                                    | quality_tier   |   target_gross_pips |   target_gross_pos |
|:--------|------------:|----------:|:----------------------|:--------------------------------------------|:---------------|--------------------:|-------------------:|
| test    |         100 |         6 | oco_first_touch_clean | oco_first_touch_clean__high_range_q80__k2   | A              |                87.6 |                  1 |
| test    |         100 |         6 | oco_first_touch_clean | oco_first_touch_clean__high_abs_vel_q80__k3 | A              |                86.6 |                  1 |
| test    |         100 |         6 | oco_first_touch_clean | oco_first_touch_clean__high_range_q80__k3   | A              |                86.6 |                  1 |
| test    |         100 |         6 | oco_first_touch_clean | oco_first_touch_clean__high_range_q70__k3   | A              |                83.4 |                  1 |
| test    |         100 |         5 | oco_first_touch_clean | oco_first_touch_clean__high_range_q70__k3   | A              |                83.4 |                  1 |
| test    |         100 |         6 | oco_first_touch_clean | oco_first_touch_clean__high_range_q80__k3   | A              |                83.4 |                  1 |
| test    |         100 |         5 | oco_first_touch_clean | oco_first_touch_clean__high_range_q80__k3   | A              |                83.4 |                  1 |
| test    |         100 |         5 | oco_first_touch_clean | oco_first_touch_clean__all__k2              | A              |                82   |                  1 |
| test    |         100 |         5 | oco_first_touch_clean | oco_first_touch_clean__high_range_q70__k2   | A              |                82   |                  1 |
| test    |         100 |         5 | oco_first_touch_clean | oco_first_touch_clean__high_range_q80__k2   | A              |                82   |                  1 |
| test    |         100 |         5 | oco_first_touch_clean | oco_first_touch_clean__ny_overlap__k2       | A              |                82   |                  1 |
| test    |         100 |         6 | oco_first_touch_clean | oco_first_touch_clean__high_abs_vel_q70__k2 | A              |                80.7 |                  1 |
| test    |         100 |         6 | oco_first_touch_clean | oco_first_touch_clean__high_abs_vel_q80__k2 | A              |                80.7 |                  1 |
| test    |         100 |         6 | oco_first_touch_clean | oco_first_touch_clean__ny_overlap__k2       | A              |                80.7 |                  1 |
| test    |         100 |         6 | oco_first_touch_clean | oco_first_touch_clean__high_range_q80__k2   | A              |                80.7 |                  1 |
| test    |         100 |         6 | oco_first_touch_clean | oco_first_touch_clean__high_abs_vel_q80__k3 | A              |                79.7 |                  1 |
| test    |         100 |         6 | oco_first_touch_clean | oco_first_touch_clean__high_range_q80__k3   | A              |                79.7 |                  1 |
| test    |         100 |         6 | oco_first_touch_clean | oco_first_touch_clean__high_abs_vel_q80__k3 | A              |                79   |                  1 |
| test    |         100 |         6 | oco_first_touch_clean | oco_first_touch_clean__high_range_q80__k3   | A              |                79   |                  1 |
| test    |         100 |         5 | oco_first_touch_clean | oco_first_touch_clean__high_abs_vel_q80__k2 | A              |                78.2 |                  1 |
