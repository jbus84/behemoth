# BoostLSS Jump-Diffusion & SHASH Distribution Comparison — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Compare GaussianLSS (current baseline) against Merton Jump-Diffusion and SHASH
distributional families for the reversion-OCO straddle strategy, on both distributional fit
quality (OOS NLL) and actual trading P&L (Option B all-in bps/fill), and determine whether
Merton's jump-intensity (`lam`) is a useful new meta-labeler feature.

**Architecture:** A small `DistSpec` registry (`scripts/boostlss_xs/distributions.py`) describes
each family's `boostlss_py` constructor, learner params, which param sizes the OCO entry/SL
(`sigma` for all three), which extra params become meta-labeler features, and a
Python-side NLL function for OOS diagnostics. `meta_label_straddle.py`'s WFO fitting and
tick-backtest functions generalize to accept a `DistSpec` instead of being hardcoded to
GaussianLSS. A new `compare_distributions.py` orchestrates a 4-pair run per family and prints
a side-by-side comparison table.

**Tech Stack:** Python, `boostlss_py` (Rust-backed BoostLSS bindings via `uv` git dependency),
polars, pandas, numpy, scikit-learn (`HistGradientBoostingClassifier` for the meta-labeler).

## Global Constraints

- Sizing sigma for OCO entry/SL is **diffusion-only** `sigma` for all three families — no
  total-variance (diffusion + jump) sizing. This keeps `entry_k`/`sl_k` semantics identical
  to the current baseline for a clean comparison.
- Merton's jump-intensity `lam` and SHASH's `nu`/`tau` are exposed **only as meta-labeler
  features**, not as hard pre-filters on OCO placement.
- Comparison runs on 4 pairs only: `EURUSD, GBPJPY, AUDUSD, USDJPY`. Do not expand to the
  full 17-pair universe as part of this plan — that's a follow-up once a family shows a
  clear win.
- No new pytest coverage — this codebase's `scripts/boostlss_xs/` research scripts are
  validated informally (run the script, inspect the printed summary). Match that pattern.
- All existing cost-model logic (fill-time spread, TB exits charged taker cost, Option B
  post-fill filter, `_has_fill_1m` pre-filter, non-overlap blackout anchored to fill
  timestamp) must be preserved unchanged — this plan only changes *which distribution
  predicts sigma*, not the tick-exact simulation or cost model.

---

### Task 1: Bump `boostlss` dependency and smoke-test the new families

**Files:**
- Modify: `uv.lock` (via `uv lock --upgrade-package boostlss`)
- No manual edits to `pyproject.toml` — `tool.uv.sources.boostlss` has no rev pin, so
  `uv lock --upgrade-package boostlss` re-resolves to upstream HEAD automatically.

**Interfaces:**
- Produces: a working `boostlss_py` install where
  `from boostlss_py import MertonJumpDiffusionLss, SHASHLss, BoostLssModel, PyFamily, PyTreeLearner`
  succeeds.

- [ ] **Step 1: Bump the lock file**

```bash
uv lock --upgrade-package boostlss
```

Expected: lock file updates, new resolved commit hash for `boostlss` differs from the old
`6b9924ea08db10e6bc440d93f20a5105f6b7e4ca`. Confirm with:

```bash
grep -A2 '^name = "boostlss"$' uv.lock
```

Expected output shows a `source = { git = "...#<new-commit-hash>" }` line with a different
hash than before.

- [ ] **Step 2: Sync the environment**

```bash
uv sync
```

Expected: completes without error, rebuilds the `boostlss` Rust extension.

- [ ] **Step 3: Smoke-test the new families import and construct**

```bash
uv run python -c "
from boostlss_py import MertonJumpDiffusionLss, SHASHLss, BoostLssModel, PyTreeLearner
import numpy as np

merton = MertonJumpDiffusionLss(max_jumps=10)
model = BoostLssModel(merton, mstop=2)
for p in ['mu', 'sigma', 'lam', 'mu_j', 'sigma_j']:
    model.add_learner(p, PyTreeLearner(feature_indices=[0], max_depth=2))

np.random.seed(42)
X = np.random.normal(size=(50, 1))
y = np.random.normal(loc=0.05, scale=0.1, size=50)
model.fit(X, y)
preds = model.predict(X, 'lam')
print('Merton OK, lam preds shape:', preds.shape)

shash = SHASHLss()
model2 = BoostLssModel(shash, mstop=2)
for p in ['mu', 'sigma', 'nu', 'tau']:
    model2.add_learner(p, PyTreeLearner(feature_indices=[0], max_depth=2))
model2.fit(X, y)
preds2 = model2.predict(X, 'tau')
print('SHASH OK, tau preds shape:', preds2.shape)
"
```

Expected output:
```
Merton OK, lam preds shape: (50,)
SHASH OK, tau preds shape: (50,)
```

If this fails with an import error, the lock bump in Step 1 didn't pick up the family
commits — re-run `uv lock --upgrade-package boostlss --refresh-package boostlss` and retry.

- [ ] **Step 4: Commit**

```bash
git add uv.lock
git commit -m "chore(deps): bump boostlss to pick up MertonJumpDiffusionLss and SHASHLss"
```

