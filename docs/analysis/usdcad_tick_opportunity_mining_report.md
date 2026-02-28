# Tick Opportunity Mining Report

## Setup
- symbol: `USDCAD`
- bar_ticks_grid: `100,1000,2000`
- horizons: `1,2,3,4,5,6`
- train_years: `2022,2023,2024`
- test_year: `2025`
- min_annual_fills: `5000.0`
- inclusion_metric: `mean`

## Directional Top
|   bar_ticks |   horizon | family       | state_id                       | quality_tier   |   annualized_test_fills |   mean_gross_pips_test |   median_gross_pips_test |   gross_std_test |   hit_rate_gross_test | selection_pass   |
|------------:|----------:|:-------------|:-------------------------------|:---------------|------------------------:|-----------------------:|-------------------------:|-----------------:|----------------------:|:-----------------|
|         100 |         1 | path_follow  | path_follow__all               | C              |                 91961.6 |              0.0193274 |                      0   |          2.11354 |              0.489688 | True             |
|         100 |         2 | path_follow  | path_follow__all               | C              |                 91960.6 |              0.038701  |                      0   |          2.85401 |              0.497081 | True             |
|         100 |         3 | path_follow  | path_follow__all               | C              |                 91959.7 |              0.0429299 |                      0   |          3.43861 |              0.499596 | True             |
|         100 |         6 | path_follow  | path_follow__all               | C              |                 91959.6 |              0.0569528 |                      0.1 |          4.76021 |              0.504152 | True             |
|         100 |         5 | path_follow  | path_follow__all               | C              |                 91959.6 |              0.0566615 |                      0.1 |          4.35765 |              0.502013 | True             |
|         100 |         4 | path_follow  | path_follow__all               | C              |                 91959.6 |              0.0513329 |                      0   |          3.92421 |              0.499875 | True             |
|         100 |         1 | shock_revert | shock_revert__all              | C              |                 69139.3 |              0.0245577 |                      0   |          2.20017 |              0.49082  | True             |
|         100 |         2 | shock_revert | shock_revert__all              | C              |                 69138.3 |              0.0489884 |                      0   |          2.95365 |              0.499115 | True             |
|         100 |         3 | shock_revert | shock_revert__all              | C              |                 69137.3 |              0.0526917 |                      0.1 |          3.52159 |              0.50021  | True             |
|         100 |         5 | shock_revert | shock_revert__all              | C              |                 69137   |              0.0772759 |                      0.1 |          4.48128 |              0.504253 | True             |
|         100 |         6 | shock_revert | shock_revert__all              | C              |                 69137   |              0.0757214 |                      0.1 |          4.88201 |              0.507141 | True             |
|         100 |         4 | shock_revert | shock_revert__all              | C              |                 69137   |              0.063053  |                      0.1 |          4.03189 |              0.501524 | True             |
|         100 |         5 | path_follow  | path_follow__high_abs_vel_q70  | C              |                 58186.5 |              0.0874151 |                      0.1 |          4.8966  |              0.50595  | True             |
|         100 |         6 | path_follow  | path_follow__high_abs_vel_q70  | C              |                 58186.5 |              0.0848677 |                      0.1 |          5.33843 |              0.507744 | True             |
|         100 |         4 | path_follow  | path_follow__high_abs_vel_q70  | C              |                 58186.5 |              0.0728364 |                      0.1 |          4.41257 |              0.503829 | True             |
|         100 |         3 | path_follow  | path_follow__high_abs_vel_q70  | C              |                 58186.5 |              0.0618192 |                      0.1 |          3.87851 |              0.501966 | True             |
|         100 |         2 | path_follow  | path_follow__high_abs_vel_q70  | C              |                 58186.5 |              0.0568556 |                      0.1 |          3.23319 |              0.50119  | True             |
|         100 |         1 | path_follow  | path_follow__high_abs_vel_q70  | C              |                 58186.5 |              0.0283398 |                      0   |          2.41685 |              0.492687 | True             |
|         100 |         5 | shock_revert | shock_revert__high_abs_vel_q70 | C              |                 52940.1 |              0.09281   |                      0.1 |          4.84328 |              0.506161 | True             |
|         100 |         6 | shock_revert | shock_revert__high_abs_vel_q70 | C              |                 52940.1 |              0.0905391 |                      0.1 |          5.27175 |              0.508473 | True             |

