### Auto Snapshot - Stage 07

- generated_at: `2026-03-30 10:10:58 UTC`
- C01..C10 checks are the logical contract gate before robustness sign-off.
- Open issue rows: 0.

#### Key Results
| symbol   |   total_checks |   failed_checks |
|:---------|---------------:|----------------:|
| AUDUSD   |             10 |               0 |
| EURUSD   |             10 |               0 |
| GBPUSD   |             10 |               0 |
| USDCAD   |             10 |               0 |
| USDCHF   |             10 |               0 |
| USDJPY   |             10 |               0 |

#### Interpretation Notes
- C01..C10 checks are the logical contract gate before robustness sign-off.
- Open issue rows: 0.

#### Action Trigger Summary
| symbol   | metric_id               | band   | severity   | action_code    | action_summary         | owner    |
|:---------|:------------------------|:-------|:-----------|:---------------|:-----------------------|:---------|
| AUDUSD   | S01_lb95_dependence_gap | amber  | medium     | A1_REVIEW      | review and monitor     | research |
| AUDUSD   | S02_practical_lb95_gt0  | green  | info       | A0_MONITOR     | within policy band     | research |
| EURUSD   | S01_lb95_dependence_gap | red    | high       | A2_RECALIBRATE | escalate and remediate | research |
| EURUSD   | S02_practical_lb95_gt0  | green  | info       | A0_MONITOR     | within policy band     | research |
| GBPUSD   | S01_lb95_dependence_gap | green  | info       | A0_MONITOR     | within policy band     | research |
| GBPUSD   | S02_practical_lb95_gt0  | green  | info       | A0_MONITOR     | within policy band     | research |
| USDCAD   | S01_lb95_dependence_gap | red    | high       | A2_RECALIBRATE | escalate and remediate | research |
| USDCAD   | S02_practical_lb95_gt0  | green  | info       | A0_MONITOR     | within policy band     | research |
| USDCHF   | S01_lb95_dependence_gap | amber  | medium     | A1_REVIEW      | review and monitor     | research |
| USDCHF   | S02_practical_lb95_gt0  | green  | info       | A0_MONITOR     | within policy band     | research |
| USDJPY   | S01_lb95_dependence_gap | amber  | medium     | A1_REVIEW      | review and monitor     | research |
| USDJPY   | S02_practical_lb95_gt0  | green  | info       | A0_MONITOR     | within policy band     | research |

#### Details
| check_id   | status   |   size |
|:-----------|:---------|-------:|
| C01        | pass     |      6 |
| C02        | pass     |      6 |
| C03        | pass     |      6 |
| C04        | pass     |      6 |
| C05        | pass     |      6 |
| C06        | pass     |      6 |
| C07        | pass     |      6 |
| C08        | pass     |      6 |
| C09        | pass     |      6 |
| C10        | pass     |      6 |

#### Plots
![stage_07_audit_failures](../../figures/oco_bible/stage_07_audit_failures.png)

#### Statistical Inference Ladder (S01-S03)
| symbol   |   lb95_trade_mean_gross_pips |   s01_lb95_dependence_gap |   pvalue_bonferroni |   pvalue_fdr_bh |   s02_practical_lb95_gt0 |   s03_multiplicity_survival |
|:---------|-----------------------------:|--------------------------:|--------------------:|----------------:|-------------------------:|----------------------------:|
| AUDUSD   |                      1.51152 |                  0.410158 |         4.17399e-12 |     1.39133e-12 |                        1 |                           1 |
| EURUSD   |                      2.42312 |                  0.660769 |         9.73222e-13 |     2.30749e-13 |                        1 |                           1 |
| GBPUSD   |                      2.58253 |                  0.124144 |         0           |     0           |                        1 |                           1 |
| USDCAD   |                      1.95503 |                  0.79349  |         6.15095e-11 |     1.23019e-11 |                        1 |                           1 |
| USDCHF   |                      1.748   |                  0.480625 |         1.21902e-13 |     6.09512e-14 |                        1 |                           1 |
| USDJPY   |                      3.79905 |                  0.347844 |         0           |     0           |                        1 |                           1 |
