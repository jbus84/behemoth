"""Weekly MR with stop-loss simulation — can we cap DD at ~10% without killing edge?

Takes the validated weekly mean-reversion trades and adds a daily-path stop loss.
For each trade we simulate the daily mark-to-market using the causal daily return path.
If the cumulative PnL hits the stop before the 5-day hold expires, we exit at stop.

Tests stops at: -50, -75, -100, -125, -150, -200 bps (roughly -5% to -20%)
Reports: trades, accuracy, net, max DD, Sharpe, Calmar, pos-years.

Usage: uv run python scripts/fx_coint/weekly_stop_simulation.py
"""
# ruff: noqa: E402
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import polars as pl

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import scripts.fx_coint.reg_signal_hunt as rsh

rsh.FREQ_MINUTES["1d"] = 1440
TIGHT = ["EURUSD", "GBPUSD", "USDJPY"]
STOPS = [-50, -75, -100, -125, -150, -200, None]
RNG = np.random.default_rng(0)

COMM = 0.60
SPR = {"EURUSD": .1, "USDJPY": .1, "GBPUSD": .2, "USDCAD": .3, "AUDUSD": .15, "USDCHF": .3}
PX = {"EURUSD": 1.08, "USDJPY": 150., "GBPUSD": 1.27, "USDCAD": 1.36, "AUDUSD": .65, "USDCHF": .89}


def cost(sym):
    pip = 0.01 if sym.endswith("JPY") else 0.0001
    return COMM + (SPR[sym] * pip / PX[sym]) * 1e4


def daily_series(sym):
    src = _REPO_ROOT / f"data/tick_bars/{sym}_1m_flow.parquet"
    if not src.exists():
        candidate = _REPO_ROOT
        while candidate.name != "behemoth" and candidate.parent != candidate:
            candidate = candidate.parent
        src = candidate / f"data/tick_bars/{sym}_1m_flow.parquet"
    bars = rsh.build_freq_bars(pl.read_parquet(src), "1d", session=(0, 24))
    mid = bars["mid"].to_numpy()
    r = np.empty(len(mid))
    r[0] = np.nan
    r[1:] = (np.log(mid[1:]) - np.log(mid[:-1])) * 1e4
    r[~bars["contig"].to_numpy()] = np.nan
    return mid, r, bars["bucket"].to_numpy()


def build_trades(sym):
    """Build weekly MR trades with daily path for stop simulation."""
    mid, r, bk = daily_series(sym)
    rs = pd.Series(r)
    sig = (rs.rolling(10, min_periods=5).sum()).to_numpy()
    n = len(mid)
    # Forward returns for each day (causal)
    fwd = np.full((n, 5), np.nan)
    for h in range(1, 6):
        fwd[:n - h, h - 1] = (np.log(mid[h:]) - np.log(mid[:n - h])) * 1e4

    # Causal decile thresholds on first half
    split = n // 2
    hi = np.nanquantile(sig[:split], 0.90)
    lo = np.nanquantile(sig[:split], 0.10)

    trades = []
    for i in range(split, n):
        s = sig[i]
        c = cost(sym)
        if s >= hi and np.isfinite(fwd[i]).all():
            # Extended up -> short (fade)
            trades.append({
                "sym": sym,
                "entry_idx": i,
                "bucket": pd.Timestamp(bk[i]),
                "direction": -1,
                "path": -fwd[i],  # short path = -forward returns
                "final": -fwd[i][-1],
                "cost": c,
            })
        elif s <= lo and np.isfinite(fwd[i]).all():
            # Extended down -> long (fade)
            trades.append({
                "sym": sym,
                "entry_idx": i,
                "bucket": pd.Timestamp(bk[i]),
                "direction": 1,
                "path": fwd[i],  # long path = forward returns
                "final": fwd[i][-1],
                "cost": c,
            })
    return pd.DataFrame(trades)


