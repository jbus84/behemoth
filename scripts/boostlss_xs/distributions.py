"""
Distribution family registry for the BoostLSS reversion-OCO strategy.

Each DistSpec describes how to plug an alternative BoostLSS distributional family
into the existing WFO + tick-exact backtest pipeline (meta_label_straddle.py):

  make_family     — zero-arg constructor returning a boostlss_py family object
                     (either a PyFamily enum instance, or a family class instance
                     like MertonJumpDiffusionLss(max_jumps=10))
  param_names     — the distributional parameters to fit learners for, e.g.
                     ["mu", "sigma"] for Gaussian, or
                     ["mu", "sigma", "lam", "mu_j", "sigma_j"] for Merton.
  sizing_param    — which predicted param sizes the OCO entry/SL levels.
                     Diffusion-only "sigma" for all three families here — jump/skew
                     risk is exposed via extra_features to the meta-labeler instead
                     of baked into position sizing.
  extra_features  — predicted params (beyond sizing_param) to expose to the
                     meta-labeler as new feature columns, e.g. ["lam"] for Merton
                     (jump intensity — momentum-continuation risk) or ["nu", "tau"]
                     for SHASH (skew, kurtosis). These are NOT rescaled by the
                     per-symbol MAD factor: lam/nu/tau are dimensionless shape
                     parameters, unlike sigma/mu_j/sigma_j which are in
                     MAD-normalised return units.
  nll_fn          — computes mean per-observation negative log-likelihood on a
                     held-out (y, preds) slice, using the exact same formula as
                     the underlying Rust family's nll() — used as an OOS
                     diagnostic fit-quality metric independent of trading P&L.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import numpy as np


@dataclass
class DistSpec:
    name: str
    make_family: Callable[[], object]
    param_names: list[str]
    sizing_param: str
    extra_features: list[str]
    nll_fn: Callable[[np.ndarray, dict[str, np.ndarray]], float]


def _gaussian_nll(y: np.ndarray, preds: dict[str, np.ndarray]) -> float:
    mu = preds["mu"]
    sigma = np.maximum(preds["sigma"], 1e-10)
    ll = -0.5 * np.log(2 * np.pi * sigma ** 2) - 0.5 * ((y - mu) / sigma) ** 2
    return float(np.mean(-ll))


def _merton_nll(y: np.ndarray, preds: dict[str, np.ndarray], max_jumps: int = 10) -> float:
    mu = preds["mu"]
    sigma = np.maximum(preds["sigma"], 1e-10)
    lam = np.maximum(preds["lam"], 1e-10)
    mu_j = preds["mu_j"]
    sigma_j = np.maximum(preds["sigma_j"], 1e-10)

    var_diff = sigma ** 2
    var_jump = sigma_j ** 2
    drift = mu - 0.5 * var_diff

    ln_fact = np.zeros(max_jumps + 1)
    for j in range(1, max_jumps + 1):
        ln_fact[j] = ln_fact[j - 1] + np.log(j)

    n = len(y)
    log_terms = np.empty((max_jumps + 1, n))
    for j in range(max_jumps + 1):
        mu_total = drift + j * mu_j
        var_total = var_diff + j * var_jump
        std_total = np.sqrt(var_total)
        ln_prob_jump = -lam + j * np.log(lam) - ln_fact[j]
        diff = y - mu_total
        ln_norm = -0.5 * np.log(2 * np.pi) - np.log(std_total) - 0.5 * (diff ** 2) / var_total
        log_terms[j] = ln_prob_jump + ln_norm

    max_log = log_terms.max(axis=0)
    sum_exp = np.sum(np.exp(log_terms - max_log[None, :]), axis=0)
    ll = max_log + np.log(sum_exp)
    return float(np.mean(-ll))


def _shash_nll(y: np.ndarray, preds: dict[str, np.ndarray]) -> float:
    mu = preds["mu"]
    sigma = np.maximum(preds["sigma"], 1e-10)
    nu = preds["nu"]
    tau = np.maximum(preds["tau"], 1e-10)

    z = (y - mu) / sigma
    asinh_z = np.arcsinh(z)
    term1 = np.exp(tau * asinh_z)
    term2 = np.exp(-nu * asinh_z)
    r = 0.5 * (term1 - term2)
    c = np.maximum(0.5 * (tau * term1 + nu * term2), 1e-15)

    log_2pi_half = 0.5 * np.log(2 * np.pi)
    ll = np.log(c) - log_2pi_half - np.log(sigma) - 0.5 * np.log(1 + z ** 2) - 0.5 * (r ** 2)
    return float(np.mean(-ll))


def _make_gaussian():
    from boostlss_py import PyFamily  # type: ignore[import]
    return PyFamily("GaussianLSS")


def _make_merton():
    from boostlss_py import MertonJumpDiffusionLss  # type: ignore[import]
    return MertonJumpDiffusionLss(max_jumps=10)


def _make_shash():
    from boostlss_py import SHASHLss  # type: ignore[import]
    return SHASHLss()


REGISTRY: dict[str, DistSpec] = {
    "gaussian": DistSpec(
        name="gaussian",
        make_family=_make_gaussian,
        param_names=["mu", "sigma"],
        sizing_param="sigma",
        extra_features=[],
        nll_fn=_gaussian_nll,
    ),
    "merton": DistSpec(
        name="merton",
        make_family=_make_merton,
        param_names=["mu", "sigma", "lam", "mu_j", "sigma_j"],
        sizing_param="sigma",
        extra_features=["lam"],
        nll_fn=_merton_nll,
    ),
    "shash": DistSpec(
        name="shash",
        make_family=_make_shash,
        param_names=["mu", "sigma", "nu", "tau"],
        sizing_param="sigma",
        extra_features=["nu", "tau"],
        nll_fn=_shash_nll,
    ),
}


def get_dist_spec(name: str) -> DistSpec:
    if name not in REGISTRY:
        raise ValueError(f"Unknown distribution family: {name}")
    return REGISTRY[name]
