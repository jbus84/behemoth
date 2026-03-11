# Stage 4 - Execution Realism (Stop-Limit)

## Objective
Convert bar-level OCO outcomes to tick-aware stop-limit realism and quantify execution-driven EV erosion.

## Inputs
- Tickfill detail:
`data/analysis/tick_opportunity_mining/stop_limit_tickfill_fullcap/<SYMBOL>_stop_limit_tickfill_detail.csv`
- Cap sweep:
`data/analysis/tick_opportunity_mining/stop_limit_tickfill_fullcap/<SYMBOL>_stop_limit_tickfill_caps.csv`
- Summary:
`data/analysis/tick_opportunity_mining/stop_limit_tickfill_fullcap/summary.csv`
- Stage 04 policy output:
`data/analysis/tick_opportunity_mining/stage04_execution_policy_status.csv`
- Stage 04 session cap policy output:
`data/analysis/tick_opportunity_mining/stage04_cap_policy_by_session.csv`

## Process
- Reconstruct first-touch execution with tick-first crossing.
- Apply stop-limit cap sweep and classify execution-policy bands.
- Quantify cap robustness and overshoot/session dispersion diagnostics (`E11-E13`).
- Build causal rolling session caps before session-dispersion diagnostics.

## Exact Calculations
- session cap at event `t`: `q0.90(overshoot)` over `[t-20d, t)` with `min_periods=200`
- cap fallback chain: session cap -> global cap -> static symbol q0.90 fallback
- `overshoot_capped = min(overshoot_tick_pips, cap_applied_pips)`
- `E11_session_overshoot_dispersion = std(mean_overshoot_capped_by_session) / mean(mean_overshoot_capped_by_session)`
- `E12_cap_plateau_width_pips`:
- width of cap interval where per-signal performance >= 95% of best
- `E13_nonfill_opportunity_cost_pips`:
- `(mean_per_signal_no_extra_slip - mean_per_signal_full_overshoot) * fill_rate` at best cap
- `erosion_spread_fee_plus_slip = base_mean_gross_pips - best_cap_mean_per_signal_full_overshoot`

### Execution Contract Semantics (Stop-Limit)
- A touch event is rebuilt from candidate metadata (`bar_ticks`, `horizon`, `barrier_pips`, `side`) and bar-level first-touch logic.
- For each touch bar, the first tick crossing the barrier is found inside `[touch_open_ts, touch_close_ts]`.
- Overshoot is measured in pips from barrier to first crossing tick:
- Buy side: `overshoot = (first_tick_px - barrier_px) / pip`
- Sell side: `overshoot = (barrier_px - first_tick_px) / pip`
- Cap (`cap_pips`) means maximum allowed overshoot for fill acceptance:
- Fill if `touch_found_tick == 1` and `overshoot_tick_pips <= cap_pips`
- No fill otherwise

### Why Stop-Limit (vs Market / Passive Limit)
- Market-at-touch captures almost all triggers but pays worst overshoot tails during bursty ticks.
- Passive limit can avoid overshoot but misses momentum breaks when price does not retrace.
- Stop-limit is the controllable middle ground: trigger on break, but reject fills with excessive overshoot.

### What a Cap Is
- `cap_pips` is the maximum entry slippage tolerance after trigger.
- Smaller caps improve realized entry quality but reduce fill rate.
- Larger caps increase fill rate but admit more adverse overshoot.
- Stage 04 policy chooses and monitors this trade-off explicitly.

### Stage 04 Policy Bands and Actions
- Metrics and directions:
- `E11_session_overshoot_dispersion` lower is better
- `E12_cap_plateau_width_pips` higher is better
- `E13_nonfill_opportunity_cost_pips` lower is better
- `erosion_spread_fee_plus_slip` lower is better
- `tick_overshoot_p95_pips` lower is better
- Bands:
- `green`: within stable operating region
- `amber`: degraded but tradable with mitigation
- `red`: unsafe; halt/recalibrate before relying on results
- Action codes:
- `A0_MONITOR`: continue, no parameter change
- `A1_RECALIBRATE_CAP`: rerun cap sweep and reselect cap
- `A2_SESSION_GUARD`: add session-specific safeguards/filters
- `A3_HALT_RECALIBRATE`: pause deployment and revalidate
- `A9_DATA_GAP`: missing diagnostics; block until resolved

