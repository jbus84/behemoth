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

- generated_at: `2026-04-03 12:49:19 UTC`
- selection_pass candidates are broad hypotheses only.
- Scatter shows the high-count >0 gross opportunity frontier.
- M01-M03 quantify concentration risk, horizon smoothness, and positive-edge density.

#### Key Results
| symbol   |   candidates_total |   selected_total |   selected_mean_gross_pips |   selected_median_annualized |   m01_top3_contrib_share |   m02_smoothness_abs_jump |   m03_positive_density |
|:---------|-------------------:|-----------------:|---------------------------:|-----------------------------:|-------------------------:|--------------------------:|-----------------------:|
| EURUSD   |               2160 |             1790 |                    2.6611  |                      4366.13 |                0.0329489 |                  0.242923 |               0.865922 |
| GBPUSD   |               2160 |             1685 |                    3.30005 |                      4664.23 |                0.0340572 |                  0.27724  |               0.91632  |
| AUDUSD   |               2160 |             1689 |                    2.08392 |                      2379.58 |                0.032857  |                  0.195525 |               0.912374 |
| USDJPY   |               2160 |             1742 |                    4.32458 |                      7682.67 |                0.0310775 |                  0.31229  |               0.88806  |
| USDCHF   |               2160 |             1481 |                    2.56006 |                      2660.46 |                0.0361571 |                  0.220386 |               0.885888 |
| USDCAD   |               2160 |             1509 |                    2.63432 |                      2771.41 |                0.0413922 |                  0.237025 |               0.901922 |

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
| AUDUSD   | oco_first_touch_clean | oco_first_touch_clean__all__k2              |         100 |         6 |      122356   |      0.0127413  |
| AUDUSD   | oco_first_touch_clean | oco_first_touch_clean__low_cost_q50__k2     |         100 |         6 |       97752.1 |      0.0101792  |
| AUDUSD   | oco_first_touch_clean | oco_first_touch_clean__all__k2              |         100 |         5 |       95421.5 |      0.00993651 |
| AUDUSD   | oco_first_touch_clean | oco_first_touch_clean__low_cost_q30__k2     |         100 |         6 |       76081.6 |      0.00792259 |
| AUDUSD   | oco_first_touch_clean | oco_first_touch_clean__low_cost_q50__k2     |         100 |         5 |       74510.5 |      0.00775899 |
| AUDUSD   | oco_first_touch_clean | oco_first_touch_clean__all__k2              |         100 |         4 |       67922.6 |      0.00707297 |
| AUDUSD   | oco_first_touch_clean | oco_first_touch_clean__low_cost_q30__k2     |         100 |         5 |       57137.8 |      0.00594992 |
| AUDUSD   | oco_first_touch_clean | oco_first_touch_clean__all__k3              |        1000 |         6 |       55122.6 |      0.00574008 |
| EURUSD   | oco_first_touch_clean | oco_first_touch_clean__all__k2              |         100 |         6 |      272613   |      0.0133585  |
| EURUSD   | oco_first_touch_clean | oco_first_touch_clean__all__k2              |         100 |         5 |      225718   |      0.0110606  |
| EURUSD   | oco_first_touch_clean | oco_first_touch_clean__all__k2              |         100 |         4 |      174071   |      0.00852979 |
| EURUSD   | oco_first_touch_clean | oco_first_touch_clean__low_cost_q30__k2     |         100 |         6 |      161967   |      0.00793669 |
| EURUSD   | oco_first_touch_clean | oco_first_touch_clean__high_range_q70__k2   |         100 |         6 |      155049   |      0.00759769 |
| EURUSD   | oco_first_touch_clean | oco_first_touch_clean__all__k3              |         100 |         6 |      144259   |      0.00706895 |
| EURUSD   | oco_first_touch_clean | oco_first_touch_clean__high_range_q70__k2   |         100 |         5 |      132254   |      0.00648066 |
| EURUSD   | oco_first_touch_clean | oco_first_touch_clean__low_cost_q30__k2     |         100 |         5 |      126831   |      0.00621494 |
| GBPUSD   | oco_first_touch_clean | oco_first_touch_clean__all__k2              |         100 |         6 |      315133   |      0.0126775  |
| GBPUSD   | oco_first_touch_clean | oco_first_touch_clean__all__k2              |         100 |         5 |      266499   |      0.010721   |
| GBPUSD   | oco_first_touch_clean | oco_first_touch_clean__low_cost_q50__k2     |         100 |         6 |      264953   |      0.0106588  |
| GBPUSD   | oco_first_touch_clean | oco_first_touch_clean__low_cost_q50__k2     |         100 |         5 |      224032   |      0.00901258 |
| GBPUSD   | oco_first_touch_clean | oco_first_touch_clean__all__k2              |         100 |         4 |      210536   |      0.00846963 |
| GBPUSD   | oco_first_touch_clean | oco_first_touch_clean__low_cost_q30__k2     |         100 |         6 |      194478   |      0.00782362 |
| GBPUSD   | oco_first_touch_clean | oco_first_touch_clean__all__k3              |         100 |         6 |      180718   |      0.00727009 |
| GBPUSD   | oco_first_touch_clean | oco_first_touch_clean__low_cost_q50__k2     |         100 |         4 |      176415   |      0.007097   |
| USDCAD   | oco_first_touch_clean | oco_first_touch_clean__all__k2              |         100 |         6 |      214977   |      0.0167786  |
| USDCAD   | oco_first_touch_clean | oco_first_touch_clean__all__k2              |         100 |         5 |      178325   |      0.013918   |
| USDCAD   | oco_first_touch_clean | oco_first_touch_clean__all__k2              |         100 |         4 |      137039   |      0.0106956  |
| USDCAD   | oco_first_touch_clean | oco_first_touch_clean__all__k3              |         100 |         6 |      110391   |      0.00861585 |
| USDCAD   | oco_first_touch_clean | oco_first_touch_clean__all__k2              |         100 |         3 |       94819.4 |      0.00740049 |
| USDCAD   | oco_first_touch_clean | oco_first_touch_clean__all__k3              |         100 |         5 |       85318.9 |      0.006659   |
| USDCAD   | oco_first_touch_clean | oco_first_touch_clean__ny_overlap__k2       |         100 |         6 |       82404.5 |      0.00643153 |
| USDCAD   | oco_first_touch_clean | oco_first_touch_clean__high_range_q70__k2   |         100 |         6 |       80517.5 |      0.00628425 |
| USDCHF   | oco_first_touch_clean | oco_first_touch_clean__all__k2              |         100 |         6 |      159476   |      0.0148063  |
| USDCHF   | oco_first_touch_clean | oco_first_touch_clean__all__k2              |         100 |         5 |      128262   |      0.0119082  |
| USDCHF   | oco_first_touch_clean | oco_first_touch_clean__low_cost_q50__k2     |         100 |         6 |      101705   |      0.00944262 |
| USDCHF   | oco_first_touch_clean | oco_first_touch_clean__all__k2              |         100 |         4 |       95817   |      0.00889594 |
| USDCHF   | oco_first_touch_clean | oco_first_touch_clean__low_cost_q50__k2     |         100 |         5 |       79128.4 |      0.00734652 |
| USDCHF   | oco_first_touch_clean | oco_first_touch_clean__low_cost_q30__k2     |         100 |         6 |       75140.3 |      0.00697625 |
| USDCHF   | oco_first_touch_clean | oco_first_touch_clean__all__k3              |         100 |         6 |       73379.4 |      0.00681277 |
| USDCHF   | oco_first_touch_clean | oco_first_touch_clean__high_abs_vel_q70__k2 |         100 |         6 |       66185.7 |      0.00614488 |
| USDJPY   | oco_first_touch_clean | oco_first_touch_clean__all__k2              |         100 |         6 |      603378   |      0.0119181  |
| USDJPY   | oco_first_touch_clean | oco_first_touch_clean__all__k2              |         100 |         5 |      530354   |      0.0104757  |
| USDJPY   | oco_first_touch_clean | oco_first_touch_clean__all__k2              |         100 |         4 |      439630   |      0.0086837  |
| USDJPY   | oco_first_touch_clean | oco_first_touch_clean__all__k3              |         100 |         6 |      425708   |      0.00840869 |
| USDJPY   | oco_first_touch_clean | oco_first_touch_clean__low_cost_q50__k2     |         100 |         6 |      380115   |      0.00750813 |
| USDJPY   | oco_first_touch_clean | oco_first_touch_clean__all__k3              |         100 |         5 |      338206   |      0.00668033 |
| USDJPY   | oco_first_touch_clean | oco_first_touch_clean__low_cost_q50__k2     |         100 |         5 |      332407   |      0.0065658  |
| USDJPY   | oco_first_touch_clean | oco_first_touch_clean__all__k2              |         100 |         3 |      330877   |      0.00653556 |

