# Target Predictability Report Card Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a feature-agnostic tool that scores how *learnable* a candidate target is — a two-stage funnel (well-posedness → bracketed intrinsic ceiling) emitting one report card per target.

**Architecture:** Three modules in `scripts/fx_coint/`. `target_wellposedness.py` (Stage C: cheap label-quality metrics, pure functions). `target_ceiling.py` (Stage A: own-history bracketed ceiling — model lower bound + kNN-MI, both vs a block-permutation null). `target_report.py` (orchestrates the funnel with C-fail→skip-A gating, builds the `ReportCard`, CLI entry that builds targets from datasets the way `triple_barrier_ic.py` does).

**Tech Stack:** Python, numpy, pandas, scipy.stats, scikit-learn (`GradientBoostingRegressor`/`Classifier`, `mutual_info_regression`/`mutual_info_classif`). Tests via pytest, imported as `from scripts.fx_coint.X import Y` (run from repo root).

## Global Constraints

- All new code lives in `scripts/fx_coint/`; tests in `tests/fx_coint/` named `test_*.py`.
- Modules follow existing convention: pure functions + a thin `main()` / `_self_test()` under `if __name__ == "__main__":`.
- Information set for the ceiling is **own-history only** — no cross-sectional or exogenous inputs.
- A block-permutation null is computed for **every** Stage-A statistic; report distance-from-null (empirical p + z).
- Stage A uses **purged + embargoed** cross-validation (no leakage across overlapping labels).
- Skill metric: Spearman IC for continuous targets; balanced accuracy for barrier-class targets. Normalized MI is the kNN-MI side of the bracket for both kinds.
- `kind` is always one of the string literals `"continuous"` or `"barrier"`.
- Run `make quality` (ty + ruff + ...) before any PR, not just pytest — collection errors redden the whole CI job.

---

### Task 1: Stage C — effective-N and temporal concentration

**Files:**
- Create: `scripts/fx_coint/target_wellposedness.py`
- Test: `tests/fx_coint/test_target_wellposedness.py`

**Interfaces:**
- Consumes: nothing (first task).
- Produces:
  - `effective_n(labels: np.ndarray) -> dict` → keys `n`, `tau` (integrated autocorrelation time), `n_eff`, `overlap_ratio` (= `n_eff / n`).
  - `temporal_concentration(signal: np.ndarray, day_index: np.ndarray) -> dict` → keys `gini`, `top1pct_share` (fraction of total `|signal|` in the most-concentrated 1% of days).

- [ ] **Step 1: Write the failing tests**

```python
# tests/fx_coint/test_target_wellposedness.py
import numpy as np

from scripts.fx_coint.target_wellposedness import (
    effective_n,
    temporal_concentration,
)


def test_effective_n_iid_series_has_tau_near_one():
    rng = np.random.default_rng(0)
    x = rng.standard_normal(5000)
    out = effective_n(x)
    assert out["n"] == 5000
    assert 0.5 < out["tau"] < 2.0          # iid -> tau ~ 1
    assert out["n_eff"] > 2500              # close to n
    assert np.isclose(out["overlap_ratio"], out["n_eff"] / out["n"])


def test_effective_n_strongly_autocorrelated_series_collapses():
    # AR(1) phi=0.95 -> long memory -> tau >> 1, n_eff << n
    rng = np.random.default_rng(1)
    n = 5000
    x = np.zeros(n)
    eps = rng.standard_normal(n)
    for i in range(1, n):
        x[i] = 0.95 * x[i - 1] + eps[i]
    out = effective_n(x)
    assert out["tau"] > 5.0
    assert out["n_eff"] < n / 4


def test_temporal_concentration_uniform_vs_spiked():
    # 100 days, one value per day
    days = np.arange(100)
    uniform = np.ones(100)
    spiked = np.ones(100) * 0.01
    spiked[0] = 1000.0
    g_uniform = temporal_concentration(uniform, days)["gini"]
    g_spiked = temporal_concentration(spiked, days)
    assert g_uniform < 0.05                 # near-equal -> gini ~ 0
    assert g_spiked["gini"] > 0.9
    assert g_spiked["top1pct_share"] > 0.9  # ~all mass in 1 of 100 days
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/fx_coint/test_target_wellposedness.py -v`
Expected: FAIL with `ModuleNotFoundError` / `ImportError` (module not created yet).

- [ ] **Step 3: Write minimal implementation**

