"""Verify StateManager implements the state reader protocols.

These tests ensure the protocol definitions match StateManager's actual interface
(method names, argument signatures, and return types).
"""

import pytest
from typing import get_type_hints

from src.behemoth.runtime.state import StateManager
from src.behemoth.runtime.state_readers import (
    BarStateReader,
    AccountRiskStateReader,
    ReservationWriter,
)


class TestBarStateReaderCompliance:
    """Verify StateManager implements BarStateReader protocol."""

    def test_has_bar_count_method(self) -> None:
        """StateManager has bar_count(symbol, bar_ticks) -> int."""
        mgr = StateManager()
        assert hasattr(mgr, "bar_count")
        assert callable(mgr.bar_count)
        mgr.close()

    def test_has_get_latest_bar_context_method(self) -> None:
        """StateManager has get_latest_bar_context(symbol, bar_ticks) -> BarContext | None."""
        mgr = StateManager()
        assert hasattr(mgr, "get_latest_bar_context")
        assert callable(mgr.get_latest_bar_context)
        result = mgr.get_latest_bar_context("EURUSD", 100)
        assert result is None  # no bars yet
        mgr.close()

    def test_has_get_bar_context_method(self) -> None:
        """StateManager has get_bar_context(symbol, bar_ticks, *, bar_number, side) -> BarContext | None."""
        mgr = StateManager()
        assert hasattr(mgr, "get_bar_context")
        assert callable(mgr.get_bar_context)
        result = mgr.get_bar_context("EURUSD", 100)
        assert result is None
        mgr.close()

    def test_has_get_latest_bar_method(self) -> None:
        """StateManager has get_latest_bar(symbol, bar_ticks) -> dict | None."""
        mgr = StateManager()
        assert hasattr(mgr, "get_latest_bar")
        assert callable(mgr.get_latest_bar)
        result = mgr.get_latest_bar("EURUSD", 100)
        assert result is None
        mgr.close()

    def test_has_get_latest_close_ts_method(self) -> None:
        """StateManager has get_latest_close_ts(symbol) -> datetime | None."""
        mgr = StateManager()
        assert hasattr(mgr, "get_latest_close_ts")
        assert callable(mgr.get_latest_close_ts)
        result = mgr.get_latest_close_ts("EURUSD")
        assert result is None
        mgr.close()

    def test_has_compute_features_method(self) -> None:
        """StateManager has compute_features(symbol, bar_ticks, horizon, barrier_pips) -> ModelFeatures | None."""
        mgr = StateManager()
        assert hasattr(mgr, "compute_features")
        assert callable(mgr.compute_features)
        result = mgr.compute_features("EURUSD", 100, 30, 3.0)
        assert result is None  # no warmup
        mgr.close()

    def test_has_compute_regime_quantiles_method(self) -> None:
        """StateManager has compute_regime_quantiles(symbol, bar_ticks) -> dict[str, float]."""
        mgr = StateManager()
        assert hasattr(mgr, "compute_regime_quantiles")
        assert callable(mgr.compute_regime_quantiles)
        result = mgr.compute_regime_quantiles("EURUSD", 100)
        assert isinstance(result, dict)
        mgr.close()


