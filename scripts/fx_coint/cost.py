from __future__ import annotations

import numpy as np

from scripts.era_scalp.load_splits import _pip_size
from scripts.fx_coint.instruments import MAJORS

# Added markup per leg (pips), swept so the verdict can be read at any broker assumption.
MARKUP_SWEEP_PIPS: tuple[float, ...] = (0.0, 0.3, 0.6, 1.0)


def leg_cost_frac(symbol: str, spread_price: float, mid: float,
                  markup_pips: float) -> float:
    """One leg's round-trip cost in fractional (log) units."""
    price_cost = spread_price + markup_pips * _pip_size(symbol)
    return float(price_cost / mid)


def spread_cost_frac(weights: np.ndarray, spreads: np.ndarray, mids: np.ndarray,
                     markup_pips: float) -> float:
    """Round-trip cost of a weight-vector spread = sum_i |w_i| * leg_cost_i."""
    total = 0.0
    for i, sym in enumerate(MAJORS):
        if weights[i] == 0.0:
            continue
        total += abs(weights[i]) * leg_cost_frac(sym, float(spreads[i]),
                                                 float(mids[i]), markup_pips)
    return total
