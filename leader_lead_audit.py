import polars as pl
import numpy as np
import os

def run_leader_lead_audit(dataset_path):
    if not os.path.exists(dataset_path): return
    df = pl.read_parquet(dataset_path)
    nodes = ['SPXUSD', 'EURUSD', 'GBPUSD', 'USDJPY', 'USDCHF', 'AUDUSD', 'USDCAD', 'XAUUSD']
    
    print(f"\n>>> LEADER LEAD-NY AUDIT FOR {dataset_path} <<<")
    
    df = df.with_columns(
        pl.col("timestamp").dt.date().alias("date"),
        pl.col("timestamp").dt.hour().alias("hour_utc"),
        pl.col("timestamp").dt.minute().alias("min_utc")
    )
    
    # 1. Capture snapshots
    def get_snaps(asset_list, df):
        df_snaps = None
        for asset in asset_list:
            p_09_30 = df.filter((pl.col("hour_utc") == 9) & (pl.col("min_utc") == 30)).select(["date", f"{asset}_mid"]).rename({f"{asset}_mid": f"{asset}_09_30"})
            p_13_30 = df.filter((pl.col("hour_utc") == 13) & (pl.col("min_utc") == 30)).select(["date", f"{asset}_mid"]).rename({f"{asset}_mid": f"{asset}_13_30"})
            snap = p_09_30.join(p_13_30, on="date")
            if df_snaps is None: df_snaps = snap
            else: df_snaps = df_snaps.join(snap, on="date")
        return df_snaps

    # Add NSX 13:30 and 16:30 for target
    df_snaps = get_snaps(nodes, df)
    p_nsx_13_30 = df.filter((pl.col("hour_utc") == 13) & (pl.col("min_utc") == 30)).select(["date", "NSXUSD_mid"]).rename({"NSXUSD_mid": "nsx_13_30"})
    p_nsx_15_30 = df.filter((pl.col("hour_utc") == 15) & (pl.col("min_utc") == 30)).select(["date", "NSXUSD_mid"]).rename({"NSXUSD_mid": "nsx_15_30"})
    
    df_final = df_snaps.join(p_nsx_13_30, on="date").join(p_nsx_15_30, on="date")
    
    df_final = df_final.with_columns(
        (pl.col("nsx_15_30").log() - pl.col("nsx_13_30").log()).alias("target_bps")
    )
    
    print(f"{'Leader':<10} | {'Trades':<8} | {'Win Rate':<10} | {'Avg PnL (Net)':<15}")
    print("-" * 65)
    
    for leader in nodes:
        # USD Alignment
        if leader in ['EURUSD', 'GBPUSD', 'AUDUSD', 'XAUUSD', 'SPXUSD']:
            df_final = df_final.with_columns(
                (pl.col(f"{leader}_09_30").log() - pl.col(f"{leader}_13_30").log()).alias(f"{leader}_lead") # Note: Inverse for USD strength
            )
        else:
            df_final = df_final.with_columns(
                (pl.col(f"{leader}_13_30").log() - pl.col(f"{leader}_09_30").log()).alias(f"{leader}_lead")
            )
            
        # Strategy: Continuation (Follow the London USD direction)
        # Threshold: 20 bps on leader
        t = 20 / 10000
        df_strat = df_final.with_columns(
            (pl.when(pl.col(f"{leader}_lead") > t).then(pl.col("target_bps") * 10000 - 1.5) # Lead up (USD strong) -> We expect Assets down (Short NSX)
              .when(pl.col(f"{leader}_lead") < -t).then(-pl.col("target_bps") * 10000 - 1.5) # Lead down (USD weak) -> We expect Assets up (Long NSX)
              .otherwise(0)).alias("pnl")
        )
        
        res = df_strat.filter(pl.col("pnl") != 0)
        if len(res) > 0:
            print(f"{leader:<10} | {len(res):<8} | { (res['pnl'] > 0).mean()*100:>8.2f}% | {res['pnl'].mean():>8.3f} bps")

if __name__ == "__main__":
    for y in ["2023", "2024", "2025"]:
        run_leader_lead_audit(f"graph_dataset_1m_{y}.parquet")
