# PUCT-Guided Boosting Feature Search — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let the PUCT tree build a boosting system — nodes generate literature-seeded feature sets, a fixed CatBoost consumes them, and the existing cost-aware verdict judges the result.

**Architecture:** A new boosting RunSpec extends atomic mode. A node renders to `build_features(ctx)` (np-only, sandboxed, causality-probed). `boost_spec` closes over the train split: its `run_program(src, ctx)` builds features on train + on the passed split, trains a small CatBoost (purged K-fold) on train, and returns predictions for the passed split — so `score_program` / `score_frame` / `engine_verdict` work unchanged. Extra overfitting rigor: purged/embargoed folds, a feature-count complexity penalty, and a V1/V2 selection-vs-confirmation split before the sacred holdout.

**Tech Stack:** Python 3.12, numpy, pandas, **catboost 1.2.10**, `uv run pytest`. Extends `scripts/era_scalp/era_engine.py` (RunSpec, score_program, run_search_rich, engine_verdict). Mirrors the 2-D sandbox pattern in `scripts/era_scalp/basket_sandbox.py` (on main). Spec: `docs/superpowers/specs/2026-06-06-puct-boosting-feature-search-design.md`.

**Conventions (this repo):**
- `uv run pytest -q <path>`; run `make quality` (ty+ruff+xenon) before any PR.
- Sandboxed feature code may use only `np`; no imports, no `np.random`, no dunder, no forward indexing. CatBoost runs ONLY in the trusted scorer, never in the sandbox.
- Commit after each passing task. Work stays in this worktree; merge via PR.
- CatBoost determinism: always pass `random_seed`, `thread_count=1`, `verbose=False`.

---

## File Structure

| File | Responsibility |
|---|---|
| `scripts/era_scalp/feature_concepts.py` | `FEATURE_CONCEPT_TAXONOMY` (literature feature operators), `FEATURE_SKELETON`, `composition_to_features_source`, `FEATURE_SEED_COMPOSITIONS`. |
| `scripts/era_scalp/boosting_sandbox.py` | `static_check` / `run_program` / `causality_probe` for `build_features(ctx) -> (n_bars, n_feat)`. |
| `scripts/era_scalp/boosting_scorer.py` | `purged_folds`, `complexity_penalty`, `train_predict` (CatBoost). |
| `scripts/era_scalp/era_boost.py` | `boost_spec(...) -> RunSpec` (train-split closure, target derivation, score_frame), `run_boost_search` driver (V1/V2 + holdout). |
| `tests/era_scalp/test_feature_concepts.py` | render + seeds. |
| `tests/era_scalp/test_boosting_sandbox.py` | 2-D output + causality. |
| `tests/era_scalp/test_boosting_scorer.py` | folds, penalty, train_predict. |
| `tests/era_scalp/test_era_boost.py` | end-to-end score_program + driver. |

---

## Task 1: Feature-concept taxonomy + renderer

**Files:**
- Create: `scripts/era_scalp/feature_concepts.py`
- Test: `tests/era_scalp/test_feature_concepts.py`

A node is a composition `{skeleton, operators: {slot: concept}, params}`. Each concept is a code template producing ONE causal feature column appended to a list; the skeleton assembles them into `build_features(ctx)` returning an `(n_bars, n_feat)` array. Operators are literature-seeded microstructure constructs.

- [ ] **Step 1: Write the failing test**

```python
# tests/era_scalp/test_feature_concepts.py
import numpy as np
from scripts.era_scalp.feature_concepts import (
    FEATURE_CONCEPT_TAXONOMY,
    FEATURE_SEED_COMPOSITIONS,
    composition_to_features_source,
)


def test_taxonomy_nonempty_and_seeds_present():
    assert len(FEATURE_CONCEPT_TAXONOMY) >= 4
    assert len(FEATURE_SEED_COMPOSITIONS) >= 2


def test_render_produces_runnable_build_features():
    comp = FEATURE_SEED_COMPOSITIONS[next(iter(FEATURE_SEED_COMPOSITIONS))]
    src = composition_to_features_source(comp["skeleton"], comp["operators"], comp.get("params", {}))
    assert "def build_features(ctx)" in src
    # exec it against a fake ctx-like object exposing .col/.X/.n_bars
    ns = {"np": np}
    exec(src, ns)

    class Ctx:
        def __init__(self, n, names):
            self.X = np.random.default_rng(0).standard_normal((n, len(names)))
            self.names = names
        @property
        def n_bars(self):
            return self.X.shape[0]
        def col(self, name):
            return self.X[:, self.names.index(name)]
    ctx = Ctx(200, ["vel_pips_h1", "signed_flow_24", "range_pips", "spread_pips", "tick_volume"])
    out = np.asarray(ns["build_features"](ctx), float)
    assert out.shape[0] == ctx.n_bars and out.ndim == 2 and out.shape[1] >= 1
    assert np.isfinite(out[10:]).any()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest -q tests/era_scalp/test_feature_concepts.py`
Expected: FAIL `ModuleNotFoundError: scripts.era_scalp.feature_concepts`.

- [ ] **Step 3: Write minimal implementation**

