#!/usr/bin/env python3
"""
Explore drawdown-reduction controls that do NOT rely on TP/SL/trailing stops.
Evaluates holdout 2024-2025, event-level pred>20 best MOM/REV trades.
"""

import numpy as np
import pandas as pd
import polars as pl
from catboost import CatBoostRegressor

DATA_PATH = "data/analysis/mfe_mae_h1.csv"
MODEL_PATH = "models/meta_model_h1/catboost_h1_reg.cbm"

CATEGORICAL_FEATURES = ['strategy_type', 'active_leg', 'side']
NUMERIC_FEATURES = [
    'z_entry', 'z_velocity', 'spread_std', 'beta_stability', 'beta',
    'signal_beta_lookback', 'hedge_beta_lookback', 'beta_mismatch',
    'vol_ratio', 'correlation_500', 'trend_strength', 'hour', 'day_of_week',
    'ret_X_16b', 'ret_Y_16b', 'atr_ratio', 'entry_atr', 'vol_regime'
]
ALL_FEATURES = CATEGORICAL_FEATURES + NUMERIC_FEATURES


def max_dd(pnl):
    if len(pnl) == 0:
        return 0.0
    curve = np.cumsum(pnl)
    peak = np.maximum.accumulate(curve)
    return float((curve - peak).min())


def metrics(df):
    if len(df) == 0:
        return dict(trades=0, win_rate=0.0, mean_pnl=0.0, total_pnl=0.0, max_dd=0.0)
    d = df.sort_values('timestamp')
    pnl = d['pnl_bps'].to_numpy()
    return dict(
        trades=len(df),
        win_rate=float((pnl > 0).mean() * 100),
        mean_pnl=float(pnl.mean()),
        total_pnl=float(pnl.sum()),
        max_dd=max_dd(pnl),
    )


def circuit_breaker(df, loss_streak=3, pause_days=30):
    d = df.sort_values('timestamp').copy()
    d['dt'] = pd.to_datetime(d['timestamp'], unit='ns')

    out = []
    state = {}

    for _, row in d.iterrows():
        pair = row['pair']
        dt = row['dt']
        if pair not in state:
            state[pair] = {'losses': 0, 'pause_until': None}

        st = state[pair]
        if st['pause_until'] is not None and dt < st['pause_until']:
            continue

        out.append(row)

        if row['pnl_bps'] > 0:
            st['losses'] = 0
        else:
            st['losses'] += 1
            if st['losses'] >= loss_streak:
                st['pause_until'] = dt + pd.Timedelta(days=pause_days)
                st['losses'] = 0

    return pd.DataFrame(out)


def monthly_kill(df, monthly_loss_cap=-1000):
    d = df.sort_values('timestamp').copy()
    d['dt'] = pd.to_datetime(d['timestamp'], unit='ns')

    out = []
    current_month = None
    month_pnl = 0.0
    killed = False

    for _, row in d.iterrows():
        month_key = (row['dt'].year, row['dt'].month)
        if month_key != current_month:
            current_month = month_key
            month_pnl = 0.0
            killed = False

        if killed:
            continue

        out.append(row)
        month_pnl += row['pnl_bps']
        if month_pnl <= monthly_loss_cap:
            killed = True

    return pd.DataFrame(out)


def main():
    df = pl.read_csv(DATA_PATH).to_pandas()

    model = CatBoostRegressor()
    model.load_model(MODEL_PATH)
    model_features = list(getattr(model, "feature_names_", [])) or [f for f in ALL_FEATURES if f in df.columns]
    df['pred_pnl'] = model.predict(df[model_features])

    # Event-level best MOM/REV
    idx = df.groupby(['pair', 'timestamp'])['pred_pnl'].idxmax()
    best = df.loc[idx].copy()

    # Holdout + threshold
    base = best[(best['year'] >= 2024) & (best['pred_pnl'] > 20)].copy()

    candidates = {
        'baseline_pred>20': base,
        'trend_strength<=0.03': base[base['trend_strength'] <= 0.03],
        'exclude_SPX_pairs': base[~base['pair'].str.startswith('SPX/')],
        'circuit_breaker_3loss_30d': circuit_breaker(base, 3, 30),
        'monthly_kill_-500': monthly_kill(base, -500),
        'monthly_kill_-1000': monthly_kill(base, -1000),
        'monthly_kill_-1500': monthly_kill(base, -1500),
        'trend<=0.03 + circuit_breaker': circuit_breaker(base[base['trend_strength'] <= 0.03], 3, 30),
        'exclude_SPX + circuit_breaker': circuit_breaker(base[~base['pair'].str.startswith('SPX/')], 3, 30),
    }

    print("| Rule | Trades | Win Rate | Mean PnL | Total PnL | Max DD |")
    print("|---|---|---|---|---|---|")
    for name, d in candidates.items():
        m = metrics(d)
        print(f"| {name} | {m['trades']} | {m['win_rate']:.1f}% | {m['mean_pnl']:.2f} | {m['total_pnl']:.0f} | {m['max_dd']:.0f} |")


if __name__ == '__main__':
    main()
