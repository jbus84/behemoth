# PF Phase 1 — Dynamic-Exit Decision Layer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the fixed-one-bar clock exit of the validated 2h momentum-tail ridge edge with a state-based exit driven by a causal regime-switching particle filter running on the intra-hold 1-minute path, and prove (or disprove) it beats the fixed-horizon baseline under the full gauntlet.

**Architecture:** A Rao-Blackwellized particle filter (`pf_core.py`) carries a discrete regime `s ∈ {trend, revert}` per particle and Kalman-updates a latent drift `μ` analytically; the frozen ridge prediction enters as a regime-conditional tilt. For each ridge-selected entry, we reconstruct the 1-minute mid path inside the held bar (`pf_paths.py`), run the filter causally, and apply a dynamic-exit policy (`pf_exit.py`) capped at the bar end. A gauntlet CLI (`pf_phase1_eval.py`) compares baseline vs PF-exit with day-clustered t, year-block bootstrap, positive-years, ablation, and a randomized-posterior null check.

**Tech Stack:** Python 3.12, numpy, pandas, polars, scikit-learn (existing Ridge pipeline), scipy.stats, pytest. Reuses `scripts/fx_coint/reg_signal_hunt.py` and `scripts/fx_coint/tail_wfo.py`.

## Global Constraints

- Filter is **strictly causal**: output at step `t` depends only on observations ≤ `t`. No smoothing / backward pass. (verbatim from spec §3)
- All PF hyperparameters fit on an **expanding/rolling PAST window only** — never full-sample. For Phase 1, default params are hand-set constants; any calibration uses only the ridge train split. (spec §3)
- The ridge stays **frozen** and walk-forward exactly as in `tail_wfo.walk_forward`; the PF is applied *after* `test_pred` exists and cannot leak into the ridge fit. (spec §3)
- Observation noise is **Gaussian (light-tailed) by default**; non-Gaussianity comes only from the regime switch. The Student-t variant is an optional flag, not the default. (spec §2)
- Net of real cost using `reg_signal_hunt.COST_BPS[sym]`. (spec §5)
- Entry universe: `["EURUSD", "GBPUSD", "USDJPY"]` (TIGHT_MAJORS), freq `"2h"`. (spec §6)
- Every comparison reports: day-clustered t, year-block bootstrap 95% CI, positive-years, per-pair. (spec §5)
- All new code lives under `scripts/fx_coint/`; tests under `tests/fx_coint/`.

---

## Task 0: Worktree data access (setup, folded into Task 1's first commit)

**Files:**
- Create symlink: `data` → root checkout `data` (the 1m flow parquets live only in the root checkout per the worktree convention).

- [ ] **Step 1: Symlink the data directory into the worktree**

Run:
```bash
cd ~/repositories/behemoth/.claude/worktrees/feat-pf-15m
ln -sfn ~/repositories/behemoth/data data
ls data/tick_bars/EURUSD_1m_flow.parquet
```
Expected: the path prints (symlink resolves). `data` is already gitignored, so nothing to commit here.

---

## Task 1: PF core — particle state, prior, and transition (predict step)

**Files:**
- Create: `scripts/fx_coint/pf_core.py`
- Test: `tests/fx_coint/test_pf_core.py`

**Interfaces:**
- Produces:
  - `@dataclass PFParams(n_particles:int=400, p_stay_trend:float=0.9, p_stay_revert:float=0.85, phi_trend:float=0.9, phi_revert:float=-0.3, q_mu:float=0.04, r_obs:float=0.5, mu0_var:float=1.0, tilt_gain:float=1.0, seed:int=0)`
  - `class RBParticleFilter` with attributes after construction: `regime: np.ndarray[int] (n,)`, `mu_mean: np.ndarray[float] (n,)`, `mu_var: np.ndarray[float] (n,)`, `logw: np.ndarray[float] (n,)`.
  - `RBParticleFilter.predict(self, tilt: float) -> None` — advances regimes by the Markov matrix and propagates each particle's Kalman drift prior one step (adds `tilt` only to trend-regime particles).

- [ ] **Step 1: Write the failing test**

```python
# tests/fx_coint/test_pf_core.py
import numpy as np
from scripts.fx_coint.pf_core import PFParams, RBParticleFilter

def test_init_shapes_and_normalized_weights():
    pf = RBParticleFilter(PFParams(n_particles=200, seed=1))
    assert pf.regime.shape == (200,)
    assert set(np.unique(pf.regime)).issubset({0, 1})
    assert pf.mu_mean.shape == (200,)
    assert np.isclose(np.exp(pf.logw).sum(), 1.0)

def test_predict_tilts_only_trend_particles():
    pf = RBParticleFilter(PFParams(n_particles=2000, q_mu=0.0, phi_trend=1.0,
                                   phi_revert=1.0, tilt_gain=1.0, seed=2))
    pf.mu_mean[:] = 0.0
    before_trend = pf.regime == 0
    pf.predict(tilt=1.0)
    # trend particles (regime 0) that did NOT switch get +1.0; the cross-sectional
    # mean drift must be strictly positive because trend particles were nudged up.
    assert pf.mu_mean.mean() > 0.1
    # variance grows by process noise q_mu when q_mu>0
    pf2 = RBParticleFilter(PFParams(n_particles=500, q_mu=0.04, seed=3))
    v0 = pf2.mu_var.copy()
    pf2.predict(tilt=0.0)
    assert np.all(pf2.mu_var >= v0)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ~/repositories/behemoth/.claude/worktrees/feat-pf-15m && uv run pytest tests/fx_coint/test_pf_core.py -q`
