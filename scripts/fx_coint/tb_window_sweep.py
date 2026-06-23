"""Triple-barrier vertical-window sweep (1000tick, bounce-free).

Sweeps N (vertical barrier in bars) and reports, pooled over 5 ex-JPY majors:
  - feature IC vs the N-bar triple-barrier first-touch return (ffd reversion +
    the others), sign/5
  - avg hold (bars / hours) and %% vertical-touched (labeling characterization)
Maps the reversion IC-vs-horizon curve and the holding cost, to pick a TB window.

Usage: uv run python scripts/fx_coint/tb_window_sweep.py
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
N_GRID = [5, 10, 20, 30, 50, 100, 200]
N_EVENTS = 30000
FEATS = ["ffd_0.1", "pxdev_96h", "mom_10bar", "intra_bar_mom", "hl_pos_frac"]


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
    tns = t.view("int64")[o]
    bph = n / ((tns[-1] - tns[0]) / 3.6e12)
    dt = np.diff(tns) / 6e10
    bar_min = float(np.mean(dt[(dt > 0) & (dt < 360)]))
    s = pd.Series(logp)
    r = s.diff().fillna(0.0)
    feats = {
        "ffd_0.1": ffd01(logp, bph),
        "pxdev_96h": ((logp - s.rolling(int(96 * bph)).mean()) / s.rolling(int(96 * bph)).std()).to_numpy(),
        "mom_10bar": (r.rolling(10).sum() * 1e4).to_numpy(),
        "intra_bar_mom": df["intra_bar_momentum"].to_numpy()[o],
        "hl_pos_frac": df["hl_pos_frac"].to_numpy()[o],
    }
    vol = r.ewm(span=100).std().to_numpy()
    return logp, feats, vol, bph, bar_min


def main():
    rng = np.random.default_rng(0)
    cache = {s: build(s) for s in POOL}
    bar_min = np.mean([cache[s][4] for s in POOL])
    evset = {}
    for s in POOL:
        logp, feats, vol, bph, _ = cache[s]
        n = len(logp)
        warm = int(96 * bph) + 20
        idx = np.arange(warm, n - max(N_GRID) - 3)
        idx = idx[np.isfinite(vol[idx + 1]) & (vol[idx + 1] > 0)]
        evset[s] = np.sort(rng.choice(idx, min(N_EVENTS, len(idx)), replace=False))

    print(f"{SUFFIX} (avg bar ~{bar_min:.0f} min), bounce-free, pooled IC (5 ex-JPY) | sign/5\n")
    header = f"{'N (bars)':>9s} {'hold(bars)':>11s} {'hold(h)':>8s} {'vert%':>6s}  " + \
             "".join(f"{f:>16s}" for f in FEATS)
    print(header)
    for N in N_GRID:
        holds, verts = [], []
        ic = {f: [] for f in FEATS}
        for s in POOL:
            logp, feats, vol, bph, _ = cache[s]
            ev = evset[s]
            entry = ev + 1
            vert = np.minimum(entry + N, len(logp) - 1)
            _, y, hold, tc = triple_barrier_core(logp, entry, vert, 1.0 * vol[entry] * np.sqrt(N))
            holds.append(hold.mean())
            verts.append(np.mean(tc == 0))
            for f in FEATS:
                x = feats[f][ev]
                ok = np.isfinite(x) & np.isfinite(y)
                ic[f].append(stats.spearmanr(x[ok], y[ok])[0])
        h = np.mean(holds)
        cells = []
        for f in FEATS:
            a = np.array(ic[f])
            sgn = int((np.sign(a) == np.sign(a.mean())).sum())
            cells.append(f"{a.mean():+.4f} {sgn}/5")
        print(f"{N:>9d} {h:>11.1f} {h*bar_min/60:>8.1f} {np.mean(verts)*100:>5.0f}%  "
              + "".join(f"{c:>16s}" for c in cells))

    print("\nffd reversion IC grows with N then plateaus; longer N = longer hold (cost/capacity).")


if __name__ == "__main__":
    main()