---

### Task 2: Create the distribution registry

**Files:**
- Create: `scripts/boostlss_xs/distributions.py`

**Interfaces:**
- Consumes: nothing from other tasks (constructs `boostlss_py` family objects directly).
- Produces:
  - `DistSpec` dataclass with fields `name: str`, `make_family: Callable[[], object]`,
    `param_names: list[str]`, `sizing_param: str`, `extra_features: list[str]`,
    `nll_fn: Callable[[np.ndarray, dict[str, np.ndarray]], float]`.
  - `REGISTRY: dict[str, DistSpec]` with keys `"gaussian"`, `"merton"`, `"shash"`.
  - `get_dist_spec(name: str) -> DistSpec` — looks up `REGISTRY[name]`, raises
    `ValueError(f"Unknown distribution family: {name}")` if not found.
  - These are consumed by Task 3 (`fit_wfo_dist`, `run_tick_backtest`) and Task 4
    (`compare_distributions.py`).

- [ ] **Step 1: Write the file**

```python
"""
Distribution family registry for the BoostLSS reversion-OCO strategy.

Each DistSpec describes how to plug an alternative BoostLSS distributional family
into the existing WFO + tick-exact backtest pipeline (meta_label_straddle.py):

  make_family     — zero-arg constructor returning a boostlss_py family object
                     (either a PyFamily enum instance, or a family class instance
                     like MertonJumpDiffusionLss(max_jumps=10))
  param_names     — the distributional parameters to fit learners for, e.g.
                     ["mu", "sigma"] for Gaussian, or
                     ["mu", "sigma", "lam", "mu_j", "sigma_j"] for Merton.
  sizing_param    — which predicted param sizes the OCO entry/SL levels.
                     Diffusion-only "sigma" for all three families here — jump/skew
                     risk is exposed via extra_features to the meta-labeler instead
                     of baked into position sizing.
  extra_features  — predicted params (beyond sizing_param) to expose to the
                     meta-labeler as new feature columns, e.g. ["lam"] for Merton
                     (jump intensity — momentum-continuation risk) or ["nu", "tau"]
                     for SHASH (skew, kurtosis). These are NOT rescaled by the
                     per-symbol MAD factor: lam/nu/tau are dimensionless shape
                     parameters, unlike sigma/mu_j/sigma_j which are in
                     MAD-normalised return units.
  nll_fn          — computes mean per-observation negative log-likelihood on a
                     held-out (y, preds) slice, using the exact same formula as
                     the underlying Rust family's nll() — used as an OOS
                     diagnostic fit-quality metric independent of trading P&L.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import numpy as np


@dataclass
class DistSpec:
    name: str
    make_family: Callable[[], object]
    param_names: list[str]
    sizing_param: str
    extra_features: list[str]
    nll_fn: Callable[[np.ndarray, dict[str, np.ndarray]], float]


def _gaussian_nll(y: np.ndarray, preds: dict[str, np.ndarray]) -> float:
    mu = preds["mu"]
    sigma = np.maximum(preds["sigma"], 1e-10)
    ll = -0.5 * np.log(2 * np.pi * sigma ** 2) - 0.5 * ((y - mu) / sigma) ** 2
    return float(np.mean(-ll))


def _merton_nll(y: np.ndarray, preds: dict[str, np.ndarray], max_jumps: int = 10) -> float:
    mu = preds["mu"]
    sigma = np.maximum(preds["sigma"], 1e-10)
    lam = np.maximum(preds["lam"], 1e-10)
    mu_j = preds["mu_j"]
    sigma_j = np.maximum(preds["sigma_j"], 1e-10)

    var_diff = sigma ** 2
    var_jump = sigma_j ** 2
    drift = mu - 0.5 * var_diff

    ln_fact = np.zeros(max_jumps + 1)
    for j in range(1, max_jumps + 1):
        ln_fact[j] = ln_fact[j - 1] + np.log(j)

    n = len(y)
    log_terms = np.empty((max_jumps + 1, n))
    for j in range(max_jumps + 1):
        mu_total = drift + j * mu_j
        var_total = var_diff + j * var_jump
        std_total = np.sqrt(var_total)
        ln_prob_jump = -lam + j * np.log(lam) - ln_fact[j]
        diff = y - mu_total
        ln_norm = -0.5 * np.log(2 * np.pi) - np.log(std_total) - 0.5 * (diff ** 2) / var_total
        log_terms[j] = ln_prob_jump + ln_norm

    max_log = log_terms.max(axis=0)
    sum_exp = np.sum(np.exp(log_terms - max_log[None, :]), axis=0)
    ll = max_log + np.log(sum_exp)
    return float(np.mean(-ll))


def _shash_nll(y: np.ndarray, preds: dict[str, np.ndarray]) -> float:
    mu = preds["mu"]
    sigma = np.maximum(preds["sigma"], 1e-10)
    nu = preds["nu"]
    tau = np.maximum(preds["tau"], 1e-10)

    z = (y - mu) / sigma
    asinh_z = np.arcsinh(z)
    term1 = np.exp(tau * asinh_z)
    term2 = np.exp(-nu * asinh_z)
    r = 0.5 * (term1 - term2)
    c = np.maximum(0.5 * (tau * term1 + nu * term2), 1e-15)

    log_2pi_half = 0.5 * np.log(2 * np.pi)
    ll = np.log(c) - log_2pi_half - np.log(sigma) - 0.5 * np.log(1 + z ** 2) - 0.5 * (r ** 2)
    return float(np.mean(-ll))


def _make_gaussian():
    from boostlss_py import PyFamily  # type: ignore[import]
    return PyFamily("GaussianLSS")


def _make_merton():
    from boostlss_py import MertonJumpDiffusionLss  # type: ignore[import]
    return MertonJumpDiffusionLss(max_jumps=10)


def _make_shash():
    from boostlss_py import SHASHLss  # type: ignore[import]
    return SHASHLss()


REGISTRY: dict[str, DistSpec] = {
    "gaussian": DistSpec(
        name="gaussian",
        make_family=_make_gaussian,
        param_names=["mu", "sigma"],
        sizing_param="sigma",
        extra_features=[],
        nll_fn=_gaussian_nll,
    ),
    "merton": DistSpec(
        name="merton",
        make_family=_make_merton,
        param_names=["mu", "sigma", "lam", "mu_j", "sigma_j"],
        sizing_param="sigma",
        extra_features=["lam"],
        nll_fn=_merton_nll,
    ),
    "shash": DistSpec(
        name="shash",
        make_family=_make_shash,
        param_names=["mu", "sigma", "nu", "tau"],
        sizing_param="sigma",
        extra_features=["nu", "tau"],
        nll_fn=_shash_nll,
    ),
}


def get_dist_spec(name: str) -> DistSpec:
    if name not in REGISTRY:
        raise ValueError(f"Unknown distribution family: {name}")
    return REGISTRY[name]
```