### Cap Recalibration Decision Tree
```mermaid
flowchart TD
  A[Latest Stage 04 metrics] --> B{Any metric red?}
  B -->|Yes| C[A3_HALT_RECALIBRATE]
  B -->|No| D{Any metric amber?}
  D -->|No| E[A0_MONITOR]
  D -->|Yes| F{Amber in E12/E13/erosion?}
  F -->|Yes| G[A1_RECALIBRATE_CAP]
  F -->|No| H[A2_SESSION_GUARD]
```

### Degradation Playbooks
- `A1_RECALIBRATE_CAP`:
- Recompute cap sweep on most recent month and prior train window.
- Require stable `E12` plateau and non-negative per-signal expectancy at selected cap.
- `A2_SESSION_GUARD`:
- Identify worst overshoot UTC buckets and gate/scale entries in those sessions.
- Re-check `E11` after guard.
- `A3_HALT_RECALIBRATE`:
- Stop symbol for deployment.
- Re-run Stage 03 -> Stage 08 checks after recalibration.
- `A9_DATA_GAP`:
- Do not interpret Stage 04 pass/fail.
- Regenerate missing stop-limit detail/cap artifacts and rerun docs-contract checks.

### Worked Example
- If `E12` collapses from `0.7` to `0.2` pips while `E13` rises above `0.35`, cap robustness is unstable.
- Policy outcome should escalate to `A3_HALT_RECALIBRATE` because slippage sensitivity dominates expectancy.

## Causality / Leakage Controls
- Uses realized tick path around touch events only.
- No future month leakage in execution diagnostics.

## Failure Modes
- Overshoot tail thickening in specific sessions.
- Performance dependent on razor-thin cap choice.
- Unrealistic fill assumptions causing optimistic net.

## Interpretation Guide
- Lower `E11` indicates more uniform execution quality across sessions.
- Larger `E12` indicates more robust cap choice.
- Higher `E13` indicates more opportunity loss from realistic fill behavior.

## Validation Gates
- Hard execution gates live in `E01-E10` preflight audit.
- `E11-E13` are informational hardening diagnostics.
- Stage 04 policy status (`stage04_execution_policy_status.csv`) must map every required metric to band + action.

## Canonical Analysis Reports
- `docs/analysis/oco_execution_risk_prelive_report.md`
- `docs/analysis/oco_stop_limit_tickfill_fullcap_report.md`
- `docs/analysis/oco_execution_drift_report.md`
- `docs/strategy_bible/signal_lifecycle_reference.md`
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
uv run python scripts/analyze_oco_stop_limit_tickfill.py \
  --symbols EURUSD,GBPUSD,USDJPY,USDCHF,AUDUSD,USDCAD
uv run python scripts/build_oco_execution_drift_report.py

uv run python scripts/build_oco_strategy_bible.py \
  --manifest configs/research/docs/oco_bible_manifest.yaml --strict false
