"""Scaled needle hunt: pooled OOS IC across 6 pairs x 8 years (max breadth).

A minute IC is only settled by power. This pools every (pair, year, WFO fold)
OOS ridge IC of flow/price signals vs the vol-normalised h-bar forward return.

Per (horizon, arm) it reports:
  * breadth t  = mean fold IC / SE over ALL (pair,year,fold) slices  [HONEST stat —
    accounts for cross-slice variance; this is the gate]
  * slice sign-stability = fraction of (pair,year) slices whose mean IC matches the
    pooled sign  [a real needle holds its sign across pairs AND years]
  * pooled giant-N IC + t  [optimistic; ignores overlap/cross-pair correlation]
  * implied IR = mean fold IC * sqrt(mean breadth)
Flow "works" only if a flow arm's IC is (a) sign-stable, (b) breadth-t significant
after BH, AND (c) beats price_only. Otherwise any IC is a price effect, not flow.

Usage:
    uv run python scripts/fx_coint/hourly_ic_scaled.py --horizons 1,3,6
"""
# ruff: noqa: E402
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
from scripts.fx_coint.hourly_multirocket_wfo import load_hourly
from scripts.fx_coint.hourly_nextbar_label import label_horizon_tercile
from scripts.fx_coint.multiplicity import bh_reject, p_from_t

PAIRS = ["EURUSD", "GBPUSD", "AUDUSD", "USDJPY", "USDCHF", "USDCAD"]
YEARS = [2018, 2019, 2020, 2021, 2022, 2023, 2024, 2025]
TRAIN_MO, TEST_MO, WINDOW, VOL_WIN = 6, 1, 500, 24


def _vol_norm_target(df: pd.DataFrame) -> np.ndarray:
    r = np.log(df["mid"]).diff() * 1e4
    vol = r.rolling(VOL_WIN, min_periods=VOL_WIN).std().shift(1).to_numpy()
    return df["fwd_ret_bps"].to_numpy() / (vol + 1e-9)


def slice_folds(full: pd.DataFrame, year: int, horizon: int, channels: list[str]):
    """Yield per-fold (oos_ic, pred, target) for one pair-year."""
    start, end = pd.Timestamp(f"{year}-01-01"), pd.Timestamp(f"{year+1}-01-01")
    df = full[(full["bucket"] >= start - pd.Timedelta(hours=WINDOW + VOL_WIN + 50))
              & (full["bucket"] < end)].reset_index(drop=True)
    if len(df) < 3000:
        return
    months = pd.date_range(start, end, freq="MS")
    n_windows = len(months) - TRAIN_MO - TEST_MO
    df = label_horizon_tercile(df, horizon=horizon, window=WINDOW)
    df = add_channels(df)
    y = _vol_norm_target(df)
    X = df[channels].to_numpy(dtype=np.float64)
    ts = df["bucket"]
    valid = df["_label_valid"].to_numpy() & np.isfinite(y) & np.isfinite(X).all(1)
    for i in range(n_windows):
        tr_s, tr_e = months[i], months[i + TRAIN_MO]
        te_s = months[i + TRAIN_MO]
        te_e = months[i + TRAIN_MO + TEST_MO] if (i + TRAIN_MO + TEST_MO) < len(months) else end
        tr = np.where(((ts >= tr_s) & (ts < tr_e)).to_numpy() & valid)[0]
        te = np.where(((ts >= te_s) & (ts < te_e)).to_numpy() & valid)[0]
        if len(tr) < 500 or len(te) < 100:
            continue
        ic, _r2, pred = ridge_oos(X[tr], y[tr], X[te], y[te])
        yield ic, pred, y[te]


