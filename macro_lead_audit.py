import polars as pl
import numpy as np
import os

def run_lead_audit():
    dataset_path = "graph_dataset_1m_2025.parquet"
    if not os.path.exists(dataset_path): return
        
    df = pl.read_parquet(dataset_path)
    nodes = ['NSXUSD', 'SPXUSD', 'EURUSD', 'GBPUSD', 'USDJPY', 'USDCHF', 'AUDUSD', 'USDCAD', 'XAUUSD']
    anchors = [n for n in nodes if n != 'NSXUSD']
    
    print(">>> AUDITING MACRO LEADERS FOR NASDAQ (NSX)...")
    
    # We want to see: If Anchor[t] moves > 1bps, what is P(NSX[t+1:t+15] moves same way)?
    # Threshold for a 'Significant Lead'
    THRESHOLD = 1.0 / 10000 
    
    results = []
    
    for a in anchors:
        # Define the Lead Event
        df = df.with_columns([
            (pl.col(f"{a}_ret_1m") > THRESHOLD).alias(f"{a}_lead_up"),
            (pl.col(f"{a}_ret_1m") < -THRESHOLD).alias(f"{a}_lead_down")
        ])
        
        # Calculate PnL for this specific anchor's signals
        # (Net of 1.5bps spread)
        df = df.with_columns(
            (pl.when(pl.col(f"{a}_lead_up")).then(pl.col("target_nsx_15m") * 10000 - 1.5)
              .when(pl.col(f"{a}_lead_down")).then(-pl.col("target_nsx_15m") * 10000 - 1.5)
              .otherwise(0)).alias(f"{a}_pnl")
        )
        
        trades = df.filter(pl.col(f"{a}_lead_up") | pl.col(f"{a}_lead_down"))
        
        if len(trades) > 0:
            win_rate = (trades[f"{a}_pnl"] > 0).mean()
            avg_pnl = trades[f"{a}_pnl"].mean()
            results.append({
                "Asset": a,
                "Trades": len(trades),
                "WinRate": win_rate * 100,
                "AvgPnL": avg_pnl
            })
            
    # Sort by Avg PnL
    results = sorted(results, key=lambda x: x["AvgPnL"], reverse=True)
    
    print("\n>>> MACRO LEAD RANKINGS (OOS 2025) <<<")
    print(f"{'Asset':<10} | {'Trades':<8} | {'Win Rate':<10} | {'Avg PnL (Net)':<15}")
    print("-" * 55)
    for r in results:
        print(f"{r['Asset']:<10} | {r['Trades']:<8} | {r['WinRate']:>8.2f}% | {r['AvgPnL']:>12.3f} bps")

if __name__ == "__main__":
    run_lead_audit()
