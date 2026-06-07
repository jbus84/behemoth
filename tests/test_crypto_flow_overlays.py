"""Guard tests for crypto_flow_overlays.

These lock down the three bugs that produced the fake "Sharpe 4.66 / -10% DD / 1,719x"
crypto-flow result (see docs/analysis/2026-06-07_crypto_flow_VALIDATION_corrected.md):
  1. look-ahead in the drawdown guard / momentum stop,
  2. sqrt(365) annualization for an h-hour rebalance period,
  3. zero ("free") trading cost from maker_rebate == spread.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from scripts.research.crypto_flow_overlays import (
    RETAIL_MAKER,
    ann_factor,
    cost_per_turn,
    drawdown_guard,
    metrics,
    momentum_stop,
    periods_per_year,
)


def _series(vals: list[float]) -> pd.Series:
    idx = pd.date_range("2021-01-01", periods=len(vals), freq="48h")
    return pd.Series(vals, index=idx)


def test_annualization_is_period_aware_not_365():
    # h=48h -> 182.5 periods/yr, factor sqrt(182.5), NOT sqrt(365).
    assert periods_per_year(48) == pytest.approx(182.5)
    assert ann_factor(48) == pytest.approx(np.sqrt(182.5))
    # the old bug used sqrt(365); confirm we are ~1.41x smaller.
    assert ann_factor(48) / np.sqrt(365) == pytest.approx(1 / np.sqrt(2), rel=1e-6)
    # daily (h=24) genuinely is sqrt(365).
    assert ann_factor(24) == pytest.approx(np.sqrt(365))


def test_guard_is_causal_cannot_cut_the_loss_bar_itself():
    # A single sharp loss at period i. A causal guard reacts on i+1, so the loss bar
    # is NOT scaled down (no look-ahead). A look-ahead guard would zero it out.
    s = _series([0.01, 0.01, 0.01, -0.30, 0.01, 0.01])
    g = drawdown_guard(s, soft=-0.08, hard=-0.15, soft_scale=0.25)
    # the -0.30 bar survives unscaled (guard only knows after the fact)
    assert g.iloc[3] == pytest.approx(-0.30)
    # the bar AFTER the crash is scaled (we are now in a drawdown)
    assert abs(g.iloc[4]) < abs(s.iloc[4]) + 1e-12
    assert g.iloc[4] != pytest.approx(s.iloc[4])


def test_momentum_stop_is_causal():
    s = _series([0.02, 0.02, 0.02, -0.10, -0.10, 0.02, 0.02])
    m = momentum_stop(s, window=2, threshold=-0.05, scale=0.5)
    # the drop bars themselves are not retroactively scaled
    assert m.iloc[3] == pytest.approx(s.iloc[3])
    # a later bar, after the trailing-return breach is visible, is scaled
    assert m.iloc[5] == pytest.approx(s.iloc[5] * 0.5)


def test_lookahead_mode_differs_from_causal():
    s = _series([0.01, 0.01, -0.30, 0.01, 0.01, 0.01])
    causal = drawdown_guard(s, causal=True)
    lookahead = drawdown_guard(s, causal=False)
    # the two must differ on the crash bar: look-ahead scales it, causal does not.
    assert not np.allclose(causal.to_numpy(), lookahead.to_numpy())
    assert causal.iloc[2] == pytest.approx(-0.30)


def test_retail_maker_is_not_free_trading():
    # The canonical fee model must charge a real per-turn cost; rebate must not equal spread.
    assert RETAIL_MAKER["maker_rebate_bps"] < RETAIL_MAKER["spread_bps"]
    assert cost_per_turn(RETAIL_MAKER) > 0.0
    # the old free-lunch model (rebate == spread, perfect fill) is exactly zero — guard against it.
    free = {"spread_bps": 2.0, "maker_rebate_bps": 2.0, "taker_fee_bps": 5.0,
            "queue_pos": 0.0, "adv_bps": 0.0, "p_fill_base": 1.0}
    assert cost_per_turn(free) == pytest.approx(0.0)


def test_metrics_keys_and_sharpe_sign():
    s = _series([0.01, -0.005, 0.02, 0.01, -0.01, 0.015])
    m = metrics(s, 48)
    assert set(m) == {"sharpe", "max_dd", "final", "vol_ann", "pos", "neg"}
    assert m["max_dd"] <= 0.0
    assert m["pos"] + m["neg"] <= len(s)
