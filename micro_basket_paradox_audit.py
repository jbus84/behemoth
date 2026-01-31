import polars as pl
import numpy as np
import os

def audit_micro_basket_paradox(dataset_path):
    if not os.path.exists(dataset_path): return
    df = pl.read_parquet(dataset_path)
    
    # Core Leaders for Nasdaq
    leaders = ['USDJPY', 'SPXUSD', 'XAUUSD']
    target = 'NSXUSD'
    
    print(f"\n>>> MICRO-BASKET PARADOX AUDIT FOR {dataset_path} (CORE 3 LEADERS) <<<")
    print(f"{'Energy Thr':<10} | {'Trades':<8} | {'Win Rate':<10} | {'Avg Pnl (Net)':<15}")
    print("-" * 60)
    
    # Consensus: 3/3 moving in unison
    # Logic: USDJPY up = USD strength = NSX down (usually)
    # SPX up = Equity strength = NSX up
    # Gold up = Risk off = NSX down (usually)
    
    # Actually, simpler: just use signed correlation direction.
    # 3 out of 3 moving in THEIR usual direction relative to NSX.
    
    df = df.with_columns([
        # Pulse Up: SPX Up, USDJPY Down, XAU Down
        ((pl.col("SPXUSD_ret_1m") > 0) & (pl.col("USDJPY_ret_1m") < 0) & (pl.col("XAUUSD_ret_1m") < 0)).alias("pulse_up"),
        # Pulse Down: SPX Down, USDJPY Up, XAU Up
        ((pl.col("SPXUSD_ret_1m") < 0) & (pl.col("USDJPY_ret_1m") > 0) & (pl.col("XAUUSD_ret_1m") > 0)).alias("pulse_down"),
        pl.mean_horizontal([pl.col(f"{a}_ret_1m").abs() for a in leaders]).alias("macro_energy")
    ])
    
    NSX_STALL = 0.1 / 10000
    
    for nrg in [1.0, 2.0, 3.0]:
        e_thr = nrg / 10000
        
        df_thr = df.with_columns([
            (pl.col("pulse_up") & (pl.col("macro_energy") > e_thr) & (pl.col("NSXUSD_ret_1m").abs() < NSX_STALL)).alias("sig_long"),
            (pl.col("pulse_down") & (pl.col("macro_energy") > e_thr) & (pl.col("NSXUSD_ret_1m").abs() < NSX_STALL)).alias("sig_short")
        ])
        
        df_thr = df_thr.with_columns(
            (pl.when(pl.col("sig_long")).then(pl.col("target_nsx_15m") * 10000 - 1.5)
              .when(pl.col("sig_short")).then(-pl.col("target_nsx_15m") * 10000 - 1.5)
              .otherwise(0)).alias("pnl")
        )
        
        res = df_thr.filter(pl.col("pnl") != 0)
        if len(res) > 0:
             print(f"{nrg:<10} | {len(res):<8} | { (res['pnl'] > 0).mean()*100:>8.2f}% | {res['pnl'].mean():>8.3f} bps")

if __name__ == "__main__":
    for y in ["2023", "2024", "2025"]:
        audit_micro_basket_paradox(f"graph_dataset_1m_{y}.parquet")
