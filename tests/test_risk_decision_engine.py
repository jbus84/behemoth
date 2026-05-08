from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from src.behemoth.risk.account import (
    evaluate_account_risk_decision,
    load_account_risk_profile,
)


class FakeRiskState:
    def __init__(self) -> None:
        self.latest = {
            "snapshot_ts": datetime(2026, 3, 6, 12, 0, tzinfo=timezone.utc),
            "symbol": "EURUSD",
            "balance": 10000.0,
            "equity": 9550.0,
        }
        self.snapshots = [
            {
                "snapshot_ts": datetime(2026, 3, 6, 0, 1, tzinfo=timezone.utc),
                "symbol": "EURUSD",
                "balance": 10000.0,
                "equity": 10000.0,
            }
        ]

    def get_latest_account_risk_snapshot(self, symbol: str | None = None) -> dict | None:
        return self.latest

    def get_account_risk_snapshots_since(
        self,
        *,
        since_ts: datetime,
        symbol: str | None = None,
    ) -> list[dict]:
        return [row for row in self.snapshots if row["snapshot_ts"] >= since_ts]

    def sum_active_account_risk_reserved_loss_ccy(self, **_kwargs) -> float:
        return 0.0

    def list_active_account_risk_reservations(self, **_kwargs) -> list[dict]:
        return []


def test_account_risk_decision_engine_evaluates_from_state_reader() -> None:
    profile = load_account_risk_profile(
        Path("configs/research/governance/account_risk/account_risk_rules.yaml")
    )

    out = evaluate_account_risk_decision(
        profile=profile,
        state_reader=FakeRiskState(),
        symbol="EURUSD",
        now_utc=datetime(2026, 3, 6, 12, 0, tzinfo=timezone.utc),
        enabled=True,
    )

    assert out["enabled"] is True
    assert out["allow_trading"] is False
    assert out["block_reason"] == "ACCOUNT_RISK_DAILY_LOSS_BUFFER_BREACH"
    assert out["trading_day_id"] == "2026-03-06"


def test_account_risk_decision_engine_disabled_allows_trading() -> None:
    profile = load_account_risk_profile(
        Path("configs/research/governance/account_risk/account_risk_rules.yaml")
    )

    out = evaluate_account_risk_decision(
        profile=profile,
        state_reader=FakeRiskState(),
        symbol="EURUSD",
        now_utc=datetime.now(tz=timezone.utc) + timedelta(seconds=1),
        enabled=False,
    )

    assert out["enabled"] is False
    assert out["allow_trading"] is True
