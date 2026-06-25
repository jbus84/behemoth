"""Directionally-adaptive, per-pair, rolling-window diagnostic across all horizons.

For each (symbol, horizon, window_months):
  - Trains a rolling Ridge on target_z
  - Evaluates BOTH top-q (LONG) and bottom-q (SHORT) on OOS
  - Selects the direction with better t-stat / Sharpe estimate
  - Scores by entry hour

Tests: EURUSD, GBPUSD, USDJPY | 1h, 2h, 3h, 4h | 6/12/18/24mo windows
Includes enhanced features (range, vol_ratio, near_fix, spr_bps).

Usage:
    uv run python scripts/fx_coint/adaptive_direction_diagnostic.py
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
_HORIZONS = ["1h", "2h", "3h", "4h"]
_WINDOWS = [6, 12, 18, 24]
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

        if len(train) < 30 or len(test) < 3:
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
    short_df["net"] = -short_df["act"] - cost  # flip sign for short

    return long_df, short_df


def evaluate(df: pd.DataFrame, label: str, sym: str, freq: str, wmo: int, direction: str) -> pd.DataFrame:
    """Score by entry hour."""
    if df.empty:
        return pd.DataFrame()
    df = df.copy()
    df["hour"] = df["bucket"].dt.hour
    df["year"] = df["bucket"].dt.year
    rows = []
    for hr in sorted(df["hour"].unique()):
        cell = df[df["hour"] == hr]
        if len(cell) < 5:
            continue
        t, p = ttest_1samp(cell["net"], 0) if len(cell) > 2 else (np.nan, np.nan)
        yr = cell.groupby("year")["net"].mean()
        # Sharpe estimate: annualized net / annualized vol
        if len(cell) > 3:
            monthly = cell.groupby(cell["bucket"].dt.to_period("M"))["net"].sum()
            sharpe_est = (monthly.mean() / monthly.std()) * np.sqrt(12) if monthly.std() > 0 else np.nan
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
    print("ADAPTIVE DIRECTION DIAGNOSTIC")
    print("Per-pair, per-horizon, rolling windows, both LONG and SHORT evaluated")
    print(f"Symbols: {_SYMBOLS} | Horizons: {_HORIZONS} | Windows: {_WINDOWS}mo")
    print("=" * 80)

    all_grids = []
    survivor_candidates = []

    for sym in _SYMBOLS:
        src = _WORKTREE.parents[2] / f"data/tick_bars/{sym}_1m_flow.parquet"
        if not src.exists():
            continue
        cost = _COSTS[sym]

        print(f"\n{'='*60}")
        print(f"Symbol: {sym}")
        print(f"{'='*60}")

        for freq in _HORIZONS:
            df_1m = pl.read_parquet(src)
            bars = build_freq_bars(df_1m, freq)
            panel = build_panel_interactive(bars, "ENH")
            if len(panel) < 500:
                continue
            feat_cols = panel["feature_cols"].iloc[0]

            for wmo in _WINDOWS:
                long_df, short_df = rolling_adaptive(panel, feat_cols, cost, wmo)
                long_grid = evaluate(long_df, f"{freq}_{wmo}mo_LONG", sym, freq, wmo, "LONG")
                short_grid = evaluate(short_df, f"{freq}_{wmo}mo_SHORT", sym, freq, wmo, "SHORT")

                for grid in [long_grid, short_grid]:
                    if not grid.empty:
                        all_grids.append(grid)
                        # Capture strong candidates
                        strong = grid[grid["t"].abs() > 1.5]
                        if not strong.empty:
                            survivor_candidates.append(strong)

    if not all_grids:
        print("\nNo grids produced.")
        return

    master = pd.concat(all_grids, ignore_index=True)

    # Rank by |t| globally and show top 20
    top20 = master.reindex(master["t"].abs().sort_values(ascending=False).index).head(20)

    print(f"\n{'='*80}")
    print("TOP 20 CELLS GLOBALLY (by |t|)")
    print(f"{'='*80}")
    print(f"{'sym':>7} {'freq':>4} {'wmo':>3} {'dir':>6} {'hr':>3} {'n':>5} {'mean':>7} {'t':>6} {'p':>7} {'sharpe':>7} {'years':>6}")
    print("-" * 75)
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
            f"hr={best['hour']:02d} n={best['n']} mean={best['mean']:+.2f} "
            f"t={best['t']:+.2f} p={best['p']:.4f} sharpe_est={best['sharpe_est']:+.2f} {best['years_str']}"
        )

    # 1h focus specifically
    print(f"\n{'='*80}")
    print("1H GRID DETAIL (per symbol, all windows, both directions)")
    print(f"{'='*80}")
    h1 = master[master["freq"] == "1h"].sort_values(["sym", "t"], ascending=[True, False])
    for sym in _SYMBOLS:
        sub = h1[h1["sym"] == sym]
        if sub.empty:
            continue
        print(f"\n{sym}:")
        print(f"  {'wmo':>3} {'dir':>6} {'hr':>3} {'n':>5} {'mean':>7} {'t':>6} {'p':>7} {'sharpe':>7} {'years':>6}")
        for _, r in sub.iterrows():
            print(
                f"  {r['window']:>3} {r['direction']:>6} {r['hour']:>3} {r['n']:>5} "
                f"{r['mean']:>+7.2f} {r['t']:>+6.2f} {r['p']:>7.4f} "
                f"{r['sharpe_est']:>+7.2f} {r['years_str']:>6}"
            )

    # Any Sharpe_est > 1.0?
    high_sharpe = master[master["sharpe_est"] > 1.0]
    if not high_sharpe.empty:
        print(f"\n{'='*80}")
        print("HIGH SHARPE ESTIMATES (> 1.0) — treat as exploratory, not validated")
        print(f"{'='*80}")
        for _, r in high_sharpe.sort_values("sharpe_est", ascending=False).iterrows():
            print(
                f"{r['sym']} {r['freq']} {r['window']}mo {r['direction']} hr={r['hour']:02d} "
                f"sharpe_est={r['sharpe_est']:+.2f} t={r['t']:+.2f} p={r['p']:.4f} {r['years_str']} n={r['n']}"
            )
    else:
        print(f"\n{'='*80}")
        print("No cells with estimated Sharpe > 1.0.")
        print(f"{'='*80}")


if __name__ == "__main__":
    main()
