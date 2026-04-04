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

- generated_at: `2026-04-03 12:49:19 UTC`
- Robustness summary uses bootstrap lower bounds from the configured smoke/full run artifacts.
- Interpretation: LB95 > 0 indicates conservative positive expectancy under sampled uncertainty.
- Overfit panel adds month-stratified null uplift and dependence-aware LB95 comparisons.
- T01-T04 summarize stress elasticity, negative-cost crossing, max survivable cost, and post-worst-month recovery efficiency.

#### Key Results
| symbol   |   quantile |   rows |   months |   mean_gross_pips |   lb95_trade_mean_gross_pips |   positive_months |
|:---------|-----------:|-------:|---------:|------------------:|-----------------------------:|------------------:|
| EURUSD   |        0.9 |   6771 |       11 |           2.41681 |                      2.31991 |                11 |
| GBPUSD   |        0.9 |  13737 |       11 |           2.70327 |                      2.63023 |                11 |
| AUDUSD   |        0.9 |   8867 |       11 |           1.64042 |                      1.56594 |                11 |
| USDJPY   |        0.9 |  17066 |       11 |           3.65559 |                      3.58099 |                11 |
| USDCHF   |        0.9 |   8287 |       11 |           2.31187 |                      2.21857 |                11 |
| USDCAD   |        0.9 |   6905 |       11 |           1.75629 |                      1.66355 |                11 |

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
| GBPUSD   | T03_post_worst_month_recovery | amber  | medium     | A1_REVIEW     | review and monitor | risk    |
| USDCAD   | T01_stress_elasticity         | green  | info       | A0_MONITOR    | within policy band | risk    |
| USDCAD   | T02_first_negative_costplus   | green  | info       | A0_MONITOR    | within policy band | risk    |
| USDCAD   | T03_post_worst_month_recovery | green  | info       | A0_MONITOR    | within policy band | risk    |

#### Details
| symbol   |   pvalue_month_mean_gt0 |   pvalue_bonferroni |   pvalue_fdr_bh |   t01_stress_elasticity |   t02_first_negative_costplus |   t04_max_survivable_cost_lb95_trade |   t03_post_worst_month_recovery |   lb95_trade_mean_net_pips_costplus_0.10 |   lb95_trade_mean_net_pips_costplus_0.20 |   lb95_trade_mean_net_pips_costplus_0.30 |   lb95_trade_mean_net_pips_costplus_0.50 |
|:---------|------------------------:|--------------------:|----------------:|------------------------:|------------------------------:|-------------------------------------:|--------------------------------:|-----------------------------------------:|-----------------------------------------:|-----------------------------------------:|-----------------------------------------:|
| EURUSD   |             1.11022e-16 |         6.66134e-16 |     1.66533e-16 |                      -1 |                          2    |                              2       |                         1.16067 |                                  2.21662 |                                  2.11159 |                                  2.01666 |                                  1.81668 |
| GBPUSD   |             0           |         0           |     0           |                      -1 |                          2    |                              2       |                         1.26364 |                                  2.53224 |                                  2.43298 |                                  2.32649 |                                  2.13224 |
| AUDUSD   |             4.41092e-12 |         2.64655e-11 |     5.2931e-12  |                      -1 |                          1.75 |                              1.56404 |                         3.21804 |                                  1.46337 |                                  1.3619  |                                  1.263   |                                  1.06448 |
| USDJPY   |             0           |         0           |     0           |                      -1 |                          2    |                              2       |                         1.30391 |                                  3.48385 |                                  3.37869 |                                  3.28286 |                                  3.08388 |
| USDCHF   |             1.97176e-12 |         1.18305e-11 |     3.94351e-12 |                      -1 |                          2    |                              2       |                         1.85057 |                                  2.12269 |                                  2.02059 |                                  1.92036 |                                  1.71939 |
| USDCAD   |             0           |         0           |     0           |                      -1 |                          2    |                              1.6664  |                         1.72207 |                                  1.57259 |                                  1.46583 |                                  1.36772 |                                  1.16719 |

#### Plots
![stage_08_robustness_lb95](../figures/oco_bible/stage_08_robustness_lb95.png)
![stage_08_overfit_symbol_panel](../figures/oco_bible/stage_08_overfit_symbol_panel.png)
<!-- GENERATED:STAGE_08:END -->
