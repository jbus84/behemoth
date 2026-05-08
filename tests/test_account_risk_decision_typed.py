"""Test AccountRiskDecision typed dataclass."""

from datetime import datetime, timezone

from src.behemoth.risk.account import AccountRiskDecision, evaluate_account_risk_decision


class TestAccountRiskDecisionTyping:
    """Verify AccountRiskDecision is used instead of raw dict."""

    def test_account_risk_decision_creation(self) -> None:
        """Can create AccountRiskDecision instances."""
        decision = AccountRiskDecision(
            enabled=True,
            allow_trading=False,
            block_reason="DAILY_LOSS_BUFFER_BREACH",
            trading_day_id="2026-05-08",
            day_start_balance=10000.0,
            current_equity=9500.0,
        )
        assert decision.enabled is True
        assert decision.allow_trading is False
        assert decision.block_reason == "DAILY_LOSS_BUFFER_BREACH"
        assert decision.trading_day_id == "2026-05-08"

    def test_evaluate_account_risk_decision_disabled_returns_typed(self) -> None:
        """evaluate_account_risk_decision returns AccountRiskDecision when disabled."""
        result = evaluate_account_risk_decision(
            profile=None,
            state_reader=None,
            symbol="EURUSD",
            now_utc=datetime.now(tz=timezone.utc),
            enabled=False,
        )
        assert isinstance(result, AccountRiskDecision)
        assert result.enabled is False
        assert result.allow_trading is True
        assert result.block_reason is None

    def test_evaluate_account_risk_decision_returns_typed(self) -> None:
        """evaluate_account_risk_decision returns AccountRiskDecision type."""
        result = evaluate_account_risk_decision(
            profile=None,
            state_reader=None,
            symbol="EURUSD",
            now_utc=datetime.now(tz=timezone.utc),
            enabled=True,
        )
        assert isinstance(result, AccountRiskDecision)
        # When disabled or profile is None, allow_trading defaults to True
        assert result.allow_trading is True
