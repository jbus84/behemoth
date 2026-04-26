# Stage 2 - Opportunity Mining

## Objective
Stage 2 Opportunity Mining mines high-count, gross-positive OCO opportunity families as hypotheses before Monthly WFO model filtering and robustness controls.

## Inputs
- Candidate catalogs:
- `data/analysis/tick_opportunity_mining/<SYMBOL>_oco_candidates.csv`
- Key candidate fields:
- `selection_pass`, `annualized_test_fills`, `mean_gross_pips_test`, `family`, `state_id`, `bar_ticks`, `horizon`

## Process
- Enumerate OCO state families and horizons.
- Keep broad Opportunity Mining candidate frontier (`selection_pass`) for downstream filtering.
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
- No governed deployment-scope gating at this stage without downstream Monthly WFO and robustness confirmation.
- Rule universe is locked before reduced-core/live selection and checked against frozen governance locks (`RU06-RU09`).

## Failure Modes
- Edge concentration in very few states (fragile alpha).
- Non-smooth parameter surfaces indicating noisy search.
- Post-hoc over-interpretation without Stage 3 Monthly WFO and Stage 8 controls.

## Interpretation Guide
- Lower `M01` is better diversification.
- Lower `M02` indicates smoother, less brittle parameter landscape.
- Higher `M03` indicates a denser positive frontier.

## Validation Gates
- Informational at Stage 2.
- Stage 2 itself does not issue `PASS`/`FAIL` or `GO`/`NO_GO` decisions; downstream hard gates appear later in the governance process, while formal certification is reserved for Stages 12-14.
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
- Read `Key Results` first for research posture and core health metrics.
- Use `Interpretation Notes` and `Action Trigger Summary` to map observed values to operational actions.

## What To Do If It Fails
- `critical/high`: halt promotion progression, remediate root cause, and rerun this stage plus downstream dependent stages.
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

- generated_at: `2026-04-12 17:21:09 UTC`
- selection_pass candidates are broad hypotheses only.
- Scatter shows the high-count >0 gross opportunity frontier.
- M01-M03 quantify concentration risk, horizon smoothness, and positive-edge density.

