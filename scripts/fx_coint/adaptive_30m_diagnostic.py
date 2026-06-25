"""Adaptive direction diagnostic at 30m frequency.

Same methodology as adaptive_direction_diagnostic.py but focused on 30m
horizon with per-pair rolling windows and both LONG/SHORT evaluation.

Usage:
    uv run python scripts/fx_coint/adaptive_30m_diagnostic.py
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
_FREQ = "30m"
_WINDOWS = [3, 6, 12, 18]
_COSTS = {"EURUSD": 0.69, "GBPUSD": 0.76, "USDJPY": 0.67}
_Q = 0.90
_ALPHA = 1.0


def rolling_adaptive(
    panel: pd.DataFrame,
    feat_cols: list[str],
    cost: float,
    window_months: int,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Generate predictions from rolling monthly retraining.
    Returns (long_results, short_results) DataFrames.
    """
    panel = panel.copy().sort_values("bucket").reset_index(drop=True)
    panel["month"] = panel["bucket"].dt.to_period("M")
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

        X_train = train[feat_cols].to_numpy()
        y_train = train["target_z"].to_numpy()
        X_test = test[feat_cols].to_numpy()
        act_test = test["ret_next_bps"].to_numpy()
        bk_test = test["bucket"].to_numpy()

        sc = StandardScaler().fit(X_train)
        beta = Ridge(alpha=_ALPHA).fit(sc.transform(X_train), y_train)
        mu = beta.predict(sc.transform(X_test))

        # LONG: top quantile
        thresh_long = np.quantile(mu, _Q)
        mask_long = mu >= thresh_long
        if mask_long.sum() >= 1:
            long_frames.append(pd.DataFrame({
                "act": act_test[mask_long],
                "bucket": pd.to_datetime(bk_test[mask_long]),
                "month": months[i],
            }))

        # SHORT: bottom quantile
        thresh_short = np.quantile(mu, 1 - _Q)
        mask_short = mu <= thresh_short
        if mask_short.sum() >= 1:
            short_frames.append(pd.DataFrame({
                "act": act_test[mask_short],
                "bucket": pd.to_datetime(bk_test[mask_short]),
                "month": months[i],
            }))

    if not long_frames:
        return pd.DataFrame(), pd.DataFrame()

    long_df = pd.concat(long_frames, ignore_index=True)
    short_df = pd.concat(short_frames, ignore_index=True)

    # Net returns
    long_df["net"] = long_df["act"] - cost
    short_df["net"] = -short_df["act"] - cost

    return long_df, short_df


def evaluate(df: pd.DataFrame, label: str, sym: str, freq: str, wmo: int, direction: str) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame()
    df = df.copy()
    df["hour"] = df["bucket"].dt.hour
    df["minute"] = df["bucket"].dt.minute
    df["hm"] = df["hour"].astype(str) + ":" + df["minute"].astype(str).str.zfill(2)
    df["year"] = df["bucket"].dt.year
    rows = []
    # Group by hour (ignore minute for now)
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
            "sym": sym,
            "freq": freq,
            "window": wmo,
            "direction": direction,
            "label": label,
            "hour": hr,
            "n": len(cell),
            "mean": cell["net"].mean(),
            "t": t,
            "p": p,
            "sharpe_est": sharpe_est,
            "pos_years": (yr > 0).sum(),
            "nyears": len(yr),
            "years_str": f"{(yr > 0).sum()}/{len(yr)}",
            "months_covered": cell["month"].nunique() if "month" in cell.columns else np.nan,
        })
    return pd.DataFrame(rows)


def main():
    print("=" * 80)
    print("ADAPTIVE DIRECTION DIAGNOSTIC — 30m FREQUENCY")
    print("Per-pair, rolling windows, both LONG and SHORT evaluated")
    print(f"Symbols: {_SYMBOLS} | Freq: {_FREQ} | Windows: {_WINDOWS}mo")
    print("=" * 80)

    all_grids = []

    for sym in _SYMBOLS:
        src = _WORKTREE.parents[2] / f"data/tick_bars/{sym}_1m_flow.parquet"
        if not src.exists():
            continue
        cost = _COSTS[sym]

        print(f"\n{'='*60}")
        print(f"Symbol: {sym}")
        print(f"{'='*60}")

        df_1m = pl.read_parquet(src)
        bars = build_freq_bars(df_1m, _FREQ)
        panel = build_panel_interactive(bars, "ENH")
        if len(panel) < 500:
            print(f"  Panel too short ({len(panel)}), skipping")
            continue
        feat_cols = panel["feature_cols"].iloc[0]

        for wmo in _WINDOWS:
            long_df, short_df = rolling_adaptive(panel, feat_cols, cost, wmo)
            long_grid = evaluate(long_df, f"{_FREQ}_{wmo}mo_LONG", sym, _FREQ, wmo, "LONG")
            short_grid = evaluate(short_df, f"{_FREQ}_{wmo}mo_SHORT", sym, _FREQ, wmo, "SHORT")

            for grid in [long_grid, short_grid]:
                if not grid.empty:
                    all_grids.append(grid)
                    # Show best cell for this window
                    best = grid.loc[grid["t"].abs().idxmax()]
                    print(f"  {wmo:2d}mo {best['direction']:6s} hr={best['hour']:02d} n={best['n']} mean={best['mean']:+.2f} t={best['t']:+.2f} p={best['p']:.3f} sharpe={best['sharpe_est']:+.2f} {best['years_str']}")

    if not all_grids:
        print("\nNo grids produced.")
        return

    master = pd.concat(all_grids, ignore_index=True)

    # Rank by |t| globally
    top20 = master.reindex(master["t"].abs().sort_values(ascending=False).index).head(20)

    print(f"\n{'='*80}")
    print("TOP 20 CELLS GLOBALLY (by |t|)")
    print(f"{'='*80}")
    print(f"{'sym':>7} {'wmo':>3} {'dir':>6} {'hr':>3} {'n':>5} {'mean':>7} {'t':>6} {'p':>7} {'sharpe':>7} {'years':>6}")
    print("-" * 75)
    for _, r in top20.iterrows():
        print(
            f"{r['sym']:>7} {r['window']:>3} {r['direction']:>6} {r['hour']:>3} {r['n']:>5} "
            f"{r['mean']:>+7.2f} {r['t']:>+6.2f} {r['p']:>7.4f} "
            f"{r['sharpe_est']:>+7.2f} {r['years_str']:>6}"
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
            f"{sym:7s} {best['window']:>3}mo {best['direction']:>6} hr={best['hour']:02d} n={best['n']} "
            f"mean={best['mean']:+.2f} t={best['t']:+.2f} p={best['p']:.4f} sharpe_est={best['sharpe_est']:+.2f} {best['years_str']}"
        )

    # Positive cells with decent t-stat
    print(f"\n{'='*80}")
    print("PROMISING CELLS (t > 1.5, any direction)")
    print(f"{'='*80}")
    prom = master[master["t"].abs() > 1.5].sort_values("t", ascending=False)
    if prom.empty:
        print("None.")
    else:
        for _, r in prom.iterrows():
            print(
                f"{r['sym']} {r['window']}mo {r['direction']} hr={r['hour']:02d} "
                f"mean={r['mean']:+.2f} t={r['t']:+.2f} p={r['p']:.4f} sharpe={r['sharpe_est']:+.2f} {r['years_str']} n={r['n']}"
            )


if __name__ == "__main__":
    main()
