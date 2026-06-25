"""Parallel feature ablation study for hourly MultiRocketHydra WFO.

Runs the baseline and one-at-a-time exclusions in parallel using joblib.

Usage:
    uv run python scripts/fx_coint/hourly_multirocket_ablation_parallel.py
"""
# ruff: noqa: E402

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import polars as pl
from aeon.classification.convolution_based import MultiRocketHydraClassifier
from joblib import Parallel, delayed

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.fx_coint.hourly_multirocket_wfo import (
    DEFAULT_COST_BPS,
    build_feature_panel,
    classify_regime,
    label_hourly,
    load_hourly,
    simulate_trades,
)

ALL_CHANNELS = [
    "mid_ret",
    "norm_ret",
    "flow_tick",
    "flow_ofi",
    "rvol_bps",
    "spread_bps",
    "raw_spread_norm",
    "hour_sin",
    "hour_cos",
    "dow_sin",
    "dow_cos",
]

SYM = "EURUSD"
YEAR = 2024
HORIZON = 12
LOOKBACK = 24
TRAIN_MO = 6
TEST_MO = 1
BARRIER_BPS = 10.0
COST_BPS = DEFAULT_COST_BPS[SYM]


def _run_variant(exclude: set[str]) -> dict:
    """Run a single WFO variant."""
    df = load_hourly(SYM)
    start = pd.Timestamp(f"{YEAR}-01-01")
    end = pd.Timestamp(f"{YEAR + 1}-01-01")
    mask = (df["bucket"] >= start) & (df["bucket"] < end)
    df = df[mask].copy().reset_index(drop=True)

    df_pl = pl.from_pandas(df)
    df_pl = label_hourly(df_pl, SYM, barrier_bps=BARRIER_BPS, horizon=HORIZON)
    df = df_pl.to_pandas()

    timestamps = df["bucket"].iloc[LOOKBACK:].reset_index(drop=True)
    months = pd.date_range(start, end, freq="MS")
    n_months = len(months)
    n_windows = n_months - TRAIN_MO - TEST_MO

    sherpes = []
    accs = []
    pos_pcts = []

    for i in range(n_windows):
        train_start = months[i]
        train_end = months[i + TRAIN_MO]
        test_start = months[i + TRAIN_MO]
        test_end = months[i + TRAIN_MO + TEST_MO] if (i + TRAIN_MO + TEST_MO) < n_months else end

        train_mask = (timestamps >= train_start) & (timestamps < train_end)
        test_mask = (timestamps >= test_start) & (timestamps < test_end)

        train_idx = np.where(train_mask.to_numpy())[0]
        test_idx = np.where(test_mask.to_numpy())[0]

        if len(train_idx) < 500 or len(test_idx) < 100:
            continue

        df["regime"] = classify_regime(df["rvol_bps"], train_idx)
        X, y, regime = build_feature_panel(df, LOOKBACK, exclude_channels=exclude)
        regime_test = regime.iloc[test_idx].to_numpy()

        X_train, y_train = X[train_idx], y[train_idx]
        X_test, y_test = X[test_idx], y[test_idx]

        clf = MultiRocketHydraClassifier(random_state=42, n_jobs=1)
        clf.fit(X_train, y_train)
        preds = clf.predict(X_test)

        acc = float((preds == y_test).mean())
        base_df = df.iloc[LOOKBACK:].reset_index(drop=True)
        test_df = base_df.iloc[test_idx].copy().reset_index(drop=True)
        sim = simulate_trades(test_df, preds, COST_BPS, regime_gate=regime_test)

        sherpes.append(sim["net_sharpe"])
        accs.append(acc)
        pos_pcts.append(sim["positive_pct"])

    return {
        "variant": "baseline" if not exclude else "-".join(sorted(exclude)),
        "n_win": len(sherpes),
        "avg_sharpe": round(float(np.mean(sherpes)), 3) if sherpes else 0.0,
        "avg_acc": round(float(np.mean(accs)), 3) if accs else 0.0,
        "avg_pos": round(float(np.mean(pos_pcts)), 1) if pos_pcts else 0.0,
        "sharpe_std": round(float(np.std(sherpes)), 3) if sherpes else 0.0,
    }


def main():
    print("=" * 70)
    print("Feature Ablation Study (parallel)")
    print(f"Config: {SYM} {YEAR} H={HORIZON} B={BARRIER_BPS}")
    print("=" * 70)

    # Prepare all variants
    variants = [set()] + [{ch} for ch in ALL_CHANNELS]

    print(f"\nRunning {len(variants)} variants in parallel...")
    results = Parallel(n_jobs=2, pre_dispatch=2, verbose=10)(
        delayed(_run_variant)(v) for v in variants
    )

    print("\n" + "=" * 70)
    print("ABLATION RESULTS")
    print("=" * 70)
    print(
        f"{'Variant':<25s} {'Win':>4s} {'AvgAcc':>7s} {'AvgPos%':>8s} "
        f"{'AvgSharpe':>10s} {'StdSharpe':>10s}"
    )
    print("-" * 70)
    for r in results:
        print(
            f"{r['variant']:<25s} {r['n_win']:>4d} {r['avg_acc']:>7.3f} "
            f"{r['avg_pos']:>8.1f} {r['avg_sharpe']:>10.3f} {r['sharpe_std']:>10.3f}"
        )

    baseline_sh = results[0]["avg_sharpe"]
    print("-" * 70)
    print(f"Baseline Sharpe: {baseline_sh:.3f}")
    print("\nDelta from baseline (positive = hurt when removed):")
    for r in results[1:]:
        delta = baseline_sh - r["avg_sharpe"]
        sign = "▲" if delta > 0 else "▼"
        print(
            f"  {sign}  Exclude {r['variant']:<20s}  Sharpe {r['avg_sharpe']:>7.3f}  "
            f"delta {delta:+.3f}"
        )


if __name__ == "__main__":
    main()
