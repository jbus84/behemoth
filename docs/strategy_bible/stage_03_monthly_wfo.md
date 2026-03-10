# Stage 3 - Monthly Walk-Forward Modeling

## Objective
Evaluate model filtering with strict monthly walk-forward ordering and quantify threshold robustness.

## Inputs
- WFO metrics:
- `data/analysis/tick_opportunity_mining/wfo_*/<SYMBOL>_monthly_metrics_all.csv`
- WFO thresholds:
- `data/analysis/tick_opportunity_mining/wfo_*/<SYMBOL>_monthly_thresholds_all.csv`
- WFO predictions:
- `data/analysis/tick_opportunity_mining/wfo_*/<SYMBOL>_monthly_predictions_all.parquet`

## Process
- Train on prior months only and score next month.
- Apply execution quantile filter (`q`, default 0.9).
- Compute threshold/calibration/turnover diagnostics (`W13-W15`).

## CatBoost Model Specification (Critical)

### Model Purpose
- Rank OCO event rows by conditional probability of positive gross outcome (`target_gross_pos=1`).
- Selection is then performed by thresholding this probability stream, not by direct regression on pip magnitude.

### Model Validity and Retrain Cadence
- **Validity window:** CatBoost predictions are valid for exactly one scored test month.
- **Policy term:** **one-month validity**.
- **Expiry rule:** At the first timestamp of a new calendar test month, prior-month predictions are stale for production decisions.
- **Retrain cadence:** retrain monthly using the latest rolling train window (`rolling_train_months`, default `3`).
- **Policy term:** **monthly retrain**.
- **Cross-year behavior:** in cross-year mode, history is prepended only to satisfy rolling warmup; validity is still one scored month at a time.

### Training Label
- Binary target: `target_gross_pos = 1` if `target_gross_pips > 0`, else `0`.
- `target_gross_pips` is the realized gross pip label generated from strict forward path logic in prior stages.

### Feature Vector (Current)
- `cost_est_pips`
- `range_pips`
- `ret1_pips`
- `ret_z`
- `ret_abs_z`
- `vel_cost_units_h1`
- `vel_abs_cost_units_h1`
- `spread_z`
- `tick_rate_z`
- `hour_utc`
- `hl_first`
- `hl_first_mean_24`
- `hl_pos_frac_mean_24`
- `bar_ticks`
- `horizon`
- `barrier_pips`

Source of truth: `scripts/run_tick_opportunity_monthly_wfo.py` (`_feature_cols`).

### CatBoost Hyperparameters (Current)
- `loss_function=Logloss`
- `eval_metric=AUC`
- `iterations=350`
- `learning_rate=0.05`
- `depth=6`
- `l2_leaf_reg=5.0`
- `random_seed=seed + month_index`
- `verbose=False`

Source of truth: `scripts/run_tick_opportunity_monthly_wfo.py` (`_wfo_monthly`).

### Monthly WFO Training Loop
1. Build month boundaries.
2. For each test month `M`, use prior `rolling_train_months` months as train window.
3. Candidate prefilter inside train window only:
- keep `candidate_uid` where `train_rows >= min_candidate_rows_in_train_window`
- and `train_mean_gross > 0`.
4. Apply same keep-set to test month rows.
5. Enforce minimum train/test row gates and class-balance gate (`target_gross_pos` has both classes).
6. Fit CatBoost on train rows and score test rows with `predict_proba(... )[:,1]`.
7. Persist per-row `pred_prob` and threshold-selection flags for downstream stages.

### Thresholding Logic
- Candidate quantiles are swept (default: `0.5,0.6,0.7,0.8,0.9,0.95`).
- `execution_quantile` (default `0.9`) is the live selection quantile.
- Two modes are supported:
- `train_quantile`: threshold from current train-month score distribution.
- `rolling_days`: threshold computed causally from a rolling history pool (`rolling_threshold_days`, `rolling_threshold_min_history`), including train history and already-seen prior test days only.
- If rolling history is insufficient, Stage 3 uses a strict **train-only fallback** quantile.
- It **never uses unseen same-month test pools** for fallback thresholding.
- If both rolling history and train history are unavailable, threshold source is `no_history` and rows are fail-closed (not selected).
- Output rows include execution-threshold fields used by Stage 5:
- `threshold_exec`
- `selected_exec`
- `threshold_mode`
- `threshold_days`
- `threshold_source`