```

## Traceability
- `scripts/analyze_oco_stop_limit_tickfill.py`
- `scripts/build_oco_execution_drift_report.py`
- `docs/analysis/oco_stop_limit_tickfill_fullcap_report.md`
- `docs/strategy_bible/generated/stage_04_snapshot.md`

## Generated Run Snapshot
<!-- GENERATED:STAGE_04:START -->
### Auto Snapshot - Stage 04

- generated_at: `2026-03-11 21:50:05 UTC`
- Execution realism is applied with tick first-cross overshoot.
- Session-aware rolling caps are built causally (20D lookback, q=0.90) before E11 dispersion is measured.
- Cap curve highlights fill-rate versus signal-level expectancy.
- E11-E13 are informational execution diagnostics: session dispersion, plateau width, and non-fill opportunity cost.
- Policy status artifact: data/analysis/tick_opportunity_mining/stage04_execution_policy_status.csv
- Session cap artifact: data/analysis/tick_opportunity_mining/stage04_cap_policy_by_session.csv

#### Key Results
| symbol   |   rows |   touch_found_rate |   base_mean_gross_pips |   tick_overshoot_mean_pips |   tick_overshoot_p95_pips |   e11_session_overshoot_dispersion |   e12_cap_plateau_width_pips |   e13_nonfill_opportunity_cost_pips |
|:---------|-------:|-------------------:|-----------------------:|---------------------------:|--------------------------:|-----------------------------------:|-----------------------------:|------------------------------------:|
| EURUSD   | 490796 |           0.998384 |                1.07233 |                   0.208765 |                       0.8 |                           0.352335 |                          1.2 |                           0.120106  |
| GBPUSD   | 490796 |           0.998384 |                1.07233 |                   0.208765 |                       0.8 |                           0.535492 |                          1.2 |                           0.120789  |
| AUDUSD   | 490796 |           0.998384 |                1.07233 |                   0.208765 |                       0.8 |                           0.299421 |                          1.2 |                           0.0930029 |
| USDJPY   | 490796 |           0.998384 |                1.07233 |                   0.208765 |                       0.8 |                           0.201612 |                          1.2 |                           0.193773  |
| USDCHF   | 490796 |           0.998384 |                1.07233 |                   0.208765 |                       0.8 |                           0.818511 |                          1.2 |                           0.110504  |
| USDCAD   | 490796 |           0.998384 |                1.07233 |                   0.208765 |                       0.8 |                           0.458596 |                          0.8 |                           0.163799  |

#### Interpretation Notes
- Execution realism is applied with tick first-cross overshoot.
- Session-aware rolling caps are built causally (20D lookback, q=0.90) before E11 dispersion is measured.
- Cap curve highlights fill-rate versus signal-level expectancy.

#### Action Trigger Summary
| symbol   | metric_id                         | band   | severity   | action_code   | action_summary     | owner     |
|:---------|:----------------------------------|:-------|:-----------|:--------------|:-------------------|:----------|
| AUDUSD   | E11_session_overshoot_dispersion  | green  | info       | A0_MONITOR    | within policy band | execution |
| AUDUSD   | E12_cap_plateau_width_pips        | green  | info       | A0_MONITOR    | within policy band | execution |
| AUDUSD   | E13_nonfill_opportunity_cost_pips | green  | info       | A0_MONITOR    | within policy band | execution |
| EURUSD   | E11_session_overshoot_dispersion  | green  | info       | A0_MONITOR    | within policy band | execution |
| EURUSD   | E12_cap_plateau_width_pips        | green  | info       | A0_MONITOR    | within policy band | execution |
| EURUSD   | E13_nonfill_opportunity_cost_pips | green  | info       | A0_MONITOR    | within policy band | execution |
| GBPUSD   | E11_session_overshoot_dispersion  | green  | info       | A0_MONITOR    | within policy band | execution |
| GBPUSD   | E12_cap_plateau_width_pips        | green  | info       | A0_MONITOR    | within policy band | execution |
| GBPUSD   | E13_nonfill_opportunity_cost_pips | green  | info       | A0_MONITOR    | within policy band | execution |
| USDCAD   | E11_session_overshoot_dispersion  | green  | info       | A0_MONITOR    | within policy band | execution |
| USDCAD   | E12_cap_plateau_width_pips        | green  | info       | A0_MONITOR    | within policy band | execution |
| USDCAD   | E13_nonfill_opportunity_cost_pips | green  | info       | A0_MONITOR    | within policy band | execution |

#### Details
| symbol   |   cap_pips |   fill_rate |   mean_per_signal_full_overshoot |
|:---------|-----------:|------------:|---------------------------------:|
| AUDUSD   |        0.5 |    0.956491 |                         0.465553 |
| AUDUSD   |        0.8 |    0.974506 |                         0.47988  |
| AUDUSD   |        1   |    0.979712 |                         0.486285 |
| AUDUSD   |        1.2 |    0.981747 |                         0.489629 |
| AUDUSD   |        1.5 |    0.984574 |                         0.490827 |
| AUDUSD   |        2   |    0.986787 |                         0.492384 |
| EURUSD   |        0.5 |    0.938104 |                         1.1459   |
| EURUSD   |        0.8 |    0.971863 |                         1.21426  |
| EURUSD   |        1   |    0.983004 |                         1.23076  |
| EURUSD   |        1.2 |    0.987035 |                         1.24441  |
| EURUSD   |        1.5 |    0.990848 |                         1.25958  |
| EURUSD   |        2   |    0.994395 |                         1.26305  |
| GBPUSD   |        0.5 |    0.94663  |                         0.786967 |
| GBPUSD   |        0.8 |    0.978886 |                         0.82024  |
| GBPUSD   |        1   |    0.986181 |                         0.830194 |
| GBPUSD   |        1.2 |    0.9885   |                         0.832394 |
| GBPUSD   |        1.5 |    0.991524 |                         0.836307 |
| GBPUSD   |        2   |    0.993695 |                         0.838588 |
| USDCAD   |        0.5 |    0.892452 |                         0.709153 |
| USDCAD   |        0.8 |    0.945747 |                         0.772661 |
| USDCAD   |        1   |    0.964403 |                         0.799066 |
| USDCAD   |        1.2 |    0.972137 |                         0.817707 |
| USDCAD   |        1.5 |    0.979906 |                         0.844199 |
| USDCAD   |        2   |    0.987687 |                         0.850956 |
| USDCHF   |        0.5 |    0.943388 |                         0.600932 |
| USDCHF   |        0.8 |    0.965392 |                         0.622451 |
| USDCHF   |        1   |    0.972475 |                         0.622054 |
| USDCHF   |        1.2 |    0.975451 |                         0.625408 |
| USDCHF   |        1.5 |    0.981129 |                         0.632769 |
| USDCHF   |        2   |    0.984922 |                         0.633259 |
| USDJPY   |        0.5 |    0.908321 |                         1.04343  |
| USDJPY   |        0.8 |    0.955769 |                         1.10499  |
| USDJPY   |        1   |    0.97119  |                         1.12371  |
| USDJPY   |        1.2 |    0.976286 |                         1.12799  |
| USDJPY   |        1.5 |    0.983136 |                         1.1389   |
| USDJPY   |        2   |    0.987084 |                         1.14705  |

#### Plots
![stage_04_stop_limit_caps](../figures/oco_bible/stage_04_stop_limit_caps.png)
![stage_04_execution_policy_bands](../figures/oco_bible/stage_04_execution_policy_bands.png)

#### Execution Risk Pre-Live
| symbol   |   checks_total |   checks_failed |   high_critical_failed |   e02_min_month_fill_rate |   e03_tail_above_cap |   e10_lb95_month_signal_net |
|:---------|---------------:|----------------:|-----------------------:|--------------------------:|---------------------:|----------------------------:|
| EURUSD   |             10 |               0 |                      0 |                  0.982913 |           0.0120075  |                    1.01939  |
| GBPUSD   |             10 |               0 |                      0 |                  0.980556 |           0.00966105 |                    0.758192 |
| AUDUSD   |             10 |               0 |                      0 |                  0.967436 |           0.0100915  |                    0.235633 |
| USDJPY   |             10 |               0 |                      0 |                  0.96919  |           0.0186887  |                    1.04015  |
| USDCHF   |             10 |               0 |                      0 |                  0.940036 |           0.0250009  |                    0.257279 |
| USDCAD   |             10 |               0 |                      0 |                  0.930754 |           0.0253186  |                    0.526809 |

#### Policy Status
| symbol   |   metrics_total |   green_metric_count |   amber_metric_count |   red_metric_count | worst_band   | recommended_action_code   | recommended_action_summary                                 | red_metrics                  | amber_metrics                                        |
|:---------|----------------:|---------------------:|---------------------:|-------------------:|:-------------|:--------------------------|:-----------------------------------------------------------|:-----------------------------|:-----------------------------------------------------|
| AUDUSD   |               5 |                    3 |                    1 |                  1 | red          | A3_HALT_RECALIBRATE       | execution erosion too high; halt symbol until recalibrated | erosion_spread_fee_plus_slip | tick_overshoot_p95_pips                              |
| EURUSD   |               5 |                    4 |                    1 |                  0 | amber        | A2_SESSION_GUARD          | overshoot tail elevated; apply session guard and monitor   |                              | tick_overshoot_p95_pips                              |
| GBPUSD   |               5 |                    4 |                    1 |                  0 | amber        | A2_SESSION_GUARD          | overshoot tail elevated; apply session guard and monitor   |                              | tick_overshoot_p95_pips                              |
| USDCAD   |               5 |                    4 |                    1 |                  0 | amber        | A2_SESSION_GUARD          | overshoot tail elevated; apply session guard and monitor   |                              | tick_overshoot_p95_pips                              |
| USDCHF   |               5 |                    3 |                    2 |                  0 | amber        | A2_SESSION_GUARD          | overshoot tail elevated; apply session guard and monitor   |                              | erosion_spread_fee_plus_slip,tick_overshoot_p95_pips |
| USDJPY   |               5 |                    4 |                    1 |                  0 | amber        | A2_SESSION_GUARD          | overshoot tail elevated; apply session guard and monitor   |                              | tick_overshoot_p95_pips                              |

- policy_csv: `data/analysis/tick_opportunity_mining/stage04_execution_policy_status.csv`

#### Policy Metric Mapping (Detail)
| symbol   | metric_id                         |   metric_value | band   | action_code         | green_threshold   | amber_threshold   |
|:---------|:----------------------------------|---------------:|:-------|:--------------------|:------------------|:------------------|
| EURUSD   | E11_session_overshoot_dispersion  |      0.352335  | green  | A0_MONITOR          | <= 1.0000         | <= 1.3000         |
| EURUSD   | E12_cap_plateau_width_pips        |      1.2       | green  | A0_MONITOR          | >= 0.5000         | >= 0.3000         |
| EURUSD   | E13_nonfill_opportunity_cost_pips |      0.120106  | green  | A0_MONITOR          | <= 0.2000         | <= 0.3500         |
| EURUSD   | erosion_spread_fee_plus_slip      |     -0.190721  | green  | A0_MONITOR          | <= 0.3000         | <= 0.5000         |
| EURUSD   | tick_overshoot_p95_pips           |      0.8       | amber  | A2_SESSION_GUARD    | <= 0.7000         | <= 1.0000         |
| GBPUSD   | E11_session_overshoot_dispersion  |      0.535492  | green  | A0_MONITOR          | <= 1.0000         | <= 1.3000         |
| GBPUSD   | E12_cap_plateau_width_pips        |      1.2       | green  | A0_MONITOR          | >= 0.5000         | >= 0.3000         |
| GBPUSD   | E13_nonfill_opportunity_cost_pips |      0.120789  | green  | A0_MONITOR          | <= 0.2000         | <= 0.3500         |
| GBPUSD   | erosion_spread_fee_plus_slip      |      0.233744  | green  | A0_MONITOR          | <= 0.3000         | <= 0.5000         |
| GBPUSD   | tick_overshoot_p95_pips           |      0.8       | amber  | A2_SESSION_GUARD    | <= 0.7000         | <= 1.0000         |
| AUDUSD   | E11_session_overshoot_dispersion  |      0.299421  | green  | A0_MONITOR          | <= 1.0000         | <= 1.3000         |
| AUDUSD   | E12_cap_plateau_width_pips        |      1.2       | green  | A0_MONITOR          | >= 0.5000         | >= 0.3000         |
| AUDUSD   | E13_nonfill_opportunity_cost_pips |      0.0930029 | green  | A0_MONITOR          | <= 0.2000         | <= 0.3500         |
| AUDUSD   | erosion_spread_fee_plus_slip      |      0.579948  | red    | A3_HALT_RECALIBRATE | <= 0.3000         | <= 0.5000         |
| AUDUSD   | tick_overshoot_p95_pips           |      0.8       | amber  | A2_SESSION_GUARD    | <= 0.7000         | <= 1.0000         |
| USDJPY   | E11_session_overshoot_dispersion  |      0.201612  | green  | A0_MONITOR          | <= 1.0000         | <= 1.3000         |
| USDJPY   | E12_cap_plateau_width_pips        |      1.2       | green  | A0_MONITOR          | >= 0.5000         | >= 0.3000         |
| USDJPY   | E13_nonfill_opportunity_cost_pips |      0.193773  | green  | A0_MONITOR          | <= 0.2000         | <= 0.3500         |
| USDJPY   | erosion_spread_fee_plus_slip      |     -0.0747181 | green  | A0_MONITOR          | <= 0.3000         | <= 0.5000         |
| USDJPY   | tick_overshoot_p95_pips           |      0.8       | amber  | A2_SESSION_GUARD    | <= 0.7000         | <= 1.0000         |
| USDCHF   | E11_session_overshoot_dispersion  |      0.818511  | green  | A0_MONITOR          | <= 1.0000         | <= 1.3000         |
| USDCHF   | E12_cap_plateau_width_pips        |      1.2       | green  | A0_MONITOR          | >= 0.5000         | >= 0.3000         |
| USDCHF   | E13_nonfill_opportunity_cost_pips |      0.110504  | green  | A0_MONITOR          | <= 0.2000         | <= 0.3500         |
| USDCHF   | erosion_spread_fee_plus_slip      |      0.439073  | amber  | A1_RECALIBRATE_CAP  | <= 0.3000         | <= 0.5000         |
| USDCHF   | tick_overshoot_p95_pips           |      0.8       | amber  | A2_SESSION_GUARD    | <= 0.7000         | <= 1.0000         |
| USDCAD   | E11_session_overshoot_dispersion  |      0.458596  | green  | A0_MONITOR          | <= 1.0000         | <= 1.3000         |
| USDCAD   | E12_cap_plateau_width_pips        |      0.8       | green  | A0_MONITOR          | >= 0.5000         | >= 0.3000         |
| USDCAD   | E13_nonfill_opportunity_cost_pips |      0.163799  | green  | A0_MONITOR          | <= 0.2000         | <= 0.3500         |
| USDCAD   | erosion_spread_fee_plus_slip      |      0.221376  | green  | A0_MONITOR          | <= 0.3000         | <= 0.5000         |
| USDCAD   | tick_overshoot_p95_pips           |      0.8       | amber  | A2_SESSION_GUARD    | <= 0.7000         | <= 1.0000         |

#### Session Rolling Cap Policy
| symbol   | session_bucket   |   lookback_days |   cap_quantile |   cap_pips |   rows_used |   session_cap_rows |   global_cap_rows |   fallback_rows |
|:---------|:-----------------|----------------:|---------------:|-----------:|------------:|-------------------:|------------------:|----------------:|
| EURUSD   | ASIA             |              20 |            0.9 |        0.2 |      107209 |             107009 |                31 |             169 |
| EURUSD   | LATE             |              20 |            0.9 |        0.2 |       22275 |              21494 |               750 |              31 |
| EURUSD   | LONDON           |              20 |            0.9 |        0.2 |      104589 |             104389 |               200 |               0 |
| EURUSD   | NY               |              20 |            0.9 |        0.3 |      196314 |             196114 |               200 |               0 |
| GBPUSD   | ASIA             |              20 |            0.9 |        0.3 |       83267 |              83067 |                85 |             115 |
| GBPUSD   | LATE             |              20 |            0.9 |        0.2 |       13332 |              12792 |               537 |               3 |
| GBPUSD   | LONDON           |              20 |            0.9 |        0.4 |      154294 |             154094 |               118 |              82 |
| GBPUSD   | NY               |              20 |            0.9 |        0.3 |      173379 |             173179 |               200 |               0 |
| AUDUSD   | ASIA             |              20 |            0.9 |        0.2 |      159940 |             159740 |                47 |             153 |
| AUDUSD   | LATE             |              20 |            0.9 |        0.1 |       18982 |              17978 |               957 |              47 |
| AUDUSD   | LONDON           |              20 |            0.9 |        0.2 |       74290 |              74090 |               200 |               0 |
| AUDUSD   | NY               |              20 |            0.9 |        0.3 |      157903 |             157703 |               200 |               0 |
| USDJPY   | ASIA             |              20 |            0.9 |        0.5 |      242329 |             242129 |                21 |             179 |
| USDJPY   | LATE             |              20 |            0.9 |        0.4 |       30336 |              30136 |               179 |              21 |
| USDJPY   | LONDON           |              20 |            0.9 |        0.5 |       89015 |              88815 |               200 |               0 |
| USDJPY   | NY               |              20 |            0.9 |        0.7 |       98716 |              98516 |               200 |               0 |
| USDCHF   | ASIA             |              20 |            0.9 |        0.2 |       72296 |              72096 |                81 |             119 |
| USDCHF   | LATE             |              20 |            0.9 |        0.1 |       12696 |              11679 |               953 |              64 |
| USDCHF   | LONDON           |              20 |            0.9 |        0.2 |      107894 |             107694 |               183 |              17 |
| USDCHF   | NY               |              20 |            0.9 |        0.3 |      155012 |             154812 |               200 |               0 |
| USDCAD   | ASIA             |              20 |            0.9 |        0.2 |       99914 |              99714 |               195 |               5 |
| USDCAD   | LATE             |              20 |            0.9 |        0.3 |       19902 |              18699 |              1183 |              20 |
| USDCAD   | LONDON           |              20 |            0.9 |        0.3 |       87184 |              86984 |               104 |              96 |
| USDCAD   | NY               |              20 |            0.9 |        0.4 |      282718 |             282518 |               121 |              79 |
<!-- GENERATED:STAGE_04:END -->
