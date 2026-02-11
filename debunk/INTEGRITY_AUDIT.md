# Integrity Audit Report

Date: 2026-02-08
Scope: MOM strategy datasets (M5/M15) + guardrail timing sensitivity

## M5 Results
- **Timestamp regularity**: PASS — mode_delta_ns=300000000000, irregular_rate=0.48%, dup_rate=0.000%
- **Z-window entry index**: PASS — entries_before_500=0
- **Entry timestamp alignment**: PASS — missing_ts=0 (0.00%), missing_pair=0
- **Duration bounds**: PASS — invalid_duration=0, out_of_range=0
- **Active leg validity**: PASS — invalid_active_leg=0
- **PnL recompute**: PASS — mean_abs=0.0025, p95_abs=0.0048, max_abs=0.0050, mismatch_rate>0.1bps=0.00%
- **Next-bar entry sensitivity**: PASS — delta_mean=0.062 bps, delta_p95=8.111, flip_rate=3.93%
- **Guardrail timing sensitivity**: WARN — entry_vs_exit: trade_diff=-6.65%, mean_diff=-1.582 bps
- **Universe stability**: PASS — no multi-year gaps
- **Max concurrent trades**: INFO — max_open=167

## M15 Results
- **Timestamp regularity**: PASS — mode_delta_ns=900000000000, irregular_rate=1.06%, dup_rate=0.000%
- **Z-window entry index**: PASS — entries_before_500=0
- **Entry timestamp alignment**: PASS — missing_ts=0 (0.00%), missing_pair=0
- **Duration bounds**: PASS — invalid_duration=0, out_of_range=0
- **Active leg validity**: PASS — invalid_active_leg=0
- **PnL recompute**: PASS — mean_abs=0.0025, p95_abs=0.0048, max_abs=0.0050, mismatch_rate>0.1bps=0.00%
- **Next-bar entry sensitivity**: PASS — delta_mean=-0.029 bps, delta_p95=13.804, flip_rate=3.56%
- **Guardrail timing sensitivity**: WARN — entry_vs_exit: trade_diff=-4.10%, mean_diff=-4.019 bps
- **Universe stability**: PASS — no multi-year gaps
- **Max concurrent trades**: INFO — max_open=147

## Feature Lookahead Scan
- M5 compute_features_at_entry contains i+? False
- M15 compute_features_at_entry contains i+? False

