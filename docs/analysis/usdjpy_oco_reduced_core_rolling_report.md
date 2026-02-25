# USDJPY OCO Reduced-Core Rolling Selection

## Setup
- family_keep: `oco_first_touch_clean`
- barrier_keep: `[2.0, 3.0]`
- horizon_keep: `[5, 6]`
- locked_quantile: `0.9`
- selection_mode: `auto`
- execution_mode: `stop_limit`
- stop_limit_detail_csv: `data/analysis/tick_opportunity_mining/stop_limit_tickfill_fullcap/USDJPY_stop_limit_tickfill_detail.csv`
- stop_limit_cap_pips: `1.2`
- stop_limit_slippage_mode: `full_overshoot`
- stop_limit_match_rate: `0.998827`
- stop_limit_fill_rate_selected: `0.987160`
- state_train_months: `3`
- min_train_months: `3`
- overlap_corr_max: `0.85`
- overlap_divergence_max: `0.4`
- max_states/min_states: `12/4`
- strict_gate_only: `True`

## Summary
```
symbol  locked_quantile selection_mode execution_mode  state_train_months  months_total  months_scored  rows_total  signal_rows_total  mean_gross_pips  monthly_mean_gross_pips  lb95_month_mean_gross_pips  mean_signal_pips  monthly_mean_signal_pips  lb95_month_mean_signal_pips  positive_months  positive_months_signal  avg_month_rows  avg_month_signal_rows  fill_rate_overall  annualized_rows  capacity_floor_monthly  capacity_floor_annual  capacity_pass_monthly_or_annual
USDJPY              0.9           auto     stop_limit                   3             9              6        7843               7940          3.31998                 3.248265                    2.959013          3.279421                  3.208732                     2.908896                6                       6     1307.166667            1323.333333           0.987783          15686.0                  3000.0                 5000.0                             True
```

## Monthly Portfolio
```
symbol test_month            train_months  states_selected  rows  signal_rows  fill_rate  mean_gross_pips  mean_signal_pips  median_gross_pips  pos_rate      status
USDJPY    2025-04                                        0     0            0        NaN              NaN               NaN                NaN       NaN warmup_skip
USDJPY    2025-05                 2025-04                0     0            0        NaN              NaN               NaN                NaN       NaN warmup_skip
USDJPY    2025-06         2025-04,2025-05                0     0            0        NaN              NaN               NaN                NaN       NaN warmup_skip
USDJPY    2025-07 2025-04,2025-05,2025-06                2  1727         1747   0.988552         3.859351          3.815169                3.3  0.728105          ok
USDJPY    2025-08 2025-05,2025-06,2025-07                2  1545         1564   0.987852         3.674822          3.630179                3.0  0.736573          ok
USDJPY    2025-09 2025-06,2025-07,2025-08                3  1341         1358   0.987482         2.981581          2.944256                2.6  0.709867          ok
USDJPY    2025-10 2025-07,2025-08,2025-09                2  1160         1171   0.990606         3.455776          3.423313                3.0  0.737831          ok
USDJPY    2025-11 2025-08,2025-09,2025-10                2  1227         1245   0.985542         2.700978          2.661928                2.3  0.673092          ok
USDJPY    2025-12 2025-09,2025-10,2025-11                2   843          855   0.985965         2.817082          2.777544                2.4  0.722807          ok
```

