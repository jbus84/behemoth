"""The decision contract — and a naive fade baseline.

`TickState` is the *only* information a policy may use: everything in it is causal
(derived from ticks <= now). `TickPolicy.decide(state) -> Action` is the contract. This
is deliberately the exact shape the ERA PUCT writer will fill in later: a passing
baseline becomes a "program" the search mutates, with no change to the engine.

`NaiveFadePolicy` is the Day-1 baseline: in the oscillatory (REVERT) regime, when the
raw mid has extended away from the filtered micro-price (large residual z-score) and the
filtered drift has started to turn back, fade it; then exit on take-profit, stop,
momentum reversal, a trailing give-back, or a max holding time.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Protocol, runtime_checkable

from scripts.era_tick.regime import Regime


class Action(Enum):
    NONE = 0
    ENTER_LONG = 1
    ENTER_SHORT = 2
    EXIT = 3


@dataclass(frozen=True, slots=True)
class TickState:
    """Causal snapshot handed to the policy on every tick."""

    spread_pips: float
    mid_hat: float
    drift_hat: float
    drift_t: float  # drift_hat / sqrt(Var(drift)): filter confidence in the trend direction
    residual_z: float  # (mid - mid_hat) in innovation std: >0 extended up, <0 extended down
    regime: Regime
    # position context (0 flat, +1 long, -1 short)
    position: int
    unrealized_pips: float  # mid-to-mid, signed by position
    run_up_pips: float  # best unrealized seen this trade
    drawdown_pips: float  # give-back from that peak (>= 0)
    hold_ticks: int


@runtime_checkable
class TickPolicy(Protocol):
    def decide(self, state: TickState) -> Action: ...


@dataclass(frozen=True, slots=True)
class NaiveFadePolicy:
    """Fade micro-extensions in the oscillatory regime; managed exits."""

    enter_z: float = 2.0
    max_spread_pips: float = 0.5
    take_profit_pips: float = 2.0
    stop_pips: float = 1.5
    max_hold_ticks: int = 400
    trail_arm_pips: float = 1.0  # once run-up reaches this...
    trail_give_pips: float = 0.6  # ...exit if it gives back this much from the peak
    exit_reverse_z: float = 2.0  # exit if price extends hard against us again

    def decide(self, state: TickState) -> Action:
        if state.position == 0:
            return self._entry(state)
        return self._exit(state)

    def _entry(self, state: TickState) -> Action:
        if state.regime is not Regime.REVERT:
            return Action.NONE
        if state.spread_pips > self.max_spread_pips:
            return Action.NONE
        # Extended up and rolling over -> fade short. Extended down and turning up -> fade long.
        if state.residual_z >= self.enter_z and state.drift_hat < 0.0:
            return Action.ENTER_SHORT
        if state.residual_z <= -self.enter_z and state.drift_hat > 0.0:
            return Action.ENTER_LONG
        return Action.NONE

    def _exit(self, state: TickState) -> Action:
        if state.unrealized_pips >= self.take_profit_pips:
            return Action.EXIT
        if state.unrealized_pips <= -self.stop_pips:
            return Action.EXIT
        if state.hold_ticks >= self.max_hold_ticks:
            return Action.EXIT
        if state.run_up_pips >= self.trail_arm_pips and state.drawdown_pips >= self.trail_give_pips:
            return Action.EXIT
        # Price extends hard *against* the position again -> thesis broken.
        if state.position == 1 and state.residual_z <= -self.exit_reverse_z:
            return Action.EXIT
        if state.position == -1 and state.residual_z >= self.exit_reverse_z:
            return Action.EXIT
        return Action.NONE


@dataclass(frozen=True, slots=True)
class ConfidentMomentumPolicy:
    """Trade WITH a confident trend; ride through pullbacks with hysteresis.

    The trend-regime counterpart to NaiveFadePolicy. Entry needs the DRIFT regime and the
    Kalman drift t-stat above ``enter_t`` (statistical confidence a real move exists). Exits
    do NOT bail on a mere dip: only a hard stop, a trailing give-back once armed, a confident
    reversal of the drift t-stat, or a max-hold. This is the "cut losers, ride winners" leg
    that beat cost on trending days; route to it only when the regime is trending.
    """

    enter_t: float = 3.0  # |drift_t| required to open
    reversal_t: float = 4.0  # opposite-sign confidence required to close (hysteresis)
    stop_pips: float = 2.0  # cut losers
    trail_arm_pips: float = 2.0  # once run-up reaches this...
    trail_give_pips: float = 1.5  # ...exit on this much give-back from the peak
    max_hold_ticks: int = 4000
    max_spread_pips: float = 0.5

    def decide(self, state: TickState) -> Action:
        if state.position == 0:
            return self._entry(state)
        return self._exit(state)

    def _entry(self, state: TickState) -> Action:
        if state.regime is not Regime.DRIFT or state.spread_pips > self.max_spread_pips:
            return Action.NONE
        if abs(state.drift_t) < self.enter_t:
            return Action.NONE
        return Action.ENTER_LONG if state.drift_t > 0 else Action.ENTER_SHORT

    def _exit(self, state: TickState) -> Action:
        if state.unrealized_pips <= -self.stop_pips:
            return Action.EXIT
        if state.run_up_pips >= self.trail_arm_pips and state.drawdown_pips >= self.trail_give_pips:
            return Action.EXIT
        if state.hold_ticks >= self.max_hold_ticks:
            return Action.EXIT
        reversed_hard = (state.position == 1 and state.drift_t <= -self.reversal_t) or (
            state.position == -1 and state.drift_t >= self.reversal_t
        )
        return Action.EXIT if reversed_hard else Action.NONE
