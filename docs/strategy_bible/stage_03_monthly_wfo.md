# Stage 3 - Monthly Walk-Forward Modeling

## Objective
Evaluate model filtering with strict monthly walk-forward ordering and quantify threshold robustness.

## Inputs
- WFO metrics:
- `data/analysis/tick_opportunity_mining/wfo_*/<SYMBOL>_monthly_metrics_all.csv`
- WFO thresholds:
- `data/analysis/tick_opportunity_mining/wfo_*/<SYMBOL>_monthly_thresholds_all.csv`
- WFO predictions:
- `data/analysis/tick_opportunity_mining/wfo_*/<SYMBOL>_monthly_predictions_all.parquet`

## Process
- Train on prior months only and score next month.
- Apply execution quantile filter (`q`, default 0.9).
- Compute threshold/calibration/turnover diagnostics (`W13-W15`).

## Exact Calculations
- `W13_threshold_fragility`:
- Around execution `q`, aggregate mean gross by quantile and compute slope:
- `(max(mean_gross_near_q)-min(mean_gross_near_q)) / (max(q_near)-min(q_near))`
- `W14_brier_drift_std = std(monthly_brier)`
- `W15_selection_turnover = 1 - mean(Jaccard(selected_uid_month_t, selected_uid_month_t-1))`

## Causality / Leakage Controls
- Strict 3M train -> 1M test ordering.
- Selection thresholding uses historical window only (rolling causal threshold).

## Failure Modes
- Threshold fragility: tiny `q` change causes large performance change.
- Calibration drift over months.
- High turnover suggesting unstable signal identity.

## Interpretation Guide
- Lower `W13` is less fragile.
- Lower `W14` indicates more stable calibration.
- Lower `W15` indicates higher month-to-month continuity.

## Validation Gates
- WFO gating and leakage contract checks are hard gates.
- `W13-W15` remain informational until promoted.

## Canonical Analysis Reports
- `docs/analysis/eurusd_tick_opportunity_monthly_wfo_oco_fullcap_report.md`
- `docs/analysis/gbpusd_tick_opportunity_monthly_wfo_oco_fullcap_report.md`
- `docs/analysis/usdjpy_tick_opportunity_monthly_wfo_oco_fullcap_report.md`
- `docs/analysis/oco_threshold_sensitivity_report.md`

## Operator Decision Tree
- If any hard gate in this stage fails, block promotion and escalate using the operator runbook.
- If only warning/amber diagnostics trigger, continue with mitigation and add an owner/deadline in remediation artifacts.

## How To Run
- Run the `Reproduction Commands` in this stage exactly as listed.
- Confirm artifacts are refreshed and timestamps are current before interpreting outcomes.

## How To Interpret Outputs
- Read `Key Results` first for pass/fail posture and core health metrics.
- Use `Interpretation Notes` and `Action Trigger Summary` to map observed values to operational actions.

## What To Do If It Fails
- `critical/high`: halt deployment progression, remediate root cause, rerun stage and downstream dependent stages.
- `medium/low`: open tracked remediation with owner and ETA, monitor for recurrence in next cycle.

## Reproduction Commands
```bash
uv run python scripts/run_tick_opportunity_monthly_wfo.py \
  --config configs/research/experiments/eurusd_tick_opportunity_monthly_wfo_oco_fullcap_2025.yaml
uv run python scripts/build_oco_threshold_sensitivity_report.py
```

## Traceability
- `scripts/run_tick_opportunity_monthly_wfo.py`
- `scripts/build_oco_threshold_sensitivity_report.py`
- `docs/analysis/*_tick_opportunity_monthly_wfo_oco_*_report.md`
- `docs/strategy_bible/generated/stage_03_snapshot.md`

## Generated Run Snapshot
<!-- GENERATED:STAGE_03:START -->
### Auto Snapshot - Stage 03

- generated_at: `2026-02-27 14:15:43 UTC`
- Execution threshold summary is aligned to quantile=0.9.
- Metrics are strictly month-forward (3M train -> 1M test).
- W13-W15 are informational diagnostics for threshold fragility, calibration drift, and selection turnover.

#### Key Results
| symbol   |   months |   auc_mean |   brier_mean |   test_rows_total |   w13_threshold_fragility |   w14_brier_drift_std |   w15_selection_turnover |
|:---------|---------:|-----------:|-------------:|------------------:|--------------------------:|----------------------:|-------------------------:|
| EURUSD   |        9 |   0.526973 |     0.249766 |        3.3563e+06 |                   1.34602 |           0.00162703  |                0.0799501 |
| GBPUSD   |        9 |   0.522514 |     0.24961  |        4.2722e+06 |                   1.25854 |           0.000778954 |                0.0593122 |
| USDJPY   |        9 |   0.526568 |     0.247866 |        4.5452e+06 |                   1.50447 |           0.000967283 |                0.0163693 |

#### Interpretation Notes
- Execution threshold summary is aligned to quantile=0.9.
- Metrics are strictly month-forward (3M train -> 1M test).
- W13-W15 are informational diagnostics for threshold fragility, calibration drift, and selection turnover.

