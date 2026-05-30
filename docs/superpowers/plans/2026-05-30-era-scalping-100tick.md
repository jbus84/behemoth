# ERA 100-tick Scalping Discovery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Apply the ERA search engine to discover a causally-valid, net-of-cost **directional scalping signal on 100-tick bars** for the USD majors, grounded in modern microstructure research (OU reversion, Hawkes bursts, multi-horizon OFI), with honest evaluation via embargoed splits + BH-FDR.

**Architecture:** New `scripts/era_scalp/` package that **reuses the engine** in `scripts/era/` (`puct`, `select`, `llm`, `sandbox.static_check`, `harness.task_score`, `sandbox._arrays_match`) by import, and adds scalping-specific `context` (single-symbol `FeatureContext`), `sandbox` (FeatureContext worker + causality probe), `harness` (directional), `seeds`, `load_splits` (embargoed), and `run_era_scalp` driver. The dispersion loop is untouched.

**Tech Stack:** Python 3.12, numpy, pandas, pyarrow, pytest, `uv run`. Generator: `scripts/cheap_llm.sh` → ollama.com `qwen3-coder-next` (only in the final live run; unit tests use seeds or mocked writers). Spec: `docs/superpowers/specs/2026-05-30-era-scalping-100tick-design.md`.

**Causal contract (every seed + every generated program):** programs define `signal(ctx) -> np.ndarray`; `signal[k]` may depend ONLY on bars ≤ k. Per-bar feature ops are always causal; time-axis use must be trailing/expanding (`x[lo:k]`, EWMA), never future rows. The causality probe enforces this. The **feature whitelist** (Task S6/S7 audited) is the separate gate against baked-in column leakage.

**Reused engine signatures (verified on main):**
- `scripts/era/sandbox.py`: `static_check(src) -> (bool,str)` (Task S1 generalizes to `static_check(src, required_fn="residual")`), `run_program`, `_arrays_match(a,b)->bool`, `causality_probe`.
- `scripts/era/select.py`: `bh_fdr(pvalues, q=0.10)->mask`, `holdout_pvalue(net)->float`.
- `scripts/era/llm.py`: `build_prompt(parent_src,parent_score,logs,idea)`, `propose_program(parent_src,parent_score,logs,idea,cache_dir,caller=None)`, `recombine_program(srcA,scoreA,srcB,scoreB,cache_dir,caller=None)`, `extract_program(resp)`, `_ollama_caller(prompt)`, module `_RULES` (Task S1 generalizes these to accept `rules=`).
- `scripts/era/harness.py`: `task_score(df)`, `standardise(resid)`.
- `scripts/era/puct.py`: `Node(payload,score,parent,visits=1,logs="",children=[])`, `puct_search(initial_nodes, expand_fn, budget, c_puct=1.0, seed=0)`.

---

## File Structure

- Modify: `scripts/era/sandbox.py` — `static_check` gains `required_fn="residual"` (back-compat).
- Modify: `scripts/era/llm.py` — `build_prompt`/`propose_program`/`build_recombine_prompt`/`recombine_program` gain `rules=_RULES` (back-compat).
- Create: `scripts/era_scalp/__init__.py`
- Create: `scripts/era_scalp/context.py` — `FeatureContext`.
- Create: `scripts/era_scalp/sandbox.py` — `run_program` (FeatureContext worker), `causality_probe`.
- Create: `scripts/era_scalp/harness.py` — `scale_signal`, `evaluate_signal`, `entry_diagnostics` (+ re-export `task_score`).
- Create: `scripts/era_scalp/score_program.py` — `ScalpSplitData`, `ScalpScorer`.
- Create: `scripts/era_scalp/seeds.py` — `SEED_PROGRAMS`, `BASELINE_SEED_NAMES`, `RESEARCH_IDEAS`.
- Create: `scripts/era_scalp/prompt.py` — `SCALP_RULES`, `FEATURE_NAMES`.
- Create: `scripts/era_scalp/load_splits.py` — `WHITELIST`, `build_splits` (embargoed).
- Create: `scripts/era_scalp/run_era_scalp.py` — driver.
- Create tests under `tests/era_scalp/`: `test_context.py`, `test_sandbox_causality.py`, `test_harness.py`, `test_score_program.py`, `test_seeds.py`, `test_prompt.py`, `test_load_splits.py`, `test_integration.py`.

---

## Task S1: Generalize the shared engine (static_check + llm rules)

**Files:**
- Modify: `scripts/era/sandbox.py`
- Modify: `scripts/era/llm.py`
- Test: `tests/era/test_sandbox.py`, `tests/era/test_llm.py` (append)

- [ ] **Step 1: Failing test — append to `tests/era/test_sandbox.py`**

```python
def test_static_check_custom_required_fn():
    from scripts.era.sandbox import static_check

    ok, _ = static_check("def signal(ctx):\n    return ctx\n", required_fn="signal")
    assert ok
    bad, reason = static_check("def residual(ctx):\n    return ctx\n", required_fn="signal")
    assert not bad and "signal" in reason
```

- [ ] **Step 2: Run — expect FAIL** (`static_check() got an unexpected keyword argument`)

Run: `uv run pytest tests/era/test_sandbox.py::test_static_check_custom_required_fn -q`

- [ ] **Step 3: Edit `scripts/era/sandbox.py`** — change the signature and the function-name check:

Change `def static_check(src: str) -> tuple[bool, str]:` to:
```python
def static_check(src: str, required_fn: str = "residual") -> tuple[bool, str]:
```
Change the loop's residual check from:
```python
        if isinstance(node, ast.FunctionDef) and node.name == "residual":
            has_residual = True
```
to:
```python
        if isinstance(node, ast.FunctionDef) and node.name == required_fn:
            has_residual = True
```
and the failure message from `"must define residual(ctx)"` to `f"must define {required_fn}(ctx)"`.

- [ ] **Step 4: Failing test — append to `tests/era/test_llm.py`**

```python
def test_build_prompt_accepts_custom_rules():
    from scripts.era.llm import build_prompt

    p = build_prompt("x", 0.0, "", "idea", rules="CUSTOM_RULES_SENTINEL")
    assert "CUSTOM_RULES_SENTINEL" in p
```

- [ ] **Step 5: Run — expect FAIL**

Run: `uv run pytest tests/era/test_llm.py::test_build_prompt_accepts_custom_rules -q`

- [ ] **Step 6: Edit `scripts/era/llm.py`** — thread an optional `rules` param (default = module `_RULES`) through the prompt builders and program functions:

`build_prompt`:
```python
def build_prompt(parent_src: str, parent_score: float, logs: str, idea: str, rules: str = _RULES) -> str:
    return (
        "Improve this dispersion residual program to increase its score.\n\n"
        f"{rules}\n"
        f"Research idea to consider: {idea}\n\n"
        f"Parent score: {parent_score}\n"
        f"Parent logs: {logs[:500]}\n\n"
        f"Parent program:\n```python\n{parent_src}\n```\n"
    )
```
`propose_program` — add `rules: str = _RULES` param and pass it to `build_prompt`:
```python
def propose_program(parent_src, parent_score, logs, idea, cache_dir, caller=None, rules=_RULES):
    ...
    prompt = build_prompt(parent_src, parent_score, logs, idea, rules=rules)
```
`build_recombine_prompt` — add `rules: str = _RULES` and use `f"{rules}\n"` in place of `f"{_RULES}\n"`.
`recombine_program` — add `rules: str = _RULES` and pass `rules=rules` to `build_recombine_prompt`.

