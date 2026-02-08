#!/usr/bin/env python3
"""
Compare exit rule variants for MOM entries using the same signals.
Rules:
- z_band: current (Z0 loss, Zstop win, else timeout)
- z0_only: exit on Z0 cross, else timeout
- zstop_only: exit on Zstop, else timeout
- time_only: fixed horizon timeout only
- regime_shift: exit when regime features leave training bounds
- edge_decay: exit when predicted edge decays below threshold or by drop-from-peak
- mfe_giveback: exit when PnL gives back X% of MFE

Outputs:
- data/analysis/exit_rule_compare_<bar>.csv
"""

from __future__ import annotations

import argparse
import importlib
import os
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd
from catboost import CatBoostRegressor

RULES = [
    "z_band",
    "z_band_3_0",
    "z_band_2_5",
    "z0_only",
    "zstop_only",
    "time_only",
    "model_exit",
    "regime_shift",
    "edge_decay",
    "mfe_giveback",
]
THRESH_MOM = 1.5
STOP_LEVEL = 3.5
STOP_LEVELS = {
    "z_band": 3.5,
    "z_band_3_0": 3.0,
    "z_band_2_5": 2.5,
}
MIN_GAP = 20
MAX_HOLD = 500
EDGE_FLOOR = 0.0
EDGE_DECAY_DROP = 5.0
MFE_GIVEBACK_PCT = 0.5
MFE_MIN_BPS = 5.0

REGIME_FEATURES = ["vol_ratio", "correlation_500", "trend_strength", "vol_regime"]

BAR_MODULES = {
    "m15": "scripts.build_meta_dataset_v3",
    "m30": "scripts.build_meta_dataset_v3_m30",
    "m45": "scripts.build_meta_dataset_v3_m45",
    "h1": "scripts.build_meta_dataset_v3_h1",
}

DATASETS = {
    "m15": "data/meta_model/events_m15_8yr_v3_dual.csv",
    "m30": "data/meta_model/events_m30_8yr_v3_dual.csv",
    "m45": "data/meta_model/events_m45_8yr_v3_dual.csv",
    "h1": "data/meta_model/events_h1_8yr_v3_dual.csv",
}

MODEL_FEATURES = [
    "z_entry",
    "z_velocity",
    "z_lag1",
    "z_lag2",
    "z_lag3",
    "dz_lag1",
    "dz_lag2",
    "spread_std",
    "beta_stability",
    "signal_beta_lookback",
    "hedge_beta_lookback",
    "beta_mismatch",
    "beta",
    "beta_lag1",
    "beta_lag2",
    "hour",
    "day_of_week",
]

CLF_PARAMS = dict(
    iterations=600,
    depth=6,
    learning_rate=0.05,
    loss_function="Logloss",
    verbose=False,
    random_seed=42,
)
REG_PARAMS = dict(
    iterations=800,
    depth=6,
    learning_rate=0.05,
    loss_function="RMSE",
    verbose=False,
    random_seed=42,
)


def _simulate_rule(
    entry_idx: int,
    direction: int,
    z_scores: np.ndarray,
    prices: np.ndarray,
    rule: str,
    regime_shift: np.ndarray | None = None,
    edge_scores: np.ndarray | None = None,
) -> float:
    entry_price = prices[entry_idx]
    end = min(entry_idx + MAX_HOLD, len(z_scores) - 1)
    edge_peak = None
    mfe = 0.0

    for i in range(entry_idx + 1, end + 1):
        z = z_scores[i]
        curr_price = prices[i]

        if rule == "regime_shift":
            if regime_shift is not None and regime_shift[i]:
                return (curr_price - entry_price) * 10000 if direction == 1 else -(curr_price - entry_price) * 10000
            continue

        if rule == "edge_decay":
            if edge_scores is None:
                continue
            edge = edge_scores[i]
            if edge_peak is None:
                edge_peak = edge
            else:
                edge_peak = max(edge_peak, edge)
            if edge <= EDGE_FLOOR:
                return (curr_price - entry_price) * 10000 if direction == 1 else -(curr_price - entry_price) * 10000
            if edge_peak is not None and edge <= edge_peak - EDGE_DECAY_DROP:
                return (curr_price - entry_price) * 10000 if direction == 1 else -(curr_price - entry_price) * 10000
            continue

        if rule == "mfe_giveback":
            pnl = (curr_price - entry_price) * 10000 if direction == 1 else -(curr_price - entry_price) * 10000
            mfe = max(mfe, pnl)
            if mfe >= MFE_MIN_BPS and pnl <= mfe * (1.0 - MFE_GIVEBACK_PCT):
                return pnl
            continue

        if rule in {"z_band", "z_band_3_0", "z_band_2_5"}:
            stop = STOP_LEVELS[rule]
            if direction == 1:
                if z < 0:
                    return (curr_price - entry_price) * 10000
                if z > stop:
                    return (curr_price - entry_price) * 10000
            else:
                if z > 0:
                    return -(curr_price - entry_price) * 10000
                if z < -stop:
                    return -(curr_price - entry_price) * 10000

        elif rule == "z0_only":
            if direction == 1 and z < 0:
                return (curr_price - entry_price) * 10000
            if direction == -1 and z > 0:
                return -(curr_price - entry_price) * 10000

        elif rule == "zstop_only":
            if direction == 1 and z > STOP_LEVEL:
                return (curr_price - entry_price) * 10000
            if direction == -1 and z < -STOP_LEVEL:
                return -(curr_price - entry_price) * 10000

        elif rule == "time_only":
            continue

    # timeout
    curr_price = prices[end]
    if direction == 1:
        return (curr_price - entry_price) * 10000
    return -(curr_price - entry_price) * 10000


