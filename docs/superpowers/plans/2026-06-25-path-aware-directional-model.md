# Path-aware Directional Model (Stage 1) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Determine whether the W-bar *path* leading into an entry carries directional information that point-in-time features miss, at the edge-bearing horizons N=30/50, using a flattened-window model (sklearn) evaluated on the existing walk-forward harness.

**Architecture:** A new script `scripts/fx_coint/path_window_model.py` builds, per symbol, a flattened `W×C` window matrix of per-bar path channels and feeds it as the `X` in the existing `model_oos_pnl` walk-forward evaluator. The same sampled event set drives a point-in-time benchmark (the existing 30-feature design matrix) so the path-vs-point comparison is on identical events/folds. Per-symbol results are produced by calling `model_oos_pnl` with a single-symbol dict; a pooled readout uses all symbols. Verdict gates Stage 2 (torch).

**Tech Stack:** Python, numpy, scikit-learn (MLPRegressor, HistGradientBoostingRegressor, StandardScaler, Pipeline), pytest, uv.

## Global Constraints

- Run everything via `uv run` (e.g. `uv run python ...`, `uv run pytest ...`).
- numpy 2.4.2, sklearn 1.8.0 are installed; **torch is NOT installed and must NOT be added in Stage 1.**
- Horizons restricted to **N ∈ {30, 50}**. Do not add N=1,2,3.
- Per-bar path channels (length-n arrays, in this fixed order): `[log_return, vol, intra_bar_mom, hl_pos_frac]` where `log_return = np.diff(logp, prepend=logp[0])`, `vol` is the per-bar vol array, and `intra_bar_mom`/`hl_pos_frac` come from the `f` dict returned by `build_all`. C=4.
- Window sweep **W ∈ {16, 32, 64}**.
- Evaluation must reuse `pnl_walkforward.model_oos_pnl` and `pnl_walkforward.fold_block_bootstrap_ci` unchanged. Top-decile |mu| gating, non-overlap, per-symbol realistic cost from `COST_BPS`.
- Per-symbol evaluation is the primary readout; pooled is reference only.
- Follow the existing `scripts/fx_coint/` import idiom: `sys.path.insert(0, str(Path(__file__).resolve().parent))` then bare module imports with `# noqa: E402`.
- `make quality` (ty + ruff) must pass before any commit; collection errors redden the whole job.
- Commit messages end with the `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>` trailer.

---

### Task 1: Per-bar channel extraction + flattened window matrix

**Files:**
- Create: `scripts/fx_coint/path_window_model.py`
- Test: `tests/fx_coint/test_path_window_model.py`

**Interfaces:**
- Consumes: nothing (pure numpy).
- Produces:
  - `path_channels(logp, f, vol) -> list[np.ndarray]` — returns the 4 per-bar channel arrays in fixed order `[log_return, vol, intra_bar_mom, hl_pos_frac]`, each shape `(n,)`.
  - `build_window_matrix(channels, entry, W) -> np.ndarray` — returns shape `(len(entry), W*C)`. Row i is the flattened window for bars `[entry[i]-W+1 .. entry[i]]` inclusive, channel-major then time (i.e. `np.concatenate([ch[e-W+1:e+1] for ch in channels])`). Entries with `entry[i]-W+1 < 0` are invalid; the caller guarantees warmup excludes them, but the function must raise `ValueError` if any `entry[i] < W-1`.

- [ ] **Step 1: Write the failing test**

