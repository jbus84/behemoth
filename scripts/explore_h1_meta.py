
import polars as pl
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns

DATA_PATH = "data/events/events_h1_8yr_v3_dual.csv"

def explore_h1():
    print("Loading H1 Data...")
    df = pl.read_csv(DATA_PATH)

    # Filter for MOMENTUM only (Alpha Driver)
    df = df.filter(pl.col("strategy_type") == "MOM")

    print(f"MOM Events: {len(df)}")

    # 1. Hour Analysis
    print("\n=== PnL by Hour (MOM) ===")
    h_stats = df.group_by('hour').agg([
        pl.len().alias('count'),
        pl.col('pnl_bps').mean().alias('mean_pnl'),
        (pl.col('pnl_bps') > 0).mean().alias('win_rate')
    ]).sort('hour')
    print(h_stats)

    # 2. Vol Regime Analysis (Deciles)
    print("\n=== PnL by Vol Regime (Short/Long Vol) ===")
    pdf = df.to_pandas()
    pdf['vol_bin'] = pd.qcut(pdf['vol_regime'], 5)
    v_stats = pdf.groupby('vol_bin')['pnl_bps'].agg(['count', 'mean', 'sum'])
    print(v_stats)

    # 3. Trend Strength Analysis
    print("\n=== PnL by Trend Strength ===")
    pdf['trend_bin'] = pd.qcut(pdf['trend_strength'].abs(), 5)
    t_stats = pdf.groupby('trend_bin')['pnl_bps'].agg(['count', 'mean', 'sum'])
    print(t_stats)

    # 4. Beta Analysis
    print("\n=== PnL by Beta (Regime) ===")
    pdf['beta_bin'] = pd.cut(pdf['beta'], bins=[0, 0.8, 0.95, 1.05, 1.2, 5])
    b_stats = pdf.groupby('beta_bin')['pnl_bps'].agg(['count', 'mean', 'sum'])
    print(b_stats)

if __name__ == "__main__":
    explore_h1()
