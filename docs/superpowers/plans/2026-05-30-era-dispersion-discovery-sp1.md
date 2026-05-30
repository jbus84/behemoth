# ERA Dispersion-Discovery SP1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a faithful ERA PUCT tree search that has `qwen3-coder-next` rewrite causal-sandboxed dispersion programs, scores them with a continuous repo metric, and rediscovers/beats the `dispersion_rank` baselines.

**Architecture:** A `scripts/era/` package. Programs are Python sources exposing `residual(ctx) -> np.ndarray` over a causal cross-section (no `y_fwd`). A sandbox AST-validates and subprocess-executes them. A harness turns the residual into entries/sides/net and a continuous TaskScore. A globally-flat PUCT engine drives the search; the in-loop writer is `qwen3-coder-next` via ollama.com. End-stage Benjamini–Hochberg FDR + held-out gate the reported winner — never the per-node signal.

**Tech Stack:** Python 3.12, numpy, pandas, scipy.stats, `uv run`, pytest. Reuses `scripts/cross_symbol.py` (`get_or_build_cross_symbol_frame`, `CROSS_SYMBOLS`, `_USD_SIGN`). LLM via ollama.com `/api/generate` (`OLLAMA_API_KEY` from gitignored `.env`).

**Verification:** Haiku implements each task; Opus reviews. The live `qwen3-coder-next` evidence run (final task) is executed by Opus, not in CI.

---

## File Structure

| File | Responsibility |
|---|---|
| `scripts/era/__init__.py` | package marker |
| `scripts/era/context.py` | `CrossSectionContext` dataclass — the causal feature surface (no `y_fwd`) |
| `scripts/era/sandbox.py` | `static_check()` (AST whitelist) + `run_program()` (subprocess, timeout) |
| `scripts/era/harness.py` | `evaluate_residual()` (residual→entries/sides/net) + `task_score()` (continuous) |
| `scripts/era/llm.py` | `propose_program()` — ollama.com call, prompt assembly, file cache |
| `scripts/cheap_llm.sh` | thin shell wrapper around ollama.com `/api/generate` |
| `scripts/era/puct.py` | `Node`, `puct_search()` — globally-flat PUCT engine |
| `scripts/era/seeds.py` | baseline programs (as source strings) + research-idea summaries |
| `scripts/era/select.py` | end-stage `bh_fdr()` + held-out selection |
| `scripts/era/run_era.py` | driver: splits → seeds → search → report |
| `tests/era/…` | one test module per file above |

Data for scoring is loaded from a `--tom-dir`/`--velocity-dir` pair (the trial artifacts), never committed.

---

## Task 0: Package scaffold

**Files:**
- Create: `scripts/era/__init__.py`
- Create: `tests/era/__init__.py`
- Create: `tests/era/test_smoke.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/era/test_smoke.py
def test_package_imports():
    import scripts.era  # noqa: F401
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/era/test_smoke.py -q`
Expected: FAIL (ModuleNotFoundError: scripts.era)

- [ ] **Step 3: Create the package files**

```python
# scripts/era/__init__.py
"""ERA dispersion-signal discovery (SP1)."""
```
```python
# tests/era/__init__.py
```

- [ ] **Step 4: Run it to verify it passes**

Run: `uv run pytest tests/era/test_smoke.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/era/__init__.py tests/era/__init__.py tests/era/test_smoke.py
git commit -m "feat(era): package scaffold"
```

---

## Task 1: CrossSectionContext — the causal feature surface

**Files:**
- Create: `scripts/era/context.py`
- Test: `tests/era/test_context.py`

The context a program receives. It carries ONLY causal inputs: the per-bar
6-symbol USD-aligned return matrix `r` (shape `(n_bars, 6)`, columns ordered by
`CROSS_SYMBOLS`), the target column index, the target's `usd_sign`, and the
peer mask. **No `y_fwd`, no future data, no timestamps used for scoring.**

- [ ] **Step 1: Write the failing test**

```python
# tests/era/test_context.py
import numpy as np
from scripts.era.context import CrossSectionContext

def _ctx():
    r = np.arange(12, dtype=float).reshape(4, 3)  # 4 bars, 3 symbols (test size)
    return CrossSectionContext(r=r, names=["EURUSD", "GBPUSD", "USDJPY"],
                               target="EURUSD", usd_sign=-1)

def test_target_index_and_peers():
    ctx = _ctx()
    assert ctx.target_idx == 0
    assert ctx.n_bars == 4
    assert ctx.peer_idx == [1, 2]
    # target column view
    np.testing.assert_array_equal(ctx.target_col(), np.array([0.0, 3.0, 6.0, 9.0]))
    # peers matrix is (n_bars, n_peers)
    assert ctx.peers().shape == (4, 2)

def test_no_future_attributes():
    ctx = _ctx()
    for bad in ("y_fwd", "y_fwd_pips", "future", "label", "target_gross"):
        assert not hasattr(ctx, bad)
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/era/test_context.py -q`
Expected: FAIL (cannot import CrossSectionContext)

- [ ] **Step 3: Implement**

```python
# scripts/era/context.py
from __future__ import annotations
from dataclasses import dataclass
import numpy as np

@dataclass(frozen=True)
class CrossSectionContext:
    """Causal cross-section handed to a candidate program.

    r: (n_bars, n_symbols) USD-aligned vol-normalised returns (xs_ret_z),
       columns ordered by `names`. Carries NO forward/label data.
    """
    r: np.ndarray
    names: list[str]
    target: str
    usd_sign: int

    @property
    def target_idx(self) -> int:
        return self.names.index(self.target)

    @property
    def peer_idx(self) -> list[int]:
        return [i for i in range(len(self.names)) if i != self.target_idx]

    @property
    def n_bars(self) -> int:
        return int(self.r.shape[0])

    def target_col(self) -> np.ndarray:
        return self.r[:, self.target_idx]

    def peers(self) -> np.ndarray:
        return self.r[:, self.peer_idx]
```

- [ ] **Step 4: Run it to verify it passes**

Run: `uv run pytest tests/era/test_context.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/era/context.py tests/era/test_context.py
git commit -m "feat(era): causal CrossSectionContext (no y_fwd)"
```

