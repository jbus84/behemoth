#!/usr/bin/env python3
"""
Explore guardrails on holdout 2024-2025 for pred>20 event-level trades.
Outputs summary table for baseline and guard variants.
"""

import json
import numpy as np
import pandas as pd
import polars as pl
from catboost import CatBoostRegressor

DATA_PATH = "data/meta_model/events_h1_8yr_v3_dual.csv"
MODEL_PATH = "models/meta_model_h1/catboost_h1_reg.cbm"
RANGE_PATH = "models/meta_model_h1/feature_ranges_h1.json"

CATEGORICAL_FEATURES = ['strategy_type', 'active_leg', 'side']
NUMERIC_FEATURES = [
    'z_entry', 'z_velocity', 'spread_std', 'beta_stability', 'beta',
    'signal_beta_lookback', 'hedge_beta_lookback', 'beta_mismatch',
    'vol_ratio', 'correlation_500', 'trend_strength', 'hour', 'day_of_week',
    'ret_X_4h', 'ret_Y_4h', 'atr_ratio', 'entry_atr', 'vol_regime'
]
ALL_FEATURES = CATEGORICAL_FEATURES + NUMERIC_FEATURES


def max_drawdown(pnl_series):
    if len(pnl_series) == 0:
        return 0.0
    curve = pnl_series.cumsum().to_numpy()
    peak = np.maximum.accumulate(curve)
    dd = curve - peak
    return float(dd.min())


def metrics(df):
    if df.empty:
        return dict(trades=0, win_rate=0.0, mean_pnl=0.0, total_pnl=0.0, max_dd=0.0)
    pnl = df['pnl_bps']
    return dict(
        trades=len(df),
        win_rate=float((pnl > 0).mean() * 100),
        mean_pnl=float(pnl.mean()),
        total_pnl=float(pnl.sum()),
        max_dd=max_drawdown(pnl),
    )


def apply_circuit_breaker(df, loss_streak=3, pause_days=30):
    # df sorted by timestamp
    df = df.copy()
    df['dt'] = pd.to_datetime(df['timestamp'], unit='ns')
    keep = []
    state = {}

    for _, row in df.iterrows():
        pair = row['pair']
        dt = row['dt']
        if pair not in state:
            state[pair] = dict(losses=0, pause_until=None)

        st = state[pair]
        if st['pause_until'] is not None and dt < st['pause_until']:
            continue

        # take trade
        keep.append(row)

        # update streak
        if row['pnl_bps'] > 0:
            st['losses'] = 0
        else:
            st['losses'] += 1
            if st['losses'] >= loss_streak:
                st['pause_until'] = dt + pd.Timedelta(days=pause_days)
                st['losses'] = 0

    if not keep:
        return df.iloc[:0]
    return pd.DataFrame(keep)


def main():
    # Load holdout
    holdout = pl.read_csv(DATA_PATH).filter(pl.col('year') >= 2024).to_pandas()

    # Predict
    model = CatBoostRegressor()
    model.load_model(MODEL_PATH)
    model_features = list(getattr(model, "feature_names_", [])) or [f for f in ALL_FEATURES if f in holdout.columns]
    holdout['pred_pnl'] = model.predict(holdout[model_features])

    # Event-level selection (best pred per signal)
    idx = holdout.groupby(['pair', 'timestamp'])['pred_pnl'].idxmax()
    best = holdout.loc[idx].copy()
    best = best.sort_values('timestamp')

    # Baseline: pred > 20
    base = best[best['pred_pnl'] > 20].copy()

    # Shift score baseline
    if RANGE_PATH and os.path.exists(RANGE_PATH):
        with open(RANGE_PATH, 'r') as f:
            ranges = json.load(f)["features"]
        range_features = [k for k in NUMERIC_FEATURES if (k in best.columns and k in ranges)]
        low_arr = np.array([ranges[k]['p01'] for k in range_features])
        high_arr = np.array([ranges[k]['p99'] for k in range_features])
        vals = best[range_features].to_numpy()
        out = (vals < low_arr) | (vals > high_arr)
        best['shift_score'] = out.mean(axis=1)
    else:
        best['shift_score'] = 0.0

    # Guards
    guards = {}
    guards['baseline_pred>20'] = base
    guards['shift<=0.00'] = best[(best['pred_pnl'] > 20) & (best['shift_score'] <= 0.0)].copy()

    # Regime guard: block REV when beta high AND corr high
    reg = best[(best['pred_pnl'] > 20)].copy()
    reg = reg[~((reg['strategy_type'] == 'REV') & (reg['beta'] > 1.1) & (reg['correlation_500'] > 0.6))]
    guards['no_REV_if_beta>1.1_corr>0.6'] = reg

    # Trend guard: block when trend_strength > 0.03
    tg = best[(best['pred_pnl'] > 20) & (best['trend_strength'] <= 0.03)].copy()
    guards['trend_strength<=0.03'] = tg

    # Circuit breaker (3 losses, 30 days)
    cb = apply_circuit_breaker(base, loss_streak=3, pause_days=30)
    guards['circuit_breaker_3loss_30d'] = cb

    # Combo: regime guard + circuit breaker
    rg_cb = apply_circuit_breaker(reg, loss_streak=3, pause_days=30)
    guards['regime_guard + circuit_breaker'] = rg_cb

    # Report
    print("Guardrail exploration (holdout 2024-2025, event-level pred>20)")
    print("| Guard | Trades | Win Rate | Mean PnL | Total PnL | Max DD |")
    print("|---|---|---|---|---|---|")
    for name, df in guards.items():
        m = metrics(df)
        print(f"| {name} | {m['trades']} | {m['win_rate']:.1f}% | {m['mean_pnl']:.2f} | {m['total_pnl']:.0f} | {m['max_dd']:.0f} |")


if __name__ == "__main__":
    import os
    main()