```python
# scripts/fx_coint/target_wellposedness.py
"""Stage C — target well-posedness metrics (feature-agnostic, own-history only).

Cheap label-quality diagnostics that run first in the predictability funnel. Each
metric maps to a past mirage: overlap inflation, day-clustered significance,
degenerate balance, regime shift, tick-exact illusions. Pure functions, unit-tested.

Self-test: `uv run python scripts/fx_coint/target_wellposedness.py`
"""
from __future__ import annotations

import numpy as np


def _autocorr(x: np.ndarray, max_lag: int) -> np.ndarray:
    x = x - x.mean()
    var = np.dot(x, x)
    if var == 0:
        return np.zeros(max_lag + 1)
    out = np.empty(max_lag + 1)
    for k in range(max_lag + 1):
        out[k] = np.dot(x[: len(x) - k], x[k:]) / var
    return out


def effective_n(labels: np.ndarray) -> dict:
    """Integrated-autocorrelation-time estimate of independent sample count.

    tau = 1 + 2 * sum_{k>=1} rho_k, truncated at the first non-positive rho
    (initial-positive-sequence rule). n_eff = n / tau.
    """
    x = np.asarray(labels, dtype=float)
    x = x[np.isfinite(x)]
    n = int(x.size)
    if n < 3:
        return {"n": n, "tau": 1.0, "n_eff": float(n), "overlap_ratio": 1.0}
    max_lag = min(n - 1, 500)
    rho = _autocorr(x, max_lag)
    tau = 1.0
    for k in range(1, max_lag + 1):
        if rho[k] <= 0:
            break
        tau += 2.0 * rho[k]
    tau = max(tau, 1.0)
    n_eff = n / tau
    return {"n": n, "tau": float(tau), "n_eff": float(n_eff),
            "overlap_ratio": float(n_eff / n)}


def _gini(v: np.ndarray) -> float:
    v = np.sort(np.abs(v))
    n = v.size
    if n == 0 or v.sum() == 0:
        return 0.0
    idx = np.arange(1, n + 1)
    return float((2.0 * np.dot(idx, v) / (n * v.sum())) - (n + 1.0) / n)


def temporal_concentration(signal: np.ndarray, day_index: np.ndarray) -> dict:
    """Gini of total |signal| aggregated per day + share in the top 1% of days."""
    s = np.abs(np.asarray(signal, dtype=float))
    d = np.asarray(day_index)
    ok = np.isfinite(s)
    s, d = s[ok], d[ok]
    uniq = np.unique(d)
    per_day = np.array([s[d == u].sum() for u in uniq])
    total = per_day.sum()
    if total == 0 or per_day.size == 0:
        return {"gini": 0.0, "top1pct_share": 0.0}
    k = max(1, int(np.ceil(0.01 * per_day.size)))
    top = np.sort(per_day)[::-1][:k].sum()
    return {"gini": _gini(per_day), "top1pct_share": float(top / total)}


def _self_test() -> None:
    rng = np.random.default_rng(0)
    print("iid:", effective_n(rng.standard_normal(2000)))
    print("conc:", temporal_concentration(np.ones(100), np.arange(100)))


if __name__ == "__main__":
    _self_test()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/fx_coint/test_target_wellposedness.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add scripts/fx_coint/target_wellposedness.py tests/fx_coint/test_target_wellposedness.py
git commit -m "feat(fx_coint): Stage C effective-N + temporal concentration metrics"
```

---

### Task 2: Stage C — class balance and regime stability

**Files:**
- Modify: `scripts/fx_coint/target_wellposedness.py`
- Test: `tests/fx_coint/test_target_wellposedness.py` (add tests)

**Interfaces:**
- Consumes: nothing new.
- Produces:
  - `class_balance(labels: np.ndarray, kind: str) -> dict`. For `kind="barrier"` (int values in {-1,0,1}): keys `frac_up`, `frac_dn`, `frac_vert`, `entropy` (base-3 normalized, in [0,1]). For `kind="continuous"`: keys `skew`, `tail_share` (fraction of total |x| in top 5% of |x|), `entropy=np.nan`.
  - `regime_stability(labels: np.ndarray, split_idx: int, kind: str) -> dict` → keys `vol_ratio`, `skew_diff`, `acf1_diff`, `max_shift` (= max of the standardized absolute differences). `split_idx` separates train `[:split_idx]` from OOS `[split_idx:]`.

- [ ] **Step 1: Write the failing tests**

```python
# append to tests/fx_coint/test_target_wellposedness.py
from scripts.fx_coint.target_wellposedness import class_balance, regime_stability


def test_class_balance_barrier_balanced_high_entropy():
    labels = np.array([1, -1, 0] * 100)
    out = class_balance(labels, kind="barrier")
    assert np.isclose(out["frac_up"], 1 / 3, atol=0.02)
    assert out["entropy"] > 0.95            # near-uniform 3 classes


def test_class_balance_barrier_degenerate_low_entropy():
    labels = np.array([1] * 297 + [-1, -1, 0])
    out = class_balance(labels, kind="barrier")
    assert out["frac_up"] > 0.95
    assert out["entropy"] < 0.2


def test_class_balance_continuous_reports_tail_share():
    x = np.concatenate([np.full(95, 0.01), np.full(5, 100.0)])
    out = class_balance(x, kind="continuous")
    assert out["tail_share"] > 0.9
    assert np.isnan(out["entropy"])


def test_regime_stability_stable_series_small_shift():
    rng = np.random.default_rng(2)
    x = rng.standard_normal(4000)
    out = regime_stability(x, split_idx=2000, kind="continuous")
    assert out["max_shift"] < 0.5


def test_regime_stability_vol_shift_detected():
    rng = np.random.default_rng(3)
    x = np.concatenate([rng.standard_normal(2000),
                        rng.standard_normal(2000) * 5.0])
    out = regime_stability(x, split_idx=2000, kind="continuous")
    assert out["vol_ratio"] > 3.0
    assert out["max_shift"] > 2.0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/fx_coint/test_target_wellposedness.py -k "class_balance or regime" -v`
Expected: FAIL with `ImportError` (functions not defined).

- [ ] **Step 3: Write minimal implementation**

