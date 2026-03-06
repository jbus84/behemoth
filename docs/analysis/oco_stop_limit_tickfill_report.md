# OCO Stop-Limit Tick-First-Crossing Analysis

## Setup
- symbols: `USDCAD`
- use_exec_selected: `True`
- quantile fallback: `0.9`
- caps (pips): `0.5,0.8,1.0,1.2,1.5,2.0`

## Tick Overshoot Summary
| symbol   |   rows |   touch_found_rate |   base_mean_gross_pips |   tick_overshoot_mean_pips |   tick_overshoot_median_pips |   tick_overshoot_p90_pips |   tick_overshoot_p95_pips |   tick_overshoot_p99_pips |
|:---------|-------:|-------------------:|-----------------------:|---------------------------:|-----------------------------:|--------------------------:|--------------------------:|--------------------------:|
| USDCAD   | 527101 |           0.998391 |                 1.0177 |                   0.211795 |                          0.1 |                       0.5 |                       0.8 |                         2 |

## Stop-Limit Cap Sweep
| symbol   |   cap_pips |   fill_rate |   mean_gross_filled_no_extra_slip |   mean_net_filled_full_overshoot |   mean_per_signal_no_extra_slip |   mean_per_signal_full_overshoot |
|:---------|-----------:|------------:|----------------------------------:|---------------------------------:|--------------------------------:|---------------------------------:|
| USDCAD   |        0.5 |    0.892305 |                          0.83307  |                         0.735155 |                        0.743353 |                         0.655983 |
| USDCAD   |        0.8 |    0.946699 |                          0.892342 |                         0.765695 |                        0.844779 |                         0.724883 |
| USDCAD   |        1   |    0.965403 |                          0.921503 |                         0.780215 |                        0.889622 |                         0.753222 |
| USDCAD   |        1.2 |    0.973113 |                          0.939108 |                         0.790227 |                        0.913858 |                         0.768981 |
| USDCAD   |        1.5 |    0.98062  |                          0.962662 |                         0.80492  |                        0.944006 |                         0.789321 |
| USDCAD   |        2   |    0.988129 |                          0.978067 |                         0.808521 |                        0.966457 |                         0.798923 |
