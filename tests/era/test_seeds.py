import numpy as np

from scripts.era.context import CrossSectionContext
from scripts.era.sandbox import run_program
from scripts.era.seeds import RESEARCH_IDEAS, SEED_PROGRAMS


def test_all_seeds_validate_and_run():
    r = np.random.RandomState(2).randn(50, 6)
    ctx = CrossSectionContext(
        r=r, names=list("ABCDEF"), target="A", usd_sign=-1, hour=(np.arange(50) % 24)
    )
    assert {
        "loo_z",
        "robust_z",
        "graph_laplacian",
        "dispersion_rank",
        "loo_z_asia",
        "loo_z_highdisp",
    } <= set(SEED_PROGRAMS)
    for name, src in SEED_PROGRAMS.items():
        resid, err, logs = run_program(src, ctx, timeout=10.0)
        assert err is None, f"{name}: {err}"
        assert resid.shape == (50,)


def test_research_ideas_nonempty():
    assert len(RESEARCH_IDEAS) >= 4 and all(len(s) > 20 for s in RESEARCH_IDEAS)


def test_pairwise_median_seed_present_and_runs():
    import numpy as np

    from scripts.era.context import CrossSectionContext
    from scripts.era.sandbox import run_program
    from scripts.era.seeds import SEED_PROGRAMS

    assert "pairwise_median" in SEED_PROGRAMS
    rng = np.random.default_rng(0)
    ctx = CrossSectionContext(
        r=rng.standard_normal((50, 6)),
        names=["EURUSD", "GBPUSD", "AUDUSD", "USDJPY", "USDCHF", "USDCAD"],
        target="EURUSD",
        usd_sign=1,
        hour=(np.arange(50) % 24).astype(float),
    )
    resid, err, _ = run_program(SEED_PROGRAMS["pairwise_median"], ctx)
    assert err is None
    assert resid.shape == (50,)


def test_corr_weighted_graph_seed_present_and_causal():
    import numpy as np

    from scripts.era.context import CrossSectionContext
    from scripts.era.sandbox import causality_probe, run_program
    from scripts.era.seeds import SEED_PROGRAMS

    assert "corr_weighted_graph" in SEED_PROGRAMS
    rng = np.random.default_rng(2)
    ctx = CrossSectionContext(
        r=rng.standard_normal((140, 6)),
        names=["EURUSD", "GBPUSD", "AUDUSD", "USDJPY", "USDCHF", "USDCAD"],
        target="EURUSD",
        usd_sign=1,
        hour=(np.arange(140) % 24).astype(float),
    )
    resid, err, _ = run_program(SEED_PROGRAMS["corr_weighted_graph"], ctx)
    assert err is None
    ok, reason = causality_probe(SEED_PROGRAMS["corr_weighted_graph"], ctx, resid)
    assert ok, reason


def test_factor_resid_seed_present_and_causal():
    import numpy as np

    from scripts.era.context import CrossSectionContext
    from scripts.era.sandbox import causality_probe, run_program
    from scripts.era.seeds import SEED_PROGRAMS

    assert "factor_resid" in SEED_PROGRAMS
    rng = np.random.default_rng(4)
    ctx = CrossSectionContext(
        r=rng.standard_normal((140, 6)),
        names=["EURUSD", "GBPUSD", "AUDUSD", "USDJPY", "USDCHF", "USDCAD"],
        target="EURUSD",
        usd_sign=1,
        hour=(np.arange(140) % 24).astype(float),
    )
    resid, err, _ = run_program(SEED_PROGRAMS["factor_resid"], ctx)
    assert err is None
    ok, reason = causality_probe(SEED_PROGRAMS["factor_resid"], ctx, resid)
    assert ok, reason
