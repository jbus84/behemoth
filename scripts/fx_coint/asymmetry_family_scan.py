"""Widen the return-asymmetry feature family + REPLICATION-based evaluation.

Statistical stance (deliberate): the pooled p-value is unreliable here (df=4
across 5 symbols vs. overlapping + cross-correlated obs => no clean null). So p
is used ONLY as a screening rank. The accept gate is REPLICATION:
  - orthogonality   : |corr to ffd_0.1 reversion| < 0.3   (carries NEW info)
  - effect size     : partial IC magnitude
  - cross-symbol    : >=4/5 sign agreement
  - temporal        : 1st-half and 2nd-half partial IC SAME sign
  - overlap-robust  : non-overlapping (every-h) partial IC SAME sign
A feature is 'robust' only if orthogonal AND sign-consistent AND stable in BOTH
halves AND under non-overlap. p reported alongside, not used as the gate.

Usage: uv run python scripts/fx_coint/asymmetry_family_scan.py
"""
from __future__ import annotations

import glob
import os

import numpy as np
import pandas as pd
from scipy import stats

BARS = sorted(glob.glob("data/tick_bars/*_1h_flow.parquet"))
POOL = ["AUDUSD", "EURUSD", "GBPUSD", "USDCAD", "USDCHF"]
HORIZONS = [24, 48]


def ffd_weights(d: float, thres: float = 1e-4) -> np.ndarray:
    w = [1.0]; k = 1
    while True:
        w_ = -w[-1] * (d - k + 1) / k
        if abs(w_) < thres:
            break
        w.append(w_); k += 1
    return np.array(w[::-1])


def ffd(s: pd.Series, d: float = 0.1) -> pd.Series:
    w = ffd_weights(d); width = len(w); v = s.to_numpy(float)
    out = np.full(len(v), np.nan)
    for i in range(width - 1, len(v)):
        out[i] = np.dot(w, v[i - width + 1: i + 1])
    return pd.Series(out, index=s.index)


def build(sym_file: str, usd_cum: pd.Series) -> pd.DataFrame:
    df = pd.read_parquet(sym_file)
    df["bucket"] = pd.to_datetime(df["bucket"]); df = df.set_index("bucket").sort_index()
    logp = np.log(df["mid"])
    r = (logp.diff() * 1e4).where(lambda x: x.abs() < 500)
    d = pd.DataFrame(index=df.index)
    fd = ffd(logp, 0.1)
    d["base"] = ((fd - fd.mean()) / fd.std()).shift(1)

    # --- asymmetry family ---
    for w in (12, 24, 48, 96):
        d[f"skew{w}"] = r.rolling(w).skew().shift(1)
        # downside-vol share
        dn = r.clip(upper=0).rolling(w).std()
        up = r.clip(lower=0).rolling(w).std()
        d[f"downshare{w}"] = (dn / (dn + up).clip(lower=1e-9)).shift(1)
        # signed: recent move sign x its skew (does asymmetry depend on direction?)
        d[f"sskew{w}"] = (np.sign(r.rolling(w).sum()) * r.rolling(w).skew()).shift(1)
    # up/down vol gap (normalized)
    d["voldiff24"] = ((r.clip(lower=0).rolling(24).std() - r.clip(upper=0).rolling(24).std())
                      / r.abs().rolling(24).std().clip(lower=1e-9)).shift(1)
    # co-skewness with USD basket: corr of own ret with squared USD move
    usd_ret = usd_cum.diff()
    d["coskew_usd"] = (r.rolling(48).cov(usd_ret**2)).shift(1)

    for h in HORIZONS:
        d[f"y{h}"] = (logp.shift(-h) - logp) * 1e4
    return d


def partial_ic(x, y, z):
    rxy = stats.spearmanr(x, y)[0]; rxz = stats.spearmanr(x, z)[0]; ryz = stats.spearmanr(y, z)[0]
    den = np.sqrt(max(1 - rxz**2, 1e-9) * max(1 - ryz**2, 1e-9))
    return (rxy - rxz * ryz) / den, rxz