## Outcome Usage Scan
Occurrences of 'outcome' in scripts:
- scripts/build_meta_dataset_v3_m5_1step.py:# record trade outcome for rolling stats
- scripts/integrity_audit.py:if "outcome" in text:
- scripts/integrity_audit.py:lines.append("Occurrences of 'outcome' in scripts:")
- scripts/integrity_audit.py:lines.append("- No 'outcome' usages found.")
- scripts/integrity_audit.py:lines.append("Unexpected outcome usage (needs review):")
- scripts/integrity_audit.py:lines.append("- No unexpected outcome usage.")
- scripts/build_meta_dataset_v3_m1.py:pnl, duration, outcome = simulate_trade(
- scripts/build_meta_dataset_v3_m1.py:"outcome": outcome,
- scripts/build_meta_dataset_v3_m1.py:pnl, duration, outcome = simulate_trade(
- scripts/build_meta_dataset_v3_m1.py:"outcome": outcome,
- scripts/build_meta_dataset_v3_h4.py:pnl, duration, outcome = simulate_trade(
- scripts/build_meta_dataset_v3_h4.py:"outcome": outcome,
- scripts/build_meta_dataset_v3_h4.py:pnl, duration, outcome = simulate_trade(
- scripts/build_meta_dataset_v3_h4.py:"outcome": outcome,
- scripts/build_meta_dataset_v3_m5.py:pnl, duration, outcome = simulate_trade(
- scripts/build_meta_dataset_v3_m5.py:"outcome": outcome,
- scripts/build_meta_dataset_v3_m5.py:pnl, duration, outcome = simulate_trade(
- scripts/build_meta_dataset_v3_m5.py:"outcome": outcome,
- scripts/build_meta_dataset_v3_h1.py:pnl, duration, outcome = simulate_trade(
- scripts/build_meta_dataset_v3_h1.py:"outcome": outcome,
- scripts/build_meta_dataset_v3_h1.py:pnl, duration, outcome = simulate_trade(
- scripts/build_meta_dataset_v3_h1.py:"outcome": outcome,
- scripts/explore_rev_reversion_classifier.py:- Target: outcome == WIN_REV (z0 cross before stop/timeout)
- scripts/explore_rev_reversion_classifier.py:rev["label_win_rev"] = (rev["outcome"] == "WIN_REV").astype(int)
- scripts/build_meta_dataset_v3_h2.py:pnl, duration, outcome = simulate_trade(
- scripts/build_meta_dataset_v3_h2.py:"outcome": outcome,
- scripts/build_meta_dataset_v3_h2.py:pnl, duration, outcome = simulate_trade(
- scripts/build_meta_dataset_v3_h2.py:"outcome": outcome,
- scripts/build_meta_dataset_v3_m30.py:pnl, duration, outcome = simulate_trade(
- scripts/build_meta_dataset_v3_m30.py:"outcome": outcome,
- scripts/build_meta_dataset_v3_m30.py:pnl, duration, outcome = simulate_trade(
- scripts/build_meta_dataset_v3_m30.py:"outcome": outcome,
- scripts/build_meta_dataset_v3_m45.py:pnl, duration, outcome = simulate_trade(
- scripts/build_meta_dataset_v3_m45.py:"outcome": outcome,
- scripts/build_meta_dataset_v3_m45.py:pnl, duration, outcome = simulate_trade(
- scripts/build_meta_dataset_v3_m45.py:"outcome": outcome,
- scripts/redteam_logic_tests.py:usecols = ["pair", "timestamp", "outcome", "pnl_bps", "duration_bars"]
- scripts/redteam_logic_tests.py:purpose = "Quantify outcome/PNL alignment (WIN_MOM should be >0, LOSS_REV should be <=0)."
- scripts/redteam_logic_tests.py:win_neg = ((df["outcome"] == "WIN_MOM") & (df["pnl_bps"] <= 0)).mean()
- scripts/redteam_logic_tests.py:loss_pos = ((df["outcome"] == "LOSS_REV") & (df["pnl_bps"] > 0)).mean()
- scripts/ml_threshold_feasibility.py:outcome = 0 # 0=Loss, 1=Win
- scripts/diagnose_rev_pred_pnl.py:pred[["pair", "timestamp", "year", "pnl_bps", "pred_pnl", "p_up", "outcome"]].to_csv(out_path, index=False)
- scripts/build_meta_dataset_v3_m10.py:pnl, duration, outcome = simulate_trade(
- scripts/build_meta_dataset_v3_m10.py:"outcome": outcome,
- scripts/build_meta_dataset_v3_m10.py:pnl, duration, outcome = simulate_trade(
- scripts/build_meta_dataset_v3_m10.py:"outcome": outcome,
- scripts/build_meta_dataset_v3_m5_optimized.py:'outcome': out, 'pnl_bps': pnl, 'duration_bars': dur,
- scripts/build_meta_dataset_v3_m5_optimized.py:'outcome': out, 'pnl_bps': pnl, 'duration_bars': dur,
- scripts/build_meta_dataset_v2.py:outcome = ""
- scripts/build_meta_dataset_v2.py:outcome = "LOSS_REV"
- ... (26 more)
Unexpected outcome usage (needs review):
- scripts/ml_threshold_feasibility.py:outcome = 0 # 0=Loss, 1=Win
- scripts/diagnose_rev_pred_pnl.py:pred[["pair", "timestamp", "year", "pnl_bps", "pred_pnl", "p_up", "outcome"]].to_csv(out_path, index=False)
