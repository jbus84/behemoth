### Auto Snapshot - Stage 11

- generated_at: `2026-03-10 10:13:11 UTC`
- Execution Monte Carlo uses month x session stress scenarios derived from Stage 04 tickfill artifacts.
- EM01-EM05 summarize mild/moderate survival, month negativity risk, fill-rate decay, and data integrity.

#### Key Results
| symbol   |   signals |   lb95_s1 |   lb95_s2 |   prob_negative_month_s1 |   fill_rate_drop_s1 |   drawdown_proxy_p95_s1 |
|:---------|----------:|----------:|----------:|-------------------------:|--------------------:|------------------------:|
| EURUSD   |    429980 |  1.18004  |  1.10725  |                0         |           0.0101049 |               0         |
| GBPUSD   |    392129 |  0.810873 |  0.747306 |                0         |           0.0100145 |               0.522332  |
| AUDUSD   |    439660 |  0.489323 |  0.429505 |                0.111111  |           0.0103046 |              -0.112555  |
| USDJPY   |    459073 |  1.0729   |  1.00281  |                0         |           0.0102521 |               0.501545  |
| USDCHF   |    369217 |  0.702936 |  0.640603 |                0.0303333 |           0.0103226 |              -0.0221893 |
| USDCAD   |    378368 |  0.571529 |  0.511163 |                0.0259444 |           0.0106667 |              -0.0235458 |

#### Interpretation Notes
- Execution Monte Carlo uses month x session stress scenarios derived from Stage 04 tickfill artifacts.
- EM01-EM05 summarize mild/moderate survival, month negativity risk, fill-rate decay, and data integrity.

#### Action Trigger Summary
| symbol   | metric_id                    | band   | severity   | action_code   | action_summary                      | owner     |
|:---------|:-----------------------------|:-------|:-----------|:--------------|:------------------------------------|:----------|
| AUDUSD   | EM03_prob_negative_month_s1  | green  | info       | A0_MONITOR    | within policy band                  | risk      |
| AUDUSD   | EM04_fill_rate_drop_vs_s0_s1 | green  | info       | A0_MONITOR    | within policy band                  | execution |
| AUDUSD   | EM05_nan_core_fields         | gray   | high       | A9_DATA_GAP   | metric not present in stage metrics | data      |
| EURUSD   | EM03_prob_negative_month_s1  | green  | info       | A0_MONITOR    | within policy band                  | risk      |
| EURUSD   | EM04_fill_rate_drop_vs_s0_s1 | green  | info       | A0_MONITOR    | within policy band                  | execution |
| EURUSD   | EM05_nan_core_fields         | green  | info       | A0_MONITOR    | within policy band                  | data      |
| GBPUSD   | EM03_prob_negative_month_s1  | green  | info       | A0_MONITOR    | within policy band                  | risk      |
| GBPUSD   | EM04_fill_rate_drop_vs_s0_s1 | green  | info       | A0_MONITOR    | within policy band                  | execution |
| GBPUSD   | EM05_nan_core_fields         | green  | info       | A0_MONITOR    | within policy band                  | data      |
| USDCAD   | EM03_prob_negative_month_s1  | green  | info       | A0_MONITOR    | within policy band                  | risk      |
| USDCAD   | EM04_fill_rate_drop_vs_s0_s1 | green  | info       | A0_MONITOR    | within policy band                  | execution |
| USDCAD   | EM05_nan_core_fields         | gray   | high       | A9_DATA_GAP   | metric not present in stage metrics | data      |

