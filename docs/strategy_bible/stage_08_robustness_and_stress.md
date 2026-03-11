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
  --symbols EURUSD,GBPUSD,USDJPY,USDCHF,AUDUSD,USDCAD
```

## Traceability
- `scripts/analyze_oco_monthly_wfo_robustness.py`
- `docs/analysis/*_oco_monthly_wfo_robustness_*_report.md`
- `docs/strategy_bible/generated/stage_08_snapshot.md`

## Generated Run Snapshot
<!-- GENERATED:STAGE_08:START -->
### Auto Snapshot - Stage 08

- generated_at: `2026-03-11 21:50:05 UTC`
- Robustness summary uses bootstrap lower bounds from the configured smoke/full run artifacts.
- Interpretation: LB95 > 0 indicates conservative positive expectancy under sampled uncertainty.
- Overfit panel adds month-stratified null uplift and dependence-aware LB95 comparisons.
- T01-T04 summarize stress elasticity, negative-cost crossing, max survivable cost, and post-worst-month recovery efficiency.

#### Key Results
| symbol   |   quantile |   rows |   months |   mean_gross_pips |   lb95_trade_mean_gross_pips |   positive_months |
|:---------|-----------:|-------:|---------:|------------------:|-----------------------------:|------------------:|
| EURUSD   |        0.9 |   5934 |       10 |           2.83795 |                      2.72549 |                10 |
| GBPUSD   |        0.9 |  12161 |       11 |           2.77239 |                      2.69625 |                11 |
| AUDUSD   |        0.9 |   7789 |       11 |           1.6767  |                      1.59632 |                11 |
| USDJPY   |        0.9 |  13266 |       11 |           3.88653 |                      3.79579 |                11 |
| USDCHF   |        0.9 |  10408 |       11 |           2.15095 |                      2.07321 |                11 |
| USDCAD   |        0.9 |   7809 |       11 |           2.30917 |                      2.21911 |                11 |

#### Interpretation Notes
- Robustness summary uses bootstrap lower bounds from the configured smoke/full run artifacts.
- Interpretation: LB95 > 0 indicates conservative positive expectancy under sampled uncertainty.
- Overfit panel adds month-stratified null uplift and dependence-aware LB95 comparisons.

#### Action Trigger Summary
| symbol   | metric_id                     | band   | severity   | action_code   | action_summary     | owner   |
|:---------|:------------------------------|:-------|:-----------|:--------------|:-------------------|:--------|
| AUDUSD   | T01_stress_elasticity         | green  | info       | A0_MONITOR    | within policy band | risk    |
| AUDUSD   | T02_first_negative_costplus   | green  | info       | A0_MONITOR    | within policy band | risk    |
| AUDUSD   | T03_post_worst_month_recovery | green  | info       | A0_MONITOR    | within policy band | risk    |
| EURUSD   | T01_stress_elasticity         | green  | info       | A0_MONITOR    | within policy band | risk    |
| EURUSD   | T02_first_negative_costplus   | green  | info       | A0_MONITOR    | within policy band | risk    |
| EURUSD   | T03_post_worst_month_recovery | green  | info       | A0_MONITOR    | within policy band | risk    |
| GBPUSD   | T01_stress_elasticity         | green  | info       | A0_MONITOR    | within policy band | risk    |
| GBPUSD   | T02_first_negative_costplus   | green  | info       | A0_MONITOR    | within policy band | risk    |
| GBPUSD   | T03_post_worst_month_recovery | green  | info       | A0_MONITOR    | within policy band | risk    |
| USDCAD   | T01_stress_elasticity         | green  | info       | A0_MONITOR    | within policy band | risk    |
| USDCAD   | T02_first_negative_costplus   | green  | info       | A0_MONITOR    | within policy band | risk    |
| USDCAD   | T03_post_worst_month_recovery | green  | info       | A0_MONITOR    | within policy band | risk    |

#### Details
| symbol   |   pvalue_month_mean_gt0 |   pvalue_bonferroni |   pvalue_fdr_bh |   t01_stress_elasticity |   t02_first_negative_costplus |   t04_max_survivable_cost_lb95_trade |   t03_post_worst_month_recovery |   lb95_trade_mean_net_pips_costplus_0.10 |   lb95_trade_mean_net_pips_costplus_0.20 |   lb95_trade_mean_net_pips_costplus_0.30 |   lb95_trade_mean_net_pips_costplus_0.50 |
|:---------|------------------------:|--------------------:|----------------:|------------------------:|------------------------------:|-------------------------------------:|--------------------------------:|-----------------------------------------:|-----------------------------------------:|-----------------------------------------:|-----------------------------------------:|
| EURUSD   |             1.88738e-15 |         1.13243e-14 |     5.66214e-15 |                      -1 |                          2    |                              2       |                         1.29602 |                                  2.62152 |                                  2.5239  |                                  2.42593 |                                  2.22439 |
| GBPUSD   |             0           |         0           |     0           |                      -1 |                          2    |                              2       |                         1.10572 |                                  2.59791 |                                  2.50045 |                                  2.39667 |                                  2.20334 |
| AUDUSD   |             0           |         0           |     0           |                      -1 |                          1.75 |                              1.59776 |                         2.43772 |                                  1.49704 |                                  1.39533 |                                  1.29631 |                                  1.09853 |
| USDJPY   |             0           |         0           |     0           |                      -1 |                          2    |                              2       |                         1.13612 |                                  3.69815 |                                  3.59624 |                                  3.49552 |                                  3.29708 |
| USDCHF   |             4.32987e-14 |         2.59792e-13 |     2.59792e-13 |                      -1 |                          2    |                              2       |                         2.21997 |                                  1.97892 |                                  1.87454 |                                  1.77512 |                                  1.57802 |
| USDCAD   |             8.88178e-16 |         5.32907e-15 |     5.32907e-15 |                      -1 |                          2    |                              2       |                         2.9865  |                                  2.11745 |                                  2.01949 |                                  1.91395 |                                  1.71427 |

#### Plots
![stage_08_robustness_lb95](../figures/oco_bible/stage_08_robustness_lb95.png)
![stage_08_overfit_symbol_panel](../figures/oco_bible/stage_08_overfit_symbol_panel.png)
<!-- GENERATED:STAGE_08:END -->
