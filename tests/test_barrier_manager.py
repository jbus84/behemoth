"""Tests for BarrierManager barrier detection parity with _oco_precompute."""
from __future__ import annotations

import pytest

from src.behemoth.runtime.barrier_manager import BarrierManager


class TestRegisterScan:
    def test_register_creates_scanning_record(self):
        mgr = BarrierManager()
        scan_id = mgr.register_scan(
            symbol="GBPUSD",
            candidate_uid="oco|GBPUSD|100|h6|abc",
            signal_bar_idx=10,
            ref_price=1.29500,
            barrier_pips=2.0,
            horizon=6,
            pip_size=0.0001,
            pred_prob=0.625,
            threshold=0.599,
            model_month="2026-02",
            reservation_id="res-001",
            run_id="test",
        )
        assert scan_id is not None
        assert mgr.has_active_scan("GBPUSD", "oco|GBPUSD|100|h6|abc")

    def test_register_sets_correct_barriers(self):
        mgr = BarrierManager()
        scan_id = mgr.register_scan(
            symbol="GBPUSD",
            candidate_uid="oco|GBPUSD|100|h6|abc",
            signal_bar_idx=10,
            ref_price=1.29500,
            barrier_pips=2.0,
            horizon=6,
            pip_size=0.0001,
            pred_prob=0.625,
            threshold=0.599,
            model_month="2026-02",
            reservation_id=None,
            run_id="test",
        )
        scan = mgr.get_scan(scan_id)
        assert scan["upper_barrier"] == pytest.approx(1.29500 + 2.0 * 0.0001)
        assert scan["lower_barrier"] == pytest.approx(1.29500 - 2.0 * 0.0001)
        assert scan["status"] == "SCANNING"
        assert scan["scan_bars_remaining"] == 6

    def test_has_active_scan_false_when_none(self):
        mgr = BarrierManager()
        assert not mgr.has_active_scan("GBPUSD", "oco|GBPUSD|100|h6|abc")


class TestEvaluateBar:
    def _make_manager_with_scan(self, ref_price=1.29500, barrier_pips=2.0, horizon=6):
        mgr = BarrierManager()
        scan_id = mgr.register_scan(
            symbol="GBPUSD",
            candidate_uid="oco|GBPUSD|100|h6|abc",
            signal_bar_idx=10,
            ref_price=ref_price,
            barrier_pips=barrier_pips,
            horizon=horizon,
            pip_size=0.0001,
            pred_prob=0.625,
            threshold=0.599,
            model_month="2026-02",
            reservation_id="res-001",
            run_id="test",
        )
        return mgr, scan_id

    def test_upper_barrier_touch_produces_buy(self):
        """Bar high >= upper_barrier -> BUY action."""
        mgr, scan_id = self._make_manager_with_scan()
        # upper = 1.29500 + 2.0 * 0.0001 = 1.29520
        actions = mgr.evaluate_bar(
            symbol="GBPUSD",
            bar_ticks=100,
            bar_high=1.29525,
            bar_low=1.29490,   # > lower (1.29480)
            bar_hl_first=1.0,
            current_bar_idx=11,
        )
        assert len(actions) == 1
        assert actions[0]["type"] == "OPEN_MARKET"
        assert actions[0]["side"] == "BUY"
        scan = mgr.get_scan(scan_id)
        assert scan["status"] == "HOLDING"
        assert scan["touch_step"] == 1
        assert scan["hold_bars_remaining"] == 6

    def test_lower_barrier_touch_produces_sell(self):
        """Bar low <= lower_barrier -> SELL action."""
        mgr, scan_id = self._make_manager_with_scan()
        actions = mgr.evaluate_bar(
            symbol="GBPUSD",
            bar_ticks=100,
            bar_high=1.29510,
            bar_low=1.29475,   # <= 1.29480
            bar_hl_first=-1.0,
            current_bar_idx=11,
        )
        assert len(actions) == 1
        assert actions[0]["type"] == "OPEN_MARKET"
        assert actions[0]["side"] == "SELL"

    def test_no_touch_decrements_scan_bars(self):
        """No barrier touched -> no actions, scan_bars_remaining decremented."""
        mgr, scan_id = self._make_manager_with_scan()
        actions = mgr.evaluate_bar(
            symbol="GBPUSD",
            bar_ticks=100,
            bar_high=1.29510,
            bar_low=1.29490,
            bar_hl_first=0.0,
            current_bar_idx=11,
        )
        assert len(actions) == 0
        scan = mgr.get_scan(scan_id)
        assert scan["status"] == "SCANNING"
        assert scan["scan_bars_remaining"] == 5

    def test_scan_expires_after_horizon_bars_no_touch(self):
        """After horizon bars with no touch -> EXPIRED."""
        mgr, scan_id = self._make_manager_with_scan(horizon=2)
        mgr.evaluate_bar("GBPUSD", 100, 1.29510, 1.29490, 0.0, 11)
        actions = mgr.evaluate_bar("GBPUSD", 100, 1.29510, 1.29490, 0.0, 12)
        assert len(actions) == 0
        scan = mgr.get_scan(scan_id)
        assert scan["status"] == "EXPIRED"
        assert not mgr.has_active_scan("GBPUSD", "oco|GBPUSD|100|h6|abc")


