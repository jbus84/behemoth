#!/usr/bin/env python3
"""
Meta Model Dataset Generator v3 (M5, 1-step targets)
DUAL STRATEGY: Generate BOTH Momentum AND Reversion trades for each signal.
Adds forward targets for 1-bar and 3-bar PnL on the active leg.

Entry/hold bands:
- MOM when |Z| in (2.0, 3.5]
- REV when |Z| in (0.5, 2.0)

Exit logic:
- Exit when leaving band (|Z| <= 2.0 or |Z| >= 3.5 for MOM; |Z| <= 0.5 or |Z| >= 2.0 for REV)
"""

import os
import sys
from collections import defaultdict
from datetime import datetime

import numpy as np
import pandas as pd
import polars as pl

sys.path.append(os.path.join(os.getcwd(), "scripts"))
from kalman_filter import KalmanFilterReg

DATA_DIR = "data/global_5m"
OUTPUT_DIR = "data/meta_model"
os.makedirs(OUTPUT_DIR, exist_ok=True)

# === PAIR UNIVERSE ===
PAIRS = [
    # FX & Commodities
    ("EUR/GBP", "EURUSD_5m.parquet", "GBPUSD_5m.parquet", "close_EURUSD", "close_GBPUSD", 1.6, 1.0),
    ("Gold/Oil", "BCOUSD_5m.parquet", "XAUUSD_5m.parquet", "close_BCOUSD", "close_XAUUSD", 3.0, 3.0),
    ("Oil/Silver", "BCOUSD_5m.parquet", "XAGUSD_5m.parquet", "close_BCOUSD", "close_XAGUSD", 3.0, 3.0),
    ("AUD/NZD", "NZDUSD_5m.parquet", "AUDUSD_5m.parquet", "close_NZDUSD", "close_AUDUSD", 2.0, 2.0),
    ("CAC/NZD", "NZDUSD_5m.parquet", "FRXEUR_5m.parquet", "close_NZDUSD", "close_FRXEUR", 3.0, 3.0),
    ("Gold/Silver", "XAUUSD_5m.parquet", "XAGUSD_5m.parquet", "close_XAUUSD", "close_XAGUSD", 3.0, 3.0),
    # Global Equities
    ("SPX/DAX", "SPXUSD_5m.parquet", "GRXEUR_5m.parquet", "close_SPXUSD", "close_GRXEUR", 3.0, 2.0),
    ("SPX/CAC", "SPXUSD_5m.parquet", "FRXEUR_5m.parquet", "close_SPXUSD", "close_FRXEUR", 3.0, 2.0),
    ("SPX/FTSE", "SPXUSD_5m.parquet", "UKXGBP_5m.parquet", "close_SPXUSD", "close_UKXGBP", 3.0, 2.0),
    ("SPX/Nikkei", "SPXUSD_5m.parquet", "JPXJPY_5m.parquet", "close_SPXUSD", "close_JPXJPY", 3.0, 2.0),
    ("SPX/HK", "SPXUSD_5m.parquet", "HKXHKD_5m.parquet", "close_SPXUSD", "close_HKXHKD", 4.0, 2.0),
    ("SPX/Dow", "SPXUSD_5m.parquet", "UDXUSD_5m.parquet", "close_SPXUSD", "close_UDXUSD", 2.0, 2.0),
    ("SPX/Nas", "SPXUSD_5m.parquet", "NSXUSD_5m.parquet", "close_SPXUSD", "close_NSXUSD", 2.0, 2.0),
    # Extended FX
    ("AUD/CAD", "AUDUSD_5m.parquet", "USDCAD_5m.parquet", "close_AUDUSD", "close_USDCAD", 2.0, 2.0),
    ("EUR/CHF", "EURUSD_5m.parquet", "USDCHF_5m.parquet", "close_EURUSD", "close_USDCHF", 2.0, 2.0),
    ("EUR/JPY", "EURUSD_5m.parquet", "USDJPY_5m.parquet", "close_EURUSD", "close_USDJPY", 2.0, 1.0),
    ("GBP/JPY", "GBPUSD_5m.parquet", "USDJPY_5m.parquet", "close_GBPUSD", "close_USDJPY", 2.0, 1.0),
    ("CHF/JPY", "USDCHF_5m.parquet", "USDJPY_5m.parquet", "close_USDCHF", "close_USDJPY", 2.0, 1.0),
    ("EUR/AUD", "EURUSD_5m.parquet", "AUDUSD_5m.parquet", "close_EURUSD", "close_AUDUSD", 2.0, 2.0),
    ("GBP/AUD", "GBPUSD_5m.parquet", "AUDUSD_5m.parquet", "close_GBPUSD", "close_AUDUSD", 2.0, 2.0),
    ("GBP/CAD", "GBPUSD_5m.parquet", "USDCAD_5m.parquet", "close_GBPUSD", "close_USDCAD", 2.0, 2.0),
    ("NZD/CAD", "NZDUSD_5m.parquet", "USDCAD_5m.parquet", "close_NZDUSD", "close_USDCAD", 2.0, 2.0),
]

