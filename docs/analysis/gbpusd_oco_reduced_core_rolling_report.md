# GBPUSD OCO Reduced-Core Rolling Selection

## Setup
- family_keep: `oco_first_touch_clean`
- barrier_keep: `[2.0, 3.0]`
- horizon_keep: `[5, 6]`
- locked_quantile: `0.9`
- selection_mode: `auto`
- execution_mode: `stop_limit`
- stop_limit_detail_csv: `data/analysis/tick_opportunity_mining/stop_limit_tickfill_fullcap/GBPUSD_stop_limit_tickfill_detail.csv`
- stop_limit_cap_pips: `1.2`
- stop_limit_slippage_mode: `full_overshoot`
- stop_limit_match_rate: `0.999070`
- stop_limit_fill_rate_selected: `0.993537`
- state_train_months: `3`
- min_train_months: `3`
- overlap_corr_max: `0.85`
- overlap_divergence_max: `0.4`
- max_states/min_states: `12/4`
- strict_gate_only: `True`

## Summary
```
symbol  locked_quantile selection_mode execution_mode  state_train_months  months_total  months_scored  rows_total  signal_rows_total  mean_gross_pips  monthly_mean_gross_pips  lb95_month_mean_gross_pips  mean_signal_pips  monthly_mean_signal_pips  lb95_month_mean_signal_pips  positive_months  positive_months_signal  avg_month_rows  avg_month_signal_rows  fill_rate_overall  annualized_rows  capacity_floor_monthly  capacity_floor_annual  capacity_pass_monthly_or_annual
GBPUSD              0.9           auto     stop_limit                   3             9              6        8148               8221         2.456038                 2.511683                    2.253165          2.434229                  2.487622                      2.26222                6                       6          1358.0            1370.166667            0.99112          16296.0                  3000.0                 5000.0                             True
```

## Monthly Portfolio
```
symbol test_month            train_months  states_selected  rows  signal_rows  fill_rate  mean_gross_pips  mean_signal_pips  median_gross_pips  pos_rate      status
GBPUSD    2025-04                                        0     0            0        NaN              NaN               NaN                NaN       NaN warmup_skip
GBPUSD    2025-05                 2025-04                0     0            0        NaN              NaN               NaN                NaN       NaN warmup_skip
GBPUSD    2025-06         2025-04,2025-05                0     0            0        NaN              NaN               NaN                NaN       NaN warmup_skip
GBPUSD    2025-07 2025-04,2025-05,2025-06                2  1521         1536   0.990234         2.572781          2.547656               2.00  0.680339          ok
GBPUSD    2025-08 2025-05,2025-06,2025-07                2  1150         1156   0.994810         2.902000          2.886938               2.30  0.697232          ok
GBPUSD    2025-09 2025-06,2025-07,2025-08                3  1864         1874   0.994664         2.196030          2.184312               1.70  0.675027          ok
GBPUSD    2025-10 2025-07,2025-08,2025-09                2  1189         1202   0.989185         2.433810          2.407488               2.10  0.666389          ok
GBPUSD    2025-11 2025-08,2025-09,2025-10                2   964          980   0.983673         2.974793          2.926224               2.30  0.677551          ok
GBPUSD    2025-12 2025-09,2025-10,2025-11                3  1460         1473   0.991174         1.990685          1.973116               1.65  0.655804          ok
```