- [ ] **Step 2: Verify the registry + NLL functions against known values**

```bash
uv run python -c "
import numpy as np
from scripts.boostlss_xs.distributions import get_dist_spec

# Gaussian NLL sanity check: y == mu exactly, sigma=1 -> NLL = 0.5*log(2*pi)
spec = get_dist_spec('gaussian')
y = np.array([0.0, 0.0])
preds = {'mu': np.array([0.0, 0.0]), 'sigma': np.array([1.0, 1.0])}
nll = spec.nll_fn(y, preds)
expected = 0.5 * np.log(2 * np.pi)
assert abs(nll - expected) < 1e-9, f'{nll} != {expected}'
print('gaussian NLL sanity check OK:', nll)

# Registry lookup + unknown family error
for name in ['gaussian', 'merton', 'shash']:
    s = get_dist_spec(name)
    print(name, '->', s.param_names, 'sizing:', s.sizing_param, 'extra:', s.extra_features)

try:
    get_dist_spec('nonexistent')
    print('FAIL: should have raised')
except ValueError as e:
    print('Unknown family correctly raises:', e)
"
```

Expected output:
```
gaussian NLL sanity check OK: 0.9189385332046727
gaussian -> ['mu', 'sigma'] sizing: sigma extra: []
merton -> ['mu', 'sigma', 'lam', 'mu_j', 'sigma_j'] sizing: sigma extra: ['lam']
shash -> ['mu', 'sigma', 'nu', 'tau'] sizing: sigma extra: ['nu', 'tau']
Unknown family correctly raises: Unknown distribution family: nonexistent
```

Note: since `scripts/boostlss_xs` has no `__init__.py`-based package import path set up for
`-c` inline scripts, if the import fails with `ModuleNotFoundError`, run instead from the
repo root using:
```bash
PYTHONPATH=scripts/boostlss_xs uv run python -c "
import numpy as np
from distributions import get_dist_spec
..."
```
(same body as above, just the import line changed). Confirm which import style works and
use that same style consistently in Tasks 3 and 4.

- [ ] **Step 3: Commit**

```bash
git add scripts/boostlss_xs/distributions.py
git commit -m "feat(boostlss_xs): add distribution family registry (gaussian/merton/shash)"
```

---

### Task 3: Generalize WFO fitting and tick backtest to accept a distribution family

**Files:**
- Modify: `scripts/boostlss_xs/meta_label_straddle.py`

**Interfaces:**
- Consumes: `DistSpec`, `get_dist_spec` from `distributions.py` (Task 2).
- Produces:
  - `fit_wfo_dist(X: np.ndarray, y: np.ndarray, spec: DistSpec) -> tuple[dict[str, np.ndarray], list[float]]`
    — replaces `fit_wfo_gaussian`. Returns `(preds, fold_nll)` where `preds` maps each
    `spec.param_names` entry to a length-`n` OOS array (NaN outside OOS windows), and
    `fold_nll` is a list of per-fold mean OOS NLL values.
  - `run_tick_backtest(..., family: str = "gaussian", ...) -> tuple[pd.DataFrame, list[float]]`
    — now returns `(trade_df, fold_nll)` instead of just `trade_df`. Trade rows include
    extra columns named after `spec.extra_features` (e.g. `lam`, `nu`, `tau`) when
    `family != "gaussian"`.
  - `fit_meta_label_wfo(df: pd.DataFrame, feat_cols: list[str] = _FEAT_COLS) -> pd.DataFrame`
    — gains a `feat_cols` parameter (defaults to current `_FEAT_COLS`, so existing callers
    are unaffected) so `compare_distributions.py` (Task 4) can pass
    `_FEAT_COLS + spec.extra_features`.
