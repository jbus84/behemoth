from __future__ import annotations

import numpy as np
import pandas as pd


def close_to_close_amplitude(res: pd.Series, entry_z: float = 1.0,
                             horizon: int = 1) -> float:
    """Mean reversion pnl captured per round-trip at close-to-close (taker FLOOR).

    For each deviation event (|z|>entry_z), the directional pnl of a mean-reversion
    trade held `horizon` bars: short the spread when above the mean, long when below,
    so captured = sign(z[t]) * (r[t] - r[t+horizon]). This earns the full traversal
    through the mean (including overshoot), unlike a |deviation|-shrinkage measure
    which reads zero on a symmetric overshoot. Averaged over ALL events (winners and
    losers) — no positive-only filter, which would cherry-pick and inflate the floor.
    """
    r = res.to_numpy()
    if r.std() == 0:
        return 0.0
    z = (r - r.mean()) / r.std()
    caps = [np.sign(z[t]) * (r[t] - r[t + horizon])
            for t in range(len(r) - horizon) if abs(z[t]) > entry_z]
    return float(np.mean(caps)) if caps else 0.0


def intrabar_excursion(fine_res: pd.Series, coarse_freq: str) -> pd.Series:
    """Per coarse window, the fine-residual peak-to-trough range (maker CEILING).

    This is the synchronous intrabar excursion of the spread itself (computed on
    the fine residual), NOT leg highs minus lows.
    """
    g = fine_res.resample(coarse_freq)
    return (g.max() - g.min()).dropna()


def amplitude_vs_cost(amplitude: float, cost_by_markup: dict) -> dict:
    """Amplitude / round-trip cost, one ratio per markup level."""
    return {mk: (amplitude / c if c > 0 else float("inf"))
            for mk, c in cost_by_markup.items()}
