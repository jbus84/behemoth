#!/usr/bin/env python3
"""Signal discovery: does early directional conviction predict persistence?

Hypothesis: After a period of quiet, if a minute shows strong directional
conviction (close near the extreme, high efficiency ratio, elevated range),
then the next 1–10 minutes are more likely to continue in that direction.

This tests the user's thesis: "moves that persist for a longer period after
some initial behaviour can be detected early and modelled."
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.canonical_tick_feed import (  # noqa: E402
    DEFAULT_CANONICAL_ROOT,
    month_tags_between,
    quote_sql_path,
)
import duckdb  # noqa: E402


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
    """Compute per-minute directional-conviction features."""
    b = bars.copy()
    b["ret"] = np.log(b["close"] / b["open"])
    b["range"] = (b["high"] - b["low"]) / b["open"]
    b["eff_ratio"] = np.where(
        b["range"] > 0,
        np.abs(b["close"] - b["open"]) / (b["high"] - b["low"]),
        0.0,
    )
    # Close position: 0 = closed at low, 1 = closed at high
    b["close_pos"] = np.where(
        b["range"] > 0,
        (b["close"] - b["low"]) / (b["high"] - b["low"]),
        0.5,
    )
    # Rolling context (look-back only)
    b["prior_range_5"] = b["range"].rolling(5, min_periods=3).mean().shift(1)
    b["prior_range_20"] = b["range"].rolling(20, min_periods=10).mean().shift(1)
    b["prior_eff_5"] = b["eff_ratio"].rolling(5, min_periods=3).mean().shift(1)
    b["prior_ret_std_5"] = b["ret"].rolling(5, min_periods=3).std(ddof=0).shift(1)
    b["prior_abs_ret_5"] = b["ret"].abs().rolling(5, min_periods=3).mean().shift(1)
    return b


def test_signal_persistence(b: pd.DataFrame) -> None:
    """Test whether directional-conviction minutes predict continuation."""
    print("\n" + "=" * 70)
    print("SIGNAL PERSISTENCE TEST")
    print("=" * 70)

    # Require enough data for context
    b = b.dropna().copy()

    # Define a "directional conviction" signal minute
    # Criteria: elevated range + high efficiency ratio + close near extreme
    b["is_signal"] = (
        (b["range"] > b["prior_range_20"] * 1.5)  # elevated vs recent
        & (b["eff_ratio"] > 0.7)                    # directional, not chop
        & ((b["close_pos"] > 0.85) | (b["close_pos"] < 0.15))  # near extreme
    )

    n_signal = b["is_signal"].sum()
    print(f"\nSignal minutes: {n_signal:,} / {len(b):,} ({n_signal / len(b) * 100:.2f}%)")

    # For each signal minute, compute forward returns
    for horizon in [1, 2, 3, 5, 10]:
        b[f"fwd_{horizon}"] = np.log(b["close"].shift(-horizon) / b["close"])

    # Separate UP signals (close near high) vs DOWN signals (close near low)
    up_sig = b[b["is_signal"] & (b["close_pos"] > 0.85)].copy()
    dn_sig = b[b["is_signal"] & (b["close_pos"] < 0.15)].copy()

    print(f"\nUP signals (close near high):   {len(up_sig):,}")
    print(f"DOWN signals (close near low):  {len(dn_sig):,}")

    # Baseline: random minute directional accuracy
    baseline_acc = {}
    for h in [1, 2, 3, 5, 10]:
        fwd = b[f"fwd_{h}"].dropna()
        baseline_acc[h] = (fwd > 0).mean()

    print("\n--- Baseline (all minutes): prob(next N min is up) ---")
    for h, acc in baseline_acc.items():
        print(f"  h={h:2d}: {acc * 100:.1f}%")

    # Signal accuracy: for UP signals, what % of time does fwd continue UP?
    print("\n--- UP signal: prob(next N min continues UP) ---")
    for h in [1, 2, 3, 5, 10]:
        if len(up_sig) > 10:
            fwd = up_sig[f"fwd_{h}"].dropna()
            acc = (fwd > 0).mean()
            mean_fwd = fwd.mean()
            print(f"  h={h:2d}: acc={acc * 100:5.1f}%  mean_fwd={mean_fwd * 10000:+.3f} bp  (n={len(fwd)})")

    print("\n--- DOWN signal: prob(next N min continues DOWN) ---")
    for h in [1, 2, 3, 5, 10]:
        if len(dn_sig) > 10:
            fwd = dn_sig[f"fwd_{h}"].dropna()
            acc = (fwd < 0).mean()
            mean_fwd = fwd.mean()
            print(f"  h={h:2d}: acc={acc * 100:5.1f}%  mean_fwd={mean_fwd * 10000:+.3f} bp  (n={len(fwd)})")

    # Combined directional edge (long UP signals, short DOWN signals)
    print("\n--- Combined strategy: long UP, short DOWN signals ---")
    for h in [1, 2, 3, 5, 10]:
        up_fwd = up_sig[f"fwd_{h}"].dropna()
        dn_fwd = dn_sig[f"fwd_{h}"].dropna()
        if len(up_fwd) > 5 and len(dn_fwd) > 5:
            # PnL: long up + short down
            pnl = pd.concat([up_fwd, -dn_fwd])
            mean_pnl = pnl.mean()
            std_pnl = pnl.std(ddof=0)
            sharpe = mean_pnl / std_pnl if std_pnl > 0 else 0
            print(f"  h={h:2d}: mean={mean_pnl * 10000:+.3f} bp  sharpe={sharpe:+.4f}  n={len(pnl)}")

    # Breakout vs continuation: does prior quiet help?
    print("\n--- Does prior quiet improve the signal? ---")
    quiet_thresh = b["prior_range_20"].quantile(0.50)
    b["was_quiet"] = b["prior_range_20"] < quiet_thresh

    for quiet in [True, False]:
        subset = b[b["is_signal"] & b["was_quiet"]] if quiet else b[b["is_signal"] & ~b["was_quiet"]]
        label = "Quiet before" if quiet else "Already volatile"
        up = subset[subset["close_pos"] > 0.85]
        dn = subset[subset["close_pos"] < 0.15]
        if len(up) > 5 and len(dn) > 5:
            pnl = pd.concat([up["fwd_3"].dropna(), -dn["fwd_3"].dropna()])
            print(f"  {label}: h=3 mean={pnl.mean() * 10000:+.3f} bp  (n_up={len(up)}, n_dn={len(dn)})")

    # Signal strength decile analysis
    print("\n--- Signal strength vs forward return (h=3) ---")
    b["sig_score"] = b["eff_ratio"] * (b["range"] / (b["prior_range_20"] + 1e-12))
    sig_minutes = b[b["is_signal"]].copy()
    sig_minutes["decile"] = pd.qcut(sig_minutes["sig_score"], 5, labels=False, duplicates="drop")
    for d in sorted(sig_minutes["decile"].dropna().unique()):
        sub = sig_minutes[sig_minutes["decile"] == d]
        up = sub[sub["close_pos"] > 0.85]
        dn = sub[sub["close_pos"] < 0.15]
        if len(up) > 2 and len(dn) > 2:
            pnl = pd.concat([up["fwd_3"].dropna(), -dn["fwd_3"].dropna()])
            print(f"  decile {int(d)}: mean={pnl.mean() * 10000:+.3f} bp  n={len(pnl)}")


def test_early_detection(b: pd.DataFrame) -> None:
    """Can we detect a move in the FIRST minute of the hour?"""
    print("\n" + "=" * 70)
    print("EARLY DETECTION: First minute of the hour")
    print("=" * 70)

    b["minute_of_hour"] = b["timestamp"].dt.minute
    first_min = b[b["minute_of_hour"] == 0].copy()
    print(f"\nFirst minutes analyzed: {len(first_min):,}")

    # Define first-minute signal: strong directional close
    first_min["is_strong"] = (
        (first_min["eff_ratio"] > 0.7)
        & ((first_min["close_pos"] > 0.85) | (first_min["close_pos"] < 0.15))
    )
    print(f"Strong first minutes: {first_min['is_strong'].sum():,}")

    for h in [1, 2, 3, 5, 10]:
        first_min[f"fwd_{h}"] = np.log(first_min["close"].shift(-h) / first_min["close"])

    up = first_min[first_min["is_strong"] & (first_min["close_pos"] > 0.85)]
    dn = first_min[first_min["is_strong"] & (first_min["close_pos"] < 0.15)]

    for h in [1, 2, 3, 5, 10]:
        if len(up) > 5 and len(dn) > 5:
            pnl = pd.concat([up[f"fwd_{h}"].dropna(), -dn[f"fwd_{h}"].dropna()])
            print(f"  h={h:2d}: mean={pnl.mean() * 10000:+.3f} bp  n={len(pnl)}")


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

    test_signal_persistence(bars)
    test_early_detection(bars)

    print("\n" + "=" * 70)
    print("INTERPRETATION")
    print("=" * 70)
    print("If 'UP signal' accuracy is > 55% and mean_fwd > 0.5 bp,")
    print("then we have a real directional edge worth modelling.")
    print("If combined mean PnL is positive, a TimeBridge-style")
    print("architecture could learn to rank these moments.")


if __name__ == "__main__":
    main()
