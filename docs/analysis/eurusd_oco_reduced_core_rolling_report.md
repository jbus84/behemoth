# EURUSD OCO Reduced-Core Rolling Selection

## Setup
- family_keep: `oco_first_touch_clean`
- barrier_keep: `[2.0, 3.0]`
- horizon_keep: `[5, 6]`
- locked_quantile: `0.9`
- selection_mode: `auto`
- execution_mode: `stop_limit`
- stop_limit_detail_csv: `data/analysis/tick_opportunity_mining/stop_limit_tickfill_eurusd_fixed/EURUSD_stop_limit_tickfill_detail.csv`
- stop_limit_cap_pips: `1.2`
- stop_limit_slippage_mode: `full_overshoot`
- stop_limit_match_rate: `0.998816`
- stop_limit_fill_rate_selected: `0.991658`
- state_train_months: `3`
- min_train_months: `3`
- overlap_corr_max: `0.85`
- overlap_divergence_max: `0.4`
- max_states/min_states: `12/4`
- strict_gate_only: `True`

## Summary
```
symbol  locked_quantile selection_mode execution_mode  state_train_months  months_total  months_scored  rows_total  signal_rows_total  mean_gross_pips  monthly_mean_gross_pips  lb95_month_mean_gross_pips  mean_signal_pips  monthly_mean_signal_pips  lb95_month_mean_signal_pips  positive_months  positive_months_signal  avg_month_rows  avg_month_signal_rows  fill_rate_overall  annualized_rows  capacity_floor_monthly  capacity_floor_annual  capacity_pass_monthly_or_annual
EURUSD              0.9           auto     stop_limit                   3             9              6        4432               4476         1.962816                 1.708947                    1.292893          1.943521                  1.692639                     1.268999                6                       6      738.666667                  746.0            0.99017           8864.0                  3000.0                 5000.0                             True
```

## Monthly Portfolio
```
symbol test_month            train_months  states_selected  rows  signal_rows  fill_rate  mean_gross_pips  mean_signal_pips  median_gross_pips  pos_rate      status
EURUSD    2025-04                                        0     0            0        NaN              NaN               NaN                NaN       NaN warmup_skip
EURUSD    2025-05                 2025-04                0     0            0        NaN              NaN               NaN                NaN       NaN warmup_skip
EURUSD    2025-06         2025-04,2025-05                0     0            0        NaN              NaN               NaN                NaN       NaN warmup_skip
EURUSD    2025-07 2025-04,2025-05,2025-06                2  1079         1093   0.987191         2.607322          2.573925                2.0  0.678866          ok
EURUSD    2025-08 2025-05,2025-06,2025-07                2  1179         1194   0.987437         2.235454          2.207370                1.6  0.654104          ok
EURUSD    2025-09 2025-06,2025-07,2025-08                2   812          820   0.990244         1.878941          1.860610                1.4  0.630488          ok
EURUSD    2025-10 2025-07,2025-08,2025-09                2   626          630   0.993651         1.646166          1.635714                1.5  0.646032          ok
EURUSD    2025-11 2025-08,2025-09,2025-10                1   355          356   0.997191         0.938028          0.935393                0.8  0.581461          ok
EURUSD    2025-12 2025-09,2025-10,2025-11                1   381          383   0.994778         0.947769          0.942820                0.7  0.584856          ok
```