#### Overfitting Diagnostics (Downstream, Exec Quantile)
| symbol   |   quantile |   rows |   months |   positive_months |   lb95_trade_mean_gross_pips |   lb95_trade_mean_gross_pips_iid |   lb95_trade_mean_gross_pips_month_block |   pvalue_month_mean_gt0 |   pvalue_bonferroni |   pvalue_fdr_bh |   uplift_vs_null_pips |   pvalue_perm_uplift |   pvalue_perm_fdr_bh | majority_positive_months   | bonferroni_pass_10pct   | fdr_pass_10pct   | perm_fdr_pass_10pct   |
|:---------|-----------:|-------:|---------:|------------------:|-----------------------------:|---------------------------------:|-----------------------------------------:|------------------------:|--------------------:|----------------:|----------------------:|---------------------:|---------------------:|:---------------------------|:------------------------|:-----------------|:----------------------|
| AUDUSD   |        0.9 |   8867 |       11 |                11 |                      1.56594 |                          1.56594 |                                  1.03458 |             4.41092e-12 |         2.64655e-11 |     5.2931e-12  |                   nan |                  nan |                  nan | True                       | True                    | True             | False                 |
| EURUSD   |        0.9 |   6771 |       11 |                11 |                      2.31991 |                          2.31991 |                                  1.6917  |             1.11022e-16 |         6.66134e-16 |     1.66533e-16 |                   nan |                  nan |                  nan | True                       | True                    | True             | False                 |
| GBPUSD   |        0.9 |  13737 |       11 |                11 |                      2.63023 |                          2.63023 |                                  2.43777 |             0           |         0           |     0           |                   nan |                  nan |                  nan | True                       | True                    | True             | False                 |
| USDCAD   |        0.9 |   6905 |       11 |                11 |                      1.66355 |                          1.66355 |                                  1.2799  |             0           |         0           |     0           |                   nan |                  nan |                  nan | True                       | True                    | True             | False                 |
| USDCHF   |        0.9 |   8287 |       11 |                11 |                      2.21857 |                          2.21857 |                                  1.19544 |             1.97176e-12 |         1.18305e-11 |     3.94351e-12 |                   nan |                  nan |                  nan | True                       | True                    | True             | False                 |
| USDJPY   |        0.9 |  17066 |       11 |                11 |                      3.58099 |                          3.58099 |                                  3.32542 |             0           |         0           |     0           |                   nan |                  nan |                  nan | True                       | True                    | True             | False                 |

- Interpretation: Stage 2 mining is accepted only as hypothesis generation; false-discovery control is enforced downstream via Stage 3/8 out-of-sample evaluation.
- Multiplicity fields (`pvalue_bonferroni`, `pvalue_fdr_bh`) are reported at the execution quantile and should be used with LB95/month-consistency, not in isolation.
<!-- GENERATED:STAGE_02:END -->