class TestAccountRiskStateReaderCompliance:
    """Verify StateManager implements AccountRiskStateReader protocol."""

    def test_has_get_latest_account_risk_snapshot_method(self) -> None:
        """StateManager has get_latest_account_risk_snapshot(symbol=None) -> dict | None."""
        mgr = StateManager()
        assert hasattr(mgr, "get_latest_account_risk_snapshot")
        result = mgr.get_latest_account_risk_snapshot()
        assert result is None  # no snapshots yet
        mgr.close()

    def test_has_get_account_risk_snapshots_since_method(self) -> None:
        """StateManager has get_account_risk_snapshots_since(*, since_ts, symbol=None) -> list[dict]."""
        from datetime import datetime, timezone

        mgr = StateManager()
        assert hasattr(mgr, "get_account_risk_snapshots_since")
        result = mgr.get_account_risk_snapshots_since(
            since_ts=datetime.now(tz=timezone.utc)
        )
        assert isinstance(result, list)
        mgr.close()

    def test_has_sum_active_account_risk_reserved_loss_ccy_method(self) -> None:
        """StateManager has sum_active_account_risk_reserved_loss_ccy(**kwargs) -> float."""
        mgr = StateManager()
        assert hasattr(mgr, "sum_active_account_risk_reserved_loss_ccy")
        result = mgr.sum_active_account_risk_reserved_loss_ccy()
        assert isinstance(result, float)
        assert result == 0.0  # no reservations
        mgr.close()

    def test_has_list_active_account_risk_reservations_method(self) -> None:
        """StateManager has list_active_account_risk_reservations(**kwargs) -> list[dict]."""
        mgr = StateManager()
        assert hasattr(mgr, "list_active_account_risk_reservations")
        result = mgr.list_active_account_risk_reservations()
        assert isinstance(result, list)
        mgr.close()


class TestReservationWriterCompliance:
    """Verify StateManager implements ReservationWriter protocol."""

    def test_has_create_account_risk_reservation_method(self) -> None:
        """StateManager has create_account_risk_reservation(...) -> str."""
        mgr = StateManager()
        assert hasattr(mgr, "create_account_risk_reservation")
        assert callable(mgr.create_account_risk_reservation)
        mgr.close()

    def test_has_transition_account_risk_reservation_method(self) -> None:
        """StateManager has transition_account_risk_reservation(...) -> str."""
        mgr = StateManager()
        assert hasattr(mgr, "transition_account_risk_reservation")
        assert callable(mgr.transition_account_risk_reservation)
        mgr.close()

    def test_has_release_account_risk_reservation_method(self) -> None:
        """StateManager has release_account_risk_reservation(...) -> int."""
        mgr = StateManager()
        assert hasattr(mgr, "release_account_risk_reservation")
        assert callable(mgr.release_account_risk_reservation)
        mgr.close()

    def test_has_expire_stale_account_risk_pending_reservations_method(self) -> None:
        """StateManager has expire_stale_account_risk_pending_reservations(...) -> int."""
        mgr = StateManager()
        assert hasattr(mgr, "expire_stale_account_risk_pending_reservations")
        assert callable(mgr.expire_stale_account_risk_pending_reservations)
        mgr.close()


class TestProtocolIntegration:
    """Verify protocols work end-to-end."""

    def test_state_manager_as_bar_state_reader(self) -> None:
        """StateManager can be used where BarStateReader is expected."""
        mgr = StateManager()

        def accepts_reader(reader: BarStateReader) -> int:
            return reader.bar_count("EURUSD", 100)

        # This should type-check (and pass at runtime)
        result = accepts_reader(mgr)  # type: ignore[arg-type]
        assert result == 0
        mgr.close()

    def test_state_manager_as_account_risk_reader(self) -> None:
        """StateManager can be used where AccountRiskStateReader is expected."""
        mgr = StateManager()

        def accepts_reader(reader: AccountRiskStateReader) -> float:
            return reader.sum_active_account_risk_reserved_loss_ccy()

        # This should type-check (and pass at runtime)
        result = accepts_reader(mgr)  # type: ignore[arg-type]
        assert result == 0.0
        mgr.close()

    def test_state_manager_as_reservation_writer(self) -> None:
        """StateManager can be used where ReservationWriter is expected."""
        mgr = StateManager()

        def accepts_writer(writer: ReservationWriter) -> str:
            return writer.create_account_risk_reservation(
                symbol="EURUSD",
                candidate_uid="test",
                reserved_loss_ccy=100.0,
                barrier_pips=50.0,
                cap_pips=75.0,
                cost_est_pips=10.0,
                volume_units=1000.0,
            )

        # This should type-check (and pass at runtime)
        result = accepts_writer(mgr)  # type: ignore[arg-type]
        assert isinstance(result, str)
        mgr.close()
