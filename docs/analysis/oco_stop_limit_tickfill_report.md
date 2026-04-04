# OCO Stop-Limit Tick-First-Crossing Analysis

## Setup
- symbols: `USDCAD`
- use_exec_selected: `True`
- quantile fallback: `0.9`
- caps (pips): `0.5,0.8,1.0,1.2,1.5,2.0`

## Tick Overshoot Summary
| symbol   |   rows |   touch_found_rate |   base_mean_gross_pips |   tick_overshoot_mean_pips |   tick_overshoot_median_pips |   tick_overshoot_p90_pips |   tick_overshoot_p95_pips |   tick_overshoot_p99_pips |
|:---------|-------:|-------------------:|-----------------------:|---------------------------:|-----------------------------:|--------------------------:|--------------------------:|--------------------------:|
| USDCAD   | 451709 |           0.996502 |                1.10529 |                    0.24967 |                          0.1 |                       0.5 |                       0.9 |                       2.4 |

## Stop-Limit Cap Sweep
| symbol   |   cap_pips |   fill_rate |   mean_gross_filled_no_extra_slip |   mean_net_filled_full_overshoot |   mean_per_signal_no_extra_slip |   mean_per_signal_full_overshoot |
|:---------|-----------:|------------:|----------------------------------:|---------------------------------:|--------------------------------:|---------------------------------:|
| USDCAD   |        0.5 |    0.888897 |                          0.86508  |                         0.769601 |                        0.768968 |                         0.684097 |
| USDCAD   |        0.8 |    0.939029 |                          0.939901 |                         0.817709 |                        0.882594 |                         0.767852 |
| USDCAD   |        1   |    0.959009 |                          0.969288 |                         0.831152 |                        0.929556 |                         0.797082 |
| USDCAD   |        1.2 |    0.966341 |                          1.00002  |                         0.854574 |                        0.96636  |                         0.82581  |
| USDCAD   |        1.5 |    0.974233 |                          1.02256  |                         0.867617 |                        0.99621  |                         0.845262 |
| USDCAD   |        2   |    0.982996 |                          1.05036  |                         0.881544 |                        1.0325   |                         0.866553 |
