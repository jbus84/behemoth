"""Phase 1: does flow give the aeon models hourly directional skill?

Grid {1,3,6h} x {price_only,+raw_flow,+engineered,+both}, pooled WFO with
block-bootstrap CI + Sidak/BH. price_only is the ~0.50 control.
"""
from __future__ import annotations

import argparse
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import balanced_accuracy_score

warnings.filterwarnings("ignore")
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.fx_coint.hourly_multirocket_wfo import (
    DEFAULT_COST_BPS, classify_regime, load_hourly,
)
from scripts.fx_coint.hourly_nextbar_label import label_horizon_tercile
from scripts.fx_coint.hourly_flow_features import add_channels, ARMS, build_panel
from scripts.fx_coint.hourly_pooled_decomp import (
    SEEDS, make_model, fit_members, majority_vote, moving_block_bootstrap_ci,
)
from scripts.fx_coint.multiplicity import p_from_t, sidak_alpha, bh_reject

LOOKBACK = 24
TRAIN_MO = 6
TEST_MO = 1
WINDOW = 500


def pooled_metrics(pred, fwd, y_true, cost) -> dict:
    active = pred != 0
    n = int(active.sum())
    dir_acc = float((np.sign(pred[active]) == np.sign(fwd[active])).mean()) if n else np.nan
    bal = float(balanced_accuracy_score(y_true, pred))
    net = pred[active] * fwd[active] - cost
    nm = float(net.mean()) if n else np.nan
    t = float(np.sqrt(n) * nm / (net.std() + 1e-12)) if n else np.nan
    lo, hi = moving_block_bootstrap_ci(net, block=4) if n else (np.nan, np.nan)
    return {"n": n, "dir_acc": dir_acc, "bal_acc": bal, "net": nm, "t": t,
            "ci_lo": lo, "ci_hi": hi}


def run_cell(symbol, year, horizon, arm, seeds, model="QUANT") -> dict:
    cost = DEFAULT_COST_BPS[symbol]
    df = load_hourly(symbol)
    start, end = pd.Timestamp(f"{year}-01-01"), pd.Timestamp(f"{year+1}-01-01")
    df = df[(df["bucket"] >= start) & (df["bucket"] < end)].reset_index(drop=True)
    months = pd.date_range(start, end, freq="MS")
    n_windows = len(months) - TRAIN_MO - TEST_MO
    channels = ARMS[arm]
    preds_all, fwd_all, y_all = [], [], []

    for i in range(n_windows):
        tr_s, tr_e = months[i], months[i + TRAIN_MO]
        te_s = months[i + TRAIN_MO]
        te_e = months[i + TRAIN_MO + TEST_MO] if (i + TRAIN_MO + TEST_MO) < len(months) else end
        margin = tr_s - pd.Timedelta(hours=max(LOOKBACK * 2, WINDOW + 50))
        wdf = df[(df["bucket"] >= margin) & (df["bucket"] < te_e)].reset_index(drop=True)
        wdf = label_horizon_tercile(wdf, horizon=horizon, window=WINDOW)
        wdf = add_channels(wdf)
        X, y, _ = build_panel(wdf, channels, LOOKBACK)
        ts = wdf["bucket"].iloc[LOOKBACK:].reset_index(drop=True)
        valid = wdf["_label_valid"].to_numpy()[LOOKBACK:]
        tr_idx = np.where(((ts >= tr_s) & (ts < tr_e)).to_numpy() & valid)[0]
        te_idx = np.where(((ts >= te_s) & (ts < te_e)).to_numpy() & valid)[0]
        if len(tr_idx) < 500 or len(te_idx) < 100:
            continue
        X_tr, y_tr, X_te = X[tr_idx], y[tr_idx], X[te_idx]
        if np.unique(y_tr).size < 2:
            continue
        votes = fit_members(model, X_tr, y_tr, X_te, seeds)
        preds = majority_vote(votes)
        base = wdf.iloc[LOOKBACK:].reset_index(drop=True)
        preds_all.append(preds)
        fwd_all.append(base["fwd_ret_bps"].to_numpy()[te_idx])
        y_all.append(y[te_idx])

    pred = np.concatenate(preds_all); fwd = np.concatenate(fwd_all); yt = np.concatenate(y_all)
    m = pooled_metrics(pred, fwd, yt, cost)
    m.update(horizon=horizon, arm=arm)
    return m


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbol", default="EURUSD")
    ap.add_argument("--year", type=int, default=2024)
    ap.add_argument("--seeds", type=int, default=5)
    ap.add_argument("--model", default="QUANT")
    args = ap.parse_args()
    seeds = SEEDS[: args.seeds]
    horizons = [1, 3, 6]
    arms = ["price_only", "raw_flow", "engineered", "both"]

    rows = []
    for h in horizons:
        for arm in arms:
            r = run_cell(args.symbol, args.year, h, arm, seeds, args.model)
            rows.append(r)
            print(f"  h={h} {arm:<11s} dirAcc={r['dir_acc']:.3f} balAcc={r['bal_acc']:.3f} "
                  f"net={r['net']:+.3f} t={r['t']:+.2f} CI=[{r['ci_lo']:+.3f},{r['ci_hi']:+.3f}] n={r['n']}",
                  flush=True)

    m = len(rows)
    pvals = [p_from_t(r["t"], r["n"]) for r in rows]
    bh = bh_reject(pvals, 0.05)
    sa = sidak_alpha(0.05, m)
    print(f"\nGrid={m} cells.  Sidak alpha={sa:.4f}")
    print(f"{'cell':<16s} {'dirAcc':>7s} {'net':>7s} {'p':>7s} {'BH':>4s} {'Sidak':>6s}  verdict")
    any_edge = False
    for r, p, bhr in zip(rows, pvals, bh):
        sidak_pass = p < sa
        ci_edge = (r["ci_lo"] > 0) or (r["ci_hi"] < 0)
        edge = ci_edge and (bhr or sidak_pass) and r["net"] > 0
        any_edge = any_edge or edge
        print(f"  h={r['horizon']} {r['arm']:<11s} {r['dir_acc']:>7.3f} {r['net']:>+7.3f} "
              f"{p:>7.4f} {str(bhr):>4s} {str(sidak_pass):>6s}  {'EDGE' if edge else 'noise'}")
    print(f"\nPHASE 1 VERDICT: {'EDGE FOUND -> proceed to Phase 2' if any_edge else 'NO-GO (flow does not rescue hourly direction)'}")


if __name__ == "__main__":
    main()
