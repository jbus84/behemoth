import polars as pl
import numpy as np
import os
import matplotlib.pyplot as plt

class KalmanInnovationShock:
    """
    Focuses on the INNOVATION (Measurement Surprise) of the Kalman Filter.
    Alpha = Velocity of Innovation Shock.
    """
    def __init__(self, r_ratio=0.1, q_ratio=0.0001):
        self.P = np.eye(2) * 1.0 
        self.F = np.array([[1, 1], [0, 1]]) # Level, Drift
        self.Q = np.eye(2) * q_ratio
        self.R = r_ratio 
        self.H = np.array([[1, 0]]) 
        self.x = np.zeros((2, 1)) 
        
    def filter_dataset(self, df):
        print(">>> EXTRACTING MACRO INNOVATION SHOCKS <<<")
        nodes = ['NSXUSD', 'SPXUSD', 'EURUSD', 'GBPUSD', 'USDJPY', 'USDCHF', 'AUDUSD', 'USDCAD', 'XAUUSD']
        
        for asset in nodes:
            mid_col = f"{asset}_mid"
            df = df.with_columns(
                (pl.col(mid_col).log() - pl.col(mid_col).first().log()).alias(f"{asset}_level")
            )
            
        anchors = [f"{n}_level" for n in nodes if n != 'NSXUSD']
        df = df.with_columns(pl.mean_horizontal(anchors).alias("macro_anchor"))
        
        actuals = df["NSXUSD_level"].to_numpy()
        innovations = []
        
        self.x[0,0] = actuals[0]
        
        for k in range(len(df)):
            # Predict
            self.x = self.F @ self.x
            self.P = self.F @ self.P @ self.F.T + self.Q
            
            # Measurement
            z = actuals[k]
            
            # INNOVATION (y = z - Hx)
            # This is the 'Surprise' relative to the filtered state
            y = z - (self.H @ self.x)
            
            # Update
            S = self.H @ self.P @ self.H.T + self.R
            K = self.P @ self.H.T @ np.linalg.inv(S)
            self.x = self.x + K @ y
            self.P = (np.eye(2) - K @ self.H) @ self.P
            
            innovations.append(y[0, 0])
            
        df = df.with_columns(pl.Series("innovation", innovations))
        
        # KEY METRIC: Innovation Velocity (The 'Shock')
        # dY/dt
        df = df.with_columns(
            (pl.col("innovation") - pl.col("innovation").shift(1)).alias("innovation_shock")
        )
        
        # Normalize Shock to Z-score
        df = df.with_columns(
            (pl.col("innovation_shock") / pl.col("innovation_shock").rolling_std(60)).alias("shock_zscore")
        )
        
        return df

def run_analysis():
    dataset_path = "graph_dataset_1m_2025.parquet"
    if not os.path.exists(dataset_path): return
        
    df = pl.read_parquet(dataset_path)
    
    # Filter
    model = KalmanInnovationShock(r_ratio=0.1, q_ratio=0.0001)
    df = model.filter_dataset(df)
    
    # Strategy: Trade the SHOCK
    # If Shock Z > 3.0 -> Nasdaq is suddenly outperforming its macro peers (Trend Continuation)
    # If Shock Z < -3.0 -> Nasdaq is suddenly underperforming (Trend Continuation)
    SHOCK_THRESHOLD = 3.0
    
    df = df.with_columns([
        (pl.col("shock_zscore").shift(1) > SHOCK_THRESHOLD).alias("signal_long"),
        (pl.col("shock_zscore").shift(1) < -SHOCK_THRESHOLD).alias("signal_short")
    ])
    
    # Evaluation
    df = df.with_columns(
        (pl.when(pl.col("signal_long")).then(pl.col("target_nsx_15m") * 10000 - pl.col("NSXUSD_spread"))
          .when(pl.col("signal_short")).then(-pl.col("target_nsx_15m") * 10000 - pl.col("NSXUSD_spread"))
          .otherwise(0)).alias("pnl_bps")
    )
    
    results = df.filter(pl.col("signal_long") | pl.col("signal_short"))
    
    if len(results) > 0:
        print(f"\n>>> KALMAN INNOVATION SHOCK RESULTS (2025 OOS) <<<")
        print(f"  Trades:       {len(results)}")
        print(f"  Win Rate:     {(results['pnl_bps'] > 0).mean()*100:.2f}%")
        print(f"  Avg PnL:      {results['pnl_bps'].mean():.3f} bps")
        print(f"  Signal Conv:  {SHOCK_THRESHOLD} Sigma")
        
    # Plotting
    sub = df.head(1000)
    plt.figure(figsize=(15, 8))
    plt.subplot(2, 1, 1)
    plt.plot(sub["timestamp"], sub["innovation"], label="Kalman Innovation (Raw Surprise)", color='orange')
    plt.title("Innovation: The 'Unexplained' Part of Nasdaq Price")
    plt.legend()
    
    plt.subplot(2, 1, 2)
    plt.plot(sub["timestamp"], sub["shock_zscore"], label="Innovation Shock (Velocity)", color='red')
    plt.axhline(3, color='black', linestyle='--')
    plt.axhline(-3, color='black', linestyle='--')
    plt.title("Shock Detector: Trading the Sudden Disconnect")
    plt.legend()
    plt.tight_layout()
    plt.savefig("innovation_shock_results.png")
    print("\nVisualized results in: innovation_shock_results.png")

if __name__ == "__main__":
    run_analysis()