#### Details
| symbol   | scenario_id   |   mean_per_signal_pips |   lb95_per_signal_pips |   lb99_per_signal_pips |   mean_per_trade_pips |   mean_fill_rate |   prob_negative_month |   fill_rate_drop_vs_S0 |   drawdown_proxy_p95 |
|:---------|:--------------|-----------------------:|-----------------------:|-----------------------:|----------------------:|-----------------:|----------------------:|-----------------------:|---------------------:|
| EURUSD   | S0_baseline   |               1.26048  |               1.24303  |               1.23702  |              1.27778  |         0.98646  |           0           |              0         |            0         |
| EURUSD   | S1_mild       |               1.19774  |               1.18004  |               1.17405  |              1.22675  |         0.976355 |           0           |              0.0101049 |            0         |
| EURUSD   | S2_moderate   |               1.12497  |               1.10725  |               1.10027  |              1.17623  |         0.956417 |           0           |              0.0300428 |            0         |
| EURUSD   | S3_severe     |               0.99893  |               0.982149 |               0.975095 |              1.07867  |         0.926076 |           0           |              0.0603837 |            0         |
| GBPUSD   | S0_baseline   |               0.884247 |               0.870175 |               0.864605 |              0.890352 |         0.993143 |           0           |              0         |            0.57941   |
| GBPUSD   | S1_mild       |               0.825116 |               0.810873 |               0.804659 |              0.839277 |         0.983128 |           0           |              0.0100145 |            0.522332  |
| GBPUSD   | S2_moderate   |               0.761641 |               0.747306 |               0.741465 |              0.791266 |         0.96256  |           0           |              0.0305828 |            0.466077  |
| GBPUSD   | S3_severe     |               0.643698 |               0.629631 |               0.623198 |              0.690323 |         0.932459 |           0           |              0.0606838 |            0.360717  |
| AUDUSD   | S0_baseline   |               0.555709 |               0.5439   |               0.539617 |              0.557563 |         0.996675 |           0.106333    |              0         |           -0.064557  |
| AUDUSD   | S1_mild       |               0.500575 |               0.489323 |               0.484351 |              0.507492 |         0.98637  |           0.111111    |              0.0103046 |           -0.112555  |
| AUDUSD   | S2_moderate   |               0.440628 |               0.429505 |               0.424774 |              0.456145 |         0.965982 |           0.115556    |              0.0306927 |           -0.171422  |
| AUDUSD   | S3_severe     |               0.333669 |               0.321585 |               0.31749  |              0.356525 |         0.935892 |           0.315556    |              0.060783  |           -0.260771  |
| USDJPY   | S0_baseline   |               1.15096  |               1.13474  |               1.1283   |              1.15791  |         0.993999 |           0           |              0         |            0.554273  |
| USDJPY   | S1_mild       |               1.08924  |               1.0729   |               1.06628  |              1.10724  |         0.983747 |           0           |              0.0102521 |            0.501545  |
| USDJPY   | S2_moderate   |               1.0193   |               1.00281  |               0.997444 |              1.05784  |         0.963564 |           0           |              0.0304348 |            0.44301   |
| USDJPY   | S3_severe     |               0.891014 |               0.875546 |               0.870111 |              0.954916 |         0.933081 |           0           |              0.0609174 |            0.332702  |
| USDCHF   | S0_baseline   |               0.77068  |               0.758833 |               0.753654 |              0.780944 |         0.986856 |           0.000222222 |              0         |            0.0287082 |
| USDCHF   | S1_mild       |               0.714639 |               0.702936 |               0.698143 |              0.731813 |         0.976533 |           0.0303333   |              0.0103226 |           -0.0221893 |
| USDCHF   | S2_moderate   |               0.652669 |               0.640603 |               0.633921 |              0.682491 |         0.956304 |           0.106       |              0.0305519 |           -0.0682946 |
| USDCHF   | S3_severe     |               0.539481 |               0.527428 |               0.522318 |              0.582449 |         0.926229 |           0.111222    |              0.0606271 |           -0.155625  |
| USDCAD   | S0_baseline   |               0.640567 |               0.626395 |               0.619727 |              0.64611  |         0.991421 |           0.0005      |              0         |            0.0268025 |
| USDCAD   | S1_mild       |               0.584652 |               0.571529 |               0.565783 |              0.596125 |         0.980754 |           0.0259444   |              0.0106667 |           -0.0235458 |
| USDCAD   | S2_moderate   |               0.525182 |               0.511163 |               0.50475  |              0.546755 |         0.960543 |           0.0996667   |              0.0308779 |           -0.0704239 |
| USDCAD   | S3_severe     |               0.414978 |               0.40128  |               0.395852 |              0.446298 |         0.929823 |           0.111111    |              0.0615982 |           -0.162355  |

#### Plots
![stage_11_mc_lb95_by_scenario](../../figures/oco_bible/stage_11_mc_lb95_by_scenario.png)
![stage_11_mc_fill_vs_pnl](../../figures/oco_bible/stage_11_mc_fill_vs_pnl.png)

#### Monte Carlo Governance Checks
| symbol   |   checks_total |   checks_failed |   high_critical_failed |
|:---------|---------------:|----------------:|-----------------------:|
| EURUSD   |              5 |               0 |                      0 |
| GBPUSD   |              5 |               0 |                      0 |
| USDJPY   |              5 |               0 |                      0 |