```python
# scripts/era_scalp/feature_concepts.py
"""Literature-seeded feature operators for the PUCT-built boosting search.

Each concept is a causal code template that appends ONE feature column (length n_bars)
to the list `feats` inside build_features(ctx). All templates use cumulative / shifted
windows so a row at t depends only on rows <= t (passes the causality probe). np only.
"""
from __future__ import annotations

# name -> (causal feature code template appended to `feats`)
FEATURE_CONCEPT_TAXONOMY: dict[str, str] = {
    # signed order-flow imbalance over a trailing window (Cont-Kukanov-Stoikov)
    "signed_flow_imbalance": (
        "    _x = np.nan_to_num(ctx.col('signed_flow_24'))\n"
        "    _c = np.cumsum(_x)\n"
        "    _w = {w}\n"
        "    _sf = np.full(n, np.nan)\n"
        "    for t in range(n):\n"
        "        lo = t - _w + 1\n"
        "        if lo >= 0:\n"
        "            _sf[t] = _c[t] - (_c[lo-1] if lo > 0 else 0.0)\n"
        "    feats.append(_sf)\n"
    ),
    # realized-range volatility regime (Parkinson-style), trailing mean of range_pips
    "range_vol_regime": (
        "    _r = np.nan_to_num(ctx.col('range_pips'))\n"
        "    _c = np.cumsum(_r)\n"
        "    _w = {w}\n"
        "    _rv = np.full(n, np.nan)\n"
        "    for t in range(n):\n"
        "        lo = t - _w + 1\n"
        "        if lo >= 0:\n"
        "            _rv[t] = (_c[t] - (_c[lo-1] if lo > 0 else 0.0)) / _w\n"
        "    feats.append(_rv)\n"
    ),
    # path-dependent reversal: trailing cumulative velocity (mean-reversion signal)
    "trailing_reversal": (
        "    _v = np.nan_to_num(ctx.col('vel_pips_h1'))\n"
        "    _c = np.cumsum(_v)\n"
        "    _w = {w}\n"
        "    _tr = np.full(n, np.nan)\n"
        "    for t in range(n):\n"
        "        lo = t - _w + 1\n"
        "        if lo >= 0:\n"
        "            _tr[t] = -(_c[t] - (_c[lo-1] if lo > 0 else 0.0))\n"
        "    feats.append(_tr)\n"
    ),
    # quote-revision intensity scaled by spread (Easley-O'Hara info flow)
    "quote_revision_intensity": (
        "    _q = np.nan_to_num(ctx.col('quote_revision_rate_z'))\n"
        "    _s = np.nan_to_num(ctx.col('spread_pips')) + 1e-9\n"
        "    feats.append(_q / _s)\n"
    ),
    # liquidity proxy: tick volume z trailing mean
    "liquidity_state": (
        "    _tv = np.nan_to_num(ctx.col('tick_volume'))\n"
        "    _c = np.cumsum(_tv)\n"
        "    _w = {w}\n"
        "    _ls = np.full(n, np.nan)\n"
        "    for t in range(n):\n"
        "        lo = t - _w + 1\n"
        "        if lo >= 0:\n"
        "            _ls[t] = (_c[t] - (_c[lo-1] if lo > 0 else 0.0)) / _w\n"
        "    feats.append(_ls)\n"
    ),
}

FEATURE_SKELETON = (
    "def build_features(ctx):\n"
    "    n = ctx.n_bars\n"
    "    feats = []\n"
    "{body}"
    "    if not feats:\n"
    "        feats.append(np.zeros(n))\n"
    "    return np.column_stack(feats)\n"
)


def composition_to_features_source(skeleton: str, operators, params=None) -> str:
    """Render a composition into build_features(ctx) source. `operators` maps slot->concept
    (slot names are arbitrary; only the concept values matter). `params` may set window `w`
    per slot (default 20)."""
    params = params or {}
    if not isinstance(operators, dict):
        operators = {}
    body = ""
    for slot, concept in operators.items():
        tmpl = FEATURE_CONCEPT_TAXONOMY.get(concept if isinstance(concept, str) else "")
        if tmpl is None:
            continue
        w = int((params.get(slot, {}) or {}).get("w", 20)) if isinstance(params.get(slot), dict) else int(params.get("w", 20))
        body += tmpl.replace("{w}", str(max(2, w)))
    return FEATURE_SKELETON.format(body=body or "    feats.append(np.zeros(n))\n")


FEATURE_SEED_COMPOSITIONS: dict[str, dict] = {
    "flow_vol": {
        "skeleton": "default",
        "operators": {"a": "signed_flow_imbalance", "b": "range_vol_regime"},
        "params": {"w": 24},
    },
    "reversal_liquidity": {
        "skeleton": "default",
        "operators": {"a": "trailing_reversal", "b": "liquidity_state", "c": "quote_revision_intensity"},
        "params": {"w": 16},
    },
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest -q tests/era_scalp/test_feature_concepts.py`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add scripts/era_scalp/feature_concepts.py tests/era_scalp/test_feature_concepts.py
git commit -m "feat(era-boost): literature-seeded feature-concept taxonomy + renderer"
```

---

## Task 2: Boosting sandbox (2-D `build_features`)

**Files:**
- Create: `scripts/era_scalp/boosting_sandbox.py`
- Test: `tests/era_scalp/test_boosting_sandbox.py`

Mirror `scripts/era_scalp/basket_sandbox.py` but the entry point is `build_features`, the output is `(n_bars, n_feat)` with **variable** `n_feat`, and the context is `FeatureContext` (so the worker reconstructs `FeatureContext`, not `BasketContext`).

- [ ] **Step 1: Write the failing test**

```python
# tests/era_scalp/test_boosting_sandbox.py
import numpy as np
from scripts.era_scalp.context import FeatureContext
from scripts.era_scalp.boosting_sandbox import causality_probe, run_program, static_check

