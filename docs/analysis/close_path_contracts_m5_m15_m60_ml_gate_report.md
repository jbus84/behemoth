# Close-Path Contracts Report (Unclipped Primary, Clipped Secondary)

- Generated: **2026-02-16 UTC**
- Universe: **FX + commodities ex-oil**
- Validation: **Causal walk-forward OOS (2020-2025)**
- Default PnL mode: **unclipped close-at-closure**
- Sensitivity PnL mode: **clipped contract (+TP/-SL caps)**

## Model Semantics

This is a **close-path first-hit contract** model:
- Build signed close-to-close path over next `h=5` bars.
- Determine closure bar by first close-path hit of `+TP` or `-SL`, else timeout at bar `h`.
- Primary PnL uses the **actual close-path value at that closure bar** (unclipped).
- Secondary PnL applies TP/SL caps for sensitivity only.

## Contract Settings

- `m5`: `TP=4 bps`, `SL=2 bps`, `h=5`
- `m15`: `TP=6 bps`, `SL=2 bps`, `h=5`
- `m60`: `TP=10 bps`, `SL=2 bps`, `h=5`

## Headline OOS (Primary = Unclipped)

| timeframe | variant | trades | mean_pnl_bps (primary) | sharpe (primary) | TIM % | worst day bps (primary) | max daily DD bps (primary) |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| m5 | baseline_q_accel | 514,661 | -0.090 | -2.683 | 53.393 | -1,445.015 | -46,452.843 |
| m5 | ml_gated | 28,742 | 3.443 | 11.180 | 7.924 | -61.229 | -97.927 |
| m15 | baseline_q_accel | 172,400 | -0.125 | -1.385 | 51.541 | -742.614 | -25,135.580 |
| m15 | ml_gated | 11,788 | 4.328 | 7.659 | 8.042 | -177.740 | -368.302 |
| m60 | baseline_q_accel | 44,852 | -0.321 | -0.945 | 50.623 | -1,027.503 | -14,710.089 |
| m60 | ml_gated | 14,381 | -0.025 | -0.039 | 23.894 | -694.748 | -2,710.297 |

## Secondary Sensitivity (Clipped Contract PnL)

| timeframe | variant | mean_pnl_bps (secondary) | sharpe (secondary) | worst day bps (secondary) | max daily DD bps (secondary) |
| --- | --- | ---: | ---: | ---: | ---: |
| m5 | baseline_q_accel | 0.380 | 16.428 | -95.170 | -120.103 |
| m5 | ml_gated | 1.973 | 15.277 | -19.021 | -19.778 |
| m15 | baseline_q_accel | 0.973 | 15.893 | -45.319 | -47.871 |
| m15 | ml_gated | 2.680 | 11.819 | -18.000 | -22.000 |
| m60 | baseline_q_accel | 2.248 | 13.271 | -44.652 | -68.820 |
| m60 | ml_gated | 2.547 | 9.870 | -30.000 | -41.725 |

Interpretation:
- Unclipped primary is materially harsher (especially baseline and `m60`).
- Gating is still strongly helpful for `m5`/`m15` under primary semantics.
- `m60` under unclipped primary is near flat/negative in this setup.

## Time-to-TP and Overshoot (Unclipped-Primary Runs)

| timeframe | variant | TP hit rate | median TP hit bar | median overshoot at hit (bps) | median overshoot to h=5 (bps) |
| --- | --- | ---: | ---: | ---: | ---: |
| m5 | baseline_q_accel | 31.415% | 2 | 1.726 | 4.030 |
| m5 | ml_gated | 58.274% | 2 | 2.106 | 5.435 |
| m15 | baseline_q_accel | 32.777% | 2 | 2.974 | 7.228 |
| m15 | ml_gated | 55.217% | 1 | 3.823 | 10.056 |
| m60 | baseline_q_accel | 32.830% | 1 | 5.713 | 13.956 |
| m60 | ml_gated | 36.027% | 1 | 6.355 | 16.720 |

## Execution Robustness (+1 Bar Delay)

ML-gated only, evaluated on close-path contracts.

| timeframe | +1 bar, +0 bps | +1 bar, +1 bps | +1 bar, +2 bps |
| --- | ---: | ---: | ---: |
| m5 mean pnl/trade | 1.273 | 0.697 | 0.135 |
| m15 mean pnl/trade | 2.179 | 1.725 | 1.213 |
| m60 mean pnl/trade | 2.460 | 2.123 | 1.731 |

## Quick Feature Importance Breakdown

Method:
- Permutation importance on fold calibration slices (`neg_log_loss` scoring).
- Sample cap: `4,000` rows per fold; repeats: `2`.
- Uses the fold-selected model (`hgbt` for m5/m15; mix of `hgbt`/`logit` for m60).

Top signal features (average over folds):

| timeframe | top features (highest average permutation importance) |
| --- | --- |
| m5 | `m15_kf_robust_z`, `kf_student_loglik`, `accel_sign`, `beta`, `kf_z_accel`, `m60_kf_robust_z` |
| m15 | `m60_kf_robust_z`, `m60_kf_z_vel`, `kf_z_accel`, `beta`, `kf_student_loglik`, `accel_sign` |
| m60 | `m15_kf_z_vel`, `entry_hour_utc`, `abs_accel`, `m5_kf_robust_z`, `m5_kf_z_vel`, `accel_sign` |

Takeaway:
- `m5`/`m15` are driven mainly by cross-timeframe robust-Z/velocity plus local acceleration structure.
- `m60` importances are much smaller in magnitude, consistent with the weak unclipped edge there.

## Practical Conclusion

- If you want realism aligned to close-only execution, **use unclipped primary**.
- Keep clipped numbers as sensitivity only.
- With leakage-safe splits and optimized thresholding, `m15` improves materially and remains robust under delay/penalty tests.
- `m5` remains strong and robust with lower time-in-market.
- `m60` remains weak under unclipped primary and should likely be a secondary/filter leg only.

## Reproducibility and Artifacts

Core script:
- `scripts/meta_m15_accel_h5_ml_gate_wfo.py`

Primary runs used in this report:
- `data/analysis/m5_accel_h5_ml_gate_q90_tp4_sl2_ctx_unclipped_primary_optthr_leakfix_summary.csv`
- `data/analysis/m15_accel_h5_ml_gate_q90_tp6_sl2_ctx_unclipped_primary_optthr_leakfix_summary.csv`
- `data/analysis/m60_accel_h5_ml_gate_q90_tp10_sl2_ctx_lag0_det_unclipped_primary_summary.csv`

Derived diagnostics:
- `data/analysis/close_path_overshoot_summary_unclipped_primary_leakfix_optthr.csv`
- `data/analysis/close_path_fill_delay_spread_robustness_unclipped_primary_leakfix_optthr.csv`
- `data/analysis/close_path_feature_importance_permutation_unclipped_primary_agg.csv`
- `data/analysis/close_path_feature_importance_permutation_unclipped_primary_top12_signal.csv`
