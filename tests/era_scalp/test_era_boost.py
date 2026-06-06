import numpy as np
from scripts.era_scalp.load_splits import TradeSplitData
from scripts.era_scalp.feature_concepts import FEATURE_SEED_COMPOSITIONS, composition_to_features_source
from scripts.era_scalp.era_boost import boost_spec
from scripts.era_scalp.era_engine import score_program


def _split(n=1200, seed=0):
    rng = np.random.default_rng(seed)
    names = ["vel_pips_h1", "signed_flow_24", "range_pips", "spread_pips", "tick_volume",
             "quote_revision_rate_z"]
    X = rng.standard_normal((n, len(names)))
    return TradeSplitData(
        X=X, names=names, hour=(np.arange(n) % 24).astype(float),
        mid=1.1 + np.cumsum(rng.standard_normal(n)) * 1e-4,
        cost=np.full(n, 0.2),
        test_month=np.array([f"2024-{1 + (i // 100) % 12:02d}" for i in range(n)]),
        spread_pips=np.full(n, 0.2),
    )


def _seed_src():
    c = FEATURE_SEED_COMPOSITIONS["flow_vol"]
    return composition_to_features_source(c["skeleton"], c["operators"], c.get("params", {}))


def test_boost_spec_fields():
    spec = boost_spec(_split(), symbol="EURUSD", target="forward", horizon=12)
    assert spec.required_fn == "build_features"
    assert spec.grid_h == [12]


def test_score_program_runs_end_to_end():
    train = _split(seed=1)
    spec = boost_spec(train, symbol="EURUSD", target="forward", horizon=12)
    val = _split(seed=2)
    value, mean, se, logs = score_program(_seed_src(), spec, val)
    assert np.isfinite(value) and value > -1e6, logs
