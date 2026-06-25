"""Diagnose WHY RDST P&L mirrors MRHydra: anti-correlated skill vs opposite bias.

For each WFO window (seed 42, single fit per model) collect prediction vectors,
then pool and report:
  * per-model long/short/flat fractions  (directional bias)
  * pairwise correlation of prediction vectors  (shared/inverted axis?)
  * sign agreement on co-active samples       (do they invert each other?)
  * mean forward 12h return by predicted class (is P&L just bias x drift?)

Usage:
    uv run python scripts/fx_coint/hourly_pred_agreement.py --year 2024
"""
# ruff: noqa: E402

from __future__ import annotations

import argparse
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import polars as pl

warnings.filterwarnings("ignore")

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.fx_coint.hourly_multirocket_wfo import (
    build_feature_panel,
    classify_regime,
    load_hourly,
)
from scripts.fx_coint.hourly_pooled_decomp import (
    BARRIER_BPS,
    EXCLUDE,
    HORIZON,
    LOOKBACK,
    TEST_MO,
    TRAIN_MO,
    make_model,
)
from scripts.fx_coint.hourly_triple_barrier import label_hourly

MODELS = ["MRHydra", "QUANT", "RDST"]
SEED = 42


def run(symbol: str, year: int):
    df = load_hourly(symbol)
    start, end = pd.Timestamp(f"{year}-01-01"), pd.Timestamp(f"{year+1}-01-01")
    df = df[(df["bucket"] >= start) & (df["bucket"] < end)].reset_index(drop=True)
    months = pd.date_range(start, end, freq="MS")
    n_windows = len(months) - TRAIN_MO - TEST_MO

    preds_pool = {m: [] for m in MODELS}
    fwd_pool = []  # forward 12h mid return (bps) aligned to each test sample

    for i in range(n_windows):
        tr_s, tr_e = months[i], months[i + TRAIN_MO]
        te_s = months[i + TRAIN_MO]
        te_e = months[i + TRAIN_MO + TEST_MO] if (i + TRAIN_MO + TEST_MO) < len(months) else end
        margin = tr_s - pd.Timedelta(hours=LOOKBACK * 2)
        wdf = df[(df["bucket"] >= margin) & (df["bucket"] < te_e)].reset_index(drop=True)
        wdf = label_hourly(pl.from_pandas(wdf), symbol, barrier_bps=BARRIER_BPS,
                           horizon=HORIZON).to_pandas()
        ts = wdf["bucket"].iloc[LOOKBACK:].reset_index(drop=True)
        tr_idx = np.where(((ts >= tr_s) & (ts < tr_e)).to_numpy())[0]
        te_idx = np.where(((ts >= te_s) & (ts < te_e)).to_numpy())[0]
        if len(tr_idx) < 500 or len(te_idx) < 100:
            continue
        wdf["regime"] = classify_regime(wdf["rvol_bps"], tr_idx)
        X, y, _ = build_feature_panel(wdf, LOOKBACK, exclude_channels=EXCLUDE)
        X = X.astype(np.float64)
        X_tr, y_tr, X_te = X[tr_idx], y[tr_idx], X[te_idx]
        if np.unique(y_tr).size < 2:
            continue

        # forward 12h mid return for each test sample
        base = wdf.iloc[LOOKBACK:].reset_index(drop=True)
        mid = base["mid"].to_numpy()
        fwd = np.full(len(te_idx), np.nan)
        for k, ti in enumerate(te_idx):
            j = min(ti + HORIZON, len(mid) - 1)
            fwd[k] = (mid[j] - mid[ti]) / mid[ti] * 10_000.0
        fwd_pool.append(fwd)

        print(f"  [W{i+1}] {te_s:%Y-%m}  n_te={len(te_idx)}", flush=True)
        for m in MODELS:
            clf = make_model(m, SEED)
            clf.fit(X_tr, y_tr)
            preds_pool[m].append(clf.predict(X_te).astype(np.int8))

    P = {m: np.concatenate(v) for m, v in preds_pool.items()}
    fwd = np.concatenate(fwd_pool)
    return P, fwd


def report(P: dict, fwd: np.ndarray):
    n = len(next(iter(P.values())))
    print(f"\n{'='*78}\nPREDICTION STRUCTURE  (pooled, n={n} test samples)\n{'='*78}")
    print(f"{'model':<10s} {'long%':>7s} {'short%':>7s} {'flat%':>7s} "
          f"{'fwd|long':>9s} {'fwd|short':>9s}")
    for m, p in P.items():
        lng, sht, flt = (p == 1).mean(), (p == -1).mean(), (p == 0).mean()
        fl = fwd[p == 1].mean() if (p == 1).any() else np.nan
        fs = fwd[p == -1].mean() if (p == -1).any() else np.nan
        print(f"{m:<10s} {lng*100:>6.1f}% {sht*100:>6.1f}% {flt*100:>6.1f}% "
              f"{fl:>+9.3f} {fs:>+9.3f}")

    print("\nPairwise prediction-vector correlation (Pearson on -1/0/1):")
    ms = list(P)
    for a in range(len(ms)):
        for b in range(a + 1, len(ms)):
            pa, pb = P[ms[a]], P[ms[b]]
            c = np.corrcoef(pa, pb)[0, 1]
            co = (pa != 0) & (pb != 0)
            agree = (np.sign(pa[co]) == np.sign(pb[co])).mean() if co.any() else np.nan
            print(f"  {ms[a]:>8s} vs {ms[b]:<8s}  corr={c:+.3f}   "
                  f"co-active={co.mean()*100:4.1f}%  same-sign-when-both-active={agree*100:5.1f}%")

    print("\nfwd 12h return by predicted class tells the story:")
    print("  if fwd|long > 0 and fwd|short < 0 for a model -> real directional skill")
    print("  if a model is ~all-long (or all-short) -> P&L is bias x drift, not skill")
    print(f"  overall market fwd-12h drift = {fwd.mean():+.3f} bps/bar")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbol", default="EURUSD")
    ap.add_argument("--year", type=int, default=2024)
    args = ap.parse_args()
    print(f"=== prediction agreement  {args.symbol} {args.year}  seed={SEED} ===")
    P, fwd = run(args.symbol, args.year)
    report(P, fwd)


if __name__ == "__main__":
    main()
