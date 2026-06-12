"""Constant-velocity Kalman filter for the micro-price.

Hidden state is ``[price, velocity]``; the measurement is the raw mid. The filter
denoises quote-bounce into a smooth ``mid_hat`` trajectory and an instantaneous
``drift_hat`` (price per second). The one-step prediction residual ``mid - predicted``
is the "surprise" — a large residual that the filter then reels back in is the
micro-extension a fade policy trades against.

This is the principled generalisation of the EWMA-of-mid + EWMA-of-drift sketch: the
gains adapt to elapsed time between ticks (``dt``) and to measurement noise instead of
being fixed. Everything updates per tick — no bar aggregation anywhere.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True, slots=True)
class MicroState:
    mid_hat: float  # filtered price
    drift_hat: float  # filtered velocity, price units per second
    residual: float  # measurement - one-step prediction (the "surprise")
    innovation_var: float  # S: variance of the residual (normaliser for confidence)
    vel_var: float  # P[1,1]: posterior variance of the velocity estimate

    def residual_z(self) -> float:
        """Residual in standard deviations of the innovation (0 if not yet warm)."""
        s = self.innovation_var
        return self.residual / np.sqrt(s) if s > 0.0 else 0.0

    def drift_t(self) -> float:
        """Drift estimate as a t-statistic: drift_hat / sqrt(Var(drift)).

        This is the filter's own confidence that a real directional trend exists (vs
        noise). Large |drift_t| = "confident about the future direction"; near 0 = unsure.
        It is the principled gate for "only enter when confident".
        """
        v = self.vel_var
        return self.drift_hat / np.sqrt(v) if v > 0.0 else 0.0


class KalmanMicroPrice:
    """2-state (price, velocity) Kalman filter updated one tick at a time.

    Parameters
    ----------
    process_var:
        Velocity process noise per second. Larger => filter tracks turns faster but
        denoises less.
    meas_var:
        Measurement (quote-bounce) variance in price^2. Sensible default is
        ``(half_spread)^2``; pass via :meth:`set_measurement_var` once the typical
        spread is known, or leave at the constructor value.
    """

    def __init__(self, process_var: float = 1.0e-9, meas_var: float = 4.0e-9) -> None:
        self._q = float(process_var)
        self._r = float(meas_var)
        self._x = np.zeros(2, dtype=float)  # [price, velocity]
        self._p = np.diag([1.0, 1.0])  # large initial uncertainty
        self._initialised = False

    def set_measurement_var(self, meas_var: float) -> None:
        self._r = float(meas_var)

    @property
    def warm(self) -> bool:
        return self._initialised

    def update(self, mid: float, dt: float) -> MicroState:
        """Advance the filter by one tick and return the new state.

        `dt` is seconds since the previous tick; `mid` is the raw measured mid.
        """
        if not self._initialised:
            self._x[:] = (mid, 0.0)
            self._initialised = True
            return MicroState(
                mid_hat=mid,
                drift_hat=0.0,
                residual=0.0,
                innovation_var=0.0,
                vel_var=float(self._p[1, 1]),
            )

        dt = max(dt, 1.0e-6)
        f = np.array([[1.0, dt], [0.0, 1.0]])
        # Continuous white-noise-acceleration process covariance.
        q = self._q * np.array([[dt**3 / 3.0, dt**2 / 2.0], [dt**2 / 2.0, dt]], dtype=float)

        x_pred = f @ self._x
        p_pred = f @ self._p @ f.T + q

        residual = mid - x_pred[0]
        s = p_pred[0, 0] + self._r
        k = p_pred[:, 0] / s  # Kalman gain (H = [1, 0])

        self._x = x_pred + k * residual
        self._p = p_pred - np.outer(k, p_pred[0, :])

        return MicroState(
            mid_hat=float(self._x[0]),
            drift_hat=float(self._x[1]),
            residual=float(residual),
            innovation_var=float(s),
            vel_var=float(self._p[1, 1]),
        )
