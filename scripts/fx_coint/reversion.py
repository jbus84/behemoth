from __future__ import annotations

import numpy as np
import pandas as pd

MIN_REVERSION_EVENTS = 100      # statistical-weight floor for condition B
MAX_SENSIBLE_HALF_LIFE = 500    # bars; longer = effectively a random walk
ENTRY_Z = 1.0                   # |z| beyond which we count a "deviation event"


def ou_fit(res: pd.Series) -> dict:
    """Discrete OU via AR(1): r_t = phi*r_{t-1} + e. theta=-ln(phi); hl=ln2/theta."""
    r = res.to_numpy()
    lag, cur = r[:-1], r[1:]
    A = np.column_stack([lag, np.ones_like(lag)])
    phi, _ = np.linalg.lstsq(A, cur, rcond=None)[0]
    if phi <= 0 or phi >= 1:
        return {"theta": 0.0, "half_life": float("inf"), "phi": float(phi)}
    theta = -np.log(phi)
    return {"theta": float(theta), "half_life": float(np.log(2) / theta),
            "phi": float(phi)}


def oos_reversion(res: pd.Series, horizon: int) -> dict:
    """For each bar where |z|>ENTRY_Z, did |residual| shrink `horizon` bars later?

    Returns the fraction of deviation events that reverted (toward the mean) and
    the mean signed reversion (positive = reverts), measured purely forward.
    """
    r = res.to_numpy()
    if r.std() == 0:
        return {"mean_reversion_frac": 0.0, "mean_reversion": 0.0, "n_events": 0}
    z = (r - r.mean()) / r.std()
    reverts, amounts = [], []
    for t in range(len(r) - horizon):
        if abs(z[t]) <= ENTRY_Z:
            continue
        # signed reversion: deviation magnitude consumed toward the mean
        moved = abs(r[t]) - abs(r[t + horizon])
        reverts.append(moved > 0)
        amounts.append(moved)
    n = len(reverts)
    return {
        "mean_reversion_frac": float(np.mean(reverts)) if n else 0.0,
        "mean_reversion": float(np.mean(amounts)) if n else 0.0,
        "n_events": n,
    }


def reversion_exists(fit: dict, rev: dict) -> bool:
    """Condition B: finite sensible half-life + net reversion over enough events."""
    return (0 < fit["half_life"] < MAX_SENSIBLE_HALF_LIFE
            and rev["n_events"] >= MIN_REVERSION_EVENTS
            and rev["mean_reversion_frac"] > 0.5
            and rev["mean_reversion"] > 0)
