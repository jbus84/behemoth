"""CatBoost threshold sweep on EURUSD — hour as feature, varying prob thresholds.

Tests 0.55, 0.60, 0.65, 0.70 to find where genuine selectivity emerges.

Usage:
    uv run python scripts/fx_coint/catboost_threshold_sweep.py
"""
# ruff: noqa: E402
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import polars as pl
from catboost import CatBoostClassifier
from scipy.stats import ttest_1samp
from sklearn.preprocessing import StandardScaler

_WORKTREE = Path("/Users/danielfisher/repositories/behemoth/.claude/worktrees/feat-pf-15m")
sys.path.insert(0, str(_WORKTREE))
import importlib.util

spec = importlib.util.spec_from_file_location(
    "ird", str(_WORKTREE / "scripts/fx_coint/interaction_ridge_diagnostic.py")
)
ird = importlib.util.module_from_spec(spec)
sys.modules["ird"] = ird
spec.loader.exec_module(ird)
build_freq_bars = ird.build_freq_bars
build_panel_interactive = ird.build_panel_interactive

_SYMBOL = "EURUSD"
_FREQS = ["30m", "1h"]
_WINDOWS = [3, 6, 12, 18]
_COST = 0.69
_THRESHOLDS = [0.55, 0.60, 0.65, 0.70, 0.75]


