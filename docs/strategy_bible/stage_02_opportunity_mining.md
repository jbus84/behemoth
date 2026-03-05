# Stage 2 - Opportunity Mining

## Objective
Mine high-count, gross-positive OCO opportunity families as hypotheses before model filtering and robustness controls.

## Inputs
- Candidate catalogs:
- `data/analysis/tick_opportunity_mining/<SYMBOL>_oco_candidates.csv`
- Key candidate fields:
- `selection_pass`, `annualized_test_fills`, `mean_gross_pips_test`, `family`, `state_id`, `bar_ticks`, `horizon`

## Process
- Enumerate OCO state families and horizons.
- Keep broad candidate frontier (`selection_pass`) for downstream filtering.
- Compute concentration/smoothness diagnostics (`M01-M03`).
- Constrain mining outputs to a pre-registered rule universe contract used by downstream reduced-core and live governance.

## Exact Calculations
- `edge_weight = annualized_test_fills * mean_gross_pips_test`
- `M01_top3_contrib_share = sum(top3 edge_weight by state block) / sum(all edge_weight)`
- `M02_smoothness_abs_jump = median(abs(diff(mean_gross_pips_test across adjacent horizon)))`
- `M03_positive_density = mean(mean_gross_pips_test > 0 among selection_pass)`

## Pre-Registered Rule-Universe Contract
- Registry artifact: `configs/research/governance/oco_rule_universe_registry.yaml`
- Required frozen fields:
- `symbols`
- `allowed_families`
- `allowed_barrier_keep`
- `allowed_horizon_keep`
- `selection_mode_contract`
- `locked_runtime_contract`
- Integrity rule:
- Canonical payload hash (SHA-256 over sorted JSON with `hash_sha256` removed) must match `hash_sha256` in registry.
- Contract validation artifacts:
- `data/analysis/tick_opportunity_mining/oco_rule_universe_registry_checks.csv`
- `data/analysis/tick_opportunity_mining/oco_rule_universe_registry_issues.csv`
- `docs/analysis/oco_rule_universe_registry_report.md`
- Purpose:
- Prevent silent expansion of families/barriers/horizons after seeing results, which is a primary overfitting pathway in mining workflows.

## Causality / Leakage Controls
- Mining outputs are hypothesis-generation only.
- No deployment gating at this stage without downstream WFO/robustness confirmation.
- Rule universe is locked before reduced-core/live selection and checked against frozen governance locks (`RU06-RU09`).

## Failure Modes
- Edge concentration in very few states (fragile alpha).
- Non-smooth parameter surfaces indicating noisy search.
- Post-hoc over-interpretation without Stage 3/8 controls.

## Interpretation Guide
- Lower `M01` is better diversification.
- Lower `M02` indicates smoother, less brittle parameter landscape.
- Higher `M03` indicates a denser positive frontier.

## Validation Gates
- Informational at Stage 2.
- Hard pass/fail occurs later via Stage 3, Stage 7, Stage 8.
- Governance contract gate: registry checks must have zero high/critical failures (`C33` at docs-contract level).

## Canonical Analysis Reports
- `docs/analysis/eurusd_tick_opportunity_mining_report.md`
- `docs/analysis/gbpusd_tick_opportunity_mining_report.md`
- `docs/analysis/usdjpy_tick_opportunity_mining_report.md`
- `docs/analysis/oco_rule_universe_registry_report.md`
- `docs/strategy_bible/signal_lifecycle_reference.md`

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
uv run python scripts/run_tick_opportunity_mining.py \
  --config configs/research/experiments/eurusd_tick_opportunity_mining.yaml