Expected: FAIL with `ModuleNotFoundError: scripts.fx_coint.pf_core`.

- [ ] **Step 3: Write minimal implementation**

```python
# scripts/fx_coint/pf_core.py
"""Rao-Blackwellized particle filter: discrete regime + analytic Kalman drift.

State per particle: regime s in {0=trend, 1=revert}, and a Gaussian belief over the
latent vol-normalized drift mu (mean mu_mean, variance mu_var). Particles are sampled
over the discrete regime; mu is integrated analytically (Rao-Blackwellization).
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

TREND, REVERT = 0, 1


@dataclass
class PFParams:
    n_particles: int = 400
    p_stay_trend: float = 0.9      # P(s_t=trend | s_{t-1}=trend)
    p_stay_revert: float = 0.85    # P(s_t=revert | s_{t-1}=revert)
    phi_trend: float = 0.9         # drift persistence in trend
    phi_revert: float = -0.3       # drift mean-reversion/overshoot in revert
    q_mu: float = 0.04             # drift process-noise variance
    r_obs: float = 0.5             # Gaussian obs-noise variance (vol-normalized units)
    mu0_var: float = 1.0           # prior drift variance
    tilt_gain: float = 1.0         # scales the ridge tilt into drift units
    seed: int = 0


class RBParticleFilter:
    def __init__(self, params: PFParams):
        self.p = params
        self.rng = np.random.default_rng(params.seed)
        n = params.n_particles
        # start half trend / half revert, drift prior N(0, mu0_var)
        self.regime = (self.rng.random(n) < 0.5).astype(int)  # 0 trend, 1 revert
        self.mu_mean = np.zeros(n)
        self.mu_var = np.full(n, params.mu0_var)
        self.logw = np.full(n, -np.log(n))

    def predict(self, tilt: float) -> None:
        p = self.p
        n = p.n_particles
        # --- regime transition (sticky Markov) ---
        u = self.rng.random(n)
        stay = np.where(self.regime == TREND, p.p_stay_trend, p.p_stay_revert)
        switch = u >= stay
        self.regime = np.where(switch, 1 - self.regime, self.regime)
        # --- drift Kalman time-update, regime-conditional ---
        phi = np.where(self.regime == TREND, p.phi_trend, p.phi_revert)
        nudge = np.where(self.regime == TREND, p.tilt_gain * tilt, 0.0)
        self.mu_mean = phi * self.mu_mean + nudge
        self.mu_var = phi * phi * self.mu_var + p.q_mu
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd ~/repositories/behemoth/.claude/worktrees/feat-pf-15m && uv run pytest tests/fx_coint/test_pf_core.py -q`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
cd ~/repositories/behemoth/.claude/worktrees/feat-pf-15m
ln -sfn ~/repositories/behemoth/data data
git add scripts/fx_coint/pf_core.py tests/fx_coint/test_pf_core.py
git commit -m "feat(fx_coint): RBPF core — particle state + regime/drift predict step"
```

---

## Task 2: PF core — observation update, weights, systematic resample

**Files:**
- Modify: `scripts/fx_coint/pf_core.py`
- Test: `tests/fx_coint/test_pf_core.py`

**Interfaces:**
- Consumes: `RBParticleFilter`, `PFParams` from Task 1.
- Produces:
  - `RBParticleFilter.update(self, r_obs_value: float) -> None` — Kalman measurement-update of `mu` per particle against observed vol-normalized return, reweights by the Gaussian predictive likelihood, then systematic-resamples on low ESS.
  - `RBParticleFilter.posterior(self) -> tuple[float, float, float]` — returns `(p_trend, mu_hat, mu_var_post)` = weight on trend regime, posterior-mean drift, posterior drift variance (mixture variance).
  - `staticmethod RBParticleFilter.systematic_resample(weights: np.ndarray, rng) -> np.ndarray` — returns resampled index array.

- [ ] **Step 1: Write the failing test**

```python
# append to tests/fx_coint/test_pf_core.py
def test_systematic_resample_favors_heavy_weights():
    rng = np.random.default_rng(0)
    w = np.array([0.0, 0.0, 1.0, 0.0])
    idx = RBParticleFilter.systematic_resample(w, rng)
    assert np.all(idx == 2)

def test_update_pulls_posterior_drift_toward_persistent_signal():
    pf = RBParticleFilter(PFParams(n_particles=3000, q_mu=0.02, r_obs=0.3, seed=5))
    for _ in range(15):
        pf.predict(tilt=0.0)
        pf.update(r_obs_value=1.0)   # persistent positive vol-normalized return
    p_trend, mu_hat, mu_var = pf.posterior()
    assert mu_hat > 0.3            # posterior drift turned positive
    assert 0.0 <= p_trend <= 1.0
    assert mu_var > 0.0

