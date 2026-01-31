import polars as pl
import numpy as np
import os

def run_momentum_anchor_audit(dataset_path):
    if not os.path.exists(dataset_path): return
    df = pl.read_parquet(dataset_path)
    
    print(f"\n>>> MOMENTUM ANCHOR AUDIT FOR {dataset_path} <<<")
    
    # 1. Align and Filter Day session
    df = df.with_columns(
        pl.col("timestamp").dt.date().alias("date"),
        pl.col("timestamp").dt.hour().alias("hour_utc"),
        pl.col("timestamp").dt.minute().alias("min_utc")
    )
    
    # Calculate 4-hour return (London trend)
    # We'll just use the price at 13:30 vs price at 09:30
    
    def get_price_at(hour, minute, df):
        # Find the first row in each day that matches the hour/minute
        return df.filter((pl.col("hour_utc") == hour) & (pl.col("min_utc") == minute)).select(["date", "NSXUSD_mid"]).rename({"NSXUSD_mid": f"price_{hour}_{minute}"})

    p_09_30 = get_price_at(9, 30, df)
    p_13_30 = get_price_at(13, 30, df)
    p_16_30 = get_price_at(16, 30, df)
    
    # Join them by date
    df_day = p_09_30.join(p_13_30, on="date").join(p_16_30, on="date")
    
    if len(df_day) == 0:
        print("No paired days found. Checking coverage...")
        print(f"09:30 count: {len(p_09_30)}, 13:30 count: {len(p_13_30)}, 16:30 count: {p_16_30.len()}")
        return

    df_day = df_day.with_columns([
        (pl.col("price_13_30").log() - pl.col("price_9_30").log()).alias("london_trend"),
        (pl.col("price_16_30").log() - pl.col("price_13_30").log()).alias("ny_target")
    ])
    
    print(f"Paired Days: {len(df_day)}")
    print(f"{'London Trend (bps)':<20} | {'Trades':<8} | {'Win Rate':<10} | {'Avg PnL (Net)':<15}")
    print("-" * 75)
    
    for tr in [0, 10, 25, 50]:
        t = tr / 10000
        
        # Strategy: Continuation
        df_strat = df_day.with_columns(
            (pl.when(pl.col("london_trend") > t).then(pl.col("ny_target") * 10000 - 1.5)
              .when(pl.col("london_trend") < -t).then(-pl.col("ny_target") * 10000 - 1.5)
              .otherwise(0)).alias("pnl")
        )
        
        res = df_strat.filter(pl.col("pnl") != 0)
        label = f"T > {tr} bps (Cont)"
        if len(res) > 0:
            print(f"{label:<20} | {len(res):<8} | { (res['pnl'] > 0).mean()*100:>8.2f}% | {res['pnl'].mean():>8.3f} bps")

if __name__ == "__main__":
    for y in ["2023", "2024", "2025"]:
        run_momentum_anchor_audit(f"graph_dataset_1m_{y}.parquet")
