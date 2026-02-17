# Strategy Master Manual - Causal Mixed Portfolio (FX + Commodities ex-Oil)

**Version**: 9.2  
**Date**: February 15, 2026  
**Status**: Active

[!IMPORTANT]
This manual is the canonical runbook for the current causal mixed-strategy pipeline.
It documents exactly how to recreate:
- mixed MOM/REV results,
- exposure-focused strategy-family sweeps,
- report rollups and recommended top-2 outputs.

## Scope
- Universe: FX + commodities whitelist excluding oil-linked pairs
- Excluded pairs: `Gold/Oil`, `Oil/Silver`
- Included pair examples: `EUR/GBP`, `AUD/NZD`, `EUR/CHF`, `EUR/JPY`, `GBP/JPY`, `CHF/JPY`, `EUR/AUD`, `GBP/AUD`, `AUD/CAD`, `GBP/CAD`, `NZD/CAD`, `Gold/Silver`
- Timeframes: `m5`, `m15`, `m60` (`h1` source for `m60`)
- Strategy families:
- Baseline families: `MOM`, `REV` across each timeframe
- Exposure-focused stage-A families: `MOM_PERSIST`, `MOM_BURST`, `REV_EXHAUSTION`, `REV_QUICKFAIL`
- Mixed search space: all 8 combinations of `MOM/REV` over `m5/m15/m60`

## Causal Rules

### Exit Contract
Exit conditions are frozen at entry in the event builders/reports:
- `max_hold_bars`
- `entry_cross_zero_level`
- `entry_stop_win_level_abs_z`
- `entry_use_stop_win`

No future information is used to modify an already-open trade's exit contract.

### Guardrail Contract
Guardrail is strictly causal and pair-local:
1. Check pause at entry timestamp.
2. If pair is paused, block the new entry.
3. Update loss streak only when accepted trades exit.
4. Never cancel already-open accepted trades.

This prevents the prior Sharpe/DD inflation bug from retroactive trade cancellation.

## Pipeline Overview
1. Run mixed triple-barrier meta filter over all 8 baseline MOM/REV mixes.
2. Optionally run exposure-focused strategy-family sweep mixes.
3. Append mixed OOS variants into strategy report outputs.
4. Select top-2 promoted mixes (Sharpe or balanced exposure objective).
5. Materialize top-2-only mixed report slices.

Deep-dive model report:
- `docs/analysis/m5_mom_m15_momrev_m60_rev_hgbt_report.md`

## ML Model Spec (Meta Triple-Barrier Filter)
This section documents the exact ML design used by `scripts/meta_triple_barrier_mixed_dd.py`.

### Objective
- Estimate `P(bad_trade)` for short-horizon legs (`m5`, `m15`) and gate entries with a train-selected probability threshold.
- Keep long-horizon `m60` leg as a structural leg in portfolio evaluation.

### Labels (Train/Test Fold-Local)
- Labels are first-hit triple-barrier outcomes on short trades:
- `0`: profit barrier hit first.
- `1`: stop barrier hit first, or timeout-like close with negative terminal PnL.
- `-1`: neutral (neither barrier hit in allowed hold window).
- Barrier magnitudes are computed on train only, per timeframe, via quantiles:
- `pt_q` from positive train PnL distribution.
- `sl_q` from absolute negative train PnL distribution.

### Features
- Numeric:
- `abs_z`, `z_velocity`, `z_accel`
- `rolling_win_rate_10`, `rolling_avg_pnl_10`
- `max_hold_bars`, `entry_hour_utc`, `entry_dow_utc`
- Categorical (one-hot encoded):
- `pair`, `timeframe`, `side`, `active_leg`

### Model
- `HistGradientBoostingClassifier` with:
- `max_depth=4`
- `learning_rate=0.05`
- `max_iter=350`
- `min_samples_leaf=80`
- `random_state` fold-adjusted from base seed

### Calibration
- Enabled by default.
- Time-ordered split from train labeled rows:
- model-fit subset first, calibration subset last (`calibration_frac=0.20` by default).
- Default calibrator: `isotonic`.
- Alternate calibrator options: `platt`, `none`.
- Calibration quality artifacts are written to:
- `*_fold_calibration.csv`

