"""Needle detector: pooled OOS IC of flow signals vs forward return.

Higher-powered than the dirAcc grid. For each (horizon, arm):
  * signal = closed-form RIDGE on CURRENT-BAR features (low variance; won't
    manufacture a fake needle the way overfit TS models can).
  * target = VOL-NORMALISED h-bar forward return (equalises SNR per bar).
  * per-WFO-fold OOS IC; report pooled IC + t, mean fold IC, and SIGN-STABILITY
    (fraction of folds whose IC matches the pooled sign) — the anti-overfit gate.
  * CONDITIONAL IC on the high-|OFI| subset (flow informs only when flow exists).
  * implied IR = mean_fold_IC * sqrt(mean breadth) and the cost-implied IC hurdle.
  * BH across the grid so the best cell isn't just the luckiest trial.

A found needle = sign-stable IC across folds (continuation IC>0 or, per impact-
reversion, IC<0), surviving BH. Exploitability is a separate IR-vs-cost readout.

Usage:
    uv run python scripts/fx_coint/hourly_ic_detector.py --year 2024
"""
# ruff: noqa: E402  (imports follow sys.path bootstrap, by design)
from __future__ import annotations

import argparse
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.fx_coint.flow_metrics import ridge_oos, spearman_ic
from scripts.fx_coint.hourly_flow_features import ARMS, add_channels
from scripts.fx_coint.hourly_multirocket_wfo import DEFAULT_COST_BPS, load_hourly
from scripts.fx_coint.hourly_nextbar_label import label_horizon_tercile
from scripts.fx_coint.multiplicity import bh_reject, p_from_t

TRAIN_MO = 6
TEST_MO = 1
WINDOW = 500
VOL_WIN = 24  # trailing bars for realised-vol normalisation


def _vol_norm_target(df: pd.DataFrame) -> np.ndarray:
    """fwd_ret_bps / trailing realised vol (causal)."""
    r = np.log(df["mid"]).diff() * 1e4
    vol = r.rolling(VOL_WIN, min_periods=VOL_WIN).std().shift(1).to_numpy()
    return df["fwd_ret_bps"].to_numpy() / (vol + 1e-9)


def run_cell(symbol: str, year: int, horizon: int, arm: str) -> dict:
    df = load_hourly(symbol)
    start, end = pd.Timestamp(f"{year}-01-01"), pd.Timestamp(f"{year+1}-01-01")
    df = df[(df["bucket"] >= start) & (df["bucket"] < end)].reset_index(drop=True)
    months = pd.date_range(start, end, freq="MS")
    n_windows = len(months) - TRAIN_MO - TEST_MO
    channels = ARMS[arm]

    fold_ics: list[float] = []
    fold_ns: list[int] = []
    pooled_pred, pooled_y, pooled_ofi = [], [], []

    for i in range(n_windows):
        tr_s, tr_e = months[i], months[i + TRAIN_MO]
        te_s = months[i + TRAIN_MO]
        te_e = months[i + TRAIN_MO + TEST_MO] if (i + TRAIN_MO + TEST_MO) < len(months) else end
        margin = tr_s - pd.Timedelta(hours=WINDOW + VOL_WIN + 50)
        wdf = df[(df["bucket"] >= margin) & (df["bucket"] < te_e)].reset_index(drop=True)
        wdf = label_horizon_tercile(wdf, horizon=horizon, window=WINDOW)
        wdf = add_channels(wdf)
        y = _vol_norm_target(wdf)
        X = wdf[channels].to_numpy(dtype=np.float64)         # CURRENT-BAR features
        ofi = wdf["flow_ofi"].to_numpy()
        ts = wdf["bucket"]
        valid = wdf["_label_valid"].to_numpy() & np.isfinite(y) & np.isfinite(X).all(1)
        tr = np.where(((ts >= tr_s) & (ts < tr_e)).to_numpy() & valid)[0]
        te = np.where(((ts >= te_s) & (ts < te_e)).to_numpy() & valid)[0]
        if len(tr) < 500 or len(te) < 100:
            continue
        oos_ic, _r2, pred = ridge_oos(X[tr], y[tr], X[te], y[te])
        fold_ics.append(oos_ic)
        fold_ns.append(len(te))
        pooled_pred.append(pred)
        pooled_y.append(y[te])
        pooled_ofi.append(np.abs(ofi[te]))

    if not fold_ics:
        return {"horizon": horizon, "arm": arm, "n_folds": 0}

    pred = np.concatenate(pooled_pred)
    yt = np.concatenate(pooled_y)
    aofi = np.concatenate(pooled_ofi)
    ic, t, n = spearman_ic(pred, yt)
    mean_fold = float(np.nanmean(fold_ics))
    pooled_sign = np.sign(ic)
    sign_stab = float(np.mean([np.sign(f) == pooled_sign for f in fold_ics if np.isfinite(f)]))
    # conditional IC on top-tercile |OFI|
    hi = aofi >= np.quantile(aofi, 2 / 3)
    ic_hi, t_hi, n_hi = spearman_ic(pred[hi], yt[hi])
    breadth = float(np.mean(fold_ns))
    implied_ir = mean_fold * np.sqrt(breadth)
    return {
        "horizon": horizon, "arm": arm, "n_folds": len(fold_ics), "n": n,
        "ic": ic, "t": t, "p": p_from_t(t, n), "mean_fold_ic": mean_fold,
        "sign_stab": sign_stab, "ic_hi_ofi": ic_hi, "t_hi": t_hi,
        "implied_ir": implied_ir,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbol", default="EURUSD")
    ap.add_argument("--year", type=int, default=2024)
    args = ap.parse_args()
    print(f"=== IC needle detector  {args.symbol} {args.year}  (ridge on current-bar "
          f"features, vol-normalised target) ===")
    print(f"cost={DEFAULT_COST_BPS[args.symbol]} bps   gate: sign-stable IC surviving BH")
    horizons = [1, 3, 6]
    arms = ["price_only", "raw_flow", "engineered", "both"]
    rows = []
    for h in horizons:
        for arm in arms:
            r = run_cell(args.symbol, args.year, h, arm)
            rows.append(r)
            if r.get("n_folds"):
                print(f"  h={h} {arm:<11s} IC={r['ic']:+.4f} t={r['t']:+5.2f} "
                      f"meanFold={r['mean_fold_ic']:+.4f} signStab={r['sign_stab']:.2f} "
                      f"IC|hiOFI={r['ic_hi_ofi']:+.4f} IR~{r['implied_ir']:+.2f} n={r['n']}",
                      flush=True)

    valid = [r for r in rows if r.get("n_folds")]
    bh = bh_reject([r["p"] for r in valid], 0.05)
    print(f"\n{'='*92}\nVERDICT (needle = sign-stable IC surviving BH; sign-stab>=0.8):")
    found = False
    for r, sig in zip(valid, bh):
        needle = sig and r["sign_stab"] >= 0.8
        found = found or needle
        print(f"  h={r['horizon']} {r['arm']:<11s} IC={r['ic']:+.4f} p={r['p']:.4f} "
              f"BH={str(sig):>5s} signStab={r['sign_stab']:.2f} -> {'NEEDLE' if needle else 'noise'}")
    print(f"\n{'NEEDLE(S) FOUND' if found else 'NO NEEDLE — flow IC not sign-stable/significant'}")


if __name__ == "__main__":
    main()
