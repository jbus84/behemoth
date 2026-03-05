# OCO Stop-Limit Tick-First-Crossing Analysis

## Setup
- symbols: `USDCAD`
- use_exec_selected: `True`
- quantile fallback: `0.9`
- caps (pips): `0.5,0.8,1.0,1.2,1.5,2.0`

## Tick Overshoot Summary
| symbol   |   rows |   touch_found_rate |   base_mean_gross_pips |   tick_overshoot_mean_pips |   tick_overshoot_median_pips |   tick_overshoot_p90_pips |   tick_overshoot_p95_pips |   tick_overshoot_p99_pips |
|:---------|-------:|-------------------:|-----------------------:|---------------------------:|-----------------------------:|--------------------------:|--------------------------:|--------------------------:|
| USDCAD   | 379629 |           0.996657 |               0.824065 |                   0.188771 |                          0.1 |                       0.4 |                       0.7 |                       1.9 |

## Stop-Limit Cap Sweep
| symbol   |   cap_pips |   fill_rate |   mean_gross_filled_no_extra_slip |   mean_net_filled_full_overshoot |   mean_per_signal_no_extra_slip |   mean_per_signal_full_overshoot |
|:---------|-----------:|------------:|----------------------------------:|---------------------------------:|--------------------------------:|---------------------------------:|
| USDCAD   |        0.5 |    0.911392 |                          0.710386 |                         0.617323 |                        0.647441 |                         0.562624 |
| USDCAD   |        0.8 |    0.957993 |                          0.744361 |                         0.626913 |                        0.713093 |                         0.600578 |
| USDCAD   |        1   |    0.971833 |                          0.755718 |                         0.627406 |                        0.734432 |                         0.609734 |
| USDCAD   |        1.2 |    0.976485 |                          0.765958 |                         0.632973 |                        0.747946 |                         0.618088 |
| USDCAD   |        1.5 |    0.982083 |                          0.783915 |                         0.644202 |                        0.769869 |                         0.632659 |
| USDCAD   |        2   |    0.988128 |                          0.795127 |                         0.645686 |                        0.785688 |                         0.638021 |