#### Action Trigger Summary
| symbol   | metric_id               | band   | severity   | action_code   | action_summary     | owner    |
|:---------|:------------------------|:-------|:-----------|:--------------|:-------------------|:---------|
| EURUSD   | W13_threshold_fragility | green  | info       | A0_MONITOR    | within policy band | research |
| EURUSD   | W14_brier_drift_std     | green  | info       | A0_MONITOR    | within policy band | research |
| EURUSD   | W15_selection_turnover  | green  | info       | A0_MONITOR    | within policy band | research |
| GBPUSD   | W13_threshold_fragility | green  | info       | A0_MONITOR    | within policy band | research |
| GBPUSD   | W14_brier_drift_std     | green  | info       | A0_MONITOR    | within policy band | research |
| GBPUSD   | W15_selection_turnover  | green  | info       | A0_MONITOR    | within policy band | research |
| USDJPY   | W13_threshold_fragility | green  | info       | A0_MONITOR    | within policy band | research |
| USDJPY   | W14_brier_drift_std     | green  | info       | A0_MONITOR    | within policy band | research |
| USDJPY   | W15_selection_turnover  | green  | info       | A0_MONITOR    | within policy band | research |

#### Details
| symbol   |   months |   mean_coverage |   mean_gross_pips |   rows_selected |
|:---------|---------:|----------------:|------------------:|----------------:|
| EURUSD   |        9 |       0.0953233 |          0.884677 |          325515 |
| GBPUSD   |        9 |       0.096381  |          0.996288 |          414128 |
| USDJPY   |        9 |       0.101975  |          1.33948  |          459585 |

#### Plots
![stage_03_wfo_monthly_gross](../figures/oco_bible/stage_03_wfo_monthly_gross.png)

#### Threshold Robustness Around Execution Quantile
| symbol   | test_month   |   quantile |   mean_gross_pips |   coverage |   selected_rows |
|:---------|:-------------|-----------:|------------------:|-----------:|----------------:|
| EURUSD   | aggregate    |       0.8  |          0.758561 |  0.191746  |         72544.3 |
| EURUSD   | aggregate    |       0.9  |          0.884677 |  0.0953233 |         36168.3 |
| EURUSD   | aggregate    |       0.95 |          0.960465 |  0.0475931 |         18029.7 |
| GBPUSD   | aggregate    |       0.8  |          0.870914 |  0.196065  |         93435.1 |
| GBPUSD   | aggregate    |       0.9  |          0.996288 |  0.096381  |         46014.2 |
| GBPUSD   | aggregate    |       0.95 |          1.0597   |  0.0463834 |         22195.2 |
| USDJPY   | aggregate    |       0.8  |          1.1889   |  0.202026  |        101383   |
| USDJPY   | aggregate    |       0.9  |          1.33948  |  0.101975  |         51065   |
| USDJPY   | aggregate    |       0.95 |          1.41457  |  0.0514609 |         25614.4 |

#### Overfitting Diagnostics (Exec Quantile)
| symbol   |   quantile |   rows |   months |   positive_months |   lb95_trade_mean_gross_pips |   lb95_trade_mean_gross_pips_iid |   lb95_trade_mean_gross_pips_month_block |   pvalue_month_mean_gt0 |   pvalue_bonferroni |   pvalue_fdr_bh |   uplift_vs_null_pips |   pvalue_perm_uplift |   pvalue_perm_fdr_bh | majority_positive_months   | bonferroni_pass_10pct   | fdr_pass_10pct   | perm_fdr_pass_10pct   |
|:---------|-----------:|-------:|---------:|------------------:|-----------------------------:|---------------------------------:|-----------------------------------------:|------------------------:|--------------------:|----------------:|----------------------:|---------------------:|---------------------:|:---------------------------|:------------------------|:-----------------|:----------------------|
| EURUSD   |        0.9 | 325515 |        9 |                 9 |                      1.02232 |                              nan |                                      nan |             1.15261e-09 |         1.15261e-09 |     1.15261e-09 |                   nan |                  nan |                  nan | True                       | True                    | True             | False                 |
| GBPUSD   |        0.9 | 414128 |        9 |                 9 |                      1.00211 |                              nan |                                      nan |             0           |         0           |     0           |                   nan |                  nan |                  nan | True                       | True                    | True             | False                 |
| USDJPY   |        0.9 | 459585 |        9 |                 9 |                      1.36145 |                              nan |                                      nan |             0           |         0           |     0           |                   nan |                  nan |                  nan | True                       | True                    | True             | False                 |

- Interpretation: these diagnostics are computed on WFO out-of-sample predictions only.
- `bonferroni_pass_10pct` and `fdr_pass_10pct` summarize multiplicity-adjusted significance at alpha=0.10.

#### Leakage/Label Integrity (WFO Focus)
| symbol   |   checks_total |   checks_failed |   high_critical_failed |
|:---------|---------------:|----------------:|-----------------------:|
| EURUSD   |              6 |               0 |                      0 |
| GBPUSD   |              6 |               0 |                      0 |
| USDJPY   |              6 |               0 |                      0 |
<!-- GENERATED:STAGE_03:END -->
