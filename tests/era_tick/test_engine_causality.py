"""The headline correctness guard: the engine cannot see the future.

If a decision at tick i depended on any tick > i, then running the engine on the prefix
[0..k] would produce a different decision at some tick <= k than running it on the full
stream. We assert they are identical. A "smooth" backtest that quietly used look-ahead
(the failure mode that once faked a Sharpe of 4.66) cannot pass this.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from scripts.era_tick.engine import TickEngine
from scripts.era_tick.fill_model import FillModel
from scripts.era_tick.policy import Action, NaiveFadePolicy, TickPolicy, TickState
from scripts.era_tick.regime import RegimeDetector
from scripts.era_tick.tick_replay import TickReplay
from tests.era_tick._synthetic import make_frame, oscillation


@dataclass
class RecordingPolicy:
    inner: TickPolicy
    actions: list[Action] = field(default_factory=list)

    def decide(self, state: TickState) -> Action:
        action = self.inner.decide(state)
        self.actions.append(action)
        return action


def _engine() -> TickEngine:
    fill = FillModel(pip=1e-4)
    policy = RecordingPolicy(NaiveFadePolicy(enter_z=1.5, max_spread_pips=10.0))
    regime = RegimeDetector(window=20, churn_pips=0.1, pip=fill.pip)
    return TickEngine(policy, fill, regime=regime, record_trace=False)


def test_prefix_decisions_are_identical_to_full_run():
    mids = oscillation(n=1200, seed=11)
    k = 800

    full = _engine()
    full.run(TickReplay("EURUSD", make_frame(mids)))
    full_actions = full.policy.actions

    prefix = _engine()
    prefix.run(TickReplay("EURUSD", make_frame(mids[:k])))
    prefix_actions = prefix.policy.actions

    assert len(prefix_actions) == k
    assert prefix_actions == full_actions[:k], "engine decision depends on future ticks"


def test_engine_actually_trades_on_oscillation():
    # The guard is only meaningful if the entry/exit paths are exercised.
    mids = oscillation(n=1500, seed=3)
    eng = _engine()
    result = eng.run(TickReplay("EURUSD", make_frame(mids)))
    assert len(result.trades) > 0
    assert any(a is not Action.NONE for a in eng.policy.actions)


def test_gross_minus_net_equals_cost():
    mids = oscillation(n=1500, seed=3)
    eng = _engine()
    result = eng.run(TickReplay("EURUSD", make_frame(mids)))
    for t in result.trades:
        assert abs((t.gross_pips - t.net_pips) - t.cost_pips) < 1e-9
        assert t.cost_pips > 0.0  # taker always pays


def test_cost_matches_spread_for_zero_markup():
    mids = oscillation(n=1500, seed=3)
    eng = _engine()  # spread is 0.2 pip, markup 0
    result = eng.run(TickReplay("EURUSD", make_frame(mids, spread_pips=0.2)))
    costs = np.array([t.cost_pips for t in result.trades])
    assert np.allclose(costs, 0.2, atol=1e-6)