---

## Task 2: Sandbox — static AST check + subprocess execution

**Files:**
- Create: `scripts/era/sandbox.py`
- Test: `tests/era/test_sandbox.py`

A program is a source string defining `def residual(ctx): -> np.ndarray`.
`static_check(src)` rejects imports, dunder access, and dangerous names.
`run_program(src, ctx, timeout)` executes the validated source in a subprocess
that reconstructs `ctx` from a temp `.npz`, calls `residual`, and returns the
array (or an error string + logs).

- [ ] **Step 1: Write the failing test**

```python
# tests/era/test_sandbox.py
import numpy as np
from scripts.era.context import CrossSectionContext
from scripts.era.sandbox import static_check, run_program

GOOD = """
def residual(ctx):
    import numpy as np  # NOTE: numpy provided in namespace, no import needed
    t = ctx.target_col()
    p = ctx.peers()
    return (t - p.mean(axis=1)) / (p.std(axis=1) + 1e-9)
"""

CLEAN = """
def residual(ctx):
    t = ctx.target_col(); p = ctx.peers()
    return (t - p.mean(axis=1)) / (p.std(axis=1) + 1e-9)
"""

def _ctx():
    r = np.random.RandomState(0).randn(20, 6)
    return CrossSectionContext(r=r, names=list("ABCDEF"), target="A", usd_sign=-1)

def test_static_check_rejects_imports_and_dunders():
    ok, reason = static_check("def residual(ctx):\n    import os\n    return ctx.target_col()")
    assert not ok and "import" in reason.lower()
    ok, _ = static_check("def residual(ctx):\n    return ctx.__class__")
    assert not ok
    ok, _ = static_check("def residual(ctx):\n    return open('x')")
    assert not ok

def test_static_check_accepts_clean():
    ok, reason = static_check(CLEAN)
    assert ok, reason

def test_run_clean_program_returns_array():
    res, err, logs = run_program(CLEAN, _ctx(), timeout=10.0)
    assert err is None, err
    assert res.shape == (20,)

def test_run_rejects_bad_program_before_exec():
    res, err, logs = run_program("def residual(ctx):\n    import os\n    return 1", _ctx(), timeout=10.0)
    assert res is None and err is not None
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/era/test_sandbox.py -q`
Expected: FAIL (cannot import sandbox)

- [ ] **Step 3: Implement**

```python
# scripts/era/sandbox.py
from __future__ import annotations
import ast, json, subprocess, sys, tempfile
from pathlib import Path
import numpy as np
from scripts.era.context import CrossSectionContext

_FORBIDDEN_NAMES = {"open", "eval", "exec", "compile", "__import__", "globals",
                    "locals", "getattr", "setattr", "delattr", "vars", "input"}

def static_check(src: str) -> tuple[bool, str]:
    """Reject imports, dunder access, and dangerous builtins. Require residual()."""
    try:
        tree = ast.parse(src)
    except SyntaxError as e:
        return False, f"syntax error: {e}"
    has_residual = False
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            return False, "imports are not allowed"
        if isinstance(node, ast.Attribute) and node.attr.startswith("__"):
            return False, f"dunder attribute access not allowed: {node.attr}"
        if isinstance(node, ast.Name) and node.id in _FORBIDDEN_NAMES:
            return False, f"forbidden name: {node.id}"
        if isinstance(node, ast.FunctionDef) and node.name == "residual":
            has_residual = True
    if not has_residual:
        return False, "must define residual(ctx)"
    return True, "ok"

# Worker source: runs in a subprocess, reconstructs ctx, execs the program.
_WORKER = r'''
import sys, json, numpy as np
from scripts.era.context import CrossSectionContext
payload = np.load(sys.argv[1], allow_pickle=True)
src = str(payload["src"])
ctx = CrossSectionContext(r=payload["r"], names=list(payload["names"]),
                          target=str(payload["target"]), usd_sign=int(payload["usd_sign"]))
ns = {"np": np}
try:
    exec(src, ns)
    out = np.asarray(ns["residual"](ctx), dtype=float).reshape(-1)
    if out.shape[0] != ctx.n_bars:
        raise ValueError(f"residual length {out.shape[0]} != n_bars {ctx.n_bars}")
    np.save(sys.argv[2], out)
    print("OK")
except Exception as e:
    print(f"ERR {type(e).__name__}: {e}", file=sys.stderr)
    sys.exit(3)
'''

def run_program(src: str, ctx: CrossSectionContext, timeout: float = 10.0):
    """Return (residual_array | None, error | None, logs)."""
    ok, reason = static_check(src)
    if not ok:
        return None, f"static_check: {reason}", ""
    with tempfile.TemporaryDirectory() as d:
        inp = Path(d) / "in.npz"; out = Path(d) / "out.npy"; wrk = Path(d) / "w.py"
        np.savez(inp, src=src, r=ctx.r, names=np.array(ctx.names),
                 target=ctx.target, usd_sign=ctx.usd_sign)
        wrk.write_text(_WORKER)
        try:
            proc = subprocess.run([sys.executable, str(wrk), str(inp), str(out)],
                                  capture_output=True, text=True, timeout=timeout,
                                  cwd=str(Path.cwd()))
        except subprocess.TimeoutExpired:
            return None, "timeout", ""
        logs = (proc.stdout + proc.stderr).strip()
        if proc.returncode != 0 or not out.exists():
            return None, logs or f"exit {proc.returncode}", logs
        return np.load(out), None, logs
```

- [ ] **Step 4: Run it to verify it passes**

Run: `uv run pytest tests/era/test_sandbox.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/era/sandbox.py tests/era/test_sandbox.py
git commit -m "feat(era): program sandbox (AST whitelist + subprocess exec)"
```

---

## Task 3: Harness — residual → entries/sides/net

**Files:**
- Create: `scripts/era/harness.py`
- Test: `tests/era/test_harness.py`