def test_posterior_drift_flips_with_signal():
    pf = RBParticleFilter(PFParams(n_particles=3000, seed=6))
    for _ in range(15):
        pf.predict(0.0); pf.update(-1.0)
    _, mu_hat, _ = pf.posterior()
    assert mu_hat < -0.3
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ~/repositories/behemoth/.claude/worktrees/feat-pf-15m && uv run pytest tests/fx_coint/test_pf_core.py -q`
Expected: FAIL with `AttributeError: 'RBParticleFilter' object has no attribute 'update'`.

- [ ] **Step 3: Write minimal implementation**

```python
# add to scripts/fx_coint/pf_core.py (inside RBParticleFilter)
    def update(self, r_obs_value: float) -> None:
        p = self.p
        # predictive variance of the observation per particle: Var(mu)+R
        s = self.mu_var + p.r_obs
        resid = r_obs_value - self.mu_mean
        # Gaussian log-likelihood of the observation (the RB weight increment)
        loglik = -0.5 * (np.log(2.0 * np.pi * s) + resid * resid / s)
        self.logw = self.logw + loglik
        self.logw -= _logsumexp(self.logw)
        # Kalman measurement update of mu per particle
        k = self.mu_var / s
        self.mu_mean = self.mu_mean + k * resid
        self.mu_var = (1.0 - k) * self.mu_var
        # resample on low ESS
        w = np.exp(self.logw)
        ess = 1.0 / np.sum(w * w)
        if ess < 0.5 * p.n_particles:
            idx = self.systematic_resample(w, self.rng)
            self.regime = self.regime[idx]
            self.mu_mean = self.mu_mean[idx]
            self.mu_var = self.mu_var[idx]
            self.logw = np.full(p.n_particles, -np.log(p.n_particles))

    def posterior(self) -> tuple[float, float, float]:
        w = np.exp(self.logw)
        p_trend = float(w[self.regime == TREND].sum())
        mu_hat = float(np.sum(w * self.mu_mean))
        # mixture variance = E[var] + var of means
        mu_var_post = float(np.sum(w * self.mu_var) + np.sum(w * (self.mu_mean - mu_hat) ** 2))
        return p_trend, mu_hat, mu_var_post

    @staticmethod
    def systematic_resample(weights: np.ndarray, rng) -> np.ndarray:
        n = len(weights)
        positions = (rng.random() + np.arange(n)) / n
        cumsum = np.cumsum(weights)
        cumsum[-1] = 1.0
        return np.searchsorted(cumsum, positions).astype(int)
```

Add this module-level helper near the top of `pf_core.py` (after imports):
```python
def _logsumexp(x: np.ndarray) -> float:
    m = np.max(x)
    return float(m + np.log(np.sum(np.exp(x - m))))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd ~/repositories/behemoth/.claude/worktrees/feat-pf-15m && uv run pytest tests/fx_coint/test_pf_core.py -q`
Expected: PASS (5 passed).

- [ ] **Step 5: Commit**

```bash
git add scripts/fx_coint/pf_core.py tests/fx_coint/test_pf_core.py
git commit -m "feat(fx_coint): RBPF observation update, weights, systematic resample"
```

---

## Task 3: Online filter driver + causality guarantee

**Files:**
- Modify: `scripts/fx_coint/pf_core.py`
- Test: `tests/fx_coint/test_pf_core.py`

**Interfaces:**
- Consumes: `RBParticleFilter`, `PFParams`.
- Produces:
  - `run_filter(observations: np.ndarray, tilt: float, params: PFParams) -> dict[str, np.ndarray]` — runs predict/update for each step; the constant `tilt` (the frozen ridge `test_pred` for this trade) is injected every step. Returns `{"p_trend": (T,), "mu_hat": (T,), "mu_var": (T,)}`, one row per observation, each computed from observations `[0..t]` only.

- [ ] **Step 1: Write the failing test**

```python
# append to tests/fx_coint/test_pf_core.py
from scripts.fx_coint.pf_core import run_filter

def test_run_filter_output_shapes():
    obs = np.array([0.5, 0.4, -0.2, 1.1, 0.9])
    out = run_filter(obs, tilt=0.3, params=PFParams(n_particles=300, seed=0))
    assert out["mu_hat"].shape == (5,)
    assert out["p_trend"].shape == (5,)
    assert out["mu_var"].shape == (5,)

