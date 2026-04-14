# Stage 11 - Execution Monte Carlo

## Objective
Stress-test stop-limit execution realism using month x session Monte Carlo scenarios and quantify deployment envelopes.

## Inputs
- `data/analysis/tick_opportunity_mining/stop_limit_tickfill_fullcap/<SYMBOL>_stop_limit_tickfill_detail.csv`
- `data/analysis/tick_opportunity_mining/stop_limit_tickfill_fullcap/<SYMBOL>_stop_limit_tickfill_caps.csv`
- `data/analysis/tick_opportunity_mining/execution_mc_month_session_summary.csv`
- `data/analysis/tick_opportunity_mining/execution_mc_symbol_scenarios.csv`
- `data/analysis/tick_opportunity_mining/execution_mc_checks.csv`

## Process
- Select production cap per symbol from Stage 04 cap sweep (`max mean_per_signal_full_overshoot`).
- Bucket events by `test_month x session_bucket`.
- Apply scenario stress transforms on cap and slippage.
- Simulate per-group and per-month distributions over `N` iterations.
- Aggregate to symbol scenario summaries and run governance checks `EM01..EM05`.

## Exact Calculations
- `cap_eff = max(cap_pips - latency_shift_pips, 0)`
- `extra_slip = spread_add_pips + max(0, overshoot_tick_pips - cap_eff)` (if cap-eligible, else 0)
- `pnl_pre = target_gross_pips - extra_slip` (if cap-eligible, else 0)
- `q_keep = 1 - fill_decay` (if cap-eligible, else 0)
- Per-signal random variable: `X = pnl_pre * Bernoulli(q_keep)`
- Group-level `mean_per_signal` draws use moment-matched normal approximation:
- `mu = E[X]`, `var = E[X^2] - mu^2`, draw `mu_draw ~ Normal(mu, sqrt(var/n))`
- Month-level and symbol-level draws are weighted sums of group draws.

## Causality / Leakage Controls
- Uses only realized tickfill artifacts already fixed in time.
- No future month labels are introduced.
- Scenario transforms are mechanical and do not use future outcomes for tuning.

## Failure Modes
- Over-optimistic pass when stress levels are too mild.
- Unstable estimates in sparse month/session buckets.
- Distribution shift beyond historical overshoot behavior.

## Interpretation Guide
- Higher `lb95_per_signal_pips` and `lb99_per_signal_pips` indicate stronger execution robustness.
- Lower `prob_negative_month` indicates better month-to-month stability.
- Lower `fill_rate_drop_vs_S0` indicates lower sensitivity to stress.
- `drawdown_proxy_p95` closer to zero indicates better downside containment.

## Validation Gates
- `EM01`: `lb95_per_signal_pips > 0` in `S1_mild`
- `EM02`: `lb95_per_signal_pips >= 0` in `S2_moderate`
- `EM03`: `prob_negative_month <= 0.35` in `S1_mild`
- `EM04`: `fill_rate_drop_vs_S0 <= 0.12` in `S1_mild`
- `EM05`: no NaN in core scenario outputs

## Canonical Analysis Reports
- `docs/analysis/oco_execution_monte_carlo_report.md`
- `docs/analysis/oco_execution_monte_carlo_validation_report.md`
- `docs/strategy_bible/operator_runbook.md`

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
uv run python scripts/run_execution_monte_carlo.py \
  --symbols EURUSD,GBPUSD,USDJPY,USDCHF,AUDUSD,USDCAD

uv run python scripts/validate_execution_monte_carlo.py
```

## Traceability
- `scripts/run_execution_monte_carlo.py`
- `scripts/validate_execution_monte_carlo.py`
- `docs/analysis/oco_execution_monte_carlo_report.md`
- `docs/strategy_bible/generated/stage_11_snapshot.md`

## Generated Run Snapshot
<!-- GENERATED:STAGE_11:START -->
### Auto Snapshot - Stage 11

- generated_at: `2026-04-12 17:21:09 UTC`
- Execution Monte Carlo uses month x session stress scenarios derived from Stage 04 tickfill artifacts.
- EM01-EM05 summarize mild/moderate survival, month negativity risk, fill-rate decay, and data integrity.

#### Key Results
_empty_

#### Interpretation Notes
- Execution Monte Carlo uses month x session stress scenarios derived from Stage 04 tickfill artifacts.
- EM01-EM05 summarize mild/moderate survival, month negativity risk, fill-rate decay, and data integrity.

#### Action Trigger Summary
| symbol   | metric_id                    | band   | severity   | action_code   | action_summary                      | owner     |
|:---------|:-----------------------------|:-------|:-----------|:--------------|:------------------------------------|:----------|
| AUDUSD   | EM03_prob_negative_month_s1  | gray   | high       | A9_DATA_GAP   | metric not present in stage metrics | risk      |
| AUDUSD   | EM04_fill_rate_drop_vs_s0_s1 | gray   | high       | A9_DATA_GAP   | metric not present in stage metrics | execution |
| AUDUSD   | EM05_nan_core_fields         | gray   | high       | A9_DATA_GAP   | metric not present in stage metrics | data      |
| EURUSD   | EM03_prob_negative_month_s1  | gray   | high       | A9_DATA_GAP   | metric not present in stage metrics | risk      |
| EURUSD   | EM04_fill_rate_drop_vs_s0_s1 | gray   | high       | A9_DATA_GAP   | metric not present in stage metrics | execution |
| EURUSD   | EM05_nan_core_fields         | gray   | high       | A9_DATA_GAP   | metric not present in stage metrics | data      |
| GBPUSD   | EM03_prob_negative_month_s1  | gray   | high       | A9_DATA_GAP   | metric not present in stage metrics | risk      |
| GBPUSD   | EM04_fill_rate_drop_vs_s0_s1 | gray   | high       | A9_DATA_GAP   | metric not present in stage metrics | execution |
| GBPUSD   | EM05_nan_core_fields         | gray   | high       | A9_DATA_GAP   | metric not present in stage metrics | data      |
| USDCAD   | EM03_prob_negative_month_s1  | gray   | high       | A9_DATA_GAP   | metric not present in stage metrics | risk      |
| USDCAD   | EM04_fill_rate_drop_vs_s0_s1 | gray   | high       | A9_DATA_GAP   | metric not present in stage metrics | execution |
| USDCAD   | EM05_nan_core_fields         | gray   | high       | A9_DATA_GAP   | metric not present in stage metrics | data      |

#### Plots
![stage_11_mc_lb95_by_scenario](../figures/oco_bible/stage_11_mc_lb95_by_scenario.png)
![stage_11_mc_fill_vs_pnl](../figures/oco_bible/stage_11_mc_fill_vs_pnl.png)
<!-- GENERATED:STAGE_11:END -->
