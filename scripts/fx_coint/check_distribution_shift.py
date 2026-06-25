"""Check if train/test distribution shift explains WFO failure.

Computes per-window train-vs-test KS distance on key features.
If shift correlates with Sharpe drop, the user's hypothesis is correct.

Usage:
    uv run python scripts/fx_coint/check_distribution_shift.py
"""
# ruff: noqa: E402

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import polars as pl
from scipy.stats import ks_2samp

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from aeon.classification.convolution_based import MultiRocketHydraClassifier

from scripts.fx_coint.hourly_minimal_multirocket_strict import simulate_strict
from scripts.fx_coint.hourly_multirocket_wfo import (
    DEFAULT_COST_BPS,
    build_feature_panel,
    classify_regime,
    label_hourly,
    load_hourly,
)

EXCLUDE = set(["flow_tick","flow_ofi","rvol_bps","spread_bps","hour_sin","hour_cos","dow_sin","dow_cos"])
SYM = "EURUSD"
YEAR = 2024
HORIZON = 12
LOOKBACK = 24
TRAIN_MO = 6
TEST_MO = 1
BARRIER_BPS = 10.0
COST_BPS = DEFAULT_COST_BPS[SYM]

FEATURES = ["mid_ret", "norm_ret", "raw_spread_norm"]


def ks_distance(train_vals: np.ndarray, test_vals: np.ndarray) -> float:
    """Kolmogorov-Smirnov statistic: max distance between CDFs."""
    stat, _ = ks_2samp(train_vals, test_vals)
    return stat


