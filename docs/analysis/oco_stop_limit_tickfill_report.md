# OCO Stop-Limit Tick-First-Crossing Analysis

## Setup
- symbols: `USDCAD`
- use_exec_selected: `True`
- quantile fallback: `0.9`
- caps (pips): `0.5,0.8,1.0,1.2,1.5,2.0`

## Tick Overshoot Summary
| symbol   |   rows |   touch_found_rate |   base_mean_gross_pips |   tick_overshoot_mean_pips |   tick_overshoot_median_pips |   tick_overshoot_p90_pips |   tick_overshoot_p95_pips |   tick_overshoot_p99_pips |
|:---------|-------:|-------------------:|-----------------------:|---------------------------:|-----------------------------:|--------------------------:|--------------------------:|--------------------------:|
| USDCAD   | 501026 |                  0 |                1.05289 |                        nan |                          nan |                       nan |                       nan |                       nan |

## Stop-Limit Cap Sweep
| symbol   |   cap_pips |   fill_rate |   mean_gross_filled_no_extra_slip |   mean_net_filled_full_overshoot |   mean_per_signal_no_extra_slip |   mean_per_signal_full_overshoot |
|:---------|-----------:|------------:|----------------------------------:|---------------------------------:|--------------------------------:|---------------------------------:|
| USDCAD   |        0.5 |           0 |                               nan |                              nan |                             nan |                              nan |
| USDCAD   |        0.8 |           0 |                               nan |                              nan |                             nan |                              nan |
| USDCAD   |        1   |           0 |                               nan |                              nan |                             nan |                              nan |
| USDCAD   |        1.2 |           0 |                               nan |                              nan |                             nan |                              nan |
| USDCAD   |        1.5 |           0 |                               nan |                              nan |                             nan |                              nan |
| USDCAD   |        2   |           0 |                               nan |                              nan |                             nan |                              nan |