- Consumed by: Task 4 (`compare_distributions.py`) and the existing `__main__` CLI block in
  this same file (updated in this task to match the new signatures).

- [ ] **Step 1: Replace `fit_wfo_gaussian` with `fit_wfo_dist`**

Find this block (current lines 190-217):

```python
# ── WFO GaussianLSS ──────────────────────────────────────────────────────────

def fit_wfo_gaussian(X: np.ndarray, y: np.ndarray) -> np.ndarray:
    from boostlss_py import BoostLssModel, PyFamily, PyTreeLearner  # type: ignore[import]

    n, n_feat = X.shape
    sg_oos    = np.full(n, np.nan)
    fold_size = n // (_N_FOLDS + 1)
    for fi in range(_N_FOLDS):
        tr_end   = fold_size * (fi + 1)
        te_start = tr_end + 8
        te_end   = min(te_start + fold_size, n)
        if te_end <= te_start:
            break
        ok  = ~(np.isnan(X[:tr_end]).any(axis=1) | np.isnan(y[:tr_end]))
        idx = np.where(ok)[0]
        if len(idx) > _MAX_TRAIN:
            idx = np.random.default_rng(42 + fi).choice(idx, _MAX_TRAIN, replace=False)
            idx.sort()
        if len(idx) < 200:
            continue
        model = BoostLssModel(PyFamily("GaussianLSS"), mstop=200, step_length=0.1)
        for p in ["mu", "sigma"]:
            model.add_learner(p, PyTreeLearner(feature_indices=list(range(n_feat)), max_depth=3))
        model.fit(X[idx].astype(np.float64), y[idx].astype(np.float64))
        sg_oos[te_start:te_end] = np.array(
            model.predict(X[te_start:te_end].astype(np.float64), "sigma"))
    return sg_oos
```

Replace it with:

```python
# ── WFO distribution fitting ─────────────────────────────────────────────────

def fit_wfo_dist(
    X: np.ndarray, y: np.ndarray, spec: "DistSpec"
) -> tuple[dict[str, np.ndarray], list[float]]:
    """
    Generalized 5-fold expanding WFO with embargo=8 bars, for any registered
    BoostLSS distribution family.

    Returns:
      preds:    dict mapping each spec.param_names entry to a length-n OOS
                prediction array (NaN outside OOS windows).
      fold_nll: list of per-fold mean OOS negative log-likelihood (diagnostic
                fit-quality metric; lower is better; independent of sigma scale).
    """
    from boostlss_py import BoostLssModel, PyTreeLearner  # type: ignore[import]

    n, n_feat = X.shape
    preds: dict[str, np.ndarray] = {p: np.full(n, np.nan) for p in spec.param_names}
    fold_nll: list[float] = []
    fold_size = n // (_N_FOLDS + 1)
    for fi in range(_N_FOLDS):
        tr_end   = fold_size * (fi + 1)
        te_start = tr_end + 8
        te_end   = min(te_start + fold_size, n)
        if te_end <= te_start:
            break
        ok  = ~(np.isnan(X[:tr_end]).any(axis=1) | np.isnan(y[:tr_end]))
        idx = np.where(ok)[0]
        if len(idx) > _MAX_TRAIN:
            idx = np.random.default_rng(42 + fi).choice(idx, _MAX_TRAIN, replace=False)
            idx.sort()
        if len(idx) < 200:
            continue
        model = BoostLssModel(spec.make_family(), mstop=200, step_length=0.1)
        for p in spec.param_names:
            model.add_learner(p, PyTreeLearner(feature_indices=list(range(n_feat)), max_depth=3))
        model.fit(X[idx].astype(np.float64), y[idx].astype(np.float64))

        te_ok = ~(np.isnan(X[te_start:te_end]).any(axis=1) | np.isnan(y[te_start:te_end]))
        fold_preds: dict[str, np.ndarray] = {}
        for p in spec.param_names:
            pred = np.array(model.predict(X[te_start:te_end].astype(np.float64), p))
            preds[p][te_start:te_end] = pred
            fold_preds[p] = pred[te_ok]
        y_te = y[te_start:te_end][te_ok]
        if len(y_te) > 0:
            fold_nll.append(spec.nll_fn(y_te, fold_preds))
    return preds, fold_nll
```

- [ ] **Step 2: Add the `distributions` import**

Find the import block (current lines 51-62):

```python
from __future__ import annotations

import argparse
import glob
import os
from pathlib import Path

import numpy as np
import pandas as pd
import polars as pl
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import roc_auc_score
```

Replace with:

```python
from __future__ import annotations

import argparse
import glob
import os
from pathlib import Path

import numpy as np
import pandas as pd
import polars as pl
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import roc_auc_score

from distributions import DistSpec, get_dist_spec
```

- [ ] **Step 3: Update `run_tick_backtest` signature and WFO call site**

Find (current lines 366-397):

