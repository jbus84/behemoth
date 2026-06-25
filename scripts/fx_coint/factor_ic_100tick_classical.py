"""Classical features (FFD, pxdev, skew, momentum) on 100tick bars.

Rebuilds the price-based factor library from factor_ic_tickbars.py but on
100tick (~2min) bars with SHORT wall-clock horizons (15m, 30m, 1h, 2h).
This is the direct comparison to the time-bar baseline table the user
cited (ffd_0.1, pxdev_96h, skew_48h at 15m/30m/1h).

Usage:
    uv run python scripts/fx_coint/factor_ic_100tick_classical.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats
from statsmodels.tsa.stattools import adfuller

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

DATA_DIR = Path("/Users/danielfisher/repositories/behemoth/data/tick_bars")

POOL = ["AUDUSD", "EURUSD", "GBPUSD", "USDCAD", "USDCHF"]
HORIZONS_H = [0.25, 0.5, 1, 2]  # 15min, 30min, 1h, 2h
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


def min_stationary_d(logp: pd.Series) -> tuple[float, int]:
    sample = logp.dropna()
    for d in D_GRID:
        fd = frac_diff_ffd(sample, d).dropna()
        if len(fd) < 1000:
            continue
        s = fd.iloc[:: max(1, len(fd) // 8000)]
        try:
            p = adfuller(s, maxlag=10, autolag=None)[1]
        except Exception:
            continue
        if p < 0.05:
            return d, len(ffd_weights(d))
    return 1.0, 1


def load_tick_bars(sym: str, size: int = TICK_SIZE) -> pd.DataFrame:
    path = DATA_DIR / f"{sym}_{size}tick.parquet"
    df = pd.read_parquet(path)
    df["ts"] = pd.to_datetime(df["timestamp"], utc=True)
    df["mid"] = (df["close_bid"] + df["close_ask"]) / 2.0
    df = df.sort_values("ts").reset_index(drop=True)
    return df[["ts", "mid"]]


def build_features(df: pd.DataFrame, d_star: float | None = None) -> pd.DataFrame:
    """Build classical features on 100tick bars with wall-clock rolling."""
    df = df.copy().set_index("ts").sort_index()
    logp = np.log(df["mid"])
    r = (logp.diff() * 1e4).where(lambda x: x.abs() < 500)

    d = pd.DataFrame(index=df.index)
    d["logp"] = logp
    d["r"] = r

    # --- FFD reversion family ---
    for dd in (0.1, 0.2, 0.3):
        fd = frac_diff_ffd(logp, dd)
        d[f"ffd_{dd}"] = ((fd - fd.mean()) / fd.std()).shift(1)
    if d_star is not None:
        fd = frac_diff_ffd(logp, d_star)
        d["ffd_dstar"] = ((fd - fd.mean()) / fd.std()).shift(1)

    # --- px_dev (level z) --- wall-clock rolling ---
    for wh in (24, 48, 96, 240):
        wh_td = pd.Timedelta(hours=wh)
        rm = logp.rolling(wh_td, min_periods=max(2, wh // 4)).mean()
        rs = logp.rolling(wh_td, min_periods=max(2, wh // 4)).std()
        d[f"pxdev_{wh}h"] = ((logp - rm) / rs.clip(lower=1e-9)).shift(1)

    # --- skew --- wall-clock rolling ---
    for wh in (24, 48, 96):
        wh_td = pd.Timedelta(hours=wh)
        d[f"skew_{wh}h"] = r.rolling(wh_td, min_periods=max(5, wh // 4)).skew().shift(1)

    # --- momentum --- wall-clock rolling ---
    for wh in (1, 2, 6, 12, 24):
        wh_td = pd.Timedelta(hours=wh)
        d[f"mom_{wh}h"] = r.rolling(wh_td, min_periods=max(10, wh * 5)).sum().shift(1)

    # --- realized vol --- wall-clock rolling ---
    d["rvol_1h"] = r.rolling("1h", min_periods=10).std().shift(1)
    d["rvol_6h"] = r.rolling("6h", min_periods=30).std().shift(1)
    d["rvol_24h"] = r.rolling("24h", min_periods=60).std().shift(1)

    # --- forward returns (wall-clock aligned) ---
    ts_arr = df.index.to_numpy()
    ts_ns = pd.DatetimeIndex(ts_arr).tz_localize(None).to_numpy()
    logp_arr = logp.to_numpy()
    for h in HORIZONS_H:
        target = ts_ns + np.timedelta64(int(h * 60), "m")
        idx = np.searchsorted(ts_ns, target, side="right") - 1
        idx = np.clip(idx, 0, len(ts_ns) - 1)
        d[f"y_{h}h"] = (logp_arr[idx] - logp_arr) * 1e4

    y_cols = [c for c in d.columns if c.startswith("y_")]
    feat_cols = [c for c in d.columns if not c.startswith("y_") and c not in ("logp", "r")]

    finite = d[feat_cols + y_cols].notna().all(axis=1)
    d = d[finite]

    if len(d) > 10:
        median_gap = d.index.to_series().diff().dropna().median()
        gap_thresh = max(median_gap * 3, pd.Timedelta("10min"))
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


def partial_ic(data: dict[str, pd.DataFrame], feat: str, target: str, control: str) -> dict:
    pics = []
    for _sym, df in data.items():
        dd = df[[feat, target, control]].dropna()
        if len(dd) < 200:
            pics.append(np.nan)
            continue
        r_fy = stats.spearmanr(dd[feat], dd[target])[0]
        r_fc = stats.spearmanr(dd[feat], dd[control])[0]
        r_yc = stats.spearmanr(dd[target], dd[control])[0]
        den = np.sqrt(max(1 - r_fc**2, 1e-9) * max(1 - r_yc**2, 1e-9))
        pic = (r_fy - r_fc * r_yc) / den
        pics.append(pic)
    pics = np.array(pics)
    valid = np.isfinite(pics)
    if valid.sum() == 0:
        return dict(ic=np.nan, t=np.nan, p=1.0, sign="0/5")
    ic = float(np.nanmean(pics))
    se = float(np.nanstd(pics, ddof=1) / np.sqrt(valid.sum()))
    t = ic / se if se > 0 else np.nan
    p = 2 * stats.t.sf(abs(t), df=valid.sum() - 1) if np.isfinite(t) else 1.0
    sgn = int((np.sign(pics[valid]) == np.sign(ic)).sum())
    return dict(ic=ic, t=t, p=p, sign=f"{sgn}/{valid.sum()}")


def main() -> None:
    pd.set_option("display.width", 220, "display.float_format", lambda x: f"{x:8.4f}")

    print("=" * 96)
    print("CLASSICAL FEATURES ON 100TICK BARS — short-horizon IC")
    print("=" * 96)
    print(f"Symbols: {POOL}")
    print(f"Horizons: {HORIZONS_H}h")
    print()

    # 1. FFD diagnostic
    print("-" * 96)
    print("1. FRACTIONAL DIFF DIAGNOSTIC — min stationary d on 100tick bars")
    print("-" * 96)
    for sym in POOL + ["USDJPY"]:
        tdf = load_tick_bars(sym)
        d_tick, w_tick = min_stationary_d(np.log(tdf["mid"]))
        print(f"  {sym}: 100tick d*={d_tick:.2f} (win={w_tick})")
    print()

    # 2. Build features
    print("-" * 96)
    print("2. BUILD FEATURES")
    print("-" * 96)
    tick_data = {}
    for sym in POOL:
        tdf = load_tick_bars(sym)
        tick_data[sym] = build_features(tdf, d_star=None)
        print(f"  {sym}: {len(tick_data[sym]):,} bars")
    print()

    # 3. Key factor comparison table
    print("-" * 96)
    print("3. KEY FACTORS — 100tick bars vs user baseline (time-bar table)")
    print("-" * 96)
    key_feats = ["ffd_0.1", "ffd_0.2", "ffd_0.3", "pxdev_96h", "pxdev_48h", "pxdev_24h",
                 "skew_48h", "skew_96h", "skew_24h", "mom_1h", "mom_6h", "mom_24h",
                 "rvol_1h", "rvol_6h", "rvol_24h"]

    print(f"{'factor':>16} {'15m':>22} {'30m':>22} {'1h':>22} {'2h':>22}")
    print("-" * 110)
    for feat in key_feats:
        cells = []
        for h in HORIZONS_H:
            target = f"y_{h}h"
            res = pooled_ic(tick_data, feat, target)
            cells.append(f"{res['ic']:+.4f} {res['sign']} t={res['t']:+.1f}")
        print(f"{feat:>16} {cells[0]:>22} {cells[1]:>22} {cells[2]:>22} {cells[3]:>22}")
    print()

    # 4. Non-overlapping robustness for top feature
    print("-" * 96)
    print("4. NON-OVERLAPPING robustness for ffd_0.1")
    print("-" * 96)
    for h in HORIZONS_H:
        target = f"y_{h}h"
        full = pooled_ic(tick_data, "ffd_0.1", target)
        # non-overlapping: step by ~h hours
        nov_ics = []
        for _sym, df in tick_data.items():
            dd = df[["ffd_0.1", target]].dropna()
            if len(dd) < 50:
                continue
            # step by target horizon in bars (approximate via time)
            step = max(1, int(h * 30))  # ~30 bars per hour at 100tick
            no = dd.iloc[::step]
            if len(no) > 10:
                rho = stats.spearmanr(no["ffd_0.1"], no[target])[0]
                nov_ics.append(rho)
        nov_ic = float(np.nanmean(nov_ics)) if nov_ics else np.nan
        print(f"  h={h:.2f}h: full IC={full['ic']:+.4f} | non-overlap IC={nov_ic:+.4f} | n_sym={len(nov_ics)}")
    print()

    # 5. Per-symbol detail for ffd_0.1 @ 15min
    print("-" * 96)
    print("5. PER-SYMBOL detail: ffd_0.1 @ 15min")
    print("-" * 96)
    res = pooled_ic(tick_data, "ffd_0.1", "y_0.25h")
    for sym, icv in sorted(res["per_sym"].items()):
        print(f"  {sym}: IC = {icv:+.4f}")
    print()

    # 6. Comparison to user's time-bar table
    print("-" * 96)
    print("6. COMPARISON: user's time-bar baseline vs 100tick")
    print("-" * 96)
    print("  User baseline (time bars):")
    print("    ffd_0.1 @ 15m: −0.0655 5/5")
    print("    pxdev_96h @ 15m: −0.0244 5/5")
    print("    skew_48h @ 15m: −0.0351 5/5")
    print()
    print("  100tick bars:")
    for feat in ["ffd_0.1", "pxdev_96h", "skew_48h"]:
        res = pooled_ic(tick_data, feat, "y_0.25h")
        print(f"    {feat} @ 15m: {res['ic']:+.4f} {res['sign']}")
    print()

    # 7. Partial IC: does FFD add anything beyond price momentum?
    print("-" * 96)
    print("7. PARTIAL IC — ffd_0.1 orthogonal to mom_1h")
    print("-" * 96)
    for h in HORIZONS_H:
        target = f"y_{h}h"
        res = partial_ic(tick_data, "ffd_0.1", target, control="mom_1h")
        print(f"  h={h:.2f}h: partial IC={res['ic']:+.4f} t={res['t']:+.2f} {res['sign']}")
    print()

    print("=" * 96)
    print("DONE")
    print("=" * 96)


if __name__ == "__main__":
    main()