## State Schedule (Top Rows)
```
symbol test_month            train_months  selected_rank                                    state_id                                         state_key  bar_ticks  horizon                family                  regime_desc  barrier_pips  overlap_corr_max  overlap_div_max  train_rows  train_months_count  train_avg_month_rows  train_mean_gross_pips  train_mean_signal_pips  train_lb95_trade_mean_gross_pips  train_lb95_month_mean_gross_pips  train_positive_months  train_fill_rate  gate_pass
EURUSD    2025-07 2025-04,2025-05,2025-06              1       oco_first_touch_clean__ny_overlap__k2       oco_first_touch_clean__ny_overlap__k2|100|6        100        6 oco_first_touch_clean       ny_overlap;barrier=2.0           2.0          0.000000         0.000000        1886                   3            621.000000               3.067848                3.030435                          2.808391                          2.214147                      3         0.987805       True
EURUSD    2025-07 2025-04,2025-05,2025-06              2 oco_first_touch_clean__high_abs_vel_q80__k2 oco_first_touch_clean__high_abs_vel_q80__k2|100|6        100        6 oco_first_touch_clean high_abs_vel_q80;barrier=2.0           2.0          0.807282         0.157349        2712                   3            894.666667               2.917884                2.887758                          2.711256                          2.162805                      3         0.989676       True
EURUSD    2025-08 2025-05,2025-06,2025-07              1 oco_first_touch_clean__high_abs_vel_q80__k2 oco_first_touch_clean__high_abs_vel_q80__k2|100|6        100        6 oco_first_touch_clean high_abs_vel_q80;barrier=2.0           2.0          0.000000         0.000000        1947                   3            643.000000               2.469207                2.446379                          2.250752                          2.162805                      3         0.990755       True
EURUSD    2025-08 2025-05,2025-06,2025-07              2       oco_first_touch_clean__ny_overlap__k2       oco_first_touch_clean__ny_overlap__k2|100|6        100        6 oco_first_touch_clean       ny_overlap;barrier=2.0           2.0          0.680535         0.213602        1221                   3            403.000000               2.196443                2.174857                          1.967563                          2.016350                      3         0.990172       True
EURUSD    2025-09 2025-06,2025-07,2025-08              1 oco_first_touch_clean__high_abs_vel_q80__k2 oco_first_touch_clean__high_abs_vel_q80__k2|100|6        100        6 oco_first_touch_clean high_abs_vel_q80;barrier=2.0           2.0          0.000000         0.000000        1945                   3            642.000000               2.621028                2.595424                          2.402946                          2.312997                      3         0.990231       True
EURUSD    2025-09 2025-06,2025-07,2025-08              2       oco_first_touch_clean__ny_overlap__k2       oco_first_touch_clean__ny_overlap__k2|100|6        100        6 oco_first_touch_clean       ny_overlap;barrier=2.0           2.0          0.794083         0.025370        1293                   3            424.666667               1.986342                1.957154                          1.749018                          1.693205                      3         0.985305       True
EURUSD    2025-10 2025-07,2025-08,2025-09              1 oco_first_touch_clean__high_abs_vel_q80__k2 oco_first_touch_clean__high_abs_vel_q80__k2|100|6        100        6 oco_first_touch_clean high_abs_vel_q80;barrier=2.0           2.0          0.000000         0.000000        1790                   3            590.000000               2.614463                2.585251                          2.381506                          2.183357                      3         0.988827       True
EURUSD    2025-10 2025-07,2025-08,2025-09              2       oco_first_touch_clean__ny_overlap__k2       oco_first_touch_clean__ny_overlap__k2|100|5        100        5 oco_first_touch_clean       ny_overlap;barrier=2.0           2.0          0.551770         0.253569        1090                   3            358.666667               1.434665                1.416239                          1.189936                          1.183958                      3         0.987156       True
EURUSD    2025-11 2025-08,2025-09,2025-10              1 oco_first_touch_clean__high_abs_vel_q80__k2 oco_first_touch_clean__high_abs_vel_q80__k2|100|6        100        6 oco_first_touch_clean high_abs_vel_q80;barrier=2.0           2.0          0.000000         0.000000        1596                   3            526.333333               2.229006                2.205263                          1.999586                          1.763642                      3         0.989348       True
EURUSD    2025-12 2025-09,2025-10,2025-11              1   oco_first_touch_clean__high_range_q80__k2   oco_first_touch_clean__high_range_q80__k2|100|6        100        6 oco_first_touch_clean   high_range_q80;barrier=2.0           2.0          0.000000         0.000000        1310                   3            434.666667               1.578298                1.571069                          1.393691                          1.334378                      3         0.995420       True
```