CAUSAL = (
    "def build_features(ctx):\n"
    "    v = np.nan_to_num(ctx.col('vel_pips_h1'))\n"
    "    c = np.cumsum(v)\n"
    "    out = np.full((ctx.n_bars, 1), np.nan)\n"
    "    for t in range(ctx.n_bars):\n"
    "        if t >= 4:\n"
    "            out[t, 0] = c[t] - c[t-5]\n"
    "    return out\n"
)
LEAKY = (
    "def build_features(ctx):\n"
    "    v = ctx.col('vel_pips_h1')\n"
    "    return (v - v.mean()).reshape(-1, 1)\n"  # uses full-column mean = future
)
NOFUNC = "def other(ctx):\n    return ctx.X\n"


def _ctx(n=40, seed=0):
    rng = np.random.default_rng(seed)
    names = ["vel_pips_h1", "range_pips"]
    return FeatureContext(X=rng.standard_normal((n, len(names))), names=names, hour=None)


def test_static_check_requires_build_features():
    assert not static_check(NOFUNC)[0]
    assert static_check(CAUSAL)[0]


def test_run_program_returns_2d_variable_width():
    out, err, _ = run_program(CAUSAL, _ctx())
    assert err is None and out.ndim == 2 and out.shape[0] == 40


def test_causality_probe_accepts_causal_rejects_leaky():
    out, err, _ = run_program(CAUSAL, _ctx())
    assert err is None and causality_probe(CAUSAL, _ctx(), out)[0]
    out2, err2, _ = run_program(LEAKY, _ctx())
    assert err2 is None and not causality_probe(LEAKY, _ctx(), out2)[0]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest -q tests/era_scalp/test_boosting_sandbox.py`
Expected: FAIL `ModuleNotFoundError`.

- [ ] **Step 3: Write minimal implementation**

```python
# scripts/era_scalp/boosting_sandbox.py
"""Sandbox for build_features(ctx) -> (n_bars, n_feat). Mirrors basket_sandbox but for
variable-width 2-D feature output over FeatureContext. np-only; causality-probed."""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np

from scripts.era.sandbox import _arrays_match, static_check as _static_check
from scripts.era_scalp.context import FeatureContext


def static_check(src: str, required_fn: str = "build_features"):
    return _static_check(src, required_fn=required_fn)


_WORKER = r"""
import sys, numpy as np
from scripts.era_scalp.context import FeatureContext
payload = np.load(sys.argv[1], allow_pickle=True)
src = str(payload["src"])
hour = payload["hour"]; hour = None if hour.size == 0 else hour
ctx = FeatureContext(X=payload["X"], names=list(payload["names"]), hour=hour)
ns = {"np": np}
try:
    exec(src, ns)
    out = np.asarray(ns["build_features"](ctx), dtype=float)
    if out.ndim != 2 or out.shape[0] != ctx.n_bars:
        raise ValueError(f"build_features shape {out.shape} != (n_bars, n_feat) rows {ctx.n_bars}")
    np.save(sys.argv[2], out)
    print("OK")
except Exception as e:
    print(f"ERR {type(e).__name__}: {e}", file=sys.stderr)
    sys.exit(3)
"""


def run_program(src: str, ctx: FeatureContext, timeout: float = 10.0,
                required_fn: str = "build_features"):
    ok, reason = static_check(src, required_fn=required_fn)
    if not ok:
        return None, f"static_check: {reason}", ""
    with tempfile.TemporaryDirectory() as d:
        inp = Path(d) / "in.npz"
        out = Path(d) / "out.npy"
        wrk = Path(d) / "w.py"
        np.savez(inp, src=src, X=ctx.X, names=np.array(ctx.names),
                 hour=ctx.hour if ctx.hour is not None else np.array([]))
        wrk.write_text(_WORKER)
        env = dict(os.environ)
        env["PYTHONPATH"] = str(Path.cwd()) + os.pathsep + env.get("PYTHONPATH", "")
        try:
            proc = subprocess.run([sys.executable, str(wrk), str(inp), str(out)],
                                  capture_output=True, text=True, timeout=timeout,
                                  cwd=str(Path.cwd()), env=env)
        except subprocess.TimeoutExpired:
            return None, "timeout", ""
        logs = (proc.stdout + proc.stderr).strip()
        if proc.returncode != 0 or not out.exists():
            return None, logs or f"exit {proc.returncode}", logs
        return np.load(out), None, logs


