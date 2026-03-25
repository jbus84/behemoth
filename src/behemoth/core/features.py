"""Canonical feature builder for the OCO CatBoost model.

This is the SINGLE SOURCE OF TRUTH for computing the 16-feature vector.
Both the research pipeline (``scripts/build_tick_velocity_dataset.py``)
and the production runtime (``behemoth.runtime.state``) MUST
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

# ── Constants ─────────────────────────────────────────────────────────

class FeatureConstants:
    """Hardcoded physical constants and thresholds for feature computation."""

    # Masking thresholds
    WEEKEND_GAP_SEC = 43200.0  # 12 hours

    # Slip proxy quantiles and factors
    SLIP_QUANTILE = 0.75
    SLIP_FALLBACK_FACTOR = 0.2
    SLIP_FALLBACK_DEFAULT = 0.1
    SLIP_MIN_CLIP = 0.01

    # Structural feature rolling
    STRUCTURAL_WINDOW = 24
    STRUCTURAL_MIN_PERIODS = 8

    # Safe float clipping
    DURATION_MIN_SEC = 1e-6


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

    Returns the features for the LAST bar in the DataFrame.
    """
    matrix = compute_feature_matrix_from_bars(
        df,
        symbol=symbol,
        bar_ticks=bar_ticks,
        horizon=horizon,
        barrier_pips=barrier_pips,
        cfg=cfg,
    )
    if matrix is None or matrix.empty:
        return None

    # Extract last row into ModelFeatures
    row = matrix.iloc[-1]
    return ModelFeatures(**row.to_dict())


def compute_feature_matrix_from_bars(
    df: pd.DataFrame,
    *,
    symbol: str,
    bar_ticks: int,
    horizon: int,
    barrier_pips: float,
    cfg: FeatureConfig = FeatureConfig(),
) -> pd.DataFrame | None:
    """Compute the 16-feature matrix for all bars in the DataFrame.

    Returns a DataFrame with one row per input bar. Rows with insufficient
    warmup history will contain NaN values.
    """
    n = len(df)
    if n < 1:
        return None

    pip = pip_size(symbol)
    close, open_, high, low, close_ts, timestamp = _extract_core_series(df)

    # ── Temporal gap masking (weekend protection) ──
    bar_gap_sec = (timestamp - timestamp.shift(1)).dt.total_seconds()
    is_weekend_gap = bar_gap_sec > FeatureConstants.WEEKEND_GAP_SEC

    durations = (close_ts - timestamp).dt.total_seconds().clip(lower=FeatureConstants.DURATION_MIN_SEC)

    # ── Sub-components (all vectorized pd.Series) ──
    tick_rate_z, spread_z, spread_pips = _compute_micro_features(df, pip, durations, cfg)
    vel_h1, ret_z, ret_abs_z = _compute_velocity_features(close, pip, is_weekend_gap, cfg)
    range_pips = (high - low) / pip
    cost_est, vel_cu, vel_abs_cu = _compute_cost_features(
        spread_pips, range_pips, open_, close, pip, is_weekend_gap, vel_h1, cfg
    )
    hl_first_m24, hl_pos_frac_m24 = _compute_structural_features(df)

    # ── Assemble Feature Matrix ──
    out = pd.DataFrame({
        "cost_est_pips": cost_est,
        "range_pips": range_pips,
        "ret1_pips": vel_h1,
        "ret_z": ret_z,
        "ret_abs_z": ret_abs_z,
        "vel_cost_units_h1": vel_cu,
        "vel_abs_cost_units_h1": vel_abs_cu,
        "spread_z": spread_z,
        "tick_rate_z": tick_rate_z,
        "hour_utc": close_ts.dt.hour.astype(float),
        "hl_first": df["hl_first"].astype(float) if "hl_first" in df.columns else np.nan,
        "hl_first_mean_24": hl_first_m24,
        "hl_pos_frac_mean_24": hl_pos_frac_m24,
        "bar_ticks": float(bar_ticks),
        "horizon": float(horizon),
        "barrier_pips": float(barrier_pips),
    })

    # Mask rows with insufficient warmup (n < cfg.full_warmup_bars)
    # We keep the rows but they will have NaNs from the rolling operations anyway.
    # However, to maintain strict parity with compute_features_from_bars,
    # we return None if the *total* length is too small.
    if n < cfg.full_warmup_bars:
        return out.iloc[0:0] # Return empty df with correct columns

    # Match legacy _safe() behavior: coerce NaNs/Infs to 0.0
    return out.replace([np.inf, -np.inf], np.nan).fillna(0.0)


