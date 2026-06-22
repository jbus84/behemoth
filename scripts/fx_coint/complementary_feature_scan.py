"""Find features with COMPLEMENTARY (orthogonal) information to the known
FFD/level reversion factor.

A feature is only useful if it predicts forward return AFTER controlling for the
reversion signal we already have. We measure PARTIAL Spearman IC controlling for
the base (ffd_0.1), and require: (a) low correlation with base, (b) significant
partial IC, (c) >=4/5 sign consistency, (d) survives BH-FDR.

Candidate families (deliberately NON-price-level, to be orthogonal to reversion):
  VOL REGIME : rvol_z, vol_ratio(short/long), vol_of_vol
  FLOW       : flow_ofi_n (ofi per tick), flow_tick_cum, flow_sign_persist
  ASYMMETRY  : ret_skew_24, downvol_ratio
  ACTIVITY   : n_ticks_z, spread_z
  SESSION    : sin/cos hour, is_london_overlap
  CROSS-SECT : usd_resid_dev (own level dev minus USD-basket level dev)
  TREND-STR  : autocorr_sign / accel

Partial corr: r_xy.z = (r_xy - r_xz r_yz)/sqrt((1-r_xz^2)(1-r_yz^2)), all Spearman.

Usage: uv run python scripts/fx_coint/complementary_feature_scan.py
"""
from __future__ import annotations

import glob
import os

import numpy as np
import pandas as pd
from scipy import stats

BARS = sorted(glob.glob("data/tick_bars/*_1h_flow.parquet"))
POOL = ["AUDUSD", "EURUSD", "GBPUSD", "USDCAD", "USDCHF"]
HORIZONS = [6, 24, 48]


def ffd_weights(d: float, thres: float = 1e-4) -> np.ndarray:
    w = [1.0]; k = 1
    while True:
        w_ = -w[-1] * (d - k + 1) / k
        if abs(w_) < thres:
            break
        w.append(w_); k += 1
    return np.array(w[::-1])


def ffd(series: pd.Series, d: float = 0.1, thres: float = 1e-4) -> pd.Series:
    w = ffd_weights(d, thres); width = len(w)
    v = series.to_numpy(float); out = np.full(len(v), np.nan)
    for i in range(width - 1, len(v)):
        out[i] = np.dot(w, v[i - width + 1 : i + 1])
    return pd.Series(out, index=series.index)


def zscore(s: pd.Series, w: int) -> pd.Series:
    return (s - s.rolling(w).mean()) / s.rolling(w).std()


def load_panel() -> dict[str, pd.DataFrame]:
    raw = {}
    for f in BARS:
        sym = os.path.basename(f).split("_")[0]
        df = pd.read_parquet(f)
        df["bucket"] = pd.to_datetime(df["bucket"])
        df = df.set_index("bucket").sort_index()
        raw[sym] = df
    # common USD basket: mean standardized 1h return across pool
    rets = {}
    for s in POOL:
        r = np.log(raw[s]["mid"]).diff() * 1e4
        rets[s] = (r - r.mean()) / r.std()
    usd = pd.DataFrame(rets).mean(axis=1)  # USD factor (avg standardized return)
    raw["_USD"] = usd
    return raw


