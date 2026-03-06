# Stage 5 - Reduced Core Selection

## Objective
Reduce candidate universe to a stable, capacity-valid core set with preserved expectancy.

## Inputs
- Reduced summary:
- `data/analysis/tick_opportunity_mining/reduced_core_rolling*/<SYMBOL>_oco_reduced_summary.csv`
- Reduced monthly:
- `data/analysis/tick_opportunity_mining/reduced_core_rolling*/<SYMBOL>_oco_reduced_monthly.csv`
- State churn:
- `data/analysis/tick_opportunity_mining/reduced_core_rolling*/<SYMBOL>_oco_reduced_state_churn.csv`

## Process
- Select reduced states month-by-month using prior train window.
- Validate capacity floor and state churn constraints.
- Compute reduction diagnostics (`R01-R03`).
- Enforce that reduced states stay inside the pre-registered rule universe contract.

## Dependency on Stage 3 (CatBoost Outputs)
- Stage 5 consumes Stage 3 prediction artifacts (`*_monthly_predictions.parquet`) and does not refit CatBoost.
- Default reduced-core entry set is controlled by `selection_mode`:
- `auto` / `exec_flag`: uses Stage 3 execution flag (`selected_exec == 1`).
- `monthly_quantile`: recomputes monthwise quantile filter from `pred_prob` when explicitly configured.
- Stage 3 is model-level row ranking; Stage 5 is state-level governance filtering:
- model layer: probability thresholding (`pred_prob`, `threshold_exec`, `selected_exec`)
- state layer: stability/capacity/risk gates across rolling train months
- If Stage 3 predictions are stale for the current test month, Stage 5 outputs are operationally invalid.

## CatBoost x Core Spec Interaction
- Final tradable rows are the strict intersection of three gates:
- `core_spec_match == 1` (row is inside reduced-core state set)
- `selected_exec == 1` (Stage 3 CatBoost passed execution threshold)
- `execution_feasible == 1` (Stage 4 stop-limit realism/fill constraints passed)
- Operational rule:
- `trade_row = core_spec_match AND selected_exec AND execution_feasible`
- Rejection logic:
- CatBoost positive but outside core spec -> reject.
- Core spec match but CatBoost below threshold -> reject.
- Passes both but execution infeasible (for configured cap/fill policy) -> reject.

```mermaid
flowchart TD
    A[Candidate row at test timestamp] --> B{Inside reduced-core state spec}
    B -- no --> X1[Reject]
    B -- yes --> C{CatBoost selected_exec equals 1}
    C -- no --> X2[Reject]
    C -- yes --> D{Execution feasible under stop-limit policy}
    D -- no --> X3[Reject]
    D -- yes --> E[Trade row admitted]
```

### Row-Level Example
- Example row:
- `state_key=tf30_revert_b2_h3`
- `core_spec_match=1`
- `pred_prob=0.84`
- `threshold_exec=0.79`
- `selected_exec=1`
- `execution_feasible=1`
- Outcome: admitted (`trade_row=1`).
- If the same row had `core_spec_match=0`, it would be rejected even with `selected_exec=1`.

## Exact Calculations
- `R01_post_pre_row_ratio = reduced_rows / prefilter_wfo_selected_rows`
- `R02_top_state_dependency = max_top_state_share` (or `top_state_share` if available)
- `R03_reselection_stability = 1 - mean(state_churn_rate)`

## Rule-Universe Enforcement
- Registry artifact: `configs/research/governance/oco_rule_universe_registry.yaml`
- Allowed reduced dimensions:
- families: `allowed_families`
- barriers: `allowed_barrier_keep`
- horizons: `allowed_horizon_keep`
- Contract checks:
- `RU08`: reduced states file exists per symbol.
- `RU09`: every reduced state row is inside the registered universe.
- Artifacts:
- `data/analysis/tick_opportunity_mining/oco_rule_universe_registry_checks.csv`
- `data/analysis/tick_opportunity_mining/oco_rule_universe_registry_issues.csv`
- `docs/analysis/oco_rule_universe_registry_report.md`

## Causality / Leakage Controls
- State schedule and selection produced from prior-month training only.
- Universe lock prevents post-hoc adding states/families discovered after out-of-sample review.