> Note: the hardcoded lead-in sentences ("Improve this dispersion residual program…") are dispersion-flavoured but harmless for scalping; the scalping `rules` (Task S7) define the actual contract. Leave the lead-in as-is to keep the diff minimal.

- [ ] **Step 7: Run all era tests — expect PASS (no regressions)**

Run: `uv run pytest -q tests/era/`
Expected: all pass.

- [ ] **Step 8: Commit**

```bash
git add scripts/era/sandbox.py scripts/era/llm.py tests/era/test_sandbox.py tests/era/test_llm.py
git commit -m "feat(era): generalize static_check(required_fn) + llm rules param (reuse for scalp)"
```

---

## Task S2: FeatureContext

**Files:**
- Create: `scripts/era_scalp/__init__.py`, `scripts/era_scalp/context.py`
- Test: `tests/era_scalp/__init__.py`, `tests/era_scalp/test_context.py`

- [ ] **Step 1: Create empty `scripts/era_scalp/__init__.py` and `tests/era_scalp/__init__.py`**

```bash
mkdir -p scripts/era_scalp tests/era_scalp
printf '"""ERA 100-tick scalping discovery."""\n' > scripts/era_scalp/__init__.py
: > tests/era_scalp/__init__.py
```

- [ ] **Step 2: Failing test — `tests/era_scalp/test_context.py`**

```python
import numpy as np

from scripts.era_scalp.context import FeatureContext

NAMES = ["spread_z", "vel_z_h1", "bar_return_sign", "hour_utc"]


def _ctx(n=50):
    X = np.arange(n * len(NAMES), dtype=float).reshape(n, len(NAMES))
    hour = (np.arange(n) % 24).astype(float)
    return FeatureContext(X=X, names=list(NAMES), hour=hour)


def test_feature_context_accessors():
    ctx = _ctx()
    assert ctx.n_bars == 50
    assert ctx.names == NAMES
    np.testing.assert_array_equal(ctx.col("vel_z_h1"), ctx.X[:, 1])
    assert ctx.col("hour_utc").shape == (50,)


def test_col_unknown_raises():
    ctx = _ctx()
    try:
        ctx.col("does_not_exist")
        raise AssertionError("expected KeyError")
    except KeyError:
        pass
```

- [ ] **Step 3: Run — expect FAIL** (`ModuleNotFoundError`)

Run: `uv run pytest tests/era_scalp/test_context.py -q`

- [ ] **Step 4: Create `scripts/era_scalp/context.py`**

```python
from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class FeatureContext:
    """Causal single-symbol microstructure features handed to a scalping program.

    X: (n_bars, n_features) time-ordered, CAUSAL features only (no y_fwd, no cost).
       Column order matches `names`.
    """

    X: np.ndarray
    names: list[str]
    hour: np.ndarray | None = None

    @property
    def n_bars(self) -> int:
        return int(self.X.shape[0])

    def col(self, name: str) -> np.ndarray:
        try:
            j = self.names.index(name)
        except ValueError as e:
            raise KeyError(name) from e
        return self.X[:, j]
```

- [ ] **Step 5: Run — expect PASS**

Run: `uv run pytest tests/era_scalp/test_context.py -q`

- [ ] **Step 6: Commit**

```bash
git add scripts/era_scalp/__init__.py scripts/era_scalp/context.py tests/era_scalp/
git commit -m "feat(era-scalp): FeatureContext (causal single-symbol feature matrix)"
```

---

## Task S3: Sandbox — FeatureContext worker + causality probe

**Files:**
- Create: `scripts/era_scalp/sandbox.py`
- Test: `tests/era_scalp/test_sandbox_causality.py`

- [ ] **Step 1: Failing test — `tests/era_scalp/test_sandbox_causality.py`**

```python
import numpy as np

from scripts.era_scalp.context import FeatureContext
from scripts.era_scalp.sandbox import causality_probe, run_program

NAMES = ["spread_z", "vel_z_h1", "vel_pips_h1", "bar_return_sign", "hour_utc"]


def _ctx(n=120, seed=0):
    rng = np.random.default_rng(seed)
    X = rng.standard_normal((n, len(NAMES)))
    return FeatureContext(X=X, names=list(NAMES), hour=(np.arange(n) % 24).astype(float))


CAUSAL = (
    "def signal(ctx):\n"
    "    return ctx.col('vel_z_h1')\n"
)
FORWARD = (
    "def signal(ctx):\n"
    "    x = ctx.col('vel_z_h1').copy()\n"
    "    x[:-1] = (x[:-1] + x[1:]) / 2.0  # reads bar k+1\n"
    "    return x\n"
)


def test_run_program_ok_and_probe_accepts_causal():
    ctx = _ctx()
    sig, err, _ = run_program(CAUSAL, ctx)
    assert err is None and sig.shape == (120,)
    ok, reason = causality_probe(CAUSAL, ctx, sig)
    assert ok, reason


def test_probe_rejects_forward():
    ctx = _ctx()
    sig, err, _ = run_program(FORWARD, ctx)
    assert err is None
    ok, reason = causality_probe(FORWARD, ctx, sig)
    assert not ok and ("future" in reason.lower() or "causal" in reason.lower())


def test_static_check_requires_signal():
    ctx = _ctx()
    _, err, _ = run_program("def residual(ctx):\n    return ctx.col('vel_z_h1')\n", ctx)
    assert err is not None and "signal" in err.lower()
```

- [ ] **Step 2: Run — expect FAIL** (`ModuleNotFoundError`)

Run: `uv run pytest tests/era_scalp/test_sandbox_causality.py -q`

- [ ] **Step 3: Create `scripts/era_scalp/sandbox.py`**

