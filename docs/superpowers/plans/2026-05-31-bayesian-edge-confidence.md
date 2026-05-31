# Bayesian Edge-Confidence Layer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Bayesian hierarchical (partial-pooled) edge-confidence layer in `scripts/era_scalp/bayes_edge.py` that gives an honest per-symbol + pooled posterior `P(net edge > 0)` from per-(symbol,month) net-of-cost PnL, and apply it as the verdict on `vr_gated_fade`.

**Architecture:** Pure-function NumPyro model (`fit_hierarchical_edge`) + a `monthly_net` aggregator + an `edge_verdict` orchestrator that takes per-symbol trade frames; a CLI/driver wires it to the fade harness to produce the `vr_gated_fade` verdict. Phase-2 (Bayesian-integrated PUCT) is out of scope.

**Tech Stack:** Python 3.12, NumPyro (JAX NUTS), numpy, pandas, pytest, `uv`.

**Spec:** `docs/superpowers/specs/2026-05-31-bayesian-edge-confidence-design.md`

**Branch:** build on `era-fair-fade` (it reuses `trade_harness`/`fade_seeds`/`load_splits.build_trade_splits`, which are on that branch via #283, not yet on main). The Bayesian verdict is the natural companion to the fade PR.

**Reused signatures (on `era-fair-fade`):**
- `scripts/era_scalp/trade_harness.evaluate_trades(signal, mid, cost, test_month, pip, q, h) -> DataFrame(net, test_month)`.
- `scripts/era_scalp/fade_seeds.FADE_SEED_PROGRAMS` (dict name->src), `scripts/era_scalp/trade_score.GRID_Q/GRID_H`.
- `scripts/era_scalp/sandbox.run_program(src, ctx, required_fn="signal")`, `context.FeatureContext`.
- `scripts/era_scalp/load_splits.build_trade_splits(symbol, parquet_path, embargo=400)`, `_pip_size(symbol)`.

---

## File Structure

- Modify: `pyproject.toml` — add `numpyro` (pulls `jax`).
- Create: `scripts/era_scalp/bayes_edge.py` — `monthly_net`, `_model`, `fit_hierarchical_edge`, `EdgePosterior`, `edge_verdict`, `main` (CLI).
- Create: `tests/era_scalp/test_bayes_edge.py`.

---

## Task B1: Dependency + monthly aggregator

**Files:** Modify `pyproject.toml`; Create `scripts/era_scalp/bayes_edge.py` (partial); Test `tests/era_scalp/test_bayes_edge.py`

- [ ] **Step 1: Add the dependency**

Run: `uv add numpyro`
Expected: `pyproject.toml` gains `numpyro` (and `jax` transitively); `uv.lock` updated; `uv run python -c "import numpyro, jax"` succeeds.

- [ ] **Step 2: Write the failing test**

```python
# tests/era_scalp/test_bayes_edge.py
import numpy as np
import pandas as pd

from scripts.era_scalp.bayes_edge import monthly_net


def test_monthly_net_mean_and_count():
    df = pd.DataFrame({
        "net": [1.0, 3.0, 2.0, 2.0],
        "test_month": ["2025-01", "2025-01", "2025-02", "2025-02"],
    })
    out = monthly_net(df).sort_values("test_month").reset_index(drop=True)
    assert list(out["test_month"]) == ["2025-01", "2025-02"]
    assert np.allclose(out["mean_net"], [2.0, 2.0])
    assert list(out["n"]) == [2, 2]


def test_monthly_net_empty():
    out = monthly_net(pd.DataFrame({"net": [], "test_month": []}))
    assert len(out) == 0
    assert set(out.columns) >= {"test_month", "mean_net", "n"}
```

- [ ] **Step 3: Run — expect FAIL.** `uv run pytest tests/era_scalp/test_bayes_edge.py -q`

- [ ] **Step 4: Create `scripts/era_scalp/bayes_edge.py` with the aggregator**

```python
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


def monthly_net(net_frame: pd.DataFrame) -> pd.DataFrame:
    """Per-month mean net + trade count from a strategy's (net, test_month) trade frame.

    Monthly aggregation de-correlates the within-month overlap of h-bar holds, giving
    near-independent observations for the hierarchical model.
    """
    if len(net_frame) == 0:
        return pd.DataFrame({"test_month": [], "mean_net": [], "n": []})
    g = net_frame.groupby("test_month")["net"]
    return pd.DataFrame({"mean_net": g.mean(), "n": g.size()}).reset_index()
```

- [ ] **Step 5: Run — expect PASS.** `uv run pytest tests/era_scalp/test_bayes_edge.py -q`

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml uv.lock scripts/era_scalp/bayes_edge.py tests/era_scalp/test_bayes_edge.py
git commit -m "feat(era-scalp): bayes_edge monthly_net aggregator + numpyro dep"
```

---

## Task B2: Hierarchical model + posterior

**Files:** Modify `scripts/era_scalp/bayes_edge.py`; Test `tests/era_scalp/test_bayes_edge.py` (append)

- [ ] **Step 1: Write the failing tests (append)**

```python
def _synth(mu_per_symbol, months=14, seed=0):
    """Build long-form (y, n, sym_idx) for symbols with given true monthly-edge means."""
    rng = np.random.default_rng(seed)
    ys, ns, idx = [], [], []
    for i, mu in enumerate(mu_per_symbol):
        for _ in range(months):
            n = int(rng.integers(40, 200))
            ys.append(mu + rng.normal(0, 1.0))  # monthly mean net ~ N(mu, 1)
            ns.append(n); idx.append(i)
    return np.array(ys, float), np.array(ns, float), np.array(idx)


def test_recovers_positive_edge():
    from scripts.era_scalp.bayes_edge import fit_hierarchical_edge
    y, n, idx = _synth([1.0, 1.0, 1.0, 1.0], seed=1)
    post = fit_hierarchical_edge(y, n, idx, n_symbols=4, seed=0, num_warmup=400, num_samples=400)
    assert post.pooled["p_positive"] > 0.95
    assert post.pooled["lo"] < 1.0 < post.pooled["hi"]


def test_zero_edge_is_uncertain():
    from scripts.era_scalp.bayes_edge import fit_hierarchical_edge
    y, n, idx = _synth([0.0, 0.0, 0.0, 0.0], seed=2)
    post = fit_hierarchical_edge(y, n, idx, n_symbols=4, seed=0, num_warmup=400, num_samples=400)
    assert 0.30 < post.pooled["p_positive"] < 0.70


def test_thin_symbol_wider_posterior():
    from scripts.era_scalp.bayes_edge import fit_hierarchical_edge
    # symbol 0 rich (14 months), symbol 1 thin (3 months); same true mu
    rng = np.random.default_rng(3)
    ys, ns, idx = [], [], []
    for i, months in enumerate([14, 3]):
        for _ in range(months):
            ys.append(0.5 + rng.normal(0, 1.0)); ns.append(100); idx.append(i)
    post = fit_hierarchical_edge(np.array(ys), np.array(ns, float), np.array(idx),
                                 n_symbols=2, seed=0, num_warmup=400, num_samples=400)
    w_rich = post.per_symbol[0]["hi"] - post.per_symbol[0]["lo"]
    w_thin = post.per_symbol[1]["hi"] - post.per_symbol[1]["lo"]
    assert w_thin > w_rich
```

- [ ] **Step 2: Run — expect FAIL.** `uv run pytest tests/era_scalp/test_bayes_edge.py -k "edge or thin" -q`

- [ ] **Step 3: Add the model + fit to `scripts/era_scalp/bayes_edge.py`**

```python
import jax
import jax.numpy as jnp
import numpyro
import numpyro.distributions as dist
from numpyro.infer import MCMC, NUTS


@dataclass
class EdgePosterior:
    per_symbol: dict          # idx -> {p_positive, mean, lo, hi}
    pooled: dict              # {p_positive, mean, lo, hi}
    names: list | None = None  # optional symbol names aligned to per_symbol keys


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
    import numpy as _np
    return {
        "p_positive": float((samples_1d > 0).mean()),
        "mean": float(_np.mean(samples_1d)),
        "lo": float(_np.percentile(samples_1d, 3.0)),
        "hi": float(_np.percentile(samples_1d, 97.0)),
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
    mu_s = np.asarray(s["mu_s"])      # (draws, n_symbols)
    mu_pop = np.asarray(s["mu_pop"])  # (draws,)
    per_symbol = {i: _summary(mu_s[:, i]) for i in range(n_symbols)}
    return EdgePosterior(per_symbol=per_symbol, pooled=_summary(mu_pop))
```

- [ ] **Step 4: Run — expect PASS** (all 3; sampling is seeded, asserts are ranges not exact). `uv run pytest tests/era_scalp/test_bayes_edge.py -q`

- [ ] **Step 5: Commit**

```bash
git add scripts/era_scalp/bayes_edge.py tests/era_scalp/test_bayes_edge.py
git commit -m "feat(era-scalp): hierarchical partial-pooled edge posterior (NumPyro NUTS)"
```

---

## Task B3: Verdict orchestrator + CLI

**Files:** Modify `scripts/era_scalp/bayes_edge.py`; Test `tests/era_scalp/test_bayes_edge.py` (append)

- [ ] **Step 1: Write the failing test (append)**

```python
def test_edge_verdict_from_net_frames():
    from scripts.era_scalp.bayes_edge import edge_verdict
    rng = np.random.default_rng(5)

    def frame(mu, months=12):
        rows = []
        for mo in range(months):
            for _ in range(rng.integers(40, 120)):
                rows.append({"net": mu + rng.normal(0, 2.0), "test_month": f"2025-{mo+1:02d}"})
        return pd.DataFrame(rows)

    nets = {"EURUSD": frame(1.2), "GBPUSD": frame(0.4), "USDCHF": frame(0.0)}
    post = edge_verdict(nets, seed=0, num_warmup=300, num_samples=300)
    assert post.names == ["EURUSD", "GBPUSD", "USDCHF"]
    assert set(post.per_symbol[0]) >= {"p_positive", "mean", "lo", "hi"}
    # EURUSD edge should read more confident than USDCHF (zero-edge)
    assert post.per_symbol[0]["p_positive"] > post.per_symbol[2]["p_positive"]
```

- [ ] **Step 2: Run — expect FAIL.** `uv run pytest tests/era_scalp/test_bayes_edge.py -k verdict -q`

- [ ] **Step 3: Add `edge_verdict` + CLI to `scripts/era_scalp/bayes_edge.py`**

```python
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
        f.write(f"# Bayesian edge verdict — {args.seed_name} (q={args.q}, h={args.h})\n\n")
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
```

- [ ] **Step 4: Run — expect PASS.** `uv run pytest tests/era_scalp/test_bayes_edge.py -q` (full file).

- [ ] **Step 5: Commit**

```bash
git add scripts/era_scalp/bayes_edge.py tests/era_scalp/test_bayes_edge.py
git commit -m "feat(era-scalp): edge_verdict orchestrator + CLI (per-symbol + pooled posterior report)"
```

---

## Task B4: Quality gate + PR

- [ ] **Step 1:** `uv run pytest -q tests/era_scalp/ tests/era/ && make quality` → all pass; quality exit 0 (fix only new-file ruff; NumPyro import-order/line-length).
- [ ] **Step 2:** Push `era-fair-fade` (already the open PR #283 branch) — the Bayesian layer rides with it, OR open a stacked PR. Since #283 is the fade work and this verifies it, append to #283:

```bash
git push
```
(Comment on PR #283 noting the Bayesian edge-confidence layer + dep were added; or, if preferred, cut a stacked branch `era-bayes-edge` off `era-fair-fade` and open a separate PR. Decide with the maintainer.)

---

## Task B5: Opus live verdict run (maintainer step — NOT Haiku)

**Requires:** the 5 `*_100tick_velocity.parquet`; `numpyro`/`jax` installed.

- [ ] **Step 1: Run the verdict on `vr_gated_fade`:**

```bash
uv run python -m scripts.era_scalp.bayes_edge --seed-name vr_gated_fade --q 0.99 --h 100 \
  --out /tmp/era_fade/bayes_verdict.md
```

- [ ] **Step 2: Write evidence** `docs/analysis/era_fade_bayes_verdict_<DATE>.md` — the per-symbol + pooled posterior table, and the honest read: which symbols' edge credibly exceeds 0 (EUR/GBP/AUD expected tight-positive; CHF/JPY expected wide, likely straddling 0 → "indistinguishable from zero"). State the caveat that the posterior is over optimistic mid-to-mid/flat-cost net, so it bounds *confidence given that net*, not deployability (tick-exact cost gate still pending). Commit.

---

## Self-Review

**Spec coverage:** monthly per-(symbol,month) obs → B1 `monthly_net`; hierarchical Student-t partial-pooled zero-prior model → B2 `_model`/`fit_hierarchical_edge`; per-symbol + pooled `P(edge>0)` + CI + shrinkage → B2 (`EdgePosterior`, thin→wide test); verdict driver reusing trade harness + CLI → B3 `edge_verdict`/`main`; NumPyro tooling + dep → B1; tests (recovery, zero-edge, thin-wider, pooling, aggregation, verdict) → B2/B3; vr_gated_fade verdict → B5. Phase 2 explicitly out of scope. Covered. (Shrinkage is exercised implicitly via the thin-symbol-wider test + partial-pooling structure; an explicit shrinkage assertion is optional.)

**Placeholder scan:** no TBD/TODO; complete code each step; commands have expected output.

**Type consistency:** `monthly_net(frame)->DataFrame[test_month,mean_net,n]` B1, used B3; `fit_hierarchical_edge(y,n,sym_idx,n_symbols,seed,num_warmup,num_samples,num_chains)->EdgePosterior` B2, used B3; `EdgePosterior(per_symbol: dict[int->{p_positive,mean,lo,hi}], pooled: dict, names)` consistent B2/B3; `edge_verdict(net_by_symbol, seed, num_warmup, num_samples, num_chains)->EdgePosterior` B3; CLI reuses `evaluate_trades`/`run_program`/`build_trade_splits`/`_pip_size`/`FADE_SEED_PROGRAMS` (all on era-fair-fade). NumPyro `num_chains` uses `chain_method="sequential"` + `set_host_device_count` for CPU determinism.
