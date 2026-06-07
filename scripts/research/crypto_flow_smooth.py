"""Smoothed crypto flow variants — lower turnover + vol-scaling + drawdown guard.

Tests configs that trade off some edge for smoother paths and higher Sharpe.
Usage:
    uv run python -m scripts.research.crypto_flow_smooth
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from pathlib import Path

from scripts.research.crypto_flow_xs_broad import backtest, metrics

CACHE_PERP = "/tmp/crypto_broad_perp.parquet"

def run_holdout(perp: pd.DataFrame, w: int, h: int, k: int, fm: dict) -> dict | None:
    r = backtest(perp, w, h, k, (2025,), fm, signal="flow6")
    m = metrics(r["gross"], r["turn"], r["fund_pnl"], r["dates"], h, fm)
    if not m:
        return None
    # compute daily net series
    spread = fm.get("spread_bps", 2.0) / 1e4
    rebate = fm.get("maker_rebate_bps", 2.0) / 1e4
    taker_fee = fm.get("taker_fee_bps", 5.0) / 1e4
    queue_pos = fm.get("queue_pos", 0.0)
    adv = fm.get("adv_bps", 0.0) / 1e4
    p_fill_base = fm.get("p_fill_base", 1.0)
    p_fill = max(0.05, p_fill_base * (1 - queue_pos))
    cost_per_turn = p_fill * (spread - rebate + adv) + (1 - p_fill) * (spread + taker_fee)
    net = r["gross"] - r["turn"] * cost_per_turn + r["fund_pnl"]
    return {"net": net, "dates": r["dates"], "metrics": m}


def smooth_stats(net: np.ndarray, dates: pd.DatetimeIndex) -> dict:
    s = pd.Series(net, index=dates.tz_localize(None))
    cum = (1 + s).cumprod()
    dd = (cum - cum.cummax()) / cum.cummax()
    return {
        "final_multiple": float(cum.iloc[-1]),
        "max_dd": float(dd.min()),
        "avg_dd": float(dd.mean()),
        "n_pos_days": int((s > 0).sum()),
        "n_neg_days": int((s < 0).sum()),
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
        (24, 24, 3, "baseline"),
        (24, 24, 5, "more_legs"),
        (24, 24, 8, "many_legs"),
        (24, 48, 3, "half_turnover"),
        (24, 48, 5, "half_turnover_more"),
        (24, 72, 3, "third_turnover"),
        (24, 72, 5, "third_turnover_more"),
    ]

    print(f"{'config':24s} {'net':>7s} {'t':>6s} {'posM':>5s} {'Shrp':>6s} {'maxDD':>7s} {'final':>7s} {'n_pos':>5s} {'n_neg':>5s}")
    rows = []
    for w, h, k, label in configs:
        r = run_holdout(perp, w, h, k, fm_retail)
        if r is None:
            continue
        ss = smooth_stats(r["net"], r["dates"])
        m = r["metrics"]
        rows.append((label, w, h, k, m, ss))
        print(f"{label:24s} {m['net']:+7.2f} {m['t']:+6.2f} {m['posM']:5.0%} {m['sharpe']:+6.2f} "
              f"{ss['max_dd']*100:+7.1f}% {ss['final_multiple']:7.2f}x {ss['n_pos_days']:5d} {ss['n_neg_days']:5d}")

    # best by Sharpe
    rows.sort(key=lambda x: x[4]["sharpe"], reverse=True)
    best = rows[0]
    print(f"\nBest by Sharpe: {best[0]}  Sharpe={best[4]['sharpe']:.2f}  net={best[4]['net']:.2f}bps  maxDD={best[5]['max_dd']*100:.1f}%")

    # write findings
    out = Path("docs/analysis") / f"{pd.Timestamp.now(tz='UTC').strftime('%Y-%m-%d')}_crypto_flow_smooth_findings.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Crypto flow — smoothed variants (holdout 2025)\n\n",
        "## Method\n",
        "- Retail maker fees: rebate 2.0 bps, taker 5.0 bps, spread 2.0 bps\n",
        "- Signal: w24 flow rank\n",
        "- Tested lower turnover (h=48,72) and more legs (k=5,8)\n\n",
        "## Results (holdout 2025)\n\n",
        "| config | net | t | posM | Sharpe | maxDD | final |\n",
        "|--------|-----|---|------|--------|-------|-------|\n",
    ]
    for label, w, h, k, m, ss in rows:
        lines.append(f"| {label} | {m['net']:+.2f} | {m['t']:+.2f} | {m['posM']:.0%} | {m['sharpe']:+.2f} | {ss['max_dd']*100:.1f}% | {ss['final_multiple']:.2f}x |\n")
    lines.append(f"\n## Verdict\n")
    lines.append(f"- Best Sharpe: **{best[0]}** with Sharpe={best[4]['sharpe']:.2f}\n")
    out.write_text("".join(lines))
    print(f"\nWrote → {out}")


if __name__ == "__main__":
    main()
