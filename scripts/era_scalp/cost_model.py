from __future__ import annotations

import numpy as np

COMMISSION_PIPS = 0.06   # Dukascopy round-trip commission (~0.03/side)
SLIPPAGE_PIPS = 0.10     # buffer for adverse fills at extreme-dislocation bars


def realistic_cost(spread_pips) -> np.ndarray:
    """Per-bar realistic round-trip taker cost: bar spread + commission + slippage (pips)."""
    return np.asarray(spread_pips, float) + COMMISSION_PIPS + SLIPPAGE_PIPS
