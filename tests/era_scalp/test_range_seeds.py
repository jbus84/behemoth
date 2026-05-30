import numpy as np

from scripts.era_scalp.context import FeatureContext
from scripts.era_scalp.load_splits import WHITELIST
from scripts.era_scalp.range_seeds import BASELINE_SEED_NAMES, DEPLOY_SEED_PROGRAMS, RESEARCH_IDEAS
from scripts.era_scalp.sandbox import causality_probe, run_program


def _ctx(n=400, seed=1):
    rng = np.random.default_rng(seed)
    X = np.abs(rng.standard_normal((n, len(WHITELIST))))
    return FeatureContext(X=X, names=list(WHITELIST), hour=(np.arange(n) % 24).astype(float))


def test_expected_seeds_present():
    for name in ("range_vol_deploy", "meanrev_regime_deploy", "toxicity_gate_deploy",
                 "burst_veto_deploy", "spread_harvest_deploy"):
        assert name in DEPLOY_SEED_PROGRAMS
    for b in BASELINE_SEED_NAMES:
        assert b in DEPLOY_SEED_PROGRAMS


def test_all_seeds_run_causal_and_nondirectional():
    ctx = _ctx()
    bad = []
    for name, src in DEPLOY_SEED_PROGRAMS.items():
        sig, err, _ = run_program(src, ctx, required_fn="deploy")
        if err is not None:
            bad.append(f"{name}: {err}")
            continue
        ok, reason = causality_probe(src, ctx, sig, required_fn="deploy")
        if not ok:
            bad.append(f"{name}: {reason}")
            continue
        finite = sig[np.isfinite(sig)]
        if finite.size and finite.min() < 0:
            bad.append(f"{name}: emitted negative (should be non-directional >=0 or nan)")
    assert not bad, "; ".join(bad)


def test_research_ideas_cite_streams_and_combination():
    blob = " ".join(RESEARCH_IDEAS).lower()
    for kw in ["realized range", "variance ratio", "vpin", "hawkes", "avellaneda", "combine"]:
        assert kw in blob, f"missing idea keyword: {kw}"
