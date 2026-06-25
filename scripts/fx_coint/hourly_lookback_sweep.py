"""Sweep lookback lengths to find if signal exists at a different temporal scale.

Uses window-clean labels + RidgeClassifierCV + strict simulation.
Fast enough to test many lookbacks.

Usage:
    uv run python scripts/fx_coint/hourly_lookback_sweep.py
"""
# ruff: noqa: E402

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import polars as pl
from sklearn.linear_model import RidgeClassifierCV

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.fx_coint.hourly_minimal_multirocket_strict import simulate_strict
from scripts.fx_coint.hourly_multirocket_wfo import (
    DEFAULT_COST_BPS,
    build_feature_panel,
    classify_regime,
    load_hourly,
)
from scripts.fx_coint.hourly_triple_barrier import label_hourly

EXCLUDE = set([
    "flow_tick",
    "flow_ofi",
    "rvol_bps",
    "spread_bps",
    "hour_sin",
    "hour_cos",
    "dow_sin",
    "dow_cos",
])

SYM = "EURUSD"
YEAR = 2024
HORIZON = 12
TRAIN_MO = 6
TEST_MO = 1
BARRIER_BPS = 10.0
COST_BPS = DEFAULT_COST_BPS[SYM]

LOOKBACKS = [6, 12, 18, 24, 36, 48, 72, 96]


def run_lookback(lookback: int) -> dict:
    print(f"\n--- LOOKBACK = {lookback}h ---")
    df = load_hourly(SYM)
    start = pd.Timestamp(f"{YEAR}-01-01")
    end = pd.Timestamp(f"{YEAR + 1}-01-01")
    mask = (df["bucket"] >= start) & (df["bucket"] < end)
    df = df[mask].copy().reset_index(drop=True)

    # Window-clean labels
    margin_start = start - pd.Timedelta(hours=lookback * 2)
    window_df = df[(df["bucket"] >= margin_start) & (df["bucket"] < end)].copy().reset_index(drop=True)
    window_df = label_hourly(pl.from_pandas(window_df), SYM, barrier_bps=BARRIER_BPS, horizon=HORIZON).to_pandas()

    timestamps = window_df["bucket"].iloc[lookback:].reset_index(drop=True)
    months = pd.date_range(start, end, freq="MS")
    n_windows = len(months) - TRAIN_MO - TEST_MO

    sherpes = []
    accs = []
    pos_pcts = []
    n_trades_list = []

    for i in range(n_windows):
        train_start = months[i]
        train_end = months[i + TRAIN_MO]
        test_start = months[i + TRAIN_MO]
        test_end = months[i + TRAIN_MO + TEST_MO] if (i + TRAIN_MO + TEST_MO) < len(months) else end

        train_mask = (timestamps >= train_start) & (timestamps < train_end)
        test_mask = (timestamps >= test_start) & (timestamps < test_end)
        train_idx = np.where(train_mask.to_numpy())[0]
        test_idx = np.where(test_mask.to_numpy())[0]

        if len(train_idx) < 500 or len(test_idx) < 100:
            continue

        window_df["regime"] = classify_regime(window_df["rvol_bps"], train_idx)
        X, y, regime = build_feature_panel(window_df, lookback, exclude_channels=EXCLUDE)
        regime_test = regime.iloc[test_idx].to_numpy()

        X_train, y_train = X[train_idx], y[train_idx]
        X_test, y_test = X[test_idx], y[test_idx]

        if np.unique(y_train).size < 2 or np.unique(y_test).size < 2:
            continue

        clf = RidgeClassifierCV(alphas=[0.01, 0.1, 1.0, 10.0, 100.0], cv=3)
        X_train_f = X_train.reshape(len(X_train), -1)
        X_test_f = X_test.reshape(len(X_test), -1)
        clf.fit(X_train_f, y_train)
        preds = clf.predict(X_test_f)

        acc = float((preds == y_test).mean())
        base_df = window_df.iloc[lookback:].reset_index(drop=True)
        test_df = base_df.iloc[test_idx].copy().reset_index(drop=True)
        sim = simulate_strict(test_df, preds, COST_BPS, BARRIER_BPS, HORIZON, regime_gate=regime_test)

        sherpes.append(sim["net_sharpe"])
        accs.append(acc)
        pos_pcts.append(sim["positive_pct"])
        n_trades_list.append(sim["n_trades"])

        print(
            f"  W{i+1}: Sharpe={sim['net_sharpe']: .3f}  Acc={acc:.3f}  "
            f"Pos={sim['positive_pct']:.1f}%  Trades={sim['n_trades']}"
        )

    if not sherpes:
        return {"lookback": lookback, "avg_sharpe": 0.0, "median_sharpe": 0.0, "std_sharpe": 0.0, "n": 0}

    return {
        "lookback": lookback,
        "avg_sharpe": round(float(np.mean(sherpes)), 3),
        "median_sharpe": round(float(np.median(sherpes)), 3),
        "std_sharpe": round(float(np.std(sherpes)), 3),
        "avg_acc": round(float(np.mean(accs)), 3),
        "avg_pos_pct": round(float(np.mean(pos_pcts)), 1),
        "avg_trades": round(float(np.mean(n_trades_list)), 0),
        "n": len(sherpes),
    }


def main():
    print("=" * 70)
    print("LOOKBACK SWEEP  (window-clean + RidgeClassifierCV + strict simulation)")
    print(f"Symbol={SYM}  Year={YEAR}  H={HORIZON}  Barrier={BARRIER_BPS}")
    print("=" * 70)

    results = []
    for lb in LOOKBACKS:
        r = run_lookback(lb)
        results.append(r)

    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"{'Lookback':>10s} {'AvgSharpe':>10s} {'Median':>10s} {'Std':>8s} {'N':>4s} {'AvgAcc':>8s} {'AvgPos%':>8s}")
    print("-" * 70)
    for r in results:
        print(
            f"{r['lookback']:>10d} {r['avg_sharpe']:>10.3f} {r['median_sharpe']:>10.3f} "
            f"{r['std_sharpe']:>8.3f} {r['n']:>4d} {r['avg_acc']:>8.3f} {r['avg_pos_pct']:>8.1f}"
        )

    best = max(results, key=lambda x: x["avg_sharpe"])
    print(f"\nBest lookback: {best['lookback']}h  AvgSharpe={best['avg_sharpe']:.3f}")


if __name__ == "__main__":
    main()
