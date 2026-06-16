"""Causal UMAP wrapper: fit on train only, transform anything."""

from __future__ import annotations

import numpy as np
import umap

from scripts.fx_cluster import config


class Embedder:
    def __init__(self, n_components: int = config.UMAP_N_COMPONENTS,
                 n_neighbors: int = config.UMAP_N_NEIGHBORS,
                 min_dist: float = config.UMAP_MIN_DIST):
        self._um = umap.UMAP(
            n_components=n_components, n_neighbors=n_neighbors, min_dist=min_dist,
            random_state=config.RANDOM_SEED,
        )

    def fit(self, x: np.ndarray) -> Embedder:
        self._um.fit(np.asarray(x, dtype=float))
        return self

    def transform(self, x: np.ndarray) -> np.ndarray:
        return self._um.transform(np.asarray(x, dtype=float))
