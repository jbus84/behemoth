import numpy as np
import pytest

# umap-learn/hdbscan are isolated-env-only deps (cluster-regimes was a NO-GO);
# skip the module when they are absent (e.g. CI).
pytest.importorskip("umap")
pytest.importorskip("hdbscan")

from scripts.fx_cluster.cluster import Clusterer  # noqa: E402
from scripts.fx_cluster.embed import Embedder  # noqa: E402


def _three_blobs(seed=0):
    rng = np.random.default_rng(seed)
    a = rng.normal([-5, -5], 0.3, (200, 2))
    b = rng.normal([5, 5], 0.3, (200, 2))
    c = rng.normal([-5, 5], 0.3, (200, 2))
    return np.vstack([a, b, c])


def test_embedder_fits_train_and_transforms_test_to_same_dim():
    x = _three_blobs()
    emb = Embedder(n_components=2).fit(x)
    z_train = emb.transform(x)
    z_test = emb.transform(_three_blobs(seed=1))
    assert z_train.shape == (600, 2)
    assert z_test.shape[1] == 2


def test_clusterer_recovers_blobs_and_predicts_oos():
    x = _three_blobs()
    clu = Clusterer(min_cluster_size=50, min_samples=5).fit(x)
    labels = clu.labels_
    assert len(set(labels) - {-1}) == 3
    new_labels, strengths = clu.predict(_three_blobs(seed=2))
    assert new_labels.shape == (600,)
    assert strengths.shape == (600,)
