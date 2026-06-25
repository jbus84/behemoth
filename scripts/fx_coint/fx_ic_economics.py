"""Translate IC into economic terms: implied Sharpe, optimal sizing, and break-even cost.

Uses the Fundamental Law of Active Management to back out what IC=0.036 implies.

Usage:
    uv run python scripts/fx_coint/fx_ic_economics.py
"""
from __future__ import annotations

import numpy as np


def grinold_metrics(ic: float, n_bets_per_year: float, vol_target: float = 0.10,
                    cost_per_bet_bps: float = 0.6, tc: float = 1.0) -> dict:
    """
    ic              : Spearman correlation (forecast vs actual)
    n_bets_per_year: number of independent bets per year
    vol_target      : annual volatility target (e.g. 0.10 = 10%)
    cost_per_bet_bps: one-way cost in bps per bet (we assume round-trip ≈ 2×)
    tc              : transfer coefficient (implementation efficiency, 1.0 = perfect)
    """
    ir = ic * np.sqrt(n_bets_per_year) * tc  # Information Ratio
    ann_ret = ir * vol_target  # Annual return at target vol

    # Optimal aggressiveness: target vol / (IC × realized_vol_per_bet)
    # Assuming daily vol ≈ 10% / √250 ≈ 63 bps per day for FX
    daily_vol_bps = vol_target / np.sqrt(250) * 1e4  # ≈ 63 bps
    # Position size multiplier to hit vol target
    # Var(portfolio) = Σ w_i² σ_i² + cross terms; with 1 asset it's just sizing
    vol_target / (ic * daily_vol_bps / 1e4)  # not quite right, use approximation

    # Simpler: Kelly-style edge
    # Edge per bet ≈ IC × σ_return
    edge_per_bet = ic * daily_vol_bps  # bps per bet at unit exposure
    # But this scales with position size

    # Breakeven: edge per bet must exceed cost
    # Edge at optimal sizing
    breakeven_ic = cost_per_bet_bps * 2 / daily_vol_bps  # rough: cost / (IC * vol) = 1

    return {
        "ic": ic,
        "ir": ir,
        "ann_ret_pct": ann_ret * 100,
        "edge_per_bet_bps": edge_per_bet,
        "breakeven_ic": breakeven_ic,
        "profitable": edge_per_bet > cost_per_bet_bps * 2,
    }


def main():
    print("=" * 60)
    print("IC Economics: What do these correlations actually mean?")
    print("=" * 60)

    # Observed best ICs from the 15m regime regression runs
    results = [
        ("EURUSD", "global", 0.006),
        ("EURUSD", "hour_evening", 0.060),
        ("GBPUSD", "global", 0.036),
        ("AUDUSD", "global", 0.016),
        ("AUDUSD", "hour_evening", 0.056),
        ("USDJPY", "global", 0.018),
        ("USDJPY", "hour_evening", 0.046),
        ("USDCAD", "rvol_high", 0.050),
    ]

    print(f"\n{'Pair':<10} {'Regime':<16} {'IC':>6} {'IR*':>6} {'AnnRet%':>8} {'Edge/bet':>9} {'BE_IC':>6} {'Viable?'}")
    print("-" * 75)
    for pair, regime, ic in results:
        # 15m bars, trade top 10% ≈ 10% of bars ≈ 0.1 bets per bar
        # But we hold 3h = 12 bars, so non-overlapping ≈ 1/12 of bars
        # Bars per year at 15m: 4 bars/hour × 24 × 250 ≈ 24,000 (minus weekends)
        # Actual: ~20,000 15m bars/year per pair
        # Independent bets (non-overlap 3h): ~20,000 / 12 ≈ 1,667
        n_bets = 1667
        m = grinold_metrics(ic, n_bets, vol_target=0.10, cost_per_bet_bps=0.5)
        viable = "YES" if m["profitable"] else "NO"
        print(f"{pair:<10} {regime:<16} {m['ic']:>6.3f} {m['ir']:>6.2f} {m['ann_ret_pct']:>8.2f} {m['edge_per_bet_bps']:>9.2f} {m['breakeven_ic']:>6.3f} {viable}")

    print("\n* IR assumes Transfer Coefficient = 1.0 (perfect implementation)")
    print("  In reality TC ≈ 0.3-0.6 for retail, so divide IR by 2-3.")
    print("\nBreakeven IC: minimum correlation needed to cover 1 bps round-trip cost")
    print("  at 63 bps/day vol. IC_BE = cost / vol ≈ 1.0 / 63 ≈ 0.016")

    # Now compute the ACTUAL signal-to-noise from our backtests
    print("\n" + "=" * 60)
    print("ACTUAL BACKTEST ECONOMICS (from 15m regime regression)")
    print("=" * 60)

    # Table: pair, strategy, gross_mean, net_mean, n_trades_test, implied_yearly_net
    backtests = [
        ("EURUSD", "chase_global", -0.09, -0.53, 1235),
        ("EURUSD", "chase_evening", +0.54, +0.13, 1219),
        ("GBPUSD", "chase_global", +0.33, -0.49, 1313),
        ("AUDUSD", "chase_evening", +1.77, -0.15, 1238),
        ("USDJPY", "chase_evening", +0.87, +0.20, 1036),
        ("USDCAD", "chase_rvol_high", +0.60, -0.58, 1403),
    ]

    print(f"\n{'Pair':<10} {'Strategy':<16} {'Gross':>7} {'Net':>7} {'N':>6} {'$/yr@$1M':>10} {'Sharpe':>7}")
    print("-" * 65)
    for pair, strat, gross, net, n in backtests:
        # Assume test set = 30% of data = ~1/3 year
        trades_per_year = n * 3
        yearly_net_bps = net * trades_per_year
        yearly_ret_pct = yearly_net_bps / 100  # 1 bp = 0.01%
        # Sharpe approx: ret / vol; vol ≈ daily vol × √250, but we're levered to target
        # Rough: if each trade has vol ≈ 50 bps, portfolio vol ≈ 50 × √trades/year / 100
        vol_pct = 0.10  # assume 10% vol target
        sharpe = yearly_ret_pct / vol_pct if vol_pct > 0 else 0
        print(f"{pair:<10} {strat:<16} {gross:>+7.2f} {net:>+7.2f} {n:>6} {yearly_net_bps:>+10.0f} {sharpe:>+7.2f}")

    print("\nNote: $/yr assumes $1M capital, 1× leverage, 10% vol target.")
    print("      Negative Sharpe = below risk-free rate at target volatility.")


if __name__ == "__main__":
    main()
