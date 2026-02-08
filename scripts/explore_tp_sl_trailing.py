#!/usr/bin/env python3
"""
Evaluate TP/SL and trailing stop using MFE/MAE approximations.
Event-level trades, pred>20, best MOM/REV per signal.
Outputs summary for full period and holdout 2024-2025.
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
    'ret_X_4h', 'ret_Y_4h', 'atr_ratio', 'entry_atr', 'vol_regime'
]
ALL_FEATURES = CATEGORICAL_FEATURES + NUMERIC_FEATURES


def max_dd(pnl):
    if len(pnl) == 0:
        return 0.0
    curve = pnl.cumsum().to_numpy()
    peak = np.maximum.accumulate(curve)
    dd = curve - peak
    return float(dd.min())


def metrics(df):
    if df.empty:
        return dict(trades=0, win_rate=0.0, mean_pnl=0.0, total_pnl=0.0, max_dd=0.0)
    pnl = df['pnl_adj']
    return dict(
        trades=len(df),
        win_rate=float((pnl > 0).mean() * 100),
        mean_pnl=float(pnl.mean()),
        total_pnl=float(pnl.sum()),
        max_dd=max_dd(pnl),
    )


def apply_tp_sl(df, tp, sl, mode="conservative"):
    pnl = df['pnl_bps'].to_numpy()
    mfe = df['mfe_bps'].to_numpy()
    mae = df['mae_bps'].to_numpy()
    out = pnl.copy()

    if mode == "conservative":
        # If stop was hit at any point, assume stop first
        hit_sl = mae <= -sl
        out[hit_sl] = -sl
        # Otherwise take TP if reached
        hit_tp = (mfe >= tp) & (~hit_sl)
        out[hit_tp] = tp
    else:
        # Optimistic: TP takes priority
        hit_tp = mfe >= tp
        out[hit_tp] = tp
        hit_sl = (mae <= -sl) & (~hit_tp)
        out[hit_sl] = -sl

    return out


def apply_trailing(df, trail):
    pnl = df['pnl_bps'].to_numpy()
    mfe = df['mfe_bps'].to_numpy()
    # If price retraces by trail from MFE, exit at MFE-trail.
    # Using final PnL as a proxy for retrace; if PnL <= MFE-trail, assume stop triggered.
    exit_trail = mfe - trail
    out = np.where(pnl <= exit_trail, exit_trail, pnl)
    return out


def run_block(df, label):
    print(f"\n== {label} ==")
    print("| Variant | Trades | Win Rate | Mean PnL | Total PnL | Max DD |")
    print("|---|---|---|---|---|---|")

    base = df.copy()
    base['pnl_adj'] = base['pnl_bps']
    m = metrics(base)
    print(f"| baseline | {m['trades']} | {m['win_rate']:.1f}% | {m['mean_pnl']:.2f} | {m['total_pnl']:.0f} | {m['max_dd']:.0f} |")

    for tp, sl in [(200,100), (300,150), (500,200)]:
        for mode in ["conservative", "optimistic"]:
            out = apply_tp_sl(df, tp, sl, mode=mode)
            temp = df.copy()
            temp['pnl_adj'] = out
            m = metrics(temp)
            print(f"| TP{tp}/SL{sl} ({mode[0:4]}) | {m['trades']} | {m['win_rate']:.1f}% | {m['mean_pnl']:.2f} | {m['total_pnl']:.0f} | {m['max_dd']:.0f} |")

    for trail in [100,150,200,300]:
        out = apply_trailing(df, trail)
        temp = df.copy()
        temp['pnl_adj'] = out
        m = metrics(temp)
        print(f"| trail {trail} | {m['trades']} | {m['win_rate']:.1f}% | {m['mean_pnl']:.2f} | {m['total_pnl']:.0f} | {m['max_dd']:.0f} |")


def main():
    df = pl.read_csv(DATA_PATH).to_pandas()

    model = CatBoostRegressor()
    model.load_model(MODEL_PATH)
    model_features = list(getattr(model, "feature_names_", [])) or [f for f in ALL_FEATURES if f in df.columns]
    df['pred_pnl'] = model.predict(df[model_features])

    idx = df.groupby(['pair','timestamp'])['pred_pnl'].idxmax()
    best = df.loc[idx].copy().sort_values('timestamp')
    trades = best[best['pred_pnl'] > 20].copy()

    run_block(trades, "All Available Data (2018–2025)")

    holdout = trades[trades['year'] >= 2024].copy()
    run_block(holdout, "Holdout 2024–2025")


if __name__ == "__main__":
    main()
