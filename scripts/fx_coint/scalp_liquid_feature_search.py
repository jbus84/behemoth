"""Temporal feature search for the London+Overlap liquid sessions @ 15m H1.

The session probe showed the confident-classifier tail gross concentrates in liquid hours
(London 07-13, Overlap 13-16 UTC) but hit ceilings ~54% (< ~56% breakeven). Hypothesis:
richer TEMPORAL features (multi-lookback momentum, session-relative time, range position,
persistence) carry directional signal the microstructure cocktail misses.

Method (the needle-hunt discipline): build ~20 causal temporal candidates; for each compute
pooled OUT-OF-SAMPLE Spearman IC vs the vol-normalized 15m forward return, RESTRICTED to
liquid hours; per-pair sign-stability; BH-FDR across candidates. Then fit a ridge on the
surviving features and measure the liquid-tail hit/net vs the cocktail baseline.

Usage:
    uv run python scripts/fx_coint/scalp_liquid_feature_search.py --year 2024
"""

from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path

_ROOT = _Path(__file__).resolve().parents[2]
if str(_ROOT) not in _sys.path:
    _sys.path.insert(0, str(_ROOT))

import argparse  # noqa: E402

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from scipy.stats import spearmanr  # noqa: E402
from sklearn.linear_model import Ridge  # noqa: E402
from sklearn.preprocessing import StandardScaler  # noqa: E402

from scripts.fx_coint.phase0_scalp_common import (  # noqa: E402
    add_rolling_features,
    compute_forward_returns,
    load_raw_ticks,
)
from scripts.fx_coint.scalp_tf_probe import build_enriched  # noqa: E402

TIGHT = ["EURUSD", "GBPUSD", "USDJPY"]
LIQUID = (7, 16)  # London + Overlap UTC


