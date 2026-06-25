# Signed-Return Regression Model + Purged CV Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a signed-return regression model ladder (Ridge → Ridge+interactions → HistGBM → bagged-HistGBM) tuned with de Prado PurgedKFold + return-attribution weights, and gate it on walk-forward non-overlap net-bps vs the fixed base.

**Architecture:** Five primitives compose the pipeline. `purged_kfold.py` adds the AFML PurgedKFold splitter + an IC/edge CV scorer. `sample_weights.py` gains an explicit-start concurrency so return-attribution weights work on a sampled event set. `model_search.py` builds the design matrix (features + interaction terms) and the model ladder. `pnl_walkforward.py` gains a model-µ-driven OOS evaluator (fit-per-fold, `sign(µ)` side, top-decile `|µ|` selection). A driver compares the ladder on CV and on walk-forward net-bps.

**Tech Stack:** Python, numpy, pandas, scipy.stats, scikit-learn (`Ridge`, `HistGradientBoostingRegressor`). Reuses `feature_ic_definitive.build_all`, `triple_barrier.triple_barrier_core`, `sample_weights`, `pnl_walkforward.greedy_nonoverlap`. Tests via pytest from repo root, imported as `from scripts.fx_coint.X import Y`.

## Global Constraints

- New code in `scripts/fx_coint/`; tests in `tests/fx_coint/` named `test_*.py`; reports in `reports/model_search/`.
- Modules follow existing convention: pure functions + a thin `main()`; intra-package imports via `sys.path.insert(0, parent)` + bare module names.
- **Regression**, target = signed first-touch return in bps; predicted µ → `sign(µ)` side + `|µ|` conviction. No classification.
- Fixed base strategy: fade `ffd_zvol20` × top-decile `|ffd_zvol20|`; triple-barrier barriers `1.0 * vol * sqrt(N)`; pooled 5 ex-JPY majors `["AUDUSD","EURUSD","GBPUSD","USDCAD","USDCHF"]`; cost 1.0 bps; **N=50 primary, N=30 robustness**.
- Sample weight = return-attribution (`sample_weights.return_attribution_weights`, uniqueness × |return|). Time-decay off.
- PurgedKFold for tuning/CV-scoring (data-efficient); walk-forward non-overlap for the final P&L gate (live-like). Two tools, two jobs.
- A model wins only if it beats BOTH Ridge and the fixed base on walk-forward net-bps, robustly across folds and symbols.
- `build_all(sym) -> (logp, f, vol, bph)`; events `ev` (entry `ev+1`, `vert=min(entry+N, n-1)`); `triple_barrier_core(logp, entry, vert, width) -> (t1, ret, hold, touched)`.
- `run make quality` before any PR.

---

### Task 1: PurgedKFold splitter

**Files:**
- Create: `scripts/fx_coint/purged_kfold.py`
- Test: `tests/fx_coint/test_purged_kfold.py`

**Interfaces:**
- Consumes: nothing (first task).
- Produces:
  - `class PurgedKFold(n_splits=5, embargo_pct=0.01)` with `split(entry, t1) -> iterator of (train_idx, test_idx)`. `entry`/`t1` are integer bar-index arrays for time-sorted events (`entry[i]` = entry bar, `t1[i]` = first-touch/label-end bar). Test folds are contiguous event blocks; train purges any event whose label interval `[entry, t1]` overlaps the test bar interval, plus an embargo of `embargo_pct * n_bars` bars after the test interval. `n_bars = t1.max() + 1`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/fx_coint/test_purged_kfold.py
import numpy as np

from scripts.fx_coint.purged_kfold import PurgedKFold


def test_purged_kfold_no_train_label_overlaps_test_interval():
    n = 500
    entry = np.arange(n) * 2            # entries at bars 0,2,4,...
    t1 = entry + 5                       # each label spans 5 bars
    pk = PurgedKFold(n_splits=5, embargo_pct=0.0)
    for tr, te in pk.split(entry, t1):
        t_lo, t_hi = entry[te].min(), t1[te].max()
        # no train label interval may intersect [t_lo, t_hi]
        overlap = (entry[tr] <= t_hi) & (t1[tr] >= t_lo)
        assert not overlap.any()


