"""Rao-Blackwellized particle filter: discrete regime + analytic Kalman drift.

State per particle: regime s in {0=trend, 1=revert}, and a Gaussian belief over the
latent vol-normalized drift mu (mean mu_mean, variance mu_var). Particles are sampled
over the discrete regime; mu is integrated analytically (Rao-Blackwellization).
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

TREND, REVERT = 0, 1


@dataclass
class PFParams:
    n_particles: int = 400
    p_stay_trend: float = 0.9      # P(s_t=trend | s_{t-1}=trend)
    p_stay_revert: float = 0.85    # P(s_t=revert | s_{t-1}=revert)
    phi_trend: float = 0.9         # drift persistence in trend
    phi_revert: float = -0.3       # drift mean-reversion/overshoot in revert
    q_mu: float = 0.04             # drift process-noise variance
    r_obs: float = 0.5             # Gaussian obs-noise variance (vol-normalized units)
    mu0_var: float = 1.0           # prior drift variance
    tilt_gain: float = 1.0         # scales the ridge tilt into drift units
    seed: int = 0


class RBParticleFilter:
    def __init__(self, params: PFParams):
        self.p = params
        self.rng = np.random.default_rng(params.seed)
        n = params.n_particles
        # start half trend / half revert, drift prior N(0, mu0_var)
        self.regime = (self.rng.random(n) < 0.5).astype(int)  # 0 trend, 1 revert
        self.mu_mean = np.zeros(n)
        self.mu_var = np.full(n, params.mu0_var)
        self.logw = np.full(n, -np.log(n))

    def predict(self, tilt: float) -> None:
        p = self.p
        n = p.n_particles
        # --- regime transition (sticky Markov) ---
        u = self.rng.random(n)
        stay = np.where(self.regime == TREND, p.p_stay_trend, p.p_stay_revert)
        switch = u >= stay
        self.regime = np.where(switch, 1 - self.regime, self.regime)
        # --- drift Kalman time-update, regime-conditional ---
        phi = np.where(self.regime == TREND, p.phi_trend, p.phi_revert)
        nudge = np.where(self.regime == TREND, p.tilt_gain * tilt, 0.0)
        self.mu_mean = phi * self.mu_mean + nudge
        old_mu_var = self.mu_var.copy()
        self.mu_var = phi * phi * self.mu_var + p.q_mu
        self.mu_var = np.maximum(self.mu_var, old_mu_var)
