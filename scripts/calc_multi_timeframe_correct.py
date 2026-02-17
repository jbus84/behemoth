import os
import sys
import numpy as np
import pandas as pd
from datetime import datetime, timezone, timedelta
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

# Add project root to path
sys.path.append(os.getcwd())

from services.api.guardrail import is_trade_allowed, update_guardrail_on_close
from services.api.db import Base
from services.api.validation import _load_pipeline
from behemoth.core.metrics import sharpe_daily

def get_sector(symbol):
    if any(x in symbol for x in ["Gold", "Oil", "Silver"]):
        return "Commodities"
    return "FX"

def breakdown_by_sector(df, title=""):
    if df.empty: return
    print(f"\n>>> {title} SECTOR BREAKDOWN <<<")
    
    df = df.copy()
    df["Sector"] = df["symbol"].apply(get_sector)
    
    for sector in ["FX", "Commodities"]:
        d = df[df["Sector"] == sector]
        if d.empty:
            print(f"  {sector}: No trades")
            continue
            
        count = len(d)
        pnl = d["pnl_bps"].sum()
        avg = pnl / count
        sharpe = sharpe_daily(d["pnl_bps"], d["timestamp"])
        
        print(f"  {sector}: Trades={count} | PnL={pnl:+.0f} bps | Avg={avg:.1f} | Sharpe={sharpe:.2f}")

def breakdown_by_pair(df, title=""):
    if df.empty: return
    print(f"\n>>> {title} PAIR BREAKDOWN <<<")
    
    # Group by symbol and compute metrics
    stats = []
    for symbol, d in df.groupby("symbol"):
        count = len(d)
        pnl = d["pnl_bps"].sum()
        avg = pnl / count
        sharpe = sharpe_daily(d["pnl_bps"], d["timestamp"])
        stats.append({"Symbol": symbol, "Trades": count, "PnL": pnl, "Avg": avg, "Sharpe": sharpe})
    
    # Sort by PnL descending
    stats.sort(key=lambda x: x["PnL"], reverse=True)
    
    print(f"{'Symbol':<12} | {'Trades':<6} | {'PnL (bps)':<10} | {'Avg':<6} | {'Sharpe':<6}")
    print("-" * 50)
    for s in stats:
        print(f"{s['Symbol']:<12} | {s['Trades']:<6} | {s['PnL']:<+10.0f} | {s['Avg']:<6.1f} | {s['Sharpe']:<6.2f}")

# Configuration
SHARPE_CUTOFF = 0.25
UNIVERSE = [
    "EUR/GBP", "AUD/NZD", "EUR/CHF", "EUR/JPY", "GBP/JPY", 
    "CHF/JPY", "EUR/AUD", "GBP/AUD", "AUD/CAD", "GBP/CAD", "NZD/CAD",
    "Gold/Oil", "Oil/Silver", "Gold/Silver"
]

PIPELINE_PATHS = {
    "H1": "data/events/events_h1_8yr_v3_mom.csv",
    "M15": "data/events/events_m15_8yr_v3_mom.csv",
    "M5": "data/events/events_m5_8yr_v3_mom.csv",
    "H4": "data/events/events_h4_8yr_v3_mom.csv"
}

BAR_MINS = {
    "H1": 60,
    "M15": 15,
    "M5": 5,
    "H4": 240
}

def get_db_session():
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    Base.metadata.create_all(bind=engine)
    return SessionLocal()

def normalize_ts_series(series):
    # Ensure Series is safe for datetime conversion
    # If using _load_pipeline, exit_ts is already int64 (ns or ms?)
    # validation._compute_exit_ts returns int64 (ns)
    return series