def compute_regime_quantiles_from_bars(
    df: pd.DataFrame,
    *,
    symbol: str,
    cfg: FeatureConfig = FeatureConfig(),
) -> dict[str, float]:
    """Compute regime-quantile cutoffs from a recent bar buffer.

    Quantile names and feature definitions mirror ``run_tick_opportunity_mining._quantiles``.
    Values are computed on the available warmup buffer and are intended for runtime
    regime gating (e.g. ``high_abs_vel_q80``) in API inference.
    """
    n = len(df)
    if n < cfg.full_warmup_bars:
        return {}

    pip = pip_size(symbol)
    close, open_, high, low, _close_ts, timestamp = _extract_core_series(df)
    bar_gap_sec = (timestamp - timestamp.shift(1)).dt.total_seconds()
    is_weekend_gap = bar_gap_sec > FeatureConstants.WEEKEND_GAP_SEC
    durations = (_close_ts - timestamp).dt.total_seconds().clip(lower=FeatureConstants.DURATION_MIN_SEC)

    tick_rate_z, spread_z, spread_pips = _compute_micro_features(df, pip, durations, cfg)
    vel_h1, _ret_z, ret_abs_z = _compute_velocity_features(close, pip, is_weekend_gap, cfg)
    range_pips = (high - low) / pip
    cost_est, _vel_cu, vel_abs_cu = _compute_cost_features(
        spread_pips, range_pips, open_, close, pip, is_weekend_gap, vel_h1, cfg
    )

    def _q(series: pd.Series, quantile: float) -> float:
        s = pd.to_numeric(series, errors="coerce").replace([np.inf, -np.inf], np.nan).dropna()
        if len(s) == 0:
            return float("nan")
        return float(s.quantile(float(quantile)))

    return {
        "cost_q30": _q(cost_est, 0.30),
        "cost_q50": _q(cost_est, 0.50),
        "rng_q70": _q(range_pips, 0.70),
        "rng_q80": _q(range_pips, 0.80),
        "shock_q60": _q(ret_abs_z, 0.60),
        "shock_q70": _q(ret_abs_z, 0.70),
        "shock_q80": _q(ret_abs_z, 0.80),
        "vel_q70": _q(vel_abs_cu, 0.70),
        "vel_q80": _q(vel_abs_cu, 0.80),
        "spread_q70": _q(spread_z, 0.70),
        "tick_q30": _q(tick_rate_z, 0.30),
    }


def _extract_core_series(df: pd.DataFrame) -> tuple[pd.Series, pd.Series, pd.Series, pd.Series, pd.Series, pd.Series]:
    """Resolve column names and return strongly-typed base series."""
    cc = "close_price" if "close_price" in df.columns else "close"
    oc = "open_price" if "open_price" in df.columns else "open"
    hc = "high_price" if "high_price" in df.columns else "high"
    lc = "low_price" if "low_price" in df.columns else "low"
    tc = "ts" if "ts" in df.columns else "timestamp"

    close = df[cc].astype(float)
    open_ = df[oc].astype(float)
    high = df[hc].astype(float)
    low = df[lc].astype(float)
    close_ts = pd.to_datetime(df["close_ts"], utc=True)
    timestamp = pd.to_datetime(df[tc], utc=True)
    return close, open_, high, low, close_ts, timestamp


def _build_model_features(df: pd.DataFrame, feats: tuple, context: tuple) -> ModelFeatures:
    """Safely extract the last row into the ModelFeatures schema."""
    cost_est, range_pips, vel_h1, ret_z, ret_abs_z, vel_cu, vel_abs_cu, spread_z, tick_rate_z, hl_first_m24, hl_pos_frac_m24 = feats
    hour_utc, bar_ticks, horizon, barrier_pips = context

    i = len(df) - 1

    def _safe(series: pd.Series) -> float:
        v = float(series.iloc[i])
        return v if np.isfinite(v) else float("nan")

    return ModelFeatures(
        cost_est_pips=_safe(cost_est),
        range_pips=_safe(range_pips),
        ret1_pips=_safe(vel_h1),
        ret_z=_safe(ret_z),
        ret_abs_z=_safe(ret_abs_z),
        vel_cost_units_h1=_safe(vel_cu),
        vel_abs_cost_units_h1=_safe(vel_abs_cu),
        spread_z=_safe(spread_z),
        tick_rate_z=_safe(tick_rate_z),
        hour_utc=hour_utc,
        hl_first=_safe(df["hl_first"].astype(float)),
        hl_first_mean_24=_safe(hl_first_m24),
        hl_pos_frac_mean_24=_safe(hl_pos_frac_m24),
        bar_ticks=float(bar_ticks),
        horizon=float(horizon),
        barrier_pips=float(barrier_pips),
    )


