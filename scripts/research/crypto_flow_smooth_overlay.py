"""Risk overlays on h48_k5 — vol-scaling + drawdown guard."""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from scripts.research.crypto_flow_overlays import (
    RETAIL_MAKER,
    cost_per_turn,
    drawdown_guard,
    metrics,
)
from scripts.research.crypto_flow_overlays import (
    vol_target as _vol_target,
)
from scripts.research.crypto_flow_xs_broad import backtest

CACHE_PERP = "/tmp/crypto_broad_perp.parquet"
H = 48

def run_raw(perp, w, h, k, years, fm, signal):
    r = backtest(perp, w, h, k, years, fm, signal=signal)
    net = r["gross"] - r["turn"] * cost_per_turn(fm) + r["fund_pnl"]
    return pd.Series(net, index=pd.DatetimeIndex(r["dates"]).tz_localize(None)), r["dates"]


def apply_overlays(s: pd.Series, btc: pd.Series) -> dict:
    # All overlays are causal (decisions use only prior-period info) and Sharpe is
    # annualised for the H-hour rebalance period via crypto_flow_overlays.metrics.
    baseline = metrics(s, H)

    # vol-target on an external (BTC) vol proxy — past-only rolling vol, causal
    btc_ret = btc.pct_change().dropna()
    s_vol = _vol_target(s, btc_ret, H)
    vol_target = metrics(s_vol, H)

    # causal drawdown guard
    s_guard = drawdown_guard(s, soft=-0.15, hard=-0.25, soft_scale=0.5)
    guard = metrics(s_guard, H)

    # combined: re-derive vol scale and guard scale, both causal
    vol_scale = (s_vol / s).replace([float("inf"), float("-inf")], 1.0).fillna(1.0)
    guard_scale = (s_guard / s).replace([float("inf"), float("-inf")], 1.0).fillna(1.0)
    s_comb = s * vol_scale * guard_scale
    comb = metrics(s_comb, H)

    return {"baseline": baseline, "vol_target": vol_target, "drawdown_guard": guard, "combined": comb}


def main() -> None:
    perp = pd.read_parquet(CACHE_PERP)
    perp = perp[(perp["dt"] >= "2020-01-01") & (perp["dt"] < "2025-06-01")]
    perp = perp.sort_values(["symbol", "dt"])
    bar_counts = perp.groupby("symbol").size()
    keep_syms = bar_counts[bar_counts >= 5000].index.tolist()
    perp = perp[perp["symbol"].isin(keep_syms)].copy()

    fm_retail = dict(RETAIL_MAKER)

    years = tuple(range(2020, 2026))
    s, _ = run_raw(perp, 24, 48, 5, years, fm_retail, "flow6")

    # BTC close for vol proxy
    btc = perp[perp["symbol"] == "BTCUSDT"].set_index("dt")["close"]
    if btc.index.tz:
        btc = btc.tz_localize(None)

    results = apply_overlays(s, btc)
    print(f"{'overlay':18s} {'Sharpe':>7s} {'maxDD':>7s} {'final':>7s} {'vol':>7s}")
    for name, m in results.items():
        print(f"{name:18s} {m['sharpe']:+7.2f} {m['max_dd']*100:+7.1f}% {m['final']:7.2f}x {m['vol_ann']*100:7.2f}%")

    # write
    out = Path("docs/analysis") / f"{pd.Timestamp.now(tz='UTC').strftime('%Y-%m-%d')}_crypto_flow_overlay_findings.md"
    lines = ["# Risk overlays on h48_k5 (full history 2020-2025)\n\n"]
    lines.append("| overlay | Sharpe | maxDD | final | vol |\n")
    lines.append("|---------|--------|-------|-------|-----|\n")
    for name, m in results.items():
        lines.append(f"| {name} | {m['sharpe']:+.2f} | {m['max_dd']*100:.1f}% | {m['final']:.2f}x | {m['vol_ann']*100:.2f}% |\n")
    out.write_text("".join(lines))
    print(f"\nWrote → {out}")


if __name__ == "__main__":
    main()
