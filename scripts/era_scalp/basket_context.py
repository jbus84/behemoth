from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class BasketContext:
    """Causal cross-sectional basket context handed to a basket program.

    r: (n_bars, n_sym) time-ordered returns (or similar bar-level series).
    names: symbol names.
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