### Threshold Selection (Train-Only)
- Grid over `P(bad_trade)` threshold (`--threshold-grid`).
- For each threshold, compute guarded train metrics and train MC stress metrics.
- Hard pass uses:
- annualized retention floor (`--retain-annualized-frac`)
- trade retention floor (`--min-trade-frac`)
- max daily DD cap (absolute and percent variants)
- MC p5 DD cap
- Rank score:
- `0.45 * norm(max_daily_dd_bps) + 0.35 * norm(sharpe) + 0.20 * norm(annualized_bps_calendar)`
- If no strict pass exists, fallback is best eligible score (`strict_caps_unmet` recorded).

### Causality Controls
- Walk-forward by calendar year with embargo (`--embargo-days`, default 5).
- Train window is strictly pre-test-year.
- Barrier parameters, calibrator fit, and threshold are selected from train data only.
- Pair filter uses train-only pair Sharpe (`--pair-sharpe-cutoff`).
- Guardrail does not retroactively cancel open trades.

### Mix Syntax
- Timeframe strategy specs support single or combined tokens:
- Single: `m15=MOM` or `m15=REV`
- Combined: `m15=MOM+REV`
- Canonical output mix IDs normalize combined tokens, for example:
- `m5=MOM,m15=MOM+REV,m60=REV` -> `m5_mom__m15_momrev__m60_rev`

## Reproduction Commands
Run from repo root.

### 1) Run all mixed combinations (authoritative)
```bash
python scripts/meta_triple_barrier_mixed_dd.py \
  --mixes all \
  --exclude-oil \
  --out-prefix meta_tb_mixed_no_oil_allmix
```

Primary outputs:
- `data/analysis/meta_tb_mixed_no_oil_allmix_summary.csv`
- `data/analysis/meta_tb_mixed_no_oil_allmix_folds.csv`
- `data/analysis/meta_tb_mixed_no_oil_allmix_oos_trades.csv`
- `data/analysis/meta_tb_mixed_no_oil_allmix_oos_scored_trades.csv`
- `data/analysis/meta_tb_mixed_no_oil_allmix_threshold_grid.csv`
- `data/analysis/meta_tb_mixed_no_oil_allmix_label_ablation.csv`
- `data/analysis/meta_tb_mixed_no_oil_allmix_fold_calibration.csv`
- `data/analysis/meta_tb_mixed_no_oil_allmix_mc_daily_paths.csv`
- `data/analysis/meta_tb_mixed_no_oil_allmix_mc_daily_summary.csv`

### 2) Build strategy report with mixed variants included
```bash
python scripts/report_strategy_fx_comm_multi_tf.py \
  --exclude-oil \
  --include-meta-mixed \
  --meta-mixed-path data/analysis/meta_tb_mixed_no_oil_allmix_oos_trades.csv
```

Outputs:
- `data/analysis/strategy_fx_comm_no_oil_overall.csv`
- `data/analysis/strategy_fx_comm_no_oil_yearly.csv`
- `data/analysis/strategy_fx_comm_no_oil_pair.csv`
- `data/analysis/strategy_fx_comm_no_oil_pair_yearly.csv`
- `data/analysis/strategy_fx_comm_no_oil_accel_thresholds.csv`

Notes:
- Mixed rows are emitted as distinct variants: `mixed_<mix_id>__<variant>`
- No blending across mixes.

### 3) Produce recommended top-2 and filtered mixed report slices
```bash
python scripts/select_meta_mixed_top2.py
```

Outputs:
- `data/analysis/meta_tb_mixed_no_oil_allmix_recommended_top2.csv`
- `data/analysis/strategy_fx_comm_no_oil_mixed_top2_overall.csv`
- `data/analysis/strategy_fx_comm_no_oil_mixed_top2_yearly.csv`
- `data/analysis/strategy_fx_comm_no_oil_mixed_top2_pair.csv`
- `data/analysis/strategy_fx_comm_no_oil_mixed_top2_pair_yearly.csv`

### 4) Run exposure-focused strategy-family sweeps
```bash
python scripts/sweep_strategy_families.py \
  --exclude-oil \
  --mixes all \
  --out-prefix strategy_family_sweep_no_oil
```

Outputs:
- `data/analysis/strategy_family_sweep_no_oil_summary.csv`
- `data/analysis/strategy_family_sweep_no_oil_ranking.csv`
- `data/analysis/strategy_family_sweep_no_oil_selected_trades.csv`

