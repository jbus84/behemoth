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


_MIN_MONTHS = 2


def edge_verdict(net_by_symbol: dict, seed: int = 0, num_warmup: int = 500,
                 num_samples: int = 500, num_chains: int = 2) -> EdgePosterior:
    """Posterior on per-symbol + pooled net edge from per-symbol (net, test_month) frames.

    Symbols with < _MIN_MONTHS active months are dropped (too thin to place in the hierarchy).
    """
    names, ys, ns, idx = [], [], [], []
    for sym, frame in net_by_symbol.items():
        mn = monthly_net(frame)
        if len(mn) < _MIN_MONTHS:
            continue
        i = len(names)
        names.append(sym)
        ys.extend(mn["mean_net"].tolist())
        ns.extend(mn["n"].tolist())
        idx.extend([i] * len(mn))
    if len(names) == 0:
        raise ValueError("no symbol has >= _MIN_MONTHS active months")
    post = fit_hierarchical_edge(np.asarray(ys), np.asarray(ns, float), np.asarray(idx),
                                 n_symbols=len(names), seed=seed, num_warmup=num_warmup,
                                 num_samples=num_samples, num_chains=num_chains)
    post.names = names
    return post


def main() -> None:
    import argparse
    from pathlib import Path

    from scripts.era_scalp.context import FeatureContext
    from scripts.era_scalp.fade_seeds import FADE_SEED_PROGRAMS
    from scripts.era_scalp.load_splits import _pip_size, build_trade_splits
    from scripts.era_scalp.sandbox import run_program
    from scripts.era_scalp.trade_harness import evaluate_trades

    ap = argparse.ArgumentParser()
    ap.add_argument("--seed-name", default="vr_gated_fade", help="program in FADE_SEED_PROGRAMS")
    ap.add_argument("--tv-dir", default="data/analysis/tick_velocity")
    ap.add_argument("--symbols", default="EURUSD,GBPUSD,AUDUSD,USDCHF,USDJPY")
    ap.add_argument("--q", type=float, default=0.99)
    ap.add_argument("--h", type=int, default=100)
    ap.add_argument("--out", default="/tmp/era_fade/bayes_verdict.md")
    args = ap.parse_args()

    src = FADE_SEED_PROGRAMS[args.seed_name]
    symbols = [s.strip() for s in args.symbols.split(",") if s.strip()]
    nets = {}
    for sym in symbols:
        sp = build_trade_splits(sym, Path(args.tv_dir) / f"{sym}_100tick_velocity.parquet",
                                embargo=args.h)
        d = sp["holdout"]
        ctx = FeatureContext(X=d.X, names=d.names, hour=d.hour)
        sig, err, _ = run_program(src, ctx, required_fn="signal")
        if err is not None:
            continue
        nets[sym] = evaluate_trades(sig, d.mid, d.cost, d.test_month, _pip_size(sym), args.q, args.h)
    post = edge_verdict(nets)

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    with open(args.out, "w") as f:
        f.write(f"# Bayesian edge verdict - {args.seed_name} (q={args.q}, h={args.h})\n\n")
        f.write(f"## Pooled: P(edge>0)={post.pooled['p_positive']:.3f}  "
                f"mean={post.pooled['mean']:+.3f}  94% CI=[{post.pooled['lo']:+.3f}, "
                f"{post.pooled['hi']:+.3f}] pips\n\n")
        f.write("## Per symbol\n\n| symbol | P(edge>0) | mean | 94% CI (pips) |\n|---|---|---|---|\n")
        for i, name in enumerate(post.names):
            ps = post.per_symbol[i]
            f.write(f"| {name} | {ps['p_positive']:.3f} | {ps['mean']:+.3f} | "
                    f"[{ps['lo']:+.3f}, {ps['hi']:+.3f}] |\n")
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
