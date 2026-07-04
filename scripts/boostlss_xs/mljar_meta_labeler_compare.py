"""
mljar-supervised meta-labeler comparison: does model mixing (LightGBM, Xgboost,
CatBoost, Random Forest, Extra Trees combined via mljar's AutoML ensemble) beat
the existing single HistGradientBoostingClassifier meta-labeler, on the current
best trade population (q=0.90 quantile regression, window 4.5:5.5, tail_ratio
feature -- the just-merged +6.014 bps/fill result)?

Requires mljar-supervised, kept as an EPHEMERAL dependency (not added to
pyproject.toml/uv.lock):

    uv run --with mljar-supervised python scripts/boostlss_xs/mljar_meta_labeler_compare.py \\
        --data-dir /path/to/tick_bars \\
        --tick-dir /path/to/raw_ticks \\
        [--pairs EURUSD] \\
        [--high-quantile 0.90] \\
        [--low-quantile 0.5] \\
        [--sig-thresh 4.5] \\
        [--sig-thresh-hi 5.5] \\
        [--threshold 0.55] \\
        [--automl-time-limit 90] \\
        [--tail-rows N]

mljar's AutoML defaults to a 1-hour time budget and ~10 model families plus
ensembling/stacking -- across even one pair's 5 WFO folds that would risk
multi-hour runtimes. This script caps it hard: mode="Explain" (fastest),
algorithms restricted to 5 tree-based families, explain_level=0 (skip full
SHAP report generation), total_time_limit defaulting to 90 seconds per fold.

--tail-rows truncates the raw 1-minute parquet before 1h aggregation, for fast
smoke-testing only -- omit it (or pass a small value like 20000) to sanity-check
the script quickly before committing to the full, untruncated run.
"""
from __future__ import annotations

import argparse
import shutil
import tempfile

import numpy as np
import pandas as pd
from meta_label_straddle import (
    _FEAT_COLS,
    _N_FOLDS,
    _option_b_net_per_fill,
    build_1h_features,
    run_tick_backtest,
)
from plain_regression_baseline import fit_wfo_quantile_robust
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import roc_auc_score
from supervised import AutoML

_RATIO_FLOOR = 1e-6
_ALGORITHMS = ["LightGBM", "Xgboost", "CatBoost", "Random Forest", "Extra Trees"]


def _build_trade_population(
    pairs: list[str],
    data_dir: str,
    tick_dir: str,
    high_quantile: float,
    low_quantile: float,
    sig_thresh: float,
    sig_thresh_hi: float,
    tail_rows: int | None,
) -> pd.DataFrame:
    tick_dfs: list[pd.DataFrame] = []
    for sym in pairs:
        d = build_1h_features(sym, data_dir, tail_rows=tail_rows)
        X, vs, ts = d["X"], d["vs"], d["ts"]
        n = len(vs)
        y = np.full(n, np.nan)
        y[:-1] = vs[1:]

        print(f"  {sym}: fitting high (q={high_quantile}) + "
              f"low (q={low_quantile}) quantile WFO...", flush=True)
        sg_high = fit_wfo_quantile_robust(X, y, quantile=high_quantile)
        sg_low = fit_wfo_quantile_robust(X, y, quantile=low_quantile)
        tail_ratio = sg_high / np.maximum(sg_low, _RATIO_FLOOR)

        ratio_by_ts = {
            str(ts[i]): tail_ratio[i] for i in range(n) if not np.isnan(tail_ratio[i])
        }

        df_sym, _ = run_tick_backtest(
            sym=sym, data_dir=data_dir, tick_dir=tick_dir,
            family="gaussian", sigma_override=sg_high,
            sig_thresh=sig_thresh, sig_thresh_hi=sig_thresh_hi,
            tail_rows=tail_rows,
        )
        if len(df_sym) == 0:
            continue
        df_sym["tail_ratio"] = df_sym["ts"].map(ratio_by_ts)
        tick_dfs.append(df_sym)

    if not tick_dfs:
        print("No trades produced.")
        raise SystemExit(1)
    return pd.concat(tick_dfs, ignore_index=True)


