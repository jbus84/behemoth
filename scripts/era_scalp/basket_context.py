from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass
class BasketContext:
    """Symmetric cross-section handed to a candidate basket program.

    r: (n_bars, n_sym) USD-aligned vol-normalised returns, columns ordered by `names`.
    Carries NO forward/label data. There is no 'target' — every symbol is rankable.
    """

    r: np.ndarray
    names: list[str]
    hour: np.ndarray | None = None

    @property
    def n_bars(self) -> int:
        return int(self.r.shape[0])

    @property
    def n_sym(self) -> int:
        return int(self.r.shape[1])

    def dispersion(self) -> np.ndarray:
        """Per-bar cross-sectional standard deviation of returns."""
        return self.r.std(axis=1)


@dataclass
class BasketSplit:
    """Panel data for one split (train/validation/holdout), aligned on a common bar grid.

    r:          (n_bars, n_sym) USD-aligned returns for ranking (the program input).
    y_fwd_panel:(n_bars, n_sym) each symbol's forward return at the build horizon.
    cost_panel: (n_bars, n_sym) each symbol's per-leg round-trip cost (pips).
    """

    r: np.ndarray
    y_fwd_panel: np.ndarray
    cost_panel: np.ndarray
    names: list[str]
    test_month: np.ndarray
    hour: np.ndarray | None = None