```python
def run_tick_backtest(
    sym: str,
    data_dir: str,
    tick_dir: str,
    entry_k: float = 0.5,
    tp_k: float    = 0.5,
    sl_k: float    = 1.0,
    hold_hours: int  = 8,
    sig_thresh: float = 1.5,
    verbose: bool   = True,
) -> pd.DataFrame:
    """
    Full tick-exact non-overlapping backtest for one symbol.
    Returns a DataFrame with one row per trade (including tick-exact outcome and features).
    """
    if verbose:
        print(f"  {sym}: building features + WFO...", flush=True)

    d   = build_1h_features(sym, data_dir)
    X   = d["X"]
    ts  = d["ts"]
    mid = d["mid"]
    vs  = d["vs"]
    mad = d["mad"]
    raw = d["raw"]
    feat_df = d["feat_df"]
    n   = len(ts)

    y = np.full(n, np.nan)
    y[:-1] = vs[1:]
    sg_oos = fit_wfo_gaussian(X, y)
    sbps   = np.clip(sg_oos * mad, 0.0, 200.0)
```

Replace with:

```python
def run_tick_backtest(
    sym: str,
    data_dir: str,
    tick_dir: str,
    entry_k: float = 0.5,
    tp_k: float    = 0.5,
    sl_k: float    = 1.0,
    hold_hours: int  = 8,
    sig_thresh: float = 1.5,
    family: str = "gaussian",
    verbose: bool   = True,
) -> tuple[pd.DataFrame, list[float]]:
    """
    Full tick-exact non-overlapping backtest for one symbol.

    Returns (trade_df, fold_nll):
      trade_df — one row per trade (tick-exact outcome + features). Includes extra
                 columns named after the family's extra_features (e.g. "lam" for
                 merton) when family != "gaussian".
      fold_nll — per-WFO-fold mean OOS negative log-likelihood (diagnostic).
    """
    if verbose:
        print(f"  {sym}: building features + WFO ({family})...", flush=True)

    spec = get_dist_spec(family)

    d   = build_1h_features(sym, data_dir)
    X   = d["X"]
    ts  = d["ts"]
    mid = d["mid"]
    vs  = d["vs"]
    mad = d["mad"]
    raw = d["raw"]
    feat_df = d["feat_df"]
    n   = len(ts)

    y = np.full(n, np.nan)
    y[:-1] = vs[1:]
    preds, fold_nll = fit_wfo_dist(X, y, spec)
    sg_oos = preds[spec.sizing_param]
    sbps   = np.clip(sg_oos * mad, 0.0, 200.0)
```

- [ ] **Step 4: Merge extra_features into each trade row**

Find the row-append block (current lines 501-514):

```python
        rows.append({
            "sym":             sym,
            "ts":              str(ts[i]),
            "outcome":         outcome,
            "direction":       direction,
            "gross":           gross,
            "maker_net":       gross - maker_cost,
            "taker_net":       gross - taker_cost,
            "sigma_bps":       sigma_bps_i,
            "live_spread":     live_sp,
            "spread_bps":      spread_med,
            "fill_spread":     fill_spread,
            "fill_spread_raw": fill_spread_raw,  # pre-fallback; NaN/0/outlier → implausible tick
        })
```

Replace with:

```python
        row = {
            "sym":             sym,
            "ts":              str(ts[i]),
            "outcome":         outcome,
            "direction":       direction,
            "gross":           gross,
            "maker_net":       gross - maker_cost,
            "taker_net":       gross - taker_cost,
            "sigma_bps":       sigma_bps_i,
            "live_spread":     live_sp,
            "spread_bps":      spread_med,
            "fill_spread":     fill_spread,
            "fill_spread_raw": fill_spread_raw,  # pre-fallback; NaN/0/outlier → implausible tick
        }
        # Extra distribution params (e.g. jump intensity, skew, kurtosis) exposed
        # to the meta-labeler as features. Not MAD-rescaled — these are dimensionless
        # shape parameters, unlike sigma/mu_j/sigma_j which are in normalised-return units.
        for feat_name in spec.extra_features:
            row[feat_name] = float(preds[feat_name][i])
        rows.append(row)
```

- [ ] **Step 5: Return the tuple and update the verbose print**

Find (current lines 516-530):

```python
    df = pd.DataFrame(rows)
    if len(df) > 0:
        # Merge 1h features for meta-labeling
        df = df.merge(feat_df[["ts"] + [c for c in _FEAT_COLS
                                         if c not in ("sigma_bps","direction","live_spread")]],
                      on="ts", how="left")
    if verbose:
        n_trades  = len(df)
        tp_r      = (df.outcome == "tp").mean() if n_trades else 0
        fallback_r = spread_fallback_n / n_trades if n_trades else 0
        warn = "  ⚠ HIGH FALLBACK RATE" if fallback_r > 0.05 else ""
        print(f"  {sym}: {n_trades} trades  gross={df.gross.mean():+.3f}  "
              f"maker_net={df.maker_net.mean():+.3f}  TP%={tp_r:.1%}  "
              f"spread_fallback={fallback_r:.1%}{warn}", flush=True)
    return df
```

Replace with:

