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
- M5 compute_features_at_entry: skipped (features removed)
- M15 compute_features_at_entry: skipped (features removed)

## Outcome Usage Scan
Legacy ML/meta‑dataset builders were removed. Outcome usage is now limited to
rule‑based QA/diagnostic scripts (e.g., `scripts/redteam_logic_tests.py`) and
the integrity audit itself. No unexpected outcome usage remains in the active
pipeline.