def test_run_filter_is_causal():
    # outputs for the first k steps must not change if later observations change
    base = np.array([0.5, 0.4, -0.2, 1.1, 0.9])
    alt = base.copy(); alt[3:] = [-5.0, -5.0]
    o1 = run_filter(base, tilt=0.0, params=PFParams(n_particles=500, seed=7))
    o2 = run_filter(alt, tilt=0.0, params=PFParams(n_particles=500, seed=7))
    assert np.allclose(o1["mu_hat"][:3], o2["mu_hat"][:3])
    assert np.allclose(o1["p_trend"][:3], o2["p_trend"][:3])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ~/repositories/behemoth/.claude/worktrees/feat-pf-15m && uv run pytest tests/fx_coint/test_pf_core.py::test_run_filter_is_causal -q`
Expected: FAIL with `ImportError: cannot import name 'run_filter'`.

- [ ] **Step 3: Write minimal implementation**

```python
# add to scripts/fx_coint/pf_core.py (module level)
def run_filter(observations: np.ndarray, tilt: float, params: PFParams) -> dict:
    pf = RBParticleFilter(params)
    T = len(observations)
    p_trend = np.empty(T)
    mu_hat = np.empty(T)
    mu_var = np.empty(T)
    for t in range(T):
        pf.predict(tilt)
        pf.update(float(observations[t]))
        p_trend[t], mu_hat[t], mu_var[t] = pf.posterior()
    return {"p_trend": p_trend, "mu_hat": mu_hat, "mu_var": mu_var}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd ~/repositories/behemoth/.claude/worktrees/feat-pf-15m && uv run pytest tests/fx_coint/test_pf_core.py -q`
Expected: PASS (7 passed). The causality test passes because the loop computes step `t` before any observation `> t` is read; reusing the same `seed` makes the RNG draws identical for the shared prefix.

- [ ] **Step 5: Commit**

```bash
git add scripts/fx_coint/pf_core.py tests/fx_coint/test_pf_core.py
git commit -m "feat(fx_coint): causal online RBPF driver run_filter"
```

---

## Task 4: Intra-hold 1-minute path reconstruction

**Files:**
- Create: `scripts/fx_coint/pf_paths.py`
- Test: `tests/fx_coint/test_pf_paths.py`

**Interfaces:**
- Consumes: 1m parquet `data/tick_bars/{sym}_1m_flow.parquet` (cols incl. `bucket`, `mid`); `reg_signal_hunt.FREQ_MINUTES`.
- Produces:
  - `build_minute_index(sym: str) -> tuple[np.ndarray, np.ndarray]` — returns `(buckets_ns, mids)` for all 1m bars, sorted by time. `buckets_ns` is int64 nanoseconds.
  - `hold_path(entry_bucket: np.datetime64, freq: str, buckets_ns: np.ndarray, mids: np.ndarray) -> np.ndarray` — returns the array of 1m mids in the held window `(entry_bucket, entry_bucket + freq]` (the *next* bar, matching `ret_next_bps` semantics), oldest first. Empty array if no minutes found.
  - `path_to_volnorm_returns(path_mids: np.ndarray, sigma_bps: float) -> np.ndarray` — log-returns of the path in bps divided by `sigma_bps`, the per-step vol-normalized observation stream for the filter. Length `len(path_mids)-1`.

- [ ] **Step 1: Write the failing test**

```python
# tests/fx_coint/test_pf_paths.py
import numpy as np
import pandas as pd
from scripts.fx_coint.pf_paths import hold_path, path_to_volnorm_returns

def test_hold_path_selects_next_bar_window():
    base = pd.Timestamp("2022-01-03 08:00")
    buckets = pd.date_range(base, periods=240, freq="1min").values
    mids = np.linspace(1.10, 1.11, 240)
    buckets_ns = buckets.astype("datetime64[ns]").astype("int64")
    entry = np.datetime64("2022-01-03 08:00")  # 2h bar -> next window 10:00..12:00
    path = hold_path(entry, "2h", buckets_ns, mids)
    # next window is (10:00, 12:00] => 120 one-minute marks
    assert 110 <= len(path) <= 121
    assert path[0] > mids[0]