def _max_dd(pnl: List[float]) -> float:
    if not pnl:
        return 0.0
    curve = np.cumsum(pnl)
    peak = np.maximum.accumulate(curve)
    return float((curve - peak).min())


def _metrics(pnl: List[float]) -> dict:
    if not pnl:
        return dict(trades=0, win_rate=0.0, mean_pnl=0.0, total_pnl=0.0, max_dd=0.0)
    arr = np.asarray(pnl)
    return dict(
        trades=len(arr),
        win_rate=float((arr > 0).mean() * 100.0),
        mean_pnl=float(arr.mean()),
        total_pnl=float(arr.sum()),
        max_dd=_max_dd(pnl),
    )


def _rolling_mean(arr: np.ndarray, window: int) -> np.ndarray:
    s = pd.Series(arr)
    out = s.rolling(window, min_periods=1).mean().shift(1).to_numpy()
    return np.nan_to_num(out, nan=arr[0] if len(arr) else 0.0)


def _rolling_std(arr: np.ndarray, window: int) -> np.ndarray:
    s = pd.Series(arr)
    out = s.rolling(window, min_periods=1).std().shift(1).to_numpy()
    return np.nan_to_num(out, nan=0.0)

def _load_regime_bounds(bar: str) -> dict:
    path = DATASETS[bar]
    df = pd.read_csv(path)
    if "timestamp" not in df.columns:
        raise RuntimeError("Dataset missing timestamp for regime bounds.")
    df["timestamp"] = pd.to_datetime(df["timestamp"].astype("int64"), unit="ns", utc=True, errors="coerce")
    df = df.dropna(subset=["timestamp"])
    df["year"] = df["timestamp"].dt.year
    train = df[df["year"] <= 2023].copy()

    bounds = {}
    for feat in REGIME_FEATURES:
        if feat not in train.columns:
            raise RuntimeError(f"Dataset missing regime feature: {feat}")
        vals = train[feat].replace([np.inf, -np.inf], np.nan).dropna()
        if vals.empty:
            raise RuntimeError(f"No valid values for regime feature: {feat}")
        bounds[feat] = (float(vals.min()), float(vals.max()))
    return bounds


