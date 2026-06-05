import numpy as np

from scripts.era.context import CrossSectionContext
from scripts.era.sandbox import causality_probe, run_program
from scripts.era.score_program import SplitData
from scripts.era_scalp.era_engine import run_search_rich
from scripts.era_scalp.era_xs import crosssym_spec
from scripts.era_scalp.xs_atomic_concepts import (
    XS_BASE_OPERATORS,
    XS_CONCEPT_TAXONOMY,
    XS_GATE_OPERATORS,
    XS_NORMALIZATION_OPERATORS,
    XS_SEED_COMPOSITIONS,
    XS_SMOOTHING_OPERATORS,
    composition_to_source,
    extract_concepts_from_composition,
    render_composition,
)


def _ctx(n=600, seed=0):
    rng = np.random.default_rng(seed)
    r = rng.standard_normal((n, 6))
    names = ["EURUSD", "GBPUSD", "AUDUSD", "USDJPY", "USDCHF", "USDCAD"]
    return CrossSectionContext(
        r=r,
        names=names,
        target="EURUSD",
        usd_sign=1,
        hour=(np.arange(n) % 24).astype(float),
    )


def test_seed_compositions_all_causal():
    """Every seed composition must render, run, and pass the causality probe."""
    ctx = _ctx()
    for name, comp in XS_SEED_COMPOSITIONS.items():
        src = composition_to_source(comp)
        out, err, _ = run_program(src, ctx)
        assert err is None, f"{name}: run error: {err}"
        assert out is not None, f"{name}: no output"
        assert out.shape == (ctx.n_bars,), f"{name}: shape mismatch"
        ok, reason = causality_probe(src, ctx, out)
        assert ok, f"{name}: causality probe failed: {reason}"


def test_all_operators_causal():
    """Every concept in every slot must produce a causal program when used alone."""
    ctx = _ctx()
    slot_specs = {
        "base": XS_BASE_OPERATORS,
        "gate": XS_GATE_OPERATORS,
        "smoothing": XS_SMOOTHING_OPERATORS,
        "normalization": XS_NORMALIZATION_OPERATORS,
    }
    for slot, ops in slot_specs.items():
        for op_name in ops:
            comp = {"skeleton": "xs_residual", "operators": {slot: op_name}, "params": {}}
            src = composition_to_source(comp)
            out, err, _ = run_program(src, ctx)
            assert err is None, f"{slot}/{op_name}: run error: {err}"
            assert out is not None, f"{slot}/{op_name}: no output"
            ok, reason = causality_probe(src, ctx, out)
            assert ok, f"{slot}/{op_name}: causality: {reason}"


def test_full_pipeline_composition_causal():
    """A composition using all four slots must be causal."""
    ctx = _ctx()
    comp = {
        "skeleton": "xs_residual",
        "operators": {
            "base": "factor_resid",
            "smoothing": "ewma",
            "normalization": "vol_scale",
            "gate": "high_dispersion",
        },
        "params": {"alpha": 0.1, "W": 20},
    }
    src = composition_to_source(comp)
    out, err, _ = run_program(src, ctx)
    assert err is None, err
    assert out is not None
    ok, reason = causality_probe(src, ctx, out)
    assert ok, reason


def test_loo_z_rendering_oracle():
    """Pin the exact rendered source for the loo_z seed (regression guard)."""
    comp = XS_SEED_COMPOSITIONS["loo_z"]
    src = composition_to_source(comp)
    expected = (
        "def residual(ctx):\n"
        "    r = ctx.r\n"
        "    n = r.shape[0]\n"
        "        # Base: leave-one-out basket z (target vs peer mean/std)\n"
        "    t = ctx.target_col(); p = ctx.peers()\n"
        "    raw = (t - p.mean(axis=1)) / (p.std(axis=1) + 1e-9)\n"
        "        # Smoothing: none (passthrough)\n"
        "    smoothed = raw\n"
        "        # Normalization: none (passthrough)\n"
        "    normalized = smoothed\n"
        "        # Gate: pass-through (no gating)\n"
        "    mask = np.ones(n, dtype=bool)\n"
        "    return np.where(mask, normalized, np.nan)\n"
    )
    assert src == expected, f"loo_z rendering mismatch:\n{src}"