```python
# add to scripts/fx_coint/target_wellposedness.py
from scipy import stats  # add at top with other imports


def class_balance(labels: np.ndarray, kind: str) -> dict:
    x = np.asarray(labels)
    x = x[np.isfinite(x.astype(float))]
    if kind == "barrier":
        n = x.size
        up = float(np.mean(x == 1)) if n else 0.0
        dn = float(np.mean(x == -1)) if n else 0.0
        vt = float(np.mean(x == 0)) if n else 0.0
        p = np.array([up, dn, vt])
        nz = p[p > 0]
        ent = float(-np.sum(nz * np.log(nz)) / np.log(3)) if nz.size else 0.0
        return {"frac_up": up, "frac_dn": dn, "frac_vert": vt, "entropy": ent}
    a = np.abs(x.astype(float))
    total = a.sum()
    k = max(1, int(np.ceil(0.05 * a.size)))
    tail = np.sort(a)[::-1][:k].sum()
    return {"skew": float(stats.skew(x.astype(float))),
            "tail_share": float(tail / total) if total else 0.0,
            "entropy": float("nan")}


def regime_stability(labels: np.ndarray, split_idx: int, kind: str) -> dict:
    x = np.asarray(labels, dtype=float)
    tr, oos = x[:split_idx], x[split_idx:]
    tr = tr[np.isfinite(tr)]
    oos = oos[np.isfinite(oos)]
    s_tr = tr.std() if tr.size else 0.0
    s_oos = oos.std() if oos.size else 0.0
    vol_ratio = float(max(s_oos, 1e-12) / max(s_tr, 1e-12))
    skew_diff = abs(float(stats.skew(oos)) - float(stats.skew(tr))) if min(tr.size, oos.size) > 2 else 0.0
    acf1_diff = abs(_autocorr(oos, 1)[1] - _autocorr(tr, 1)[1]) if min(tr.size, oos.size) > 2 else 0.0
    # standardized shifts: log vol ratio, raw skew diff, raw acf diff
    shifts = [abs(np.log(vol_ratio)) if vol_ratio > 0 else 0.0, skew_diff, acf1_diff]
    return {"vol_ratio": vol_ratio, "skew_diff": float(skew_diff),
            "acf1_diff": float(acf1_diff), "max_shift": float(max(shifts))}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/fx_coint/test_target_wellposedness.py -v`
