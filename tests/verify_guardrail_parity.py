"""
Verify Parity between Pandas-based Guardrail (Backtest/Validation)
and SQL-based Guardrail (Live API).
"""
import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta, timezone
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import sys
from pathlib import Path

# Add project root to path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.api.db import Base
from services.api.models import GuardrailState
from services.api.guardrail import update_guardrail_on_close, is_trade_allowed
from behemoth.core.guardrail import apply_loss_streak_guardrail
from services.api import settings

# Setup In-Memory DB for SQL implementation
engine = create_engine(
    "sqlite+pysqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
Base.metadata.create_all(bind=engine)

def test_guardrail_parity():
    # 1. Setup Synthetic Data
    # Scenario: 3 losses in a row (trigger), then some trades during cooldown, then a trade after cooldown.
    start = datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    
    trades = [
        # 3 Losses (trigger cooldown)
        {"pair": "EUR/USD", "exit_ts": start + timedelta(hours=1), "pnl_bps": -10.0},
        {"pair": "EUR/USD", "exit_ts": start + timedelta(hours=2), "pnl_bps": -10.0},
        {"pair": "EUR/USD", "exit_ts": start + timedelta(hours=3), "pnl_bps": -10.0},
        # Triggered here. Cooldown = 7 days. Pause until ~Jan 8th.
        
        # Blocked Trades (During Cooldown)
        {"pair": "EUR/USD", "exit_ts": start + timedelta(hours=4), "pnl_bps": 50.0},  # Winning trade that shouldn't happen
        {"pair": "EUR/USD", "exit_ts": start + timedelta(days=2), "pnl_bps": 20.0}, 
        
        # Allowed Trade (After Cooldown)
        {"pair": "EUR/USD", "exit_ts": start + timedelta(days=8), "pnl_bps": 10.0},
        
        # Another pair (should be unaffected)
        {"pair": "GBP/USD", "exit_ts": start + timedelta(hours=5), "pnl_bps": -5.0},
    ]
    
    df = pd.DataFrame(trades)
    # Ensure they are datetime64[ns]
    df["exit_ts"] = pd.to_datetime(df["exit_ts"], utc=True)
    # Cast to int64 (nanoseconds) - Force explicit multiplication to avoid ambiguity
    df["exit_ts_val"] = df["exit_ts"].apply(lambda x: int(x.timestamp() * 1e9))
    
    # We need to construct a DF that works with apply_loss_streak_guardrail
    # It sorts by "exit_ts" so we should keep that column name pointing to the sortable value.
    df_pandas = df.copy()
    df_pandas["exit_ts"] = df_pandas["exit_ts_val"]
    
    # 2. Run Pandas Implementation (Backtest)
    print("Running PANDAS Guardrail...")
    # Mock settings?
    # The function takes args. Let's pass them explicit match defaults.
    # settings: streak=3, threshold=0.0, cooldown=7
    
    df_kept = apply_loss_streak_guardrail(
        df_pandas,
        loss_threshold=0.0,
        loss_streak=3,
        cooldown_days=7
    )
    
    print(f"Pandas Kept: {len(df_kept)} trades")
    print(df_kept)
    
    # 3. Run SQL Implementation (Live Simulation)
    print("\nRunning SQL Guardrail...")
    session = TestingSessionLocal()
    
    # We simulate the events sequentially
    kept_sql = []
    
    for i, row in df.iterrows():
        pair = row["pair"]
        ts = row["exit_ts"]
        pnl = row["pnl_bps"]
        
        # Simulate Entry Check (Is allowed now?)
        # IMPORTANT: In backtest, we filter based on EXIT_TS.
        # But in live, we filter at ENTRY time.
        # If the trade exited at T, it entered at T - duration.
        # The backtest simplifies this by checking 'exit_ts < pause_until'.
        # Wait. Backtest check: "if ts < pause_until: skipped". 'ts' is row.exit_ts.
        # This implies it blocks trades that *EXIT* during the cooldown?
        # That's a proxy for "Trade happened during cooldown".
        # Ideally, we block at Entry.
        # But `apply_loss_streak_guardrail` uses `exit_ts`.
        # So for parity, we must use `exit_ts` as the "check time" in our SQL simulation too?
        # Or confirm that both effectively block the same set.
        
        # Let's verify strict parity of the logic AS WRITTEN.
        # SQL check: is_trade_allowed(..., as_of=ts)  <-- checking at exit_ts logic
        
        allowed, _, _ = is_trade_allowed(session, "test_strat", pair, as_of=ts)
        
        if allowed:
            kept_sql.append(row)
            # Update state with result
            update_guardrail_on_close(
                session, 
                "test_strat", 
                pair, 
                ts, 
                pnl
            )
        else:
            print(f"SQL Blocked: {pair} at {ts} (PnL {pnl})")
            
    session.close()
    
    df_sql = pd.DataFrame(kept_sql)
    print(f"SQL Kept: {len(df_sql)} trades")
    print(df_sql)
    
    # 4. Compare
    # Sort both by exit_ts to ensure order matches
    df_kept = df_kept.sort_values("exit_ts").reset_index(drop=True)
    df_sql = df_sql.sort_values("exit_ts").reset_index(drop=True)
    
    assert len(df_kept) == len(df_sql)
    assert df_kept["pnl_bps"].equals(df_sql["pnl_bps"])
    
    # Check specific logic
    # Trade 3 (Index 3): EUR/USD +4h. Should be blocked.
    # Trade 4 (Index 4): EUR/USD +2d. Should be blocked.
    # Trade 5 (Index 5): EUR/USD +8d. Should be allowed.
    # Trade 6 (Index 6): GBP/USD. Should be allowed.
    
    print("\nSUCCESS: Implementations matching.")

if __name__ == "__main__":
    test_guardrail_parity()
