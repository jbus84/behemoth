# OCO Stop-Limit Tick-First-Crossing Analysis

## Setup
- symbols: `USDCAD`
- use_exec_selected: `True`
- quantile fallback: `0.9`
- caps (pips): `0.5,0.8,1.0,1.2,1.5,2.0`

## Tick Overshoot Summary
| symbol   |   rows |   touch_found_rate |   base_mean_gross_pips |   tick_overshoot_mean_pips |   tick_overshoot_median_pips |   tick_overshoot_p90_pips |   tick_overshoot_p95_pips |   tick_overshoot_p99_pips |
|:---------|-------:|-------------------:|-----------------------:|---------------------------:|-----------------------------:|--------------------------:|--------------------------:|--------------------------:|
| USDCAD   | 378368 |           0.999979 |               0.826811 |                   0.188771 |                          0.1 |                       0.4 |                       0.7 |                       1.9 |

## Stop-Limit Cap Sweep
| symbol   |   cap_pips |   fill_rate |   mean_gross_filled_no_extra_slip |   mean_net_filled_full_overshoot |   mean_per_signal_no_extra_slip |   mean_per_signal_full_overshoot |
|:---------|-----------:|------------:|----------------------------------:|---------------------------------:|--------------------------------:|---------------------------------:|
| USDCAD   |        0.5 |    0.91443  |                          0.710386 |                         0.617323 |                        0.649599 |                         0.564499 |
| USDCAD   |        0.8 |    0.961186 |                          0.744361 |                         0.626913 |                        0.715469 |                         0.60258  |
| USDCAD   |        1   |    0.975072 |                          0.755718 |                         0.627406 |                        0.736879 |                         0.611766 |
| USDCAD   |        1.2 |    0.979739 |                          0.765958 |                         0.632973 |                        0.750439 |                         0.620148 |
| USDCAD   |        1.5 |    0.985356 |                          0.783915 |                         0.644202 |                        0.772435 |                         0.634768 |
| USDCAD   |        2   |    0.991421 |                          0.795127 |                         0.645686 |                        0.788306 |                         0.640147 |