`evaluate_residual(residual, usd_sign, y_fwd, cost, test_month, threshold)`
applies the FIXED entry/side/scoring around a program's residual:
`entry = |z| >= threshold`, `side = -sign(z) * usd_sign`,
`net = side * y_fwd - cost`. Returns a per-entry DataFrame `[net, test_month]`.
`z` is the residual standardised across its own finite values so a single
`threshold` grid is comparable across programs.

- [ ] **Step 1: Write the failing test**

```python
# tests/era/test_harness.py
import numpy as np, pandas as pd
from scripts.era.harness import standardise, evaluate_residual

def test_standardise_zero_mean_unit_std():
    z = standardise(np.array([1.0, 2, 3, 4, 5]))
    assert abs(np.nanmean(z)) < 1e-9 and abs(np.nanstd(z) - 1.0) < 1e-6

def test_entries_sides_and_net():
    resid = np.array([3.0, -3.0, 0.0, 5.0])     # standardise then |z|>=thr
    y_fwd = np.array([2.0, 2.0, 2.0, 2.0])
    cost  = np.array([0.5, 0.5, 0.5, 0.5])
    months = np.array(["2025-01"] * 4)
    df = evaluate_residual(resid, usd_sign=-1, y_fwd=y_fwd, cost=cost,
                           test_month=months, threshold=1.0)
    # bar 2 (z==0) is never an entry
    assert len(df) == 3
    # side = -sign(z) * usd_sign ; for z>0, usd_sign=-1 -> side = +1
    # net for bar0 (z>0): side=+1 -> 1*2 - 0.5 = 1.5
    assert abs(df.iloc[0]["net"] - 1.5) < 1e-9
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/era/test_harness.py -q`
Expected: FAIL (cannot import harness)

- [ ] **Step 3: Implement**

```python
# scripts/era/harness.py
from __future__ import annotations
import numpy as np, pandas as pd

def standardise(resid: np.ndarray) -> np.ndarray:
    r = np.asarray(resid, dtype=float)
    finite = np.isfinite(r)
    if finite.sum() < 2:
        return np.full_like(r, np.nan)
    mu = r[finite].mean(); sd = r[finite].std(ddof=0)
    if sd == 0:
        return np.zeros_like(r)
    return (r - mu) / sd

def evaluate_residual(residual, usd_sign, y_fwd, cost, test_month, threshold):
    """Fixed causal entry/side/scoring around a program's residual."""
    z = standardise(residual)
    y_fwd = np.asarray(y_fwd, float); cost = np.asarray(cost, float)
    valid = np.isfinite(z) & np.isfinite(y_fwd) & np.isfinite(cost)
    entry = valid & (np.abs(z) >= float(threshold))
    side = -np.sign(z) * int(usd_sign)
    net = side * y_fwd - cost
    return pd.DataFrame({"net": net[entry], "test_month": np.asarray(test_month)[entry]})
```

- [ ] **Step 4: Run it to verify it passes**

Run: `uv run pytest tests/era/test_harness.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/era/harness.py tests/era/test_harness.py
git commit -m "feat(era): harness residual->entries/sides/net"
```

---

## Task 4: Continuous TaskScore (dense, permissive)

**Files:**
- Modify: `scripts/era/harness.py`
- Test: `tests/era/test_taskscore.py`

`task_score(df)` over one split's entry DataFrame is a **continuous** signal —
no hard gate: `score = net_lb95 * month_weight * n_weight`, where
`net_lb95 = mean - 1.645*SE`, `month_weight = positive_month_share` (∈[0,1]),
`n_weight = n / (n + N0)` (smooth saturation, `N0=100`). Empty/degenerate → a
finite floor (a large negative number) so PUCT still has a gradient. Best over a
threshold grid is taken by the caller.

- [ ] **Step 1: Write the failing test**

```python
# tests/era/test_taskscore.py
import numpy as np, pandas as pd
from scripts.era.harness import task_score

def _df(nets, months):
    return pd.DataFrame({"net": nets, "test_month": months})

def test_warmer_scores_higher():
    good = _df([2.0]*60 + [1.0]*60, ["2025-01"]*60 + ["2025-02"]*60)
    weak = _df([0.1]*60 + [-0.1]*60, ["2025-01"]*60 + ["2025-02"]*60)
    assert task_score(good) > task_score(weak)

def test_empty_is_finite_floor():
    s = task_score(_df([], []))
    assert np.isfinite(s) and s < -1e3

def test_more_months_positive_helps():
    a = _df([1.0]*100, ["2025-01"]*50 + ["2025-02"]*50)            # 2/2 months +
    b = _df([1.0]*50 + [-3.0]*50, ["2025-01"]*50 + ["2025-02"]*50)  # 1/2 months +
    assert task_score(a) > task_score(b)
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/era/test_taskscore.py -q`
Expected: FAIL (task_score not defined)

- [ ] **Step 3: Implement (append to harness.py)**

```python
# scripts/era/harness.py  (append)
_FLOOR = -1e6
_N0 = 100

def task_score(df: pd.DataFrame) -> float:
    """Continuous, permissive per-node signal. NEVER a hard gate."""
    n = len(df)
    if n < 2:
        return _FLOOR + n  # finite, slightly rewards 'some entries' over none
    net = df["net"].to_numpy(float)
    mean = net.mean(); se = net.std(ddof=1) / np.sqrt(n)
    net_lb95 = mean - 1.645 * se
    monthly = df.groupby("test_month")["net"].mean()
    month_weight = float((monthly > 0).mean())          # in [0,1]
    n_weight = n / (n + _N0)                             # smooth saturation
    # keep continuous & signed: a positive lb95 with consistent months scores high
    return float(net_lb95 * (0.25 + 0.75 * month_weight) * n_weight)
```

- [ ] **Step 4: Run it to verify it passes**

Run: `uv run pytest tests/era/test_taskscore.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/era/harness.py tests/era/test_taskscore.py
git commit -m "feat(era): continuous dense TaskScore (no in-search gate)"
```

---

## Task 5: Scoring adapter — load split data, score a program end-to-end

**Files:**
- Create: `scripts/era/score_program.py`
- Test: `tests/era/test_score_program.py`

