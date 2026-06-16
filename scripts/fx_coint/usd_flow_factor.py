"""Estimation-free USD-flow factor decomposition (no look-ahead: purely
cross-sectional at each t). Mirrors the price USD-factor trick (EW ≈ PC1)."""

from __future__ import annotations

import numpy as np


def orient(flow: np.ndarray, signs: np.ndarray) -> np.ndarray:
    """flow (T, P) -> oriented to USD strength via signs (P,) of +-1."""
    return flow * signs[None, :]


def usd_factor_residual(flow_oriented: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Dollar-flow factor = cross-pair mean (T,); residual = oriented - factor (T, P)."""
    factor = flow_oriented.mean(axis=1)
    residual = flow_oriented - factor[:, None]
    return factor, residual