def main():
    print("=" * 70)
    print("Distribution Shift Analysis  EURUSD 2024")
    print("=" * 70)

    df = load_hourly(SYM)
    start = pd.Timestamp(f"{YEAR}-01-01")
    end = pd.Timestamp(f"{YEAR + 1}-01-01")
    mask = (df["bucket"] >= start) & (df["bucket"] < end)
    df = df[mask].copy().reset_index(drop=True)

    df_pl = pl.from_pandas(df)
    df_pl = label_hourly(df_pl, SYM, barrier_bps=BARRIER_BPS, horizon=HORIZON)
    df = df_pl.to_pandas()

    # Build features once (causal, no leakage)
    df["mid_ret"] = np.log(df["mid"]).diff().fillna(0.0)
    df["norm_ret"] = (
        (df["mid_ret"] - df["mid_ret"].rolling(24, min_periods=24).mean().shift(1))
        / (df["mid_ret"].rolling(24, min_periods=24).std().shift(1) + 1e-12)
    ).fillna(0.0)
    df["raw_spread"] = df["ask"] - df["bid"]
    df["raw_spread_norm"] = (
        (df["raw_spread"] - df["raw_spread"].rolling(24, min_periods=24).mean().shift(1))
        / (df["raw_spread"].rolling(24, min_periods=24).std().shift(1) + 1e-12)
    ).fillna(0.0)

    timestamps = df["bucket"].iloc[LOOKBACK:].reset_index(drop=True)
    months = pd.date_range(start, end, freq="MS")
    n_windows = len(months) - TRAIN_MO - TEST_MO

    results = []
    for i in range(n_windows):
        train_start = months[i]
        train_end = months[i + TRAIN_MO]
        test_start = months[i + TRAIN_MO]
        test_end = months[i + TRAIN_MO + TEST_MO] if (i + TRAIN_MO + TEST_MO) < len(months) else end

        train_mask = (timestamps >= train_start) & (timestamps < train_end)
        test_mask = (timestamps >= test_start) & (timestamps < test_end)
        train_idx = np.where(train_mask.to_numpy())[0] + LOOKBACK
        test_idx = np.where(test_mask.to_numpy())[0] + LOOKBACK

        if len(train_idx) < 500 or len(test_idx) < 100:
            continue

        # Train model
        df["regime"] = classify_regime(df["rvol_bps"], train_idx - LOOKBACK)
        X, y, regime = build_feature_panel(df, LOOKBACK, exclude_channels=EXCLUDE)
        regime_test = regime.iloc[test_idx - LOOKBACK].to_numpy()

        X_train, y_train = X[train_idx - LOOKBACK], y[train_idx - LOOKBACK]
        X_test, y_test = X[test_idx - LOOKBACK], y[test_idx - LOOKBACK]

        if np.unique(y_train).size < 2 or np.unique(y_test).size < 2:
            continue

        clf = MultiRocketHydraClassifier(n_jobs=1, random_state=42)
        clf.fit(X_train, y_train)
        preds = clf.predict(X_test)

        base_df = df.iloc[LOOKBACK:].reset_index(drop=True)
        test_df = base_df.iloc[test_idx - LOOKBACK].copy().reset_index(drop=True)
        sim = simulate_strict(test_df, preds, COST_BPS, BARRIER_BPS, HORIZON, regime_gate=regime_test)
        sharpe = sim["net_sharpe"]

        # Compute distribution shift per feature
        ks_vals = {}
        for feat in FEATURES:
            tr = df[feat].iloc[train_idx].dropna().to_numpy()
            te = df[feat].iloc[test_idx].dropna().to_numpy()
            ks_vals[feat] = ks_distance(tr, te)

        # Also check regime shift (proportion of high-vol)
        train_high = (df["regime"].iloc[train_idx] == 2).mean()
        test_high = (df["regime"].iloc[test_idx] == 2).mean()
        regime_shift = abs(train_high - test_high)

        results.append({
            "window": i + 1,
            "sharpe": sharpe,
            "train_start": train_start.strftime("%Y-%m"),
            "test_start": test_start.strftime("%Y-%m"),
            "mid_ret_ks": ks_vals["mid_ret"],
            "norm_ret_ks": ks_vals["norm_ret"],
            "spread_ks": ks_vals["raw_spread_norm"],
            "max_ks": max(ks_vals.values()),
            "regime_shift": regime_shift,
            "train_highvol_pct": round(train_high * 100, 1),
            "test_highvol_pct": round(test_high * 100, 1),
        })

        print(
            f"  W{i+1}: Sharpe={sharpe: .3f}  "
            f"mid_ret_KS={ks_vals['mid_ret']:.3f}  "
            f"norm_KS={ks_vals['norm_ret']:.3f}  "
            f"spread_KS={ks_vals['raw_spread_norm']:.3f}  "
            f"regime_shift={regime_shift:.3f}"
        )

    if not results:
        print("No results.")
        return

    print("-" * 70)
    # Correlation between KS distance and Sharpe
    ks_arr = np.array([r["max_ks"] for r in results])
    sharpe_arr = np.array([r["sharpe"] for r in results])
    regime_arr = np.array([r["regime_shift"] for r in results])

    if len(ks_arr) > 2:
        corr_ks = np.corrcoef(ks_arr, sharpe_arr)[0, 1]
        corr_regime = np.corrcoef(regime_arr, sharpe_arr)[0, 1]
        print(f"Corr(Max_KS, Sharpe)     = {corr_ks: .3f}")
        print(f"Corr(RegimeShift, Sharpe)  = {corr_regime: .3f}")
        print(f"\nMean max KS distance: {ks_arr.mean():.3f}  (0 = identical, 1 = completely different)")

    # Print sorted by KS distance
    print("\nSorted by distribution shift (highest KS first):")
    for r in sorted(results, key=lambda x: x["max_ks"], reverse=True):
        print(
            f"  W{r['window']}  Train={r['train_start']}→{r['test_start']}  "
            f"Sharpe={r['sharpe']: .3f}  MaxKS={r['max_ks']:.3f}  "
            f"RegimeShift={r['regime_shift']:.3f}"
        )


if __name__ == "__main__":
    main()
