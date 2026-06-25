"""Do the surviving PRICE-based factors persist at 15m / 30m / 1h?

Compares the validated factors across bar resolutions with windows and forward
horizons fixed in WALL-CLOCK HOURS (so the comparison is fair; only the bar
granularity changes). Expectation: IC drops at finer resolution but the SIGN
and cross-symbol consistency persist.

Factors (all per-symbol, strictly lagged, on 5 non-JPY majors):
  mom_1bar    immediate reversion (1 bar)
  pxdev_96h   level reversion (price z vs 96h mean)         [main reversion factor]
  ffd_0.1     fractional-diff reversion (wall-clock-matched weight window)
  skew_48h    return-asymmetry / skew premium               [2nd factor]
Plus variance ratio VR(h) as the over-differencing / mean-reversion signature.

Flow features are EXCLUDED: 15m OFI cannot be reconstructed from 1m (corr 0.28)
and flow was already non-orthogonal/dead.

Usage: uv run python scripts/fx_coint/multires_factor_check.py
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats

POOL = ["AUDUSD", "EURUSD", "GBPUSD", "USDCAD", "USDCHF"]
RES_BPH = {"15m": 4, "30m": 2, "1h": 1}  # bars per hour
FWD_HOURS = [24, 48]                      # 1 day, 2 days
SKEW_HOURS = 48
PXDEV_HOURS = 96
FFD_HOURS = 480                           # wall-clock-matched FFD memory window


def ffd_weights(d: float, max_width: int, thres: float = 1e-5) -> np.ndarray:
    w = [1.0]
    k = 1
    while len(w) < max_width:
        w_ = -w[-1] * (d - k + 1) / k
        if abs(w_) < thres:
            break
        w.append(w_)
        k += 1
    return np.array(w[::-1])


def ffd(s: pd.Series, d: float, max_width: int) -> pd.Series:
    w = ffd_weights(d, max_width)
    width = len(w)
    v = s.to_numpy(float)
    out = np.full(len(v), np.nan)
    for i in range(width - 1, len(v)):
        out[i] = np.dot(w, v[i - width + 1: i + 1])
    return pd.Series(out, index=s.index)


def build(sym: str, res: str) -> pd.DataFrame:
    bph = RES_BPH[res]
    path = f"data/tick_bars/{sym}_{res}_flow.parquet"
    df = pd.read_parquet(path)
    df["bucket"] = pd.to_datetime(df["bucket"])
    df = df.set_index("bucket").sort_index()
    logp = np.log(df["mid"])
    r = (logp.diff() * 1e4).where(lambda x: x.abs() < 500)
    d = pd.DataFrame(index=df.index)
    d["mom_1bar"] = r.shift(1)
    w_px = PXDEV_HOURS * bph
    d["pxdev_96h"] = ((logp - logp.rolling(w_px).mean()) / logp.rolling(w_px).std()).shift(1)
    fd = ffd(logp, 0.1, max_width=FFD_HOURS * bph)
    d["ffd_0.1"] = ((fd - fd.mean()) / fd.std()).shift(1)
    d["skew_48h"] = r.rolling(SKEW_HOURS * bph).skew().shift(1)
    for h in FWD_HOURS:
        d[f"y{h}"] = (logp.shift(-h * bph) - logp) * 1e4
    return d


def pooled_ic(data: dict, feat: str, h: int, bph: int):
    full, novs = [], []
    for s in POOL:
        dd = data[s][[feat, f"y{h}"]].replace([np.inf, -np.inf], np.nan).dropna()
        if len(dd) < 500:
            continue
        full.append(stats.spearmanr(dd[feat], dd[f"y{h}"])[0])
        step = h * bph  # non-overlapping
        no = dd.iloc[::step]
        if len(no) > 150:
            novs.append(stats.spearmanr(no[feat], no[f"y{h}"])[0])
    full = np.array(full)
    ic = full.mean()
    sgn = int((np.sign(full) == np.sign(ic)).sum())
    nov = np.mean(novs) if novs else np.nan
    return ic, sgn, nov


def variance_ratio(sym: str, res: str) -> dict:
    bph = RES_BPH[res]
    logp = np.log(pd.read_parquet(f"data/tick_bars/{sym}_{res}_flow.parquet")["mid"])
    r1 = logp.diff().dropna()
    v1 = r1.var()
    out = {}
    for h in FWD_HOURS:
        hb = h * bph
        rh = (logp.shift(-hb) - logp).dropna()
        out[h] = rh.var() / (hb * v1)
    return out


def main() -> None:
    pd.set_option("display.width", 200)
    feats = ["mom_1bar", "pxdev_96h", "ffd_0.1", "skew_48h"]

    for h in FWD_HOURS:
        print("=" * 92)
        print(f"FORWARD HORIZON = {h}h  —  pooled Spearman IC (5 ex-JPY) | sign/5 | non-overlap IC")
        print("=" * 92)
        print(f"{'factor':12s} " + " ".join(f"{res:>22s}" for res in RES_BPH))
        # build once per res
        cache = {res: {s: build(s, res) for s in POOL} for res in RES_BPH}
        for f in feats:
            cells = []
            for res, bph in RES_BPH.items():
                ic, sgn, nov = pooled_ic(cache[res], f, h, bph)
                cells.append(f"{ic:+.4f} {sgn}/5 nov{nov:+.4f}")
            print(f"{f:12s} " + " ".join(f"{c:>22s}" for c in cells))
        print()

    print("=" * 92)
    print("VARIANCE RATIO VR(h) per resolution (mean over 5 ex-JPY; <1 = mean-revert)")
    print("=" * 92)
    print(f"{'horizon':10s} " + " ".join(f"{res:>10s}" for res in RES_BPH))
    for h in FWD_HOURS:
        cells = []
        for res in RES_BPH:
            vrs = [variance_ratio(s, res)[h] for s in POOL]
            cells.append(f"{np.mean(vrs):.4f}")
        print(f"{h:>4d}h      " + " ".join(f"{c:>10s}" for c in cells))


if __name__ == "__main__":
    main()