```python
# tests/fx_coint/test_path_window_model.py
import numpy as np
import pytest

from scripts.fx_coint.path_window_model import path_channels, build_window_matrix


def test_path_channels_order_and_shape():
    n = 50
    logp = np.cumsum(np.ones(n) * 0.001)
    vol = np.full(n, 0.002)
    f = {"intra_bar_mom": np.arange(n, dtype=float),
         "hl_pos_frac": np.linspace(0, 1, n)}
    chans = path_channels(logp, f, vol)
    assert len(chans) == 4
    assert all(c.shape == (n,) for c in chans)
    # channel 0 is log_return = diff(logp, prepend=logp[0]) -> first element 0
    assert chans[0][0] == 0.0
    np.testing.assert_allclose(chans[0][1:], np.diff(logp))
    np.testing.assert_array_equal(chans[2], np.arange(n, dtype=float))


def test_build_window_matrix_shape_and_content():
    n, W = 20, 4
    ch0 = np.arange(n, dtype=float)
    ch1 = np.arange(n, dtype=float) * 10
    channels = [ch0, ch1]  # C=2
    entry = np.array([5, 10])
    X = build_window_matrix(channels, entry, W)
    assert X.shape == (2, W * 2)
    # row 0: ch0[2:6]=[2,3,4,5] then ch1[2:6]=[20,30,40,50]
    np.testing.assert_array_equal(X[0], np.array([2, 3, 4, 5, 20, 30, 40, 50], dtype=float))


def test_build_window_matrix_rejects_short_entry():
    channels = [np.arange(20, dtype=float)]
    with pytest.raises(ValueError):
        build_window_matrix(channels, np.array([2]), W=4)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/fx_coint/test_path_window_model.py -v`
Expected: FAIL with `ModuleNotFoundError` / `ImportError: cannot import name 'path_channels'`.

- [ ] **Step 3: Write minimal implementation**

```python
# scripts/fx_coint/path_window_model.py
"""Path-aware directional model (Stage 1): does the W-bar path into an entry carry
directional information that point-in-time features miss, at N=30/50?

Flattens a window of per-bar path channels and feeds it as X to the existing
walk-forward harness (pnl_walkforward.model_oos_pnl). Benchmarks against the
point-in-time 30-feature design matrix on identical events. Per-symbol primary,
pooled reference. Verdict gates Stage 2 (torch GRU/TCN).

Usage: uv run python scripts/fx_coint/path_window_model.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))


def path_channels(logp, f, vol) -> list[np.ndarray]:
    """Per-bar path channels in fixed order: [log_return, vol, intra_bar_mom, hl_pos_frac]."""
    log_return = np.diff(np.asarray(logp, dtype=float), prepend=float(logp[0]))
    return [log_return,
            np.asarray(vol, dtype=float),
            np.asarray(f["intra_bar_mom"], dtype=float),
            np.asarray(f["hl_pos_frac"], dtype=float)]


def build_window_matrix(channels, entry, W: int) -> np.ndarray:
    """Flatten the W-bar window ending at each entry into a (len(entry), W*C) matrix.

    Row i = concatenate over channels of ch[entry[i]-W+1 : entry[i]+1] (channel-major).
    Raises ValueError if any entry[i] < W-1 (window would underflow).
    """
    entry = np.asarray(entry)
    if entry.min() < W - 1:
        raise ValueError(f"entry index {int(entry.min())} < W-1={W - 1}; window underflows")
    rows = np.empty((len(entry), W * len(channels)), dtype=float)
    for i, e in enumerate(entry):
        rows[i] = np.concatenate([ch[e - W + 1:e + 1] for ch in channels])
    return rows
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/fx_coint/test_path_window_model.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add scripts/fx_coint/path_window_model.py tests/fx_coint/test_path_window_model.py
git commit -m "feat(fx_coint): per-bar path channels + flattened window matrix

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 2: Shared event sampling + per-symbol window / point-in-time data builders

**Files:**
- Modify: `scripts/fx_coint/path_window_model.py`
- Test: `tests/fx_coint/test_path_window_model.py`

**Interfaces:**
- Consumes: `path_channels`, `build_window_matrix` (Task 1); `feature_ic_definitive.build_all`, `triple_barrier.triple_barrier_core`, `sample_weights.event_weights`, `model_search.build_design` (existing).
- Produces:
  - Module constants `POOL = ["AUDUSD","EURUSD","GBPUSD","USDCAD","USDCHF"]`, `N_GRID = [30, 50]`, `W_GRID = [16, 32, 64]`, `N_EVENTS = 10000`, and `COST_BPS` (copied from `model_search.COST_BPS`).
  - `sample_events(cache, n_tb, W_max, rng) -> dict[str, np.ndarray]` — per-symbol sorted event indices `ev`, with warmup `int(96*bph)+60` AND `ev >= W_max-1`, finite next-bar vol, capped at `N_EVENTS`. Shared across window and point-in-time builders so comparisons use identical events.
  - `build_sym_window(cache, ev_by_sym, n_tb, W) -> dict[str, dict]` — `{s: {X, y, entry, t1, ret, sw}}` where `X` is the flattened window matrix; rows filtered to finite `X` and finite `ret`.
  - `build_sym_pointwise(cache, ev_by_sym, n_tb) -> dict[str, dict]` — same dict shape but `X` is the existing 30-feature design matrix (`build_design`), identical event set, identical finite-filtering convention.

Note: both builders compute `entry = ev + 1`, triple-barrier with `1.0 * vol[entry] * np.sqrt(n_tb)` and vertical `np.minimum(entry + n_tb, n-1)`, and `sw = event_weights(np.diff(logp, prepend=logp[0]), entry, t1)` — matching `model_search.build_sym_data` exactly.

- [ ] **Step 1: Write the failing test**

```python
# append to tests/fx_coint/test_path_window_model.py
from scripts.fx_coint.path_window_model import (
    sample_events, build_sym_window, build_sym_pointwise, POOL, W_GRID, N_GRID,
)


