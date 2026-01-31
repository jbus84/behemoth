import polars as pl
import numpy as np
import os
from sklearn.linear_model import LinearRegression

def run_dynamic_fair_price():
    dataset_path = "graph_dataset_1m_2025.parquet"
    if not os.path.exists(dataset_path): return
        
    df = pl.read_parquet(dataset_path)
    nodes = ['NSXUSD', 'SPXUSD', 'EURUSD', 'GBPUSD', 'USDJPY', 'USDCHF', 'AUDUSD', 'USDCAD', 'XAUUSD']
    anchors = [n for n in nodes if n != 'NSXUSD']
    
    print(">>> RUNNING DYNAMIC FAIR PRICE MODEL (ROLLING OLS) <<<")
    
    # 1. Prepare Log Levels
    for n in nodes:
        df = df.with_columns((pl.col(f"{n}_mid").log() - pl.col(f"{n}_mid").first().log()).alias(f"{n}_level"))
        
    actuals = df["NSXUSD_level"].to_numpy()
    exog = df.select([f"{a}_level" for a in anchors]).to_numpy()
    
    # 2. Rolling Estimation
    # We use a 60-minute window to estimate betas
    WINDOW = 60
    fair_prices = np.zeros(len(df))
    # Fill first window with actuals to avoid 0s
    fair_prices[:WINDOW] = actuals[:WINDOW]
    
    # Optimization: Chunk the OLS (computing every step is slow, let's do every 5 steps and interpolate or just every step)
    # Actually for accuracy let's do every step but vectorized if possible (not easily with OLS)
    # Let's do it every step. It's only 500k.
    
    print(f">>> CALCULATING BETAS FOR {len(df)} STEPS...")
    
    for i in range(WINDOW, len(df), 10): # Step by 10 to speed up iteration
        y = actuals[i-WINDOW:i]
        X = exog[i-WINDOW:i]
        
        # Fit OLS
        reg = LinearRegression().fit(X, y)
        
        # Predict fair price for next 10 steps using current betas
        steps = min(10, len(df) - i)
        fair_prices[i:i+steps] = reg.predict(exog[i:i+steps])
        
    df = df.with_columns(pl.Series("fair_price", fair_prices))
    df = df.with_columns(
        (pl.col("NSXUSD_level") - pl.col("fair_price")).alias("residual")
    )
    
    # Adaptive Z-score on residual
    df = df.with_columns(
        (pl.col("residual") / pl.col("residual").rolling_std(100)).alias("residual_zscore")
    )
    
    # 3. Trade Strategy (Trend Following)
    # Testing hypothesis: Deviations are breakouts (86% win rate expected)
    Z_ENTRY = 2.5
    df = df.with_columns([
        (pl.col("residual_zscore").shift(1) > Z_ENTRY).alias("signal_long"),
        (pl.col("residual_zscore").shift(1) < -Z_ENTRY).alias("signal_short")
    ])
    
    # Evaluation
    df = df.with_columns(
        (pl.when(pl.col("signal_long")).then(pl.col("target_nsx_15m") * 10000 - pl.col("NSXUSD_spread"))
          .when(pl.col("signal_short")).then(-pl.col("target_nsx_15m") * 10000 - pl.col("NSXUSD_spread"))
          .otherwise(0)).alias("pnl_bps")
    )
    
    results = df.filter(pl.col("signal_long") | pl.col("signal_short"))
    
    if len(results) > 0:
        print(f"\n>>> DYNAMIC FAIR PRICE RESULTS (OOS 2025) <<<")
        print(f"  Trades:       {len(results)}")
        print(f"  Win Rate:     {(results['pnl_bps'] > 0).mean()*100:.2f}%")
        print(f"  Avg PnL:      {results['pnl_bps'].mean():.3f} bps")
        print(f"  Total PnL:    {results['pnl_bps'].sum():.2f} bps")
        
    import matplotlib.pyplot as plt
    sub = df.head(1000)
    plt.figure(figsize=(12, 6))
    plt.plot(sub["timestamp"], sub["NSXUSD_level"], label="NSX Spot")
    plt.plot(sub["timestamp"], sub["fair_price"], label="OLS Fair Price", color='red')
    plt.title("Dynamic Fair Value Model (Rolling 60m OLS)")
    plt.legend()
    plt.savefig("ols_fair_price.png")
    
if __name__ == "__main__":
    run_dynamic_fair_price()
