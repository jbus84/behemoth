"""EURUSD ECN 100-tick bar reversion WFO — lookbacks N=1..10.

Tests whether simple momentum fade on 100-tick bars survives causal expanding-window
WFO at ECN cost (zero spread, 0.6 bps RT). Each 100tick bar ≈ 1–3 minutes.

Design
------
* Symbol     : EURUSD only (ECN zero-spread access)
* Bars       : 100-tick bars from data/tick_bars/EURUSD_100tick.parquet
* Signal     : fade N-bar momentum = -sign(sum of past N bar returns)
* Hold       : next 100tick bar (H=1)
* Cost       : 0.6 bps RT (ECN commission, zero spread)
* Threshold  : expanding-window |mom_N| quantile on training data (top 10%, 20%)

Causality
---------
* mom_N uses only past N bars (causal)
* Magnitude bands: expanding-window quantile on training data only
* WFO: train on all prior years, test on current year

Usage
-----
    uv run python scripts/fx_coint/eurusd_ecn_100tick_reversion_wfo.py

Output
------
  * Per-N, per-variant fold-by-fold results
  * Pooled OOS summary with non-overlapping t-stat
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

DATA_DIR = Path("/Users/danielfisher/repositories/behemoth/data/tick_bars")
SYMBOL = "EURUSD"
COST_BPS = 0.60
BAR_SIZE = 100


def load_100tick_bars(sym: str) -> pd.DataFrame:
    path = DATA_DIR / f"{sym}_{BAR_SIZE}tick.parquet"
    df = pd.read_parquet(path)
    df["ts"] = pd.to_datetime(df["timestamp"], utc=True)
    df["mid"] = (df["close_bid"] + df["close_ask"]) / 2.0
    df = df.sort_values("ts").reset_index(drop=True)
    df["year"] = df["ts"].dt.year
    df["ret_bps"] = np.log(df["mid"] / df["mid"].shift(1)) * 1e4
    return df


def bootstrap_ci(x: np.ndarray, n_boot: int = 10_000, ci: float = 0.95) -> tuple[float, float]:
    if len(x) < 5:
        return (np.nan, np.nan)
    rng = np.random.default_rng(42)
    means = np.array([rng.choice(x, size=len(x), replace=True).mean() for _ in range(n_boot)])
    lo = (1 - ci) / 2
    return float(np.percentile(means, lo * 100)), float(np.percentile(means, (1 - lo) * 100))


def main():
    parser = argparse.ArgumentParser(description="EURUSD ECN 100tick reversion WFO")
    parser.add_argument("--cost", type=float, default=COST_BPS)
    parser.add_argument("--ns", type=str, default="1,2,3,4,5,6,7,8,9,10")
    parser.add_argument("--bands", type=str, default="unconditional,top20,top10")
    args = parser.parse_args()

    ns = [int(x.strip()) for x in args.ns.split(",")]
    bands = [x.strip() for x in args.bands.split(",")]

    print(f"EURUSD ECN 100tick Reversion WFO  |  Cost: {args.cost:.2f} bps RT")
    print(f"Lookbacks N = {ns}")
    print(f"Bands = {bands}")
    print("=" * 100)

    df = load_100tick_bars(SYMBOL)
    years = sorted(df["year"].unique())
    print(f"Years available: {years[0]}–{years[-1]}  |  Total bars: {len(df)}")

    # Precompute forward return once
    df["fwd_ret_bps"] = np.log(df["mid"].shift(-1) / df["mid"]) * 1e4

    # Precompute mom_n for all N
    for n in ns:
        df[f"mom_{n}"] = df["ret_bps"].rolling(n, min_periods=n).sum().shift(1)

    yearly_dfs = {y: df[df["year"] == y].copy().reset_index(drop=True) for y in years}

    # Expanding-window WFO
    for n in ns:
        mom_col = f"mom_{n}"
        print(f"\n{'='*100}")
        print(f"N = {n}")
        print(f"{'='*100}")
        print(f"{'Fold':>4} {'Train':>9} {'Test':>4} {'Band':>14} {'N':>7} {'Gross':>7} {'Net':>7} {'t':>7} {'t_no':>7} {'Hit%':>6} {'Boot95':>20}")
        print("-" * 120)

        pooled_nets = {b: [] for b in bands}
        pooled_years = {b: [] for b in bands}

        for i in range(1, len(years)):
            test_year = years[i]
            train_years = years[:i]
            train_df = pd.concat([yearly_dfs[y] for y in train_years], ignore_index=True)
            test_df = yearly_dfs[test_year]

            # Precompute thresholds from training data for each band
            train_valid = train_df[np.isfinite(train_df[mom_col])].copy()
            absmom_train = train_valid[mom_col].abs().values
            thresholds = {}
            for band in bands:
                if band == "unconditional":
                    thresholds[band] = None
                elif band == "top20":
                    thresholds[band] = np.percentile(absmom_train, 80) if len(absmom_train) > 100 else np.nan
                elif band == "top10":
                    thresholds[band] = np.percentile(absmom_train, 90) if len(absmom_train) > 100 else np.nan
                elif band == "top5":
                    thresholds[band] = np.percentile(absmom_train, 95) if len(absmom_train) > 100 else np.nan
                else:
                    thresholds[band] = np.percentile(absmom_train, float(band)) if len(absmom_train) > 100 else np.nan

            test_valid = test_df[np.isfinite(test_df[mom_col]) & np.isfinite(test_df["fwd_ret_bps"])].copy()
            if len(test_valid) == 0:
                continue

            for band in bands:
                thr = thresholds[band]
                if thr is not None and np.isnan(thr):
                    continue
                sel = test_valid.copy()
                if thr is not None:
                    sel = sel[sel[mom_col].abs() >= thr]
                if len(sel) == 0:
                    continue

                gross = -np.sign(sel[mom_col].values) * sel["fwd_ret_bps"].values
                net = gross - args.cost
                net_no = net[::2]

                mean_net = float(np.mean(net))
                std_net = float(np.std(net, ddof=1))
                tstat = mean_net / (std_net / np.sqrt(len(net))) if std_net > 0 else np.nan
                tstat_no = float(np.mean(net_no) / (np.std(net_no, ddof=1) / np.sqrt(len(net_no)))) if len(net_no) > 3 and np.std(net_no) > 0 else np.nan
                boot_lo, boot_hi = bootstrap_ci(net)
                hit = float(np.mean(net > 0)) * 100.0

                print(
                    f"{i:>4} {f'{train_years[0]}-{train_years[-1]}':>9} {test_year:>4} {band:>14} "
                    f"{len(net):>7} {np.mean(gross):>+7.2f} {mean_net:>+7.2f} "
                    f"{tstat:>+7.2f} {tstat_no:>+7.2f} {hit:>6.1f}% "
                    f"[{boot_lo:>+7.2f},{boot_hi:>+7.2f}]"
                )

                # Pool directly from computed net array
                for n_ in net:
                    if not np.isnan(n_):
                        pooled_nets[band].append(n_)
                        pooled_years[band].append(test_year)

        # Pooled summary for this N
        print(f"\n{' '*50}POOLED OOS (N={n})")
        print(f"{'Band':>14} {'N':>8} {'Net':>7} {'t':>7} {'t_no':>7} {'Hit%':>6} {'Boot95':>20} {'PosYrs':>8}")
        print("-" * 100)
        best_band = None
        best_net = -1e9
        for band in bands:
            nets = np.array(pooled_nets[band])
            if len(nets) == 0:
                continue
            mean_net = float(np.mean(nets))
            std_net = float(np.std(nets, ddof=1))
            tstat = mean_net / (std_net / np.sqrt(len(nets))) if std_net > 0 else np.nan
            net_no = nets[::2]
            tstat_no = float(np.mean(net_no) / (np.std(net_no, ddof=1) / np.sqrt(len(net_no)))) if len(net_no) > 3 and np.std(net_no) > 0 else np.nan
            boot_lo, boot_hi = bootstrap_ci(nets)
            hit = float(np.mean(nets > 0)) * 100.0
            year_means = {}
            for y in set(pooled_years[band]):
                yn = [n for n, yr in zip(nets, pooled_years[band]) if yr == y]
                year_means[y] = np.mean(yn)
            pos_years = sum(1 for v in year_means.values() if v > 0)
            total_years = len(year_means)
            print(f"{band:>14} {len(nets):>8} {mean_net:>+7.2f} {tstat:>+7.2f} {tstat_no:>+7.2f} {hit:>6.1f}% [{boot_lo:>+8.2f},{boot_hi:>+8.2f}] {pos_years}/{total_years}")
            if mean_net > best_net:
                best_net = mean_net
                best_band = band

        if best_band:
            nets = np.array(pooled_nets[best_band])
            boot_lo, boot_hi = bootstrap_ci(nets)
            net_no = nets[::2]
            tstat_no = float(np.mean(net_no) / (np.std(net_no, ddof=1) / np.sqrt(len(net_no)))) if len(net_no) > 3 and np.std(net_no) > 0 else np.nan
            year_means = {}
            for y in set(pooled_years[best_band]):
                yn = [n for n, yr in zip(nets, pooled_years[best_band]) if yr == y]
                year_means[y] = np.mean(yn)
            pos_years = sum(1 for v in year_means.values() if v > 0)
            total_years = len(year_means)
            clears_zero = boot_lo > 0
            strong = tstat_no is not None and tstat_no > 2.0 and pos_years >= max(1, total_years // 2)
            if clears_zero and strong:
                verdict = "🟢 PASSES"
            elif clears_zero:
                verdict = "🟡 MARGINAL"
            else:
                verdict = "🔴 FAILS"
            print(f"\n  Best: {best_band}  |  Verdict: {verdict}  (net={best_net:+.2f}, boot95=[{boot_lo:+.2f},{boot_hi:+.2f}], t_no={tstat_no:+.2f}, posYrs={pos_years}/{total_years})")


if __name__ == "__main__":
    main()
