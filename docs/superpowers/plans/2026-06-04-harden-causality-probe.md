# Harden the Causality Probe (Plan B) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close two known blind spots in `scripts/era_scalp/sandbox.causality_probe`: too few cut points (a program non-causal only at unprobed indices passes), and finiteness-pattern leakage (future rows are overwritten with *finite* noise, so a program leaking through `isfinite(future).sum()` is invisible).

**Architecture:** Raise the default `n_cuts` from 2 to 5, and in each perturbation overwrite a fraction of the future rows with `NaN` in addition to the large finite noise — so both value leakage and NaN-pattern leakage change a past output and are caught. Add regression tests proving a finiteness-leak program is now rejected while genuine causal programs still pass.

**Tech Stack:** numpy, pytest. Changes in `scripts/era_scalp/sandbox.py` + `tests/era_scalp/test_sandbox_causality.py`.

---

### Background

`scripts/era_scalp/sandbox.py:75` perturbs future rows with `rng.standard_normal(...) * 10.0` — always finite. A program that reads `np.isfinite(future_col).sum()` (or any NaN-count statistic over future rows) sees an identical finiteness pattern in the clean and perturbed runs, so its past output does not change and the probe wrongly accepts it. Also `n_cuts=2` only probes 2 interior indices; non-causality localized elsewhere slips through.

Note: `scripts/era/sandbox.py` has a sibling `causality_probe` for the cross-symbol (`CrossSectionContext`) search. This plan hardens the `era_scalp` (single-symbol `FeatureContext`) probe only; mirroring the change into `scripts/era/sandbox.py` is listed as a follow-up.

---

### Task 1: More cut points + NaN injection in the probe

**Files:**
- Modify: `scripts/era_scalp/sandbox.py:75-97` (`causality_probe`)
- Test: `tests/era_scalp/test_sandbox_causality.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/era_scalp/test_sandbox_causality.py`:

```python
# A program that leaks the NaN-pattern of FUTURE rows into a PAST output.
# 'spread_z' is column 0 in NAMES. It counts how many future spread_z are NaN
# and writes that count into every past bar, so perturbing future finiteness
# changes the past output -> must be rejected.
FINITENESS_LEAK = (
    "def signal(ctx):\n"
    "    x = ctx.col('spread_z')\n"
    "    n = x.shape[0]\n"
    "    out = np.empty(n)\n"
    "    for i in range(n):\n"
    "        out[i] = np.isfinite(x[i + 1:]).sum()  # reads future finiteness\n"
    "    return out\n"
)


def test_probe_rejects_finiteness_leak():
    ctx = _ctx()
    sig, err, _ = run_program(FINITENESS_LEAK, ctx)
    assert err is None
    ok, reason = causality_probe(FINITENESS_LEAK, ctx, sig)
    assert not ok and ("future" in reason.lower() or "causal" in reason.lower())


def test_probe_default_uses_five_cuts():
    import inspect
    sig = inspect.signature(causality_probe)
    assert sig.parameters["n_cuts"].default == 5
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/era_scalp/test_sandbox_causality.py::test_probe_rejects_finiteness_leak tests/era_scalp/test_sandbox_causality.py::test_probe_default_uses_five_cuts -v`
Expected: `test_probe_default_uses_five_cuts` FAILS (default is 2); `test_probe_rejects_finiteness_leak` FAILS (probe accepts it because future stays finite).

- [ ] **Step 3: Harden the probe**

Replace `causality_probe` in `scripts/era_scalp/sandbox.py` with:

```python
def causality_probe(src, ctx, clean_signal, n_cuts: int = 5, seed: int = 0,
                    required_fn: str = "signal", nan_frac: float = 0.3):
    """Reject programs whose past output depends on future bars.

    For each of `n_cuts` interior cut points k, every row at index > k is
    replaced with large finite noise AND a `nan_frac` fraction of those future
    rows are set to NaN. This catches both value leakage and NaN-pattern
    (finiteness) leakage: any op reading future rows perturbs a past output and
    is rejected. Returns (ok, reason).
    """
    n = ctx.n_bars
    if n < 6:
        return True, "too-short-to-probe"
    rng = np.random.default_rng(seed)
    clean = np.asarray(clean_signal, float)
    cuts = [max(1, n * (i + 1) // (n_cuts + 1)) for i in range(n_cuts)]
    for k in cuts:
        X2 = ctx.X.copy()
        fut = X2[k + 1 :, :]
        fut[:] = rng.standard_normal(fut.shape) * 10.0
        if fut.size:
            nan_mask = rng.random(fut.shape) < nan_frac
            fut[nan_mask] = np.nan
        X2[k + 1 :, :] = fut
        hour2 = None
        if ctx.hour is not None:
            hour2 = ctx.hour.copy()
            hour2[k + 1 :] = rng.integers(0, 24, size=hour2[k + 1 :].shape).astype(float)
        ctx2 = FeatureContext(X=X2, names=ctx.names, hour=hour2)
        sig2, err, _ = run_program(src, ctx2, timeout=10.0, required_fn=required_fn)
        if err is not None:
            return False, f"non-causal: errors under future perturbation at k={k}: {err}"
        if not _arrays_match(clean[: k + 1], np.asarray(sig2, float)[: k + 1]):
            return False, f"non-causal: signal[:{k + 1}] changed when future bars perturbed"
    return True, "ok"
```