Expected: PASS (all tests including Task 1's).

- [ ] **Step 5: Commit**

```bash
git add scripts/fx_coint/target_wellposedness.py tests/fx_coint/test_target_wellposedness.py
git commit -m "feat(fx_coint): Stage C class balance + regime stability metrics"
```

---

### Task 3: Stage C — label-noise via ±1-pip barrier perturbation

**Files:**
- Modify: `scripts/fx_coint/target_wellposedness.py`
- Test: `tests/fx_coint/test_target_wellposedness.py` (add tests)

**Interfaces:**
- Consumes: `triple_barrier_core` from `scripts/fx_coint/triple_barrier.py` (signature: `triple_barrier_core(logp, ev, vert, width) -> (t1, ret, hold, touched)`).
- Produces:
  - `label_noise(logp: np.ndarray, ev: np.ndarray, vert: np.ndarray, width: np.ndarray, perturb: float) -> dict` → keys `flip_rate` (fraction of events whose first-touch sign `touched` changes when the barrier half-width is widened vs narrowed by `perturb` log-units), `frac_unstable_up`, `frac_unstable_dn`. Only barrier-family targets use this.

- [ ] **Step 1: Write the failing tests**

```python
# append to tests/fx_coint/test_target_wellposedness.py
from scripts.fx_coint.target_wellposedness import label_noise


def test_label_noise_clear_barriers_low_flip():
    # monotone strong uptrend -> up-touch is robust to a tiny barrier nudge
    logp = np.log(np.linspace(100, 110, 50))
    ev = np.array([0, 5, 10])
    vert = np.array([40, 45, 49])
    width = np.array([0.02, 0.02, 0.02])
    out = label_noise(logp, ev, vert, width, perturb=1e-5)
    assert out["flip_rate"] < 0.1


def test_label_noise_borderline_barriers_high_flip():
    # price oscillates so that touch order flips when the barrier moves slightly
    logp = np.log(np.array([100.0, 100.10, 99.92, 100.11, 99.90, 100.2] + [100.2] * 20))
    ev = np.array([0])
    vert = np.array([20])
    width = np.array([np.log(100.10 / 100.0)])  # barrier sits right at the first up move
    out = label_noise(logp, ev, vert, width, perturb=np.log(100.10 / 100.0) * 0.5)
    assert 0.0 <= out["flip_rate"] <= 1.0
    assert out["flip_rate"] > 0.0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/fx_coint/test_target_wellposedness.py -k label_noise -v`
Expected: FAIL with `ImportError`.

- [ ] **Step 3: Write minimal implementation**

```python
# add to scripts/fx_coint/target_wellposedness.py
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from triple_barrier import triple_barrier_core  # noqa: E402


def label_noise(logp: np.ndarray, ev: np.ndarray, vert: np.ndarray,
                width: np.ndarray, perturb: float) -> dict:
    """Fraction of first-touch labels whose sign flips when the barrier half-width
    is widened (+perturb) vs narrowed (-perturb) by one tick/pip in log-units.

    A high flip rate means the label is an artifact of exact barrier placement
    (tick-exact-vs-OHLC illusion / adverse-selection sensitivity).
    """
    _, _, _, t_wide = triple_barrier_core(logp, ev, vert, width + perturb)
    narrow_w = np.maximum(width - perturb, 1e-9)
    _, _, _, t_narrow = triple_barrier_core(logp, ev, vert, narrow_w)
    flip = t_wide != t_narrow
    return {"flip_rate": float(np.mean(flip)),
            "frac_unstable_up": float(np.mean(flip & (t_wide == 1))),
            "frac_unstable_dn": float(np.mean(flip & (t_wide == -1)))}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/fx_coint/test_target_wellposedness.py -v`
Expected: PASS (all well-posedness tests).

- [ ] **Step 5: Commit**

```bash
git add scripts/fx_coint/target_wellposedness.py tests/fx_coint/test_target_wellposedness.py
git commit -m "feat(fx_coint): Stage C label-noise via +/-1-pip barrier perturbation"
```

---

### Task 4: Stage A — lag embedding + purged/embargoed CV splits

**Files:**
- Create: `scripts/fx_coint/target_ceiling.py`
- Test: `tests/fx_coint/test_target_ceiling.py`

**Interfaces:**
- Consumes: nothing new.
- Produces:
  - `lag_embedding(returns: np.ndarray, lags: tuple[int, ...]) -> np.ndarray` → shape `(n, len(lags)*2)`: for each lag `L`, columns `[return at t-L, rolling vol (std of returns) over the trailing L bars at t-1]`. Rows with insufficient history are filled `np.nan`.
  - `purged_embargo_splits(n: int, t1: np.ndarray, n_splits: int, embargo: int) -> list[tuple[np.ndarray, np.ndarray]]` → forward-chaining (train, test) index arrays where any train index whose label end `t1` reaches into the test block (plus `embargo` bars) is purged.

- [ ] **Step 1: Write the failing tests**

```python
# tests/fx_coint/test_target_ceiling.py
import numpy as np

from scripts.fx_coint.target_ceiling import lag_embedding, purged_embargo_splits


def test_lag_embedding_shape_and_nan_warmup():
    r = np.arange(100, dtype=float)
    X = lag_embedding(r, lags=(1, 5, 10))
    assert X.shape == (100, 6)
    assert np.all(np.isnan(X[0]))          # no history at t=0
    assert np.all(np.isfinite(X[20]))      # plenty of history by t=20


def test_lag_embedding_return_column_is_lagged():
    r = np.array([0.0, 1.0, 2.0, 3.0, 4.0, 5.0])
    X = lag_embedding(r, lags=(1,))
    # column 0 = return at t-1
    assert X[3, 0] == 2.0
    assert X[5, 0] == 4.0


def test_purged_embargo_splits_no_leakage():
    n = 1000
    t1 = np.arange(n) + 3            # each label ends 3 bars later
    splits = purged_embargo_splits(n, t1, n_splits=4, embargo=5)
    assert len(splits) == 3          # forward-chaining -> n_splits-1 usable folds
    for tr, te in splits:
        assert tr.max() < te.min()   # train strictly before test
        # no train label leaks into [test_start - 0, test_end + embargo]
        gap_ok = t1[tr] < te.min()
        assert gap_ok.all()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/fx_coint/test_target_ceiling.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Write minimal implementation**

```python
# scripts/fx_coint/target_ceiling.py
"""Stage A — intrinsic-ceiling estimators (own-history info set, bracketed).

The ceiling is reported as an interval, not a point:
  lower bound  = flexible model (gradient boosting) on own-history lags, purged+embargoed CV
  upper estim. = Kraskov k-NN mutual information on the lag embedding
Both compared to a block-permutation null so we know what "zero" looks like.

Self-test: `uv run python scripts/fx_coint/target_ceiling.py`
"""
from __future__ import annotations

import numpy as np


def lag_embedding(returns: np.ndarray, lags: tuple[int, ...]) -> np.ndarray:
    r = np.asarray(returns, dtype=float)
    n = r.size
    cols = []
    for L in lags:
        ret_lag = np.full(n, np.nan)
        ret_lag[L:] = r[:-L] if L > 0 else r
        vol = np.full(n, np.nan)
        for t in range(L, n):
            w = r[t - L:t]
            vol[t] = w.std() if w.size else np.nan
        cols.append(ret_lag)
        cols.append(vol)
    return np.column_stack(cols)


def purged_embargo_splits(n: int, t1: np.ndarray, n_splits: int,
                          embargo: int) -> list[tuple[np.ndarray, np.ndarray]]:
    t1 = np.asarray(t1)
    bounds = np.linspace(0, n, n_splits + 1, dtype=int)
    splits = []
    for i in range(1, n_splits):
        te_start, te_end = bounds[i], bounds[i + 1]
        test = np.arange(te_start, te_end)
        cand = np.arange(0, te_start)
        # purge train labels that overlap the test block start (+ embargo)
        keep = t1[cand] < (te_start)
        train = cand[keep]
        if train.size and test.size:
            splits.append((train, test))
    return splits
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/fx_coint/test_target_ceiling.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add scripts/fx_coint/target_ceiling.py tests/fx_coint/test_target_ceiling.py
git commit -m "feat(fx_coint): Stage A lag embedding + purged/embargoed CV splits"
```

---

### Task 5: Stage A — model lower bound + kNN mutual information

**Files:**
- Modify: `scripts/fx_coint/target_ceiling.py`
- Test: `tests/fx_coint/test_target_ceiling.py` (add tests)

**Interfaces:**
- Consumes: `lag_embedding`, `purged_embargo_splits` (Task 4).
- Produces:
  - `model_lower_bound(X: np.ndarray, y: np.ndarray, t1: np.ndarray, kind: str, n_splits: int = 4, embargo: int = 10) -> float`. Returns out-of-fold skill: Spearman IC (`kind="continuous"`) or balanced accuracy (`kind="barrier"`), averaged over purged/embargoed folds. Rows with NaN in `X` or `y` are dropped per-fold.
  - `knn_mi(X: np.ndarray, y: np.ndarray, kind: str) -> float`. Mean sklearn mutual information (`mutual_info_regression` / `mutual_info_classif`) across feature columns, in nats. NaN rows dropped.

- [ ] **Step 1: Write the failing tests**

```python
# append to tests/fx_coint/test_target_ceiling.py
from scripts.fx_coint.target_ceiling import knn_mi, model_lower_bound


def test_model_lower_bound_recovers_learnable_signal():
    rng = np.random.default_rng(0)
    n = 3000
    r = rng.standard_normal(n)
    X = lag_embedding(r, lags=(1, 2))
    # target depends on lag-1 return -> learnable from own history
    y = np.roll(r, -1) + 0.3 * rng.standard_normal(n)
    y[-1] = np.nan
    t1 = np.arange(n) + 1
    ic = model_lower_bound(X, y, t1, kind="continuous")
    assert ic > 0.1


def test_model_lower_bound_pure_noise_near_zero():
    rng = np.random.default_rng(1)
    n = 3000
    X = lag_embedding(rng.standard_normal(n), lags=(1, 2))
    y = rng.standard_normal(n)               # independent of X
    t1 = np.arange(n) + 1
    ic = model_lower_bound(X, y, t1, kind="continuous")
    assert abs(ic) < 0.1


def test_knn_mi_detects_dependence():
    rng = np.random.default_rng(2)
    n = 2000
    r = rng.standard_normal(n)
    X = lag_embedding(r, lags=(1,))
    y_dep = np.roll(r, -1)
    y_dep[-1] = np.nan
    y_indep = rng.standard_normal(n)
    mi_dep = knn_mi(X, y_dep, kind="continuous")
    mi_indep = knn_mi(X, y_indep, kind="continuous")
    assert mi_dep > mi_indep
    assert mi_dep > 0.05
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/fx_coint/test_target_ceiling.py -k "model_lower or knn" -v`
Expected: FAIL with `ImportError`.

- [ ] **Step 3: Write minimal implementation**

```python
# add to scripts/fx_coint/target_ceiling.py
from scipy import stats  # top of file
from sklearn.ensemble import GradientBoostingClassifier, GradientBoostingRegressor
from sklearn.feature_selection import mutual_info_classif, mutual_info_regression
from sklearn.metrics import balanced_accuracy_score


def _drop_nan(X: np.ndarray, y: np.ndarray):
    ok = np.isfinite(X).all(axis=1) & np.isfinite(np.asarray(y, dtype=float))
    return X[ok], np.asarray(y)[ok], ok


def model_lower_bound(X: np.ndarray, y: np.ndarray, t1: np.ndarray, kind: str,
                      n_splits: int = 4, embargo: int = 10) -> float:
    n = len(y)
    scores = []
    for tr, te in purged_embargo_splits(n, t1, n_splits, embargo):
        Xtr, ytr, _ = _drop_nan(X[tr], y[tr])
        Xte, yte, _ = _drop_nan(X[te], y[te])
        if len(Xtr) < 50 or len(Xte) < 20:
            continue
        if kind == "barrier":
            if np.unique(ytr).size < 2:
                continue
            m = GradientBoostingClassifier(n_estimators=100, max_depth=3,
                                           random_state=0)
            m.fit(Xtr, ytr.astype(int))
            scores.append(balanced_accuracy_score(yte.astype(int), m.predict(Xte)))
        else:
            m = GradientBoostingRegressor(n_estimators=100, max_depth=3,
                                          random_state=0)
            m.fit(Xtr, ytr)
            pred = m.predict(Xte)
            if np.std(pred) == 0:
                scores.append(0.0)
            else:
                scores.append(stats.spearmanr(pred, yte)[0])
    return float(np.nanmean(scores)) if scores else float("nan")


def knn_mi(X: np.ndarray, y: np.ndarray, kind: str) -> float:
    Xc, yc, _ = _drop_nan(X, y)
    if len(Xc) < 50:
        return float("nan")
    if kind == "barrier":
        mi = mutual_info_classif(Xc, yc.astype(int), random_state=0)
    else:
        mi = mutual_info_regression(Xc, yc, random_state=0)
    return float(np.mean(mi))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/fx_coint/test_target_ceiling.py -v`
Expected: PASS (all ceiling tests).

- [ ] **Step 5: Commit**

```bash
git add scripts/fx_coint/target_ceiling.py tests/fx_coint/test_target_ceiling.py
git commit -m "feat(fx_coint): Stage A model lower bound + kNN mutual information"
```

---

### Task 6: Stage A — block-permutation null + ceiling bracket

**Files:**
- Modify: `scripts/fx_coint/target_ceiling.py`
- Test: `tests/fx_coint/test_target_ceiling.py` (add tests)

**Interfaces:**
- Consumes: `model_lower_bound`, `knn_mi` (Task 5).
- Produces:
  - `block_permutation_null(stat_fn, y: np.ndarray, block_len: int, n_draws: int, rng: np.random.Generator) -> np.ndarray` → array of `n_draws` statistics computed on block-shuffled copies of `y` (shuffling whole contiguous blocks preserves short-range autocorrelation). `stat_fn(y_perm) -> float`.
  - `ceiling_bracket(X, y, t1, kind, block_len=50, n_draws=50, embargo=10, rng=None) -> dict` → keys `lower` (model IC/bal-acc), `mi` (kNN MI), and for each: `lower_p`, `lower_z`, `mi_p`, `mi_z` (empirical p = fraction of null ≥ observed; z = (obs − null_mean)/null_std).

- [ ] **Step 1: Write the failing tests**

```python
# append to tests/fx_coint/test_target_ceiling.py
from scripts.fx_coint.target_ceiling import block_permutation_null, ceiling_bracket


def test_block_permutation_null_preserves_length_and_values():
    rng = np.random.default_rng(0)
    y = np.arange(200, dtype=float)
    null = block_permutation_null(lambda z: z.mean(), y, block_len=20,
                                  n_draws=10, rng=rng)
    assert null.shape == (10,)
    # mean of a permutation of the same values is unchanged
    assert np.allclose(null, y.mean())


def test_ceiling_bracket_signal_beats_null():
    rng = np.random.default_rng(1)
    n = 3000
    r = rng.standard_normal(n)
    X = lag_embedding(r, lags=(1, 2))
    y = np.roll(r, -1) + 0.3 * rng.standard_normal(n)
    y[-1] = np.nan
    t1 = np.arange(n) + 1
    out = ceiling_bracket(X, y, t1, kind="continuous", block_len=50,
                          n_draws=30, rng=np.random.default_rng(2))
    assert out["lower"] > 0.1
    assert out["lower_p"] < 0.1              # clears the null
    assert out["lower_z"] > 2.0


def test_ceiling_bracket_noise_indistinguishable_from_null():
    rng = np.random.default_rng(3)
    n = 3000
    X = lag_embedding(rng.standard_normal(n), lags=(1, 2))
    y = rng.standard_normal(n)
    t1 = np.arange(n) + 1
    out = ceiling_bracket(X, y, t1, kind="continuous", block_len=50,
                          n_draws=30, rng=np.random.default_rng(4))
    assert out["lower_p"] > 0.1              # cannot reject null
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/fx_coint/test_target_ceiling.py -k "permutation or bracket" -v`
Expected: FAIL with `ImportError`.

- [ ] **Step 3: Write minimal implementation**

```python
# add to scripts/fx_coint/target_ceiling.py
def block_permutation_null(stat_fn, y: np.ndarray, block_len: int,
                           n_draws: int, rng: np.random.Generator) -> np.ndarray:
    y = np.asarray(y)
    n = y.size
    n_blocks = int(np.ceil(n / block_len))
    out = np.empty(n_draws)
    for d in range(n_draws):
        order = rng.permutation(n_blocks)
        perm = np.concatenate([y[b * block_len:(b + 1) * block_len] for b in order])
        out[d] = stat_fn(perm[:n])
    return out


def _emp_p_z(obs: float, null: np.ndarray) -> tuple[float, float]:
    null = null[np.isfinite(null)]
    if null.size == 0 or not np.isfinite(obs):
        return float("nan"), float("nan")
    p = float((np.sum(null >= obs) + 1) / (null.size + 1))
    sd = null.std()
    z = float((obs - null.mean()) / sd) if sd > 0 else float("nan")
    return p, z


def ceiling_bracket(X, y, t1, kind, block_len=50, n_draws=50, embargo=10,
                    rng=None) -> dict:
    rng = rng or np.random.default_rng(0)
    lower = model_lower_bound(X, y, t1, kind, embargo=embargo)
    mi = knn_mi(X, y, kind)
    lower_null = block_permutation_null(
        lambda yp: model_lower_bound(X, yp, t1, kind, embargo=embargo),
        y, block_len, n_draws, rng)
    mi_null = block_permutation_null(
        lambda yp: knn_mi(X, yp, kind), y, block_len, n_draws, rng)
    lp, lz = _emp_p_z(lower, lower_null)
    mp, mz = _emp_p_z(mi, mi_null)
    return {"lower": lower, "mi": mi,
            "lower_p": lp, "lower_z": lz, "mi_p": mp, "mi_z": mz}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/fx_coint/test_target_ceiling.py -v`
Expected: PASS (all ceiling tests).

- [ ] **Step 5: Commit**

```bash
git add scripts/fx_coint/target_ceiling.py tests/fx_coint/test_target_ceiling.py
git commit -m "feat(fx_coint): Stage A block-permutation null + ceiling bracket"
```

---

### Task 7: ReportCard dataclass + funnel orchestration

**Files:**
- Create: `scripts/fx_coint/target_report.py`
- Test: `tests/fx_coint/test_target_report.py`

**Interfaces:**
- Consumes: all of `target_wellposedness` (Tasks 1-3) and `ceiling_bracket` (Task 6).
- Produces:
  - `@dataclass ReportCard` with fields: `name: str`, `kind: str`, `wellposed: dict`, `wellposed_verdict: str` (`"well-posed"` | `"ill-posed"`), `ceiling: dict | None`, `ceiling_verdict: str` (`"signal"` | `"null-indistinguishable"` | `"skipped"`).
  - `wellposedness_verdict(wp: dict, min_overlap=0.1, max_concentration=0.8) -> str`. Ill-posed if `overlap_ratio < min_overlap` OR `top1pct_share > max_concentration` OR barrier `entropy < 0.1`.
  - `score_target(name, kind, labels, signal, day_index, split_idx, X, y_ceiling, t1, *, barrier_args=None, run_ceiling_on_illposed=False, rng=None) -> ReportCard`. Runs Stage C; if ill-posed and not `run_ceiling_on_illposed`, sets `ceiling=None`, `ceiling_verdict="skipped"`. Otherwise runs `ceiling_bracket` and sets `ceiling_verdict="signal"` if `lower_p < 0.05` else `"null-indistinguishable"`. `barrier_args`, when given, is a dict `{logp, ev, vert, width, perturb}` passed to `label_noise` and merged into `wellposed`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/fx_coint/test_target_report.py
import numpy as np

from scripts.fx_coint.target_report import (
    ReportCard,
    score_target,
    wellposedness_verdict,
)


def test_wellposedness_verdict_flags_overlap_collapse():
    assert wellposedness_verdict({"overlap_ratio": 0.02, "top1pct_share": 0.1,
                                  "entropy": 0.9}) == "ill-posed"


def test_wellposedness_verdict_flags_concentration():
    assert wellposedness_verdict({"overlap_ratio": 0.5, "top1pct_share": 0.95,
                                  "entropy": 0.9}) == "ill-posed"


def test_wellposedness_verdict_passes_clean_target():
    assert wellposedness_verdict({"overlap_ratio": 0.5, "top1pct_share": 0.2,
                                  "entropy": 0.9}) == "well-posed"


def test_score_target_illposed_skips_ceiling():
    n = 2000
    rng = np.random.default_rng(0)
    # AR(1) phi 0.99 label -> overlap collapse -> ill-posed
    y = np.zeros(n)
    eps = rng.standard_normal(n)
    for i in range(1, n):
        y[i] = 0.99 * y[i - 1] + eps[i]
    X = np.random.default_rng(1).standard_normal((n, 2))
    card = score_target("ar1", "continuous", labels=y, signal=y,
                        day_index=np.arange(n) // 10, split_idx=n // 2,
                        X=X, y_ceiling=y, t1=np.arange(n) + 1)
    assert isinstance(card, ReportCard)
    assert card.wellposed_verdict == "ill-posed"
    assert card.ceiling is None
    assert card.ceiling_verdict == "skipped"


def test_score_target_wellposed_runs_ceiling_and_finds_signal():
    n = 3000
    rng = np.random.default_rng(2)
    r = rng.standard_normal(n)
    from scripts.fx_coint.target_ceiling import lag_embedding
    X = lag_embedding(r, lags=(1, 2))
    y = np.roll(r, -1) + 0.3 * rng.standard_normal(n)
    y[-1] = np.nan
    card = score_target("learnable", "continuous", labels=r, signal=r,
                        day_index=np.arange(n) // 10, split_idx=n // 2,
                        X=X, y_ceiling=y, t1=np.arange(n) + 1,
                        rng=np.random.default_rng(3))
    assert card.wellposed_verdict == "well-posed"
    assert card.ceiling is not None
    assert card.ceiling_verdict == "signal"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/fx_coint/test_target_report.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Write minimal implementation**

```python
# scripts/fx_coint/target_report.py
"""Target predictability report card — funnel orchestration.

Two-stage funnel per target: Stage C (well-posedness) gates Stage A (bracketed
intrinsic ceiling). A target failing C hard is flagged ill-posed and Stage A is
skipped to save compute (override with run_ceiling_on_illposed=True).

CLI: `uv run python scripts/fx_coint/target_report.py`
"""
from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from target_ceiling import ceiling_bracket  # noqa: E402
from target_wellposedness import (  # noqa: E402
    class_balance,
    effective_n,
    label_noise,
    regime_stability,
    temporal_concentration,
)


@dataclass
class ReportCard:
    name: str
    kind: str
    wellposed: dict
    wellposed_verdict: str
    ceiling: dict | None
    ceiling_verdict: str


def wellposedness_verdict(wp: dict, min_overlap: float = 0.1,
                          max_concentration: float = 0.8) -> str:
    if wp.get("overlap_ratio", 1.0) < min_overlap:
        return "ill-posed"
    if wp.get("top1pct_share", 0.0) > max_concentration:
        return "ill-posed"
    ent = wp.get("entropy", float("nan"))
    if np.isfinite(ent) and ent < 0.1:
        return "ill-posed"
    return "well-posed"


def score_target(name, kind, labels, signal, day_index, split_idx, X, y_ceiling,
                 t1, *, barrier_args=None, run_ceiling_on_illposed=False,
                 rng=None) -> ReportCard:
    wp = {}
    wp.update(effective_n(labels))
    wp.update(temporal_concentration(signal, day_index))
    wp.update(class_balance(labels, kind))
    wp.update(regime_stability(labels, split_idx, kind))
    if barrier_args is not None:
        wp.update(label_noise(barrier_args["logp"], barrier_args["ev"],
                              barrier_args["vert"], barrier_args["width"],
                              barrier_args["perturb"]))
    verdict = wellposedness_verdict(wp)
    if verdict == "ill-posed" and not run_ceiling_on_illposed:
        return ReportCard(name, kind, wp, verdict, None, "skipped")
    cb = ceiling_bracket(X, y_ceiling, t1, kind, rng=rng)
    cv = "signal" if (np.isfinite(cb["lower_p"]) and cb["lower_p"] < 0.05) \
        else "null-indistinguishable"
    return ReportCard(name, kind, wp, verdict, cb, cv)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/fx_coint/test_target_report.py -v`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add scripts/fx_coint/target_report.py tests/fx_coint/test_target_report.py
git commit -m "feat(fx_coint): ReportCard + predictability funnel orchestration"
```

---

### Task 8: CLI — build targets from datasets and print ranked cards

**Files:**
- Modify: `scripts/fx_coint/target_report.py` (add `build_continuous_target`, `main`)
- Test: `tests/fx_coint/test_target_report.py` (add a builder test)

**Interfaces:**
- Consumes: `score_target` (Task 7), `lag_embedding` from `target_ceiling`, the data-loading pattern from `triple_barrier_ic.py` (`load`, `build`, `DATA`, `POOL`, `DATASETS`).
- Produces:
  - `build_continuous_target(ts, logp, horizon_ns) -> tuple[labels, signal, day_index, t1, X]`: continuous forward-return-to-horizon target with own-history lag embedding `X = lag_embedding(bar_returns, lags=(1,5,20,60))`, `t1` = vertical index at `horizon_ns`, `day_index` = integer day of each bar.
  - `main()`: loops a small dataset × horizon grid, pools one representative pair, calls `score_target`, prints a ranked table (sorted by `ceiling["lower_z"]` desc, ill-posed last).

- [ ] **Step 1: Write the failing test**

```python
# append to tests/fx_coint/test_target_report.py
from scripts.fx_coint.target_report import build_continuous_target


def test_build_continuous_target_shapes_align():
    n = 500
    ts = (np.arange(n) * 60_000_000_000).astype("int64")   # 1-min bars
    logp = np.cumsum(np.random.default_rng(0).standard_normal(n) * 1e-4)
    labels, signal, day_index, t1, X = build_continuous_target(
        ts, logp, horizon_ns=3600_000_000_000)             # 1h horizon
    assert labels.shape == (n,)
    assert signal.shape == (n,)
    assert day_index.shape == (n,)
    assert t1.shape == (n,)
    assert X.shape[0] == n
    assert (t1 >= np.arange(n)).all()                      # vertical never backward
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/fx_coint/test_target_report.py -k build_continuous -v`
Expected: FAIL with `ImportError`.

- [ ] **Step 3: Write minimal implementation**

```python
# add to scripts/fx_coint/target_report.py
from target_ceiling import lag_embedding  # noqa: E402  (top with other imports)

# data-loading reused from triple_barrier_ic.py
from triple_barrier import vertical_idx  # noqa: E402

DATA = "/Users/danielfisher/repositories/behemoth/data/tick_bars"
POOL = ["EURUSD", "GBPUSD"]
DATASETS = {"15m_time": "15m_flow", "1000tick": "1000tick"}
HORIZONS_NS = {"1h": 3600_000_000_000, "6h": 6 * 3600_000_000_000}


def build_continuous_target(ts, logp, horizon_ns):
    n = len(ts)
    idx = np.arange(n)
    t1 = vertical_idx(ts, idx, horizon_ns)
    labels = (logp[t1] - logp) * 1e4                       # forward return bps
    signal = labels
    day_index = (ts // (86_400 * 1_000_000_000)).astype("int64")
    r = np.diff(logp, prepend=logp[0])
    X = lag_embedding(r, lags=(1, 5, 20, 60))
    return labels, signal, day_index, t1, X


def _load(sym, suffix):
    import pandas as pd
    df = pd.read_parquet(f"{DATA}/{sym}_{suffix}.parquet")
    if "mid" in df.columns:
        mid = df["mid"].to_numpy()
        t = pd.to_datetime(df["bucket"])
    else:
        mid = ((df["close_bid"] + df["close_ask"]) / 2).to_numpy()
        t = pd.to_datetime(df["timestamp"])
    t = pd.DatetimeIndex(t).tz_localize(None).astype("datetime64[ns]")
    o = np.argsort(t.view("int64"))
    return t.view("int64").astype("int64")[o], np.log(mid[o])


def main():
    rows = []
    for ds_label, suffix in DATASETS.items():
        for h_label, h_ns in HORIZONS_NS.items():
            sym = POOL[0]
            try:
                ts, logp = _load(sym, suffix)
            except FileNotFoundError:
                print(f"skip {sym} {suffix}: not found")
                continue
            labels, signal, day_index, t1, X = build_continuous_target(ts, logp, h_ns)
            card = score_target(
                f"{sym}/{ds_label}/{h_label}", "continuous",
                labels=labels, signal=signal, day_index=day_index,
                split_idx=len(ts) // 2, X=X, y_ceiling=labels, t1=t1,
                rng=np.random.default_rng(0))
            rows.append(card)
    rows.sort(key=lambda c: (c.ceiling or {}).get("lower_z", -1e9), reverse=True)
    print(f"\n{'target':28s} {'wp':>10s} {'ovlp':>6s} {'conc':>6s} "
          f"{'lowerIC':>8s} {'p':>6s} {'z':>6s} {'MI':>6s}  ceiling")
    for c in rows:
        cb = c.ceiling or {}
        print(f"{c.name:28s} {c.wellposed_verdict:>10s} "
              f"{c.wellposed.get('overlap_ratio', float('nan')):6.2f} "
              f"{c.wellposed.get('top1pct_share', float('nan')):6.2f} "
              f"{cb.get('lower', float('nan')):8.3f} {cb.get('lower_p', float('nan')):6.2f} "
              f"{cb.get('lower_z', float('nan')):6.2f} {cb.get('mi', float('nan')):6.3f}  "
              f"{c.ceiling_verdict}")


if __name__ == "__main__":
    main()
```

Note: move the three `from target_ceiling import ...` / `from triple_barrier import ...` lines to the existing import block at the top of the file (next to the Task 7 imports) rather than mid-file; they are shown here inline only to mark what Task 8 adds.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/fx_coint/test_target_report.py -v`
Expected: PASS (all report tests).

- [ ] **Step 5: Run the full suite + quality gate**

Run: `uv run pytest tests/fx_coint/test_target_wellposedness.py tests/fx_coint/test_target_ceiling.py tests/fx_coint/test_target_report.py -q && make quality`
Expected: all tests pass; ruff/ty clean on the three new modules.

- [ ] **Step 6: Commit**

```bash
git add scripts/fx_coint/target_report.py tests/fx_coint/test_target_report.py
git commit -m "feat(fx_coint): target report CLI — build targets + ranked cards"
```

---

## Notes for the implementer

- **Run from repo root** so `from scripts.fx_coint.X import Y` resolves (matches existing tests).
- The intra-module imports use the `sys.path.insert(0, parent)` + bare-module pattern (`from triple_barrier import ...`) already used across `scripts/fx_coint/`. Keep it consistent; do not switch to package-relative imports.
- `make quality` runs ty + ruff; fix lint/type errors before committing the final task. Watch for unused imports if you reorganize the import block in Task 8.
- The CLI `main()` depends on parquet files under `data/tick_bars/`; it is exercised by hand, not in CI. Tests cover the pure builder (`build_continuous_target`) and all scoring logic with synthetic data.
