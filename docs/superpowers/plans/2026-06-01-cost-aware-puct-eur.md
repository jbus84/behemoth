# Cost-aware per-symbol Bayesian-PUCT (EUR) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a cost-aware, confidence-aware per-symbol ERA-PUCT search for EURUSD: realistic round-trip cost in the in-loop objective, a robustness-gated fast-lower-bound scorer, Thompson selection A/B'd against rank, with a rediscovery control and a must-beat-best-seed verdict.

**Architecture:** New `cost_model` (parametric round-trip cost) + `cost_aware_score` (per-symbol fast lower-bound scorer exposing a node edge posterior) + minimal `era/puct` additions (`Node.mean/se`, `select_thompson`, `puct_search(select_fn=)`) + a thin `run_era_eur` driver reusing qwen propose/recombine and `puct_search`. Final EUR-holdout verdict via `bayes_edge` on net-of-realistic-cost.

**Tech Stack:** Python, numpy, pandas, pytest, uv. qwen via existing `scripts/cheap_llm.sh`. NumPyro via `bayes_edge`. No new deps.

**Branch:** `era-cost-aware-puct` (created, spec committed). Do NOT touch main.

---

## File Structure
- `scripts/era_scalp/cost_model.py` — NEW: cost constants + `realistic_cost`.
- `scripts/era_scalp/load_splits.py` — MODIFY: `TradeSplitData.spread_pips`; `build_trade_splits` populates it.
- `scripts/era_scalp/cost_aware_score.py` — NEW: `fast_lower_bound`, `CostAwarePerSymbolScorer`.
- `scripts/era/puct.py` — MODIFY: `Node.mean/se`, `select_thompson`, `puct_search(select_fn=)`.
- `scripts/era_scalp/run_era_eur.py` — NEW: driver + CLI.
- Tests: `test_cost_model.py`, `test_cost_aware_score.py`, `test_puct_thompson.py`; extend `test_load_splits_trade.py`.
- `docs/analysis/era_cost_aware_puct_eur_2026-06-01.md` — NEW (Task 5).

---

### Task 1: Cost model + `spread_pips` on splits

**Files:** Create `scripts/era_scalp/cost_model.py`, `tests/era_scalp/test_cost_model.py`; Modify `scripts/era_scalp/load_splits.py`, `tests/era_scalp/test_load_splits_trade.py`

- [ ] **Step 1: Failing tests**

Create `tests/era_scalp/test_cost_model.py`:
```python
import numpy as np
from scripts.era_scalp.cost_model import COMMISSION_PIPS, SLIPPAGE_PIPS, realistic_cost


def test_realistic_cost_adds_commission_and_slippage():
    spread = np.array([0.3, 0.5, 1.0])
    out = realistic_cost(spread)
    assert np.allclose(out, spread + COMMISSION_PIPS + SLIPPAGE_PIPS)
    assert np.isclose(COMMISSION_PIPS + SLIPPAGE_PIPS, 0.16)


def test_realistic_cost_accepts_list():
    assert np.allclose(realistic_cost([0.4]), np.array([0.4 + 0.16]))
```

Add to `tests/era_scalp/test_load_splits_trade.py` (it already builds trade splits in a tmp parquet — mirror its existing fixture):
```python
def test_trade_split_has_spread_pips():
    # reuse this file's existing synthetic-parquet fixture/builder for build_trade_splits;
    # after building, every split must expose a spread_pips array the length of its X.
    import numpy as np
    from scripts.era_scalp.load_splits import build_trade_splits
    sp = _build_tmp_trade_splits()  # existing helper in this test module
    for phase in ("train", "validation", "holdout"):
        d = sp[phase]
        assert d.spread_pips is not None
        assert d.spread_pips.shape[0] == d.X.shape[0]
```
(If this test file has no reusable builder helper, add the new test using the same parquet-construction code the other tests in the file already use — match their fixture exactly; do not invent new columns beyond adding a `spread_pips` column to the synthetic frame.)

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/era_scalp/test_cost_model.py tests/era_scalp/test_load_splits_trade.py -q`
Expected: FAIL — `cost_model` missing; `TradeSplitData` has no `spread_pips`.

- [ ] **Step 3: Implement cost_model.py**

Create `scripts/era_scalp/cost_model.py`:
```python
from __future__ import annotations

