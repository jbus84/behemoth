"""Test RegimeQuantileContract — formalized regime quantile protocol."""

import pytest

from src.behemoth.core.regime_quantile_contract import (
    RegimeQuantile,
    RegimeQuantileContract,
    RegimeQuantileType,
)


class TestRegimeQuantile:
    """Test individual RegimeQuantile definitions."""

    def test_regime_quantile_valid_percentile(self) -> None:
        """Valid percentiles are accepted."""
        q = RegimeQuantile("cost_q30", "cost_est_pips", RegimeQuantileType.COST, 0.30)
        assert q.name == "cost_q30"
        assert q.percentile == 0.30

    def test_regime_quantile_rejects_invalid_percentile(self) -> None:
        """Percentiles outside [0, 1] are rejected."""
        with pytest.raises(ValueError, match="Percentile must be in"):
            RegimeQuantile("cost_q200", "cost_est_pips", RegimeQuantileType.COST, 2.0)

    def test_regime_quantile_is_frozen(self) -> None:
        """RegimeQuantile is immutable."""
        q = RegimeQuantile("cost_q30", "cost_est_pips", RegimeQuantileType.COST, 0.30)
        with pytest.raises(AttributeError):
            q.name = "different"


class TestRegimeQuantileContract:
    """Test the regime quantile contract and validation."""

    def test_quantiles_returns_all_valid_quantiles(self) -> None:
        """Contract.quantiles() returns all 11 valid quantile definitions."""
        quantiles = RegimeQuantileContract.quantiles()
        assert len(quantiles) == 11
        assert "cost_q30" in quantiles
        assert "vel_q80" in quantiles
        assert "tick_q30" in quantiles

    def test_quantile_returns_specific_quantile(self) -> None:
        """Contract.quantile() retrieves a specific quantile by name."""
        q = RegimeQuantileContract.quantile("cost_q30")
        assert q.name == "cost_q30"
        assert q.percentile == 0.30
        assert q.quantile_type == RegimeQuantileType.COST

    def test_quantile_raises_on_unknown_name(self) -> None:
        """Contract.quantile() raises KeyError for unknown names."""
        with pytest.raises(KeyError, match="Unknown regime quantile"):
            RegimeQuantileContract.quantile("unknown_q99")

    def test_is_valid_regime_accepts_empty_and_all(self) -> None:
        """Empty string and 'all' are valid regimes."""
        assert RegimeQuantileContract.is_valid_regime("")
        assert RegimeQuantileContract.is_valid_regime("all")

    def test_is_valid_regime_accepts_time_based_regimes(self) -> None:
        """Time-based regime names are valid."""
        assert RegimeQuantileContract.is_valid_regime("london")
        assert RegimeQuantileContract.is_valid_regime("ny_overlap")
        assert RegimeQuantileContract.is_valid_regime("asia")

    def test_is_valid_regime_accepts_quantile_regimes(self) -> None:
        """Quantile-based regime names are valid."""
        assert RegimeQuantileContract.is_valid_regime("low_cost_q30")
        assert RegimeQuantileContract.is_valid_regime("low_cost_q50")
        assert RegimeQuantileContract.is_valid_regime("high_range_q70")
        assert RegimeQuantileContract.is_valid_regime("high_range_q80")
        assert RegimeQuantileContract.is_valid_regime("high_abs_vel_q70")
        assert RegimeQuantileContract.is_valid_regime("high_abs_vel_q80")

    def test_is_valid_regime_accepts_conjunctions(self) -> None:
        """Conjunctions (A_and_B) are valid if both A and B are valid."""
        assert RegimeQuantileContract.is_valid_regime("london_and_low_cost_q30")
        assert RegimeQuantileContract.is_valid_regime("asia_and_high_range_q70")
        assert RegimeQuantileContract.is_valid_regime("london_and_ny_overlap_and_low_cost_q50")

    def test_is_valid_regime_rejects_unknown_regimes(self) -> None:
        """Unknown regime names are not valid."""
        assert not RegimeQuantileContract.is_valid_regime("unknown_regime")
        assert not RegimeQuantileContract.is_valid_regime("high_cost_q99")

    def test_is_valid_regime_rejects_conjunction_with_invalid_part(self) -> None:
        """Conjunctions are invalid if any part is unknown."""
        assert not RegimeQuantileContract.is_valid_regime("london_and_unknown_regime")
        assert not RegimeQuantileContract.is_valid_regime("high_cost_q99_and_london")

    def test_is_valid_regime_case_insensitive(self) -> None:
        """Regime names are case-insensitive."""
        assert RegimeQuantileContract.is_valid_regime("LONDON")
        assert RegimeQuantileContract.is_valid_regime("Low_Cost_Q30")

    def test_regime_description_returns_text_for_valid_regime(self) -> None:
        """Contract.regime_description() returns human-readable text."""
        desc = RegimeQuantileContract.regime_description("london")
        assert "London session" in desc or "london" in desc.lower()

    def test_regime_description_returns_unknown_for_invalid(self) -> None:
        """Contract.regime_description() returns 'Unknown regime' for invalid names."""
        desc = RegimeQuantileContract.regime_description("fake_regime")
        assert "Unknown" in desc

    def test_validate_quantile_dict_accepts_valid_dict(self) -> None:
        """Validation passes for a dict with all required quantiles."""
        valid_dict = {
            "cost_q30": 5.0,
            "cost_q50": 7.5,
            "rng_q70": 10.0,
            "rng_q80": 12.5,
            "shock_q60": 1.5,
            "shock_q70": 2.0,
            "shock_q80": 2.5,
            "vel_q70": 3.0,
            "vel_q80": 3.5,
            "spread_q70": 2.0,
            "tick_q30": 100.0,
        }
        # Should not raise
        RegimeQuantileContract.validate_quantile_dict(valid_dict)

    def test_validate_quantile_dict_rejects_missing_keys(self) -> None:
        """Validation fails if required quantiles are missing."""
        incomplete_dict = {
            "cost_q30": 5.0,
            "cost_q50": 7.5,
            # Missing: rng_q70, rng_q80, shock_q60, shock_q70, shock_q80, vel_q70, vel_q80, spread_q70, tick_q30
        }
        with pytest.raises(ValueError, match="Missing"):
            RegimeQuantileContract.validate_quantile_dict(incomplete_dict)

    def test_validate_quantile_dict_rejects_extra_keys(self) -> None:
        """Validation fails if extra unknown quantiles are present."""
        extra_dict = {
            "cost_q30": 5.0,
            "cost_q50": 7.5,
            "rng_q70": 10.0,
            "rng_q80": 12.5,
            "shock_q60": 1.5,
            "shock_q70": 2.0,
            "shock_q80": 2.5,
            "vel_q70": 3.0,
            "vel_q80": 3.5,
            "spread_q70": 2.0,
            "tick_q30": 100.0,
            "unknown_q99": 999.0,  # Extra key
        }
        with pytest.raises(ValueError, match="Extra"):
            RegimeQuantileContract.validate_quantile_dict(extra_dict)

    def test_quantile_types_are_correct(self) -> None:
        """Verify that quantiles are assigned to correct types."""
        cost_quantiles = [q for q in RegimeQuantileContract.quantiles().values() if q.quantile_type == RegimeQuantileType.COST]
        assert len(cost_quantiles) == 2  # cost_q30, cost_q50

        range_quantiles = [q for q in RegimeQuantileContract.quantiles().values() if q.quantile_type == RegimeQuantileType.RANGE]
        assert len(range_quantiles) == 2  # rng_q70, rng_q80

        velocity_quantiles = [q for q in RegimeQuantileContract.quantiles().values() if q.quantile_type == RegimeQuantileType.VELOCITY]
        assert len(velocity_quantiles) == 2  # vel_q70, vel_q80

    def test_all_quantiles_have_valid_percentiles(self) -> None:
        """All quantiles have valid percentiles in [0, 1]."""
        for q in RegimeQuantileContract.quantiles().values():
            assert 0.0 <= q.percentile <= 1.0
