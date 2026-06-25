"""Lagged-feature IC contribution (1000tick, bounce-free).

For each feature type we add lags L in {0,1,2,3,5,10} bars and assess:
  - RAW pooled IC of each lag vs the target
  - PARTIAL IC of each lag controlling for lag-0 (does the lag carry NEW info, or
    is it just autocorrelation of the lag-0 signal?)
Targets: 1-bar (microstructure regime) and 30-bar triple-barrier (reversion regime).
Pooled over 5 ex-JPY majors; sign/5. No t-stats.

Usage: uv run python scripts/fx_coint/lagged_feature_ic.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats
from scipy.signal import fftconvolve

sys.path.insert(0, str(Path(__file__).resolve().parent))
from triple_barrier import triple_barrier_core  # noqa: E402

DATA = "/Users/danielfisher/repositories/behemoth/data/tick_bars"
POOL = ["AUDUSD", "EURUSD", "GBPUSD", "USDCAD", "USDCHF"]
SUFFIX = "1000tick"
LAGS = [0, 1, 2, 3, 5, 10]
N_TB = 30
N_EVENTS = 40000
FEATS = ["ffd_0.1", "pxdev_96h", "mom_1bar", "mom_10bar", "intra_bar_mom", "hl_pos_frac"]


def ffd01(logp, bph):
    width = max(int(480 * bph), 50)
    w = [1.0]
    for k in range(1, width):
        w.append(-w[-1] * (0.1 - k + 1) / k)
    w = np.array(w[::-1])
    out = np.full(len(logp), np.nan)
    if len(logp) >= width:
        out[width - 1:] = fftconvolve(logp, w[::-1], "valid")
    return (out - np.nanmean(out)) / np.nanstd(out)


def build(sym):
    df = pd.read_parquet(f"{DATA}/{sym}_{SUFFIX}.parquet")
    t = pd.DatetimeIndex(pd.to_datetime(df["timestamp"])).tz_localize(None).astype("datetime64[ns]")
    o = np.argsort(t.view("int64"))
    logp = np.log(((df["close_bid"] + df["close_ask"]) / 2).to_numpy()[o])
    n = len(logp)
    bph = n / ((t.view("int64")[o][-1] - t.view("int64")[o][0]) / 3.6e12)
    s = pd.Series(logp)
    r = s.diff().fillna(0.0)
    feats = {
        "ffd_0.1": ffd01(logp, bph),
        "pxdev_96h": ((logp - s.rolling(int(96 * bph)).mean()) / s.rolling(int(96 * bph)).std()).to_numpy(),
        "mom_1bar": (r * 1e4).to_numpy(),
        "mom_10bar": (r.rolling(10).sum() * 1e4).to_numpy(),
        "intra_bar_mom": df["intra_bar_momentum"].to_numpy()[o],
        "hl_pos_frac": df["hl_pos_frac"].to_numpy()[o],
    }
    vol = r.ewm(span=100).std().to_numpy()
    return logp, feats, vol, bph


def partial_ic(x, y, z):
    rxy = stats.spearmanr(x, y)[0]
    rxz = stats.spearmanr(x, z)[0]
    ryz = stats.spearmanr(y, z)[0]
    den = np.sqrt(max(1 - rxz**2, 1e-9) * max(1 - ryz**2, 1e-9))
    return (rxy - rxz * ryz) / den


def main():
    rng = np.random.default_rng(0)
    cache = {s: build(s) for s in POOL}
    evset, targ = {}, {}
    for s in POOL:
        logp, feats, vol, bph = cache[s]
        n = len(logp)
        warm = int(96 * bph) + max(LAGS) + 20
        idx = np.arange(warm, n - N_TB - 3)
        idx = idx[np.isfinite(vol[idx + 1]) & (vol[idx + 1] > 0)]
        ev = np.sort(rng.choice(idx, min(N_EVENTS, len(idx)), replace=False))
        entry = ev + 1
        y1 = (logp[entry + 1] - logp[entry]) * 1e4
        vert = np.minimum(entry + N_TB, n - 1)
        _, ytb, _, _ = triple_barrier_core(logp, entry, vert, 1.0 * vol[entry] * np.sqrt(N_TB))
        evset[s] = ev
        targ[s] = {"1bar": y1, "tb30": ytb}

    for tname in ["1bar", "tb30"]:
        print("=" * 96)
        print(f"TARGET = {tname}  —  RAW IC (and [partial IC vs lag-0]) by feature x lag | sign/5")
        print("=" * 96)
        print(f"{'feature':16s}" + "".join(f"{'L='+str(L):>13s}" for L in LAGS))
        for f in FEATS:
            raw_cells, part_cells = [], []
            for L in LAGS:
                raws, parts = [], []
                for s in POOL:
                    logp, feats, vol, bph = cache[s]
                    ev = evset[s]
                    y = targ[s][tname]
                    xl = feats[f][ev - L]
                    x0 = feats[f][ev]
                    ok = np.isfinite(xl) & np.isfinite(y) & np.isfinite(x0)
                    raws.append(stats.spearmanr(xl[ok], y[ok])[0])
                    parts.append(partial_ic(xl[ok], y[ok], x0[ok]) if L > 0 else np.nan)
                raws = np.array(raws)
                sgn = int((np.sign(raws) == np.sign(raws.mean())).sum())
                raw_cells.append(f"{raws.mean():+.4f}/{sgn}")
                part_cells.append("" if L == 0 else f"[{np.nanmean(parts):+.4f}]")
            print(f"{f:16s}" + "".join(f"{c:>13s}" for c in raw_cells))
            print(f"{'  partial':16s}" + "".join(f"{c:>13s}" for c in part_cells))
        print()
    print("RAW = IC of lag-L feature vs target; [partial] = IC of lag-L controlling lag-0")
    print("(near-zero partial => lag is just autocorrelation of lag-0, adds no new info)")


if __name__ == "__main__":
    main()
