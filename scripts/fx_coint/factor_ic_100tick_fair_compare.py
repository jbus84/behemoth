"""Fair comparison: classical features on 100tick bars at LONG horizons.

User baseline (time bars) shows ffd_0.1@48h IC ≈−0.065 invariant across 15m/30m/1h
resolutions. The forward horizon was held constant in WALL-CLOCK time (48h), not
scaled to bar count.

This script rebuilds ffd_0.1, pxdev_96h, skew_48h on 100tick bars and computes IC
vs the SAME forward horizons (24h, 48h) for direct comparison.

Usage:
    uv run python scripts/fx_coint/factor_ic_100tick_fair_compare.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

DATA_DIR = Path("/Users/danielfisher/repositories/behemoth/data/tick_bars")

POOL = ["AUDUSD", "EURUSD", "GBPUSD", "USDCAD", "USDCHF"]
HORIZONS_H = [24, 48]
TICK_SIZE = 100
D_GRID = [0.1, 0.2, 0.3, 0.4, 0.5, 0.7]


def ffd_weights(d: float, thres: float = 1e-4) -> np.ndarray:
    w = [1.0]
    k = 1
    while True:
        w_ = -w[-1] * (d - k + 1) / k
        if abs(w_) < thres:
            break
        w.append(w_)
        k += 1
    return np.array(w[::-1])


def frac_diff_ffd(series: pd.Series, d: float, thres: float = 1e-4) -> pd.Series:
    w = ffd_weights(d, thres)
    width = len(w)
    vals = series.to_numpy(dtype=float)
    out = np.full(len(vals), np.nan)
    for i in range(width - 1, len(vals)):
        out[i] = np.dot(w, vals[i - width + 1 : i + 1])
    return pd.Series(out, index=series.index)


def load_tick_bars(sym: str, size: int = TICK_SIZE) -> pd.DataFrame:
    path = DATA_DIR / f"{sym}_{size}tick.parquet"
    df = pd.read_parquet(path)
    df["ts"] = pd.to_datetime(df["timestamp"], utc=True)
    df["mid"] = (df["close_bid"] + df["close_ask"]) / 2.0
    df = df.sort_values("ts").reset_index(drop=True)
    return df[["ts", "mid"]]


def load_time_bars(sym: str, freq: str = "1h") -> pd.DataFrame:
    path = DATA_DIR / f"{sym}_{freq}_flow.parquet"
    df = pd.read_parquet(path)
    df["ts"] = pd.to_datetime(df["bucket"], utc=True)
    df["mid"] = df["mid"]
    df = df.sort_values("ts").reset_index(drop=True)
    return df[["ts", "mid"]]


def build_features(df: pd.DataFrame, d_star: float | None = None) -> pd.DataFrame:
    """Build classical features with wall-clock rolling."""
    df = df.copy().set_index("ts").sort_index()
    logp = np.log(df["mid"])
    r = (logp.diff() * 1e4).where(lambda x: x.abs() < 500)

    d = pd.DataFrame(index=df.index)
    d["logp"] = logp
    d["r"] = r

    for dd in (0.1, 0.2, 0.3):
        fd = frac_diff_ffd(logp, dd)
        d[f"ffd_{dd}"] = ((fd - fd.mean()) / fd.std()).shift(1)
    if d_star is not None:
        fd = frac_diff_ffd(logp, d_star)
        d["ffd_dstar"] = ((fd - fd.mean()) / fd.std()).shift(1)

    for wh in (24, 48, 96, 240):
        wh_td = pd.Timedelta(hours=wh)
        rm = logp.rolling(wh_td, min_periods=max(2, wh // 4)).mean()
        rs = logp.rolling(wh_td, min_periods=max(2, wh // 4)).std()
        d[f"pxdev_{wh}h"] = ((logp - rm) / rs.clip(lower=1e-9)).shift(1)

    for wh in (24, 48, 96):
        wh_td = pd.Timedelta(hours=wh)
        d[f"skew_{wh}h"] = r.rolling(wh_td, min_periods=max(5, wh // 4)).skew().shift(1)

    for wh in (2, 6, 12, 24):
        wh_td = pd.Timedelta(hours=wh)
        d[f"mom_{wh}h"] = r.rolling(wh_td, min_periods=max(2, wh // 4)).sum().shift(1)

    d["rvol_24h"] = r.rolling("24h", min_periods=6).std().shift(1)
    d["rvol_48h"] = r.rolling("48h", min_periods=12).std().shift(1)

    # forward returns (wall-clock aligned)
    ts_arr = df.index.to_numpy()
    ts_ns = pd.DatetimeIndex(ts_arr).tz_localize(None).to_numpy()
    logp_arr = logp.to_numpy()
    for h in HORIZONS_H:
        target = ts_ns + np.timedelta64(h, "h")
        idx = np.searchsorted(ts_ns, target, side="right") - 1
        idx = np.clip(idx, 0, len(ts_ns) - 1)
        d[f"y_{h}h"] = (logp_arr[idx] - logp_arr) * 1e4

    y_cols = [c for c in d.columns if c.startswith("y_")]
    feat_cols = [c for c in d.columns if not c.startswith("y_") and c not in ("logp", "r")]

    finite = d[feat_cols + y_cols].notna().all(axis=1)
    d = d[finite]

    if len(d) > 10:
        median_gap = d.index.to_series().diff().dropna().median()
        gap_thresh = max(median_gap * 3, pd.Timedelta("30min"))
        gaps = d.index.to_series().diff() > gap_thresh
        d = d[~gaps.values]

    hour = d.index.hour
    d = d[(hour >= 7) & (hour < 21) & (d.index.dayofweek < 5)]

    return d.reset_index().rename(columns={"index": "ts"})


def pooled_ic(data: dict[str, pd.DataFrame], feat: str, target: str) -> dict:
    ics = []
    for _sym, df in data.items():
        dd = df[[feat, target]].dropna()
        if len(dd) < 200:
            ics.append(np.nan)
            continue
        rho = stats.spearmanr(dd[feat], dd[target])[0]
        ics.append(rho)
    ics = np.array(ics)
    valid = np.isfinite(ics)
    if valid.sum() == 0:
        return dict(ic=np.nan, t=np.nan, p=1.0, sign="0/5", per_sym={})
    ic = float(np.nanmean(ics))
    se = float(np.nanstd(ics, ddof=1) / np.sqrt(valid.sum()))
    t = ic / se if se > 0 else np.nan
    p = 2 * stats.t.sf(abs(t), df=valid.sum() - 1) if np.isfinite(t) else 1.0
    sgn = int((np.sign(ics[valid]) == np.sign(ic)).sum())
    return dict(
        ic=ic, t=t, p=p, sign=f"{sgn}/{valid.sum()}", n_valid=int(valid.sum()),
        per_sym={s: float(ics[i]) for i, s in enumerate(data.keys()) if np.isfinite(ics[i])},
    )


def main() -> None:
    pd.set_option("display.width", 220, "display.float_format", lambda x: f"{x:8.4f}")

    print("=" * 96)
    print("FAIR COMPARISON — classical features at LONG horizons (24h, 48h)")
    print("=" * 96)
    print()

    # Build tick bars
    tick_data = {}
    for sym in POOL:
        tdf = load_tick_bars(sym)
        tick_data[sym] = build_features(tdf)
        print(f"  {sym} 100tick: {len(tick_data[sym]):,} bars")

    # Build time bars
    time_data = {}
    for sym in POOL:
        hdf = load_time_bars(sym, "1h")
        time_data[sym] = build_features(hdf)
        print(f"  {sym} 1h:     {len(time_data[sym]):,} bars")
    print()

    # Direct comparison
    key_feats = ["ffd_0.1", "ffd_0.2", "ffd_0.3", "pxdev_96h", "pxdev_48h", "pxdev_24h",
                 "skew_48h", "skew_96h", "skew_24h", "mom_2h", "mom_6h", "mom_12h", "mom_24h"]

    print("-" * 96)
    print("DIRECT COMPARISON: 100tick bars vs 1h time bars")
    print("-" * 96)
    print(f"{'feature':>14} {'h':>3} {'100tick_IC':>10} {'100tick_t':>8} {'1h_IC':>10} {'1h_t':>8} {'delta':>8} {'sign':>6}")
    print("-" * 80)
    for feat in key_feats:
        for h in HORIZONS_H:
            target = f"y_{h}h"
            tic = pooled_ic(tick_data, feat, target)
            tim = pooled_ic(time_data, feat, target)
            delta = tic["ic"] - tim["ic"]
            print(f"{feat:>14} {h:>3}h {tic['ic']:>+10.4f} {tic['t']:>+8.2f} {tim['ic']:>+10.4f} {tim['t']:>+8.2f} {delta:>+8.4f} {tic['sign']:>6}")
    print()

    # Non-overlap for ffd_0.1 @ 48h
    print("-" * 96)
    print("NON-OVERLAPPING robustness: ffd_0.1 @ 48h")
    print("-" * 96)
    for label, data in [("100tick", tick_data), ("1h_time", time_data)]:
        res = pooled_ic(data, "ffd_0.1", "y_48h")
        nov_ics = []
        for _sym, df in data.items():
            dd = df[["ffd_0.1", "y_48h"]].dropna()
            if len(dd) < 50:
                continue
            step = max(1, int(48 * 30)) if label == "100tick" else max(1, 48)
            no = dd.iloc[::step]
            if len(no) > 10:
                rho = stats.spearmanr(no["ffd_0.1"], no["y_48h"])[0]
                nov_ics.append(rho)
        nov_ic = float(np.nanmean(nov_ics)) if nov_ics else np.nan
        print(f"  {label:>10}: full IC={res['ic']:+.4f} | non-overlap IC={nov_ic:+.4f} | n_sym={len(nov_ics)}")
    print()

    # Per-symbol
    print("-" * 96)
    print("PER-SYMBOL: ffd_0.1 @ 48h")
    print("-" * 96)
    tic = pooled_ic(tick_data, "ffd_0.1", "y_48h")
    tim = pooled_ic(time_data, "ffd_0.1", "y_48h")
    print(f"  {'symbol':>8} {'100tick':>10} {'1h_time':>10}")
    print("  " + "-" * 32)
    for sym in sorted(POOL):
        print(f"  {sym:>8} {tic['per_sym'].get(sym, float('nan')):>+10.4f} {tim['per_sym'].get(sym, float('nan')):>+10.4f}")
    print()

    print("=" * 96)
    print("DONE")
    print("=" * 96)


if __name__ == "__main__":
    main()
