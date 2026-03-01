# OCO Stop-Limit Tick-First-Crossing Analysis

## Setup
- symbols: `EURUSD`
- use_exec_selected: `True`
- quantile fallback: `0.9`
- caps (pips): `0.5,0.8,1.0,1.2,1.5,2.0`

## Tick Overshoot Summary
| symbol   |   rows |   touch_found_rate |   base_mean_gross_pips |   tick_overshoot_mean_pips |   tick_overshoot_median_pips |   tick_overshoot_p90_pips |   tick_overshoot_p95_pips |   tick_overshoot_p99_pips |
|:---------|-------:|-------------------:|-----------------------:|---------------------------:|-----------------------------:|--------------------------:|--------------------------:|--------------------------:|
| EURUSD   | 395199 |           0.999954 |                1.50325 |                   0.143567 |                  2.22045e-12 |                       0.3 |                       0.5 |                       1.3 |

## Stop-Limit Cap Sweep
| symbol   |   cap_pips |   fill_rate |   mean_gross_filled_no_extra_slip |   mean_net_filled_full_overshoot |   mean_per_signal_no_extra_slip |   mean_per_signal_full_overshoot |
|:---------|-----------:|------------:|----------------------------------:|---------------------------------:|--------------------------------:|---------------------------------:|
| EURUSD   |        0.5 |    0.941543 |                           1.38596 |                          1.30509 |                         1.30494 |                          1.2288  |
| EURUSD   |        0.8 |    0.973479 |                           1.42392 |                          1.32616 |                         1.38615 |                          1.29099 |
| EURUSD   |        1   |    0.98417  |                           1.43278 |                          1.32649 |                         1.4101  |                          1.30549 |
| EURUSD   |        1.2 |    0.988052 |                           1.44583 |                          1.33562 |                         1.42855 |                          1.31966 |
| EURUSD   |        1.5 |    0.992224 |                           1.46727 |                          1.35203 |                         1.45586 |                          1.34152 |
| EURUSD   |        2   |    0.995658 |                           1.46877 |                          1.34802 |                         1.46239 |                          1.34217 |
