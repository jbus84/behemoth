"""Sector / concentration check: what symbols dominate the h48_k5 book?

Heuristic sector mapping + Herfindahl concentration index.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from pathlib import Path
from collections import Counter

from scripts.research.crypto_flow_xs_broad import backtest

CACHE_PERP = "/tmp/crypto_broad_perp.parquet"


def classify_sector(symbol: str) -> str:
    s = symbol.upper()
    if s in ("BTCUSDT", "ETHUSDT"):
        return "major"
    if any(x in s for x in ("DOGE", "SHIB", "PEPE", "WIF", "FLOKI", "BONK", "BOME", "MEME", "PEOPLE")):
        return "meme"
    if any(x in s for x in ("SOL", "ADA", "AVAX", "DOT", "NEAR", "ALGO", "ICP", "FTM", "SUI", "APT")):
        return "L1"
    if any(x in s for x in ("LINK", "UNI", "AAVE", "CRV", "SNX", "MKR", "COMP", "LDO", "RAY")):
        return "defi"
    if any(x in s for x in ("MATIC", "ARB", "OP", "IMX", "STRK")):
        return "L2"
    if any(x in s for x in ("XRP", "LTC", "BCH", "ETC")):
        return "legacy"
    if any(x in s for x in ("TRX", "TON", "FIL", "VET", "XTZ", "EOS", "ATOM", "INJ", "TIA")):
        return "alt"
    return "other"


def main() -> None:
    perp = pd.read_parquet(CACHE_PERP)
    perp = perp[(perp["dt"] >= "2020-01-01") & (perp["dt"] < "2025-06-01")]
    perp = perp.sort_values(["symbol", "dt"])
    bar_counts = perp.groupby("symbol").size()
    keep_syms = bar_counts[bar_counts >= 5000].index.tolist()
    perp = perp[perp["symbol"].isin(keep_syms)].copy()

    fm_retail = {
        "name": "retail_maker", "spread_bps": 2.0, "maker_rebate_bps": 2.0,
        "taker_fee_bps": 5.0, "queue_pos": 0.0, "adv_bps": 0.0, "p_fill_base": 1.0,
    }
    years = tuple(range(2020, 2026))

    # Run backtest with weight extraction
    r = backtest(perp, 24, 48, 5, years, fm_retail, signal="flow6")

    # Extract weights from backtest?  The current backtest() doesn't return weights.
    # We'll re-run the rank logic inline.
    flow = perp.assign(flow=perp.groupby("symbol", group_keys=False)["ofi"]
                     .transform(lambda x: x.rolling(24, min_periods=12).mean()))
    close = flow.pivot(index="dt", columns="symbol", values="close")
    floww = flow.pivot(index="dt", columns="symbol", values="flow")
    fwd = close.shift(-48) / close - 1

    idx = floww.index[floww.index.year.isin(years)][::48]
    symbols = floww.columns.tolist()
    flow_arr = floww.to_numpy(float)
    fwd_arr = fwd.to_numpy(float)
    ts_map = {t: i for i, t in enumerate(floww.index)}
    rebalance_rows = np.array([ts_map[t] for t in idx if t in ts_map], dtype=int)

    top_counts = Counter()
    bot_counts = Counter()
    sector_counts = Counter()
    hhi_list = []

    for r in rebalance_rows:
        s = flow_arr[r, :]
        f = fwd_arr[r, :]
        valid = np.isfinite(s) & np.isfinite(f)
        n_valid = int(valid.sum())
        k_eff = min(5, n_valid // 2)
        if k_eff < 1:
            continue
        s_valid = s[valid]
        order = np.argsort(s_valid)
        valid_idx = np.where(valid)[0]
        bot = valid_idx[order[:k_eff]]
        top = valid_idx[order[-k_eff:]]

        bot_syms = [symbols[i] for i in bot]
        top_syms = [symbols[i] for i in top]

        for sym in bot_syms + top_syms:
            sector_counts[classify_sector(sym)] += 1
        for sym in bot_syms:
            bot_counts[sym] += 1
        for sym in top_syms:
            top_counts[sym] += 1

        # HHI of this bucket (equal-weight within bucket, so HHI = sum((1/2k)^2 * n_sym_bucket_i))
        # Actually simpler: with equal weights, each symbol gets weight 1/(2k_eff), so HHI = 2k_eff * (1/(2k_eff))^2 = 1/(2k_eff)
        # Since k_eff is fixed at 5, HHI = 1/10 = 0.1 always for the book itself.
        # Instead, measure *sector* HHI: what fraction of the 2k legs are in each sector?
        book_sectors = [classify_sector(s) for s in bot_syms + top_syms]
        c = Counter(book_sectors)
        total = sum(c.values())
        hhi = sum((v / total) ** 2 for v in c.values())
        hhi_list.append(hhi)

    total_legs = sum(sector_counts.values())
    print("Sector distribution in h48_k5 book (all rebalances 2020-2025):")
    for sector, count in sector_counts.most_common():
        print(f"  {sector:8s}: {count:6d} legs ({count/total_legs:5.1%})")

    print(f"\nMean sector-HHI per rebalance: {np.mean(hhi_list):.3f}  (1.0 = single sector, 0.1 = perfectly dispersed)")
    print(f"Max sector-HHI: {np.max(hhi_list):.3f}  Min: {np.min(hhi_list):.3f}")

    print(f"\nMost frequent longs (top-5):")
    for sym, count in top_counts.most_common(10):
        print(f"  {sym:12s}: {count:5d} times")

    print(f"\nMost frequent shorts (bottom-5):")
    for sym, count in bot_counts.most_common(10):
        print(f"  {sym:12s}: {count:5d} times")

    # check if any single rebalance had >50% of legs in one sector
    extreme = sum(1 for h in hhi_list if h > 0.5)
    print(f"\nRebalances with sector-HHI > 0.5 (half the book in one sector): {extreme} / {len(hhi_list)} ({extreme/len(hhi_list):.1%})")

    # month-level concentration check
    hhi_series = pd.Series(hhi_list, index=pd.DatetimeIndex(idx[:len(hhi_list)]).tz_localize(None))
    monthly_max = hhi_series.resample("ME").max()
    print(f"\nMonths with max sector-HHI > 0.5: {(monthly_max > 0.5).sum()} / {len(monthly_max)}")

    out = Path("docs/analysis") / f"{pd.Timestamp.now(tz='UTC').strftime('%Y-%m-%d')}_crypto_flow_sector_check.md"
    lines = ["# Sector / concentration check — h48_k5 (2020-2025)\n\n"]
    lines.append("## Sector distribution (all rebalances)\n\n")
    lines.append("| sector | legs | share |\n")
    lines.append("|--------|------|-------|\n")
    for sector, count in sector_counts.most_common():
        lines.append(f"| {sector} | {count} | {count/total_legs:.1%} |\n")
    lines.append(f"\n## Concentration metrics\n\n")
    lines.append(f"- Mean sector-HHI per rebalance: **{np.mean(hhi_list):.3f}**\n")
    lines.append(f"- Max sector-HHI: {np.max(hhi_list):.3f}\n")
    lines.append(f"- Rebalances with HHI > 0.5: {extreme} / {len(hhi_list)} ({extreme/len(hhi_list):.1%})\n")
    lines.append(f"- Months with max HHI > 0.5: {(monthly_max > 0.5).sum()} / {len(monthly_max)}\n\n")
    lines.append("## Most frequent longs (top-5)\n\n")
    lines.append("| symbol | count |\n")
    lines.append("|--------|-------|\n")
    for sym, count in top_counts.most_common(15):
        lines.append(f"| {sym} | {count} |\n")
    lines.append("\n## Most frequent shorts (bottom-5)\n\n")
    lines.append("| symbol | count |\n")
    lines.append("|--------|-------|\n")
    for sym, count in bot_counts.most_common(15):
        lines.append(f"| {sym} | {count} |\n")
    out.write_text("".join(lines))
    print(f"\nWrote → {out}")


if __name__ == "__main__":
    main()