def temporal_features(df: pd.DataFrame) -> pd.DataFrame:
    """Causal temporal candidate features on 15m bars (all use only past info)."""
    f = pd.DataFrame(index=df.index)
    mid = df["mid"].astype(float)
    r = np.log(mid / mid.shift(1)) * 1e4  # 15m bar return, bps
    rv = r.rolling(48, min_periods=20).std().shift(1)  # trailing vol (~12h)

    # multi-lookback momentum, vol-normalised
    for k in (1, 2, 3, 4, 6, 8, 12, 16, 24):
        f[f"mom_{k}"] = (r.rolling(k, min_periods=max(1, k // 2)).sum() / (rv * np.sqrt(k))).shift(1)
    f["accel"] = f["mom_2"] - f["mom_8"]
    f["mom_l_minus_s"] = f["mom_16"] - f["mom_4"]

    # session-relative time
    hr = df["bucket"].dt.hour + df["bucket"].dt.minute / 60.0
    f["min_since_london"] = (hr - 7.0).clip(lower=0)
    f["tod_sin"] = np.sin(2 * np.pi * hr / 24)
    f["tod_cos"] = np.cos(2 * np.pi * hr / 24)

    # range position over last 24 bars
    hi = df["high_bid"].rolling(24, min_periods=8).max().shift(1)
    lo = df["low_bid"].rolling(24, min_periods=8).min().shift(1)
    f["range_pos"] = ((mid - lo) / (hi - lo) - 0.5).shift(1)

    # distance from EMA, vol-normalised
    ema = mid.ewm(span=20, min_periods=10).mean().shift(1)
    f["dist_ema"] = ((mid.shift(1) - ema) / (rv * mid / 1e4))

    # vol regime ratio
    f["rvol_ratio"] = (r.rolling(8, min_periods=4).std() / r.rolling(48, min_periods=20).std()).shift(1)

    # persistence / run-length
    sgn = np.sign(r)
    f["persist_8"] = sgn.rolling(8, min_periods=4).sum().shift(1)
    f["prior_day_ret"] = (r.rolling(96, min_periods=40).sum() / (rv * np.sqrt(96))).shift(1)

    # microstructure (already causal-ish; shift to be safe)
    f["flow_tick"] = df["flow_tick"].shift(1)
    f["flow_ofi"] = df["flow_ofi"].shift(1)
    f["quote_rev_z"] = df["quote_revision_rate_z"]

    f["_target_z"] = (np.log(mid.shift(-1) / mid) * 1e4) / rv  # vol-norm 15m fwd return
    f["_hour"] = df["bucket"].dt.hour.to_numpy()
    return f


CAND = ["mom_1", "mom_2", "mom_3", "mom_4", "mom_6", "mom_8", "mom_12", "mom_16", "mom_24",
        "accel", "mom_l_minus_s", "min_since_london", "tod_sin", "tod_cos", "range_pos",
        "dist_ema", "rvol_ratio", "persist_8", "prior_day_ret", "flow_tick", "flow_ofi", "quote_rev_z"]


def bh_reject(pvals, alpha=0.1):
    p = np.asarray(pvals)
    m = len(p)
    order = np.argsort(p)
    ok = p[order] <= alpha * np.arange(1, m + 1) / m
    rej = np.zeros(m, bool)
    if ok.any():
        rej[order[: np.where(ok)[0].max() + 1]] = True
    return rej


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--year", type=int, default=2024)
    ap.add_argument("--freq", default="15m")
    args = ap.parse_args()

    feats = {}
    for sym in TIGHT:
        df = add_rolling_features(build_enriched(load_raw_ticks(sym, args.year), sym, args.freq), sym)
        df = compute_forward_returns(df, [1])
        f = temporal_features(df)
        liq = (f["_hour"] >= LIQUID[0]) & (f["_hour"] < LIQUID[1])
        feats[sym] = f[liq].reset_index(drop=True)

    # ---- (1) per-candidate pooled OOS IC (holdout 40%) + per-pair sign stability ----
    print(f"TEMPORAL FEATURE SEARCH — London+Overlap {LIQUID} UTC, {args.freq} H1, {args.year}")
    print("  pooled OOS Spearman IC vs vol-norm 15m fwd return; sign = +pairs/-pairs\n")
    rows = []
    for c in CAND:
        pooled_s, pooled_y, signs = [], [], []
        for f in feats.values():
            s = int(len(f) * 0.6)
            xx = f[c].to_numpy()[s:]
            yy = f["_target_z"].to_numpy()[s:]
            m = np.isfinite(xx) & np.isfinite(yy)
            if m.sum() < 50:
                continue
            ic_p = spearmanr(xx[m], yy[m]).statistic
            signs.append(np.sign(ic_p))
            pooled_s.append(xx[m])
            pooled_y.append(yy[m])
        if not pooled_s:
            continue
        xs, ys = np.concatenate(pooled_s), np.concatenate(pooled_y)
        ic = spearmanr(xs, ys).statistic
        t = ic * np.sqrt(len(xs) - 2) / np.sqrt(max(1e-12, 1 - ic**2))
        p = 2 * _norm_sf(abs(t))  # two-sided normal approx
        rows.append({"feat": c, "ic": ic, "t": t, "p": p, "nstab": int(sum(signs)), "npairs": len(signs)})
    rdf = pd.DataFrame(rows)
    rdf["bh"] = bh_reject(rdf["p"].to_numpy(), 0.1)
    rdf = rdf.reindex(rdf["ic"].abs().sort_values(ascending=False).index)
    print(f"  {'feature':>16} {'IC':>8} {'t':>7} {'p':>7} {'signStab':>9} {'BH':>3}")
    for _, r in rdf.iterrows():
        stab = f"{r['nstab']:+d}/{r['npairs']}"
        print(f"  {r['feat']:>16} {r['ic']:>+8.4f} {r['t']:>+7.2f} {r['p']:>7.4f} {stab:>9} "
              f"{'*' if r['bh'] else '':>3}")

    # ---- (2) ridge on BH-survivors -> liquid-tail hit/net vs cocktail ----
    surv = [r["feat"] for _, r in rdf.iterrows() if r["bh"] and r["nstab"] in (3, -3)]
    print(f"\n  BH-significant + sign-stable (3/3) features: {surv or 'NONE'}")
    if surv:
        _eval_ridge(feats, surv)


def _norm_sf(z: float) -> float:
    # survival function of standard normal via erfc
    from math import erfc, sqrt
    return 0.5 * erfc(z / sqrt(2))


def _eval_ridge(feats: dict, cols: list[str]) -> None:
    print("\n  Ridge on surviving temporal features -> liquid-tail (P90/95) net of cost:")
    pooled = {0.90: [], 0.95: []}
    for f in feats.values():
        n = len(f)
        s = int(n * 0.6)
        X = np.nan_to_num(f[cols].to_numpy(float), nan=0.0)
        y = f["_target_z"].to_numpy(float)
        fwd_bps = f["_target_z"].to_numpy(float)  # vol-norm; convert back not needed for hit
        ytr = y[:s]
        m = np.isfinite(ytr)
        sc = StandardScaler().fit(X[:s][m])
        pred = Ridge(alpha=1.0).fit(sc.transform(X[:s][m]), ytr[m]).predict(sc.transform(X[s:]))
        ftest = fwd_bps[s:]
        v = np.isfinite(pred) & np.isfinite(ftest)
        pred, ftest = pred[v], ftest[v]
        for q in (0.90, 0.95):
            sel = np.abs(pred) >= np.quantile(np.abs(pred), q)
            hit = (np.sign(pred[sel]) * ftest[sel] > 0)
            pooled[q].append(hit)
    for q in (0.90, 0.95):
        allhit = np.concatenate(pooled[q])
        print(f"    P{int(q*100)}: liquid-tail directional hit = {allhit.mean()*100:.1f}%  "
              f"(breakeven ~{56 if q==0.90 else 54}%, n={len(allhit)})")


if __name__ == "__main__":
    main()