def _fake_cache(n=3000, seed=0):
    rng = np.random.default_rng(seed)
    logp = np.cumsum(rng.standard_normal(n) * 0.001)
    vol = np.full(n, 0.002)
    f = {"intra_bar_mom": rng.standard_normal(n),
         "hl_pos_frac": rng.random(n),
         # minimal extra cols so build_design has something; pointwise builder
         # uses model_search feature list, so this fake is only for window tests
         }
    bph = 12.0
    return logp, f, vol, bph


def test_sample_events_respects_window_floor():
    cache = {s: _fake_cache(seed=i) for i, s in enumerate(POOL[:1])}
    rng = np.random.default_rng(0)
    ev = sample_events(cache, n_tb=50, W_max=64, rng=rng)
    s = POOL[0]
    assert ev[s].min() >= 64 - 1
    assert np.all(np.diff(ev[s]) > 0)  # sorted


def test_build_sym_window_shapes_align():
    cache = {s: _fake_cache(seed=i) for i, s in enumerate(POOL[:1])}
    rng = np.random.default_rng(0)
    ev = sample_events(cache, n_tb=30, W_max=32, rng=rng)
    sym_data = build_sym_window(cache, ev, n_tb=30, W=32)
    s = POOL[0]
    d = sym_data[s]
    assert d["X"].shape[1] == 32 * 4
    assert d["X"].shape[0] == d["entry"].shape[0] == d["ret"].shape[0]
    assert np.isfinite(d["X"]).all()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/fx_coint/test_path_window_model.py -k "window_floor or shapes_align" -v`
Expected: FAIL with `ImportError: cannot import name 'sample_events'`.

- [ ] **Step 3: Write minimal implementation**

Append to `scripts/fx_coint/path_window_model.py`:

```python
from feature_ic_definitive import build_all  # noqa: E402
from model_search import COST_BPS, build_design  # noqa: E402
from sample_weights import event_weights  # noqa: E402
from triple_barrier import triple_barrier_core  # noqa: E402

POOL = ["AUDUSD", "EURUSD", "GBPUSD", "USDCAD", "USDCHF"]
N_GRID = [30, 50]
W_GRID = [16, 32, 64]
N_EVENTS = 10000


def sample_events(cache, n_tb, W_max, rng):
    """Per-symbol sorted event indices, shared across builders for fair comparison."""
    out = {}
    for s, (logp, f, vol, bph) in cache.items():
        n = len(logp)
        warm = max(int(96 * bph) + 60, W_max - 1)
        idx = np.arange(warm, n - n_tb - 3)
        idx = idx[np.isfinite(vol[idx + 1]) & (vol[idx + 1] > 0)]
        out[s] = np.sort(rng.choice(idx, min(N_EVENTS, len(idx)), replace=False))
    return out


def _tb_and_weights(logp, vol, ev, n_tb):
    entry = ev + 1
    n = len(logp)
    t1, ret, _, _ = triple_barrier_core(
        logp, entry, np.minimum(entry + n_tb, n - 1),
        1.0 * vol[entry] * np.sqrt(n_tb))
    bar_log_ret = np.diff(logp, prepend=logp[0])
    sw = event_weights(bar_log_ret, entry, t1)
    return entry, t1, ret, sw