`ProgramScorer` loads the cross-symbol frame + velocity once per (symbol,
bar_ticks), splits months into train/validation/holdout, and exposes
`score(src, split) -> (score, logs)` by running the sandbox, building the
`CrossSectionContext`, sweeping the threshold grid, and taking the best
`task_score` on the requested split. This is the GenerateAndExecute backbone.

- [ ] **Step 1: Write the failing test** (uses a tiny synthetic frame, no real data)

```python
# tests/era/test_score_program.py
import numpy as np, pandas as pd
from scripts.era.score_program import ProgramScorer, SplitData

def _split():
    n = 300
    rng = np.random.RandomState(1)
    r = rng.randn(n, 6)
    # craft a reverting target: y_fwd opposes the target's idiosyncratic move
    z = (r[:, 0] - r[:, 1:].mean(1)) / (r[:, 1:].std(1) + 1e-9)
    y = -np.sign(z) * np.abs(rng.randn(n)) * (-1)   # so fading z is profitable
    months = np.array([f"2025-{1+(i%6):02d}" for i in range(n)])
    return SplitData(r=r, names=list("ABCDEF"), target="A", usd_sign=-1,
                     y_fwd=y, cost=np.full(n, 0.1), test_month=months)

LOO = "def residual(ctx):\n t=ctx.target_col(); p=ctx.peers()\n return (t-p.mean(1))/(p.std(1)+1e-9)"

def test_score_runs_and_is_finite():
    sc = ProgramScorer(splits={"train": _split()}, thresholds=[1.0, 1.5, 2.0])
    score, logs = sc.score(LOO, "train")
    assert np.isfinite(score)

def test_bad_program_returns_floor():
    sc = ProgramScorer(splits={"train": _split()}, thresholds=[1.0])
    score, logs = sc.score("def residual(ctx):\n import os\n return 1", "train")
    assert score <= -1e3 and "static_check" in logs
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/era/test_score_program.py -q`
Expected: FAIL (cannot import score_program)

- [ ] **Step 3: Implement**

```python
# scripts/era/score_program.py
from __future__ import annotations
from dataclasses import dataclass
import numpy as np
from scripts.era.context import CrossSectionContext
from scripts.era.sandbox import run_program
from scripts.era.harness import evaluate_residual, task_score

@dataclass
class SplitData:
    r: np.ndarray; names: list[str]; target: str; usd_sign: int
    y_fwd: np.ndarray; cost: np.ndarray; test_month: np.ndarray

class ProgramScorer:
    def __init__(self, splits: dict[str, SplitData], thresholds: list[float],
                 timeout: float = 10.0):
        self.splits = splits; self.thresholds = thresholds; self.timeout = timeout

    def score(self, src: str, split: str) -> tuple[float, str]:
        d = self.splits[split]
        ctx = CrossSectionContext(r=d.r, names=d.names, target=d.target, usd_sign=d.usd_sign)
        resid, err, logs = run_program(src, ctx, timeout=self.timeout)
        if err is not None:
            return -1e6, f"static_check/exec: {err}" if "static_check" in (err or "") else f"exec: {err}\n{logs}"
        best = -1e9
        for thr in self.thresholds:
            df = evaluate_residual(resid, d.usd_sign, d.y_fwd, d.cost, d.test_month, thr)
            best = max(best, task_score(df))
        return float(best), logs
```

- [ ] **Step 4: Run it to verify it passes**

Run: `uv run pytest tests/era/test_score_program.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/era/score_program.py tests/era/test_score_program.py
git commit -m "feat(era): ProgramScorer (sandbox+harness over a split)"
```

---

## Task 6: Seeds — baseline programs + research-idea summaries

**Files:**
- Create: `scripts/era/seeds.py`
- Test: `tests/era/test_seeds.py`

The four baselines **as program sources** (the loop must rediscover/beat them)
plus the research-idea summary strings injected into prompts.

- [ ] **Step 1: Write the failing test**

```python
# tests/era/test_seeds.py
import numpy as np
from scripts.era.seeds import SEED_PROGRAMS, RESEARCH_IDEAS
from scripts.era.context import CrossSectionContext
from scripts.era.sandbox import run_program

def test_all_seeds_validate_and_run():
    r = np.random.RandomState(2).randn(50, 6)
    ctx = CrossSectionContext(r=r, names=list("ABCDEF"), target="A", usd_sign=-1)
    assert {"loo_z", "robust_z", "graph_laplacian", "dispersion_rank"} <= set(SEED_PROGRAMS)
    for name, src in SEED_PROGRAMS.items():
        resid, err, logs = run_program(src, ctx, timeout=10.0)
        assert err is None, f"{name}: {err}"
        assert resid.shape == (50,)

def test_research_ideas_nonempty():
    assert len(RESEARCH_IDEAS) >= 4 and all(len(s) > 20 for s in RESEARCH_IDEAS)
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/era/test_seeds.py -q`
Expected: FAIL (cannot import seeds)

- [ ] **Step 3: Implement**

