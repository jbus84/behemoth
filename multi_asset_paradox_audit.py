import polars as pl
import numpy as np
import os

def audit_multi_asset_paradox(dataset_path):
    if not os.path.exists(dataset_path): return
    df = pl.read_parquet(dataset_path)
    nodes = ['NSXUSD', 'SPXUSD', 'EURUSD', 'GBPUSD', 'USDJPY', 'USDCHF', 'AUDUSD', 'USDCAD', 'XAUUSD']
    
    print(f"\n>>> MULTI-ASSET PARADOX AUDIT FOR {dataset_path} <<<")
    print(f"{'Target Asset':<12} | {'Trades':<8} | {'Win Rate':<10} | {'Avg Pnl (Net)':<15}")
    print("-" * 60)
    
    for target in ['SPXUSD', 'XAUUSD', 'EURUSD']:
        anchors = [n for n in nodes if n != target]
        
        # 1. Macro Signal Engine (Sign alignment needs to be careful for USD-base)
        # For simplicity, we use the consensus logic from paradox_sentinel.py
        def is_usd_up(pair, ret_col):
            if pair in ['EURUSD', 'GBPUSD', 'AUDUSD', 'XAUUSD', 'NSXUSD', 'SPXUSD']: # Treat indices as "Quotes" for USD Strength context
                return (pl.col(ret_col) < 0).cast(pl.Int32)
            else:
                return (pl.col(ret_col) > 0).cast(pl.Int32)

        # Simplified consensus: just how many move in UNISON (abs sign)
        # Actually, let's stick to the exact logic that worked for NSX:
        # Just count how many assets move UP vs how many move DOWN (raw price).
        # This worked because most anchors in our 8-set are positively correlated to NSX (USDJPY/USDCHF/USDCAD are inv).
        
        df = df.with_columns([
            pl.sum_horizontal([(pl.col(f"{a}_ret_1m") > 0).cast(pl.Int32) for a in anchors]).alias("consensus_up"),
            pl.sum_horizontal([(pl.col(f"{a}_ret_1m") < 0).cast(pl.Int32) for a in anchors]).alias("consensus_down"),
            pl.mean_horizontal([pl.col(f"{a}_ret_1m").abs() for a in anchors]).alias("macro_energy")
        ])
        
        ENERGY_MIN = 2.0 / 10000
        STALL_THR = 0.1 / 10000
        CONSENSUS_GO = 7
        
        # Spread adjustment
        spread = 1.5 if target in ['SPXUSD'] else 0.5
        if target == 'XAUUSD': spread = 2.0
            
        # Target 15m return
        df = df.with_columns(
            (pl.col(f"{target}_mid").shift(-15).log() - pl.col(f"{target}_mid").log()).alias("temp_target")
        )

        df = df.with_columns([
            (
                (pl.col("consensus_up") >= CONSENSUS_GO) & 
                (pl.col("macro_energy") > ENERGY_MIN) & 
                (pl.col(f"{target}_ret_1m").abs() < STALL_THR)
            ).alias("sig_long"),
            (
                (pl.col("consensus_down") >= CONSENSUS_GO) & 
                (pl.col("macro_energy") > ENERGY_MIN) & 
                (pl.col(f"{target}_ret_1m").abs() < STALL_THR)
            ).alias("sig_short")
        ])
        
        df = df.with_columns(
            (pl.when(pl.col("sig_long")).then(pl.col("temp_target") * 10000 - spread)
              .when(pl.col("sig_short")).then(-pl.col("temp_target") * 10000 - spread)
              .otherwise(0)).alias("pnl")
        )
        
        res = df.filter(pl.col("pnl") != 0)
        if len(res) > 0:
            print(f"{target:<12} | {len(res):<8} | { (res['pnl'] > 0).mean()*100:>8.2f}% | {res['pnl'].mean():>8.3f} bps")
        else:
            print(f"{target:<12} | 0        | N/A        | N/A")

if __name__ == "__main__":
    for y in ["2023", "2024", "2025"]:
        audit_multi_asset_paradox(f"graph_dataset_1m_{y}.parquet")
