from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class CrossSectionContext:
    """Causal cross-section handed to a candidate program.

    r: (n_bars, n_symbols) USD-aligned vol-normalised returns (xs_ret_z),
       columns ordered by `names`. Carries NO forward/label data.
    """

    r: np.ndarray
    names: list[str]
    target: str
    usd_sign: int
    hour: np.ndarray | None = None

    @property
    def target_idx(self) -> int:
        return self.names.index(self.target)

    @property
    def peer_idx(self) -> list[int]:
        return [i for i in range(len(self.names)) if i != self.target_idx]

    @property
    def n_bars(self) -> int:
        return int(self.r.shape[0])

    def target_col(self) -> np.ndarray:
        return self.r[:, self.target_idx]

    def peers(self) -> np.ndarray:
        return self.r[:, self.peer_idx]

    def dispersion(self) -> np.ndarray:
        """Per-bar cross-sectional standard deviation of returns."""
        return self.r.std(axis=1)
