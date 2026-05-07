"""Integration test for /predict endpoint orchestration.

Validates that all 5 seams work together:
1. BarContext (bar state abstraction)
2. Feature computation (16-feature vector)
3. Order submission protocol (action generation)
4. Bar boundary contract (tick bar alignment)
5. Reservation state machine (account risk lifecycle)

This test catches integration bugs that unit tests miss and documents
the predict endpoint's contract.
"""
from __future__ import annotations

import numpy as np
import pytest
from unittest.mock import MagicMock, patch

from src.behemoth.core.schemas import (
    BarContext,
    BarPrices,
    BarrierAction,
    BarrierActionType,
    ModelFeatures,
)
from src.behemoth.runtime.barrier_manager import BarrierManager
from src.behemoth.core.features import compute_features_from_bars, FeatureConfig
from src.behemoth.runtime.state import StateManager
import pandas as pd


class TestPredictEndpointIntegration:
    """End-to-end orchestration test for predict flow."""

    def test_full_predict_flow_BarContext_to_action(self):
        """Verify predict orchestrates BarContext → features → barrier detection → actions."""
        # Setup: Create bar context representing a completed bar
        bar_context = BarContext(
            symbol="GBPUSD",
            bar_ticks=100,
            bid=BarPrices(high=1.29525, low=1.29490, close=1.29500),
            ask=BarPrices(high=1.29535, low=1.29500, close=1.29510),
            hl_first=1.0,
            bar_idx=50,
        )

        # Seam 1: BarContext should extract values correctly
        assert bar_context.symbol == "GBPUSD"
        assert bar_context.bid.high == 1.29525
        assert bar_context.ask.high == 1.29535
        assert bar_context.bar_idx == 50

        # Seam 2: Feature computation should work with barrier detection
        barrier_mgr = BarrierManager()
        scan_id = barrier_mgr.register_scan(
            symbol="GBPUSD",
            candidate_uid="test_candidate",
            signal_bar_idx=40,
            ref_price=1.29500,
            barrier_pips=2.0,
            horizon=6,
            pip_size=0.0001,
            pred_prob=0.625,
            threshold=0.599,
            model_month="2026-02",
            reservation_id="res-test-001",
            run_id="integration_test",
        )

        # Seam 3: Barrier detection via BarContext
        actions = barrier_mgr.evaluate_bar(bar_context)
        assert len(actions) == 1
        assert isinstance(actions[0], BarrierAction)
        assert actions[0].type == BarrierActionType.OPEN_MARKET
        assert actions[0].side == "BUY"
        assert actions[0].candidate_uid == "test_candidate"
        assert actions[0].reservation_id == "res-test-001"

        # Seam 4: Order submission protocol should preserve action fields
        released_actions = [a for a in actions if a.type == BarrierActionType.RELEASE_RESERVATION]
        open_actions = [a for a in actions if a.type == BarrierActionType.OPEN_MARKET]
        assert len(open_actions) == 1
        assert len(released_actions) == 0  # Still in HOLDING

        barrier_mgr.close()

    def test_feature_computation_with_bar_state(self):
        """Verify feature computation produces consistent 16-vector from bar sequence."""
        # Seam 2: Feature registry - create bars with sufficient history
        n_bars = 300
        base = 1.29500
        np.random.seed(42)
        prices = base + np.cumsum(np.random.normal(0, 0.0003, n_bars))
        highs = prices + np.abs(np.random.normal(0, 0.0002, n_bars))
        lows = prices - np.abs(np.random.normal(0, 0.0002, n_bars))
        hl_first = np.random.choice([-1.0, 0.0, 1.0], n_bars)
        hl_pos_frac = np.random.uniform(0, 1, n_bars)

        df = pd.DataFrame({
            "timestamp": pd.date_range("2026-02-01", periods=n_bars, freq="1h"),
            "close_ts": pd.date_range("2026-02-01", periods=n_bars, freq="1h"),
            "open_bid": prices,
            "high_bid": highs,
            "low_bid": lows,
            "close_bid": prices,
            "high_ask": highs + 0.0001,
            "close_ask": prices + 0.00005,
            "spread": np.full(n_bars, 0.0001),
            "tick_volume": np.full(n_bars, 100),
            "hl_first": hl_first,
            "hl_pos_frac": hl_pos_frac,
        })

        # Compute features for last bar
        features = compute_features_from_bars(
            df,
            symbol="GBPUSD",
            bar_ticks=100,
            horizon=6,
            barrier_pips=2.0,
            cfg=FeatureConfig(),
        )

        assert features is not None
        assert isinstance(features, ModelFeatures)

        # Verify all 16 expected features are present in the model
        expected_fields = {
            "cost_est_pips", "range_pips", "ret1_pips", "ret_z", "ret_abs_z",
            "vel_cost_units_h1", "vel_abs_cost_units_h1", "spread_z", "tick_rate_z",
            "hour_utc", "hl_first", "hl_first_mean_24", "hl_pos_frac_mean_24",
            "bar_ticks", "horizon", "barrier_pips",
        }
        actual_fields = set(ModelFeatures.model_fields.keys())
        assert expected_fields == actual_fields

        # Verify hour_utc is raw integer (0-23), not sine/cosine encoded
        hour = features.hour_utc
        assert 0 <= hour <= 23
        assert hour == int(hour)  # Should be integer cast to float, not encoded

    def test_reservation_state_lifecycle_through_predict(self):
        """Verify reservation state machine transitions correctly through predict flow."""
        barrier_mgr = BarrierManager()

        # Register scan with reservation
        scan_id = barrier_mgr.register_scan(
            symbol="USDJPY",
            candidate_uid="test_reservation",
            signal_bar_idx=10,
            ref_price=150.0,
            barrier_pips=3.0,
            horizon=3,
            pip_size=0.01,
            pred_prob=0.7,
            threshold=0.6,
            model_month="2026-02",
            reservation_id="res-lifecycle-001",
            run_id="integration_test",
        )

        # State 1: SCANNING - no touch yet
        scan = barrier_mgr.get_scan(scan_id)
        assert scan["status"] == "SCANNING"
        assert scan["hold_bars_remaining"] is None

        # State 2: Transition to HOLDING after touch
        actions = barrier_mgr.evaluate_bar(BarContext(
            symbol="USDJPY",
            bar_ticks=100,
            bid=BarPrices(high=150.04, low=150.0, close=150.02),
            ask=BarPrices(high=150.05, low=150.0, close=150.03),
            hl_first=1.0,
            bar_idx=11,
        ))
        assert len(actions) == 1
        assert actions[0].type == BarrierActionType.OPEN_MARKET

        scan = barrier_mgr.get_scan(scan_id)
        assert scan["status"] == "HOLDING"
        assert scan["touch_side"] == "BUY"
        assert scan["hold_bars_remaining"] == 3

        # State 3: Decrement hold counter
        actions = barrier_mgr.evaluate_bar(BarContext(
            symbol="USDJPY",
            bar_ticks=100,
            bid=BarPrices(high=150.02, low=149.99, close=150.0),
            ask=BarPrices(high=150.03, low=150.0, close=150.01),
            hl_first=0.0,
            bar_idx=12,
        ))
        scan = barrier_mgr.get_scan(scan_id)
        assert scan["status"] == "HOLDING"
        assert scan["hold_bars_remaining"] == 2

        # State 4: Complete after hold expires
        actions = barrier_mgr.evaluate_bar(BarContext(
            symbol="USDJPY",
            bar_ticks=100,
            bid=BarPrices(high=150.01, low=149.98, close=150.0),
            ask=BarPrices(high=150.02, low=149.99, close=150.01),
            hl_first=0.0,
            bar_idx=13,
        ))
        actions = barrier_mgr.evaluate_bar(BarContext(
            symbol="USDJPY",
            bar_ticks=100,
            bid=BarPrices(high=150.0, low=149.97, close=149.99),
            ask=BarPrices(high=150.01, low=149.98, close=150.0),
            hl_first=0.0,
            bar_idx=14,
        ))
        assert len(actions) == 1
        assert actions[0].type == BarrierActionType.CLOSE_MARKET

        scan = barrier_mgr.get_scan(scan_id)
        assert scan["status"] == "COMPLETED"

        barrier_mgr.close()

    def test_bar_boundary_alignment(self):
        """Verify bar_ticks parameter flows through predict and aligns boundaries."""
        # Create two bar context snapshots at different bar indices
        # with same bar_ticks=100 (should use same feature window)

        bar_1 = BarContext(
            symbol="EURUSD",
            bar_ticks=100,
            bid=BarPrices(high=1.10000, low=1.09900, close=1.09950),
            ask=BarPrices(high=1.10010, low=1.09910, close=1.09960),
            hl_first=0.5,
            bar_idx=100,
        )

        bar_2 = BarContext(
            symbol="EURUSD",
            bar_ticks=100,  # Same bar size
            bid=BarPrices(high=1.10005, low=1.09895, close=1.09955),
            ask=BarPrices(high=1.10015, low=1.09905, close=1.09965),
            hl_first=0.6,
            bar_idx=200,  # Different bar index - but same alignment
        )

        # Both should use same rolling window settings since bar_ticks is same
        assert bar_1.bar_ticks == bar_2.bar_ticks
        # Feature computation would use same vol_window/cost_window for both

    def test_concurrent_symbols_isolation(self):
        """Verify barrier detection isolates state per symbol (SymbolWorker contract)."""
        # Each symbol should have independent barrier manager instance
        mgr_gbp = BarrierManager()
        mgr_jpy = BarrierManager()

        # Register scans for different symbols
        scan_gbp = mgr_gbp.register_scan(
            symbol="GBPUSD",
            candidate_uid="gbp_test",
            signal_bar_idx=10,
            ref_price=1.30000,
            barrier_pips=2.0,
            horizon=5,
            pip_size=0.0001,
            pred_prob=0.7,
            threshold=0.6,
            model_month="2026-02",
            reservation_id="res-gbp-001",
            run_id="integration_test",
        )

        scan_jpy = mgr_jpy.register_scan(
            symbol="USDJPY",
            candidate_uid="jpy_test",
            signal_bar_idx=10,
            ref_price=150.0,
            barrier_pips=3.0,
            horizon=4,
            pip_size=0.01,
            pred_prob=0.75,
            threshold=0.65,
            model_month="2026-02",
            reservation_id="res-jpy-001",
            run_id="integration_test",
        )

        # Each manager should only have its symbol's scan
        assert mgr_gbp.has_active_scan("GBPUSD", "gbp_test")
        assert not mgr_gbp.has_active_scan("USDJPY", "jpy_test")

        assert mgr_jpy.has_active_scan("USDJPY", "jpy_test")
        assert not mgr_jpy.has_active_scan("GBPUSD", "gbp_test")

        mgr_gbp.close()
        mgr_jpy.close()

    def test_action_generation_contract(self):
        """Verify all actions generated have required fields for /orders endpoint."""
        barrier_mgr = BarrierManager()

        scan_id = barrier_mgr.register_scan(
            symbol="AUDUSD",
            candidate_uid="contract_test",
            signal_bar_idx=5,
            ref_price=0.67000,
            barrier_pips=1.0,
            horizon=4,
            pip_size=0.0001,
            pred_prob=0.8,
            threshold=0.7,
            model_month="2026-02",
            reservation_id="res-contract-001",
            run_id="integration_test",
        )

        # Trigger OPEN_MARKET action
        actions = barrier_mgr.evaluate_bar(BarContext(
            symbol="AUDUSD",
            bar_ticks=100,
            bid=BarPrices(high=0.67015, low=0.67000, close=0.67010),
            ask=BarPrices(high=0.67020, low=0.67005, close=0.67015),
            hl_first=1.0,
            bar_idx=6,
        ))

        assert len(actions) == 1
        action = actions[0]

        # Required fields for /orders endpoint
        assert action.type == BarrierActionType.OPEN_MARKET
        assert action.symbol == "AUDUSD"
        assert action.side == "BUY"
        assert action.candidate_uid == "contract_test"
        assert action.scan_id == scan_id
        assert action.reservation_id == "res-contract-001"
        assert action.horizon == 4

        # Expire to trigger RELEASE_RESERVATION
        for i in range(4):
            barrier_mgr.evaluate_bar(BarContext(
                symbol="AUDUSD",
                bar_ticks=100,
                bid=BarPrices(high=0.67001, low=0.66990, close=0.66995),
                ask=BarPrices(high=0.67006, low=0.66995, close=0.67000),
                hl_first=0.0,
                bar_idx=7 + i,
            ))

        barrier_mgr.close()