def _compute_bar_features(
    y: np.ndarray,
    x: np.ndarray,
    betas: np.ndarray,
    errors: np.ndarray,
    ret_betas: np.ndarray,
    z_scores: np.ndarray,
    ts: np.ndarray,
) -> pd.DataFrame:
    n = len(y)
    z_lag1 = np.roll(z_scores, 1)
    z_lag2 = np.roll(z_scores, 2)
    z_lag3 = np.roll(z_scores, 3)
    z_lag1[:1] = 0.0
    z_lag2[:2] = 0.0
    z_lag3[:3] = 0.0
    dz_lag1 = z_lag1 - z_lag2
    dz_lag2 = z_lag2 - z_lag3

    beta_lag1 = np.roll(betas, 1)
    beta_lag2 = np.roll(betas, 2)
    beta_lag1[:1] = betas[:1]
    beta_lag2[:2] = betas[:2]

    spread_std = _rolling_std(errors, 500) * 10000.0
    beta_stability = _rolling_std(betas, 100)
    sig_beta_lb = _rolling_mean(betas, 500)
    hedge_beta_lb = _rolling_mean(ret_betas, 500)
    beta_mismatch = np.where(np.abs(sig_beta_lb) > 0.01, hedge_beta_lb / sig_beta_lb, 0.0)
    beta_mismatch = np.clip(beta_mismatch, -10.0, 10.0)

    z_velocity = np.zeros(n, dtype=float)
    for i in range(500, n):
        prev_i = max(500, i - 5)
        z_velocity[i] = z_scores[i] - z_scores[prev_i]

    dy = np.diff(y, prepend=y[0])
    dx = np.diff(x, prepend=x[0])

    vol_y = pd.Series(dy).rolling(500, min_periods=2).std().shift(1)
    vol_x = pd.Series(dx).rolling(500, min_periods=2).std().shift(1)
    vol_ratio = np.where(vol_x.to_numpy() > 0, vol_y.to_numpy() / vol_x.to_numpy(), 1.0)
    vol_ratio = np.nan_to_num(vol_ratio, nan=1.0, posinf=1.0, neginf=1.0)

    correlation_500 = pd.Series(x).rolling(500, min_periods=500).corr(pd.Series(y)).shift(1)
    correlation_500 = correlation_500.fillna(0.0).to_numpy()

    spread = y - betas * x
    window = 100
    trend_strength = np.zeros(n, dtype=float)
    if n >= window:
        t = np.arange(window, dtype=float)
        mean_t = (window - 1) / 2.0
        var_t = (window**2 - 1) / 12.0
        sum_s = np.convolve(spread, np.ones(window), mode="valid")
        sum_ts = np.convolve(spread, t[::-1], mode="valid")
        sum_sq = np.convolve(spread**2, np.ones(window), mode="valid")
        mean_s = sum_s / window
        var_s = np.maximum(sum_sq / window - mean_s**2, 0.0)
        std_s = np.sqrt(var_s)
        slope = (sum_ts - mean_t * sum_s) / var_t
        strength = slope / (std_s + 1e-8)
        trend_strength[window - 1 :] = strength
    trend_strength = np.roll(trend_strength, 1)
    trend_strength[0] = 0.0

    short_vol = pd.Series(dy).rolling(50, min_periods=2).std().shift(1).to_numpy()
    long_vol = pd.Series(dy).rolling(500, min_periods=2).std().shift(1).to_numpy()
    vol_regime = np.where(long_vol > 0, short_vol / long_vol, 1.0)
    vol_regime = np.nan_to_num(vol_regime, nan=1.0, posinf=1.0, neginf=1.0)

    ts_series = pd.Series(pd.to_datetime(ts, errors="coerce", unit="ns", utc=True))
    hour = ts_series.dt.hour.to_numpy()
    day_of_week = ts_series.dt.dayofweek.to_numpy()

    features = pd.DataFrame(
        {
            "z_entry": z_scores,
            "z_velocity": z_velocity,
            "z_lag1": z_lag1,
            "z_lag2": z_lag2,
            "z_lag3": z_lag3,
            "dz_lag1": dz_lag1,
            "dz_lag2": dz_lag2,
            "spread_std": spread_std,
            "beta_stability": beta_stability,
            "signal_beta_lookback": sig_beta_lb,
            "hedge_beta_lookback": hedge_beta_lb,
            "beta_mismatch": beta_mismatch,
            "beta": betas,
            "beta_lag1": beta_lag1,
            "beta_lag2": beta_lag2,
            "hour": hour,
            "day_of_week": day_of_week,
            "vol_ratio": vol_ratio,
            "correlation_500": correlation_500,
            "trend_strength": trend_strength,
            "vol_regime": vol_regime,
        }
    )
    return features


