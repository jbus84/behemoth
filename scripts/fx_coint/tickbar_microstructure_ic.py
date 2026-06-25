"""Tick-bar microstructure feature scan.

Tests tick-bar columns that have NO time-bar analogue:
  - intra_bar_momentum   (directional drift inside the bar)
  - quote_revisions      (number of quote changes)
  - hl_pos_frac          (where H/L occurred in the bar, 0-1)
  - high_pos_tick        (which tick the high was on)
  - low_pos_tick         (which tick the low was on)
  - hl_pos_delta_tick    (distance H-L in ticks)
  - bar_return_sign      (-1, 0, +1 direction)
  - spread               (bid-ask at close)

Also builds derived features (revision density, signed momentum, etc.)
and reports pooled Spearman IC vs wall-clock forward returns.

Usage:
    uv run python scripts/fx_coint/tickbar_microstructure_ic.py
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
HORIZONS_H = [2, 6, 24, 48]
TICK_SIZE = 1000


def load_tick_bars(sym: str, size: int = TICK_SIZE) -> pd.DataFrame:
    path = DATA_DIR / f"{sym}_{size}tick.parquet"
    df = pd.read_parquet(path)
    df["ts"] = pd.to_datetime(df["timestamp"], utc=True)
    df["mid"] = (df["close_bid"] + df["close_ask"]) / 2.0
    df = df.sort_values("ts").reset_index(drop=True)
    return df


def build_features(df: pd.DataFrame) -> pd.DataFrame:
    """Build tick-microstructure + price features.

    All features are lagged by 1 bar to avoid leakage.
    Forward returns are wall-clock aligned via searchsorted.
    """
    df = df.copy().set_index("ts").sort_index()
    logp = np.log(df["mid"])
    r = (logp.diff() * 1e4).where(lambda x: x.abs() < 500)

    d = pd.DataFrame(index=df.index)
    d["logp"] = logp
    d["r"] = r

    # --- raw tick-microstructure features (lagged) ---
    d["ibm"] = df["intra_bar_momentum"].shift(1)  # directional drift inside bar
    d["qr"] = df["quote_revisions"].shift(1)  # # quote changes
    d["hl_frac"] = df["hl_pos_frac"].shift(1)  # where H/L occurred in bar
    d["hi_tick"] = df["high_pos_tick"].shift(1)  # which tick the high was on
    d["lo_tick"] = df["low_pos_tick"].shift(1)  # which tick the low was on
    d["hl_delta"] = df["hl_pos_delta_tick"].shift(1)  # distance H-L in ticks
    d["bar_sign"] = df["bar_return_sign"].shift(1).astype(float)  # -1/0/+1 direction
    d["spread"] = df["spread"].shift(1)  # bid-ask spread

    # --- derived tick-microstructure features ---
    d["qr_density"] = (d["qr"] / TICK_SIZE).shift(1)  # revisions per tick
    d["abs_ibm"] = d["ibm"].abs().shift(1)  # bar volatility proxy
    d["ibm_x_sign"] = (d["ibm"] * d["bar_sign"]).shift(1)  # signed momentum
    d["hl_early"] = (d["hl_frac"] < 0.5).astype(float).shift(1)  # H/L in first half?
    d["spread_x_ibm"] = (d["spread"] * d["ibm"]).shift(1)  # spread × momentum
    d["hi_lo_ratio"] = (d["hi_tick"] / d["lo_tick"].clip(lower=1)).shift(1)

    # --- price-based features (for partial-IC baseline) ---
    for wh in (24, 48, 96):
        wh_td = pd.Timedelta(hours=wh)
        d[f"mom_{wh}h"] = r.rolling(wh_td, min_periods=max(2, wh // 4)).sum().shift(1)
        d[f"rvol_{wh}h"] = r.rolling(wh_td, min_periods=max(5, wh // 4)).std().shift(1)

    # --- forward returns (wall-clock aligned) ---
    ts_arr = df.index.to_numpy()
    ts_ns = pd.DatetimeIndex(ts_arr).tz_localize(None).to_numpy()
    logp_arr = logp.to_numpy()
    for h in HORIZONS_H:
        target = ts_ns + np.timedelta64(h, "h")
        idx = np.searchsorted(ts_ns, target, side="right") - 1
        idx = np.clip(idx, 0, len(ts_ns) - 1)
        d[f"y_{h}h"] = (logp_arr[idx] - logp_arr) * 1e4

    # drop NaN; drop post-gap rows
    feat_cols = [c for c in d.columns if not c.startswith("y_") and c not in ("logp", "r")]
    y_cols = [c for c in d.columns if c.startswith("y_")]
    finite = d[feat_cols + y_cols].notna().all(axis=1)
    d = d[finite]

    if len(d) > 10:
        median_gap = d.index.to_series().diff().dropna().median()
        gap_thresh = max(median_gap * 3, pd.Timedelta("30min"))
        gaps = d.index.to_series().diff() > gap_thresh
        d = d[~gaps.values]

    # liquid-session filter (7-21 UTC)
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
        ic=ic,
        t=t,
        p=p,
        sign=f"{sgn}/{valid.sum()}",
        n_valid=int(valid.sum()),
        per_sym={s: float(ics[i]) for i, s in enumerate(data.keys()) if np.isfinite(ics[i])},
    )


def partial_ic(data: dict[str, pd.DataFrame], feat: str, target: str, control: str) -> dict:
    """Partial Spearman IC of feat vs target controlling for control."""
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


def main() -> None:
    pd.set_option("display.width", 220, "display.float_format", lambda x: f"{x:8.4f}")

    print("=" * 96)
    print("TICK-BAR MICROSTRUCTURE FEATURE SCAN")
    print("=" * 96)
    print(f"Symbols: {POOL}")
    print(f"Horizons: {HORIZONS_H}h")
    print()

    # Build
    data = {}
    for sym in POOL:
        df = load_tick_bars(sym)
        data[sym] = build_features(df)
        print(f"  {sym}: {len(data[sym]):,} bars")
    print()

    # Feature list
    all_feats = [
        c
        for c in data[POOL[0]].columns
        if c not in ("ts", "logp", "r")
        and not c.startswith("y_")
        and not c.startswith("mom_")
        and not c.startswith("rvol_")
    ]
    price_feats = [c for c in data[POOL[0]].columns if c.startswith(("mom_", "rvol_"))]

    print("Tick-microstructure features:")
    for f in all_feats:
        print(f"  {f}")
    print()

    # ---- 1. Raw IC ----
    print("-" * 96)
    print("1. RAW POOLED SPEARMAN IC — tick-microstructure features")
    print("-" * 96)
    rows = []
    for feat in all_feats:
        for h in HORIZONS_H:
            target = f"y_{h}h"
            res = pooled_ic(data, feat, target)
            rows.append(
                dict(
                    feature=feat,
                    h=h,
                    ic=res["ic"],
                    t=res["t"],
                    p=res["p"],
                    sign=res["sign"],
                    n=res["n_valid"],
                )
            )
    res = pd.DataFrame(rows)
    res = res.sort_values("t", key=lambda c: c.abs(), ascending=False)
    print(res.head(20).to_string(index=False))
    print()

    # ---- 2. Partial IC controlling for price momentum ----
    print("-" * 96)
    print("2. PARTIAL IC controlling for mom_24h (orthogonal signal)")
    print("-" * 96)
    partial_rows = []
    for feat in all_feats:
        for h in HORIZONS_H:
            target = f"y_{h}h"
            pic_res = partial_ic(data, feat, target, control="mom_24h")
            partial_rows.append(
                dict(
                    feature=feat,
                    h=h,
                    pic=pic_res["ic"],
                    t=pic_res["t"],
                    p=pic_res["p"],
                    sign=pic_res["sign"],
                )
            )
    pres = pd.DataFrame(partial_rows)
    pres = pres.sort_values("t", key=lambda c: c.abs(), ascending=False)
    print(pres.head(20).to_string(index=False))
    print()

    # ---- 3. Best raw vs best partial ----
    print("-" * 96)
    print("3. HEADLINE — tick-microstructure features with |partial IC| > 0.01")
    print("-" * 96)
    merged = res.merge(pres, on=["feature", "h"], suffixes=("_raw", "_part"))
    strong = merged[merged["pic"].abs() > 0.01].sort_values(
        "t_part", key=lambda c: c.abs(), ascending=False
    )
    if len(strong):
        print(
            strong[["feature", "h", "ic", "t_raw", "pic", "t_part", "sign_part"]].to_string(
                index=False
            )
        )
    else:
        print(
            "  No tick-microstructure feature shows |partial IC| > 0.01 after controlling for mom_24h."
        )
    print()

    # ---- 4. Per-symbol detail for best feature ----
    best = res.loc[res["ic"].abs().idxmax()]
    print("-" * 96)
    print(f"4. PER-SYMBOL detail for strongest raw feature: {best['feature']} @ {best['h']}h")
    print("-" * 96)
    raw = pooled_ic(data, best["feature"], f"y_{best['h']}h")
    for sym, icv in sorted(raw["per_sym"].items()):
        print(f"  {sym}: IC = {icv:+.4f}")
    print()

    # ---- 5. Price-feature baseline for context ----
    print("-" * 96)
    print("5. PRICE-BASELINE (mom_24h / rvol_24h) for context")
    print("-" * 96)
    for feat in price_feats:
        for h in HORIZONS_H:
            target = f"y_{h}h"
            res = pooled_ic(data, feat, target)
            print(
                f"  {feat:>12} h={h:>2}h | IC={res['ic']:>+7.4f} t={res['t']:>+6.2f} {res['sign']:>5}"
            )
    print()

    print("=" * 96)
    print("DONE")
    print("=" * 96)


if __name__ == "__main__":
    main()