def test_purged_kfold_embargo_drops_post_test_rows():
    n = 500
    entry = np.arange(n)
    t1 = entry + 1
    no_emb = PurgedKFold(n_splits=5, embargo_pct=0.0)
    emb = PurgedKFold(n_splits=5, embargo_pct=0.05)
    # embargo can only REMOVE train rows -> train sets are subsets / smaller
    for (tr0, te0), (tr1, te1) in zip(no_emb.split(entry, t1), emb.split(entry, t1)):
        assert np.array_equal(te0, te1)
        assert len(tr1) <= len(tr0)
    # at least one fold actually loses rows to the embargo
    sizes0 = [len(tr) for tr, _ in no_emb.split(entry, t1)]
    sizes1 = [len(tr) for tr, _ in emb.split(entry, t1)]
    assert any(s1 < s0 for s0, s1 in zip(sizes0, sizes1))


def test_purged_kfold_covers_all_events_as_test_once():
    n = 300
    entry = np.arange(n)
    t1 = entry + 3
    pk = PurgedKFold(n_splits=6, embargo_pct=0.0)
    seen = np.concatenate([te for _, te in pk.split(entry, t1)])
    assert np.array_equal(np.sort(seen), np.arange(n))
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/fx_coint/test_purged_kfold.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Write minimal implementation**

```python
# scripts/fx_coint/purged_kfold.py
"""Purged K-Fold cross-validation (Lopez de Prado AFML ch.7) for overlapping labels.

Test folds are contiguous blocks of (time-sorted) events. Train observations whose
label interval [entry, t1] overlaps a test fold's bar interval are PURGED, and an
EMBARGO drops train observations starting just after the test interval. This is the
data-efficient CV for model tuning; the final P&L gate stays walk-forward (live-like).

Self-test: `uv run python scripts/fx_coint/purged_kfold.py`
"""
from __future__ import annotations

import numpy as np


class PurgedKFold:
    def __init__(self, n_splits: int = 5, embargo_pct: float = 0.01):
        self.n_splits = n_splits
        self.embargo_pct = embargo_pct

    def split(self, entry: np.ndarray, t1: np.ndarray):
        entry = np.asarray(entry)
        t1 = np.asarray(t1)
        n = len(entry)
        n_bars = int(t1.max()) + 1
        embargo = int(n_bars * self.embargo_pct)
        idx = np.arange(n)
        bounds = np.linspace(0, n, self.n_splits + 1, dtype=int)
        for k in range(self.n_splits):
            te = idx[bounds[k]:bounds[k + 1]]
            if len(te) == 0:
                continue
            t_lo = entry[te].min()
            t_hi = t1[te].max()
            # purge: drop train whose [entry, t1] intersects [t_lo, t_hi]
            overlap = (entry <= t_hi) & (t1 >= t_lo)
            # embargo: drop train starting within `embargo` bars after t_hi
            embargoed = (entry > t_hi) & (entry <= t_hi + embargo)
            train_mask = ~overlap & ~embargoed
            train_mask[te] = False
            yield idx[train_mask], te


def _self_test() -> None:
    entry = np.arange(100)
    t1 = entry + 3
    pk = PurgedKFold(n_splits=5, embargo_pct=0.02)
    for tr, te in pk.split(entry, t1):
        print("train", len(tr), "test", len(te))


if __name__ == "__main__":
    _self_test()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/fx_coint/test_purged_kfold.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add scripts/fx_coint/purged_kfold.py tests/fx_coint/test_purged_kfold.py
git commit -m "feat(fx_coint): PurgedKFold splitter (AFML ch.7, integer t1)"
```

---

### Task 2: Purged CV score + IC scorer

**Files:**
- Modify: `scripts/fx_coint/purged_kfold.py`
- Test: `tests/fx_coint/test_purged_kfold.py` (add tests)

**Interfaces:**
- Consumes: `PurgedKFold` (Task 1).
- Produces:
  - `ic_scorer(y_true: np.ndarray, y_pred: np.ndarray) -> float` — Spearman IC, NaN-safe (returns 0.0 if degenerate).
  - `purged_cv_score(estimator, X, y, entry, t1, sample_weight=None, n_splits=5, embargo_pct=0.01) -> np.ndarray` — clones+fits the estimator on each purged train fold (passing `sample_weight` if given), scores `ic_scorer` on the test fold, returns the per-fold score array. NaN rows in `X`/`y` dropped per fold.

- [ ] **Step 1: Write the failing tests**