### Supported Evaluation Windowing
- Legacy single-year mode via `eval_year`.
- Cross-year causal window via:
- `eval_start_month`
- `eval_end_month`
- When cross-year mode is used, the engine prepends exactly `rolling_train_months` months of history before `eval_start_month` to preserve train warmup without leakage.

### Stage-3 Output Metrics
- Classifier diagnostics:
- AUC
- Brier score
- Selection diagnostics:
- Coverage at each quantile
- Mean/median gross pips for selected rows
- W13/W14/W15 stability metrics

### Prediction Output Schema (Per Row)
| Column | Type | Meaning | Downstream use |
| --- | --- | --- | --- |
| `close_ts` | timestamp (UTC) | Event decision timestamp | Join key for execution realism and audits |
| `candidate_uid` | string | Unique candidate/state identifier | Join key for reduced-core state filtering |
| `pred_prob` | float | CatBoost probability for `target_gross_pos=1` | Ranking signal for thresholding |
| `target_gross_pips` | float | Realized gross pip label | Outcome metrics and diagnostics |
| `target_gross_pos` | int (0/1) | Binary sign label | AUC/Brier and classification diagnostics |
| `threshold_mode` | string | `rolling_days` or `train_quantile` | Provenance of threshold generation |
| `threshold_days` | int | Rolling lookback days if `rolling_days`, else `0` | Traceability of threshold policy |
| `threshold_source` | string | `rolling_history`, `train_fallback`, `train_quantile`, or `no_history` | Causal provenance audit for threshold assignment |
| `threshold_exec` | float | Applied execution threshold for `execution_quantile` | Defines selected decision boundary |
| `selected_exec` | int (0/1) | Whether row passed `threshold_exec` | Default Stage-5 entry set (`selection_mode=auto/exec_flag`) |

### Metric Definitions (Exact)
- `AUC`: ROC area for classifying `target_gross_pos`; threshold-independent ranking quality.
- `Brier`: mean squared probability error, `mean((pred_prob - target_gross_pos)^2)`; lower is better.
- `Coverage@q`: `selected_rows / total_rows` for quantile `q`.
- `Mean/Median gross@q`: mean/median of `target_gross_pips` on rows selected at quantile `q`.
- `W13_threshold_fragility`:
- Around execution `q`, aggregate mean gross by quantile and compute slope:
- `(max(mean_gross_near_q)-min(mean_gross_near_q)) / (max(q_near)-min(q_near))`
- `W14_brier_drift_std = std(monthly_brier)`
- `W15_selection_turnover = 1 - mean(Jaccard(selected_uid_month_t, selected_uid_month_t-1))`

### Operating Bands (Policy Reference)
These are operator bands for interpretation and escalation alignment. Stage hard-gate authority remains governance checks.

| Metric | Green | Amber | Red | Direction | Primary action |
| --- | --- | --- | --- | --- | --- |
| `W13_threshold_fragility` | `< 2.5` | `>= 2.5 and < 4.0` | `>= 4.0` | lower is better | recalibrate threshold policy |
| `W14_brier_drift_std` | `< 0.01` | `>= 0.01 and < 0.02` | `>= 0.02` | lower is better | review calibration drift |
| `W15_selection_turnover` | `< 0.25` | `>= 0.25 and < 0.40` | `>= 0.40` | lower is better | investigate selection instability |
| `AUC` | `>= 0.55` | `>= 0.52 and < 0.55` | `< 0.52` | higher is better | review feature/regime fit |
| `Brier` | `<= 0.245` | `> 0.245 and <= 0.255` | `> 0.255` | lower is better | review probability calibration |
| `Coverage@q=0.9` | `0.08-0.12` | `0.05-0.08 or 0.12-0.15` | `< 0.05 or > 0.15` | center-stable | inspect threshold drift |

Band notes:
- `W13/W14/W15` thresholds align to `configs/research/docs/operator_action_rules.yaml`.
- `AUC/Brier/Coverage` are operational reference bands (not standalone hard deploy gates).

