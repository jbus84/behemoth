"""Do the reversion / skew factors survive on TICK bars (better-conditioned than
time bars)? And how does fractional differentiation behave on tick bars?

Builds close-only TICK bars (every N quote-ticks, N calibrated to ~target-min
average duration) for the 5 non-JPY majors, then:
  - features windowed in WALL-CLOCK time (rolling '96h'/'48h'); FFD memory matched
    to ~480h of bars; forward returns WALL-CLOCK-aligned via searchsorted to the
    bar ~h hours ahead (bars are irregular in time).
  - pooled Spearman IC (5 ex-JPY) | sign/5 | non-overlap, at h=24h,48h.
  - compares to the TIME-bar (1h flow) baseline computed the same wall-clock way.
  - FRACDIFF diagnostic: min ADF-stationary d on tick-bar vs time-bar log-price.

Usage: uv run python scripts/fx_coint/factor_ic_tickbars.py [TARGET_MIN]
"""
from __future__ import annotations

import glob
import os
import sys

import numpy as np
import pandas as pd
import pyarrow.parquet as pq
from scipy import stats
from statsmodels.tsa.stattools import adfuller

TICK_DIR = os.path.expanduser("~/Desktop/dukascopy_ticks")
POOL = ["AUDUSD", "EURUSD", "GBPUSD", "USDCAD", "USDCHF"]
FWD_HOURS = [24, 48]


def ffd_weights(d: float, width: int) -> np.ndarray:
    w = [1.0]
    for k in range(1, width):
        w.append(-w[-1] * (d - k + 1) / k)
    return np.array(w[::-1])  # oldest..newest


def ffd_series(logp: np.ndarray, d: float, width: int) -> np.ndarray:
    w = ffd_weights(d, width)
    valid = np.convolve(logp, w[::-1], "valid")  # trailing-window dot
    out = np.full(len(logp), np.nan)
    out[width - 1:] = valid
    return out


def calib_N(files: list[str], target_min: float) -> tuple[int, float]:
    rows = sum(pq.ParquetFile(f).metadata.num_rows for f in files)
    t0 = pd.Timestamp(pd.read_parquet(files[0], columns=["timestamp"]).iloc[0, 0])
    t1 = pd.Timestamp(pd.read_parquet(files[-1], columns=["timestamp"]).iloc[-1, 0])
    minutes = (t1 - t0).total_seconds() / 60
    N = max(int(round(rows / (minutes / target_min))), 20)
    return N, rows / minutes  # ticks/min


def build_tick_close(files: list[str], N: int) -> pd.Series:
    """Memory-safe incremental close-only tick bars (close at every N-th tick)."""
    out_ts, out_mid = [], []
    gmod = 0
    for f in files:
        d = pd.read_parquet(f, columns=["timestamp", "mid"])
        ts = d["timestamp"].to_numpy()
        mid = d["mid"].to_numpy()
        first = (N - 1 - gmod) % N
        idx = np.arange(first, len(mid), N)
        out_ts.append(ts[idx])
        out_mid.append(mid[idx])
        gmod = (gmod + len(mid)) % N
    s = pd.Series(np.concatenate(out_mid), index=pd.DatetimeIndex(np.concatenate(out_ts)))
    return s[~s.index.duplicated()].sort_index()


def features_and_fwd(close: pd.Series, bars_per_h: float) -> pd.DataFrame:
    logp = np.log(close)
    v = logp.to_numpy()
    ret = (logp.diff() * 1e4)
    d = pd.DataFrame(index=close.index)
    # wall-clock-windowed features
    d["pxdev_96h"] = ((logp - logp.rolling("96h").mean()) / logp.rolling("96h").std()).shift(1)
    d["skew_48h"] = ret.rolling("48h").skew().shift(1)
    width = max(int(480 * bars_per_h), 50)
    fd = ffd_series(v, 0.1, width)
    fd = (fd - np.nanmean(fd)) / np.nanstd(fd)
    d["ffd_0.1"] = pd.Series(fd, index=close.index).shift(1)
    # wall-clock-aligned forward returns
    tnum = close.index.view("int64")
    n = len(v)
    ar = np.arange(n)
    for h in FWD_HOURS:
        j = np.searchsorted(tnum, tnum + int(h * 3600 * 1e9), side="left")
        valid = j < n
        fwd = np.full(n, np.nan)
        fwd[valid] = (v[j[valid]] - v[ar[valid]]) * 1e4
        d[f"y{h}"] = fwd
    return d