#### Month x Session Summary (head)
| symbol   | scenario_id   | test_month   | session_bucket   |   signals |   mean_per_signal_pips |   lb95_per_signal_pips |   mean_fill_rate |
|:---------|:--------------|:-------------|:-----------------|----------:|-----------------------:|-----------------------:|-----------------:|
| EURUSD   | S0_baseline   | 2025-01      | ASIA             |     29993 |               0.513768 |             0.468273   |         0.999833 |
| EURUSD   | S0_baseline   | 2025-01      | LATE             |       884 |              -0.68132  |            -0.93399    |         1        |
| EURUSD   | S0_baseline   | 2025-01      | LONDON           |     60062 |               0.749132 |             0.710779   |         0.995555 |
| EURUSD   | S0_baseline   | 2025-01      | NY               |     27822 |               0.434685 |             0.354378   |         0.991841 |
| EURUSD   | S0_baseline   | 2025-02      | ASIA             |      9161 |               0.688544 |             0.606481   |         0.998035 |
| EURUSD   | S0_baseline   | 2025-02      | LATE             |       740 |               1.66552  |             1.29387    |         1        |
| EURUSD   | S0_baseline   | 2025-02      | LONDON           |      7006 |               0.616227 |             0.500951   |         0.988867 |
| EURUSD   | S0_baseline   | 2025-02      | NY               |      6748 |               1.10641  |             0.981082   |         0.977771 |
| EURUSD   | S0_baseline   | 2025-03      | ASIA             |      8358 |               1.33477  |             1.21628    |         0.998923 |
| EURUSD   | S0_baseline   | 2025-03      | LATE             |       803 |               0.556656 |             0.300825   |         1        |
| EURUSD   | S0_baseline   | 2025-03      | LONDON           |      9156 |               0.688666 |             0.589051   |         0.999126 |
| EURUSD   | S0_baseline   | 2025-03      | NY               |      6067 |               0.603098 |             0.499455   |         0.993737 |
| EURUSD   | S0_baseline   | 2025-04      | ASIA             |     28379 |               2.18337  |             2.0997     |         0.999612 |
| EURUSD   | S0_baseline   | 2025-04      | LATE             |      7525 |               1.32723  |             1.19935    |         0.998671 |
| EURUSD   | S0_baseline   | 2025-04      | LONDON           |     26288 |               1.66452  |             1.58428    |         0.997565 |
| EURUSD   | S0_baseline   | 2025-04      | NY               |     40889 |               1.82634  |             1.74698    |         0.992394 |
| EURUSD   | S0_baseline   | 2025-05      | ASIA             |     12060 |               1.27919  |             1.1633     |         0.99859  |
| EURUSD   | S0_baseline   | 2025-05      | LATE             |      1552 |               0.154959 |            -0.0569216  |         1        |
| EURUSD   | S0_baseline   | 2025-05      | LONDON           |      6673 |               1.69621  |             1.55556    |         0.994755 |
| EURUSD   | S0_baseline   | 2025-05      | NY               |      7220 |               1.17695  |             1.05641    |         0.992382 |
| EURUSD   | S0_baseline   | 2025-06      | ASIA             |     10073 |               1.45184  |             1.3417     |         0.998412 |
| EURUSD   | S0_baseline   | 2025-06      | LATE             |      1080 |               0.981056 |             0.679901   |         0.988889 |
| EURUSD   | S0_baseline   | 2025-06      | LONDON           |      5448 |               2.86233  |             2.67588    |         0.997063 |
| EURUSD   | S0_baseline   | 2025-06      | NY               |      6420 |               2.03175  |             1.87609    |         0.994393 |
| EURUSD   | S0_baseline   | 2025-07      | ASIA             |      3579 |               1.64168  |             1.42909    |         1        |
| EURUSD   | S0_baseline   | 2025-07      | LATE             |       284 |               0.512777 |             0.00287388 |         1        |
| EURUSD   | S0_baseline   | 2025-07      | LONDON           |     10840 |               2.40808  |             2.24969    |         0.994742 |
| EURUSD   | S0_baseline   | 2025-07      | NY               |      5175 |               1.36561  |             1.21695    |         0.998261 |
| EURUSD   | S0_baseline   | 2025-08      | ASIA             |      3394 |               2.5916   |             2.3659     |         0.999705 |
| EURUSD   | S0_baseline   | 2025-08      | LATE             |       574 |               0.812812 |             0.471212   |         1        |
| EURUSD   | S0_baseline   | 2025-08      | LONDON           |     10655 |               2.58041  |             2.43276    |         0.994463 |
| EURUSD   | S0_baseline   | 2025-08      | NY               |      5938 |               1.52289  |             1.39287    |         0.990738 |
| EURUSD   | S0_baseline   | 2025-09      | ASIA             |      4695 |               0.744833 |             0.559663   |         1        |
| EURUSD   | S0_baseline   | 2025-09      | LATE             |       982 |              -0.839728 |            -1.05427    |         0.998982 |
| EURUSD   | S0_baseline   | 2025-09      | LONDON           |      7207 |               0.946989 |             0.79408    |         0.99223  |
| EURUSD   | S0_baseline   | 2025-09      | NY               |      5110 |               0.832033 |             0.691967   |         0.999804 |
| EURUSD   | S0_baseline   | 2025-10      | ASIA             |      7039 |               0.837508 |             0.71996    |         0.999574 |
| EURUSD   | S0_baseline   | 2025-10      | LATE             |       181 |              -0.419949 |            -1.0271     |         1        |
| EURUSD   | S0_baseline   | 2025-10      | LONDON           |      5870 |               0.956691 |             0.838719   |         0.998978 |
| EURUSD   | S0_baseline   | 2025-10      | NY               |      3317 |               0.913593 |             0.741449   |         1        |

- month_session_rows_shown: `40` of `944`
- full_month_session_artifact: `data/analysis/tick_opportunity_mining/execution_mc_month_session_summary.csv`