ENTRY_MOM_Z = 2.0
ENTRY_REV_Z = 2.0
EXIT_MOM_Z = 3.5
EXIT_REV_Z = 0.5
MIN_GAP = 20
MIN_SIGNAL = 1e-6
MAX_HOLD = 500


def load_pair_data(fx, fy, cx, cy):
    try:
        p_x = os.path.join(DATA_DIR, fx)
        p_y = os.path.join(DATA_DIR, fy)
        df_x = pl.read_parquet(p_x).rename({cx: "X"})
        df_y = pl.read_parquet(p_y).rename({cy: "Y"})
        df = df_x.join(df_y, on="timestamp", how="inner").sort("timestamp")
        df = df.filter(pl.col("timestamp").dt.year().is_in(list(range(2018, 2026))))
        return df
    except Exception as e:
        print(f"Error loading {fx}/{fy}: {e}")
        return None


def compute_kalman_states(y, x):
    # Level Kalman (signal beta)
    kf = KalmanFilterReg(Q=1e-5, R=1e-3)
    betas = []
    errors = []

    for i in range(len(y)):
        if i < 10:
            mu_y, mu_x = y[i], x[i]
        else:
            mu_y = np.mean(y[max(0, i - 500) : i])
            mu_x = np.mean(x[max(0, i - 500) : i])
        b, _ = kf.update(x[i] - mu_x, y[i] - mu_y)
        betas.append(b)
        errors.append((y[i] - mu_y) - b * (x[i] - mu_x))

    # Return Kalman (hedge beta proxy)
    kf_ret = KalmanFilterReg(Q=1e-5, R=1e-3)
    ret_betas = np.zeros(len(y))
    if len(y) > 1:
        for i in range(1, len(y)):
            ry = y[i] - y[i - 1]
            rx = x[i] - x[i - 1]
            b_ret, _ = kf_ret.update(rx, ry)
            ret_betas[i] = b_ret
        ret_betas[0] = ret_betas[1]

    return np.array(betas), np.array(errors), ret_betas


def compute_z_scores(errors, window=500):
    z_scores = np.zeros(len(errors))
    for i in range(window, len(errors)):
        window_data = errors[i - window : i]
        mu, std = np.mean(window_data), np.std(window_data)
        if std > 1e-6:
            z_scores[i] = (errors[i] - mu) / std
    return z_scores


