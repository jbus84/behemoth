# Strategy Master Manual - Tick OCO Stop-Limit System

**Version**: 10.3
**Date**: February 28, 2026
**Status**: Active

This is the canonical manual for the active OCO research/governance system.
If any section conflicts with generated stage artifacts, the generated stage artifacts and contract checks win.

## 1. Strategy Definition

### 1.1 Core Trade Concept
- Build tick-velocity bars from raw ticks.
- Mine OCO opportunities parameterized by `barrier_pips` and `horizon`.
- Evaluate first-touch behavior and realized gross pip outcomes.
- Use monthly walk-forward filtering and rolling probability thresholding to keep only stable opportunities.
- Enforce stop-limit execution realism (tick overshoot caps, no-touch handling) before promotion.

### 1.2 Active Universe
- `EURUSD`, `GBPUSD`, `USDJPY`, `USDCHF`

### 1.3 What This System Is Not
- Not a mixed MOM/REV portfolio framework.
- Not an API-first live runtime; current source of truth is artifact-first pipeline governance.

## 2. Why This System Works (and When It Should Not Be Used)

### 2.1 Edge Mechanism (Why it works)
- The system starts with broad OCO hypothesis mining, then keeps only states that survive rolling selection and downstream governance gates.
- Edge concentration is not dominated by a tiny handful of states: Stage-2 `M01_top3_contrib_share` is low (about `0.04-0.05` across active symbols), which reduces single-pattern fragility.
- Positive expectancy density is high at the mining layer: Stage-2 `M03_positive_density=1` for `EURUSD`, `GBPUSD`, `USDJPY`, and `USDCHF`.
- Threshold slices show monotonic quality under stricter selection (for example, aggregate mean gross rises as quantile moves from `0.8` to `0.95`), consistent with a rankable signal rather than noise sorting.
- Evidence: `docs/analysis/oco_edge_clarity_report.md`, `docs/strategy_bible/generated/pipeline_snapshot.md`.

### 2.2 Temporal Robustness (Why this is not static-fit)
- Time ordering is enforced by monthly walk-forward evaluation and rolling-history threshold policy; decisions at time `t` use only data available by `t`.
- Threshold drift diagnostics remain in controlled ranges under current policy families:
  - `W13` fragility is moderate (about `0.42-0.60`),
  - `W14` brier drift is low (about `0.0026-0.0076`),
  - `W15` turnover remains low (about `0.005-0.018` in recommended configs).
- Stage 4 execution drift remains stable in latest month snapshots:
  - fill rates around `0.986-0.994`,
  - no-touch rate near `0`,
  - overshoot `p95` around `0.3-0.6` pips.
- Governance and contract controls remain clean at the current snapshot (`docs_contract` high/critical fails = `0`).
- Evidence: `docs/analysis/oco_threshold_sensitivity_report.md`, `docs/analysis/oco_execution_drift_report.md`, `docs/analysis/oco_docs_contract_report.md`.

### 2.3 Retail ECN Suitability (Qualified)
This system is suitable for retail FX traders using ECN-style execution only when these operating conditions hold:

- Broker and platform support stop-limit semantics aligned with Stage-4 modeling (trigger + bounded fill logic).
- Monthly realized `fill_rate` remains at or above `0.98`.
- Monthly realized `overshoot_p95_pips` remains at or below `0.6` pips (symbol-specific), and no-touch remains near policy limits.
- Effective spread/fee/slippage regime remains within monitored drift controls; red execution-drift breaches block promotion.
- End-to-end latency is low enough that observed overshoot/no-touch metrics stay within the same control bands.

This is not a universal profitability claim for all retail brokers or all market regimes. It is a conditional operational claim tied to current governed evidence.

### 2.4 Invalidation and Action Triggers
| Condition | Detection metric/artifact | Required action |
| --- | --- | --- |
| Execution tail degrades | `E_DRIFT_OVERSHOOT_P95` in `docs/analysis/oco_execution_drift_report.md` | Recalibrate cap/session policy and halt symbol promotion until green/acceptable amber posture |
| Selection fragility increases | `TS01_W13_THRESHOLD_FRAGILITY` in `docs/analysis/oco_threshold_sensitivity_report.md` | Re-run threshold policy sweep and refresh active policy lock |
| Governance lock drift | `G03_lock_drift_flags` in Stage-9 outputs / edge clarity report | Block deploy path, rebuild lock from latest valid artifacts |
| Robustness deterioration | Stage-8/11 LB95 stress metrics in `docs/analysis/oco_edge_clarity_report.md` | Freeze promotion and re-evaluate assumptions/cost model before resuming |

### 2.5 How to Interpret This Section
- Treat this section as a synthesis layer, not as standalone proof.
- Final authority remains governed artifacts and stage snapshots.
- If prose and artifacts conflict, follow artifact priority rules in Section 12.

