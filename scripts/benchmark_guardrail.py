"""
Benchmark Script: 1-Bar Incremental Guardrail vs Vectorized Baseline
Validates PnL/Stats and compares Guardrail execution speed for M5 and M15.

Simulates 8 years of trading history.
"""
import time
import pandas as pd
import numpy as np
import sys
from pathlib import Path
from datetime import datetime, timezone

# Add project root to path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.api.validation import PIPELINE_PATHS, _load_pipeline, _apply_guardrail_df, _metrics

# Monkey patch PIPELINE_PATHS to include H1 for this script
PIPELINE_PATHS["h1"] = "data/events/events_h1_8yr_v3_mom.csv"
PIPELINE_PATHS["h1_ml"] = "data/ml/results_h1/events_h1_ml_filtered.csv"

from services.api.guardrail import update_guardrail_on_close, is_trade_allowed, get_guardrail_state
from services.api.models import GuardrailState
from services.api import settings

# Setup In-Memory Sqlite for benchmarking SQL implementation
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from services.api.db import Base

# We create engine/session per run to ensure clean state
def get_db_session():
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    Base.metadata.create_all(bind=engine)
    return SessionLocal()

def simulate_incremental_guardrail(df, session):
    """
    Simulates row-by-row processing using the SQL-based State logic.
    Identical to how the API processes live trades.
    """
    kept_rows = []
    
    # Pre-sort by timestamps to simulate chronological arrival
    # Incremental logic relies on time order
    # Note: Pipeline data has 'timestamp' (entry) and inferred 'exit_ts'.
    # In live trading:
    # 1. Trade check happens at Entry Time (is_trade_allowed).
    # 2. State update happens at Exit Time (update_guardrail_on_close).
    # We must interleave these events properly!
    
    # Expand events: specific (time, type, payload)
    events = []
    for row in df.itertuples(index=False):
        # Entry Event
        # For simplicity, we assume Entry happens at 'timestamp'.
        # Payload (row) is needed later.
        events.append({
            "ts": int(row.timestamp),
            "type": "ENTRY",
            "row": row
        })
        
        # Exit Event
        # Happens at 'exit_ts'.
        # Payload needed: pnl_bps
        events.append({
            "ts": int(row.exit_ts),
            "type": "EXIT",
            "row": row
        })
        
    # Sort events by time
    events.sort(key=lambda x: x["ts"])
    
    # Process events
    # We only care about entries being allowed/blocked.
    # Exits update the state.
    
    # Optimization: We only check `is_trade_allowed` for entries.
    # We only call `update_guardrail_on_close` for exits *of allowed trades*.
    # Wait, in live trading:
    # - If entry is blocked, no position is created. No exit event happens later.
    # - So we must track which trades were allowed to process their exits.
    allowed_indices = set()
    
    # Since we can't easily track by ID without adding one, let's use tuple checks or just assume unique timestamps per pair?
    # Or just store the row object ID?
    
    start_time = time.time()
    count_checks = 0
    count_updates = 0
    
    for evt in events:
        row = evt["row"]
        ts_val = evt["ts"]
        pair = row.pair
        strategy_id = row.strategy_type # e.g. MOM
        pnl = row.pnl_bps
        
        # TS as datetime for SQL function
        ts_dt = datetime.fromtimestamp(ts_val / 1e9, tz=timezone.utc)
        
        if evt["type"] == "ENTRY":
            # Check if allowed
            allowed, pause_until_dt, streak = is_trade_allowed(session, strategy_id, pair, as_of=ts_dt)
            if allowed:
                temp_id = id(row)
                allowed_indices.add(temp_id)
                kept_rows.append(row)
            else:
                # DEBUG: Why blocked?
                pass
                
            count_checks += 1
            
        elif evt["type"] == "EXIT":
            if id(row) in allowed_indices:
                state_before = get_guardrail_state(session, strategy_id, pair)
                loss_streak_before = state_before.loss_streak if state_before else 0
                
                update_guardrail_on_close(session, strategy_id, pair, ts_dt, pnl)
                
                state_after = get_guardrail_state(session, strategy_id, pair)
                loss_streak_after = state_after.loss_streak if state_after else 0
                pause_after = state_after.pause_until if state_after else None
                
                # Check if this exit TRIGGERED a pause
                if loss_streak_before < 3 and loss_streak_after == 0 and pause_after is not None:
                    # It triggered a pause!
                    # Check if there are other trades CURRENTLY OPEN for this pair?
                    # We can't easily iterate "open" trades here without tracking them.
                    pass

                count_updates += 1
                
    end_time = time.time()
    
    duration = end_time - start_time
    # Construct resulting DF
    df_kept = pd.DataFrame(kept_rows)
    return df_kept, duration, count_checks