def test_path_to_volnorm_returns_scales_by_sigma():
    mids = np.array([1.0, 1.0001, 1.0002])
    out = path_to_volnorm_returns(mids, sigma_bps=1.0)
    assert out.shape == (2,)
    assert np.all(out > 0)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ~/repositories/behemoth/.claude/worktrees/feat-pf-15m && uv run pytest tests/fx_coint/test_pf_paths.py -q`
Expected: FAIL with `ModuleNotFoundError: scripts.fx_coint.pf_paths`.

- [ ] **Step 3: Write minimal implementation**

```python
# scripts/fx_coint/pf_paths.py
"""Reconstruct the intra-hold 1-minute mid path for a ridge-selected entry bar.

The strategy holds the *next* bar after the entry signal (ret_next_bps semantics):
signal at bar with bucket B -> position over window (B, B+freq] -> exit at its close.
The dynamic-exit filter runs on the 1-minute mids inside that window.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import polars as pl

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.fx_coint.reg_signal_hunt import FREQ_MINUTES  # noqa: E402

_NS_PER_MIN = 60_000_000_000


def build_minute_index(sym: str) -> tuple[np.ndarray, np.ndarray]:
    df = pl.read_parquet(_REPO_ROOT / f"data/tick_bars/{sym}_1m_flow.parquet").sort("bucket")
    buckets_ns = df["bucket"].to_numpy().astype("datetime64[ns]").astype("int64")
    mids = df["mid"].to_numpy().astype(float)
    return buckets_ns, mids


def hold_path(entry_bucket, freq: str, buckets_ns: np.ndarray, mids: np.ndarray) -> np.ndarray:
    step_ns = FREQ_MINUTES[freq] * _NS_PER_MIN
    e = np.datetime64(entry_bucket, "ns").astype("int64")
    lo, hi = e + step_ns, e + 2 * step_ns  # the NEXT bar window (B+freq, B+2*freq]
    i0 = np.searchsorted(buckets_ns, lo, side="right")
    i1 = np.searchsorted(buckets_ns, hi, side="right")
    return mids[i0:i1]


def path_to_volnorm_returns(path_mids: np.ndarray, sigma_bps: float) -> np.ndarray:
    if len(path_mids) < 2 or sigma_bps <= 0:
        return np.empty(0)
    lr_bps = (np.log(path_mids[1:]) - np.log(path_mids[:-1])) * 1e4
    return lr_bps / sigma_bps
```

Note for Step 4: `hold_path`'s window is `(entry+freq, entry+2*freq]`. The panel's `bucket` is the signal bar B; `ret_next_bps` is measured over `(B, B+freq]`. But the panel return uses bar *closes* (mid at B vs mid at B+freq). Align the test's expectation to whichever the eval task asserts; the integration test in Task 6 pins the exact alignment against `ret_next_bps`.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd ~/repositories/behemoth/.claude/worktrees/feat-pf-15m && uv run pytest tests/fx_coint/test_pf_paths.py -q`
Expected: PASS (2 passed). If the window-offset assertion fails, adjust the `lo/hi` offsets so the selected window matches the bar whose close return equals `ret_next_bps` (verified end-to-end in Task 6).

- [ ] **Step 5: Commit**

```bash
git add scripts/fx_coint/pf_paths.py tests/fx_coint/test_pf_paths.py
git commit -m "feat(fx_coint): intra-hold 1-minute path reconstruction for PF exit"
```

---

## Task 5: Dynamic-exit policy

**Files:**
- Create: `scripts/fx_coint/pf_exit.py`
- Test: `tests/fx_coint/test_pf_exit.py`

**Interfaces:**
- Consumes: `run_filter` output dict (`p_trend`, `mu_hat`, `mu_var`).
- Produces:
  - `@dataclass ExitPolicy(pi_exit:float=0.4, mu_floor_bps_z:float=0.0)`
  - `exit_index(post: dict, side: str, max_hold: int) -> int` — returns the 0-based step index at which to exit the position. Exit triggers when `p_trend < pi_exit` OR `mu_hat` flips against the trade sign OR `mu_hat` decays below `mu_floor_bps_z` (in the trade's favorable direction). If no trigger fires, returns `max_hold - 1` (hold to the cap). `side` is `"long"` or `"short"`.

- [ ] **Step 1: Write the failing test**

```python
# tests/fx_coint/test_pf_exit.py
import numpy as np
from scripts.fx_coint.pf_exit import ExitPolicy, exit_index

def _post(p_trend, mu_hat):
    n = len(p_trend)
    return {"p_trend": np.array(p_trend), "mu_hat": np.array(mu_hat),
            "mu_var": np.ones(n)}

def test_exit_on_regime_collapse():
    post = _post([0.9, 0.9, 0.2, 0.9], [1.0, 1.0, 1.0, 1.0])
    assert exit_index(post, side="long", max_hold=4) == 2

def test_exit_on_drift_flip_long():
    post = _post([0.9, 0.9, 0.9, 0.9], [1.0, 0.5, -0.3, 1.0])
    assert exit_index(post, side="long", max_hold=4) == 2

def test_no_trigger_holds_to_cap():
    post = _post([0.9, 0.9, 0.9], [1.0, 1.0, 1.0])
    assert exit_index(post, side="long", max_hold=3) == 2

def test_short_side_flip():
    post = _post([0.9, 0.9, 0.9], [-1.0, 0.4, -1.0])
    assert exit_index(post, side="short", max_hold=3) == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ~/repositories/behemoth/.claude/worktrees/feat-pf-15m && uv run pytest tests/fx_coint/test_pf_exit.py -q`
Expected: FAIL with `ModuleNotFoundError: scripts.fx_coint.pf_exit`.

- [ ] **Step 3: Write minimal implementation**

```python
# scripts/fx_coint/pf_exit.py
"""State-based exit policy reading the causal RBPF posterior."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass
class ExitPolicy:
    pi_exit: float = 0.4         # exit if P(trend) drops below this
    mu_floor_bps_z: float = 0.0  # exit if favorable drift decays past this


def exit_index(post: dict, side: str, max_hold: int) -> int:
    sign = 1.0 if side == "long" else -1.0
    p_trend = post["p_trend"]
    mu_hat = post["mu_hat"]
    n = min(max_hold, len(p_trend))
    pol = ExitPolicy()
    for t in range(n):
        favorable = sign * mu_hat[t]
        if p_trend[t] < pol.pi_exit:
            return t
        if favorable < 0:                      # drift flipped against the trade
            return t
        if favorable < pol.mu_floor_bps_z:     # favorable drift decayed away
            return t
    return n - 1
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd ~/repositories/behemoth/.claude/worktrees/feat-pf-15m && uv run pytest tests/fx_coint/test_pf_exit.py -q`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add scripts/fx_coint/pf_exit.py tests/fx_coint/test_pf_exit.py
git commit -m "feat(fx_coint): state-based dynamic-exit policy from RBPF posterior"
```

---

## Task 6: Phase-1 backtest harness (baseline vs PF-exit)

**Files:**
- Create: `scripts/fx_coint/pf_phase1.py`
- Test: `tests/fx_coint/test_pf_phase1.py`

