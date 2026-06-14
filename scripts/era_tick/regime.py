"""Per-tick regime classification over a trailing window of mids.

A scalper does not trade every tape the same way. We classify the last `window` ticks
into one of four regimes, recomputed on every tick (never per bar):

- ``SHOCK``   : the latest tick return is a large multiple of recent volatility — abstain.
- ``DRIFT``   : high efficiency ratio (price travels in a line) — fades get run over.
- ``REVERT``  : low efficiency ratio with real movement — oscillatory, fade extremes.
- ``CHURN``   : negligible movement — noise, no edge.

The efficiency ratio (Kaufman) is ``|net move| / sum|tick moves|`` over the window: ~1
means a clean trend, ~0 means lots of motion that goes nowhere (the fade habitat).
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from enum import Enum

import numpy as np


class Regime(str, Enum):
    WARMUP = "warmup"
    SHOCK = "shock"
    DRIFT = "drift"
    REVERT = "revert"
    CHURN = "churn"


@dataclass(frozen=True, slots=True)
class RegimeState:
    regime: Regime
    efficiency_ratio: float  # 0 (churn/revert) .. 1 (clean drift)
    shock_z: float  # latest return in std units of recent returns

    @property
    def fadeable(self) -> bool:
        """True in the oscillatory regime where fading micro-extremes has a thesis."""
        return self.regime is Regime.REVERT


class RegimeDetector:
    """Streaming regime detector over a rolling window of mids.

    Parameters
    ----------
    window:
        Number of recent ticks to summarise.
    drift_er:
        Efficiency ratio above which the tape is a directional drift.
    churn_pips, pip:
        Below `churn_pips` of net travel over the window the tape is dead (churn).
    shock_z:
        Per-tick return (in std of recent returns) above which we flag a shock.
    """

    def __init__(
        self,
        *,
        window: int = 50,
        drift_er: float = 0.55,
        churn_pips: float = 0.6,
        pip: float = 1.0e-4,
        shock_z: float = 5.0,
    ) -> None:
        self._mids: deque[float] = deque(maxlen=window)
        self._rets: deque[float] = deque(maxlen=window)
        self._window = window
        self._drift_er = drift_er
        self._churn = churn_pips * pip
        self._shock_z = shock_z

    def update(self, mid: float) -> RegimeState:
        prev = self._mids[-1] if self._mids else None
        self._mids.append(mid)
        if prev is not None:
            self._rets.append(mid - prev)

        if len(self._mids) < self._window:
            return RegimeState(Regime.WARMUP, efficiency_ratio=0.0, shock_z=0.0)

        rets = np.fromiter(self._rets, dtype=float)
        gross = float(np.abs(rets).sum())
        net = abs(self._mids[-1] - self._mids[0])
        er = net / gross if gross > 0.0 else 0.0

        std = float(rets.std())
        shock_z = abs(rets[-1]) / std if std > 0.0 else 0.0

        regime = self._classify(er, net, shock_z)
        return RegimeState(regime=regime, efficiency_ratio=er, shock_z=shock_z)

    def _classify(self, er: float, net: float, shock_z: float) -> Regime:
        if shock_z >= self._shock_z:
            return Regime.SHOCK
        if net < self._churn:
            return Regime.CHURN
        if er >= self._drift_er:
            return Regime.DRIFT
        return Regime.REVERT
