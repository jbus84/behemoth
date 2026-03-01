### Auto Snapshot - Stage 07

- generated_at: `2026-03-01 12:47:46 UTC`
- C01..C10 checks are the logical contract gate before robustness sign-off.
- Open issue rows: 0.

#### Key Results
| symbol   |   total_checks |   failed_checks |
|:---------|---------------:|----------------:|
| EURUSD   |             10 |               0 |
| GBPUSD   |             10 |               0 |
| USDJPY   |             10 |               0 |

#### Interpretation Notes
- C01..C10 checks are the logical contract gate before robustness sign-off.
- Open issue rows: 0.

#### Action Trigger Summary
| symbol   | metric_id               | band   | severity   | action_code   | action_summary     | owner    |
|:---------|:------------------------|:-------|:-----------|:--------------|:-------------------|:---------|
| AUDUSD   | S01_lb95_dependence_gap | green  | info       | A0_MONITOR    | within policy band | research |
| AUDUSD   | S02_practical_lb95_gt0  | green  | info       | A0_MONITOR    | within policy band | research |
| EURUSD   | S01_lb95_dependence_gap | green  | info       | A0_MONITOR    | within policy band | research |
| EURUSD   | S02_practical_lb95_gt0  | green  | info       | A0_MONITOR    | within policy band | research |
| GBPUSD   | S01_lb95_dependence_gap | green  | info       | A0_MONITOR    | within policy band | research |
| GBPUSD   | S02_practical_lb95_gt0  | green  | info       | A0_MONITOR    | within policy band | research |
| USDCAD   | S01_lb95_dependence_gap | green  | info       | A0_MONITOR    | within policy band | research |
| USDCAD   | S02_practical_lb95_gt0  | green  | info       | A0_MONITOR    | within policy band | research |
| USDCHF   | S01_lb95_dependence_gap | green  | info       | A0_MONITOR    | within policy band | research |
| USDCHF   | S02_practical_lb95_gt0  | green  | info       | A0_MONITOR    | within policy band | research |
| USDJPY   | S01_lb95_dependence_gap | green  | info       | A0_MONITOR    | within policy band | research |
| USDJPY   | S02_practical_lb95_gt0  | green  | info       | A0_MONITOR    | within policy band | research |

#### Details
| check_id   | status   |   size |
|:-----------|:---------|-------:|
| C01        | pass     |      3 |
| C02        | pass     |      3 |
| C03        | pass     |      3 |
| C04        | pass     |      3 |
| C05        | pass     |      3 |
| C06        | pass     |      3 |
| C07        | pass     |      3 |
| C08        | pass     |      3 |
| C09        | pass     |      3 |
| C10        | pass     |      3 |

#### Plots
![stage_07_audit_failures](../../figures/oco_bible/stage_07_audit_failures.png)

#### Statistical Inference Ladder (S01-S03)
| symbol   |   lb95_trade_mean_gross_pips |   s01_lb95_dependence_gap |   pvalue_bonferroni |   pvalue_fdr_bh |   s02_practical_lb95_gt0 |   s03_multiplicity_survival |
|:---------|-----------------------------:|--------------------------:|--------------------:|----------------:|-------------------------:|----------------------------:|
| AUDUSD   |                     0.879711 |                         0 |         0           |     0           |                        1 |                           1 |
| EURUSD   |                     2.41589  |                         0 |         0           |     0           |                        1 |                           1 |
| GBPUSD   |                     2.57358  |                         0 |         0           |     0           |                        1 |                           1 |
| USDCAD   |                     1.1828   |                         0 |         4.78284e-13 |     2.39142e-13 |                        1 |                           1 |
| USDCHF   |                     1.43592  |                         0 |         0           |     0           |                        1 |                           1 |
| USDJPY   |                     3.42238  |                         0 |         0           |     0           |                        1 |                           1 |