```python
# append to tests/fx_coint/test_purged_kfold.py
from sklearn.linear_model import Ridge

from scripts.fx_coint.purged_kfold import ic_scorer, purged_cv_score


def test_ic_scorer_basic():
    y = np.arange(100.0)
    assert ic_scorer(y, y) > 0.99
    assert abs(ic_scorer(y, np.random.default_rng(0).standard_normal(100))) < 0.3


def test_purged_cv_score_recovers_linear_signal():
    rng = np.random.default_rng(0)
    n = 2000
    X = rng.standard_normal((n, 3))
    y = X[:, 0] * 1.5 + 0.3 * rng.standard_normal(n)
    entry = np.arange(n)
    t1 = entry + 2
    scores = purged_cv_score(Ridge(alpha=1.0), X, y, entry, t1, n_splits=5)
    assert np.nanmean(scores) > 0.5
    assert len(scores) == 5
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/fx_coint/test_purged_kfold.py -k "ic_scorer or cv_score" -v`
Expected: FAIL with `ImportError`.

- [ ] **Step 3: Write minimal implementation**

```python
# add to scripts/fx_coint/purged_kfold.py
from scipy import stats  # top of file
from sklearn.base import clone  # top of file


def ic_scorer(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    yt = np.asarray(y_true, dtype=float)
    yp = np.asarray(y_pred, dtype=float)
    ok = np.isfinite(yt) & np.isfinite(yp)
    if ok.sum() < 10 or np.unique(yp[ok]).size < 3:
        return 0.0
    r = stats.spearmanr(yt[ok], yp[ok])[0]
    return float(r) if np.isfinite(r) else 0.0


def purged_cv_score(estimator, X, y, entry, t1, sample_weight=None,
                    n_splits=5, embargo_pct=0.01) -> np.ndarray:
    X = np.asarray(X, dtype=float)
    y = np.asarray(y, dtype=float)
    pk = PurgedKFold(n_splits=n_splits, embargo_pct=embargo_pct)
    scores = []
    for tr, te in pk.split(entry, t1):
        okt = np.isfinite(X[tr]).all(1) & np.isfinite(y[tr])
        oke = np.isfinite(X[te]).all(1) & np.isfinite(y[te])
        if okt.sum() < 50 or oke.sum() < 20:
            continue
        est = clone(estimator)
        if sample_weight is not None:
            est.fit(X[tr][okt], y[tr][okt], sample_weight=np.asarray(sample_weight)[tr][okt])
        else:
            est.fit(X[tr][okt], y[tr][okt])
        scores.append(ic_scorer(y[te][oke], est.predict(X[te][oke])))
    return np.array(scores) if scores else np.array([np.nan])
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/fx_coint/test_purged_kfold.py -v`
Expected: PASS (all purged_kfold tests).

- [ ] **Step 5: Commit**

```bash
git add scripts/fx_coint/purged_kfold.py tests/fx_coint/test_purged_kfold.py
git commit -m "feat(fx_coint): purged CV score + IC scorer"
```

---

### Task 3: Explicit-start concurrency + event weights

**Files:**
- Modify: `scripts/fx_coint/sample_weights.py`
- Test: `tests/fx_coint/test_sample_weights_spans.py`

**Interfaces:**
- Consumes: existing `sample_weights.return_attribution_weights(log_ret, start, end_idx, co, normalize=True)`.
- Produces:
  - `concurrency_spans(n: int, start: np.ndarray, end_idx: np.ndarray) -> np.ndarray` — like `concurrency` but with EXPLICIT per-label start bars (existing `concurrency` hardcodes one-label-per-bar; a sampled event set needs explicit starts). `co[t] = #labels whose [start_i, end_i] covers bar t`, floored at 1.
  - `event_weights(bar_log_ret: np.ndarray, entry: np.ndarray, t1: np.ndarray) -> np.ndarray` — return-attribution weights for a sampled event set: `co = concurrency_spans(len(bar_log_ret), entry, t1)`, then `return_attribution_weights(bar_log_ret, entry, t1, co)`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/fx_coint/test_sample_weights_spans.py
import numpy as np

from scripts.fx_coint.sample_weights import concurrency_spans, event_weights


def test_concurrency_spans_counts_overlap():
    # two labels: [0,4] and [2,6] over a 10-bar timeline
    co = concurrency_spans(10, np.array([0, 2]), np.array([4, 6]))
    assert co[0] == 1            # only label 0
    assert co[3] == 2            # both overlap at bar 3
    assert co[5] == 1            # only label 1
    assert (co >= 1).all()       # floored at 1


