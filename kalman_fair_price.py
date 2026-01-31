import polars as pl
import numpy as np
import os
import matplotlib.pyplot as plt

class KalmanFairPrice:
    def __init__(self, r_ratio=0.01, q_ratio=0.0001):
        self.P = np.eye(2) * 1.0 
        self.F = np.array([[1, 1], [0, 1]]) # Price and Drift
        self.Q = np.eye(2) * q_ratio
        self.R = r_ratio 
        self.H = np.array([[1, 0]]) 
        self.x = np.zeros((2, 1)) 
        
    def filter_dataset(self, df):
        print(">>> INITIALIZING FAIR PRICE ESTIMATION <<<")
        nodes = ['NSXUSD', 'SPXUSD', 'EURUSD', 'GBPUSD', 'USDJPY', 'USDCHF', 'AUDUSD', 'USDCAD', 'XAUUSD']
        
        # 1. Normalize levels to 0-start for levels
        for asset in nodes:
            mid_col = f"{asset}_mid"
            df = df.with_columns(
                (pl.col(mid_col).log() - pl.col(mid_col).first().log()).alias(f"{asset}_level")
            )
            
        # 2. Compute "Macro Anchor" (Equal-weighted level of the other 8)
        anchors = [f"{n}_level" for n in nodes if n != 'NSXUSD']
        df = df.with_columns(
            pl.mean_horizontal(anchors).alias("macro_anchor")
        )
        
        actuals = df["NSXUSD_level"].to_numpy()
        anchors = df["macro_anchor"].to_numpy()
        
        fair_prices = []
        residuals = []
        uncertainties = []
        
        print(f">>> FILTERING {len(df)} DATA POINTS...")
        
        # Initialize x with first actual
        self.x[0,0] = actuals[0]
        
        for k in range(len(df)):
            # Predict
            self.x = self.F @ self.x
            self.P = self.F @ self.P @ self.F.T + self.Q
            
            # Observation: The "Fair Price" is Anchor[k]
            # We want to see how much Actual[k] deviates from the Fair Price
            z = actuals[k]
            
            # Innovation
            y = z - (self.H @ self.x)
            S = self.H @ self.P @ self.H.T + self.R
            K = self.P @ self.H.T @ np.linalg.inv(S)
            
            # Update
            self.x = self.x + K @ y
            self.P = (np.eye(2) - K @ self.H) @ self.P
            
            fair_prices.append(self.x[0, 0])
            residuals.append(y[0, 0])
            uncertainties.append(np.sqrt(self.P[0, 0]))
            
        df = df.with_columns([
            pl.Series("fair_price", fair_prices),
            pl.Series("deviation_innovation", residuals),
            pl.Series("innovation_std", uncertainties)
        ])
        
        # Adaptive Z-score based on 60m rolling window
        df = df.with_columns(
            (pl.col("deviation_innovation") / pl.col("deviation_innovation").rolling_std(60)).alias("deviation_zscore")
        )
        
        return df

def run_analysis():
    dataset_path = "graph_dataset_1m_2025.parquet"
    if not os.path.exists(dataset_path):
        print("Dataset missing.")
        return
        
    df = pl.read_parquet(dataset_path)
    
    # Run Filter (High R means we trust the fair price path less than the actual price, 
    # but we want a smoother fair price anchor)
    kf = KalmanFairPrice(r_ratio=0.1, q_ratio=0.00001)
    df = kf.filter_dataset(df)
    
    # Signal Logic: Sparse Arbitrage (Mean Reversion)
    # Only trade when deviation is extreme AND market is volatile
    ENTRY_Z = 3.5
    VOL_MIN = 3.0 # Min volatility in bps 
    
    df = df.with_columns([
        ((pl.col("deviation_zscore").shift(1) > ENTRY_Z) & (pl.col("NSXUSD_vol_30m") > VOL_MIN)).alias("signal_short"),
        ((pl.col("deviation_zscore").shift(1) < -ENTRY_Z) & (pl.col("NSXUSD_vol_30m") > VOL_MIN)).alias("signal_long")
    ])
    
    # Results Evaluation
    df = df.with_columns(
        (pl.when(pl.col("signal_long")).then(pl.col("target_nsx_15m") * 10000 - pl.col("NSXUSD_spread"))
          .when(pl.col("signal_short")).then(-pl.col("target_nsx_15m") * 10000 - pl.col("NSXUSD_spread"))
          .otherwise(0)).alias("pnl_bps")
    )
    
    results = df.filter(pl.col("signal_long") | pl.col("signal_short"))
    
    if len(results) > 0:
        avg_pnl = results["pnl_bps"].mean()
        win_rate = (results["pnl_bps"] > 0).mean()
        total_pnl = results["pnl_bps"].sum()
        
        print("\n>>> FAIR PRICE ARBITRAGE RESULTS (2025 OOS) <<<")
        print(f"  Trades:       {len(results)}")
        print(f"  Win Rate:     {win_rate*100:.2f}%")
        print(f"  Avg PnL:      {avg_pnl:.3f} bps")
        print(f"  Total PnL:    {total_pnl:.2f} bps")
    else:
        print("No signals found.")
        
    # Plotting
    sub = df.head(1000)
    plt.figure(figsize=(15, 8))
    plt.subplot(2, 1, 1)
    plt.plot(sub["timestamp"], sub["NSXUSD_level"], label="Actual Level")
    plt.plot(sub["timestamp"], sub["fair_price"], label="Kalman Fair Price", color='red')
    plt.title("Kalman Fair Price Model (Macro Anchored)")
    plt.legend()
    
    plt.subplot(2, 1, 2)
    plt.plot(sub["timestamp"], sub["deviation_zscore"], label="Signal Z-Score", color='purple')
    plt.axhline(2, color='red', linestyle='--')
    plt.axhline(-2, color='green', linestyle='--')
    plt.title("Arbitrage Signal (Deviation from Fair Price)")
    plt.legend()
    plt.tight_layout()
    plt.savefig("kalman_results.png")
    print("\nVisualized results in: kalman_results.png")

if __name__ == "__main__":
    run_analysis()