```python
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np

from scripts.era.sandbox import _arrays_match, static_check
from scripts.era_scalp.context import FeatureContext

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
    out = np.asarray(ns["signal"](ctx), dtype=float).reshape(-1)
    if out.shape[0] != ctx.n_bars:
        raise ValueError(f"signal length {out.shape[0]} != n_bars {ctx.n_bars}")
    np.save(sys.argv[2], out)
    print("OK")
except Exception as e:
    print(f"ERR {type(e).__name__}: {e}", file=sys.stderr)
    sys.exit(3)
"""


def run_program(src: str, ctx: FeatureContext, timeout: float = 10.0):
    """Return (signal_array | None, error | None, logs)."""
    ok, reason = static_check(src, required_fn="signal")
    if not ok:
        return None, f"static_check: {reason}", ""
    with tempfile.TemporaryDirectory() as d:
        inp = Path(d) / "in.npz"
        out = Path(d) / "out.npy"
        wrk = Path(d) / "w.py"
        np.savez(
            inp,
            src=src,
            X=ctx.X,
            names=np.array(ctx.names),
            hour=ctx.hour if ctx.hour is not None else np.array([]),
        )
        wrk.write_text(_WORKER)
        try:
            env = dict(os.environ)
            env["PYTHONPATH"] = str(Path.cwd()) + os.pathsep + env.get("PYTHONPATH", "")
            proc = subprocess.run(
                [sys.executable, str(wrk), str(inp), str(out)],
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=str(Path.cwd()),
                env=env,
            )
        except subprocess.TimeoutExpired:
            return None, "timeout", ""
        logs = (proc.stdout + proc.stderr).strip()
        if proc.returncode != 0 or not out.exists():
            return None, logs or f"exit {proc.returncode}", logs
        return np.load(out), None, logs


def causality_probe(src, ctx, clean_signal, n_cuts: int = 2, seed: int = 0):
    """Reject programs whose past signal depends on future bars."""
    n = ctx.n_bars
    if n < 6:
        return True, "too-short-to-probe"
    rng = np.random.default_rng(seed)
    clean = np.asarray(clean_signal, float)
    cuts = [max(1, n * (i + 1) // (n_cuts + 1)) for i in range(n_cuts)]
    for k in cuts:
        X2 = ctx.X.copy()
        X2[k + 1 :, :] = rng.standard_normal(X2[k + 1 :, :].shape) * 10.0
        hour2 = None
        if ctx.hour is not None:
            hour2 = ctx.hour.copy()
            hour2[k + 1 :] = rng.integers(0, 24, size=hour2[k + 1 :].shape).astype(float)
        ctx2 = FeatureContext(X=X2, names=ctx.names, hour=hour2)
        sig2, err, _ = run_program(src, ctx2, timeout=10.0)
        if err is not None:
            return False, f"non-causal: errors under future perturbation at k={k}: {err}"
        if not _arrays_match(clean[: k + 1], np.asarray(sig2, float)[: k + 1]):
            return False, f"non-causal: signal[:{k + 1}] changed when future bars perturbed"
    return True, "ok"
```

- [ ] **Step 4: Run — expect PASS**

Run: `uv run pytest tests/era_scalp/test_sandbox_causality.py -q`

- [ ] **Step 5: Commit**

```bash
git add scripts/era_scalp/sandbox.py tests/era_scalp/test_sandbox_causality.py
git commit -m "feat(era-scalp): sandbox FeatureContext worker + causality probe"
```

---

## Task S4: Directional harness

**Files:**
- Create: `scripts/era_scalp/harness.py`
- Test: `tests/era_scalp/test_harness.py`

- [ ] **Step 1: Failing test — `tests/era_scalp/test_harness.py`**

```python
import numpy as np

from scripts.era_scalp.harness import entry_diagnostics, evaluate_signal, scale_signal, task_score


def test_scale_signal_mad():
    s = scale_signal(np.array([0.0, 1.0, -1.0, 2.0, -2.0]))
    assert np.all(np.isfinite(s))
    # zero-variation -> all nan
    assert np.all(np.isnan(scale_signal(np.full(5, 3.0))))


def test_evaluate_signal_directional():
    # signal positive on first 50 (predict up), y_fwd +2 there -> profitable long
    signal = np.concatenate([np.full(50, 3.0), np.full(50, -3.0)])
    y_fwd = np.concatenate([np.full(50, 2.0), np.full(50, -2.0)])  # down moves on 2nd half
    cost = np.full(100, 0.4)
    tm = np.array(["2025-01"] * 50 + ["2025-02"] * 50)
    df = evaluate_signal(signal, y_fwd, cost, tm, threshold=0.5)
    assert len(df) == 100
    # long when signal>0 and y_fwd>0 => +2-0.4; short when signal<0 and y_fwd<0 => +2-0.4
    assert np.allclose(df["net"].to_numpy(), 1.6)


def test_entry_diagnostics_hit_rate():
    signal = np.array([3.0, 3.0, -3.0, -3.0])
    y_fwd = np.array([2.0, -2.0, -2.0, 2.0])  # 2 correct, 2 wrong
    cost = np.full(4, 0.4)
    tm = np.array(["2025-01"] * 4)
    d = entry_diagnostics(signal, y_fwd, cost, tm, threshold=0.5)
    assert d["n_entries"] == 4
    assert abs(d["hit_rate"] - 0.5) < 1e-9


def test_task_score_reused():
    import pandas as pd

    df = pd.DataFrame({"net": np.full(200, 0.5), "test_month": ["2025-01"] * 200})
    assert task_score(df) > 0
```

- [ ] **Step 2: Run — expect FAIL**

Run: `uv run pytest tests/era_scalp/test_harness.py -q`

- [ ] **Step 3: Create `scripts/era_scalp/harness.py`**

```python
from __future__ import annotations

import numpy as np
import pandas as pd

from scripts.era.harness import task_score  # reuse the dispersion TaskScore unchanged

__all__ = ["scale_signal", "evaluate_signal", "entry_diagnostics", "task_score"]


def scale_signal(signal: np.ndarray) -> np.ndarray:
    """MAD-scale (no mean-centering) so the program's directional sign is preserved."""
    s = np.asarray(signal, dtype=float)
    finite = np.isfinite(s)
    if finite.sum() < 2:
        return np.full_like(s, np.nan)
    med = np.median(s[finite])
    mad = np.median(np.abs(s[finite] - med))
    scale = 1.4826 * mad
    if scale <= 0:
        return np.full_like(s, np.nan)
    return s / scale


def evaluate_signal(signal, y_fwd, cost, test_month, threshold):
    """Directional entry/side/scoring: side = sign(signal); net = side*y_fwd - cost."""
    raw = np.asarray(signal, dtype=float)
    s = scale_signal(raw)
    y_fwd = np.asarray(y_fwd, float)
    cost = np.asarray(cost, float)
    valid = np.isfinite(s) & np.isfinite(y_fwd) & np.isfinite(cost)
    entry = valid & (np.abs(s) >= float(threshold))
    side = np.sign(raw)
    net = side * y_fwd - cost
    return pd.DataFrame(
        {"net": net[entry], "test_month": np.asarray(test_month)[entry]}
    )


def entry_diagnostics(signal, y_fwd, cost, test_month, threshold):
    """Scalping diagnostics for the bars a program would trade."""
    raw = np.asarray(signal, dtype=float)
    s = scale_signal(raw)
    y_fwd = np.asarray(y_fwd, float)
    cost = np.asarray(cost, float)
    valid = np.isfinite(s) & np.isfinite(y_fwd) & np.isfinite(cost)
    entry = valid & (np.abs(s) >= float(threshold))
    n = int(entry.sum())
    if n == 0:
        return {"n_entries": 0, "hit_rate": float("nan"), "mean_net": float("nan"),
                "mean_cost": float("nan"), "month_hit_rate": float("nan")}
    side = np.sign(raw)[entry]
    yf = y_fwd[entry]
    net = side * yf - cost[entry]
    months = np.asarray(test_month)[entry]
    monthly = pd.Series(net).groupby(months).mean()
    return {
        "n_entries": n,
        "hit_rate": float((side * yf > 0).mean()),
        "mean_net": float(net.mean()),
        "mean_cost": float(cost[entry].mean()),
        "month_hit_rate": float((monthly > 0).mean()),
    }
```

