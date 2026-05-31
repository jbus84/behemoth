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
                 "efficiency_gated_fade", "extreme_fade", "vr_conditional_direction"):
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
    for name in ("vr_gated_fade", "autocorr_gated_fade", "efficiency_gated_fade", "extreme_fade", "vr_conditional_direction"):
        sig, err, _ = run_program(FADE_SEED_PROGRAMS[name], ctx, required_fn="signal")
        assert err is None
        assert np.isnan(sig).any(), f"{name} never abstains"


def test_research_ideas_cite_streams():
    blob = " ".join(RESEARCH_IDEAS).lower()
    for kw in ["variance ratio", "half-life", "efficiency ratio", "extreme", "combine"]:
        assert kw in blob, f"missing idea keyword: {kw}"


def _vel_ctx(vel):
    """A FeatureContext whose vel_pips_h1 column is a chosen series (other columns zero)."""
    vel = np.asarray(vel, float)
    n = vel.shape[0]
    X = np.zeros((n, len(WHITELIST)))
    X[:, list(WHITELIST).index("vel_pips_h1")] = vel
    return FeatureContext(X=X, names=list(WHITELIST), hour=(np.arange(n) % 24).astype(float))


def _dev_ref(vel):
    """Replicate the seed's _FAIR block to get dev = fair - mid for assertions."""
    r = np.asarray(vel, float)
    n = r.shape[0]
    a = 0.05
    p = np.cumsum(np.where(np.isfinite(r), r, 0.0))
    ew = np.empty(n)
    acc = p[0]
    for i in range(n):
        acc = (1 - a) * acc + a * p[i]
        ew[i] = acc
    return ew - p


def test_vr_conditional_fades_in_reverting_regime():
    # Alternating increments => price oscillates => 20-step move ~0 => VR ~0 (<0.95) everywhere.
    # The whole finite set must be the FADE side: out == dev exactly.
    vel = np.where(np.arange(1500) % 2 == 0, 1.0, -1.0)
    sig, err, _ = run_program(FADE_SEED_PROGRAMS["vr_conditional_direction"], _vel_ctx(vel),
                              required_fn="signal")
    assert err is None
    dev = _dev_ref(vel)
    fin = np.isfinite(sig)
    assert fin.any()
    assert np.allclose(sig[fin], dev[fin]), "reverting regime must return +dev (fade)"


def test_vr_conditional_continues_in_trending_regime():
    # Positively autocorrelated increments (AR(1), phi=0.9) => persistent => VR>1 => CONTINUE side.
    rng = np.random.default_rng(0)
    e = rng.standard_normal(1500)
    vel = np.zeros(1500)
    for i in range(1, 1500):
        vel[i] = 0.9 * vel[i - 1] + e[i]
    sig, err, _ = run_program(FADE_SEED_PROGRAMS["vr_conditional_direction"], _vel_ctx(vel),
                              required_fn="signal")
    assert err is None
    dev = _dev_ref(vel)
    fin = np.isfinite(sig)
    assert fin.sum() > 0
    cont = np.isclose(sig[fin], -dev[fin])
    assert cont.mean() > 0.7, f"trending regime should mostly CONTINUE (-dev); got {cont.mean():.2f}"


def test_vr_conditional_magnitude_equals_dev():
    # Invariant: |signal| == |dev| wherever finite (only the side flips by regime).
    ctx = _ctx()
    sig, err, _ = run_program(FADE_SEED_PROGRAMS["vr_conditional_direction"], ctx,
                              required_fn="signal")
    assert err is None
    dev = _dev_ref(ctx.col("vel_pips_h1"))
    fin = np.isfinite(sig)
    assert fin.any()
    assert np.allclose(np.abs(sig[fin]), np.abs(dev[fin]))


def test_vr_conditional_deadband_abstains_more_than_reverting():
    # A random walk (iid increments) has VR ~1 => most bars land in the [0.95,1.05] dead-band
    # and abstain, so its NaN fraction exceeds the strongly-reverting series' NaN fraction.
    rng = np.random.default_rng(2)
    rw = rng.standard_normal(1500)
    revert = np.where(np.arange(1500) % 2 == 0, 1.0, -1.0)
    src = FADE_SEED_PROGRAMS["vr_conditional_direction"]
    sig_rw, e1, _ = run_program(src, _vel_ctx(rw), required_fn="signal")
    sig_rev, e2, _ = run_program(src, _vel_ctx(revert), required_fn="signal")
    assert e1 is None and e2 is None
    assert np.isnan(sig_rw).mean() > np.isnan(sig_rev).mean()
