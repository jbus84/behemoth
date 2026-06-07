"""Full-history smooth variant metrics (2020-2025) — Sharpe, maxDD, total return."""
from __future__ import annotations

import numpy as np
import pandas as pd
from pathlib import Path

from scripts.research.crypto_flow_xs_broad import backtest, metrics

CACHE_PERP = "/tmp/crypto_broad_perp.parquet"


def run_full(perp: pd.DataFrame, w: int, h: int, k: int, fm: dict) -> dict | None:
    years = tuple(range(2020, 2026))
    r = backtest(perp, w, h, k, years, fm, signal="flow6")
    m = metrics(r["gross"], r["turn"], r["fund_pnl"], r["dates"], h, fm)
    if not m:
        return None
    spread = fm.get("spread_bps", 2.0) / 1e4
    rebate = fm.get("maker_rebate_bps", 2.0) / 1e4
    taker_fee = fm.get("taker_fee_bps", 5.0) / 1e4
    queue_pos = fm.get("queue_pos", 0.0)
    adv = fm.get("adv_bps", 0.0) / 1e4
    p_fill_base = fm.get("p_fill_base", 1.0)
    p_fill = max(0.05, p_fill_base * (1 - queue_pos))
    cost_per_turn = p_fill * (spread - rebate + adv) + (1 - p_fill) * (spread + taker_fee)
    net = r["gross"] - r["turn"] * cost_per_turn + r["fund_pnl"]
    s = pd.Series(net, index=pd.DatetimeIndex(r["dates"]).tz_localize(None))
    cum = (1 + s).cumprod()
    dd = (cum - cum.cummax()) / cum.cummax()
    return {
        "net": net,
        "dates": r["dates"],
        "metrics": m,
        "max_dd": float(dd.min()),
        "final_multiple": float(cum.iloc[-1]),
        "daily_vol": float(s.std()),
        "skew": float(s.skew()),
        "kurt": float(s.kurtosis()),
    }


def main() -> None:
    perp = pd.read_parquet(CACHE_PERP)
    perp = perp[(perp["dt"] >= "2020-01-01") & (perp["dt"] < "2025-06-01")]
    perp = perp.sort_values(["symbol", "dt"])
    bar_counts = perp.groupby("symbol").size()
    keep_syms = bar_counts[bar_counts >= 5000].index.tolist()
    perp = perp[perp["symbol"].isin(keep_syms)].copy()

    fm_retail = {
        "name": "retail_maker",
        "spread_bps": 2.0,
        "maker_rebate_bps": 2.0,
        "taker_fee_bps": 5.0,
        "queue_pos": 0.0,
        "adv_bps": 0.0,
        "p_fill_base": 1.0,
    }

    configs = [
        (24, 72, 3, "h72_k3"),
        (24, 48, 5, "h48_k5"),
        (24, 24, 5, "h24_k5"),
    ]

    print(f"{'config':12s} {'net':>7s} {'t':>6s} {'posM':>5s} {'Shrp':>6s} {'maxDD':>7s} {'final':>7s} {'vol':>7s}")
    rows = []
    for w, h, k, label in configs:
        r = run_full(perp, w, h, k, fm_retail)
        if r is None:
            continue
        m = r["metrics"]
        rows.append((label, m, r))
        print(f"{label:12s} {m['net']:+7.2f} {m['t']:+6.2f} {m['posM']:5.0%} {m['sharpe']:+6.2f} "
              f"{r['max_dd']*100:+7.1f}% {r['final_multiple']:7.2f}x {r['daily_vol']*100:7.3f}%")

    rows.sort(key=lambda x: x[1]["sharpe"], reverse=True)
    best = rows[0]
    print(f"\nBest by Sharpe: {best[0]}  Sharpe={best[1]['sharpe']:.2f}  maxDD={best[2]['max_dd']*100:.1f}%  final={best[2]['final_multiple']:.2f}x")

if __name__ == "__main__":
    main()
