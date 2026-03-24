# OCO Stop-Limit Tick-First-Crossing Analysis

## Setup
- symbols: `EURUSD`
- use_exec_selected: `True`
- quantile fallback: `0.9`
- caps (pips): `0.5,0.8,1.0,1.2,1.5,2.0`

## Tick Overshoot Summary
| symbol   |   rows |   touch_found_rate |   base_mean_gross_pips |   tick_overshoot_mean_pips |   tick_overshoot_median_pips |   tick_overshoot_p90_pips |   tick_overshoot_p95_pips |   tick_overshoot_p99_pips |
|:---------|-------:|-------------------:|-----------------------:|---------------------------:|-----------------------------:|--------------------------:|--------------------------:|--------------------------:|
| EURUSD   | 490428 |           0.948525 |               0.839309 |                   0.912948 |                          0.1 |                       0.5 |                       0.9 |                      27.7 |

## Stop-Limit Cap Sweep
| symbol   |   cap_pips |   fill_rate |   mean_gross_filled_no_extra_slip |   mean_net_filled_full_overshoot |   mean_per_signal_no_extra_slip |   mean_per_signal_full_overshoot |
|:---------|-----------:|------------:|----------------------------------:|---------------------------------:|--------------------------------:|---------------------------------:|
| EURUSD   |        0.5 |    0.859614 |                          0.755277 |                         0.659646 |                        0.649247 |                         0.567041 |
| EURUSD   |        0.8 |    0.892904 |                          0.788139 |                         0.673759 |                        0.703732 |                         0.601602 |
| EURUSD   |        1   |    0.903857 |                          0.80207  |                         0.678386 |                        0.724957 |                         0.613164 |
| EURUSD   |        1.2 |    0.907919 |                          0.809005 |                         0.681007 |                        0.734511 |                         0.618299 |
| EURUSD   |        1.5 |    0.91194  |                          0.822741 |                         0.689537 |                        0.750291 |                         0.628816 |
| EURUSD   |        2   |    0.9159   |                          0.830183 |                         0.690089 |                        0.760365 |                         0.632052 |
