#!/usr/bin/env python3
"""Causal robust-KF style entry features from per-pair Kalman state series."""

from __future__ import annotations

import numpy as np
import pandas as pd


_OUT_COLS = [
    "kf_abs_z",
    "kf_innov",
    "kf_innov_std",
    "kf_robust_z",
    "kf_student_loglik",
    "kf_tod_scale",
    "kf_huber_weight",
    "kf_jump_prob",
    "kf_z_vel",
    "kf_z_accel",
]


def _ensure_cols(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    for col in _OUT_COLS:
        if col not in out.columns:
            out[col] = np.nan
    return out


def _hour_bucket(ts_ns: np.ndarray) -> np.ndarray:
    if len(ts_ns) == 0:
        return np.zeros(0, dtype=np.int16)
    ts = pd.to_datetime(pd.Series(ts_ns, dtype="int64"), unit="ns", utc=True)
    return ts.dt.hour.to_numpy(dtype=np.int16)


def compute_robust_kf_series_features(
    z: np.ndarray,
    ts_ns: np.ndarray,
    student_df: float,
    huber_c: float,
    ew_alpha: float,
    tod_alpha: float,
    jump_prior: float,
    jump_var_mult: float,
) -> dict[str, np.ndarray]:
    n = int(len(z))
    if n == 0:
        return {k: np.zeros(0, dtype=float) for k in _OUT_COLS}

    z = np.asarray(z, dtype=float)
    hours = _hour_bucket(np.asarray(ts_ns, dtype="int64"))

    innov = np.zeros(n, dtype=float)
    if n > 1:
        innov[1:] = z[1:] - z[:-1]

    warm = min(max(10, n // 20), n)
    base_var0 = float(np.var(innov[:warm], ddof=0))
    if not np.isfinite(base_var0) or base_var0 <= 1e-10:
        base_var0 = 1.0

    ew_alpha = float(np.clip(ew_alpha, 1e-4, 0.5))
    tod_alpha = float(np.clip(tod_alpha, 1e-4, 0.5))
    student_df = float(max(student_df, 2.1))
    huber_c = float(max(huber_c, 0.25))
    jump_prior = float(np.clip(jump_prior, 1e-4, 0.5))
    jump_var_mult = float(max(jump_var_mult, 1.5))

    base_var = base_var0
    global_var = base_var0
    hour_var = np.full(24, base_var0, dtype=float)

    out_abs_z = np.abs(z)
    out_z_vel = np.zeros(n, dtype=float)
    out_z_accel = np.zeros(n, dtype=float)
    if n > 1:
        out_z_vel[1:] = z[1:] - z[:-1]
    if n > 2:
        out_z_accel[2:] = out_z_vel[2:] - out_z_vel[1:-1]
    out_innov = np.zeros(n, dtype=float)
    out_innov_std = np.zeros(n, dtype=float)
    out_robust_z = np.zeros(n, dtype=float)
    out_ll = np.zeros(n, dtype=float)
    out_tod_scale = np.ones(n, dtype=float)
    out_huber_w = np.ones(n, dtype=float)
    out_jump_prob = np.full(n, jump_prior, dtype=float)

    for i in range(n):
        h = int(hours[i]) if 0 <= int(hours[i]) <= 23 else 0
        tod_scale = float(np.clip(hour_var[h] / max(global_var, 1e-10), 0.25, 4.0))
        var_t = float(max(base_var * tod_scale, 1e-10))
        std_t = float(np.sqrt(var_t))
        nu = float(innov[i])

        robust_z = float(nu / std_t)
        abs_robust_z = abs(robust_z)
        huber_w = 1.0 if abs_robust_z <= huber_c else float(huber_c / max(abs_robust_z, 1e-10))

        ll = -0.5 * np.log(var_t) - 0.5 * (student_df + 1.0) * np.log1p((nu * nu) / (student_df * var_t))

        like_base = np.exp(-0.5 * (nu * nu) / var_t) / np.sqrt(var_t)
        jump_var = float(max(var_t * jump_var_mult, 1e-10))
        like_jump = np.exp(-0.5 * (nu * nu) / jump_var) / np.sqrt(jump_var)
        denom = jump_prior * like_jump + (1.0 - jump_prior) * like_base
        p_jump = float((jump_prior * like_jump) / max(denom, 1e-12))

        out_innov[i] = nu
        out_innov_std[i] = std_t
        out_robust_z[i] = robust_z
        out_ll[i] = ll
        out_tod_scale[i] = tod_scale
        out_huber_w[i] = huber_w
        out_jump_prob[i] = p_jump

        sq = nu * nu
        base_var = (1.0 - ew_alpha) * base_var + ew_alpha * sq
        global_var = (1.0 - tod_alpha) * global_var + tod_alpha * sq
        hour_var[h] = (1.0 - tod_alpha) * hour_var[h] + tod_alpha * sq

    return {
        "kf_abs_z": out_abs_z,
        "kf_innov": out_innov,
        "kf_innov_std": out_innov_std,
        "kf_robust_z": out_robust_z,
        "kf_student_loglik": out_ll,
        "kf_tod_scale": out_tod_scale,
        "kf_huber_weight": out_huber_w,
        "kf_jump_prob": out_jump_prob,
        "kf_z_vel": out_z_vel,
        "kf_z_accel": out_z_accel,
    }


def add_robust_kf_features(
    df: pd.DataFrame,
    state_cache: dict[str, dict[str, dict]],
    student_df: float = 5.0,
    huber_c: float = 2.5,
    ew_alpha: float = 0.04,
    tod_alpha: float = 0.05,
    jump_prior: float = 0.04,
    jump_var_mult: float = 9.0,
) -> pd.DataFrame:
    """
    Add robust-KF style causal features at entry timestamps.

    The feature values at entry i are generated using only series values up to i.
    """
    out = _ensure_cols(df)
    if out.empty:
        return out
    if "entry_idx" not in out.columns:
        raise ValueError("add_robust_kf_features requires `entry_idx` column")

    cache: dict[tuple[str, str], dict[str, np.ndarray]] = {}
    for tf, pairs in state_cache.items():
        for pair, st in pairs.items():
            z = np.asarray(st.get("z", []), dtype=float)
            ts = np.asarray(st.get("ts", []), dtype="int64")
            cache[(str(tf), str(pair))] = compute_robust_kf_series_features(
                z=z,
                ts_ns=ts,
                student_df=student_df,
                huber_c=huber_c,
                ew_alpha=ew_alpha,
                tod_alpha=tod_alpha,
                jump_prior=jump_prior,
                jump_var_mult=jump_var_mult,
            )

    for i, row in out.iterrows():
        tf = str(row.get("timeframe", ""))
        pair = str(row.get("pair", ""))
        idx = int(pd.to_numeric(row.get("entry_idx", -1), errors="coerce"))
        feats = cache.get((tf, pair))
        if feats is None or idx < 0:
            continue
        for col in _OUT_COLS:
            arr = feats[col]
            if idx < len(arr):
                out.at[i, col] = float(arr[idx])

    for col in _OUT_COLS:
        out[col] = pd.to_numeric(out[col], errors="coerce").fillna(0.0).astype(float)
    return out