def main() -> None:
    pd.set_option("display.width", 220, "display.float_format", lambda x: f"{x:8.4f}")
    files = {os.path.basename(f).split("_")[0]: f for f in BARS}
    # USD basket cumulative (for co-skew)
    rets = {}
    for s in POOL:
        m = pd.read_parquet(files[s]); m["bucket"] = pd.to_datetime(m["bucket"])
        m = m.set_index("bucket").sort_index()
        rr = np.log(m["mid"]).diff() * 1e4
        rets[s] = (rr - rr.mean()) / rr.std()
    usd_cum = pd.DataFrame(rets).mean(axis=1).cumsum()

    data = {s: build(files[s], usd_cum) for s in POOL}
    cands = [c for c in data[POOL[0]].columns if c != "base" and not c.startswith("y")]

    rows = []
    for f in cands:
        for h in HORIZONS:
            full, corrs, h1s, h2s, nov = [], [], [], [], []
            for s in POOL:
                dd = data[s][[f, "base", f"y{h}"]].replace([np.inf, -np.inf], np.nan).dropna()
                if len(dd) < 800 or dd[f].nunique() < 5:
                    continue
                pic, rxz = partial_ic(dd[f], dd[f"y{h}"], dd["base"]); full.append(pic); corrs.append(rxz)
                half = len(dd) // 2
                h1s.append(partial_ic(dd[f].iloc[:half], dd[f"y{h}"].iloc[:half], dd["base"].iloc[:half])[0])
                h2s.append(partial_ic(dd[f].iloc[half:], dd[f"y{h}"].iloc[half:], dd["base"].iloc[half:])[0])
                no = dd.iloc[::h]  # non-overlapping
                if len(no) > 200:
                    nov.append(partial_ic(no[f], no[f"y{h}"], no["base"])[0])
            if len(full) < 5:
                continue
            full = np.array(full); ic = full.mean()
            t = ic / (full.std(ddof=1) / np.sqrt(len(full)))
            p = 2 * stats.t.sf(abs(t), df=len(full) - 1)
            sgn = int((np.sign(full) == np.sign(ic)).sum())
            half_stable = np.sign(np.mean(h1s)) == np.sign(np.mean(h2s)) == np.sign(ic)
            nov_ic = np.mean(nov) if nov else np.nan
            nov_ok = np.isfinite(nov_ic) and np.sign(nov_ic) == np.sign(ic)
            orth = abs(np.mean(corrs)) < 0.3
            robust = orth and sgn >= 4 and half_stable and nov_ok
            rows.append(dict(feature=f, h=h, ic=ic, corr_base=np.mean(corrs),
                             sign=f"{sgn}/5", h1=np.mean(h1s), h2=np.mean(h2s),
                             nov_ic=nov_ic, p_screen=p, robust=robust))
    res = pd.DataFrame(rows)
    res = res.reindex(res.ic.abs().sort_values(ascending=False).index)

    print("=" * 120)
    print("ASYMMETRY FAMILY — replication-based scan (p is a SCREEN only, not the gate)")
    print("  robust = |corr_base|<0.3 AND >=4/5 sign AND both halves same sign AND non-overlap same sign")
    print("=" * 120)
    print(res[["feature", "h", "ic", "corr_base", "sign", "h1", "h2", "nov_ic", "p_screen", "robust"]]
          .to_string(index=False))

    rob = res[res["robust"]]
    print(f"\nROBUST (replicating) asymmetry features: {len(rob)}")
    if len(rob):
        print(rob[["feature", "h", "ic", "corr_base", "sign", "h1", "h2", "nov_ic"]].to_string(index=False))
        print("\n  -> these carry orthogonal info to reversion AND replicate across symbols,")
        print("     time halves, and non-overlapping samples. Promote to net-of-cost backtest.")


if __name__ == "__main__":
    main()