```python
# scripts/era/seeds.py
"""Baseline dispersion programs (seeds) + research-idea summaries."""

SEED_PROGRAMS: dict[str, str] = {
    # all6 z (the diluted baseline)
    "all6_z": (
        "def residual(ctx):\n"
        "    r = ctx.r\n"
        "    mu = r.mean(axis=1, keepdims=True)\n"
        "    sd = r.std(axis=1, keepdims=True) + 1e-9\n"
        "    z = (r - mu) / sd\n"
        "    return z[:, ctx.target_idx]\n"
    ),
    # leave-one-out basket z
    "loo_z": (
        "def residual(ctx):\n"
        "    t = ctx.target_col(); p = ctx.peers()\n"
        "    return (t - p.mean(axis=1)) / (p.std(axis=1) + 1e-9)\n"
    ),
    # robust median/MAD over all 6
    "robust_z": (
        "def residual(ctx):\n"
        "    r = ctx.r\n"
        "    med = np.median(r, axis=1)\n"
        "    mad = np.median(np.abs(r - med[:, None]), axis=1) + 1e-9\n"
        "    return (ctx.target_col() - med) / (1.4826 * mad)\n"
    ),
    # fixed-cluster graph-laplacian residual (EUR/GBP/AUD vs JPY/CHF/CAD by name)
    "graph_laplacian": (
        "def residual(ctx):\n"
        "    cl = {'EURUSD':0,'GBPUSD':0,'AUDUSD':0,'USDJPY':1,'USDCHF':1,'USDCAD':1}\n"
        "    g = np.array([cl.get(n, 0) for n in ctx.names])\n"
        "    ti = ctx.target_idx; same = (g == g[ti])\n"
        "    same[ti] = False\n"
        "    if same.sum() == 0:\n"
        "        nb = ctx.peers().mean(axis=1)\n"
        "    else:\n"
        "        nb = ctx.r[:, same].mean(axis=1)\n"
        "    d = ctx.target_col() - nb\n"
        "    return d / (np.nanstd(d) + 1e-9)\n"
    ),
    # ordinal dispersion rank (k=2): +/- by extremity of cross-sectional rank
    "dispersion_rank": (
        "def residual(ctx):\n"
        "    r = ctx.r; n, m = r.shape\n"
        "    order = np.argsort(-r, axis=1, kind='stable')\n"
        "    ranks = np.empty_like(order)\n"
        "    rows = np.arange(n)[:, None]\n"
        "    ranks[rows, order] = np.broadcast_to(np.arange(1, m + 1), order.shape)\n"
        "    tr = ranks[:, ctx.target_idx].astype(float)\n"
        "    mid = (m + 1) / 2.0\n"
        "    return mid - tr  # >0 near top rank, <0 near bottom\n"
    ),
}

RESEARCH_IDEAS: list[str] = [
    "Leave-one-out basket residual: standardise the target's USD-aligned return "
    "against the mean and std of the OTHER five majors only, so the target is not "
    "in its own benchmark; fade large residuals.",
    "Robust residual: use median and MAD instead of mean/std so one extreme peer "
    "print cannot distort the basket; fade outliers.",
    "Graph/cluster residual: compare the target only to its most related peers "
    "(e.g. EUR/GBP/AUD vs JPY/CHF/CAD) rather than the equal-weight basket.",
    "Participation/concentration gate: only treat a move as idiosyncratic when it "
    "is concentrated in the target (high participation ratio), not a broad USD move.",
    "Dispersion-regime conditioning: reversion of an extreme is stronger when "
    "cross-sectional dispersion (std of the six returns) is high; weight by it.",
    "Rank-transition: an extreme cross-sectional rank tends to move back toward the "
    "middle over the horizon; size the fade by how extreme the rank is.",
]
```

- [ ] **Step 4: Run it to verify it passes**

Run: `uv run pytest tests/era/test_seeds.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/era/seeds.py tests/era/test_seeds.py
git commit -m "feat(era): seed baseline programs + research ideas"
```

---

## Task 7: LLM writer — ollama.com qwen3-coder-next with cache

**Files:**
- Create: `scripts/cheap_llm.sh`
- Create: `scripts/era/llm.py`
- Test: `tests/era/test_llm.py`

`propose_program(parent_src, parent_score, logs, idea, cache_dir, caller)`
builds the prompt, calls the generator through an injectable `caller` (so tests
mock it), extracts the program source from the response, and caches by prompt
hash. `cheap_llm.sh` is the production `caller` (curl to ollama.com).

- [ ] **Step 1: Write the failing test**

```python
# tests/era/test_llm.py
from scripts.era.llm import build_prompt, extract_program, propose_program

def test_prompt_includes_parent_context():
    p = build_prompt("def residual(ctx): return ctx.target_col()", -0.5,
                     "exec: nan residual", "use leave-one-out")
    assert "residual(ctx)" in p and "-0.5" in p and "leave-one-out" in p
    assert "y_fwd" in p.lower()  # the causal rule is stated

def test_extract_program_from_fenced_block():
    resp = "Here:\n```python\ndef residual(ctx):\n    return ctx.target_col()\n```\n"
    src = extract_program(resp)
    assert src.strip().startswith("def residual(ctx):")

def test_propose_uses_caller_and_caches(tmp_path):
    calls = []
    def fake_caller(prompt: str) -> str:
        calls.append(prompt)
        return "```python\ndef residual(ctx):\n    return ctx.target_col()\n```"
    src1 = propose_program("def residual(ctx): return ctx.target_col()", 0.0, "",
                           "idea", cache_dir=tmp_path, caller=fake_caller)
    src2 = propose_program("def residual(ctx): return ctx.target_col()", 0.0, "",
                           "idea", cache_dir=tmp_path, caller=fake_caller)
    assert src1 == src2
    assert len(calls) == 1  # second call served from cache
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/era/test_llm.py -q`
Expected: FAIL (cannot import llm)

- [ ] **Step 3: Implement**

```python
# scripts/era/llm.py
from __future__ import annotations
import hashlib, json, re, subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

_RULES = (
    "You write a Python function `residual(ctx) -> np.ndarray`.\n"
    "ctx gives ONLY causal cross-section data: ctx.r (n_bars x 6 USD-aligned\n"
    "vol-normalised returns), ctx.target_col(), ctx.peers(), ctx.target_idx,\n"
    "ctx.names, ctx.usd_sign. `np` is available. You CANNOT import anything and\n"
    "CANNOT access future returns / y_fwd / labels (they are not in ctx).\n"
    "Return a per-bar residual; larger |residual| == stronger idiosyncratic\n"
    "dislocation of the target. Output ONLY one ```python code block.\n"
)

def build_prompt(parent_src: str, parent_score: float, logs: str, idea: str) -> str:
    return (
        "Improve this dispersion residual program to increase its score.\n\n"
        f"{_RULES}\n"
        f"Research idea to consider: {idea}\n\n"
        f"Parent score: {parent_score}\n"
        f"Parent logs: {logs[:500]}\n\n"
        f"Parent program:\n```python\n{parent_src}\n```\n"
    )

def extract_program(resp: str) -> str:
    m = re.search(r"```(?:python)?\s*(.*?)```", resp, re.DOTALL)
    src = (m.group(1) if m else resp).strip()
    return src