```python
    df = pd.DataFrame(rows)
    if len(df) > 0:
        # Merge 1h features for meta-labeling
        df = df.merge(feat_df[["ts"] + [c for c in _FEAT_COLS
                                         if c not in ("sigma_bps","direction","live_spread")]],
                      on="ts", how="left")
    if verbose:
        n_trades  = len(df)
        tp_r      = (df.outcome == "tp").mean() if n_trades else 0
        fallback_r = spread_fallback_n / n_trades if n_trades else 0
        warn = "  ⚠ HIGH FALLBACK RATE" if fallback_r > 0.05 else ""
        avg_nll = np.mean(fold_nll) if fold_nll else float("nan")
        print(f"  {sym}: {n_trades} trades  gross={df.gross.mean():+.3f}  "
              f"maker_net={df.maker_net.mean():+.3f}  TP%={tp_r:.1%}  "
              f"spread_fallback={fallback_r:.1%}  oos_nll={avg_nll:.4f}{warn}", flush=True)
    return df, fold_nll
```

- [ ] **Step 6: Add `feat_cols` parameter to `fit_meta_label_wfo`**

Find (current lines 535-565):

```python
def fit_meta_label_wfo(df: pd.DataFrame) -> pd.DataFrame:
    """
    Train a HistGradientBoostingClassifier in causal WFO on tick-exact outcomes.
    Adds 'prob_tp' column to df; returns only OOS rows.
    """
    df = df.dropna(subset=_FEAT_COLS).copy()
    df["label"] = (df.outcome == "tp").astype(int)
    X  = df[_FEAT_COLS].values
    y  = df.label.values
    n  = len(df)
    fs = n // (_N_FOLDS + 1)
```

Replace with:

```python
def fit_meta_label_wfo(df: pd.DataFrame, feat_cols: list[str] = _FEAT_COLS) -> pd.DataFrame:
    """
    Train a HistGradientBoostingClassifier in causal WFO on tick-exact outcomes.
    Adds 'prob_tp' column to df; returns only OOS rows.

    feat_cols defaults to the base feature set (_FEAT_COLS); callers comparing
    alternative distribution families pass feat_cols=_FEAT_COLS + spec.extra_features
    to include e.g. jump-intensity or skew/kurtosis as additional meta-label inputs.
    """
    df = df.dropna(subset=feat_cols).copy()
    df["label"] = (df.outcome == "tp").astype(int)
    X  = df[feat_cols].values
    y  = df.label.values
    n  = len(df)
    fs = n // (_N_FOLDS + 1)
```

- [ ] **Step 7: Update the `__main__` CLI block for the new `run_tick_backtest` return type**

Find (current lines 690-694):

```python
        df_sym = run_tick_backtest(
            sym=sym, data_dir=args.data_dir, tick_dir=args.tick_dir,
            entry_k=args.entry_k, tp_k=args.tp_k, sl_k=args.sl_k,
            hold_hours=args.hold_hours, sig_thresh=args.sig_thresh,
        )
```

Replace with:

```python
        df_sym, _fold_nll = run_tick_backtest(
            sym=sym, data_dir=args.data_dir, tick_dir=args.tick_dir,
            entry_k=args.entry_k, tp_k=args.tp_k, sl_k=args.sl_k,
            hold_hours=args.hold_hours, sig_thresh=args.sig_thresh,
        )
```

(Default `family="gaussian"` is unchanged, so the CLI script's existing behavior is
unaffected — this is purely accommodating the new 2-tuple return.)

- [ ] **Step 8: Verify the module still imports and the CLI's default (gaussian) path is unchanged**

```bash
uv run python -c "
import ast
src = open('scripts/boostlss_xs/meta_label_straddle.py').read()
ast.parse(src)
print('syntax OK')
"
```

Expected: `syntax OK`

Then run a fast smoke test on one pair to confirm the gaussian path still produces the same
shape of output as before (numbers will differ run-to-run only if WFO randomness changes,
which it shouldn't since `_MAX_TRAIN` subsampling uses a fixed seed `42 + fi`):

```bash
uv run python scripts/boostlss_xs/meta_label_straddle.py \
  --data-dir /Users/danielfisher/repositories/behemoth/data/tick_bars \
  --tick-dir /Users/danielfisher/Desktop/tick \
  --output-dir /tmp/meta_label_smoketest \
  --pairs EURUSD \
  --threshold 0.55
```

Expected: runs to completion, prints the same style of per-pair summary line as before
(now including `oos_nll=...`), and the final `META-LABEL RESULTS` table — should closely
match the EURUSD row from the PR #374 post-bugfix re-run (Option B all-in ≈ +1.4 bps/fill,
per the earlier per-pair breakdown in `config.py`).

- [ ] **Step 9: Commit**

```bash
git add scripts/boostlss_xs/meta_label_straddle.py
git commit -m "refactor(boostlss_xs): generalize WFO fitting and tick backtest to accept a distribution family

fit_wfo_gaussian -> fit_wfo_dist(X, y, spec: DistSpec), returns (preds dict, fold_nll).
run_tick_backtest gains family: str param, returns (df, fold_nll) tuple, merges
extra_features (jump lam / SHASH nu,tau) into trade rows when family != gaussian.
fit_meta_label_wfo gains feat_cols param (defaults preserve existing behavior).
Default family=gaussian keeps the CLI script's behavior unchanged."
```

