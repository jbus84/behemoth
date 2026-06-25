"""Deep assessment of entry-hour-conditioned tail cells.

Applies:
  – day-clustered t (absorbs cross-pair same-day correlation)
  – Benjamini–Hochberg FDR across the full hour×horizon grid
  – per-pair attribution for surviving cells
  – per-hour liquidity audit (tick-rate reality check)

Usage:
    uv run python scripts/fx_coint/assess_entry_hour_candidates.py
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

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import scripts.fx_coint.reg_signal_hunt as rsh
from scripts.fx_coint.reg_signal_hunt import (
    FEATURE_COLS,
    build_panel,
)

rsh.FREQ_MINUTES.update({"15m": 15, "30m": 30})

# Candidates from prior exploration
HORIZONS = ["1h", "2h", "3h", "4h"]
# Liquid FX hours (07:00 – 21:00 UTC); skip overnight illiquidity
HOURS = list(range(7, 22))

# Corrected Razor commission-dominated costs (spread + $3.5/side commission)
# Spread in pips reflects liquid-hour executable, NOT Dukascopy feed spread
_COMMISSION_BPS = 0.60
_SPREAD_PIP = {
    "EURUSD": 0.1,
    "USDJPY": 0.1,
    "GBPUSD": 0.2,
    "AUDUSD": 0.1,
    "USDCAD": 0.3,
    "USDCHF": 0.3,
}
_PX = {
    "EURUSD": 1.08,
    "USDJPY": 150.0,
    "GBPUSD": 1.27,
    "AUDUSD": 0.65,
    "USDCAD": 1.36,
    "USDCHF": 0.89,
}


def razor_cost(sym: str) -> float:
    pip = 0.01 if sym.endswith("JPY") else 0.0001
    spr_bps = (_SPREAD_PIP[sym] * pip / _PX[sym]) * 1e4
    return _COMMISSION_BPS + spr_bps


def day_clustered_t(series: pd.Series, bucket: pd.Series) -> tuple[float, float, int]:
    """t-test on per-date mean; clusters same-day correlation across pairs."""
    daily = series.groupby(bucket.dt.date).mean()
    daily = daily[np.isfinite(daily)]
    if len(daily) < 3:
        return np.nan, np.nan, 0
    t, p = ttest_1samp(daily, 0)
    return float(t), float(p), len(daily)


def load_panel(sym: str, freq: str) -> pd.DataFrame | None:
    src = _REPO_ROOT / f"data/tick_bars/{sym}_1m_flow.parquet"
    if not src.exists():
        return None
    panel = build_panel(rsh.build_freq_bars(pl.read_parquet(src), freq))
    return panel if len(panel) >= 200 else None


def wfo_predictions(panel: pd.DataFrame, q: float = 0.95, n_folds: int = 5) -> pd.DataFrame:
    """Return DataFrame of top-q predictions with actual returns and timestamps."""
    n = len(panel)
    edges = np.linspace(int(n * 0.5), n, n_folds + 1).astype(int)
    X = panel[FEATURE_COLS].to_numpy()
    yz = panel["target_z"].to_numpy()
    act = panel["ret_next_bps"].to_numpy()
    bk = panel["bucket"].to_numpy()
    frames = []
    for k in range(n_folds):
        split = edges[k]
        lo, hi = edges[k] + 1, edges[k + 1]
        if hi - lo < 5 or split < 30:
            continue
        sc = StandardScaler().fit(X[:split])
        mu = Ridge(alpha=1.0).fit(
            sc.transform(X[:split]), yz[:split]
        ).predict(sc.transform(X[lo:hi]))
        df = pd.DataFrame(
            {"mu": mu, "act": act[lo:hi], "bucket": pd.to_datetime(bk[lo:hi])}
        )
        df = df[df["mu"] >= df["mu"].quantile(q)]
        frames.append(df)
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def build_universe(universe: list[str], freq: str, cost_map: dict[str, float]) -> pd.DataFrame:
    frames = []
    for sym in universe:
        p = load_panel(sym, freq)
        if p is None:
            continue
        d = wfo_predictions(p)
        if d.empty:
            continue
        d["net"] = d["act"] - cost_map[sym]
        d["sym"] = sym
        d["hour"] = d["bucket"].dt.hour
        d["year"] = d["bucket"].dt.year
        frames.append(d)
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def bh_fdr(pvals: pd.Series, alpha: float = 0.05) -> pd.Series:
    """Benjamini–Hochberg FDR correction; returns boolean mask of rejections."""
    m = len(pvals)
    if m == 0:
        return pd.Series(False, index=pvals.index)
    sorted_p = pvals.sort_values()
    thresholds = (np.arange(1, m + 1) / m) * alpha
    # Find largest i where p_i <= threshold_i
    valid = sorted_p <= thresholds
    if not valid.any():
        return pd.Series(False, index=pvals.index)
    valid[::-1].idxmax()  # last True when reversed = largest valid index
    # Actually easier:
    sorted_p = pvals.sort_values()
    ranks = np.arange(1, len(sorted_p) + 1)
    threshold = (ranks / len(sorted_p)) * alpha
    # Vectorized
    rejections = pd.Series(False, index=pvals.index)
    # Find critical value
    below = sorted_p.values <= threshold
    if not below.any():
        return rejections
    crit_rank = np.where(below)[0][-1]  # largest rank satisfying condition
    crit_p = sorted_p.iloc[crit_rank]
    rejections = pvals <= crit_p
    return rejections


def per_pair_attribution(cell_df: pd.DataFrame) -> pd.DataFrame:
    """Year×pair stability table for a single cell."""
    rows = []
    for sym, g in cell_df.groupby("sym"):
        for yr, gy in g.groupby("year"):
            net = gy["net"].to_numpy()
            t, p = ttest_1samp(net, 0) if len(net) > 2 else (np.nan, np.nan)
            rows.append(
                {
                    "sym": sym,
                    "year": yr,
                    "n": len(gy),
                    "mean": net.mean(),
                    "t": t,
                    "p": p,
                    "pos_pct": (gy["act"] > 0).mean() * 100,
                }
            )
    return pd.DataFrame(rows)


def hour_liquidity(universe: list[str], freq: str) -> pd.DataFrame:
    """Mean ticks-per-minute by hour for cost realism."""
    rows = []
    for sym in universe:
        src = _REPO_ROOT / f"data/tick_bars/{sym}_1m_flow.parquet"
        if not src.exists():
            continue
        df = pl.read_parquet(src).to_pandas()
        df["bucket"] = pd.to_datetime(df["bucket"])
        df["hour"] = df["bucket"].dt.hour
        tick_rate = df.groupby("hour")["n_ticks"].mean().reset_index()
        tick_rate["sym"] = sym
        rows.append(tick_rate)
    if not rows:
        return pd.DataFrame()
    all_rates = pd.concat(rows, ignore_index=True)
    return all_rates.groupby("hour")["n_ticks"].mean().reset_index()


def main():
    universe = ["EURUSD", "GBPUSD", "USDJPY"]
    cost_map = {s: razor_cost(s) for s in universe}
    print("Razor costs (bps RT):", {s: round(v, 2) for s, v in cost_map.items()})

    # --- Build master grid -------------------------------------------------
    rows = []
    for freq in HORIZONS:
        df = build_universe(universe, freq, cost_map)
        if df.empty:
            continue
        for hr in HOURS:
            cell = df[df["hour"] == hr]
            if len(cell) < 10:
                continue
            t, p, nd = day_clustered_t(cell["net"], cell["bucket"])
            yr_means = cell.groupby("year")["net"].mean()
            rows.append(
                {
                    "freq": freq,
                    "hour": hr,
                    "n": len(cell),
                    "mean": cell["net"].mean(),
                    "t": t,
                    "p": p,
                    "ndays": nd,
                    "pos_years": (yr_means > 0).sum(),
                    "nyears": len(yr_means),
                    "years_pos_pct": f"{(yr_means > 0).sum()}/{len(yr_means)}",
                }
            )
    grid = pd.DataFrame(rows)
    if grid.empty:
        print("No grid cells produced.")
        return

    # --- BH-FDR correction ------------------------------------------------
    grid["reject_bh"] = bh_fdr(grid["p"], alpha=0.10)
    grid_sorted = grid.sort_values("p").reset_index(drop=True)

    print("\n" + "=" * 80)
    print(f"ENTRY-HOUR GRID: {len(grid)} cells  ({len(HORIZONS)} horizons × {len(HOURS)} hours)")
    print(f"BH-FDR (α=0.10) rejects: {grid['reject_bh'].sum()}")
    print("=" * 80)
    print(f"{'freq':>5} {'hr':>3} {'n':>5} {'mean':>7} {'t':>6} {'p':>7} {'ndays':>5} {'years':>6} {'BH':>3}")
    print("-" * 60)
    for _, r in grid_sorted.iterrows():
        bh = "*" if r["reject_bh"] else " "
        print(
            f"{r['freq']:>5} {r['hour']:>3} {r['n']:>5} {r['mean']:>+7.2f} "
            f"{r['t']:>+6.2f} {r['p']:>7.4f} {r['ndays']:>5} {r['years_pos_pct']:>6} {bh:>3}"
        )

    # --- Deep dive on survivors -------------------------------------------
    survivors = grid_sorted[grid_sorted["reject_bh"]].copy()
    if survivors.empty:
        print("\nNo cells survive BH-FDR at α=0.10.")
    else:
        print("\n" + "=" * 80)
        print("SURVIVORS — per-pair attribution")
        print("=" * 80)
        for _, surv in survivors.iterrows():
            freq = surv["freq"]
            hr = surv["hour"]
            df = build_universe(universe, freq, cost_map)
            cell = df[df["hour"] == hr]
            print(f"\n>>> {freq} @ {hr:02d}:00  mean={surv['mean']:+.2f}  p={surv['p']:.4f}  n={surv['n']}")
            attr = per_pair_attribution(cell)
            if not attr.empty:
                print(attr.to_string(index=False))

    # --- Candidate highlights (top 5 by |t|, regardless of BH) ------------
    print("\n" + "=" * 80)
    print("TOP 5 BY |t| (candidates for further scrutiny)")
    print("=" * 80)
    top5 = grid.reindex(grid["t"].abs().sort_values(ascending=False).index).head(5)
    for _, r in top5.iterrows():
        freq = r["freq"]
        hr = r["hour"]
        df = build_universe(universe, freq, cost_map)
        cell = df[df["hour"] == hr]
        yr_means = cell.groupby("year")["net"].mean().round(2).tolist()
        print(
            f"{freq} @ {hr:02d}:00  mean={r['mean']:+.2f}  t={r['t']:+.2f}  "
            f"p={r['p']:.4f}  years={r['years_pos_pct']}  yearly_means={yr_means}"
        )

    # --- Liquidity audit for cost realism ----------------------------------
    print("\n" + "=" * 80)
    print("LIQUIDITY AUDIT (ticks/min, pooled 3 pairs)")
    print("=" * 80)
    liq = hour_liquidity(universe, "1h")
    for _, r in liq.iterrows():
        hr = int(r["hour"])
        note = ""
        if r["n_ticks"] < 50:
            note = "  <-- THIN (cost likely understated)"
        elif r["n_ticks"] > 200:
            note = "  <-- LIQUID"
        print(f"  {hr:02d}:00  {r['n_ticks']:>6.0f} ticks/min{note}")


if __name__ == "__main__":
    main()