def _fit_exit_model(bar: str) -> tuple[object, List[str]]:
    path = DATASETS[bar]
    df = pd.read_csv(path)
    df = df[df["strategy_type"] == "MOM"].copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"].astype("int64"), unit="ns", utc=True, errors="coerce")
    df = df.dropna(subset=["timestamp"])
    df["year"] = df["timestamp"].dt.year
    train = df[df["year"] <= 2023].copy()
    test = df[df["year"] >= 2024].copy()

    use_features = [f for f in MODEL_FEATURES if f in train.columns]
    if not use_features:
        raise RuntimeError("No model features available for model_exit.")

    cat_features = []
    model = CatBoostRegressor(**REG_PARAMS)
    model.fit(
        train[use_features],
        train["pnl_bps"],
        eval_set=(test[use_features], test["pnl_bps"]),
        verbose=False,
    )
    return model, use_features


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bar", choices=list(BAR_MODULES.keys()), default="m15")
    args = parser.parse_args()

    mod_path = BAR_MODULES[args.bar]
    if mod_path.startswith("scripts."):
        mod_path = mod_path.replace("scripts.", "", 1)
    mod = importlib.import_module(mod_path)
    pairs = getattr(mod, "PAIRS")

    trades: Dict[str, List[Tuple[int, float]]] = {rule: [] for rule in RULES}
    exit_model = None
    exit_features: List[str] = []
    regime_bounds = None
    if "model_exit" in RULES:
        exit_model, exit_features = _fit_exit_model(args.bar)
    if "regime_shift" in RULES:
        regime_bounds = _load_regime_bounds(args.bar)

    for name, fx, fy, cx, cy, _, _ in pairs:
        df = mod.load_pair_data(fx, fy, cx, cy)
        if df is None:
            continue

        y = np.log(df["Y"].to_numpy())
        x = np.log(df["X"].to_numpy())
        ts = df["timestamp"].to_numpy()

        betas, errors, ret_betas = mod.compute_kalman_states(y, x)
        z_scores = mod.compute_z_scores(errors)

        features = None
        pred_pnl_by_bar = None
        regime_shift_flags = None

        need_features = any(rule in RULES for rule in ["model_exit", "edge_decay", "regime_shift"])
        if need_features:
            features = _compute_bar_features(y, x, betas, errors, ret_betas, z_scores, ts)

        if exit_model is not None and features is not None:
            pred_pnl_by_bar = exit_model.predict(features[exit_features])

        if regime_bounds is not None and features is not None:
            flags = np.zeros(len(features), dtype=bool)
            for feat, (mn, mx) in regime_bounds.items():
                vals = features[feat].to_numpy()
                flags |= (vals < mn) | (vals > mx)
            regime_shift_flags = flags

        last_entry = 0
        for i in range(500, len(y) - 500):
            if i - last_entry < MIN_GAP:
                continue
            z = z_scores[i]
            if abs(z) < THRESH_MOM:
                continue

            direction = 1 if z > 0 else -1

            # active leg price
            beta = betas[i]
            if beta < 0.98:
                prices = y
            elif beta > 1.02:
                prices = x
            else:
                continue
            entry_price = prices[i]

            for rule in RULES:
                if rule == "model_exit":
                    end = min(i + MAX_HOLD, len(z_scores) - 1)
                    pnl = None
                    for j in range(i + 1, end + 1):
                        if pred_pnl_by_bar is not None and pred_pnl_by_bar[j] <= 0:
                            curr_price = prices[j]
                            pnl = (curr_price - entry_price) * 10000 if direction == 1 else -(curr_price - entry_price) * 10000
                            break
                    if pnl is None:
                        curr_price = prices[end]
                        pnl = (curr_price - entry_price) * 10000 if direction == 1 else -(curr_price - entry_price) * 10000
                else:
                    pnl = _simulate_rule(
                        i,
                        direction,
                        z_scores,
                        prices,
                        rule,
                        regime_shift=regime_shift_flags,
                        edge_scores=pred_pnl_by_bar,
                    )
                trades[rule].append((ts[i], pnl))

            last_entry = i

    rows = []
    for rule, entries in trades.items():
        entries = sorted(entries, key=lambda t: t[0])
        df_rule = pd.DataFrame(entries, columns=["timestamp", "pnl_bps"])
        ts = pd.to_datetime(df_rule["timestamp"].astype("int64"), unit="ns", utc=True, errors="coerce")
        df_rule["year"] = ts.dt.year
        df_rule["month"] = ts.dt.strftime("%Y-%m")

        # overall
        m = _metrics(df_rule["pnl_bps"].tolist())
        rows.append({"bar": args.bar, "rule": rule, "period_type": "all", "period": "all", **m})

        # yearly
        for year, grp in df_rule.groupby("year"):
            m = _metrics(grp["pnl_bps"].tolist())
            rows.append({"bar": args.bar, "rule": rule, "period_type": "year", "period": str(year), **m})

        # monthly
        for month, grp in df_rule.groupby("month"):
            m = _metrics(grp["pnl_bps"].tolist())
            rows.append({"bar": args.bar, "rule": rule, "period_type": "month", "period": month, **m})

    out = pd.DataFrame(rows)
    os.makedirs("data/analysis", exist_ok=True)
    out_path = f"data/analysis/exit_rule_compare_{args.bar}_by_period.csv"
    out.to_csv(out_path, index=False)
    print(f"Saved {out_path}")


if __name__ == "__main__":
    main()
