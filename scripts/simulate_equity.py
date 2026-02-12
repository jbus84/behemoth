
import pandas as pd
import numpy as np
import sys
from pathlib import Path

# Add root to sys.path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from behemoth.config import POSITION_SIZE_PCT
from behemoth.core.guardrail import apply_loss_streak_guardrail
from services.api.validation import _compute_exit_ts

PIPELINE_PATHS = {
    "m5": ("data/events/events_m5_8yr_v3_mom.csv", 5),
    "m15": ("data/events/events_m15_8yr_v3_mom.csv", 15),
}

def simulate_equity_curve(df: pd.DataFrame, start_equity: float = 100000.0) -> dict:
    if df.empty:
        return {}
    
    # Sort chronologically by entry
    if "timestamp" in df.columns:
        df = df.sort_values("timestamp")
    
    equity = start_equity
    peak_equity = start_equity
    max_dd_pct = 0.0
    
    pnls_usd = []
    equities = [start_equity]
    dates = []
    
    # Simple simulation: assuming sequential trades for now (approx)
    
    for row in df.itertuples():
        # Dynamic Sizing: 1% of current equity
        target_usd = equity * POSITION_SIZE_PCT
        
        # PnL USD = Notional * BPS / 10000
        pnl_bps = getattr(row, "pnl_bps", 0.0)
        pnl_usd = target_usd * (pnl_bps / 10000.0)
        
        equity += pnl_usd
        
        # Track Max DD
        peak_equity = max(peak_equity, equity)
        dd = (equity - peak_equity) / peak_equity
        max_dd_pct = min(max_dd_pct, dd)
        
        pnls_usd.append(pnl_usd)
        equities.append(equity)
        if hasattr(row, "timestamp"):
             dates.append(pd.to_datetime(row.timestamp, unit="ns", utc=True))

    total_return_pct = (equity - start_equity) / start_equity * 100.0
    
    # Daily Sharpe on Equity Curve
    sharpe = 0.0
    if dates:
        equity_series = pd.Series(equities[1:], index=dates)
        daily_returns = equity_series.resample("D").last().pct_change().dropna()
        if len(daily_returns) > 1 and daily_returns.std() > 0:
            sharpe = (daily_returns.mean() / daily_returns.std()) * np.sqrt(252)

    return {
        "trades": len(df),
        "start_equity": start_equity,
        "end_equity": equity,
        "total_return_pct": total_return_pct,
        "max_dd_pct": max_dd_pct * 100.0,
        "sharpe_daily": sharpe
    }

def main():
    print(f"Simulating Equity using POSITION_SIZE_PCT = {POSITION_SIZE_PCT} (1%)\n")
    
    for bar, (path, mins) in PIPELINE_PATHS.items():
        if not Path(path).exists():
            print(f"Skipping {bar}: File not found {path}")
            continue
            
        print(f"--- {bar.upper()} ---")
        
        # Load & Prep
        df = pd.read_csv(path)
        if "exit_ts" not in df.columns:
            df["exit_ts"] = _compute_exit_ts(df, mins)
        
        # 1. Baseline
        stats = simulate_equity_curve(df)
        print(f"[Baseline]  Trades: {stats['trades']} | Sharpe: {stats['sharpe_daily']:.2f} | Return: {stats['total_return_pct']:.2f}% | DD: {stats['max_dd_pct']:.2f}%")
        
        # 2. Guardrail
        # Standard settings: loss_streak=3, cooldown=7 days
        df_guard = apply_loss_streak_guardrail(df, loss_streak=3, cooldown_days=7)
        stats_g = simulate_equity_curve(df_guard)
        print(f"[Guardrail] Trades: {stats_g['trades']} | Sharpe: {stats_g['sharpe_daily']:.2f} | Return: {stats_g['total_return_pct']:.2f}% | DD: {stats_g['max_dd_pct']:.2f}%")
        print("")

if __name__ == "__main__":
    main()