## 3. Data and Label Contract

### 3.1 Inputs
- Raw tick source configured at runtime (not hard-coded in docs).
- Tick-velocity bar artifacts in `data/analysis/tick_velocity/`.
- Stage outputs in `data/analysis/tick_opportunity_mining/`.
- Builders used to produce these artifacts:
- `scripts/build_global_tick_bars.py` (raw ticks -> `data/global_tickbars/*_Ntick.parquet`)
- `scripts/build_tick_velocity_dataset.py` (`data/global_tickbars` -> `data/analysis/tick_velocity/*_tick_velocity.parquet`)

### 3.2 Event Semantics
- Entry trigger: first barrier touch in forward window.
- If no touch within horizon: event is non-filled/no-touch under execution semantics.
- Post-touch outcome: fixed-horizon gross pip move from touch context, evaluated causally.

### 3.3 Execution Realism
- Entry style: stop-limit, not naive market fill.
- Overshoot tracked in pips at tick-level.
- Cap policy controls acceptable overshoot and effective fills.

## 4. Stage Architecture

The production research process is a stage-gated chain:
1. Stage 01: data foundation + reliability checks.
2. Stage 02: opportunity mining.
3. Stage 03: monthly walk-forward selection + thresholding.
4. Stage 04: stop-limit execution realism and cap policy.
5. Stage 05: reduced-core selection.
6. Stage 06: tick-exact verification + portability.
7. Stage 07: logical/statistical audit.
8. Stage 08: robustness and stress tests.
9. Stage 09: governance lock + deploy eligibility.
10. Stage 10: known risks + backlog controls.
11. Stage 11: execution Monte Carlo degradation analysis.

Generated status is published in `docs/strategy_bible/generated/pipeline_snapshot.md`.

## 5. Causality and Leakage Controls

### 5.1 Time Ordering Rules
- Training windows are strictly prior to test windows.
- Threshold and policy selection are train-only or rolling-history-only for the decision timestamp.
- No future rows are used to decide current event selection.

### 5.2 Selection Discipline
- Candidate mining is hypothesis generation only.
- Promotion relies on downstream WFO, execution realism, and robustness gates.
- Contract checks reject stale, missing, or inconsistent artifacts.

### 5.3 Governance Controls
- Active non-green alerts require explicit disposition and owner.
- Expired exceptions and recurrence breaches are governed by policy and fail contracts when configured.

## 6. Rolling WFO Logic

### 6.1 Selection Mechanics
- Generate model probabilities for candidate events.
- Compute threshold using rolling history policy (current standard: 20-day lookback family in policy set).
- Select events above threshold for each decision period.

### 6.2 Why Rolling Thresholds
- Avoid static threshold drift.
- Keep selection calibrated to recent distribution shift.
- Reduce dependence on any single backtest-era probability scale.

### 6.3 Robustness Tracking
- Monthly positive-rate and LB95 metrics are tracked per symbol.
- Threshold sensitivity metrics (`W13`, `W14`, `W15`) monitor fragility/drift.

### 6.4 CatBoost Selection Model (Stage 3)
- Model type: `CatBoostClassifier` with `Logloss` objective and `AUC` eval metric.
- Target: `target_gross_pos` (binary sign of gross pip outcome).
- Core features: cost/range/return z-score/velocity/spread/tick-rate/hour/path features plus structure fields (`bar_ticks`, `horizon`, `barrier_pips`).
- Train/test rule: strict rolling month order (`rolling_train_months` train -> next month test).
- Model validity policy: **one-month validity** (predictions are valid only for the scored test month).
- Retrain cadence policy: **monthly retrain** at each new test month boundary.
- Staleness rule: if latest Stage-3 prediction month is older than current test month, deployment decisions are blocked.
- Candidate filtering is train-window only:
- `train_rows >= min_candidate_rows_in_train_window`
- `train_mean_gross > 0`
- Selection output is probability-threshold based:
- monthly quantile sweep and execution quantile (`q=0.9` default)
- threshold modes: `rolling_days` (causal day-by-day) or `train_quantile`
- Stage interaction: Stage 5 reduced-core filtering consumes Stage 3 `selected_exec`/`pred_prob` outputs and applies additional state-level gates.
- Key leakage control:
- no test-month row can influence that month’s fit or threshold at decision time.
- Full technical specification is maintained in `docs/strategy_bible/stage_03_monthly_wfo.md`.

### 6.5 Latest Reduced-Core Expected Gross (Per Trade)
Latest reduced-core `status=ok` row per symbol:
- execution policy context: rolling threshold policy (`q=0.9`) with reduced-core filtering
- latest completed train window in current governed artifacts: `2025-09` to `2025-11` (September 1, 2025 to November 30, 2025)
- latest evaluated month in current governed artifacts: `2025-12` (December 2025)