def compute_features_at_entry(i, y, x, betas, errors, ret_betas, z_scores, ts):
    features = {}

    # Signal Quality
    features["z_entry"] = round(z_scores[i], 2)
    prev_i = max(500, i - 5)
    features["z_velocity"] = round(z_scores[i] - z_scores[prev_i], 2)
    features["spread_std"] = round(np.std(errors[max(0, i - 500) : i]) * 10000, 2)
    features["beta_stability"] = round(np.std(betas[max(0, i - 100) : i]), 4)
    sig_beta_lb = np.mean(betas[max(0, i - 500) : i]) if i > 0 else betas[0]
    hedge_beta_lb = np.mean(ret_betas[max(0, i - 500) : i]) if i > 0 else ret_betas[0]
    features["signal_beta_lookback"] = round(sig_beta_lb, 4)
    features["hedge_beta_lookback"] = round(hedge_beta_lb, 4)
    if abs(sig_beta_lb) > 0.01:
        mismatch = hedge_beta_lb / sig_beta_lb
    else:
        mismatch = 0.0
    mismatch = float(np.clip(mismatch, -10.0, 10.0))
    features["beta_mismatch"] = round(mismatch, 3)

    # Explicit bar-by-bar lags (causal)
    features["z_lag1"] = round(z_scores[i - 1], 3) if i >= 1 else 0.0
    features["z_lag2"] = round(z_scores[i - 2], 3) if i >= 2 else 0.0
    features["z_lag3"] = round(z_scores[i - 3], 3) if i >= 3 else 0.0
    features["dz_lag1"] = round(z_scores[i - 1] - z_scores[i - 2], 3) if i >= 2 else 0.0
    features["dz_lag2"] = round(z_scores[i - 2] - z_scores[i - 3], 3) if i >= 3 else 0.0
    features["beta_lag1"] = round(betas[i - 1], 4) if i >= 1 else round(betas[i], 4)
    features["beta_lag2"] = round(betas[i - 2], 4) if i >= 2 else round(betas[i], 4)

    # Market Regime
    features["beta"] = round(betas[i], 4)
    start = max(0, i - 500)
    vol_y = np.std(np.diff(y[start:i]))
    vol_x = np.std(np.diff(x[start:i]))
    features["vol_ratio"] = round(vol_y / vol_x if vol_x > 0 else 1.0, 3)

    if i >= 500:
        corr = np.corrcoef(x[i - 500 : i], y[i - 500 : i])[0, 1]
        features["correlation_500"] = round(corr, 3)
    else:
        features["correlation_500"] = 0.0

    if i >= 100:
        spread = y[i - 100 : i] - betas[i] * x[i - 100 : i]
        slope = np.polyfit(np.arange(100), spread, 1)[0]
        features["trend_strength"] = round(slope / (np.std(spread) + 1e-8), 3)
    else:
        features["trend_strength"] = 0.0

    # Time Context
    entry_ts = ts[i]
    if hasattr(entry_ts, "hour"):
        features["hour"] = entry_ts.hour
        features["day_of_week"] = entry_ts.weekday()
    else:
        dt = np.datetime64(entry_ts, "ns").astype("datetime64[s]").astype(datetime)
        features["hour"] = dt.hour
        features["day_of_week"] = dt.weekday()

    # Technical Context
    lookback = min(i, 16)  # 16 * 5m = 80m
    features["ret_X_16b"] = round((x[i] - x[i - lookback]) * 10000, 2)
    features["ret_Y_16b"] = round((y[i] - y[i - lookback]) * 10000, 2)
    lookback_1h = min(i, 12)  # 12 * 5m = 1h
    features["ret_X_1h"] = round((x[i] - x[i - lookback_1h]) * 10000, 2)
    features["ret_Y_1h"] = round((y[i] - y[i - lookback_1h]) * 10000, 2)

    if i >= 100:
        atr_y = np.mean([max(y[j : j + 4]) - min(y[j : j + 4]) for j in range(i - 100, i, 4)])
        atr_x = np.mean([max(x[j : j + 4]) - min(x[j : j + 4]) for j in range(i - 100, i, 4)])
        features["atr_ratio"] = round(atr_y / atr_x if atr_x > 0 else 1.0, 3)
    else:
        features["atr_ratio"] = 1.0

    # Barrier Context Features (historical, no leakage)
    if i >= 50:
        recent_returns = np.diff(y[i - 50 : i])
        features["entry_atr"] = round(np.std(recent_returns) * 10000, 2)  # in bps
    else:
        features["entry_atr"] = 0.0

    if i >= 500:
        short_vol = np.std(np.diff(y[i - 50 : i]))
        long_vol = np.std(np.diff(y[i - 500 : i]))
        features["vol_regime"] = round(short_vol / long_vol if long_vol > 0 else 1.0, 2)
    else:
        features["vol_regime"] = 1.0

    return features


