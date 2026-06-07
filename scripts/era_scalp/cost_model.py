from __future__ import annotations

import numpy as np

COMMISSION_PIPS = 0.06   # Dukascopy round-trip commission (~0.03/side)
SLIPPAGE_PIPS = 0.10     # buffer for adverse fills at extreme-dislocation bars

# Crypto exchange fee assumptions (bps per side, round-trip = 2× side)
CRYPTO_TAKER_FEE_BPS = 7.5   # Binance retail taker (~0.075%)
CRYPTO_MAKER_FEE_BPS = 1.0   # Binance retail maker (~0.01%)


def realistic_cost(spread_pips) -> np.ndarray:
    """Per-bar realistic round-trip taker cost: bar spread + commission + slippage (pips)."""
    return np.asarray(spread_pips, float) + COMMISSION_PIPS + SLIPPAGE_PIPS


def crypto_taker_cost_bps(turnover: float) -> float:
    """Taker round-trip cost in bps given turnover fraction (0–2 for full rebalance)."""
    return turnover * CRYPTO_TAKER_FEE_BPS


def crypto_maker_cost_bps(turnover: float) -> float:
    """Maker fee cost in bps (adverse selection is applied separately in the scorer)."""
    return turnover * CRYPTO_MAKER_FEE_BPS
