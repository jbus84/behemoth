import numpy as np

from scripts.era_scalp.era_xs import crosssym_spec, xs_score_frame


class _XSSplit:
    def __init__(self, n, seed):
        rng = np.random.default_rng(seed)
        self.r = rng.standard_normal((n, 6))
        self.names = ["EURUSD", "GBPUSD", "AUDUSD", "USDJPY", "USDCHF", "USDCAD"]
        self.target = "EURUSD"
        self.usd_sign = 1
        self.hour = (np.arange(n) % 24).astype(float)
        self.y_fwd = rng.standard_normal(n) * 0.5
        self.cost = np.full(n, 0.2)
        self.test_month = np.array([f"2025-{1 + (i // 100) % 6:02d}" for i in range(n)])


def test_xs_score_frame_returns_net_frame():
    s = _XSSplit(600, 1)
    df = xs_score_frame(s.r[:, 0], s, q=0.9, h=3)
    assert set(df.columns) == {"net", "test_month"}
    assert 0 < len(df) <= 600


def test_xs_score_frame_q_controls_count():
    s = _XSSplit(800, 2)
    n_all = len(xs_score_frame(s.r[:, 0], s, q=0.0, h=3))      # trade all finite
    n_top = len(xs_score_frame(s.r[:, 0], s, q=0.95, h=3))     # only top 5%
    assert n_top < n_all


def test_xs_score_frame_side_is_fade_usd_aligned():
    # constant +ve residual, usd_sign=1 -> side = -1; with y_fwd=+1, cost=0 -> net = -1
    s = _XSSplit(50, 3)
    s.y_fwd = np.ones(50)
    s.cost = np.zeros(50)
    out = np.full(50, 2.0)
    df = xs_score_frame(out, s, q=0.0, h=3)
    assert np.allclose(df["net"].to_numpy(), -1.0)


def test_crosssym_spec_shape():
    spec = crosssym_spec()
    assert spec.required_fn == "residual"
    assert spec.score_frame is xs_score_frame
    assert spec.aggregate == "robust"
    assert spec.grid_h == [3]
    assert "loo_z" in spec.seed_programs and "factor_resid" in spec.seed_programs
    assert callable(spec.propose) and callable(spec.recombine)
    # adapters must accept (and ignore) required_fn without error
    assert callable(spec.run_program) and callable(spec.causality_probe)


def test_crosssym_spec_atomic_mode():
    spec = crosssym_spec(atomic_mode=True)
    assert spec.atomic_mode is True
    assert spec.seed_programs is None
    assert spec.seed_compositions is not None
    assert "loo_z" in spec.seed_compositions
    assert "factor_resid" in spec.seed_compositions
    assert spec.render_payload is not None
    assert spec.propose_atomic is not None
    assert spec.recombine_atomic is not None
    assert spec.concept_taxonomy is not None
    assert spec.sanitize_composition is not None
    assert spec.extract_concepts is not None
    assert spec.dimension_locked is True
    assert spec.self_correct is False
    assert spec.parallel_expansions == 2
    # branch tags should map to concept categories, not seed names
    assert spec.branch_tags["loo_z"] == "base"
    assert spec.branch_tags["loo_z_asia"] == "base"
