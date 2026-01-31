import polars as pl
import numpy as np
import os

class InnovationPulseFader:
    """
    Capitalizes on the discovery that extreme macro innovation spikes
    at 1-minute resolution are almost always 'Exhaustion' events.
    Strategy: Mean Reversion (Fade the consensus surprise).
    """
    def __init__(self, r_ratio=0.1, q_ratio=0.0001):
        self.r = r_ratio
        self.q = q_ratio
        
    def run_analysis(self, df):
        nodes = ['NSXUSD', 'SPXUSD', 'EURUSD', 'GBPUSD', 'USDJPY', 'USDCHF', 'AUDUSD', 'USDCAD', 'XAUUSD']
        anchors = [n for n in nodes if n != 'NSXUSD']
        
        print(f">>> RUNNING INNOVATION PULSE FADER (MEAN REVERSION)...")
        
        # State Space for all anchors
        states = {a: np.zeros((2, 1)) for a in anchors}
        covs = {a: np.eye(2) for a in anchors}
        F = np.array([[1, 1], [0, 1]])
        H = np.array([[1, 0]])
        Q = np.eye(2) * self.q
        
        anchor_innovations = {a: [] for a in anchors}
        
        for k in range(len(df)):
            for a in anchors:
                z = df[f"{a}_ret_1m"][k] * 10000 
                x = F @ states[a]
                P = F @ covs[a] @ F.T + Q
                y = z - (H @ x)
                S = H @ P @ H.T + self.r
                K = P @ H.T / S
                states[a] = x + K * y
                covs[a] = (np.eye(2) - K @ H) @ P
                anchor_innovations[a].append(y[0, 0])
                
        for a in anchors:
            df = df.with_columns(pl.Series(f"{a}_innovation", anchor_innovations[a]))
            df = df.with_columns(
                (pl.col(f"{a}_innovation") / pl.col(f"{a}_innovation").rolling_std(120)).alias(f"{a}_inn_z")
            )
            
        # Consensus Surprise
        SIGMA_THRESHOLD = 2.0
        df = df.with_columns([
            pl.sum_horizontal([(pl.col(f"{a}_inn_z") > SIGMA_THRESHOLD).cast(pl.Int32) for a in anchors]).alias("surprises_up"),
            pl.sum_horizontal([(pl.col(f"{a}_inn_z") < -SIGMA_THRESHOLD).cast(pl.Int32) for a in anchors]).alias("surprises_down")
        ])
        
        # MEAN REVERSION LOGIC: Fade the Spike
        # If 6+ assets surprise Up, NSX likely peaked -> SHORT
        CONSENSUS_GO = 6
        
        df = df.with_columns([
            (pl.col("surprises_up") >= CONSENSUS_GO).alias("signal_short"),
            (pl.col("surprises_down") >= CONSENSUS_GO).alias("signal_long")
        ])
        
        # Evaluation
        df = df.with_columns(
            (pl.when(pl.col("signal_long")).then(pl.col("target_nsx_15m") * 10000 - pl.col("NSXUSD_spread"))
              .when(pl.col("signal_short")).then(-pl.col("target_nsx_15m") * 10000 - pl.col("NSXUSD_spread"))
              .otherwise(0)).alias("pnl_bps")
        )
        
        results = df.filter(pl.col("signal_long") | pl.col("signal_short"))
        if len(results) > 0:
            print(f"\n>>> INNOVATION PULSE FADER RESULTS (OOS 2025) <<<")
            print(f"  Trades:       {len(results)}")
            print(f"  Win Rate:     {(results['pnl_bps'] > 0).mean()*100:.2f}%")
            print(f"  Avg PnL:      {results['pnl_bps'].mean():.3f} bps")
            print(f"  Total PnL:    {results['pnl_bps'].sum():.2f} bps")
        
        return df

if __name__ == "__main__":
    dataset_path = "graph_dataset_1m_2025.parquet"
    if os.path.exists(dataset_path):
        df = pl.read_parquet(dataset_path)
        model = InnovationPulseFader()
        model.run_analysis(df)