def test_extract_concepts_from_composition():
    comp = {
        "skeleton": "xs_residual",
        "operators": {"base": "loo_z", "gate": "asia_session", "smoothing": "ewma"},
        "params": {"alpha": 0.1},
    }
    concepts = extract_concepts_from_composition(comp)
    assert set(concepts) == {"loo_z", "asia_session", "ewma"}


def test_concept_taxonomy_coverage():
    """Every operator must be registered in the taxonomy."""
    all_ops = {
        **XS_BASE_OPERATORS,
        **XS_GATE_OPERATORS,
        **XS_SMOOTHING_OPERATORS,
        **XS_NORMALIZATION_OPERATORS,
    }
    for name in all_ops:
        assert name in XS_CONCEPT_TAXONOMY, f"{name} missing from taxonomy"


def test_default_params_substitution():
    """Parameters with no explicit value get sensible defaults."""
    comp = {
        "skeleton": "xs_residual",
        "operators": {"base": "loo_z", "smoothing": "ewma", "normalization": "vol_scale"},
        "params": {},  # empty — rely on defaults
    }
    src = composition_to_source(comp)
    assert "alpha = 0.5" in src  # default for {{alpha}}
    assert "W = 20" in src       # default for {{W}}


def test_render_composition_missing_slots_get_defaults():
    """A composition with only 'base' must still produce a valid program."""
    src = render_composition("xs_residual", {"base": "robust_z"})
    assert "raw = (ctx.target_col() - med) / (1.4826 * mad)" in src
    assert "smoothed = raw" in src
    assert "normalized = smoothed" in src
    assert "mask = np.ones(n, dtype=bool)" in src


def _mock_split(n=1200, seed=0):
    rng = np.random.default_rng(seed)
    names = ["EURUSD", "GBPUSD", "AUDUSD", "USDJPY", "USDCHF", "USDCAD"]
    return SplitData(
        r=rng.standard_normal((n, 6)),
        names=names,
        target="EURUSD",
        usd_sign=1,
        y_fwd=rng.standard_normal(n) * 0.5,
        cost=np.full(n, 0.2),
        test_month=np.array([f"2025-{1 + (i // 130) % 6:02d}" for i in range(n)]),
        hour=(np.arange(n) % 24).astype(float),
    )


def test_run_search_rich_atomic_mode(tmp_path, monkeypatch):
    """End-to-end: atomic cross-symbol spec + run_search_rich with deterministic stubs."""
    monkeypatch.setattr(
        "scripts.era.llm._ollama_caller", lambda prompt: ""
    )
    monkeypatch.setattr(
        "scripts.era.llm.propose_xs_atomic_change",
        lambda *a, **k: ({"skeleton": "xs_residual", "operators": {"base": "loo_z"}, "params": {}}, 0.5),
    )
    monkeypatch.setattr(
        "scripts.era.llm.recombine_xs_atomic_compositions",
        lambda *a, **k: ({"skeleton": "xs_residual", "operators": {"base": "robust_z"}, "params": {}}, 0.5),
    )

    splits = {"validation": _mock_split(), "holdout": _mock_split(seed=1)}
    spec = crosssym_spec(atomic_mode=True)
    nodes = run_search_rich(
        spec, splits, budget=4, seed=0, cache_dir=str(tmp_path)
    )

    assert len(nodes) == len(XS_SEED_COMPOSITIONS) + 4
    valid = [n for n in nodes if n.score > -1e6 + 1]
    assert len(valid) > 0

    # Seeds must be composition dicts in atomic mode
    seeds = [n for n in nodes if n.parent is None]
    assert all(isinstance(n.payload, dict) for n in seeds)
    seed_concepts = {tuple(extract_concepts_from_composition(n.payload)) for n in seeds}
    expected_concepts = {tuple(extract_concepts_from_composition(comp)) for comp in XS_SEED_COMPOSITIONS.values()}
    assert seed_concepts == expected_concepts