## State Schedule (Top Rows)
```
symbol test_month            train_months  selected_rank                                    state_id                                         state_key  bar_ticks  horizon                family                  regime_desc  barrier_pips  overlap_corr_max  overlap_div_max  train_rows  train_months_count  train_avg_month_rows  train_mean_gross_pips  train_mean_signal_pips  train_lb95_trade_mean_gross_pips  train_lb95_month_mean_gross_pips  train_positive_months  train_fill_rate  gate_pass
GBPUSD    2025-07 2025-04,2025-05,2025-06              1   oco_first_touch_clean__high_range_q80__k2   oco_first_touch_clean__high_range_q80__k2|100|6        100        6 oco_first_touch_clean   high_range_q80;barrier=2.0           2.0          0.000000         0.000000        4195                   3           1390.666667               2.810235                2.794827                          2.666567                          2.541978                      3         0.994517       True
GBPUSD    2025-07 2025-04,2025-05,2025-06              2             oco_first_touch_clean__asia__k2             oco_first_touch_clean__asia__k2|100|6        100        6 oco_first_touch_clean             asia;barrier=2.0           2.0          0.625519         0.336024        3474                   3           1156.666667               2.242133                2.239551                          2.116729                          2.150398                      3         0.998849       True
GBPUSD    2025-08 2025-05,2025-06,2025-07              1   oco_first_touch_clean__high_range_q80__k2   oco_first_touch_clean__high_range_q80__k2|100|6        100        6 oco_first_touch_clean   high_range_q80;barrier=2.0           2.0          0.000000         0.000000        3213                   3           1062.000000               2.701507                2.678805                          2.540138                          2.541978                      3         0.991597       True
GBPUSD    2025-08 2025-05,2025-06,2025-07              2           oco_first_touch_clean__london__k2           oco_first_touch_clean__london__k2|100|5        100        5 oco_first_touch_clean           london;barrier=2.0           2.0          0.189828         0.127353        1627                   3            541.333333               2.234606                2.230486                          2.043715                          2.166506                      3         0.998156       True
GBPUSD    2025-09 2025-06,2025-07,2025-08              1   oco_first_touch_clean__high_range_q80__k2   oco_first_touch_clean__high_range_q80__k2|100|6        100        6 oco_first_touch_clean   high_range_q80;barrier=2.0           2.0          0.000000         0.000000        2549                   3            842.333333               2.871191                2.846410                          2.684251                          2.629597                      3         0.991369       True
GBPUSD    2025-09 2025-06,2025-07,2025-08              2           oco_first_touch_clean__london__k2           oco_first_touch_clean__london__k2|100|6        100        6 oco_first_touch_clean           london;barrier=2.0           2.0          0.238818         0.098713        2751                   3            915.000000               2.728743                2.722792                          2.550900                          2.558330                      3         0.997819       True
GBPUSD    2025-09 2025-06,2025-07,2025-08              3 oco_first_touch_clean__high_abs_vel_q80__k2 oco_first_touch_clean__high_abs_vel_q80__k2|100|5        100        5 oco_first_touch_clean high_abs_vel_q80;barrier=2.0           2.0          0.825488         0.144297        1539                   3            509.000000               2.191945                2.174854                          1.974250                          2.013708                      3         0.992203       True
GBPUSD    2025-10 2025-07,2025-08,2025-09              1   oco_first_touch_clean__high_range_q80__k2   oco_first_touch_clean__high_range_q80__k2|100|6        100        6 oco_first_touch_clean   high_range_q80;barrier=2.0           2.0          0.000000         0.000000        2113                   3            697.666667               3.097468                3.068150                          2.892695                          2.917474                      3         0.990535       True
GBPUSD    2025-10 2025-07,2025-08,2025-09              2   oco_first_touch_clean__high_range_q80__k2   oco_first_touch_clean__high_range_q80__k2|100|5        100        5 oco_first_touch_clean   high_range_q80;barrier=2.0           2.0          0.608693         0.388629        1562                   3            513.333333               2.736364                2.697823                          2.488588                          2.639207                      3         0.985915       True
GBPUSD    2025-11 2025-08,2025-09,2025-10              1   oco_first_touch_clean__high_range_q70__k2   oco_first_touch_clean__high_range_q70__k2|100|6        100        6 oco_first_touch_clean   high_range_q70;barrier=2.0           2.0          0.000000         0.000000        1801                   3            595.000000               2.951709                2.925486                          2.723717                          2.800792                      3         0.991116       True
GBPUSD    2025-11 2025-08,2025-09,2025-10              2   oco_first_touch_clean__high_range_q80__k2   oco_first_touch_clean__high_range_q80__k2|100|6        100        6 oco_first_touch_clean   high_range_q80;barrier=2.0           2.0          0.768256         0.229869        1823                   3            603.333333               3.013923                2.992430                          2.796341                          2.768230                      3         0.992869       True
GBPUSD    2025-12 2025-09,2025-10,2025-11              1   oco_first_touch_clean__high_range_q80__k2   oco_first_touch_clean__high_range_q80__k2|100|6        100        6 oco_first_touch_clean   high_range_q80;barrier=2.0           2.0          0.000000         0.000000        1740                   3            573.333333               2.931047                2.897356                          2.686790                          2.768230                      3         0.988506       True
GBPUSD    2025-12 2025-09,2025-10,2025-11              2 oco_first_touch_clean__high_abs_vel_q80__k2 oco_first_touch_clean__high_abs_vel_q80__k2|100|6        100        6 oco_first_touch_clean high_abs_vel_q80;barrier=2.0           2.0          0.779756         0.140197        1756                   3            581.000000               2.386976                2.369305                          2.179060                          2.272259                      3         0.992597       True
GBPUSD    2025-12 2025-09,2025-10,2025-11              3             oco_first_touch_clean__asia__k2             oco_first_touch_clean__asia__k2|100|6        100        6 oco_first_touch_clean             asia;barrier=2.0           2.0          0.348557         0.191237        1969                   3            653.666667               2.207190                2.198222                          2.034368                          1.970996                      3         0.995937       True
```