class TestTieBreaking:
    def _make_manager_with_scan(self, **kwargs):
        defaults = dict(ref_price=1.29500, barrier_pips=2.0, horizon=6)
        defaults.update(kwargs)
        mgr = BarrierManager()
        scan_id = mgr.register_scan(
            symbol="GBPUSD",
            candidate_uid="oco|GBPUSD|100|h6|abc",
            signal_bar_idx=10,
            pip_size=0.0001,
            pred_prob=0.625,
            threshold=0.599,
            model_month="2026-02",
            reservation_id="res-001",
            run_id="test",
            **defaults,
        )
        return mgr, scan_id

    def test_both_touched_hl_first_positive_is_buy(self):
        mgr, scan_id = self._make_manager_with_scan()
        actions = mgr.evaluate_bar("GBPUSD", 100, 1.29530, 1.29470, 1.0, 11)
        assert len(actions) == 1
        assert actions[0]["side"] == "BUY"

    def test_both_touched_hl_first_negative_is_sell(self):
        mgr, scan_id = self._make_manager_with_scan()
        actions = mgr.evaluate_bar("GBPUSD", 100, 1.29530, 1.29470, -1.0, 11)
        assert len(actions) == 1
        assert actions[0]["side"] == "SELL"

    def test_both_touched_hl_first_zero_no_decision(self):
        mgr, scan_id = self._make_manager_with_scan()
        actions = mgr.evaluate_bar("GBPUSD", 100, 1.29530, 1.29470, 0.0, 11)
        assert len(actions) == 0
        scan = mgr.get_scan(scan_id)
        assert scan["status"] == "SCANNING"
        assert scan["scan_bars_remaining"] == 5


class TestHoldCompletion:
    def test_hold_countdown_produces_close_action(self):
        mgr = BarrierManager()
        scan_id = mgr.register_scan(
            symbol="GBPUSD",
            candidate_uid="oco|GBPUSD|100|h6|abc",
            signal_bar_idx=10,
            ref_price=1.29500,
            barrier_pips=2.0,
            horizon=3,
            pip_size=0.0001,
            pred_prob=0.625,
            threshold=0.599,
            model_month="2026-02",
            reservation_id=None,
            run_id="test",
        )
        mgr.set_broker_pos_id(scan_id, "broker-123")
        actions = mgr.evaluate_bar("GBPUSD", 100, 1.29530, 1.29490, 1.0, 11)
        assert len(actions) == 1
        assert actions[0]["type"] == "OPEN_MARKET"

        actions = mgr.evaluate_bar("GBPUSD", 100, 1.29510, 1.29490, 0.0, 12)
        assert len(actions) == 0
        actions = mgr.evaluate_bar("GBPUSD", 100, 1.29510, 1.29490, 0.0, 13)
        assert len(actions) == 0
        actions = mgr.evaluate_bar("GBPUSD", 100, 1.29510, 1.29490, 0.0, 14)
        assert len(actions) == 1
        assert actions[0]["type"] == "CLOSE_MARKET"
        assert actions[0]["broker_pos_id"] == "broker-123"
        scan = mgr.get_scan(scan_id)
        assert scan["status"] == "COMPLETED"
        assert not mgr.has_active_scan("GBPUSD", "oco|GBPUSD|100|h6|abc")

    def test_lifecycle_blocking_during_scan_and_hold(self):
        mgr = BarrierManager()
        scan_id = mgr.register_scan(
            symbol="GBPUSD",
            candidate_uid="oco|GBPUSD|100|h6|abc",
            signal_bar_idx=10,
            ref_price=1.29500,
            barrier_pips=2.0,
            horizon=2,
            pip_size=0.0001,
            pred_prob=0.625,
            threshold=0.599,
            model_month="2026-02",
            reservation_id=None,
            run_id="test",
        )
        assert mgr.has_active_scan("GBPUSD", "oco|GBPUSD|100|h6|abc")
        mgr.evaluate_bar("GBPUSD", 100, 1.29530, 1.29490, 1.0, 11)
        assert mgr.has_active_scan("GBPUSD", "oco|GBPUSD|100|h6|abc")
        mgr.evaluate_bar("GBPUSD", 100, 1.29510, 1.29490, 0.0, 12)
        assert mgr.has_active_scan("GBPUSD", "oco|GBPUSD|100|h6|abc")
        mgr.evaluate_bar("GBPUSD", 100, 1.29510, 1.29490, 0.0, 13)
        assert not mgr.has_active_scan("GBPUSD", "oco|GBPUSD|100|h6|abc")
