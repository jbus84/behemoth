"""Tests for BarrierManager barrier detection parity with _oco_precompute."""
from __future__ import annotations

import numpy as np
import pandas as pd
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
        # When both barriers are touched simultaneously with hl_first=0, the scan
        # is immediately expired — mirrors _oco_precompute which locks in side=0
        # on the first simultaneous touch and does not evaluate later bars.
        mgr, scan_id = self._make_manager_with_scan()
        actions = mgr.evaluate_bar("GBPUSD", 100, 1.29530, 1.29470, 0.0, 11)
        assert len(actions) == 0
        scan = mgr.get_scan(scan_id)
        assert scan["status"] == "EXPIRED"
        assert not mgr.has_active_scan("GBPUSD", "oco|GBPUSD|100|h6|abc")


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


def _oco_precompute_reference(
    df: pd.DataFrame,
    *,
    horizon: int,
    barrier_pips: float,
    pip: float,
) -> dict[str, np.ndarray]:
    """Exact copy of _oco_precompute from build_tick_opportunity_ml_dataset.py
    in from_touch mode — the ground truth for barrier detection."""
    close = pd.to_numeric(df["close"], errors="coerce").to_numpy(dtype=float)
    high = pd.to_numeric(df["high"], errors="coerce").to_numpy(dtype=float)
    low = pd.to_numeric(df["low"], errors="coerce").to_numpy(dtype=float)
    hlf = pd.to_numeric(df["hl_first"], errors="coerce").fillna(0.0).to_numpy(dtype=float)
    h = int(horizon)
    n_eff = len(df) - 2 * h
    if n_eff <= 0:
        return {}
    i0 = np.arange(n_eff, dtype=np.int64)
    ref = close[i0]
    valid = np.isfinite(ref)
    i0 = i0[valid]
    ref = ref[valid]
    k = float(barrier_pips)
    up_thr = ref + k * pip
    dn_thr = ref - k * pip
    inf = h + 1
    up_step = np.full(len(i0), inf, dtype=np.int32)
    dn_step = np.full(len(i0), inf, dtype=np.int32)
    for s in range(1, h + 1):
        idx = i0 + int(s)
        hu = high[idx] >= up_thr
        hd = low[idx] <= dn_thr
        set_up = (up_step == inf) & hu
        set_dn = (dn_step == inf) & hd
        up_step[set_up] = int(s)
        dn_step[set_dn] = int(s)
    side = np.zeros(len(i0), dtype=np.int8)
    side[up_step < dn_step] = 1
    side[dn_step < up_step] = -1
    same = (up_step == dn_step) & (up_step <= h)
    if np.any(same):
        same_idx = np.flatnonzero(same)
        tie_idx = i0[same_idx] + up_step[same_idx].astype(np.int64)
        tie_hlf = hlf[tie_idx]
        side[same_idx[tie_hlf > 0]] = 1
        side[same_idx[tie_hlf < 0]] = -1
    decided = side != 0
    touch_step = np.minimum(up_step, dn_step).astype(float)
    touch_step[~decided] = np.nan
    return {
        "i0": i0,
        "side": side,
        "decided": decided,
        "touch_step": touch_step,
    }


