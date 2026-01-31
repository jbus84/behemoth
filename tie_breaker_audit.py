import polars as pl
import numpy as np
import os

def run_tie_breaker_audit(dataset_path):
    if not os.path.exists(dataset_path): return
    df = pl.read_parquet(dataset_path)
    
    # Anchors excluding indices
    ghost_anchors = ['EURUSD', 'GBPUSD', 'USDJPY', 'USDCHF', 'AUDUSD', 'USDCAD', 'XAUUSD']
    
    print(f"\n>>> GHOST ANCHOR TIE-BREAKER AUDIT FOR {dataset_path} <<<")
    
    # 1. Index Divergence (15m)
    # NSX is "Lagging" or "Leading" SPX
    df = df.with_columns(
        (pl.col("NSXUSD_ret_15m") - pl.col("SPXUSD_ret_15m")).alias("nsx_spx_div")
    )
    
    # 2. Ghost Consensus (1m or 15m?)
    # Let's check 1m consensus of the ghosts as a high-frequency tie-breaker.
    def usd_ret(pair, df):
        if pair in ['EURUSD', 'GBPUSD', 'AUDUSD', 'XAUUSD']: return -pl.col(f"{pair}_ret_1m")
        else: return pl.col(f"{pair}_ret_1m")
        
    df = df.with_columns([
        usd_ret(a, df).alias(f"{a}_usd") for a in ghost_anchors
    ])
    
    df = df.with_columns([
        pl.sum_horizontal([(pl.col(f"{a}_usd") > 0).cast(pl.Int32) for a in ghost_anchors]).alias("ghost_up"),
        pl.sum_horizontal([(pl.col(f"{a}_usd") < 0).cast(pl.Int32) for a in ghost_anchors]).alias("ghost_down")
    ])
    
    print(f"{'Condition':<25} | {'Trades':<8} | {'Win Rate':<10} | {'Avg PnL (Net)':<15}")
    print("-" * 75)
    
    # Strategy: IF NSX vs SPX Div > 5 bps (Nasdaq is 'too weak' relative to SPX)
    # AND Ghost Consensus is UP (7/7) (Broad USD Strength -> Bearish for Assets)
    # Then SPX is "Wrong" and NSX is "Right" -> We SHORT NSX (Momentum continuation)
    # OR: IF Ghost Consensus is DOWN (7/7) (Broad USD Weakness -> Bullish)
    # Then NSX is "Right" and SPX is "Wrong" -> We LONG NSX (Realignment to SPX)
    
    for div_thr_bps in [5.0, 10.0]:
        t = div_thr_bps / 10000
        
        # Case 1: NSX is Weak relative to SPX, Ghosts confirm Weakness (Short Continuation)
        df_sig = df.with_columns([
            ((pl.col("nsx_spx_div") < -t) & (pl.col("ghost_up") >= 6)).alias("sig_confirm_short"),
            ((pl.col("nsx_spx_div") > t) & (pl.col("ghost_down") >= 6)).alias("sig_confirm_long")
        ])
        
        # Case 2: NSX is Weak relative to SPX, Ghosts signal Strength (Long Snap back to SPX)
        df_sig = df_sig.with_columns([
            ((pl.col("nsx_spx_div") < -t) & (pl.col("ghost_down") >= 6)).alias("sig_snap_up"),
            ((pl.col("nsx_spx_div") > t) & (pl.col("ghost_up") >= 6)).alias("sig_snap_down")
        ])
        
        # Test Case 2 (Snap back to Index Consensus)
        df_strat = df_sig.with_columns(
            (pl.when(pl.col("sig_snap_up")).then(pl.col("target_nsx_15m") * 10000 - 1.5)
              .when(pl.col("sig_snap_down")).then(-pl.col("target_nsx_15m") * 10000 - 1.5)
              .otherwise(0)).alias("pnl")
        )
        
        res = df_strat.filter(pl.col("pnl") != 0)
        label = f"Div={div_thr_bps} Snap (Case 2)"
        if len(res) > 0:
            print(f"{label:<25} | {len(res):<8} | { (res['pnl'] > 0).mean()*100:>8.2f}% | {res['pnl'].mean():>8.3f} bps")
            
        # Test Case 1 (Follow the Breakaway)
        df_strat = df_sig.with_columns(
            (pl.when(pl.col("sig_confirm_short")).then(-pl.col("target_nsx_15m") * 10000 - 1.5)
              .when(pl.col("sig_confirm_long")).then(pl.col("target_nsx_15m") * 10000 - 1.5)
              .otherwise(0)).alias("pnl")
        )
        
        res = df_strat.filter(pl.col("pnl") != 0)
        label = f"Div={div_thr_bps} Follow (Case 1)"
        if len(res) > 0:
            print(f"{label:<25} | {len(res):<8} | { (res['pnl'] > 0).mean()*100:>8.2f}% | {res['pnl'].mean():>8.3f} bps")

if __name__ == "__main__":
    for y in ["2023", "2024", "2025"]:
        run_tie_breaker_audit(f"graph_dataset_1m_{y}.parquet")