Notes:
- Mixes are built from `MOM_PERSIST`, `MOM_BURST`, `REV_EXHAUSTION`, `REV_QUICKFAIL`.
- Ranking objective is exposure-weighted and enforces configurable gates on:
- `time_in_market_pct` reduction
- Sharpe retention
- annualized bps retention
- `worst_single_day_bps` improvement (single-day DD, non-cumulative)
- Defaults now enforce at least 2 `eligible=true` mixes via adaptive gate relaxation:
- `--min-eligible 2`
- gate relaxation over `--max-relax-steps` if needed

### 5) Build report from strategy-family selected trades
```bash
python scripts/report_strategy_fx_comm_multi_tf.py \
  --exclude-oil \
  --include-meta-mixed \
  --meta-mixed-path data/analysis/strategy_family_sweep_no_oil_selected_trades.csv
```

This appends selected family-mix rows into the standard report outputs under `timeframe=mixed`.

### 6) Run low-Z + hard-ML walk-forward sweep (strict DD-first)
```bash
python scripts/sweep_lowz_ml_hardgate.py \
  --exclude-oil \
  --mixes all \
  --out-prefix lowz_ml_hardgate
```

Outputs:
- `data/analysis/lowz_ml_hardgate_summary.csv`
- `data/analysis/lowz_ml_hardgate_ranking.csv`
- `data/analysis/lowz_ml_hardgate_selected_trades.csv`
- `data/analysis/lowz_ml_hardgate_oos_trades.csv`
- `data/analysis/lowz_ml_hardgate_oos_scored_trades.csv`
- `data/analysis/lowz_ml_hardgate_fold_metrics.csv`
- `data/analysis/lowz_ml_hardgate_threshold_grid.csv`
- `data/analysis/lowz_ml_hardgate_ablation.csv`

To append selected low-Z ML results into the report:
```bash
python scripts/report_strategy_fx_comm_multi_tf.py \
  --exclude-oil \
  --include-meta-mixed \
  --meta-mixed-path data/analysis/lowz_ml_hardgate_selected_trades.csv
```

### 7) Run cluster early-warning WFO (pre-loss-cluster detection)
```bash
python scripts/meta_cluster_earlywarning_wfo.py \
  --mixes "m5=MOM,m15=MOM+REV,m60=REV" \
  --exclude-oil \
  --cluster-trade-horizon 10 \
  --cluster-trade-loss-bps -250 \
  --cluster-day-horizon 5 \
  --cluster-day-loss-bps -400 \
  --threshold-grid "0.35,0.40,0.45,0.50,0.55,0.60,0.65" \
  --min-mean-bps 5.0 \
  --out-prefix cluster_ew_m5mom_m15momrev_m60rev
```

Outputs:
- `data/analysis/cluster_ew_m5mom_m15momrev_m60rev_summary.csv`
- `data/analysis/cluster_ew_m5mom_m15momrev_m60rev_folds.csv`
- `data/analysis/cluster_ew_m5mom_m15momrev_m60rev_threshold_grid.csv`
- `data/analysis/cluster_ew_m5mom_m15momrev_m60rev_oos_trades.csv`
- `data/analysis/cluster_ew_m5mom_m15momrev_m60rev_oos_scored_trades.csv`
- `data/analysis/cluster_ew_m5mom_m15momrev_m60rev_label_stats.csv`
- `data/analysis/cluster_ew_m5mom_m15momrev_m60rev_fold_calibration.csv`
- `data/analysis/cluster_ew_m5mom_m15momrev_m60rev_mc_daily_paths.csv`
- `data/analysis/cluster_ew_m5mom_m15momrev_m60rev_mc_daily_summary.csv`

Build markdown report + figures:
```bash
python scripts/visualization/build_cluster_earlywarning_report.py \
  --prefix cluster_ew_m5mom_m15momrev_m60rev \
  --report-path docs/analysis/cluster_earlywarning_report.md \
  --fig-dir docs/figures/cluster_earlywarning
```

Cluster EW interpretation:
- `worst_single_day_bps`: worst non-cumulative daily PnL (single-day DD proxy).
- `max_daily_dd_bps`: cumulative drawdown on the daily equity curve.
- `cluster_gate_action`: `keep_full`, `keep_half`, `skip` based on calibrated risk.
- `oos_hard_pass`: fold-level pass/fail against DD-first + return/trade floors.

### 8) Run KF directional/both-sides meta WFO (Q80 actionable regimes)
```bash
python scripts/meta_kf_directional_wfo.py \
  --mixes "m5=NONE,m15=MOM+REV,m60=REV" \
  --trade-timeframes m15,m60 \
  --decision-timeframes m15,m60 \
  --models heuristic,logit,hgbt,dual_head,regime_expert \
  --target-mode z_cross \
  --accel-quantile 0.80 \
  --pt-quantile 0.60 \
  --sl-quantile 0.60 \
  --p-min-grid "0.45,0.50,0.55,0.60" \
  --ev-min-grid "0.00,0.10,0.20" \
  --exclude-oil \
  --out-prefix kf_dir_q80_1bar
```

