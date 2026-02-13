"""Compare baseline performance: All pairs vs FX+Metals+Oil only (no index legs)."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import numpy as np
import pandas as pd

from services.api.validation import _load_pipeline, _metrics, _apply_guardrail_df, PIPELINE_PATHS

INDEX_PAIRS = {
    "SPX/CAC", "SPX/DAX", "SPX/Dow", "SPX/FTSE",
    "SPX/HK", "SPX/Nas", "SPX/Nikkei", "CAC/NZD",
}


def run_comparison(bar: str, bar_minutes: int):
    path = PIPELINE_PATHS[bar]
    df = _load_pipeline(path, bar_minutes)
    if df.empty:
        print(f"  No data for {bar}")
        return

    # Full baseline (all pairs)
    df_all = df.copy()
    df_all_g = _apply_guardrail_df(df_all)

    # Filtered: exclude index pairs
    df_filt = df[~df["pair"].isin(INDEX_PAIRS)].copy()
    df_filt_g = _apply_guardrail_df(df_filt)

    # Per-pair breakdown for excluded pairs
    print(f"\n{'='*70}")
    print(f"  {bar.upper()} BASELINE COMPARISON")
    print(f"{'='*70}")

    # Show what we're excluding
    idx_df = df[df["pair"].isin(INDEX_PAIRS)]
    print(f"\n  Index pairs excluded: {sorted(idx_df['pair'].unique())}")
    print(f"  Index trades: {len(idx_df)} / {len(df)} total ({100*len(idx_df)/len(df):.1f}%)")

    # Metrics comparison
    def fmt(m):
        return (f"  Trades: {m['trades']:>5}  |  WinRate: {m['win_rate']:>5.1f}%  |  "
                f"Mean PnL: {m['mean_pnl']:>7.2f} bps  |  Total PnL: {m['total_pnl']:>9.1f} bps  |  "
                f"MaxDD: {m['max_dd']:>9.1f} bps  |  Sharpe: {m['sharpe']:>6.2f}  |  "
                f"SharpeTrade: {m['sharpe_trade']:>6.2f}")

    m_all = _metrics(df_all["pnl_bps"].to_numpy(), df_all["exit_ts"].to_numpy())
    m_all_g = _metrics(df_all_g["pnl_bps"].to_numpy(), df_all_g["exit_ts"].to_numpy())
    m_filt = _metrics(df_filt["pnl_bps"].to_numpy(), df_filt["exit_ts"].to_numpy())
    m_filt_g = _metrics(df_filt_g["pnl_bps"].to_numpy(), df_filt_g["exit_ts"].to_numpy())

    print(f"\n  --- All Pairs (Raw) ---")
    print(fmt(m_all))
    print(f"  --- All Pairs (Guardrail) ---")
    print(fmt(m_all_g))
    print(f"\n  --- FX+Metals+Oil Only (Raw) ---")
    print(fmt(m_filt))
    print(f"  --- FX+Metals+Oil Only (Guardrail) ---")
    print(fmt(m_filt_g))

    # Per-pair performance for index pairs
    print(f"\n  --- Index Pair Breakdown ---")
    print(f"  {'Pair':<15} {'Trades':>6} {'WinRate':>8} {'MeanPnL':>9} {'TotalPnL':>10} {'Sharpe':>7}")
    for pair in sorted(INDEX_PAIRS):
        sub = df[df["pair"] == pair]
        if sub.empty:
            continue
        pnls = sub["pnl_bps"].to_numpy()
        wr = float((pnls > 0).mean() * 100)
        mp = float(np.mean(pnls))
        tp = float(np.sum(pnls))
        ts = sub["exit_ts"].to_numpy()
        from behemoth.core.metrics import sharpe_trade as st
        s = float(st(pnls, ts)) if len(pnls) > 1 else 0.0
        print(f"  {pair:<15} {len(pnls):>6} {wr:>7.1f}% {mp:>9.2f} {tp:>10.1f} {s:>7.2f}")

    # Per-pair performance for kept pairs
    print(f"\n  --- Kept Pair Breakdown (Raw vs Guardrailed) ---")
    print(f"  {'Pair':<15} {'Trades':>6} {'WR%':>6} {'Mean':>7} {'Sharpe':>7}  |  {'G-Trades':>8} {'G-WR%':>6} {'G-Mean':>7} {'G-Sharpe':>8}")
    kept_pairs = sorted(df_filt["pair"].unique())
    for pair in kept_pairs:
        sub = df_filt[df_filt["pair"] == pair]
        # Raw
        pnls = sub["pnl_bps"].to_numpy()
        wr = float((pnls > 0).mean() * 100)
        mp = float(np.mean(pnls))
        ts = sub["exit_ts"].to_numpy()
        from behemoth.core.metrics import sharpe_trade as st
        s = float(st(pnls, ts)) if len(pnls) > 1 else 0.0
        
        # Guardrailed
        sub_g = _apply_guardrail_df(sub)
        pnls_g = sub_g["pnl_bps"].to_numpy()
        wr_g = float((pnls_g > 0).mean() * 100) if len(pnls_g) > 0 else 0.0
        mp_g = float(np.mean(pnls_g)) if len(pnls_g) > 0 else 0.0
        ts_g = sub_g["exit_ts"].to_numpy()
        s_g = float(st(pnls_g, ts_g)) if len(pnls_g) > 1 else 0.0

        print(f"  {pair:<15} {len(pnls):>6} {wr:>5.1f}% {mp:>7.2f} {s:>7.2f}  |  {len(pnls_g):>8} {wr_g:>5.1f}% {mp_g:>7.2f} {s_g:>8.2f}")


if __name__ == "__main__":
    run_comparison("m15", 15)
