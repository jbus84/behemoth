import numpy as np

from scripts.era_scalp.context import FeatureContext
from scripts.era_scalp.fair_seeds import BASELINE_SEED_NAMES, FAIR_SEED_PROGRAMS, RESEARCH_IDEAS
from scripts.era_scalp.load_splits import WHITELIST
from scripts.era_scalp.sandbox import causality_probe, run_program


def _ctx(n=400, seed=1):
    rng = np.random.default_rng(seed)
    return FeatureContext(X=rng.standard_normal((n, len(WHITELIST))),
                          names=list(WHITELIST), hour=(np.arange(n) % 24).astype(float))


def test_expected_seeds_present():
    for name in ("ewma_denoise_dev", "bounce_reversal_dev", "microprice_imbalance_dev",
                 "trailing_anchor_dev", "ofi_adjusted_dev"):
        assert name in FAIR_SEED_PROGRAMS
    for b in BASELINE_SEED_NAMES:
        assert b in FAIR_SEED_PROGRAMS


def test_all_seeds_run_causal_finite():
    ctx = _ctx()
    bad = []
    for name, src in FAIR_SEED_PROGRAMS.items():
        pred, err, _ = run_program(src, ctx, required_fn="fair")
        if err is not None:
            bad.append(f"{name}: {err}")
            continue
        ok, reason = causality_probe(src, ctx, pred, required_fn="fair")
        if not ok:
            bad.append(f"{name}: {reason}")
            continue
        finite = pred[np.isfinite(pred)]
        if finite.size and not np.isfinite(finite).all():
            bad.append(f"{name}: non-finite leak")
        if pred.shape[0] != ctx.n_bars:
            bad.append(f"{name}: wrong length")
    assert not bad, "; ".join(bad)


def test_research_ideas_cite_streams():
    blob = " ".join(RESEARCH_IDEAS).lower()
    for kw in ["micro-price", "efficient price", "bid-ask bounce", "order flow", "combine"]:
        assert kw in blob, f"missing idea keyword: {kw}"