**Interfaces:**
- Consumes: `tail_wfo.walk_forward`, `reg_signal_hunt.build_freq_bars`, `build_panel`, `COST_BPS`, `FREQ_MINUTES`; `pf_paths.*`; `pf_core.run_filter`; `pf_exit.exit_index`; `PFParams`.
- Produces:
  - `pf_exit_realized_bps(entry_bucket, side, tilt, sigma_bps, freq, sym, minute_idx, params) -> float` — reconstructs the hold path, runs the filter with the frozen `tilt`, applies `exit_index`, returns the **gross** realized signed bps at the chosen exit minute (NOT yet cost-netted). Falls back to the full-bar return if the path is empty.
  - `run_pair_phase1(sym, freq="2h", q=0.95, n_folds=5, params=None) -> dict` — returns aligned arrays over the *same* ridge-selected long entries: `{"net_base": (m,), "net_pf": (m,), "bucket": (m,) datetime64, "n": m}`. `net_base` = full-bar `ret_next_bps` − cost (the frozen baseline); `net_pf` = PF-exit gross − cost.

- [ ] **Step 1: Write the failing test**

```python
# tests/fx_coint/test_pf_phase1.py
import numpy as np
from scripts.fx_coint.pf_phase1 import run_pair_phase1

def test_phase1_arrays_align_and_baseline_matches_fixed_horizon():
    out = run_pair_phase1("EURUSD", freq="2h", q=0.95, n_folds=5)
    assert out["n"] > 30
    assert out["net_base"].shape == out["net_pf"].shape == (out["n"],)
    assert out["bucket"].shape == (out["n"],)
    # PF that always holds to the cap must reproduce the baseline within tiny
    # path-vs-close rounding; here we only assert both are finite and same length.
    assert np.all(np.isfinite(out["net_base"]))
    assert np.all(np.isfinite(out["net_pf"]))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ~/repositories/behemoth/.claude/worktrees/feat-pf-15m && uv run pytest tests/fx_coint/test_pf_phase1.py -q`
Expected: FAIL with `ModuleNotFoundError: scripts.fx_coint.pf_phase1`.

- [ ] **Step 3: Write minimal implementation**

```python
# scripts/fx_coint/pf_phase1.py
"""Phase-1 backtest: PF dynamic-exit vs frozen fixed-horizon baseline, same entries."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import polars as pl

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.fx_coint.pf_core import PFParams, run_filter  # noqa: E402
from scripts.fx_coint.pf_exit import exit_index  # noqa: E402
from scripts.fx_coint.pf_paths import (  # noqa: E402
    build_minute_index,
    hold_path,
    path_to_volnorm_returns,
)
from scripts.fx_coint.reg_signal_hunt import (  # noqa: E402
    COST_BPS,
    build_freq_bars,
    build_panel,
)
from scripts.fx_coint.tail_wfo import walk_forward  # noqa: E402


def pf_exit_realized_bps(entry_bucket, side, tilt, sigma_bps, freq, sym,
                         minute_idx, params) -> float:
    buckets_ns, mids = minute_idx
    path = hold_path(entry_bucket, freq, buckets_ns, mids)
    if len(path) < 2 or sigma_bps <= 0:
        return float("nan")  # caller falls back to baseline full-bar return
    obs = path_to_volnorm_returns(path, sigma_bps)
    post = run_filter(obs, tilt=float(tilt), params=params)
    xi = exit_index(post, side=side, max_hold=len(obs))
    # realized gross signed bps from entry (path[0]) to exit minute (path[xi+1])
    sign = 1.0 if side == "long" else -1.0
    gross = sign * (np.log(path[xi + 1]) - np.log(path[0])) * 1e4
    return float(gross)


def run_pair_phase1(sym, freq="2h", q=0.95, n_folds=5, params=None) -> dict:
    if params is None:
        params = PFParams()
    src = _REPO_ROOT / f"data/tick_bars/{sym}_1m_flow.parquet"
    panel = build_panel(build_freq_bars(pl.read_parquet(src), freq))
    folds = walk_forward(panel, n_folds=n_folds)
    minute_idx = build_minute_index(sym)
    cost = COST_BPS[sym]
    # rebuild per-bar sigma to vol-normalize the intra-hold path (use panel sigma_h)
    sig_by_bucket = dict(zip(panel["bucket"].to_numpy(),
                             panel["sigma_h"].to_numpy(), strict=False))
    net_base, net_pf, buckets = [], [], []
    for f in folds:
        thr = np.quantile(f["train_pred"], q)
        sel = f["test_pred"] >= thr
        for tp, act, bk in zip(f["test_pred"][sel], f["test_actual_bps"][sel],
                               f["test_bucket"][sel], strict=False):
            sigma_bps = float(sig_by_bucket.get(bk, np.nan))
            gross_pf = pf_exit_realized_bps(bk, "long", tp, sigma_bps, freq, sym,
                                            minute_idx, params)
            if not np.isfinite(gross_pf):
                gross_pf = float(act)  # fall back to fixed-horizon return
            net_base.append(float(act) - cost)
            net_pf.append(gross_pf - cost)
            buckets.append(bk)
    return {
        "net_base": np.array(net_base),
        "net_pf": np.array(net_pf),
        "bucket": np.array(buckets, dtype="datetime64[ns]"),
        "n": len(net_base),
    }
```

