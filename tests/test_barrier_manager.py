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