def _compute_micro_features(
    df: pd.DataFrame, pip: float, durations: pd.Series, cfg: FeatureConfig
) -> tuple[pd.Series, pd.Series, pd.Series]:
    vw = cfg.vol_window
    mp_vol = cfg.min_periods_vol

    tick_rate_hz = df["tick_volume"].astype(float) / durations
    tr_mu = tick_rate_hz.rolling(vw, min_periods=mp_vol).mean().shift(1)
    tr_sd = tick_rate_hz.rolling(vw, min_periods=mp_vol).std(ddof=0).shift(1)
    tick_rate_z_s = (tick_rate_hz - tr_mu) / tr_sd.replace(0.0, np.nan)

    spread_pips = df["spread"].astype(float) / pip
    sp_mu = spread_pips.rolling(vw, min_periods=mp_vol).mean().shift(1)
    sp_sd = spread_pips.rolling(vw, min_periods=mp_vol).std(ddof=0).shift(1)
    spread_z_s = (spread_pips - sp_mu) / sp_sd.replace(0.0, np.nan)
    return tick_rate_z_s, spread_z_s, spread_pips


def _compute_velocity_features(
    close: pd.Series, pip: float, is_weekend_gap: pd.Series, cfg: FeatureConfig
) -> tuple[pd.Series, pd.Series, pd.Series]:
    vw = cfg.vol_window
    mp_vol = cfg.min_periods_vol

    vel_h1 = (close - close.shift(1)) / pip
    vel_h1 = vel_h1.mask(is_weekend_gap, np.nan)

    vol_ref = vel_h1.rolling(vw, min_periods=mp_vol).std(ddof=0).shift(1)
    ret_z_s = vel_h1 / vol_ref.replace(0.0, np.nan)
    ret_abs_z_s = vel_h1.abs() / vol_ref.replace(0.0, np.nan)
    return vel_h1, ret_z_s, ret_abs_z_s


def _compute_cost_features(
    spread_pips: pd.Series,
    range_pips_s: pd.Series,
    open_: pd.Series,
    close: pd.Series,
    pip: float,
    is_weekend_gap: pd.Series,
    vel_h1: pd.Series,
    cfg: FeatureConfig
) -> tuple[pd.Series, pd.Series, pd.Series]:
    cw = cfg.cost_window
    mp_cost = cfg.min_periods_cost
    mp_cost_slip = cfg.min_periods_cost_slip

    spread_recent = spread_pips.rolling(cw, min_periods=mp_cost).median().shift(1)

    gap_abs = (open_ - close.shift(1)).abs() / pip
    gap_abs = gap_abs.mask(is_weekend_gap, np.nan)

    slip_proxy = gap_abs.rolling(cw, min_periods=mp_cost_slip).quantile(FeatureConstants.SLIP_QUANTILE).shift(1)
    slip_fallback = (
        range_pips_s.rolling(cw, min_periods=mp_cost_slip).quantile(FeatureConstants.SLIP_QUANTILE).shift(1)
        * FeatureConstants.SLIP_FALLBACK_FACTOR
    )
    slip_proxy_pips = slip_proxy.fillna(slip_fallback).fillna(FeatureConstants.SLIP_FALLBACK_DEFAULT).clip(lower=FeatureConstants.SLIP_MIN_CLIP)

    cost_est = (
        spread_recent.fillna(spread_pips.shift(1)).fillna(spread_pips.median())
        + slip_proxy_pips
    )

    vel_cu_h1 = vel_h1 / cost_est.replace(0.0, np.nan)
    vel_abs_cu_h1 = vel_h1.abs() / cost_est.replace(0.0, np.nan)
    return cost_est, vel_cu_h1, vel_abs_cu_h1


def _compute_structural_features(df: pd.DataFrame) -> tuple[pd.Series, pd.Series]:
    """Compute smoothing of micro-structural markers."""
    hl_first_s = df["hl_first"].astype(float)
    hl_pos_frac_s = df["hl_pos_frac"].astype(float)

    hl_first_mean_24 = hl_first_s.rolling(
        FeatureConstants.STRUCTURAL_WINDOW, min_periods=FeatureConstants.STRUCTURAL_MIN_PERIODS
    ).mean().shift(1)

    hl_pos_frac_mean_24 = hl_pos_frac_s.rolling(
        FeatureConstants.STRUCTURAL_WINDOW, min_periods=FeatureConstants.STRUCTURAL_MIN_PERIODS
    ).mean().shift(1)

    return hl_first_mean_24, hl_pos_frac_mean_24
