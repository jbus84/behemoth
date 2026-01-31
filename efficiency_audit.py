import polars as pl
import numpy as np
import os

def run_spread_efficiency_audit(dataset_path):
    if not os.path.exists(dataset_path): return
    df = pl.read_parquet(dataset_path)
    nodes = ['NSXUSD', 'SPXUSD', 'EURUSD', 'GBPUSD', 'USDJPY', 'USDCHF', 'AUDUSD', 'USDCAD', 'XAUUSD']
    
    print(f"\n>>> SPREAD EFFICIENCY AUDIT FOR {dataset_path} <<<")
    print(f"{'Asset':<10} | {'Spread (bps)':<12} | {'15m Vol (bps)':<15} | {'Alpha Buffer (Vol/Cost)':<20}")
    print("-" * 75)
    
    for a in nodes:
        # Volatility in bps
        vol = df[f"{a}_vol_30m"].mean() # Using 30m vol as proxy for 15m move magnitude (sqrt link)
        
        # Real-world CFD spreads (Standard)
        spread_map = {
            'NSXUSD': 1.5, 'SPXUSD': 1.5,
            'EURUSD': 0.5, 'GBPUSD': 0.6, 'USDJPY': 0.5,
            'USDCHF': 0.8, 'AUDUSD': 0.6, 'USDCAD': 0.7,
            'XAUUSD': 2.0
        }
        cost = spread_map[a]
        
        buffer = vol / cost
        print(f"{a:<10} | {cost:<12} | {vol:<15.3f} | {buffer:<20.3f}")

if __name__ == "__main__":
    for y in ["2023", "2024", "2025"]:
        run_spread_efficiency_audit(f"graph_dataset_1m_{y}.parquet")
