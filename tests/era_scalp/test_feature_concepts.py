# tests/era_scalp/test_feature_concepts.py
import numpy as np

from scripts.era_scalp.feature_concepts import (
    FEATURE_CONCEPT_TAXONOMY,
    FEATURE_SEED_COMPOSITIONS,
    composition_to_features_source,
)


def test_taxonomy_nonempty_and_seeds_present():
    assert len(FEATURE_CONCEPT_TAXONOMY) >= 4
    assert len(FEATURE_SEED_COMPOSITIONS) >= 2


def test_render_produces_runnable_build_features():
    comp = FEATURE_SEED_COMPOSITIONS[next(iter(FEATURE_SEED_COMPOSITIONS))]
    src = composition_to_features_source(comp["skeleton"], comp["operators"], comp.get("params", {}))
    assert "def build_features(ctx)" in src
    # exec it against a fake ctx-like object exposing .col/.X/.n_bars
    ns = {"np": np}
    exec(src, ns)

    class Ctx:
        def __init__(self, n, names):
            self.X = np.random.default_rng(0).standard_normal((n, len(names)))
            self.names = names
        @property
        def n_bars(self):
            return self.X.shape[0]
        def col(self, name):
            return self.X[:, self.names.index(name)]
    ctx = Ctx(200, ["vel_pips_h1", "signed_flow_24", "range_pips", "spread_pips", "tick_volume"])
    out = np.asarray(ns["build_features"](ctx), float)
    assert out.shape[0] == ctx.n_bars and out.ndim == 2 and out.shape[1] >= 1
    assert np.isfinite(out[10:]).any()
