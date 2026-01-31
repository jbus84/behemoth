import polars as pl
import os
from pathlib import Path

def create_graph_dataset(idx_root, fx_root, year, output_file):
    print(f"\n>>> BUILDING MACRO-LIQUIDITY GRAPH DATASET ({year}) <<<")
    
    # Universe (9 Nodes)
    nodes = ["NSXUSD", "SPXUSD", "EURUSD", "GBPUSD", "USDJPY", "USDCHF", "AUDUSD", "USDCAD", "XAUUSD"]
    
    months = [f"{year}{m:02d}" for m in range(1, 13)]
    all_chunks = []
    
    for ym in months:
        print(f"  Processing {ym}...")
        dfs = {}
        min_ts, max_ts = None, None
        valid = True
        
        for asset in nodes:
            path = Path(fx_root) / asset / f"{asset}_{ym}_ticks.parquet"
            if not path.exists():
                 path = Path(idx_root) / asset / f"{asset}_{ym}_ticks.parquet"
                 if not path.exists():
                     print(f"    Missing {asset} for {ym}. Skipping year.")
                     valid = False
                     break
            
            df = pl.read_parquet(path).select(["timestamp", "mid", "ask", "bid"]).sort("timestamp")
            if min_ts is None or df["timestamp"].min() < min_ts: min_ts = df["timestamp"].min()
            if max_ts is None or df["timestamp"].max() > max_ts: max_ts = df["timestamp"].max()
            dfs[asset] = df
            
        if not valid: continue
        
        grid = pl.datetime_range(min_ts, max_ts, "1m", eager=True).to_frame("timestamp").with_columns(
            pl.col("timestamp").dt.cast_time_unit("ns")
        )
        
        master = grid
        for asset in nodes:
            node_df = dfs[asset].with_columns(
                ((pl.col("ask") - pl.col("bid")) / pl.col("mid") * 10000).alias(f"{asset}_spread")
            ).select(["timestamp", "mid", f"{asset}_spread"]).rename({"mid": f"{asset}_mid"})
            master = master.join_asof(node_df, on="timestamp", strategy="backward")
            
        master = master.drop_nulls()
        
        for asset in nodes:
            px = f"{asset}_mid"
            master = master.with_columns([
                (pl.col(px).log() - pl.col(px).shift(1).log()).alias(f"{asset}_ret_1m"),
                (pl.col(px).log() - pl.col(px).shift(15).log()).alias(f"{asset}_ret_15m"),
                (pl.col(px).log() - pl.col(px).shift(60).log()).alias(f"{asset}_ret_1h"),
                (pl.col(px).log() - pl.col(px).shift(240).log()).alias(f"{asset}_ret_4h"),
                (pl.col(px).pct_change().rolling_std(30).fill_null(0) * 10000).alias(f"{asset}_vol_30m"),
                ((pl.col(px) / pl.col(px).rolling_mean(200).fill_null(pl.col(px)) - 1) * 10000).alias(f"{asset}_dist_ma_200")
            ])
            
        master = master.drop_nulls()
        
        master = master.with_columns([
            (pl.col("NSXUSD_mid").shift(-15).log() - pl.col("NSXUSD_mid").log()).alias("target_nsx_15m"),
            (pl.col("SPXUSD_mid").shift(-15).log() - pl.col("SPXUSD_mid").log()).alias("target_spx_15m")
        ]).drop_nulls()
        
        cols = ["timestamp", "target_nsx_15m", "target_spx_15m"]
        for asset in nodes:
            cols.extend([f"{asset}_mid", f"{asset}_ret_1m", f"{asset}_ret_15m", f"{asset}_ret_1h", f"{asset}_ret_4h", f"{asset}_vol_30m", f"{asset}_dist_ma_200", f"{asset}_spread"])
            
        all_chunks.append(master.select(cols))
        
    if all_chunks:
        final = pl.concat(all_chunks)
        final.write_parquet(output_file)
        print(f"Success! {len(final)} rows. Saved to {output_file}")
    else:
        print(f"No data for {year}.")

if __name__ == "__main__":
    import sys
    idx = "/Users/danielfisher/Desktop/tick"
    fx = "/Users/danielfisher/Desktop/tick"
    
    if len(sys.argv) > 1:
        years = sys.argv[1:]
    else:
        years = ["2025"]
        
    for y in years:
        create_graph_dataset(idx, fx, y, f"graph_dataset_1m_{y}.parquet")
