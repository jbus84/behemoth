### Auto Snapshot - Stage 11

- generated_at: `2026-03-15 12:55:53 UTC`
- Execution Monte Carlo uses month x session stress scenarios derived from Stage 04 tickfill artifacts.
- EM01-EM05 summarize mild/moderate survival, month negativity risk, fill-rate decay, and data integrity.

#### Key Results
| symbol   |   signals |   lb95_s1 |   lb95_s2 |   prob_negative_month_s1 |   fill_rate_drop_s1 |   drawdown_proxy_p95_s1 |
|:---------|----------:|----------:|----------:|-------------------------:|--------------------:|------------------------:|
| EURUSD   |    422926 |  1.38888  |  1.31114  |               0          |           0.0102124 |               0.56821   |
| GBPUSD   |    437491 |  0.779163 |  0.714509 |               0          |           0.0101466 |               0.404783  |
| USDJPY   |    475390 |  1.22862  |  1.15544  |               0          |           0.0103175 |               0.827472  |
| USDCHF   |    347113 |  0.492923 |  0.432755 |               0.0850357  |           0.0101953 |              -0.0476196 |
| AUDUSD   |    446926 |  0.515525 |  0.456139 |               0          |           0.0100782 |               0.0737963 |
| USDCAD   |    484870 |  0.862464 |  0.79771  |               0.00132143 |           0.010663  |               0.0147518 |

#### Interpretation Notes
- Execution Monte Carlo uses month x session stress scenarios derived from Stage 04 tickfill artifacts.
- EM01-EM05 summarize mild/moderate survival, month negativity risk, fill-rate decay, and data integrity.

#### Action Trigger Summary
| trigger            | threshold_or_signal   | action_code                   | action_summary                                                          |
|:-------------------|:----------------------|:------------------------------|:------------------------------------------------------------------------|
| hard_gate_fail     | status=fail           | A3_HALT_RECALIBRATE           | Block promotion and rerun upstream stage diagnostics before continuing. |
| monitoring_warning | band=amber            | A0_MONITOR/A1_RECALIBRATE_CAP | Apply stage runbook remediation and confirm next-run recovery.          |

#### Details
| symbol   | scenario_id   |   mean_per_signal_pips |   lb95_per_signal_pips |   lb99_per_signal_pips |   mean_per_trade_pips |   mean_fill_rate |   prob_negative_month |   fill_rate_drop_vs_S0 |   drawdown_proxy_p95 |
|:---------|:--------------|-----------------------:|-----------------------:|-----------------------:|----------------------:|-----------------:|----------------------:|-----------------------:|---------------------:|
| EURUSD   | S0_baseline   |               1.47179  |               1.45315  |               1.446    |              1.47802  |         0.995784 |           0           |              0         |          0.624198    |
| EURUSD   | S1_mild       |               1.40708  |               1.38888  |               1.38142  |              1.42767  |         0.985572 |           0           |              0.0102124 |          0.56821     |
| EURUSD   | S2_moderate   |               1.32947  |               1.31114  |               1.30388  |              1.37716  |         0.965371 |           0           |              0.0304128 |          0.507695    |
| EURUSD   | S3_severe     |               1.19265  |               1.1741   |               1.16728  |              1.27564  |         0.934941 |           0           |              0.0608432 |          0.39701     |
| GBPUSD   | S0_baseline   |               0.850627 |               0.837418 |               0.831757 |              0.8564   |         0.993259 |           0           |              0         |          0.456842    |
| GBPUSD   | S1_mild       |               0.791854 |               0.779163 |               0.773298 |              0.805456 |         0.983113 |           0           |              0.0101466 |          0.404783    |
| GBPUSD   | S2_moderate   |               0.728054 |               0.714509 |               0.710172 |              0.756523 |         0.962368 |           0           |              0.0308911 |          0.344781    |
| GBPUSD   | S3_severe     |               0.613283 |               0.601022 |               0.595605 |              0.657822 |         0.932294 |           0           |              0.0609657 |          0.242815    |
| USDJPY   | S0_baseline   |               1.30682  |               1.2911   |               1.28429  |              1.31509  |         0.993715 |           0           |              0         |          0.881601    |
| USDJPY   | S1_mild       |               1.24446  |               1.22862  |               1.22169  |              1.26547  |         0.983397 |           0           |              0.0103175 |          0.827472    |
| USDJPY   | S2_moderate   |               1.17073  |               1.15544  |               1.15022  |              1.2155   |         0.963168 |           0           |              0.0305468 |          0.758942    |
| USDJPY   | S3_severe     |               1.04106  |               1.0252   |               1.01882  |              1.1164   |         0.932513 |           0           |              0.0612016 |          0.638072    |
| USDCHF   | S0_baseline   |               0.561354 |               0.548791 |               0.542903 |              0.567161 |         0.989761 |           0.00375     |              0         |         -0.000570403 |
| USDCHF   | S1_mild       |               0.505687 |               0.492923 |               0.488467 |              0.516235 |         0.979566 |           0.0850357   |              0.0101953 |         -0.0476196   |
| USDCHF   | S2_moderate   |               0.445389 |               0.432755 |               0.428519 |              0.464194 |         0.959488 |           0.194107    |              0.0302731 |         -0.0947712   |
| USDCHF   | S3_severe     |               0.337475 |               0.325466 |               0.320106 |              0.363044 |         0.929568 |           0.339071    |              0.0601929 |         -0.188477    |
| AUDUSD   | S0_baseline   |               0.582804 |               0.571276 |               0.566132 |              0.58478  |         0.996621 |           0           |              0         |          0.124462    |
| AUDUSD   | S1_mild       |               0.527509 |               0.515525 |               0.51137  |              0.534705 |         0.986543 |           0           |              0.0100782 |          0.0737963   |
| AUDUSD   | S2_moderate   |               0.467968 |               0.456139 |               0.451716 |              0.4843   |         0.966277 |           0.000428571 |              0.0303445 |          0.0240147   |
| AUDUSD   | S3_severe     |               0.357209 |               0.345637 |               0.341692 |              0.381618 |         0.936038 |           0.112286    |              0.0605833 |         -0.0714668   |
| USDCAD   | S0_baseline   |               0.941397 |               0.923389 |               0.916477 |              0.953294 |         0.98752  |           0           |              0         |          0.066296    |
| USDCAD   | S1_mild       |               0.879807 |               0.862464 |               0.855781 |              0.90065  |         0.976857 |           0.00132143  |              0.010663  |          0.0147518   |
| USDCAD   | S2_moderate   |               0.814527 |               0.79771  |               0.791806 |              0.851536 |         0.956539 |           0.0159286   |              0.0309818 |         -0.0315082   |
| USDCAD   | S3_severe     |               0.69612  |               0.678746 |               0.671471 |              0.752645 |         0.924898 |           0.103286    |              0.0626224 |         -0.121765    |

