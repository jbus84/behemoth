"""Regime Quantile Contract — formalize valid regime names, quantiles, and their semantics."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class RegimeQuantileType(str, Enum):
    """Quantile types and their feature sources."""

    COST = "cost"  # cost_est_pips feature
    RANGE = "range"  # range_pips feature
    SHOCK = "shock"  # ret_abs_z feature
    VELOCITY = "velocity"  # vel_abs_cost_units_h1 feature
    SPREAD = "spread"  # spread_z feature
    TICK_RATE = "tick_rate"  # tick_rate_z feature


@dataclass(frozen=True)
class RegimeQuantile:
    """Definition of a single regime quantile cutoff."""

    name: str  # e.g., "cost_q30"
    feature_name: str  # e.g., "cost_est_pips" (what to compare against)
    quantile_type: RegimeQuantileType  # e.g., COST
    percentile: float  # e.g., 0.30 for "30th percentile"

    def __post_init__(self) -> None:
        if not (0.0 <= self.percentile <= 1.0):
            raise ValueError(f"Percentile must be in [0, 1], got {self.percentile}")


class RegimeQuantileContract:
    """Single source of truth for regime quantiles and valid regime names.

    Defines:
    1. All valid quantile names and their semantics (feature, percentile)
    2. All valid regime gate names and their decision rules
    3. Validation that regime gates use only defined quantiles
    """

    # All valid quantiles — computed from bar buffer during warmup
    _QUANTILES = {
        "cost_q30": RegimeQuantile("cost_q30", "cost_est_pips", RegimeQuantileType.COST, 0.30),
        "cost_q50": RegimeQuantile("cost_q50", "cost_est_pips", RegimeQuantileType.COST, 0.50),
        "rng_q70": RegimeQuantile("rng_q70", "range_pips", RegimeQuantileType.RANGE, 0.70),
        "rng_q80": RegimeQuantile("rng_q80", "range_pips", RegimeQuantileType.RANGE, 0.80),
        "shock_q60": RegimeQuantile("shock_q60", "ret_abs_z", RegimeQuantileType.SHOCK, 0.60),
        "shock_q70": RegimeQuantile("shock_q70", "ret_abs_z", RegimeQuantileType.SHOCK, 0.70),
        "shock_q80": RegimeQuantile("shock_q80", "ret_abs_z", RegimeQuantileType.SHOCK, 0.80),
        "vel_q70": RegimeQuantile("vel_q70", "vel_abs_cost_units_h1", RegimeQuantileType.VELOCITY, 0.70),
        "vel_q80": RegimeQuantile("vel_q80", "vel_abs_cost_units_h1", RegimeQuantileType.VELOCITY, 0.80),
        "spread_q70": RegimeQuantile("spread_q70", "spread_z", RegimeQuantileType.SPREAD, 0.70),
        "tick_q30": RegimeQuantile("tick_q30", "tick_rate_z", RegimeQuantileType.TICK_RATE, 0.30),
    }

    # All valid regime gates and their quantile requirements
    _REGIMES = {
        "": "Always true (no filter)",
        "all": "Always true (synonym for empty)",
        "london": "London session: 07:00–11:59 UTC",
        "ny_overlap": "NY overlap: 13:00–16:59 UTC",
        "asia": "Asia session: 00:00–05:59 UTC",
        "low_cost_q30": "cost_est_pips <= cost_q30 (30th percentile of cost)",
        "low_cost_q50": "cost_est_pips <= cost_q50 (50th percentile of cost)",
        "high_range_q70": "range_pips >= rng_q70 (70th percentile of range)",
        "high_range_q80": "range_pips >= rng_q80 (80th percentile of range)",
        "high_abs_vel_q70": "vel_abs_cost_units_h1 >= vel_q70 (70th percentile of velocity)",
        "high_abs_vel_q80": "vel_abs_cost_units_h1 >= vel_q80 (80th percentile of velocity)",
    }

    @classmethod
    def quantiles(cls) -> dict[str, RegimeQuantile]:
        """Return all valid quantiles indexed by name."""
        return dict(cls._QUANTILES)

    @classmethod
    def quantile(cls, name: str) -> RegimeQuantile:
        """Get a specific quantile by name, or raise KeyError if not found."""
        if name not in cls._QUANTILES:
            raise KeyError(f"Unknown regime quantile: {name}. Valid: {list(cls._QUANTILES.keys())}")
        return cls._QUANTILES[name]

    @classmethod
    def is_valid_regime(cls, regime_name: str) -> bool:
        """Check if a regime name (or conjunction) is valid."""
        r = str(regime_name or "").strip().lower()
        if r in cls._REGIMES:
            return True
        if "_and_" in r:
            return all(cls.is_valid_regime(sub) for sub in r.split("_and_"))
        return False

    @classmethod
    def regime_description(cls, regime_name: str) -> str:
        """Get human-readable description of a regime."""
        r = str(regime_name or "").strip().lower()
        if r in cls._REGIMES:
            return cls._REGIMES[r]
        return "Unknown regime"

    @classmethod
    def validate_quantile_dict(cls, quantile_dict: dict[str, float]) -> None:
        """Validate that a computed quantile dict has all required keys."""
        required = set(cls._QUANTILES.keys())
        provided = set(quantile_dict.keys())
        if required != provided:
            missing = required - provided
            extra = provided - required
            msg = f"Quantile dict mismatch. "
            if missing:
                msg += f"Missing: {missing}. "
            if extra:
                msg += f"Extra: {extra}."
            raise ValueError(msg)