def test_event_weights_higher_for_bigger_isolated_move():
    n = 200
    r = np.zeros(n)
    r[50] = 0.01                 # a big return inside event A's span only
    entry = np.array([48, 120])
    t1 = np.array([55, 130])     # event A spans the big bar; event B is flat
    w = event_weights(r, entry, t1)
    assert w[0] > w[1]           # A captured the move -> higher weight
    assert np.all(w >= 0)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/fx_coint/test_sample_weights_spans.py -v`
Expected: FAIL with `ImportError`.

- [ ] **Step 3: Write minimal implementation**

```python
# add to scripts/fx_coint/sample_weights.py
def concurrency_spans(n: int, start: np.ndarray, end_idx: np.ndarray) -> np.ndarray:
    """co[t] = #labels whose [start_i, end_i] covers bar t (explicit starts)."""
    delta = np.zeros(n + 1)
    np.add.at(delta, np.asarray(start), 1.0)
    np.add.at(delta, np.asarray(end_idx) + 1, -1.0)
    co = np.cumsum(delta[:n])
    return np.maximum(co, 1.0)


def event_weights(bar_log_ret: np.ndarray, entry: np.ndarray, t1: np.ndarray) -> np.ndarray:
    """Return-attribution sample weights for a sampled event set on the bar timeline."""
    co = concurrency_spans(len(bar_log_ret), entry, t1)
    return return_attribution_weights(bar_log_ret, np.asarray(entry), np.asarray(t1), co)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/fx_coint/test_sample_weights_spans.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add scripts/fx_coint/sample_weights.py tests/fx_coint/test_sample_weights_spans.py
git commit -m "feat(fx_coint): explicit-start concurrency + event return-attribution weights"
```

---

### Task 4: Design matrix + model ladder

**Files:**
- Create: `scripts/fx_coint/model_search.py`
- Test: `tests/fx_coint/test_model_search.py`

**Interfaces:**
- Consumes: `sample_weights.seq_bootstrap`.
- Produces:
  - `build_design(f: dict, ev: np.ndarray, feature_names: list[str], interactions: list[tuple[str, str]]) -> tuple[np.ndarray, list[str]]` — stack `f[name][ev]` columns, append per-interaction product columns `f[a][ev]*f[b][ev]`; returns `(X, names)`.
  - `make_models(seed=0) -> dict[str, object]` — `{"ridge": Ridge(alpha=10.0), "histgbm": HistGradientBoostingRegressor(...regularized...), "bagged_histgbm": _BaggedHistGBM(n_bags=10, seed=seed)}`. `_BaggedHistGBM` fits `n_bags` HistGBMs on sequential-bootstrap resamples (via `seq_bootstrap` on the fit's `entry`/`t1`, passed through `fit(X, y, sample_weight=None, entry=None, t1=None)`) and averages predictions; if `entry`/`t1` not given, falls back to uniform bootstrap.

- [ ] **Step 1: Write the failing tests**

```python
# tests/fx_coint/test_model_search.py
import numpy as np

from scripts.fx_coint.model_search import build_design, make_models


def test_build_design_adds_interaction_columns():
    f = {"a": np.array([1.0, 2.0, 3.0]), "b": np.array([10.0, 20.0, 30.0])}
    ev = np.array([0, 1, 2])
    X, names = build_design(f, ev, ["a", "b"], [("a", "b")])
    assert X.shape == (3, 3)
    assert names == ["a", "b", "a*b"]
    assert np.allclose(X[:, 2], [10.0, 40.0, 90.0])   # a*b


def test_models_fit_predict_learnable_signal():
    rng = np.random.default_rng(0)
    n = 1500
    X = rng.standard_normal((n, 3))
    y = X[:, 0] * 1.2 + 0.3 * rng.standard_normal(n)
    for name, m in make_models().items():
        m.fit(X, y)
        pred = m.predict(X)
        from scipy.stats import spearmanr
        assert spearmanr(pred, y)[0] > 0.4, name
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/fx_coint/test_model_search.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Write minimal implementation**

