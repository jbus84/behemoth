
import pandas as pd
import sys
import os

# Add project root to path
sys.path.append(os.getcwd())

from behemoth.core.metrics import sharpe_daily

PIPELINE_PATHS = {
    "H4": "data/events/events_h4_8yr_v3_mom.csv",
    "H1": "data/events/events_h1_8yr_v3_mom.csv",
    "M15": "data/events/events_m15_8yr_v3_mom.csv",
    "M5": "data/events/events_m5_8yr_v3_mom.csv",
}

BEST_THRESH = {"H1": 0.005, "M15": 0.05, "M5": 0.1, "H4": 0.05}

# Pairs filtering list (The "Winners")
WINNERS = [
    "EUR/GBP", "AUD/NZD", "EUR/CHF", "EUR/JPY", "GBP/JPY", 
    "CHF/JPY", "EUR/AUD", "GBP/AUD", "AUD/CAD", "GBP/CAD", "NZD/CAD",
    "Gold/Oil", "Oil/Silver", "Gold/Silver"
]

def main():
    print("--- LOADING ALL TRADES (NO UNIVERSE FILTER) ---")
    all_dfs = []
    
    for tf, path in PIPELINE_PATHS.items():
        if not os.path.exists(path):
            print(f"Skipping {tf}: File not found")
            continue
            
        df = pd.read_csv(path)
        if df.empty: continue
        
        # Standardize columns
        if "pair" in df.columns: df.rename(columns={"pair": "symbol"}, inplace=True)
        
        # Parse timestamp robustly
        try:
             df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True).astype("int64")
        except:
             pass
             
        # Fix H4 Microseconds
        if tf == "H4" and df["timestamp"].max() < 3e16:
            df["timestamp"] *= 1000

        # Filter by TF Threshold
        thresh = BEST_THRESH.get(tf, 0.0)
        if "z_accel" in df.columns:
            df = df[df["z_accel"].abs() > thresh]
            
        df["timeframe"] = tf
        all_dfs.append(df)
        
    if not all_dfs:
        print("No trades found.")
        return

    df_grand = pd.concat(all_dfs)
    
    # Analyze by Symbol
    stats = []
    for symbol, d in df_grand.groupby("symbol"):
        pnl = d["pnl_bps"].sum()
        count = len(d)
        avg = pnl / count
        sharpe = sharpe_daily(d["pnl_bps"], d["timestamp"])
        
        status = "✅ WINNER" if symbol in WINNERS else "❌ EXCLUDED"
        
        stats.append({
            "Symbol": symbol,
            "PnL": pnl,
            "Trades": count,
            "Avg": avg,
            "Sharpe": sharpe,
            "Status": status
        })
        
    df_stats = pd.DataFrame(stats).sort_values("PnL")
    
    print("\n>>> WALL OF SHAME (NEGATIVE PAIRS) <<<")
    neg = df_stats[df_stats["PnL"] < 0]
    if neg.empty:
        print("None! All pairs are positive (even excluded ones).")
    else:
        print(neg.to_string(index=False))
        
    print("\n>>> POSITIVE BUT EXCLUDED <<<")
    pos_excluded = df_stats[(df_stats["PnL"] > 0) & (df_stats["Status"].str.contains("EXCLUDED"))]
    if pos_excluded.empty:
        print("None.")
    else:
        print(pos_excluded.to_string(index=False))

    print("\n>>> FULL RANKING <<<")
    print(df_stats.to_string(index=False))

if __name__ == "__main__":
    main()
