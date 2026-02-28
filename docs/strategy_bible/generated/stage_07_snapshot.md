### Auto Snapshot - Stage 07

- generated_at: `2026-02-28 08:46:09 UTC`
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
| EURUSD   | S01_lb95_dependence_gap | green  | info       | A0_MONITOR    | within policy band | research |
| EURUSD   | S02_practical_lb95_gt0  | green  | info       | A0_MONITOR    | within policy band | research |
| GBPUSD   | S01_lb95_dependence_gap | green  | info       | A0_MONITOR    | within policy band | research |
| GBPUSD   | S02_practical_lb95_gt0  | green  | info       | A0_MONITOR    | within policy band | research |
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
| EURUSD   |                     1.04912  |                         0 |         1.45698e-08 |     2.91396e-09 |                        1 |                           1 |
| GBPUSD   |                     0.973913 |                         0 |         0           |     0           |                        1 |                           1 |
| USDJPY   |                     1.33687  |                         0 |         0           |     0           |                        1 |                           1 |
