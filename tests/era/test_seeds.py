import numpy as np
from scripts.era.seeds import SEED_PROGRAMS, RESEARCH_IDEAS
from scripts.era.context import CrossSectionContext
from scripts.era.sandbox import run_program

def test_all_seeds_validate_and_run():
    r = np.random.RandomState(2).randn(50, 6)
    ctx = CrossSectionContext(r=r, names=list("ABCDEF"), target="A", usd_sign=-1)
    assert {"loo_z", "robust_z", "graph_laplacian", "dispersion_rank"} <= set(SEED_PROGRAMS)
    for name, src in SEED_PROGRAMS.items():
        resid, err, logs = run_program(src, ctx, timeout=10.0)
        assert err is None, f"{name}: {err}"
        assert resid.shape == (50,)

def test_research_ideas_nonempty():
    assert len(RESEARCH_IDEAS) >= 4 and all(len(s) > 20 for s in RESEARCH_IDEAS)
