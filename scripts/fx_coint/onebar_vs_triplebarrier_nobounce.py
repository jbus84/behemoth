"""BOUNCE-FREE 1-bar vs N-bar triple-barrier predictability comparison.

Same as onebar_vs_triplebarrier.py but with a 1-bar ENTRY EMBARGO: feature is at
bar i, but the label's entry/path starts at bar i+1, so the feature's last price
(close i) is never shared with the label -> Roll-model bid-ask bounce removed.

  y_1bar_nb = logp[i+2] - logp[i+1]                     (embargoed next-bar)
  y_tbN_nb  = first-touch return of an N-bar triple barrier ENTERED at i+1

Reports the bounce vs non-bounce delta for mom_1bar (where bounce lives) and the
full bounce-free table. Avg hold shown in bars and minutes (trading-time).

Usage: uv run python scripts/fx_coint/onebar_vs_triplebarrier_nobounce.py
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
N_BARS = [10, 50]
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
    t = pd.DatetimeIndex(pd.to_datetime(df["timestamp"])).tz_localize(None).astype("datetime64[ns]")
    o = np.argsort(t.view("int64"))
    logp = np.log(((df["close_bid"] + df["close_ask"]) / 2).to_numpy()[o])
    ibm = df["intra_bar_momentum"].to_numpy()[o]
    hlf = df["hl_pos_frac"].to_numpy()[o]
    n = len(logp)
    tns = t.view("int64")[o]
    bph = n / ((tns[-1] - tns[0]) / 3.6e12)
    # trading-time mean bar minutes (drop weekend gaps)
    dt = np.diff(tns) / 6e10
    bar_min = float(np.mean(dt[(dt > 0) & (dt < 360)]))
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
    return logp, feats, vol, bph, bar_min


def main():
    rng = np.random.default_rng(0)
    for suffix in DATASETS:
        cache = {s: build(s, suffix) for s in POOL}
        bar_min = np.mean([cache[s][4] for s in POOL])
        print("=" * 104)
        print(f"{suffix} (avg bar ~{bar_min:.1f} min)  —  BOUNCE-FREE (1-bar entry embargo) pooled IC | sign/5")
        print("=" * 104)
        evset = {}
        for s in POOL:
            logp, feats, vol, b, _ = cache[s]
            n = len(logp)
            warm = int(96 * b) + 20
            idx = np.arange(warm, n - max(N_BARS) - 3)
            idx = idx[np.isfinite(vol[idx + 1]) & (vol[idx + 1] > 0)]
            evset[s] = np.sort(rng.choice(idx, min(N_EVENTS, len(idx)), replace=False))

        cols = ["y_1bar", *[f"y_tb{N}" for N in N_BARS]]
        ics = {c: {f: [] for f in FEATS} for c in cols}
        ics_bounce_mom1 = []  # mom_1bar with no embargo, for delta
        meta = {f"y_tb{N}": [] for N in N_BARS}
        for s in POOL:
            logp, feats, vol, b, _ = cache[s]
            ev = evset[s]
            entry = ev + 1  # embargoed entry
            targets = {"y_1bar": (logp[entry + 1] - logp[entry]) * 1e4}
            for N in N_BARS:
                vert = np.minimum(entry + N, len(logp) - 1)
                width = 1.0 * vol[entry] * np.sqrt(N)
                _, ret, hold, tc = triple_barrier_core(logp, entry, vert, width)
                targets[f"y_tb{N}"] = ret
                meta[f"y_tb{N}"].append((hold.mean(), np.mean(tc == 0)))
            # bounce vs non-bounce for mom_1bar
            y_bounce = (logp[ev + 1] - logp[ev]) * 1e4   # adjacent (shares close i)
            fv = feats["mom_1bar"][ev]
            ics_bounce_mom1.append((stats.spearmanr(fv, y_bounce)[0],
                                    stats.spearmanr(fv, targets["y_1bar"])[0]))
            for c in cols:
                y = targets[c]
                for f in FEATS:
                    x = feats[f][ev]
                    ok = np.isfinite(x) & np.isfinite(y)
                    ics[c][f].append(stats.spearmanr(x[ok], y[ok])[0] if ok.sum() > 500 else np.nan)

        for N in N_BARS:
            h, v = np.mean([m[0] for m in meta[f"y_tb{N}"]]), np.mean([m[1] for m in meta[f"y_tb{N}"]])
            print(f"  triple-barrier N={N}: avg hold {h:.1f} bars (~{h*bar_min/60:.1f} h), vertical-touched {v*100:.0f}%")
        b_arr = np.array(ics_bounce_mom1)
        print(f"  mom_1bar bounce-check: adjacent IC {b_arr[:,0].mean():+.4f}  ->  embargoed IC {b_arr[:,1].mean():+.4f}  "
              f"(bounce removed)")
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