def simulate_with_stop(trades_df, stop_bps):
    """Apply stop loss to trades. Returns DataFrame with realized PnL."""
    out = trades_df.copy()
    out["pnl"] = out["final"] - out["cost"]
    out["hit_stop"] = False
    if stop_bps is None:
        return out

    for idx, row in out.iterrows():
        path = row["path"]
        # Running cumulative from entry
        cum = np.cumsum(path)
        # For long: stop triggers if cum <= stop_bps
        # For short: stop triggers if cum >= -stop_bps (loss on short)
        if row["direction"] == 1:
            breach = np.where(cum <= stop_bps)[0]
        else:
            breach = np.where(cum >= -stop_bps)[0]
        if len(breach):
            out.at[idx, "pnl"] = stop_bps - row["cost"]  # stop level minus cost
            out.at[idx, "hit_stop"] = True
    return out


def metrics(trades_df):
    if len(trades_df) == 0:
        return {}
    pnl = trades_df["pnl"].to_numpy()
    gross = trades_df["final"].to_numpy() if "final" in trades_df.columns else pnl
    wins = pnl > 0
    yr = trades_df.copy()
    yr["year"] = pd.to_datetime(yr["bucket"]).dt.year
    yr_agg = yr.groupby("year")["pnl"].mean()
    pos_years = int((yr_agg > 0).sum())
    n_years = len(yr_agg)
    return {
        "n": len(pnl),
        "acc": float(np.mean(wins)),
        "net": float(np.mean(pnl)),
        "gross": float(np.mean(gross)),
        "win_avg": float(np.mean(pnl[wins])) if wins.any() else 0.0,
        "loss_avg": float(np.mean(pnl[~wins])) if (~wins).any() else 0.0,
        "max_dd_bps": float(np.min(pnl.cumsum() - np.maximum.accumulate(pnl.cumsum()))) if len(pnl) > 1 else 0.0,
        "pos_years": f"{pos_years}/{n_years}",
        "stop_pct": float(np.mean(trades_df["hit_stop"])) if "hit_stop" in trades_df.columns else 0.0,
    }


def main():
    print("=" * 100)
    print("WEEKLY MR STOP-LOSS SIMULATION")
    print("=" * 100)
    print("Testing various stop levels to see if we can cap DD without killing edge.")
    print()

    # Build all trades
    all_trades = []
    for sym in TIGHT:
        df = build_trades(sym)
        if len(df):
            all_trades.append(df)
    if not all_trades:
        print("No trades generated.")
        return
    base_df = pd.concat(all_trades, ignore_index=True)

    print(f"Base trades generated: {len(base_df)} across {TIGHT}")
    print()

    # Simulate each stop
    print(f"{'Stop':>6s} {'Trades':>7s} {'Acc':>6s} {'Net':>7s} {'Gross':>7s} {'WinAvg':>7s} {'LossAvg':>8s} {'MaxDD':>8s} {'PosYrs':>7s} {'StopHit':>7s}")
    print("-" * 100)
    for stop in STOPS:
        sim = simulate_with_stop(base_df, stop)
        m = metrics(sim)
        label = "None" if stop is None else f"{stop}"
        print(f"{label:>6s} {m['n']:>7d} {m['acc']:>6.3f} {m['net']:>+7.2f} {m['gross']:>+7.2f} "
              f"{m['win_avg']:>+7.2f} {m['loss_avg']:>+8.2f} {m['max_dd_bps']:>+8.2f} {m['pos_years']:>7s} {m['stop_pct']:>6.1%}")

    # Now show the scaling to 10% DD for the best stop
    print()
    print("=" * 100)
    print("POSITION SIZING FOR 10% MAX DD (best stop level)")
    print("=" * 100)
    for stop in [-50, -75, -100, -125, -150]:
        sim = simulate_with_stop(base_df, stop)
        m = metrics(sim)
        dd = abs(m["max_dd_bps"])
        if dd > 0:
            scale = 1000 / dd
            ann_ret = m["net"] * scale * (m["n"] / 8)  # rough annualization
            print(f"Stop {stop} bps: size {scale:.1%} → ~{ann_ret:.0f} bps/year = {ann_ret/100:.1f}%")


if __name__ == "__main__":
    main()