import numpy as np

COMMISSION_PIPS = 0.06   # Dukascopy round-trip commission (~0.03/side)
SLIPPAGE_PIPS = 0.10     # buffer for adverse fills at extreme-dislocation bars


def realistic_cost(spread_pips) -> np.ndarray:
    """Per-bar realistic round-trip taker cost: bar spread + commission + slippage (pips)."""
    return np.asarray(spread_pips, float) + COMMISSION_PIPS + SLIPPAGE_PIPS
```

- [ ] **Step 4: Add `spread_pips` to TradeSplitData + builder**

In `scripts/era_scalp/load_splits.py`: Read the file. In the `@dataclass class TradeSplitData` add a field after `test_month`:
```python
    spread_pips: np.ndarray | None = None
```
In `build_trade_splits`'s inner `_split(...)` `return TradeSplitData(` call, add the argument:
```python
        spread_pips=d["spread_pips"].to_numpy(float),
```
(The parquet has a `spread_pips` column — confirmed. `d` is the per-split DataFrame.)

- [ ] **Step 5: Run tests + lint**

Run: `uv run pytest tests/era_scalp/test_cost_model.py tests/era_scalp/test_load_splits_trade.py -q` (PASS)
Run: `make lint` (All checks passed!)

- [ ] **Step 6: Commit**
```bash
git add scripts/era_scalp/cost_model.py scripts/era_scalp/load_splits.py tests/era_scalp/test_cost_model.py tests/era_scalp/test_load_splits_trade.py
git commit -m "feat(era-scalp): realistic round-trip cost model + spread_pips on trade splits

cost_model.realistic_cost = spread_pips + 0.06 commission + 0.10 slippage; TradeSplitData carries
per-bar spread_pips (populated by build_trade_splits) for the cost-aware objective."
```

---

### Task 2: Cost-aware per-symbol scorer

**Files:** Create `scripts/era_scalp/cost_aware_score.py`, `tests/era_scalp/test_cost_aware_score.py`

- [ ] **Step 1: Failing tests**

Create `tests/era_scalp/test_cost_aware_score.py`:
```python
import numpy as np
import pandas as pd

from scripts.era_scalp.load_splits import WHITELIST, TradeSplitData
from scripts.era_scalp import cost_aware_score as cas


def _split(n=1500, seed=0):
    rng = np.random.default_rng(seed)
    mid = 1.10 + np.cumsum(rng.standard_normal(n)) * 1e-4
    months = ([f"2024-{m:02d}" for m in range(1, 13)] * (n // 12 + 1))[:n]
    return TradeSplitData(
        X=rng.standard_normal((n, len(WHITELIST))), names=list(WHITELIST),
        hour=(np.arange(n) % 24).astype(float), mid=mid, cost=np.full(n, 0.4),
        test_month=np.array(months), spread_pips=np.full(n, 0.4),
    )


def test_fast_lower_bound_matches_hand_calc():
    frame = pd.DataFrame({"net": [2.0, 0.0, 4.0, 2.0, 1.0, 3.0],
                          "test_month": ["2024-01", "2024-01", "2024-02", "2024-02",
                                         "2024-03", "2024-03"]})
    lb, mean, se = cas.fast_lower_bound(frame, z=1.645)
    # monthly means: 1.0, 3.0, 2.0 -> mean 2.0, sample std 1.0, se=1/sqrt(3)
    assert np.isclose(mean, 2.0)
    assert np.isclose(se, 1.0 / np.sqrt(3), atol=1e-6)
    assert np.isclose(lb, 2.0 - 1.645 * (1.0 / np.sqrt(3)), atol=1e-6)
    assert lb < mean


def test_fast_lower_bound_thin_is_nan():
    frame = pd.DataFrame({"net": [1.0], "test_month": ["2024-01"]})
    lb, mean, se = cas.fast_lower_bound(frame)
    assert np.isnan(lb) and np.isnan(mean) and np.isnan(se)


def test_scorer_runs_and_rejects_noncausal():
    sc = cas.CostAwarePerSymbolScorer({"validation": _split()}, "EURUSD")
    val, mean, se, _ = sc.score("def signal(ctx):\n    return ctx.col('vel_pips_h1')\n", "validation")
    assert np.isfinite(val)
    fwd = ("def signal(ctx):\n    x = ctx.col('vel_pips_h1').copy()\n    x[:-1] = x[1:]\n    return x\n")
    v2, _, _, logs = sc.score(fwd, "validation")
    assert v2 == -1e6 and "causal" in logs.lower()


def test_scorer_value_is_robust_aggregate_and_posterior_from_best_cell(monkeypatch):
    # Fix per-cell (lb, mean, se) so the aggregate + posterior selection are deterministic.
    seq = iter([(0.5, 1.0, 0.3), (0.1, 0.4, 0.2)] * 50)  # plenty for all cells
    monkeypatch.setattr(cas, "fast_lower_bound", lambda frame, z=1.645: next(seq))
    sc = cas.CostAwarePerSymbolScorer({"validation": _split()}, "EURUSD")
    val, mean, se, _ = sc.score("def signal(ctx):\n    return ctx.col('vel_pips_h1')\n", "validation")
    # posterior (mean,se) must come from the max-lb cell (lb=0.5 -> mean 1.0, se 0.3)
    assert np.isclose(mean, 1.0) and np.isclose(se, 0.3)
    # value is a robust aggregate (mean-std) of the per-cell lbs -> strictly below the max lb
    assert val < 0.5
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/era_scalp/test_cost_aware_score.py -q`
Expected: FAIL (`cost_aware_score` missing).

- [ ] **Step 3: Implement cost_aware_score.py**

Create `scripts/era_scalp/cost_aware_score.py`:
```python
from __future__ import annotations

import numpy as np

from scripts.era_scalp.bayes_edge import monthly_net
from scripts.era_scalp.context import FeatureContext
from scripts.era_scalp.cost_model import realistic_cost
from scripts.era_scalp.load_splits import _pip_size
from scripts.era_scalp.sandbox import causality_probe, run_program
from scripts.era_scalp.trade_harness import evaluate_trades

GRID_Q = [0.90, 0.95, 0.99]
GRID_H = [100, 200, 400]


def fast_lower_bound(net_frame, z: float = 1.645):
    """Analytic one-sided lower bound on the monthly mean net. Returns (lb, mean, se)."""
    mn = monthly_net(net_frame)
    if len(mn) < 2:
        return float("nan"), float("nan"), float("nan")
    m = mn["mean_net"].to_numpy(float)
    mean = float(m.mean())
    se = float(m.std(ddof=1) / np.sqrt(len(m)))
    return mean - z * se, mean, se


class CostAwarePerSymbolScorer:
    """Per-symbol, net-of-realistic-cost, robustness-gated, confidence-aware program scorer.

    score() -> (value, mean, se, logs): value = robust aggregate (mean-std) of per-(q,h) lower bounds;
    (mean, se) = posterior of the max-lb cell, exposed for Thompson node selection."""

    def __init__(self, split_by_phase: dict, symbol: str, z: float = 1.645, timeout: float = 10.0):
        self.splits = split_by_phase
        self.symbol = symbol
        self.pip = _pip_size(symbol)
        self.z = z
        self.timeout = timeout

    def score(self, src: str, phase: str = "validation"):
        d = self.splits[phase]
        ctx = FeatureContext(X=d.X, names=d.names, hour=d.hour)
        sig, err, logs = run_program(src, ctx, timeout=self.timeout, required_fn="signal")
        if err is not None:
            return -1e6, float("nan"), float("nan"), f"exec: {err}\n{logs}"
        ok, reason = causality_probe(src, ctx, sig, required_fn="signal")
        if not ok:
            return -1e6, float("nan"), float("nan"), f"causality_probe: {reason}"
        cost = realistic_cost(d.spread_pips)
        lbs, best = [], None
        for q in GRID_Q:
            for h in GRID_H:
                frame = evaluate_trades(sig, d.mid, cost, d.test_month, self.pip, q, h)
                lb, mean, se = fast_lower_bound(frame, z=self.z)
                if not np.isfinite(lb):
                    continue
                lbs.append(lb)
                if best is None or lb > best[0]:
                    best = (lb, mean, se)
        if not lbs:
            return -1e6, float("nan"), float("nan"), "no admissible (q,h) cell"
        arr = np.asarray(lbs, float)
        value = float(arr.mean() - arr.std())
        return value, best[1], best[2], logs
```

- [ ] **Step 4: Run tests + lint**

Run: `uv run pytest tests/era_scalp/test_cost_aware_score.py -q` (PASS)
Run: `make lint` (All checks passed!)

- [ ] **Step 5: Commit**
```bash
git add scripts/era_scalp/cost_aware_score.py tests/era_scalp/test_cost_aware_score.py
git commit -m "feat(era-scalp): cost-aware per-symbol scorer (robust lower-bound + edge posterior)

fast_lower_bound = analytic one-sided LB on monthly net; CostAwarePerSymbolScorer scores a program on
net-of-realistic-cost across the (q,h) grid, value = mean-std of per-cell LBs (knife-edge-resistant),
and exposes (mean,se) of the best cell as the node edge posterior for Thompson selection."
```

---

### Task 3: Engine — `Node.mean/se`, `select_thompson`, `puct_search(select_fn=)`

**Files:** Modify `scripts/era/puct.py`; Create `tests/era_scalp/test_puct_thompson.py`

- [ ] **Step 1: Failing tests**

Create `tests/era_scalp/test_puct_thompson.py`:
```python
import numpy as np

from scripts.era.puct import Node, puct_search, select, select_thompson


def _node(mean, se):
    return Node(payload="x", score=mean, parent=None, mean=mean, se=se)


def test_thompson_favours_dominant_node():
    rng = np.random.default_rng(0)
    nodes = [_node(2.0, 0.1), _node(0.0, 0.1), _node(-1.0, 0.1)]
    picks = [select_thompson(nodes, rng) is nodes[0] for _ in range(200)]
    assert sum(picks) > 180  # clear winner dominates


def test_thompson_sometimes_explores_uncertain_underdog():
    rng = np.random.default_rng(0)
    nodes = [_node(1.0, 0.05), _node(0.5, 3.0)]  # underdog has high uncertainty
    picks = [select_thompson(nodes, rng) is nodes[1] for _ in range(200)]
    assert 0 < sum(picks) < 200  # explored sometimes, not always


def test_thompson_zero_se_uses_mean():
    rng = np.random.default_rng(1)
    nodes = [_node(1.0, 0.0), _node(2.0, 0.0)]
    assert all(select_thompson(nodes, rng) is nodes[1] for _ in range(20))


def test_puct_search_accepts_select_fn():
    root = Node(payload=0, score=0.0, parent=None, mean=0.0, se=1.0)
    def expand(parent):
        return Node(payload=1, score=1.0, parent=parent, mean=1.0, se=1.0)
    rng = np.random.default_rng(2)
    nodes = puct_search([root], expand, budget=5,
                        select_fn=lambda ns, c: select_thompson(ns, rng))
    assert len(nodes) == 6  # root + 5 expansions
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/era_scalp/test_puct_thompson.py -q`
Expected: FAIL (`select_thompson` missing; `Node` has no `mean`/`se`; `puct_search` has no `select_fn`).

- [ ] **Step 3: Implement engine additions**

In `scripts/era/puct.py`:
1. Add fields to `Node` (after `children`):
```python
    mean: float = 0.0
    se: float = 0.0
```
2. Add `select_thompson` after `select`:
```python
def select_thompson(nodes: list[Node], rng) -> Node:
    """Thompson sampling: draw from each node's edge posterior N(mean, se), pick the argmax draw."""
    best_i, best_draw = 0, -1e18
    for i, nd in enumerate(nodes):
        draw = nd.mean if nd.se <= 0 else float(rng.normal(nd.mean, nd.se))
        if draw > best_draw:
            best_draw, best_i = draw, i
    return nodes[best_i]
```
3. Change `puct_search` signature + selection call to accept `select_fn`:
```python
def puct_search(
    initial_nodes: list[Node], expand_fn, budget: int, c_puct: float = 1.0, seed: int = 0,
    select_fn=None,
) -> list[Node]:
    np.random.seed(seed)
    nodes = list(initial_nodes)
    chooser = select_fn if select_fn is not None else (lambda ns: select(ns, c_puct))
    for _ in range(budget):
        parent = chooser(nodes)
        child = expand_fn(parent)
        parent.children.append(child)
        nodes.append(child)
        a = child.parent
        while a is not None:
            a.visits += 1
            a = a.parent
    return nodes
```
(NOTE: `select_fn` here takes ONE arg `nodes`. The test passes `lambda ns, c: ...` — adjust: make the default chooser `lambda ns: select(ns, c_puct)` and require `select_fn` to be a 1-arg callable `f(nodes)`. Update the test's lambda to one arg if needed — but the provided test uses `select_fn=lambda ns, c: ...` which is 2-arg; RECONCILE by making `puct_search` call `select_fn(nodes, c_puct)` when given, and the default `select`. So: `chooser = select_fn or select; parent = chooser(nodes, c_puct)`. Then `select_thompson` must accept `(nodes, c_puct=None, rng=...)` — simpler: keep `select_thompson(nodes, rng)` and have the test wrap it. To avoid ambiguity, IMPLEMENT puct_search to call `select_fn(nodes, c_puct)` and DEFAULT to `select`; the test's `select_fn=lambda ns, c: select_thompson(ns, rng)` matches that 2-arg shape. Use THIS form.)

Final `puct_search` (use this exact form to match the test):
```python
def puct_search(
    initial_nodes: list[Node], expand_fn, budget: int, c_puct: float = 1.0, seed: int = 0,
    select_fn=None,
) -> list[Node]:
    np.random.seed(seed)
    nodes = list(initial_nodes)
    chooser = select_fn if select_fn is not None else select
    for _ in range(budget):
        parent = chooser(nodes, c_puct)
        child = expand_fn(parent)
        parent.children.append(child)
        nodes.append(child)
        a = child.parent
        while a is not None:
            a.visits += 1
            a = a.parent
    return nodes
```

- [ ] **Step 4: Run tests + full era suites + lint**

Run: `uv run pytest tests/era_scalp/test_puct_thompson.py -q` (PASS)
Run: `uv run pytest tests/era tests/era_scalp -q` (PASS — existing `puct` callers still work: default `select_fn=None` → `select`)
Run: `make lint` (All checks passed!)

- [ ] **Step 5: Commit**
```bash
git add scripts/era/puct.py tests/era_scalp/test_puct_thompson.py
git commit -m "feat(era): Thompson selection + pluggable select_fn for PUCT

Node carries an optional edge posterior (mean, se); select_thompson samples each node's posterior and
picks the argmax draw; puct_search gains select_fn (default = existing rank-based select). Backward
compatible — existing callers unaffected."
```

---

### Task 4: EUR driver + CLI

**Files:** Create `scripts/era_scalp/run_era_eur.py`; Create `tests/era_scalp/test_run_era_eur.py`

- [ ] **Step 1: Failing smoke test (stubbed qwen + scorer)**

Create `tests/era_scalp/test_run_era_eur.py`:
```python
import numpy as np

from scripts.era_scalp.load_splits import WHITELIST, TradeSplitData
from scripts.era_scalp import run_era_eur as R


def _split(n=1500, seed=0):
    rng = np.random.default_rng(seed)
    mid = 1.10 + np.cumsum(rng.standard_normal(n)) * 1e-4
    months = ([f"2024-{m:02d}" for m in range(1, 13)] * (n // 12 + 1))[:n]
    return TradeSplitData(
        X=rng.standard_normal((n, len(WHITELIST))), names=list(WHITELIST),
        hour=(np.arange(n) % 24).astype(float), mid=mid, cost=np.full(n, 0.4),
        test_month=np.array(months), spread_pips=np.full(n, 0.4),
    )


def test_run_search_builds_forest_with_thompson(monkeypatch):
    # stub qwen writer/recombiner so no network; expansions return a trivial program
    prog = "def signal(ctx):\n    return ctx.col('vel_pips_h1')\n"
    monkeypatch.setattr(R, "propose_program",
                        lambda *a, **k: prog)
    monkeypatch.setattr(R, "recombine_program", lambda *a, **k: prog)
    splits = {"validation": _split(seed=1), "holdout": _split(seed=2)}
    nodes = R.run_search(splits, "EURUSD", budget=4, select_policy="thompson",
                         seed_programs={"fair_fade": prog}, seed=0)
    assert len(nodes) == 1 + 4  # one seed + 4 expansions
    assert all(np.isfinite(n.score) or n.score == -1e6 for n in nodes)
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/era_scalp/test_run_era_eur.py -q`
Expected: FAIL (`run_era_eur` missing).

- [ ] **Step 3: Implement run_era_eur.py**

Create `scripts/era_scalp/run_era_eur.py`:
```python
from __future__ import annotations

import argparse
import random
from pathlib import Path

import numpy as np

from scripts.era.llm import propose_program, recombine_program
from scripts.era.puct import Node, puct_search, select_thompson
from scripts.era_scalp.bayes_edge import edge_verdict
from scripts.era_scalp.context import FeatureContext
from scripts.era_scalp.cost_aware_score import GRID_H, GRID_Q, CostAwarePerSymbolScorer
from scripts.era_scalp.cost_model import realistic_cost
from scripts.era_scalp.fade_seeds import FADE_SEED_PROGRAMS, RESEARCH_IDEAS
from scripts.era_scalp.load_splits import _pip_size, build_trade_splits
from scripts.era_scalp.sandbox import run_program
from scripts.era_scalp.trade_harness import evaluate_trades

SYMBOL_DEFAULT = "EURUSD"
TRIVIAL_ROOT = "def signal(ctx):\n    return ctx.col('vel_pips_h1') * 0.0 + ctx.col('vel_pips_h1')\n"
FADE_RULES = (
    "You write `signal(ctx) -> np.ndarray`, one per-bar real value; sign = trade side, |value| ranks "
    "entries. ctx.col(name) gives causal columns; np available; no imports; never read future rows "
    "(a causality probe rejects it). Output ONE ```python block.\n"
)


def run_search(splits, symbol, budget, select_policy="thompson", seed=0,
               cache_dir="/tmp/era_eur_cache", p_recombine=0.3, seed_programs=None):
    scorer = CostAwarePerSymbolScorer(splits, symbol)
    rng = random.Random(seed)
    nprng = np.random.default_rng(seed)
    if seed_programs is None:
        seed_programs = FADE_SEED_PROGRAMS
    forest = []
    for src in seed_programs.values():
        v, mean, se, lg = scorer.score(src, "validation")
        forest.append(Node(payload=src, score=v, parent=None, logs=lg, mean=mean, se=se))
    all_nodes = list(forest)

    def expand(parent: Node) -> Node:
        if rng.random() < p_recombine and len(all_nodes) >= 2:
            cands = sorted(all_nodes, key=lambda n: n.score, reverse=True)
            child_src = recombine_program(cands[0].payload, cands[0].score, cands[1].payload,
                                          cands[1].score, cache_dir=cache_dir, rules=FADE_RULES)
        else:
            child_src = propose_program(parent.payload, parent.score, parent.logs,
                                        rng.choice(RESEARCH_IDEAS), cache_dir=cache_dir, rules=FADE_RULES)
        v, mean, se, lg = scorer.score(child_src, "validation")
        child = Node(payload=child_src, score=v, parent=parent, logs=lg, mean=mean, se=se)
        all_nodes.append(child)
        return child

    if select_policy == "thompson":
        select_fn = lambda ns, c: select_thompson(ns, nprng)
    else:
        select_fn = None  # default rank-based select
    return puct_search(forest, expand, budget=budget, c_puct=1.0, seed=seed, select_fn=select_fn)


def holdout_verdict(src, split_holdout, symbol):
    """Net-of-realistic-cost EUR holdout posterior at the best-by-(q,h) cell. None on program error."""
    d = split_holdout
    ctx = FeatureContext(X=d.X, names=d.names, hour=d.hour)
    sig, err, _ = run_program(src, ctx, required_fn="signal")
    if err is not None:
        return None
    cost = realistic_cost(d.spread_pips)
    pip = _pip_size(symbol)
    best = None
    for q in GRID_Q:
        for h in GRID_H:
            frame = evaluate_trades(sig, d.mid, cost, d.test_month, pip, q, h)
            if len(frame) < 50:
                continue
            try:
                post = edge_verdict({symbol: frame})
            except ValueError:
                continue
            p = post.pooled["p_positive"]
            if best is None or p > best["p_positive"]:
                best = {**post.pooled, "q": q, "h": h, "n_trades": int(len(frame)),
                        "raw_mean": float(frame["net"].mean())}
    return best


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbol", default=SYMBOL_DEFAULT)
    ap.add_argument("--tv-dir", default="data/analysis/tick_velocity")
    ap.add_argument("--budget", type=int, default=40)
    ap.add_argument("--policy", default="thompson", choices=["thompson", "rank"])
    ap.add_argument("--no-seeds", action="store_true", help="rediscovery control")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--out", default="/tmp/era_eur/verdict.md")
    args = ap.parse_args()
    sp = build_trade_splits(args.symbol, Path(args.tv_dir) / f"{args.symbol}_100tick_velocity.parquet",
                            embargo=max(GRID_H))
    seed_programs = {"_root": TRIVIAL_ROOT} if args.no_seeds else None
    nodes = run_search(sp, args.symbol, budget=args.budget, select_policy=args.policy,
                       seed=args.seed, seed_programs=seed_programs)
    ranked = sorted([n for n in nodes if n.score > -1e6 + 1], key=lambda n: n.score, reverse=True)
    lines = [f"# Cost-aware PUCT verdict — {args.symbol} (policy={args.policy}, "
             f"seeds={'no' if args.no_seeds else 'yes'}, budget={args.budget})\n"]
    for nd in ranked[:5]:
        hv = holdout_verdict(nd.payload, sp["holdout"], args.symbol)
        tag = "SEED" if nd.parent is None else "evolved"
        if hv:
            lines.append(f"- [{tag}] val={nd.score:+.3f} | holdout P={hv['p_positive']:.3f} "
                         f"raw={hv['raw_mean']:+.3f} (q{hv['q']} h{hv['h']} n={hv['n_trades']})")
        else:
            lines.append(f"- [{tag}] val={nd.score:+.3f} | holdout: program error")
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text("\n".join(lines) + "\n")
    print(f"wrote {args.out}")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run tests + lint**

Run: `uv run pytest tests/era_scalp/test_run_era_eur.py -q` (PASS — stubbed, no network)
Run: `uv run pytest tests/era_scalp -q` (PASS)
Run: `make lint` (All checks passed!)

- [ ] **Step 5: Commit**
```bash
git add scripts/era_scalp/run_era_eur.py tests/era_scalp/test_run_era_eur.py
git commit -m "feat(era-scalp): EUR cost-aware PUCT driver (Thompson/rank, seeds/rediscovery)

run_search scores the EUR forest with CostAwarePerSymbolScorer (sets node edge posterior), expands via
qwen propose/recombine, selects by Thompson or rank; holdout_verdict reports net-of-realistic-cost EUR
posterior. CLI A/Bs policy and seeds-vs-rediscovery."
```

---

### Task 5: Run the search + evidence doc

**Files:** Create `docs/analysis/era_cost_aware_puct_eur_2026-06-01.md`. Numbers from REAL runs — do not invent.

- [ ] **Step 1: Baseline — score the seeds' net-of-realistic-cost EUR holdout (the bar to beat)**

Run (records the best SEED, no qwen):
```bash
uv run python -m scripts.era_scalp.run_era_eur --symbol EURUSD --budget 0 --policy rank --out /tmp/era_eur/seeds_only.md
```
(budget=0 → forest = seeds only; the verdict lists each seed's net-of-realistic-cost holdout P + raw.) Read it. This is the must-beat bar AND answers the binding question: does EUR fade survive realistic cost at all?

- [ ] **Step 2: Search runs — A/B policy, with seeds**

```bash
uv run python -m scripts.era_scalp.run_era_eur --symbol EURUSD --budget 40 --policy thompson --out /tmp/era_eur/thompson.md
uv run python -m scripts.era_scalp.run_era_eur --symbol EURUSD --budget 40 --policy rank     --out /tmp/era_eur/rank.md
```
(qwen calls are slow; if a run stalls, the timeout-safe caller skips failed expansions. Re-run if needed.)

- [ ] **Step 3: Rediscovery control (no seeds)**

```bash
uv run python -m scripts.era_scalp.run_era_eur --symbol EURUSD --budget 40 --policy thompson --no-seeds --out /tmp/era_eur/rediscovery.md
```

- [ ] **Step 4: Write the evidence doc**

Create `docs/analysis/era_cost_aware_puct_eur_2026-06-01.md` from the REAL outputs:
```markdown
# ERA cost-aware PUCT — EURUSD net-of-realistic-cost (2026-06-01)

In-loop objective: net of realistic round-trip cost (spread_pips + 0.06 commission + 0.10 slippage),
robustness-gated fast lower bound across (q,h). Search = qwen program evolution under PUCT; selection
A/B Thompson vs rank; rediscovery control (no seeds). Final = EUR holdout bayes_edge on net-of-cost.

## Does the EUR fade edge survive realistic cost? (seeds-only baseline)
<paste seeds_only.md — the best seed's net-of-realistic-cost holdout P + raw. THIS is the headline: if
the best seed's net-of-cost raw <= 0 or P low, the EUR edge does NOT survive realistic cost.>

## Did search beat the best seed?
| run | best holdout P(edge>0) | raw net-of-cost | evolved or seed? |
|---|---|---|---|
| seeds-only | <fill> | <fill> | seed |
| thompson (seeds) | <fill> | <fill> | <fill> |
| rank (seeds) | <fill> | <fill> | <fill> |
| rediscovery (no seeds) | <fill> | <fill> | evolved |

## Verdict
<State plainly: (a) does EUR fade survive realistic cost (seed baseline net-of-cost)? (b) did any
evolved program credibly beat the best seed? (c) did thompson reach a better best node than rank at
equal budget? Honest nulls expected and fine: "qwen beat no seed" / "thompson == rank" / "edge dies at
cost". This is the first head-to-head of search-policy and the first cost-real EUR number.>

## Caveat
Realistic PARAMETRIC cost. Tick-exact certification (analyze_oco_stop_limit_tickfill, root checkout +
broker creds) is the final gate on any survivor — out of scope here.
```

- [ ] **Step 5: Commit + push**
```bash
git add docs/analysis/era_cost_aware_puct_eur_2026-06-01.md
git commit -m "docs(era-scalp): cost-aware PUCT EUR verdict — net-of-realistic-cost, policy A/B, rediscovery"
git push
```

---

## Self-Review

**1. Spec coverage:** realistic cost model + spread_pips (T1); fast_lower_bound + robust cost-aware scorer w/ node posterior (T2); Node.mean/se + select_thompson + puct_search select_fn (T3); EUR driver w/ policy A/B + seeds/rediscovery + net-of-cost holdout verdict (T4); seeds baseline (must-beat + does-edge-survive-cost) + A/B runs + rediscovery + evidence (T5). All spec sections mapped. ✓

**2. Placeholder scan:** Only `<fill>`/`<paste ...>` in Task 5's evidence template (filled from real runs). All code blocks complete. The Task 3 step contains a deliberate reconciliation NOTE that resolves to one exact final `puct_search` form (the second code block) — the implementer uses that final form; the test's `select_fn=lambda ns, c: ...` is 2-arg to match `chooser(nodes, c_puct)`.

**3. Type consistency:** `CostAwarePerSymbolScorer.score -> (value, mean, se, logs)` (4-tuple) consumed consistently in `run_search` (sets `Node.mean/se`). `fast_lower_bound -> (lb, mean, se)`. `Node(payload, score, parent, visits, logs, children, mean, se)`. `puct_search(..., select_fn)` called with `select_fn(nodes, c_puct)`; `select_thompson(nodes, rng)` wrapped by the driver's `lambda ns, c: select_thompson(ns, nprng)`. `realistic_cost(spread_pips)`, `TradeSplitData.spread_pips`, `GRID_Q/GRID_H` from cost_aware_score, `edge_verdict({symbol: frame}).pooled`. `build_trade_splits(..., embargo=max(GRID_H))`. Consistent.
```
