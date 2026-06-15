#!/usr/bin/env python3
"""Signal discovery v3: Trade minute-level momentum WITHIN big hours.

The data showed:
- Big hours (top 10% by range) have minute autocorr +0.028 (momentum)
- Normal hours have minute autocorr -0.010 (mean-reversion)

This tests the honest strategy: detect a big hour early, then ride
minute-level momentum for the rest of that hour.
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
    }).reset_index().rename(columns={"minute": "timestamp"})
    bars = bars.sort_values("timestamp").reset_index(drop=True)
    return bars


def test_big_hour_momentum(bars: pd.DataFrame) -> None:
    """Test: Can we detect a big hour early, then ride minute momentum?"""
    print("\n" + "=" * 70)
    print("BIG HOUR MOMENTUM: Detect early, trade the rest")
    print("=" * 70)

    bars = bars.copy()
    bars["ret"] = np.log(bars["close"] / bars["open"])
    bars["abs_ret"] = bars["ret"].abs()
    bars["range"] = (bars["high"] - bars["low"]) / bars["open"]
    bars["hour"] = bars["timestamp"].dt.floor("1h")

    # Compute hourly stats
    hourly = bars.groupby("hour").agg({
        "open": "first",
        "high": "max",
        "low": "min",
        "close": "last",
        "range": "sum",
    }).reset_index()
    hourly["h_range"] = (hourly["high"] - hourly["low"]) / hourly["open"]
    hourly["h_ret"] = np.log(hourly["close"] / hourly["open"])

    # Define big hours (top 10% by range)
    big_threshold = hourly["h_range"].quantile(0.90)
    hourly["is_big"] = hourly["h_range"] >= big_threshold

    # Merge back to minute bars
    bars = bars.merge(hourly[["hour", "is_big", "h_range"]], on="hour", how="left")
    bars["minute_of_hour"] = bars["timestamp"].dt.minute

    # Strategy 1: Look at first N minutes of each hour
    # If the hour ends up being big, what was the signal in first N minutes?
    print(f"\nBig hour threshold (90th pct): {big_threshold*10000:.2f} bp")
    print(f"Big hours: {hourly['is_big'].sum()} / {len(hourly)}")

    # What happens IN big hours AFTER the first 5 minutes?
    print("\n--- Trading AFTER first 5 minutes in big hours ---")
    big_minutes = bars[bars["is_big"]].copy()

    for entry_min in [5, 10, 15]:
        entry = big_minutes[big_minutes["minute_of_hour"] == entry_min]
        if len(entry) == 0:
            continue

        # Enter in direction of first 5 minutes
        entry["first5_ret"] = entry.apply(
            lambda row: big_minutes[
                (big_minutes["hour"] == row["hour"]) &
                (big_minutes["minute_of_hour"] < entry_min)
            ]["ret"].sum(),
            axis=1,
        )

        for exit_min in [10, 20, 30, 45, 55]:
            if exit_min <= entry_min:
                continue
            # Compute exit return
            entry[f"exit_ret_{exit_min}"] = entry.apply(
                lambda row: big_minutes[
                    (big_minutes["hour"] == row["hour"]) &
                    (big_minutes["minute_of_hour"] == exit_min)
                ]["ret"].sum() if len(big_minutes[
                    (big_minutes["hour"] == row["hour"]) &
                    (big_minutes["minute_of_hour"] == exit_min)
                ]) > 0 else np.nan,
                axis=1,
            )

            # Directional strategy: long if first5_ret > 0, short if < 0
            pos = np.sign(entry["first5_ret"])
            pnl = pos * entry[f"exit_ret_{exit_min}"]
            pnl = pnl.dropna()
            if len(pnl) > 10:
                print(f"  Entry@min{entry_min}, Exit@min{exit_min}: mean={pnl.mean()*10000:+.3f} bp  n={len(pnl)}  acc={(pnl>0).mean()*100:.1f}%")

    # Strategy 2: Real-time detection
    # Can we detect a big hour using only the first 5 minutes?
    print("\n--- Real-time detection: Can first 5 minutes predict big hour? ---")

    # For each hour, compute first-5-min stats
    hour_stats = []
    for h, group in bars.groupby("hour"):
        first5 = group[group["minute_of_hour"] < 5]
        if len(first5) >= 3:
            hour_stats.append({
                "hour": h,
                "f5_range": first5["range"].sum(),
                "f5_ret": first5["ret"].sum(),
                "f5_abs_ret": first5["abs_ret"].sum(),
                "f5_eff": abs(first5["ret"].sum()) / (first5["range"].sum() + 1e-12),
                "h_range": group["range"].sum(),
                "is_big": group["is_big"].iloc[0],
            })

    hs = pd.DataFrame(hour_stats)

    # Predictive power of first-5-min features
    for feat in ["f5_range", "f5_ret", "f5_abs_ret", "f5_eff"]:
        corr = hs[feat].corr(hs["h_range"])
        print(f"  Corr({feat}, hourly_range): {corr:.4f}")

    # Threshold test: if first-5-min range is high, is hour more likely to be big?
    thresh = hs["f5_range"].quantile(0.80)
    high_f5 = hs[hs["f5_range"] >= thresh]
    low_f5 = hs[hs["f5_range"] < thresh]
    print(f"\n  High first-5 range (top 20%): {high_f5['is_big'].mean()*100:.1f}% are big hours")
    print(f"  Low first-5 range (bottom 80%): {low_f5['is_big'].mean()*100:.1f}% are big hours")

    # If we ONLY trade hours with high first-5 range, what happens?
    print("\n--- Trading only high first-5-range hours ---")
    tradeable = hs[hs["f5_range"] >= thresh].copy()
    for hold_mins in [10, 20, 30]:
        tradeable[f"pnl_{hold_mins}"] = np.nan
        for idx, row in tradeable.iterrows():
            h = row["hour"]
            hour_data = bars[bars["hour"] == h]
            entry_data = hour_data[hour_data["minute_of_hour"] == 5]
            exit_data = hour_data[hour_data["minute_of_hour"] == min(5 + hold_mins, 55)]
            if len(entry_data) > 0 and len(exit_data) > 0:
                entry_ret = entry_data["ret"].iloc[0]
                exit_ret = exit_data["ret"].iloc[0]
                # Long if first 5 min was up
                direction = np.sign(row["f5_ret"]) if row["f5_ret"] != 0 else 0
                if direction != 0:
                    pnl = direction * (exit_ret - entry_ret)  # Return from min 5 to exit
                    tradeable.at[idx, f"pnl_{hold_mins}"] = pnl

        pnl = tradeable[f"pnl_{hold_mins}"].dropna()
        if len(pnl) > 10:
            print(f"  Hold {hold_mins} min: mean={pnl.mean()*10000:+.3f} bp  n={len(pnl)}  acc={(pnl>0).mean()*100:.1f}%")


def test_session_momentum(bars: pd.DataFrame) -> None:
    """Test: Is there momentum around session opens?"""
    print("\n" + "=" * 70)
    print("SESSION MOMENTUM: London (08:00 UTC) and NY (13:00 UTC) opens")
    print("=" * 70)

    bars = bars.copy()
    bars["ret"] = np.log(bars["close"] / bars["open"])
    bars["hour"] = bars["timestamp"].dt.hour
    bars["minute"] = bars["timestamp"].dt.minute

    # London open: 08:00 UTC
    london = bars[(bars["hour"] == 8) & (bars["minute"] < 30)].copy()
    print(f"\nLondon open minutes: {len(london):,}")
    if len(london) > 100:
        print(f"  Mean |ret|: {london['ret'].abs().mean()*10000:.2f} bp")
        print(f"  Signed ret: {london['ret'].mean()*10000:+.2f} bp")

        # Does 08:00 direction predict 08:30-09:00?
        london_8 = bars[(bars["hour"] == 8) & (bars["minute"] < 5)].copy()
        london_830 = bars[(bars["hour"] == 8) & (bars["minute"] >= 30) & (bars["minute"] < 60)].copy()
        if len(london_8) > 10 and len(london_830) > 10:
            # Sum returns by hour
            g8 = london_8.groupby(london_8["timestamp"].dt.floor("1h"))["ret"].sum()
            g830 = london_830.groupby(london_830["timestamp"].dt.floor("1h"))["ret"].sum()
            merged = pd.merge(g8.rename("early"), g830.rename("late"), left_index=True, right_index=True)
            if len(merged) > 10:
                # Long early direction
                pnl = np.sign(merged["early"]) * merged["late"]
                print(f"  London: trade early direction, hold to 08:30: mean={pnl.mean()*10000:+.3f} bp  acc={(pnl>0).mean()*100:.1f}%")

    # NY open: 13:00 UTC
    ny = bars[(bars["hour"] == 13) & (bars["minute"] < 30)].copy()
    print(f"\nNY open minutes: {len(ny):,}")
    if len(ny) > 100:
        print(f"  Mean |ret|: {ny['ret'].abs().mean()*10000:.2f} bp")
        print(f"  Signed ret: {ny['ret'].mean()*10000:+.2f} bp")

        ny_1 = bars[(bars["hour"] == 13) & (bars["minute"] < 5)].copy()
        ny_130 = bars[(bars["hour"] == 13) & (bars["minute"] >= 30) & (bars["minute"] < 60)].copy()
        if len(ny_1) > 10 and len(ny_130) > 10:
            g1 = ny_1.groupby(ny_1["timestamp"].dt.floor("1h"))["ret"].sum()
            g130 = ny_130.groupby(ny_130["timestamp"].dt.floor("1h"))["ret"].sum()
            merged = pd.merge(g1.rename("early"), g130.rename("late"), left_index=True, right_index=True)
            if len(merged) > 10:
                pnl = np.sign(merged["early"]) * merged["late"]
                print(f"  NY: trade early direction, hold to 13:30: mean={pnl.mean()*10000:+.3f} bp  acc={(pnl>0).mean()*100:.1f}%")


def test_vol_regime_switching(bars: pd.DataFrame) -> None:
    """Test: If vol jumps, does direction persist?"""
    print("\n" + "=" * 70)
    print("VOL REGIME SWITCHING: Sudden vol jump with direction")
    print("=" * 70)

    bars = bars.copy()
    bars["ret"] = np.log(bars["close"] / bars["open"])
    bars["abs_ret"] = bars["ret"].abs()
    bars["range"] = (bars["high"] - bars["low"]) / bars["open"]

    # Causal vol estimate
    bars["vol_ma5"] = bars["abs_ret"].rolling(5, min_periods=3).mean().shift(1)
    bars["vol_ma20"] = bars["abs_ret"].rolling(20, min_periods=10).mean().shift(1)

    # Minute where vol is much higher than recent average
    bars["vol_jump"] = bars["abs_ret"] > (bars["vol_ma20"] * 2.0)
    bars["vol_jump"] = bars["vol_jump"] & (bars["vol_ma20"] > 0)  # avoid divide-by-zero

    # Create forward returns BEFORE filtering
    for h in [1, 3, 5, 10]:
        bars[f"fwd_{h}"] = np.log(bars["close"].shift(-h) / bars["close"])

    up_jump = bars[bars["vol_jump"] & (bars["ret"] > 0)].copy()
    dn_jump = bars[bars["vol_jump"] & (bars["ret"] < 0)].copy()

    print(f"\nVol jump minutes: {bars['vol_jump'].sum():,}")
    print(f"  Up jumps: {len(up_jump):,}")
    print(f"  Dn jumps: {len(dn_jump):,}")

    for h in [1, 3, 5, 10]:
        if len(up_jump) > 10 and len(dn_jump) > 10:
            pnl = pd.concat([up_jump[f"fwd_{h}"].dropna(), -dn_jump[f"fwd_{h}"].dropna()])
            print(f"  h={h:2d}: mean={pnl.mean()*10000:+.3f} bp  n={len(pnl)}  acc={(pnl>0).mean()*100:.1f}%")


def main() -> None:
    print("Loading EURUSD ticks for 2024...")
    start = pd.Timestamp("2024-01-01", tz="UTC")
    end = pd.Timestamp("2024-12-31", tz="UTC")
    ticks = load_ticks("EURUSD", start, end)
    print(f"Loaded {len(ticks):,} ticks")

    print("Building minute bars...")
    bars = build_minute_bars(ticks)
    print(f"Built {len(bars):,} minute bars")

    test_big_hour_momentum(bars)
    test_session_momentum(bars)
    test_vol_regime_switching(bars)

    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print("The question: Can we detect a big hour in first 5 minutes,")
    print("then ride minute-level momentum for 10-30 minutes?")
    print("If real-time detection works AND subsequent momentum persists,")
    print("we have a tradeable signal.")


if __name__ == "__main__":
    main()