### Explicit Leakage Controls
- No row from month `M` is used in model fitting for month `M`.
- Candidate keep-set is derived from train-window aggregates only.
- Rolling threshold in `rolling_days` mode uses only:
- train rows before test month day `D`
- test rows from days strictly before `D`
- Never future-in-test.
- Fallback policy is strict: if rolling history is short, use train-only fallback; if train history is absent, mark `threshold_source=no_history` and do not select.

### Known Model Limits
- `pred_prob` is a ranking score, not a calibrated expected-pips estimator.
- Hyperparameters are static; no monthly hyperparameter re-optimization is currently performed.
- Feature importances and calibration curves are not yet part of mandatory Stage-3 outputs.

### Interaction with Reduced-Core Selection (Stage 5)
- Stage 3 contributes model-layer filtering only (`selected_exec` from `pred_prob` vs `threshold_exec`).
- Stage 5 contributes state-layer reduced-core filtering (`core_spec_match`) plus execution feasibility.
- Final tradable rows are the strict intersection of these gates, not a Stage-3-only pass.
- Reference: `docs/strategy_bible/stage_05_reduced_core.md` section `CatBoost x Core Spec Interaction`.

## Exact Calculations
- Metric formulas and units are defined in `Metric Definitions (Exact)` above.
- Computation is performed on strict out-of-sample month slices produced by the monthly WFO loop.

## Causality / Leakage Controls
- Strict 3M train -> 1M test ordering.
- Selection thresholding uses historical window only (rolling causal threshold).

## Failure Modes
- Threshold fragility: tiny `q` change causes large performance change.
- Calibration drift over months.
- High turnover suggesting unstable signal identity.

## Interpretation Guide
- Lower `W13` is less fragile.
- Lower `W14` indicates more stable calibration.
- Lower `W15` indicates higher month-to-month continuity.

## Validation Gates
- WFO gating and leakage contract checks are hard gates.
- `W13-W15` remain informational until promoted.

## Canonical Analysis Reports
- `docs/analysis/eurusd_tick_opportunity_monthly_wfo_oco_fullcap_report.md`
- `docs/analysis/gbpusd_tick_opportunity_monthly_wfo_oco_fullcap_report.md`
- `docs/analysis/usdjpy_tick_opportunity_monthly_wfo_oco_fullcap_report.md`
- `docs/analysis/oco_threshold_sensitivity_report.md`

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
uv run python scripts/run_tick_opportunity_monthly_wfo.py \
  --config configs/research/experiments/eurusd_tick_opportunity_monthly_wfo_oco_fullcap_2025.yaml
