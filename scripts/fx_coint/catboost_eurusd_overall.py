"""CatBoost classifier on EURUSD — hour as feature, not split.

The model receives all features INCLUDING hour/hour-dummies and learns session
structure internally. No per-hour evaluation; overall P&L only.

Uses CatBoost (installed: 1.2.10) with strong regularization.

Usage:
    uv run python scripts/fx_coint/catboost_eurusd_overall.py
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
_PROB_THRESH = 0.55


def rolling_catboost(
    panel: pd.DataFrame,
    feat_cols: list[str],
    window_months: int,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Rolling CatBoost classifier. Returns (long_df, short_df)."""
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

        # CatBoost expects features as-is; scale for stability
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
            rsm=0.6,  # random feature subset per tree
            loss_function="Logloss",
            eval_metric="AUC",
            verbose=False,
            random_seed=42,
            thread_count=4,
        )
        clf.fit(X_train_s, y_train)
        probs = clf.predict_proba(X_test_s)[:, 1]

        mask_long = probs >= _PROB_THRESH
        if mask_long.sum() >= 1:
            long_frames.append(pd.DataFrame({
                "prob": probs[mask_long],
                "act": act_test[mask_long],
                "bucket": pd.to_datetime(bk_test[mask_long]),
                "month": months[i],
            }))

        mask_short = probs <= (1 - _PROB_THRESH)
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


def evaluate_overall(df: pd.DataFrame, label: str, freq: str, wmo: int, direction: str) -> dict:
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
        "label": label, "n": len(df), "mean": net.mean(),
        "t": t, "p": p, "sharpe_est": sharpe_est,
        "pos_years": (yr > 0).sum(), "nyears": len(yr),
        "years_str": f"{(yr > 0).sum()}/{len(yr)}",
        "pos_pct": pos * 100,
        "months_covered": df["month"].nunique() if "month" in df.columns else np.nan,
    }


def evaluate_by_hour(df: pd.DataFrame, label: str, freq: str, wmo: int, direction: str) -> pd.DataFrame:
    """Optional: still show hour breakdown for diagnostics."""
    if df.empty:
        return pd.DataFrame()
    df = df.copy()
    df["hour"] = df["bucket"].dt.hour
    df["year"] = df["bucket"].dt.year
    rows = []
    for hr in sorted(df["hour"].unique()):
        cell = df[df["hour"] == hr]
        if len(cell) < 10:
            continue
        t, p = ttest_1samp(cell["net"], 0) if len(cell) > 2 else (np.nan, np.nan)
        yr = cell.groupby("year")["net"].mean()
        rows.append({
            "sym": _SYMBOL, "freq": freq, "window": wmo, "direction": direction,
            "label": label, "hour": hr, "n": len(cell), "mean": cell["net"].mean(),
            "t": t, "p": p,
            "pos_years": (yr > 0).sum(), "nyears": len(yr),
            "years_str": f"{(yr > 0).sum()}/{len(yr)}",
        })
    return pd.DataFrame(rows)


def main():
    print("=" * 80)
    print(f"CATBOOST OVERALL DIAGNOSTIC — {_SYMBOL}")
    print("Hour is a feature, not a split. CatBoost learns session structure internally.")
    print(f"Freqs: {_FREQS} | Windows: {_WINDOWS}mo | Cost: {_COST}")
    print("=" * 80)

    src = _WORKTREE.parents[2] / f"data/tick_bars/{_SYMBOL}_1m_flow.parquet"
    if not src.exists():
        print(f"Data not found: {src}")
        return

    overall_rows = []
    all_hourly = []

    for freq in _FREQS:
        print(f"\n{'='*60}")
        print(f"FREQUENCY: {freq}")
        print(f"{'='*60}")

        df_1m = pl.read_parquet(src)
        bars = build_freq_bars(df_1m, freq)
        panel = build_panel_interactive(bars, "INTERACT")  # full dummy + interaction features
        if len(panel) < 500:
            continue
        feat_cols = panel["feature_cols"].iloc[0]
        print(f"Feature count: {len(feat_cols)} (includes hour dummies + interactions)")

        for wmo in _WINDOWS:
            long_df, short_df = rolling_catboost(panel, feat_cols, wmo)
            for df, direction in [(long_df, "LONG"), (short_df, "SHORT")]:
                if df.empty:
                    continue
                overall = evaluate_overall(df, f"{freq}_{wmo}mo_{direction}", freq, wmo, direction)
                if overall:
                    overall_rows.append(overall)
                    print(
                        f"  {wmo:2d}mo {direction:6s} n={overall['n']:5d} "
                        f"mean={overall['mean']:+.2f} t={overall['t']:+.2f} p={overall['p']:.4f} "
                        f"sharpe={overall['sharpe_est']:+.2f} {overall['years_str']} pos={overall['pos_pct']:.0f}%"
                    )
                hourly = evaluate_by_hour(df, f"{freq}_{wmo}mo_{direction}", freq, wmo, direction)
                if not hourly.empty:
                    all_hourly.append(hourly)

    if not overall_rows:
        print("\nNo results produced.")
        return

    master = pd.DataFrame(overall_rows)

    # Best by |t|
    print(f"\n{'='*80}")
    print("TOP 10 OVERALL RESULTS (by |t|)")
    print(f"{'='*80}")
    top10 = master.reindex(master["t"].abs().sort_values(ascending=False).index).head(10)
    print(f"{'freq':>4} {'wmo':>3} {'dir':>6} {'n':>5} {'mean':>7} {'t':>6} {'p':>7} {'sharpe':>7} {'years':>6} {'pos':>5}")
    print("-" * 65)
    for _, r in top10.iterrows():
        print(
            f"{r['freq']:>4} {r['window']:>3} {r['direction']:>6} {r['n']:>5} "
            f"{r['mean']:>+7.2f} {r['t']:>+6.2f} {r['p']:>7.4f} "
            f"{r['sharpe_est']:>+7.2f} {r['years_str']:>6} {r['pos_pct']:>4.0f}%"
        )

    # Positive mean + decent t
    pos = master[(master["mean"] > 0) & (master["t"] > 1.0)].sort_values("t", ascending=False)
    if not pos.empty:
        print(f"\n{'='*80}")
        print("PROMISING OVERALL RESULTS (mean > 0, t > 1.0)")
        print(f"{'='*80}")
        for _, r in pos.iterrows():
            print(
                f"{r['freq']} {r['window']}mo {r['direction']} n={r['n']} mean={r['mean']:+.2f} "
                f"t={r['t']:+.2f} p={r['p']:.4f} sharpe={r['sharpe_est']:+.2f} {r['years_str']} pos={r['pos_pct']:.0f}%"
            )

    # Show hourly breakdown for the best overall
    if all_hourly:
        print(f"\n{'='*80}")
        print("HOURLY BREAKDOWN FOR BEST OVERALL CELL")
        print(f"{'='*80}")
        best = master.loc[master["t"].abs().idxmax()]
        matching = pd.concat(all_hourly, ignore_index=True)
        match = matching[
            (matching["freq"] == best["freq"]) &
            (matching["window"] == best["window"]) &
            (matching["direction"] == best["direction"])
        ]
        if not match.empty:
            print(f"Best overall: {best['freq']} {best['window']}mo {best['direction']} t={best['t']:+.2f}")
            print(match.sort_values("t", ascending=False).to_string(index=False))

    # Feature importance for best model
    # (Would require re-fitting on full data — skip for speed, or do a single fit)


if __name__ == "__main__":
    main()