#### Key Results
| symbol   |   candidates_total |   selected_total |   selected_mean_gross_pips |   selected_median_annualized |   m01_top3_contrib_share |   m02_smoothness_abs_jump |   m03_positive_density |
|:---------|-------------------:|-----------------:|---------------------------:|-----------------------------:|-------------------------:|--------------------------:|-----------------------:|
| EURUSD   |               2160 |              556 |                    3.64659 |                      2748.26 |                0.041842  |                   1.44142 |               0.97482  |
| GBPUSD   |               2160 |              548 |                    4.28487 |                      2547.03 |                0.0366584 |                   1.80562 |               0.994526 |
| AUDUSD   |               2160 |              429 |                    2.98069 |                      1649.2  |                0.0405964 |                   1.37434 |               0.941725 |
| USDJPY   |               2160 |              614 |                    5.76644 |                      3853.33 |                0.0443718 |                   2.23006 |               1        |
| USDCHF   |               2160 |              435 |                    3.65539 |                      1560.99 |                0.0370581 |                   1.45946 |               0.993103 |
| USDCAD   |               2160 |              455 |                    2.73781 |                      1626.09 |                0.0566392 |                   1.41878 |               0.861538 |

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
| AUDUSD   | oco_first_touch_clean | oco_first_touch_clean__all__k3              |        1000 |         6 |       32782.4 |      0.0148481  |
| AUDUSD   | oco_first_touch_clean | oco_first_touch_clean__low_cost_q50__k3     |        1000 |         6 |       29040.6 |      0.0131533  |
| AUDUSD   | oco_first_touch_clean | oco_first_touch_clean__all__k3              |        1000 |         5 |       27807.8 |      0.012595   |
| AUDUSD   | oco_first_touch_clean | oco_first_touch_clean__all__k5              |        1000 |         6 |       27086   |      0.012268   |
| AUDUSD   | oco_first_touch_clean | oco_first_touch_clean__all__k5              |        2000 |         6 |       25515.8 |      0.0115568  |
| AUDUSD   | oco_first_touch_clean | oco_first_touch_clean__low_cost_q30__k3     |        1000 |         6 |       25415.7 |      0.0115115  |
| AUDUSD   | oco_first_touch_clean | oco_first_touch_clean__all__k2              |        1000 |         6 |       25128.1 |      0.0113812  |
| AUDUSD   | oco_first_touch_clean | oco_first_touch_clean__low_cost_q50__k3     |        1000 |         5 |       24273.4 |      0.0109941  |
| EURUSD   | oco_first_touch_clean | oco_first_touch_clean__all__k2              |         100 |         6 |      121464   |      0.0183317  |
| EURUSD   | oco_first_touch_clean | oco_first_touch_clean__high_range_q70__k2   |         100 |         6 |       78448.9 |      0.0118397  |
| EURUSD   | oco_first_touch_clean | oco_first_touch_clean__low_cost_q30__k2     |         100 |         6 |       77328.4 |      0.0116706  |
| EURUSD   | oco_first_touch_clean | oco_first_touch_clean__all__k2              |         100 |         5 |       74409.1 |      0.01123    |
| EURUSD   | oco_first_touch_clean | oco_first_touch_clean__all__k5              |        1000 |         6 |       65996.2 |      0.00996031 |
| EURUSD   | oco_first_touch_clean | oco_first_touch_clean__high_range_q80__k2   |         100 |         6 |       59672.3 |      0.0090059  |
| EURUSD   | oco_first_touch_clean | oco_first_touch_clean__all__k3              |        1000 |         6 |       58913.9 |      0.00889143 |
| EURUSD   | oco_first_touch_clean | oco_first_touch_clean__high_range_q70__k2   |         100 |         5 |       54127.9 |      0.00816912 |
| GBPUSD   | oco_first_touch_clean | oco_first_touch_clean__all__k2              |         100 |         6 |       93372.1 |      0.0136915  |
| GBPUSD   | oco_first_touch_clean | oco_first_touch_clean__low_cost_q50__k2     |         100 |         6 |       85461.4 |      0.0125315  |
| GBPUSD   | oco_first_touch_clean | oco_first_touch_clean__all__k5              |        1000 |         6 |       71166.3 |      0.0104354  |
| GBPUSD   | oco_first_touch_clean | oco_first_touch_clean__low_cost_q30__k2     |         100 |         6 |       64086.3 |      0.0093972  |
| GBPUSD   | oco_first_touch_clean | oco_first_touch_clean__all__k3              |        1000 |         6 |       57701.8 |      0.00846101 |
| GBPUSD   | oco_first_touch_clean | oco_first_touch_clean__all__k5              |        1000 |         5 |       57327   |      0.00840606 |
| GBPUSD   | oco_first_touch_clean | oco_first_touch_clean__low_cost_q50__k5     |        1000 |         6 |       56388   |      0.00826837 |
| GBPUSD   | oco_first_touch_clean | oco_first_touch_clean__all__k8              |        2000 |         6 |       51225.9 |      0.00751143 |
| USDCAD   | oco_first_touch_clean | oco_first_touch_clean__all__k3              |        1000 |         6 |       43056.9 |      0.0209189  |
| USDCAD   | oco_first_touch_clean | oco_first_touch_clean__all__k5              |        1000 |         6 |       38451.4 |      0.0186814  |
| USDCAD   | oco_first_touch_clean | oco_first_touch_clean__all__k5              |        2000 |         6 |       35070.5 |      0.0170388  |
| USDCAD   | oco_first_touch_clean | oco_first_touch_clean__all__k3              |        1000 |         5 |       34878.7 |      0.0169456  |
| USDCAD   | oco_first_touch_clean | oco_first_touch_clean__all__k2              |        1000 |         6 |       33898.1 |      0.0164692  |
| USDCAD   | oco_first_touch_clean | oco_first_touch_clean__all__k8              |        2000 |         6 |       30269.4 |      0.0147062  |
| USDCAD   | oco_first_touch_clean | oco_first_touch_clean__all__k5              |        2000 |         5 |       28918.8 |      0.0140501  |
| USDCAD   | oco_first_touch_clean | oco_first_touch_clean__all__k2              |        1000 |         5 |       28421.6 |      0.0138085  |
| USDCHF   | oco_first_touch_clean | oco_first_touch_clean__all__k5              |        1000 |         6 |       35222.8 |      0.0131761  |
| USDCHF   | oco_first_touch_clean | oco_first_touch_clean__all__k3              |        1000 |         6 |       34482.3 |      0.0128991  |
| USDCHF   | oco_first_touch_clean | oco_first_touch_clean__all__k5              |        2000 |         6 |       29360.2 |      0.010983   |
| USDCHF   | oco_first_touch_clean | oco_first_touch_clean__all__k3              |        1000 |         5 |       29209.6 |      0.0109266  |
| USDCHF   | oco_first_touch_clean | oco_first_touch_clean__all__k8              |        2000 |         6 |       26828.1 |      0.0100358  |
| USDCHF   | oco_first_touch_clean | oco_first_touch_clean__all__k2              |        1000 |         6 |       26142.4 |      0.00977927 |
| USDCHF   | oco_first_touch_clean | oco_first_touch_clean__all__k5              |        2000 |         5 |       25810   |      0.00965495 |
| USDCHF   | oco_first_touch_clean | oco_first_touch_clean__all__k5              |        1000 |         5 |       25465.9 |      0.0095262  |
| USDJPY   | oco_first_touch_clean | oco_first_touch_clean__all__k2              |         100 |         6 |      308050   |      0.0186331  |
| USDJPY   | oco_first_touch_clean | oco_first_touch_clean__all__k2              |         100 |         5 |      221043   |      0.0133703  |
| USDJPY   | oco_first_touch_clean | oco_first_touch_clean__low_cost_q50__k2     |         100 |         6 |      204479   |      0.0123684  |
| USDJPY   | oco_first_touch_clean | oco_first_touch_clean__high_range_q70__k2   |         100 |         6 |      158576   |      0.00959184 |
| USDJPY   | oco_first_touch_clean | oco_first_touch_clean__low_cost_q50__k2     |         100 |         5 |      149334   |      0.00903283 |
| USDJPY   | oco_first_touch_clean | oco_first_touch_clean__high_abs_vel_q70__k2 |         100 |         6 |      145671   |      0.00881124 |
| USDJPY   | oco_first_touch_clean | oco_first_touch_clean__low_cost_q30__k2     |         100 |         6 |      139766   |      0.00845406 |
| USDJPY   | oco_first_touch_clean | oco_first_touch_clean__all__k3              |         100 |         6 |      133897   |      0.00809904 |

