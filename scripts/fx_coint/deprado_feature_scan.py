"""De Prado Ch17/18/19 feature families, tested for info ORTHOGONAL to the two
known factors (FFD reversion + skew asymmetry).

Discipline (carried over): p-value is a screen only. Accept gate = REPLICATION:
  partial IC (controlling base reversion + skew48) | low corr to controls
  | >=4/5 sign | both time-halves same sign | non-overlap same sign.

Families:
  STRUCT BREAK (Ch17): adf_sup (explosiveness), cusum_csw, smt_exp
  ENTROPY     (Ch18): ent_sign (plug-in, word=3 on FFD-return sign) -- also tested
                      as a CONDITIONING variable for reversion (De Prado's thesis)
  MICRO       (Ch19): vpin, amihud, roll_spread, flow_ac, kyle_t (t-stat feature)

Usage: uv run python scripts/fx_coint/deprado_feature_scan.py
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


# ---------- helpers ----------
def ffd_w(d, thres=1e-4):
    w = [1.0]; k = 1
    while True:
        w_ = -w[-1] * (d - k + 1) / k
        if abs(w_) < thres:
            break
        w.append(w_); k += 1
    return np.array(w[::-1])


def ffd(s, d=0.1):
    w = ffd_w(d); width = len(w); v = s.to_numpy(float); out = np.full(len(v), np.nan)
    for i in range(width - 1, len(v)):
        out[i] = np.dot(w, v[i - width + 1: i + 1])
    return pd.Series(out, index=s.index)


def roll_ols_t(y: pd.Series, x: pd.Series, win: int) -> pd.Series:
    """Vectorized rolling t-stat of slope in y ~ a + b x over `win`."""
    n = win
    Sx = x.rolling(n).sum(); Sy = y.rolling(n).sum()
    Sxx = (x * x).rolling(n).sum(); Sxy = (x * y).rolling(n).sum(); Syy = (y * y).rolling(n).sum()
    den = n * Sxx - Sx * Sx
    b = (n * Sxy - Sx * Sy) / den
    a = (Sy - b * Sx) / n
    sse = Syy - a * Sy - b * Sxy
    sigma2 = sse / (n - 2)
    se_b = np.sqrt(sigma2 * n / den)
    return b / se_b


def adf_sup(logp: pd.Series, wins=(60, 120, 240)) -> pd.Series:
    """SADF approximation: max rolling AR(1) t-stat (Dy ~ a + b*y_lag) over several
    window lengths -> explosiveness (b>0 => bubble/collapse)."""
    dy = logp.diff(); ylag = logp.shift(1)
    ts = [roll_ols_t(dy, ylag, w) for w in wins]
    return pd.concat(ts, axis=1).max(axis=1)


def cusum_csw(logp: pd.Series, win=96) -> pd.Series:
    """Chu-Stinchcombe-White on levels: sup_n (y_t - y_n)/(sigma*sqrt(t-n)),
    approximated over a trailing window (reference n = window start)."""
    dy = logp.diff()
    sig = dy.rolling(win).std()
    yref = logp.shift(win)
    return (logp - yref) / (sig * np.sqrt(win))


def smt_exp(logp: pd.Series, win=96) -> pd.Series:
    """Sub/super-martingale exponential trend: |t| of slope in log y ~ a + b t."""
    t = pd.Series(np.arange(len(logp), dtype=float), index=logp.index)
    return roll_ols_t(logp, t, win).abs()


def plugin_entropy_sign(r: pd.Series, win=168, word=3, step=6) -> pd.Series:
    """Rolling plug-in entropy (word length `word`) of the binary sign sequence,
    computed every `step` bars and forward-filled (slow-moving regime feature)."""
    sign = (r > 0).astype(int).to_numpy()
    out = np.full(len(sign), np.nan)
    for i in range(win, len(sign), step):
        seg = sign[i - win:i]
        counts = {}
        for j in range(len(seg) - word):
            key = seg[j:j + word].tobytes()
            counts[key] = counts.get(key, 0) + 1
        tot = sum(counts.values())
        h = -sum((c / tot) * np.log2(c / tot) for c in counts.values()) / word
        out[i] = h
    return pd.Series(out, index=r.index).ffill()


def build(sym_file):
    df = pd.read_parquet(sym_file); df["bucket"] = pd.to_datetime(df["bucket"])
    df = df.set_index("bucket").sort_index()
    logp = np.log(df["mid"])
    r = (logp.diff() * 1e4).where(lambda x: x.abs() < 500)
    fdr = ffd(logp, 0.1)  # for entropy encoding (memory-preserving) + base
    d = pd.DataFrame(index=df.index)
    d["base"] = ((fdr - fdr.mean()) / fdr.std()).shift(1)
    d["skew48"] = r.rolling(48).skew().shift(1)

    # --- Ch17 structural breaks ---
    d["adf_sup"] = adf_sup(logp).shift(1)
    d["cusum_csw"] = cusum_csw(logp).abs().shift(1)
    d["smt_exp"] = smt_exp(logp).shift(1)
    # --- Ch18 entropy (on FFD-return sign, De Prado's recommendation) ---
    d["ent_sign"] = plugin_entropy_sign(fdr.diff()).shift(1)
    # --- Ch19 microstructure ---
    dmid = df["mid"].diff()
    d["vpin"] = df["flow_ofi"].abs().rolling(24).mean().shift(1)
    d["amihud"] = (r.abs() / df["n_ticks"].clip(lower=1)).rolling(24).mean().shift(1)
    cov = dmid.rolling(48).cov(dmid.shift(1))
    d["roll_spread"] = np.sqrt((-cov).clip(lower=0)).shift(1)
    d["flow_ac"] = np.sign(df["flow_ofi"]).rolling(48).apply(
        lambda s: pd.Series(s).autocorr(lag=1) if pd.Series(s).std() else 0, raw=False).shift(1)
    d["kyle_t"] = roll_ols_t(dmid * 1e4, df["flow_ofi"], 48).shift(1)

    for h in HORIZONS:
        d[f"y{h}"] = (logp.shift(-h) - logp) * 1e4
    return d


def partial_ic(x, y, Z):
    """Partial Spearman: Pearson of rank-residuals after linear partialling on
    rank-controls Z (matrix of columns)."""
    def rank(v): return stats.rankdata(v)
    xr, yr = rank(x), rank(y)
    Zr = np.column_stack([np.ones(len(x))] + [rank(Z[:, j]) for j in range(Z.shape[1])])
    bx = np.linalg.lstsq(Zr, xr, rcond=None)[0]; rx = xr - Zr @ bx
    by = np.linalg.lstsq(Zr, yr, rcond=None)[0]; ry = yr - Zr @ by
    if rx.std() < 1e-9 or ry.std() < 1e-9:
        return np.nan, 1.0
    pic = np.corrcoef(rx, ry)[0, 1]
    # corr of candidate with controls (max abs simple Spearman)
    cc = max(abs(np.corrcoef(rank(x), rank(Z[:, j]))[0, 1]) for j in range(Z.shape[1]))
    return pic, cc


def main():
    pd.set_option("display.width", 220, "display.float_format", lambda x: f"{x:8.4f}")
    data = {os.path.basename(f).split("_")[0]: build(f) for f in BARS if os.path.basename(f).split("_")[0] in POOL}
    cands = [c for c in data[POOL[0]].columns
             if c not in ("base", "skew48") and not c.startswith("y")]

    rows = []
    cond_rows = []
    for f in cands:
        for h in HORIZONS:
            full, halves1, halves2, novs, ccs = [], [], [], [], []
            for s in POOL:
                dd = data[s][[f, "base", "skew48", f"y{h}"]].replace([np.inf, -np.inf], np.nan).dropna()
                if len(dd) < 800 or dd[f].nunique() < 5:
                    continue
                Z = dd[["base", "skew48"]].to_numpy()
                pic, cc = partial_ic(dd[f].to_numpy(), dd[f"y{h}"].to_numpy(), Z)
                full.append(pic); ccs.append(cc)
                half = len(dd) // 2
                halves1.append(partial_ic(dd[f].to_numpy()[:half], dd[f"y{h}"].to_numpy()[:half], Z[:half])[0])
                halves2.append(partial_ic(dd[f].to_numpy()[half:], dd[f"y{h}"].to_numpy()[half:], Z[half:])[0])
                no = dd.iloc[::h]
                if len(no) > 200:
                    novs.append(partial_ic(no[f].to_numpy(), no[f"y{h}"].to_numpy(),
                                           no[["base", "skew48"]].to_numpy())[0])
            if len(full) < 5:
                continue
            full = np.array(full); ic = full.mean()
            t = ic / (full.std(ddof=1) / np.sqrt(len(full)))
            sgn = int((np.sign(full) == np.sign(ic)).sum())
            half_ok = np.sign(np.nanmean(halves1)) == np.sign(np.nanmean(halves2)) == np.sign(ic)
            nov_ic = np.nanmean(novs) if novs else np.nan
            nov_ok = np.isfinite(nov_ic) and np.sign(nov_ic) == np.sign(ic)
            orth = np.mean(ccs) < 0.4
            robust = orth and sgn >= 4 and half_ok and nov_ok
            rows.append(dict(feature=f, h=h, partial_ic=ic, corr_ctrl=np.mean(ccs),
                             t=t, sign=f"{sgn}/5", nov_ic=nov_ic, robust=robust))

    res = pd.DataFrame(rows).reindex(
        pd.DataFrame(rows).partial_ic.abs().sort_values(ascending=False).index)
    print("=" * 116)
    print("DE PRADO Ch17/18/19 FEATURES — partial IC vs (reversion + skew), replication gate")
    print("=" * 116)
    print(res[["feature", "h", "partial_ic", "corr_ctrl", "t", "sign", "nov_ic", "robust"]].to_string(index=False))
    rob = res[res.robust]
    print(f"\nROBUST orthogonal-to-both survivors: {len(rob)}")
    if len(rob):
        print(rob[["feature", "h", "partial_ic", "corr_ctrl", "sign", "nov_ic"]].to_string(index=False))

    # --- De Prado conditioning test: does reversion strength depend on entropy / explosiveness? ---
    print("\n" + "=" * 116)
    print("CONDITIONING TEST — reversion IC (base vs y48) within terciles of a regime feature")
    print("  De Prado thesis: reversion stronger when entropy HIGH; momentum when entropy LOW/explosive")
    print("=" * 116)
    for regime in ["ent_sign", "adf_sup"]:
        print(f"\n  regime = {regime}")
        for lab, q in [("LOW", (0.0, 0.33)), ("MID", (0.33, 0.66)), ("HIGH", (0.66, 1.0))]:
            ics = []
            for s in POOL:
                dd = data[s][["base", regime, "y48"]].replace([np.inf, -np.inf], np.nan).dropna()
                lo, hi = dd[regime].quantile(q[0]), dd[regime].quantile(q[1])
                sub = dd[(dd[regime] >= lo) & (dd[regime] <= hi)]
                if len(sub) > 300:
                    ics.append(stats.spearmanr(sub["base"], sub["y48"])[0])
            print(f"    {lab:5s} {regime}: reversion IC = {np.mean(ics):+.4f}  (per-symbol {np.round(ics,3)})")


if __name__ == "__main__":
    main()
