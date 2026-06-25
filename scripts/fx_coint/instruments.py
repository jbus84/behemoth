from __future__ import annotations

from itertools import combinations

import numpy as np

MAJORS: list[str] = ["EURUSD", "GBPUSD", "USDJPY", "USDCHF", "USDCAD", "AUDUSD"]
CURRENCIES: list[str] = ["EUR", "GBP", "JPY", "CHF", "CAD", "AUD", "USD"]

# Each non-USD currency's log-value-in-USD as a signed unit weight on one major.
_CCY_LEG: dict[str, tuple[str, float]] = {
    "EUR": ("EURUSD", 1.0),
    "GBP": ("GBPUSD", 1.0),
    "AUD": ("AUDUSD", 1.0),
    "JPY": ("USDJPY", -1.0),
    "CHF": ("USDCHF", -1.0),
    "CAD": ("USDCAD", -1.0),
}


def ccy_weight(ccy: str) -> np.ndarray:
    """Weight vector over MAJORS for a currency's log-value-in-USD. USD -> zeros."""
    w = np.zeros(len(MAJORS))
    if ccy == "USD":
        return w
    major, sign = _CCY_LEG[ccy]
    w[MAJORS.index(major)] = sign
    return w


def instrument_weight(symbol: str) -> np.ndarray:
    """Weight vector over MAJORS for any 6-char pair XXXYYY (real or synthetic cross)."""
    base, quote = symbol[:3], symbol[3:]
    return ccy_weight(base) - ccy_weight(quote)


def all_pairs() -> list[str]:
    """All 21 tradeable instruments across the 7-currency complex."""
    out: list[str] = []
    for a, b in combinations(CURRENCIES, 2):
        sym = a + b
        # Skip degenerate (USD with itself never occurs); keep canonical order.
        out.append(sym)
    return out
