import polars as pl
import numpy as np
import os

def run_regime_aware_consensus():
    dataset_path = "graph_dataset_1m_2025.parquet"
    if not os.path.exists(dataset_path): return
        
    df = pl.read_parquet(dataset_path)
    nodes = ['NSXUSD', 'SPXUSD', 'EURUSD', 'GBPUSD', 'USDJPY', 'USDCHF', 'AUDUSD', 'USDCAD', 'XAUUSD']
    anchors = [n for n in nodes if n != 'NSXUSD']
    
    print(">>> RUNNING REGIME-AWARE CONSENSUS ARBITRATION <<<")
    
    # 1. Macro Consensus
    df = df.with_columns([
        pl.sum_horizontal([(pl.col(f"{a}_ret_1m") > 0).cast(pl.Int32) for a in anchors]).alias("consensus_up"),
        pl.sum_horizontal([(pl.col(f"{a}_ret_1m") < 0).cast(pl.Int32) for a in anchors]).alias("consensus_down")
    ])
    
    # 2. Macro Regime (Mean Anchor Correlation)
    # We calculate the 1h rolling correlation of NSX with the macro consensus direction
    df = df.with_columns(
        pl.mean_horizontal([pl.col(f"{a}_ret_1m") for a in anchors]).alias("avg_anchor_ret")
    )
    
    df = df.with_columns(
        pl.rolling_corr(pl.col("NSXUSD_ret_1m"), pl.col("avg_anchor_ret"), window_size=60).alias("macro_regime_corr")
    )
    
    CONSENSUS_GO = 7
    CORR_THRESHOLD = 0.3
    
    # Logic:
    # IF Corr > +0.3 (Positive Regime): FOLLOW the consensus
    # IF Corr < -0.3 (Negative Regime): FADE the consensus
    
    df = df.with_columns([
        # Positive Regime: Trend Follow
        ((pl.col("macro_regime_corr") > CORR_THRESHOLD) & (pl.col("consensus_up") >= CONSENSUS_GO)).alias("pos_long"),
        ((pl.col("macro_regime_corr") > CORR_THRESHOLD) & (pl.col("consensus_down") >= CONSENSUS_GO)).alias("pos_short"),
        
        # Negative Regime: Fade (Reversion)
        ((pl.col("macro_regime_corr") < -CORR_THRESHOLD) & (pl.col("consensus_up") >= CONSENSUS_GO)).alias("neg_short"),
        ((pl.col("macro_regime_corr") < -CORR_THRESHOLD) & (pl.col("consensus_down") >= CONSENSUS_GO)).alias("neg_long")
    ])
    
    # 3. Evaluation
    df = df.with_columns(
        (pl.when(pl.col("pos_long") | pl.col("neg_long")).then(pl.col("target_nsx_15m") * 10000 - 1.5)
          .when(pl.col("pos_short") | pl.col("neg_short")).then(-pl.col("target_nsx_15m") * 10000 - 1.5)
          .otherwise(0)).alias("pnl_bps")
    )
    
    results = df.filter(pl.col("pos_long") | pl.col("pos_short") | pl.col("neg_long") | pl.col("neg_short"))
    if len(results) > 0:
        print(f"\n>>> REGIME-AWARE CONSENSUS RESULTS (OOS 2025) <<<")
        print(f"  Trades:       {len(results)}")
        print(f"  Win Rate:     {(results['pnl_bps'] > 0).mean()*100:.2f}%")
        print(f"  Avg PnL:      {results['pnl_bps'].mean():.3f} bps")
        print(f"  Total PnL:    {results['pnl_bps'].sum():.2f} bps")
        
        # Sub-stats
        pos_reg = results.filter(pl.col("macro_regime_corr") > CORR_THRESHOLD)
        neg_reg = results.filter(pl.col("macro_regime_corr") < -CORR_THRESHOLD)
        
        if len(pos_reg) > 0: print(f"  (+) Regime PnL: {pos_reg['pnl_bps'].mean():.3f} bps ({len(pos_reg)} trades)")
        if len(neg_reg) > 0: print(f"  (-) Regime PnL: {neg_reg['pnl_bps'].mean():.3f} bps ({len(neg_reg)} trades)")

if __name__ == "__main__":
    run_regime_aware_consensus()
