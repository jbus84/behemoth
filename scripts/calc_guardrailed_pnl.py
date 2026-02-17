import polars as pl
from datetime import datetime, timedelta

# Constants from config
LOSS_STREAK_LIMIT = 3
COOLDOWN_DAYS = 7
LOSS_THRESH = 0.0 # Standard guardrail setting

def run_guardrail_simulation():
    print(f"--- SIMULATING GUARDRAILS (Cooldown: {COOLDOWN_DAYS} days after {LOSS_STREAK_LIMIT} losses) ---")
    
    df = pl.read_csv("data/events/events_h1_8yr_v3_mom.csv")
    
    # Sort by timestamp
    df = df.sort("timestamp")
    
    # State tracking per pair
    # pair -> {loss_streak: int, pause_until: datetime}
    state = {}
    
    kept_trades = []
    dropped_trades = 0
    
    for row in df.iter_rows(named=True):
        pair = row["symbol"]
        ts_str = row["timestamp"] # "2018-01-01 17:00:00"
        
        # Parse TS
        try:
            ts = datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S")
        except:
            # Try ISO format
             ts = datetime.fromisoformat(ts_str)
             
        if pair not in state:
            state[pair] = {"streak": 0, "pause_until": None}
            
        st = state[pair]
        
        # 1. Check if Paused
        if st["pause_until"] and ts < st["pause_until"]:
            dropped_trades += 1
            continue
            
        # 2. Process Trade
        kept_trades.append(row)
        pnl = row["pnl_bps"]
        
        # 3. Update State
        if pnl < 0:
            st["streak"] += 1
            if st["streak"] >= LOSS_STREAK_LIMIT:
                st["pause_until"] = ts + timedelta(days=COOLDOWN_DAYS)
                st["streak"] = 0
        else:
            st["streak"] = 0
            st["pause_until"] = None
            
    # Stats
    df_kept = pl.DataFrame(kept_trades)
    total_pnl = df_kept["pnl_bps"].sum()
    total_trades = len(df_kept)
    avg_pnl = total_pnl / total_trades if total_trades > 0 else 0
    
    print(f"Original Trades: {len(df)}")
    print(f"Kept Trades: {total_trades} (Dropped {dropped_trades})")
    print(f"Total PnL: {total_pnl:.2f} bps")
    print(f"Avg PnL: {avg_pnl:.2f} bps")
    
    # FX + Commodities
    fx_comm_pairs = [
        "EUR/GBP", "AUD/NZD", "EUR/CHF", "EUR/JPY", "GBP/JPY", 
        "CHF/JPY", "EUR/AUD", "GBP/AUD", "AUD/CAD", "GBP/CAD", "NZD/CAD",
        "Gold/Oil", "Oil/Silver", "Gold/Silver"
    ]
    df_fx = df_kept.filter(pl.col("symbol").is_in(fx_comm_pairs))
    print(f"\n--- FX + COMMODITIES (Guardrailed) ---")
    print(f"Trades: {len(df_fx)}")
    print(f"Avg PnL: {df_fx['pnl_bps'].mean():.2f} bps")

if __name__ == "__main__":
    run_guardrail_simulation()
