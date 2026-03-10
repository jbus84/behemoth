# OCO Stop-Limit Tick-First-Crossing Analysis

## Setup
- symbols: `USDCAD`
- use_exec_selected: `True`
- quantile fallback: `0.9`
- caps (pips): `0.5,0.8,1.0,1.2,1.5,2.0`

## Tick Overshoot Summary
| symbol   |   rows |   touch_found_rate |   base_mean_gross_pips |   tick_overshoot_mean_pips |   tick_overshoot_median_pips |   tick_overshoot_p90_pips |   tick_overshoot_p95_pips |   tick_overshoot_p99_pips |
|:---------|-------:|-------------------:|-----------------------:|---------------------------:|-----------------------------:|--------------------------:|--------------------------:|--------------------------:|
| USDCAD   | 490796 |           0.998384 |                1.07233 |                   0.208765 |                          0.1 |                       0.5 |                       0.8 |                       2.1 |

## Stop-Limit Cap Sweep
| symbol   |   cap_pips |   fill_rate |   mean_gross_filled_no_extra_slip |   mean_net_filled_full_overshoot |   mean_per_signal_no_extra_slip |   mean_per_signal_full_overshoot |
|:---------|-----------:|------------:|----------------------------------:|---------------------------------:|--------------------------------:|---------------------------------:|
| USDCAD   |        0.5 |    0.892452 |                          0.890493 |                         0.794612 |                        0.794723 |                         0.709153 |
| USDCAD   |        0.8 |    0.945747 |                          0.94113  |                         0.816984 |                        0.890071 |                         0.772661 |
| USDCAD   |        1   |    0.964403 |                          0.967356 |                         0.82856  |                        0.932921 |                         0.799066 |
| USDCAD   |        1.2 |    0.972137 |                          0.987577 |                         0.841143 |                        0.96006  |                         0.817707 |
| USDCAD   |        1.5 |    0.979906 |                          1.01713  |                         0.86151  |                        0.996696 |                         0.844199 |
| USDCAD   |        2   |    0.987687 |                          1.02947  |                         0.861564 |                        1.0168   |                         0.850956 |
