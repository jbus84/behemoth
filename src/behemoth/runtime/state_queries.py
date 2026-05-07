"""Read-only runtime state query interfaces."""

from __future__ import annotations

from dataclasses import dataclass
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
    """Read-only StateManager query surface."""


@dataclass(frozen=True)
class StateQueryView:
    """Adapter exposing StateManager's read-only interface without DuckDB access."""

    state: RuntimeStateReader

    def bar_count(self, symbol: str, bar_ticks: int) -> int:
        return self.state.bar_count(symbol, bar_ticks)

    def get_bar_context(
        self,
        symbol: str,
        bar_ticks: int,
        *,
        bar_number: int | None = None,
        side: str | None = None,
    ) -> BarContext | None:
        return self.state.get_bar_context(
            symbol,
            bar_ticks,
            bar_number=bar_number,
            side=side,
        )

    def compute_features(
        self,
        symbol: str,
        bar_ticks: int,
        horizon: int,
        barrier_pips: float,
    ) -> ModelFeatures | None:
        return self.state.compute_features(symbol, bar_ticks, horizon, barrier_pips)

    def get_latest_account_risk_snapshot(self, symbol: str | None = None) -> dict | None:
        return self.state.get_latest_account_risk_snapshot(symbol)

    def get_account_risk_snapshots_since(
        self,
        *,
        since_ts: datetime,
        symbol: str | None = None,
    ) -> list[dict]:
        return self.state.get_account_risk_snapshots_since(since_ts=since_ts, symbol=symbol)

    def sum_active_account_risk_reserved_loss_ccy(
        self,
        *,
        symbol: str | None = None,
        include_pending: bool = True,
        include_open: bool = True,
    ) -> float:
        return self.state.sum_active_account_risk_reserved_loss_ccy(
            symbol=symbol,
            include_pending=include_pending,
            include_open=include_open,
        )

    def list_active_account_risk_reservations(self, *, symbol: str | None = None) -> list[dict]:
        return self.state.list_active_account_risk_reservations(symbol=symbol)