def build_sym_window(cache, ev_by_sym, n_tb, W):
    """Per-symbol dicts with X = flattened W-bar path window."""
    sym_data = {}
    for s, (logp, f, vol, bph) in cache.items():
        ev = ev_by_sym[s]
        entry, t1, ret, sw = _tb_and_weights(logp, vol, ev, n_tb)
        channels = path_channels(logp, f, vol)
        X = build_window_matrix(channels, entry, W)
        fin = np.isfinite(X).all(axis=1) & np.isfinite(ret)
        sym_data[s] = dict(X=X[fin], y=ret[fin], entry=entry[fin],
                           t1=t1[fin], ret=ret[fin], sw=sw[fin])
    return sym_data


def build_sym_pointwise(cache, ev_by_sym, n_tb):
    """Per-symbol dicts with X = existing 30-feature point-in-time design matrix."""
    sym_data = {}
    for s, (logp, f, vol, bph) in cache.items():
        ev = ev_by_sym[s]
        entry, t1, ret, sw = _tb_and_weights(logp, vol, ev, n_tb)
        feature_names = [k for k in f if k != "ent_sign"]
        interactions = [("ffd_0.1", "ffd_zvol20")]
        X, _ = build_design(f, entry, feature_names, interactions)
        fin = np.isfinite(X).all(axis=1) & np.isfinite(ret)
        sym_data[s] = dict(X=X[fin], y=ret[fin], entry=entry[fin],
                           t1=t1[fin], ret=ret[fin], sw=sw[fin])
    return sym_data
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/fx_coint/test_path_window_model.py -k "window_floor or shapes_align" -v`
Expected: PASS (2 passed). (The `build_sym_pointwise` path needs the full feature dict from real `build_all`; it is exercised in the Task 4 smoke test, not here.)

- [ ] **Step 5: Run full test file + quality**

Run: `uv run pytest tests/fx_coint/test_path_window_model.py -v && make quality`
Expected: all tests PASS; ty + ruff clean.

- [ ] **Step 6: Commit**

```bash
git add scripts/fx_coint/path_window_model.py tests/fx_coint/test_path_window_model.py
git commit -m "feat(fx_coint): shared event sampling + window/pointwise data builders

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 3: Window models (MLP pipeline + HistGBM) and fit_predict closure

**Files:**
- Modify: `scripts/fx_coint/path_window_model.py`
- Test: `tests/fx_coint/test_path_window_model.py`

**Interfaces:**
- Consumes: nothing new beyond sklearn.
- Produces:
  - `make_window_models(seed=0) -> dict[str, object]` — keys `["mlp", "histgbm"]`. `mlp` is a `Pipeline([StandardScaler(), MLPRegressor(...)])` (scaling fit on train fold only, so no leakage). `histgbm` reuses the regularized config from `model_search._histgbm`.
  - `fit_predict_for(model)` -> closure `fn(train_dict, test_dict) -> mu` matching the `model_oos_pnl` contract: fits `model.fit(train["X"], train["y"], ...)` and returns `model.predict(test["X"])`. MLP/HistGBM here take no `entry`/`t1`; pass `sample_weight=train.get("sw")` to HistGBM only (sklearn Pipeline needs the `mlpregressor__sample_weight` step-prefixed key, so for the MLP pipeline pass no sample_weight to keep it simple).

- [ ] **Step 1: Write the failing test**

```python
# append to tests/fx_coint/test_path_window_model.py
from scripts.fx_coint.path_window_model import make_window_models, fit_predict_for


def test_window_models_learn_linear_signal():
    rng = np.random.default_rng(0)
    n, p = 800, 16
    X = rng.standard_normal((n, p))
    beta = np.zeros(p); beta[0] = 2.0
    y = X @ beta + rng.standard_normal(n) * 0.1
    cut = 600
    train = {"X": X[:cut], "y": y[:cut], "sw": np.ones(cut)}
    test = {"X": X[cut:], "y": y[cut:], "sw": np.ones(n - cut)}
    models = make_window_models(seed=0)
    for name, model in models.items():
        mu = fit_predict_for(model)(train, test)
        # predictions should correlate positively with the true signal X[:,0]
        corr = np.corrcoef(mu, test["X"][:, 0])[0, 1]
        assert corr > 0.5, f"{name} corr={corr:.2f}"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/fx_coint/test_path_window_model.py -k learn_linear -v`