---

### Task 4: Build the comparison script and run it

**Files:**
- Create: `scripts/boostlss_xs/compare_distributions.py`

**Interfaces:**
- Consumes: `REGISTRY`, `get_dist_spec` from `distributions.py` (Task 2); `_FEAT_COLS`,
  `_option_b_net_per_fill`, `fit_meta_label_wfo`, `run_tick_backtest` from
  `meta_label_straddle.py` (Task 3).
- Produces: a runnable script printing a side-by-side comparison table and writing
  `comparison_summary.csv` to `--output-dir`.

- [ ] **Step 1: Write the file**

```python
"""
Compare BoostLSS distribution families for the reversion-OCO strategy.

Runs the full pipeline (WFO -> tick-exact backtest -> meta-labeler) once per
distribution family on a small pair subset, and prints a side-by-side table:
OOS NLL (diagnostic fit quality), meta-labeler AUC, TP%, and Option B all-in
bps/fill (the deciding trading metric).

Usage::

    uv run python scripts/boostlss_xs/compare_distributions.py \\
        --data-dir /path/to/tick_bars \\
        --tick-dir /path/to/raw_ticks \\
        --output-dir /tmp/dist_compare \\
        [--pairs EURUSD GBPJPY AUDUSD USDJPY] \\
        [--families gaussian merton shash] \\
        [--threshold 0.55]
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path

import numpy as np
import pandas as pd

from distributions import get_dist_spec
from meta_label_straddle import (
    _FEAT_COLS,
    _option_b_net_per_fill,
    fit_meta_label_wfo,
    run_tick_backtest,
)

_DEFAULT_PAIRS: list[str] = ["EURUSD", "GBPJPY", "AUDUSD", "USDJPY"]
_DEFAULT_FAMILIES: list[str] = ["gaussian", "merton", "shash"]


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Compare BoostLSS distribution families")
    p.add_argument("--data-dir",   default="/Users/danielfisher/repositories/behemoth/data/tick_bars")
    p.add_argument("--tick-dir",   default="/Users/danielfisher/Desktop/tick")
    p.add_argument("--output-dir", default="/tmp/dist_compare")
    p.add_argument("--pairs",      nargs="+", default=_DEFAULT_PAIRS)
    p.add_argument("--families",   nargs="+", default=_DEFAULT_FAMILIES)
    p.add_argument("--threshold",  type=float, default=0.55)
    p.add_argument("--entry-k",    type=float, default=0.5)
    p.add_argument("--tp-k",       type=float, default=0.5)
    p.add_argument("--sl-k",       type=float, default=1.0)
    p.add_argument("--hold-hours", type=int,   default=8)
    p.add_argument("--sig-thresh", type=float, default=1.5)
    return p.parse_args()


def run_family(
    family: str,
    pairs: list[str],
    data_dir: str,
    tick_dir: str,
    entry_k: float,
    tp_k: float,
    sl_k: float,
    hold_hours: int,
    sig_thresh: float,
    threshold: float,
) -> dict:
    spec = get_dist_spec(family)
    feat_cols = _FEAT_COLS + spec.extra_features

    all_nll: list[float] = []
    tick_dfs: list[pd.DataFrame] = []
    for sym in pairs:
        flow_path = os.path.join(data_dir, f"{sym}_1m_flow.parquet")
        tick_path = os.path.join(tick_dir, sym)
        if not os.path.exists(flow_path) or not os.path.isdir(tick_path):
            print(f"  [{family}] {sym}: missing data, skipping")
            continue
        df_sym, fold_nll = run_tick_backtest(
            sym=sym, data_dir=data_dir, tick_dir=tick_dir,
            entry_k=entry_k, tp_k=tp_k, sl_k=sl_k,
            hold_hours=hold_hours, sig_thresh=sig_thresh,
            family=family,
        )
        all_nll.extend(fold_nll)
        if len(df_sym) == 0:
            continue
        tick_dfs.append(df_sym)

    if not tick_dfs:
        return {
            "family": family, "n_trades": 0,
            "oos_nll": float("nan"), "auc": float("nan"),
            "tp_pct": float("nan"), "option_b": float("nan"),
        }

    all_raw = pd.concat(tick_dfs, ignore_index=True)

    oos_dfs: list[pd.DataFrame] = []
    for sym, g in all_raw.groupby("sym"):
        try:
            oos_dfs.append(fit_meta_label_wfo(g.copy(), feat_cols=feat_cols))
        except Exception as e:
            print(f"  [{family}] {sym}: meta-label failed — {e}")

    if not oos_dfs:
        return {
            "family": family, "n_trades": len(all_raw),
            "oos_nll": float(np.mean(all_nll)) if all_nll else float("nan"),
            "auc": float("nan"), "tp_pct": float("nan"), "option_b": float("nan"),
        }

    result = pd.concat(oos_dfs, ignore_index=True)
    ob_net = _option_b_net_per_fill(result, threshold)

    return {
        "family":   family,
        "n_trades": len(result),
        "oos_nll":  float(np.mean(all_nll)) if all_nll else float("nan"),
        "auc":      float(result.mean_auc.mean()),
        "tp_pct":   float(result.label.mean()),
        "option_b": ob_net,
    }


if __name__ == "__main__":
    args = _parse_args()
    Path(args.output_dir).mkdir(parents=True, exist_ok=True)

    results: list[dict] = []
    for family in args.families:
        print(f"\n{'='*60}\nFamily: {family}\n{'='*60}")
        r = run_family(
            family=family, pairs=args.pairs,
            data_dir=args.data_dir, tick_dir=args.tick_dir,
            entry_k=args.entry_k, tp_k=args.tp_k, sl_k=args.sl_k,
            hold_hours=args.hold_hours, sig_thresh=args.sig_thresh,
            threshold=args.threshold,
        )
        results.append(r)

    print(f"\n{'='*76}")
    print("DISTRIBUTION COMPARISON")
    print(f"{'='*76}")
    print(f"  {'Family':<10}  {'n_trades':>8}  {'OOS NLL':>9}  {'Meta AUC':>9}  "
          f"{'TP%':>7}  {'Option B bps/fill':>18}")
    for r in results:
        print(f"  {r['family']:<10}  {r['n_trades']:>8}  {r['oos_nll']:>9.4f}  "
              f"{r['auc']:>9.3f}  {r['tp_pct']:>6.1%}  {r['option_b']:>+18.3f}")

    out_path = os.path.join(args.output_dir, "comparison_summary.csv")
    pd.DataFrame(results).to_csv(out_path, index=False)
    print(f"\nSummary → {out_path}")
```