#### Plots
![stage_11_mc_lb95_by_scenario](../../figures/oco_bible/stage_11_mc_lb95_by_scenario.png)
![stage_11_mc_fill_vs_pnl](../../figures/oco_bible/stage_11_mc_fill_vs_pnl.png)

#### Monte Carlo Governance Checks
| symbol   |   checks_total |   checks_failed |   high_critical_failed |
|:---------|---------------:|----------------:|-----------------------:|
| EURUSD   |              5 |               0 |                      0 |
| GBPUSD   |              5 |               0 |                      0 |
| USDJPY   |              5 |               0 |                      0 |
| USDCHF   |              5 |               0 |                      0 |
| AUDUSD   |              5 |               0 |                      0 |
| USDCAD   |              5 |               0 |                      0 |

#### Month x Session Summary (head)
| symbol   | scenario_id   | test_month   | session_bucket   |   signals |   mean_per_signal_pips |   lb95_per_signal_pips |   mean_fill_rate |
|:---------|:--------------|:-------------|:-----------------|----------:|-----------------------:|-----------------------:|-----------------:|
| EURUSD   | S0_baseline   | 2025-01      | ASIA             |     19736 |               0.400751 |               0.346862 |         0.997365 |
| EURUSD   | S0_baseline   | 2025-01      | LATE             |      2026 |               1.02387  |               0.798865 |         0.981737 |
| EURUSD   | S0_baseline   | 2025-01      | LONDON           |     23677 |               0.626681 |               0.576202 |         0.999831 |
| EURUSD   | S0_baseline   | 2025-01      | NY               |     52896 |               0.747605 |               0.702827 |         0.996276 |
| EURUSD   | S0_baseline   | 2025-02      | ASIA             |      6384 |               1.17447  |               1.05884  |         0.99859  |
| EURUSD   | S0_baseline   | 2025-02      | LATE             |      2098 |               1.16519  |               0.933988 |         0.980458 |
| EURUSD   | S0_baseline   | 2025-02      | LONDON           |      3210 |               0.767128 |               0.599609 |         0.996885 |
| EURUSD   | S0_baseline   | 2025-02      | NY               |     10578 |               1.53307  |               1.40795  |         0.989979 |
| EURUSD   | S0_baseline   | 2025-03      | ASIA             |      5518 |               0.961694 |               0.841269 |         0.999819 |
| EURUSD   | S0_baseline   | 2025-03      | LATE             |      1339 |               0.633796 |               0.418484 |         1        |
| EURUSD   | S0_baseline   | 2025-03      | LONDON           |      7981 |               1.07731  |               0.96201  |         0.995364 |
| EURUSD   | S0_baseline   | 2025-03      | NY               |     13951 |               1.41513  |               1.32212  |         0.997061 |
| EURUSD   | S0_baseline   | 2025-04      | ASIA             |     23317 |               2.67344  |               2.56863  |         0.995325 |
| EURUSD   | S0_baseline   | 2025-04      | LATE             |     12599 |               1.09307  |               0.986215 |         0.994206 |
| EURUSD   | S0_baseline   | 2025-04      | LONDON           |     25296 |               2.34591  |               2.24801  |         0.996442 |
| EURUSD   | S0_baseline   | 2025-04      | NY               |     43379 |               1.99893  |               1.9194   |         0.992277 |
| EURUSD   | S0_baseline   | 2025-05      | ASIA             |     10407 |               1.74956  |               1.62234  |         0.99952  |
| EURUSD   | S0_baseline   | 2025-05      | LATE             |      1300 |               2.89334  |               2.47073  |         1        |
| EURUSD   | S0_baseline   | 2025-05      | LONDON           |      7459 |               1.88169  |               1.7468   |         0.998927 |
| EURUSD   | S0_baseline   | 2025-05      | NY               |      7956 |               2.08906  |               1.94287  |         0.997486 |
| EURUSD   | S0_baseline   | 2025-06      | ASIA             |      7610 |               1.34706  |               1.22181  |         0.996978 |
| EURUSD   | S0_baseline   | 2025-06      | LATE             |       900 |               1.69523  |               1.34289  |         0.995556 |
| EURUSD   | S0_baseline   | 2025-06      | LONDON           |      4265 |               1.86463  |               1.66985  |         0.991325 |
| EURUSD   | S0_baseline   | 2025-06      | NY               |      5181 |               2.92001  |               2.70573  |         0.982243 |
| EURUSD   | S0_baseline   | 2025-07      | ASIA             |      5989 |               1.07594  |               0.952818 |         1        |
| EURUSD   | S0_baseline   | 2025-07      | LATE             |       616 |               0.955651 |               0.485892 |         1        |
| EURUSD   | S0_baseline   | 2025-07      | LONDON           |      3230 |               2.76322  |               2.49995  |         0.990093 |
| EURUSD   | S0_baseline   | 2025-07      | NY               |     10261 |               2.60873  |               2.45414  |         0.990059 |
| EURUSD   | S0_baseline   | 2025-08      | ASIA             |      6851 |               1.2281   |               1.12368  |         0.999854 |
| EURUSD   | S0_baseline   | 2025-08      | LATE             |       391 |               1.31032  |               0.718576 |         0.97954  |
| EURUSD   | S0_baseline   | 2025-08      | LONDON           |      4592 |               2.88284  |               2.66251  |         0.993249 |
| EURUSD   | S0_baseline   | 2025-08      | NY               |     11515 |               1.65548  |               1.54407  |         0.998524 |
| EURUSD   | S0_baseline   | 2025-09      | ASIA             |      5028 |               1.16245  |               1.02078  |         1        |
| EURUSD   | S0_baseline   | 2025-09      | LATE             |       469 |               1.41145  |               0.982028 |         0.995736 |
| EURUSD   | S0_baseline   | 2025-09      | LONDON           |      4873 |               1.34719  |               1.15837  |         0.992407 |
| EURUSD   | S0_baseline   | 2025-09      | NY               |      8473 |               1.37034  |               1.23838  |         0.99764  |
| EURUSD   | S0_baseline   | 2025-10      | ASIA             |      4167 |               1.63857  |               1.48199  |         0.99952  |
| EURUSD   | S0_baseline   | 2025-10      | LATE             |       588 |               0.735907 |               0.353456 |         1        |
| EURUSD   | S0_baseline   | 2025-10      | LONDON           |      4407 |               0.723137 |               0.567476 |         0.991377 |
| EURUSD   | S0_baseline   | 2025-10      | NY               |      7396 |               1.11951  |               1.0028   |         0.995538 |

- month_session_rows_shown: `40` of `1344`
- full_month_session_artifact: `data/analysis/tick_opportunity_mining_dukascopy_candidate/execution_mc_month_session_summary.csv`