## Failure Modes
- Over-pruning removes too much capacity.
- Top-state dependency increases fragility.
- High churn indicates unstable core.

## Interpretation Guide
- `R01` too low: likely over-pruned.
- `R02` high: concentration risk.
- `R03` high: more stable monthly state persistence.

## Validation Gates
- Capacity and stability conditions are hard gates in reduced-core outputs.
- `R01-R03` are monitoring diagnostics.
- Hard governance condition: reduced states must pass registry scope checks (`RU09`, surfaced by `C33`).

## Canonical Analysis Reports
- `docs/analysis/eurusd_oco_reduced_core_rolling_report.md`
- `docs/analysis/gbpusd_oco_reduced_core_rolling_report.md`
- `docs/analysis/usdjpy_oco_reduced_core_rolling_report.md`
- `docs/analysis/oco_rule_universe_registry_report.md`

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
uv run python scripts/select_oco_reduced_core_rolling.py \
  --symbols EURUSD,GBPUSD,USDJPY,USDCHF,AUDUSD,USDCAD
uv run python scripts/validate_oco_rule_universe_registry.py
```

## Traceability
- `scripts/select_oco_reduced_core_rolling.py`
- `scripts/validate_oco_rule_universe_registry.py`
- `docs/analysis/*_oco_reduced_core_rolling_report.md`
- `docs/analysis/oco_rule_universe_registry_report.md`
- `docs/strategy_bible/generated/stage_05_snapshot.md`

## Generated Run Snapshot
<!-- GENERATED:STAGE_05:START -->
### Auto Snapshot - Stage 05

- generated_at: `2026-03-06 10:46:49 UTC`
- State schedule is selected month-by-month using only prior-month train data.
- Summary emphasizes full-path gross behavior after reduced-core filtering.
- R01-R03 track pruning severity, state concentration, and re-selection stability.

#### Key Results
| symbol   |   rows_total |   mean_gross_pips |   lb95_month_mean_gross_pips |   fill_rate_overall |   positive_months |   months_total |   r01_post_pre_row_ratio |   r02_top_state_dependency |   r03_reselection_stability |
|:---------|-------------:|------------------:|-----------------------------:|--------------------:|------------------:|---------------:|-------------------------:|---------------------------:|----------------------------:|
| EURUSD   |         6136 |           2.4536  |                      1.55332 |            0.990157 |                11 |             15 |                0.0134992 |                       0.35 |                    0.361111 |
| GBPUSD   |        12675 |           2.48056 |                      2.31733 |            0.993806 |                11 |             15 |                0.0293091 |                       0.35 |                    0.270833 |
| AUDUSD   |         8286 |           1.7272  |                      0.99331 |            0.994121 |                11 |             15 |                0.0200522 |                       0.35 |                    0.416667 |
| USDJPY   |        11945 |           3.77228 |                      3.38607 |            0.984181 |                11 |             15 |                0.0259624 |                       0.35 |                    0.444444 |
| USDCHF   |         9554 |           1.93764 |                      1.14885 |            0.986474 |                11 |             15 |                0.0263301 |                       0.35 |                    0.391667 |
| USDCAD   |         8372 |           1.99961 |                      1.0742  |            0.989598 |                11 |             15 |                0.0158831 |                       0.35 |                    0.305556 |

#### Interpretation Notes
- State schedule is selected month-by-month using only prior-month train data.
- Summary emphasizes full-path gross behavior after reduced-core filtering.
- R01-R03 track pruning severity, state concentration, and re-selection stability.

#### Action Trigger Summary
| symbol   | metric_id                | band   | severity   | action_code   | action_summary     | owner    |
|:---------|:-------------------------|:-------|:-----------|:--------------|:-------------------|:---------|
| AUDUSD   | R02_top_state_dependency | green  | info       | A0_MONITOR    | within policy band | research |
| EURUSD   | R02_top_state_dependency | green  | info       | A0_MONITOR    | within policy band | research |
| GBPUSD   | R02_top_state_dependency | green  | info       | A0_MONITOR    | within policy band | research |
| USDCAD   | R02_top_state_dependency | green  | info       | A0_MONITOR    | within policy band | research |
| USDCHF   | R02_top_state_dependency | green  | info       | A0_MONITOR    | within policy band | research |
| USDJPY   | R02_top_state_dependency | green  | info       | A0_MONITOR    | within policy band | research |

#### Details
| symbol   |   months |   rows_total |   mean_fill_rate |   mean_gross |
|:---------|---------:|-------------:|-----------------:|-------------:|
| AUDUSD   |       15 |         8286 |         0.994228 |      1.19889 |
| EURUSD   |       15 |         6136 |         0.993515 |      1.8845  |
| GBPUSD   |       15 |        12675 |         0.993034 |      2.45732 |
| USDCAD   |       15 |         8372 |         0.992375 |      1.35779 |
| USDCHF   |       15 |         9554 |         0.983607 |      1.46536 |
| USDJPY   |       15 |        11945 |         0.985538 |      3.63441 |

#### Plots
![stage_05_reduced_monthly_gross](../figures/oco_bible/stage_05_reduced_monthly_gross.png)

#### State Churn
| symbol   | test_month   |   states_selected |   state_churn_rate |   top_state_share |   state_hhi |   stability_pass | status       |
|:---------|:-------------|------------------:|-------------------:|------------------:|------------:|-----------------:|:-------------|
| EURUSD   | 2025-01      |                 0 |         nan        |        nan        |  nan        |              nan | warmup_skip  |
| EURUSD   | 2025-02      |                 0 |         nan        |        nan        |  nan        |              nan | warmup_skip  |
| EURUSD   | 2025-03      |                 0 |         nan        |        nan        |  nan        |              nan | warmup_skip  |
| EURUSD   | 2025-04      |                 2 |           0        |          0.71733  |    0.594465 |                0 | ok           |
| EURUSD   | 2025-05      |                 2 |           0.666667 |          0.707404 |    0.586033 |                0 | ok           |
| EURUSD   | 2025-06      |                 2 |           1        |          0.85348  |    0.749896 |                0 | ok           |
| EURUSD   | 2025-07      |                 2 |           1        |          0.597647 |    0.51907  |                0 | ok           |
| EURUSD   | 2025-08      |                 3 |           0.75     |          0.472313 |    0.391357 |                0 | ok           |
| EURUSD   | 2025-09      |                 2 |           0.75     |          0.551247 |    0.505252 |                0 | ok           |
| EURUSD   | 2025-10      |                 1 |           1        |          1        |    1        |                0 | ok           |
| EURUSD   | 2025-11      |                 2 |           0.5      |          0.523013 |    0.501059 |                0 | ok           |
| EURUSD   | 2025-12      |                 1 |           1        |          1        |    1        |                0 | ok           |
| EURUSD   | 2026-01      |                 1 |           0        |          1        |    1        |                0 | ok           |
| EURUSD   | 2026-02      |                 1 |           1        |          1        |    1        |                0 | ok           |
| EURUSD   | 2026-03      |                 1 |           0        |        nan        |  nan        |                1 | no_test_rows |
| GBPUSD   | 2025-01      |                 0 |         nan        |        nan        |  nan        |              nan | warmup_skip  |
| GBPUSD   | 2025-02      |                 0 |         nan        |        nan        |  nan        |              nan | warmup_skip  |
| GBPUSD   | 2025-03      |                 0 |         nan        |        nan        |  nan        |              nan | warmup_skip  |
| GBPUSD   | 2025-04      |                 2 |           0        |          0.642321 |    0.540511 |                0 | ok           |
| GBPUSD   | 2025-05      |                 2 |           0.666667 |          0.584718 |    0.514354 |                0 | ok           |
| GBPUSD   | 2025-06      |                 2 |           0.666667 |          0.707182 |    0.585849 |                0 | ok           |
| GBPUSD   | 2025-07      |                 2 |           1        |          0.519398 |    0.500753 |                0 | ok           |
| GBPUSD   | 2025-08      |                 2 |           1        |          0.616474 |    0.527132 |                0 | ok           |
| GBPUSD   | 2025-09      |                 3 |           1        |          0.429344 |    0.347827 |                0 | ok           |
| GBPUSD   | 2025-10      |                 2 |           1        |          0.589074 |    0.515868 |                0 | ok           |
| GBPUSD   | 2025-11      |                 4 |           0.5      |          0.34817  |    0.265639 |                0 | ok           |
| GBPUSD   | 2025-12      |                 3 |           0.833333 |          0.355689 |    0.336022 |                0 | ok           |
| GBPUSD   | 2026-01      |                 2 |           0.75     |          0.501139 |    0.500003 |                0 | ok           |
| GBPUSD   | 2026-02      |                 2 |           0.666667 |          0.645872 |    0.542557 |                0 | ok           |
| GBPUSD   | 2026-03      |                 2 |           0.666667 |        nan        |  nan        |                0 | no_test_rows |
| AUDUSD   | 2025-01      |                 0 |         nan        |        nan        |  nan        |              nan | warmup_skip  |
| AUDUSD   | 2025-02      |                 0 |         nan        |        nan        |  nan        |              nan | warmup_skip  |
| AUDUSD   | 2025-03      |                 0 |         nan        |        nan        |  nan        |              nan | warmup_skip  |
| AUDUSD   | 2025-04      |                 2 |           0        |          0.512239 |    0.5003   |                0 | ok           |
| AUDUSD   | 2025-05      |                 2 |           0.666667 |          0.8768   |    0.783956 |                0 | ok           |
| AUDUSD   | 2025-06      |                 2 |           1        |          0.501238 |    0.500003 |                0 | ok           |
| AUDUSD   | 2025-07      |                 2 |           1        |          0.688022 |    0.570705 |                0 | ok           |
| AUDUSD   | 2025-08      |                 2 |           1        |          0.517857 |    0.500638 |                0 | ok           |
| AUDUSD   | 2025-09      |                 2 |           0.666667 |          0.5      |    0.5      |                0 | ok           |
| AUDUSD   | 2025-10      |                 2 |           0.666667 |          0.541176 |    0.503391 |                0 | ok           |
| AUDUSD   | 2025-11      |                 1 |           0.5      |          1        |    1        |                0 | ok           |
| AUDUSD   | 2025-12      |                 1 |           0        |          1        |    1        |                0 | ok           |
| AUDUSD   | 2026-01      |                 1 |           1        |          1        |    1        |                0 | ok           |
| AUDUSD   | 2026-02      |                 2 |           0.5      |          0.538787 |    0.503009 |                0 | ok           |
| AUDUSD   | 2026-03      |                 2 |           0        |        nan        |  nan        |                1 | no_test_rows |
| USDJPY   | 2025-01      |                 0 |         nan        |        nan        |  nan        |              nan | warmup_skip  |
| USDJPY   | 2025-02      |                 0 |         nan        |        nan        |  nan        |              nan | warmup_skip  |
| USDJPY   | 2025-03      |                 0 |         nan        |        nan        |  nan        |              nan | warmup_skip  |
| USDJPY   | 2025-04      |                 2 |           0        |          0.605609 |    0.522306 |                0 | ok           |
| USDJPY   | 2025-05      |                 1 |           0.5      |          1        |    1        |                0 | ok           |
| USDJPY   | 2025-06      |                 2 |           0.5      |          0.636443 |    0.537233 |                0 | ok           |
| USDJPY   | 2025-07      |                 1 |           0.5      |          1        |    1        |                0 | ok           |
| USDJPY   | 2025-08      |                 2 |           0.5      |          0.536093 |    0.502605 |                0 | ok           |
| USDJPY   | 2025-09      |                 2 |           0.666667 |          0.553411 |    0.505705 |                0 | ok           |
| USDJPY   | 2025-10      |                 2 |           0.666667 |          0.529131 |    0.501697 |                0 | ok           |
| USDJPY   | 2025-11      |                 2 |           0.666667 |          0.520055 |    0.500804 |                0 | ok           |
| USDJPY   | 2025-12      |                 2 |           0.666667 |          0.568895 |    0.509493 |                0 | ok           |
| USDJPY   | 2026-01      |                 2 |           0.666667 |          0.505768 |    0.500067 |                0 | ok           |
| USDJPY   | 2026-02      |                 2 |           0.666667 |          0.648924 |    0.544357 |                0 | ok           |
| USDJPY   | 2026-03      |                 2 |           0.666667 |        nan        |  nan        |                0 | no_test_rows |
| USDCHF   | 2025-01      |                 0 |         nan        |        nan        |  nan        |              nan | warmup_skip  |
| USDCHF   | 2025-02      |                 0 |         nan        |        nan        |  nan        |              nan | warmup_skip  |
| USDCHF   | 2025-03      |                 0 |         nan        |        nan        |  nan        |              nan | warmup_skip  |
| USDCHF   | 2025-04      |                 2 |           0        |          0.761764 |    0.637041 |                0 | ok           |
| USDCHF   | 2025-05      |                 2 |           0.666667 |          0.869822 |    0.773537 |                0 | ok           |
| USDCHF   | 2025-06      |                 3 |           1        |          0.473282 |    0.439156 |                0 | ok           |
| USDCHF   | 2025-07      |                 1 |           1        |          1        |    1        |                0 | ok           |
| USDCHF   | 2025-08      |                 2 |           0.5      |          0.575868 |    0.511512 |                0 | ok           |
| USDCHF   | 2025-09      |                 2 |           0.666667 |          0.547884 |    0.504586 |                0 | ok           |
| USDCHF   | 2025-10      |                 2 |           0        |          0.561254 |    0.507504 |                0 | ok           |
| USDCHF   | 2025-11      |                 2 |           1        |          0.560748 |    0.507381 |                0 | ok           |
| USDCHF   | 2025-12      |                 3 |           0.333333 |          0.418398 |    0.348418 |                0 | ok           |
| USDCHF   | 2026-01      |                 3 |           0.8      |          0.390187 |    0.339167 |                0 | ok           |
| USDCHF   | 2026-02      |                 2 |           0.333333 |          0.50625  |    0.500078 |                0 | ok           |
| USDCHF   | 2026-03      |                 1 |           1        |        nan        |  nan        |                0 | no_test_rows |
| USDCAD   | 2025-01      |                 0 |         nan        |        nan        |  nan        |              nan | warmup_skip  |
| USDCAD   | 2025-02      |                 0 |         nan        |        nan        |  nan        |              nan | warmup_skip  |
| USDCAD   | 2025-03      |                 0 |         nan        |        nan        |  nan        |              nan | warmup_skip  |
| USDCAD   | 2025-04      |                 2 |           0        |          0.678997 |    0.56408  |                0 | ok           |
| USDCAD   | 2025-05      |                 2 |           0.666667 |          0.705813 |    0.584718 |                0 | ok           |
| USDCAD   | 2025-06      |                 2 |           1        |          0.564685 |    0.508368 |                0 | ok           |
| USDCAD   | 2025-07      |                 2 |           0.666667 |          0.576108 |    0.511585 |                0 | ok           |
| USDCAD   | 2025-08      |                 2 |           0.666667 |          0.565826 |    0.508666 |                0 | ok           |
| USDCAD   | 2025-09      |                 2 |           1        |          0.60241  |    0.520975 |                0 | ok           |
| USDCAD   | 2025-10      |                 2 |           0.666667 |          0.501577 |    0.500005 |                0 | ok           |
| USDCAD   | 2025-11      |                 2 |           1        |          0.520548 |    0.500844 |                0 | ok           |
| USDCAD   | 2025-12      |                 2 |           0.666667 |          0.613333 |    0.525689 |                0 | ok           |
| USDCAD   | 2026-01      |                 1 |           1        |          1        |    1        |                0 | ok           |
| USDCAD   | 2026-02      |                 1 |           1        |          1        |    1        |                0 | ok           |
| USDCAD   | 2026-03      |                 1 |           0        |        nan        |  nan        |                1 | no_test_rows |

#### Leakage/Label Integrity (Reduced-Core Focus)
| symbol   |   checks_total |   checks_failed | failed_check_ids   |
|:---------|---------------:|----------------:|:-------------------|
| EURUSD   |              3 |               0 |                    |
| GBPUSD   |              3 |               0 |                    |
| AUDUSD   |              3 |               0 |                    |
| USDJPY   |              3 |               0 |                    |
| USDCHF   |              3 |               0 |                    |
| USDCAD   |              3 |               0 |                    |
<!-- GENERATED:STAGE_05:END -->