```python
# scripts/fx_coint/model_search.py
"""Signed-return regression model ladder + driver.

Predicts mu = expected signed first-touch return (bps); trade sign(mu), select/size
by |mu|. Ladder (each must beat the one below on walk-forward net-bps):
  ridge -> ridge+interactions (design matrix) -> histgbm -> bagged-histgbm (seq boot).
Tuned/compared with PurgedKFold + return-attribution weights; final gate = walk-forward
non-overlap net-bps vs the fixed base.

Usage: uv run python scripts/fx_coint/model_search.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.linear_model import Ridge

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sample_weights import seq_bootstrap  # noqa: E402


def build_design(f, ev, feature_names, interactions):
    cols = [f[name][ev] for name in feature_names]
    names = list(feature_names)
    for a, b in interactions:
        cols.append(f[a][ev] * f[b][ev])
        names.append(f"{a}*{b}")
    return np.column_stack(cols), names


def _histgbm(seed=0):
    return HistGradientBoostingRegressor(
        max_depth=3, max_iter=300, learning_rate=0.03, l2_regularization=5.0,
        min_samples_leaf=800, early_stopping=True, validation_fraction=0.2,
        random_state=seed)


class _BaggedHistGBM:
    def __init__(self, n_bags=10, seed=0):
        self.n_bags = n_bags
        self.seed = seed
        self.models_ = []

    def fit(self, X, y, sample_weight=None, entry=None, t1=None):
        rng = np.random.default_rng(self.seed)
        n = len(y)
        self.models_ = []
        for b in range(self.n_bags):
            if entry is not None and t1 is not None:
                draw = seq_bootstrap(np.asarray(entry), np.asarray(t1), n_draws=n,
                                     rng=np.random.default_rng(self.seed + b))
            else:
                draw = rng.integers(0, n, n)
            m = _histgbm(self.seed + b)
            sw = None if sample_weight is None else np.asarray(sample_weight)[draw]
            m.fit(X[draw], y[draw], sample_weight=sw)
            self.models_.append(m)
        return self

    def predict(self, X):
        return np.mean([m.predict(X) for m in self.models_], axis=0)


def make_models(seed=0):
    return {"ridge": Ridge(alpha=10.0),
            "histgbm": _histgbm(seed),
            "bagged_histgbm": _BaggedHistGBM(n_bags=10, seed=seed)}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/fx_coint/test_model_search.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add scripts/fx_coint/model_search.py tests/fx_coint/test_model_search.py
git commit -m "feat(fx_coint): signed-return model ladder (ridge/histgbm/bagged) + design matrix"
```

---

### Task 5: Walk-forward model-µ OOS net-bps evaluator

**Files:**
- Modify: `scripts/fx_coint/pnl_walkforward.py`
- Test: `tests/fx_coint/test_pnl_walkforward.py` (add a test)