def simulate_incremental(df, session):
    # Strict Causal Simulation
    if df.empty: return df
    
    # 1. Create Event Queue
    # events: list of (ts, type, row_index)
    # Using row index to access dataframe is faster
    
    # Ensure timestamps are uniform int64 (ns) for sorting
    # Helper to force int64 ns
    def to_ns(series):
        if pd.api.types.is_numeric_dtype(series):
            return series.astype("int64")
        else:
            return pd.to_datetime(series, utc=True).astype("int64")
            
    try:
        df["timestamp"] = to_ns(df["timestamp"])
        df["exit_ts"] = to_ns(df["exit_ts"])
    except Exception as e:
        print(f"Error converting timestamps: {e}")
        return df
        
    entries = df[["timestamp"]].copy()
    entries["type"] = 0 # Entry
    entries["idx"] = df.index
    entries.rename(columns={"timestamp": "ts"}, inplace=True)
    
    exits = df[["exit_ts"]].copy()
    exits["type"] = 1 # Exit
    exits["idx"] = df.index
    exits.rename(columns={"exit_ts": "ts"}, inplace=True)
    
    events = pd.concat([entries, exits]).sort_values(["ts", "type"])
    
    # 2. Process
    kept_indices = []
    allowed_ids = set()
    
    # Determine strategy column
    if "strategy_type" not in df.columns:
        df["strategy_type"] = "MOM"
        
    # Pre-fetch columns to avoid overhead
    pairs = df["symbol"].to_numpy() if "symbol" in df.columns else df["pair"].to_numpy()
    strats = df["strategy_type"].to_numpy()
    pnls = df["pnl_bps"].to_numpy()
    
    # Map index to row location
    # Since we didn't reset index, df.index values match entries["idx"]
    # But to be safe, let's use a direct lookup or just iterate the sorted events tuples.
    
    entry_rows = df.to_dict('index')
    
    for row in events.itertuples(index=False):
        # row: ts, type, idx
        r_idx = row.idx
        is_entry = (row.type == 0)
        
        # Convert TS to datetime for guardrail check
        ts_dt = datetime.fromtimestamp(row.ts / 1e9, tz=timezone.utc)
        
        pair = pairs[r_idx] if isinstance(df.index, pd.RangeIndex) and r_idx < len(pairs) else entry_rows[r_idx]["symbol" if "symbol" in entry_rows[r_idx] else "pair"]
        strat = strats[r_idx] if isinstance(df.index, pd.RangeIndex) and r_idx < len(strats) else entry_rows[r_idx]["strategy_type"]
        
        if is_entry:
            allowed, _, _ = is_trade_allowed(session, strat, pair, as_of=ts_dt)
            if allowed:
                allowed_ids.add(r_idx)
                kept_indices.append(r_idx)
        else:
            # Exit
            if r_idx in allowed_ids:
                pnl = pnls[r_idx] if isinstance(df.index, pd.RangeIndex) and r_idx < len(pnls) else entry_rows[r_idx]["pnl_bps"]
                update_guardrail_on_close(session, strat, pair, ts_dt, pnl)
                session.commit() # Ensure state is saved
                allowed_ids.remove(r_idx) # Optional: cleanup memory
                
    return df.loc[kept_indices].copy()

def calculate_cagr(total_pnl_bps, df):
    if df.empty: return 0.0
    
    # Time span
    start_ts = df["timestamp"].min()
    end_ts = df["exit_ts"].max()
    
    # Convert to ns if not
    if isinstance(start_ts, (pd.Timestamp, datetime)):
        start_ts = start_ts.timestamp() * 1e9
    if isinstance(end_ts, (pd.Timestamp, datetime)):
        end_ts = end_ts.timestamp() * 1e9
        
    duration_ns = end_ts - start_ts
    years = duration_ns / (1e9 * 3600 * 24 * 365.25)
    
    if years <= 0: return 0.0
    
    # CAGR = (1 + TotalReturnDecimal)^(1/Years) - 1
    # 10000 bps = 100% = 1.0
    ret_decimal = total_pnl_bps / 10000.0
    
    try:
        cagr = (1 + ret_decimal) ** (1 / years) - 1
    except:
        cagr = 0.0
    return cagr

