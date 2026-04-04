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

- generated_at: `2026-04-03 12:49:19 UTC`
- State schedule is selected month-by-month using only prior-month train data.
- Summary emphasizes full-path gross behavior after reduced-core filtering.
- R01-R03 track pruning severity, state concentration, and re-selection stability.

#### Key Results
| symbol   |   rows_total |   mean_gross_pips |   lb95_month_mean_gross_pips |   fill_rate_overall |   positive_months |   months_total |   r01_post_pre_row_ratio |   r02_top_state_dependency |   r03_reselection_stability |
|:---------|-------------:|------------------:|-----------------------------:|--------------------:|------------------:|---------------:|-------------------------:|---------------------------:|----------------------------:|
| EURUSD   |         6734 |           2.28759 |                     1.6048   |            0.994536 |                11 |             15 |                0.0168844 |                       0.35 |                    0.340278 |
| GBPUSD   |        13641 |           2.56616 |                     2.31434  |            0.993012 |                11 |             15 |                0.0298041 |                       0.35 |                    0.430556 |
| AUDUSD   |         8824 |           1.54805 |                     0.954024 |            0.995151 |                11 |             15 |                0.0212827 |                       0.35 |                    0.315278 |
| USDJPY   |        16864 |           3.41663 |                     3.1392   |            0.988164 |                11 |             15 |                0.0351748 |                       0.35 |                    0.355556 |
| USDCHF   |         8161 |           2.17551 |                     1.07661  |            0.984795 |                11 |             15 |                0.0218528 |                       0.35 |                    0.305556 |
| USDCAD   |         6841 |           1.60772 |                     1.17257  |            0.990731 |                11 |             15 |                0.0151447 |                       0.35 |                    0.236111 |

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
| AUDUSD   |       15 |         8824 |         0.995275 |      1.20716 |
| EURUSD   |       15 |         6734 |         0.994542 |      1.96339 |
| GBPUSD   |       15 |        13641 |         0.992776 |      2.4785  |
| USDCAD   |       15 |         6841 |         0.992733 |      1.38618 |
| USDCHF   |       15 |         8161 |         0.985956 |      1.3893  |
| USDJPY   |       15 |        16864 |         0.988259 |      3.35048 |

#### Plots
![stage_05_reduced_monthly_gross](../figures/oco_bible/stage_05_reduced_monthly_gross.png)

