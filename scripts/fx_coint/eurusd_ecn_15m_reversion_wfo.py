"""EURUSD ECN 15m London/Overlap mean-reversion WFO.

Tests whether the validated 15m mom_3 fade (IC ~ -0.054, strongest scalp directional signal)
survives causal expanding-window WFO at ECN cost (zero spread, 0.6 bps RT).

Design
------
* Symbol     : EURUSD only (ECN zero-spread access)
* Bars       : true 15m time bars from raw dukascopy ticks (close = last mid)
* Session    : London + Overlap (07:00–16:00 UTC), 36 bars/day
* Signal     : fade mom_3 = -sign(3-bar vol-normalised momentum)
* Hold       : next 15m bar (H=1) — immediate reversion
* Cost       : 0.6 bps RT (ECN commission, zero spread)
* Variants   : unconditional + |mom_3| magnitude bands (top 10%, top 20%, etc.)

Causality
---------
* mom_3 uses only past 3 bars (causal)
* vol normalisation uses past 48-bar rolling std (causal, shift(1))
* Magnitude bands: expanding-window quantile on training data only
* WFO: train on all prior years, test on current year

Usage
-----
    uv run python scripts/fx_coint/eurusd_ecn_15m_reversion_wfo.py

Output
------
  * Fold-by-fold unconditional + banded results
  * Non-overlapping t-stats (every Nth observation to avoid correlation inflation)
  * Pooled OOS summary with bootstrap CI
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import polars as pl

SRC = Path.home() / "Desktop" / "dukascopy_ticks"
SYMBOL = "EURUSD"
COST_BPS = 0.60  # ECN round-trip: $6 per $100K = 0.6 bps on EURUSD @ ~1.07
LIQUID_HOURS = range(7, 16)  # 07:00–15:59 UTC (London + Overlap)


def load_raw_ticks(symbol: str, year: int) -> pl.DataFrame:
    """Load raw dukascopy tick parquets for symbol+year."""
    sym = symbol.upper()
    sym_dir = SRC / sym
    files = sorted(sym_dir.glob(f"{sym}_{year}*_ticks.parquet"))
    if not files:
        raise FileNotFoundError(f"No tick parquet files for {sym} {year} in {sym_dir}")
    return pl.concat([pl.read_parquet(f) for f in files]).sort("timestamp")


def build_15m_bars(ticks: pl.DataFrame) -> pd.DataFrame:
    """True 15-minute time bars (close = last mid of interval)."""
    t = ticks.sort("timestamp").with_columns(
        pl.col("timestamp").dt.truncate("15m").alias("bucket")
    )
    bars = (
        t.group_by("bucket")
        .agg(
            pl.col("mid").last().alias("mid"),
            pl.col("bid").last().alias("close_bid"),
            pl.col("ask").last().alias("close_ask"),
        )
        .sort("bucket")
    )
    df = bars.to_pandas()
    df["bucket"] = pd.to_datetime(df["bucket"])
    df = df.sort_values("bucket").reset_index(drop=True)
    return df


def add_features(df: pd.DataFrame) -> pd.DataFrame:
    """Add causal 15m features: returns, rolling vol, mom_3."""
    df = df.copy()
    df["ret_bps"] = np.log(df["mid"] / df["mid"].shift(1)) * 1e4
    # Rolling realised vol (48-bar lookback, ~12 hours)
    df["rv"] = df["ret_bps"].rolling(48, min_periods=20).std()
    # 3-bar momentum (45 min), vol-normalised
    df["mom3"] = (df["ret_bps"].rolling(3, min_periods=2).sum() / (df["rv"] * np.sqrt(3)))
    # Forward return: next bar
    df["fwd_ret_bps"] = np.log(df["mid"].shift(-1) / df["mid"]) * 1e4
    df["hour"] = df["bucket"].dt.hour
    return df


def bootstrap_ci(x: np.ndarray, n_boot: int = 10_000, ci: float = 0.95) -> tuple[float, float]:
    """Percentile bootstrap CI on the mean."""
    if len(x) < 5:
        return (np.nan, np.nan)
    rng = np.random.default_rng(42)
    means = np.array([rng.choice(x, size=len(x), replace=True).mean() for _ in range(n_boot)])
    lo = (1 - ci) / 2
    return float(np.percentile(means, lo * 100)), float(np.percentile(means, (1 - lo) * 100))


def evaluate_band(df_test: pd.DataFrame, absmom_thresh: float | None) -> dict:
    """Evaluate fade-mom3 on test data with optional |mom3| threshold."""
    liq = df_test[df_test["hour"].isin(LIQUID_HOURS)].copy()
    liq = liq[np.isfinite(liq["mom3"]) & np.isfinite(liq["fwd_ret_bps"])]
    if len(liq) == 0:
        return {"n": 0, "net": np.nan, "gross": np.nan, "t": np.nan, "t_no": np.nan,
                "hit": np.nan, "boot_lo": np.nan, "boot_hi": np.nan}

    if absmom_thresh is not None:
        mask = liq["mom3"].abs() >= absmom_thresh
        liq = liq[mask]
    if len(liq) == 0:
        return {"n": 0, "net": np.nan, "gross": np.nan, "t": np.nan, "t_no": np.nan,
                "hit": np.nan, "boot_lo": np.nan, "boot_hi": np.nan}

    # Fade signal
    gross = -np.sign(liq["mom3"].values) * liq["fwd_ret_bps"].values
    net = gross - COST_BPS

    # Non-overlapping (every other bar since hold=1)
    net_no = net[::1]  # 15m bars are already effectively non-overlapping for H=1
    # Actually with H=1, consecutive bars overlap in the sense that returns are correlated.
    # Use every 2nd bar for conservative t-stat.
    net_no = net[::2]

    mean_net = float(np.mean(net))
    std_net = float(np.std(net, ddof=1))
    tstat = mean_net / (std_net / np.sqrt(len(net))) if std_net > 0 else np.nan
    tstat_no = float(np.mean(net_no) / (np.std(net_no, ddof=1) / np.sqrt(len(net_no)))) if len(net_no) > 3 and np.std(net_no) > 0 else np.nan
    boot_lo, boot_hi = bootstrap_ci(net)
    hit = float(np.mean(net > 0)) * 100.0

    return {
        "n": len(net),
        "n_no": len(net_no),
        "gross": float(np.mean(gross)),
        "net": mean_net,
        "t": tstat,
        "t_no": tstat_no,
        "hit": hit,
        "boot_lo": boot_lo,
        "boot_hi": boot_hi,
        "pos": int(np.sum(net > 0)),
        "neg": int(np.sum(net <= 0)),
    }


def run_wfo_fold(train_df: pd.DataFrame, test_df: pd.DataFrame, band_quantiles: list[float]) -> dict:
    """Run one WFO fold with unconditional + banded variants."""
    # Compute |mom3| thresholds from training liquid hours only
    train_liq = train_df[train_df["hour"].isin(LIQUID_HOURS)]
    train_liq = train_liq[np.isfinite(train_liq["mom3"])]
    absmom_vals = train_liq["mom3"].abs().dropna().values

    thresholds = {}
    for q in band_quantiles:
        thresholds[q] = float(np.percentile(absmom_vals, q * 100)) if len(absmom_vals) > 20 else np.nan

    results = {"unconditional": evaluate_band(test_df, None)}
    for q, thr in thresholds.items():
        if not np.isnan(thr):
            results[f"q{int(q*100)}"] = evaluate_band(test_df, thr)
    return results


def main():
    parser = argparse.ArgumentParser(description="EURUSD ECN 15m reversion WFO")
    parser.add_argument("--years", type=str, default="", help="Comma-separated years")
    parser.add_argument("--cost", type=float, default=COST_BPS)
    parser.add_argument("--bands", type=str, default="0.8,0.9,0.95")
    args = parser.parse_args()

    sym = SYMBOL.upper()
    sym_dir = SRC / sym
    files = sorted(sym_dir.glob(f"{sym}_*_ticks.parquet"))
    years_found = sorted({int(f.stem.split("_")[1][:4]) for f in files})
    years = [int(y.strip()) for y in args.years.split(",")] if args.years else years_found

    print(f"EURUSD ECN 15m Reversion WFO  |  Years: {years[0]}–{years[-1]}  |  Cost: {args.cost:.2f} bps RT")
    print(f"Session: London+Overlap ({LIQUID_HOURS.start}:00–{LIQUID_HOURS.stop}:00 UTC)")
    print("=" * 90)

    # Load + build 15m bars per year
    yearly_bars: dict[int, pd.DataFrame] = {}
    for year in years:
        try:
            ticks = load_raw_ticks(sym, year)
            bars = build_15m_bars(ticks)
            bars = add_features(bars)
            yearly_bars[year] = bars
            print(f"  {year}: {len(bars)} 15m bars")
        except FileNotFoundError as e:
            print(f"  {year}: SKIP ({e})")

    if len(yearly_bars) < 2:
        print("ERROR: insufficient data", file=sys.stderr)
        sys.exit(1)

    band_qs = [float(x) for x in args.bands.split(",")]
    fold_years = sorted(yearly_bars.keys())

    # Expanding-window WFO
    all_results: list[dict] = []
    pooled_nets: dict[str, list[float]] = {k: [] for k in ["unconditional"] + [f"q{int(q*100)}" for q in band_qs]}
    pooled_years: dict[str, list[int]] = {k: [] for k in pooled_nets}

    print(f"\n{'Fold':>4} {'Train':>9} {'Test':>4} {'Variant':>14} {'N':>5} {'Gross':>6} {'Net':>6} {'t':>6} {'t_no':>6} {'Hit%':>5} {'Boot95':>18}")
    print("-" * 110)

    for i in range(1, len(fold_years)):
        test_year = fold_years[i]
        train_years = fold_years[:i]
        train_df = pd.concat([yearly_bars[y] for y in train_years], ignore_index=True)
        test_df = yearly_bars[test_year]

        fold_res = run_wfo_fold(train_df, test_df, band_qs)
        all_results.append({"test_year": test_year, "train": f"{train_years[0]}-{train_years[-1]}", "variants": fold_res})

        for variant, res in fold_res.items():
            if res["n"] > 0:
                print(
                    f"{i:>4} {f'{train_years[0]}-{train_years[-1]}':>9} {test_year:>4} {variant:>14} "
                    f"{res['n']:>5} {res['gross']:>+6.2f} {res['net']:>+6.2f} "
                    f"{res['t']:>+6.2f} {res['t_no']:>+6.2f} {res['hit']:>5.1f}% "
                    f"[{res['boot_lo']:>+6.2f},{res['boot_hi']:>+6.2f}]"
                )
                # Reconstruct individual nets for pooling
                test_copy = test_df.copy()
                liq = test_copy[test_copy["hour"].isin(LIQUID_HOURS)]
                liq = liq[np.isfinite(liq["mom3"]) & np.isfinite(liq["fwd_ret_bps"])]
                if variant != "unconditional":
                    q = int(variant.replace("q", "")) / 100.0
                    train_liq = train_df[train_df["hour"].isin(LIQUID_HOURS)]
                    train_liq = train_liq[np.isfinite(train_liq["mom3"])]
                    thr = np.percentile(train_liq["mom3"].abs().dropna().values, q * 100)
                    liq = liq[liq["mom3"].abs() >= thr]
                if len(liq) > 0:
                    gross = -np.sign(liq["mom3"].values) * liq["fwd_ret_bps"].values
                    net = gross - args.cost
                    for n in net:
                        if not np.isnan(n):
                            pooled_nets[variant].append(n)
                            pooled_years[variant].append(test_year)

    # Pooled OOS summaries
    print("\n" + "=" * 90)
    print("POOLED OOS SUMMARIES")
    print("=" * 90)
    print(f"{'Variant':>14} {'N':>6} {'Net':>7} {'t':>6} {'t_no':>6} {'Hit%':>6} {'Boot95':>18} {'PosYrs':>8}")
    print("-" * 90)

    best_variant = None
    best_net = -1e9

    for variant in pooled_nets:
        nets = np.array(pooled_nets[variant])
        if len(nets) == 0:
            continue
        mean_net = float(np.mean(nets))
        std_net = float(np.std(nets, ddof=1))
        tstat = mean_net / (std_net / np.sqrt(len(nets))) if std_net > 0 else np.nan
        net_no = nets[::2]  # non-overlapping
        tstat_no = float(np.mean(net_no) / (np.std(net_no, ddof=1) / np.sqrt(len(net_no)))) if len(net_no) > 3 and np.std(net_no) > 0 else np.nan
        boot_lo, boot_hi = bootstrap_ci(nets)
        hit = float(np.mean(nets > 0)) * 100.0
        year_means = {}
        for y in set(pooled_years[variant]):
            yn = [n for n, yr in zip(nets, pooled_years[variant]) if yr == y]
            year_means[y] = np.mean(yn)
        pos_years = sum(1 for v in year_means.values() if v > 0)
        total_years = len(year_means)

        print(f"{variant:>14} {len(nets):>6} {mean_net:>+7.2f} {tstat:>+6.2f} {tstat_no:>+6.2f} {hit:>6.1f}% [{boot_lo:>+7.2f},{boot_hi:>+7.2f}] {pos_years}/{total_years}")

        if mean_net > best_net:
            best_net = mean_net
            best_variant = variant

    # Verdict
    print("\n" + "=" * 90)
    if best_variant:
        nets = np.array(pooled_nets[best_variant])
        boot_lo, boot_hi = bootstrap_ci(nets)
        net_no = nets[::2]
        tstat_no = float(np.mean(net_no) / (np.std(net_no, ddof=1) / np.sqrt(len(net_no)))) if len(net_no) > 3 and np.std(net_no) > 0 else np.nan

        # Count pos years
        year_means = {}
        for y in set(pooled_years[best_variant]):
            yn = [n for n, yr in zip(nets, pooled_years[best_variant]) if yr == y]
            year_means[y] = np.mean(yn)
        pos_years = sum(1 for v in year_means.values() if v > 0)
        total_years = len(year_means)

        clears_zero = boot_lo > 0
        strong = tstat_no is not None and tstat_no > 2.0 and pos_years >= max(1, total_years // 2)

        if clears_zero and strong:
            print(f"  BEST VARIANT: {best_variant}  |  VERDICT: 🟢 PASSES causal ECN WFO")
        elif clears_zero:
            print(f"  BEST VARIANT: {best_variant}  |  VERDICT: 🟡 MARGINAL (CI clears zero but t_no<2 or posYrs weak)")
        else:
            print(f"  BEST VARIANT: {best_variant}  |  VERDICT: 🔴 FAILS (boot95 includes zero)")
    else:
        print("  No trades generated across any fold.")
    print("=" * 90)


if __name__ == "__main__":
    main()
