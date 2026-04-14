### Auto Snapshot - Stage 07

- generated_at: `2026-04-12 17:21:09 UTC`
- C01..C10 checks are the logical contract gate before robustness sign-off.
- Open issue rows: 0.

#### Key Results
_empty_

#### Interpretation Notes
- C01..C10 checks are the logical contract gate before robustness sign-off.
- Open issue rows: 0.

#### Action Trigger Summary
| symbol   | metric_id               | band   | severity   | action_code    | action_summary         | owner    |
|:---------|:------------------------|:-------|:-----------|:---------------|:-----------------------|:---------|
| AUDUSD   | S01_lb95_dependence_gap | green  | info       | A0_MONITOR     | within policy band     | research |
| AUDUSD   | S02_practical_lb95_gt0  | green  | info       | A0_MONITOR     | within policy band     | research |
| EURUSD   | S01_lb95_dependence_gap | red    | high       | A2_RECALIBRATE | escalate and remediate | research |
| EURUSD   | S02_practical_lb95_gt0  | green  | info       | A0_MONITOR     | within policy band     | research |
| GBPUSD   | S01_lb95_dependence_gap | amber  | medium     | A1_REVIEW      | review and monitor     | research |
| GBPUSD   | S02_practical_lb95_gt0  | green  | info       | A0_MONITOR     | within policy band     | research |
| USDCAD   | S01_lb95_dependence_gap | amber  | medium     | A1_REVIEW      | review and monitor     | research |
| USDCAD   | S02_practical_lb95_gt0  | green  | info       | A0_MONITOR     | within policy band     | research |
| USDCHF   | S01_lb95_dependence_gap | red    | high       | A2_RECALIBRATE | escalate and remediate | research |
| USDCHF   | S02_practical_lb95_gt0  | green  | info       | A0_MONITOR     | within policy band     | research |
| USDJPY   | S01_lb95_dependence_gap | green  | info       | A0_MONITOR     | within policy band     | research |
| USDJPY   | S02_practical_lb95_gt0  | green  | info       | A0_MONITOR     | within policy band     | research |

#### Details
_empty_

#### Plots
![stage_07_audit_failures](../../figures/oco_bible/stage_07_audit_failures.png)

#### Statistical Inference Ladder (S01-S03)
| symbol   |   lb95_trade_mean_gross_pips |   s01_lb95_dependence_gap |   pvalue_bonferroni |   pvalue_fdr_bh |   s02_practical_lb95_gt0 |   s03_multiplicity_survival |
|:---------|-----------------------------:|--------------------------:|--------------------:|----------------:|-------------------------:|----------------------------:|
| AUDUSD   |                      5.12738 |                -0.0932454 |                   0 |               0 |                        1 |                           1 |
| EURUSD   |                      7.44487 |                 0.666574  |                   0 |               0 |                        1 |                           1 |
| GBPUSD   |                      7.50235 |                 0.398312  |                   0 |               0 |                        1 |                           1 |
| USDCAD   |                      5.28134 |                 0.403015  |                   0 |               0 |                        1 |                           1 |
| USDCHF   |                      5.48371 |                 0.743266  |                   0 |               0 |                        1 |                           1 |
| USDJPY   |                     10.7085  |                 0.220646  |                   0 |               0 |                        1 |                           1 |
