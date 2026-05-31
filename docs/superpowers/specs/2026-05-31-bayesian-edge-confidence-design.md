# Bayesian edge-confidence layer — design

- Status: Proposed
- Date: 2026-05-31
- Relates to: the fade-exploitation result (`vr_gated_fade`, PR #283) — net-positive on a pooled
  holdout but with a fragile, overlapping-window significance picture (esp. CHF/JPY). This adds a
  principled confidence layer. `scripts/era_scalp/`.

## Goal

Give an **honest, calibrated confidence** statement on a trading strategy's per-symbol and pooled
net-of-cost edge — does it credibly beat cost, accounting for the *small effective sample* hidden by
overlapping trades? Replace ad-hoc effective-n / month-hit-rate / inflated BH-FDR with a **Bayesian
hierarchical (partial-pooled) posterior** over the edge. First use: a verdict on `vr_gated_fade`,
especially the CHF/JPY "way in". This is Phase 1; it is the foundation a later Bayesian-integrated
PUCT (Phase 2) reuses.

## Why Bayesian, not boosting

At this signal level (per-trade edge ~sub-pip to ~1 pip; effective independent samples in the tens),
the goal is **confidence about a tiny, possibly-zero edge**, not maximal predictive fit. Gradient
boosting is a high-capacity interaction-finder — a mirage machine at this S/N, and it gives no
calibrated uncertainty. A Bayesian hierarchical model instead:
- yields a **posterior on the edge** (credible intervals; `P(edge > 0)`),
- **partial-pools across symbols** — the principled version of cross-symbol replication; thin symbols
  (CHF/JPY, few active months) get wide posteriors shrunk toward the group, so fragility is a
  first-class output, not an afterthought,
- regularizes via a **skeptical zero-centred prior + low capacity**, not tuning knobs,
- aligns with the project's confidence-first ethos (net-LB95, BH-FDR, month-consistency → a posterior
  is their principled generalization).

## Tooling

**NumPyro** (JAX NUTS). For the ~85-observation verdict either NumPyro or PyMC fits in <1s; NumPyro is
chosen for speed because Phase 2 (scoring many ERA programs in-loop) needs many fits, avoiding a
re-tooling. Cost: adds `jax` + `numpyro` dependencies (the one real downside; PyMC is the fallback if
JAX is unwanted). Sampling is seeded for reproducible tests.

## The observation unit (handles the overlap honestly)

The `h=100` holds make per-trade PnLs heavily autocorrelated — a naive likelihood over them is
over-confident (the exact failure that inflated the pooled BH-FDR). So observations are
**per-(symbol, month) mean net-of-cost PnL**: ~17 months × ≤5 symbols ≈ 85 near-independent points
(monthly means de-correlate the within-month overlap). This needs no explicit autocorrelation model,
aligns with the existing month-consistency metric, and makes thin symbols' fragility fall out as wide
posteriors.

## Model (`fit_hierarchical_edge`)

Inputs: for each symbol `s` and month `m`, `y[s,m]` = mean net (pips), `n[s,m]` = trades that month.

```text
mu_pop ~ Normal(0, 0.5)              # population edge, skeptical zero-centred (~0.5-pip scale)
tau    ~ HalfNormal(0.5)             # between-symbol spread
mu_s   ~ Normal(mu_pop, tau)         # per-symbol edge (partial pooling)
sigma  ~ HalfNormal(1.0)             # within-symbol month-to-month noise
nu     ~ Gamma(2, 0.1)              # Student-t dof (fat tails -> robust to outlier months)
y[s,m] ~ StudentT(nu, mu_s, sigma / sqrt(n[s,m]))   # months with more trades weigh more
```

`net` already has cost subtracted, so `mu_s > 0` means "beats cost". Non-centred parameterization for
`mu_s` (stable NUTS). Defaults exposed as args (prior scales, dof prior) so they can be tightened.

Outputs (`EdgePosterior`): per-symbol `P(mu_s > 0)`, `mu_s` mean + 94% credible interval, shrinkage
(prior→posterior); pooled `P(mu_pop > 0)`, `mu_pop` interval; sampler diagnostics (R-hat, divergences).

## Data pipeline + driver

- `monthly_net(net_frame)` — from a strategy's `(net, test_month)` trade frame → arrays of monthly
  mean net + trade count per month.
- `bayes_edge_verdict(program_src, splits_by_symbol, symbols, q, h, ...)` — reuses the existing
  `trade_harness.evaluate_trades` (and `run_program`) to generate each symbol's holdout net at a chosen
  `(q,h)`, aggregates via `monthly_net`, fits `fit_hierarchical_edge`, returns/writes the posterior
  verdict. Reusable for any strategy by passing its per-symbol net frames; first target `vr_gated_fade`
  at `q=0.99, h=100` on the 5-major holdouts.
- CLI `python -m scripts.era_scalp.bayes_edge --seed-name vr_gated_fade --q 0.99 --h 100 --out ...`
  writing a markdown verdict (per-symbol + pooled posterior table).

## Phase 2 (documented, NOT built here)

`fit_hierarchical_edge` becomes the ERA **scoring criterion** (e.g. lower 5% credible bound of
`mu_pop`, or `P(mu_pop>0)`) replacing `net-LB95 × month × n` — Occam-style: a program must earn its
confidence. Plus **Thompson-sampling PUCT** (select nodes by sampling their edge posteriors) and new
Bayesian **regime-detection signal seeds** (Bayesian online change-point detection, Bayesian-OU
half-life). These reuse Phase 1's model and a fast approximation (the in-loop fit must be cheap —
analytic/conjugate or short-chain NUTS — since it runs per program). Out of scope for this spec.

## Testing (seeded, low-draw for speed)

- `test_monthly_net` — aggregation: mean + count per (symbol, month) correct.
- `test_recovers_known_edge` — synthetic data with `mu=+1` → `P(mu_pop>0) ≈ 1` and the 94% CI brackets
  +1; with `mu=0` → `P(mu_pop>0) ≈ 0.5`.
- `test_thin_symbol_wider_posterior` — a symbol with few active months has a wider `mu_s` CI than a
  data-rich one (the fragility signal).
- `test_pooling_shrinks_outlier` — an outlier symbol's posterior mean is pulled toward `mu_pop` vs its
  raw monthly mean.
- `test_verdict_smoke` — `bayes_edge_verdict` end-to-end on small synthetic splits returns the expected
  posterior keys per symbol + pooled.
- Sampling seeded (`num_warmup`/`num_samples` small, e.g. 500/500, 2 chains) for determinism + speed.
- Add `numpyro` + `jax` to `pyproject` deps.

## Consequences

- A reusable, principled confidence layer; first verdict on `vr_gated_fade` will state plainly whether
  CHF/JPY's small positives are credible or indistinguishable from zero (likely the latter, honestly).
- It does not create edge — it tells the truth about the edge, which is the point.
- Foundation for Phase 2 (Bayesian-integrated PUCT). Adds a JAX/NumPyro dependency.
- The verdict is only as honest as the per-trade net it is fed — it composes with, and does not
  replace, the tick-exact / realistic-cost gate (a Bayesian posterior over optimistic mid-to-mid net
  is confidently optimistic).
