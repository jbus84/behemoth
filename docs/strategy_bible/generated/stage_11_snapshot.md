### Auto Snapshot - Stage 11

- generated_at: `2026-02-27 12:15:07 UTC`
- Execution Monte Carlo uses month x session stress scenarios derived from Stage 04 tickfill artifacts.
- EM01-EM05 summarize mild/moderate survival, month negativity risk, fill-rate decay, and data integrity.

#### Key Results
| symbol   |   signals |   lb95_s1 |   lb95_s2 |   prob_negative_month_s1 |   fill_rate_drop_s1 |   drawdown_proxy_p95_s1 |
|:---------|----------:|----------:|----------:|-------------------------:|--------------------:|------------------------:|
| EURUSD   |    324963 |  0.927147 |  0.854675 |                    0.006 |           0.010333  |            -0.000771565 |
| GBPUSD   |    414128 |  0.92312  |  0.856639 |                    0     |           0.0100266 |             0.65997     |
| USDJPY   |    459585 |  1.25837  |  1.1814   |                    0     |           0.0111806 |             0.701175    |

#### Details
| symbol   | scenario_id   |   mean_per_signal_pips |   lb95_per_signal_pips |   lb99_per_signal_pips |   mean_per_trade_pips |   mean_fill_rate |   prob_negative_month |   fill_rate_drop_vs_S0 |   drawdown_proxy_p95 |
|:---------|:--------------|-----------------------:|-----------------------:|-----------------------:|----------------------:|-----------------:|----------------------:|-----------------------:|---------------------:|
| EURUSD   | S0_baseline   |               1.00627  |               0.989046 |               0.981983 |              1.01243  |         0.993919 |             0         |              0         |          0.0475405   |
| EURUSD   | S1_mild       |               0.944217 |               0.927147 |               0.919396 |              0.959973 |         0.983586 |             0.006     |              0.010333  |         -0.000771565 |
| EURUSD   | S2_moderate   |               0.871076 |               0.854675 |               0.846372 |              0.905019 |         0.962495 |             0.0701111 |              0.0314247 |         -0.0554919   |
| EURUSD   | S3_severe     |               0.748821 |               0.732195 |               0.725099 |              0.803156 |         0.932348 |             0.111111  |              0.0615711 |         -0.14633     |
| GBPUSD   | S0_baseline   |               0.997564 |               0.983914 |               0.979063 |              1.00419  |         0.993398 |             0         |              0         |          0.714986    |
| GBPUSD   | S1_mild       |               0.936911 |               0.92312  |               0.917377 |              0.952754 |         0.983372 |             0         |              0.0100266 |          0.65997     |
| GBPUSD   | S2_moderate   |               0.870607 |               0.856639 |               0.850828 |              0.904242 |         0.962803 |             0         |              0.0305947 |          0.601463    |
| GBPUSD   | S3_severe     |               0.748776 |               0.735545 |               0.730405 |              0.802782 |         0.932726 |             0         |              0.0606719 |          0.487478    |
| USDJPY   | S0_baseline   |               1.34401  |               1.32717  |               1.32074  |              1.3573   |         0.990209 |             0         |              0         |          0.764592    |
| USDJPY   | S1_mild       |               1.27447  |               1.25837  |               1.25185  |              1.30177  |         0.979028 |             0         |              0.0111806 |          0.701175    |
| USDJPY   | S2_moderate   |               1.19716  |               1.1814   |               1.17451  |              1.24888  |         0.958586 |             0         |              0.031623  |          0.640216    |
| USDJPY   | S3_severe     |               1.05936  |               1.04441  |               1.03769  |              1.14274  |         0.927031 |             0         |              0.063178  |          0.520228    |

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
| EURUSD   | S0_baseline   | 2025-04      | ASIA             |     33457 |             1.40268    |               1.34451  |         0.99725  |
| EURUSD   | S0_baseline   | 2025-04      | LATE             |      5379 |             1.10611    |               0.994344 |         0.999442 |
| EURUSD   | S0_baseline   | 2025-04      | LONDON           |     28240 |             1.10882    |               1.05373  |         0.995361 |
| EURUSD   | S0_baseline   | 2025-04      | NY               |     37447 |             1.5076     |               1.43362  |         0.985553 |
| EURUSD   | S0_baseline   | 2025-05      | ASIA             |     17390 |             0.805003   |               0.74237  |         0.996837 |
| EURUSD   | S0_baseline   | 2025-05      | LATE             |      1916 |            -0.00443795 |              -0.151422 |         1        |
| EURUSD   | S0_baseline   | 2025-05      | LONDON           |      9348 |             0.975531   |               0.892256 |         0.999251 |
| EURUSD   | S0_baseline   | 2025-05      | NY               |      9936 |             0.918166   |               0.834066 |         0.982991 |
| EURUSD   | S0_baseline   | 2025-06      | ASIA             |     18231 |             0.677995   |               0.626498 |         0.996819 |
| EURUSD   | S0_baseline   | 2025-06      | LATE             |      1161 |             0.766296   |               0.548328 |         0.958656 |
| EURUSD   | S0_baseline   | 2025-06      | LONDON           |      6614 |             0.98294    |               0.88403  |         0.996674 |
| EURUSD   | S0_baseline   | 2025-06      | NY               |      9241 |             0.872936   |               0.790411 |         0.99394  |
| EURUSD   | S0_baseline   | 2025-07      | ASIA             |      6836 |             0.84664    |               0.759303 |         1        |
| EURUSD   | S0_baseline   | 2025-07      | LATE             |       265 |             0.241405   |              -0.229162 |         1        |
| EURUSD   | S0_baseline   | 2025-07      | LONDON           |     16282 |             1.76483    |               1.67441  |         0.994165 |
| EURUSD   | S0_baseline   | 2025-07      | NY               |      9605 |             1.07941    |               1.00062  |         0.990005 |
| EURUSD   | S0_baseline   | 2025-08      | ASIA             |      3435 |             1.00139    |               0.878795 |         0.996507 |
| EURUSD   | S0_baseline   | 2025-08      | LATE             |       761 |             0.845236   |               0.625639 |         0.998686 |
| EURUSD   | S0_baseline   | 2025-08      | LONDON           |     15524 |             1.63697    |               1.53472  |         0.990273 |
| EURUSD   | S0_baseline   | 2025-08      | NY               |      8312 |             0.963008   |               0.885285 |         0.990255 |
| EURUSD   | S0_baseline   | 2025-09      | ASIA             |      6590 |             0.702518   |               0.615391 |         0.998483 |
| EURUSD   | S0_baseline   | 2025-09      | LATE             |      1079 |            -0.290134   |              -0.416216 |         0.998146 |
| EURUSD   | S0_baseline   | 2025-09      | LONDON           |      9150 |             0.856449   |               0.756063 |         0.988634 |
| EURUSD   | S0_baseline   | 2025-09      | NY               |      7758 |             0.581945   |               0.493043 |         0.99652  |
| EURUSD   | S0_baseline   | 2025-10      | ASIA             |     12273 |             0.537426   |               0.478877 |         0.999267 |
| EURUSD   | S0_baseline   | 2025-10      | LATE             |       328 |            -0.521198   |              -0.743365 |         1        |
| EURUSD   | S0_baseline   | 2025-10      | LONDON           |      8320 |             0.371257   |               0.292436 |         0.996995 |
| EURUSD   | S0_baseline   | 2025-10      | NY               |      5019 |             0.849996   |               0.724987 |         0.99223  |
| EURUSD   | S0_baseline   | 2025-11      | ASIA             |      9818 |            -0.203394   |              -0.259913 |         0.995518 |
| EURUSD   | S0_baseline   | 2025-11      | LATE             |       121 |            -1.31075    |              -1.80687  |         1        |
| EURUSD   | S0_baseline   | 2025-11      | LONDON           |      6908 |             0.557868   |               0.474291 |         0.99725  |
| EURUSD   | S0_baseline   | 2025-11      | NY               |      1715 |             0.0170585  |              -0.128049 |         0.997085 |
| EURUSD   | S0_baseline   | 2025-12      | ASIA             |      6205 |             0.540015   |               0.456766 |         1        |
| EURUSD   | S0_baseline   | 2025-12      | LATE             |       208 |            -0.292526   |              -0.598397 |         1        |
| EURUSD   | S0_baseline   | 2025-12      | LONDON           |      7784 |             0.772412   |               0.691229 |         0.995632 |
| EURUSD   | S0_baseline   | 2025-12      | NY               |      2307 |             1.02773    |               0.885264 |         0.982661 |
| EURUSD   | S1_mild       | 2025-04      | ASIA             |     33457 |             1.33868    |               1.28218  |         0.987264 |
| EURUSD   | S1_mild       | 2025-04      | LATE             |      5379 |             1.04467    |               0.936628 |         0.989446 |
| EURUSD   | S1_mild       | 2025-04      | LONDON           |     28240 |             1.04812    |               0.992179 |         0.985397 |
| EURUSD   | S1_mild       | 2025-04      | NY               |     37447 |             1.43812    |               1.36634  |         0.975142 |

- month_session_rows_shown: `40` of `432`
- full_month_session_artifact: `/Users/danielfisher/repositories/behemoth/data/analysis/tick_opportunity_mining/execution_mc_month_session_summary.csv`