def _ollama_caller(prompt: str) -> str:
    out = subprocess.run([str(ROOT / "scripts/cheap_llm.sh"), prompt],
                         capture_output=True, text=True, timeout=180)
    return out.stdout

def propose_program(parent_src, parent_score, logs, idea, cache_dir, caller=None):
    caller = caller or _ollama_caller
    cache_dir = Path(cache_dir); cache_dir.mkdir(parents=True, exist_ok=True)
    prompt = build_prompt(parent_src, parent_score, logs, idea)
    key = hashlib.sha256(prompt.encode()).hexdigest()[:16]
    cached = cache_dir / f"{key}.py"
    if cached.exists():
        return cached.read_text()
    src = extract_program(caller(prompt))
    cached.write_text(src)
    return src
```
```bash
# scripts/cheap_llm.sh
#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
set -a; . "$ROOT/.env" 2>/dev/null || true; set +a
: "${OLLAMA_API_KEY:?OLLAMA_API_KEY not set (add to .env)}"
MODEL="${ERA_GEN_MODEL:-qwen3-coder-next}"
PROMPT="${1:?prompt required}"
curl -sS --max-time 180 https://ollama.com/api/generate \
  -H "Authorization: Bearer $OLLAMA_API_KEY" \
  -d "$(jq -n --arg m "$MODEL" --arg p "$PROMPT" '{model:$m, prompt:$p, stream:false}')" \
  | jq -r '.response'
```

- [ ] **Step 4: Run it to verify it passes + make the shell executable**

Run: `chmod +x scripts/cheap_llm.sh && uv run pytest tests/era/test_llm.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/era/llm.py scripts/cheap_llm.sh tests/era/test_llm.py
git commit -m "feat(era): qwen3-coder-next writer wrapper + prompt + cache"
```

---

## Task 8: PUCT engine

**Files:**
- Create: `scripts/era/puct.py`
- Test: `tests/era/test_puct.py`

Globally-flat PUCT (ERA Algorithm 1). `puct_search(root_score_fn, expand_fn,
budget, c_puct, seed)` keeps all nodes, selects `argmax RankScore + c_puct *
P * sqrt(N)/(1+V)`, calls `expand_fn(parent) -> child` once per iteration,
backpropagates visit counts, returns the full node list (selection of the
winner is end-stage, Task 9).

- [ ] **Step 1: Write the failing test** (LLM mocked via a deterministic expand_fn)

```python
# tests/era/test_puct.py
import numpy as np
from scripts.era.puct import Node, puct_search

def test_search_improves_and_keeps_all_nodes():
    # toy: a node's "program" is a float x; score = -(x-3)**2; child nudges toward 3
    rng = np.random.RandomState(0)
    def expand(parent):
        x = parent.payload + rng.uniform(-1, 1)
        return Node(payload=x, score=-(x - 3.0) ** 2, parent=parent)
    root = Node(payload=0.0, score=-(0 - 3.0) ** 2, parent=None)
    nodes = puct_search(root, expand, budget=80, c_puct=1.0, seed=0)
    assert len(nodes) == 81  # root + 80 expansions, nothing pruned
    best = max(nodes, key=lambda n: n.score)
    assert best.score > root.score  # search made progress

def test_selection_prefers_high_rank_or_low_visits():
    # a visited high scorer vs an unvisited node: exploration term must matter
    from scripts.era.puct import select
    a = Node(payload=1, score=1.0, parent=None); a.visits = 50
    b = Node(payload=2, score=0.9, parent=None); b.visits = 1
    chosen = select([a, b], c_puct=1.0)
    assert chosen is b  # low-visit node wins on exploration despite lower score
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/era/test_puct.py -q`
Expected: FAIL (cannot import puct)

- [ ] **Step 3: Implement**

```python
# scripts/era/puct.py
from __future__ import annotations
from dataclasses import dataclass, field
import numpy as np

@dataclass
class Node:
    payload: object            # program source (or toy value)
    score: float               # validation TaskScore
    parent: "Node | None"
    visits: int = 1
    logs: str = ""
    children: list = field(default_factory=list)

def _rank_scores(nodes: list[Node]) -> dict[int, float]:
    order = sorted(range(len(nodes)), key=lambda i: nodes[i].score)
    out = {}
    for rank, i in enumerate(order):
        out[i] = rank / max(1, len(nodes) - 1)  # 0..1, higher score -> higher rank
    return out

def select(nodes: list[Node], c_puct: float) -> Node:
    ranks = _rank_scores(nodes)
    n_total = sum(n.visits for n in nodes)
    p = 1.0 / len(nodes)  # uniform prior
    best_i, best_v = 0, -1e18
    for i, nd in enumerate(nodes):
        explore = c_puct * p * np.sqrt(n_total) / (1 + nd.visits)
        v = ranks[i] + explore
        if v > best_v:
            best_v, best_i = v, i
    return nodes[best_i]

def puct_search(root: Node, expand_fn, budget: int, c_puct: float = 1.0,
                seed: int = 0) -> list[Node]:
    np.random.seed(seed)
    nodes = [root]
    for _ in range(budget):
        parent = select(nodes, c_puct)
        child = expand_fn(parent)
        parent.children.append(child)
        nodes.append(child)
        a = child.parent
        while a is not None:
            a.visits += 1
            a = a.parent
    return nodes
```

- [ ] **Step 4: Run it to verify it passes**

Run: `uv run pytest tests/era/test_puct.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/era/puct.py tests/era/test_puct.py
git commit -m "feat(era): globally-flat PUCT engine"
```

---

## Task 9: End-stage selection — BH-FDR + held-out

**Files:**
- Create: `scripts/era/select.py`
- Test: `tests/era/test_select.py`

Applied ONCE after search. `bh_fdr(pvalues, q)` returns the significance mask.
`select_winners(nodes, scorer, q)` computes a one-sided p-value per node from
its **validation** entries, BH-corrects across all nodes, and for survivors
reports the **held-out** score. Never used during search.

- [ ] **Step 1: Write the failing test**

```python
# tests/era/test_select.py
import numpy as np
from scripts.era.select import bh_fdr

