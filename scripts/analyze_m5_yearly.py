
import pandas as pd
import sys
import os

# Add project root to path
sys.path.append(os.getcwd())

M5_PATH = "data/events/events_m5_8yr_v3_mom.csv"
M5_THRESH = 0.1

def apply_guardrail(df):
    if df.empty: return df
    
    # Sort chronologically by EXIT time (crucial for streak logic)
    # We need exit_ts. If not present, approximate with timestamp + duration
    if "exit_ts" not in df.columns:
        # Fallback: assume 5-minute bars
        print("Warning: exit_ts not found, approximating...")
        duration = df["duration_bars"] if "duration_bars" in df.columns else 1
        df["exit_ts"] = df["timestamp"] + pd.to_timedelta(duration * 5, unit="m")
    
    # Ensure int64 nanoseconds for speed and type safety
    df["timestamp"] = df["timestamp"].astype("int64")
    df["exit_ts"] = df["exit_ts"].astype("int64")
    
    df = df.sort_values("exit_ts").reset_index(drop=True)
    
    keep_indices = []
    
    # State: pair -> {streak: int, ready_ts: int}
    state = {}
    
    # Cooldown: 7 days in nanoseconds
    COOLDOWN_NS = 7 * 24 * 60 * 60 * 1_000_000_000
    
    for idx, row in df.iterrows():
        sym = row["symbol"]
        ts = row["timestamp"] # Entry time
        exit_ts = row["exit_ts"]
        pnl = row["pnl_bps"]
        
        if sym not in state:
            state[sym] = {"streak": 0, "ready_ts": 0}
            
        s = state[sym]
        
        # Check if paused
        if ts < s["ready_ts"]:
            continue # Skip trade
            
        keep_indices.append(idx)
        
        # Update State
        if pnl < 0:
            s["streak"] += 1
            if s["streak"] >= 3:
                s["ready_ts"] = exit_ts + COOLDOWN_NS
                s["streak"] = 0 # Reset streak after triggering cooldown
        else:
            s["streak"] = 0
            
    return df.loc[keep_indices].copy()

def main():
    print(f"--- ANALYZING M5 YEARLY PNL ---")
    
    if not os.path.exists(M5_PATH):
        print(f"File not found: {M5_PATH}")
        return
        
    df = pd.read_csv(M5_PATH)
    
    # Standardize basic columns
    if "pair" in df.columns: df.rename(columns={"pair": "symbol"}, inplace=True)
    
    # Parse timestamp
    if df["timestamp"].dtype == "object":
         df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    else:
         df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ns", utc=True)
         
    # Extract Year
    df["year"] = df["timestamp"].dt.year
    
    # Filter by Acceleration Threshold (Same as Grand Ensemble)
    if "z_accel" in df.columns:
        df = df[df["z_accel"].abs() > M5_THRESH]
        
    print(f"Loaded {len(df)} trades after filtering (ACCEL > {M5_THRESH})")
    
    # APPLY GUARDRAIL
    print("Applying Guardrail (3 losses -> 7 day cooldown)...")
    df_guard = apply_guardrail(df)
    print(f"Trades after Guardrail: {len(df_guard)} (Removed {len(df) - len(df_guard)})")
    
    df = df_guard # Use guardrailed data for pivot

    # Create Pivot Table
    # Index: Symbol, Columns: Year, Values: PnL (Sum)
    pivot = pd.pivot_table(
        df, 
        values="pnl_bps", 
        index="symbol", 
        columns="year", 
        aggfunc="sum",
        fill_value=0
    )
    
    # Add Total column
    pivot["Total"] = pivot.sum(axis=1)
    
    # Sort by Total Descending
    pivot.sort_values("Total", ascending=False, inplace=True)
    
    print("\n>>> M5 YEARLY PNL MATRIX (bps) <<<")
    print(pivot.round(0).to_string())
    
    # Also calculate Win Rate per year to see if it's just luck
    pivot_wins = pd.pivot_table(
        df, 
        values="pnl_bps", 
        index="symbol", 
        columns="year", 
        aggfunc=lambda x: (x > 0).mean(),
        fill_value=0
    )
    print("\n>>> M5 YEARLY WIN RATE MATRIX <<<")
    print(pivot_wins.round(2).to_string())

if __name__ == "__main__":
    main()
