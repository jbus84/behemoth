"""Synthetic tick streams for era_tick unit tests (no disk / feed access)."""

from __future__ import annotations

import numpy as np
import pandas as pd

from scripts.era_tick.tick_replay import TickReplay


def make_frame(
    mids: np.ndarray,
    *,
    spread_pips: float = 0.2,
    pip: float = 1.0e-4,
    start: str = "2024-01-02 08:00:00",
) -> pd.DataFrame:
    """Build a [timestamp, bid, ask] frame from a mid path with a constant spread."""
    n = len(mids)
    ts = pd.date_range(start=start, periods=n, freq="100ms", tz="UTC")
    half = 0.5 * spread_pips * pip
    return pd.DataFrame({"timestamp": ts, "bid": mids - half, "ask": mids + half})


def ramp(n: int = 200, slope_pips: float = 0.05, base: float = 1.10, pip: float = 1.0e-4):
    return base + np.arange(n) * slope_pips * pip


def oscillation(
    n: int = 1500,
    amp_pips: float = 6.0,
    period: int = 80,
    noise_pips: float = 0.6,
    base: float = 1.10,
    pip: float = 1.0e-4,
    seed: int = 7,
) -> np.ndarray:
    """Triangle-ish oscillation + noise: the habitat a fade policy is meant to trade."""
    rng = np.random.default_rng(seed)
    t = np.arange(n)
    wave = amp_pips * pip * (2.0 / np.pi) * np.arcsin(np.sin(2 * np.pi * t / period))
    noise = rng.normal(0.0, noise_pips * pip, size=n)
    return base + wave + noise


def replay_from(
    mids: np.ndarray, *, symbol: str = "EURUSD", spread_pips: float = 0.2
) -> TickReplay:
    return TickReplay(symbol, make_frame(mids, spread_pips=spread_pips))
