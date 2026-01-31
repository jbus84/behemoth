import polars as pl
import numpy as np
import os

def run_consensus_arbiter():
    dataset_path = "graph_dataset_1m_2025.parquet"
    if not os.path.exists(dataset_path): return
        
    df = pl.read_parquet(dataset_path)
    nodes = ['NSXUSD', 'SPXUSD', 'EURUSD', 'GBPUSD', 'USDJPY', 'USDCHF', 'AUDUSD', 'USDCAD', 'XAUUSD']
    anchors = [n for n in nodes if n != 'NSXUSD']
    
    print(">>> RUNNING THE CONSENSUS ARBITER MODEL (2025 OOS) <<<")
    
    # 1. Base Metrics
    df = df.with_columns([
        # Consensus
        pl.sum_horizontal([(pl.col(f"{a}_ret_1m") > 0).cast(pl.Int32) for a in anchors]).alias("consensus_up"),
        pl.sum_horizontal([(pl.col(f"{a}_ret_1m") < 0).cast(pl.Int32) for a in anchors]).alias("consensus_down"),
        # Regime Factors
        pl.col("timestamp").dt.hour().alias("hour_utc"),
        pl.col("NSXUSD_vol_30m").alias("vol"),
        pl.mean_horizontal([pl.col(f"{a}_ret_1m") for a in anchors]).alias("avg_anchor_ret")
    ])
    
    # 2. Rolling Correlation (Regime Detection)
    df = df.with_columns(
        pl.rolling_corr(pl.col("NSXUSD_ret_1m"), pl.col("avg_anchor_ret"), window_size=60).alias("macro_regime_corr")
    )
    
    # 3. Surgical Gating (From Phase 5 Discovery)
    # Time: 14-19 UTC | Vol: Extremes
    df = df.with_columns(
        (
            (pl.col("hour_utc").is_between(14, 19)) & 
            ((pl.col("vol") < 1.0) | (pl.col("vol") > 5.0))
        ).alias("market_fit")
    )
    
    CONSENSUS_GO = 7
    CORR_THRESHOLD = 0.3
    NSX_QUIET = 0.2 / 10000
    
    # 4. Arbitration Logic
    df = df.with_columns([
        # Trend Regime: Go with Macros
        ((pl.col("market_fit")) & (pl.col("macro_regime_corr") > CORR_THRESHOLD) & (pl.col("consensus_up") >= CONSENSUS_GO) & (pl.col("NSXUSD_ret_1m").abs() < NSX_QUIET)).alias("signal_long_trend"),
        ((pl.col("market_fit")) & (pl.col("macro_regime_corr") > CORR_THRESHOLD) & (pl.col("consensus_down") >= CONSENSUS_GO) & (pl.col("NSXUSD_ret_1m").abs() < NSX_QUIET)).alias("signal_short_trend"),
        
        # Fading Regime: Go against Macros
        ((pl.col("market_fit")) & (pl.col("macro_regime_corr") < -CORR_THRESHOLD) & (pl.col("consensus_up") >= CONSENSUS_GO) & (pl.col("NSXUSD_ret_1m").abs() < NSX_QUIET)).alias("signal_short_fade"),
        ((pl.col("market_fit")) & (pl.col("macro_regime_corr") < -CORR_THRESHOLD) & (pl.col("consensus_down") >= CONSENSUS_GO) & (pl.col("NSXUSD_ret_1m").abs() < NSX_QUIET)).alias("signal_long_fade")
    ])
    
    # 5. Evaluation (15m horizon)
    df = df.with_columns(
        (pl.when(pl.col("signal_long_trend") | pl.col("signal_long_fade")).then(pl.col("target_nsx_15m") * 10000 - 1.5)
          .when(pl.col("signal_short_trend") | pl.col("signal_short_fade")).then(-pl.col("target_nsx_15m") * 10000 - 1.5)
          .otherwise(0)).alias("pnl_bps")
    )
    
    results = df.filter(pl.col("pnl_bps") != 0)
    if len(results) > 0:
        print(f"\n>>> CONSENSUS ARBITER RESULTS <<<")
        print(f"  Trades:       {len(results)}")
        print(f"  Win Rate:     {(results['pnl_bps'] > 0).mean()*100:.2f}%")
        print(f"  Avg PnL:      {results['pnl_bps'].mean():.3f} bps")
        print(f"  Total PnL:    {results['pnl_bps'].sum():.2f} bps")
        
        trend_res = results.filter(pl.col("macro_regime_corr") > CORR_THRESHOLD)
        fade_res = results.filter(pl.col("macro_regime_corr") < -CORR_THRESHOLD)
        
        if len(trend_res) > 0: print(f"  (+) Trend Mode: {trend_res['pnl_bps'].mean():.3f} bps ({len(trend_res)})")
        if len(fade_res) > 0: print(f"  (-) Fade Mode:  {fade_res['pnl_bps'].mean():.3f} bps ({len(fade_res)})")
        
    return df

if __name__ == "__main__":
    run_consensus_arbiter()
