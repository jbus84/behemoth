"""Do the reversion / skew factors survive on TICK bars (vs TIME bars)?

Rebuilds px_dev (price deviation), FFD reversion, and skew on TICK bars
(1000-tick bars, ~20min avg) with features windowed in WALL-CLOCK time and
forward returns WALL-CLOCK-aligned (searchsorted to bar ~h hours ahead).
Compares pooled Spearman IC to the 1h TIME-bar baseline computed the same way.
Also runs fractional-diff diagnostic: min stationary d on tick bars vs time bars.

Usage:
    uv run python scripts/fx_coint/factor_ic_tickbars.py
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

# Data lives in the main repo checkout (worktree may not have the symlink)
DATA_DIR = Path("/Users/danielfisher/repositories/behemoth/data/tick_bars")

POOL = ["AUDUSD", "EURUSD", "GBPUSD", "USDCAD", "USDCHF"]
HORIZONS_H = [2, 6, 24, 48]
D_GRID = [0.1, 0.2, 0.3, 0.4, 0.5, 0.7]

# Target average tick-bar duration in minutes (1000tick ~20min)
TICK_SIZE = 1000


# ------------------------------------------------------------------
# Fractional differencing (fixed-width window, AFML ch.5)
# ------------------------------------------------------------------
def ffd_weights(d: float, thres: float = 1e-4) -> np.ndarray:
    w = [1.0]
    k = 1
    while True:
        w_ = -w[-1] * (d - k + 1) / k
        if abs(w_) < thres:
            break
        w.append(w_)
        k += 1
    return np.array(w[::-1])  # oldest..newest


def frac_diff_ffd(series: pd.Series, d: float, thres: float = 1e-4) -> pd.Series:
    w = ffd_weights(d, thres)
    width = len(w)
    vals = series.to_numpy(dtype=float)
    out = np.full(len(vals), np.nan)
    for i in range(width - 1, len(vals)):
        out[i] = np.dot(w, vals[i - width + 1 : i + 1])
    return pd.Series(out, index=series.index)


def min_stationary_d(logp: pd.Series) -> tuple[float, int]:
    """Smallest d in D_GRID whose ADF rejects unit root at 5%."""
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


# ------------------------------------------------------------------
# Bar loaders
# ------------------------------------------------------------------
def load_tick_bars(sym: str, size: int = TICK_SIZE) -> pd.DataFrame:
    """Load pre-built tick bars; derive mid from close_bid/close_ask."""
    path = DATA_DIR / f"{sym}_{size}tick.parquet"
    df = pd.read_parquet(path)
    df["ts"] = pd.to_datetime(df["close_ts"], utc=True)
    df["mid"] = (df["close_bid"] + df["close_ask"]) / 2.0
    df = df.sort_values("ts").reset_index(drop=True)
    return df[["ts", "mid", "close_bid", "close_ask", "spread"]]


def load_time_bars(sym: str, freq: str = "1h") -> pd.DataFrame:
    """Load 1h (or 30m) flow bars; mid already present."""
    path = DATA_DIR / f"{sym}_{freq}_flow.parquet"
    df = pd.read_parquet(path)
    df["ts"] = pd.to_datetime(df["bucket"], utc=True)
    df = df.sort_values("ts").reset_index(drop=True)
    return df[["ts", "mid", "rvol_bps", "spread_bps"]]


# ------------------------------------------------------------------
# Feature builders (wall-clock rolling on irregular bar index)
# ------------------------------------------------------------------
def build_features(
    df: pd.DataFrame,
    bar_type: str,
    d_star: float | None = None,
) -> pd.DataFrame:
    """Return DataFrame indexed by ts with features + forward returns.

    Features are windowed in WALL-CLOCK time, not bar count.
    Forward returns are WALL-CLOCK aligned (searchsorted).
    """
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

    # --- px_dev (level z, d≈0 family) --- wall-clock rolling ---
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
    for wh in (2, 6, 12, 24):
        wh_td = pd.Timedelta(hours=wh)
        d[f"mom_{wh}h"] = r.rolling(wh_td, min_periods=max(2, wh // 4)).sum().shift(1)

    # --- realized vol --- wall-clock rolling ---
    d["rvol_24h"] = r.rolling("24h", min_periods=6).std().shift(1)
    d["rvol_48h"] = r.rolling("48h", min_periods=12).std().shift(1)

    # --- forward returns (wall-clock aligned via searchsorted) ---
    ts_arr = df.index.to_numpy()
    # strip timezone for numpy arithmetic
    ts_ns = pd.DatetimeIndex(ts_arr).tz_localize(None).to_numpy()
    logp_arr = logp.to_numpy()
    for h in HORIZONS_H:
        target = ts_ns + np.timedelta64(h, "h")
        idx = np.searchsorted(ts_ns, target, side="right") - 1
        idx = np.clip(idx, 0, len(ts_arr) - 1)
        d[f"y_{h}h"] = (logp_arr[idx] - logp_arr) * 1e4

    # lag to avoid leakage (features at t predict return from t to t+h)
    y_cols = [c for c in d.columns if c.startswith("y_")]
    feat_cols = [c for c in d.columns if not c.startswith("y_") and c not in ("logp", "r")]

    # drop rows with any feature or target NaN
    finite = d[feat_cols + y_cols].notna().all(axis=1)
    d = d[finite]

    # drop rows immediately after a time gap (preserve shift relationships).
    # adaptive threshold: 3x median bar spacing (avoids killing regular time-bar gaps)
    if len(d) > 10:
        median_gap = d.index.to_series().diff().dropna().median()
        gap_thresh = max(median_gap * 3, pd.Timedelta("30min"))
        gaps = d.index.to_series().diff() > gap_thresh
        d = d[~gaps.values]

    # liquid-session filter (7-21 UTC)
    hour = d.index.hour
    d = d[(hour >= 7) & (hour < 21) & (d.index.dayofweek < 5)]

    return d.reset_index().rename(columns={"index": "ts"})


# ------------------------------------------------------------------
# IC engine
# ------------------------------------------------------------------
def pooled_ic(data: dict[str, pd.DataFrame], feat: str, target: str) -> dict:
    """Pooled Spearman IC across symbols."""
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
        return dict(ic=np.nan, t=np.nan, p=1.0, sign="0/5", n_valid=0, per_sym={})
    ic = float(np.nanmean(ics))
    se = float(np.nanstd(ics, ddof=1) / np.sqrt(valid.sum()))
    t = ic / se if se > 0 else np.nan
    p = 2 * stats.t.sf(abs(t), df=valid.sum() - 1) if np.isfinite(t) else 1.0
    sgn = int((np.sign(ics[valid]) == np.sign(ic)).sum())
    return dict(
        ic=ic,
        t=t,
        p=p,
        sign=f"{sgn}/{valid.sum()}",
        n_valid=int(valid.sum()),
        per_sym={s: float(ics[i]) for i, s in enumerate(data.keys()) if np.isfinite(ics[i])},
    )


def bh_reject(pvals: list[float], q: float = 0.10) -> list[bool]:
    p = np.asarray(pvals, float)
    m = len(p)
    order = np.argsort(p)
    thresh = q * (np.arange(1, m + 1)) / m
    passed = p[order] <= thresh
    rej = np.zeros(m, bool)
    if passed.any():
        kmax = np.max(np.where(passed)[0])
        rej[order[: kmax + 1]] = True
    return rej.tolist()


# ------------------------------------------------------------------
# Main
# ------------------------------------------------------------------
def main() -> None:
    pd.set_option("display.width", 200, "display.float_format", lambda x: f"{x:8.4f}")

    print("=" * 96)
    print("FACTOR IC ON TICK BARS vs TIME BARS — wall-clock features + returns")
    print("=" * 96)
    print(f"Tick bars: {TICK_SIZE}tick (~20min avg)")
    print("Time bars: 1h")
    print(f"Symbols: {POOL}")
    print(f"Horizons: {HORIZONS_H}h")
    print()

    # ------------------------------------------------------------------
    # 1. FFD diagnostic: min stationary d
    # ------------------------------------------------------------------
    print("-" * 96)
    print("1. FRACTIONAL DIFF DIAGNOSTIC — min stationary d (ADF<0.05)")
    print("-" * 96)
    diag_rows = []
    for sym in POOL + ["USDJPY"]:
        # tick bars
        tdf = load_tick_bars(sym, TICK_SIZE)
        d_tick, w_tick = min_stationary_d(np.log(tdf["mid"]))
        # time bars
        hdf = load_time_bars(sym, "1h")
        d_time, w_time = min_stationary_d(np.log(hdf["mid"]))
        diag_rows.append(
            dict(symbol=sym, d_tick=d_tick, w_tick=w_tick, d_time=d_time, w_time=w_time)
        )
        print(f"  {sym}: tick d*={d_tick:.2f} (win={w_tick}), time d*={d_time:.2f} (win={w_time})")
    print()

    # ------------------------------------------------------------------
    # 2. Build features
    # ------------------------------------------------------------------
    print("-" * 96)
    print("2. BUILD FEATURES (tick bars + time bars)")
    print("-" * 96)

    tick_data: dict[str, pd.DataFrame] = {}
    time_data: dict[str, pd.DataFrame] = {}
    for sym in POOL:
        # tick
        tdf = load_tick_bars(sym, TICK_SIZE)
        # use a pooled median d* for tick (or per-symbol)
        tick_data[sym] = build_features(tdf, "tick", d_star=None)
        # time
        hdf = load_time_bars(sym, "1h")
        time_data[sym] = build_features(hdf, "time", d_star=None)
        print(f"  {sym}: tick {len(tick_data[sym]):,} bars, time {len(time_data[sym]):,} bars")
    print()

    # ------------------------------------------------------------------
    # 3. Feature IC comparison
    # ------------------------------------------------------------------
    print("-" * 96)
    print("3. POOLED SPEARMAN IC — tick bars vs time bars")
    print("-" * 96)

    all_feats = [
        c
        for c in tick_data[POOL[0]].columns
        if c.startswith(("ffd_", "pxdev_", "skew_", "mom_", "rvol_"))
    ]

    rows = []
    for feat in all_feats:
        for h in HORIZONS_H:
            target = f"y_{h}h"
            tic = pooled_ic(tick_data, feat, target)
            tim = pooled_ic(time_data, feat, target)
            rows.append(
                dict(
                    feature=feat,
                    h=h,
                    tick_ic=tic["ic"],
                    tick_t=tic["t"],
                    tick_p=tic["p"],
                    tick_sign=tic["sign"],
                    time_ic=tim["ic"],
                    time_t=tim["t"],
                    time_p=tim["p"],
                    time_sign=tim["sign"],
                )
            )

    res = pd.DataFrame(rows)
    # BH-FDR per bar-type separately
    for prefix in ("tick", "time"):
        res = res.sort_values(f"{prefix}_p").reset_index(drop=True)
        m = len(res)
        res[f"{prefix}_bh"] = (res.index + 1) / m * 0.10
        res[f"{prefix}_sig"] = res[f"{prefix}_p"] <= res[f"{prefix}_bh"]
        res = res.sort_values(["feature", "h"]).reset_index(drop=True)

    # Show top by |t| on tick bars
    show = res.sort_values("tick_t", key=lambda c: c.abs(), ascending=False).head(30)
    hdr = f"{'feature':>14} {'h':>3} {'tick_IC':>8} {'tick_t':>7} {'tick_p':>7} {'tick_sgn':>7} {'time_IC':>8} {'time_t':>7} {'time_p':>7} {'time_sgn':>7}"
    print(hdr)
    print("-" * len(hdr))
    for _, r in show.iterrows():
        print(
            f"{r['feature']:>14} {r['h']:>3} {r['tick_ic']:>+8.4f} {r['tick_t']:>+7.2f} {r['tick_p']:>7.3f} {r['tick_sign']:>7} "
            f"{r['time_ic']:>+8.4f} {r['time_t']:>+7.2f} {r['time_p']:>7.3f} {r['time_sign']:>7}"
        )
    print()

    # ------------------------------------------------------------------
    # 4. Summary: which features IMPROVE on tick bars?
    # ------------------------------------------------------------------
    print("-" * 96)
    print("4. SUMMARY — features where tick bars improve |IC| over time bars")
    print("-" * 96)
    res["delta_abs_ic"] = res["tick_ic"].abs() - res["time_ic"].abs()
    improves = res[res["delta_abs_ic"] > 0].sort_values("delta_abs_ic", ascending=False)
    print(f"  {len(improves)} / {len(res)} cells have larger |IC| on tick bars")
    if len(improves) > 0:
        print(
            improves[
                ["feature", "h", "tick_ic", "time_ic", "delta_abs_ic", "tick_sign", "time_sign"]
            ]
            .head(15)
            .to_string(index=False)
        )
    print()

    # ------------------------------------------------------------------
    # 5. Headline comparison for key factors
    # ------------------------------------------------------------------
    print("-" * 96)
    print("5. HEADLINE — key reversion / skew / momentum factors")
    print("-" * 96)
    key_feats = [
        "ffd_0.1",
        "ffd_0.2",
        "ffd_0.3",
        "pxdev_48h",
        "pxdev_96h",
        "pxdev_240h",
        "skew_24h",
        "skew_48h",
        "skew_96h",
        "mom_6h",
        "mom_24h",
        "rvol_24h",
    ]
    sub = res[res["feature"].isin(key_feats)].sort_values(["feature", "h"])
    for _, r in sub.iterrows():
        star = " ***" if (r["tick_sig"] and r["tick_ic"] > 0) else ""
        print(
            f"  {r['feature']:>12} h={r['h']:>2}h | tick {r['tick_ic']:>+7.4f} t={r['tick_t']:>+6.2f} {r['tick_sign']:>5} "
            f"| time {r['time_ic']:>+7.4f} t={r['time_t']:>+6.2f} {r['time_sign']:>5}{star}"
        )
    print()

    # ------------------------------------------------------------------
    # 6. Per-symbol detail for top tick factor
    # ------------------------------------------------------------------
    top = res.loc[res["tick_ic"].abs().idxmax()]
    print("-" * 96)
    print(f"6. PER-SYMBOL detail for strongest tick factor: {top['feature']} @ {top['h']}h")
    print("-" * 96)
    tic = pooled_ic(tick_data, top["feature"], f"y_{top['h']}h")
    for sym, icv in sorted(tic["per_sym"].items()):
        print(f"  {sym}: IC = {icv:+.4f}")
    print()

    print("=" * 96)
    print("DONE")
    print("=" * 96)


if __name__ == "__main__":
    main()