def fit_meta_label_wfo_compare(
    df: pd.DataFrame,
    feat_cols: list[str],
    automl_time_limit: int,
    mode: str = "Explain",
    n_jobs: int = 0,
) -> tuple[pd.DataFrame, list[tuple[int, pd.DataFrame]]]:
    """
    Fits BOTH the baseline HistGradientBoostingClassifier and mljar's AutoML
    on identical WFO fold splits (matching fit_meta_label_wfo's fold logic
    exactly: fs = n // (_N_FOLDS + 1), expanding window, no embargo).

    Returns (df_oos, leaderboards): df_oos has 'prob_tp_baseline' and
    'prob_tp_mljar' columns for OOS rows where BOTH classifiers produced a
    prediction; leaderboards is a list of (fold_index, leaderboard_dataframe)
    for folds where mljar succeeded, so the caller can inspect which model
    family actually won that fold.
    """
    df = df.dropna(subset=feat_cols).copy()
    df["label"] = (df.outcome == "tp").astype(int)
    X = df[feat_cols].values
    y = df.label.values
    n = len(df)
    fs = n // (_N_FOLDS + 1)

    oos_prob_baseline = np.full(n, np.nan)
    oos_prob_mljar = np.full(n, np.nan)
    aucs_baseline: list[float] = []
    aucs_mljar: list[float] = []
    leaderboards: list[tuple[int, pd.DataFrame]] = []

    for fi in range(_N_FOLDS):
        tr_end = fs * (fi + 1)
        te_start = tr_end
        te_end = min(te_start + fs, n)
        if te_end <= te_start:
            break

        clf = HistGradientBoostingClassifier(max_iter=200, max_depth=4, random_state=42)
        clf.fit(X[:tr_end], y[:tr_end])
        oos_prob_baseline[te_start:te_end] = clf.predict_proba(X[te_start:te_end])[:, 1]
        aucs_baseline.append(
            roc_auc_score(y[te_start:te_end], oos_prob_baseline[te_start:te_end])
        )

        results_path = tempfile.mkdtemp(prefix=f"mljar_meta_compare_fold{fi}_")
        try:
            automl = AutoML(
                mode=mode,
                ml_task="binary_classification",
                total_time_limit=automl_time_limit,
                algorithms=_ALGORITHMS,
                explain_level=0,
                results_path=results_path,
                n_jobs=n_jobs,
                verbose=0,
            )
            automl.fit(
                pd.DataFrame(X[:tr_end], columns=feat_cols),
                pd.Series(y[:tr_end]),
            )
            oos_prob_mljar[te_start:te_end] = automl.predict_proba(
                pd.DataFrame(X[te_start:te_end], columns=feat_cols)
            )[:, 1]
            aucs_mljar.append(
                roc_auc_score(y[te_start:te_end], oos_prob_mljar[te_start:te_end])
            )
            leaderboards.append((fi, automl.get_leaderboard()))
        except Exception as e:
            print(f"  fold {fi}: mljar AutoML failed — {e}")
        finally:
            shutil.rmtree(results_path, ignore_errors=True)

    mask = ~np.isnan(oos_prob_baseline) & ~np.isnan(oos_prob_mljar)
    df_oos = df[mask].copy()
    df_oos["prob_tp_baseline"] = oos_prob_baseline[mask]
    df_oos["prob_tp_mljar"] = oos_prob_mljar[mask]
    df_oos["mean_auc_baseline"] = float(np.mean(aucs_baseline)) if aucs_baseline else float("nan")
    df_oos["mean_auc_mljar"] = float(np.mean(aucs_mljar)) if aucs_mljar else float("nan")
    return df_oos, leaderboards


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="mljar-supervised meta-labeler comparison")
    p.add_argument("--data-dir",          default="/Users/danielfisher/repositories/behemoth/data/tick_bars")
    p.add_argument("--tick-dir",          default="/Users/danielfisher/Desktop/tick")
    p.add_argument("--pairs",             nargs="+", default=["EURUSD"])
    p.add_argument("--high-quantile",     type=float, default=0.90)
    p.add_argument("--low-quantile",      type=float, default=0.5)
    p.add_argument("--sig-thresh",        type=float, default=4.5)
    p.add_argument("--sig-thresh-hi",     type=float, default=5.5)
    p.add_argument("--threshold",         type=float, default=0.55)
    p.add_argument("--automl-time-limit", type=int, default=90)
    p.add_argument("--mode",              default="Explain",
                   choices=["Explain", "Perform", "Compete"],
                   help="mljar AutoML mode (Compete = most thorough tuning + stacked ensemble)")
    p.add_argument("--n-jobs",            type=int, default=0,
                   help="mljar/joblib parallel workers (0=auto/-1=all cores). Use 1 to "
                        "serialize and avoid joblib memmap/fork pressure under Compete.")
    p.add_argument("--tail-rows",         type=int, default=None)
    return p.parse_args()


if __name__ == "__main__":
    args = _parse_args()

    all_raw = _build_trade_population(
        pairs=args.pairs, data_dir=args.data_dir, tick_dir=args.tick_dir,
        high_quantile=args.high_quantile, low_quantile=args.low_quantile,
        sig_thresh=args.sig_thresh, sig_thresh_hi=args.sig_thresh_hi,
        tail_rows=args.tail_rows,
    )

    feat_cols = [*_FEAT_COLS, "tail_ratio"]

    oos_dfs: list[pd.DataFrame] = []
    all_leaderboards: list[tuple[str, int, pd.DataFrame]] = []
    for sym, g in all_raw.groupby("sym"):
        print(f"  {sym}: running WFO comparison "
              f"(mode={args.mode}, automl_time_limit={args.automl_time_limit}s/fold)...", flush=True)
        try:
            df_oos, leaderboards = fit_meta_label_wfo_compare(
                g.copy(), feat_cols=feat_cols, automl_time_limit=args.automl_time_limit,
                mode=args.mode, n_jobs=args.n_jobs,
            )
            oos_dfs.append(df_oos)
            for fi, lb in leaderboards:
                all_leaderboards.append((sym, fi, lb))
        except Exception as e:
            print(f"  {sym}: comparison failed — {e}")

    if not oos_dfs:
        print("Meta-labeling comparison produced no results.")
        raise SystemExit(1)

    result = pd.concat(oos_dfs, ignore_index=True)

    print()
    print("=" * 70)
    print("BASELINE vs MLJAR COMPARISON")
    print("=" * 70)
    for label, prob_col, auc_col in [
        ("baseline (HistGradientBoostingClassifier)", "prob_tp_baseline", "mean_auc_baseline"),
        ("mljar (AutoML ensemble)", "prob_tp_mljar", "mean_auc_mljar"),
    ]:
        cmp_df = result.rename(columns={prob_col: "prob_tp"})
        ob_net = _option_b_net_per_fill(cmp_df, args.threshold)
        print(f"{label:<42}  n={len(cmp_df):>5}  AUC={cmp_df[auc_col].mean():.3f}  "
              f"TP%={cmp_df.label.mean():.1%}  Option B={ob_net:+.3f} bps/fill")

    print()
    print("=" * 70)
    print("LEADERBOARD (one row per fold that mljar completed)")
    print("=" * 70)
    for sym, fi, lb in all_leaderboards:
        print(f"\n  {sym} fold {fi}:")
        print(lb.to_string(index=False))
