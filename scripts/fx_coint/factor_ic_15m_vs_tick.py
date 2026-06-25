"""Fair comparison the USER asked for: classical factors on 15m TIME bars vs
TICK bars (1000tick ~10min, 100tick ~1min).

Single harness, identical everything (mirrors multires_factor_check, which
reproduces the validated 15m ffd_0.1@48h IC ~ -0.0655 — used here as a
correctness check). NO liquid-session filter, NO gap-dropping, NO inflated
t-stats. Metrics: pooled Spearman IC (5 ex-JPY) | sign/5 | non-overlap IC.

  ffd_0.1   reversion (FFD memory matched to ~480h of bars)
  pxdev_96h reversion (price z vs 96h mean)
  skew_48h  asymmetry  (expected to die on tick bars)

Usage: uv run python scripts/fx_coint/factor_ic_15m_vs_tick.py
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats

DATA = "/Users/danielfisher/repositories/behemoth/data/tick_bars"
POOL = ["AUDUSD", "EURUSD", "GBPUSD", "USDCAD", "USDCHF"]
FWD_HOURS = [24, 48]
DATASETS = {  # label -> (filename suffix, price-builder kind)
    "15m_time": "15m_flow",
    "1000tick": "1000tick",
    "100tick": "100tick",
}


def ffd_weights(d: float, width: int) -> np.ndarray:
    w = [1.0]
    for k in range(1, width):
        w.append(-w[-1] * (d - k + 1) / k)
    return np.array(w[::-1])


def ffd_series(logp: np.ndarray, d: float, width: int) -> np.ndarray:
    w = ffd_weights(d, width)
    out = np.full(len(logp), np.nan)
    if len(logp) >= width:
        out[width - 1:] = np.convolve(logp, w[::-1], "valid")
    return out


def load_close(sym: str, suffix: str) -> pd.Series:
    df = pd.read_parquet(f"{DATA}/{sym}_{suffix}.parquet")
    if "mid" in df.columns:                       # time bars
        mid = df["mid"].to_numpy()
        t = pd.to_datetime(df["bucket"])
    else:                                         # tick bars: mid of close quotes
        mid = ((df["close_bid"] + df["close_ask"]) / 2).to_numpy()
        t = pd.to_datetime(df["timestamp"])
    # force tz-naive nanosecond resolution (time bars are ms, tick bars ns)
    t = pd.DatetimeIndex(t).tz_localize(None).astype("datetime64[ns]")
    s = pd.Series(mid, index=t)
    return s[~s.index.duplicated()].sort_index()


def features_and_fwd(close: pd.Series) -> tuple[pd.DataFrame, float]:
    span_h = (close.index[-1] - close.index[0]).total_seconds() / 3600
    bph = len(close) / span_h
    logp = np.log(close)
    v = logp.to_numpy()
    ret = logp.diff() * 1e4
    d = pd.DataFrame(index=close.index)
    d["pxdev_96h"] = ((logp - logp.rolling("96h").mean()) / logp.rolling("96h").std()).shift(1)
    d["skew_48h"] = ret.rolling("48h").skew().shift(1)
    width = max(int(480 * bph), 50)
    fd = ffd_series(v, 0.1, width)
    fd = (fd - np.nanmean(fd)) / np.nanstd(fd)
    d["ffd_0.1"] = pd.Series(fd, index=close.index).shift(1)
    tnum = close.index.view("int64")
    n = len(v)
    ar = np.arange(n)
    for h in FWD_HOURS:
        j = np.searchsorted(tnum, tnum + int(h * 3600 * 1e9), side="left")
        valid = j < n
        fwd = np.full(n, np.nan)
        fwd[valid] = (v[j[valid]] - v[ar[valid]]) * 1e4
        d[f"y{h}"] = fwd
    return d, bph


def main() -> None:
    feats = ["ffd_0.1", "pxdev_96h", "skew_48h"]
    print("Loading + building features per dataset ...")
    store: dict[str, dict] = {}
    for label, suffix in DATASETS.items():
        data, bph = {}, {}
        for s in POOL:
            d, b = features_and_fwd(load_close(s, suffix))
            data[s] = d
            bph[s] = b
        store[label] = {"data": data, "bph": bph}
        print(f"  {label}: ~{np.mean(list(bph.values())):.1f} bars/h")

    for h in FWD_HOURS:
        print("\n" + "=" * 96)
        print(f"FORWARD {h}h  —  pooled Spearman IC (5 ex-JPY) | sign/5 | non-overlap IC")
        print("=" * 96)
        print(f"{'factor':12s} " + " ".join(f"{lab:>24s}" for lab in DATASETS))
        for f in feats:
            cells = []
            for label in DATASETS:
                data = store[label]["data"]
                bph = store[label]["bph"]
                ics, novs = [], []
                for s in POOL:
                    dd = data[s][[f, f"y{h}"]].replace([np.inf, -np.inf], np.nan).dropna()
                    if len(dd) < 500:
                        continue
                    ics.append(stats.spearmanr(dd[f], dd[f"y{h}"])[0])
                    step = max(int(h * bph[s]), 1)
                    no = dd.iloc[::step]
                    if len(no) > 150:
                        novs.append(stats.spearmanr(no[f], no[f"y{h}"])[0])
                ics = np.array(ics)
                ic = ics.mean()
                sgn = int((np.sign(ics) == np.sign(ic)).sum())
                nov = np.mean(novs) if novs else np.nan
                cells.append(f"{ic:+.4f} {sgn}/5 nov{nov:+.4f}")
            print(f"{f:12s} " + " ".join(f"{c:>24s}" for c in cells))

    print("\nCorrectness check: 15m_time ffd_0.1@48h should reproduce ~ -0.0655 (validated baseline).")


if __name__ == "__main__":
    main()