def run_cell(horizon: int, arm: str, dfs: dict) -> dict:
    channels = ARMS[arm]
    fold_ics, pooled_pred, pooled_y = [], [], []
    slice_ics = []  # mean OOS IC per (pair,year)
    for pair in PAIRS:
        for year in YEARS:
            s_ics = []
            for ic, pred, yt in slice_folds(dfs[pair], year, horizon, channels):
                fold_ics.append(ic)
                s_ics.append(ic)
                pooled_pred.append(pred)
                pooled_y.append(yt)
            if s_ics:
                slice_ics.append(float(np.nanmean(s_ics)))
    fold_ics = np.array([f for f in fold_ics if np.isfinite(f)])
    slice_ics = np.array(slice_ics)
    if len(fold_ics) < 5:
        return {"horizon": horizon, "arm": arm, "n_folds": len(fold_ics)}
    mean_ic = float(fold_ics.mean())
    se = float(fold_ics.std(ddof=1) / np.sqrt(len(fold_ics)))
    breadth_t = mean_ic / (se + 1e-12)
    pooled_ic, pooled_tt, pooled_n = spearman_ic(np.concatenate(pooled_pred),
                                                 np.concatenate(pooled_y))
    sign = np.sign(mean_ic)
    sign_stab = float(np.mean(np.sign(slice_ics) == sign))
    mean_breadth = float(np.mean([len(p) for p in pooled_pred]))
    return {
        "horizon": horizon, "arm": arm, "n_folds": len(fold_ics),
        "n_slices": len(slice_ics), "mean_ic": mean_ic, "breadth_t": breadth_t,
        "p": p_from_t(breadth_t, len(fold_ics)), "pooled_ic": pooled_ic,
        "pooled_n": pooled_n, "sign_stab": sign_stab,
        "implied_ir": mean_ic * np.sqrt(mean_breadth),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--horizons", default="1,3,6")
    ap.add_argument("--arms", default="price_only,raw_flow,engineered,both")
    args = ap.parse_args()
    horizons = [int(h) for h in args.horizons.split(",")]
    arms = args.arms.split(",")
    print(f"=== SCALED IC needle hunt  {len(PAIRS)} pairs x {len(YEARS)} years ===")
    print("loading pairs...", flush=True)
    dfs = {p: load_hourly(p) for p in PAIRS}

    rows = []
    for h in horizons:
        for arm in arms:
            r = run_cell(h, arm, dfs)
            rows.append(r)
            if r.get("n_folds", 0) >= 5:
                print(f"  h={h} {arm:<11s} meanIC={r['mean_ic']:+.4f} breadth_t={r['breadth_t']:+6.2f} "
                      f"signStab={r['sign_stab']:.2f} pooledIC={r['pooled_ic']:+.4f} "
                      f"(N={r['pooled_n']}) IR~{r['implied_ir']:+.2f} folds={r['n_folds']}",
                      flush=True)

    valid = [r for r in rows if r.get("n_folds", 0) >= 5]
    bh = bh_reject([r["p"] for r in valid], 0.05)
    # price_only IC per horizon, to test "flow beats price"
    price_ic = {r["horizon"]: r["mean_ic"] for r in valid if r["arm"] == "price_only"}
    print(f"\n{'='*100}\nVERDICT (needle = sign-stable + breadth-t survives BH + beats price_only):")
    found = False
    for r, sig in zip(valid, bh):
        beats_price = (r["arm"] != "price_only" and
                       abs(r["mean_ic"]) > abs(price_ic.get(r["horizon"], 0)) and
                       np.sign(r["mean_ic"]) == np.sign(price_ic.get(r["horizon"], r["mean_ic"])))
        stable = r["sign_stab"] >= 0.7
        flow_needle = sig and stable and beats_price
        price_needle = sig and stable and r["arm"] == "price_only"
        found = found or flow_needle
        tag = "FLOW-NEEDLE" if flow_needle else ("price-effect" if price_needle else "noise")
        print(f"  h={r['horizon']} {r['arm']:<11s} meanIC={r['mean_ic']:+.4f} "
              f"breadth_t={r['breadth_t']:+6.2f} BH={str(sig):>5s} signStab={r['sign_stab']:.2f} "
              f"beatsPrice={str(beats_price) if r['arm']!='price_only' else '-':>5s} -> {tag}")
    print(f"\n{'FLOW NEEDLE FOUND' if found else 'NO FLOW NEEDLE'} "
          f"(price-effect rows show any standalone price IC that scales)")


if __name__ == "__main__":
    main()
