"""Local-extremum seeker on the *filtered* micro-price.

We detect turning points on the Kalman trajectory (not the raw mid, which is too noisy)
by watching the sign of ``drift_hat``. A swing high is a + -> - flip; a swing low is a
- -> + flip. The seeker remembers the most recent confirmed extremum so a fade policy
can ask "did the smoothed price just put in a local low `k` ticks ago, and is it now
turning up?" — the continuous-time analogue of "price hit a local low and bounced".
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class ExtremumKind(str, Enum):
    NONE = "none"
    HIGH = "high"
    LOW = "low"


@dataclass(frozen=True, slots=True)
class ExtremumState:
    just_flipped: ExtremumKind  # extremum confirmed on THIS tick (else NONE)
    last_kind: ExtremumKind  # most recent confirmed extremum kind
    last_price: float  # filtered price at that extremum
    ticks_since: int  # ticks elapsed since it was confirmed


class ExtremumSeeker:
    """Tracks turning points in the sign of the filtered drift, one tick at a time."""

    def __init__(self) -> None:
        self._prev_drift: float | None = None
        self._last_kind = ExtremumKind.NONE
        self._last_price = 0.0
        self._ticks_since = 0

    def update(self, mid_hat: float, drift_hat: float) -> ExtremumState:
        flipped = ExtremumKind.NONE
        if self._prev_drift is not None:
            if self._prev_drift > 0.0 >= drift_hat:
                flipped = ExtremumKind.HIGH
            elif self._prev_drift < 0.0 <= drift_hat:
                flipped = ExtremumKind.LOW
        self._prev_drift = drift_hat

        if flipped is not ExtremumKind.NONE:
            self._last_kind = flipped
            self._last_price = mid_hat
            self._ticks_since = 0
        elif self._last_kind is not ExtremumKind.NONE:
            self._ticks_since += 1

        return ExtremumState(
            just_flipped=flipped,
            last_kind=self._last_kind,
            last_price=self._last_price,
            ticks_since=self._ticks_since,
        )