def pooled_ic(data: dict, feat: str, h: int, bars_per_h: dict):
    full, novs = [], []
    for s in POOL:
        dd = data[s][[feat, f"y{h}"]].replace([np.inf, -np.inf], np.nan).dropna()
        if len(dd) < 500:
            continue
        full.append(stats.spearmanr(dd[feat], dd[f"y{h}"])[0])
        step = max(int(h * bars_per_h[s]), 1)
        no = dd.iloc[::step]
        if len(no) > 150:
            novs.append(stats.spearmanr(no[feat], no[f"y{h}"])[0])
    full = np.array(full)
    ic = full.mean()
    sgn = int((np.sign(full) == np.sign(ic)).sum())
    return ic, sgn, (np.mean(novs) if novs else np.nan)


def min_stationary_d(logp: np.ndarray, label: str) -> None:
    for d in [0.05, 0.1, 0.2, 0.3, 0.4, 0.5]:
        width = 400
        fd = ffd_series(logp, d, width)
        fd = fd[~np.isnan(fd)]
        s = fd[:: max(1, len(fd) // 8000)]
        p = adfuller(s, maxlag=10, autolag=None)[1]
        if p < 0.05:
            print(f"  {label}: min ADF-stationary d* = {d:.2f}  (ADF p={p:.4f})")
            return
    print(f"  {label}: not stationary up to d=0.5")


def main() -> None:
    target_min = float(sys.argv[1]) if len(sys.argv) > 1 else 30.0
    pd.set_option("display.width", 200)

    data, bph = {}, {}
    for s in POOL:
        files = sorted(glob.glob(f"{TICK_DIR}/{s}/{s}_*_ticks.parquet"))
        N, tpm = calib_N(files, target_min)
        close = build_tick_close(files, N)
        bph[s] = len(close) / ((close.index[-1] - close.index[0]).total_seconds() / 3600)
        data[s] = features_and_fwd(close, bph[s])
        print(f"  {s}: N={N} ticks/bar ({tpm:.0f} tick/min), {len(close):,} tick-bars, "
              f"{bph[s]:.1f} bars/h")

    print("\n" + "=" * 96)
    print(f"FACTOR IC on TICK bars (~{target_min:.0f}min avg) — pooled Spearman (5 ex-JPY) | sign/5 | non-overlap")
    print("=" * 96)
    feats = ["pxdev_96h", "ffd_0.1", "skew_48h"]
    for h in FWD_HOURS:
        print(f"\n  forward {h}h:")
        for f in feats:
            ic, sgn, nov = pooled_ic(data, f, h, bph)
            print(f"    {f:12s} IC={ic:+.4f}  {sgn}/5  nov={nov:+.4f}")

    print("\n" + "=" * 96)
    print("FRACDIFF diagnostic — min ADF-stationary d* (EURUSD): tick bars vs 1h time bars")
    print("=" * 96)
    eur_tick = np.log(build_tick_close(
        sorted(glob.glob(f"{TICK_DIR}/EURUSD/EURUSD_*_ticks.parquet")),
        calib_N(sorted(glob.glob(f"{TICK_DIR}/EURUSD/EURUSD_*_ticks.parquet")), target_min)[0],
    ).to_numpy())
    min_stationary_d(eur_tick, "EURUSD TICK-bar log-price")
    eur_time = np.log(pd.read_parquet("data/tick_bars/EURUSD_1h_flow.parquet")["mid"].to_numpy())
    min_stationary_d(eur_time, "EURUSD 1h TIME-bar log-price")

    print("\nBaseline reference (1h TIME bars, prior run): ffd_0.1@48h IC -0.0655 5/5; "
          "pxdev_96h@48h -0.0245 5/5; skew_48h@48h -0.0440 5/5")


if __name__ == "__main__":
    main()