#### State Churn
| symbol   | test_month   |   states_selected |   state_churn_rate |   top_state_share |   state_hhi |   stability_pass | status       |
|:---------|:-------------|------------------:|-------------------:|------------------:|------------:|-----------------:|:-------------|
| EURUSD   | 2025-01      |                 0 |         nan        |        nan        |  nan        |              nan | warmup_skip  |
| EURUSD   | 2025-02      |                 0 |         nan        |        nan        |  nan        |              nan | warmup_skip  |
| EURUSD   | 2025-03      |                 0 |         nan        |        nan        |  nan        |              nan | warmup_skip  |
| EURUSD   | 2025-04      |                 2 |           0        |          0.651685 |    0.546017 |                0 | ok           |
| EURUSD   | 2025-05      |                 2 |           0.666667 |          0.567036 |    0.508988 |                0 | ok           |
| EURUSD   | 2025-06      |                 1 |           0.5      |          1        |    1        |                0 | ok           |
| EURUSD   | 2025-07      |                 1 |           0        |          1        |    1        |                0 | ok           |
| EURUSD   | 2025-08      |                 3 |           0.666667 |          0.374464 |    0.335899 |                0 | ok           |
| EURUSD   | 2025-09      |                 2 |           0.75     |          0.551053 |    0.505213 |                0 | ok           |
| EURUSD   | 2025-10      |                 2 |           1        |          0.774306 |    0.650487 |                0 | ok           |
| EURUSD   | 2025-11      |                 2 |           0.666667 |          0.534247 |    0.502346 |                0 | ok           |
| EURUSD   | 2025-12      |                 2 |           1        |          0.552699 |    0.505554 |                0 | ok           |
| EURUSD   | 2026-01      |                 2 |           0.666667 |          0.638847 |    0.538557 |                0 | ok           |
| EURUSD   | 2026-02      |                 1 |           1        |          1        |    1        |                0 | ok           |
| EURUSD   | 2026-03      |                 1 |           1        |        nan        |  nan        |                0 | no_test_rows |
| GBPUSD   | 2025-01      |                 0 |         nan        |        nan        |  nan        |              nan | warmup_skip  |
| GBPUSD   | 2025-02      |                 0 |         nan        |        nan        |  nan        |              nan | warmup_skip  |
| GBPUSD   | 2025-03      |                 0 |         nan        |        nan        |  nan        |              nan | warmup_skip  |
| GBPUSD   | 2025-04      |                 2 |           0        |          0.53899  |    0.50304  |                0 | ok           |
| GBPUSD   | 2025-05      |                 2 |           0.666667 |          0.673291 |    0.560059 |                0 | ok           |
| GBPUSD   | 2025-06      |                 2 |           0        |          0.683219 |    0.567139 |                0 | ok           |
| GBPUSD   | 2025-07      |                 2 |           0.666667 |          0.575778 |    0.511484 |                0 | ok           |
| GBPUSD   | 2025-08      |                 2 |           0.666667 |          0.509195 |    0.500169 |                0 | ok           |
| GBPUSD   | 2025-09      |                 2 |           0.666667 |          0.543656 |    0.503812 |                0 | ok           |
| GBPUSD   | 2025-10      |                 2 |           0.666667 |          0.503882 |    0.50003  |                0 | ok           |
| GBPUSD   | 2025-11      |                 2 |           0.666667 |          0.644118 |    0.54154  |                0 | ok           |
| GBPUSD   | 2025-12      |                 2 |           0.666667 |          0.556716 |    0.506434 |                0 | ok           |
| GBPUSD   | 2026-01      |                 2 |           1        |          0.564677 |    0.508366 |                0 | ok           |
| GBPUSD   | 2026-02      |                 2 |           0.666667 |          0.552655 |    0.505545 |                0 | ok           |
| GBPUSD   | 2026-03      |                 1 |           0.5      |        nan        |  nan        |                0 | no_test_rows |
| AUDUSD   | 2025-01      |                 0 |         nan        |        nan        |  nan        |              nan | warmup_skip  |
| AUDUSD   | 2025-02      |                 0 |         nan        |        nan        |  nan        |              nan | warmup_skip  |
| AUDUSD   | 2025-03      |                 0 |         nan        |        nan        |  nan        |              nan | warmup_skip  |
| AUDUSD   | 2025-04      |                 2 |           0        |          0.557899 |    0.506705 |                0 | ok           |
| AUDUSD   | 2025-05      |                 2 |           0.666667 |          0.575283 |    0.511335 |                0 | ok           |
| AUDUSD   | 2025-06      |                 2 |           0.666667 |          0.560299 |    0.507272 |                0 | ok           |
| AUDUSD   | 2025-07      |                 2 |           1        |          0.777559 |    0.654078 |                0 | ok           |
| AUDUSD   | 2025-08      |                 4 |           0.8      |          0.342484 |    0.289067 |                0 | ok           |
| AUDUSD   | 2025-09      |                 2 |           1        |          0.577017 |    0.511863 |                0 | ok           |
| AUDUSD   | 2025-10      |                 2 |           0.666667 |          0.510597 |    0.500225 |                0 | ok           |
| AUDUSD   | 2025-11      |                 3 |           0.333333 |          0.389365 |    0.339196 |                0 | ok           |
| AUDUSD   | 2025-12      |                 2 |           0.75     |          0.68306  |    0.567022 |                0 | ok           |
| AUDUSD   | 2026-01      |                 2 |           1        |          0.506369 |    0.500081 |                0 | ok           |
| AUDUSD   | 2026-02      |                 2 |           0.666667 |          0.554839 |    0.506015 |                0 | ok           |
| AUDUSD   | 2026-03      |                 2 |           0.666667 |        nan        |  nan        |                0 | no_test_rows |
| USDJPY   | 2025-01      |                 0 |         nan        |        nan        |  nan        |              nan | warmup_skip  |
| USDJPY   | 2025-02      |                 0 |         nan        |        nan        |  nan        |              nan | warmup_skip  |
| USDJPY   | 2025-03      |                 0 |         nan        |        nan        |  nan        |              nan | warmup_skip  |
| USDJPY   | 2025-04      |                 2 |           0        |          0.608278 |    0.523448 |                0 | ok           |
| USDJPY   | 2025-05      |                 3 |           0.333333 |          0.419526 |    0.345646 |                0 | ok           |
| USDJPY   | 2025-06      |                 3 |           0.8      |          0.470968 |    0.415302 |                0 | ok           |
| USDJPY   | 2025-07      |                 1 |           1        |          1        |    1        |                0 | ok           |
| USDJPY   | 2025-08      |                 2 |           0.5      |          0.515371 |    0.500473 |                0 | ok           |
| USDJPY   | 2025-09      |                 2 |           0.666667 |          0.761364 |    0.636622 |                0 | ok           |
| USDJPY   | 2025-10      |                 2 |           0.666667 |          0.610429 |    0.524389 |                0 | ok           |
| USDJPY   | 2025-11      |                 4 |           0.8      |          0.288344 |    0.255373 |                0 | ok           |
| USDJPY   | 2025-12      |                 2 |           0.8      |          0.542469 |    0.503607 |                0 | ok           |
| USDJPY   | 2026-01      |                 2 |           0.666667 |          0.624346 |    0.530924 |                0 | ok           |
| USDJPY   | 2026-02      |                 1 |           1        |          1        |    1        |                0 | ok           |
| USDJPY   | 2026-03      |                 2 |           0.5      |        nan        |  nan        |                0 | no_test_rows |
| USDCHF   | 2025-01      |                 0 |         nan        |        nan        |  nan        |              nan | warmup_skip  |
| USDCHF   | 2025-02      |                 0 |         nan        |        nan        |  nan        |              nan | warmup_skip  |
| USDCHF   | 2025-03      |                 0 |         nan        |        nan        |  nan        |              nan | warmup_skip  |
| USDCHF   | 2025-04      |                 3 |           0        |          0.545053 |    0.471653 |                0 | ok           |
| USDCHF   | 2025-05      |                 1 |           0.666667 |          1        |    1        |                0 | ok           |
| USDCHF   | 2025-06      |                 2 |           0.5      |          0.703704 |    0.58299  |                0 | ok           |
| USDCHF   | 2025-07      |                 2 |           1        |          0.87007  |    0.773903 |                0 | ok           |
| USDCHF   | 2025-08      |                 2 |           0.666667 |          0.774882 |    0.65112  |                0 | ok           |
| USDCHF   | 2025-09      |                 2 |           0.666667 |          0.586364 |    0.514917 |                0 | ok           |
| USDCHF   | 2025-10      |                 2 |           0.666667 |          0.54102  |    0.503365 |                0 | ok           |
| USDCHF   | 2025-11      |                 2 |           0.666667 |          0.511574 |    0.500268 |                0 | ok           |
| USDCHF   | 2025-12      |                 2 |           1        |          0.524272 |    0.501178 |                0 | ok           |
| USDCHF   | 2026-01      |                 1 |           0.5      |          1        |    1        |                0 | ok           |
| USDCHF   | 2026-02      |                 1 |           1        |          1        |    1        |                0 | ok           |
| USDCHF   | 2026-03      |                 2 |           1        |        nan        |  nan        |                0 | no_test_rows |
| USDCAD   | 2025-01      |                 0 |         nan        |        nan        |  nan        |              nan | warmup_skip  |
| USDCAD   | 2025-02      |                 0 |         nan        |        nan        |  nan        |              nan | warmup_skip  |
| USDCAD   | 2025-03      |                 0 |         nan        |        nan        |  nan        |              nan | warmup_skip  |
| USDCAD   | 2025-04      |                 2 |           0        |          0.533278 |    0.502215 |                0 | ok           |
| USDCAD   | 2025-05      |                 2 |           1        |          0.511208 |    0.500251 |                0 | ok           |
| USDCAD   | 2025-06      |                 2 |           0.666667 |          0.812088 |    0.694798 |                0 | ok           |
| USDCAD   | 2025-07      |                 2 |           1        |          0.802158 |    0.682599 |                0 | ok           |
| USDCAD   | 2025-08      |                 2 |           1        |          0.612058 |    0.525114 |                0 | ok           |
| USDCAD   | 2025-09      |                 2 |           0        |          0.522305 |    0.500995 |                0 | ok           |
| USDCAD   | 2025-10      |                 1 |           1        |          1        |    1        |                0 | ok           |
| USDCAD   | 2025-11      |                 2 |           0.5      |          0.542125 |    0.503549 |                0 | ok           |
| USDCAD   | 2025-12      |                 1 |           1        |          1        |    1        |                0 | ok           |
| USDCAD   | 2026-01      |                 2 |           1        |          0.51927  |    0.500743 |                0 | ok           |
| USDCAD   | 2026-02      |                 1 |           1        |          1        |    1        |                0 | ok           |
| USDCAD   | 2026-03      |                 2 |           1        |        nan        |  nan        |                0 | no_test_rows |

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
