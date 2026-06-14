# Intraday Cross-Sectional FX Basket Book — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a long/short cross-sectional FX basket book as a new ERA `RunSpec`, sibling to the single-leg `era_xs`, reusing the engine's verdict machinery.

**Architecture:** A symmetric `BasketContext` (no target symbol) carries USD-aligned returns for all `CROSS_SYMBOLS`. A program outputs a `(n_bars, n_sym)` cross-sectional score; a banded, dollar-neutral, top-k/bottom-k `score_frame` turns that into a per-rebalance net P&L frame under an aggressive/passive cost toggle. Periodic-rebalance-at-horizon P&L sits behind a swappable `holding_model` hook. The net frame feeds `edge_verdict` / DSR / temporal-robustness unchanged.

**Tech Stack:** Python 3.12, numpy, pandas, `uv run pytest`, existing `scripts/era*` modules. Spec: `docs/superpowers/specs/2026-06-06-era-basket-cross-sectional-design.md`.

**Conventions (this repo):**
- Run tests with `uv run pytest -q <path>`.
- Before any PR run `make quality` (ty + ruff + …), not just pytest — collection errors redden the whole job.
- Programs in the sandbox may use only `np`; no imports, no `np.random`, no dunder access, no forward indexing.
- Commit after every passing task. Work stays in this worktree; merge via PR.

---

## File Structure

| File | Responsibility |
|---|---|
| `scripts/era_scalp/basket_context.py` | `BasketContext` (symmetric ctx for programs) + `BasketSplit` (panel data). |
| `scripts/era_scalp/basket_sandbox.py` | `static_check` / `run_program` / `causality_probe` for `(n_bars, n_sym)` `score(ctx)` programs. |
| `scripts/era_scalp/basket_panel.py` | `build_basket_panel(...)` → `{train,validation,holdout}` of `BasketSplit`. |
| `scripts/era_scalp/basket_score.py` | `rank_to_weights`, `apply_band`, `periodic_rebalance` holding model, `make_basket_score_frame`. |
| `scripts/era_scalp/basket_seeds.py` | Three canonical seed programs + research-idea prompts. |
| `scripts/era_scalp/era_basket.py` | `basket_spec(...) -> RunSpec` wiring context/sandbox/score/seeds into the engine. |
| `tests/era_scalp/test_basket_context.py` | Context + split shape/accessor tests. |
| `tests/era_scalp/test_basket_sandbox.py` | 2-D output + causality probe tests. |
| `tests/era_scalp/test_basket_panel.py` | Panel alignment + no-leak tests. |
| `tests/era_scalp/test_basket_score.py` | Neutrality, band turnover monotonicity, cost monotonicity, non-overlap, determinism. |
| `tests/era_scalp/test_basket_seeds.py` | Seeds execute + pass causality probe. |
| `tests/era_scalp/test_era_basket_spec.py` | `basket_spec` builds a valid `RunSpec`; `score_program` runs end-to-end on a tiny split. |

---

## Task 1: `BasketContext` + `BasketSplit`

**Files:**
- Create: `scripts/era_scalp/basket_context.py`
- Test: `tests/era_scalp/test_basket_context.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/era_scalp/test_basket_context.py
import numpy as np
from scripts.era_scalp.basket_context import BasketContext, BasketSplit


def test_context_shape_and_dispersion():
    r = np.array([[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]])
    ctx = BasketContext(r=r, names=["a", "b", "c"], hour=None)
    assert ctx.n_bars == 2
    assert ctx.n_sym == 3
    assert np.allclose(ctx.dispersion(), r.std(axis=1))


def test_split_carries_panels():
    n, m = 4, 3
    split = BasketSplit(
        r=np.zeros((n, m)),
        y_fwd_panel=np.ones((n, m)),
        cost_panel=np.full((n, m), 0.5),
        names=["a", "b", "c"],
        test_month=np.array(["2025-01"] * n),
        hour=np.zeros(n),
    )
    assert split.r.shape == (n, m)
    assert split.y_fwd_panel.shape == (n, m)
    assert split.cost_panel.shape == (n, m)
    assert len(split.test_month) == n
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest -q tests/era_scalp/test_basket_context.py`
Expected: FAIL with `ModuleNotFoundError: scripts.era_scalp.basket_context`.

- [ ] **Step 3: Write minimal implementation**

```python
# scripts/era_scalp/basket_context.py
from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass
class BasketContext:
    """Symmetric cross-section handed to a candidate basket program.

    r: (n_bars, n_sym) USD-aligned vol-normalised returns, columns ordered by `names`.
    Carries NO forward/label data. There is no 'target' — every symbol is rankable.
    """

    r: np.ndarray
    names: list[str]
    hour: np.ndarray | None = None

    @property
    def n_bars(self) -> int:
        return int(self.r.shape[0])

    @property
    def n_sym(self) -> int:
        return int(self.r.shape[1])

    def dispersion(self) -> np.ndarray:
        """Per-bar cross-sectional standard deviation of returns."""
        return self.r.std(axis=1)


@dataclass
class BasketSplit:
    """Panel data for one split (train/validation/holdout), aligned on a common bar grid.

    r:          (n_bars, n_sym) USD-aligned returns for ranking (the program input).
    y_fwd_panel:(n_bars, n_sym) each symbol's forward return at the build horizon.
    cost_panel: (n_bars, n_sym) each symbol's per-leg round-trip cost (pips).
    """

    r: np.ndarray
    y_fwd_panel: np.ndarray
    cost_panel: np.ndarray
    names: list[str]
    test_month: np.ndarray
    hour: np.ndarray | None = None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest -q tests/era_scalp/test_basket_context.py`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add scripts/era_scalp/basket_context.py tests/era_scalp/test_basket_context.py