Expected gross pips/trade proxy below is taken from reduced-core monthly outputs (latest `ok` month by symbol).

| Pair | Test month | Training months | Expected gross pips/trade | Selected rows | Source |
| --- | --- | --- | ---:| ---:| --- |
| EURUSD | 2025-12 | 2025-09,2025-10,2025-11 | 1.061547 | 892 | `data/analysis/tick_opportunity_mining/reduced_core_rolling/EURUSD_oco_reduced_monthly.csv` |
| GBPUSD | 2025-12 | 2025-09,2025-10,2025-11 | n/a (`status != ok`) | 0 | `data/analysis/tick_opportunity_mining/reduced_core_rolling_gbpusd/GBPUSD_oco_reduced_monthly.csv` |
| USDJPY | 2025-12 | 2025-09,2025-10,2025-11 | n/a (`status != ok`) | 0 | `data/analysis/tick_opportunity_mining/reduced_core_rolling_usdjpy/USDJPY_oco_reduced_monthly.csv` |
| USDCHF | 2025-12 | 2025-09,2025-10,2025-11 | 0.723562 | 365 | `data/analysis/tick_opportunity_mining/reduced_core_rolling_usdchf/USDCHF_oco_reduced_monthly.csv` |

Interpretation note:
- these are cycle-level expectancy estimates under the current selection policy, not guaranteed live outcomes;
- execution-drift and governance gates (Sections 7-13) must still pass for deploy suitability.

## 7. Execution Semantics (Stop-Limit)

### 7.1 Why Stop-Limit
- Pure market entries can overpay through overshoot.
- Pure limits can miss directional breakout-style touches.
- Stop-limit balances trigger certainty with bounded adverse fill.

### 7.2 Cap Definition
- `cap_pips` is the maximum allowed overshoot from barrier price to accepted fill.
- If overshoot exceeds cap, treat as non-fill under capped scenario.

### 7.3 Key Stage-04 Outputs
- Drift report: `docs/analysis/oco_execution_drift_report.md`
- Tickfill detail/cap sweeps in `data/analysis/tick_opportunity_mining/`.

## 8. Current Acceptance Gates

A symbol is release-eligible only when governed gates pass (representative):
- Reduced-core monthly LB95 and capacity gates.
- Tick-exact consistency gates.
- Robustness LB95 and month-stability gates.
- Stage integrity + docs contract high/critical failures equal zero.

See:
- `docs/analysis/oco_stage_integrity_report.md`
- `docs/analysis/oco_docs_contract_report.md`
- `docs/analysis/oco_edge_clarity_report.md`

## 9. Core Scripts

### 9.1 Strategy Pipeline
- `scripts/run_tick_opportunity_mining.py`
- `scripts/run_tick_opportunity_monthly_wfo.py`
- `scripts/select_oco_reduced_core.py`
- `scripts/select_oco_reduced_core_rolling.py`
- `scripts/verify_oco_tick_exact_shortlist.py`
- `scripts/analyze_oco_monthly_wfo_robustness.py`
- `scripts/analyze_oco_stop_limit_tickfill.py`
- `scripts/simulate_api_e2e_replay.py` (E2E Replay Parity Check)

### 9.2 Governance and Docs
- `scripts/build_oco_strategy_bible.py`
- `scripts/build_oco_system_reference_docs.py`
- `scripts/check_oco_docs_stage_integrity.py`
- `scripts/validate_oco_docs_contract.py`
- `scripts/build_oco_execution_drift_report.py`
- `scripts/build_oco_threshold_sensitivity_report.py`
- `scripts/remediate_oco_monitoring_alerts.py`
- `scripts/build_oco_governance_explainability_report.py`
- `scripts/build_operator_action_report.py`
- `scripts/validate_oco_rule_universe_registry.py`

## 10. Standard Reproduction

Run from repo root:

```bash
make docs-contract-ci
uv run mkdocs build
```

## 11. Operator Workflow

Daily/weekly/monthly actions are defined in:
- `docs/strategy_bible/operator_runbook.md`
- `docs/strategy_bible/operator_playbook.md`

The minimum operational cycle is:
1. Refresh governed artifacts.
2. Resolve non-green alerts/dispositions.
3. Re-check stage and docs contracts.
4. Rebuild docs and review stage snapshots.

## 12. Artifact Priority Rules

When documents disagree, use this priority:
1. `data/analysis/tick_opportunity_mining/*` governed CSV artifacts
2. `docs/strategy_bible/generated/*` snapshots
3. `docs/analysis/*` governed reports
4. this manual (`docs/STRATEGY_MASTER_MANUAL.md`)

## 13. Change Control

Any change to strategy logic, threshold policy, execution semantics, or gate definitions requires:
1. regenerated stage artifacts,
2. regenerated governance reports,
3. passing docs contract checks,
4. updated manual and impacted stage specs.
