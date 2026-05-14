"""Test BarTouchSemantics — explicit tie-breaking logic."""

from src.behemoth.runtime.bar_touch_semantics import (
    BarTouchResult,
    BarTouchSemantics,
)


class TestBarTouchSemantics:
    """Verify hl_first tie-breaking semantics are explicit and correct."""

    def test_no_touch_returns_no_decision(self) -> None:
        """When neither barrier touched, result has no decision."""
        result = BarTouchSemantics.evaluate(
            upper_touched=False,
            lower_touched=False,
            hl_first=0.0,
        )
        assert result.upper_touched is False
        assert result.lower_touched is False
        assert result.decided_side is None
        assert result.expiry_reason is None

    def test_upper_touch_only_decides_buy(self) -> None:
        """Upper touch alone triggers BUY regardless of hl_first."""
        result = BarTouchSemantics.evaluate(
            upper_touched=True,
            lower_touched=False,
            hl_first=0.0,
        )
        assert result.upper_touched is True
        assert result.lower_touched is False
        assert result.decided_side == "BUY"
        assert result.expiry_reason is None

    def test_lower_touch_only_decides_sell(self) -> None:
        """Lower touch alone triggers SELL regardless of hl_first."""
        result = BarTouchSemantics.evaluate(
            upper_touched=False,
            lower_touched=True,
            hl_first=0.0,
        )
        assert result.upper_touched is False
        assert result.lower_touched is True
        assert result.decided_side == "SELL"
        assert result.expiry_reason is None

    def test_both_touch_positive_hl_first_decides_buy(self) -> None:
        """Both touched with hl_first > 0 (high first) triggers BUY."""
        result = BarTouchSemantics.evaluate(
            upper_touched=True,
            lower_touched=True,
            hl_first=1.5,
        )
        assert result.upper_touched is True
        assert result.lower_touched is True
        assert result.decided_side == "BUY"
        assert result.expiry_reason is None

    def test_both_touch_negative_hl_first_decides_sell(self) -> None:
        """Both touched with hl_first < 0 (low first) triggers SELL."""
        result = BarTouchSemantics.evaluate(
            upper_touched=True,
            lower_touched=True,
            hl_first=-2.0,
        )
        assert result.upper_touched is True
        assert result.lower_touched is True
        assert result.decided_side == "SELL"
        assert result.expiry_reason is None

    def test_both_touch_zero_hl_first_expires(self) -> None:
        """Both touched with hl_first == 0 (simultaneous) expires immediately."""
        result = BarTouchSemantics.evaluate(
            upper_touched=True,
            lower_touched=True,
            hl_first=0.0,
        )
        assert result.upper_touched is True
        assert result.lower_touched is True
        assert result.decided_side is None
        assert result.expiry_reason == "simultaneous_touch_no_hl_first"

    def test_result_is_immutable(self) -> None:
        """BarTouchResult is frozen/immutable."""
        result = BarTouchResult(True, False, "BUY", None)
        try:
            result.decided_side = "SELL"
            raise AssertionError("Should not be able to modify frozen dataclass")
        except AttributeError:
            pass  # Expected