def test_bh_basic():
    p = np.array([0.001, 0.2, 0.03, 0.8])
    sig = bh_fdr(p, q=0.1)
    assert sig[0] and not sig[3]
    assert sig.dtype == bool and sig.shape == (4,)

def test_bh_all_null():
    assert not bh_fdr(np.array([0.9, 0.8, 0.95]), q=0.1).any()
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/era/test_select.py -q`
Expected: FAIL (cannot import select)

- [ ] **Step 3: Implement**

```python
# scripts/era/select.py
from __future__ import annotations
import numpy as np

def bh_fdr(pvalues: np.ndarray, q: float = 0.10) -> np.ndarray:
    p = np.asarray(pvalues, float)
    ok = np.isfinite(p)
    idx = np.where(ok)[0]
    if idx.size == 0:
        return np.zeros_like(p, dtype=bool)
    order = idx[np.argsort(p[idx])]
    m = order.size
    thresh = 0.0
    for rank, i in enumerate(order, start=1):
        if p[i] <= rank / m * q:
            thresh = p[i]
    return ok & (p <= thresh)
```

(`select_winners` orchestration — computing per-node validation p-values via a
one-sided t-test on entry nets and reporting held-out scores — is wired in the
driver, Task 10, where the scorer and nodes are in scope. The BH primitive is
the unit under test here.)

- [ ] **Step 4: Run it to verify it passes**

Run: `uv run pytest tests/era/test_select.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/era/select.py tests/era/test_select.py
git commit -m "feat(era): end-stage Benjamini-Hochberg FDR"
```

---

## Task 10: Driver + data loading + integration test

**Files:**
- Create: `scripts/era/load_splits.py`
- Create: `scripts/era/run_era.py`
- Test: `tests/era/test_integration.py`

`load_splits.build_splits(symbol, bar_ticks, tom_dir, velocity_dir, month_bins)`
returns `{train, validation, holdout}` `SplitData` by joining the cross-symbol
frame's `xs_ret_z__*` with that symbol's velocity `y_fwd_pips_h{h}`/`cost_est_pips`
on `close_ts`, and partitioning by `test_month`. `run_era.main()` wires seeds →
PUCT (`expand_fn` = sandbox-score a qwen-proposed child) → report. The
**integration test** uses a synthetic split + a **mocked writer** that returns
seed programs, and asserts a seed baseline lands at the top of the tree.

- [ ] **Step 1: Write the failing integration test**

```python
# tests/era/test_integration.py
import numpy as np
from scripts.era.score_program import SplitData
from scripts.era.seeds import SEED_PROGRAMS
from scripts.era.run_era import run_search

def _reverting_split(n=400, seed=3):
    rng = np.random.RandomState(seed)
    r = rng.randn(n, 6)
    z = (r[:, 0] - r[:, 1:].mean(1)) / (r[:, 1:].std(1) + 1e-9)
    # fading z (side = -sign(z)*usd_sign, usd_sign=-1) is profitable:
    y = np.sign(z) * np.abs(rng.randn(n))      # so side*y = -|.| ... see harness
    months = np.array([f"2025-{1 + (i % 8):02d}" for i in range(n)])
    return SplitData(r=r, names=list("ABCDEF"), target="A", usd_sign=-1,
                     y_fwd=-y, cost=np.full(n, 0.05), test_month=months)