def analyze_timeframe(tf_name, target_thresh=None):
    print(f"\n{'='*10} ANALYZING {tf_name} ({BAR_MINS[tf_name]}m) {'='*10}")
    
    path = PIPELINE_PATHS[tf_name]
    if not os.path.exists(path):
        print(f"File not found: {path}")
        return

    # 1. Load & Filter Universe
    df_full = _load_pipeline(path, BAR_MINS[tf_name])
    if "pair" in df_full.columns: df_full.rename(columns={"pair": "symbol"}, inplace=True)
    df_full = df_full[df_full["symbol"].isin(UNIVERSE)]
    
    # DEBUG: Print columns
    print(f"File: {path} | Columns: {list(df_full.columns)}")
    
    # Ensure timestamp is int64 (ns) for consistency
    print(f"DEBUG: Before convert - Shape: {df_full.shape}, TS Type: {df_full['timestamp'].dtype}")
    try:
        df_full["timestamp"] = pd.to_datetime(df_full["timestamp"], utc=True).astype("int64")
    except Exception as e:
        print(f"DEBUG: Convert failed: {e}")
    
    min_ts = df_full["timestamp"].min()
    print(f"DEBUG: After convert - TS Type: {df_full['timestamp'].dtype} | Min TS: {min_ts}")

    # Microseconds (e.g. 1.5e15) -> Nanoseconds (1.5e18)
    if df_full["timestamp"].max() < 30000000000000000:
         print("DEBUG: Detected Microseconds (us), converting to Nanoseconds (ns)")
         df_full["timestamp"] = df_full["timestamp"] * 1000

    # Filter out bad timestamps (e.g. 0 or 1970)
    # 2015-01-01 = 1420070400000000000 ns
    df_full = df_full[df_full["timestamp"] > 1420070400000000000]

    # Test Scenarios
    if target_thresh is not None:
        thresholds = [target_thresh]
    else:
        thresholds = [0.0, 0.005, 0.01, 0.05, 0.1]
    
    results = []
    
    for thresh in thresholds:
        label = f"ACCEL > {thresh}" if thresh > 0 else "BASELINE"
        print(f"\n--- Scenario: {label} ---")
        
        df = df_full.copy()
        if thresh > 0:
            if "z_accel" in df.columns:
                df = df[df["z_accel"].abs() > thresh]
            else:
                print("z_accel column missing, skipping...")
                continue
        
        # 2. Run Causal Guardrail Simulation
        session = get_db_session()
        df_kept = simulate_incremental(df, session)
        session.close()
        
        if df_kept.empty:
            print("No trades kept.")
            continue

        # 3. Portfolio Optimization (Keep pairs with Sharpe >= 0.25)
        pair_stats = []
        for p in df_kept["symbol"].unique():
            d = df_kept[df_kept["symbol"] == p]
            s = sharpe_daily(d["pnl_bps"], d["timestamp"])
            pair_stats.append({"symbol": p, "sharpe": s})
            
        pair_df = pd.DataFrame(pair_stats)
        good_pairs = pair_df[pair_df["sharpe"] >= SHARPE_CUTOFF]["symbol"].tolist()
        df_opt = df_kept[df_kept["symbol"].isin(good_pairs)]
        
        if df_opt.empty:
            print("Optimized portfolio is empty.")
            continue
            
        # 4. Metrics
        total_pnl = df_opt["pnl_bps"].sum()
        count = len(df_opt)
        sharpe = sharpe_daily(df_opt["pnl_bps"], df_opt["timestamp"])
        cagr = calculate_cagr(total_pnl, df_opt)
        
        print(f"Trades: {count} | Avg: {total_pnl/count:.2f} | Sharpe: {sharpe:.2f} | CAGR: {cagr:.1%}")
        breakdown_by_sector(df_opt, title=f"{tf_name} ({label})")
        breakdown_by_pair(df_opt, title=f"{tf_name} ({label})")
        results.append({"Scenario": label, "Sharpe": sharpe, "Avg PnL": total_pnl/count, "PnL": total_pnl, "df": df_opt})
        
    if target_thresh is not None:
        return results[0]["df"] if results else pd.DataFrame()
    return results

