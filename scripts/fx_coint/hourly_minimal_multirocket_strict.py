"""Minimal + MultiRocketHydra H=12 with STRICT barrier simulation.

Same model training, but simulation monitors bid/ask in real time within
each test window to determine exit (no pre-labeled tb_horizon leakage).

Usage:
    uv run python scripts/fx_coint/hourly_minimal_multirocket_strict.py
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


def simulate_strict(
    df: pd.DataFrame,
    preds: np.ndarray,
    cost_bps: float,
    barrier_bps: float,
    horizon: int,
    regime_gate: np.ndarray | None = None,
) -> dict:
    """Simulate trading by monitoring barriers live — no pre-labeled hold times."""
    n = len(df)
    rets = []
    skipped = 0
    for i in range(n - 1):
        pred = preds[i]
        if pred == 0:
            continue
        if regime_gate is not None and regime_gate[i] == 2:
            skipped += 1
            continue

        entry_ask = df["ask"].iloc[i + 1]
        entry_bid = df["bid"].iloc[i + 1]
        entry_mid = (entry_ask + entry_bid) / 2.0
        cost_target = entry_mid * barrier_bps / 10_000.0
        cost_price = entry_mid * cost_bps / 10_000.0

        upper = entry_ask + cost_target
        lower = entry_bid - cost_target

        # Scan forward within this test window
        exit_idx = None
        max_j = min(i + 1 + horizon, n)
        for j in range(i + 1, max_j):
            if pred == 1 and df["bid"].iloc[j] >= upper:
                exit_idx = j
                break
            if pred == -1 and df["ask"].iloc[j] <= lower:
                exit_idx = j
                break

        if exit_idx is None:
            # Time expiry — exit at last bar
            exit_idx = max_j - 1

        exit_ask = df["ask"].iloc[exit_idx]
        exit_bid = df["bid"].iloc[exit_idx]

        gross = exit_bid - entry_ask if pred == 1 else entry_bid - exit_ask

        net = gross - cost_price
        rets.append(net / entry_mid)

    if not rets:
        return {"net_sharpe": 0.0, "positive_pct": 0.0, "n_trades": 0, "skipped": skipped}

    rets = np.array(rets)
    return {
        "net_sharpe": round(np.sqrt(len(rets)) * rets.mean() / (rets.std() + 1e-12), 3),
        "positive_pct": round((rets > 0).mean() * 100, 1),
        "n_trades": len(rets),
        "skipped": skipped,
    }


def main():
    print("=" * 70)
    print("Minimal + MultiRocketHydra  H=12  (STRICT simulation)")
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
        sim = simulate_strict(test_df, preds, COST_BPS, BARRIER_BPS, HORIZON, regime_gate=regime_test)

        sherpes.append(sim["net_sharpe"])
        accs.append(acc)
        pos_pcts.append(sim["positive_pct"])
        label_counts.append(int((y_test != 0).sum()))

        print(
            f"  Window {i+1}: Sharpe={sim['net_sharpe']:.3f}  "
            f"Acc={acc:.3f}  Pos={sim['positive_pct']:.1f}%  "
            f"Trades={sim['n_trades']}"
        )

    if not sherpes:
        print("No valid windows.")
        return

    print("-" * 70)
    print(
        f"AVERAGE  Sharpe={np.mean(sherpes):.3f}  Acc={np.mean(accs):.3f}  "
        f"Pos={np.mean(pos_pcts):.1f}%"
    )


if __name__ == "__main__":
    main()
