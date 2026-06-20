import numpy as np

from scripts.fx_coint.pf_core import PFParams, RBParticleFilter, run_filter


def test_init_shapes_and_normalized_weights():
    pf = RBParticleFilter(PFParams(n_particles=200, seed=1))
    assert pf.regime.shape == (200,)
    assert set(np.unique(pf.regime)).issubset({0, 1})
    assert pf.mu_mean.shape == (200,)
    assert np.isclose(np.exp(pf.logw).sum(), 1.0)

def test_predict_tilts_only_trend_particles():
    pf = RBParticleFilter(PFParams(n_particles=2000, q_mu=0.0, phi_trend=1.0,
                                   phi_revert=1.0, tilt_gain=1.0, seed=2))
    pf.mu_mean[:] = 0.0
    pf.predict(tilt=1.0)
    # trend particles (regime 0) that did NOT switch get +1.0; the cross-sectional
    # mean drift must be strictly positive because trend particles were nudged up.
    assert pf.mu_mean.mean() > 0.1
    # predict applies the AR(1) Kalman variance time-update phi^2*var + q_mu per
    # particle; from mu0_var=1.0 (above the stationary variance) it CONTRACTS.
    pf2 = RBParticleFilter(PFParams(n_particles=500, q_mu=0.04, seed=3))
    pf2.predict(tilt=0.0)
    expect_trend = pf2.p.phi_trend ** 2 * 1.0 + pf2.p.q_mu
    expect_revert = pf2.p.phi_revert ** 2 * 1.0 + pf2.p.q_mu
    is_trend = pf2.regime == 0
    assert np.allclose(pf2.mu_var[is_trend], expect_trend)
    assert np.allclose(pf2.mu_var[~is_trend], expect_revert)


def test_systematic_resample_favors_heavy_weights():
    rng = np.random.default_rng(0)
    w = np.array([0.0, 0.0, 1.0, 0.0])
    idx = RBParticleFilter.systematic_resample(w, rng)
    assert np.all(idx == 2)


def test_update_pulls_posterior_drift_toward_persistent_signal():
    pf = RBParticleFilter(PFParams(n_particles=3000, q_mu=0.02, r_obs=0.3, seed=5))
    for _ in range(15):
        pf.predict(tilt=0.0)
        pf.update(r_obs_value=1.0)   # persistent positive vol-normalized return
    p_trend, mu_hat, mu_var = pf.posterior()
    assert mu_hat > 0.3            # posterior drift turned positive
    assert 0.0 <= p_trend <= 1.0
    assert mu_var > 0.0


def test_posterior_drift_flips_with_signal():
    pf = RBParticleFilter(PFParams(n_particles=3000, seed=6))
    for _ in range(15):
        pf.predict(0.0)
        pf.update(-1.0)
    _, mu_hat, _ = pf.posterior()
    assert mu_hat < -0.3


def test_run_filter_output_shapes():
    obs = np.array([0.5, 0.4, -0.2, 1.1, 0.9])
    out = run_filter(obs, tilt=0.3, params=PFParams(n_particles=300, seed=0))
    assert out["mu_hat"].shape == (5,)
    assert out["p_trend"].shape == (5,)
    assert out["mu_var"].shape == (5,)


def test_run_filter_is_causal():
    # outputs for the first k steps must not change if later observations change
    base = np.array([0.5, 0.4, -0.2, 1.1, 0.9])
    alt = base.copy()
    alt[3:] = [-5.0, -5.0]
    o1 = run_filter(base, tilt=0.0, params=PFParams(n_particles=500, seed=7))
    o2 = run_filter(alt, tilt=0.0, params=PFParams(n_particles=500, seed=7))
    assert np.allclose(o1["mu_hat"][:3], o2["mu_hat"][:3])
    assert np.allclose(o1["p_trend"][:3], o2["p_trend"][:3])