- [ ] **Step 4: Run — expect PASS**

Run: `uv run pytest tests/era_scalp/test_harness.py -q`

- [ ] **Step 5: Commit**

```bash
git add scripts/era_scalp/harness.py tests/era_scalp/test_harness.py
git commit -m "feat(era-scalp): directional harness (MAD scale, side=sign, hit-rate diagnostics)"
```

---

## Task S5: ScalpScorer

**Files:**
- Create: `scripts/era_scalp/score_program.py`
- Test: `tests/era_scalp/test_score_program.py`

- [ ] **Step 1: Failing test — `tests/era_scalp/test_score_program.py`**

```python
import numpy as np

from scripts.era_scalp.score_program import ScalpScorer, ScalpSplitData

NAMES = ["spread_z", "vel_z_h1", "vel_pips_h1", "bar_return_sign", "hour_utc"]


def _split(n=200, seed=0):
    rng = np.random.default_rng(seed)
    return ScalpSplitData(
        X=rng.standard_normal((n, len(NAMES))),
        names=list(NAMES),
        hour=(np.arange(n) % 24).astype(float),
        y_fwd=rng.standard_normal(n),
        cost=np.full(n, 0.4),
        test_month=np.array(["2025-01"] * (n // 2) + ["2025-02"] * (n - n // 2)),
    )


def test_scorer_runs_causal_program():
    scorer = ScalpScorer(splits={"validation": _split()}, thresholds=[0.5, 1.0])
    score, logs = scorer.score("def signal(ctx):\n    return ctx.col('vel_z_h1')\n", "validation")
    assert np.isfinite(score)


def test_scorer_rejects_noncausal():
    scorer = ScalpScorer(splits={"validation": _split()}, thresholds=[0.5, 1.0])
    fwd = ("def signal(ctx):\n"
           "    x = ctx.col('vel_z_h1').copy()\n"
           "    x[:-1] = (x[:-1] + x[1:]) / 2.0\n"
           "    return x\n")
    score, logs = scorer.score(fwd, "validation")
    assert score == -1e6 and "causal" in logs.lower()
```

- [ ] **Step 2: Run — expect FAIL**

Run: `uv run pytest tests/era_scalp/test_score_program.py -q`

- [ ] **Step 3: Create `scripts/era_scalp/score_program.py`**

```python
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from scripts.era_scalp.context import FeatureContext
from scripts.era_scalp.harness import evaluate_signal, task_score
from scripts.era_scalp.sandbox import causality_probe, run_program


@dataclass
class ScalpSplitData:
    X: np.ndarray
    names: list[str]
    hour: np.ndarray | None
    y_fwd: np.ndarray
    cost: np.ndarray
    test_month: np.ndarray
    close_ts: np.ndarray | None = None


class ScalpScorer:
    def __init__(self, splits: dict[str, ScalpSplitData], thresholds: list[float],
                 timeout: float = 10.0):
        self.splits = splits
        self.thresholds = thresholds
        self.timeout = timeout

    def score(self, src: str, split: str) -> tuple[float, str]:
        d = self.splits[split]
        ctx = FeatureContext(X=d.X, names=d.names, hour=d.hour)
        sig, err, logs = run_program(src, ctx, timeout=self.timeout)
        if err is not None:
            return -1e6, f"static_check/exec: {err}" if "static_check" in (
                err or ""
            ) else f"exec: {err}\n{logs}"
        ok, reason = causality_probe(src, ctx, sig)
        if not ok:
            return -1e6, f"causality_probe: {reason}"
        best = -1e9
        for thr in self.thresholds:
            df = evaluate_signal(sig, d.y_fwd, d.cost, d.test_month, thr)
            best = max(best, task_score(df))
        return float(best), logs
```

- [ ] **Step 4: Run — expect PASS**

Run: `uv run pytest tests/era_scalp/test_score_program.py -q`

- [ ] **Step 5: Commit**

```bash
git add scripts/era_scalp/score_program.py tests/era_scalp/test_score_program.py
git commit -m "feat(era-scalp): ScalpScorer (sandbox + causality + directional harness)"
```

---

## Task S6: Seeds (modern multi-stream families)

**Files:**
- Create: `scripts/era_scalp/seeds.py`
- Test: `tests/era_scalp/test_seeds.py`

- [ ] **Step 1: Failing test — `tests/era_scalp/test_seeds.py`**

```python
import numpy as np

from scripts.era_scalp.context import FeatureContext
from scripts.era_scalp.sandbox import causality_probe, run_program
from scripts.era_scalp.seeds import BASELINE_SEED_NAMES, RESEARCH_IDEAS, SEED_PROGRAMS

NAMES = ["spread_z", "spread_pips", "tick_volume", "tick_rate_z", "tick_burst_score",
         "bar_return_sign", "vel_pips_h1", "vel_z_h1", "vel_z_h2", "vel_z_h5",
         "vel_z_h10", "hour_utc"]


def _ctx(n=400, seed=1):
    rng = np.random.default_rng(seed)
    X = rng.standard_normal((n, len(NAMES)))
    # make bar_return_sign in {-1,0,1}, tick_volume positive
    X[:, NAMES.index("bar_return_sign")] = np.sign(X[:, NAMES.index("bar_return_sign")])
    X[:, NAMES.index("tick_volume")] = np.abs(X[:, NAMES.index("tick_volume")]) * 50 + 1
    return FeatureContext(X=X, names=list(NAMES), hour=(np.arange(n) % 24).astype(float))


def test_expected_seeds_present():
    for name in ("ofi_flow", "ofi_multihorizon", "ou_sscore", "roll_bounce_fade",
                 "hawkes_cont", "spread_gated_flow"):
        assert name in SEED_PROGRAMS
    for b in BASELINE_SEED_NAMES:
        assert b in SEED_PROGRAMS


def test_all_seeds_run_and_are_causal():
    ctx = _ctx()
    bad = []
    for name, src in SEED_PROGRAMS.items():
        sig, err, _ = run_program(src, ctx)
        if err is not None:
            bad.append(f"{name}: {err}")
            continue
        ok, reason = causality_probe(src, ctx, sig)
        if not ok:
            bad.append(f"{name}: {reason}")
    assert not bad, "; ".join(bad)


def test_research_ideas_cite_modern_streams():
    blob = " ".join(RESEARCH_IDEAS).lower()
    for kw in ["ornstein", "hawkes", "order flow", "multi-horizon", "half-life"]:
        assert kw in blob, f"missing idea keyword: {kw}"
```

- [ ] **Step 2: Run — expect FAIL**

Run: `uv run pytest tests/era_scalp/test_seeds.py -q`

- [ ] **Step 3: Create `scripts/era_scalp/seeds.py`**

