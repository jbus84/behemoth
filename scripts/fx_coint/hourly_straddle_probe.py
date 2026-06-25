"""Can the magnitude skill be monetised non-directionally (straddle)?

Direction is ~chance, but balAcc>chance suggests the models flag big-move bars.
For each model (seed 42, WFO) measure, POOLED over test bars:

  * E[fwd] and E[|fwd|] by predicted class (-1/0/+1)   -> is there magnitude skill?
  * magnitude lift = E[|fwd| | pred!=0] - E[|fwd| | pred==0]
  * straddle net on flagged (pred!=0) bars:
        net = |fwd_bps| - fair_premium - spread
    fair_premium = trailing causal mean |move| (what a vol seller charges).
    NOTE: charging only the spread (an earlier version) is WRONG — it ignores
    the option premium and manufactures a fake ~+6bps edge equal to the average
    hourly move. A straddle is only profitable if realized |move| beats the fair
    premium (the variance risk premium), which in hourly EURUSD is ~0 and
    negative for the buyer after spread. Keep fair_premium in the cost.

Usage:
    uv run python scripts/fx_coint/hourly_straddle_probe.py --year 2024 --window 500
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
    make_model,
    moving_block_bootstrap_ci,
)

MODELS = ["MRHydra", "QUANT", "RDST"]


def _confidence(m: str, models, X_tr, y_tr, X_te, seeds):
    """P(big move) per test bar. QUANT -> mean predict_proba; ridge models -> seed
    agreement (fraction of seeds predicting non-neutral). Returns (conf, pred_sign)."""
    move_p = np.zeros(len(X_te))
    sign_votes = np.zeros(len(X_te))
    for seed in seeds:
        clf = make_model(m, seed)
        clf.fit(X_tr, y_tr)
        if m == "QUANT":
            proba = clf.predict_proba(X_te)
            classes = list(clf.classes_)
            zi = classes.index(0) if 0 in classes else None
            move_p += (1 - proba[:, zi]) if zi is not None else 1.0
        p = clf.predict(X_te).astype(np.int8)
        move_p += (p != 0).astype(float) if m != "QUANT" else 0.0
        sign_votes += p
    n = len(seeds)
    conf = move_p / n
    return conf, np.sign(sign_votes)


def run(symbol: str, year: int, window: int, n_seeds: int):
    cost = DEFAULT_COST_BPS[symbol]
    df = load_hourly(symbol)
    start, end = pd.Timestamp(f"{year}-01-01"), pd.Timestamp(f"{year+1}-01-01")
    df = df[(df["bucket"] >= start) & (df["bucket"] < end)].reset_index(drop=True)
    months = pd.date_range(start, end, freq="MS")
    n_windows = len(months) - TRAIN_MO - TEST_MO
    seeds = SEEDS[:n_seeds]
    pools = {m: [] for m in MODELS}

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
        print(f"  [W{i+1}] {te_s:%Y-%m} n_te={len(te_idx)}", flush=True)
        for m in MODELS:
            conf, sgn = _confidence(m, MODELS, X_tr, y_tr, X_te, seeds)
            pools[m].append(pd.DataFrame({"conf": conf, "sign": sgn, "fwd": fwd, "bucket": bucket}))

    return {m: pd.concat(v, ignore_index=True) for m, v in pools.items()}, cost


def report(pools, cost):
    print(f"\n{'='*100}\nTHRESHOLDED MAGNITUDE / STRADDLE PROBE   (cost={cost} bps/leg)\n{'='*100}")
    for m, d in pools.items():
        conf = d["conf"].to_numpy()
        fwd = d["fwd"].to_numpy()
        af = np.abs(fwd)
        print(f"\n{m}:  E[|fwd|] by confidence decile (does magnitude rise with conf?)")
        # decile buckets of confidence
        try:
            q = pd.qcut(conf, 10, labels=False, duplicates="drop")
        except ValueError:
            q = pd.qcut(conf.argsort().argsort(), 10, labels=False)
        print(f"   {'decile':>6s} {'conf':>6s} {'n':>5s} {'E|fwd|':>7s} {'E[fwd]':>7s} "
              f"{'strad k=2 net':>13s}")
        for dq in sorted(pd.unique(q)):
            sel = q == dq
            net2 = af[sel].mean() - 2 * cost
            print(f"   {int(dq):>6d} {conf[sel].mean():>6.2f} {sel.sum():>5d} "
                  f"{af[sel].mean():>7.3f} {fwd[sel].mean():>+7.3f} {net2:>+13.3f}")

        # top-confidence slice straddle test
        thr = np.quantile(conf, 0.7)
        top = conf >= thr
        print(f"   --- top-30% confidence (conf>={thr:.2f}, n={top.sum()}):")
        for k in (1, 2):
            net = af[top] - k * cost
            lo, hi = moving_block_bootstrap_ci(net, block=4)
            t = np.sqrt(len(net)) * net.mean() / (net.std() + 1e-12)
            dd = d[top].assign(month=pd.to_datetime(d[top]["bucket"]).dt.to_period("M"))
            by_m = dd.groupby("month").apply(lambda x: (np.abs(x["fwd"]) - k * cost).mean())
            pos_mo = (by_m > 0).mean() * 100 if len(by_m) else np.nan
            verdict = "EDGE" if lo > 0 else ("NEG" if hi < 0 else "noise")
            print(f"       straddle k={k}: net={net.mean():+6.3f} t={t:+5.2f} "
                  f"CI=[{lo:+.3f},{hi:+.3f}] posMo={pos_mo:3.0f}% -> {verdict}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbol", default="EURUSD")
    ap.add_argument("--year", type=int, default=2024)
    ap.add_argument("--window", type=int, default=500)
    ap.add_argument("--seeds", type=int, default=5)
    args = ap.parse_args()
    print(f"=== thresholded straddle probe  {args.symbol} {args.year}  W={args.window} "
          f"seeds={args.seeds} ===")
    pools, cost = run(args.symbol, args.year, args.window, args.seeds)
    report(pools, cost)


if __name__ == "__main__":
    main()
