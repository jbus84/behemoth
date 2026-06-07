import numpy as np

from scripts.era_scalp.crypto_boost_spec import (
    CryptoPanel,
    _filter_panel,
    _halve_panel,
    _sanitize,
    crypto_boost_spec,
    mutate_composition,
    recombine_compositions,
)
from scripts.era_scalp.crypto_feature_concepts import (
    CRYPTO_SEED_COMPOSITIONS,
    crypto_composition_to_source,
)
from scripts.era_scalp.era_engine import score_program


def _make_panel(n: int = 200, n_sym: int = 3, seed: int = 0) -> CryptoPanel:
    rng = np.random.default_rng(seed)
    symbols = [f"SYM{i}" for i in range(n_sym)]
    dt = np.arange(n)
    close = {s: 100.0 * np.cumsum(1 + rng.standard_normal(n) * 0.001) for s in symbols}
    ofi = {s: rng.standard_normal(n) * 0.1 for s in symbols}
    vol = {s: rng.uniform(100, 1000, n) for s in symbols}
    return_1h = {}
    for s in symbols:
        c = close[s]
        r = np.full(n, np.nan)
        r[1:] = (c[1:] - c[:-1]) / np.maximum(np.abs(c[:-1]), 1e-12)
        return_1h[s] = r
    test_month = np.array([f"2024-{1 + (i // 30) % 12:02d}" for i in range(n)])
    hour_utc = (np.arange(n) % 24).astype(float)
    return CryptoPanel(
        symbols=symbols, dt=dt, close=close, ofi=ofi, vol=vol,
        return_1h=return_1h, test_month=test_month, hour_utc=hour_utc,
    )


def test_filter_panel_preserves_shape():
    panel = _make_panel(n=100)
    mask = np.ones(100, bool)
    mask[50:] = False
    filtered = _filter_panel(panel, mask)
    assert filtered.n_bars == 50
    assert filtered.symbols == panel.symbols
    assert np.allclose(filtered.close[panel.symbols[0]], panel.close[panel.symbols[0]][:50])


def test_halve_panel_splits_evenly():
    panel = _make_panel(n=100)
    a, b = _halve_panel(panel)
    assert a.n_bars == 50
    assert b.n_bars == 50
    assert np.allclose(a.close[panel.symbols[0]], panel.close[panel.symbols[0]][:50])
    assert np.allclose(b.close[panel.symbols[0]], panel.close[panel.symbols[0]][50:])


def test_sanitize_empty_payload():
    assert _sanitize("garbage") == {"skeleton": "default", "operators": {}, "params": {"w": 24}}


def test_sanitize_filters_invalid_concepts():
    comp = {"operators": {"a": "ofi_ma", "b": "nonexistent"}, "params": {"w": 12}}
    out = _sanitize(comp)
    assert out["operators"] == {"a": "ofi_ma"}
    assert out["params"]["w"] == 12


def test_mutate_composition_returns_dict():
    parent = CRYPTO_SEED_COMPOSITIONS["flow_raw"]
    child, prior = mutate_composition(parent, 0.0, "", "", seed=42)
    assert isinstance(child, dict)
    assert "operators" in child
    assert "params" in child
    assert 0.0 <= prior <= 1.0


def test_recombine_compositions_unions_operators():
    a = CRYPTO_SEED_COMPOSITIONS["flow_raw"]
    b = CRYPTO_SEED_COMPOSITIONS["flow_momentum"]
    merged, prior = recombine_compositions(a, 1.0, b, 0.0)
    ops = merged["operators"]
    assert "ofi_ma" in ops.values()
    # Params should favour higher-scoring parent (a)
    assert merged["params"]["w"] == a["params"]["w"]


def test_crypto_boost_spec_fields():
    train = _make_panel(n=120)
    spec = crypto_boost_spec(train, horizon=6, seed_only=True)
    assert spec.required_fn == "build_features"
    assert spec.grid_h == [6]
    assert spec.atomic_mode is True
    assert spec.name == "crypto_flow_h6"


def test_score_frame_runs_on_seed():
    train = _make_panel(n=120)
    val = _make_panel(n=120, seed=1)
    spec = crypto_boost_spec(train, horizon=6, seed=0)
    seed_src = crypto_composition_to_source(
        "default",
        CRYPTO_SEED_COMPOSITIONS["flow_raw"]["operators"],
        CRYPTO_SEED_COMPOSITIONS["flow_raw"].get("params", {}),
    )
    value, mean, se, logs = score_program(seed_src, spec, val)
    # Should not crash; value may be negative with random data but finite
    assert np.isfinite(value) or value == -1e6
    assert isinstance(logs, str)


def test_score_frame_portfolio_shape():
    panel = _make_panel(n=50)
    # Fake predictions matrix
    preds = np.random.randn(50, 3)
    spec = crypto_boost_spec(panel, horizon=6, seed_only=True)
    frame = spec.score_frame(preds, panel, 0.90, 6)
    assert isinstance(frame, dict) or hasattr(frame, "__len__")
    # Frame should have net and test_month columns when there are rebalances
    if len(frame) > 0:
        assert "net" in frame.columns
        assert "test_month" in frame.columns
        assert "gross" in frame.columns
        assert "cost" in frame.columns