## State Schedule (Top Rows)
```
symbol test_month            train_months  selected_rank                                    state_id                                         state_key  bar_ticks  horizon                family                  regime_desc  barrier_pips  overlap_corr_max  overlap_div_max  train_rows  train_months_count  train_avg_month_rows  train_mean_gross_pips  train_mean_signal_pips  train_lb95_trade_mean_gross_pips  train_lb95_month_mean_gross_pips  train_positive_months  train_fill_rate  gate_pass
USDJPY    2025-07 2025-04,2025-05,2025-06              1   oco_first_touch_clean__high_range_q80__k2   oco_first_touch_clean__high_range_q80__k2|100|6        100        6 oco_first_touch_clean   high_range_q80;barrier=2.0           2.0          0.000000         0.000000        5321                   3           1739.666667               4.036501                3.959124                          3.819290                          3.675901                      3         0.980831       True
USDJPY    2025-07 2025-04,2025-05,2025-06              2   oco_first_touch_clean__high_range_q70__k2   oco_first_touch_clean__high_range_q70__k2|100|6        100        6 oco_first_touch_clean   high_range_q70;barrier=2.0           2.0          0.707443         0.291369        4986                   3           1635.666667               3.834298                3.773546                          3.641134                          3.615730                      3         0.984156       True
USDJPY    2025-08 2025-05,2025-06,2025-07              1   oco_first_touch_clean__high_range_q80__k2   oco_first_touch_clean__high_range_q80__k2|100|6        100        6 oco_first_touch_clean   high_range_q80;barrier=2.0           2.0          0.000000         0.000000        3401                   3           1116.666667               3.880567                3.822376                          3.654047                          3.630890                      3         0.985004       True
USDJPY    2025-08 2025-05,2025-06,2025-07              2     oco_first_touch_clean__low_cost_q50__k2     oco_first_touch_clean__low_cost_q50__k2|100|6        100        6 oco_first_touch_clean     low_cost_q50;barrier=2.0           2.0          0.830383         0.071277        2856                   3            941.000000               3.127595                3.091457                          2.937680                          2.974470                      3         0.988445       True
USDJPY    2025-09 2025-06,2025-07,2025-08              1   oco_first_touch_clean__high_range_q80__k2   oco_first_touch_clean__high_range_q80__k2|100|6        100        6 oco_first_touch_clean   high_range_q80;barrier=2.0           2.0          0.000000         0.000000        2536                   3            833.000000               3.794638                3.739274                          3.535150                          3.630890                      3         0.985410       True
USDJPY    2025-09 2025-06,2025-07,2025-08              2 oco_first_touch_clean__high_abs_vel_q80__k2 oco_first_touch_clean__high_abs_vel_q80__k2|100|6        100        6 oco_first_touch_clean high_abs_vel_q80;barrier=2.0           2.0          0.832803         0.158165        2425                   3            798.333333               3.488142                3.444990                          3.259495                          3.322002                      3         0.987629       True
USDJPY    2025-09 2025-06,2025-07,2025-08              3   oco_first_touch_clean__high_range_q70__k2   oco_first_touch_clean__high_range_q70__k2|100|5        100        5 oco_first_touch_clean   high_range_q70;barrier=2.0           2.0          0.419451         0.355932        1938                   3            639.666667               3.045857                3.015996                          2.810312                          2.960017                      3         0.990196       True
USDJPY    2025-10 2025-07,2025-08,2025-09              1   oco_first_touch_clean__high_range_q80__k2   oco_first_touch_clean__high_range_q80__k2|100|6        100        6 oco_first_touch_clean   high_range_q80;barrier=2.0           2.0          0.000000         0.000000        2126                   3            698.333333               3.769308                3.714346                          3.498528                          3.428765                      3         0.985419       True
USDJPY    2025-10 2025-07,2025-08,2025-09              2              oco_first_touch_clean__all__k2              oco_first_touch_clean__all__k2|100|5        100        5 oco_first_touch_clean              all;barrier=2.0           2.0          0.683430         0.302006        1223                   3            403.000000               2.667080                2.636549                          2.371468                          2.253872                      3         0.988553       True
USDJPY    2025-11 2025-08,2025-09,2025-10              1   oco_first_touch_clean__high_range_q80__k2   oco_first_touch_clean__high_range_q80__k2|100|6        100        6 oco_first_touch_clean   high_range_q80;barrier=2.0           2.0          0.000000         0.000000        2036                   3            669.666667               3.669935                3.621267                          3.405459                          3.352495                      3         0.986739       True
USDJPY    2025-11 2025-08,2025-09,2025-10              2 oco_first_touch_clean__high_abs_vel_q80__k2 oco_first_touch_clean__high_abs_vel_q80__k2|100|6        100        6 oco_first_touch_clean high_abs_vel_q80;barrier=2.0           2.0          0.839152         0.101970        2105                   3            693.000000               3.339009                3.297767                          3.095152                          3.086293                      3         0.987648       True
USDJPY    2025-12 2025-09,2025-10,2025-11              1   oco_first_touch_clean__high_range_q80__k2   oco_first_touch_clean__high_range_q80__k2|100|6        100        6 oco_first_touch_clean   high_range_q80;barrier=2.0           2.0          0.000000         0.000000        1808                   3            595.666667               3.300448                3.262113                          3.042622                          2.954651                      3         0.988385       True
USDJPY    2025-12 2025-09,2025-10,2025-11              2 oco_first_touch_clean__high_abs_vel_q70__k2 oco_first_touch_clean__high_abs_vel_q70__k2|100|5        100        5 oco_first_touch_clean high_abs_vel_q70;barrier=2.0           2.0          0.840885         0.148479        1380                   3            454.000000               2.654479                2.619855                          2.391069                          2.333657                      3         0.986957       True
```
