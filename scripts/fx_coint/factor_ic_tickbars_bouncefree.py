"""Bounce-free 1-bar-ahead IC on tick bars.

The H=1 close-to-close 'reversion' (mom_1bar) is largely Roll-model bid-ask
bounce: feature r_i and target r_{i+1} share the SAME noisy mid price_i, forcing
a mechanical negative correlation. Fix = a 1-bar EMBARGO: predict the H-bar
return that STARTS one bar later, so feature (ends at close i) and target (starts
at close i+1) share no price.

  y_adj_H   = logp[i+H]   - logp[i]      (adjacent, contains bounce)
  y_gap_H   = logp[i+1+H] - logp[i+1]    (1-bar embargo, bounce-free)

Reports both side by side; a feature whose IC survives the embargo is a real
signal, one that collapses was bounce. Metrics: pooled IC (5 ex-JPY) | sign/5.

Usage: uv run python scripts/fx_coint/factor_ic_tickbars_bouncefree.py
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats
from scipy.signal import fftconvolve

DATA = "/Users/danielfisher/repositories/behemoth/data/tick_bars"
POOL = ["AUDUSD", "EURUSD", "GBPUSD", "USDCAD", "USDCHF"]
BAR_H = [1, 5, 10]
DATASETS = ["1000tick", "100tick"]
FEATS = ["ffd_0.1", "pxdev_96h", "mom_1bar", "mom_10bar", "intra_bar_momentum",
         "hl_pos_frac", "high_pos_tick", "low_pos_tick", "quote_revisions", "abs_ibm"]


def ffd_weights(d: float, width: int) -> np.ndarray:
    w = [1.0]
    for k in range(1, width):
        w.append(-w[-1] * (d - k + 1) / k)
    return np.array(w[::-1])


def ffd_series(logp: np.ndarray, d: float, width: int) -> np.ndarray:
    out = np.full(len(logp), np.nan)
    if len(logp) >= width:
        out[width - 1:] = fftconvolve(logp, ffd_weights(d, width)[::-1], mode="valid")
    return out


def build(sym: str, suffix: str) -> pd.DataFrame:
    df = pd.read_parquet(f"{DATA}/{sym}_{suffix}.parquet")
    t = pd.DatetimeIndex(pd.to_datetime(df["timestamp"])).tz_localize(None).astype("datetime64[ns]")
    df = df.set_index(t).sort_index()
    df = df[~df.index.duplicated()]
    logp = np.log((df["close_bid"] + df["close_ask"]) / 2)
    v = logp.to_numpy()
    ret = logp.diff() * 1e4
    bph = len(df) / ((df.index[-1] - df.index[0]).total_seconds() / 3600)
    d = pd.DataFrame(index=df.index)
    d["pxdev_96h"] = (logp - logp.rolling("96h").mean()) / logp.rolling("96h").std()
    fd = ffd_series(v, 0.1, max(int(480 * bph), 50))
    d["ffd_0.1"] = (fd - np.nanmean(fd)) / np.nanstd(fd)
    d["mom_1bar"] = ret
    d["mom_10bar"] = ret.rolling(10).sum()
    for c in ["intra_bar_momentum", "hl_pos_frac", "high_pos_tick", "low_pos_tick", "quote_revisions"]:
        d[c] = df[c]
    d["abs_ibm"] = df["intra_bar_momentum"].abs()
    for h in BAR_H:
        d[f"adj{h}"] = (logp.shift(-h) - logp) * 1e4              # adjacent (bounce)
        d[f"gap{h}"] = (logp.shift(-(1 + h)) - logp.shift(-1)) * 1e4  # 1-bar embargo
    return d


def pooled(data: dict, feat: str, tgt: str) -> tuple[float, int]:
    ics = []
    for s in POOL:
        c = data[s][[feat, tgt]].replace([np.inf, -np.inf], np.nan).dropna()
        if len(c) < 1000 or c[feat].nunique() < 5:
            continue
        ics.append(stats.spearmanr(c[feat], c[tgt])[0])
    if len(ics) < 5:
        return np.nan, 0
    ics = np.array(ics)
    return ics.mean(), int((np.sign(ics) == np.sign(ics.mean())).sum())


def main() -> None:
    store = {}
    print("Loading + features ...")
    for suffix in DATASETS:
        store[suffix] = {s: build(s, suffix) for s in POOL}
        print(f"  {suffix} done")

    for suffix in DATASETS:
        data = store[suffix]
        print("\n" + "=" * 100)
        print(f"{suffix}  —  adjacent (bounce) vs 1-bar-embargo (bounce-free) pooled IC | sign/5")
        print("=" * 100)
        print(f"{'feature':20s}" + "".join(f"{'adj H='+str(h):>13s}{'gap H='+str(h):>13s}" for h in BAR_H))
        for f in FEATS:
            cells = []
            for h in BAR_H:
                a, sa = pooled(data, f, f"adj{h}")
                g, sg = pooled(data, f, f"gap{h}")
                cells.append(f"{a:+.4f}/{sa}" + " " + f"{g:+.4f}/{sg}")
            print(f"{f:20s}" + "".join(f"{c:>26s}" for c in cells))
        print("  (adj = adjacent close-to-close incl bounce; gap = 1-bar embargo, bounce-free)")


if __name__ == "__main__":
    main()