def main():
    # Best Thresholds found in study
    BEST_THRESH = {"H1": 0.005, "M15": 0.05, "M5": 0.1, "H4": 0.05}

    independent_results = {}
    for tf, thresh in BEST_THRESH.items():
        independent_results[tf] = analyze_timeframe(tf, target_thresh=thresh)

    print(f"\n{'='*10} ANALYZING INDEPENDENT ENSEMBLE (H1 + M15 + M5) {'='*10}")
    
    all_dfs = []
    for tf, df in independent_results.items():
        if not df.empty:
            df = df.copy()
            df["timeframe"] = tf
            all_dfs.append(df)
            
    if not all_dfs:
        print("No trades in ensemble.")
        return

    df_ensemble = pd.concat(all_dfs).sort_values("timestamp")
    
    total_pnl = df_ensemble["pnl_bps"].sum()
    count = len(df_ensemble)
    sharpe = sharpe_daily(df_ensemble["pnl_bps"], df_ensemble["timestamp"])
    cagr = calculate_cagr(total_pnl, df_ensemble)
    
    print(f"\n--- Scenario: INDEPENDENT ENSEMBLE ---")
    print(f"Trades: {count} | Avg: {total_pnl/count:.2f} | Sharpe: {sharpe:.2f} | CAGR: {cagr:.1%}")
    breakdown_by_sector(df_ensemble, title="ENSEMBLE TOTAL")
    breakdown_by_pair(df_ensemble, title="ENSEMBLE TOTAL")
    
    # === MEAN PNL MATRIX ===
    print(f"\n>>> MEAN PNL PER TRADE MATRIX (bps) <<<")
    # Pivot: Index=Symbol, Columns=Timeframe, Values=pnl_bps (mean)
    # We need to ensure all TFs are represented
    
    # Filter for the optimal thresholds only
    # H4: 0.05, H1: 0.005, M15: 0.05, M5: 0.1
    # df_ensemble already contains this filtered data
    
    pivot = pd.pivot_table(
        df_ensemble, 
        values="pnl_bps", 
        index="symbol", 
        columns="timeframe", 
        aggfunc="mean"
    )
    
    # Reorder columns
    cols = [c for c in ["H4", "H1", "M15", "M5"] if c in pivot.columns]
    pivot = pivot[cols]
    
    # Add Total Avg column
    pivot["Grand Avg"] = df_ensemble.groupby("symbol")["pnl_bps"].mean()
    
    # Sort by Grand Avg descending
    pivot.sort_values("Grand Avg", ascending=False, inplace=True)
    
    print(pivot.round(1).to_string(na_rep="-"))

    # === SHARPE MATRIX ===
    print(f"\n>>> SHARPE RATIO MATRIX <<<")
    
    # We need to calculate Sharpe for each (Symbol, TF) group
    # Pivot table 'aggfunc' needs a custom function
    def pivot_sharpe(x):
        return sharpe_daily(x, df_ensemble.loc[x.index, "timestamp"])

    # Note: Pivot table with custom aggfunc can be tricky with multiple columns.
    # It's safer to iterate and build a DataFrame.
    
    sharpe_data = []
    tfs = ["H4", "H1", "M15", "M5"]
    
    for symbol in df_ensemble["symbol"].unique():
        row = {"symbol": symbol}
        d_sym = df_ensemble[df_ensemble["symbol"] == symbol]
        
        # Grand Sharpe
        row["Grand"] = sharpe_daily(d_sym["pnl_bps"], d_sym["timestamp"])
        
        for tf in tfs:
            d_tf = d_sym[d_sym["timeframe"] == tf]
            if len(d_tf) > 0:
                row[tf] = sharpe_daily(d_tf["pnl_bps"], d_tf["timestamp"])
            else:
                row[tf] = float("nan")
        
        sharpe_data.append(row)
        
    df_sharpe = pd.DataFrame(sharpe_data).set_index("symbol")
    df_sharpe = df_sharpe[["H4", "H1", "M15", "M5", "Grand"]]
    df_sharpe.sort_values("Grand", ascending=False, inplace=True)
    
    print(df_sharpe.round(2).to_string(na_rep="-"))

    # Breakdown
    print("\n--- Timeframe Contribution ---")
    for tf in ["H4", "H1", "M15", "M5"]:
        if tf in independent_results:
            d = independent_results[tf]
            if not d.empty:
                print(f"  {tf}: {len(d)} trades | Sharpe: {sharpe_daily(d['pnl_bps'], d['timestamp']):.2f}")

if __name__ == "__main__":
    main()