#### Overfitting Diagnostics (Downstream, Exec Quantile)
| symbol   |   quantile |   rows |   months |   positive_months |   lb95_trade_mean_gross_pips |   lb95_trade_mean_gross_pips_iid |   lb95_trade_mean_gross_pips_month_block |   pvalue_month_mean_gt0 |   pvalue_bonferroni |   pvalue_fdr_bh |   uplift_vs_null_pips |   pvalue_perm_uplift |   pvalue_perm_fdr_bh | majority_positive_months   | bonferroni_pass_10pct   | fdr_pass_10pct   | perm_fdr_pass_10pct   |
|:---------|-----------:|-------:|---------:|------------------:|-----------------------------:|---------------------------------:|-----------------------------------------:|------------------------:|--------------------:|----------------:|----------------------:|---------------------:|---------------------:|:---------------------------|:------------------------|:-----------------|:----------------------|
| AUDUSD   |        0.9 |   2388 |        7 |                 7 |                      5.12738 |                          5.12738 |                                  5.22063 |                       0 |                   0 |               0 |                   nan |                  nan |                  nan | True                       | True                    | True             | False                 |
| EURUSD   |        0.9 |   6430 |       12 |                12 |                      7.44487 |                          7.44487 |                                  6.77829 |                       0 |                   0 |               0 |                   nan |                  nan |                  nan | True                       | True                    | True             | False                 |
| GBPUSD   |        0.9 |   7191 |       12 |                12 |                      7.50235 |                          7.50235 |                                  7.10403 |                       0 |                   0 |               0 |                   nan |                  nan |                  nan | True                       | True                    | True             | False                 |
| USDCAD   |        0.9 |   4062 |       10 |                10 |                      5.28134 |                          5.28134 |                                  4.87833 |                       0 |                   0 |               0 |                   nan |                  nan |                  nan | True                       | True                    | True             | False                 |
| USDCHF   |        0.9 |   1773 |        6 |                 6 |                      5.48371 |                          5.48371 |                                  4.74044 |                       0 |                   0 |               0 |                   nan |                  nan |                  nan | True                       | True                    | True             | False                 |
| USDJPY   |        0.9 |   5205 |       12 |                12 |                     10.7085  |                         10.7085  |                                 10.4879  |                       0 |                   0 |               0 |                   nan |                  nan |                  nan | True                       | True                    | True             | False                 |

- Interpretation: Stage 2 mining is accepted only as hypothesis generation; false-discovery control is enforced downstream via Stage 3/8 out-of-sample evaluation.
- Multiplicity fields (`pvalue_bonferroni`, `pvalue_fdr_bh`) are reported at the execution quantile and should be used with LB95/month-consistency, not in isolation.
<!-- GENERATED:STAGE_02:END -->