```python
"""Modern microstructure scalping seeds (causal, numpy-only). signal(ctx)->array.

Families: order-flow imbalance (Cont-Kukanov-Stoikov; Kolm-Turiel-Westray),
OU mean-reversion (Avellaneda-Lee s-score; Leung-Li; Bertram), Hawkes
self-exciting bursts (Bacry-Mastromatteo-Muzy), with a tradeable-spread regime gate.
"""

SEED_PROGRAMS: dict[str, str] = {
    # --- Order-flow imbalance / price impact ---
    "ofi_flow": (
        "def signal(ctx):\n"
        "    sgn = ctx.col('bar_return_sign'); vol = ctx.col('tick_volume')\n"
        "    flow = np.where(np.isfinite(sgn) & np.isfinite(vol), sgn * vol, 0.0)\n"
        "    n = flow.shape[0]; a = 0.1; out = np.empty(n); acc = 0.0\n"
        "    for i in range(n):\n"
        "        acc = (1 - a) * acc + a * flow[i]\n"
        "        out[i] = acc\n"
        "    return out  # OFI continuation: positive flow -> expect up\n"
    ),
    "ofi_multihorizon": (
        "def signal(ctx):\n"
        "    zs = [ctx.col('vel_z_h1'), ctx.col('vel_z_h2'), ctx.col('vel_z_h5'),\n"
        "          ctx.col('vel_z_h10')]\n"
        "    w = [0.4, 0.3, 0.2, 0.1]; out = np.zeros(ctx.n_bars)\n"
        "    for wi, z in zip(w, zs):\n"
        "        out = out + wi * np.where(np.isfinite(z), z, 0.0)\n"
        "    return out  # multi-horizon momentum (Kolm-Turiel-Westray)\n"
    ),
    # --- OU mean-reversion (Avellaneda-Lee s-score over a trailing equilibrium) ---
    "ou_sscore": (
        "def signal(ctx):\n"
        "    ret = ctx.col('vel_pips_h1'); n = ret.shape[0]; W = 120\n"
        "    x = np.cumsum(np.where(np.isfinite(ret), ret, 0.0))  # detrended price proxy\n"
        "    k = np.arange(n); lo = np.maximum(0, k - W); m = (k - lo).astype(float)\n"
        "    ms = np.where(m > 0, m, 1.0)\n"
        "    cx = np.concatenate(([0.0], np.cumsum(x)))\n"
        "    cxx = np.concatenate(([0.0], np.cumsum(x * x)))\n"
        "    sx = cx[k] - cx[lo]; sxx = cxx[k] - cxx[lo]\n"
        "    mu = sx / ms; var = sxx / ms - mu * mu\n"
        "    sd = np.sqrt(np.clip(var, 1e-12, None))\n"
        "    s = (x - mu) / sd\n"
        "    out = -s  # fade deviation from trailing OU equilibrium\n"
        "    out[m < 20] = np.nan\n"
        "    return out\n"
    ),
    "roll_bounce_fade": (
        "def signal(ctx):\n"
        "    v = ctx.col('vel_pips_h1'); sp = ctx.col('spread_pips')\n"
        "    small = np.isfinite(v) & np.isfinite(sp) & (np.abs(v) < 1.0 * sp)\n"
        "    return np.where(small, -np.sign(v), np.nan)  # fade sub-spread bounce (Roll)\n"
    ),
    # --- Hawkes self-exciting burst continuation ---
    "hawkes_cont": (
        "def signal(ctx):\n"
        "    inten = ctx.col('tick_burst_score'); move = ctx.col('vel_pips_h1')\n"
        "    n = inten.shape[0]; a = 0.2; out = np.full(n, np.nan); acc = 0.0\n"
        "    for i in range(n):\n"
        "        xi = inten[i] if np.isfinite(inten[i]) else 0.0\n"
        "        acc = (1 - a) * acc + a * max(xi, 0.0)\n"
        "        if acc > 0.5 and np.isfinite(move[i]):\n"
        "            out[i] = np.sign(move[i]) * acc  # continuation when bursts cluster\n"
        "    return out\n"
    ),
    # --- regime gate ---
    "spread_gated_flow": (
        "def signal(ctx):\n"
        "    spz = ctx.col('spread_z'); base = ctx.col('vel_z_h1')\n"
        "    base = np.where(np.isfinite(base), base, np.nan)\n"
        "    return np.where(np.isfinite(spz) & (spz <= 0.0), base, np.nan)\n"
    ),
}

# Canonical baselines the rediscovery tracer must regenerate when removed.
BASELINE_SEED_NAMES = ("ofi_flow", "ou_sscore", "hawkes_cont", "ofi_multihorizon")

RESEARCH_IDEAS: list[str] = [
    "Order-flow imbalance (Cont-Kukanov-Stoikov): signed flow (bar_return_sign x "
    "tick_volume, or hl_pos_delta_tick) predicts the next-bar move in the SAME "
    "direction (price impact); smooth it causally and trade side=sign(flow).",
    "Multi-horizon OFI alpha (Kolm-Turiel-Westray): stack backward returns/imbalance "
    "at several horizons (vel_z_h1/h2/h5/h10) with weights and combine for direction.",
    "Ornstein-Uhlenbeck mean-reversion (Avellaneda-Lee s-score): model the short-window "
    "price deviation as OU, estimate the reversion speed / half-life on a TRAILING "
    "window, emit the s-score and fade it when it breaches a band (Leung-Li bands).",
    "Bid-ask bounce reversion (Roll): a move smaller than the spread is mostly bounce; "
    "fade it.",
    "Hawkes self-exciting bursts (Bacry-Mastromatteo-Muzy): tick arrivals cluster; use a "
    "causal EWMA of tick intensity (tick_rate_z/tick_burst) and trade continuation only "
    "when intensity is elevated.",
    "Regime gate: only trade when spread_z is low (tradeable) and/or a vol regime is "
    "favorable, to keep net-of-cost edge positive.",
]
```

- [ ] **Step 4: Run — expect PASS**

Run: `uv run pytest tests/era_scalp/test_seeds.py -q`

- [ ] **Step 5: Commit**

```bash
git add scripts/era_scalp/seeds.py tests/era_scalp/test_seeds.py
git commit -m "feat(era-scalp): modern seeds (OFI, OU s-score, Hawkes) + research ideas"
```

---

## Task S7: Scalping prompt

**Files:**
- Create: `scripts/era_scalp/prompt.py`
- Test: `tests/era_scalp/test_prompt.py`

- [ ] **Step 1: Failing test — `tests/era_scalp/test_prompt.py`**

```python
def test_scalp_rules_cover_contract_and_causality():
    from scripts.era.llm import build_prompt
    from scripts.era_scalp.prompt import FEATURE_NAMES, SCALP_RULES

    p = build_prompt("def signal(ctx):\n    return ctx.col('vel_z_h1')\n", 0.0, "", "idea",
                     rules=SCALP_RULES).lower()
    assert "signal(ctx)" in p
    assert "future" in p and ("trailing" in p or "expanding" in p)
    assert "ctx.col" in p
    # advertises real feature names
    assert "vel_z_h1" in p and "spread_z" in p
    assert "vel_z_h1" in FEATURE_NAMES and "y_fwd" not in " ".join(FEATURE_NAMES)
```

- [ ] **Step 2: Run — expect FAIL**

Run: `uv run pytest tests/era_scalp/test_prompt.py -q`

