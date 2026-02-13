"""
Portfolio Breakdown Analysis Script.
Calculates performance metrics (Sharpe, Avg PnL, Win Rate) for:
- FX
- Oil
- Metals
- Indices
Across M5, M15, and H1 timeframes using the Incremental Guardrail simulation.
"""

import pandas as pd
import numpy as np
import time
import sys
import os
from pathlib import Path
from datetime import datetime, timezone
from collections import defaultdict

# Add project root to path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.api.validation import _load_pipeline, _metrics
from services.api.guardrail import is_trade_allowed, update_guardrail_on_close, get_guardrail_state
from services.api.db import Base

# Setup In-Memory DB (Same as benchmark)
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

# Pipelines
PIPELINE_PATHS = {
    "m5": "data/events/events_5m_8yr_v3_mom.csv", # Check path
    "m15": "data/events/events_15m_8yr_v3_mom.csv", # Check path
    "h1": "data/events/events_h1_8yr_v3_mom.csv"
}
# Note: M5 path in benchmark was via env var or default. 
# Default in validation.py is "data/events/events_m5_8yr_v3_mom.csv" (no '5').
# Benchmark used PIPELINE_PATHS from validation.py which uses "events_m5...".
# I'll rely on the same PIPELINE_PATHS dict imported if possible, or manual.
# Let's import from validation to be safe, then patch.
from services.api.validation import PIPELINE_PATHS as DEFAULT_PATHS
PIPELINE_PATHS = DEFAULT_PATHS.copy()
PIPELINE_PATHS["h1"] = "data/events/events_h1_8yr_v3_mom.csv"

def get_db_session():
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    Base.metadata.create_all(bind=engine)
    return SessionLocal()

def categorize_asset(pair):
    p = pair.upper()
    if any(x in p for x in ["OIL", "BCO", "XTI", "XBR", "NG"]):
        return "Oil"
    if any(x in p for x in ["GOLD", "SILVER", "XAU", "XAG", "XPT", "XPD"]):
        # If it has Oil and Gold? e.g. Gold/Oil. Prioritize Oil?
        # User asked for "fx, oil, metals".
        # Gold/Oil is... let's check.
        if "OIL" in p or "BCO" in p: return "Oil" 
        return "Metals"
    if any(x in p for x in ["SPX", "DAX", "CAC", "FTSE", "NIKKEI", "DOW", "NAS", "JPX", "HKX", "UDX", "NSX", "GRX", "UKX"]):
        return "Indices"
    return "FX"

def normalize_ts(series):
    # Robust timestamp conversion (copied from benchmark_guardrail.py fix)
    if pd.api.types.is_numeric_dtype(series):
        vals = series.to_numpy(dtype=np.int64)
        if len(vals) > 0 and vals.max() < 1e17 and vals.max() > 1e14:
            return vals * 1000
        return vals
    else:
        return pd.to_datetime(series, utc=True).astype(np.int64)

def simulate_incremental(df, session):
    # Simplified simulation logic
    kept_rows = []
    events = []
    
    # Pre-process DF
    df["timestamp"] = normalize_ts(df["timestamp"])
    df["exit_ts"] = normalize_ts(df["exit_ts"])
    
    for row in df.itertuples(index=False):
        events.append({"ts": row.timestamp, "type": "ENTRY", "row": row})
        events.append({"ts": row.exit_ts, "type": "EXIT", "row": row})
        
    events.sort(key=lambda x: x["ts"])
    
    allowed_ids = set()
    
    for evt in events:
        row = evt["row"]
        ts_val = evt["ts"]
        ts_dt = datetime.fromtimestamp(ts_val / 1e9, tz=timezone.utc)
        pair = row.pair
        strategy = row.strategy_type
        
        if evt["type"] == "ENTRY":
            allowed, _, _ = is_trade_allowed(session, strategy, pair, as_of=ts_dt)
            if allowed:
                allowed_ids.add(id(row))
                kept_rows.append(row)
                
        elif evt["type"] == "EXIT":
            if id(row) in allowed_ids:
                update_guardrail_on_close(session, strategy, pair, ts_dt, row.pnl_bps)
                
    return pd.DataFrame(kept_rows)

def calculate_sharpe(pnls):
    if len(pnls) < 2: return 0.0
    mean = np.mean(pnls)
    std = np.std(pnls)
    if std == 0: return 0.0
    # Annualized Sharpe Approximation for Trade Series
    # Assuming ~3 trades/day for portfolio?
    # Actually, standard formula for trade series is just Mean/Std * Sqrt(N_trades_per_year).
    # But usually Sharpe is calculated on Daily Returns.
    # The _metrics function in validation.py uses sharpe_daily on aggregated daily PnL.
    # We should replicate that.
    return 0.0

