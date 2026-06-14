"""Continuous-time, tick-by-tick scalping research (the "tape reader").

Every other model in this repo aggregates ticks into bars and decides at bar
boundaries. This package instead replays the raw bid/ask quote stream one tick at
a time and runs a continuous state machine: a Kalman micro-price estimator filters
quote-bounce noise, a regime + extremum detector reads the tape, and a swappable
``TickPolicy`` decides enter/exit per tick with tick-exact fills.

The ``TickPolicy.decide(state) -> Action`` contract is intentionally the same shape
the ERA PUCT writer fills in, so a passing Day-1 prototype can later be wrapped in a
``RunSpec`` and optimised by ``scripts.era_scalp.era_engine.run_era_search`` unchanged.
"""

PIP = {
    "EURUSD": 1e-4,
    "GBPUSD": 1e-4,
    "AUDUSD": 1e-4,
    "USDCHF": 1e-4,
    "USDCAD": 1e-4,
    "USDJPY": 1e-2,
}


def pip_size(symbol: str) -> float:
    """Pip size for ``symbol`` (1e-4 for most majors, 1e-2 for JPY crosses)."""
    return PIP[str(symbol).upper()]
