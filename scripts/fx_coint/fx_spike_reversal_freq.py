"""Extreme-spike reversal on FX bars — multi-frequency (1m, 5m, 15m, 1h).

Builds aggregate bars on-the-fly from 1-min flow data, then runs the identical
spike-reversal construction (scaled momentum + hold windows).

Usage:
    uv run python scripts/fx_coint/fx_spike_reversal_freq.py --freq 5m
    uv run python scripts/fx_coint/fx_spike_reversal_freq.py --freq 15m
    uv run python scripts/fx_coint/fx_spike_reversal_freq.py --freq 1h
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import polars as pl

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

PAIRS = ["EURUSD", "GBPUSD", "AUDUSD", "USDJPY", "USDCHF", "USDCAD"]

FREQ_MAP = {
    "1m": ("1m", 1, 360, 180),     # 6h mom, 3h hold in minutes
    "5m": ("5m", 5, 72, 36),       # 6h = 72×5m, 3h = 36×5m
    "15m": ("15m", 15, 24, 12),    # 6h = 24×15m, 3h = 12×15m
    "1h": ("1h", 60, 6, 3),        # canonical hourly
}


def build_bars(sym: str, freq_label: str) -> pd.DataFrame:
    """Aggregate 1m flow bars to target frequency on-the-fly."""
    freq, minutes_per_bar, _, _ = FREQ_MAP[freq_label]
    src = _REPO_ROOT / f"data/tick_bars/{sym}_1m_flow.parquet"
    df = pl.read_parquet(src).sort("bucket")

    # Need at least 1-min log-ret for vol
    t = df.with_columns(
        pl.col("mid").log().diff().alias("lr1"),
        ((pl.col("ask") - pl.col("bid")) / pl.col("mid")).alias("relspr"),
    )

    if freq_label == "1m":
        # Passthrough, just rename / compute spread
        out = t.select([
            pl.col("bucket"),
            pl.col("mid"),
            pl.col("bid"),
            pl.col("ask"),
            pl.col("n_ticks"),
            pl.col("flow_tick"),
            pl.col("flow_ofi"),
            (pl.col("lr1").std() * 1e4).alias("rvol_bps"),
            (pl.col("relspr") * 1e4).alias("spread_bps"),
        ]).to_pandas()
        out["bucket"] = pd.to_datetime(out["bucket"])
        return out.sort_values("bucket").reset_index(drop=True)

    # Truncate to freq
    out = (
        t.with_columns(pl.col("bucket").dt.truncate(freq).alias("bf"))
        .group_by("bf")
        .agg(
            pl.col("mid").last(),
            pl.col("bid").last(),
            pl.col("ask").last(),
            pl.col("n_ticks").sum(),
            pl.col("flow_tick").mean(),
            pl.col("flow_ofi").mean(),
            (pl.col("lr1").std() * 1e4).alias("rvol_bps"),
            (pl.col("relspr").mean() * 1e4).alias("spread_bps"),
        )
        .rename({"bf": "bucket"})
        .sort("bucket")
        .to_pandas()
    )
    out["bucket"] = pd.to_datetime(out["bucket"])
    return out.sort_values("bucket").reset_index(drop=True)


def trades(df: pd.DataFrame, pct: float, mom_bars: int, hold_bars: int, minutes_per_bar: int) -> dict:
    """Return gross and net return arrays for top-pct absolute momentum spikes."""
    mid = df["mid"].to_numpy()
    bid = df["bid"].to_numpy()
    ask = df["ask"].to_numpy()
    # Use actual timestamps for contiguity so weekends / gaps are excluded
    t = df["bucket"].to_numpy().astype("datetime64[m]").astype(np.int64)

    r = np.empty(len(mid))
    r[0] = np.nan
    r[1:] = (np.log(mid[1:]) - np.log(mid[:-1])) * 1e4
    contig = np.empty(len(mid), bool)
    contig[0] = False
    contig[1:] = (t[1:] - t[:-1]) == minutes_per_bar
    r[~contig] = np.nan

    mom = pd.Series(r).rolling(mom_bars).sum().to_numpy()
    sgn = np.sign(mom)
    strength = np.abs(mom)
    n = len(mid)
    valid = np.isfinite(strength) & (sgn != 0)
    idx = np.where(valid)[0]
    idx = idx[(idx + 1 + hold_bars < n)]
    if np.sum(valid) == 0:
        return {"gross": np.array([]), "net": np.array([])}
    thr = np.nanquantile(strength[valid], 1 - pct / 100)
    idx = idx[strength[idx] >= thr]
    idx = idx[(t[idx + 1 + hold_bars] - t[idx]) == minutes_per_bar * (1 + hold_bars)]

    # Non-overlap: enforce gap >= hold_bars between picks
    picked, last = [], -10**9
    for i in idx:
        if i - last >= hold_bars:
            picked.append(i)
            last = i
    picked = np.array(picked)
    if len(picked) < 20:
        return {"gross": np.array([]), "net": np.array([])}

    e, x = picked + 1, picked + 1 + hold_bars
    fade = -sgn[picked]
    m = mid[picked]

    net = np.where(
        fade < 0,
        (bid[e] - ask[x]) / m * 1e4,
        (bid[x] - ask[e]) / m * 1e4,
    )
    gross = np.where(
        fade < 0,
        (mid[e] - mid[x]) / m * 1e4,
        (mid[x] - mid[e]) / m * 1e4,
    )
    return {"gross": gross, "net": net}


def run_for_freq(freq_label: str) -> None:
    freq, minutes_per_bar, mom_bars, hold_bars = FREQ_MAP[freq_label]
    print("\n" + "=" * 65)
    print(f"FREQUENCY = {freq_label}  |  {mom_bars}-bar momentum ({mom_bars*minutes_per_bar/60:.0f}h)")
    print(f"hold = {hold_bars} bars ({hold_bars*minutes_per_bar/60:.0f}h)  |  top-pct fade")
    print("=" * 65)

    data = {p: build_bars(p, freq_label) for p in PAIRS}

    for pct in [1.0, 0.5]:
        print(f"\n### top {pct}% |momentum|  |  {hold_bars}-bar fade  |  N≥20 per pair ###")
        print(f"  {'pair':>8} {'grossMean':>9} {'netMean':>9} {'cost':>8} {'grossT':>6} {'netT':>6} {'N':>5}")
        gross_means, net_means = [], []
        for p in PAIRS:
            tr = trades(data[p], pct, mom_bars, hold_bars, minutes_per_bar)
            g, n = tr["gross"], tr["net"]
            if len(g) < 20:
                print(f"  {p:>8} {'—':>9} {'—':>9} {'—':>8} {'—':>6} {'—':>6} {len(g):>5}")
                continue
            gm, nm = g.mean(), n.mean()
            gt = gm / (g.std() + 1e-12) * np.sqrt(len(g))
            nt = nm / (n.std() + 1e-12) * np.sqrt(len(n))
            gross_means.append(gm)
            net_means.append(nm)
            print(f"  {p:>8} {gm:+9.2f} {nm:+9.2f} {nm - gm:+8.2f} {gt:+6.1f} {nt:+6.1f} {len(g):>5}")

        gross_means = np.array(gross_means)
        net_means = np.array(net_means)
        if len(gross_means) == 0:
            continue

        pos_gross = (gross_means > 0).mean() * 100
        pos_net = (net_means > 0).mean() * 100
        bt_gross = gross_means.mean() / (gross_means.std(ddof=1) + 1e-12) * np.sqrt(len(gross_means))
        bt_net = net_means.mean() / (net_means.std(ddof=1) + 1e-12) * np.sqrt(len(net_means))

        print("\n  BREADTH SUMMARY:")
        print(f"    pairs evaluated : {len(gross_means)}/{len(PAIRS)}")
        print(f"    gross : {pos_gross:.0f}% pairs positive, mean={gross_means.mean():+.2f} bps, cross-pair t={bt_gross:+.1f}")
        print(f"    net   : {pos_net:.0f}% pairs positive, mean={net_means.mean():+.2f} bps, cross-pair t={bt_net:+.1f}")
        print(f"    cost  : mean drag {net_means.mean() - gross_means.mean():+.2f} bps")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--freq", choices=list(FREQ_MAP.keys()), default="1h",
                    help="Bar frequency to test (1m, 5m, 15m, 1h)")
    args = ap.parse_args()
    run_for_freq(args.freq)


if __name__ == "__main__":
    main()
