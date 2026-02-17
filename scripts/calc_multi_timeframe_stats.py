import polars as pl
import numpy as np
import os
from datetime import datetime, timedelta

# Constants (Baseline Guardrails)
LOSS_STREAK_LIMIT = 3
COOLDOWN_DAYS = 7
LOSS_THRESH = 0.0

FX_COMM_PAIRS = [
    "EUR/GBP", "AUD/NZD", "EUR/CHF", "EUR/JPY", "GBP/JPY", 
    "CHF/JPY", "EUR/AUD", "GBP/AUD", "AUD/CAD", "GBP/CAD", "NZD/CAD",
    "Gold/Oil", "Oil/Silver", "Gold/Silver"
]

def calculate_cagr(total_pnl_bps, start_dt, end_dt):
    if not isinstance(start_dt, datetime) or not isinstance(end_dt, datetime):
        return 0.0
    if start_dt >= end_dt:
        return 0.0
    
    # Duration in Years
    years = (end_dt - start_dt).days / 365.25
    if years <= 0: return 0.0
    
    # Total Return % (Assuming linear sum of BPS on fixed capital)
    # 10,000 bps = 100% Return
    total_return_decimal = total_pnl_bps / 10000.0
    
    # CAGR = (1 + TotalReturn)^(1/Years) - 1
    # Note: This assumes compounding. If trading fixed size, Annualized ROI is better.
    # But user asked for CAGR. We'll provide both or just CAGR.
    # Let's assume compounding for CAGR formula.
    try:
        cagr = (1 + total_return_decimal) ** (1 / years) - 1
    except:
        cagr = 0.0
        
    return cagr

def calculate_sharpe(df_trades):
    # Convert timestamp to date for grouping
    # Check type
    dtype = df_trades["timestamp"].dtype
    
    if dtype in [pl.Float64, pl.Int64]:
        # Assume ns
        df_trades = df_trades.with_columns(
            pl.from_epoch(pl.col("timestamp").cast(pl.Int64), time_unit="ns").dt.date().alias("date")
        )
    else:
        # String - try parse
        try:
            df_trades = df_trades.with_columns(
                pl.col("timestamp").str.strptime(pl.Datetime, "%Y-%m-%d %H:%M:%S").dt.date().alias("date")
            )
        except:
             # Try iso
             df_trades = df_trades.with_columns(
                pl.col("timestamp").str.to_datetime().dt.date().alias("date")
            )

    daily_pnl = df_trades.group_by("date").agg(pl.sum("pnl_bps").alias("daily_pnl"))
    pnls = daily_pnl["daily_pnl"].to_numpy() # BPS per day
    
    if len(pnls) < 2: return 0.0
    
    # Convert BPS to % Return (Assuming 100bps = 1% risk/return)
    # Actually Sharpe is unitless, so BPS is fine as long as consistent.
    mean = np.mean(pnls)
    std = np.std(pnls)
    
    if std == 0: return 0.0
    
    # Annualized Sharpe (assuming 252 days)
    sharpe = (mean / std) * np.sqrt(252)
    return sharpe

def process_timeframe(tf_name, filepath):
    print(f"\n{'='*10} ANALYZING {tf_name} {'='*10}")
    
    if not os.path.exists(filepath):
        print(f"File not found: {filepath}")
        return

    try:
        df = pl.read_csv(filepath)
    except Exception as e:
        print(f"Error reading csv: {e}")
        return
        
    # Rename pair -> symbol if needed
    if "pair" in df.columns and "symbol" not in df.columns:
        df = df.rename({"pair": "symbol"})
        
    print(f"Columns: {df.columns}")
    print(f"First 5 rows:\n{df.head(5)}")
    
    # Filter Universe (FX + Commodities)
    print(f"Universe: FX + Commodities ({len(FX_COMM_PAIRS)} pairs)")
    df = df.filter(pl.col("symbol").is_in(FX_COMM_PAIRS))
    print(f"Rows after Universe Filter: {len(df)}")
    
    # Sort
    df = df.sort("timestamp")
    
    # --- GUARDRAIL SIMULATION ---
    # Cooldown: Pause 7 days after 3 consecutive losses
    
    state = {} # pair -> {streak, pause_until}
    kept_trades = []
    dropped_count = 0
    
    for row in df.iter_rows(named=True):
        pair = row["symbol"]
        ts_str = row["timestamp"]
        
        # Parse TS
        if isinstance(ts_str, (int, float)):
            # Assuming Nanoseconds if > 1e14
            if ts_str > 1e14:
                ts = datetime.fromtimestamp(ts_str / 1e9)
            else:
                ts = datetime.fromtimestamp(ts_str)
        else:
            try:
                 # Fast parse 'YYYY-MM-DD HH:MM:SS'
                 ts = datetime.strptime(str(ts_str), "%Y-%m-%d %H:%M:%S")
            except:
                 try:
                     ts = datetime.fromisoformat(str(ts_str))
                 except:
                     continue

        if pair not in state:
            state[pair] = {"streak": 0, "pause_until": None}
        st = state[pair]
        
        # 1. Check Pause
        if st["pause_until"] and ts < st["pause_until"]:
            dropped_count += 1
            # If paused, we skip trade.
            # Does streak reset? Usually pause resets streak.
            # Logic: After cooldown, streak is 0.
            if ts >= st["pause_until"]:
                 st["pause_until"] = None
                 st["streak"] = 0
            else:
                 continue
                 
        # 2. Process Trade
        kept_trades.append(row)
        pnl = row["pnl_bps"]
        
        # 3. Update State
        if pnl < LOSS_THRESH:
            st["streak"] += 1
            if st["streak"] >= LOSS_STREAK_LIMIT:
                st["pause_until"] = ts + timedelta(days=COOLDOWN_DAYS)
                st["streak"] = 0
        else:
            st["streak"] = 0
            st["pause_until"] = None
            
    # --- METRICS ---
    df_kept = pl.DataFrame(kept_trades)
    count = len(df_kept)
    
    if count == 0:
        print("No trades left after guardrails.")
        return

    total_pnl = df_kept["pnl_bps"].sum()
    avg_pnl = total_pnl / count
    
    # Sharpe
    sharpe = calculate_sharpe(df_kept)
    
    # CAGR
    def get_dt(val):
        if isinstance(val, (int, float)):
            if val > 1e14: return datetime.fromtimestamp(val / 1e9)
            return datetime.fromtimestamp(val)
        try: return datetime.fromisoformat(str(val))
        except: 
            try: return datetime.strptime(str(val), "%Y-%m-%d %H:%M:%S")
            except: return datetime.fromisoformat(str(val).replace("T", " "))

    ts_min = get_dt(df_kept["timestamp"].min())
    ts_max = get_dt(df_kept["timestamp"].max())
    
    cagr = calculate_cagr(total_pnl, ts_min, ts_max)
    
    print(f"Total Trades: {count} (Dropped {dropped_count})")
    print(f"Total PnL:    {total_pnl:,.0f} bps")
    print(f"Avg PnL:      {avg_pnl:.2f} bps")
    print(f"Sharpe Ratio: {sharpe:.2f}")
    print(f"CAGR:         {cagr:.1%}")

def main():
    files = [
        ("H1", "data/events/events_h1_8yr_v3_mom.csv"),
        ("M15", "data/events/events_m15_8yr_v3_mom.csv"),
        ("M5", "data/events/events_m5_8yr_v3_mom.csv")
    ]
    
    for name, path in files:
        process_timeframe(name, path)

if __name__ == "__main__":
    main()
