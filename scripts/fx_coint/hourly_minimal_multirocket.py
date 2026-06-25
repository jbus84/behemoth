"""Minimal feature set + MultiRocketHydra on H=12.

Only mid_ret, norm_ret, raw_spread_norm.
Single-threaded to avoid RAM/parallel issues.

Usage:
    uv run python scripts/fx_coint/hourly_minimal_multirocket.py
"""
# ruff: noqa: E402

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import polars as pl
from aeon.classification.convolution_based import MultiRocketHydraClassifier

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
LOOKBACK = 24
TRAIN_MO = 6
TEST_MO = 1
BARRIER_BPS = 10.0
COST_BPS = DEFAULT_COST_BPS[SYM]


def main():
    print("=" * 70)
    print("Minimal + MultiRocketHydra  H=12")
    print("Features: mid_ret, norm_ret, raw_spread_norm")
    print(f"Config: {SYM} {YEAR}  H={HORIZON}  B={BARRIER_BPS}")
    print("=" * 70)

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
    label_counts = []

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
        X, y, regime = build_feature_panel(df, LOOKBACK, exclude_channels=EXCLUDE)
        regime_test = regime.iloc[test_idx].to_numpy()

        X_train, y_train = X[train_idx], y[train_idx]
        X_test, y_test = X[test_idx], y[test_idx]

        if np.unique(y_train).size < 2 or np.unique(y_test).size < 2:
            print(f"  Window {i+1}: insufficient label diversity — skipped")
            continue

        clf = MultiRocketHydraClassifier(n_jobs=1, random_state=42)
        clf.fit(X_train, y_train)
        preds = clf.predict(X_test)

        acc = float((preds == y_test).mean())
        base_df = df.iloc[LOOKBACK:].reset_index(drop=True)
        test_df = base_df.iloc[test_idx].copy().reset_index(drop=True)
        sim = simulate_trades(test_df, preds, COST_BPS, regime_gate=regime_test)

        sherpes.append(sim["net_sharpe"])
        accs.append(acc)
        pos_pcts.append(sim["positive_pct"])
        label_counts.append(int((y_test != 0).sum()))

        print(
            f"  Window {i+1}: Sharpe={sim['net_sharpe']:.3f}  "
            f"Acc={acc:.3f}  Pos={sim['positive_pct']:.1f}%  "
            f"NonZeroLabels={label_counts[-1]}"
        )

    if not sherpes:
        print("No valid windows.")
        return

    print("-" * 70)
    print(
        f"AVERAGE  Sharpe={np.mean(sherpes):.3f}  Acc={np.mean(accs):.3f}  "
        f"Pos={np.mean(pos_pcts):.1f}%  NonZeroLabels={np.mean(label_counts):.0f}"
    )


if __name__ == "__main__":
    main()
