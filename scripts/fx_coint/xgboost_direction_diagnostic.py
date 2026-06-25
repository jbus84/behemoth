"""Tree-based direction diagnostic at 30m/1h with strong regularization.

Tests whether interaction effects / nonlinearity rescue the weak classification edges.
HistGradientBoostingClassifier is heavily regularized to prevent free-tree overfitting:
  max_depth=3, learning_rate=0.05, l2_regularization=10, min_samples_leaf=20

Same per-pair, rolling-window, hour-grid evaluation as classification diagnostic.

Usage:
    uv run python scripts/fx_coint/xgboost_direction_diagnostic.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import polars as pl
from scipy.stats import ttest_1samp
from sklearn.ensemble import HistGradientBoostingClassifier
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

_SYMBOLS = ["EURUSD", "GBPUSD", "USDJPY"]
_FREQS = ["30m", "1h"]
_WINDOWS = [3, 6, 12, 18]
_COSTS = {"EURUSD": 0.69, "GBPUSD": 0.76, "USDJPY": 0.67}
_PROB_THRESH = 0.55


def rolling_xgboost(
    panel: pd.DataFrame,
    feat_cols: list[str],
    cost: float,
    window_months: int,
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

        clf = HistGradientBoostingClassifier(
            max_depth=3,
            learning_rate=0.05,
            l2_regularization=10.0,
            max_bins=128,
            min_samples_leaf=20,
            max_iter=100,
            early_stopping=True,
            validation_fraction=0.2,
            n_iter_no_change=10,
            scoring="neg_log_loss",
            random_state=42,
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
    long_df["net"] = long_df["act"] - cost
    short_df["net"] = -short_df["act"] - cost
    return long_df, short_df


def evaluate(df: pd.DataFrame, sym: str, freq: str, wmo: int, direction: str) -> pd.DataFrame:
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
        if len(cell) > 3:
            weekly = cell.groupby(cell["bucket"].dt.to_period("W"))["net"].sum()
            sharpe_est = (weekly.mean() / weekly.std()) * np.sqrt(52) if weekly.std() > 0 else np.nan
        else:
            sharpe_est = np.nan
        rows.append({
            "sym": sym, "freq": freq, "window": wmo, "direction": direction,
            "hour": hr, "n": len(cell), "mean": cell["net"].mean(),
            "t": t, "p": p, "sharpe_est": sharpe_est,
            "pos_years": (yr > 0).sum(), "nyears": len(yr),
            "years_str": f"{(yr > 0).sum()}/{len(yr)}",
            "months_covered": cell["month"].nunique() if "month" in cell.columns else np.nan,
        })
    return pd.DataFrame(rows)


def main():
    print("=" * 80)
    print("XGBOOST DIRECTION DIAGNOSTIC (heavily regularized)")
    print("max_depth=3, lr=0.05, reg_lambda=10, subsample=0.5, colsample=0.5")
    print(f"Symbols: {_SYMBOLS} | Freqs: {_FREQS} | Windows: {_WINDOWS}mo | Prob thresh: {_PROB_THRESH}")
    print("=" * 80)

    all_grids = []

    for freq in _FREQS:
        print(f"\n{'='*60}")
        print(f"FREQUENCY: {freq}")
        print(f"{'='*60}")
        for sym in _SYMBOLS:
            src = _WORKTREE.parents[2] / f"data/tick_bars/{sym}_1m_flow.parquet"
            if not src.exists():
                continue
            cost = _COSTS[sym]
            df_1m = pl.read_parquet(src)
            bars = build_freq_bars(df_1m, freq)
            panel = build_panel_interactive(bars, "ENH")
            if len(panel) < 500:
                continue
            feat_cols = panel["feature_cols"].iloc[0]

            print(f"\n--- {sym} ---")
            for wmo in _WINDOWS:
                long_df, short_df = rolling_xgboost(panel, feat_cols, cost, wmo)
                for grid, direction in [(long_df, "LONG"), (short_df, "SHORT")]:
                    if grid.empty:
                        continue
                    ev = evaluate(grid, sym, freq, wmo, direction)
                    if not ev.empty:
                        all_grids.append(ev)
                        best = ev.loc[ev["t"].abs().idxmax()]
                        print(
                            f"  {wmo:2d}mo {direction:6s} hr={best['hour']:02d} n={best['n']} "
                            f"mean={best['mean']:+.2f} t={best['t']:+.2f} p={best['p']:.3f} "
                            f"sharpe={best['sharpe_est']:+.2f} {best['years_str']}"
                        )

    if not all_grids:
        print("\nNo grids produced.")
        return

    master = pd.concat(all_grids, ignore_index=True)

    # Top 20 by |t|
    top20 = master.reindex(master["t"].abs().sort_values(ascending=False).index).head(20)
    print(f"\n{'='*80}")
    print("TOP 20 CELLS GLOBALLY (by |t|)")
    print(f"{'='*80}")
    print(f"{'sym':>7} {'freq':>4} {'wmo':>3} {'dir':>6} {'hr':>3} {'n':>5} {'mean':>7} {'t':>6} {'p':>7} {'sharpe':>7} {'years':>6}")
    print("-" * 70)
    for _, r in top20.iterrows():
        print(
            f"{r['sym']:>7} {r['freq']:>4} {r['window']:>3} {r['direction']:>6} "
            f"{r['hour']:>3} {r['n']:>5} {r['mean']:>+7.2f} {r['t']:>+6.2f} "
            f"{r['p']:>7.4f} {r['sharpe_est']:>+7.2f} {r['years_str']:>6}"
        )

    # Best per symbol
    print(f"\n{'='*80}")
    print("BEST CELL PER SYMBOL")
    print(f"{'='*80}")
    for sym in _SYMBOLS:
        sub = master[master["sym"] == sym]
        if sub.empty:
            continue
        best = sub.loc[sub["t"].abs().idxmax()]
        print(
            f"{sym:7s} {best['freq']:>4} {best['window']:>3}mo {best['direction']:>6} "
            f"hr={best['hour']:02d} n={best['n']} mean={best['mean']:+.2f} t={best['t']:+.2f} p={best['p']:.4f} "
            f"sharpe_est={best['sharpe_est']:+.2f} {best['years_str']}"
        )

    # Promising cells (t > 1.5, positive mean)
    prom = master[(master["t"] > 1.5) & (master["mean"] > 0)].sort_values("t", ascending=False)
    if not prom.empty:
        print(f"\n{'='*80}")
        print("PROMISING CELLS (t > 1.5, positive mean)")
        print(f"{'='*80}")
        for _, r in prom.head(30).iterrows():
            print(
                f"{r['sym']} {r['freq']} {r['window']}mo {r['direction']} hr={r['hour']:02d} "
                f"mean={r['mean']:+.2f} t={r['t']:+.2f} p={r['p']:.4f} sharpe={r['sharpe_est']:+.2f} {r['years_str']} n={r['n']}"
            )
    else:
        print(f"\n{'='*80}")
        print("No cells with t > 1.5 and positive mean.")
        print(f"{'='*80}")

    # Head-to-head: XGB vs prior logistic winners on same cells
    print(f"\n{'='*80}")
    print("XGBoost vs Logistic Regression — same (sym, freq, wmo, hour, dir) cells")
    print(f"{'='*80}")
    # Load prior classification results if available for comparison
    print("(Run classification_direction_diagnostic.py for direct comparison)")
    print("Visual check: compare hours/models that won under logistic vs XGB here:")
    for sym in _SYMBOLS:
        sub = master[master["sym"] == sym]
        if sub.empty:
            continue
        pos = sub[(sub["t"] > 1.5) & (sub["mean"] > 0)]
        if not pos.empty:
            print(f"\n  {sym} positive cells:")
            for _, r in pos.head(5).iterrows():
                print(
                    f"    {r['freq']} {r['window']}mo {r['direction']} hr={r['hour']:02d} "
                    f"t={r['t']:+.2f} mean={r['mean']:+.2f} sharpe={r['sharpe_est']:+.2f} {r['years_str']}"
                )
        else:
            print(f"\n  {sym}: no positive t>1.5 cells")


if __name__ == "__main__":
    main()