Both-sides one-bar probe:
```bash
python scripts/meta_kf_directional_wfo.py \
  --mixes "m5=NONE,m15=MOM+REV,m60=REV" \
  --trade-timeframes m15,m60 \
  --decision-timeframes m15,m60 \
  --models heuristic,logit,hgbt,dual_head,regime_expert \
  --target-mode one_bar \
  --policy-mode both_sides \
  --p-move-min 0.85 \
  --both-balance-tol 0.08 \
  --both-capture-mult 1.00 \
  --accel-quantile 0.80 \
  --pt-quantile 0.60 \
  --sl-quantile 0.60 \
  --exclude-oil \
  --out-prefix kf_both_q80_1bar
```

Outputs:
- `data/analysis/kf_dir_q80_1bar_summary.csv`
- `data/analysis/kf_dir_q80_1bar_folds.csv`
- `data/analysis/kf_dir_q80_1bar_model_grid.csv`
- `data/analysis/kf_dir_q80_1bar_oos_trades.csv`
- `data/analysis/kf_dir_q80_1bar_oos_scored.csv`
- `data/analysis/kf_dir_q80_1bar_yearly.csv`
- `data/analysis/kf_dir_q80_1bar_pair_timeframe_breakdown.csv`

Directional KF interpretation:
- Trading universe can be restricted with `--trade-timeframes` (for example `m15,m60`), while still using `m5` as context features.
- `--target-mode z_cross` uses full trade outcomes (existing causal z-cross/contract exits) for labels and policy scoring.
- `--target-mode one_bar` is available for short-horizon probing, but is not the primary production objective.
- `--policy-mode directional` keeps the directional keep/skip/override logic.
- `--policy-mode both_sides` enables OCO-style one-bar capture on high move-probability, direction-ambiguous rows.
- `--policy-mode both_sides` currently requires `--target-mode one_bar`.
- Actionable rows are selected by train-only threshold on `|kf_z_accel|` at quantile `--accel-quantile`.
- Labels are one-bar forward directional classes from raw move:
- `+1` if move >= PT barrier.
- `-1` if move <= -SL barrier.
- `0` otherwise.
- PT/SL barriers are estimated from train-only actionable rows per timeframe.
- Candidate policy overrides baseline side only when both confidence and EV pass selected thresholds; otherwise baseline side is retained.
- Promotion is strict hard-gate only (`directional_promoted` falls back to baseline on fold hard-fail).

Smoke report template:
- `docs/analysis/kf_directional_q80_1bar_report.md`

## Current Recommended Top-2 (from full all-mix run)

Selection rule:
- Rank `meta_tb_promoted` mixes by `sharpe` descending, tie-break `annualized_bps_calendar` descending.

| Rank | Mix | Trades | Mean PnL/Trade (bps) | Sharpe | Annualized BPS | Max Daily DD (bps) | MC Pass Rate |
|---|---|---:|---:|---:|---:|---:|---:|
| 1 | `m5_mom__m15_mom__m60_rev` | 13,539 | 20.37 | 5.097 | 46,027.29 | -5,437.81 | 1.00 |
| 2 | `m5_mom__m15_rev__m60_rev` | 8,432 | 19.26 | 4.032 | 27,147.51 | -3,504.99 | 1.00 |

## Interpretation Notes
- `annualized_bps_calendar`: average daily bps over calendar days annualized by `365.25`.
- `max_daily_dd_bps`: worst peak-to-trough drawdown on the calendar-day cumulative bps curve (more negative is worse).
- `cagr` in report tables is account-equity CAGR under risk sizing (`risk_per_trade_pct=1%`); it is not directly comparable to raw bps without the risk-sizing context.
- Exposure metrics now included in report rows:
- `time_in_market_pct`
- `avg_concurrent_trades`
- `trade_density_per_day`
- `avg_trade_duration_bars`
- `avg_trade_duration_hours`

## Strategy Guide Hygiene
- This manual intentionally excludes deprecated or non-causal reporting sections.
- Source-of-truth artifacts are the CSVs listed above.
- If rerunning with changed parameters, update this guide with the exact command line and new result table.
