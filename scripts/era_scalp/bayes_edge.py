from __future__ import annotations

from dataclasses import dataclass

import jax
import jax.numpy as jnp
import numpy as np
import numpyro
import numpyro.distributions as dist
import pandas as pd
from numpyro.infer import MCMC, NUTS


def monthly_net(net_frame: pd.DataFrame) -> pd.DataFrame:
    """Per-month mean net + trade count from a strategy's (net, test_month) trade frame.

    Monthly aggregation de-correlates the within-month overlap of h-bar holds, giving
    near-independent observations for the hierarchical model.
    """
    if len(net_frame) == 0:
        return pd.DataFrame({"test_month": [], "mean_net": [], "n": []})
    g = net_frame.groupby("test_month")["net"]
    return pd.DataFrame({"mean_net": g.mean(), "n": g.size()}).reset_index()


@dataclass
class EdgePosterior:
    per_symbol: dict          # idx -> {p_positive, mean, lo, hi}
    pooled: dict              # {p_positive, mean, lo, hi}
    names: list | None = None


def _model(sym_idx, y, n, n_symbols):
    mu_pop = numpyro.sample("mu_pop", dist.Normal(0.0, 0.5))
    tau = numpyro.sample("tau", dist.HalfNormal(0.5))
    with numpyro.plate("symbols", n_symbols):
        z = numpyro.sample("z", dist.Normal(0.0, 1.0))   # non-centred
    mu_s = numpyro.deterministic("mu_s", mu_pop + tau * z)
    sigma = numpyro.sample("sigma", dist.HalfNormal(1.0))
    nu = numpyro.sample("nu", dist.Gamma(2.0, 0.1))
    se = sigma / jnp.sqrt(n)
    numpyro.sample("obs", dist.StudentT(nu, mu_s[sym_idx], se), obs=y)


def _summary(samples_1d) -> dict:
    return {
        "p_positive": float((samples_1d > 0).mean()),
        "mean": float(np.mean(samples_1d)),
        "lo": float(np.percentile(samples_1d, 3.0)),
        "hi": float(np.percentile(samples_1d, 97.0)),
    }


def fit_hierarchical_edge(y, n, sym_idx, n_symbols, seed: int = 0,
                          num_warmup: int = 500, num_samples: int = 500,
                          num_chains: int = 2) -> EdgePosterior:
    numpyro.set_host_device_count(num_chains)
    mcmc = MCMC(NUTS(_model), num_warmup=num_warmup, num_samples=num_samples,
                num_chains=num_chains, chain_method="sequential", progress_bar=False)
    mcmc.run(jax.random.PRNGKey(seed),
             sym_idx=jnp.asarray(sym_idx), y=jnp.asarray(y, dtype=float),
             n=jnp.asarray(n, dtype=float), n_symbols=int(n_symbols))
    s = mcmc.get_samples()
    mu_s = np.asarray(s["mu_s"])
    mu_pop = np.asarray(s["mu_pop"])
    per_symbol = {i: _summary(mu_s[:, i]) for i in range(n_symbols)}
    return EdgePosterior(per_symbol=per_symbol, pooled=_summary(mu_pop))
