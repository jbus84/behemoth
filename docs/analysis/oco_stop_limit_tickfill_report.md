# OCO Stop-Limit Tick-First-Crossing Analysis

## Setup
- symbols: `EURUSD`
- use_exec_selected: `True`
- quantile fallback: `0.9`
- caps (pips): `0.5,0.8,1.0,1.2,1.5,2.0`

## Tick Overshoot Summary
| symbol   |   rows |   touch_found_rate |   base_mean_gross_pips |   tick_overshoot_mean_pips |   tick_overshoot_median_pips |   tick_overshoot_p90_pips |   tick_overshoot_p95_pips |   tick_overshoot_p99_pips |
|:---------|-------:|-------------------:|-----------------------:|---------------------------:|-----------------------------:|--------------------------:|--------------------------:|--------------------------:|
| EURUSD   | 454544 |           0.999826 |                1.42166 |                   0.144438 |                  2.22045e-12 |                       0.3 |                       0.5 |                       1.3 |

## Stop-Limit Cap Sweep
| symbol   |   cap_pips |   fill_rate |   mean_gross_filled_no_extra_slip |   mean_net_filled_full_overshoot |   mean_per_signal_no_extra_slip |   mean_per_signal_full_overshoot |
|:---------|-----------:|------------:|----------------------------------:|---------------------------------:|--------------------------------:|---------------------------------:|
| EURUSD   |        0.5 |    0.939603 |                           1.31385 |                          1.23367 |                         1.2345  |                          1.15916 |
| EURUSD   |        0.8 |    0.972205 |                           1.3492  |                          1.25169 |                         1.3117  |                          1.2169  |
| EURUSD   |        1   |    0.983658 |                           1.36088 |                          1.25423 |                         1.33864 |                          1.23373 |
| EURUSD   |        1.2 |    0.987821 |                           1.37078 |                          1.25994 |                         1.35408 |                          1.2446  |
| EURUSD   |        1.5 |    0.992082 |                           1.38586 |                          1.26989 |                         1.37488 |                          1.25984 |
| EURUSD   |        2   |    0.995805 |                           1.39027 |                          1.2683  |                         1.38443 |                          1.26298 |