uv run python scripts/validate_oco_rule_universe_registry.py
```

## Traceability
- `scripts/run_tick_opportunity_mining.py`
- `scripts/validate_oco_rule_universe_registry.py`
- `docs/analysis/*_tick_opportunity_mining_report.md`
- `docs/analysis/oco_rule_universe_registry_report.md`
- `docs/strategy_bible/generated/stage_02_snapshot.md`

## Generated Run Snapshot
<!-- GENERATED:STAGE_02:START -->
### Auto Snapshot - Stage 02

- generated_at: `2026-03-05 07:55:58 UTC`
- selection_pass candidates are broad hypotheses only.
- Scatter shows the high-count >0 gross opportunity frontier.
- M01-M03 quantify concentration risk, horizon smoothness, and positive-edge density.

#### Key Results
| symbol   |   candidates_total |   selected_total |   selected_mean_gross_pips |   selected_median_annualized |   m01_top3_contrib_share |   m02_smoothness_abs_jump |   m03_positive_density |
|:---------|-------------------:|-----------------:|---------------------------:|-----------------------------:|-------------------------:|--------------------------:|-----------------------:|
| EURUSD   |               2160 |             1828 |                   2.72708  |                      4510.31 |                0.0326511 |                 0.254985  |               0.884026 |
| GBPUSD   |               2160 |             1685 |                   3.32768  |                      4814.26 |                0.0337978 |                 0.288919  |               0.910386 |
| AUDUSD   |               2160 |             1672 |                   2.1009   |                      2459.85 |                0.032903  |                 0.20972   |               0.910885 |
| USDJPY   |               2160 |             1742 |                   4.35846  |                      8170.66 |                0.0307445 |                 0.339244  |               0.889208 |
| USDCHF   |               2160 |             1489 |                   2.58074  |                      2808.79 |                0.0354318 |                 0.24956   |               0.8818   |
| USDCAD   |                720 |              669 |                   0.404258 |                      9234.52 |                0.0896167 |                 0.0592627 |               0.898356 |

#### Interpretation Notes
- selection_pass candidates are broad hypotheses only.
- Scatter shows the high-count >0 gross opportunity frontier.
- M01-M03 quantify concentration risk, horizon smoothness, and positive-edge density.

#### Action Trigger Summary
| trigger            | threshold_or_signal   | action_code                   | action_summary                                                          |
|:-------------------|:----------------------|:------------------------------|:------------------------------------------------------------------------|
| hard_gate_fail     | status=fail           | A3_HALT_RECALIBRATE           | Block promotion and rerun upstream stage diagnostics before continuing. |
| monitoring_warning | band=amber            | A0_MONITOR/A1_RECALIBRATE_CAP | Apply stage runbook remediation and confirm next-run recovery.          |

#### Plots
![stage_02_selected_scatter](../figures/oco_bible/stage_02_selected_scatter.png)

#### Edge Contribution by State Block
| symbol   | family                | state_id                                    |   bar_ticks |   horizon |   edge_weight |   contrib_share |
|:---------|:----------------------|:--------------------------------------------|------------:|----------:|--------------:|----------------:|
| AUDUSD   | oco_first_touch_clean | oco_first_touch_clean__all__k2              |         100 |         6 |      122379   |      0.0127718  |
| AUDUSD   | oco_first_touch_clean | oco_first_touch_clean__low_cost_q50__k2     |         100 |         6 |       97464.1 |      0.0101715  |
| AUDUSD   | oco_first_touch_clean | oco_first_touch_clean__all__k2              |         100 |         5 |       95434.4 |      0.00995972 |
| AUDUSD   | oco_first_touch_clean | oco_first_touch_clean__low_cost_q50__k2     |         100 |         5 |       74287.3 |      0.00775278 |
| AUDUSD   | oco_first_touch_clean | oco_first_touch_clean__low_cost_q30__k2     |         100 |         6 |       74125.1 |      0.00773585 |
| AUDUSD   | oco_first_touch_clean | oco_first_touch_clean__all__k2              |         100 |         4 |       67908   |      0.00708701 |
| AUDUSD   | oco_first_touch_clean | oco_first_touch_clean__low_cost_q30__k2     |         100 |         5 |       55668.8 |      0.00580971 |
| AUDUSD   | oco_first_touch_clean | oco_first_touch_clean__all__k3              |        1000 |         6 |       55122.6 |      0.00575271 |
| EURUSD   | oco_first_touch_clean | oco_first_touch_clean__all__k2              |         100 |         6 |      273060   |      0.0132451  |
| EURUSD   | oco_first_touch_clean | oco_first_touch_clean__all__k2              |         100 |         5 |      225779   |      0.0109517  |
| EURUSD   | oco_first_touch_clean | oco_first_touch_clean__all__k2              |         100 |         4 |      174293   |      0.00845431 |
| EURUSD   | oco_first_touch_clean | oco_first_touch_clean__low_cost_q30__k2     |         100 |         6 |      155374   |      0.00753662 |
| EURUSD   | oco_first_touch_clean | oco_first_touch_clean__high_range_q70__k2   |         100 |         6 |      145548   |      0.00705999 |
| EURUSD   | oco_first_touch_clean | oco_first_touch_clean__all__k3              |         100 |         6 |      143860   |      0.00697809 |
| EURUSD   | oco_first_touch_clean | oco_first_touch_clean__high_range_q70__k2   |         100 |         5 |      124395   |      0.00603396 |
| EURUSD   | oco_first_touch_clean | oco_first_touch_clean__low_cost_q30__k2     |         100 |         5 |      121071   |      0.00587269 |
| GBPUSD   | oco_first_touch_clean | oco_first_touch_clean__all__k2              |         100 |         6 |      316345   |      0.0125907  |
| GBPUSD   | oco_first_touch_clean | oco_first_touch_clean__all__k2              |         100 |         5 |      266813   |      0.0106193  |
| GBPUSD   | oco_first_touch_clean | oco_first_touch_clean__low_cost_q50__k2     |         100 |         6 |      266020   |      0.0105877  |
| GBPUSD   | oco_first_touch_clean | oco_first_touch_clean__low_cost_q50__k2     |         100 |         5 |      224246   |      0.00892514 |
| GBPUSD   | oco_first_touch_clean | oco_first_touch_clean__all__k2              |         100 |         4 |      209899   |      0.0083541  |
| GBPUSD   | oco_first_touch_clean | oco_first_touch_clean__low_cost_q30__k2     |         100 |         6 |      191214   |      0.00761041 |
| GBPUSD   | oco_first_touch_clean | oco_first_touch_clean__all__k3              |         100 |         6 |      180164   |      0.00717062 |
| GBPUSD   | oco_first_touch_clean | oco_first_touch_clean__low_cost_q50__k2     |         100 |         4 |      175963   |      0.00700343 |
| USDCAD   | oco_first_touch_clean | oco_first_touch_clean__all__k2              |         100 |         6 |      214555   |      0.0364454  |
| USDCAD   | oco_first_touch_clean | oco_first_touch_clean__all__k2              |         100 |         5 |      176951   |      0.0300578  |
| USDCAD   | oco_first_touch_clean | oco_first_touch_clean__all__k2              |         100 |         4 |      136070   |      0.0231136  |
| USDCAD   | oco_first_touch_clean | oco_first_touch_clean__all__k3              |         100 |         6 |      108809   |      0.0184828  |
| USDCAD   | oco_first_touch_clean | oco_first_touch_clean__london__k2           |         100 |         6 |       96180.9 |      0.0163377  |
| USDCAD   | oco_first_touch_clean | oco_first_touch_clean__all__k2              |         100 |         3 |       93635.8 |      0.0159054  |
| USDCAD   | oco_first_touch_clean | oco_first_touch_clean__all__k3              |         100 |         5 |       83451.2 |      0.0141754  |
| USDCAD   | oco_first_touch_clean | oco_first_touch_clean__high_range_q70__k2   |         100 |         6 |       80799.5 |      0.013725   |
| USDCHF   | oco_first_touch_clean | oco_first_touch_clean__all__k2              |         100 |         6 |      159348   |      0.0145451  |
| USDCHF   | oco_first_touch_clean | oco_first_touch_clean__all__k2              |         100 |         5 |      128335   |      0.0117142  |
| USDCHF   | oco_first_touch_clean | oco_first_touch_clean__low_cost_q50__k2     |         100 |         6 |      100489   |      0.00917252 |
| USDCHF   | oco_first_touch_clean | oco_first_touch_clean__all__k2              |         100 |         4 |       96283.3 |      0.00878859 |
| USDCHF   | oco_first_touch_clean | oco_first_touch_clean__low_cost_q50__k2     |         100 |         5 |       78759.7 |      0.00718906 |
| USDCHF   | oco_first_touch_clean | oco_first_touch_clean__all__k3              |         100 |         6 |       73784.2 |      0.0067349  |
| USDCHF   | oco_first_touch_clean | oco_first_touch_clean__low_cost_q30__k2     |         100 |         6 |       73666.3 |      0.00672415 |
| USDCHF   | oco_first_touch_clean | oco_first_touch_clean__high_abs_vel_q70__k2 |         100 |         6 |       65565.3 |      0.0059847  |
| USDJPY   | oco_first_touch_clean | oco_first_touch_clean__all__k2              |         100 |         6 |      605018   |      0.0117861  |
| USDJPY   | oco_first_touch_clean | oco_first_touch_clean__all__k2              |         100 |         5 |      531927   |      0.0103623  |
| USDJPY   | oco_first_touch_clean | oco_first_touch_clean__all__k2              |         100 |         4 |      441263   |      0.00859607 |
| USDJPY   | oco_first_touch_clean | oco_first_touch_clean__all__k3              |         100 |         6 |      426780   |      0.00831393 |
| USDJPY   | oco_first_touch_clean | oco_first_touch_clean__low_cost_q50__k2     |         100 |         6 |      385493   |      0.00750965 |
| USDJPY   | oco_first_touch_clean | oco_first_touch_clean__all__k3              |         100 |         5 |      338588   |      0.0065959  |
| USDJPY   | oco_first_touch_clean | oco_first_touch_clean__low_cost_q50__k2     |         100 |         5 |      336760   |      0.00656029 |
| USDJPY   | oco_first_touch_clean | oco_first_touch_clean__all__k2              |         100 |         3 |      330929   |      0.00644671 |

#### Overfitting Diagnostics (Downstream, Exec Quantile)
| symbol   |   quantile |   rows |   months |   positive_months |   lb95_trade_mean_gross_pips |   lb95_trade_mean_gross_pips_iid |   lb95_trade_mean_gross_pips_month_block |   pvalue_month_mean_gt0 |   pvalue_bonferroni |   pvalue_fdr_bh |   uplift_vs_null_pips |   pvalue_perm_uplift |   pvalue_perm_fdr_bh | majority_positive_months   | bonferroni_pass_10pct   | fdr_pass_10pct   | perm_fdr_pass_10pct   |
|:---------|-----------:|-------:|---------:|------------------:|-----------------------------:|---------------------------------:|-----------------------------------------:|------------------------:|--------------------:|----------------:|----------------------:|---------------------:|---------------------:|:---------------------------|:------------------------|:-----------------|:----------------------|
| AUDUSD   |        0.9 |   4227 |        6 |                 6 |                     0.952247 |                         0.952247 |                                 0.839258 |                       0 |                   0 |               0 |                   nan |                  nan |                  nan | True                       | True                    | True             | False                 |
| EURUSD   |        0.9 |   6715 |       11 |                11 |                     2.5027   |                         2.5027   |                                 1.80464  |                       0 |                   0 |               0 |                   nan |                  nan |                  nan | True                       | True                    | True             | False                 |
| GBPUSD   |        0.9 |   6978 |        6 |                 6 |                     2.57413  |                         2.57413  |                                 2.44927  |                       0 |                   0 |               0 |                   nan |                  nan |                  nan | True                       | True                    | True             | False                 |
| USDCAD   |        0.9 |   3574 |        6 |                 6 |                     1.41111  |                         1.41111  |                                 1.2101   |                       0 |                   0 |               0 |                   nan |                  nan |                  nan | True                       | True                    | True             | False                 |
| USDCHF   |        0.9 |   4170 |        6 |                 6 |                     1.37476  |                         1.37476  |                                 1.21468  |                       0 |                   0 |               0 |                   nan |                  nan |                  nan | True                       | True                    | True             | False                 |
| USDJPY   |        0.9 |   8186 |        6 |                 6 |                     3.41566  |                         3.41566  |                                 3.15864  |                       0 |                   0 |               0 |                   nan |                  nan |                  nan | True                       | True                    | True             | False                 |

- Interpretation: Stage 2 mining is accepted only as hypothesis generation; false-discovery control is enforced downstream via Stage 3/8 out-of-sample evaluation.
- Multiplicity fields (`pvalue_bonferroni`, `pvalue_fdr_bh`) are reported at the execution quantile and should be used with LB95/month-consistency, not in isolation.
<!-- GENERATED:STAGE_02:END -->