def precompute_feature_arrays(y, x, betas, errors, ret_betas, z_scores, ts):
    n = len(y)
    arr = {}

    z_lag1 = np.roll(z_scores, 1)
    z_lag2 = np.roll(z_scores, 2)
    z_lag3 = np.roll(z_scores, 3)
    z_lag1[:1] = 0.0
    z_lag2[:2] = 0.0
    z_lag3[:3] = 0.0

    arr["z_entry"] = z_scores
    arr["z_lag1"] = z_lag1
    arr["z_lag2"] = z_lag2
    arr["z_lag3"] = z_lag3
    arr["dz_lag1"] = z_lag1 - z_lag2
    arr["dz_lag2"] = z_lag2 - z_lag3

    z_vel = z_scores - np.roll(z_scores, 5)
    z_vel[:5] = 0.0
    arr["z_velocity"] = z_vel

    beta_lag1 = np.roll(betas, 1)
    beta_lag2 = np.roll(betas, 2)
    beta_lag1[:1] = betas[:1]
    beta_lag2[:2] = betas[:2]
    arr["beta"] = betas
    arr["beta_lag1"] = beta_lag1
    arr["beta_lag2"] = beta_lag2

    spread_std = pd.Series(errors).rolling(500, min_periods=2).std().shift(1).fillna(0.0).to_numpy()
    arr["spread_std"] = spread_std * 10000.0

    beta_stability = pd.Series(betas).rolling(100, min_periods=2).std().shift(1).fillna(0.0).to_numpy()
    arr["beta_stability"] = beta_stability

    sig_beta_lb = pd.Series(betas).rolling(500, min_periods=2).mean().shift(1).fillna(betas[0]).to_numpy()
    hedge_beta_lb = pd.Series(ret_betas).rolling(500, min_periods=2).mean().shift(1).fillna(ret_betas[0]).to_numpy()
    arr["signal_beta_lookback"] = sig_beta_lb
    arr["hedge_beta_lookback"] = hedge_beta_lb

    mismatch = np.where(np.abs(sig_beta_lb) > 0.01, hedge_beta_lb / sig_beta_lb, 0.0)
    arr["beta_mismatch"] = np.clip(mismatch, -10.0, 10.0)

    dy = np.diff(y, prepend=y[0])
    dx = np.diff(x, prepend=x[0])
    vol_y = pd.Series(dy).rolling(500, min_periods=2).std().shift(1)
    vol_x = pd.Series(dx).rolling(500, min_periods=2).std().shift(1)
    vol_ratio = np.where(vol_x.to_numpy() > 0, vol_y.to_numpy() / vol_x.to_numpy(), 1.0)
    arr["vol_ratio"] = np.nan_to_num(vol_ratio, nan=1.0, posinf=1.0, neginf=1.0)

    corr_500 = pd.Series(x).rolling(500, min_periods=500).corr(pd.Series(y)).shift(1)
    arr["correlation_500"] = corr_500.fillna(0.0).to_numpy()

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
    arr["trend_strength"] = trend_strength

    ts_series = pd.to_datetime(ts, unit="ns", utc=True, errors="coerce")
    arr["hour"] = ts_series.hour.to_numpy()
    arr["day_of_week"] = ts_series.dayofweek.to_numpy()
    year_arr = ts_series.year.to_numpy()

    ret_x_16 = (x - np.roll(x, 16)) * 10000.0
    ret_y_16 = (y - np.roll(y, 16)) * 10000.0
    ret_x_16[:16] = (x[:16] - x[0]) * 10000.0
    ret_y_16[:16] = (y[:16] - y[0]) * 10000.0
    arr["ret_X_16b"] = ret_x_16
    arr["ret_Y_16b"] = ret_y_16

    ret_x_1h = (x - np.roll(x, 12)) * 10000.0
    ret_y_1h = (y - np.roll(y, 12)) * 10000.0
    ret_x_1h[:12] = (x[:12] - x[0]) * 10000.0
    ret_y_1h[:12] = (y[:12] - y[0]) * 10000.0
    arr["ret_X_1h"] = ret_x_1h
    arr["ret_Y_1h"] = ret_y_1h

    range4_y = pd.Series(y).rolling(4, min_periods=4).max() - pd.Series(y).rolling(4, min_periods=4).min()
    range4_x = pd.Series(x).rolling(4, min_periods=4).max() - pd.Series(x).rolling(4, min_periods=4).min()
    atr_y = range4_y.rolling(100, min_periods=4).mean().shift(1).fillna(0.0).to_numpy()
    atr_x = range4_x.rolling(100, min_periods=4).mean().shift(1).fillna(0.0).to_numpy()
    atr_ratio = np.where(atr_x > 0, atr_y / atr_x, 1.0)
    arr["atr_ratio"] = np.nan_to_num(atr_ratio, nan=1.0, posinf=1.0, neginf=1.0)

    entry_atr = pd.Series(dy).rolling(50, min_periods=2).std().shift(1).fillna(0.0).to_numpy() * 10000.0
    arr["entry_atr"] = entry_atr

    short_vol = pd.Series(dy).rolling(50, min_periods=2).std().shift(1).to_numpy()
    long_vol = pd.Series(dy).rolling(500, min_periods=2).std().shift(1).to_numpy()
    vol_regime = np.where(long_vol > 0, short_vol / long_vol, 1.0)
    arr["vol_regime"] = np.nan_to_num(vol_regime, nan=1.0, posinf=1.0, neginf=1.0)

    return arr, year_arr


