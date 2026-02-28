# OCO Stop-Limit Tick-First-Crossing Analysis

## Setup
- symbols: `USDJPY`
- use_exec_selected: `True`
- quantile fallback: `0.9`
- caps (pips): `0.5,0.8,1.0,1.2,1.5,2.0`

## Tick Overshoot Summary
| symbol   |   rows |   touch_found_rate |   base_mean_gross_pips |   tick_overshoot_mean_pips |   tick_overshoot_median_pips |   tick_overshoot_p90_pips |   tick_overshoot_p95_pips |   tick_overshoot_p99_pips |
|:---------|-------:|-------------------:|-----------------------:|---------------------------:|-----------------------------:|--------------------------:|--------------------------:|--------------------------:|
| USDJPY   | 459585 |           0.999954 |                1.37853 |                   0.221513 |                          0.1 |                       0.5 |                       0.7 |                       1.5 |

## Stop-Limit Cap Sweep
| symbol   |   cap_pips |   fill_rate |   mean_gross_filled_no_extra_slip |   mean_net_filled_full_overshoot |   mean_per_signal_no_extra_slip |   mean_per_signal_full_overshoot |
|:---------|-----------:|------------:|----------------------------------:|---------------------------------:|--------------------------------:|---------------------------------:|
| USDJPY   |        0.5 |    0.918872 |                           1.2937  |                          1.15283 |                         1.18875 |                          1.0593  |
| USDJPY   |        0.8 |    0.963719 |                           1.31736 |                          1.15227 |                         1.26957 |                          1.11047 |
| USDJPY   |        1   |    0.978787 |                           1.33495 |                          1.15831 |                         1.30663 |                          1.13374 |
| USDJPY   |        1.2 |    0.983461 |                           1.33888 |                          1.15775 |                         1.31674 |                          1.13861 |
| USDJPY   |        1.5 |    0.990209 |                           1.35687 |                          1.16783 |                         1.34358 |                          1.1564  |
| USDJPY   |        2   |    0.993945 |                           1.3662  |                          1.17134 |                         1.35792 |                          1.16424 |
