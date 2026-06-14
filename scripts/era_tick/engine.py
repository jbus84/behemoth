"""The continuous-time state machine: OUT -> IN_LONG/IN_SHORT -> OUT.

`TickEngine` replays a `TickReplay`, updating the Kalman filter, regime detector and
extremum seeker on every tick, asking the `TickPolicy` what to do, and applying
tick-exact fills. It emits a `Trade` per round trip (with gross mid-to-mid pips, the
cost actually paid, and net) plus a lightweight per-tick `trace` for visualisation.

Causality is enforced by construction: the engine only ever consumes the current tick
from the iterator and per-tick state objects that depend solely on the past. The
`test_engine_causality` guard pins this down.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from scripts.era_tick.extrema import ExtremumKind, ExtremumSeeker
from scripts.era_tick.fill_model import FillModel
from scripts.era_tick.micro_price import KalmanMicroPrice
from scripts.era_tick.policy import Action, TickPolicy, TickState
from scripts.era_tick.regime import RegimeDetector
from scripts.era_tick.tick_replay import Tick, TickReplay


@dataclass(frozen=True, slots=True)
class Trade:
    direction: int  # +1 long, -1 short
    entry_i: int
    exit_i: int
    entry_ts: object
    exit_ts: object
    entry_fill: float
    exit_fill: float
    entry_mid: float
    exit_mid: float
    gross_pips: float  # mid-to-mid, signed by direction
    cost_pips: float  # spread + markup actually paid
    net_pips: float  # fill-to-fill, signed by direction
    hold_ticks: int
    run_up_pips: float
    drawdown_pips: float


@dataclass
class _OpenPosition:
    direction: int
    entry_i: int
    entry_ts: object
    entry_fill: float
    entry_mid: float
    run_up_pips: float = 0.0
    peak_pips: float = 0.0


@dataclass
class EngineResult:
    symbol: str
    pip: float
    trades: list[Trade] = field(default_factory=list)
    trace: dict[str, list] = field(default_factory=dict)


class TickEngine:
    def __init__(
        self,
        policy: TickPolicy,
        fill: FillModel,
        *,
        kalman: KalmanMicroPrice | None = None,
        regime: RegimeDetector | None = None,
        record_trace: bool = True,
    ) -> None:
        self.policy = policy
        self.fill = fill
        self.kalman = kalman or KalmanMicroPrice()
        self.regime = regime or RegimeDetector(pip=fill.pip)
        self.extrema = ExtremumSeeker()
        self.record_trace = record_trace

    def run(self, replay: TickReplay) -> EngineResult:
        pip = replay.pip
        result = EngineResult(symbol=replay.symbol, pip=pip)
        trace = _new_trace() if self.record_trace else None
        pos: _OpenPosition | None = None
        last_tick: Tick | None = None

        for tick in replay:
            last_tick = tick
            # Adapt measurement noise to the live half-spread, then filter.
            self.kalman.set_measurement_var(max((0.5 * tick.spread) ** 2, 1.0e-12))
            micro = self.kalman.update(tick.mid, tick.dt)
            reg = self.regime.update(tick.mid)
            ext = self.extrema.update(micro.mid_hat, micro.drift_hat)

            state, unreal = self._state(tick, micro, reg, pos, pip)
            if trace is not None:
                _append_trace(trace, tick, micro, reg, ext, pos, unreal)

            action = self.policy.decide(state)
            pos = self._apply(action, tick, pos, result, pip)

        if pos is not None and last_tick is not None:
            self._close(pos, last_tick, result, pip)
        if trace is not None:
            result.trace = trace
        return result

    # -- state assembly --------------------------------------------------------

    def _state(self, tick, micro, reg, pos, pip) -> tuple[TickState, float]:
        spread_pips = tick.spread / pip
        if pos is None:
            return (
                TickState(
                    spread_pips=spread_pips,
                    mid_hat=micro.mid_hat,
                    drift_hat=micro.drift_hat,
                    drift_t=micro.drift_t(),
                    residual_z=micro.residual_z(),
                    regime=reg.regime,
                    position=0,
                    unrealized_pips=0.0,
                    run_up_pips=0.0,
                    drawdown_pips=0.0,
                    hold_ticks=0,
                ),
                0.0,
            )
        unreal = pos.direction * (tick.mid - pos.entry_mid) / pip
        pos.peak_pips = max(pos.peak_pips, unreal)
        pos.run_up_pips = pos.peak_pips
        drawdown = max(0.0, pos.peak_pips - unreal)
        return (
            TickState(
                spread_pips=spread_pips,
                mid_hat=micro.mid_hat,
                drift_hat=micro.drift_hat,
                drift_t=micro.drift_t(),
                residual_z=micro.residual_z(),
                regime=reg.regime,
                position=pos.direction,
                unrealized_pips=unreal,
                run_up_pips=pos.run_up_pips,
                drawdown_pips=drawdown,
                hold_ticks=tick.i - pos.entry_i,
            ),
            unreal,
        )

    # -- position transitions --------------------------------------------------

    def _apply(self, action, tick, pos, result, pip) -> _OpenPosition | None:
        if pos is None:
            if action is Action.ENTER_LONG:
                return self._open(+1, tick)
            if action is Action.ENTER_SHORT:
                return self._open(-1, tick)
            return None
        if action is Action.EXIT:
            self._close(pos, tick, result, pip)
            return None
        return pos

    def _open(self, direction: int, tick: Tick) -> _OpenPosition:
        fill = self.fill.buy_price(tick) if direction == 1 else self.fill.sell_price(tick)
        return _OpenPosition(
            direction=direction,
            entry_i=tick.i,
            entry_ts=tick.ts,
            entry_fill=fill,
            entry_mid=tick.mid,
        )

    def _close(self, pos: _OpenPosition, tick: Tick, result: EngineResult, pip: float) -> None:
        exit_fill = self.fill.sell_price(tick) if pos.direction == 1 else self.fill.buy_price(tick)
        net_pips = pos.direction * (exit_fill - pos.entry_fill) / pip
        gross_pips = pos.direction * (tick.mid - pos.entry_mid) / pip
        result.trades.append(
            Trade(
                direction=pos.direction,
                entry_i=pos.entry_i,
                exit_i=tick.i,
                entry_ts=pos.entry_ts,
                exit_ts=tick.ts,
                entry_fill=pos.entry_fill,
                exit_fill=exit_fill,
                entry_mid=pos.entry_mid,
                exit_mid=tick.mid,
                gross_pips=gross_pips,
                cost_pips=gross_pips - net_pips,
                net_pips=net_pips,
                hold_ticks=tick.i - pos.entry_i,
                run_up_pips=pos.run_up_pips,
                drawdown_pips=max(0.0, pos.peak_pips - net_pips),
            )
        )


def _new_trace() -> dict[str, list]:
    keys = ("i", "ts", "mid", "mid_hat", "drift_hat", "residual_z", "regime", "extremum", "pos")
    return {k: [] for k in keys}


def _append_trace(trace, tick, micro, reg, ext, pos, unreal) -> None:
    trace["i"].append(tick.i)
    trace["ts"].append(tick.ts)
    trace["mid"].append(tick.mid)
    trace["mid_hat"].append(micro.mid_hat)
    trace["drift_hat"].append(micro.drift_hat)
    trace["residual_z"].append(micro.residual_z())
    trace["regime"].append(reg.regime.value)
    trace["extremum"].append(
        ext.just_flipped.value if ext.just_flipped is not ExtremumKind.NONE else ""
    )
    trace["pos"].append(0 if pos is None else pos.direction)


__all__ = ["TickEngine", "EngineResult", "Trade"]
