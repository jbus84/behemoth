"""Forward fade target for the reversion null-test. Pure numpy."""

from __future__ import annotations

import numpy as np


def compute_targets(lr: np.ndarray, residual: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """lr, residual: (T, P) oriented returns / residuals, lr[t] completing at bar t.
    signed_fade[t] = -sign(residual[t]) * lr[t+1] * 1e4  (bps a fade earns, gross).
    abs_move[t]    = |lr[t+1]| * 1e4. Last row is NaN (no forward return)."""
    signed = np.full_like(lr, np.nan, dtype=float)
    absm = np.full_like(lr, np.nan, dtype=float)
    fwd = lr[1:]
    signed[:-1] = -np.sign(residual[:-1]) * fwd * 1e4
    absm[:-1] = np.abs(fwd) * 1e4
    return signed, absm
