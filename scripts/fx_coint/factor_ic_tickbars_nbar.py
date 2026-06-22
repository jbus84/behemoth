"""IC of ALL features on TICK bars at N-BARS-ahead forward returns (not wall-clock).

Forward target = logp.shift(-H) - logp (H bars ahead), H in {1,5,10,50}; the
headline is H=1 (next-bar return). Features are taken at the CURRENT bar's close
(causal: feature known at close i, target = return i -> i+H), so no extra lag.

Features:
  classical (price): ffd_0.1, pxdev_96h, skew_48h, mom_1bar, mom_10bar
  native (tick cols): intra_bar_momentum, hl_pos_frac, hl_pos_delta_tick,
    high_pos_tick, low_pos_tick, quote_revisions, tick_burst, spread,
    tick_volume, bar_return_sign, abs_ibm

Metrics: pooled Spearman IC (5 ex-JPY) | sign/5 | non-overlap IC (step=H).
FFD via FFT convolution (long wall-clock memory window on millions of bars).

Usage: uv run python scripts/fx_coint/factor_ic_tickbars_nbar.py
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats
from scipy.signal import fftconvolve

DATA = "/Users/danielfisher/repositories/behemoth/data/tick_bars"
POOL = ["AUDUSD", "EURUSD", "GBPUSD", "USDCAD", "USDCHF"]
BAR_H = [1, 5, 10, 50]
DATASETS = ["1000tick", "100tick"]
NATIVE = ["intra_bar_momentum", "hl_pos_frac", "hl_pos_delta_tick", "high_pos_tick",
          "low_pos_tick", "quote_revisions", "tick_burst", "spread", "tick_volume",
          "bar_return_sign"]
CLASSICAL = ["ffd_0.1", "pxdev_96h", "skew_48h", "mom_1bar", "mom_10bar"]


def ffd_weights(d: float, width: int) -> np.ndarray:
    w = [1.0]
    for k in range(1, width):
        w.append(-w[-1] * (d - k + 1) / k)
    return np.array(w[::-1])


def ffd_series(logp: np.ndarray, d: float, width: int) -> np.ndarray:
    w = ffd_weights(d, width)
    out = np.full(len(logp), np.nan)
    if len(logp) >= width:
        out[width - 1:] = fftconvolve(logp, w[::-1], mode="valid")
    return out


def build(sym: str, suffix: str) -> tuple[pd.DataFrame, float]:
    df = pd.read_parquet(f"{DATA}/{sym}_{suffix}.parquet")
    t = pd.DatetimeIndex(pd.to_datetime(df["timestamp"])).tz_localize(None).astype("datetime64[ns]")
    df = df.set_index(t).sort_index()
    df = df[~df.index.duplicated()]
    logp = np.log((df["close_bid"] + df["close_ask"]) / 2)
    v = logp.to_numpy()
    ret = logp.diff() * 1e4
    span_h = (df.index[-1] - df.index[0]).total_seconds() / 3600
    bph = len(df) / span_h
    d = pd.DataFrame(index=df.index)
    # classical (causal at close i)
    d["pxdev_96h"] = (logp - logp.rolling("96h").mean()) / logp.rolling("96h").std()
    d["skew_48h"] = ret.rolling("48h").skew()
    fd = ffd_series(v, 0.1, max(int(480 * bph), 50))
    d["ffd_0.1"] = (fd - np.nanmean(fd)) / np.nanstd(fd)
    d["mom_1bar"] = ret
    d["mom_10bar"] = ret.rolling(10).sum()
    # native (already known at close i)
    for c in NATIVE:
        d[c] = df[c]
    d["abs_ibm"] = df["intra_bar_momentum"].abs()
    # N-bars-ahead forward returns
    for h in BAR_H:
        d[f"y{h}"] = (logp.shift(-h) - logp) * 1e4
    return d, bph


def main() -> None:
    feats = CLASSICAL + NATIVE + ["abs_ibm"]
    store = {}
    print("Loading tick bars + features ...")
    for suffix in DATASETS:
        data, bph = {}, {}
        for s in POOL:
            dd, b = build(s, suffix)
            data[s] = dd
            bph[s] = b
        store[suffix] = (data, bph)
        print(f"  {suffix}: ~{np.mean(list(bph.values())):.0f} bars/h, "
              f"{int(np.mean([len(data[s]) for s in POOL])):,} bars/sym")

    pd.set_option("display.width", 220, "display.float_format", lambda x: f"{x:9.4f}")
    for suffix in DATASETS:
        data, bph = store[suffix]
        print("\n" + "=" * 104)
        print(f"{suffix}  —  pooled Spearman IC (5 ex-JPY) at N-BARS ahead  | sign/5 | (non-overlap at H=1 == full)")
        print("=" * 104)
        header = f"{'feature':20s}" + "".join(f"{'H='+str(h):>16s}" for h in BAR_H)
        print(header)
        for f in feats:
            cells = []
            for h in BAR_H:
                ics, novs = [], []
                for s in POOL:
                    col = data[s][[f, f"y{h}"]].replace([np.inf, -np.inf], np.nan).dropna()
                    if len(col) < 1000 or col[f].nunique() < 5:
                        continue
                    ics.append(stats.spearmanr(col[f], col[f"y{h}"])[0])
                    no = col.iloc[::h] if h > 1 else col
                    if len(no) > 200:
                        novs.append(stats.spearmanr(no[f], no[f"y{h}"])[0])
                if len(ics) < 5:
                    cells.append("    --        ")
                    continue
                ics = np.array(ics)
                ic = ics.mean()
                sgn = int((np.sign(ics) == np.sign(ic)).sum())
                cells.append(f"{ic:+.4f} {sgn}/5")
            print(f"{f:20s}" + "".join(f"{c:>16s}" for c in cells))


if __name__ == "__main__":
    main()
