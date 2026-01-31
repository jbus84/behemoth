import polars as pl
import numpy as np
import os

def run_cross_currency_lead():
    dataset_path = "graph_dataset_1m_2025.parquet"
    if not os.path.exists(dataset_path): return
        
    df = pl.read_parquet(dataset_path)
    # USD Majors as Leaders
    leaders = ['EURUSD', 'GBPUSD', 'USDJPY', 'USDCHF', 'AUDUSD', 'USDCAD']
    
    # We need to calculate EURJPY mid from the components if missing,
    # but let's assume we want to predict a cross that is already in our set.
    # Wait, my nodes only have USD majors + Indices + Gold.
    
    # I don't have EURJPY in the graph_dataset_1m_2025.
    
    # NEW IDEA: Use the 5 USD pairs to predict the 6th.
    # Prediction of 'The Laggard' in the USD Basket.
    
    print(">>> AUDITING USD BASKET LAGS (WHICH USD PAIR IS SLOWEST?) <<<")
    
    usd_majors = ['EURUSD', 'GBPUSD', 'USDJPY', 'USDCHF', 'AUDUSD', 'USDCAD']
    
    for target in usd_majors:
        anchors = [p for p in usd_majors if p != target]
        
        # Consistent USD Direction:
        # USD up = USDJPY up, USDCHF up, USDCAD up
        # USD up = EURUSD down, GBPUSD down, AUDUSD down
        
        df = df.with_columns([
            pl.sum_horizontal([
                (pl.col("EURUSD_ret_1m") < 0).cast(pl.Int32),
                (pl.col("GBPUSD_ret_1m") < 0).cast(pl.Int32),
                (pl.col("AUDUSD_ret_1m") < 0).cast(pl.Int32),
                (pl.col("USDJPY_ret_1m") > 0).cast(pl.Int32),
                (pl.col("USDCHF_ret_1m") > 0).cast(pl.Int32),
                (pl.col("USDCAD_ret_1m") > 0).cast(pl.Int32)
            ]).alias("usd_strength_consensus")
        ])
        
        # The above logic counts the Target too. Let's fix it.
        # Consensus of OTHER 5
        def is_usd_up(pair, ret_col):
            if pair in ['EURUSD', 'GBPUSD', 'AUDUSD']:
                return (pl.col(ret_col) < 0).cast(pl.Int32)
            else:
                return (pl.col(ret_col) > 0).cast(pl.Int32)
                
        df = df.with_columns(
            pl.sum_horizontal([is_usd_up(p, f"{p}_ret_1m") for p in anchors]).alias("consensus_up"),
            pl.sum_horizontal([(1 - is_usd_up(p, f"{p}_ret_1m")) for p in anchors]).alias("consensus_down")
        )
        
        # Target: 15m return (aligned to USD direction)
        # For EURUSD, USD up => EURUSD down.
        if target in ['EURUSD', 'GBPUSD', 'AUDUSD']:
            df = df.with_columns(
                (pl.col(f"{target}_mid").shift(-15).log() - pl.col(f"{target}_mid").log()).alias("target_ret")
            )
            # Signal UP (USD Strength) => Target DOWN
            df = df.with_columns(
                (pl.when(pl.col("consensus_up") >= 5).then(-pl.col("target_ret") * 10000 - 0.5)
                  .when(pl.col("consensus_down") >= 5).then(pl.col("target_ret") * 10000 - 0.5)
                  .otherwise(0)).alias("pnl")
            )
        else:
             df = df.with_columns(
                (pl.col(f"{target}_mid").shift(-15).log() - pl.col(f"{target}_mid").log()).alias("target_ret")
            )
             # Signal UP (USD Strength) => Target UP
             df = df.with_columns(
                (pl.when(pl.col("consensus_up") >= 5).then(pl.col("target_ret") * 10000 - 0.5)
                  .when(pl.col("consensus_down") >= 5).then(-pl.col("target_ret") * 10000 - 0.5)
                  .otherwise(0)).alias("pnl")
            )
             
        res = df.filter(pl.col("pnl") != 0)
        if len(res) > 0:
            print(f"Target: {target:<10} | Win: {(res['pnl']>0).mean()*100:>5.2f}% | Avg: {res['pnl'].mean():>8.3f} bps | Trades: {len(res)}")

if __name__ == "__main__":
    run_cross_currency_lead()
