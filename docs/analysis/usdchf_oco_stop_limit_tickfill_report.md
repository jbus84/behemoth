# OCO Stop-Limit Tick-First-Crossing Analysis

## Setup
- symbols: `USDCHF`
- use_exec_selected: `True`
- quantile fallback: `0.9`
- caps (pips): `0.5,0.8,1.0,1.2,1.5,2.0`

## Tick Overshoot Summary
| symbol   |   rows |   touch_found_rate |   base_mean_gross_pips |   tick_overshoot_mean_pips |   tick_overshoot_median_pips |   tick_overshoot_p90_pips |   tick_overshoot_p95_pips |   tick_overshoot_p99_pips |
|:---------|-------:|-------------------:|-----------------------:|---------------------------:|-----------------------------:|--------------------------:|--------------------------:|--------------------------:|
| USDCHF   | 364968 |           0.999951 |               0.901119 |                   0.181818 |                  1.11022e-12 |                       0.3 |                       0.5 |                       2.7 |

## Stop-Limit Cap Sweep
| symbol   |   cap_pips |   fill_rate |   mean_gross_filled_no_extra_slip |   mean_net_filled_full_overshoot |   mean_per_signal_no_extra_slip |   mean_per_signal_full_overshoot |
|:---------|-----------:|------------:|----------------------------------:|---------------------------------:|--------------------------------:|---------------------------------:|
| USDCHF   |        0.5 |    0.946351 |                          0.796263 |                         0.717404 |                        0.753545 |                         0.678917 |
| USDCHF   |        0.8 |    0.96817  |                          0.82135  |                         0.730205 |                        0.795206 |                         0.706963 |
| USDCHF   |        1   |    0.974277 |                          0.822693 |                         0.726591 |                        0.801531 |                         0.707902 |
| USDCHF   |        1.2 |    0.977236 |                          0.827001 |                         0.72794  |                        0.808176 |                         0.71137  |
| USDCHF   |        1.5 |    0.982412 |                          0.843561 |                         0.738106 |                        0.828724 |                         0.725124 |
| USDCHF   |        2   |    0.986462 |                          0.85038  |                         0.738151 |                        0.838867 |                         0.728158 |
