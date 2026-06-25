"""Fair comparison: 1-bar-ahead label vs an N-bar TRIPLE-BARRIER label.

Same features, same events; only the TARGET changes. Asks how making the label
longer-horizon AND path-aware (vertical = N bars + symmetric vol stops, first
touch) changes which features predict — vs the immediate 1-bar return.

  y_1bar   = (logp[i+1] - logp[i])                       next-bar return
  y_tbN    = first-touch return within N bars, horizontals = 1.0 * N-bar vol

Tick bars (100tick, 1000tick), pooled Spearman IC (5 ex-JPY) | sign/5.

Usage: uv run python scripts/fx_coint/onebar_vs_triplebarrier.py
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
DATASETS = ["1000tick", "100tick"]
N_BARS = [10, 50]          # vertical-barrier horizons (bars)
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


def build(sym, suffix):
    df = pd.read_parquet(f"{DATA}/{sym}_{suffix}.parquet")
    mid = ((df["close_bid"] + df["close_ask"]) / 2).to_numpy()
    t = pd.DatetimeIndex(pd.to_datetime(df["timestamp"])).tz_localize(None).astype("datetime64[ns]")
    o = np.argsort(t.view("int64"))
    logp = np.log(mid[o])
    ibm = df["intra_bar_momentum"].to_numpy()[o]
    hlf = df["hl_pos_frac"].to_numpy()[o]
    n = len(logp)
    bph = n / ((t.view("int64")[o][-1] - t.view("int64")[o][0]) / 3.6e12)
    s = pd.Series(logp)
    r = s.diff().fillna(0.0)
    feats = {
        "ffd_0.1": ffd01(logp, bph),
        "pxdev_96h": ((logp - s.rolling(int(96 * bph)).mean()) / s.rolling(int(96 * bph)).std()).to_numpy(),
        "mom_1bar": (r * 1e4).to_numpy(),
        "mom_10bar": (r.rolling(10).sum() * 1e4).to_numpy(),
        "intra_bar_mom": ibm,
        "hl_pos_frac": hlf,
    }
    vol = r.ewm(span=100).std().to_numpy()
    return logp, feats, vol, bph


def main():
    rng = np.random.default_rng(0)
    for suffix in DATASETS:
        cache = {s: build(s, suffix) for s in POOL}
        bph = np.mean([cache[s][3] for s in POOL])
        print("=" * 100)
        print(f"{suffix} (~{bph:.0f} bars/h)  —  pooled Spearman IC (5 ex-JPY) | sign/5")
        print("=" * 100)
        # event set per symbol (shared across targets)
        evset = {}
        for s in POOL:
            logp, feats, vol, b = cache[s]
            n = len(logp)
            warm = int(96 * b) + 20
            pool_idx = np.arange(warm, n - max(N_BARS) - 1)
            pool_idx = pool_idx[np.isfinite(vol[pool_idx]) & (vol[pool_idx] > 0)]
            evset[s] = np.sort(rng.choice(pool_idx, min(N_EVENTS, len(pool_idx)), replace=False))

        cols = ["y_1bar"] + [f"y_tb{N}" for N in N_BARS]
        meta = {f"y_tb{N}": [] for N in N_BARS}  # (hold, vert%)
        ics = {c: {f: [] for f in FEATS} for c in cols}
        for s in POOL:
            logp, feats, vol, b = cache[s]
            ev = evset[s]
            targets = {"y_1bar": (logp[ev + 1] - logp[ev]) * 1e4}
            for N in N_BARS:
                vert = np.minimum(ev + N, len(logp) - 1)
                width = 1.0 * vol[ev] * np.sqrt(N)
                _, ret, hold, tc = triple_barrier_core(logp, ev, vert, width)
                targets[f"y_tb{N}"] = ret
                meta[f"y_tb{N}"].append((hold.mean(), np.mean(tc == 0)))
            for c in cols:
                y = targets[c]
                for f in FEATS:
                    fv = feats[f][ev]
                    ok = np.isfinite(fv) & np.isfinite(y)
                    ics[c][f].append(stats.spearmanr(fv[ok], y[ok])[0] if ok.sum() > 500 else np.nan)

        for N in N_BARS:
            h, v = np.mean([m[0] for m in meta[f"y_tb{N}"]]), np.mean([m[1] for m in meta[f"y_tb{N}"]])
            print(f"  triple-barrier N={N}: avg hold {h:.1f} bars (~{h/bph*60:.0f} min), vertical-touched {v*100:.0f}%")
        print(f"\n  {'feature':16s}" + "".join(f"{c:>14s}" for c in cols))
        for f in FEATS:
            cells = []
            for c in cols:
                a = np.array(ics[c][f])
                sgn = int((np.sign(a) == np.sign(np.nanmean(a))).sum())
                cells.append(f"{np.nanmean(a):+.4f} {sgn}/5")
            print(f"  {f:16s}" + "".join(f"{x:>14s}" for x in cells))
        print()


if __name__ == "__main__":
    main()
