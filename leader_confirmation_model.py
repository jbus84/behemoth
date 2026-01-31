import polars as pl
import numpy as np
import os

class LeaderConfirmation:
    """
    Treats NSXUSD as the LEADER.
    Uses the 8 macro anchors as VALIDATORS.
    Strategy: Fade NSX if it moves without macro consensus (Fakeout Arbitration).
    """
    def __init__(self, r_ratio=0.1, q_ratio=0.0001):
        self.r = r_ratio
        self.q = q_ratio
        
    def run_analysis(self, df):
        nodes = ['NSXUSD', 'SPXUSD', 'EURUSD', 'GBPUSD', 'USDJPY', 'USDCHF', 'AUDUSD', 'USDCAD', 'XAUUSD']
        anchors = [n for n in nodes if n != 'NSXUSD']
        
        print(">>> RUNNING LEADER-CONFIRMATION MODEL (NSX=LEADER) <<<")
        
        # 1. Measure NSX Momentum Pulse
        # Using a sudden 2-minute move to identify 'Breakout Attempts'
        df = df.with_columns(
            (pl.col("NSXUSD_mid").log() - pl.col("NSXUSD_mid").shift(2).log()).alias("nsx_pulse_2m")
        )
        
        # 2. Measure Macro Support
        # How many anchors are moving with the NSX pulse?
        df = df.with_columns([
            pl.sum_horizontal([
                ( (pl.col("nsx_pulse_2m") > 0) & (pl.col(f"{a}_ret_1m") > 0) ).cast(pl.Int32) +
                ( (pl.col("nsx_pulse_2m") < 0) & (pl.col(f"{a}_ret_1m") < 0) ).cast(pl.Int32)
                for a in anchors
            ]).alias("macro_support_count")
        ])
        
        # 3. Strategy: Fakeout Arbitration
        # IF NSX makes a big pulse (> 2 bps) BUT Macro Support is Low (< 3/8)
        # THEN Fade the move (Mean Reversion)
        PULSE_THRESHOLD = 2.0 / 10000 
        MIN_SUPPORT = 3
        
        df = df.with_columns([
            ((pl.col("nsx_pulse_2m") > PULSE_THRESHOLD) & (pl.col("macro_support_count") <= MIN_SUPPORT)).alias("fade_short"),
            ((pl.col("nsx_pulse_2m") < -PULSE_THRESHOLD) & (pl.col("macro_support_count") <= MIN_SUPPORT)).alias("fade_long")
        ])
        
        # 4. Evaluation (5m horizon because fakes revert quickly)
        # Re-using the 15m target for consistency but logically fades are fast
        df = df.with_columns(
            (pl.when(pl.col("fade_long")).then(pl.col("target_nsx_15m") * 10000 - pl.col("NSXUSD_spread"))
              .when(pl.col("fade_short")).then(-pl.col("target_nsx_15m") * 10000 - pl.col("NSXUSD_spread"))
              .otherwise(0)).alias("pnl_bps")
        )
        
        results = df.filter(pl.col("fade_long") | pl.col("fade_short"))
        if len(results) > 0:
            print(f"\n>>> LEADER-CONFIRMATION RESULTS (OOS 2025) <<<")
            print(f"  Trades:       {len(results)}")
            print(f"  Win Rate:     {(results['pnl_bps'] > 0).mean()*100:.2f}%")
            print(f"  Avg PnL:      {results['pnl_bps'].mean():.3f} bps")
            print(f"  Total PnL:    {results['pnl_bps'].sum():.2f} bps")
            
        return df

if __name__ == "__main__":
    dataset_path = "graph_dataset_1m_2025.parquet"
    if os.path.exists(dataset_path):
        df = pl.read_parquet(dataset_path)
        lc = LeaderConfirmation()
        lc.run_analysis(df)
