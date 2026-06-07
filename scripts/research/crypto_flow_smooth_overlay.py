"""Risk overlays on h48_k5 — vol-scaling + drawdown guard."""
from __future__ import annotations

import numpy as np
import pandas as pd
from pathlib import Path

from scripts.research.crypto_flow_xs_broad import backtest

CACHE_PERP = "/tmp/crypto_broad_perp.parquet"

def run_raw(perp, w, h, k, years, fm, signal):
    r = backtest(perp, w, h, k, years, fm, signal=signal)
    spread = fm.get("spread_bps", 2.0) / 1e4
    rebate = fm.get("maker_rebate_bps", 2.0) / 1e4
    taker_fee = fm.get("taker_fee_bps", 5.0) / 1e4
    queue_pos = fm.get("queue_pos", 0.0)
    adv = fm.get("adv_bps", 0.0) / 1e4
    p_fill_base = fm.get("p_fill_base", 1.0)
    p_fill = max(0.05, p_fill_base * (1 - queue_pos))
    cost_per_turn = p_fill * (spread - rebate + adv) + (1 - p_fill) * (spread + taker_fee)
    net = r["gross"] - r["turn"] * cost_per_turn + r["fund_pnl"]
    return pd.Series(net, index=pd.DatetimeIndex(r["dates"]).tz_localize(None)), r["dates"]


def apply_overlays(s: pd.Series, btc: pd.Series) -> dict:
    # 1) baseline
    cum = (1 + s).cumprod()
    dd = (cum - cum.cummax()) / cum.cummax()
    baseline = {"sharpe": s.mean() / s.std() * np.sqrt(365), "max_dd": dd.min(), "final": cum.iloc[-1], "vol": s.std() * np.sqrt(365)}

    # 2) vol-target: scale by median_30d_vol / current_30d_vol, clipped [0.25, 2.0]
    btc_ret = btc.pct_change().dropna()
    rolling_vol = btc_ret.rolling(30).std() * np.sqrt(365)
    med_vol = rolling_vol.median()
    vol_scale = (med_vol / rolling_vol).reindex(s.index, method="ffill").fillna(1.0)
    vol_scale = vol_scale.clip(0.25, 2.0)
    # apply to returns (assumes scaling doesn't affect fill/cost dynamics, first-order approx)
    s_vol = s * vol_scale
    cum_vol = (1 + s_vol).cumprod()
    dd_vol = (cum_vol - cum_vol.cummax()) / cum_vol.cummax()
    vol_target = {"sharpe": s_vol.mean() / s_vol.std() * np.sqrt(365), "max_dd": dd_vol.min(), "final": cum_vol.iloc[-1], "vol": s_vol.std() * np.sqrt(365)}

    # 3) drawdown guard: if dd > -0.15, scale to 0.5; if dd > -0.25, scale to 0.0
    guard_scale = pd.Series(1.0, index=s.index)
    for i in range(1, len(cum)):
        c = cum.iloc[i]
        peak = cum.iloc[:i+1].max()
        ddi = (c - peak) / peak
        if ddi < -0.25:
            guard_scale.iloc[i] = 0.0
        elif ddi < -0.15:
            guard_scale.iloc[i] = 0.5
        else:
            guard_scale.iloc[i] = 1.0
    s_guard = s * guard_scale
    cum_guard = (1 + s_guard).cumprod()
    dd_guard = (cum_guard - cum_guard.cummax()) / cum_guard.cummax()
    guard = {"sharpe": s_guard.mean() / s_guard.std() * np.sqrt(365), "max_dd": dd_guard.min(), "final": cum_guard.iloc[-1], "vol": s_guard.std() * np.sqrt(365)}

    # 4) combined
    comb_scale = vol_scale * guard_scale
    s_comb = s * comb_scale
    cum_comb = (1 + s_comb).cumprod()
    dd_comb = (cum_comb - cum_comb.cummax()) / cum_comb.cummax()
    comb = {"sharpe": s_comb.mean() / s_comb.std() * np.sqrt(365), "max_dd": dd_comb.min(), "final": cum_comb.iloc[-1], "vol": s_comb.std() * np.sqrt(365)}

    return {"baseline": baseline, "vol_target": vol_target, "drawdown_guard": guard, "combined": comb}


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
    s, _ = run_raw(perp, 24, 48, 5, years, fm_retail, "flow6")

    # BTC close for vol proxy
    btc = perp[perp["symbol"] == "BTCUSDT"].set_index("dt")["close"]
    if btc.index.tz:
        btc = btc.tz_localize(None)

    results = apply_overlays(s, btc)
    print(f"{'overlay':18s} {'Sharpe':>7s} {'maxDD':>7s} {'final':>7s} {'vol':>7s}")
    for name, m in results.items():
        print(f"{name:18s} {m['sharpe']:+7.2f} {m['max_dd']*100:+7.1f}% {m['final']:7.2f}x {m['vol']*100:7.2f}%")

    # write
    out = Path("docs/analysis") / f"{pd.Timestamp.now(tz='UTC').strftime('%Y-%m-%d')}_crypto_flow_overlay_findings.md"
    lines = ["# Risk overlays on h48_k5 (full history 2020-2025)\n\n"]
    lines.append("| overlay | Sharpe | maxDD | final | vol |\n")
    lines.append("|---------|--------|-------|-------|-----|\n")
    for name, m in results.items():
        lines.append(f"| {name} | {m['sharpe']:+.2f} | {m['max_dd']*100:.1f}% | {m['final']:.2f}x | {m['vol']*100:.2f}% |\n")
    out.write_text("".join(lines))
    print(f"\nWrote → {out}")


if __name__ == "__main__":
    main()