- [ ] **Step 3: Create `scripts/era_scalp/prompt.py`**

```python
from __future__ import annotations

FEATURE_NAMES: list[str] = [
    "spread_pips", "spread_z", "tick_volume", "tick_rate_hz", "tick_rate_z",
    "tick_burst", "tick_burst_score", "high_pos_tick", "low_pos_tick",
    "hl_pos_delta_tick", "bar_return_sign", "vel_pips_h1", "vel_pips_h2",
    "vel_pips_h5", "vel_pips_h10", "vel_z_h1", "vel_z_h2", "vel_z_h5",
    "vel_z_h10", "accel_pips", "hour_utc",
]

SCALP_RULES = (
    "You write a Python function `signal(ctx) -> np.ndarray` for 100-tick FX scalping.\n"
    "It returns a per-bar DIRECTIONAL score: sign = predicted direction of the next move,\n"
    "magnitude = conviction. The harness scales it (MAD), trades side=sign(signal) when\n"
    "|scaled| >= threshold, and scores net = side*y_fwd - cost. Return np.nan for bars you\n"
    "DO NOT want to trade (self-gating).\n"
    "ctx.col(name) returns a causal per-bar feature column; ctx.X is (n_bars x n_feat);\n"
    "ctx.n_bars; ctx.hour is the per-bar UTC hour. `np` is available. NO imports.\n"
    "Available causal features (all backward / as-of, NEVER forward):\n"
    f"  {', '.join(FEATURE_NAMES)}\n"
    "You CANNOT access y_fwd / cost / future bars. You MAY use the full time axis causally:\n"
    "trailing/expanding windows, EWMA, rolling stats over bars <= k ONLY (use x[k-W:k], not\n"
    "x[k:], no centered windows, no full-sample mean/std). A causality probe perturbs future\n"
    "rows and REJECTS any program whose past output changes.\n"
    "Mechanisms to consider: order-flow imbalance (signed flow -> continuation), Ornstein-\n"
    "Uhlenbeck s-score reversion (fade trailing-equilibrium deviation), Hawkes bursts\n"
    "(EWMA tick intensity gating continuation), multi-horizon momentum, spread/vol regime\n"
    "gates. Output ONLY one ```python code block.\n"
)
```

- [ ] **Step 4: Run — expect PASS**

Run: `uv run pytest tests/era_scalp/test_prompt.py -q`

- [ ] **Step 5: Commit**

```bash
git add scripts/era_scalp/prompt.py tests/era_scalp/test_prompt.py
git commit -m "feat(era-scalp): scalping generator prompt (signal contract + feature menu)"
```

---

## Task S8: Embargoed splits loader

**Files:**
- Create: `scripts/era_scalp/load_splits.py`
- Test: `tests/era_scalp/test_load_splits.py`

- [ ] **Step 1: Failing test — `tests/era_scalp/test_load_splits.py`**

```python
import numpy as np
import pandas as pd

from scripts.era_scalp.load_splits import WHITELIST, build_splits


