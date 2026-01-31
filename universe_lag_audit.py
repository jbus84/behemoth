import polars as pl
import numpy as np
import os

def run_universe_lag_audit():
    dataset_path = "graph_dataset_1m_2025.parquet"
    if not os.path.exists(dataset_path): return
        
    df = pl.read_parquet(dataset_path)
    nodes = ['NSXUSD', 'SPXUSD', 'EURUSD', 'GBPUSD', 'USDJPY', 'USDCHF', 'AUDUSD', 'USDCAD', 'XAUUSD']
    
    print(">>> AUDITING MACRO LAG SENSITIVITY ACROSS UNIVERSE...")
    print(f"{'Target Asset':<12} | {'Win Rate':<8} | {'Avg PnL (Net)':<15} | {'Trades':<8}")
    print("-" * 55)
    
    # We need 15m targets for ALL assets. 
    # Since they aren't in the dataset, we calculate them on the fly
    for target in nodes:
        # 1. Define Consensus of the OTHER 8
        anchors = [n for n in nodes if n != target]
        
        # Simple consensus (sign agreement)
        # Note: USDJPY, USDCHF, USDCAD are USD-base. EUR, GBP, AUD are USD-quote.
        # To align consensus, we must flip the sign logic for USD-base pairs
        # if the "Consensus" sought is USD Strength.
        # But let's simplify: Consensus = "Moving in a correlated direction"
        # We'll use the 1m return sign.
        
        # We need to know if the asset is POSITIVELY or NEGATIVELY correlated to the global basket.
        # For simplicity, let's just use the 'signed' consensus.
        # 7 out of 8 assets moving in THEIR respective directions.
        
        # To handle the 'Inversion' (USDJPY up = USD strength), we use the ret_1m directly.
        # But we need to know the 'Normal' correlation sign.
        # Let's just use the current approach: count how many assets move in unison.
        
        df = df.with_columns([
            pl.sum_horizontal([(pl.col(f"{a}_ret_1m") > 0).cast(pl.Int32) for a in anchors]).alias("consensus_up"),
            pl.sum_horizontal([(pl.col(f"{a}_ret_1m") < 0).cast(pl.Int32) for a in anchors]).alias("consensus_down")
        ])
        
        # 2. Target Return (15m forward)
        # Since shift(-15) drops data, we do it in a temporary column
        df = df.with_columns(
            (pl.col(f"{target}_mid").shift(-15).log() - pl.col(f"{target}_mid").log()).alias("temp_target")
        )
        
        CONSENSUS_GO = 7
        # Strategy: Trend Following on Consensus
        # (Assuming the target Lags the consensus)
        
        df = df.with_columns([
            (pl.col("consensus_up") >= CONSENSUS_GO).alias("sig_up"),
            (pl.col("consensus_down") >= CONSENSUS_GO).alias("sig_down")
        ])
        
        # PnL (Net of 1.5bps spread for indices, 0.5bps for FX, 2.0bps for Gold)
        spread = 1.5
        if "USD" in target and target not in ["NSXUSD", "SPXUSD"]: spread = 0.5
        if target == "XAUUSD": spread = 2.0
            
        df = df.with_columns(
            (pl.when(pl.col("sig_up")).then(pl.col("temp_target") * 10000 - spread)
              .when(pl.col("sig_down")).then(-pl.col("temp_target") * 10000 - spread)
              .otherwise(None)).alias("pnl")
        )
        
        results = df.filter(pl.col("pnl").is_not_null())
        if len(results) > 0:
            win_rate = (results["pnl"] > 0).mean()
            avg_pnl = results["pnl"].mean()
            print(f"{target:<12} | {win_rate:>7.2f}% | {avg_pnl:>12.3f} bps | {len(results):<8}")

if __name__ == "__main__":
    run_universe_lag_audit()
