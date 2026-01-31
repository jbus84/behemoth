import polars as pl
import numpy as np
import os

def run_pairwise_lead_audit():
    dataset_path = "graph_dataset_1m_2025.parquet"
    if not os.path.exists(dataset_path): return
        
    df = pl.read_parquet(dataset_path)
    nodes = ['NSXUSD', 'SPXUSD', 'EURUSD', 'GBPUSD', 'USDJPY', 'USDCHF', 'AUDUSD', 'USDCAD', 'XAUUSD']
    
    threshold = 1.0 / 10000
    results = []
    
    print(">>> AUDITING ALL PAIRWISE LEAD-LAG COMBINATIONS (2025 OOS) <<<")
    
    for lead in nodes:
        for lag in nodes:
            if lead == lag: continue
            
            # 1. Lead Event
            df = df.with_columns([
                (pl.col(f"{lead}_ret_1m") > threshold).alias("sig_up"),
                (pl.col(f"{lead}_ret_1m") < -threshold).alias("sig_down")
            ])
            
            # 2. Lag PnL (15m window)
            # Define specific spread for the lag asset
            spread = 1.5
            if "USD" in lag and lag not in ["NSXUSD", "SPXUSD"]: spread = 0.5
            if lag == "XAUUSD": spread = 2.0
            
            df = df.with_columns(
                (pl.when(pl.col("sig_up")).then( (pl.col(f"{lag}_mid").shift(-15).log() - pl.col(f"{lag}_mid").log()) * 10000 - spread)
                  .when(pl.col("sig_down")).then(-(pl.col(f"{lag}_mid").shift(-15).log() - pl.col(f"{lag}_mid").log()) * 10000 - spread)
                  .otherwise(None)).alias("pnl")
            )
            
            res = df.filter(pl.col("pnl").is_not_null())
            if len(res) > 0:
                win_rate = (res["pnl"] > 0).mean()
                avg_pnl = res["pnl"].mean()
                results.append({
                    "Lead": lead,
                    "Lag": lag,
                    "Trades": len(res),
                    "WinRate": win_rate,
                    "AvgPnL": avg_pnl
                })
                
    # Sort and show Top 10
    top = sorted(results, key=lambda x: x["AvgPnL"], reverse=True)[:10]
    
    print("\n>>> TOP 10 MACRO LEAD RELATIONSHIPS <<<")
    print(f"{'Lead Asset':<10} -> {'Lag Asset':<10} | {'Trades':<8} | {'Win Rate':<10} | {'Avg PnL':<10}")
    print("-" * 65)
    for r in top:
        print(f"{r['Lead']:<10} -> {r['Lag']:<10} | {r['Trades']:<8} | {r['WinRate']:>8.2f}% | {r['AvgPnL']:>8.3f} bps")

if __name__ == "__main__":
    run_pairwise_lead_audit()