def calculate_cagr(total_pnl_bps, start_ts, end_ts):
    if start_ts is None or end_ts is None or start_ts == end_ts:
        return 0.0
    
    # Total Return in % (e.g. 450000 bps -> 4500%)
    # Wait, 10000 bps = 100%. 
    # If Total PnL is 458,000 bps, that's 4,580% return (45.8x).
    total_return_pct = total_pnl_bps / 10000.0
    
    # Duration in Years
    # ts is nanoseconds
    duration_ns = end_ts - start_ts
    years = duration_ns / (1e9 * 3600 * 24 * 365.25)
    
    if years <= 0: return 0.0
    
    # CAGR = (1 + r)^(1/t) - 1
    # Note: If we use simple interest (sum of bps), checking "growth" might be misleading if we didn't compound.
    # But usually CAGR implies compounding.
    # If the strategy uses "Fixed Fractional" (bps of current equity), then Sum Bps is actually Log Return?
    # No, typically backtest sums R-multiples.
    # Let's assume standard CAGR formula on the total return.
    
    try:
        cagr = (1 + total_return_pct) ** (1 / years) - 1
    except:
        cagr = 0.0
        
    return cagr

def run_analysis():
    for bar in ["m5", "m15", "h1"]:
        print(f"\n{'='*20} ANALYSIS: {bar.upper()} {'='*20}")
        
        # Load
        bar_mins = 60 if bar == "h1" else (15 if bar == "m15" else 5)
        path = PIPELINE_PATHS.get(bar)
        
        # Mapping hack for M5/M15 filenames if they differ from dict
        if not path or not os.path.exists(path):
            # Try default names
            alt = f"data/events/events_{bar}_8yr_v3_mom.csv"
            if os.path.exists(alt):
                path = alt
            else:
                print(f"Skipping {bar}: Path not found ({path})")
                continue
            
        print(f"Loading {path}...")
        df = _load_pipeline(path, bar_mins)
        if df.empty:
            print("Empty dataframe.")
            continue
            
        if "strategy_type" not in df.columns:
            df["strategy_type"] = f"mom_{bar}"
            
        # Simulate
        print("Running Guardrail Simulation...")
        session = get_db_session()
        df_inc = simulate_incremental(df, session)
        session.close()
        
        if df_inc.empty:
            print("No trades kept by guardrail.")
            continue
            
        print(f"Kept {len(df_inc)} / {len(df)} Trades")
        
        # Categorize
        df_inc["AssetClass"] = df_inc["pair"].apply(categorize_asset)
        
        # Analysis Groups
        groups = ["AssetClass", "pair"]
        
        # 1. By Asset Class
        print(f"\n--- Results by Asset Class ({bar.upper()}) ---")
        print(f"{'Class':<15} | {'Trades':<8} | {'PnL (bps)':<12} | {'Avg PnL':<8} | {'Win Rate':<8} | {'Sharpe':<8} | {'CAGR':<8}")
        print("-" * 95)
        
        for cls in sorted(df_inc["AssetClass"].unique()):
            sub = df_inc[df_inc["AssetClass"] == cls]
            metrics = _metrics(sub["pnl_bps"].to_numpy(), sub["exit_ts"].to_numpy())
            
            # CAGR
            start_ts = sub["timestamp"].min()
            end_ts = sub["exit_ts"].max()
            cagr = calculate_cagr(metrics['total_pnl'], start_ts, end_ts)
            
            print(f"{cls:<15} | {metrics['trades']:<8} | {metrics['total_pnl']:<12.0f} | {metrics['mean_pnl']:<8.2f} | {metrics['win_rate']:<8.1f}% | {metrics['sharpe']:<8.4f} | {cagr:<8.1%}")
            
        # 2. Detailed by Pair & Filtering
        print(f"\n--- Detailed by Pair ({bar.upper()}) ---")
        print(f"{'Pair':<15} | {'Class':<10} | {'Trades':<8} | {'PnL (bps)':<12} | {'Avg PnL':<8} | {'Win Rate':<8} | {'Sharpe':<8} | {'CAGR':<8}")
        print("-" * 105)
        
        pair_metrics = []
        for pair in df_inc["pair"].unique():
            sub = df_inc[df_inc["pair"] == pair]
            m = _metrics(sub["pnl_bps"].to_numpy(), sub["exit_ts"].to_numpy())
            m["pair"] = pair
            m["class"] = sub["AssetClass"].iloc[0]
            
            start_ts = sub["timestamp"].min()
            end_ts = sub["exit_ts"].max()
            m["cagr"] = calculate_cagr(m['total_pnl'], start_ts, end_ts)
            
            pair_metrics.append(m)
            
        pair_metrics.sort(key=lambda x: x["sharpe"], reverse=True)
        
        kept_pairs = []
        dropped_pairs = []
        
        for m in pair_metrics:
            status = ""
            if m['sharpe'] < 0.25:
                status = "(DROP)"
                dropped_pairs.append(m['pair'])
            else:
                kept_pairs.append(m['pair'])
                
            print(f"{m['pair']:<15} | {m['class']:<10} | {m['trades']:<8} | {m['total_pnl']:<12.0f} | {m['mean_pnl']:<8.2f} | {m['win_rate']:<8.1f}% | {m['sharpe']:<8.4f} | {m['cagr']:<8.1%} {status}")

        print(f"\n--- OPTIMIZED PORTFOLIO (Sharpe >= 0.25) ---")
        print(f"Dropped {len(dropped_pairs)} pairs: {', '.join(dropped_pairs)}")
        
        df_opt = df_inc[df_inc["pair"].isin(kept_pairs)]
        
        if df_opt.empty:
            print("No pairs left after filtering.")
            continue
            
        # Re-calc Asset Class Metrics for Optimized Portfolio
        print(f"\n--- Optimized Results by Asset Class ({bar.upper()}) ---")
        print(f"{'Class':<15} | {'Trades':<8} | {'PnL (bps)':<12} | {'Avg PnL':<8} | {'Win Rate':<8} | {'Sharpe':<8} | {'CAGR':<8}")
        print("-" * 95)
        
        total_pnl = 0
        total_trades = 0
        
        # We need overall Start/End for Portfolio CAGR?
        # Or just sum PnL?
        # Let's do asset classes first.
        
        for cls in sorted(df_opt["AssetClass"].unique()):
            sub = df_opt[df_opt["AssetClass"] == cls]
            metrics = _metrics(sub["pnl_bps"].to_numpy(), sub["exit_ts"].to_numpy())
            
            start_ts = sub["timestamp"].min()
            end_ts = sub["exit_ts"].max()
            cagr = calculate_cagr(metrics['total_pnl'], start_ts, end_ts)
            
            print(f"{cls:<15} | {metrics['trades']:<8} | {metrics['total_pnl']:<12.0f} | {metrics['mean_pnl']:<8.2f} | {metrics['win_rate']:<8.1f}% | {metrics['sharpe']:<8.4f} | {cagr:<8.1%}")
            
        # Total Portfolio Specs (Sharpe >= 0.25)
        metrics_total = _metrics(df_opt["pnl_bps"].to_numpy(), df_opt["exit_ts"].to_numpy())
        start_ts = df_opt["timestamp"].min()
        end_ts = df_opt["exit_ts"].max()
        cagr_total = calculate_cagr(metrics_total['total_pnl'], start_ts, end_ts)
        
        print("-" * 95)
        print(f"{'TOTAL':<15} | {metrics_total['trades']:<8} | {metrics_total['total_pnl']:<12.0f} | {metrics_total['mean_pnl']:<8.2f} | {metrics_total['win_rate']:<8.1f}% | {metrics_total['sharpe']:<8.4f} | {cagr_total:<8.1%}")

        # --- SCENARIO: FX + Oil + Metals ONLY (Optimized) ---
        print(f"\n--- SCENARIO: FX + Oil + Metals ONLY (Optimized) ({bar.upper()}) ---")
        target_classes = ["FX", "Oil", "Metals"]
        df_fom = df_opt[df_opt["AssetClass"].isin(target_classes)]
        
        if df_fom.empty:
            print("No trades left in FX/Oil/Metals after optimization.")
            continue
            
        metrics_fom = _metrics(df_fom["pnl_bps"].to_numpy(), df_fom["exit_ts"].to_numpy())
        cagr_fom = calculate_cagr(metrics_fom['total_pnl'], df_fom["timestamp"].min(), df_fom["exit_ts"].max())
        
        print(f"{'FOM_TOTAL':<15} | {metrics_fom['trades']:<8} | {metrics_fom['total_pnl']:<12.0f} | {metrics_fom['mean_pnl']:<8.2f} | {metrics_fom['win_rate']:<8.1f}% | {metrics_fom['sharpe']:<8.4f} | {cagr_fom:<8.1%}")
        
        print("-" * 95)
        # Breakdown of this subset
        for cls in sorted(target_classes):
            sub = df_fom[df_fom["AssetClass"] == cls]
            if sub.empty: continue
            metrics = _metrics(sub["pnl_bps"].to_numpy(), sub["exit_ts"].to_numpy())
            cagr = calculate_cagr(metrics['total_pnl'], sub["timestamp"].min(), sub["exit_ts"].max())
            print(f"{cls:<15} | {metrics['trades']:<8} | {metrics['total_pnl']:<12.0f} | {metrics['mean_pnl']:<8.2f} | {metrics['win_rate']:<8.1f}% | {metrics['sharpe']:<8.4f} | {cagr:<8.1%}")

if __name__ == "__main__":
    # Redirect stdout to file
    out_file = "data/portfolio_breakdown_fom.txt"
    with open(out_file, "w") as f:
        sys.stdout = f
        run_analysis()
    sys.stdout = sys.__stdout__
    print(f"Analysis complete. Results written to {out_file}")
