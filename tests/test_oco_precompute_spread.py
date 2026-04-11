"""Tests for spread-adjusted _oco_precompute: ASK BUY trigger and ASK SELL exit."""
from __future__ import annotations

import numpy as np
import pandas as pd

from scripts.build_tick_opportunity_ml_dataset import _oco_precompute


def _make_bars(n: int, *, close: float = 1.10000, pip: float = 0.0001) -> pd.DataFrame:
    """Minimal bar DataFrame with flat prices and placeholder ask columns."""
    return pd.DataFrame(
        {
            "close": [close] * n,
            "high": [close + 0.00005] * n,   # BID high: 0.5 pips above ref
            "low": [close - 0.00050] * n,
            "hl_first": [1.0] * n,
            "high_ask": [close + 0.00025] * n,  # ASK high: 2.5 pips above ref
            "close_ask": [close + 0.00015] * n,  # ASK close: 1.5 pips above ref
        }
    )


def test_buy_trigger_uses_ask():
    """BUY fires when high_ask >= upper_barrier even when high (BID) < upper_barrier.

    barrier_pips=2.0 → upper = ref + 0.0002.
    BID high = ref + 0.00005 — misses.
    ASK high = ref + 0.00025 — hits.
    Expect at least one event with side=1 (BUY).
    """
    pip = 0.0001
    barrier_pips = 2.0
    n = 500
    df = _make_bars(n)

    result = _oco_precompute(
        df,
        horizon=6,
        barrier_pips=barrier_pips,
        pip=pip,
        hold_mode="from_touch",
    )
    assert result, "Expected non-empty result"
    side = result["side"]
    decided = result["decided"]
    assert np.any(side[decided] == 1), "Expected at least one BUY event"
    assert not np.any(side[decided] == -1), "Expected no SELL events (low never hits dn_thr)"


def test_sell_exit_label_uses_close_ask():
    """SELL exit label uses close_ask (ASK), not close (BID).

    Setup: all bars have close=1.10000, dn_thr = ref - 0.0002 = 1.09980.
    bar_low = ref - 0.00050 = 1.09950 — triggers SELL.
    BID close = 1.10000, ASK close = 1.10015.

    SELL gross for from_touch:
      side=-1, ref=1.10000, exit_price=close_ask[exit_bar]=1.10015
      gross = -1 * ((1.10015 - 1.10000) / 0.0001) - 2.0
            = -1 * 1.5 - 2.0 = -3.5

    If BID close were used (old behaviour):
      gross = -1 * ((1.10000 - 1.10000) / 0.0001) - 2.0 = -2.0
    """
    pip = 0.0001
    barrier_pips = 2.0
    n = 500

    # Build bars where SELL triggers but BUY never does
    df = pd.DataFrame(
        {
            "close": [1.10000] * n,
            "high": [1.10005] * n,       # BID high: never reaches upper (1.10020)
            "low": [1.09950] * n,        # BID low: reaches dn_thr (1.09980) — SELL
            "hl_first": [-1.0] * n,
            "high_ask": [1.10007] * n,   # ASK high: still below upper (1.10020) — no BUY
            "close_ask": [1.10015] * n,  # ASK close: 1.5 pips above BID close
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
    # All SELL gross values should be -3.5 (using close_ask), not -2.0 (using BID close)
    assert np.allclose(sell_gross, -3.5, atol=1e-6), (
        f"Expected sell gross=-3.5 (ASK exit), got {sell_gross[:5]}"
    )