git commit -m "feat(era-basket): BasketContext + BasketSplit panel dataclasses"
```

---

## Task 2: `basket_sandbox` — 2-D `score(ctx)` execution

**Files:**
- Create: `scripts/era_scalp/basket_sandbox.py`
- Test: `tests/era_scalp/test_basket_sandbox.py`

The existing `scripts/era_scalp/sandbox.py` `reshape(-1)`s output to 1-D and requires length `== n_bars`; a basket program returns `(n_bars, n_sym)`. This module is a sibling sandbox with a 2-D contract. It reuses the `static_check` rules (no imports / dunder / `np.random` / forbidden names) but requires `score(ctx)` and validates a 2-D shape.

- [ ] **Step 1: Write the failing test**

```python
# tests/era_scalp/test_basket_sandbox.py
import numpy as np
from scripts.era_scalp.basket_context import BasketContext
from scripts.era_scalp.basket_sandbox import causality_probe, run_program, static_check

CAUSAL = """
def score(ctx):
    r = ctx.r
    n, m = r.shape
    out = np.full((n, m), np.nan)
    c = np.cumsum(np.nan_to_num(r), axis=0)
    w = 3
    for t in range(n):
        lo = t - w + 1
        if lo < 0:
            continue
        s = c[t] - (c[lo - 1] if lo > 0 else 0.0)
        out[t] = -s
    return out
"""

NONCAUSAL = """
def score(ctx):
    r = ctx.r
    # reads the FULL column (future rows) -> must be rejected
    return -(r - r.mean(axis=0))
"""

BADSHAPE = """
def score(ctx):
    return ctx.r[:, 0]
"""


def _ctx(n=12, m=4, seed=0):
    rng = np.random.default_rng(seed)
    return BasketContext(r=rng.standard_normal((n, m)), names=list("abcd"), hour=None)


def test_static_check_requires_score():
    ok, _ = static_check("def residual(ctx):\n    return ctx.r")
    assert not ok
    ok, _ = static_check(CAUSAL)
    assert ok


def test_run_program_returns_2d():
    ctx = _ctx()
    out, err, _ = run_program(CAUSAL, ctx)
    assert err is None
    assert out.shape == (ctx.n_bars, ctx.n_sym)


def test_run_program_rejects_bad_shape():
    out, err, _ = run_program(BADSHAPE, _ctx())
    assert out is None
    assert err is not None


def test_causality_probe_passes_causal_rejects_noncausal():
    ctx = _ctx()
    out, err, _ = run_program(CAUSAL, ctx)
    assert err is None
    ok, _ = causality_probe(CAUSAL, ctx, out)
    assert ok

    out2, err2, _ = run_program(NONCAUSAL, ctx)
    assert err2 is None
    ok2, _ = causality_probe(NONCAUSAL, ctx, out2)
    assert not ok2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest -q tests/era_scalp/test_basket_sandbox.py`
Expected: FAIL with `ModuleNotFoundError: scripts.era_scalp.basket_sandbox`.

- [ ] **Step 3: Write minimal implementation**

```python
# scripts/era_scalp/basket_sandbox.py
from __future__ import annotations

import ast
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np

from scripts.era_scalp.basket_context import BasketContext

_FORBIDDEN_NAMES = {"open", "eval", "exec", "compile", "globals", "locals",
                    "vars", "getattr", "setattr", "delattr", "__import__", "input"}


def static_check(src: str, required_fn: str = "score") -> tuple[bool, str]:
    """Reject imports, dunder access, np.random, dangerous builtins. Require score(ctx)."""
    try:
        tree = ast.parse(src)
    except SyntaxError as e:
        return False, f"syntax error: {e}"
    has_fn = False
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            return False, "imports are not allowed"
        if isinstance(node, ast.Attribute) and node.attr.startswith("__"):
            return False, f"dunder attribute access not allowed: {node.attr}"
        if (
            isinstance(node, ast.Attribute)
            and node.attr == "random"
            and isinstance(node.value, ast.Name)
            and node.value.id == "np"
        ):
            return False, "np.random is not allowed (non-deterministic)"
        if isinstance(node, ast.Name) and node.id in _FORBIDDEN_NAMES:
            return False, f"forbidden name: {node.id}"
        if isinstance(node, ast.FunctionDef) and node.name == required_fn:
            has_fn = True
    if not has_fn:
        return False, f"must define {required_fn}(ctx)"
    return True, "ok"


_WORKER = r"""
import sys, numpy as np
from scripts.era_scalp.basket_context import BasketContext
payload = np.load(sys.argv[1], allow_pickle=True)
src = str(payload["src"])
hour = payload["hour"]; hour = None if hour.size == 0 else hour
ctx = BasketContext(r=payload["r"], names=list(payload["names"]), hour=hour)
ns = {"np": np}
try:
    exec(src, ns)
    out = np.asarray(ns["score"](ctx), dtype=float)
    if out.shape != (ctx.n_bars, ctx.n_sym):
        raise ValueError(f"score shape {out.shape} != (n_bars, n_sym) {(ctx.n_bars, ctx.n_sym)}")
    np.save(sys.argv[2], out)
    print("OK")
except Exception as e:
    print(f"ERR {type(e).__name__}: {e}", file=sys.stderr)
    sys.exit(3)
"""


