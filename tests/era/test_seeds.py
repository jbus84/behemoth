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


def test_research_ideas_cover_adr_transfers():
    from scripts.era.seeds import RESEARCH_IDEAS

    blob = " ".join(RESEARCH_IDEAS).lower()
    for kw in ["pairwise", "pca", "covariance", "ewma", "dispersion change", "correlation"]:
        assert kw in blob, f"missing research idea keyword: {kw}"


def _nan_allclose(a, b, atol=1e-6):
    import numpy as np

    a = np.asarray(a, float)
    b = np.asarray(b, float)
    na, nb = np.isnan(a), np.isnan(b)
    if not np.array_equal(na, nb):
        return False
    return bool(np.allclose(a[~na], b[~nb], rtol=1e-5, atol=atol))


def test_vectorised_seeds_match_naive_reference_and_are_fast():
    """corr_weighted_graph & factor_resid are vectorised; assert they equal a
    naive trailing-window reference loop and run fast on a large input."""
    import time

    import numpy as np

    from scripts.era.context import CrossSectionContext
    from scripts.era.sandbox import run_program
    from scripts.era.seeds import SEED_PROGRAMS

    names = ["EURUSD", "GBPUSD", "AUDUSD", "USDJPY", "USDCHF", "USDCAD"]
    rng = np.random.default_rng(7)
    n = 600
    r = rng.standard_normal((n, 6))
    ctx = CrossSectionContext(r=r, names=names, target="EURUSD", usd_sign=1,
                              hour=(np.arange(n) % 24).astype(float))
    ti = ctx.target_idx
    pidx = ctx.peer_idx
    W = 250

    # naive references (the trailing-window definitions the vectorised seeds encode)
    def ref_factor():
        basket = r.mean(axis=1)
        out = np.full(n, np.nan)
        for k in range(n):
            lo = max(0, k - W)
            if k - lo < 20:
                continue
            x = basket[lo:k]
            yw = r[lo:k, ti]
            sxx = ((x - x.mean()) ** 2).sum()
            if abs(sxx) <= 1e-12:
                continue
            beta = ((x - x.mean()) * (yw - yw.mean())).sum() / sxx
            out[k] = r[k, ti] - beta * basket[k]
        return out

    def ref_corr():
        out = np.full(n, np.nan)
        for k in range(n):
            lo = max(0, k - W)
            if k - lo < 20:
                continue
            win = r[lo:k, :]
            tg = win[:, ti]
            w = np.zeros(len(pidx))
            for j, pj in enumerate(pidx):
                c = np.corrcoef(tg, win[:, pj])[0, 1]
                w[j] = c if np.isfinite(c) else 0.0
            sw = np.abs(w).sum()
            if sw <= 1e-9:
                continue
            w = w / sw
            out[k] = r[k, ti] - float(np.dot(w, r[k, pidx]))
        return out

    fr, err, _ = run_program(SEED_PROGRAMS["factor_resid"], ctx)
    assert err is None
    assert _nan_allclose(fr, ref_factor())

    cg, err, _ = run_program(SEED_PROGRAMS["corr_weighted_graph"], ctx)
    assert err is None
    assert _nan_allclose(cg, ref_corr())

    # fast on a large input (no per-bar python loop): both well under the 10s
    # sandbox timeout. Use a fresh big ctx.
    big = CrossSectionContext(r=rng.standard_normal((40000, 6)), names=names,
                              target="EURUSD", usd_sign=1)
    for seed in ("factor_resid", "corr_weighted_graph"):
        t0 = time.time()
        out, err, _ = run_program(SEED_PROGRAMS[seed], big)
        assert err is None, f"{seed}: {err}"
        assert time.time() - t0 < 8.0, f"{seed} too slow on 40k bars"
