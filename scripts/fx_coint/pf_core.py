"""Rao-Blackwellized particle filter: discrete regime + analytic Kalman drift.

State per particle: regime s in {0=trend, 1=revert}, and a Gaussian belief over the
latent vol-normalized drift mu (mean mu_mean, variance mu_var). Particles are sampled
over the discrete regime; mu is integrated analytically (Rao-Blackwellization).
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

TREND, REVERT = 0, 1


def _logsumexp(x: np.ndarray) -> float:
    m = np.max(x)
    return float(m + np.log(np.sum(np.exp(x - m))))


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
        # --- regime transition (sticky Markov) ---
        u = self.rng.random(p.n_particles)
        stay = np.where(self.regime == TREND, p.p_stay_trend, p.p_stay_revert)
        switch = u >= stay
        self.regime = np.where(switch, 1 - self.regime, self.regime)
        # --- drift Kalman time-update, regime-conditional ---
        phi = np.where(self.regime == TREND, p.phi_trend, p.phi_revert)
        nudge = np.where(self.regime == TREND, p.tilt_gain * tilt, 0.0)
        self.mu_mean = phi * self.mu_mean + nudge
        self.mu_var = phi * phi * self.mu_var + p.q_mu

    def update(self, r_obs_value: float) -> None:
        p = self.p
        # predictive variance of the observation per particle: Var(mu)+R
        s = self.mu_var + p.r_obs
        resid = r_obs_value - self.mu_mean
        # Gaussian log-likelihood of the observation (the RB weight increment)
        loglik = -0.5 * (np.log(2.0 * np.pi * s) + resid * resid / s)
        self.logw = self.logw + loglik
        self.logw -= _logsumexp(self.logw)
        # Kalman measurement update of mu per particle
        k = self.mu_var / s
        self.mu_mean = self.mu_mean + k * resid
        self.mu_var = (1.0 - k) * self.mu_var
        # resample on low ESS
        w = np.exp(self.logw)
        ess = 1.0 / np.sum(w * w)
        if ess < 0.5 * p.n_particles:
            idx = self.systematic_resample(w, self.rng)
            self.regime = self.regime[idx]
            self.mu_mean = self.mu_mean[idx]
            self.mu_var = self.mu_var[idx]
            self.logw = np.full(p.n_particles, -np.log(p.n_particles))

    def posterior(self) -> tuple[float, float, float]:
        w = np.exp(self.logw)
        p_trend = float(w[self.regime == TREND].sum())
        mu_hat = float(np.sum(w * self.mu_mean))
        # mixture variance = E[var] + var of means
        mu_var_post = float(np.sum(w * self.mu_var) + np.sum(w * (self.mu_mean - mu_hat) ** 2))
        return p_trend, mu_hat, mu_var_post

    @staticmethod
    def systematic_resample(weights: np.ndarray, rng) -> np.ndarray:
        n = len(weights)
        positions = (rng.random() + np.arange(n)) / n
        cumsum = np.cumsum(weights)
        cumsum[-1] = 1.0
        return np.searchsorted(cumsum, positions).astype(int)


def run_filter(observations: np.ndarray, tilt: float, params: PFParams) -> dict[str, np.ndarray]:
    """Run the RBPF online: predict/update per observation, return posterior arrays.

    Args:
        observations: (T,) array of vol-normalized returns.
        tilt: scalar ridge forecast injected each predict step.
        params: PFParams instance with seed, particles, etc.

    Returns:
        dict with keys "p_trend", "mu_hat", "mu_var", each shape (T,).
        Element [t] is the posterior computed from observations[0..t] inclusive.
    """
    pf = RBParticleFilter(params)
    T = len(observations)
    p_trend = np.empty(T)
    mu_hat = np.empty(T)
    mu_var = np.empty(T)
    for t in range(T):
        pf.predict(tilt)
        pf.update(float(observations[t]))
        p_trend[t], mu_hat[t], mu_var[t] = pf.posterior()
    return {"p_trend": p_trend, "mu_hat": mu_hat, "mu_var": mu_var}