def rolling_catboost_thresh(
    panel: pd.DataFrame,
    feat_cols: list[str],
    window_months: int,
    thresh: float,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    panel = panel.copy().sort_values("bucket").reset_index(drop=True)
    panel["month"] = panel["bucket"].dt.to_period("M")
    panel["y_bin"] = (panel["ret_next_bps"] > 0).astype(int)
    months = panel["month"].unique()
    if len(months) < window_months + 2:
        return pd.DataFrame(), pd.DataFrame()

    long_frames, short_frames = [], []

    for i in range(window_months, len(months)):
        train_months = months[i - window_months : i]
        test_months = [months[i]]
        train = panel[panel["month"].isin(train_months)]
        test = panel[panel["month"].isin(test_months)]
        if len(train) < 100 or len(test) < 10:
            continue

        up_ratio = train["y_bin"].mean()
        if up_ratio < 0.3 or up_ratio > 0.7:
            continue

        X_train = train[feat_cols].to_numpy()
        y_train = train["y_bin"].to_numpy()
        X_test = test[feat_cols].to_numpy()
        act_test = test["ret_next_bps"].to_numpy()
        bk_test = test["bucket"].to_numpy()

        sc = StandardScaler().fit(X_train)
        X_train_s = sc.transform(X_train)
        X_test_s = sc.transform(X_test)

        clf = CatBoostClassifier(
            iterations=200,
            depth=4,
            learning_rate=0.05,
            l2_leaf_reg=10.0,
            border_count=32,
            subsample=0.6,
            rsm=0.6,
            loss_function="Logloss",
            eval_metric="AUC",
            verbose=False,
            random_seed=42,
            thread_count=4,
        )
        clf.fit(X_train_s, y_train)
        probs = clf.predict_proba(X_test_s)[:, 1]

        mask_long = probs >= thresh
        if mask_long.sum() >= 1:
            long_frames.append(pd.DataFrame({
                "prob": probs[mask_long],
                "act": act_test[mask_long],
                "bucket": pd.to_datetime(bk_test[mask_long]),
                "month": months[i],
            }))

        mask_short = probs <= (1 - thresh)
        if mask_short.sum() >= 1:
            short_frames.append(pd.DataFrame({
                "prob": probs[mask_short],
                "act": act_test[mask_short],
                "bucket": pd.to_datetime(bk_test[mask_short]),
                "month": months[i],
            }))

    if not long_frames:
        return pd.DataFrame(), pd.DataFrame()

    long_df = pd.concat(long_frames, ignore_index=True)
    short_df = pd.concat(short_frames, ignore_index=True)
    long_df["net"] = long_df["act"] - _COST
    short_df["net"] = -short_df["act"] - _COST
    return long_df, short_df


def evaluate_overall(df: pd.DataFrame, freq: str, wmo: int, direction: str, thresh: float) -> dict:
    if df.empty:
        return {}
    df = df.copy()
    df["year"] = df["bucket"].dt.year
    net = df["net"].to_numpy()
    t, p = ttest_1samp(net, 0) if len(net) > 2 else (np.nan, np.nan)
    yr = df.groupby("year")["net"].mean()
    pos = (net > 0).sum() / len(net)
    if len(net) > 3:
        weekly = df.groupby(df["bucket"].dt.to_period("W"))["net"].sum()
        sharpe_est = (weekly.mean() / weekly.std()) * np.sqrt(52) if weekly.std() > 0 else np.nan
    else:
        sharpe_est = np.nan
    return {
        "sym": _SYMBOL, "freq": freq, "window": wmo, "direction": direction,
        "thresh": thresh, "n": len(df), "mean": net.mean(),
        "t": t, "p": p, "sharpe_est": sharpe_est,
        "pos_years": (yr > 0).sum(), "nyears": len(yr),
        "years_str": f"{(yr > 0).sum()}/{len(yr)}",
        "pos_pct": pos * 100,
        "avg_prob": df["prob"].mean() if "prob" in df.columns else np.nan,
    }


def main():
    print("=" * 80)
    print(f"CATBOOST THRESHOLD SWEEP — {_SYMBOL}")
    print("Testing prob thresholds: 0.55, 0.60, 0.65, 0.70, 0.75")
    print("=" * 80)

    src = _WORKTREE.parents[2] / f"data/tick_bars/{_SYMBOL}_1m_flow.parquet"
    if not src.exists():
        print(f"Data not found: {src}")
        return

    overall_rows = []

    for freq in _FREQS:
        print(f"\n{'='*60}")
        print(f"FREQUENCY: {freq}")
        print(f"{'='*60}")

        df_1m = pl.read_parquet(src)
        bars = build_freq_bars(df_1m, freq)
        panel = build_panel_interactive(bars, "INTERACT")
        if len(panel) < 500:
            continue
        feat_cols = panel["feature_cols"].iloc[0]

        for wmo in _WINDOWS:
            print(f"\n  Window: {wmo}mo")
            print(f"  {'thresh':>7} {'dir':>6} {'n':>6} {'mean':>7} {'t':>6} {'p':>7} {'sharpe':>7} {'years':>6} {'pos':>5} {'avg_prob':>9}")
            print(f"  {'-'*70}")
            for thresh in _THRESHOLDS:
                long_df, short_df = rolling_catboost_thresh(panel, feat_cols, wmo, thresh)
                for df, direction in [(long_df, "LONG"), (short_df, "SHORT")]:
                    if df.empty:
                        continue
                    overall = evaluate_overall(df, freq, wmo, direction, thresh)
                    if overall:
                        overall_rows.append(overall)
                        print(
                            f"  {thresh:.2f}  {direction:6s} {overall['n']:6d} "
                            f"{overall['mean']:+.2f} {overall['t']:+.2f} {overall['p']:.4f} "
                            f"{overall['sharpe_est']:+.2f} {overall['years_str']:6s} "
                            f"{overall['pos_pct']:4.0f}% {overall['avg_prob']:+.4f}"
                        )

    if not overall_rows:
        print("\nNo results produced.")
        return

    master = pd.DataFrame(overall_rows)

    # Best by |t| globally
    print(f"\n{'='*80}")
    print("TOP 15 CELLS GLOBALLY (by |t|)")
    print(f"{'='*80}")
    top15 = master.reindex(master["t"].abs().sort_values(ascending=False).index).head(15)
    print(f"{'freq':>4} {'wmo':>3} {'thresh':>7} {'dir':>6} {'n':>6} {'mean':>7} {'t':>6} {'p':>7} {'sharpe':>7} {'years':>6} {'pos':>5}")
    print("-" * 70)
    for _, r in top15.iterrows():
        print(
            f"{r['freq']:>4} {r['window']:>3} {r['thresh']:>7.2f} {r['direction']:>6} "
            f"{r['n']:>6} {r['mean']:>+7.2f} {r['t']:>+6.2f} {r['p']:>7.4f} "
            f"{r['sharpe_est']:>+7.2f} {r['years_str']:>6} {r['pos_pct']:>4.0f}%"
        )

    # Best positive cells
    pos = master[(master["mean"] > 0) & (master["t"] > 1.0)].sort_values("t", ascending=False)
    if not pos.empty:
        print(f"\n{'='*80}")
        print("PROMISING CELLS (mean > 0, t > 1.0)")
        print(f"{'='*80}")
        print(f"{'freq':>4} {'wmo':>3} {'thresh':>7} {'dir':>6} {'n':>6} {'mean':>7} {'t':>6} {'p':>7} {'sharpe':>7} {'years':>6} {'pos':>5}")
        print("-" * 70)
        for _, r in pos.head(20).iterrows():
            print(
                f"{r['freq']:>4} {r['window']:>3} {r['thresh']:>7.2f} {r['direction']:>6} "
                f"{r['n']:>6} {r['mean']:>+7.2f} {r['t']:>+6.2f} {r['p']:>7.4f} "
                f"{r['sharpe_est']:>+7.2f} {r['years_str']:>6} {r['pos_pct']:>4.0f}%"
            )
    else:
        print(f"\n{'='*80}")
        print("No cells with mean > 0 and t > 1.0.")
        print(f"{'='*80}")

    # Show threshold sensitivity for 30m 3mo
    print(f"\n{'='*80}")
    print("THRESHOLD SENSITIVITY: EURUSD 30m 3mo")
    print(f"{'='*80}")
    sens = master[(master["freq"] == "30m") & (master["window"] == 3)].sort_values(["direction", "thresh"])
    if not sens.empty:
        print(f"{'thresh':>7} {'dir':>6} {'n':>6} {'mean':>7} {'t':>6} {'p':>7} {'sharpe':>7} {'years':>6} {'pos':>5} {'avg_prob':>9}")
        for _, r in sens.iterrows():
            print(
                f"{r['thresh']:>7.2f} {r['direction']:>6} {r['n']:>6} "
                f"{r['mean']:+.2f} {r['t']:+.2f} {r['p']:.4f} "
                f"{r['sharpe_est']:+.2f} {r['years_str']:6s} {r['pos_pct']:4.0f}% {r['avg_prob']:+.4f}"
            )


if __name__ == "__main__":
    main()
