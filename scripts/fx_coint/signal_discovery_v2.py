#!/usr/bin/env python3
"""Signal discovery v2: rolling trend detection after quiet periods.

Hypothesis: After a quiet/consolidation period, a coherent directional
move of 2-3 consecutive minutes is more likely to persist than a single
spike. We detect the move as it starts and measure persistence.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import duckdb  # noqa: E402

from scripts.canonical_tick_feed import (  # noqa: E402
    DEFAULT_CANONICAL_ROOT,
    month_tags_between,
    quote_sql_path,
)


def load_ticks(symbol: str, start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    sym = symbol.upper()
    files_all = sorted((DEFAULT_CANONICAL_ROOT / sym).glob(f"{sym}_*_ticks.parquet"))
    tags = set(month_tags_between(start, end))
    files = [p for p in files_all if any(tag in p.name for tag in tags)]
    if not files:
        files = files_all
    files_sql = "[" + ",".join(quote_sql_path(p) for p in files) + "]"
    con = duckdb.connect()
    sql = f"""
    SELECT
        try_cast(timestamp AS TIMESTAMP WITH TIME ZONE) AS ts,
        try_cast(bid AS DOUBLE) AS bid,
        try_cast(ask AS DOUBLE) AS ask
    FROM read_parquet({files_sql})
    WHERE ts IS NOT NULL AND bid IS NOT NULL AND ask IS NOT NULL
    ORDER BY ts
    """
    df = con.execute(sql).fetchdf()
    con.close()
    df["ts"] = pd.to_datetime(df["ts"], utc=True)
    df["mid"] = (df["bid"] + df["ask"]) / 2
    return df.dropna().reset_index(drop=True)


def build_minute_bars(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["minute"] = df["ts"].dt.floor("1min")
    g = df.groupby("minute")
    bars = pd.DataFrame({
        "open": g["mid"].first(),
        "high": g["mid"].max(),
        "low": g["mid"].min(),
        "close": g["mid"].last(),
        "n_ticks": g.size(),
    }).reset_index().rename(columns={"minute": "timestamp"})
    bars = bars.sort_values("timestamp").reset_index(drop=True)
    return bars


def compute_features(bars: pd.DataFrame) -> pd.DataFrame:
    b = bars.copy()
    b["ret"] = np.log(b["close"] / b["open"])
    b["range"] = (b["high"] - b["low"]) / b["open"]

    # Causal context only
    b["ret_lag1"] = b["ret"].shift(1)
    b["ret_lag2"] = b["ret"].shift(2)
    b["ret_lag3"] = b["ret"].shift(3)
    b["abs_ret_ma5"] = b["ret"].abs().rolling(5, min_periods=3).mean().shift(1)
    b["abs_ret_ma20"] = b["ret"].abs().rolling(20, min_periods=10).mean().shift(1)
    b["range_ma5"] = b["range"].rolling(5, min_periods=3).mean().shift(1)
    b["range_ma20"] = b["range"].rolling(20, min_periods=10).mean().shift(1)
    return b


def test_rolling_trend(b: pd.DataFrame) -> None:
    """Test: after N consecutive minutes in same direction, does it persist?"""
    print("\n" + "=" * 70)
    print("ROLLING TREND TEST: Consecutive directional minutes")
    print("=" * 70)

    b = b.dropna().copy()

    # Signal 1: 2 consecutive minutes same direction after quiet period
    b["sig_2up"] = (
        (b["ret"] > 0) & (b["ret_lag1"] > 0)
        & (b["abs_ret_ma20"] < b["abs_ret_ma20"].quantile(0.50))
    )
    b["sig_2dn"] = (
        (b["ret"] < 0) & (b["ret_lag1"] < 0)
        & (b["abs_ret_ma20"] < b["abs_ret_ma20"].quantile(0.50))
    )

    # Signal 2: 3 consecutive minutes same direction
    b["sig_3up"] = (
        (b["ret"] > 0) & (b["ret_lag1"] > 0) & (b["ret_lag2"] > 0)
        & (b["abs_ret_ma20"] < b["abs_ret_ma20"].quantile(0.50))
    )
    b["sig_3dn"] = (
        (b["ret"] < 0) & (b["ret_lag1"] < 0) & (b["ret_lag2"] < 0)
        & (b["abs_ret_ma20"] < b["abs_ret_ma20"].quantile(0.50))
    )

    for h in [1, 2, 3, 5, 10]:
        b[f"fwd_{h}"] = np.log(b["close"].shift(-h) / b["close"])

    for sig_name, up_col, dn_col in [
        ("2-min trend after quiet", "sig_2up", "sig_2dn"),
        ("3-min trend after quiet", "sig_3up", "sig_3dn"),
    ]:
        up = b[b[up_col]]
        dn = b[b[dn_col]]
        print(f"\n{sig_name}: UP={len(up):,}, DN={len(dn):,}")
        for h in [1, 2, 3, 5, 10]:
            if len(up) > 10 and len(dn) > 10:
                pnl = pd.concat([up[f"fwd_{h}"].dropna(), -dn[f"fwd_{h}"].dropna()])
                mean_pnl = pnl.mean()
                print(f"  h={h:2d}: mean={mean_pnl*10000:+.3f} bp  n={len(pnl)}")


def test_breakout(b: pd.DataFrame) -> None:
    """Test: breakout from a recent range."""
    print("\n" + "=" * 70)
    print("BREAKOUT TEST: Price breaks recent high/low")
    print("=" * 70)

    b = b.dropna().copy()

    # Rolling high/low over last 20 minutes
    b["roll_high_20"] = b["high"].rolling(20, min_periods=10).max().shift(1)
    b["roll_low_20"] = b["low"].rolling(20, min_periods=10).min().shift(1)

    # Breakout signal: close breaks above/below the 20-min range
    # But only if prior range was tight (consolidation)
    b["prior_range"] = (b["roll_high_20"] - b["roll_low_20"]) / b["open"]
    b["was_tight"] = b["prior_range"] < b["prior_range"].quantile(0.30)

    b["breakout_up"] = (b["close"] > b["roll_high_20"]) & b["was_tight"]
    b["breakout_dn"] = (b["close"] < b["roll_low_20"]) & b["was_tight"]

    for h in [1, 2, 3, 5, 10]:
        b[f"fwd_{h}"] = np.log(b["close"].shift(-h) / b["close"])

    up = b[b["breakout_up"]]
    dn = b[b["breakout_dn"]]
    print(f"\nBreakout from tight range: UP={len(up):,}, DN={len(dn):,}")
    for h in [1, 2, 3, 5, 10]:
        if len(up) > 10 and len(dn) > 10:
            pnl = pd.concat([up[f"fwd_{h}"].dropna(), -dn[f"fwd_{h}"].dropna()])
            mean_pnl = pnl.mean()
            print(f"  h={h:2d}: mean={mean_pnl*10000:+.3f} bp  n={len(pnl)}")

    # Also: does the breakout direction matter?
    print("\n--- Breakout direction accuracy ---")
    for h in [1, 3, 5, 10]:
        if len(up) > 10:
            acc_up = (up[f"fwd_{h}"].dropna() > 0).mean()
            print(f"  UP breakout, h={h:2d}: {acc_up*100:.1f}% continue up")
        if len(dn) > 10:
            acc_dn = (dn[f"fwd_{h}"].dropna() < 0).mean()
            print(f"  DN breakout, h={h:2d}: {acc_dn*100:.1f}% continue down")


def test_volatility_expansion(b: pd.DataFrame) -> None:
    """Test: sudden volatility expansion with direction."""
    print("\n" + "=" * 70)
    print("VOLATILITY EXPANSION: Sudden range expansion with direction")
    print("=" * 70)

    b = b.dropna().copy()

    # Minute has much larger range than recent average AND directional close
    b["range_expansion"] = b["range"] > (b["range_ma20"] * 2.0)
    b["directional_up"] = (b["close"] > b["open"]) & ((b["close"] - b["open"]) > (b["range"] * 0.6))
    b["directional_dn"] = (b["close"] < b["open"]) & ((b["open"] - b["close"]) > (b["range"] * 0.6))

    b["sig_vol_up"] = b["range_expansion"] & b["directional_up"] & (b["range_ma20"] < b["range_ma20"].quantile(0.40))
    b["sig_vol_dn"] = b["range_expansion"] & b["directional_dn"] & (b["range_ma20"] < b["range_ma20"].quantile(0.40))

    for h in [1, 2, 3, 5, 10]:
        b[f"fwd_{h}"] = np.log(b["close"].shift(-h) / b["close"])

    up = b[b["sig_vol_up"]]
    dn = b[b["sig_vol_dn"]]
    print(f"\nVol expansion + directional: UP={len(up):,}, DN={len(dn):,}")
    for h in [1, 2, 3, 5, 10]:
        if len(up) > 10 and len(dn) > 10:
            pnl = pd.concat([up[f"fwd_{h}"].dropna(), -dn[f"fwd_{h}"].dropna()])
            mean_pnl = pnl.mean()
            print(f"  h={h:2d}: mean={mean_pnl*10000:+.3f} bp  n={len(pnl)}")


def test_microstructure_momentum(b: pd.DataFrame) -> None:
    """Test: does the CLOSE of a minute relative to its range predict next minute?"""
    print("\n" + "=" * 70)
    print("MICROSTRUCTURE MOMENTUM: Close position in minute predicts next minute")
    print("=" * 70)

    b = b.dropna().copy()

    # Close position: where in the minute's range did we close?
    b["close_pos"] = np.where(
        b["range"] > 0,
        (b["close"] - b["low"]) / (b["high"] - b["low"]),
        0.5,
    )

    # Extreme close positions
    b["closed_top"] = b["close_pos"] > 0.90
    b["closed_bottom"] = b["close_pos"] < 0.10

    b["fwd_1"] = np.log(b["close"].shift(-1) / b["close"])

    top = b[b["closed_top"]]
    bot = b[b["closed_bottom"]]

    print(f"\nClosed at top (>90%): {len(top):,}")
    print(f"  Next minute mean: {top['fwd_1'].mean()*10000:+.3f} bp")
    print(f"  Next minute up %:   {(top['fwd_1'] > 0).mean()*100:.1f}%")

    print(f"\nClosed at bottom (<10%): {len(bot):,}")
    print(f"  Next minute mean: {bot['fwd_1'].mean()*10000:+.3f} bp")
    print(f"  Next minute down %: {(bot['fwd_1'] < 0).mean()*100:.1f}%")

    # Combined: long top, short bottom
    if len(top) > 10 and len(bot) > 10:
        pnl = pd.concat([top["fwd_1"].dropna(), -bot["fwd_1"].dropna()])
        print(f"\nCombined (long top, short bottom): mean={pnl.mean()*10000:+.3f} bp  n={len(pnl)}")

    # But what about AFTER a quiet period?
    quiet = b["range_ma20"] < b["range_ma20"].quantile(0.30)
    top_q = b[b["closed_top"] & quiet]
    bot_q = b[b["closed_bottom"] & quiet]
    print("\n--- After QUIET period ---")
    print(f"Top, n={len(top_q)}: next mean={top_q['fwd_1'].mean()*10000:+.3f} bp, up %={(top_q['fwd_1']>0).mean()*100:.1f}%")
    print(f"Bot, n={len(bot_q)}: next mean={bot_q['fwd_1'].mean()*10000:+.3f} bp, dn %={(bot_q['fwd_1']<0).mean()*100:.1f}%")


def main() -> None:
    print("Loading EURUSD ticks for 2024...")
    start = pd.Timestamp("2024-01-01", tz="UTC")
    end = pd.Timestamp("2024-12-31", tz="UTC")
    ticks = load_ticks("EURUSD", start, end)
    print(f"Loaded {len(ticks):,} ticks")

    print("Building minute bars...")
    bars = build_minute_bars(ticks)
    print(f"Built {len(bars):,} minute bars")

    print("Computing features...")
    bars = compute_features(bars)

    test_rolling_trend(bars)
    test_breakout(bars)
    test_volatility_expansion(bars)
    test_microstructure_momentum(bars)

    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print("Look for signals where combined mean is > +0.2 bp per trade.")
    print("That would cover a 1.2 pip spread over 5-6 trades.")


if __name__ == "__main__":
    main()
