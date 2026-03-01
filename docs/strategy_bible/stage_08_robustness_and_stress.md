# Stage 8 - Robustness and Stress

## Objective
Quantify conservative expectancy and stress elasticity under cost and regime perturbations.

## Inputs
- Robustness summary:
- `data/analysis/tick_opportunity_mining/full_robustness/<SYMBOL>_oco_robustness_summary.csv`
- Reduced monthly outputs:
- `data/analysis/tick_opportunity_mining/reduced_core_rolling*/<SYMBOL>_oco_reduced_monthly.csv`

## Process
- Evaluate bootstrap LB95 and multiplicity-adjusted metrics.
- Evaluate cost-plus stress curve behavior.
- Compute stress diagnostics (`T01-T04`).

## Exact Calculations
- `T01_stress_elasticity`:
- slope across available `mean_net_pips_costplus_*` levels
- `T02_first_negative_costplus`:
- minimum stress level where net turns negative; if never negative, set to max tested level
- `T03_post_worst_month_recovery`:
- `mean_gross(next_month_after_worst) / abs(mean_gross(worst_month))`
- `T04_max_survivable_cost_lb95_trade`:
- highest extra round-trip cost where `lb95_trade_mean_net_pips_costplus_* > 0`
- if crossing exists between stress points, estimate crossing with linear interpolation

## Causality / Leakage Controls
- Uses finalized out-of-sample monthly artifacts only.

## Failure Modes
- Positive mean but negative conservative lower bound.
- Excessive sensitivity to cost assumptions.
- Poor recovery after adverse month.

## Interpretation Guide
- `T01` less negative is more resilient.
- Higher `T02` implies deeper cost resilience.
- Higher `T04` gives a direct operational extra-cost headroom estimate under LB95.
- Higher `T03` suggests stronger post-worst-month recovery efficiency.

## Validation Gates
- Robustness LB95 and monthly consistency are hard promotion criteria.
- `T01-T04` are stress diagnostics for hardening.

## Canonical Analysis Reports
- `docs/analysis/eurusd_oco_monthly_wfo_robustness_fullcap_report.md`
- `docs/analysis/gbpusd_oco_monthly_wfo_robustness_fullcap_report.md`
- `docs/analysis/usdjpy_oco_monthly_wfo_robustness_fullcap_report.md`
- `docs/analysis/remediation_metric_decomposition.md`

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
uv run python scripts/analyze_oco_monthly_wfo_robustness.py \
  --symbols EURUSD,GBPUSD,USDJPY,USDCHF