def run_program(src: str, ctx: BasketContext, timeout: float = 10.0, required_fn: str = "score"):
    """Return (score_2d | None, error | None, logs)."""
    ok, reason = static_check(src, required_fn=required_fn)
    if not ok:
        return None, f"static_check: {reason}", ""
    with tempfile.TemporaryDirectory() as d:
        inp = Path(d) / "in.npz"
        out = Path(d) / "out.npy"
        wrk = Path(d) / "w.py"
        np.savez(
            inp,
            src=src,
            r=ctx.r,
            names=np.array(ctx.names),
            hour=ctx.hour if ctx.hour is not None else np.array([]),
        )
        wrk.write_text(_WORKER)
        try:
            env = dict(os.environ)
            env["PYTHONPATH"] = str(Path.cwd()) + os.pathsep + env.get("PYTHONPATH", "")
            proc = subprocess.run(
                [sys.executable, str(wrk), str(inp), str(out)],
                capture_output=True, text=True, timeout=timeout,
                cwd=str(Path.cwd()), env=env,
            )
        except subprocess.TimeoutExpired:
            return None, "timeout", ""
        logs = (proc.stdout + proc.stderr).strip()
        if proc.returncode != 0 or not out.exists():
            return None, logs or f"exit {proc.returncode}", logs
        return np.load(out), None, logs


def _arrays_match(a: np.ndarray, b: np.ndarray) -> bool:
    a = np.asarray(a, float)
    b = np.asarray(b, float)
    na, nb = np.isnan(a), np.isnan(b)
    if not np.array_equal(na, nb):
        return False
    return bool(np.allclose(a[~na], b[~nb], rtol=1e-9, atol=1e-9))


