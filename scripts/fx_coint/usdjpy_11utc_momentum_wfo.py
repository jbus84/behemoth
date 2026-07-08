"""Causal expanding-window WFO for USDJPY 11:00 UTC momentum on extreme moves.

Design
------
* Symbol : USDJPY only (the session-structure needle is pair-specific).
* Session: 11:00 UTC bar (covers 11:00–12:00 UTC).
* Signal : top-5 % |1 h return| at that hour, momentum (chase the move).
* Hold   : next bar (12:00–13:00 UTC).
* Cost   : Pepperstone Razor round-trip (0.72 bps for USDJPY).

WFO folds are calendar-year expanding windows:
  – Fold Y uses all prior years to compute the |return| quantile threshold.
  – Only past 11:00-UTC bars inform the threshold (no cross-hour leakage).
  – Report fold-by-fold plus pooled post-WFO summary.

Usage
-----
    uv run python scripts/fx_coint/usdjpy_11utc_momentum_wfo.py

Output
------
  * Fold-by-fold table (threshold, trades, net, t, boot95, posYrs, hit%).
  * Pooled summary across all out-of-sample folds.
  * Yearly breakdown to check for decay.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd
import polars as pl

_REPO_ROOT = Path(__file__).resolve().parents[2]
SRC = Path.home() / "Desktop" / "dukascopy_ticks"

# Pepperstone Razor round-trip cost (bps) — from phase0_scalp_common.py
COST_BPS: dict[str, float] = {
    "EURUSD": 0.64,
    "GBPUSD": 0.80,
    "AUDUSD": 0.88,
    "USDJPY": 0.72,
    "USDCHF": 0.88,
    "USDCAD": 0.88,
}

SYMBOL = "USDJPY"
SESSION_HOUR = 11          # 11:00 UTC bar (covers 11:00–12:00)
HOLD_HOURS = 1
QUANTILE = 0.95            # top-5 % |return|
COST = COST_BPS[SYMBOL]    # bps round-trip


def _pip_size(symbol: str) -> float:
    return 0.01 if str(symbol).upper().endswith("JPY") else 0.0001


def load_raw_ticks(symbol: str, year: int) -> pl.DataFrame:
    """Load raw dukascopy tick parquets for symbol+year."""
    sym = symbol.upper()
    src = SRC / sym
    if not src.exists():
        raise FileNotFoundError(f"Raw tick directory not found: {src}")
    files = sorted(src.glob(f"{sym}_{year}*_ticks.parquet"))
    if not files:
        raise FileNotFoundError(f"No tick parquet files for {sym} {year} in {src}")
    return pl.concat([pl.read_parquet(f) for f in files]).sort("timestamp")


def build_hourly_bars(ticks: pl.DataFrame) -> pd.DataFrame:
    """True hourly time bars (OHLC on bid/ask, close mid, spread)."""
    t = ticks.sort("timestamp").with_columns(
        pl.col("timestamp").dt.truncate("1h").alias("bar_time")
    )
    bars = (
        t.group_by("bar_time")
        .agg(
            pl.col("bid").first().alias("open_bid"),
            pl.col("ask").first().alias("open_ask"),
            pl.col("bid").max().alias("high_bid"),
            pl.col("ask").min().alias("low_ask"),
            pl.col("bid").last().alias("close_bid"),
            pl.col("ask").last().alias("close_ask"),
            pl.col("mid").last().alias("close_mid"),
        )
        .sort("bar_time")
        .with_columns(
            ((pl.col("close_bid") + pl.col("close_ask")) / 2.0).alias("mid"),
            ((pl.col("close_ask") - pl.col("close_bid")) / ((pl.col("close_bid") + pl.col("close_ask")) / 2.0)).alias("rel_spread"),
        )
    )
    df = bars.to_pandas()
    df["bar_time"] = pd.to_datetime(df["bar_time"])
    df = df.sort_values("bar_time").reset_index(drop=True)
    return df


def bootstrap_ci(x: np.ndarray, n_boot: int = 10_000, ci: float = 0.95) -> tuple[float, float]:
    """Percentile bootstrap CI on the mean."""
    if len(x) == 0:
        return (np.nan, np.nan)
    rng = np.random.default_rng(42)
    means = np.array([rng.choice(x, size=len(x), replace=True).mean() for _ in range(n_boot)])
    lo = (1 - ci) / 2
    return float(np.percentile(means, lo * 100)), float(np.percentile(means, (1 - lo) * 100))


def run_fold(train_df: pd.DataFrame, test_df: pd.DataFrame, quantile: float) -> dict:
    """Run one WFO fold.  train_df contains past years; test_df is the current year."""
    # Compute returns on FULL training series, then filter to 11:00 UTC for threshold
    train_df = train_df.sort_values("bar_time").reset_index(drop=True)
    train_df["ret_bps"] = np.log(train_df["mid"] / train_df["mid"].shift(1)) * 1e4
    train_session = train_df[train_df["bar_time"].dt.hour == SESSION_HOUR].copy()
    if len(train_session) < 20:
        return {"trades": 0, "net": np.nan, "t": np.nan, "boot_lo": np.nan, "boot_hi": np.nan,
                "hit": np.nan, "threshold_bps": np.nan, "pos": 0, "neg": 0}

    train_session = train_session.dropna(subset=["ret_bps"])
    threshold = np.percentile(train_session["ret_bps"].abs().values, quantile * 100)

    # Compute returns on FULL test series, then filter to 11:00 UTC
    test_df = test_df.sort_values("bar_time").reset_index(drop=True)
    test_df["ret_bps"] = np.log(test_df["mid"] / test_df["mid"].shift(1)) * 1e4
    test_df["next_ret_bps"] = np.log(test_df["mid"].shift(-1) / test_df["mid"]) * 1e4
    test_session = test_df[test_df["bar_time"].dt.hour == SESSION_HOUR].copy()

    # Signal: |ret| >= threshold
    mask = test_session["ret_bps"].abs() >= threshold
    trades = test_session[mask].copy()

    if len(trades) == 0:
        return {"trades": 0, "net": np.nan, "t": np.nan, "boot_lo": np.nan, "boot_hi": np.nan,
                "hit": np.nan, "threshold_bps": threshold, "pos": 0, "neg": 0}

    # Momentum: sign of current bar return
    direction = np.sign(trades["ret_bps"].values)
    gross = direction * trades["next_ret_bps"].values
    net = gross - COST

    mean_net = float(np.nanmean(net))
    std_net = float(np.nanstd(net, ddof=1))
    tstat = mean_net / (std_net / np.sqrt(len(net))) if std_net > 0 else np.nan
    boot_lo, boot_hi = bootstrap_ci(net)
    hit = float(np.mean(net > 0)) * 100.0
    pos = int(np.sum(net > 0))
    neg = int(np.sum(net <= 0))

    return {
        "trades": len(net),
        "net": mean_net,
        "t": tstat,
        "boot_lo": boot_lo,
        "boot_hi": boot_hi,
        "hit": hit,
        "threshold_bps": threshold,
        "pos": pos,
        "neg": neg,
    }


def main():
    parser = argparse.ArgumentParser(description="USDJPY 11:00 UTC momentum WFO")
    parser.add_argument("--tick-root", type=str, default=str(SRC), help="Path to dukascopy_ticks dir")
    parser.add_argument("--years", type=str, default="", help="Comma-separated years (default: all available)")
    parser.add_argument("--quantile", type=float, default=QUANTILE)
    parser.add_argument("--cost", type=float, default=COST)
    parser.add_argument("--output-json", type=str, default="")
    args = parser.parse_args()

    tick_root = Path(args.tick_root)
    symbol = SYMBOL.upper()
    sym_dir = tick_root / symbol
    if not sym_dir.exists():
        print(f"ERROR: tick directory not found: {sym_dir}", file=sys.stderr)
        sys.exit(1)

    # Discover available years
    files = sorted(sym_dir.glob(f"{symbol}_*_ticks.parquet"))
    years_found = sorted({int(f.stem.split("_")[1][:4]) for f in files})
    if args.years:
        years = [int(y.strip()) for y in args.years.split(",")]
    else:
        years = years_found

    if len(years) < 2:
        print(f"ERROR: need >=2 years, found {years}", file=sys.stderr)
        sys.exit(1)

    print(f"USDJPY 11:00 UTC Momentum WFO")
    print(f"Years: {years[0]}–{years[-1]}  |  Quantile: {args.quantile:.0%}  |  Cost: {args.cost:.2f} bps RT")
    print("=" * 80)

    # Load + build hourly bars per year
    yearly_bars: dict[int, pd.DataFrame] = {}
    for year in years:
        try:
            ticks = load_raw_ticks(symbol, year)
            bars = build_hourly_bars(ticks)
            yearly_bars[year] = bars
            print(f"  {year}: {len(bars)} hourly bars")
        except FileNotFoundError as e:
            print(f"  {year}: SKIP ({e})")

    if len(yearly_bars) < 2:
        print("ERROR: insufficient data", file=sys.stderr)
        sys.exit(1)

    # Expanding-window WFO: first year is train-only, each subsequent year is a test fold
    folds = []
    all_nets: list[float] = []
    all_years: list[int] = []
    fold_years = sorted(yearly_bars.keys())

    for i in range(1, len(fold_years)):
        test_year = fold_years[i]
        train_years = fold_years[:i]
        train_df = pd.concat([yearly_bars[y] for y in train_years], ignore_index=True)
        test_df = yearly_bars[test_year]

        result = run_fold(train_df, test_df, args.quantile)
        result["train_years"] = f"{train_years[0]}-{train_years[-1]}"
        result["test_year"] = test_year
        folds.append(result)

        if result["trades"] > 0:
            # Reconstruct net returns for pooling (compute on full series first)
            test_df = test_df.sort_values("bar_time").reset_index(drop=True)
            test_df["ret_bps"] = np.log(test_df["mid"] / test_df["mid"].shift(1)) * 1e4
            test_df["next_ret_bps"] = np.log(test_df["mid"].shift(-1) / test_df["mid"]) * 1e4
            test_session = test_df[test_df["bar_time"].dt.hour == SESSION_HOUR].copy()
            threshold = result["threshold_bps"]
            mask = test_session["ret_bps"].abs() >= threshold
            trades = test_session[mask]
            direction = np.sign(trades["ret_bps"].values)
            gross = direction * trades["next_ret_bps"].values
            net = gross - args.cost
            for n in net:
                if not np.isnan(n):
                    all_nets.append(n)
                    all_years.append(test_year)

    # Fold-by-fold table
    print(f"\n{'Fold':>4} {'Train':>9} {'Test':>4} {'Thr':>6} {'N':>4} {'Net':>7} {'t':>6} {'Boot95':>18} {'Hit%':>5} {'Pos/Neg':>8}")
    print("-" * 95)
    yearly_nets = defaultdict(list)
    for f in folds:
        print(
            f"{fold_years.index(f['test_year']):>4} "
            f"{f['train_years']:>9} "
            f"{f['test_year']:>4} "
            f"{f['threshold_bps']:>6.2f} "
            f"{f['trades']:>4} "
            f"{f['net']:>7.2f} "
            f"{f['t']:>6.2f} "
            f"[{f['boot_lo']:>6.2f}, {f['boot_hi']:>6.2f}] "
            f"{f['hit']:>5.1f} "
            f"{f['pos']}/{f['neg']}"
        )
        if f["trades"] > 0:
            yearly_nets[f["test_year"]].extend(
                [n for n in ([f["net"]] * f["trades"])]  # approximation for yearly summary
            )

    # Pooled summary
    if len(all_nets) > 0:
        nets = np.array(all_nets)
        mean_net = float(np.mean(nets))
        std_net = float(np.std(nets, ddof=1))
        tstat = mean_net / (std_net / np.sqrt(len(nets))) if std_net > 0 else np.nan
        boot_lo, boot_hi = bootstrap_ci(nets)
        hit = float(np.mean(nets > 0)) * 100.0

        # pos years (calendar years with positive mean net)
        year_means = {}
        for y in set(all_years):
            yn = [n for n, yr in zip(all_nets, all_years) if yr == y]
            year_means[y] = np.mean(yn)
        pos_years = sum(1 for v in year_means.values() if v > 0)
        total_years = len(year_means)

        print("=" * 95)
        print(f"\nPOOLED OOS SUMMARY  ({len(nets)} trades across {total_years} years)")
        print(f"  Net/trade : {mean_net:+.2f} bps")
        print(f"  t-stat    : {tstat:+.2f}")
        print(f"  boot95    : [{boot_lo:+.2f}, {boot_hi:+.2f}]")
        print(f"  Hit%      : {hit:.1f}%")
        print(f"  posYrs    : {pos_years}/{total_years}")

        # Yearly breakdown
        print(f"\nYearly means:")
        for y in sorted(year_means.keys()):
            print(f"  {y}: {year_means[y]:+.2f} bps")

        out = {
            "symbol": SYMBOL,
            "session_hour": SESSION_HOUR,
            "quantile": args.quantile,
            "cost_bps": args.cost,
            "pooled": {
                "n": len(nets),
                "net": round(mean_net, 4),
                "t": round(tstat, 4),
                "boot_lo": round(boot_lo, 4),
                "boot_hi": round(boot_hi, 4),
                "hit_pct": round(hit, 2),
                "pos_years": f"{pos_years}/{total_years}",
            },
            "yearly_means": {str(y): round(v, 4) for y, v in year_means.items()},
            "folds": folds,
        }

        if args.output_json:
            Path(args.output_json).write_text(json.dumps(out, indent=2))
            print(f"\nJSON written to {args.output_json}")

        # Verdict
        clears_zero = boot_lo > 0
        strong = tstat > 2.0 and pos_years >= max(1, total_years // 2)
        if clears_zero and strong:
            print(f"\n{'='*40}")
            print("  VERDICT: 🟢 PASSES causal WFO")
            print(f"{'='*40}")
        elif clears_zero:
            print(f"\n{'='*40}")
            print("  VERDICT: 🟡 MARGINAL (CI clears zero but t<2 or posYrs weak)")
            print(f"{'='*40}")
        else:
            print(f"\n{'='*40}")
            print("  VERDICT: 🔴 FAILS (boot95 touches zero)")
            print(f"{'='*40}")
    else:
        print("\nNo trades generated across any fold.")


if __name__ == "__main__":
    main()