Expected: FAIL with `ImportError: cannot import name 'make_window_models'`.

- [ ] **Step 3: Write minimal implementation**

Append to `scripts/fx_coint/path_window_model.py` (add imports at top with the others):

```python
from sklearn.neural_network import MLPRegressor  # noqa: E402
from sklearn.pipeline import Pipeline  # noqa: E402
from sklearn.preprocessing import StandardScaler  # noqa: E402

from model_search import _histgbm  # noqa: E402


def make_window_models(seed=0):
    """Stage-1 path models: scaled MLP + regularized HistGBM."""
    mlp = Pipeline([
        ("scale", StandardScaler()),
        ("mlp", MLPRegressor(hidden_layer_sizes=(64, 32), alpha=1e-3,
                             max_iter=300, early_stopping=True,
                             validation_fraction=0.15, random_state=seed)),
    ])
    return {"mlp": mlp, "histgbm": _histgbm(seed)}


def fit_predict_for(model):
    """fit_predict closure for model_oos_pnl. HistGBM gets sample_weight; MLP pipeline
    is fit unweighted (keeps the step-prefixed sample_weight plumbing out of scope)."""
    def _fn(train_dict, test_dict):
        is_pipeline = isinstance(model, Pipeline)
        if is_pipeline:
            model.fit(train_dict["X"], train_dict["y"])
        else:
            model.fit(train_dict["X"], train_dict["y"],
                      sample_weight=train_dict.get("sw"))
        return model.predict(test_dict["X"])
    return _fn
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/fx_coint/test_path_window_model.py -k learn_linear -v`
Expected: PASS (1 passed).

- [ ] **Step 5: Commit**

```bash
git add scripts/fx_coint/path_window_model.py tests/fx_coint/test_path_window_model.py
git commit -m "feat(fx_coint): window models (scaled MLP + HistGBM) + fit_predict closure

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 4: Evaluation driver — per-symbol + pooled, window vs point-in-time, bootstrap CI

**Files:**
- Modify: `scripts/fx_coint/path_window_model.py`
- Test: `tests/fx_coint/test_path_window_model.py`

**Interfaces:**
- Consumes: `model_oos_pnl`, `fold_block_bootstrap_ci` (existing); all Task 1–3 functions.
- Produces:
  - `evaluate_cell(sym_data, model, cost_by_sym, n_folds=5) -> dict` — runs `model_oos_pnl` once **pooled** (all symbols, but cost is per-symbol — see note) and once **per symbol** (single-symbol dicts). Returns `{"pooled": <model_oos_pnl out + bootCI fields>, "per_symbol": {s: <out + bootCI>}}`. Because `model_oos_pnl` takes a scalar `cost`, per-symbol calls pass `cost_by_sym[s]`; the pooled call passes the POOL-mean cost as a documented approximation.
  - `_with_ci(out) -> dict` — adds `lo, hi, p_neg` via `fold_block_bootstrap_ci(out["fold_net"])` when `len(fold_net) >= 3`, else NaNs.
  - `main()` — sweeps `N_GRID × W_GRID × {mlp, histgbm}` for the window model and `N_GRID × {mlp, histgbm}` for the point-in-time benchmark (built once per N via `build_sym_pointwise`), printing comparison tables (net bps, bootCI, pNeg, folds+, sym+) per symbol and pooled. `cache = {s: build_all(s) for s in POOL}` built once; events sampled once per N with `W_max=max(W_GRID)`.

- [ ] **Step 1: Write the failing test**

```python
# append to tests/fx_coint/test_path_window_model.py
from scripts.fx_coint.path_window_model import evaluate_cell, make_window_models as _mwm