def causality_probe(src, ctx, clean_score, n_cuts: int = 5, seed: int = 0,
                    required_fn: str = "score", nan_frac: float = 0.3):
    """Reject programs whose past scores depend on future bars.

    For each interior cut k, rows > k are replaced with large finite noise (and a
    nan_frac fraction set to NaN); the program is re-run and score[:k+1, :] must be
    unchanged vs the clean run."""
    n = ctx.n_bars
    if n < 6:
        return True, "too-short-to-probe"
    rng = np.random.default_rng(seed)
    clean = np.asarray(clean_score, float)
    cuts = [max(1, n * (i + 1) // (n_cuts + 1)) for i in range(n_cuts)]
    for k in cuts:
        r2 = ctx.r.copy()
        fut = r2[k + 1:, :]
        fut[:] = rng.standard_normal(fut.shape) * 10.0
        if fut.size:
            fut[rng.random(fut.shape) < nan_frac] = np.nan
        r2[k + 1:, :] = fut
        hour2 = None
        if ctx.hour is not None:
            hour2 = ctx.hour.copy()
            hour2[k + 1:] = rng.integers(0, 24, size=hour2[k + 1:].shape).astype(float)
        ctx2 = BasketContext(r=r2, names=ctx.names, hour=hour2)
        score2, err, _ = run_program(src, ctx2, timeout=10.0, required_fn=required_fn)
        if err is not None:
            return False, f"non-causal: errors under future perturbation at k={k}: {err}"
        if not _arrays_match(clean[: k + 1, :], np.asarray(score2, float)[: k + 1, :]):
            return False, f"non-causal: score[:{k + 1}] changed when future bars perturbed"
    return True, "ok"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest -q tests/era_scalp/test_basket_sandbox.py`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add scripts/era_scalp/basket_sandbox.py tests/era_scalp/test_basket_sandbox.py
git commit -m "feat(era-basket): 2-D score(ctx) sandbox with causality probe"
```

---

## Task 3: `basket_score` — weights, band, periodic-rebalance P&L

**Files:**
- Create: `scripts/era_scalp/basket_score.py`
- Test: `tests/era_scalp/test_basket_score.py`

This is the keystone. `rank_to_weights` produces dollar-neutral top-k/bottom-k weights. `apply_band` is a **book-level L1 turnover band**: carry the previous weights unless the L1 distance to the fresh target exceeds `band` (neutrality is trivially preserved because both prev and target are neutral). `periodic_rebalance` steps in non-overlapping blocks of `h`, applies an optional session gate, and charges cost via the aggressive/passive toggle. `make_basket_score_frame` binds the parameters into the `(out, split, q, h)` signature the engine calls (q is unused — band/k/fill are RunSpec-fixed).

(Per-symbol rank hysteresis is a documented future refinement; v1 uses the book-level L1 band.)

- [ ] **Step 1: Write the failing test**

```python
# tests/era_scalp/test_basket_score.py
import numpy as np
from scripts.era_scalp.basket_context import BasketSplit
from scripts.era_scalp.basket_score import (
    apply_band,
    make_basket_score_frame,
    periodic_rebalance,
    rank_to_weights,
)


def test_weights_dollar_neutral():
    s = np.array([3.0, 1.0, 2.0, -1.0, 0.5, -2.0])
    w = rank_to_weights(s, k=2)
    assert abs(w.sum()) < 1e-12
    assert np.isclose(w.max(), 0.5)   # 1/k
    assert np.isclose(w.min(), -0.5)
    assert int((w > 0).sum()) == 2 and int((w < 0).sum()) == 2


def test_weights_insufficient_finite_returns_zero():
    s = np.array([np.nan, np.nan, 1.0])
    assert np.allclose(rank_to_weights(s, k=2), 0.0)


def test_apply_band_carries_when_small_move():
    prev = np.array([0.5, -0.5, 0.0])
    target = np.array([0.5, 0.0, -0.5])  # L1 distance = 1.0
    assert np.allclose(apply_band(prev, target, band=2.0), prev)   # carried
    assert np.allclose(apply_band(prev, target, band=0.0), target)  # rebalanced


def _panel_split(n=20, m=4, seed=1):
    rng = np.random.default_rng(seed)
    return BasketSplit(
        r=rng.standard_normal((n, m)),
        y_fwd_panel=rng.standard_normal((n, m)),
        cost_panel=np.full((n, m), 0.2),
        names=list("abcd"),
        test_month=np.array(["2025-01"] * n),
        hour=np.full(n, 13.0),
    )


def test_periodic_rebalance_neutral_and_nonoverlap():
    split = _panel_split()
    scores = split.r.copy()
    frame = periodic_rebalance(scores, split, h=4, k=1, band=0.0,
                               fill_mode="aggressive", passive_frac=0.5, session=None)
    # non-overlapping bars 0,4,8,12 within n=20 minus horizon -> 4 rows
    assert len(frame) == 4
    assert set(frame.columns) == {"net", "test_month"}


def test_passive_cost_lower_than_aggressive():
    split = _panel_split()
    scores = split.r.copy()
    agg = periodic_rebalance(scores, split, h=4, k=1, band=0.0,
                             fill_mode="aggressive", passive_frac=0.5, session=None)
    pas = periodic_rebalance(scores, split, h=4, k=1, band=0.0,
                             fill_mode="passive", passive_frac=0.5, session=None)
    # identical gross, passive pays less cost -> passive net >= aggressive net, summed
    assert pas["net"].sum() >= agg["net"].sum()


def test_larger_band_reduces_turnover():
    split = _panel_split(n=60, seed=7)
    scores = split.r.copy()

    def turnover(band):
        prev = np.zeros(split.r.shape[1])
        total = 0.0
        for t in range(0, scores.shape[0] - 4, 4):
            target = rank_to_weights(scores[t], k=1)
            w = apply_band(prev, target, band)
            total += np.abs(w - prev).sum()
            prev = w
        return total

    assert turnover(10.0) <= turnover(0.0)


def test_score_frame_deterministic():
    split = _panel_split()
    sf = make_basket_score_frame(k=1, band=0.0, fill_mode="aggressive",
                                 passive_frac=0.5, session=None)
    a = sf(split.r.copy(), split, 0.0, 4)
    b = sf(split.r.copy(), split, 0.0, 4)
    assert a.equals(b)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest -q tests/era_scalp/test_basket_score.py`
Expected: FAIL with `ModuleNotFoundError: scripts.era_scalp.basket_score`.

- [ ] **Step 3: Write minimal implementation**

```python
# scripts/era_scalp/basket_score.py
from __future__ import annotations

import numpy as np
import pandas as pd


def rank_to_weights(s: np.ndarray, k: int) -> np.ndarray:
    """Dollar-neutral top-k/bottom-k weights: long top-k (+1/k), short bottom-k (-1/k).

    Returns all-zero (flat) when fewer than 2*k finite scores are available."""
    s = np.asarray(s, float)
    m = s.shape[0]
    w = np.zeros(m)
    finite = np.where(np.isfinite(s))[0]
    if finite.size < 2 * k:
        return w
    order = finite[np.argsort(s[finite], kind="stable")]
    shorts = order[:k]
    longs = order[-k:]
    w[longs] = 1.0 / k
    w[shorts] = -1.0 / k
    return w


def apply_band(prev_w: np.ndarray, target_w: np.ndarray, band: float) -> np.ndarray:
    """Book-level L1 turnover band: carry prev weights unless the L1 distance to the
    fresh target exceeds `band`. Both prev and target are dollar-neutral, so the carried
    book stays neutral. band=0 -> always rebalance; large band -> rarely rebalance."""
    if float(np.abs(np.asarray(target_w) - np.asarray(prev_w)).sum()) <= band:
        return np.asarray(prev_w, float)
    return np.asarray(target_w, float)


def _session_ok(hour_val, session) -> bool:
    if session is None:
        return True
    lo, hi = session
    return bool(lo <= hour_val < hi)


def periodic_rebalance(scores, split, h, *, k, band, fill_mode, passive_frac, session):
    """Periodic rebalance at horizon h. Step in non-overlapping blocks of h bars;
    form dollar-neutral top-k/bottom-k weights, apply the turnover band, and book
    net = (gross forward P&L) - (turnover * per-leg cost). One row per rebalance.

    fill_mode: 'aggressive' charges the full cost_panel spread; 'passive' charges
    passive_frac of it (earning rather than paying part of the spread)."""
    scores = np.asarray(scores, float)
    y = np.asarray(split.y_fwd_panel, float)
    cost = np.asarray(split.cost_panel, float)
    tm = np.asarray(split.test_month)
    hour = split.hour
    n, m = scores.shape
    prev_w = np.zeros(m)
    nets, months = [], []
    for t in range(0, n - h, h):
        if session is not None and (hour is None or not _session_ok(hour[t], session)):
            continue
        s = scores[t]
        if not np.isfinite(s).any():
            continue
        target = rank_to_weights(s, k)
        w = apply_band(prev_w, target, band)
        gross = float(np.nansum(w * y[t]))
        turn = np.abs(w - prev_w)
        per_leg = cost[t] if fill_mode == "aggressive" else cost[t] * passive_frac
        c = float(np.nansum(turn * per_leg))
        nets.append(gross - c)
        months.append(tm[t])
        prev_w = w
    return pd.DataFrame({"net": np.asarray(nets, float), "test_month": np.asarray(months)})


def make_basket_score_frame(*, k, band, fill_mode, passive_frac, session,
                            holding_model=periodic_rebalance):
    """Bind basket parameters into the engine's (out, split, q, h) score_frame signature.

    q is unused (k/band/fill are RunSpec-fixed, not grid-swept). holding_model is the
    swappable P&L strategy; periodic_rebalance is v1."""
    def score_frame(out, split, q, h):
        return holding_model(out, split, h, k=k, band=band, fill_mode=fill_mode,
                             passive_frac=passive_frac, session=session)
    return score_frame
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest -q tests/era_scalp/test_basket_score.py`
Expected: PASS (7 passed).

- [ ] **Step 5: Commit**

```bash
git add scripts/era_scalp/basket_score.py tests/era_scalp/test_basket_score.py
git commit -m "feat(era-basket): dollar-neutral banded periodic-rebalance score frame"
```

---

## Task 4: `basket_panel` — build aligned panels from the cross-symbol frames

**Files:**
- Create: `scripts/era_scalp/basket_panel.py`
- Test: `tests/era_scalp/test_basket_panel.py`

Reuse `get_or_build_cross_symbol_frame` (already look-ahead-free) for the reference grid + the `xs_ret_z__{sym}` columns (→ `r`). For each symbol's own forward return and cost, read that symbol's cross frame and `merge_asof(direction="backward")` onto the reference grid, so each reference bar at time `T` sees only that symbol's bar with `close_ts <= T`. The test injects two tiny fake frames via monkeypatch to keep it offline and deterministic.

- [ ] **Step 1: Write the failing test**

```python
# tests/era_scalp/test_basket_panel.py
import numpy as np
import pandas as pd
import pytest

import scripts.era_scalp.basket_panel as bp
from scripts.cross_symbol import CROSS_SYMBOLS


def _fake_frame(symbol, horizon, n=12):
    ts = pd.date_range("2025-01-01", periods=n, freq="h", tz="UTC")
    df = pd.DataFrame({"close_ts": ts})
    df["ret_z"] = np.linspace(-1, 1, n) + CROSS_SYMBOLS.index(symbol)
    for s in CROSS_SYMBOLS:
        df[f"xs_ret_z__{s}"] = np.linspace(-1, 1, n) + CROSS_SYMBOLS.index(s)
    df[f"y_fwd_pips_h{horizon}"] = np.full(n, float(CROSS_SYMBOLS.index(symbol)))
    df["cost_est_pips"] = np.full(n, 0.3)
    df["hour_utc"] = df["close_ts"].dt.hour
    return df


def test_panel_shapes_and_per_symbol_yfwd(monkeypatch):
    monkeypatch.setattr(
        bp, "get_or_build_cross_symbol_frame",
        lambda symbol, bar_ticks, velocity_dir, horizons: _fake_frame(symbol, horizons[0]),
    )
    splits = bp.build_basket_panel(
        bar_ticks=100, velocity_dir="/tmp/unused", horizon=3,
        train=("2025-01",), validation=("2025-01",), holdout=("2025-01",),
    )
    tr = splits["train"]
    m = len(CROSS_SYMBOLS)
    assert tr.r.shape[1] == m
    assert tr.y_fwd_panel.shape == tr.r.shape == tr.cost_panel.shape
    # each column's y_fwd equals that symbol's constant (index), proving per-symbol placement
    for j, s in enumerate(tr.names):
        col = tr.y_fwd_panel[:, j]
        assert np.allclose(col[np.isfinite(col)], float(CROSS_SYMBOLS.index(s)))
    assert tr.names == list(CROSS_SYMBOLS)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest -q tests/era_scalp/test_basket_panel.py`
Expected: FAIL with `ModuleNotFoundError: scripts.era_scalp.basket_panel` (or `AttributeError` on the monkeypatch target).

- [ ] **Step 3: Write minimal implementation**

```python
# scripts/era_scalp/basket_panel.py
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from scripts.cross_symbol import CROSS_SYMBOLS, _USD_SIGN, get_or_build_cross_symbol_frame
from scripts.era_scalp.basket_context import BasketSplit

_REFERENCE = "eurusd"


def build_basket_panel(
    bar_ticks: int,
    velocity_dir,
    horizon: int = 3,
    train=("2025-01", "2025-02", "2025-03", "2025-04", "2025-05", "2025-06"),
    validation=("2025-07", "2025-08", "2025-09", "2025-10"),
    holdout=("2025-11", "2025-12", "2026-01", "2026-02"),
):
    """Build {train,validation,holdout} BasketSplits aligned on the reference grid.

    r comes from the reference frame's xs_ret_z__{sym} columns (USD-aligned, all symbols).
    y_fwd_panel / cost_panel are each symbol's own forward return / cost, merged backward
    (look-ahead-free) onto the reference close_ts grid."""
    velocity_dir = Path(velocity_dir)
    ref = get_or_build_cross_symbol_frame(_REFERENCE, bar_ticks, velocity_dir, [horizon]).copy()
    ref["close_ts"] = pd.to_datetime(ref["close_ts"], utc=True)
    # reference's own usd-aligned column (mirrors cross_symbol._usd_aligned_ret_z)
    ref[f"xs_ret_z__{_REFERENCE}"] = int(_USD_SIGN[_REFERENCE]) * pd.to_numeric(
        ref["ret_z"], errors="coerce"
    )
    ref["test_month"] = ref["close_ts"].dt.strftime("%Y-%m")
    ref = ref.sort_values("close_ts").reset_index(drop=True)

    ycol = f"y_fwd_pips_h{horizon}"
    base = ref[["close_ts", "test_month", "hour_utc"]].copy()
    r_cols = [f"xs_ret_z__{s}" for s in CROSS_SYMBOLS]
    r_panel = ref[r_cols].copy()

    # per-symbol forward-return + cost, merged backward onto the reference grid
    yfwd = pd.DataFrame(index=ref.index)
    cost = pd.DataFrame(index=ref.index)
    for s in CROSS_SYMBOLS:
        cs = get_or_build_cross_symbol_frame(s, bar_ticks, velocity_dir, [horizon]).copy()
        cs["close_ts"] = pd.to_datetime(cs["close_ts"], utc=True)
        right = cs[["close_ts", ycol, "cost_est_pips"]].dropna(subset=["close_ts"])
        right = right.sort_values("close_ts").reset_index(drop=True)
        merged = pd.merge_asof(base[["close_ts"]], right, on="close_ts", direction="backward")
        yfwd[s] = merged[ycol].to_numpy(float)
        cost[s] = merged["cost_est_pips"].to_numpy(float)

    def _split(months):
        mask = base["test_month"].isin(months).to_numpy()
        return BasketSplit(
            r=r_panel.to_numpy(float)[mask],
            y_fwd_panel=yfwd.to_numpy(float)[mask],
            cost_panel=cost.to_numpy(float)[mask],
            names=list(CROSS_SYMBOLS),
            test_month=base["test_month"].to_numpy()[mask],
            hour=base["hour_utc"].to_numpy(float)[mask],
        )

    return {"train": _split(train), "validation": _split(validation), "holdout": _split(holdout)}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest -q tests/era_scalp/test_basket_panel.py`
Expected: PASS (1 passed).

- [ ] **Step 5: Commit**

```bash
git add scripts/era_scalp/basket_panel.py tests/era_scalp/test_basket_panel.py
git commit -m "feat(era-basket): look-ahead-free per-symbol panel builder"
```

---

## Task 5: `basket_seeds` — canonical reversal / momentum / lead-lag

**Files:**
- Create: `scripts/era_scalp/basket_seeds.py`
- Test: `tests/era_scalp/test_basket_seeds.py`

Three causal `score(ctx)` programs (np-only, cumulative windows so they stay causal under the probe) plus research-idea prompts for the generator.

- [ ] **Step 1: Write the failing test**

```python
# tests/era_scalp/test_basket_seeds.py
import numpy as np
from scripts.era_scalp.basket_context import BasketContext
from scripts.era_scalp.basket_sandbox import causality_probe, run_program
from scripts.era_scalp.basket_seeds import BASKET_RESEARCH_IDEAS, BASKET_SEED_PROGRAMS


def _ctx(n=24, m=6, seed=3):
    rng = np.random.default_rng(seed)
    return BasketContext(r=rng.standard_normal((n, m)), names=list("abcdef"), hour=None)


def test_seeds_present():
    assert set(BASKET_SEED_PROGRAMS) == {"reversal", "momentum", "lead_lag"}
    assert len(BASKET_RESEARCH_IDEAS) >= 3


def test_seeds_execute_and_are_causal():
    ctx = _ctx()
    for name, src in BASKET_SEED_PROGRAMS.items():
        out, err, logs = run_program(src, ctx)
        assert err is None, f"{name} exec error: {err}\n{logs}"
        assert out.shape == (ctx.n_bars, ctx.n_sym)
        ok, reason = causality_probe(src, ctx, out)
        assert ok, f"{name} not causal: {reason}"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest -q tests/era_scalp/test_basket_seeds.py`
Expected: FAIL with `ModuleNotFoundError: scripts.era_scalp.basket_seeds`.

- [ ] **Step 3: Write minimal implementation**

```python
# scripts/era_scalp/basket_seeds.py
"""Canonical intraday cross-sectional basket seeds (causal, np-only).

Each program defines score(ctx) -> (n_bars, n_sym). Windows use cumulative sums so a
row at index t depends only on rows <= t (passes the basket causality probe)."""
from __future__ import annotations

# Cross-sectional reversal: fade recent relative winners (short strong, long weak).
REVERSAL = """
def score(ctx):
    r = ctx.r
    n, m = r.shape
    out = np.full((n, m), np.nan)
    c = np.cumsum(np.nan_to_num(r), axis=0)
    w = 5
    for t in range(n):
        lo = t - w + 1
        if lo < 0:
            continue
        s = c[t] - (c[lo - 1] if lo > 0 else 0.0)
        out[t] = -s
    return out
"""

# Relative momentum: ride recent relative winners (long strong, short weak).
MOMENTUM = """
def score(ctx):
    r = ctx.r
    n, m = r.shape
    out = np.full((n, m), np.nan)
    c = np.cumsum(np.nan_to_num(r), axis=0)
    w = 10
    for t in range(n):
        lo = t - w + 1
        if lo < 0:
            continue
        out[t] = c[t] - (c[lo - 1] if lo > 0 else 0.0)
    return out
"""

# Lead-lag: laggards catch up to the basket's prior-bar move (Hasbrouck-style).
# score = (basket mean move at t-1) - (own move at t-1): long under-reactors.
LEAD_LAG = """
def score(ctx):
    r = ctx.r
    n, m = r.shape
    out = np.full((n, m), np.nan)
    prev = np.nan_to_num(r)
    for t in range(1, n):
        lead = prev[t - 1].mean()
        out[t] = lead - prev[t - 1]
    return out
"""

BASKET_SEED_PROGRAMS = {
    "reversal": REVERSAL,
    "momentum": MOMENTUM,
    "lead_lag": LEAD_LAG,
}

BASKET_RESEARCH_IDEAS = [
    "Cross-sectional reversal over a short lookback: rank pairs by recent USD-aligned "
    "return and fade the extremes (long laggards, short leaders).",
    "Relative momentum over a longer lookback: ride the persistent relative winners.",
    "Lead-lag: predict each pair's move from the basket's prior-bar move; go long "
    "under-reactors and short over-reactors.",
    "Dispersion-conditioned reversal: only express the ranking when cross-sectional "
    "dispersion is elevated (more relative-value to harvest).",
]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest -q tests/era_scalp/test_basket_seeds.py`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add scripts/era_scalp/basket_seeds.py tests/era_scalp/test_basket_seeds.py
git commit -m "feat(era-basket): canonical reversal/momentum/lead-lag seeds"
```

---

## Task 6: `basket_spec` — assemble the `RunSpec`

**Files:**
- Create: `scripts/era_scalp/era_basket.py`
- Test: `tests/era_scalp/test_era_basket_spec.py`

Wire context/sandbox/score/seeds into a `RunSpec` the engine's `score_program` can drive. Use a single-cell grid (`grid_q=[0.0]`, `grid_h=[horizon]`) with `aggregate="robust"` (single cell ⇒ value = the cell's lower bound). The context factory adapts a `BasketSplit` to a `BasketContext`. The sandbox wrappers ignore `required_fn` plumbing beyond defaulting it to `"score"`.

- [ ] **Step 1: Write the failing test**

```python
# tests/era_scalp/test_era_basket_spec.py
import numpy as np
from scripts.era_scalp.basket_context import BasketSplit
from scripts.era_scalp.basket_seeds import BASKET_SEED_PROGRAMS
from scripts.era_scalp.era_basket import basket_spec
from scripts.era_scalp.era_engine import score_program


def _split(n=40, m=6, seed=2):
    rng = np.random.default_rng(seed)
    return BasketSplit(
        r=rng.standard_normal((n, m)),
        y_fwd_panel=rng.standard_normal((n, m)) * 0.5,
        cost_panel=np.full((n, m), 0.1),
        names=list("abcdef"),
        test_month=np.array([f"2025-{1 + (i % 3):02d}" for i in range(n)]),
        hour=np.full(n, 13.0),
    )


def test_basket_spec_fields():
    spec = basket_spec(horizon=3, k=2, band=0.0, fill_mode="aggressive")
    assert spec.required_fn == "score"
    assert spec.grid_h == [3]
    assert spec.aggregate == "robust"
    assert "reversal" in spec.seed_programs


def test_score_program_runs_end_to_end():
    spec = basket_spec(horizon=3, k=2, band=0.0, fill_mode="aggressive")
    split = _split()
    value, mean, se, logs = score_program(BASKET_SEED_PROGRAMS["reversal"], spec, split)
    assert np.isfinite(value)
    assert value > -1e6, f"program failed to score: {logs}"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest -q tests/era_scalp/test_era_basket_spec.py`
Expected: FAIL with `ModuleNotFoundError: scripts.era_scalp.era_basket`.

- [ ] **Step 3: Write minimal implementation**

```python
# scripts/era_scalp/era_basket.py
"""Intraday cross-sectional FX basket book as a RunSpec for the unified ERA engine.

Sibling to era_xs (single-leg residual fade): this is a dollar-neutral long/short basket.
A program outputs a (n_bars, n_sym) cross-sectional score; the score_frame ranks it into a
banded, top-k/bottom-k, cost-toggled per-rebalance net frame consumed by the shared engine
(guards: temporal robustness, DSR, effective-m Sidak, edge_verdict)."""
from __future__ import annotations

from scripts.era_scalp.basket_context import BasketContext
from scripts.era_scalp.basket_sandbox import causality_probe as _bk_causality_probe
from scripts.era_scalp.basket_sandbox import run_program as _bk_run_program
from scripts.era_scalp.basket_score import make_basket_score_frame, periodic_rebalance
from scripts.era_scalp.basket_seeds import BASKET_RESEARCH_IDEAS, BASKET_SEED_PROGRAMS
from scripts.era_scalp.era_engine import RunSpec

# London/NY overlap (UTC), the deepest-liquidity intraday window.
LONDON_NY_OVERLAP = (12, 16)


def basket_spec(
    horizon: int = 3,
    k: int = 2,
    band: float = 0.0,
    fill_mode: str = "aggressive",
    passive_frac: float = 0.5,
    session=None,
    holding_model=periodic_rebalance,
) -> RunSpec:
    """RunSpec for the cross-sectional basket book (data passed separately via splits).

    fill_mode='aggressive' is the gating verdict; score again with 'passive' to report
    the optimistic bound. session=LONDON_NY_OVERLAP restricts to the liquid window."""

    def context_factory(split):
        return BasketContext(r=split.r, names=split.names, hour=split.hour)

    def run_program(src, ctx, timeout=10.0, required_fn=None):
        return _bk_run_program(src, ctx, timeout=timeout)

    def causality_probe(src, ctx, out, required_fn=None):
        return _bk_causality_probe(src, ctx, out)

    score_frame = make_basket_score_frame(
        k=k, band=band, fill_mode=fill_mode, passive_frac=passive_frac,
        session=session, holding_model=holding_model,
    )

    return RunSpec(
        name=f"basket_k{k}_b{band}_{fill_mode}",
        required_fn="score",
        run_program=run_program,
        causality_probe=causality_probe,
        context_factory=context_factory,
        score_frame=score_frame,
        grid_q=[0.0],
        grid_h=[horizon],
        aggregate="robust",
        seed_programs=dict(BASKET_SEED_PROGRAMS),
        branch_tags={name: name for name in BASKET_SEED_PROGRAMS},
        ideas=list(BASKET_RESEARCH_IDEAS),
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest -q tests/era_scalp/test_era_basket_spec.py`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add scripts/era_scalp/era_basket.py tests/era_scalp/test_era_basket_spec.py
git commit -m "feat(era-basket): basket_spec RunSpec wiring engine + seeds"
```

---

## Task 7: Quality gate + full suite

**Files:** none (verification only).

- [ ] **Step 1: Run the new suite together**

Run: `uv run pytest -q tests/era_scalp/test_basket_context.py tests/era_scalp/test_basket_sandbox.py tests/era_scalp/test_basket_score.py tests/era_scalp/test_basket_panel.py tests/era_scalp/test_basket_seeds.py tests/era_scalp/test_era_basket_spec.py`
Expected: PASS (all green).

- [ ] **Step 2: Run the repo quality gate**

Run: `make quality`
Expected: ty + ruff + any other configured checks all pass. Fix any ty/ruff findings in the new files (e.g. unused imports, type hints) until clean. Do NOT skip — collection errors redden the whole CI job.

- [ ] **Step 3: Commit any quality fixes**

```bash
git add -A
git commit -m "chore(era-basket): satisfy ty/ruff quality gate"
```

(Skip the commit if `make quality` produced no changes.)

---

## Task 8: Smoke search on real data (manual, optional gate before PR)

**Files:** none (validation only). Requires velocity parquets symlinked into the worktree (`data/`).

- [ ] **Step 1: Confirm data is reachable**

Run: `ls data/tick_velocity/ 2>/dev/null | head` (or the repo's velocity dir). If absent, symlink per the project's data convention before proceeding.

- [ ] **Step 2: Build a panel and score the seeds end-to-end**

Run:
```bash
uv run python -c "
from scripts.era_scalp.basket_panel import build_basket_panel
from scripts.era_scalp.basket_seeds import BASKET_SEED_PROGRAMS
from scripts.era_scalp.era_basket import basket_spec
from scripts.era_scalp.era_engine import score_program
sp = build_basket_panel(bar_ticks=100, velocity_dir='data/tick_velocity', horizon=3)
for fill in ('aggressive','passive'):
    spec = basket_spec(horizon=3, k=2, band=0.0, fill_mode=fill)
    for name, src in BASKET_SEED_PROGRAMS.items():
        v,_,_,_ = score_program(src, spec, sp['validation'])
        print(fill, name, round(v,4))
"
```
Expected: finite values per (fill, seed); aggressive ≤ passive per seed. Record the numbers — this is the honest pre-search baseline (no claim of edge yet).

- [ ] **Step 3: Note results, do NOT tune band/k to holdout**

Capture the validation numbers in the PR description. Per the no-mirage discipline, band/k/passive_frac defaults are set conservatively and not optimized against the holdout. Holdout is touched only once, at verdict time.

---

## Self-Review

**Spec coverage:**
- Panel builder (spec §Data) → Task 4. ✔
- Symmetric `BasketContext` + `cross_score`/`score` contract (spec §Program contract) → Tasks 1, 2. ✔
- Periodic rebalance, dollar-neutral, banded, cost-toggled, session gate, non-overlap (spec §score_frame) → Task 3 (+ session wired in Task 6). ✔
- Holding-model hook for "design for both" (spec §4) → `holding_model` param in `make_basket_score_frame`/`basket_spec`. ✔
- Canonical seeds + evolve (spec §Seeds) → Task 5; engine evolution reuses `run_search_rich` via the assembled `RunSpec` (Task 6). ✔
- Reuse verdict machinery (spec §Relationship) → Task 6 returns a `RunSpec`; `score_program` (engine) consumed in Task 6 test. ✔
- Tests enumerated in spec §Testing → Tasks 1-6 each ship them; Task 7 runs the gate. ✔
- Aggressive gates verdict, passive reported (spec decision) → `fill_mode` param; Task 8 scores both. ✔

**Open-question defaults locked for v1:** `k=2` (long 2 / short 2 / middle 2 flat), `band=0.0` default with the band lever available, `passive_frac=0.5`, `session=None` by default (`LONDON_NY_OVERLAP` constant provided for opt-in). These are conservative starting points, not holdout-tuned.

**Type consistency:** `BasketContext(r, names, hour)` and `BasketSplit(r, y_fwd_panel, cost_panel, names, test_month, hour)` used identically across Tasks 1-6. `rank_to_weights(s, k)`, `apply_band(prev_w, target_w, band)`, `periodic_rebalance(scores, split, h, *, k, band, fill_mode, passive_frac, session)`, `make_basket_score_frame(*, k, band, fill_mode, passive_frac, session, holding_model)` consistent across Tasks 3, 6. Sandbox `run_program(src, ctx, timeout, required_fn)` / `causality_probe(src, ctx, out, required_fn)` match the engine's call sites (`era_engine.score_program` lines 145-148).

**Deviation from spec naming:** spec mentions `required_fn="cross_score"`; the plan uses `required_fn="score"` (the actual function name programs define), which is simpler and what the sandbox checks. Functionally equivalent; noted here for the reviewer.
