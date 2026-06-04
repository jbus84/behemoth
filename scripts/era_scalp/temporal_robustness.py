from __future__ import annotations

import jax
import jax.numpy as jnp
import numpy as np
import numpyro
import numpyro.distributions as dist
from numpyro.infer import MCMC, NUTS

from scripts.era_scalp.bayes_edge import monthly_net

_MIN_WINDOWS = 3


def _time_model(y, n, n_windows):
    """Per-symbol hierarchical-over-time edge. Each window's mean shrinks toward mu."""
    mu = numpyro.sample("mu", dist.Normal(0.0, 0.5))          # symbol long-run edge (pips/trade)
    tau = numpyro.sample("tau", dist.HalfNormal(0.5))         # between-window dispersion
    sigma = numpyro.sample("sigma", dist.HalfNormal(1.0))     # within-window trade scale
    nu = numpyro.sample("nu", dist.Gamma(2.0, 0.1))
    with numpyro.plate("windows", n_windows):
        z = numpyro.sample("z", dist.Normal(0.0, 1.0))        # non-centred
    mu_w = numpyro.deterministic("mu_w", mu + tau * z)
    se = sigma / jnp.sqrt(n)
    numpyro.sample("obs", dist.StudentT(nu, mu_w, se), obs=y)


def temporal_robustness_verdict(net_frame, min_trades_per_window: int = 5, seed: int = 0,
                                num_warmup: int = 400, num_samples: int = 400,
                                num_chains: int = 2) -> dict:
    """Per-symbol hierarchical-over-time edge robustness (NO cross-symbol pooling).

    Partitions one symbol's (net, test_month) trades into calendar-month windows,
    drops windows with < min_trades_per_window trades, and fits a model where each
    window's mean shrinks toward the symbol's long-run edge mu (thin windows borrow
    strength so the estimate isn't starved). Returns posterior summaries incl. the
    worst-window P(edge>0) — the temporal-consistency metric.
    """
    mn = monthly_net(net_frame)
    if len(mn):
        mn = mn[mn["n"] >= min_trades_per_window]
    n_windows = int(len(mn))
    if n_windows < _MIN_WINDOWS:
        return {"status": "insufficient_windows", "n_windows": n_windows,
                "p_positive": float("nan"), "worst_window_p_positive": float("nan"),
                "mu_mean": float("nan"), "mu_lo": float("nan"), "mu_hi": float("nan"),
                "tau_mean": float("nan"), "frac_windows_positive": float("nan")}
    y = mn["mean_net"].to_numpy(float)
    n = mn["n"].to_numpy(float)
    numpyro.set_host_device_count(num_chains)
    mcmc = MCMC(NUTS(_time_model), num_warmup=num_warmup, num_samples=num_samples,
                num_chains=num_chains, chain_method="sequential", progress_bar=False)
    mcmc.run(jax.random.PRNGKey(seed), y=jnp.asarray(y), n=jnp.asarray(n), n_windows=n_windows)
    s = mcmc.get_samples()
    mu = np.asarray(s["mu"])
    mu_w = np.asarray(s["mu_w"])           # (n_samples, n_windows)
    tau = np.asarray(s["tau"])
    window_p = (mu_w > 0).mean(axis=0)     # P(mu_w > 0) per window
    window_mean = mu_w.mean(axis=0)
    return {
        "status": "ok",
        "n_windows": n_windows,
        "p_positive": float((mu > 0).mean()),
        "mu_mean": float(mu.mean()),
        "mu_lo": float(np.percentile(mu, 3.0)),
        "mu_hi": float(np.percentile(mu, 97.0)),
        "tau_mean": float(tau.mean()),
        "worst_window_p_positive": float(window_p.min()),
        "frac_windows_positive": float((window_mean > 0).mean()),
    }


def is_temporally_robust(verdict: dict, min_p_positive: float = 0.9,
                         min_worst_window_p: float = 0.5) -> bool:
    """Gate: long-run edge clearly positive AND positive even in its weakest window."""
    if verdict.get("status") != "ok":
        return False
    return (verdict["p_positive"] >= min_p_positive
            and verdict["worst_window_p_positive"] >= min_worst_window_p)
