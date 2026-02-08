#!/usr/bin/env python3
"""
Tick-level trailing stop simulation for event-level pred>20 trades.
Uses H1 Z-exit logic for baseline exit time, then applies trailing stop on tick data.

Outputs summary for holdout 2024-2025.
"""

import os
import sys
import json
import numpy as np
import pandas as pd
import polars as pl
from catboost import CatBoostRegressor

sys.path.append(os.path.join(os.getcwd(), 'scripts'))
from build_meta_dataset_v3_h1 import PAIRS, load_pair_data, compute_kalman_states, compute_z_scores

DATA_PATH = "data/meta_model/events_h1_8yr_v3_dual.csv"
MODEL_PATH = "models/meta_model_h1/catboost_h1_reg.cbm"
TICK_ROOT = "/Users/danielfisher/Desktop/tick"

CATEGORICAL_FEATURES = ['strategy_type', 'active_leg', 'side']
NUMERIC_FEATURES = [
    'z_entry', 'z_velocity', 'spread_std', 'beta_stability', 'beta',
    'signal_beta_lookback', 'hedge_beta_lookback', 'beta_mismatch',
    'vol_ratio', 'correlation_500', 'trend_strength', 'hour', 'day_of_week',
    'ret_X_4h', 'ret_Y_4h', 'atr_ratio', 'entry_atr', 'vol_regime'
]
ALL_FEATURES = CATEGORICAL_FEATURES + NUMERIC_FEATURES

# Map pair name -> (X_sym, Y_sym)
PAIR_MAP = {}
for name, fx, fy, cx, cy, _, _ in PAIRS:
    x_sym = fx.split('_')[0]
    y_sym = fy.split('_')[0]
    PAIR_MAP[name] = (x_sym, y_sym)


class TickCache:
    def __init__(self, max_months=6):
        self.max_months = max_months
        self.cache = {}
        self.order = []

    def _add(self, key, val):
        if key in self.cache:
            return
        self.cache[key] = val
        self.order.append(key)
        if len(self.order) > self.max_months:
            old = self.order.pop(0)
            self.cache.pop(old, None)

    def get_month(self, symbol, yyyymm):
        key = (symbol, yyyymm)
        if key in self.cache:
            return self.cache[key]

        path = os.path.join(TICK_ROOT, symbol, f"{symbol}_{yyyymm}_ticks.parquet")
        if not os.path.exists(path):
            return None

        df = pl.read_parquet(path, columns=["timestamp", "mid"]).sort("timestamp")
        ts = df["timestamp"].to_numpy()
        mid = df["mid"].to_numpy()
        self._add(key, (ts, mid))
        return ts, mid


def month_range(start, end):
    s = pd.Timestamp(start).to_period('M')
    e = pd.Timestamp(end).to_period('M')
    months = []
    cur = s
    while cur <= e:
        months.append(cur.strftime('%Y%m'))
        cur = cur + 1
    return months


def load_ticks(symbol, start, end, cache):
    start = pd.to_datetime(start, utc=True)
    end = pd.to_datetime(end, utc=True)
    months = month_range(start, end)
    all_ts = []
    all_mid = []
    for m in months:
        res = cache.get_month(symbol, m)
        if res is None:
            continue
        ts, mid = res
        mask = (ts >= start.to_datetime64()) & (ts <= end.to_datetime64())
        if mask.any():
            all_ts.append(ts[mask])
            all_mid.append(mid[mask])

    if not all_ts:
        return None, None

    ts = np.concatenate(all_ts)
    mid = np.concatenate(all_mid)
    order = np.argsort(ts)
    return ts[order], mid[order]


def simulate_exit_idx(entry_idx, direction, strategy_type, z_scores, stop=3.5):
    for i in range(entry_idx + 1, min(entry_idx + 500, len(z_scores))):
        z = z_scores[i]
        if strategy_type == 'MOM':
            if direction == 1:
                if z < 0 or z > stop:
                    return i
            else:
                if z > 0 or z < -stop:
                    return i
        else:
            if direction == 1:
                if z > 0 or z < -stop:
                    return i
            else:
                if z < 0 or z > stop:
                    return i
    return min(entry_idx + 499, len(z_scores) - 1)


def apply_trailing(ts, prices, entry_time, exit_time, side, trail_bps):
    if ts is None or len(ts) == 0:
        return None, None

    # use tick window within [entry, exit]
    entry_time = pd.to_datetime(entry_time, utc=True).to_datetime64()
    exit_time = pd.to_datetime(exit_time, utc=True).to_datetime64()

    idx0 = np.searchsorted(ts, entry_time, side='left')
    idx1 = np.searchsorted(ts, exit_time, side='right') - 1
    if idx0 > idx1:
        return None, None

    p = prices[idx0:idx1+1]
    t = ts[idx0:idx1+1]

    entry_price = p[0]
    trail = trail_bps / 10000.0

    if side == 'LONG':
        cummax = np.maximum.accumulate(p)
        stop = cummax * (1 - trail)
        hit = p <= stop
    else:  # SHORT
        cummin = np.minimum.accumulate(p)
        stop = cummin * (1 + trail)
        hit = p >= stop

    if hit.any():
        hit_idx = int(np.argmax(hit))
        return t[hit_idx], p[hit_idx]

    # no trailing hit; exit at last tick in window
    return t[-1], p[-1]


