"""Account risk decision engine independent of FastAPI endpoints."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from src.behemoth.risk.account import (
    AccountRiskProfile,
    evaluate_account_risk_limits,
    trading_day_id,
)
from src.behemoth.runtime.state_queries import AccountRiskStateReader

DISABLED_ACCOUNT_RISK_EVAL: dict[str, Any] = {
    "enabled": False,
    "profile_id": None,
    "allow_trading": True,
    "block_reason": None,
    "snapshot_available": False,
    "trading_day_id": None,
}


@dataclass(frozen=True)
class AccountRiskDecisionEngine:
    """Evaluate account-level risk limits from read-only runtime state."""

    profile: AccountRiskProfile | None
    state: AccountRiskStateReader | None
    enabled: bool

    def evaluate(self, symbol: str, now_utc: datetime) -> dict[str, Any]:
        if (not self.enabled) or self.profile is None or self.state is None:
            return dict(DISABLED_ACCOUNT_RISK_EVAL)

        sym = str(symbol).upper().strip()
        prof = self.profile
        latest = self.state.get_latest_account_risk_snapshot(sym)
        if latest is None:
            latest = self.state.get_latest_account_risk_snapshot(None)

        day_id = trading_day_id(
            now_utc,
            timezone_name=prof.daily_reset_timezone,
            reset_hour=prof.daily_reset_hour,
            reset_minute=prof.daily_reset_minute,
        )
        if latest is None:
            eval_out = evaluate_account_risk_limits(
                prof,
                balance=None,
                equity=None,
                day_start_balance=None,
            )
            eval_out["enabled"] = True
            eval_out["profile_id"] = prof.profile_id
            eval_out["trading_day_id"] = day_id
            return eval_out

        since = _as_utc(now_utc) - timedelta(days=3)
        snaps = self.state.get_account_risk_snapshots_since(since_ts=since, symbol=sym)
        if not snaps:
            snaps = self.state.get_account_risk_snapshots_since(since_ts=since, symbol=None)

        day_start_balance = self._day_start_balance(snaps, latest, now_utc)
        eval_out = evaluate_account_risk_limits(
            prof,
            balance=float(latest["balance"]),
            equity=float(latest["equity"]),
            day_start_balance=day_start_balance,
        )
        eval_out["enabled"] = True
        eval_out["profile_id"] = prof.profile_id
        eval_out["trading_day_id"] = day_id
        return eval_out

    def _day_start_balance(
        self,
        snapshots: list[dict],
        latest: dict,
        now_utc: datetime,
    ) -> float:
        assert self.profile is not None
        prof = self.profile
        day_id = trading_day_id(
            now_utc,
            timezone_name=prof.daily_reset_timezone,
            reset_hour=prof.daily_reset_hour,
            reset_minute=prof.daily_reset_minute,
        )
        for row in snapshots:
            row_day = trading_day_id(
                row["snapshot_ts"],
                timezone_name=prof.daily_reset_timezone,
                reset_hour=prof.daily_reset_hour,
                reset_minute=prof.daily_reset_minute,
            )
            if row_day == day_id:
                return float(row["balance"])
        return float(latest["balance"])


def _as_utc(ts: datetime) -> datetime:
    if ts.tzinfo is None:
        return ts.replace(tzinfo=timezone.utc)
    return ts.astimezone(timezone.utc)