**Interfaces:**
- Consumes: `greedy_nonoverlap` (existing).
- Produces:
  - `model_oos_pnl(sym_data, fit_predict, cost=1.0, n_folds=5) -> dict` → keys `net`, `folds_pos`, `sym_pos`, `n_trades`. `sym_data` is a dict `{symbol: {"X","y","entry","t1","ret","sw"}}` of PRE-BUILT per-event arrays (the caller builds design + weights once). Expanding walk-forward over pooled `entry`: for each fold, call `fit_predict(train_dict, test_dict) -> mu_test` (caller-supplied; fits on train, returns µ for test rows — modelling stays in the caller), then trade `sign(mu)` with top-decile `|mu|` selection (threshold from the test fold's own |mu| at 0.90), non-overlap, net of `cost`. The per-fold `train_dict`/`test_dict` are `sym_data[s]` sliced to that fold's train/test masks (same keys).

- [ ] **Step 1: Write the failing test**

```python
# append to tests/fx_coint/test_pnl_walkforward.py
from scripts.fx_coint.pnl_walkforward import model_oos_pnl


def test_model_oos_pnl_runs_and_scores_oracle():
    rng = np.random.default_rng(0)

    def fit_predict(tr, te):
        # oracle-ish: predict realized return direction with noise (fit unused)
        return te["ret"] + rng.standard_normal(len(te["ret"]))

    n = 3000
    entry = np.arange(n) * 2
    ret = rng.standard_normal(n)
    sym_data = {"S": dict(X=rng.standard_normal((n, 2)), y=ret, entry=entry,
                          t1=entry + 1, ret=ret, sw=np.abs(rng.standard_normal(n)))}
    out = model_oos_pnl(sym_data, fit_predict, cost=0.0, n_folds=4)
    assert set(out) == {"net", "folds_pos", "sym_pos", "n_trades"}
    assert out["n_trades"] > 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/fx_coint/test_pnl_walkforward.py -k model_oos -v`
Expected: FAIL with `ImportError`.

- [ ] **Step 3: Write minimal implementation**

```python
# add to scripts/fx_coint/pnl_walkforward.py
def model_oos_pnl(sym_data, fit_predict, cost=1.0, n_folds=5) -> dict:
    """Walk-forward OOS net-bps of a model-mu strategy: sign(mu) side, top-decile
    |mu| selection, non-overlap. `sym_data[s]` carries pre-built X,y,entry,t1,ret,sw;
    `fit_predict(train_dict, test_dict) -> mu_test` fits on train (modelling lives in
    the caller) and returns mu for the test rows."""
    syms = list(sym_data)
    all_entry = np.concatenate([sym_data[s]["entry"] for s in syms])
    edges = np.quantile(all_entry, np.linspace(0, 1, n_folds + 1))
    fold_net, n_trades, sym_pos = [], 0, np.zeros(len(syms))
    for k in range(1, n_folds):
        lo, hi = edges[k], edges[k + 1]
        fold = []
        for si, s in enumerate(syms):
            d = sym_data[s]
            tr = d["entry"] < lo
            te = (d["entry"] >= lo) & (d["entry"] < hi)
            if tr.sum() < 200 or te.sum() < 20:
                continue
            mu = np.asarray(fit_predict({kk: vv[tr] for kk, vv in d.items()},
                                        {kk: vv[te] for kk, vv in d.items()}), dtype=float)
            ret_te, ent_te, t1_te = d["ret"][te], d["entry"][te], d["t1"][te]
            ok = np.isfinite(mu) & np.isfinite(ret_te)
            thr = np.nanquantile(np.abs(mu[ok]), 0.90) if ok.sum() else np.inf
            sel = ok & (np.abs(mu) >= thr)
            order = np.argsort(ent_te[sel])
            keep = greedy_nonoverlap(ent_te[sel][order], t1_te[sel][order])
            pnl = np.sign(mu[sel][order][keep]) * ret_te[sel][order][keep] - cost
            if len(pnl):
                fold.append(pnl)
                n_trades += len(pnl)
                if np.mean(pnl) > 0:
                    sym_pos[si] += 1
        if fold:
            fold_net.append(np.mean(np.concatenate(fold)))
    fold_net = np.array(fold_net)
    return dict(net=float(np.mean(fold_net)) if len(fold_net) else float("nan"),
                folds_pos=int((fold_net > 0).sum()),
                sym_pos=int((sym_pos >= (n_folds - 1) / 2).sum()),
                n_trades=n_trades)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/fx_coint/test_pnl_walkforward.py -k model_oos -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/fx_coint/pnl_walkforward.py tests/fx_coint/test_pnl_walkforward.py
git commit -m "feat(fx_coint): walk-forward model-mu OOS net-bps evaluator"
```

---

### Task 6: Driver — CV comparison + walk-forward gate + report

**Files:**
- Modify: `scripts/fx_coint/model_search.py` (add `main` + helpers)
- Test: `tests/fx_coint/test_model_search.py` (add a fit_predict closure test)

**Interfaces:**
- Consumes: `build_design`, `make_models` (Task 4); `build_all` (`feature_ic_definitive`); `triple_barrier_core`; `event_weights` (`sample_weights`); `purged_cv_score` (`purged_kfold`); `model_oos_pnl` (`pnl_walkforward`).
- Produces:
  - `MODEL_SPECS` — dict mapping each ladder rung to `(estimator_name, design_key)`: `ridge→(ridge,X)`, `ridge_inter→(ridge,Xi)`, `histgbm→(histgbm,X)`, `bagged_histgbm→(bagged_histgbm,X)`. This realizes all four rungs (plain Ridge on base design vs Ridge on +interactions design vs HistGBM vs bagged).
  - `make_fit_predict(estimator_name, design_key, use_weights) -> callable` — `fit_predict(train_dict, test_dict)` closure: fits `make_models()[estimator_name]` on `tr[design_key]` (with return-attribution `sw` if `use_weights`; passing `entry`/`t1` for `bagged_histgbm`), predicts µ on `te[design_key]`.
  - `assemble_sym_data(n_tb, feature_names) -> dict` — per-symbol pre-built arrays `{symbol: {"X","Xi","y","entry","t1","ret","sw"}}`: `X` = base design (`interactions=[]`), `Xi` = `INTERACTIONS` design; via `build_all` + `triple_barrier_core` (target = first-touch `ret`) + `build_design` + `event_weights`.
  - `main()` — for N in (50, 30): `assemble_sym_data`; for each `MODEL_SPECS` rung, (a) PurgedKFold `purged_cv_score` on the rung's pooled design for CV-IC; (b) `model_oos_pnl(sym_data, fit_predict)` for the walk-forward net-bps gate; write `reports/model_search/{cv.csv, oos.csv, REPORT.md}` noting Ridge floor + base comparison.

- [ ] **Step 1: Write the failing test**

```python
# append to tests/fx_coint/test_model_search.py
from scripts.fx_coint.model_search import make_fit_predict


def test_make_fit_predict_returns_test_length_mu():
    rng = np.random.default_rng(0)
    n_tr, n_te, p = 800, 200, 4
    tr = {"X": rng.standard_normal((n_tr, p)), "y": rng.standard_normal(n_tr),
          "sw": np.abs(rng.standard_normal(n_tr)), "entry": np.arange(n_tr), "t1": np.arange(n_tr) + 1}
    te = {"X": rng.standard_normal((n_te, p)), "y": rng.standard_normal(n_te),
          "sw": np.abs(rng.standard_normal(n_te)), "entry": np.arange(n_te), "t1": np.arange(n_te) + 1}
    fp = make_fit_predict("ridge", "X", use_weights=True)
    mu = fp(tr, te)
    assert mu.shape == (n_te,)
    assert np.isfinite(mu).all()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/fx_coint/test_model_search.py -k make_fit_predict -v`
Expected: FAIL with `ImportError`.

- [ ] **Step 3: Write minimal implementation**

```python
# add to scripts/fx_coint/model_search.py (imports at top)
import pandas as pd

from feature_ic_definitive import build_all  # noqa: E402
from purged_kfold import purged_cv_score  # noqa: E402
from pnl_walkforward import model_oos_pnl  # noqa: E402
from sample_weights import event_weights  # noqa: E402
from triple_barrier import triple_barrier_core  # noqa: E402

POOL = ["AUDUSD", "EURUSD", "GBPUSD", "USDCAD", "USDCHF"]
N_EVENTS = 40000
INTERACTIONS = [("ffd_zvol20", "dev_age"), ("ffd_zvol20", "adf_sup")]
OUT_DIR = Path("reports/model_search")


# model -> (estimator name in make_models, design key in sym_data: "X"=base, "Xi"=+interactions)
MODEL_SPECS = {"ridge": ("ridge", "X"), "ridge_inter": ("ridge", "Xi"),
               "histgbm": ("histgbm", "X"), "bagged_histgbm": ("bagged_histgbm", "X")}


def make_fit_predict(estimator_name, design_key, use_weights):
    """fit_predict(train_dict, test_dict) -> mu. Fits the estimator on the chosen
    pre-built design (`design_key` = "X" base or "Xi" +interactions) with return-
    attribution sw if use_weights, predicts mu on test. Modelling only."""
    def fit_predict(tr, te):
        m = make_models()[estimator_name]
        sw = tr["sw"] if use_weights else None
        if estimator_name == "bagged_histgbm":
            m.fit(tr[design_key], tr["y"], sample_weight=sw, entry=tr["entry"], t1=tr["t1"])
        else:
            m.fit(tr[design_key], tr["y"], sample_weight=sw)
        return m.predict(te[design_key])
    return fit_predict


def assemble_sym_data(n_tb, feature_names):
    """Per-symbol pre-built event arrays: X (base design), Xi (+interactions),
    y=ret, entry, t1, ret, sw."""
    rng = np.random.default_rng(0)
    sym_data = {}
    for s in POOL:
        logp, f, vol, bph = build_all(s)
        n = len(logp)
        warm = int(96 * bph) + 60
        idx = np.arange(warm, n - n_tb - 3)
        idx = idx[np.isfinite(vol[idx + 1]) & (vol[idx + 1] > 0)]
        ev = np.sort(rng.choice(idx, min(N_EVENTS, len(idx)), replace=False))
        entry = ev + 1
        t1, ret, _, _ = triple_barrier_core(logp, entry, np.minimum(entry + n_tb, n - 1),
                                            1.0 * vol[entry] * np.sqrt(n_tb))
        X, _ = build_design(f, ev, feature_names, [])
        Xi, _ = build_design(f, ev, feature_names, INTERACTIONS)
        sw = event_weights(np.diff(logp, prepend=logp[0]), entry, t1)
        sym_data[s] = dict(X=X, Xi=Xi, y=ret, entry=entry, t1=t1, ret=ret, sw=sw)
    return sym_data


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    feats = list(build_all(POOL[0])[1])
    cv_rows, oos_rows = [], []
    for n_tb in (50, 30):
        sym_data = assemble_sym_data(n_tb, feats)
        for model, (est, dk) in MODEL_SPECS.items():
            # pooled design for PurgedKFold CV-IC
            Xc = np.vstack([sym_data[s][dk] for s in POOL])
            yc = np.concatenate([sym_data[s]["y"] for s in POOL])
            ec = np.concatenate([sym_data[s]["entry"] for s in POOL])
            tc = np.concatenate([sym_data[s]["t1"] for s in POOL])
            wc = np.concatenate([sym_data[s]["sw"] for s in POOL])
            cv = purged_cv_score(make_models()[est], Xc, yc, ec, tc, sample_weight=wc)
            cv_rows.append(dict(model=model, N=n_tb, cv_ic=float(np.nanmean(cv))))
            # walk-forward OOS net-bps gate (fit per fold on train, predict mu on test)
            fp = make_fit_predict(est, dk, use_weights=True)
            res = model_oos_pnl(sym_data, fp, cost=1.0)
            oos_rows.append(dict(model=model, N=n_tb, **res))
    cv = pd.DataFrame(cv_rows)
    oos = pd.DataFrame(oos_rows)
    cv.to_csv(OUT_DIR / "cv.csv", index=False)
    oos.to_csv(OUT_DIR / "oos.csv", index=False)
    print(cv.to_string(index=False))
    print(oos.to_string(index=False))
    (OUT_DIR / "REPORT.md").write_text(
        "# Model Search — Report\n\nLadder ridge -> histgbm -> bagged-histgbm, "
        "signed-return regression, return-attribution weights. PurgedKFold CV-IC + "
        "walk-forward non-overlap net-bps vs the fixed base (fade ffd_zvol20 x top-decile). "
        "Ridge is the floor; a model wins only if it beats Ridge AND the base on net-bps.\n\n"
        "## CV-IC (PurgedKFold)\n\n" + cv.to_markdown(index=False)
        + "\n\n## Walk-forward net-bps\n\n" + oos.to_markdown(index=False) + "\n")
    print(f"report -> {OUT_DIR / 'REPORT.md'}")
```

- [ ] **Step 4: Run test + full suite + quality**

Run: `uv run pytest tests/fx_coint/test_model_search.py tests/fx_coint/test_purged_kfold.py tests/fx_coint/test_sample_weights_spans.py tests/fx_coint/test_pnl_walkforward.py -q && make quality`
Expected: tests pass; ruff/ty clean.

- [ ] **Step 5: Run end-to-end and commit**

```bash
uv run python scripts/fx_coint/model_search.py
git add scripts/fx_coint/model_search.py scripts/fx_coint/pnl_walkforward.py tests/fx_coint/ reports/model_search/
git commit -m "feat(fx_coint): model-search driver — purged CV + walk-forward net-bps gate + report"
```

---

## Notes for the implementer

- Run from repo root so `from scripts.fx_coint.X import Y` resolves and `reports/` paths are correct.
- **Interface contract (Tasks 5↔6):** `model_oos_pnl` consumes pre-built `sym_data[s] = {X,y,entry,t1,ret,sw}` and slices each fold's train/test by the `entry` mask; the `fit_predict` closure is model-only (fit on the train slice's `X`/`y`/`sw`, predict on the test slice's `X`). The driver (`assemble_sym_data`) builds the design matrix and return-attribution weights ONCE per symbol over all that symbol's events. Note this means `sw` is computed over the full event set (its concurrency/return-attribution), then sliced to train — standard AFML usage; weights only re-emphasise training rows and never leak the target into prediction. The design matrix is per-event (no cross-row leakage). This is the deliberate, leak-safe contract — do not reintroduce per-fold weight recomputation unless a review finds drift.
- Models fit per walk-forward fold on ~hundreds–thousands of pooled events; the bagged HistGBM (10 bags × per-fold) is the slow part — the end-to-end `main` run takes several minutes. Use the regularized hyperparameters as given.
- `make quality` runs ruff + ty; watch for unused-import / E702 (no `;`), and set matplotlib `Agg` before pyplot if you add plots.
- **Monotonic constraints deferred:** the spec mentions HistGBM monotonic constraints "where a sign is believed". v1 starts UNCONSTRAINED — setting `monotonic_cst` needs a per-feature sign map over the 25-feature design that is better decided after seeing v1 OOS. Leave `_histgbm` unconstrained; a follow-up can add `monotonic_cst` for the ffd-reversion features once v1 results justify it.
- **Base comparison:** the walk-forward `oos.csv` reports each model's net-bps; **Ridge is the in-table floor**. The fixed-base number (fade `ffd_zvol20` × top-decile, ~+0.61 @N=50 / +0.34 @N=30 from `pnl_walkforward`) is the external bar to beat — reference it in `REPORT.md`; re-run `pnl_walkforward.py` if you want it recomputed alongside.
