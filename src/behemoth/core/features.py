"""Canonical feature builder for the OCO CatBoost model.

This is the SINGLE SOURCE OF TRUTH for computing the 16-feature vector.
Both the research pipeline (``scripts/build_tick_velocity_dataset.py``)
and the production runtime (``src/behemoth/runtime/state.py``) MUST
delegate to this module.  Any change to feature calculation happens
here and only here.

Warmup Requirements
-------------------
The rolling window calculations require a minimum history buffer:

- ``vol_window`` (default 96):  rolling std/mean for z-score normalizers.
  Min periods = ``max(8, vol_window // 3)`` = 32 bars.
- ``cost_window`` (default 288): rolling median/quantile for cost estimation.
  Min periods = ``max(8, cost_window // 4)`` = 72 bars.
- ``hl_first/hl_pos_frac`` rolling 24: min periods = 8 bars.
- All rolling windows use ``.shift(1)`` (lag-1 causality), adding +1 bar.

**Full precision**: ``cost_window + 1 = 289`` bars.
**Minimum usable**: ``max(8, cost_window // 4) + 1 = 73`` bars (with partial
windows for vol normalizers — NOT recommended for production).

Production policy: require ``cost_window + 1`` bars before emitting features
to guarantee full-precision rolling statistics and avoid partial-window noise.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from src.behemoth.core.schemas import ModelFeatures


# ── Configuration ─────────────────────────────────────────────────────

@dataclass(frozen=True)
class FeatureConfig:
    """Immutable configuration governing rolling window sizes.

    Matches the defaults in ``scripts/build_tick_velocity_dataset.py``.
    """

    vol_window: int = 96
    """Window for tick-rate, spread, and velocity std normalizers (bars)."""

    cost_window: int = 288
    """Window for spread-median and slippage-proxy estimation (bars)."""

    @property
    def min_periods_vol(self) -> int:
        return max(8, self.vol_window // 3)

    @property
    def min_periods_cost(self) -> int:
        return max(8, self.cost_window // 4)

    @property
    def min_periods_cost_slip(self) -> int:
        return max(8, self.cost_window // 6)

    @property
    def full_warmup_bars(self) -> int:
        """Number of bars needed for full-precision feature computation."""
        return max(self.vol_window, self.cost_window) + 1


# ── Pip Size ──────────────────────────────────────────────────────────

def pip_size(symbol: str) -> float:
    """Return the pip unit for a given FX symbol."""
    s = symbol.upper().strip()
    if s.endswith("JPY"):
        return 0.01
    if s.startswith("XAU"):
        return 0.1
    if s.startswith("XAG"):
        return 0.01
    return 0.0001


# ── Feature Builder ───────────────────────────────────────────────────

def compute_features_from_bars(
    df: pd.DataFrame,
    *,
    symbol: str,
    bar_ticks: int,
    horizon: int,
    barrier_pips: float,
    cfg: FeatureConfig = FeatureConfig(),
) -> ModelFeatures | None:
    """Compute the 16-feature vector from a DataFrame of tick bars.

    Parameters
    ----------
    df : pd.DataFrame
        Must contain columns: ``close_ts``, ``timestamp`` (or ``ts``),
        ``open``, ``high``, ``low``, ``close``, ``spread``, ``tick_volume``,
        ``hl_first``, ``hl_pos_frac``.  Rows must be sorted by time ascending.
    symbol : str
        FX pair name (used for pip size calculation).
    bar_ticks : int
        Number of ticks per bar (structural feature passed through).
    horizon : int
        OCO horizon parameter (structural feature passed through).
    barrier_pips : float
        OCO barrier in pips (structural feature passed through).
    cfg : FeatureConfig
        Rolling window configuration.

    Returns
    -------
    ModelFeatures | None
        The 16-feature Pydantic model, or None if insufficient warmup.
    """
    n = len(df)
    if n < cfg.full_warmup_bars:
        return None

    pip = pip_size(symbol)

    # Resolve column names (DuckDB uses _price suffix, pandas uses raw names)
    close_col = "close_price" if "close_price" in df.columns else "close"
    open_col = "open_price" if "open_price" in df.columns else "open"
    high_col = "high_price" if "high_price" in df.columns else "high"
    low_col = "low_price" if "low_price" in df.columns else "low"
    ts_col = "ts" if "ts" in df.columns else "timestamp"

    close = df[close_col].astype(float)
    open_ = df[open_col].astype(float)
    high = df[high_col].astype(float)
    low = df[low_col].astype(float)

    close_ts = pd.to_datetime(df["close_ts"], utc=True)
    timestamp = pd.to_datetime(df[ts_col], utc=True)

    vw = cfg.vol_window
    cw = cfg.cost_window
    mp_vol = cfg.min_periods_vol
    mp_cost = cfg.min_periods_cost
    mp_cost_slip = cfg.min_periods_cost_slip

    # ── hour_utc ──
    hour_utc = float(close_ts.iloc[-1].hour)

    # ── duration + tick_rate ──
    duration_sec = (close_ts - timestamp).dt.total_seconds().clip(lower=1e-6)
    tick_rate_hz = df["tick_volume"].astype(float) / duration_sec

    # ── tick_rate_z ──
    tr_mu = tick_rate_hz.rolling(vw, min_periods=mp_vol).mean().shift(1)
    tr_sd = tick_rate_hz.rolling(vw, min_periods=mp_vol).std(ddof=0).shift(1)
    tick_rate_z_s = (tick_rate_hz - tr_mu) / tr_sd.replace(0.0, np.nan)

    # ── spread_z ──
    spread_pips = df["spread"].astype(float) / pip
    sp_mu = spread_pips.rolling(vw, min_periods=mp_vol).mean().shift(1)
    sp_sd = spread_pips.rolling(vw, min_periods=mp_vol).std(ddof=0).shift(1)
    spread_z_s = (spread_pips - sp_mu) / sp_sd.replace(0.0, np.nan)

    # ── range_pips ──
    range_pips_s = (high - low) / pip

    # ── ret1_pips (vel_pips_h1) ──
    vel_h1 = (close - close.shift(1)) / pip

    # ── ret_z, ret_abs_z ──
    vol_ref = vel_h1.rolling(vw, min_periods=mp_vol).std(ddof=0).shift(1)
    ret_z_s = vel_h1 / vol_ref.replace(0.0, np.nan)
    ret_abs_z_s = vel_h1.abs() / vol_ref.replace(0.0, np.nan)

    # ── cost_est_pips ──
    spread_recent = spread_pips.rolling(cw, min_periods=mp_cost).median().shift(1)
    gap_abs = (open_ - close.shift(1)).abs() / pip
    slip_proxy = gap_abs.rolling(cw, min_periods=mp_cost_slip).quantile(0.75).shift(1)
    slip_fallback = (
        range_pips_s.rolling(cw, min_periods=mp_cost_slip).quantile(0.75).shift(1) * 0.2
    )
    slip_proxy_pips = slip_proxy.fillna(slip_fallback).fillna(0.1).clip(lower=0.01)
    cost_est = (
        spread_recent.fillna(spread_pips.shift(1)).fillna(spread_pips.median())
        + slip_proxy_pips
    )

    # ── vel_cost_units_h1, vel_abs_cost_units_h1 ──
    vel_cu_h1 = vel_h1 / cost_est.replace(0.0, np.nan)
    vel_abs_cu_h1 = vel_h1.abs() / cost_est.replace(0.0, np.nan)

    # ── hl_first_mean_24, hl_pos_frac_mean_24 ──
    hl_first_s = df["hl_first"].astype(float)
    hl_pos_frac_s = df["hl_pos_frac"].astype(float)
    hl_first_mean_24 = hl_first_s.rolling(24, min_periods=8).mean().shift(1)
    hl_pos_frac_mean_24 = hl_pos_frac_s.rolling(24, min_periods=8).mean().shift(1)

    # ── Extract last row ──
    i = n - 1

    def _safe(series: pd.Series) -> float:
        v = float(series.iloc[i])
        if not np.isfinite(v):
            return float("nan")
        return v

    return ModelFeatures(
        cost_est_pips=_safe(cost_est),
        range_pips=_safe(range_pips_s),
        ret1_pips=_safe(vel_h1),
        ret_z=_safe(ret_z_s),
        ret_abs_z=_safe(ret_abs_z_s),
        vel_cost_units_h1=_safe(vel_cu_h1),
        vel_abs_cost_units_h1=_safe(vel_abs_cu_h1),
        spread_z=_safe(spread_z_s),
        tick_rate_z=_safe(tick_rate_z_s),
        hour_utc=hour_utc,
        hl_first=_safe(hl_first_s),
        hl_first_mean_24=_safe(hl_first_mean_24),
        hl_pos_frac_mean_24=_safe(hl_pos_frac_mean_24),
        bar_ticks=float(bar_ticks),
        horizon=float(horizon),
        barrier_pips=float(barrier_pips),
    )