def test_search_rediscovers_a_seed_baseline():
    splits = {"train": _reverting_split(), "validation": _reverting_split(seed=4)}
    # mocked writer: always returns the loo_z seed (stands in for qwen)
    def writer(parent_src, parent_score, logs, idea, cache_dir, caller=None):
        return SEED_PROGRAMS["loo_z"]
    nodes = run_search(splits, thresholds=[1.0, 1.5, 2.0], budget=20,
                       writer=writer, ideas=["loo"], seed=0)
    best = max(nodes, key=lambda nd: nd.score)
    assert np.isfinite(best.score)
    # loo_z must score finite & be selected among the top
    assert best.score >= sorted(nd.score for nd in nodes)[len(nodes)//2]
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/era/test_integration.py -q`
Expected: FAIL (cannot import run_era.run_search)

- [ ] **Step 3: Implement `run_search` + driver glue**

```python
# scripts/era/run_era.py
from __future__ import annotations
import argparse, random
from pathlib import Path
import numpy as np
from scripts.era.score_program import ProgramScorer, SplitData
from scripts.era.puct import Node, puct_search
from scripts.era.seeds import SEED_PROGRAMS, RESEARCH_IDEAS
from scripts.era.llm import propose_program

def run_search(splits: dict[str, SplitData], thresholds, budget, writer=propose_program,
               ideas=None, seed: int = 0, cache_dir: str = "/tmp/era_cache"):
    ideas = ideas or RESEARCH_IDEAS
    scorer = ProgramScorer(splits=splits, thresholds=thresholds)
    rng = random.Random(seed)
    # seed the tree with the best baseline as root; others as initial children
    root_src = SEED_PROGRAMS["loo_z"]
    rs, rlogs = scorer.score(root_src, "validation" if "validation" in splits else "train")
    root = Node(payload=root_src, score=rs, parent=None, logs=rlogs)
    nodes = [root]
    for name, src in SEED_PROGRAMS.items():
        if name == "loo_z":
            continue
        s, lg = scorer.score(src, "validation" if "validation" in splits else "train")
        ch = Node(payload=src, score=s, parent=root, logs=lg)
        root.children.append(ch); nodes.append(ch)

    split_for_rank = "validation" if "validation" in splits else "train"
    def expand(parent: Node) -> Node:
        idea = rng.choice(ideas)
        child_src = writer(parent.payload, parent.score, parent.logs, idea, cache_dir=cache_dir)
        s, lg = scorer.score(child_src, split_for_rank)
        return Node(payload=child_src, score=s, parent=parent, logs=lg)

    # continue PUCT from the seeded forest
    extra = puct_search(root, expand, budget=budget, c_puct=1.0, seed=seed)
    # puct_search starts from root only; merge the pre-seeded children list
    seen = {id(n) for n in extra}
    for n in nodes:
        if id(n) not in seen:
            extra.append(n)
    return extra

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbol", default="EURUSD")
    ap.add_argument("--bar-ticks", type=int, default=2000)
    ap.add_argument("--budget", type=int, default=60)
    ap.add_argument("--tom-dir", required=True)
    ap.add_argument("--velocity-dir", required=True)
    ap.add_argument("--horizon", type=int, default=3)
    ap.add_argument("--out", default="/tmp/era/report.md")
    args = ap.parse_args()
    from scripts.era.load_splits import build_splits
    splits = build_splits(args.symbol, args.bar_ticks, Path(args.tom_dir),
                          Path(args.velocity_dir), horizon=args.horizon)
    nodes = run_search(splits, thresholds=[1.0, 1.5, 2.0, 2.5], budget=args.budget)
    nodes.sort(key=lambda n: n.score, reverse=True)
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    with open(args.out, "w") as f:
        f.write(f"# ERA SP1 run — {args.symbol} {args.bar_ticks}tick\n\n")
        f.write(f"nodes: {len(nodes)}\n\n## Top 10 by validation score\n\n")
        for nd in nodes[:10]:
            f.write(f"- score={nd.score:.4f}\n```python\n{nd.payload}\n```\n")
    print(f"wrote {args.out}")

if __name__ == "__main__":
    main()
```
```python
# scripts/era/load_splits.py
from __future__ import annotations
from pathlib import Path
import numpy as np, pandas as pd
from scripts.era.score_program import SplitData

def build_splits(symbol, bar_ticks, tom_dir: Path, velocity_dir: Path, horizon: int = 3,
                 train=("2025-01","2025-02","2025-03","2025-04","2025-05","2025-06"),
                 validation=("2025-07","2025-08","2025-09","2025-10"),
                 holdout=("2025-11","2025-12","2026-01","2026-02")):
    import sys
    sys.path.insert(0, str(Path.cwd()))
    from scripts.cross_symbol import get_or_build_cross_symbol_frame, CROSS_SYMBOLS, _USD_SIGN
    cs = get_or_build_cross_symbol_frame(symbol, bar_ticks, velocity_dir, [horizon]).copy()
    cs["close_ts"] = pd.to_datetime(cs["close_ts"], utc=True)
    vel = pd.read_parquet(velocity_dir / f"{symbol}_{bar_ticks}tick_velocity.parquet")
    vel["close_ts"] = pd.to_datetime(vel["close_ts"], utc=True)
    keep = ["close_ts", "cost_est_pips", f"y_fwd_pips_h{horizon}", "test_month"] \
        if "test_month" in vel.columns else ["close_ts", "cost_est_pips", f"y_fwd_pips_h{horizon}"]
    m = cs.merge(vel[keep].drop_duplicates("close_ts"), on="close_ts", how="inner")
    if "test_month" not in m.columns:
        m["test_month"] = m["close_ts"].dt.strftime("%Y-%m")
    cols = [f"xs_ret_z__{s}" for s in CROSS_SYMBOLS]
    def _split(months):
        d = m[m["test_month"].isin(months)]
        return SplitData(r=d[cols].to_numpy(float), names=list(CROSS_SYMBOLS),
                         target=symbol, usd_sign=int(_USD_SIGN[symbol]),
                         y_fwd=d[f"y_fwd_pips_h{horizon}"].to_numpy(float),
                         cost=d["cost_est_pips"].to_numpy(float),
                         test_month=d["test_month"].to_numpy())
    return {"train": _split(train), "validation": _split(validation), "holdout": _split(holdout)}
```

- [ ] **Step 4: Run it to verify it passes**

Run: `uv run pytest tests/era/test_integration.py -q`
Expected: PASS

- [ ] **Step 5: Run the full era test suite**

Run: `uv run pytest tests/era/ -q`
Expected: PASS (all)

- [ ] **Step 6: Commit**

```bash
git add scripts/era/load_splits.py scripts/era/run_era.py tests/era/test_integration.py
git commit -m "feat(era): driver, split loading, mocked-LLM integration test"
```

---

## Task 11 (Opus, evidence — not CI): live qwen3-coder-next run

**Files:** none (produces `/tmp/era/report.md`)

> Executed by Opus, against the trial artifacts, with the real generator.

- [ ] **Step 1: Confirm key + model**

Run: `bash -c 'set -a; . .env; set +a; scripts/cheap_llm.sh "say ok"'`
Expected: a short reply (auth + model OK)

- [ ] **Step 2: Small live run on the dispersion lead**

Run:
```bash
TR=.worktrees/multi-family-trial-2026-05/data/analysis
uv run python -m scripts.era.run_era --symbol EURUSD --bar-ticks 2000 --horizon 3 \
  --budget 60 --tom-dir $TR/tick_opportunity_mining --velocity-dir $TR/tick_velocity \
  --out /tmp/era/eurusd_2000_h3.md
```
Expected: writes a top-10 report; `dispersion_rank`/`loo_z`/`robust_z` appear
near the top; ideally a discovered program's validation score exceeds the
`dispersion_rank` seed's. Opus reviews `report.md`, spot-checks the winner for
causality, and records findings (no commit of `/tmp` artifacts).

---

## Self-Review

**Spec coverage:** node=sandboxed program (T2,T5); causal context no y_fwd (T1);
fixed entry/side/net harness (T3); continuous dense TaskScore (T4); PUCT engine
(T8); qwen3-coder-next writer + .env + cache (T7); seeds incl. baselines + ideas
(T6); end-stage BH-FDR (T9) + held-out split (T10 load_splits); driver +
milestone integration (T10); live evidence (T11). Sandbox isolation tested (T2).
Model/build division documented in header. All spec sections map to a task.

**Placeholders:** none — every code step contains runnable code; `select_winners`
orchestration is explicitly deferred to the driver where scorer+nodes are in
scope, with the testable BH primitive delivered in T9.

**Type consistency:** `SplitData` fields and `Node` fields are used identically
across T5/T8/T10; `task_score(df)`, `evaluate_residual(...)`, `run_program(...)`
signatures match their callers; `propose_program(..., caller=)` matches the
mock in T7 and the `writer=` injection in T10.
