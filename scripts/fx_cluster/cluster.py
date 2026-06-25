"""HDBSCAN wrapper: fit on train embedding, assign OOS via approximate_predict."""

from __future__ import annotations

import hdbscan
import numpy as np

from scripts.fx_cluster import config


class Clusterer:
    def __init__(self, min_cluster_size: int = config.HDBSCAN_MIN_CLUSTER_SIZE,
                 min_samples: int = config.HDBSCAN_MIN_SAMPLES,
                 cluster_selection_method: str = config.HDBSCAN_CLUSTER_SELECTION):
        self._h = hdbscan.HDBSCAN(
            min_cluster_size=min_cluster_size, min_samples=min_samples,
            cluster_selection_method=cluster_selection_method,
            prediction_data=True,
        )
        self.labels_: np.ndarray = np.array([])

    def fit(self, z: np.ndarray) -> Clusterer:
        self.labels_ = self._h.fit_predict(np.asarray(z, dtype=float))
        return self

    def predict(self, z: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        labels, strengths = hdbscan.approximate_predict(self._h, np.asarray(z, dtype=float))
        return labels, strengths
