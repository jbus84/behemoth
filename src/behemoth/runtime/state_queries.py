"""Read-only runtime state query interfaces."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol

from src.behemoth.core.schemas import BarContext, ModelFeatures


class BarStateReader(Protocol):
    """Read-only Tick Bar and Feature Set state needed by runtime consumers."""

    def bar_count(self, symbol: str, bar_ticks: int) -> int:
        ...

    def get_bar_context(
        self,
        symbol: str,
        bar_ticks: int,
        *,
        bar_number: int | None = None,
        side: str | None = None,
    ) -> BarContext | None:
        ...

    def compute_features(
        self,
        symbol: str,
        bar_ticks: int,
        horizon: int,
        barrier_pips: float,
    ) -> ModelFeatures | None:
        ...


class AccountRiskStateReader(Protocol):
    """Read-only account risk state needed by risk decision modules."""

    def get_latest_account_risk_snapshot(self, symbol: str | None = None) -> dict | None:
        ...

    def get_account_risk_snapshots_since(
        self,
        *,
        since_ts: datetime,
        symbol: str | None = None,
    ) -> list[dict]:
        ...

    def sum_active_account_risk_reserved_loss_ccy(
        self,
        *,
        symbol: str | None = None,
        include_pending: bool = True,
        include_open: bool = True,
    ) -> float:
        ...

    def list_active_account_risk_reservations(self, *, symbol: str | None = None) -> list[dict]:
        ...


class RuntimeStateReader(BarStateReader, AccountRiskStateReader, Protocol):
    """Read-only StateManager query surface.

    Consumers should depend on this protocol, not directly on StateManager.
    This allows testing without running the full DB-backed StateManager.
    """