- [ ] **Step 4: Run the full causality suite**

Run: `uv run pytest tests/era_scalp/test_sandbox_causality.py -v`
Expected: PASS (all). The existing `test_run_program_ok_and_probe_accepts_causal`, `test_probe_rejects_forward`, and `test_static_check_requires_signal` must still pass — a genuinely causal program is unaffected by future NaNs.

- [ ] **Step 5: Guard against false rejection of NaN-robust causal programs**

Append one more test to `tests/era_scalp/test_sandbox_causality.py` and re-run the suite:

```python
# A causal program that tolerates NaNs in its OWN bar must still be accepted.
CAUSAL_NAN_SAFE = (
    "def signal(ctx):\n"
    "    x = ctx.col('vel_z_h1')\n"
    "    return np.where(np.isfinite(x), x, 0.0)\n"
)


def test_probe_accepts_nan_safe_causal():
    ctx = _ctx()
    sig, err, _ = run_program(CAUSAL_NAN_SAFE, ctx)
    assert err is None
    ok, reason = causality_probe(CAUSAL_NAN_SAFE, ctx, sig)
    assert ok, reason
```

Run: `uv run pytest tests/era_scalp/test_sandbox_causality.py -v`
Expected: PASS (all).

- [ ] **Step 6: Commit**

```bash
git add scripts/era_scalp/sandbox.py tests/era_scalp/test_sandbox_causality.py
git commit -m "feat(era-scalp): harden causality probe (5 cuts + NaN-pattern injection)"
```

---

### Task 2: Spot-check the probe does not break discovery throughput

**Files:**
- Test: `tests/era_scalp/test_sandbox_causality.py`

- [ ] **Step 1: Add a timing-bounded smoke test**

The probe now re-runs the sandbox `n_cuts=5` times per program. Confirm the seed programs still pass and the wall-time is acceptable on a realistic-size context.

```python
from scripts.era_scalp.fade_seeds import FADE_SEED_PROGRAMS


def test_seed_programs_pass_hardened_probe():
    ctx = _ctx(n=2000, seed=3)
    for name, src in FADE_SEED_PROGRAMS.items():
        sig, err, _ = run_program(src, ctx)
        assert err is None, f"{name}: {err}"
        ok, reason = causality_probe(src, ctx, sig)
        assert ok, f"{name}: {reason}"
```

- [ ] **Step 2: Run it**

Run: `uv run pytest tests/era_scalp/test_sandbox_causality.py::test_seed_programs_pass_hardened_probe -v`
Expected: PASS. If any seed FAILS, that is a genuine causality bug in the seed surfaced by the stronger probe — investigate before proceeding (do not weaken the probe to make it pass).

- [ ] **Step 3: Commit**

```bash
git add tests/era_scalp/test_sandbox_causality.py
git commit -m "test(era-scalp): all fade seeds pass the hardened causality probe"
```

---

### Self-Review checklist

- **Spec coverage:** more cuts (Task 1, default 5) ✓; NaN-pattern injection ✓; finiteness-leak rejection test ✓; NaN-safe causal acceptance test ✓; throughput/seed regression (Task 2) ✓.
- **Type consistency:** `causality_probe(..., n_cuts=5, ..., nan_frac=0.3)` — new `nan_frac` kwarg has a default so all existing callers (`cost_aware_score`, `score_program`, the run drivers) are unaffected.
- **Placeholders:** none.
- **Follow-up (out of scope):** mirror the NaN-injection + 5-cut change into `scripts/era/sandbox.causality_probe` for the cross-symbol search; ship as its own PR.
