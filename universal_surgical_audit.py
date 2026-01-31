import polars as pl
import numpy as np
import os

def find_universal_surgical_hours():
    paths = {
        "2023": "graph_dataset_1m_2023.parquet",
        "2024": "graph_dataset_1m_2024.parquet",
        "2025": "graph_dataset_1m_2025.parquet"
    }
    
    hour_stats = {}
    
    for year, path in paths.items():
        if not os.path.exists(path): continue
        df = pl.read_parquet(path)
        nodes = ['NSXUSD', 'SPXUSD', 'EURUSD', 'GBPUSD', 'USDJPY', 'USDCHF', 'AUDUSD', 'USDCAD', 'XAUUSD']
        anchors = [n for n in nodes if n != 'NSXUSD']
        
        df = df.with_columns([
            pl.sum_horizontal([(pl.col(f"{a}_ret_1m") > 0).cast(pl.Int32) for a in anchors]).alias("consensus_up"),
            pl.sum_horizontal([(pl.col(f"{a}_ret_1m") < 0).cast(pl.Int32) for a in anchors]).alias("consensus_down"),
            pl.col("timestamp").dt.hour().alias("hour_utc"),
            pl.col("NSXUSD_vol_30m").alias("vol")
        ])
        
        # Surgical Filter: Vol < 1 or Vol > 5
        df = df.with_columns(
            ((pl.col("vol") < 1.0) | (pl.col("vol") > 5.0)).alias("vol_gate")
        )
        
        # Eval 7/8 Consensus in Vol Gate
        df = df.with_columns(
            (pl.when(pl.col("vol_gate") & (pl.col("consensus_up") >= 7)).then(pl.col("target_nsx_15m") * 10000 - 1.5)
              .when(pl.col("vol_gate") & (pl.col("consensus_down") >= 7)).then(-pl.col("target_nsx_15m") * 10000 - 1.5)
              .otherwise(0)).alias("pnl")
        )
        
        # Real signals only
        sig_stats = df.filter(pl.col("pnl") != 0).group_by("hour_utc").agg([
            pl.col("pnl").mean().alias("avg_pnl"),
            pl.len().alias("trades")
        ])
        
        hour_stats[year] = sig_stats
        
    print("\n>>> UNIVERSAL SURGICAL HOURS (VOL-GATED 7/8 CONSENSUS) <<<")
    print(f"{'Hour (UTC)':<12} | {'2023 PnL':<10} | {'2024 PnL':<10} | {'2025 PnL':<10}")
    print("-" * 55)
    
    for h in range(24):
        p23 = hour_stats["2023"].filter(pl.col("hour_utc") == h)["avg_pnl"].to_list()
        p24 = hour_stats["2024"].filter(pl.col("hour_utc") == h)["avg_pnl"].to_list()
        p25 = hour_stats["2025"].filter(pl.col("hour_utc") == h)["avg_pnl"].to_list()
        
        p23 = p23[0] if p23 else -99
        p24 = p24[0] if p24 else -99
        p25 = p25[0] if p25 else -99
        
        if p23 > 0 and p24 > 0 and p25 > 0:
            print(f"{h:<12} | {p23:>8.3f} | {p24:>8.3f} | {p25:>8.3f} (UNIVERSAL ALPHA)")
        elif p23 > 0 or p24 > 0 or p25 > 0:
             print(f"{h:<12} | {p23:>8.3f} | {p24:>8.3f} | {p25:>8.3f}")

if __name__ == "__main__":
    find_universal_surgical_hours()
