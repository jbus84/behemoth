import polars as pl
import numpy as np
import os
import matplotlib.pyplot as plt

class MultiKalmanInnovation:
    """
    Tracks the Innovations (Surprises) of ALL 8 anchors simultaneously.
    If 7/8 anchors are 'Surprising' the market in the same direction, 
    we preempt the Nasdaq lag.
    """
    def __init__(self, r_ratio=0.1, q_ratio=0.0001):
        self.r = r_ratio
        self.q = q_ratio
        
    def run_analysis(self, df):
        nodes = ['NSXUSD', 'SPXUSD', 'EURUSD', 'GBPUSD', 'USDJPY', 'USDCHF', 'AUDUSD', 'USDCAD', 'XAUUSD']
        anchors = [n for n in nodes if n != 'NSXUSD']
        
        print(f">>> TRACKING SURPRISES ACROSS {len(anchors)} ANCHORS...")
        
        # We need a separate Kalman state for each anchor to detect its individual innovation
        states = {a: np.zeros((2, 1)) for a in anchors}
        covs = {a: np.eye(2) for a in anchors}
        F = np.array([[1, 1], [0, 1]])
        H = np.array([[1, 0]])
        Q = np.eye(2) * self.q
        R = self.r
        
        anchor_innovations = {a: [] for a in anchors}
        
        for k in range(len(df)):
            for a in anchors:
                val = df[f"{a}_mid"][k]
                # Log level (rolling relative)
                # To simplify, we use the return or log level? 
                # Let's use the 1m return as the observation for a drift-only model
                z = df[f"{a}_ret_1m"][k] * 10000 # Observation in BPS
                
                # Predict
                x = F @ states[a]
                P = F @ covs[a] @ F.T + Q
                
                # Update
                y = z - (H @ x) # Innovation (Actual return - Predicted Drift)
                S = H @ P @ H.T + R
                K = P @ H.T / S
                
                states[a] = x + K * y
                covs[a] = (np.eye(2) - K @ H) @ P
                
                anchor_innovations[a].append(y[0, 0])
                
        # Aggregate
        for a in anchors:
            df = df.with_columns(pl.Series(f"{a}_innovation", anchor_innovations[a]))
            
        # 2. Consensus Surprise
        # Detect where surprises are unidirectional
        df = df.with_columns([
            pl.sum_horizontal([(pl.col(f"{a}_innovation") > 1.0).cast(pl.Int32) for a in anchors]).alias("surprises_up"),
            pl.sum_horizontal([(pl.col(f"{a}_innovation") < -1.0).cast(pl.Int32) for a in anchors]).alias("surprises_down")
        ])
        
        # 3. Preemption Logic
        # If 7/8 anchors are surprising Up AND NSX is currently quiet
        THRESHOLD = 7
        NSX_QUIET = 0.5 # BPS
        
        df = df.with_columns([
            ((pl.col("surprises_up") >= THRESHOLD) & (pl.col("NSXUSD_ret_1m").abs() < NSX_QUIET / 10000)).alias("signal_long"),
            ((pl.col("surprises_down") >= THRESHOLD) & (pl.col("NSXUSD_ret_1m").abs() < NSX_QUIET / 10000)).alias("signal_short")
        ])
        
        # 4. Evaluation
        df = df.with_columns(
            (pl.when(pl.col("signal_long")).then(pl.col("target_nsx_15m") * 10000 - pl.col("NSXUSD_spread"))
              .when(pl.col("signal_short")).then(-pl.col("target_nsx_15m") * 10000 - pl.col("NSXUSD_spread"))
              .otherwise(0)).alias("pnl_bps")
        )
        
        results = df.filter(pl.col("signal_long") | pl.col("signal_short"))
        if len(results) > 0:
            print(f"\n>>> MULTI-ANCHOR INNOVATION RESULTS <<<")
            print(f"  Trades:       {len(results)}")
            print(f"  Win Rate:     {(results['pnl_bps'] > 0).mean()*100:.2f}%")
            print(f"  Avg PnL:      {results['pnl_bps'].mean():.3f} bps")
            
        return df

if __name__ == "__main__":
    dataset_path = "graph_dataset_1m_2025.parquet"
    if os.path.exists(dataset_path):
        df = pl.read_parquet(dataset_path)
        mki = MultiKalmanInnovation()
        mki.run_analysis(df)
