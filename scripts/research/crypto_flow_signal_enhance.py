"""Test composite signals: flow + funding, volume-weighted flow, different w."""
from __future__ import annotations

import numpy as np
import pandas as pd
from pathlib import Path

from scripts.research.crypto_flow_xs_broad import backtest

CACHE_PERP = "/tmp/crypto_broad_perp.parquet"


def run(perp: pd.DataFrame, w: int, h: int, k: int, years: tuple, fm: dict, signal: str, use_fund: bool = False) -> dict:
    r = backtest(perp, w, h, k, years, fm, signal=signal, use_funding_signal=use_fund)
    spread = fm.get("spread_bps", 2.0) / 1e4
    rebate = fm.get("maker_rebate_bps", 2.0) / 1e4
    taker_fee = fm.get("taker_fee_bps", 5.0) / 1e4
    queue_pos = fm.get("queue_pos", 0.0)
    adv = fm.get("adv_bps", 0.0) / 1e4
    p_fill_base = fm.get("p_fill_base", 1.0)
    p_fill = max(0.05, p_fill_base * (1 - queue_pos))
    cost_per_turn = p_fill * (spread - rebate + adv) + (1 - p_fill) * (spread + taker_fee)
    net = r["gross"] - r["turn"] * cost_per_turn + r["fund_pnl"]
    idx = pd.DatetimeIndex(r["dates"]).tz_localize(None)
    return pd.Series(net, index=idx)


def metrics(s: pd.Series) -> dict:
    cum = (1 + s).cumprod()
    dd = (cum - cum.cummax()) / cum.cummax()
    return {
        "sharpe": s.mean() / s.std() * np.sqrt(365) if s.std() > 0 else 0.0,
        "max_dd": dd.min(),
        "final": cum.iloc[-1],
        "vol_ann": s.std() * np.sqrt(365),
    }


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

    configs = [
        (24, 48, 5, "flow6", False, "baseline_h48_k5"),
        (12, 48, 5, "flow6", False, "w12_h48_k5"),
        (48, 48, 5, "flow6", False, "w48_h48_k5"),
        (72, 48, 5, "flow6", False, "w72_h48_k5"),
        (24, 48, 5, "flow6", True, "flow6+fund"),
        (12, 48, 5, "flow6", True, "w12+fund"),
    ]

    print(f"{'config':20s} {'Sharpe':>7s} {'maxDD':>7s} {'final':>8s} {'vol':>7s}")
    rows = []
    for w, h, k, sig, use_fund, label in configs:
        try:
            s = run(perp, w, h, k, years, fm_retail, sig, use_fund)
            m = metrics(s)
            rows.append((label, m))
            print(f"{label:20s} {m['sharpe']:+7.2f} {m['max_dd']*100:+7.1f}% {m['final']:8.2f}x {m['vol_ann']*100:7.1f}%")
        except Exception as e:
            print(f"{label:20s} ERROR: {e}")

    rows.sort(key=lambda x: x[1]["sharpe"], reverse=True)
    print(f"\nTop by Sharpe: {rows[0][0]}  Sharpe={rows[0][1]['sharpe']:.2f}  maxDD={rows[0][1]['max_dd']:.1%}")

    out = Path("docs/analysis") / f"{pd.Timestamp.now(tz='UTC').strftime('%Y-%m-%d')}_crypto_flow_signal_enhance.md"
    lines = ["# Signal enhancement screening (full history 2020-2025)\n\n"]
    lines.append("| config | Sharpe | maxDD | final | vol |\n")
    lines.append("|--------|--------|-------|-------|-----|\n")
    for label, m in rows:
        lines.append(f"| {label} | {m['sharpe']:+.2f} | {m['max_dd']:.1%} | {m['final']:.2f}x | {m['vol_ann']*100:.1f}% |\n")
    out.write_text("".join(lines))
    print(f"\nWrote → {out}")


if __name__ == "__main__":
    main()