- [ ] **Step 2: Verify the module parses and imports cleanly**

```bash
uv run python -c "
import ast
src = open('scripts/boostlss_xs/compare_distributions.py').read()
ast.parse(src)
print('syntax OK')
"
```

Expected: `syntax OK`

- [ ] **Step 3: Run the comparison on the 4-pair test set**

```bash
uv run python scripts/boostlss_xs/compare_distributions.py \
  --data-dir /Users/danielfisher/repositories/behemoth/data/tick_bars \
  --tick-dir /Users/danielfisher/Desktop/tick \
  --output-dir /tmp/dist_compare \
  --pairs EURUSD GBPJPY AUDUSD USDJPY \
  --families gaussian merton shash \
  --threshold 0.55
```

Expected: runs to completion (Merton and SHASH will take noticeably longer per pair than
gaussian due to more learners / more expensive NLL — this is expected, not a bug), and
prints a final table like:

```
============================================================================
DISTRIBUTION COMPARISON
============================================================================
  Family      n_trades   OOS NLL   Meta AUC      TP%   Option B bps/fill
  gaussian        8300    1.4123      0.820    75.0%              +0.850
  merton          8100    1.3890      0.834    77.2%              +1.020
  shash           8200    1.4050      0.826    76.1%              +0.910
```

(Exact numbers will differ — this is illustrative of the table shape, not a prediction of
actual results.)

If `merton` shows meaningfully higher Option B than `gaussian`, also inspect meta-labeler
feature importance for the `lam` column to validate the jump-filter hypothesis:

```bash
uv run python -c "
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.inspection import permutation_importance
import numpy as np

df = pd.read_csv('/tmp/dist_compare/comparison_summary.csv')
print(df)
"
```

(This step is diagnostic only — feature-importance inspection code for `lam` specifically
can be written ad hoc at this point based on what the comparison table shows; it's not a
required deliverable of this plan.)

- [ ] **Step 4: Record the findings**

Add a new entry to `scripts/boostlss_xs/BACKLOG.md` under a new `## Distribution comparison
(2026-07-02)` heading summarizing the table from Step 3 and stating which family (if any)
is recommended for promotion to the full 17-pair run, and whether `lam`/`nu`/`tau` showed
meaningful meta-labeler feature importance.

- [ ] **Step 5: Commit**

```bash
git add scripts/boostlss_xs/compare_distributions.py scripts/boostlss_xs/BACKLOG.md
git commit -m "feat(boostlss_xs): add distribution comparison script + record 4-pair findings"
```

---

## Self-review notes (for the plan author, not a task)

- Spec coverage: dependency bump (Task 1), registry with NLL diagnostics (Task 2),
  generalized WFO/backtest (Task 3), comparison harness + findings (Task 4) — all spec
  sections covered. The spec's "open questions for later" (SHASH pre-filter, full 17-pair
  promotion tuning) are explicitly out of scope per the spec itself, not omissions here.
- No placeholders: every step has literal code or literal commands with expected output.
- Type consistency checked: `DistSpec` fields used identically in Task 2 (definition),
  Task 3 (`fit_wfo_dist`, `run_tick_backtest` consuming `spec.param_names`,
  `spec.sizing_param`, `spec.extra_features`), and Task 4 (`get_dist_spec`, `spec.extra_features`
  for `feat_cols`). `run_tick_backtest`'s new `(df, fold_nll)` return type is consistently
  unpacked in both the `__main__` block (Task 3, Step 7) and `compare_distributions.py`
  (Task 4, Step 1).