class TestParityWithOcoPrecompute:
    def test_barrier_manager_matches_oco_precompute(self):
        """Feed identical bar data to both systems, verify identical decisions."""
        rng = np.random.default_rng(42)
        n_bars = 200
        base = 1.29500
        prices = base + np.cumsum(rng.normal(0, 0.0003, n_bars))
        highs = prices + np.abs(rng.normal(0, 0.0002, n_bars))
        lows = prices - np.abs(rng.normal(0, 0.0002, n_bars))
        hl_firsts = rng.choice([-1.0, 0.0, 1.0], n_bars)

        df = pd.DataFrame({
            "close": prices,
            "high": highs,
            "low": lows,
            "hl_first": hl_firsts,
        })

        horizon = 6
        barrier_pips = 2.0
        pip = 0.0001

        ref_result = _oco_precompute_reference(
            df, horizon=horizon, barrier_pips=barrier_pips, pip=pip,
        )
        if not ref_result:
            pytest.skip("Not enough bars for reference")

        ref_i0 = ref_result["i0"]
        ref_side = ref_result["side"]
        ref_decided = ref_result["decided"]
        ref_touch_step = ref_result["touch_step"]

        mismatches = []
        for idx in range(len(ref_i0)):
            signal_bar = int(ref_i0[idx])
            expected_side = int(ref_side[idx])
            expected_decided = bool(ref_decided[idx])
            expected_touch = ref_touch_step[idx]

            mgr = BarrierManager()
            mgr.register_scan(
                symbol="GBPUSD",
                candidate_uid=f"test_cand_{signal_bar}",
                signal_bar_idx=signal_bar,
                ref_price=float(prices[signal_bar]),
                barrier_pips=barrier_pips,
                horizon=horizon,
                pip_size=pip,
                pred_prob=0.6,
                threshold=0.5,
                model_month="2026-02",
                reservation_id=None,
                run_id="parity_test",
            )

            actual_side = 0
            actual_touch_step = np.nan
            for s in range(1, horizon + 1):
                bar_idx = signal_bar + s
                if bar_idx >= n_bars:
                    break
                actions = mgr.evaluate_bar(
                    symbol="GBPUSD",
                    bar_ticks=100,
                    bar_high=float(highs[bar_idx]),
                    bar_low=float(lows[bar_idx]),
                    bar_hl_first=float(hl_firsts[bar_idx]),
                    current_bar_idx=bar_idx,
                )
                if actions and actions[0]["type"] == "OPEN_MARKET":
                    actual_side = 1 if actions[0]["side"] == "BUY" else -1
                    actual_touch_step = float(s)
                    break
            mgr.close()

            if expected_decided:
                if actual_side != expected_side:
                    mismatches.append(
                        f"bar {signal_bar}: side mismatch: expected={expected_side}, got={actual_side}"
                    )
                if not np.isnan(expected_touch) and actual_touch_step != expected_touch:
                    mismatches.append(
                        f"bar {signal_bar}: touch_step mismatch: expected={expected_touch}, got={actual_touch_step}"
                    )
            else:
                if actual_side != 0:
                    mismatches.append(
                        f"bar {signal_bar}: expected no decision but got side={actual_side}"
                    )

        assert len(mismatches) == 0, f"Parity failures:\n" + "\n".join(mismatches[:20])


class TestActionSchemas:
    def test_open_market_action_serializes(self):
        from src.behemoth.core.schemas import BarrierAction, BarrierActionType
        action = BarrierAction(
            type=BarrierActionType.OPEN_MARKET,
            symbol="GBPUSD",
            candidate_uid="oco|GBPUSD|100|h6|abc",
            scan_id="scan_001",
            side="SELL",
            reservation_id="res-001",
        )
        d = action.model_dump()
        assert d["type"] == "OPEN_MARKET"
        assert d["side"] == "SELL"

    def test_close_market_action_serializes(self):
        from src.behemoth.core.schemas import BarrierAction, BarrierActionType
        action = BarrierAction(
            type=BarrierActionType.CLOSE_MARKET,
            symbol="GBPUSD",
            candidate_uid="oco|GBPUSD|100|h6|abc",
            scan_id="scan_002",
            broker_pos_id="272708355",
        )
        d = action.model_dump()
        assert d["type"] == "CLOSE_MARKET"
        assert d["broker_pos_id"] == "272708355"

    def test_predict_response_wrapper(self):
        from src.behemoth.core.schemas import BarrierAction, BarrierActionType, PredictResponse
        resp = PredictResponse(
            predictions=[],
            actions=[
                BarrierAction(
                    type=BarrierActionType.OPEN_MARKET,
                    symbol="GBPUSD",
                    candidate_uid="oco|GBPUSD|100|h6|abc",
                    scan_id="scan_001",
                    side="BUY",
                ),
            ],
        )
        d = resp.model_dump()
        assert len(d["actions"]) == 1
        assert d["actions"][0]["type"] == "OPEN_MARKET"
