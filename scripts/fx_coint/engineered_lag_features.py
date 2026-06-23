"""Hunt for an ENGINEERED temporal/lag feature that adds predictive content
ORTHOGONAL to lag-0 ffd, at the 30-bar triple-barrier target (1000tick, bounce-free).

Constructs new lag-derived features (velocity/acceleration of the deviation, its
age, de-meaned 'reversion of the reversion', choppiness/run-length, already-
reverting, vol-regime) and scores each by partial IC controlling for ffd_0.1.

Replication gate (no t-stats): orthogonal (|corr to ffd|<0.5) AND >=4/5 sign AND
non-overlap same-sign AND |partial IC|>0.004.

Usage: uv run python scripts/fx_coint/engineered_lag_features.py
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
N_TB = 30
N_EVENTS = 40000


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


def age_since_sign_change(x: np.ndarray) -> np.ndarray:
    sg = np.sign(x)
    change = np.concatenate([[True], sg[1:] != sg[:-1]])
    idx = np.where(change, np.arange(len(x)), 0)
    np.maximum.accumulate(idx, out=idx)
    return np.arange(len(x)) - idx


def build(sym):
    df = pd.read_parquet(f"{DATA}/{sym}_{SUFFIX}.parquet")
    t = pd.DatetimeIndex(pd.to_datetime(df["timestamp"])).tz_localize(None).astype("datetime64[ns]")
    o = np.argsort(t.view("int64"))
    logp = np.log(((df["close_bid"] + df["close_ask"]) / 2).to_numpy()[o])
    n = len(logp)
    bph = n / ((t.view("int64")[o][-1] - t.view("int64")[o][0]) / 3.6e12)
    s = pd.Series(logp)
    r = (s.diff().fillna(0.0) * 1e4)
    ffd = ffd01(logp, bph)
    fser = pd.Series(ffd)
    eps = 1e-9

    f = {}
    f["ffd_0.1"] = ffd  # control
    # velocity / acceleration of the deviation
    f["ffd_vel5"] = ffd - np.concatenate([np.full(5, np.nan), ffd[:-5]])
    f["ffd_vel20"] = ffd - np.concatenate([np.full(20, np.nan), ffd[:-20]])
    f["ffd_accel"] = f["ffd_vel5"] - np.concatenate([np.full(5, np.nan), f["ffd_vel5"][:-5]])
    # reversion-of-the-reversion (de-mean the slow signal)
    f["ffd_demean20"] = (fser - fser.rolling(20).mean()).to_numpy()
    f["ffd_demean50"] = (fser - fser.rolling(50).mean()).to_numpy()
    # deviation in units of its own recent variability
    f["ffd_zvol20"] = (ffd / (fser.rolling(20).std().to_numpy() + eps))
    # age of the current deviation direction
    f["dev_age"] = age_since_sign_change(ffd).astype(float)
    # already-reverting: has price moved AGAINST the deviation recently?
    f["already_rev"] = (-np.sign(ffd) * r.rolling(5).sum().to_numpy())
    f["already_rev20"] = (-np.sign(ffd) * r.rolling(20).sum().to_numpy())
    # choppiness / run structure of returns
    f["runlen"] = age_since_sign_change(r.to_numpy()).astype(float)
    f["signflips10"] = pd.Series(np.sign(r.to_numpy())).diff().abs().rolling(10).sum().to_numpy()
    # path curvature / macd
    f["ret_curv"] = (r - 2 * r.shift(1) + r.shift(2)).to_numpy()
    f["macd"] = (r.ewm(span=5).mean() - r.ewm(span=20).mean()).to_numpy()
    # vol regime
    f["volratio"] = (r.abs().rolling(5).mean() / (r.abs().rolling(50).mean() + eps)).to_numpy()
    # tick-native microstructure (orthogonal continuation cluster)
    f["intra_bar_mom"] = df["intra_bar_momentum"].to_numpy()[o]
    f["hl_pos_frac"] = df["hl_pos_frac"].to_numpy()[o]

    vol = (s.diff().fillna(0.0)).ewm(span=100).std().to_numpy()
    return logp, f, vol, bph


def partial_ic(x, y, z):
    rxy = stats.spearmanr(x, y)[0]
    rxz = stats.spearmanr(x, z)[0]
    ryz = stats.spearmanr(y, z)[0]
    den = np.sqrt(max(1 - rxz**2, 1e-9) * max(1 - ryz**2, 1e-9))
    return (rxy - rxz * ryz) / den, rxz


def main():
    rng = np.random.default_rng(0)
    cache = {s: build(s) for s in POOL}
    evset, targ = {}, {}
    for s in POOL:
        logp, f, vol, bph = cache[s]
        n = len(logp)
        warm = int(96 * bph) + 60
        idx = np.arange(warm, n - N_TB - 3)
        idx = idx[np.isfinite(vol[idx + 1]) & (vol[idx + 1] > 0)]
        ev = np.sort(rng.choice(idx, min(N_EVENTS, len(idx)), replace=False))
        entry = ev + 1
        vert = np.minimum(entry + N_TB, n - 1)
        _, y, _, _ = triple_barrier_core(logp, entry, vert, 1.0 * vol[entry] * np.sqrt(N_TB))
        evset[s] = ev
        targ[s] = y

    feats = [k for k in cache[POOL[0]][1] if k != "ffd_0.1"]
    rows = []
    for fn in feats:
        pics, ccs, novs = [], [], []
        for s in POOL:
            logp, f, vol, bph = cache[s]
            ev = evset[s]
            y = targ[s]
            x = f[fn][ev]
            z = f["ffd_0.1"][ev]
            ok = np.isfinite(x) & np.isfinite(y) & np.isfinite(z)
            pic, cc = partial_ic(x[ok], y[ok], z[ok])
            pics.append(pic)
            ccs.append(cc)
            no = slice(None, None, N_TB)
            xo, yo, zo = x[ok][no], y[ok][no], z[ok][no]
            if len(xo) > 200:
                novs.append(partial_ic(xo, yo, zo)[0])
        pics = np.array(pics)
        pic = pics.mean()
        sgn = int((np.sign(pics) == np.sign(pic)).sum())
        nov = np.nanmean(novs) if novs else np.nan
        rows.append(dict(feature=fn, partial_ic=pic, corr_ffd=np.mean(ccs), sign=f"{sgn}/5",
                         nov_ic=nov,
                         robust=(sgn >= 4 and np.isfinite(nov) and np.sign(nov) == np.sign(pic)
                                 and abs(np.mean(ccs)) < 0.5 and abs(pic) > 0.004)))
    res = pd.DataFrame(rows).reindex(pd.DataFrame(rows).partial_ic.abs().sort_values(ascending=False).index)
    pd.set_option("display.width", 160, "display.float_format", lambda x: f"{x:9.4f}")
    print("=" * 92)
    print(f"ENGINEERED LAG FEATURES — partial IC vs ffd_0.1, target = {N_TB}-bar TB (1000tick)")
    print("=" * 92)
    print(res[["feature", "partial_ic", "corr_ffd", "sign", "nov_ic", "robust"]].to_string(index=False))
    rob = res[res.robust]
    print(f"\nROBUST orthogonal engineered features: {len(rob)}")
    if len(rob):
        print(rob[["feature", "partial_ic", "corr_ffd", "sign", "nov_ic"]].to_string(index=False))


if __name__ == "__main__":
    main()