def test_evaluate_cell_structure_on_synthetic():
    rng = np.random.default_rng(0)
    sym_data = {}
    for s in ["A", "B"]:
        n = 1200
        entry = np.sort(rng.choice(np.arange(100, 5000), n, replace=False))
        X = rng.standard_normal((n, 8))
        ret = X[:, 0] * 0.001 + rng.standard_normal(n) * 0.0005
        sym_data[s] = dict(X=X, y=ret, entry=entry, t1=entry + 1,
                           ret=ret, sw=np.ones(n))
    model = _mwm(seed=0)["histgbm"]
    out = evaluate_cell(sym_data, model, cost_by_sym={"A": 0.0, "B": 0.0}, n_folds=4)
    assert set(out) == {"pooled", "per_symbol"}
    assert set(out["per_symbol"]) == {"A", "B"}
    for v in [out["pooled"], *out["per_symbol"].values()]:
        assert {"net", "lo", "hi", "p_neg", "folds_pos", "n_trades"} <= set(v)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/fx_coint/test_path_window_model.py -k evaluate_cell -v`
Expected: FAIL with `ImportError: cannot import name 'evaluate_cell'`.

- [ ] **Step 3: Write minimal implementation**

Add imports and functions to `scripts/fx_coint/path_window_model.py`:

```python
from pnl_walkforward import fold_block_bootstrap_ci, model_oos_pnl  # noqa: E402


def _with_ci(out):
    fold_net = out.get("fold_net", np.array([]))
    if len(fold_net) >= 3:
        lo, hi, p_neg = fold_block_bootstrap_ci(fold_net, n_boot=5000)
    else:
        lo = hi = p_neg = float("nan")
    return {**out, "lo": float(lo), "hi": float(hi), "p_neg": float(p_neg)}


def evaluate_cell(sym_data, model, cost_by_sym, n_folds=5):
    """Run model_oos_pnl pooled (mean cost) and per-symbol (own cost), add bootstrap CI."""
    fp = fit_predict_for(model)
    mean_cost = float(np.mean([cost_by_sym[s] for s in sym_data]))
    pooled = _with_ci(model_oos_pnl(sym_data, fp, cost=mean_cost, n_folds=n_folds))
    per_symbol = {}
    for s in sym_data:
        out = model_oos_pnl({s: sym_data[s]}, fp, cost=cost_by_sym[s], n_folds=n_folds)
        per_symbol[s] = _with_ci(out)
    return {"pooled": pooled, "per_symbol": per_symbol}


def _print_row(label, v):
    ci = f"[{v['lo']:+.2f},{v['hi']:+.2f}]" if np.isfinite(v["lo"]) else "[   n/a]"
    print(f"  {label:22s} {v['n_trades']:>8d} {v['net']:+9.3f} {ci:>18s} "
          f"{v['p_neg']:>6.3f} {v['folds_pos']:>3d}/{len(v.get('fold_net', []))}")


def main():
    rng = np.random.default_rng(0)
    cache = {s: build_all(s) for s in POOL}
    for n_tb in N_GRID:
        ev = sample_events(cache, n_tb=n_tb, W_max=max(W_GRID), rng=rng)
        # point-in-time benchmark (built once per N)
        pw = build_sym_pointwise(cache, ev, n_tb)
        print("=" * 96)
        print(f"PATH-WINDOW vs POINT-IN-TIME — N={n_tb}, per-symbol cost, top-decile gating")
        print("=" * 96)
        for name, model in make_window_models(seed=0).items():
            r = evaluate_cell(pw, model, COST_BPS, n_folds=5)
            print(f"[point-in-time {name}] pooled:")
            _print_row(f"pt:{name}:POOL", r["pooled"])
            for s, v in r["per_symbol"].items():
                _print_row(f"pt:{name}:{s}", v)
        # window sweep
        for W in W_GRID:
            win = build_sym_window(cache, ev, n_tb, W)
            for name, model in make_window_models(seed=0).items():
                r = evaluate_cell(win, model, COST_BPS, n_folds=5)
                print(f"[window W={W} {name}] pooled + per-symbol:")
                _print_row(f"win{W}:{name}:POOL", r["pooled"])
                for s, v in r["per_symbol"].items():
                    _print_row(f"win{W}:{name}:{s}", v)
        print()


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/fx_coint/test_path_window_model.py -k evaluate_cell -v`
Expected: PASS (1 passed).

- [ ] **Step 5: Run full test file + quality**

Run: `uv run pytest tests/fx_coint/test_path_window_model.py -v && make quality`
Expected: all PASS; ty + ruff clean.

- [ ] **Step 6: Commit**

```bash
git add scripts/fx_coint/path_window_model.py tests/fx_coint/test_path_window_model.py
git commit -m "feat(fx_coint): path-window vs point-in-time eval driver + bootstrap CI

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 5: Run the full sweep, record results, write verdict + Stage-2 gate decision

