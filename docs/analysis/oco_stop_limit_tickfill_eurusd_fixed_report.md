# OCO Stop-Limit Tick-First-Crossing Analysis

## Setup
- symbols: `EURUSD`
- use_exec_selected: `True`
- quantile fallback: `0.9`
- caps (pips): `0.5,0.8,1.0,1.2,1.5,2.0`

## Tick Overshoot Summary
| symbol   |   rows |   touch_found_rate |   base_mean_gross_pips |   tick_overshoot_mean_pips |   tick_overshoot_median_pips |   tick_overshoot_p90_pips |   tick_overshoot_p95_pips |   tick_overshoot_p99_pips |
|:---------|-------:|-------------------:|-----------------------:|---------------------------:|-----------------------------:|--------------------------:|--------------------------:|--------------------------:|
| EURUSD   | 324963 |           0.999985 |                1.04109 |                   0.136206 |                          0.1 |                       0.3 |                       0.5 |                       1.2 |

## Stop-Limit Cap Sweep
| symbol   |   cap_pips |   fill_rate |   mean_gross_filled_no_extra_slip |   mean_net_filled_full_overshoot |   mean_per_signal_no_extra_slip |   mean_per_signal_full_overshoot |
|:---------|-----------:|------------:|----------------------------------:|---------------------------------:|--------------------------------:|---------------------------------:|
| EURUSD   |        0.5 |    0.942824 |                          0.931086 |                         0.847064 |                        0.87785  |                         0.798632 |
| EURUSD   |        0.8 |    0.975843 |                          0.972296 |                         0.870849 |                        0.948809 |                         0.849812 |
| EURUSD   |        1   |    0.986275 |                          0.987235 |                         0.877513 |                        0.973686 |                         0.865469 |
| EURUSD   |        1.2 |    0.990054 |                          0.999338 |                         0.885829 |                        0.989399 |                         0.877019 |
| EURUSD   |        1.5 |    0.993919 |                          1.01278  |                         0.894542 |                        1.00662  |                         0.889102 |
| EURUSD   |        2   |    0.997058 |                          1.01449  |                         0.891275 |                        1.01151  |                         0.888653 |