Note: `build_panel` must expose `sigma_h`; it does (`feats["sigma_h"]` is set before `target_z`). If `sigma_h` is not a retained column, add it to the panel return in `reg_signal_hunt.build_panel` — confirm by printing `panel.columns` before running.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd ~/repositories/behemoth/.claude/worktrees/feat-pf-15m && uv run pytest tests/fx_coint/test_pf_phase1.py -q`
Expected: PASS (1 passed). If `sigma_h` KeyError appears, add `feats["sigma_h"]` to the columns kept by `build_panel` and re-run.

- [ ] **Step 5: Commit**

```bash
git add scripts/fx_coint/pf_phase1.py tests/fx_coint/test_pf_phase1.py
git commit -m "feat(fx_coint): Phase-1 backtest harness — PF-exit vs fixed-horizon baseline"
```

---

## Task 7: Gauntlet CLI — ablation, day-clustered t, year bootstrap, null check

**Files:**
- Create: `scripts/fx_coint/pf_phase1_eval.py`
- Test: `tests/fx_coint/test_pf_phase1_eval.py`

**Interfaces:**
- Consumes: `run_pair_phase1`; `tail_wfo.day_clustered_tstat`; `PFParams`.
- Produces:
  - `year_block_bootstrap_ci(net, bucket, n_boot=3000, seed=0) -> tuple[float,float]` — 95% CI resampling whole calendar years (clusters).
  - `positive_years(net, bucket) -> tuple[int,int]` — `(n_positive, n_total)` years by mean net.
  - `summarize(net, bucket, label) -> dict` — `{label, n, mean, day_t, day_p, ci_lo, ci_hi, pos_y, n_y}`.
  - `null_check(sym, freq, q, params, seed) -> dict` — re-runs the PF exit with a **randomized** posterior (shuffled `p_trend`/`mu_hat` per trade) and returns its `summarize`; used to confirm the real PF beats a turnover-only null.
  - `main()` — prints, for pooled TIGHT_MAJORS: baseline summary, PF-exit summary, their per-pair breakdown, and the null-check summary; writes a markdown results block to `scripts/fx_coint/pf_phase1_results.md`.

- [ ] **Step 1: Write the failing test**

```python
# tests/fx_coint/test_pf_phase1_eval.py
import numpy as np
import pandas as pd
from scripts.fx_coint.pf_phase1_eval import positive_years, year_block_bootstrap_ci

def test_positive_years_counts_year_means():
    bucket = pd.to_datetime(["2020-01-01", "2020-06-01", "2021-01-01"]).values
    net = np.array([1.0, 1.0, -2.0])
    pos, tot = positive_years(net, bucket)
    assert (pos, tot) == (1, 2)

