"""Canonical risk overlays + metrics for the crypto cross-sectional flow book.

This module exists because three exploratory scripts (smooth_overlay, holdout_combined,
adverse_selection) each re-implemented the drawdown guard / momentum stop / Sharpe with
THREE shared bugs that together manufactured a fake "Sharpe 4.66 / -10% DD / 1,719x"
result. See docs/analysis/2026-06-07_crypto_flow_VALIDATION_corrected.md.

Bugs fixed here, once:
  1. LOOK-AHEAD overlays. The guard/stop computed the drawdown (or trailing return)
     *including the current period* and then scaled *that same period's* return — i.e.
     it cut the loss on the exact bar the loss happened. The honest version decides the
     scale for period i using information available at the *start* of period i, so the
     scale series is shifted forward by one period (`causal=True`, the default).
  2. WRONG ANNUALIZATION. Sharpe was annualised with sqrt(365), but the book rebalances
     every `h` hours (h=48 -> 2-day periods -> 182.5 periods/yr, not 365). Use
     `ann_factor(h)` instead; this is a flat sqrt(2) ~ 1.41x inflation at h=48.
  3. FREE TRADING. The fee model set maker_rebate_bps == spread_bps == 2.0, making
     `cost_per_turn` identically 0. A 2 bps maker *rebate* is not retail reality (Binance
     USD-M retail maker is ~ +1 bps fee). Use `RETAIL_MAKER` below, which keeps the
     0.2 bps rebate / queue / adverse-selection assumptions from the earlier Stage-2/3
     fee models rather than the free-lunch one.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

BARS_PER_YEAR = 24 * 365  # hourly bars

# Realistic retail maker fee model (NOT the free-lunch rebate==spread one).
RETAIL_MAKER = {
    "name": "retail_maker",
    "spread_bps": 2.0,
    "maker_rebate_bps": 0.2,
    "taker_fee_bps": 5.0,
    "queue_pos": 0.2,
    "adv_bps": 0.5,
    "p_fill_base": 0.85,
}


def periods_per_year(h: int) -> float:
    """Number of rebalance periods per year for an h-hour holding period."""
    return BARS_PER_YEAR / h


def ann_factor(h: int) -> float:
    """Sharpe annualization factor for an h-hour rebalance period."""
    return float(np.sqrt(periods_per_year(h)))


def cost_per_turn(fm: dict) -> float:
    """Per-unit-turnover cost (fraction) from a fee model dict."""
    spread = fm.get("spread_bps", 2.0) / 1e4
    rebate = fm.get("maker_rebate_bps", 0.2) / 1e4
    taker_fee = fm.get("taker_fee_bps", 5.0) / 1e4
    queue_pos = fm.get("queue_pos", 0.2)
    adv = fm.get("adv_bps", 0.5) / 1e4
    p_fill_base = fm.get("p_fill_base", 0.85)
    p_fill = max(0.05, p_fill_base * (1 - queue_pos))
    return p_fill * (spread - rebate + adv) + (1 - p_fill) * (spread + taker_fee)


def drawdown_guard(s: pd.Series, soft: float = -0.08, hard: float = -0.15,
                   soft_scale: float = 0.25, causal: bool = True) -> pd.Series:
    """Scale exposure down inside a drawdown.

    With ``causal=True`` (the default and the only honest mode) the scale applied to
    period i is decided from the drawdown observed through period i-1.
    """
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
    if causal:
        scale = scale.shift(1).fillna(1.0)
    return s * scale


def momentum_stop(s: pd.Series, window: int = 3, threshold: float = -0.02,
                  scale: float = 0.5, causal: bool = True) -> pd.Series:
    """Cut exposure after a trailing-return drop over ``window`` periods.

    With ``causal=True`` the cut applies to the period *after* the drop is observed.
    """
    cum = (1 + s).cumprod()
    roll = cum.pct_change(window).reindex(s.index).fillna(0)
    sc = pd.Series(1.0, index=s.index)
    sc[roll < threshold] = scale
    if causal:
        sc = sc.shift(1).fillna(1.0)
    return s * sc


def vol_target(s: pd.Series, vol_proxy_ret: pd.Series, h: int,
               lo: float = 0.25, hi: float = 2.0) -> pd.Series:
    """Scale by median/current rolling vol of an external proxy (e.g. BTC).

    Uses past-only rolling vol, reindexed with ffill, so it is causal by construction.
    """
    rolling_vol = vol_proxy_ret.rolling(30).std() * ann_factor(h)
    med = rolling_vol.median()
    vs = (med / rolling_vol).reindex(s.index, method="ffill").fillna(1.0).clip(lo, hi)
    return s * vs


def metrics(s: pd.Series, h: int) -> dict:
    """Sharpe (correctly annualised for h-hour periods), maxDD, final multiple."""
    cum = (1 + s).cumprod()
    dd = (cum - cum.cummax()) / cum.cummax()
    sharpe = s.mean() / s.std() * ann_factor(h) if s.std() > 0 else 0.0
    return {
        "sharpe": float(sharpe),
        "max_dd": float(dd.min()),
        "final": float(cum.iloc[-1]),
        "vol_ann": float(s.std() * ann_factor(h)),
        "pos": int((s > 0).sum()),
        "neg": int((s < 0).sum()),
    }
