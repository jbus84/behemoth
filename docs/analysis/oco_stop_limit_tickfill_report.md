# OCO Stop-Limit Tick-First-Crossing Analysis

## Setup
- symbols: `USDCAD`
- use_exec_selected: `True`
- quantile fallback: `0.9`
- caps (pips): `0.5,0.8,1.0,1.2,1.5,2.0`

## Tick Overshoot Summary
| symbol   |   rows |   touch_found_rate |   base_mean_gross_pips |   tick_overshoot_mean_pips |   tick_overshoot_median_pips |   tick_overshoot_p90_pips |   tick_overshoot_p95_pips |   tick_overshoot_p99_pips |
|:---------|-------:|-------------------:|-----------------------:|---------------------------:|-----------------------------:|--------------------------:|--------------------------:|--------------------------:|
| USDCAD   | 346993 |           0.999939 |               0.809054 |                   0.178786 |                          0.1 |                       0.4 |                       0.6 |                       1.9 |

## Stop-Limit Cap Sweep
| symbol   |   cap_pips |   fill_rate |   mean_gross_filled_no_extra_slip |   mean_net_filled_full_overshoot |   mean_per_signal_no_extra_slip |   mean_per_signal_full_overshoot |
|:---------|-----------:|------------:|----------------------------------:|---------------------------------:|--------------------------------:|---------------------------------:|
| USDCAD   |        0.5 |    0.921385 |                          0.692191 |                         0.604398 |                        0.637774 |                         0.556883 |
| USDCAD   |        0.8 |    0.96325  |                          0.724237 |                         0.614405 |                        0.697621 |                         0.591826 |
| USDCAD   |        1   |    0.975668 |                          0.738109 |                         0.618453 |                        0.720149 |                         0.603404 |
| USDCAD   |        1.2 |    0.979827 |                          0.747807 |                         0.62395  |                        0.732722 |                         0.611363 |
| USDCAD   |        1.5 |    0.985285 |                          0.7661   |                         0.635643 |                        0.754827 |                         0.626289 |
| USDCAD   |        2   |    0.991328 |                          0.778279 |                         0.63807  |                        0.77153  |                         0.632537 |