def main():
    # Load events
    df = pl.read_csv(DATA_PATH).to_pandas()

    # Predict
    model = CatBoostRegressor()
    model.load_model(MODEL_PATH)
    model_features = list(getattr(model, "feature_names_", [])) or [f for f in ALL_FEATURES if f in df.columns]
    df['pred_pnl'] = model.predict(df[model_features])

    # Event-level best
    # ensure timestamp is datetime64 for reliable joins
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ns', utc=True).to_numpy()
    idx = df.groupby(['pair','timestamp'])['pred_pnl'].idxmax()
    best = df.loc[idx].copy()

    # Holdout 2024-2025, pred>20
    trades = best[(best['year'] >= 2024) & (best['pred_pnl'] > 20)].copy()
    trades = trades.sort_values('timestamp')

    # Precompute z-scores per pair
    pair_state = {}
    for pair in trades['pair'].unique():
        if pair not in PAIR_MAP:
            continue
        x_sym, y_sym = PAIR_MAP[pair]
        df_pair = load_pair_data(f"{x_sym}_1h.parquet", f"{y_sym}_1h.parquet", f"close_{x_sym}", f"close_{y_sym}")
        if df_pair is None:
            continue
        y = np.log(df_pair["Y"].to_numpy())
        x = np.log(df_pair["X"].to_numpy())
        ts = df_pair["timestamp"].to_numpy()
        betas, errors, _ = compute_kalman_states(y, x)
        z_scores = compute_z_scores(errors)
        idx_map = {ts[i]: i for i in range(len(ts))}
        pair_state[pair] = dict(ts=ts, z_scores=z_scores, idx_map=idx_map)

    # Simulate
    cache = TickCache(max_months=6)
    results = []

    for _, row in trades.iterrows():
        pair = row['pair']
        state = pair_state.get(pair)
        if state is None:
            continue

        entry_time = pd.to_datetime(row['timestamp'], unit='ns', utc=True).to_datetime64()
        entry_idx = state['idx_map'].get(entry_time)
        if entry_idx is None:
            continue

        direction = 1 if row['side'] == 'LONG' else -1
        strategy_type = row['strategy_type']

        exit_idx = simulate_exit_idx(entry_idx, direction, strategy_type, state['z_scores'])
        exit_time = state['ts'][exit_idx]

        # Active symbol
        x_sym, y_sym = PAIR_MAP[pair]
        active_sym = y_sym if row['active_leg'] == 'Y' else x_sym

        # Load tick window
        ts_ticks, mid = load_ticks(active_sym, entry_time, exit_time, cache)
        if ts_ticks is None:
            continue

        entry_idx_tick = np.searchsorted(ts_ticks, entry_time, side='left')
        exit_idx_tick = np.searchsorted(ts_ticks, exit_time, side='right') - 1
        if entry_idx_tick < 0 or entry_idx_tick >= len(mid):
            continue
        if exit_idx_tick < entry_idx_tick:
            exit_idx_tick = entry_idx_tick

        p_entry = mid[entry_idx_tick]
        p_exit = mid[exit_idx_tick]
        if row['side'] == 'LONG':
            pnl_base = (p_exit - p_entry) / p_entry * 10000
        else:
            pnl_base = (p_entry - p_exit) / p_entry * 10000

        results.append({
            'pair': pair,
            'timestamp': entry_time,
            'trail_bps': 0,
            'pnl_bps': pnl_base,
        })

        for trail in [100, 150]:
            t_exit, p_exit = apply_trailing(ts_ticks, mid, entry_time, exit_time, row['side'], trail)
            if t_exit is None:
                continue
            if row['side'] == 'LONG':
                pnl = (p_exit - p_entry) / p_entry * 10000
            else:
                pnl = (p_entry - p_exit) / p_entry * 10000

            results.append({
                'pair': pair,
                'timestamp': entry_time,
                'trail_bps': trail,
                'pnl_bps': pnl,
            })

    if not results:
        print("No results produced. Check tick data availability.")
        return

    res = pd.DataFrame(results)

    print("\nTrailing stop (tick-level) results for holdout 2024-2025")
    print("| trail_bps | trades | win_rate | mean_pnl | total_pnl | max_dd |")
    print("|---|---|---|---|---|---|")

    for trail in [0, 100, 150]:
        r = res[res['trail_bps'] == trail].sort_values('timestamp')
        pnl = r['pnl_bps'].to_numpy()
        curve = pnl.cumsum()
        peak = np.maximum.accumulate(curve)
        dd = curve - peak
        max_dd = dd.min() if len(dd) else 0
        win_rate = (pnl > 0).mean() * 100
        label = "baseline" if trail == 0 else str(trail)
        print(f"| {label} | {len(pnl)} | {win_rate:.1f}% | {pnl.mean():.2f} | {pnl.sum():.0f} | {max_dd:.0f} |")


if __name__ == "__main__":
    main()
