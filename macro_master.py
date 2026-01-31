import polars as pl
import numpy as np
import os

def run_macro_master(dataset_path):
    if not os.path.exists(dataset_path):
        print(f"Dataset {dataset_path} missing.")
        return
        
    df = pl.read_parquet(dataset_path)
    nodes = ['NSXUSD', 'SPXUSD', 'EURUSD', 'GBPUSD', 'USDJPY', 'USDCHF', 'AUDUSD', 'USDCAD', 'XAUUSD']
    anchors = [n for n in nodes if n != 'NSXUSD']
    
    # 1. Base Metrics
    df = df.with_columns([
        pl.sum_horizontal([(pl.col(f"{a}_ret_1m") > 0).cast(pl.Int32) for a in anchors]).alias("consensus_up"),
        pl.sum_horizontal([(pl.col(f"{a}_ret_1m") < 0).cast(pl.Int32) for a in anchors]).alias("consensus_down"),
        pl.col("timestamp").dt.hour().alias("hour_utc"),
        pl.col("NSXUSD_vol_30m").alias("vol")
    ])
    
    # 2. Strategy Parameters
    CONSENSUS_GO = 7
    NSX_QUIET = 0.2 / 10000        # Sentinel filter
    SLINGSHOT_DIV = 1.0 / 10000    # Slingshot 'Deep Coil' filter
    SPREAD = 1.5
    
    # 3. Strategy Logic
    # [A] SURGICAL SENTINEL (Follow the consensus)
    df = df.with_columns(
        (
            (pl.col("hour_utc").is_between(12, 19)) & 
            ((pl.col("vol") < 1.0) | (pl.col("vol") > 5.0))
        ).alias("sentinel_gate")
    )
    
    df = df.with_columns([
        ((pl.col("sentinel_gate")) & (pl.col("consensus_up") >= CONSENSUS_GO) & (pl.col("NSXUSD_ret_1m").abs() < NSX_QUIET)).alias("sentinel_long"),
        ((pl.col("sentinel_gate")) & (pl.col("consensus_down") >= CONSENSUS_GO) & (pl.col("NSXUSD_ret_1m").abs() < NSX_QUIET)).alias("sentinel_short")
    ])
    
    # [B] NASDAQ SLINGSHOT (Fade the divergence)
    df = df.with_columns(
        (pl.col("hour_utc").is_between(12, 20)).alias("slingshot_gate")
    )
    
    df = df.with_columns([
        ((pl.col("slingshot_gate")) & (pl.col("consensus_up") >= CONSENSUS_GO) & (pl.col("NSXUSD_ret_1m") < -SLINGSHOT_DIV)).alias("slingshot_long"),
        ((pl.col("slingshot_gate")) & (pl.col("consensus_down") >= CONSENSUS_GO) & (pl.col("NSXUSD_ret_1m") > SLINGSHOT_DIV)).alias("slingshot_short")
    ])
    
    # 4. Evaluation
    df = df.with_columns([
        # Sentinel PnL
        (pl.when(pl.col("sentinel_long")).then(pl.col("target_nsx_15m") * 10000 - SPREAD)
          .when(pl.col("sentinel_short")).then(-pl.col("target_nsx_15m") * 10000 - SPREAD)
          .otherwise(0)).alias("pnl_sentinel"),
          
        # Slingshot PnL
        (pl.when(pl.col("slingshot_long")).then(pl.col("target_nsx_15m") * 10000 - SPREAD)
          .when(pl.col("slingshot_short")).then(-pl.col("target_nsx_15m") * 10000 - SPREAD)
          .otherwise(0)).alias("pnl_slingshot")
    ])
    
    # Combined Portfolio (No overlapping trades allowed for simplicity - Sentinel takes priority)
    df = df.with_columns(
        (pl.col("pnl_sentinel") + (pl.when(pl.col("pnl_sentinel") == 0).then(pl.col("pnl_slingshot")).otherwise(0))).alias("pnl_combined")
    )
    
    # 5. Report
    print(f"\n>>> MACRO MASTER PORTFOLIO: {dataset_path} <<<")
    
    for strategy in ["sentinel", "slingshot", "combined"]:
        pnl_col = f"pnl_{strategy}"
        res = df.filter(pl.col(pnl_col) != 0)
        if len(res) > 0:
            print(f"  {strategy.upper():<10} | Trades: {len(res):<5} | Win: {(res[pnl_col]>0).mean()*100:>5.2f}% | Avg: {res[pnl_col].mean():>8.3f} bps")
        else:
            print(f"  {strategy.upper():<10} | No trades.")

if __name__ == "__main__":
    import sys
    paths = sys.argv[1:] if len(sys.argv) > 1 else ["graph_dataset_1m_2025.parquet"]
    for p in paths:
        run_macro_master(p)
