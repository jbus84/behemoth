"""Rolling-window per-symbol diagnostic.

Hypothesis: per-pair models with shorter adaptation windows reveal
regime-specific edges invisible to pooled long-run WFO.

Trains a separate Ridge per symbol on a rolling lookback window,
then predicts the next month. Scores net returns by entry hour.

Lookback windows tested: 6mo, 12mo, 18mo, 24mo.

Usage:
    uv run python scripts/fx_coint/rolling_window_symbol_diagnostic.py
"""
# ruff: noqa: E402
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import polars as pl
from scipy.stats import ttest_1samp
from sklearn.linear_model import Ridge
from sklearn.preprocessing import StandardScaler

_WORKTREE = Path("/Users/danielfisher/repositories/behemoth/.claude/worktrees/feat-pf-15m")
_REPO = Path("/Users/danielfisher/repositories/behemoth")
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

SYMBOLS = ["EURUSD", "GBPUSD", "USDJPY"]
FREQ = "2h"
WINDOW_MONTHS = [6, 12, 18, 24]
ALPHA = 1.0
HOLDOUT_MONTHS = 1  # predict forward 1 month from end of training window
LIQUID_HOURS = list(range(7, 21))

_COST_MAP = {
    "EURUSD": 0.69,
    "GBPUSD": 0.76,
    "USDJPY": 0.67,
}


def rolling_predict(panel: pd.DataFrame, feat_cols: list[str], window_months: int):
    """Generate predictions from rolling monthly retraining.

    Trains on [t-window_months, t), predicts t+1 month.
    Returns DataFrame of selected top predictions with actuals.
    """
    panel = panel.copy().sort_values("bucket").reset_index(drop=True)
    panel["month"] = panel["bucket"].dt.to_period("M")
    months = panel["month"].unique()
    if len(months) < window_months + HOLDOUT_MONTHS + 1:
        return pd.DataFrame()

    frames = []
    # Step through months; train on preceding window_months, predict next
    for i in range(window_months, len(months) - HOLDOUT_MONTHS + 1):
        train_months = months[i - window_months : i]
        test_months = months[i : i + HOLDOUT_MONTHS]

        train = panel[panel["month"].isin(train_months)]
        test = panel[panel["month"].isin(test_months)]

        if len(train) < 30 or len(test) < 3:
            continue

        X_train = train[feat_cols].to_numpy()
        y_train = train["target_z"].to_numpy()
        X_test = test[feat_cols].to_numpy()
        act_test = test["ret_next_bps"].to_numpy()
        bk_test = test["bucket"].to_numpy()

        # Scale on training data only
        sc = StandardScaler().fit(X_train)
        beta = Ridge(alpha=ALPHA).fit(sc.transform(X_train), y_train)
        mu = beta.predict(sc.transform(X_test))

        # Select top 10% of predictions (sparser than 5% to avoid over-selection in small windows)
        q = 0.90
        thresh = np.quantile(mu, q)
        mask = mu >= thresh
        if mask.sum() < 1:
            continue

        df = pd.DataFrame({
            "mu": mu[mask],
            "act": act_test[mask],
            "bucket": pd.to_datetime(bk_test[mask]),
            "train_end": months[i - 1],
        })
        frames.append(df)

    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def evaluate_hourly(pred_df: pd.DataFrame, label: str, sym: str) -> pd.DataFrame:
    pred_df = pred_df.copy()
    pred_df["net"] = pred_df["act"] - _COST_MAP.get(sym, 0.7)
    pred_df["hour"] = pred_df["bucket"].dt.hour
    pred_df["year"] = pred_df["bucket"].dt.year
    pred_df["month"] = pred_df["bucket"].dt.to_period("M")
    rows = []
    for hr in sorted(pred_df["hour"].unique()):
        cell = pred_df[pred_df["hour"] == hr]
        if len(cell) < 5:
            continue
        t, p = ttest_1samp(cell["net"], 0) if len(cell) > 2 else (np.nan, np.nan)
        yr = cell.groupby("year")["net"].mean()
        rows.append({
            "sym": sym,
            "label": label,
            "hour": hr,
            "n": len(cell),
            "mean": cell["net"].mean(),
            "t": t,
            "p": p,
            "pos_years": (yr > 0).sum(),
            "nyears": len(yr),
            "years_str": f"{(yr > 0).sum()}/{len(yr)}",
            "months_covered": cell["month"].nunique(),
        })
    return pd.DataFrame(rows)


def main():
    print("=" * 80)
    print("ROLLING-WINDOW PER-SYMBOL DIAGNOSTIC")
    print(f"Symbols: {SYMBOLS} | Freq: {FREQ} | Windows: {WINDOW_MONTHS}mo")
    print("Train on N months, predict next month, select top 10% per prediction month")
    print("=" * 80)

    all_grids = []

    for sym in SYMBOLS:
        src = _REPO / f"data/tick_bars/{sym}_1m_flow.parquet"
        if not src.exists():
            continue
        df_1m = pl.read_parquet(src)
        bars = build_freq_bars(df_1m, FREQ)
        panel = build_panel_interactive(bars, "BASE")
        if len(panel) < 500:
            print(f"\n{sym}: panel too short ({len(panel)}), skipping")
            continue

        feat_cols = ["r_1", "mom_short", "mom_long", "rvol_24", "hour"]

        print(f"\n{'='*60}")
        print(f"Symbol: {sym}  |  Panel: {len(panel)} rows  |  {panel['bucket'].min()} to {panel['bucket'].max()}")
        print(f"{'='*60}")

        for wmo in WINDOW_MONTHS:
            preds = rolling_predict(panel, feat_cols, wmo)
            if preds.empty:
                print(f"  {wmo:2d}mo: no predictions")
                continue
            print(f"  {wmo:2d}mo: {len(preds)} predictions from {preds['bucket'].dt.to_period('M').nunique()} months")
            grid = evaluate_hourly(preds, f"{wmo}mo", sym)
            if not grid.empty:
                # Show best cell for this window
                best = grid.loc[grid["t"].abs().idxmax()]
                print(f"    Best: {best['hour']:02d}:00  mean={best['mean']:+.2f}  t={best['t']:+.2f}  p={best['p']:.3f}  {best['years_str']}  n={best['n']}")
                all_grids.append(grid)

    if not all_grids:
        print("\nNo grids produced.")
        return

    master = pd.concat(all_grids, ignore_index=True)

    # Summarize any strong cells
    print(f"\n{'='*80}")
    print("ALL STRONG CELLS (|t| > 1.5) across symbols & windows")
    print(f"{'='*80}")
    strong = master[master["t"].abs() > 1.5].sort_values("t", ascending=False)
    if strong.empty:
        print("None.")
    else:
        for _, r in strong.iterrows():
            print(f"  {r['sym']}  {r['label']}  hr={r['hour']:02d}  n={r['n']}  mean={r['mean']:+.2f}  t={r['t']:+.2f}  p={r['p']:.3f}  {r['years_str']}  months={r['months_covered']}")

    # Best per symbol
    print(f"\n{'='*80}")
    print("BEST CELL PER SYMBOL (by |t|)")
    print(f"{'='*80}")
    for sym in SYMBOLS:
        sub = master[master["sym"] == sym]
        if sub.empty:
            continue
        best = sub.loc[sub["t"].abs().idxmax()]
        print(f"  {sym}  {best['label']}  hr={best['hour']:02d}  n={best['n']}  mean={best['mean']:+.2f}  t={best['t']:+.2f}  p={best['p']:.3f}  {best['years_str']}")


if __name__ == "__main__":
    main()
