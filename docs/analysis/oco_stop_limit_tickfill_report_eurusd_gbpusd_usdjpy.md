# OCO Stop-Limit Tick-First-Crossing Analysis

## Setup
- symbols: `EURUSD,GBPUSD,USDJPY`
- use_exec_selected: `True`
- quantile fallback: `0.9`
- caps (pips): `0.5,0.8,1.0,1.2,1.5,2.0`

## Tick Overshoot Summary
```
symbol   rows  touch_found_rate  base_mean_gross_pips  tick_overshoot_mean_pips  tick_overshoot_median_pips  tick_overshoot_p90_pips  tick_overshoot_p95_pips  tick_overshoot_p99_pips
EURUSD 328767          0.999982              1.056728                  0.136725                         0.1                      0.3                      0.5                      1.2
GBPUSD 412664          0.999990              1.072781                  0.142874                         0.1                      0.3                      0.5                      1.2
USDJPY 459585          0.999954              1.378528                  0.221513                         0.1                      0.5                      0.7                      1.5
```

## Stop-Limit Cap Sweep
```
symbol  cap_pips  fill_rate  mean_gross_filled_no_extra_slip  mean_net_filled_full_overshoot  mean_per_signal_no_extra_slip  mean_per_signal_full_overshoot
EURUSD       0.5   0.943744                         0.945048                        0.861189                       0.891884                        0.812742
EURUSD       0.8   0.976299                         0.986863                        0.885733                       0.963473                        0.864741
EURUSD       1.0   0.986979                         1.003759                        0.894151                       0.990689                        0.882508
EURUSD       1.2   0.990185                         1.012506                        0.899693                       1.002567                        0.890863
EURUSD       1.5   0.994063                         1.023742                        0.906213                       1.017664                        0.900832
EURUSD       2.0   0.997080                         1.027043                        0.904698                       1.024044                        0.902056
GBPUSD       0.5   0.947553                         1.008270                        0.915674                       0.955389                        0.867649
GBPUSD       0.8   0.980289                         1.025704                        0.916613                       1.005487                        0.898546
GBPUSD       1.0   0.988327                         1.043123                        0.927762                       1.030946                        0.916933
GBPUSD       1.2   0.990266                         1.046251                        0.928925                       1.036067                        0.919883
GBPUSD       1.5   0.992834                         1.051037                        0.930581                       1.043506                        0.923913
GBPUSD       2.0   0.994945                         1.056227                        0.932354                       1.050887                        0.927641
USDJPY       0.5   0.918872                         1.293703                        1.152826                       1.188748                        1.059300
USDJPY       0.8   0.963719                         1.317361                        1.152273                       1.269566                        1.110468
USDJPY       1.0   0.978787                         1.334946                        1.158309                       1.306628                        1.133738
USDJPY       1.2   0.983461                         1.338881                        1.157753                       1.316737                        1.138605
USDJPY       1.5   0.990209                         1.356866                        1.167831                       1.343580                        1.156396
USDJPY       2.0   0.993945                         1.366196                        1.171335                       1.357923                        1.164242
```