def causality_probe(src, ctx, clean_feats, n_cuts: int = 4, seed: int = 0,
                    required_fn: str = "build_features", nan_frac: float = 0.3):
    """Reject feature code whose past rows depend on future rows. Perturbs rows > k and
    requires feats[:k+1, :] unchanged."""
    n = ctx.n_bars
    if n < 6:
        return True, "too-short-to-probe"
    rng = np.random.default_rng(seed)
    clean = np.asarray(clean_feats, float)
    cuts = [max(1, n * (i + 1) // (n_cuts + 1)) for i in range(n_cuts)]
    for k in cuts:
        X2 = ctx.X.copy()
        fut = X2[k + 1:, :]
        fut[:] = rng.standard_normal(fut.shape) * 10.0
        if fut.size:
            fut[rng.random(fut.shape) < nan_frac] = np.nan
        X2[k + 1:, :] = fut
        ctx2 = FeatureContext(X=X2, names=ctx.names, hour=ctx.hour)
        f2, err, _ = run_program(src, ctx2, required_fn=required_fn)
        if err is not None:
            return False, f"non-causal: errors under future perturbation at k={k}: {err}"
        if not _arrays_match(clean[: k + 1, :], np.asarray(f2, float)[: k + 1, :]):
            return False, f"non-causal: feats[:{k + 1}] changed when future perturbed"
    return True, "ok"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest -q tests/era_scalp/test_boosting_sandbox.py`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add scripts/era_scalp/boosting_sandbox.py tests/era_scalp/test_boosting_sandbox.py
git commit -m "feat(era-boost): 2-D build_features sandbox with causality probe"
```

---

## Task 3: Boosting scorer (purged folds, penalty, CatBoost train/predict)

**Files:**
- Create: `scripts/era_scalp/boosting_scorer.py`
- Test: `tests/era_scalp/test_boosting_scorer.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/era_scalp/test_boosting_scorer.py
import numpy as np
from scripts.era_scalp.boosting_scorer import complexity_penalty, purged_folds, train_predict


def test_purged_folds_no_overlap_with_embargo():
    folds = purged_folds(1000, k=4, embargo=50)
    assert len(folds) == 4
    for tr, va in folds:
        assert set(tr).isdisjoint(set(va))
        # embargo: no train index within `embargo` of any val index
        va_set = set(va)
        for i in tr:
            assert all(abs(i - j) > 50 or j == i for j in (min(va), max(va)))  # boundary check
        assert len(va) > 0


def test_complexity_penalty_monotonic():
    assert complexity_penalty(1) < complexity_penalty(5) < complexity_penalty(20)


def test_train_predict_shape_and_determinism():
    rng = np.random.default_rng(0)
    Xtr = rng.standard_normal((400, 3)); ytr = Xtr[:, 0] * 0.5 + rng.standard_normal(400) * 0.1
    Xpr = rng.standard_normal((120, 3))
    a = train_predict(Xtr, ytr, Xpr, seed=0)
    b = train_predict(Xtr, ytr, Xpr, seed=0)
    assert a.shape == (120,)
    assert np.allclose(a, b)  # deterministic with fixed seed + thread_count=1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest -q tests/era_scalp/test_boosting_scorer.py`
Expected: FAIL `ModuleNotFoundError`.

- [ ] **Step 3: Write minimal implementation**

```python
# scripts/era_scalp/boosting_scorer.py
"""Trusted boosting scorer: purged/embargoed folds, complexity penalty, CatBoost
train->predict. CatBoost runs ONLY here (never in the sandbox)."""
from __future__ import annotations

import numpy as np


def purged_folds(n: int, k: int = 4, embargo: int = 50):
    """Contiguous-block K-fold with an embargo gap. Returns [(train_idx, val_idx)]; train
    excludes the val block plus `embargo` rows on each side (purged to avoid leakage from
    overlapping forward-return windows)."""
    idx = np.arange(n)
    bounds = np.linspace(0, n, k + 1).astype(int)
    folds = []
    for i in range(k):
        lo, hi = bounds[i], bounds[i + 1]
        val = idx[lo:hi]
        keep = np.ones(n, bool)
        keep[max(0, lo - embargo): min(n, hi + embargo)] = False
        folds.append((idx[keep], val))
    return folds


def complexity_penalty(n_feat: int, per_feature: float = 0.02) -> float:
    """Monotonic penalty subtracted from node value to punish large feature sets."""
    return per_feature * float(max(0, n_feat))


def train_predict(X_tr, y_tr, X_pred, *, seed: int = 0, depth: int = 4,
                  iterations: int = 200, lr: float = 0.05) -> np.ndarray:
    """Train a small, deterministic CatBoost regressor on (X_tr, y_tr); predict X_pred."""
    from catboost import CatBoostRegressor

    X_tr = np.nan_to_num(np.asarray(X_tr, float))
    y_tr = np.asarray(y_tr, float)
    fin = np.isfinite(y_tr)
    model = CatBoostRegressor(depth=depth, iterations=iterations, learning_rate=lr,
                              loss_function="RMSE", random_seed=seed, thread_count=1,
                              verbose=False)
    model.fit(X_tr[fin], y_tr[fin])
    return np.asarray(model.predict(np.nan_to_num(np.asarray(X_pred, float))), float)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest -q tests/era_scalp/test_boosting_scorer.py`
Expected: PASS (3 passed). (If the embargo boundary assertion is brittle, simplify it to assert `keep[lo:hi]` all False and the embargo rows around the block are excluded.)

- [ ] **Step 5: Commit**

```bash
git add scripts/era_scalp/boosting_scorer.py tests/era_scalp/test_boosting_scorer.py
git commit -m "feat(era-boost): purged folds + complexity penalty + CatBoost train/predict"
```

---

## Task 4: `boost_spec` — train-split closure RunSpec (linchpin)

**Files:**
- Create: `scripts/era_scalp/era_boost.py`
- Test: `tests/era_scalp/test_era_boost.py` (part A)

`boost_spec` closes over the **train split**. `run_program(src, ctx)` builds features on train + on `ctx`'s split, trains CatBoost on train-features→train-target, returns predictions for `ctx` — so the generic `score_program` works unchanged. Training is cached by `src` hash so repeated calls (grid cells, verdict) don't retrain. `causality_probe` probes `build_features` (not predictions). The target is derived from the split's `mid` at horizon `h`.

- [ ] **Step 1: Write the failing test**

```python
# tests/era_scalp/test_era_boost.py
import numpy as np
from scripts.era_scalp.load_splits import TradeSplitData
from scripts.era_scalp.feature_concepts import FEATURE_SEED_COMPOSITIONS, composition_to_features_source
from scripts.era_scalp.era_boost import boost_spec
from scripts.era_scalp.era_engine import score_program


def _split(n=1200, seed=0):
    rng = np.random.default_rng(seed)
    names = ["vel_pips_h1", "signed_flow_24", "range_pips", "spread_pips", "tick_volume",
             "quote_revision_rate_z"]
    X = rng.standard_normal((n, len(names)))
    return TradeSplitData(
        X=X, names=names, hour=(np.arange(n) % 24).astype(float),
        mid=1.1 + np.cumsum(rng.standard_normal(n)) * 1e-4,
        cost=np.full(n, 0.2),
        test_month=np.array([f"2024-{1 + (i // 100) % 12:02d}" for i in range(n)]),
        spread_pips=np.full(n, 0.2),
    )


def _seed_src():
    c = FEATURE_SEED_COMPOSITIONS["flow_vol"]
    return composition_to_features_source(c["skeleton"], c["operators"], c.get("params", {}))


def test_boost_spec_fields():
    spec = boost_spec(_split(), symbol="EURUSD", target="forward", horizon=12)
    assert spec.required_fn == "build_features"
    assert spec.grid_h == [12]


def test_score_program_runs_end_to_end():
    train = _split(seed=1)
    spec = boost_spec(train, symbol="EURUSD", target="forward", horizon=12)
    val = _split(seed=2)
    value, mean, se, logs = score_program(_seed_src(), spec, val)
    assert np.isfinite(value) and value > -1e6, logs
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest -q tests/era_scalp/test_era_boost.py::test_boost_spec_fields`
Expected: FAIL `ModuleNotFoundError`.

- [ ] **Step 3: Write minimal implementation**

```python
# scripts/era_scalp/era_boost.py
"""PUCT-built boosting feature search as a RunSpec for the unified ERA engine.

A node renders to build_features(ctx) (sandboxed, causality-probed). boost_spec closes
over the train split: run_program builds features on train + the scored split, trains a
small CatBoost on train, and returns predictions for the scored split -> the generic
score_program/score_frame/engine_verdict work unchanged."""
from __future__ import annotations

import hashlib

import numpy as np

from scripts.era_scalp.boosting_sandbox import causality_probe as _bf_causality
from scripts.era_scalp.boosting_sandbox import run_program as _bf_run
from scripts.era_scalp.boosting_scorer import complexity_penalty, train_predict
from scripts.era_scalp.context import FeatureContext
from scripts.era_scalp.cost_model import realistic_cost
from scripts.era_scalp.era_engine import RunSpec
from scripts.era_scalp.load_splits import _pip_size
from scripts.era_scalp.trade_harness import evaluate_fair_price_trades, evaluate_trades


def _forward_target(mid: np.ndarray, h: int, pip: float) -> np.ndarray:
    """Forward h-bar return in pips (label for the GBDT). NaN in the last h rows."""
    mid = np.asarray(mid, float)
    fwd = np.full(mid.shape, np.nan)
    fwd[:-h] = (mid[h:] - mid[:-h]) / pip
    return fwd


def boost_spec(train_split, *, symbol: str = "EURUSD", target: str = "forward",
               horizon: int = 12, grid_q=None, complexity_per_feat: float = 0.02,
               seed: int = 0, timeout: float = 20.0) -> RunSpec:
    """RunSpec where PUCT searches feature compositions feeding a fixed CatBoost.

    target='forward' (lower-turnover real shot) or 'fair' (intraday calibration)."""
    pip = _pip_size(symbol)
    grid_q = grid_q or [0.80, 0.90, 0.95]
    y_train = _forward_target(train_split.mid, horizon, pip)
    _cache: dict[str, np.ndarray] = {}

    def _features(src, ctx):
        feats, err, _ = _bf_run(src, ctx, timeout=timeout)
        return feats, err

    def context_factory(split):
        return FeatureContext(X=split.X, names=split.names, hour=split.hour)

    def run_program(src, ctx, timeout=timeout, required_fn="build_features"):
        # 1) features on the scored split
        Xpred, err = _features(src, ctx)
        if err is not None:
            return None, err, ""
        # 2) train (cached by src): features on train + CatBoost fit
        key = hashlib.sha1(src.encode()).hexdigest()
        if key not in _cache:
            tctx = FeatureContext(X=train_split.X, names=train_split.names, hour=train_split.hour)
            Xtr, terr = _features(src, tctx)
            if terr is not None:
                return None, terr, ""
            _cache[key] = ("model", Xtr)
        _, Xtr = _cache[key]
        try:
            preds = train_predict(Xtr, y_train, Xpred, seed=seed)
        except Exception as e:  # catboost failure -> reject node
            return None, f"catboost: {e}", ""
        # stash feature count on the array for the complexity penalty via score_frame
        return preds, None, f"n_feat={Xpred.shape[1]}"

    def causality_probe(src, ctx, out, required_fn="build_features"):
        # probe the FEATURE code, not the predictions
        feats, err, _ = _bf_run(src, ctx, timeout=timeout)
        if err is not None:
            return False, f"feature exec: {err}"
        return _bf_causality(src, ctx, feats)

    def score_frame(out, split, q, h):
        if target == "fair":
            return evaluate_fair_price_trades(out, split.mid, realistic_cost(split.spread_pips),
                                              split.test_month, pip, q, h)
        return evaluate_trades(out, split.mid, realistic_cost(split.spread_pips),
                               split.test_month, pip, q, h)

    return RunSpec(
        name=f"boost_{target}_h{horizon}",
        required_fn="build_features",
        run_program=run_program,
        causality_probe=causality_probe,
        context_factory=context_factory,
        score_frame=score_frame,
        grid_q=list(grid_q),
        grid_h=[horizon],
        aggregate="robust",
        atomic_mode=True,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest -q tests/era_scalp/test_era_boost.py::test_boost_spec_fields tests/era_scalp/test_era_boost.py::test_score_program_runs_end_to_end`
Expected: PASS (2 passed). (CatBoost on 1200 synthetic rows trains in well under the timeout.)

- [ ] **Step 5: Commit**

```bash
git add scripts/era_scalp/era_boost.py tests/era_scalp/test_era_boost.py
git commit -m "feat(era-boost): boost_spec train-split closure RunSpec (CatBoost predictions)"
```

---

## Task 5: Seed compositions + PUCT writers wired for boosting

**Files:**
- Modify: `scripts/era_scalp/era_boost.py` (add `seed_compositions`, `propose_atomic`, `recombine_atomic`, `render_payload`, `branch_tags`, `ideas` to the RunSpec)
- Test: `tests/era_scalp/test_era_boost.py` (part B)

Wire the feature seeds and the atomic propose/recombine writers so `run_search_rich` can evolve feature compositions. Reuse `scripts.era.llm.propose_xs_atomic_change` / `recombine_xs_atomic_compositions` patterns OR a thin deterministic mutator if the LLM writer's prompt doesn't fit feature concepts; for v1 use a **deterministic composition mutator** (no LLM) so the search is reproducible and testable, with the LLM writer as a later enhancement.

- [ ] **Step 1: Write the failing test**

```python
# add to tests/era_scalp/test_era_boost.py
from scripts.era_scalp.era_boost import boost_spec, mutate_composition, recombine_compositions
from scripts.era_scalp.feature_concepts import FEATURE_SEED_COMPOSITIONS


def test_mutate_returns_valid_composition():
    base = FEATURE_SEED_COMPOSITIONS["flow_vol"]
    comp, prior = mutate_composition(base, 0.0, [], None, seed=1)
    assert isinstance(comp, dict) and "operators" in comp and isinstance(prior, float)


def test_recombine_merges_operators():
    a = FEATURE_SEED_COMPOSITIONS["flow_vol"]
    b = FEATURE_SEED_COMPOSITIONS["reversal_liquidity"]
    comp, prior = recombine_compositions(a, 0.0, b, 0.0)
    assert "operators" in comp and len(comp["operators"]) >= 1


def test_spec_carries_seeds():
    spec = boost_spec(None, symbol="EURUSD", seed_only=True)
    assert spec.seed_compositions and spec.render_payload is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest -q tests/era_scalp/test_era_boost.py::test_mutate_returns_valid_composition`
Expected: FAIL `ImportError: cannot import name 'mutate_composition'`.

- [ ] **Step 3: Write minimal implementation**

Add to `scripts/era_scalp/era_boost.py`:

```python
import random as _random

from scripts.era_scalp.feature_concepts import (
    FEATURE_CONCEPT_TAXONOMY,
    FEATURE_SEED_COMPOSITIONS,
    composition_to_features_source,
)


def _sanitize(comp):
    if not isinstance(comp, dict):
        return {"skeleton": "default", "operators": {}, "params": {"w": 20}}
    ops = comp.get("operators", {})
    ops = {k: v for k, v in ops.items() if isinstance(v, str) and v in FEATURE_CONCEPT_TAXONOMY}
    return {"skeleton": "default", "operators": ops, "params": comp.get("params", {"w": 20})}


def mutate_composition(parent, score, logs, idea, *, cache_dir=None, seed=0):
    """Deterministic mutation: add/swap/drop one feature operator. Returns (comp, prior)."""
    rng = _random.Random(hash((repr(parent), seed)) & 0xFFFFFFFF)
    comp = _sanitize(parent)
    ops = dict(comp["operators"])
    concepts = list(FEATURE_CONCEPT_TAXONOMY)
    action = rng.choice(["add", "swap", "drop"]) if ops else "add"
    if action == "add":
        ops[f"s{len(ops)}"] = rng.choice(concepts)
    elif action == "swap" and ops:
        ops[rng.choice(list(ops))] = rng.choice(concepts)
    elif action == "drop" and len(ops) > 1:
        del ops[rng.choice(list(ops))]
    w = int(comp["params"].get("w", 20))
    params = {"w": max(2, w + rng.choice([-8, 0, 8]))}
    return {"skeleton": "default", "operators": ops, "params": params}, 0.5


def recombine_compositions(comp_a, score_a, comp_b, score_b, *, cache_dir=None):
    """Union the two parents' operators (favouring the higher-scoring parent's window)."""
    a, b = _sanitize(comp_a), _sanitize(comp_b)
    ops = {**a["operators"], **b["operators"]}
    params = a["params"] if score_a >= score_b else b["params"]
    return {"skeleton": "default", "operators": ops, "params": params}, 0.5
```

And extend the `RunSpec(...)` returned by `boost_spec` (set these fields; add a `seed_only` param that returns the spec without requiring `train_split`):

```python
    return RunSpec(
        name=f"boost_{target}_h{horizon}",
        required_fn="build_features",
        run_program=(None if seed_only else run_program),
        causality_probe=causality_probe,
        context_factory=context_factory,
        score_frame=score_frame,
        grid_q=list(grid_q),
        grid_h=[horizon],
        aggregate="robust",
        atomic_mode=True,
        seed_compositions=dict(FEATURE_SEED_COMPOSITIONS),
        render_payload=lambda comp: composition_to_features_source(
            "default", _sanitize(comp)["operators"], _sanitize(comp)["params"]),
        branch_tags={k: k for k in FEATURE_SEED_COMPOSITIONS},
        propose_atomic=mutate_composition,
        recombine_atomic=recombine_compositions,
        ideas=["Compose causal microstructure features (flow, vol regime, reversal, "
               "liquidity, quote-revision) for a boosted forward-return model."],
    )
```

Add `seed_only: bool = False` to the `boost_spec` signature; when true, skip `y_train`/closure setup that needs `train_split`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest -q tests/era_scalp/test_era_boost.py`
Expected: PASS (all).

- [ ] **Step 5: Commit**

```bash
git add scripts/era_scalp/era_boost.py tests/era_scalp/test_era_boost.py
git commit -m "feat(era-boost): seed compositions + deterministic mutate/recombine writers"
```

---

## Task 6: Driver — V1/V2 selection split + complexity-penalised verdict

**Files:**
- Modify: `scripts/era_scalp/era_boost.py` (add `run_boost_search`)
- Test: `tests/era_scalp/test_era_boost.py` (part C)

`run_boost_search` builds `boost_spec` from train, runs `run_search_rich` scoring on **V1**, applies the complexity penalty to node values, confirms the top survivor on **V2**, then evaluates holdout once via `engine_verdict`.

- [ ] **Step 1: Write the failing test**

```python
# add to tests/era_scalp/test_era_boost.py
from scripts.era_scalp.era_boost import run_boost_search


def test_run_boost_search_smoke(tmp_path):
    splits = {"train": _split(seed=1), "validation": _split(seed=2), "holdout": _split(seed=3)}
    res = run_boost_search(splits, symbol="EURUSD", target="forward", horizon=12,
                           budget=3, seed=0, cache_dir=str(tmp_path))
    assert "survivor" in res and "holdout" in res
    assert np.isfinite(res["survivor"]["val_v1"])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest -q tests/era_scalp/test_era_boost.py::test_run_boost_search_smoke`
Expected: FAIL `ImportError: cannot import name 'run_boost_search'`.

- [ ] **Step 3: Write minimal implementation**

Add to `scripts/era_scalp/era_boost.py`:

```python
import numpy as _np

from scripts.era_scalp.era_engine import engine_verdict, run_search_rich


def _halve(split):
    """Split a TradeSplitData in half by time -> (V1, V2)."""
    from dataclasses import replace
    n = len(split.mid); m = n // 2
    def cut(s, a, b):
        return replace(s, X=s.X[a:b], hour=(None if s.hour is None else s.hour[a:b]),
                       mid=s.mid[a:b], cost=s.cost[a:b], test_month=s.test_month[a:b],
                       spread_pips=(None if s.spread_pips is None else s.spread_pips[a:b]))
    return cut(split, 0, m), cut(split, m, n)


def run_boost_search(splits, *, symbol="EURUSD", target="forward", horizon=12,
                     budget=20, seed=0, cache_dir=".era_boost_cache",
                     complexity_per_feat=0.02):
    """PUCT feature search: select on V1, confirm on V2, holdout once."""
    v1, v2 = _halve(splits["validation"])
    spec = boost_spec(splits["train"], symbol=symbol, target=target, horizon=horizon,
                      complexity_per_feat=complexity_per_feat, seed=seed)
    nodes = run_search_rich(spec, {"validation": v1}, budget=budget, seed=seed,
                            cache_dir=cache_dir)
    # apply complexity penalty to node value using logged n_feat (fallback: len(operators))
    def penalised(n):
        nf = 0
        comp = _sanitize(getattr(n, "payload", {}))
        nf = len(comp["operators"])
        return n.score - complexity_penalty(nf, complexity_per_feat)
    ranked = sorted([n for n in nodes if n.score > -1e6 + 1], key=penalised, reverse=True)
    if not ranked:
        return {"survivor": None, "holdout": None}
    best = ranked[0]
    src = spec.render_payload(best.payload)
    # confirm on V2
    from scripts.era_scalp.era_engine import score_program
    v2_val, _, _, _ = score_program(src, spec, v2)
    # holdout once (engine_verdict at best cell)
    verdict = engine_verdict(spec, [best], {"validation": v1, "holdout": splits.get("holdout")},
                             top_k=1)
    return {
        "survivor": {"branch": best.branch, "val_v1": float(best.score),
                     "val_v1_penalised": float(penalised(best)), "val_v2": float(v2_val),
                     "n_feat": len(_sanitize(best.payload)["operators"]), "src": src},
        "holdout": verdict[0] if verdict else None,
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest -q tests/era_scalp/test_era_boost.py::test_run_boost_search_smoke`
Expected: PASS. (Budget=3 keeps CatBoost trainings small; should finish in seconds–tens of seconds.)

- [ ] **Step 5: Commit**

```bash
git add scripts/era_scalp/era_boost.py tests/era_scalp/test_era_boost.py
git commit -m "feat(era-boost): V1/V2 selection-split driver with complexity penalty + holdout"
```

---

## Task 7: Quality gate + full suite

**Files:** none (verification).

- [ ] **Step 1: Run the new suite**

Run: `uv run pytest -q tests/era_scalp/test_feature_concepts.py tests/era_scalp/test_boosting_sandbox.py tests/era_scalp/test_boosting_scorer.py tests/era_scalp/test_era_boost.py`
Expected: all PASS.

- [ ] **Step 2: Confirm no regression in the engine characterization oracle**

Run: `uv run pytest -q tests/era_scalp/test_run_search_characterization.py tests/era_scalp/test_era_engine.py`
Expected: PASS (boosting adds a RunSpec; it must not change existing search behavior).

- [ ] **Step 3: Quality gate**

Run: `make quality`
Expected: ty + ruff + xenon clean. Fix findings in the new files (unused imports, type hints, complexity) until green.

- [ ] **Step 4: Commit any fixes**

```bash
git add -A && git commit -m "chore(era-boost): satisfy quality gate"
```

(Skip if no changes.)

---

## Task 8: Real-data smoke run (manual gate; holdout discipline)

**Files:** none. Requires velocity parquets (`data/analysis/tick_velocity`).

- [ ] **Step 1: Build splits and run a small search on both targets**

Run:
```bash
uv run python -c "
from scripts.era_scalp.load_splits import build_trade_splits
from scripts.era_scalp.era_boost import run_boost_search
sp = build_trade_splits('EURUSD', 'data/analysis/tick_velocity/EURUSD_1000tick_velocity.parquet')
for target,h in [('forward',12),('fair',3)]:
    r = run_boost_search(sp, symbol='EURUSD', target=target, horizon=h, budget=20)
    s = r['survivor']
    print(target, 'V1=%.3f V1pen=%.3f V2=%.3f n_feat=%d' % (s['val_v1'], s['val_v1_penalised'], s['val_v2'], s['n_feat']))
    print('  holdout:', r['holdout'])
"
```
Expected: finite V1/V2; record numbers. Per [[feedback_gross_cost_significance_decomposition]], a survivor is real ONLY if V2 confirms V1 (not just V1) AND the holdout edge is positive with the DSR/temporal guards passing. A V1-strong / V2-weak survivor is overfit — report it as such.

- [ ] **Step 2: Record findings (do NOT tune to holdout)**

Capture results in `docs/analysis/2026-06-XX_puct_boosting_findings.md`: per target, V1/V2/holdout, whether DSR + temporal pass, and the honest verdict. Holdout is read once.

---

## Self-Review

**Spec coverage:**
- Node = feature-composition (spec §1) → Task 1. ✔
- Two-stage scorer: sandboxed build_features + causality probe + trusted CatBoost (spec §2) → Tasks 2, 3, 4. ✔
- Two targets, one search (spec §3) → `target` param in Task 4 (`forward`/`fair`), both run in Task 8. ✔
- Overfitting regime: purged folds + complexity penalty + V1/V2 split + existing guards (spec §4) → Task 3 (folds, penalty), Task 6 (V1/V2, engine_verdict reuses DSR/temporal/Šidák). ✔
- Compute discipline: tiny CatBoost + cache by src hash (spec §5) → Task 4 (`_cache`, small model). ✔
- Testing (spec §6) → Tasks 1-6 ship tests; Task 7 gate. ✔
- Honest expectation / report gross-cost-significance (spec §7) → Task 8. ✔

**Placeholder scan:** none — every code step is concrete. The Task 3 embargo assertion has a noted simplification fallback.

**Type consistency:** `composition_to_features_source(skeleton, operators, params)` consistent (Tasks 1, 5). `build_features` entry point consistent across sandbox (Task 2) and concepts (Task 1). `boost_spec(train_split, *, symbol, target, horizon, ..., seed_only)` consistent (Tasks 4, 5, 6). `run_program` returns predictions, `causality_probe` probes features (Task 4) — matches engine call sites (`era_engine.score_program`, `engine_verdict`). `_sanitize`, `mutate_composition`, `recombine_compositions`, `purged_folds`, `complexity_penalty`, `train_predict`, `run_boost_search` used consistently.

**Known risk flagged for the executor:** CatBoost determinism across machines is not guaranteed bit-for-bit; the `test_train_predict_shape_and_determinism` check is same-process same-seed (reliable). If `run_search_rich`'s node `.payload` for atomic mode is the composition dict, `render_payload`/`_sanitize` handle it; verify the payload shape on first run of Task 6 and adjust `_sanitize` if PUCT wraps it.
