"""Additional smoothness ideas: dynamic h, strategy-vol overlay, momentum overlay."""
from __future__ import annotations

import numpy as np
import pandas as pd
from pathlib import Path

from scripts.research.crypto_flow_xs_broad import backtest

CACHE_PERP = "/tmp/crypto_broad_perp.parquet"


def run_raw(perp: pd.DataFrame, w: int, h: int, k: int, years: tuple, fm: dict, signal: str = "flow6") -> dict:
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
    idx = pd.DatetimeIndex(r["dates"]).tz_localize(None)
    return {"net": pd.Series(net, index=idx), "gross": r["gross"], "turn": r["turn"],
            "fund_pnl": r["fund_pnl"], "dates": idx}


def metrics(s: pd.Series) -> dict:
    cum = (1 + s).cumprod()
    dd = (cum - cum.cummax()) / cum.cummax()
    return {
        "sharpe": s.mean() / s.std() * np.sqrt(365) if s.std() > 0 else 0.0,
        "max_dd": dd.min(),
        "final": cum.iloc[-1],
        "vol_ann": s.std() * np.sqrt(365),
        "pos_days": int((s > 0).sum()),
        "neg_days": int((s < 0).sum()),
        "sortino": s.mean() / s[s < 0].std() * np.sqrt(365) if (s < 0).std() > 0 else 0.0,
    }


def overlay_strategy_vol(s: pd.Series, window: int = 15, quantile: float = 0.8, scale: float = 0.5) -> pd.Series:
    """Reduce exposure when strategy's own realized vol spikes."""
    rolling_vol = s.rolling(window).std().reindex(s.index).fillna(s.std())
    thresh = rolling_vol.quantile(quantile)
    sc = pd.Series(1.0, index=s.index)
    sc[rolling_vol > thresh] = scale
    return s * sc


def overlay_momentum_stop(s: pd.Series, window: int = 5, threshold: float = -0.03, scale: float = 0.5) -> pd.Series:
    """Reduce exposure when strategy has lost >threshold over last N days."""
    cum_ret = (1 + s).cumprod()
    rolling_ret = cum_ret.pct_change(window).reindex(s.index).fillna(0)
    sc = pd.Series(1.0, index=s.index)
    sc[rolling_ret < threshold] = scale
    return s * sc


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

    base = run_raw(perp, 24, 48, 5, years, fm_retail)
    s_base = base["net"]

    variants = [("baseline", s_base)]

    # strategy-vol overlays
    for w, q in [(15, 0.8), (10, 0.85), (20, 0.75)]:
        s = overlay_strategy_vol(s_base, w, q, 0.5)
        variants.append((f"strat_vol_{w}_{q}", s))

    # momentum-stop overlays
    for w, th in [(5, -0.03), (10, -0.05), (3, -0.02)]:
        s = overlay_momentum_stop(s_base, w, th, 0.5)
        variants.append((f"mom_stop_{w}_{th}", s))

    # combined: guard + strat_vol
    def guard(s):
        cum = (1 + s).cumprod()
        sc = pd.Series(1.0, index=s.index)
        peak = cum.iloc[0]
        for i in range(len(cum)):
            peak = max(peak, cum.iloc[i])
            dd = (cum.iloc[i] - peak) / peak
            if dd <= -0.20:
                sc.iloc[i] = 0.0
            elif dd <= -0.10:
                sc.iloc[i] = 0.25
        return s * sc

    variants.append(("guard+strat_vol", overlay_strategy_vol(guard(s_base), 15, 0.8, 0.5)))
    variants.append(("guard+mom_stop", overlay_momentum_stop(guard(s_base), 5, -0.03, 0.5)))

    print(f"{'variant':22s} {'Sharpe':>7s} {'Sortino':>7s} {'maxDD':>7s} {'final':>8s} {'vol':>7s}")
    rows = []
    for name, s in variants:
        m = metrics(s)
        rows.append((name, m))
        print(f"{name:22s} {m['sharpe']:+7.2f} {m['sortino']:+7.2f} {m['max_dd']*100:+7.1f}% {m['final']:8.2f}x {m['vol_ann']*100:7.1f}%")

    rows.sort(key=lambda x: x[1]["sharpe"], reverse=True)
    print(f"\nTop by Sharpe: {rows[0][0]}  Sharpe={rows[0][1]['sharpe']:.2f}  maxDD={rows[0][1]['max_dd']:.1%}")

    out = Path("docs/analysis") / f"{pd.Timestamp.now(tz='UTC').strftime('%Y-%m-%d')}_crypto_flow_explore_more.md"
    lines = ["# Additional smoothness overlays (full history 2020-2025)\n\n"]
    lines.append("| variant | Sharpe | Sortino | maxDD | final | vol |\n")
    lines.append("|---------|--------|---------|-------|-------|-----|\n")
    for name, m in rows:
        lines.append(f"| {name} | {m['sharpe']:+.2f} | {m['sortino']:+.2f} | {m['max_dd']:.1%} | {m['final']:.2f}x | {m['vol_ann']*100:.1f}% |\n")
    out.write_text("".join(lines))
    print(f"\nWrote → {out}")


if __name__ == "__main__":
    main()