def _target_pnl(prices: np.ndarray, idx: int, horizon: int, direction: int) -> float | None:
    if idx + horizon >= len(prices):
        return None
    delta = prices[idx + horizon] - prices[idx]
    pnl = delta * 10000
    return pnl if direction == 1 else -pnl


def _in_mom_band(z: float) -> bool:
    return abs(z) > ENTRY_MOM_Z and abs(z) <= EXIT_MOM_Z


def _in_rev_band(z: float) -> bool:
    return abs(z) > EXIT_REV_Z and abs(z) < ENTRY_REV_Z


def main():
    print("Phase 1: Loading data and computing Kalman states...")
    pair_states = {}

    for name, fx, fy, cx, cy, cost_y, cost_x in PAIRS:
        df = load_pair_data(fx, fy, cx, cy)
        if df is None:
            continue

        y = np.log(df["Y"].to_numpy())
        x = np.log(df["X"].to_numpy())
        ts = df["timestamp"].to_numpy()

        betas, errors, ret_betas = compute_kalman_states(y, x)
        z_scores = compute_z_scores(errors)

        pair_states[name] = {
            "y": y,
            "x": x,
            "ts": ts,
            "betas": betas,
            "errors": errors,
            "ret_betas": ret_betas,
            "z_scores": z_scores,
            "cost_y": cost_y,
            "cost_x": cost_x,
        }
        print(f"  {name}: {len(y)} bars")

    print("\nPhase 2: Generating stateful per-bar samples...")
    all_events = []
    pair_trade_history = defaultdict(lambda: {"MOM": [], "REV": []})

    for name, state in pair_states.items():
        print(f"  Processing {name}...")

        y, x, ts = state["y"], state["x"], state["ts"]
        betas, errors, ret_betas, z_scores = state["betas"], state["errors"], state["ret_betas"], state["z_scores"]
        cost_y, cost_x = state["cost_y"], state["cost_x"]
        feature_arr, year_arr = precompute_feature_arrays(y, x, betas, errors, ret_betas, z_scores, ts)

        mom_open = False
        rev_open = False
        mom_state = {}
        rev_state = {}
        last_exit_mom = -MIN_GAP
        last_exit_rev = -MIN_GAP

        for i in range(500, len(y) - 3):
            z = z_scores[i]

            beta = betas[i]

            if beta < 0.98:
                active_asset = "Y"
                cost = cost_y
                prices = y
            elif beta > 1.02:
                active_asset = "X"
                cost = cost_x
                prices = x
            else:
                # If we are in a trade and the active leg becomes ambiguous, close it.
                if mom_open:
                    mom_open = False
                    last_exit_mom = i
                if rev_open:
                    rev_open = False
                    last_exit_rev = i
                continue

            # MOM trade management
            if mom_open:
                if not _in_mom_band(z):
                    # exit trade when leaving band
                    mom_open = False
                    last_exit_mom = i
                    # record trade outcome for rolling stats
                    exit_pnl = (prices[i] - mom_state["entry_price"]) * 10000
                    exit_pnl = exit_pnl if mom_state["direction"] == 1 else -exit_pnl
                    pair_trade_history[name]["MOM"].append(exit_pnl)
                else:
                    features = {k: float(feature_arr[k][i]) for k in feature_arr}
                    features["num_active_signals"] = 0
                    pnl_unreal = (prices[i] - mom_state["entry_price"]) * 10000
                    pnl_unreal = pnl_unreal if mom_state["direction"] == 1 else -pnl_unreal
                    row = {
                        "trade_id": mom_state["trade_id"],
                        "trade_entry_ts": mom_state["entry_ts"],
                        "trade_entry_idx": mom_state["entry_idx"],
                        "bar_offset": i - mom_state["entry_idx"],
                        "pair": name,
                        "timestamp": ts[i],
                        "year": int(year_arr[i]),
                        "strategy_type": "MOM",
                        "active_leg": mom_state["active_leg"],
                        "side": "LONG" if mom_state["direction"] == 1 else "SHORT",
                        "pnl_bps": round(pnl_unreal, 2),
                        "rolling_win_rate_10": mom_state["rolling_wr"],
                        "rolling_avg_pnl_10": mom_state["rolling_pnl"],
                        "cost_bps": cost,
                        "target_pnl_1b": _target_pnl(prices, i, 1, mom_state["direction"]),
                        "target_pnl_3b": _target_pnl(prices, i, 3, mom_state["direction"]),
                        **features,
                    }
                    all_events.append(row)

            # REV trade management
            if rev_open:
                if not _in_rev_band(z):
                    rev_open = False
                    last_exit_rev = i
                    exit_pnl = (prices[i] - rev_state["entry_price"]) * 10000
                    exit_pnl = exit_pnl if rev_state["direction"] == 1 else -exit_pnl
                    pair_trade_history[name]["REV"].append(exit_pnl)
                else:
                    features = {k: float(feature_arr[k][i]) for k in feature_arr}
                    features["num_active_signals"] = 0
                    pnl_unreal = (prices[i] - rev_state["entry_price"]) * 10000
                    pnl_unreal = pnl_unreal if rev_state["direction"] == 1 else -pnl_unreal
                    row = {
                        "trade_id": rev_state["trade_id"],
                        "trade_entry_ts": rev_state["entry_ts"],
                        "trade_entry_idx": rev_state["entry_idx"],
                        "bar_offset": i - rev_state["entry_idx"],
                        "pair": name,
                        "timestamp": ts[i],
                        "year": int(year_arr[i]),
                        "strategy_type": "REV",
                        "active_leg": rev_state["active_leg"],
                        "side": "LONG" if rev_state["direction"] == 1 else "SHORT",
                        "pnl_bps": round(pnl_unreal, 2),
                        "rolling_win_rate_10": rev_state["rolling_wr"],
                        "rolling_avg_pnl_10": rev_state["rolling_pnl"],
                        "cost_bps": cost,
                        "target_pnl_1b": _target_pnl(prices, i, 1, rev_state["direction"]),
                        "target_pnl_3b": _target_pnl(prices, i, 3, rev_state["direction"]),
                        **features,
                    }
                    all_events.append(row)

            # Open new MOM trade
            if not mom_open and _in_mom_band(z) and (i - last_exit_mom >= MIN_GAP):
                mom_dir = 1 if z > 0 else -1
                history = pair_trade_history[name]["MOM"]
                if len(history) >= 10:
                    rolling_wr = sum(1 for p in history[-10:] if p > 0) / 10
                    rolling_pnl = float(np.mean(history[-10:]))
                else:
                    rolling_wr = 0.5
                    rolling_pnl = 0.0
                mom_state = {
                    "trade_id": f"{name}:MOM:{i}",
                    "entry_idx": i,
                    "entry_ts": ts[i],
                    "entry_price": prices[i],
                    "direction": mom_dir,
                    "active_leg": active_asset,
                    "rolling_wr": round(rolling_wr, 2),
                    "rolling_pnl": round(rolling_pnl, 2),
                }
                mom_open = True
                features = {k: float(feature_arr[k][i]) for k in feature_arr}
                features["num_active_signals"] = 0
                row = {
                    "trade_id": mom_state["trade_id"],
                    "trade_entry_ts": mom_state["entry_ts"],
                    "trade_entry_idx": mom_state["entry_idx"],
                    "bar_offset": 0,
                    "pair": name,
                    "timestamp": ts[i],
                    "year": int(year_arr[i]),
                    "strategy_type": "MOM",
                    "active_leg": mom_state["active_leg"],
                    "side": "LONG" if mom_state["direction"] == 1 else "SHORT",
                    "pnl_bps": 0.0,
                    "rolling_win_rate_10": mom_state["rolling_wr"],
                    "rolling_avg_pnl_10": mom_state["rolling_pnl"],
                    "cost_bps": cost,
                    "target_pnl_1b": _target_pnl(prices, i, 1, mom_state["direction"]),
                    "target_pnl_3b": _target_pnl(prices, i, 3, mom_state["direction"]),
                    **features,
                }
                all_events.append(row)

            # Open new REV trade
            if not rev_open and _in_rev_band(z) and (i - last_exit_rev >= MIN_GAP):
                rev_dir = -1 if z > 0 else 1
                history = pair_trade_history[name]["REV"]
                if len(history) >= 10:
                    rolling_wr = sum(1 for p in history[-10:] if p > 0) / 10
                    rolling_pnl = float(np.mean(history[-10:]))
                else:
                    rolling_wr = 0.5
                    rolling_pnl = 0.0
                rev_state = {
                    "trade_id": f"{name}:REV:{i}",
                    "entry_idx": i,
                    "entry_ts": ts[i],
                    "entry_price": prices[i],
                    "direction": rev_dir,
                    "active_leg": active_asset,
                    "rolling_wr": round(rolling_wr, 2),
                    "rolling_pnl": round(rolling_pnl, 2),
                }
                rev_open = True
                features = {k: float(feature_arr[k][i]) for k in feature_arr}
                features["num_active_signals"] = 0
                row = {
                    "trade_id": rev_state["trade_id"],
                    "trade_entry_ts": rev_state["entry_ts"],
                    "trade_entry_idx": rev_state["entry_idx"],
                    "bar_offset": 0,
                    "pair": name,
                    "timestamp": ts[i],
                    "year": int(year_arr[i]),
                    "strategy_type": "REV",
                    "active_leg": rev_state["active_leg"],
                    "side": "LONG" if rev_state["direction"] == 1 else "SHORT",
                    "pnl_bps": 0.0,
                    "rolling_win_rate_10": rev_state["rolling_wr"],
                    "rolling_avg_pnl_10": rev_state["rolling_pnl"],
                    "cost_bps": cost,
                    "target_pnl_1b": _target_pnl(prices, i, 1, rev_state["direction"]),
                    "target_pnl_3b": _target_pnl(prices, i, 3, rev_state["direction"]),
                    **features,
                }
                all_events.append(row)

    df_out = pl.DataFrame(all_events)
    dual_path = os.path.join(OUTPUT_DIR, "events_m5_8yr_v3_1step_dual.csv")
    df_out.write_csv(dual_path)

    df_mom = df_out.filter(pl.col("strategy_type") == "MOM")
    df_rev = df_out.filter(pl.col("strategy_type") == "REV")
    mom_path = os.path.join(OUTPUT_DIR, "events_m5_8yr_v3_1step_mom.csv")
    rev_path = os.path.join(OUTPUT_DIR, "events_m5_8yr_v3_1step_rev.csv")
    df_mom.write_csv(mom_path)
    df_rev.write_csv(rev_path)

    print("\nDataset saved:")
    print(f"- {dual_path}")
    print(f"- {mom_path}")
    print(f"- {rev_path}")

    print("\nSummary:")
    mom_trades = {e["trade_id"] for e in all_events if e["strategy_type"] == "MOM"}
    rev_trades = {e["trade_id"] for e in all_events if e["strategy_type"] == "REV"}
    print(f"  MOM trades: {len(mom_trades)}")
    print(f"  REV trades: {len(rev_trades)}")


if __name__ == "__main__":
    main()