## OCO Top
|   bar_ticks |   horizon | family                | state_id                          | quality_tier   |   annualized_test_fills |   mean_gross_pips_test |   median_gross_pips_test |   gross_std_test |   hit_rate_gross_test | selection_pass   |
|------------:|----------:|:----------------------|:----------------------------------|:---------------|------------------------:|-----------------------:|-------------------------:|-----------------:|----------------------:|:-----------------|
|         100 |         6 | oco_first_touch       | oco_first_touch__all__k2          | C              |                213640   |              0.103729  |              0.1         |          4.30852 |              0.5019   | True             |
|         100 |         5 | oco_first_touch       | oco_first_touch__all__k2          | C              |                206652   |              0.113288  |              0.1         |          3.91911 |              0.504514 | True             |
|         100 |         4 | oco_first_touch       | oco_first_touch__all__k2          | C              |                195531   |              0.122855  |              0.1         |          3.50159 |              0.506597 | True             |
|         100 |         3 | oco_first_touch       | oco_first_touch__all__k2          | C              |                177353   |              0.126944  |              0.1         |          3.04785 |              0.509195 | True             |
|         100 |         6 | oco_first_touch       | oco_first_touch__all__k3          | C              |                171537   |              0.103294  |              0.1         |          4.29931 |              0.502843 | True             |
|         100 |         5 | oco_first_touch_clean | oco_first_touch_clean__all__k2    | A              |                170447   |              1.03816   |              0.6         |          2.95103 |              0.595941 | True             |
|         100 |         4 | oco_first_touch_clean | oco_first_touch_clean__all__k2    | B              |                169287   |              0.803787  |              0.4         |          2.67343 |              0.575217 | True             |
|         100 |         6 | oco_first_touch_clean | oco_first_touch_clean__all__k2    | A              |                167943   |              1.27755   |              0.7         |          3.21858 |              0.615067 | True             |
|         100 |         3 | oco_first_touch_clean | oco_first_touch_clean__all__k2    | B              |                161097   |              0.581239  |              0.3         |          2.38074 |              0.555347 | True             |
|         100 |         5 | oco_first_touch       | oco_first_touch__all__k3          | C              |                157241   |              0.117687  |              0.1         |          3.95607 |              0.504959 | True             |
|         100 |         6 | oco_first_touch_clean | oco_first_touch_clean__all__k3    | B              |                157129   |              0.692484  |              0.3         |          3.40446 |              0.543868 | True             |
|         100 |         5 | oco_first_touch_clean | oco_first_touch_clean__all__k3    | B              |                147050   |              0.567504  |              0.2         |          3.15828 |              0.536093 | True             |
|         100 |         2 | oco_first_touch       | oco_first_touch__all__k2          | C              |                145158   |              0.147117  |              0.1         |          2.55422 |              0.517991 | True             |
|         100 |         4 | oco_first_touch       | oco_first_touch__all__k3          | C              |                138272   |              0.134501  |              0.1         |          3.59751 |              0.509402 | True             |
|         100 |         2 | oco_first_touch_clean | oco_first_touch_clean__all__k2    | C              |                137925   |              0.395822  |              0.2         |          2.05348 |              0.542636 | True             |
|         100 |         4 | oco_first_touch_clean | oco_first_touch_clean__all__k3    | B              |                131763   |              0.45894   |              0.2         |          2.91367 |              0.531785 | True             |
|         100 |         3 | oco_first_touch       | oco_first_touch__all__k3          | C              |                112801   |              0.146067  |              0.1         |          3.2287  |              0.51463  | True             |
|         100 |         3 | oco_first_touch_clean | oco_first_touch_clean__all__k3    | C              |                109252   |              0.368879  |              0.1         |          2.64554 |              0.529503 | True             |
|         100 |         6 | oco_first_touch       | oco_first_touch__low_cost_q50__k2 | C              |                 87639.4 |              0.0641272 |             -2.20268e-13 |          3.52888 |              0.4981   | True             |
|         100 |         6 | oco_first_touch       | oco_first_touch__all__k5          | C              |                 86281.1 |              0.153645  |              0.1         |          4.79156 |              0.509148 | True             |

## Selection Summary
| library     |   rows_total |   rows_pass |   pass_rate |   mean_annualized_fills_all |   mean_annualized_fills_pass |   mean_gross_all |   mean_gross_pass |   tier_a_rows |   tier_b_rows |   tier_c_rows |
|:------------|-------------:|------------:|------------:|----------------------------:|-----------------------------:|-----------------:|------------------:|--------------:|--------------:|--------------:|
| directional |          696 |         286 |     0.41092 |                     20345.2 |                      23582.6 |        0.0241063 |         0.0753373 |             0 |            65 |           221 |
| oco         |          720 |         423 |     0.5875  |                     19371.9 |                      31703.8 |        0.344084  |         0.448224  |            28 |           140 |           255 |