def build(sym: str, raw: dict) -> pd.DataFrame:
    df = raw[sym]
    logp = np.log(df["mid"])
    r = (logp.diff() * 1e4).where(lambda x: x.abs() < 500)
    z = (r - r.mean()) / r.std()
    d = pd.DataFrame(index=df.index)

    # BASE reversion factor we control for
    fd = ffd(logp, 0.1)
    d["base"] = ((fd - fd.mean()) / fd.std()).shift(1)

    # --- candidate complementary features (all strictly lagged) ---
    rvol = df["rvol_bps"]
    d["rvol_z"] = zscore(rvol, 96).shift(1)
    d["vol_ratio"] = (rvol.rolling(6).mean() / rvol.rolling(96).mean()).shift(1)
    d["vol_of_vol"] = zscore(rvol.rolling(24).std(), 96).shift(1)
    d["flow_ofi_n"] = (df["flow_ofi"] / df["n_ticks"].clip(lower=1)).shift(1)
    d["flow_tick_cum"] = z.rolling(6).apply(lambda x: 0, raw=True)  # placeholder removed below
    d["flow_ofi_z"] = zscore(df["flow_ofi"], 96).shift(1)
    d["flow_persist"] = np.sign(df["flow_ofi"]).rolling(6).mean().shift(1)
    d["ret_skew24"] = r.rolling(24).skew().shift(1)
    d["downvol_ratio"] = (r.clip(upper=0).rolling(24).std()
                          / r.abs().rolling(24).std().clip(lower=1e-9)).shift(1)
    d["n_ticks_z"] = zscore(df["n_ticks"], 96).shift(1)
    d["spread_z"] = zscore((df["ask"] - df["bid"]) / df["mid"], 96).shift(1)
    hour = df.index.hour
    d["hour_sin"] = np.sin(2 * np.pi * hour / 24)
    d["hour_cos"] = np.cos(2 * np.pi * hour / 24)
    d["is_overlap"] = ((hour >= 12) & (hour < 16)).astype(float)
    # cross-sectional: own level dev minus USD-basket cumulative level dev
    usd_cum = raw["_USD"].cumsum()
    usd_dev = ((usd_cum - usd_cum.rolling(96).mean()) / usd_cum.rolling(96).std())
    own_dev = ((logp - logp.rolling(96).mean()) / logp.rolling(96).std())
    d["usd_resid_dev"] = (own_dev - own_dev.corr(usd_dev) * usd_dev).shift(1)
    d["accel"] = (z - z.shift(6)).shift(1)

    d = d.drop(columns=["flow_tick_cum"])
    for h in HORIZONS:
        d[f"y{h}"] = (logp.shift(-h) - logp) * 1e4
    return d


def partial_spearman(x, y, zc):
    rxy = stats.spearmanr(x, y)[0]
    rxz = stats.spearmanr(x, zc)[0]
    ryz = stats.spearmanr(y, zc)[0]
    denom = np.sqrt(max(1 - rxz**2, 1e-9) * max(1 - ryz**2, 1e-9))
    return (rxy - rxz * ryz) / denom, rxz


def main() -> None:
    pd.set_option("display.width", 200, "display.float_format", lambda x: f"{x:8.4f}")
    raw = load_panel()
    data = {s: build(s, raw) for s in POOL}
    cands = [c for c in data[POOL[0]].columns
             if c not in ("base",) and not c.startswith("y")]

    rows = []
    for f in cands:
        for h in HORIZONS:
            pics, rawics, corrs = [], [], []
            for s in POOL:
                dd = data[s][[f, "base", f"y{h}"]].replace([np.inf, -np.inf], np.nan).dropna()
                if len(dd) < 500 or dd[f].nunique() < 5:
                    continue
                pic, rxz = partial_spearman(dd[f], dd[f"y{h}"], dd["base"])
                pics.append(pic); corrs.append(rxz)
                rawics.append(stats.spearmanr(dd[f], dd[f"y{h}"])[0])
            if len(pics) < 5:
                continue
            pics = np.array(pics)
            pic = pics.mean()
            se = pics.std(ddof=1) / np.sqrt(len(pics))
            t = pic / se if se > 0 else np.nan
            p = 2 * stats.t.sf(abs(t), df=len(pics) - 1) if np.isfinite(t) else 1.0
            sgn = int((np.sign(pics) == np.sign(pic)).sum())
            rows.append(dict(feature=f, h=h, partial_ic=pic, raw_ic=np.mean(rawics),
                             corr_base=np.mean(corrs), t=t, p=p, sign=f"{sgn}/5"))
    res = pd.DataFrame(rows).sort_values("p").reset_index(drop=True)
    m = len(res)
    res["bh"] = res["p"] <= (res.index + 1) / m * 0.10
    res["complementary"] = res["bh"] & res["sign"].isin(["5/5", "4/5"]) & (res["corr_base"].abs() < 0.3)

    print("=" * 100)
    print("COMPLEMENTARY-FEATURE SCAN — partial Spearman IC controlling for ffd_0.1 reversion")
    print(f"  {m} cells, BH-FDR q=0.10. 'complementary' = BH-sig AND >=4/5 sign AND |corr_base|<0.3")
    print("=" * 100)
    print(res[["feature", "h", "partial_ic", "raw_ic", "corr_base", "t", "sign", "bh", "complementary"]]
          .head(25).to_string(index=False))

    comp = res[res["complementary"]]
    print(f"\nCOMPLEMENTARY survivors: {len(comp)}")
    if len(comp):
        print(comp[["feature", "h", "partial_ic", "corr_base", "t", "sign"]]
              .sort_values("t", key=lambda c: c.abs(), ascending=False).to_string(index=False))
    else:
        print("  -> none. No candidate adds orthogonal predictive info beyond reversion.")


if __name__ == "__main__":
    main()
