# OCO Stop-Limit Tick-First-Crossing Analysis

## Setup
- symbols: `EURUSD,GBPUSD,USDJPY,USDCHF,AUDUSD,USDCAD`
- use_exec_selected: `True`
- quantile fallback: `0.9`
- caps (pips): `0.5,0.8,1.0,1.2,1.5,2.0`

## Tick Overshoot Summary
| symbol   |   rows |   touch_found_rate |   base_mean_gross_pips |   tick_overshoot_mean_pips |   tick_overshoot_median_pips |   tick_overshoot_p90_pips |   tick_overshoot_p95_pips |   tick_overshoot_p99_pips |
|:---------|-------:|-------------------:|-----------------------:|---------------------------:|-----------------------------:|--------------------------:|--------------------------:|--------------------------:|
| EURUSD   |    930 |           0.898925 |             -0.0853763 |                    0.14067 |                          0.1 |                       0.4 |                       0.6 |                       0.9 |
| GBPUSD   |      0 |         nan        |            nan         |                  nan       |                        nan   |                     nan   |                     nan   |                     nan   |
| USDJPY   |      0 |         nan        |            nan         |                  nan       |                        nan   |                     nan   |                     nan   |                     nan   |
| USDCHF   |      0 |         nan        |            nan         |                  nan       |                        nan   |                     nan   |                     nan   |                     nan   |
| AUDUSD   |      0 |         nan        |            nan         |                  nan       |                        nan   |                     nan   |                     nan   |                     nan   |
| USDCAD   |      0 |         nan        |            nan         |                  nan       |                        nan   |                     nan   |                     nan   |                     nan   |

## Stop-Limit Cap Sweep
| symbol   |   cap_pips |   fill_rate |   mean_gross_filled_no_extra_slip |   mean_net_filled_full_overshoot |   mean_per_signal_no_extra_slip |   mean_per_signal_full_overshoot |
|:---------|-----------:|------------:|----------------------------------:|---------------------------------:|--------------------------------:|---------------------------------:|
| EURUSD   |        0.5 |    0.823656 |                        -0.357833  |                        -0.444256 |                      -0.294731  |                        -0.365914 |
| EURUSD   |        0.8 |    0.886022 |                        -0.142718  |                        -0.263835 |                      -0.126452  |                        -0.233763 |
| EURUSD   |        1   |    0.892473 |                        -0.0954217 |                        -0.222169 |                      -0.0851613 |                        -0.19828  |
| EURUSD   |        1.2 |    0.893548 |                        -0.101203  |                        -0.229001 |                      -0.0904301 |                        -0.204624 |
| EURUSD   |        1.5 |    0.894624 |                        -0.0885817 |                        -0.217668 |                      -0.0792473 |                        -0.194731 |
| EURUSD   |        2   |    0.895699 |                        -0.0747899 |                        -0.205522 |                      -0.0669892 |                        -0.184086 |
