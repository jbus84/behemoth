import numpy as np

from scripts.fx_coint.pf_core import PFParams, RBParticleFilter


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