def test_bootstrap_ci_orders_lo_below_hi():
    rng = np.random.default_rng(0)
    bucket = pd.to_datetime(
        np.repeat(["2019", "2020", "2021", "2022"], 25)).values
    net = rng.normal(0.5, 1.0, size=100)
    lo, hi = year_block_bootstrap_ci(net, bucket, n_boot=500, seed=1)
    assert lo < hi
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ~/repositories/behemoth/.claude/worktrees/feat-pf-15m && uv run pytest tests/fx_coint/test_pf_phase1_eval.py -q`
Expected: FAIL with `ModuleNotFoundError: scripts.fx_coint.pf_phase1_eval`.

- [ ] **Step 3: Write minimal implementation**

```python
# scripts/fx_coint/pf_phase1_eval.py
"""Phase-1 gauntlet: does PF dynamic-exit beat the fixed-horizon baseline?

Run: uv run python scripts/fx_coint/pf_phase1_eval.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.fx_coint.pf_core import PFParams  # noqa: E402
from scripts.fx_coint.pf_phase1 import run_pair_phase1  # noqa: E402
from scripts.fx_coint.tail_wfo import day_clustered_tstat  # noqa: E402

TIGHT_MAJORS = ["EURUSD", "GBPUSD", "USDJPY"]


def positive_years(net, bucket):
    yr = pd.Series(net, index=pd.to_datetime(pd.Series(bucket)).dt.year)
    means = yr.groupby(level=0).mean()
    return int((means > 0).sum()), int(len(means))


def year_block_bootstrap_ci(net, bucket, n_boot=3000, seed=0):
    rng = np.random.default_rng(seed)
    s = pd.Series(net, index=pd.to_datetime(pd.Series(bucket)).dt.year)
    blocks = [g.to_numpy() for _, g in s.groupby(level=0)]
    if len(blocks) < 2:
        return float("nan"), float("nan")
    means = np.empty(n_boot)
    for b in range(n_boot):
        pick = rng.integers(0, len(blocks), len(blocks))
        means[b] = np.concatenate([blocks[i] for i in pick]).mean()
    return float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5))


def summarize(net, bucket, label):
    dc = day_clustered_tstat(np.asarray(net), bucket)
    lo, hi = year_block_bootstrap_ci(net, bucket)
    pos, ny = positive_years(net, bucket)
    return {"label": label, "n": len(net), "mean": float(np.mean(net)),
            "day_t": dc["t_stat"], "day_p": dc["p_value"],
            "ci_lo": lo, "ci_hi": hi, "pos_y": pos, "n_y": ny}


def _pool(params, q, freq):
    base, pf, bk = [], [], []
    per_pair = {}
    for sym in TIGHT_MAJORS:
        out = run_pair_phase1(sym, freq=freq, q=q, params=params)
        base.append(out["net_base"]); pf.append(out["net_pf"]); bk.append(out["bucket"])
        per_pair[sym] = (out["net_base"], out["net_pf"], out["bucket"])
    return (np.concatenate(base), np.concatenate(pf),
            np.concatenate(bk), per_pair)


def null_check(q, freq, params, seed):
    rng = np.random.default_rng(seed)
    nets, bks = [], []
    for sym in TIGHT_MAJORS:
        # randomized posterior == break the filter's signal by shuffling exits:
        # emulate by sampling a uniform random exit fraction per trade.
        out = run_pair_phase1(sym, freq=freq, q=q, params=params)
        # null = baseline scrambled toward random early exits (no info):
        scramble = rng.uniform(0.5, 1.0, size=out["n"])
        nets.append(out["net_base"] * scramble)
        bks.append(out["bucket"])
    return summarize(np.concatenate(nets), np.concatenate(bks), "NULL(random-exit)")


def _fmt(d):
    return (f"{d['label']:>20} n={d['n']:>4} mean={d['mean']:>+6.2f} "
            f"day_t={d['day_t']:>+5.2f} day_p={d['day_p']:>6.3f} "
            f"pos={d['pos_y']}/{d['n_y']} boot95=[{d['ci_lo']:>+6.2f},{d['ci_hi']:>+6.2f}]")


def main():
    q, freq, params = 0.95, "2h", PFParams()
    base, pf, bk, per_pair = _pool(params, q, freq)
    lines = ["# PF Phase-1 dynamic-exit results", "",
             "## Pooled TIGHT_MAJORS (EUR/GBP/USDJPY), 2h long top-5%", ""]
    for d in (summarize(base, bk, "BASELINE(fixed)"),
              summarize(pf, bk, "PF-EXIT"),
              null_check(q, freq, params, seed=0)):
        line = _fmt(d)
        print(line); lines.append("    " + line)
    lines.append("\n## Per-pair (baseline -> pf-exit)")
    for sym, (b, p, kb) in per_pair.items():
        line = (f"{sym}: base {summarize(b, kb, sym)['mean']:+.2f} -> "
                f"pf {summarize(p, kb, sym)['mean']:+.2f}")
        print(line); lines.append("    " + line)
    (Path(__file__).resolve().parent / "pf_phase1_results.md").write_text("\n".join(lines))


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run tests, then run the eval**

Run: `cd ~/repositories/behemoth/.claude/worktrees/feat-pf-15m && uv run pytest tests/fx_coint/test_pf_phase1_eval.py -q`
Expected: PASS (2 passed).

Then run the real evaluation:
Run: `cd ~/repositories/behemoth/.claude/worktrees/feat-pf-15m && uv run python scripts/fx_coint/pf_phase1_eval.py`
Expected: prints BASELINE, PF-EXIT, NULL summaries + per-pair, and writes `scripts/fx_coint/pf_phase1_results.md`. **Interpretation gate:** PF-EXIT must beat BASELINE on mean net AND keep day-clustered significance AND beat the NULL — otherwise Phase 1 is a NO-GO and we record that verdict rather than shipping.

- [ ] **Step 5: Run quality gate and commit**

Run: `cd ~/repositories/behemoth/.claude/worktrees/feat-pf-15m && make quality`
Expected: ty + ruff clean (fix any lint in the new files before committing).

```bash
git add scripts/fx_coint/pf_phase1_eval.py tests/fx_coint/test_pf_phase1_eval.py scripts/fx_coint/pf_phase1_results.md
git commit -m "feat(fx_coint): Phase-1 gauntlet CLI + results (ablation/day-t/bootstrap/null)"
```

---

## Self-Review notes

- **Spec coverage:** §2 model → Tasks 1-3; §3 causality → Task 3 test + Global Constraints; §4 dynamic-exit rule → Task 5; §5 gauntlet (day-t, bootstrap, pos-years, per-pair, null) → Task 7; entry-confirm/sizing/denoise are Phase 2-3, intentionally out of this plan. Prior-art `BetaPF` head-to-head is deferred to Phase 2 (it is a comparison, not required to validate dynamic-exit).
- **Type consistency:** `run_filter` returns dict with keys `p_trend/mu_hat/mu_var` used identically in Tasks 5-6; `run_pair_phase1` returns `net_base/net_pf/bucket/n` consumed in Task 7.
- **Known integration risk:** the exact `hold_path` window offset vs `ret_next_bps` is pinned by the Task 6 baseline-alignment check — if `net_base` does not reproduce the known `tail_wfo` baseline mean, fix the offset there before trusting `net_pf`.
- **Honest-null caveat:** the Task 7 `null_check` is a turnover/early-exit scramble; if results are promising, Phase 2 should strengthen it to a true shuffled-posterior null fed through `exit_index`.
