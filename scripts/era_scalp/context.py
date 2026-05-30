from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class FeatureContext:
    """Causal single-symbol microstructure features handed to a scalping program.

    X: (n_bars, n_features) time-ordered, CAUSAL features only (no y_fwd, no cost).
       Column order matches `names`.
    """

    X: np.ndarray
    names: list[str]
    hour: np.ndarray | None = None

    @property
    def n_bars(self) -> int:
        return int(self.X.shape[0])

    def col(self, name: str) -> np.ndarray:
        try:
            j = self.names.index(name)
        except ValueError as e:
            raise KeyError(name) from e
        return self.X[:, j]