```

## Traceability
- `scripts/analyze_oco_monthly_wfo_robustness.py`
- `docs/analysis/*_oco_monthly_wfo_robustness_*_report.md`
- `docs/strategy_bible/generated/stage_08_snapshot.md`

## Generated Run Snapshot
<!-- GENERATED:STAGE_08:START -->
### Auto Snapshot - Stage 08

- generated_at: `2026-03-01 12:47:46 UTC`
- Robustness summary uses bootstrap lower bounds from the configured smoke/full run artifacts.
- Interpretation: LB95 > 0 indicates conservative positive expectancy under sampled uncertainty.
- Overfit panel adds month-stratified null uplift and dependence-aware LB95 comparisons.
- T01-T04 summarize stress elasticity, negative-cost crossing, max survivable cost, and post-worst-month recovery efficiency.

#### Key Results
| symbol   |   quantile |   rows |   months |   mean_gross_pips |   lb95_trade_mean_gross_pips |   positive_months |
|:---------|-----------:|-------:|---------:|------------------:|-----------------------------:|------------------:|
| EURUSD   |        0.9 |   6982 |       11 |          2.52728  |                     2.41589  |                11 |
| GBPUSD   |        0.9 |   6890 |        6 |          2.66852  |                     2.57358  |                 6 |
| AUDUSD   |        0.9 |   4188 |        6 |          0.971705 |                     0.879711 |                 6 |
| USDJPY   |        0.9 |   7940 |        6 |          3.53076  |                     3.42238  |                 6 |
| USDCHF   |        0.9 |   4173 |        6 |          1.54333  |                     1.43592  |                 6 |
| USDCAD   |        0.9 |   3874 |        6 |          1.29264  |                     1.1828   |                 6 |

#### Interpretation Notes
- Robustness summary uses bootstrap lower bounds from the configured smoke/full run artifacts.
- Interpretation: LB95 > 0 indicates conservative positive expectancy under sampled uncertainty.
- Overfit panel adds month-stratified null uplift and dependence-aware LB95 comparisons.

#### Action Trigger Summary
| symbol   | metric_id                     | band   | severity   | action_code    | action_summary         | owner   |
|:---------|:------------------------------|:-------|:-----------|:---------------|:-----------------------|:--------|
| AUDUSD   | T01_stress_elasticity         | green  | info       | A0_MONITOR     | within policy band     | risk    |
| AUDUSD   | T02_first_negative_costplus   | amber  | medium     | A1_REVIEW      | review and monitor     | risk    |
| AUDUSD   | T03_post_worst_month_recovery | red    | high       | A2_RECALIBRATE | escalate and remediate | risk    |
| EURUSD   | T01_stress_elasticity         | green  | info       | A0_MONITOR     | within policy band     | risk    |
| EURUSD   | T02_first_negative_costplus   | green  | info       | A0_MONITOR     | within policy band     | risk    |
| EURUSD   | T03_post_worst_month_recovery | red    | high       | A2_RECALIBRATE | escalate and remediate | risk    |
| GBPUSD   | T01_stress_elasticity         | green  | info       | A0_MONITOR     | within policy band     | risk    |
| GBPUSD   | T02_first_negative_costplus   | green  | info       | A0_MONITOR     | within policy band     | risk    |
| GBPUSD   | T03_post_worst_month_recovery | green  | info       | A0_MONITOR     | within policy band     | risk    |
| USDCAD   | T01_stress_elasticity         | green  | info       | A0_MONITOR     | within policy band     | risk    |
| USDCAD   | T02_first_negative_costplus   | green  | info       | A0_MONITOR     | within policy band     | risk    |
| USDCAD   | T03_post_worst_month_recovery | red    | high       | A2_RECALIBRATE | escalate and remediate | risk    |

#### Details
| symbol   |   pvalue_month_mean_gt0 |   pvalue_bonferroni |   pvalue_fdr_bh |   t01_stress_elasticity |   t02_first_negative_costplus |   t04_max_survivable_cost_lb95_trade |   t03_post_worst_month_recovery |   lb95_trade_mean_net_pips_costplus_0.10 |   lb95_trade_mean_net_pips_costplus_0.20 |   lb95_trade_mean_net_pips_costplus_0.30 |   lb95_trade_mean_net_pips_costplus_0.50 |
|:---------|------------------------:|--------------------:|----------------:|------------------------:|------------------------------:|-------------------------------------:|--------------------------------:|-----------------------------------------:|-----------------------------------------:|-----------------------------------------:|-----------------------------------------:|
| EURUSD   |              0          |         0           |     0           |                      -1 |                          2    |                             2        |                         1.28178 |                                 2.32234  |                                 2.22328  |                                 2.11978  |                                 1.92278  |
| GBPUSD   |              0          |         0           |     0           |                      -1 |                          2    |                             2        |                         1.33224 |                                 2.46851  |                                 2.3712   |                                 2.26905  |                                 2.07023  |
| AUDUSD   |              0          |         0           |     0           |                      -1 |                          1    |                             0.881824 |                       nan       |                                 0.781428 |                                 0.680127 |                                 0.582336 |                                 0.381061 |
| USDJPY   |              0          |         0           |     0           |                      -1 |                          2    |                             2        |                         1.04299 |                                 3.32182  |                                 3.22655  |                                 3.12819  |                                 2.92276  |
| USDCHF   |              0          |         0           |     0           |                      -1 |                          1.75 |                             1.43499  |                         1.03157 |                                 1.33558  |                                 1.22767  |                                 1.13335  |                                 0.932108 |
| USDCAD   |              7.9714e-14 |         4.78284e-13 |     2.39142e-13 |                      -1 |                          1.5  |                             1.18686  |                       nan       |                                 1.08558  |                                 0.981581 |                                 0.888121 |                                 0.684399 |

#### Plots
![stage_08_robustness_lb95](../figures/oco_bible/stage_08_robustness_lb95.png)
![stage_08_overfit_symbol_panel](../figures/oco_bible/stage_08_overfit_symbol_panel.png)
<!-- GENERATED:STAGE_08:END -->
