import polars as pl
import numpy as np
import os
import matplotlib.pyplot as plt

class JointInnovationEnergy:
    """
    Fuses 8 macro innovations into a single 'Global Energy' metric.
    Detects 'Global Macro Shocks' and trades the Nasdaq lag.
    """
    def __init__(self, r_ratio=0.1, q_ratio=0.0001):
        self.r = r_ratio
        self.q = q_ratio
        
    def run_analysis(self, df):
        nodes = ['NSXUSD', 'SPXUSD', 'EURUSD', 'GBPUSD', 'USDJPY', 'USDCHF', 'AUDUSD', 'USDCAD', 'XAUUSD']
        anchors = [n for n in nodes if n != 'NSXUSD']
        
        print(f">>> FUSING GLOBAL INNOVATION ENERGY (8 ANCHORS)...")
        
        # State Space for all assets (including NSX to check lag)
        states = {n: np.zeros((2, 1)) for n in nodes}
        covs = {n: np.eye(2) for n in nodes}
        F = np.array([[1, 1], [0, 1]])
        H = np.array([[1, 0]])
        Q = np.eye(2) * self.q
        
        innovations = {n: [] for n in nodes}
        
        for k in range(len(df)):
            for n in nodes:
                # Observation: 1m Return
                z = df[f"{n}_ret_1m"][k] * 10000 
                x = F @ states[n]
                P = F @ covs[n] @ F.T + Q
                y = z - (H @ x)
                S = H @ P @ H.T + self.r
                K = P @ H.T / S
                states[n] = x + K * y
                covs[n] = (np.eye(2) - K @ H) @ P
                innovations[n].append(y[0, 0])
                
        # Z-Score Innovations
        for n in nodes:
            df = df.with_columns(pl.Series(f"{n}_inn", innovations[n]))
            df = df.with_columns(
                (pl.col(f"{n}_inn") / pl.col(f"{n}_inn").rolling_std(120)).alias(f"{n}_inn_z")
            )
            
        # 1. CALCULATE GLOBAL ENERGY
        # Mean absolute surprise across anchors
        df = df.with_columns(
            pl.mean_horizontal([pl.col(f"{a}_inn_z").abs() for a in anchors]).alias("global_energy"),
            # Directional Consensus (weighted by surprise)
            pl.mean_horizontal([pl.col(f"{a}_inn_z") for a in anchors]).alias("macro_direction")
        )
        
        # 2. LOGIC: LAG PREEMPTION
        # Signal: Global Energy High (> 1.5) AND Nasdaq is lagging the Macro Direction
        # e.g., Macro is moving +3 Sigma but NSX is only moving +0.5 Sigma.
        ENERGY_GO = 1.8
        LAG_LIMIT = 0.5 
        
        df = df.with_columns([
            ((pl.col("global_energy") > ENERGY_GO) & 
             (pl.col("macro_direction") > 1.0) & 
             (pl.col("NSXUSD_inn_z") < LAG_LIMIT)).alias("signal_long"),
             
            ((pl.col("global_energy") > ENERGY_GO) & 
             (pl.col("macro_direction") < -1.0) & 
             (pl.col("NSXUSD_inn_z") > -LAG_LIMIT)).alias("signal_short")
        ])
        
        # 3. Evaluation
        df = df.with_columns(
            (pl.when(pl.col("signal_long")).then(pl.col("target_nsx_15m") * 10000 - pl.col("NSXUSD_spread"))
              .when(pl.col("signal_short")).then(-pl.col("target_nsx_15m") * 10000 - pl.col("NSXUSD_spread"))
              .otherwise(0)).alias("pnl_bps")
        )
        
        results = df.filter(pl.col("signal_long") | pl.col("signal_short"))
        if len(results) > 0:
            print(f"\n>>> JOINT INNOVATION ENERGY RESULTS <<<")
            print(f"  Trades:       {len(results)}")
            print(f"  Win Rate:     {(results['pnl_bps'] > 0).mean()*100:.2f}%")
            print(f"  Avg PnL:      {results['pnl_bps'].mean():.3f} bps")
            print(f"  Total PnL:    {results['pnl_bps'].sum():.2f} bps")
        else:
            print("No signals.")
            
        return df

if __name__ == "__main__":
    dataset_path = "graph_dataset_1m_2025.parquet"
    if os.path.exists(dataset_path):
        df = pl.read_parquet(dataset_path)
        jie = JointInnovationEnergy()
        jie.run_analysis(df)