uv run python scripts/build_oco_threshold_sensitivity_report.py
```

## Traceability
- `scripts/run_tick_opportunity_monthly_wfo.py`
- `scripts/build_oco_threshold_sensitivity_report.py`
- `docs/analysis/*_tick_opportunity_monthly_wfo_oco_*_report.md`
- `docs/strategy_bible/generated/stage_03_snapshot.md`

## Generated Run Snapshot
<!-- GENERATED:STAGE_03:START -->
### Auto Snapshot - Stage 03

- generated_at: `2026-03-10 10:13:11 UTC`
- Execution threshold summary is aligned to quantile=0.9.
- Metrics are strictly month-forward (3M train -> 1M test).
- W13-W15 are informational diagnostics for threshold fragility, calibration drift, and selection turnover.

#### Key Results
| symbol   |   months |   auc_mean |   brier_mean |   test_rows_total |   w13_threshold_fragility |   w14_brier_drift_std |   w15_selection_turnover |
|:---------|---------:|-----------:|-------------:|------------------:|--------------------------:|----------------------:|-------------------------:|
| EURUSD   |       14 |   0.521779 |     0.249732 |       3.79276e+06 |                  4.30025  |           0.00132205  |                0.130227  |
| GBPUSD   |       14 |   0.523117 |     0.249639 |       4.59833e+06 |                  1.43409  |           0.000769545 |                0.0738935 |
| AUDUSD   |       14 |   0.522254 |     0.251136 |       4.18266e+06 |                  0.572776 |           0.000946094 |                0.162401  |
| USDJPY   |       14 |   0.526009 |     0.247588 |       4.81562e+06 |                  1.94653  |           0.000700228 |                0.0452724 |
| USDCHF   |       14 |   0.530064 |     0.250296 |       3.95814e+06 |                  1.48074  |           0.00159589  |                0.199366  |
| USDCAD   |       14 |   0.537569 |     0.249334 |       4.44682e+06 |                  1.97218  |           0.0037627   |                0.174985  |

#### Interpretation Notes
- Execution threshold summary is aligned to quantile=0.9.
- Metrics are strictly month-forward (3M train -> 1M test).
- W13-W15 are informational diagnostics for threshold fragility, calibration drift, and selection turnover.

#### Action Trigger Summary
| symbol   | metric_id               | band   | severity   | action_code           | action_summary         | owner    |
|:---------|:------------------------|:-------|:-----------|:----------------------|:-----------------------|:---------|
| AUDUSD   | W13_threshold_fragility | green  | info       | A0_MONITOR            | within policy band     | research |
| AUDUSD   | W14_brier_drift_std     | green  | info       | A0_MONITOR            | within policy band     | research |
| AUDUSD   | W15_selection_turnover  | green  | info       | A0_MONITOR            | within policy band     | research |
| EURUSD   | W13_threshold_fragility | red    | high       | A3_HALT_AND_REMEDIATE | escalate and remediate | research |
| EURUSD   | W14_brier_drift_std     | green  | info       | A0_MONITOR            | within policy band     | research |
| EURUSD   | W15_selection_turnover  | green  | info       | A0_MONITOR            | within policy band     | research |
| GBPUSD   | W13_threshold_fragility | green  | info       | A0_MONITOR            | within policy band     | research |
| GBPUSD   | W14_brier_drift_std     | green  | info       | A0_MONITOR            | within policy band     | research |
| GBPUSD   | W15_selection_turnover  | green  | info       | A0_MONITOR            | within policy band     | research |
| USDCAD   | W13_threshold_fragility | amber  | medium     | A2_RECALIBRATE        | review and monitor     | research |
| USDCAD   | W14_brier_drift_std     | green  | info       | A0_MONITOR            | within policy band     | research |
| USDCAD   | W15_selection_turnover  | green  | info       | A0_MONITOR            | within policy band     | research |

#### Details
| symbol   |   months |   mean_coverage |   mean_gross_pips |   rows_selected |
|:---------|---------:|----------------:|------------------:|----------------:|
| AUDUSD   |       14 |       0.0897709 |          0.449535 |          415660 |
| EURUSD   |       14 |       0.0962194 |          1.46115  |          431387 |
| GBPUSD   |       14 |       0.0897346 |          0.96337  |          425220 |
| USDCAD   |       14 |       0.0893935 |          0.824392 |          490796 |
| USDCHF   |       14 |       0.0843316 |          0.599204 |          348850 |
| USDJPY   |       14 |       0.0977184 |          1.37202  |          463768 |

#### Plots
![stage_03_wfo_monthly_gross](../figures/oco_bible/stage_03_wfo_monthly_gross.png)

#### Threshold Robustness Around Execution Quantile
| symbol   | test_month   |   quantile |   mean_gross_pips |   coverage |   selected_rows |
|:---------|:-------------|-----------:|------------------:|-----------:|----------------:|
| EURUSD   | aggregate    |       0.8  |          1.15137  |  0.191809  |         57851.1 |
| EURUSD   | aggregate    |       0.9  |          1.46115  |  0.0962194 |         30813.4 |
| EURUSD   | aggregate    |       0.95 |          1.79641  |  0.0474474 |         15976.1 |
| GBPUSD   | aggregate    |       0.8  |          0.848037 |  0.185145  |         61979.6 |
| GBPUSD   | aggregate    |       0.9  |          0.96337  |  0.0897346 |         30372.9 |
| GBPUSD   | aggregate    |       0.95 |          1.06315  |  0.0418456 |         14327.1 |
| AUDUSD   | aggregate    |       0.8  |          0.41137  |  0.192869  |         60849.6 |
| AUDUSD   | aggregate    |       0.9  |          0.449535 |  0.0897709 |         29690   |
| AUDUSD   | aggregate    |       0.95 |          0.497286 |  0.0394586 |         14047.1 |
| USDJPY   | aggregate    |       0.8  |          1.20166  |  0.196789  |         66914.2 |
| USDJPY   | aggregate    |       0.9  |          1.37202  |  0.0977184 |         33126.3 |
| USDJPY   | aggregate    |       0.95 |          1.49364  |  0.0485493 |         16319.5 |
| USDCHF   | aggregate    |       0.8  |          0.522041 |  0.177115  |         51441.7 |
| USDCHF   | aggregate    |       0.9  |          0.599204 |  0.0843316 |         24917.9 |
| USDCHF   | aggregate    |       0.95 |          0.744152 |  0.0387301 |         11500.4 |
| USDCAD   | aggregate    |       0.8  |          0.680782 |  0.187831  |         67802.1 |
| USDCAD   | aggregate    |       0.9  |          0.824392 |  0.0893935 |         35056.9 |
| USDCAD   | aggregate    |       0.95 |          0.976609 |  0.0412976 |         17635.4 |

#### Overfitting Diagnostics (Exec Quantile)
| symbol   |   quantile |   rows |   months |   positive_months |   lb95_trade_mean_gross_pips |   lb95_trade_mean_gross_pips_iid |   lb95_trade_mean_gross_pips_month_block |   pvalue_month_mean_gt0 |   pvalue_bonferroni |   pvalue_fdr_bh |   uplift_vs_null_pips |   pvalue_perm_uplift |   pvalue_perm_fdr_bh | majority_positive_months   | bonferroni_pass_10pct   | fdr_pass_10pct   | perm_fdr_pass_10pct   |
|:---------|-----------:|-------:|---------:|------------------:|-----------------------------:|---------------------------------:|-----------------------------------------:|------------------------:|--------------------:|----------------:|----------------------:|---------------------:|---------------------:|:---------------------------|:------------------------|:-----------------|:----------------------|
| AUDUSD   |        0.9 |   7789 |       11 |                11 |                      1.59632 |                          1.59632 |                                  1.18207 |             0           |         0           |     0           |                   nan |                  nan |                  nan | True                       | True                    | True             | False                 |
| EURUSD   |        0.9 |   5934 |       10 |                10 |                      2.72549 |                          2.72549 |                                  1.82044 |             1.88738e-15 |         1.13243e-14 |     5.66214e-15 |                   nan |                  nan |                  nan | True                       | True                    | True             | False                 |
| GBPUSD   |        0.9 |  12161 |       11 |                11 |                      2.69625 |                          2.69625 |                                  2.50797 |             0           |         0           |     0           |                   nan |                  nan |                  nan | True                       | True                    | True             | False                 |
| USDCAD   |        0.9 |   7809 |       11 |                11 |                      2.21911 |                          2.21911 |                                  1.29081 |             8.88178e-16 |         5.32907e-15 |     5.32907e-15 |                   nan |                  nan |                  nan | True                       | True                    | True             | False                 |
| USDCHF   |        0.9 |  10408 |       11 |                11 |                      2.07321 |                          2.07321 |                                  1.28667 |             4.32987e-14 |         2.59792e-13 |     2.59792e-13 |                   nan |                  nan |                  nan | True                       | True                    | True             | False                 |
| USDJPY   |        0.9 |  13266 |       11 |                11 |                      3.79579 |                          3.79579 |                                  3.40256 |             0           |         0           |     0           |                   nan |                  nan |                  nan | True                       | True                    | True             | False                 |

- Interpretation: these diagnostics are computed on WFO out-of-sample predictions only.
- `bonferroni_pass_10pct` and `fdr_pass_10pct` summarize multiplicity-adjusted significance at alpha=0.10.

#### Leakage/Label Integrity (WFO Focus)
| symbol   |   checks_total |   checks_failed |   high_critical_failed |
|:---------|---------------:|----------------:|-----------------------:|
| EURUSD   |              6 |               0 |                      0 |
| GBPUSD   |              6 |               0 |                      0 |
| AUDUSD   |              6 |               0 |                      0 |
| USDJPY   |              6 |               0 |                      0 |
| USDCHF   |              6 |               0 |                      0 |
| USDCAD   |              6 |               0 |                      0 |
<!-- GENERATED:STAGE_03:END -->
