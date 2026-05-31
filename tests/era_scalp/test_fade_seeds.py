import numpy as np

from scripts.era_scalp.context import FeatureContext
from scripts.era_scalp.fade_seeds import BASELINE_SEED_NAMES, FADE_SEED_PROGRAMS, RESEARCH_IDEAS
from scripts.era_scalp.load_splits import WHITELIST
from scripts.era_scalp.sandbox import causality_probe, run_program


def _ctx(n=400, seed=1):
    rng = np.random.default_rng(seed)
    return FeatureContext(X=rng.standard_normal((n, len(WHITELIST))),
                          names=list(WHITELIST), hour=(np.arange(n) % 24).astype(float))


def test_expected_seeds_present():
    for name in ("fair_fade", "vr_gated_fade", "autocorr_gated_fade",
                 "efficiency_gated_fade", "extreme_fade"):
        assert name in FADE_SEED_PROGRAMS
    for b in BASELINE_SEED_NAMES:
        assert b in FADE_SEED_PROGRAMS


def test_all_seeds_run_causal():
    ctx = _ctx()
    bad = []
    for name, src in FADE_SEED_PROGRAMS.items():
        sig, err, _ = run_program(src, ctx, required_fn="signal")
        if err is not None:
            bad.append(f"{name}: {err}")
            continue
        ok, reason = causality_probe(src, ctx, sig, required_fn="signal")
        if not ok:
            bad.append(f"{name}: {reason}")
            continue
        if sig.shape[0] != ctx.n_bars:
            bad.append(f"{name}: wrong length")
    assert not bad, "; ".join(bad)


def test_gated_seeds_abstain_sometimes():
    ctx = _ctx()
    for name in ("vr_gated_fade", "autocorr_gated_fade", "efficiency_gated_fade", "extreme_fade"):
        sig, err, _ = run_program(FADE_SEED_PROGRAMS[name], ctx, required_fn="signal")
        assert err is None
        assert np.isnan(sig).any(), f"{name} never abstains"


def test_research_ideas_cite_streams():
    blob = " ".join(RESEARCH_IDEAS).lower()
    for kw in ["variance ratio", "half-life", "efficiency ratio", "extreme", "combine"]:
        assert kw in blob, f"missing idea keyword: {kw}"
