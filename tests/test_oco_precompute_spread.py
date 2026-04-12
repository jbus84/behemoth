"""Tests for spread-adjusted _oco_precompute: touch-bar entry and side-aware exit pricing."""
from __future__ import annotations

import numpy as np
import pandas as pd

from scripts.build_tick_opportunity_ml_dataset import _oco_precompute


def _gross_for_start(result: dict[str, np.ndarray], start_idx: int) -> float:
    matches = np.flatnonzero(result["i0"] == start_idx)
    assert len(matches) == 1, f"Expected exactly one match for start {start_idx}, got {matches}"
    return float(result["gross"][matches[0]])


def _side_for_start(result: dict[str, np.ndarray], start_idx: int) -> int:
    matches = np.flatnonzero(result["i0"] == start_idx)
    assert len(matches) == 1, f"Expected exactly one match for start {start_idx}, got {matches}"
    return int(result["side"][matches[0]])


def test_buy_trigger_anchors_off_signal_close_ask() -> None:
    """BUY should not trigger if only close_bid + barrier is cleared."""
    pip = 0.0001
    barrier_pips = 2.0
    n = 120
    df = pd.DataFrame(
        {
            "close_bid": [1.10000] * n,
            "high_bid": [1.10005] * n,
            "low_bid": [1.09990] * n,
            "hl_first": [1.0] * n,
            "high_ask": [1.10005] * n,
            "close_ask": [1.10010] * n,
        }
    )
    df.loc[1, "high_ask"] = 1.10025

    result = _oco_precompute(
        df,
        horizon=6,
        barrier_pips=barrier_pips,
        pip=pip,
        hold_mode="from_touch",
    )
    assert result, "Expected non-empty result"
    assert _side_for_start(result, 0) == 0


def test_sell_trigger_anchors_off_signal_close_bid() -> None:
    """SELL should not trigger if only close_ask - barrier is cleared."""
    pip = 0.0001
    barrier_pips = 2.0
    n = 120
    df = pd.DataFrame(
        {
            "close_bid": [1.10000] * n,
            "high_bid": [1.10005] * n,
            "low_bid": [1.09990] * n,
            "hl_first": [-1.0] * n,
            "high_ask": [1.10005] * n,
            "close_ask": [1.10010] * n,
        }
    )
    df.loc[1, "low_bid"] = 1.09985

    result = _oco_precompute(
        df,
        horizon=6,
        barrier_pips=barrier_pips,
        pip=pip,
        hold_mode="from_touch",
    )
    assert result, "Expected non-empty result"
    assert _side_for_start(result, 0) == 0


def test_buy_entry_gross_uses_touch_bar_close_ask() -> None:
    """BUY should trigger on high_ask and price entry from the touch bar close_ask."""
    pip = 0.0001
    barrier_pips = 2.0
    n = 120
    df = pd.DataFrame(
        {
            "close_bid": [1.10000] * n,
            "high_bid": [1.10005] * n,
            "low_bid": [1.09990] * n,
            "hl_first": [1.0] * n,
            "high_ask": [1.10005] * n,
            "close_ask": [1.10010] * n,
        }
    )
    df.loc[1, "high_ask"] = 1.10035
    df.loc[1, "close_ask"] = 1.10025
    df.loc[7, "close_bid"] = 1.10050

    result = _oco_precompute(
        df,
        horizon=6,
        barrier_pips=barrier_pips,
        pip=pip,
        hold_mode="from_touch",
    )
    assert result, "Expected non-empty result"
    assert _side_for_start(result, 0) == 1
    assert np.isclose(_gross_for_start(result, 0), 2.5, atol=1e-6)


def test_sell_entry_gross_uses_touch_bar_close_bid_and_ask_exit() -> None:
    """SELL should trigger on low_bid and price entry from the touch bar close_bid."""
    pip = 0.0001
    barrier_pips = 2.0
    n = 120
    df = pd.DataFrame(
        {
            "close_bid": [1.10000] * n,
            "high_bid": [1.10005] * n,
            "low_bid": [1.09990] * n,
            "hl_first": [-1.0] * n,
            "high_ask": [1.10005] * n,
            "close_ask": [1.10010] * n,
        }
    )
    df.loc[1, "low_bid"] = 1.09975
    df.loc[1, "close_bid"] = 1.09990
    df.loc[7, "close_ask"] = 1.09970

    result = _oco_precompute(
        df,
        horizon=6,
        barrier_pips=barrier_pips,
        pip=pip,
        hold_mode="from_touch",
    )
    assert result, "Expected non-empty result"
    assert _side_for_start(result, 0) == -1
    assert np.isclose(_gross_for_start(result, 0), 2.0, atol=1e-6)


def test_sell_exit_label_uses_close_ask() -> None:
    """SELL exit label still uses close_ask (ASK), not close_bid (BID)."""
    pip = 0.0001
    barrier_pips = 2.0
    n = 120
    df = pd.DataFrame(
        {
            "close_bid": [1.10000] * n,
            "high_bid": [1.10005] * n,
            "low_bid": [1.09950] * n,
            "hl_first": [-1.0] * n,
            "high_ask": [1.10007] * n,
            "close_ask": [1.10015] * n,
        }
    )

    result = _oco_precompute(
        df,
        horizon=6,
        barrier_pips=barrier_pips,
        pip=pip,
        hold_mode="from_touch",
    )
    assert result, "Expected non-empty result"
    gross = result["gross"]
    side = result["side"]
    decided = result["decided"]

    sell_gross = gross[decided & (side == -1)]
    assert len(sell_gross) > 0, "Expected SELL events"
    assert np.allclose(sell_gross, -1.5, atol=1e-6), (
        f"Expected sell gross=-1.5 (ASK exit), got {sell_gross[:5]}"
    )
