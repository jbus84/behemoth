import polars as pl
import numpy as np
import os

class AdaptiveConsensusInnovation:
    """
    Refinement of the Multi-Anchor Innovation model.
    Uses rolling innovation variance to adapt to market regimes.
    """
    def __init__(self, r_ratio=0.1, q_ratio=0.0001):
        self.r = r_ratio
        self.q = q_ratio
        
    def run_analysis(self, df):
        nodes = ['NSXUSD', 'SPXUSD', 'EURUSD', 'GBPUSD', 'USDJPY', 'USDCHF', 'AUDUSD', 'USDCAD', 'XAUUSD']
        anchors = [n for n in nodes if n != 'NSXUSD']
        
        print(f">>> RUNNING ADAPTIVE CONSENSUS ANALYSIS...")
        
        # State Space
        states = {a: np.zeros((2, 1)) for a in anchors}
        covs = {a: np.eye(2) for a in anchors}
        F = np.array([[1, 1], [0, 1]])
        H = np.array([[1, 0]])
        Q = np.eye(2) * self.q
        
        anchor_innovations = {a: [] for a in anchors}
        
        for k in range(len(df)):
            for a in anchors:
                z = df[f"{a}_ret_1m"][k] * 10000 
                # Kalman
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
            # DYNAMIC: Z-score the innovation
            df = df.with_columns(
                (pl.col(f"{a}_innovation") / pl.col(f"{a}_innovation").rolling_std(120)).alias(f"{a}_inn_z")
            )
            
        # 2. Consensus Logic (Z > 2.0 Sigma is a significant surprise)
        SIGMA_THRESHOLD = 2.0
        df = df.with_columns([
            pl.sum_horizontal([(pl.col(f"{a}_inn_z") > SIGMA_THRESHOLD).cast(pl.Int32) for a in anchors]).alias("consensus_up"),
            pl.sum_horizontal([(pl.col(f"{a}_inn_z") < -SIGMA_THRESHOLD).cast(pl.Int32) for a in anchors]).alias("consensus_down")
        ])
        
        # 3. Strategy: 6/8 Consensus leads to NSX Preemption
        # Lowered to 6 to increase frequency from the 14-trade test
        CONSENSUS_GO = 6
        NSX_LIMIT = 0.5 / 10000
        
        df = df.with_columns([
            ((pl.col("consensus_up") >= CONSENSUS_GO) & (pl.col("NSXUSD_ret_1m").abs() < NSX_LIMIT)).alias("signal_long"),
            ((pl.col("consensus_down") >= CONSENSUS_GO) & (pl.col("NSXUSD_ret_1m").abs() < NSX_LIMIT)).alias("signal_short")
        ])
        
        # 4. Evaluation
        df = df.with_columns(
            (pl.when(pl.col("signal_long")).then(pl.col("target_nsx_15m") * 10000 - pl.col("NSXUSD_spread"))
              .when(pl.col("signal_short")).then(-pl.col("target_nsx_15m") * 10000 - pl.col("NSXUSD_spread"))
              .otherwise(0)).alias("pnl_bps")
        )
        
        results = df.filter(pl.col("signal_long") | pl.col("signal_short"))
        if len(results) > 0:
            print(f"\n>>> ADAPTIVE CONSENSUS RESULTS (Sigma={SIGMA_THRESHOLD}, Vote={CONSENSUS_GO}) <<<")
            print(f"  Trades:       {len(results)}")
            print(f"  Win Rate:     {(results['pnl_bps'] > 0).mean()*100:.2f}%")
            print(f"  Avg PnL:      {results['pnl_bps'].mean():.3f} bps")
            print(f"  Total PnL:    {results['pnl_bps'].sum():.2f} bps")
        
        return df

if __name__ == "__main__":
    dataset_path = "graph_dataset_1m_2025.parquet"
    if os.path.exists(dataset_path):
        df = pl.read_parquet(dataset_path)
        model = AdaptiveConsensusInnovation()
        model.run_analysis(df)
