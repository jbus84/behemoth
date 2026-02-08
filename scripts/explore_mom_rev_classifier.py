#!/usr/bin/env python3
"""
Explore MOM vs REV classifier instead of PnL regressor.
Builds event-level labels: 1 if MOM pnl > REV pnl, else 0.
Evaluates on holdout 2024-2025.
"""

import numpy as np
import pandas as pd
import polars as pl
from catboost import CatBoostClassifier

DATA_PATH = "data/meta_model/events_h1_8yr_v3_dual.csv"

NUMERIC_FEATURES = [
    'z_entry', 'z_velocity', 'spread_std', 'beta_stability', 'beta',
    'vol_ratio', 'correlation_500', 'trend_strength', 'hour', 'day_of_week',
    'ret_X_4h', 'ret_Y_4h', 'atr_ratio', 'entry_atr', 'vol_regime'
]


def build_event_level(df):
    # pivot to get MOM/REV pnl per signal
    mom = df[df['strategy_type'] == 'MOM'].copy()
    rev = df[df['strategy_type'] == 'REV'].copy()

    mom = mom.rename(columns={'pnl_bps': 'pnl_mom'})
    rev = rev.rename(columns={'pnl_bps': 'pnl_rev'})

    # merge on pair/timestamp
    merged = mom.merge(rev[['pair','timestamp','pnl_rev']], on=['pair','timestamp'], how='inner')

    # label: 1 if MOM better, else REV
    merged['label_mom'] = (merged['pnl_mom'] > merged['pnl_rev']).astype(int)

    # features from MOM row (same as REV row for shared features)
    return merged


def metrics(pnl_series):
    if len(pnl_series) == 0:
        return dict(trades=0, win_rate=0.0, mean_pnl=0.0, total_pnl=0.0, max_dd=0.0)
    curve = pnl_series.cumsum().to_numpy()
    peak = np.maximum.accumulate(curve)
    dd = curve - peak
    return dict(
        trades=len(pnl_series),
        win_rate=float((pnl_series > 0).mean() * 100),
        mean_pnl=float(pnl_series.mean()),
        total_pnl=float(pnl_series.sum()),
        max_dd=float(dd.min()),
    )


def main():
    df = pl.read_csv(DATA_PATH).to_pandas()
    events = build_event_level(df)

    train = events[events['year'] <= 2023]
    test = events[events['year'] >= 2024]

    X_train = train[NUMERIC_FEATURES]
    y_train = train['label_mom']

    X_test = test[NUMERIC_FEATURES]
    y_test = test['label_mom']

    clf = CatBoostClassifier(
        iterations=500,
        depth=6,
        learning_rate=0.05,
        loss_function='Logloss',
        verbose=False,
        random_seed=42,
    )

    clf.fit(X_train, y_train, eval_set=(X_test, y_test), verbose=False)
    probs = clf.predict_proba(X_test)[:,1]

    # Choose MOM if prob>=0.5 else REV
    choose_mom = probs >= 0.5
    pnl = np.where(choose_mom, test['pnl_mom'].values, test['pnl_rev'].values)

    base = metrics(pd.Series(pnl))

    # Add probability filter (take trade only if |p-0.5| >= 0.1)
    conf = np.abs(probs - 0.5) >= 0.1
    pnl_conf = pnl[conf]
    conf_m = metrics(pd.Series(pnl_conf))

    print("MOM/REV classifier (event-level, holdout 2024-2025)")
    print(f"Accuracy: {((choose_mom == y_test.values).mean()*100):.1f}%")
    print("\nAll trades:")
    print(base)
    print("\nConf>=0.1 filter:")
    print(conf_m)


if __name__ == "__main__":
    main()