**Files:**
- Create: `docs/superpowers/specs/2026-06-25-path-aware-directional-model-results.md`

**Interfaces:**
- Consumes: the committed `path_window_model.py` driver.
- Produces: a results doc with the per-symbol/pooled tables and an explicit Stage-2 go/no-go.

- [ ] **Step 1: Run the driver and capture output**

Run: `uv run python scripts/fx_coint/path_window_model.py 2>&1 | tee /private/tmp/claude-501/-Users-danielfisher-repositories-behemoth--claude-worktrees-fx-sample-weights/580cf616-8add-4090-9ad7-ff8b4bf457aa/scratchpad/path_window_results.txt`
Expected: full N×W×model tables, no exceptions. (Heavy — MLP over the window grid; if runtime is excessive, run in background and poll.)

- [ ] **Step 2: Apply the Stage-2 gate**

Compare each window cell's net bps against the point-in-time benchmark of the same model/N. Gate (from the spec): window beats point-in-time by a margin whose fold-level bootstrap CI excludes zero, on a **majority of (symbol, N) cells**. Record per-cell pass/fail.

- [ ] **Step 3: Write the results doc**

Create `docs/superpowers/specs/2026-06-25-path-aware-directional-model-results.md` containing: the captured tables (window vs point-in-time, per-symbol + pooled, with bootCI/pNeg), the raw single-feature fade incumbent numbers for context (from prior `pnl_walkforward` runs: N=50 fade +0.608 [+0.15,+1.24]), the gate evaluation, and an explicit **GO / NO-GO for Stage 2 (torch GRU/TCN)** with one-paragraph rationale.

- [ ] **Step 4: Commit**

```bash
git add docs/superpowers/specs/2026-06-25-path-aware-directional-model-results.md
git commit -m "docs(fx_coint): path-window Stage-1 results + Stage-2 gate verdict

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Self-Review

**Spec coverage:**
- Horizons N=30/50, exclude N=1,2,3 → `N_GRID = [30, 50]` (Global Constraints, Task 2). ✓
- Per-symbol primary, pooled reference → `evaluate_cell` returns both (Task 4). ✓
- Window inputs W∈{16,32,64}, C=4 channels → `W_GRID`, `path_channels`, `build_window_matrix` (Tasks 1–2). ✓
- Stage-1 models MLP + HistGBM, no torch → `make_window_models` (Task 3); torch barred in Global Constraints. ✓
- Benchmarks: point-in-time ridge/HistGBM + raw fade → point-in-time via `build_sym_pointwise` + driver; raw-fade incumbent numbers recorded in results doc (Task 5). Note: point-in-time models are `mlp`/`histgbm` (same classes on the 30-feature matrix), which is a fair "same model, different features" control; the ridge incumbent and raw-fade are cited from prior committed runs in the results doc. ✓
- Reuse `model_oos_pnl` + `fold_block_bootstrap_ci` unchanged → Task 4. ✓
- Identical events for window vs point-in-time → `sample_events` shared (Task 2). ✓
- Per-symbol realistic cost → `COST_BPS` from `model_search` (Tasks 2, 4). ✓
- Gate to Stage 2 → Task 5. ✓

**Placeholder scan:** No TBD/TODO; every code step has full code. ✓

**Type consistency:** `path_channels` → `build_window_matrix` (list of arrays); builders emit the `{X,y,entry,t1,ret,sw}` dict consumed by `model_oos_pnl`; `fit_predict_for` matches the `fit_predict(train,test)->mu` contract; `evaluate_cell` consumes `cost_by_sym` dict and `_with_ci` consumes `model_oos_pnl` output (has `fold_net`). Consistent. ✓

**Known approximation (documented, not a gap):** `model_oos_pnl` takes a scalar cost, so the pooled readout uses POOL-mean cost; per-symbol readouts (the primary) use exact per-symbol cost. This is acceptable since per-symbol is primary.
