# OCO Stop-Limit Tick-First-Crossing Analysis

## Setup
- symbols: `USDCHF`
- use_exec_selected: `True`
- quantile fallback: `0.9`
- caps (pips): `0.5,0.8,1.0,1.2,1.5,2.0`

## Tick Overshoot Summary
| symbol   |   rows |   touch_found_rate |   base_mean_gross_pips |   tick_overshoot_mean_pips |   tick_overshoot_median_pips |   tick_overshoot_p90_pips |   tick_overshoot_p95_pips |   tick_overshoot_p99_pips |
|:---------|-------:|-------------------:|-----------------------:|---------------------------:|-----------------------------:|--------------------------:|--------------------------:|--------------------------:|
| USDCHF   | 348015 |           0.998193 |               0.854698 |                   0.170283 |                  1.11022e-12 |                       0.3 |                       0.5 |                       2.2 |

## Stop-Limit Cap Sweep
| symbol   |   cap_pips |   fill_rate |   mean_gross_filled_no_extra_slip |   mean_net_filled_full_overshoot |   mean_per_signal_no_extra_slip |   mean_per_signal_full_overshoot |
|:---------|-----------:|------------:|----------------------------------:|---------------------------------:|--------------------------------:|---------------------------------:|
| USDCHF   |        0.5 |    0.947962 |                          0.773903 |                         0.694601 |                        0.73363  |                         0.658455 |
| USDCHF   |        0.8 |    0.968996 |                          0.785184 |                         0.694132 |                        0.76084  |                         0.67261  |
| USDCHF   |        1   |    0.976145 |                          0.795691 |                         0.698744 |                        0.77671  |                         0.682075 |
| USDCHF   |        1.2 |    0.978754 |                          0.800919 |                         0.701367 |                        0.783902 |                         0.686465 |
| USDCHF   |        1.5 |    0.9838   |                          0.803947 |                         0.698204 |                        0.790923 |                         0.686893 |
| USDCHF   |        2   |    0.98698  |                          0.807604 |                         0.696613 |                        0.79709  |                         0.687543 |
