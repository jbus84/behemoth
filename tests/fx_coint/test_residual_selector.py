"""Unit tests for the causal residual selector.

Covers:
  * Label construction correctness (fade win / loss).
  * Feature causality (no look-ahead leakage).
  * Regime-lift on synthetic data with deterministic mean-reversion.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from scripts.fx_coint.instruments import MAJORS
from scripts.fx_coint.residual_selector import (
    _build_features,
    _build_labels_and_capture,
    _oriented_returns,
    _residuals,
)


def _synthetic_panel(n_hours: int = 120, n_5m_per_hour: int = 12, seed: int = 7):
    """Build a synthetic fine (5min) + hourly panel for all MAJORS.

    Returns (fine_df, hourly_df).
    """
    rng = np.random.default_rng(seed)
    pairs = MAJORS
    # 5min timestamps
    idx_5m = pd.date_range("2020-01-01", periods=n_hours * n_5m_per_hour,
                            freq="5min", tz="UTC")
    # hourly timestamps
    idx_h = idx_5m[::n_5m_per_hour]

    fine_data = {}
    hourly_data = {}
    for sym in pairs:
        # random walk logmid
        logmid_5m = np.cumsum(rng.normal(0, 0.0002, len(idx_5m)))
        # spread: small fixed absolute spread (scaled by typical price level)
        base_spread = 0.00003 if "JPY" not in sym else 0.003
        spread_5m = np.full(len(idx_5m), base_spread)
        fine_data[(sym, "logmid")] = logmid_5m
        fine_data[(sym, "spread")] = spread_5m
        hourly_data[(sym, "logmid")] = logmid_5m[::n_5m_per_hour]
        hourly_data[(sym, "spread")] = spread_5m[::n_5m_per_hour]

    fine = pd.DataFrame(fine_data, index=idx_5m)
    fine.columns = pd.MultiIndex.from_tuples(fine.columns)
    hourly = pd.DataFrame(hourly_data, index=idx_h)
    hourly.columns = pd.MultiIndex.from_tuples(hourly.columns)
    return fine, hourly


def test_label_construction():
    """Binary label = 1 exactly when residual reverts next hour."""
    # simple 2-pair, 4-hour residual matrix
    residuals = np.array([
        [0.001, -0.0005],   # t0: pair0 long, pair1 short
        [-0.0008, 0.0003],  # t1: pair0 reverts, pair1 reverts
        [0.0002, 0.0001],   # t2
        [0.0001, -0.0002],  # t3
    ])
    spreads = np.full_like(residuals, 0.0001)
    y, cap, net = _build_labels_and_capture(residuals, spreads)
    # flat order: t0p0, t0p1, t1p0, t1p1, t2p0, t2p1
    # t0p0: sign=+1, fwd=-0.0008 -> fade wins -> y=1, cap=+0.0008
    # t0p1: sign=-1, fwd=+0.0003 -> fade wins -> y=1, cap=+0.0003
    # t1p0: sign=-1, fwd=+0.0002 -> fade wins -> y=1
    # t1p1: sign=+1, fwd=+0.0001 -> fade LOSES -> y=0
    assert y[0] == 1
    assert y[1] == 1
    assert y[2] == 1
    assert y[3] == 0
    np.testing.assert_allclose(cap[0], 0.0008 * 1e4, rtol=1e-9)
    np.testing.assert_allclose(net[0], (0.0008 - 0.0001) * 1e4, rtol=1e-9)


def test_no_look_ahead_in_features():
    """Features at hour t must not change when future data is truncated."""
    fine, hourly = _synthetic_panel(n_hours=120)
    hours, oriented = _oriented_returns(hourly)
    factor, residuals = _residuals(oriented)
    features_full = _build_features(hourly, fine, oriented, residuals, factor)

    # Choose a truncation point well inside the data (hour 60)
    trunc = 60
    hourly_t = hourly.iloc[:trunc]
    fine_t = fine.loc[fine.index < hourly.index[trunc]]
    hours_t, oriented_t = _oriented_returns(hourly_t)
    factor_t, residuals_t = _residuals(oriented_t)
    features_trunc = _build_features(hourly_t, fine_t, oriented_t, residuals_t, factor_t)

    # Compare every row that exists in both frames (hours up to trunc-1,
    # because residuals need one diff and features need a few hours of history)
    common = features_trunc.index
    feat_full_sub = features_full.loc[common]
    # numeric columns only
    num_cols = [c for c in feat_full_sub.columns if c not in ("hour", "dow")]
    for col in num_cols:
        full_vals = feat_full_sub[col].to_numpy()
        trunc_vals = features_trunc[col].to_numpy()
        # Both may have NaN in the early warm-up rows; compare where finite
        ok = np.isfinite(full_vals) & np.isfinite(trunc_vals)
        if not ok.any():
            continue
        np.testing.assert_allclose(
            full_vals[ok], trunc_vals[ok], rtol=1e-9,
            err_msg=f"Look-ahead leakage detected in feature '{col}'",
        )


def _inject_regime_hourly(hourly: pd.DataFrame, regime: list[str]) -> pd.DataFrame:
    """Inject deterministic residual reversion/continuation into an hourly panel.

    regime is a list of 'R' (revert) or 'T' (trend) per hour.
    """
    pairs = [c[0] for c in hourly.columns if c[1] == "logmid"]
    logmid = {sym: hourly[(sym, "logmid")].to_numpy().copy() for sym in pairs}
    n_hours = len(regime)
    for h, mode in enumerate(regime):
        direction = 1.0 if h % 2 == 0 else -1.0
        shock = direction * 0.0010
        for sym in pairs:
            logmid[sym][h] += shock
            if mode == "R" and h + 1 < n_hours:
                # Revert next hour
                logmid[sym][h + 1] -= shock * 0.8
            elif mode == "T" and h + 1 < n_hours:
                # Continue next hour
                logmid[sym][h + 1] += shock * 0.5
    for sym in pairs:
        hourly[(sym, "logmid")] = logmid[sym]
    return hourly


def test_regime_selector_lifts_gross():
    """On synthetic data where R regime hours revert strongly,
    the feature engine should produce distinguishable regime signals
    and the capture should be higher in R than T.
    """
    rng = np.random.default_rng(13)
    n_hours = 200
    n_5m = 12
    idx_5m = pd.date_range("2020-01-01", periods=n_hours * n_5m, freq="5min", tz="UTC")
    idx_h = idx_5m[::n_5m]
    pairs = MAJORS
    fine_data, hourly_data = {}, {}
    for sym in pairs:
        logmid = np.cumsum(rng.normal(0, 0.0002, len(idx_5m)))
        hourly_data[(sym, "logmid")] = logmid[::n_5m]
        hourly_data[(sym, "spread")] = np.full(len(idx_h), 0.00002)
        fine_data[(sym, "logmid")] = logmid
        fine_data[(sym, "spread")] = np.full(len(idx_5m), 0.00002)

    hourly = pd.DataFrame(hourly_data, index=idx_h)
    hourly.columns = pd.MultiIndex.from_tuples(hourly.columns)
    fine = pd.DataFrame(fine_data, index=idx_5m)
    fine.columns = pd.MultiIndex.from_tuples(fine.columns)

    # Inject regime: first 100 hours = ranging (revert), last 100 = trending (continue)
    regime = ["R"] * 100 + ["T"] * 100
    hourly = _inject_regime_hourly(hourly, regime)

    hours, oriented = _oriented_returns(hourly)
    factor, residuals = _residuals(oriented)
    features_df = _build_features(hourly, fine, oriented, residuals, factor)
    y_flat, capture_flat, net_flat = _build_labels_and_capture(
        residuals,
        np.stack([hourly[(sym, "spread")].to_numpy()[1:] for sym in pairs], axis=1),
    )

    # Trim last hour
    features_df = features_df.iloc[:-len(pairs)]

    # Verify factor_eff_6 is lower in R regime (more choppy)
    eff_r = features_df.loc[
        features_df.index.get_level_values(0).isin(idx_h[:100]), "factor_eff_6"
    ].mean()
    eff_t = features_df.loc[
        features_df.index.get_level_values(0).isin(idx_h[100:]), "factor_eff_6"
    ].mean()
    assert eff_r < eff_t, "factor_eff_6 should be lower in ranging regime"

    # Verify that capture is positive more often in R regime than T regime
    cap_r = capture_flat[:len(pairs) * 99]  # first 99 valid R hours
    cap_t = capture_flat[len(pairs) * 100:len(pairs) * 199]
    assert (cap_r > 0).mean() > (cap_t > 0).mean(), "R regime should have higher win rate"