def _write_fake_parquet(path, n=3000):
    rng = np.random.default_rng(0)
    ts = pd.date_range("2023-06-01", periods=n, freq="min", tz="UTC")
    # span 2023 (train), 2024 (validation), 2025 (holdout)
    ts = pd.to_datetime(np.r_[
        pd.date_range("2023-06-01", periods=n // 3, freq="5min", tz="UTC"),
        pd.date_range("2024-06-01", periods=n // 3, freq="5min", tz="UTC"),
        pd.date_range("2025-06-01", periods=n - 2 * (n // 3), freq="5min", tz="UTC"),
    ])
    cols = {c: rng.standard_normal(n) for c in WHITELIST}
    cols["close_ts"] = ts
    cols["cost_est_pips"] = np.full(n, 0.4)
    for h in (1, 2, 3):
        cols[f"y_fwd_pips_h{h}"] = rng.standard_normal(n)
    # non-whitelist leakage columns that must NOT appear in names
    cols["close_bid"] = rng.standard_normal(n)
    pd.DataFrame(cols).to_parquet(path)


def test_build_splits_embargo_and_no_leakage(tmp_path):
    p = tmp_path / "EURUSD_100tick_velocity.parquet"
    _write_fake_parquet(p)
    splits = build_splits("EURUSD", p, horizon=3,
                          train=("2023",), validation=("2024",), holdout=("2025",))
    for name in ("train", "validation", "holdout"):
        d = splits[name]
        assert d.X.shape[0] == len(d.y_fwd) == len(d.test_month)
        assert d.X.shape[1] == len(WHITELIST)
        assert "close_bid" not in d.names and "y_fwd_pips_h3" not in d.names
        assert d.X.shape[0] > 0
    # embargo: train and validation tails trimmed by `horizon` bars
    full_train = (pd.read_parquet(p)["close_ts"].dt.year == 2023).sum()
    assert splits["train"].X.shape[0] == full_train - 3
```

- [ ] **Step 2: Run — expect FAIL**

Run: `uv run pytest tests/era_scalp/test_load_splits.py -q`

- [ ] **Step 3: Create `scripts/era_scalp/load_splits.py`**

```python
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from scripts.era_scalp.score_program import ScalpSplitData

# Causal, stationary feature whitelist (audited backward/.shift(1) in
# scripts/build_tick_velocity_dataset.py). Excludes y_fwd_*, raw OHLC,
# cost_est_pips, close_ts, bar_ticks.
WHITELIST: list[str] = [
    "spread_pips", "spread_z", "tick_volume", "tick_rate_hz", "tick_rate_z",
    "tick_burst", "tick_burst_score", "high_pos_tick", "low_pos_tick",
    "hl_pos_delta_tick", "bar_return_sign", "vel_pips_h1", "vel_pips_h2",
    "vel_pips_h5", "vel_pips_h10", "vel_z_h1", "vel_z_h2", "vel_z_h5",
    "vel_z_h10", "accel_pips", "hour_utc",
]


def build_splits(
    symbol: str,
    parquet_path: Path,
    horizon: int = 1,
    train=("2018", "2019", "2020", "2021", "2022", "2023"),
    validation=("2024",),
    holdout=("2025", "2026"),
) -> dict[str, ScalpSplitData]:
    df = pd.read_parquet(parquet_path)
    df["close_ts"] = pd.to_datetime(df["close_ts"], utc=True, errors="coerce")
    df = df[df["close_ts"].notna()].sort_values("close_ts").reset_index(drop=True)
    df["year"] = df["close_ts"].dt.strftime("%Y")
    df["test_month"] = df["close_ts"].dt.strftime("%Y-%m")
    ycol = f"y_fwd_pips_h{horizon}"

    def _split(years, embargo_tail: bool) -> ScalpSplitData:
        d = df[df["year"].isin(years)].reset_index(drop=True)
        # Embargo (Lopez de Prado): the last `horizon` bars' y_fwd windows reach into
        # the next split, so drop them to keep label windows from crossing the boundary.
        if embargo_tail and len(d) > horizon:
            d = d.iloc[: len(d) - horizon].reset_index(drop=True)
        return ScalpSplitData(
            X=d[WHITELIST].to_numpy(float),
            names=list(WHITELIST),
            hour=d["hour_utc"].to_numpy(float),
            y_fwd=d[ycol].to_numpy(float),
            cost=d["cost_est_pips"].to_numpy(float),
            test_month=d["test_month"].to_numpy(),
            close_ts=d["close_ts"].to_numpy(),
        )

    return {
        "train": _split(train, embargo_tail=True),
        "validation": _split(validation, embargo_tail=True),
        "holdout": _split(holdout, embargo_tail=False),  # last split: y_fwd tail is NaN anyway
    }
```

- [ ] **Step 4: Run — expect PASS**

Run: `uv run pytest tests/era_scalp/test_load_splits.py -q`

- [ ] **Step 5: Commit**

```bash
git add scripts/era_scalp/load_splits.py tests/era_scalp/test_load_splits.py
git commit -m "feat(era-scalp): embargoed single-symbol splits + causal whitelist"
```

---

## Task S9: Driver

**Files:**
- Create: `scripts/era_scalp/run_era_scalp.py`
- Test: `tests/era_scalp/test_integration.py`

- [ ] **Step 1: Failing test — `tests/era_scalp/test_integration.py`**

```python
import numpy as np
import pandas as pd

from scripts.era_scalp.run_era_scalp import finalize_selection, run_search, select_seed_programs
from scripts.era_scalp.score_program import ScalpSplitData

NAMES_FROM_WHITELIST = None


def _split(n=300, seed=0):
    from scripts.era_scalp.load_splits import WHITELIST

    rng = np.random.default_rng(seed)
    return ScalpSplitData(
        X=rng.standard_normal((n, len(WHITELIST))),
        names=list(WHITELIST),
        hour=(np.arange(n) % 24).astype(float),
        y_fwd=rng.standard_normal(n),
        cost=np.full(n, 0.4),
        test_month=np.array(["2024-01"] * (n // 2) + ["2024-02"] * (n - n // 2)),
    )


def test_select_seed_programs_ablation():
    full = select_seed_programs(no_baseline=False)
    ablated = select_seed_programs(no_baseline=True)
    for b in ("ofi_flow", "ou_sscore", "hawkes_cont", "ofi_multihorizon"):
        assert b in full and b not in ablated
    assert "roll_bounce_fade" in ablated


def test_finalize_applies_bh_fdr():
    holdout_nets = {
        "winner": pd.DataFrame({"net": np.random.default_rng(0).normal(0.5, 1.0, 400)}),
        "null": pd.DataFrame({"net": np.random.default_rng(1).normal(0.0, 1.0, 400)}),
    }
    survivors = finalize_selection(holdout_nets, q=0.10)
    assert "winner" in survivors and "null" not in survivors


def test_run_search_with_mocked_writer():
    splits = {"validation": _split(), "holdout": _split(seed=2)}

    def fake_writer(parent_src, parent_score, logs, idea, cache_dir, rules=None, caller=None):
        return "def signal(ctx):\n    return ctx.col('vel_z_h2')\n"

    nodes = run_search(splits, thresholds=[0.5, 1.0], budget=3,
                       writer=fake_writer, p_recombine=0.0)
    assert len(nodes) >= 3
    assert all(np.isfinite(n.score) for n in nodes)
```

- [ ] **Step 2: Run — expect FAIL**

Run: `uv run pytest tests/era_scalp/test_integration.py -q`

- [ ] **Step 3: Create `scripts/era_scalp/run_era_scalp.py`**

```python
from __future__ import annotations

import argparse
import random
from pathlib import Path

import numpy as np

from scripts.era.llm import propose_program, recombine_program
from scripts.era.puct import Node, puct_search
from scripts.era.select import bh_fdr, holdout_pvalue
from scripts.era_scalp.context import FeatureContext
from scripts.era_scalp.harness import entry_diagnostics, evaluate_signal
from scripts.era_scalp.prompt import SCALP_RULES
from scripts.era_scalp.sandbox import run_program
from scripts.era_scalp.score_program import ScalpScorer, ScalpSplitData
from scripts.era_scalp.seeds import BASELINE_SEED_NAMES, RESEARCH_IDEAS, SEED_PROGRAMS

THRESHOLDS = [0.5, 1.0, 1.5, 2.0]


def select_seed_programs(no_baseline: bool = False) -> dict:
    if not no_baseline:
        return dict(SEED_PROGRAMS)
    return {k: v for k, v in SEED_PROGRAMS.items() if k not in BASELINE_SEED_NAMES}


def finalize_selection(holdout_nets: dict, q: float = 0.10) -> list[str]:
    names = list(holdout_nets)
    pvals = np.array([holdout_pvalue(holdout_nets[n]["net"].to_numpy(float)) for n in names])
    keep = bh_fdr(pvals, q=q)
    return [n for n, k in zip(names, keep, strict=True) if k]


def run_search(splits, thresholds, budget, writer=propose_program, ideas=None,
               seed: int = 0, cache_dir: str = "/tmp/era_scalp_cache",
               p_recombine: float = 0.3, seed_programs=None):
    ideas = ideas or RESEARCH_IDEAS
    seed_programs = seed_programs or SEED_PROGRAMS
    scorer = ScalpScorer(splits=splits, thresholds=thresholds)
    rng = random.Random(seed)
    split_for_rank = "validation" if "validation" in splits else "train"
    forest = []
    for _name, src in seed_programs.items():
        s, lg = scorer.score(src, split_for_rank)
        forest.append(Node(payload=src, score=s, parent=None, logs=lg))
    all_nodes = list(forest)

    def expand(parent: Node) -> Node:
        if rng.random() < p_recombine and len(all_nodes) >= 2:
            distinct = {}
            for nd in all_nodes:
                key = id(nd.payload)
                if key not in distinct or nd.score > distinct[key].score:
                    distinct[key] = nd
            cands = sorted(distinct.values(), key=lambda n: n.score, reverse=True)
            if len(cands) >= 2:
                child_src = recombine_program(cands[0].payload, cands[0].score,
                                              cands[1].payload, cands[1].score,
                                              cache_dir=cache_dir, rules=SCALP_RULES)
            else:
                idea = rng.choice(ideas)
                child_src = writer(parent.payload, parent.score, parent.logs, idea,
                                   cache_dir=cache_dir, rules=SCALP_RULES)
        else:
            idea = rng.choice(ideas)
            child_src = writer(parent.payload, parent.score, parent.logs, idea,
                               cache_dir=cache_dir, rules=SCALP_RULES)
        s, lg = scorer.score(child_src, split_for_rank)
        child = Node(payload=child_src, score=s, parent=parent, logs=lg)
        all_nodes.append(child)
        return child

    return puct_search(forest, expand, budget=budget, c_puct=1.0, seed=seed)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbol", default="EURUSD")
    ap.add_argument("--parquet", required=True, help="path to <SYMBOL>_100tick_velocity.parquet")
    ap.add_argument("--horizon", type=int, default=1)
    ap.add_argument("--budget", type=int, default=60)
    ap.add_argument("--no-baseline-seeds", action="store_true")
    ap.add_argument("--holdout-top", type=int, default=5)
    ap.add_argument("--out", default="/tmp/era_scalp/report.md")
    args = ap.parse_args()
    from scripts.era_scalp.load_splits import build_splits

    splits = build_splits(args.symbol, Path(args.parquet), horizon=args.horizon)
    seed_programs = select_seed_programs(no_baseline=args.no_baseline_seeds)
    nodes = run_search(splits, thresholds=THRESHOLDS, budget=args.budget,
                       seed_programs=seed_programs)
    nodes.sort(key=lambda n: n.score, reverse=True)

    hold = splits["holdout"]
    top = nodes[: args.holdout_top]
    holdout_nets, diag_rows = {}, {}
    ndays = max(1, len(np.unique(np.asarray(hold.test_month))))
    for i, nd in enumerate(top):
        ctx = FeatureContext(X=hold.X, names=hold.names, hour=hold.hour)
        sig, err, _ = run_program(nd.payload, ctx)
        if err is not None:
            continue
        best = None
        for thr in THRESHOLDS:
            df = evaluate_signal(sig, hold.y_fwd, hold.cost, hold.test_month, thr)
            if len(df) >= 5 and (best is None or len(df) < len(best[1])):
                best = (thr, df)
        if best is None:
            continue
        key = f"node{i}"
        holdout_nets[key] = best[1]
        diag_rows[key] = entry_diagnostics(sig, hold.y_fwd, hold.cost, hold.test_month, best[0])
    survivors = finalize_selection(holdout_nets, q=0.10) if holdout_nets else []

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    with open(args.out, "w") as f:
        f.write(f"# ERA-scalp run — {args.symbol} 100tick (h{args.horizon})\n\n")
        f.write(f"nodes: {len(nodes)} | no_baseline_seeds={args.no_baseline_seeds}\n\n")
        f.write(f"## BH-FDR holdout survivors (q=0.10): {survivors or 'none'}\n\n")
        f.write("## Top by validation score (with holdout diagnostics)\n\n")
        for i, nd in enumerate(top):
            d = diag_rows.get(f"node{i}", {})
            f.write(f"- val_score={nd.score:.4f} holdout={d}\n```python\n{nd.payload}\n```\n")
    print(f"wrote {args.out}; survivors={survivors}")


if __name__ == "__main__":
    main()
```

> Note: `propose_program`/`recombine_program` accept `rules=` after Task S1; the mocked
> `fake_writer` in the test mirrors that signature (`rules=None`).

- [ ] **Step 4: Run — expect PASS**

Run: `uv run pytest tests/era_scalp/test_integration.py -q`

- [ ] **Step 5: Commit**

```bash
git add scripts/era_scalp/run_era_scalp.py tests/era_scalp/test_integration.py
git commit -m "feat(era-scalp): driver — search + embargoed holdout BH-FDR + diagnostics"
```

---

## Task S10: Quality gate + PR

- [ ] **Step 1: Full suite + quality**

Run: `uv run pytest -q tests/era_scalp/ tests/era/ && make quality`
Expected: all pass; `make quality` exit 0 (fix any ruff line-length/import issues on the new files only — do not touch unrelated pre-existing INFO findings).

- [ ] **Step 2: Push + open PR** (branch `era-scalp-100tick`, base `main`)

```bash
git push -u origin era-scalp-100tick
gh pr create --base main --title "feat(era-scalp): ERA 100-tick scalping discovery loop" --body "$(cat <<'EOF'
Applies the ERA engine to single-symbol directional scalping on 100-tick bars.
Reuses scripts/era/ (puct/select/llm/static_check/task_score); new scripts/era_scalp/
adds FeatureContext, a directional harness (side=sign, MAD scale, hit-rate), modern
multi-stream seeds (OFI / OU s-score / Hawkes), a scalping prompt, embargoed splits
(Lopez de Prado purge for overlapping labels), and the driver with holdout BH-FDR.

Causal discipline: causality probe + audited feature whitelist (the gate against
baked-in column leakage). Spec: docs/superpowers/specs/2026-05-30-era-scalping-100tick-design.md.

Tests: tests/era_scalp/ (context, sandbox/causality, harness, scorer, seeds, prompt,
splits, integration) + era engine regressions. make quality green.

Evidence (live qwen run on EURUSD 100-tick) to follow as a maintainer step.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

---

## Task S11: Opus live evidence run (maintainer step — NOT Haiku)

**Requires:** `OLLAMA_API_KEY` in `.env`, `data/analysis/tick_velocity/EURUSD_100tick_velocity.parquet`.

- [ ] **Step 1: Coverage run**

```bash
ERA_GEN_TEMP=0.8 uv run python -m scripts.era_scalp.run_era_scalp \
  --symbol EURUSD --parquet data/analysis/tick_velocity/EURUSD_100tick_velocity.parquet \
  --horizon 1 --budget 80 --out /tmp/era_scalp/coverage.md
```

- [ ] **Step 2: Rediscovery tracer**

```bash
ERA_GEN_TEMP=0.8 uv run python -m scripts.era_scalp.run_era_scalp \
  --symbol EURUSD --parquet data/analysis/tick_velocity/EURUSD_100tick_velocity.parquet \
  --horizon 1 --budget 40 --no-baseline-seeds --out /tmp/era_scalp/rediscovery.md
```

- [ ] **Step 3: Write evidence doc** `docs/analysis/era_scalp_100tick_evidence_<DATE>.md` — top programs, directional hit-rate, fills, BH-FDR holdout survivors, and an honest verdict (deployable only after the real governance ladder). Commit.

---

## Self-Review

**Spec coverage:** Approach A reuse → S1 + imports across S3/S5/S9. FeatureContext → S2. Sandbox+probe → S3. Directional harness (MAD scale, side=sign, hit-rate) → S4. Scorer → S5. Modern seeds (OU/Hawkes/OFI) + research ideas → S6. Prompt + feature menu → S7. Embargoed splits + whitelist + leakage gate → S8. Driver + BH-FDR + ablation → S9. Testing → each task's tests + S10. Evidence → S11. Literature foundations are documented in the spec; seeds/ideas cite them. All covered.

**Placeholder scan:** no TBD/TODO; every code step is complete; commands have expected output.

**Type/name consistency:** `FeatureContext(X, names, hour)` consistent S2/S3/S5/S9; `signal(ctx)` contract consistent S3/S6/S7; `ScalpSplitData(X,names,hour,y_fwd,cost,test_month,close_ts=None)` consistent S5/S8/S9; `ScalpScorer(splits,thresholds,timeout=10)` S5/S9; `evaluate_signal(signal,y_fwd,cost,test_month,threshold)` S4/S9; `entry_diagnostics(signal,y_fwd,cost,test_month,threshold)` S4/S9; `scale_signal`, `task_score` (reused) S4; `build_splits(symbol,parquet_path,horizon,train,validation,holdout)` + `WHITELIST` S8 used in S9 test; `static_check(src, required_fn)` S1 used in S3; `propose_program(...rules=)`/`recombine_program(...rules=)` S1 used in S9; `select_seed_programs`/`finalize_selection`/`BASELINE_SEED_NAMES` S6/S9. Consistent.
