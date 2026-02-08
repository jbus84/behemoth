#!/usr/bin/env python3
"""
Causality audit for H1 Meta Model features.

Checks (on real data):
1) Future perturbation invariance: features at index i are unchanged when future data is modified.
2) Inference parity: inference feature computation matches training feature logic for the same index.
"""

import os
import sys
import numpy as np
import polars as pl
from datetime import datetime

sys.path.append(os.path.join(os.getcwd(), "scripts"))
from build_meta_dataset_v3_h1 import compute_kalman_states, compute_z_scores, compute_features_at_entry
from inference_meta_model import MetaModelInference


TOL = {
    "spread_std": 0.1,
    "entry_atr": 0.1,
    "ret_X_16b": 0.1,
    "ret_Y_16b": 0.1,
    "trend_strength": 0.02,
    "vol_ratio": 0.02,
    "correlation_500": 0.02,
    "beta_stability": 0.01,
    "atr_ratio": 0.02,
    "vol_regime": 0.02,
    "z_entry": 0.01,
    "z_velocity": 0.01,
    "beta": 0.01,
    "signal_beta_lookback": 0.02,
    "hedge_beta_lookback": 0.02,
    "beta_mismatch": 0.05,
    "hour": 0.0,
    "day_of_week": 0.0,
}

KEYS = [
    "z_entry",
    "z_velocity",
    "spread_std",
    "beta_stability",
    "beta",
    "signal_beta_lookback",
    "hedge_beta_lookback",
    "beta_mismatch",
    "vol_ratio",
    "correlation_500",
    "trend_strength",
    "hour",
    "day_of_week",
    "ret_X_16b",
    "ret_Y_16b",
    "atr_ratio",
    "entry_atr",
    "vol_regime",
]


def _assert_close(a, b, tol):
    return abs(a - b) <= tol


def load_pair(y_sym, x_sym, n_tail=6000):
    p_y = f"data/global_1h/{y_sym}_1h.parquet"
    p_x = f"data/global_1h/{x_sym}_1h.parquet"
    if not os.path.exists(p_y) or not os.path.exists(p_x):
        raise FileNotFoundError(f"Missing data for {y_sym} or {x_sym}")

    df_y = pl.read_parquet(p_y).rename({f"close_{y_sym}": "Y"})
    df_x = pl.read_parquet(p_x).rename({f"close_{x_sym}": "X"})
    df = df_y.join(df_x, on="timestamp", how="inner").sort("timestamp")

    if len(df) > n_tail:
        df = df.tail(n_tail)

    y = np.log(df["Y"].to_numpy())
    x = np.log(df["X"].to_numpy())
    ts = df["timestamp"].to_numpy()
    return df, y, x, ts


def audit_future_perturbation(y, x, ts, seed=7, samples=20):
    rng = np.random.default_rng(seed)
    n = len(y)
    # ensure enough history and future
    idxs = rng.integers(700, n - 200, size=samples)

    betas, errors, ret_betas = compute_kalman_states(y, x)
    z_scores = compute_z_scores(errors)

    max_diff = {k: 0.0 for k in KEYS}
    failures = 0

    for i in idxs:
        feat = compute_features_at_entry(i, y, x, betas, errors, ret_betas, z_scores, ts)

        # Perturb future only
        y2 = y.copy()
        x2 = x.copy()
        y2[i + 1:] += rng.normal(0.0, 0.05, size=n - i - 1)
        x2[i + 1:] += rng.normal(0.0, 0.05, size=n - i - 1)

        betas2, errors2, ret_betas2 = compute_kalman_states(y2, x2)
        z_scores2 = compute_z_scores(errors2)

        feat2 = compute_features_at_entry(i, y2, x2, betas2, errors2, ret_betas2, z_scores2, ts)

        for k in KEYS:
            a = float(feat[k])
            b = float(feat2[k])
            diff = abs(a - b)
            if diff > max_diff[k]:
                max_diff[k] = diff
            if not _assert_close(a, b, TOL.get(k, 0.05)):
                failures += 1

    return {
        "samples": samples,
        "failures": failures,
        "max_diff": max_diff,
    }


def audit_inference_parity(df, y, x, ts, seed=11, samples=20):
    rng = np.random.default_rng(seed)
    n = len(y)
    idxs = rng.integers(700, n - 1, size=samples)

    inf = MetaModelInference(load_model=False)

    max_diff = {k: 0.0 for k in KEYS}
    failures = 0

    for i in idxs:
        # Train features at i
        betas, errors, ret_betas = compute_kalman_states(y[: i + 1], x[: i + 1])
        z_scores = compute_z_scores(errors)
        feat = compute_features_at_entry(i, y[: i + 1], x[: i + 1], betas, errors, ret_betas, z_scores, ts[: i + 1])

        # Inference features at i (last row)
        df_slice = df.head(i + 1)
        betas_inf, errors_inf, ret_betas_inf = inf._compute_kalman(np.log(df_slice["Y"].to_numpy()), np.log(df_slice["X"].to_numpy()))
        # recompute z for inference parity
        s_err = errors_inf
        z_inf = compute_z_scores(s_err)
        pdf = inf._compute_features(df_slice.rename({"Y": "close_Y", "X": "close_X"}), betas_inf, errors_inf, ret_betas_inf, z_inf)
        last = pdf.iloc[-1]

        for k in KEYS:
            a = float(feat[k])
            b = float(last[k])
            diff = abs(a - b)
            if diff > max_diff[k]:
                max_diff[k] = diff
            if not _assert_close(a, b, TOL.get(k, 0.05)):
                failures += 1

    return {
        "samples": samples,
        "failures": failures,
        "max_diff": max_diff,
    }


def main():
    y_sym = os.environ.get("Y_SYM", "XAUUSD")
    x_sym = os.environ.get("X_SYM", "BCOUSD")
    samples = int(os.environ.get("SAMPLES", "20"))

    df, y, x, ts = load_pair(y_sym, x_sym)

    print(f"Causality audit on {y_sym}/{x_sym} | bars={len(y)} | samples={samples}")

    fut = audit_future_perturbation(y, x, ts, samples=samples)
    print("\nFuture perturbation invariance:")
    print(f"  Samples: {fut['samples']}")
    print(f"  Failures: {fut['failures']}")
    print("  Max diffs (selected):")
    for k in ["z_entry", "spread_std", "beta", "beta_mismatch", "vol_ratio", "entry_atr", "trend_strength"]:
        print(f"    {k}: {fut['max_diff'][k]:.4f}")

    inf = audit_inference_parity(df, y, x, ts, samples=samples)
    print("\nInference parity:")
    print(f"  Samples: {inf['samples']}")
    print(f"  Failures: {inf['failures']}")
    print("  Max diffs (selected):")
    for k in ["z_entry", "spread_std", "beta", "beta_mismatch", "vol_ratio", "entry_atr", "trend_strength"]:
        print(f"    {k}: {inf['max_diff'][k]:.4f}")


if __name__ == "__main__":
    main()
