"""Predictability test for the next-bar tercile label (drift-immune, balanced).

WFO (6mo train / 1mo test), EURUSD-style. For MRHydra / QUANT / RDST, plus
per-model 5-seed vote and a combined 15-member stack, score POOLED:

  * balanced 3-class accuracy        (chance = 0.333)
  * directional precision (+1 / -1)  (of the calls, how many right sign)
  * dir-accuracy on non-flat calls   (chance = 0.50)
  * mean signed next-bar return:  pred * fwd_mid_bps  (gross), minus cost (net)
    with moving-block bootstrap 95% CI + t-stat, and positive-month %

Drift crutch is removed by the label, so anything above chance is real
1-bar-ahead directional information.

Usage:
    uv run python scripts/fx_coint/hourly_nextbar_eval.py --year 2024 --window 500 --seeds 5
"""
# ruff: noqa: E402

from __future__ import annotations

import argparse
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import balanced_accuracy_score, precision_score

warnings.filterwarnings("ignore")

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.fx_coint.hourly_multirocket_wfo import (
    DEFAULT_COST_BPS,
    build_feature_panel,
    classify_regime,
    load_hourly,
)
from scripts.fx_coint.hourly_nextbar_label import label_next_bar_tercile
from scripts.fx_coint.hourly_pooled_decomp import (
    EXCLUDE,
    LOOKBACK,
    SEEDS,
    TEST_MO,
    TRAIN_MO,
    fit_members,
    majority_vote,
    moving_block_bootstrap_ci,
)

MODELS = ["MRHydra", "QUANT", "RDST"]


def run(symbol: str, year: int, window: int, n_seeds: int):
    cost = DEFAULT_COST_BPS[symbol]
    df = load_hourly(symbol)
    start, end = pd.Timestamp(f"{year}-01-01"), pd.Timestamp(f"{year+1}-01-01")
    df = df[(df["bucket"] >= start) & (df["bucket"] < end)].reset_index(drop=True)
    months = pd.date_range(start, end, freq="MS")
    n_windows = len(months) - TRAIN_MO - TEST_MO
    seeds = SEEDS[:n_seeds]

    pools: dict[str, list[pd.DataFrame]] = {}

    for i in range(n_windows):
        tr_s, tr_e = months[i], months[i + TRAIN_MO]
        te_s = months[i + TRAIN_MO]
        te_e = months[i + TRAIN_MO + TEST_MO] if (i + TRAIN_MO + TEST_MO) < len(months) else end
        margin = tr_s - pd.Timedelta(hours=max(LOOKBACK * 2, window + 50))
        wdf = df[(df["bucket"] >= margin) & (df["bucket"] < te_e)].reset_index(drop=True)
        wdf = label_next_bar_tercile(wdf, window=window)

        ts = wdf["bucket"].iloc[LOOKBACK:].reset_index(drop=True)
        valid = wdf["_label_valid"].to_numpy()[LOOKBACK:]
        tr_idx = np.where(((ts >= tr_s) & (ts < tr_e)).to_numpy() & valid)[0]
        te_idx = np.where(((ts >= te_s) & (ts < te_e)).to_numpy() & valid)[0]
        if len(tr_idx) < 500 or len(te_idx) < 100:
            continue
        wdf["regime"] = classify_regime(wdf["rvol_bps"], tr_idx)
        X, y, _ = build_feature_panel(wdf, LOOKBACK, exclude_channels=EXCLUDE)
        X = X.astype(np.float64)
        X_tr, y_tr, X_te = X[tr_idx], y[tr_idx], X[te_idx]
        if np.unique(y_tr).size < 2:
            continue

        base = wdf.iloc[LOOKBACK:].reset_index(drop=True)
        fwd = base["fwd_ret_bps"].to_numpy()[te_idx]
        bucket = base["bucket"].to_numpy()[te_idx]
        y_true = y[te_idx]

        print(f"  [W{i+1}] {te_s:%Y-%m}  n_tr={len(tr_idx)} n_te={len(te_idx)}", flush=True)
        all_votes = []
        for m in MODELS:
            votes = fit_members(m, X_tr, y_tr, X_te, seeds)
            all_votes.append(votes)
            _store(pools, f"{m}[1seed]", votes[0], fwd, bucket, y_true)
            if len(seeds) > 1:
                _store(pools, f"{m}[{len(seeds)}seed]", majority_vote(votes), fwd, bucket, y_true)
        if len(MODELS) > 1:
            comb = np.vstack(all_votes)
            _store(pools, f"STACK[{comb.shape[0]}]", majority_vote(comb), fwd, bucket, y_true)

    return {k: pd.concat(v, ignore_index=True) for k, v in pools.items()}, cost


def _store(pools, key, preds, fwd, bucket, y_true):
    pools.setdefault(key, []).append(pd.DataFrame({
        "pred": preds, "fwd_bps": fwd, "bucket": bucket, "y_true": y_true,
    }))


def summarize(d: pd.DataFrame, cost: float, label: str):
    pred = d["pred"].to_numpy()
    fwd = d["fwd_bps"].to_numpy()
    y = d["y_true"].to_numpy()
    bal_acc = balanced_accuracy_score(y, pred)
    prec1 = precision_score(y, pred, labels=[1], average="micro", zero_division=0)
    precm1 = precision_score(y, pred, labels=[-1], average="micro", zero_division=0)

    active = pred != 0
    n_act = int(active.sum())
    dir_acc = (np.sign(pred[active]) == np.sign(fwd[active])).mean() if n_act else np.nan
    signed_gross = pred[active] * fwd[active]
    signed_net = signed_gross - cost
    g = signed_gross.mean() if n_act else np.nan
    nt = signed_net.mean() if n_act else np.nan
    t = np.sqrt(n_act) * nt / (signed_net.std() + 1e-12) if n_act else np.nan
    lo, hi = moving_block_bootstrap_ci(signed_net, block=4) if n_act else (np.nan, np.nan)

    dd = d[active].assign(month=pd.to_datetime(d[active]["bucket"]).dt.to_period("M"))
    by_m = dd.groupby("month").apply(lambda x: (x["pred"] * x["fwd_bps"] - cost).mean())
    pos_mo = (by_m > 0).mean() * 100 if len(by_m) else np.nan

    verdict = "EDGE" if lo > 0 else ("NEG" if hi < 0 else "noise")
    print(f"  {label:<16s} balAcc={bal_acc:.3f} dirAcc={dir_acc:.3f} "
          f"prec+={prec1:.3f} prec-={precm1:.3f} | act={n_act:>5d} "
          f"gross={g:+.3f} net={nt:+.3f} t={t:+5.2f} "
          f"CI=[{lo:+.3f},{hi:+.3f}] posMo={pos_mo:3.0f}% -> {verdict}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbol", default="EURUSD")
    ap.add_argument("--year", type=int, default=2024)
    ap.add_argument("--window", type=int, default=500)
    ap.add_argument("--seeds", type=int, default=5)
    args = ap.parse_args()

    print(f"=== next-bar predictability  {args.symbol} {args.year}  W={args.window} "
          f"seeds={args.seeds} ===")
    print("chance: balAcc=0.333  dirAcc=0.500")
    pools, cost = run(args.symbol, args.year, args.window, args.seeds)
    print(f"\n{'='*112}\nPOOLED  (signed next-bar return, bps/call; cost={cost} bps; "
          f"block-bootstrap CI)\n{'='*112}")
    for k in sorted(pools):
        summarize(pools[k], cost, k)


if __name__ == "__main__":
    main()
