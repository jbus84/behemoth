"""Explore smoothing overlays: signal strength, correlation regime, BTC vol regime, adaptive h.

Run on full history to screen ideas, then holdout-test winners.
"""
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
            "fund_pnl": r["fund_pnl"], "dates": idx, "flow": r.get("flow_arr"), "fwd": r.get("fwd_arr")}


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


def overlay_signal_strength(s: pd.Series, perp: pd.DataFrame, w: int, h: int, k: int, years: tuple, threshold: float) -> pd.Series:
    """Only trade when top-minus-bottom z-score spread > threshold."""
    # Recompute flow ranks to get spread
    # This is expensive; we approximate by using per-symbol flow std
    perp_yr = perp[perp["dt"].dt.year.isin(years)].copy()
    perp_yr["flow6"] = perp_yr["tbv"] / perp_yr["vol"]
    pivot = perp_yr.pivot(index="dt", columns="symbol", values="flow6")
    # cross-sectional z-score per bar
    z = pivot.sub(pivot.mean(axis=1), axis=0).div(pivot.std(axis=1), axis=0)
    # top-minus-bottom spread (using k)
    ranked = z.rank(axis=1, pct=True)
    top_mean = z[ranked >= (1 - k / z.shape[1])].mean(axis=1)
    bot_mean = z[ranked <= (k / z.shape[1])].mean(axis=1)
    spread_idx = top_mean.index.tz_localize(None) if top_mean.index.tz else top_mean.index
    spread = pd.Series(top_mean.values - bot_mean.values, index=spread_idx)
    spread = spread.reindex(s.index, method="ffill").fillna(0)
    mask = spread >= threshold
    return s.where(mask, 0.0)


def overlay_corr_regime(s: pd.Series, perp: pd.DataFrame, years: tuple, quantile: float = 0.8) -> pd.Series:
    """Reduce to 0.5x when median pairwise correlation in top quantile."""
    perp_yr = perp[perp["dt"].dt.year.isin(years)].copy()
    pivot = perp_yr.pivot(index="dt", columns="symbol", values="close")
    rets = pivot.pct_change().dropna()
    # rolling 30-bar median pairwise correlation
    def rolling_median_corr(df: pd.DataFrame, window: int = 30) -> pd.Series:
        out = pd.Series(np.nan, index=df.index)
        for i in range(window, len(df)):
            sub = df.iloc[i - window:i].dropna(axis=1, thresh=window // 2)
            if sub.shape[1] < 3:
                continue
            c = sub.corr().values
            # upper triangle median
            tri = c[np.triu_indices_from(c, k=1)]
            out.iloc[i] = np.median(tri[np.isfinite(tri)])
        return out

    med_corr = rolling_median_corr(rets, 30)
    if med_corr.index.tz:
        med_corr = med_corr.tz_localize(None)
    med_corr = med_corr.reindex(s.index, method="ffill").fillna(0.5)
    thresh = med_corr.quantile(quantile)
    scale = pd.Series(1.0, index=s.index)
    scale[med_corr > thresh] = 0.5
    return s * scale


def overlay_btc_vol(s: pd.Series, perp: pd.DataFrame, years: tuple, window: int = 30, quantile: float = 0.8) -> pd.Series:
    """Reduce to 0.5x when BTC 30d realized vol is in top quantile."""
    perp_yr = perp[perp["dt"].dt.year.isin(years)].copy()
    btc = perp_yr[perp_yr["symbol"] == "BTCUSDT"].set_index("dt")["close"]
    if btc.index.tz:
        btc = btc.tz_localize(None)
    btc_ret = btc.pct_change().dropna()
    vol = btc_ret.rolling(window).std().reindex(s.index, method="ffill").fillna(btc_ret.std())
    thresh = vol.quantile(quantile)
    scale = pd.Series(1.0, index=s.index)
    scale[vol > thresh] = 0.5
    return s * scale


def overlay_drawdown_guard(s: pd.Series, soft: float = -0.10, hard: float = -0.20, soft_scale: float = 0.25) -> pd.Series:
    """Trailing-peak drawdown guard."""
    cum = (1 + s).cumprod()
    scale = pd.Series(1.0, index=s.index)
    peak = cum.iloc[0]
    for i in range(len(cum)):
        peak = max(peak, cum.iloc[i])
        dd = (cum.iloc[i] - peak) / peak
        if dd <= hard:
            scale.iloc[i] = 0.0
        elif dd <= soft:
            scale.iloc[i] = soft_scale
    return s * scale


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

    # base h48_k5
    base = run_raw(perp, 24, 48, 5, years, fm_retail)
    s_base = base["net"]
    m_base = metrics(s_base)

    variants = [("baseline", s_base)]

    # 1) drawdown guard (trained on full history for screening)
    s_guard = overlay_drawdown_guard(s_base, -0.10, -0.20, 0.25)
    variants.append(("guard_-10_-20_0.25", s_guard))

    # 2) signal strength filter (approximate threshold grid)
    for thresh in [1.0, 1.5, 2.0]:
        s_str = overlay_signal_strength(s_base, perp, 24, 48, 5, years, thresh)
        variants.append((f"signal_strength_{thresh}", s_str))

    # 3) correlation regime
    s_corr = overlay_corr_regime(s_base, perp, years, quantile=0.8)
    variants.append(("corr_regime_0.8", s_corr))

    # 4) BTC vol regime
    s_bvol = overlay_btc_vol(s_base, perp, years, 30, 0.8)
    variants.append(("btc_vol_30_0.8", s_bvol))

    # 5) combined: guard + btc vol
    s_comb = overlay_btc_vol(overlay_drawdown_guard(s_base, -0.10, -0.20, 0.25), perp, years, 30, 0.8)
    variants.append(("guard+bvol", s_comb))

    # 6) combined: guard + corr
    s_comb2 = overlay_corr_regime(overlay_drawdown_guard(s_base, -0.10, -0.20, 0.25), perp, years, 0.8)
    variants.append(("guard+corr", s_comb2))

    print(f"{'variant':22s} {'Sharpe':>7s} {'Sortino':>7s} {'maxDD':>7s} {'final':>8s} {'vol':>7s}")
    rows = []
    for name, s in variants:
        m = metrics(s)
        rows.append((name, m))
        print(f"{name:22s} {m['sharpe']:+7.2f} {m['sortino']:+7.2f} {m['max_dd']*100:+7.1f}% {m['final']:8.2f}x {m['vol_ann']*100:7.1f}%")

    # rank by Sharpe
    rows.sort(key=lambda x: x[1]["sharpe"], reverse=True)
    print(f"\nTop by Sharpe: {rows[0][0]}  Sharpe={rows[0][1]['sharpe']:.2f}  maxDD={rows[0][1]['max_dd']:.1%}")

    # write
    out = Path("docs/analysis") / f"{pd.Timestamp.now(tz='UTC').strftime('%Y-%m-%d')}_crypto_flow_explore_smooth.md"
    lines = ["# Smoothness overlay screening (full history 2020-2025)\n\n"]
    lines.append("| variant | Sharpe | Sortino | maxDD | final | vol |\n")
    lines.append("|---------|--------|---------|-------|-------|-----|\n")
    for name, m in rows:
        lines.append(f"| {name} | {m['sharpe']:+.2f} | {m['sortino']:+.2f} | {m['max_dd']:.1%} | {m['final']:.2f}x | {m['vol_ann']*100:.1f}% |\n")
    out.write_text("".join(lines))
    print(f"\nWrote → {out}")


if __name__ == "__main__":
    main()