def run_benchmark(bar):
    print(f"\n================ BENCHMARK: {bar.upper()} ================")
    
    # 1. Load Data
    print("Loading Pipeline Data...")
    
    bar_mins = 60 if bar == "h1" else (15 if bar == "m15" else 5)
    df = _load_pipeline(PIPELINE_PATHS[bar], bar_minutes=bar_mins)
    print(f"Loaded {len(df)} trades.")
    
    if df.empty:
        print("No data found.")
        return

    # Robust Timestamp Conversion Function
    def _normalize_ts(series):
        if pd.api.types.is_numeric_dtype(series):
            vals = series.to_numpy(dtype=np.int64)
            # Check for Microseconds (approx < 1e17, Year 1973-5138 range in ns is > 1e17)
            # 2021 in ns is ~1.6e18. 2021 in us is ~1.6e15.
            # If value < 1e16, likely microseconds.
            if len(vals) > 0 and vals.max() < 1e17 and vals.max() > 1e14:
                return vals * 1000
            return vals
        else:
            # String / Object -> Datetime -> Int64 (ns)
            return pd.to_datetime(series, utc=True).astype(np.int64)

    try:
        df["timestamp"] = _normalize_ts(df["timestamp"])
        df["exit_ts"] = _normalize_ts(df["exit_ts"])
    except Exception as e:
        print(f"Error converting timestamps: {e}")
        return

    # Add dummy strategy_type if missing (needed for SQL function)
    if "strategy_type" not in df.columns:
        df["strategy_type"] = f"mom_{bar}"
    
    # 2. Baseline (Vectorized)
    print("\n--- Baseline (Vectorized/Pandas) ---")
    start_base = time.time()
    df_base = _apply_guardrail_df(df)
    time_base = time.time() - start_base
    
    metrics_base = _metrics(df_base["pnl_bps"].to_numpy(), df_base["exit_ts"].to_numpy())
    print(f"Trades: {metrics_base['trades']}")
    print(f"PnL: {metrics_base['total_pnl']:.2f} bps")
    print(f"Sharpe: {metrics_base['sharpe']:.4f}")
    print(f"Time: {time_base:.4f}s")
    
    # 3. Incremental (SQL Simulation)
    print("\n--- Incremental (1-Bar Simulation) ---")
    session = get_db_session()
    
    # Run Simulation
    df_inc, time_inc, checks = simulate_incremental_guardrail(df, session)
    
    # Compute Metrics specific to Simulation Result
    if not df_inc.empty:
        metrics_inc = _metrics(df_inc["pnl_bps"].to_numpy(), df_inc["exit_ts"].to_numpy())
    else:
        metrics_inc = _metrics(np.array([]), np.array([]))
        
    print(f"Trades: {metrics_inc['trades']}")
    print(f"PnL: {metrics_inc['total_pnl']:.2f} bps")
    print(f"Sharpe: {metrics_inc['sharpe']:.4f}")
    print(f"Time: {time_inc:.4f}s (processed {checks} entries)")
    print(f"Speed: {time_inc/checks*1000:.3f} ms/entry")
    
    session.close()
    
    # 4. Verification
    print("\n--- Comparison ---")
    diff_trades = metrics_inc['trades'] - metrics_base['trades']
    diff_pnl = metrics_inc['total_pnl'] - metrics_base['total_pnl']
    
    if diff_trades == 0 and abs(diff_pnl) < 1e-4:
         print("✅ EXACT MATCH: Incremental logic produced identical results.")
    else:
         print(f"❌ MISMATCH: Trades Diff={diff_trades}, PnL Diff={diff_pnl:.2f}")

if __name__ == "__main__":
    for bar in ["m5", "m15", "h1", "h1_ml"]:
        run_benchmark(bar)
