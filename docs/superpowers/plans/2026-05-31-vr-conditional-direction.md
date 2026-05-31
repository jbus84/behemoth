# vr_conditional_direction Seed Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a single causal ERA fade seed whose trade *side* is chosen per-bar by the trailing variance ratio — fade when mean-reverting (VR<0.95), continue when trending (VR>1.05), abstain in the dead-band — and validate it with the existing Bayesian edge layer across the 5 majors.

**Architecture:** The seed is a string program in `FADE_SEED_PROGRAMS` (`scripts/era_scalp/fade_seeds.py`). It reuses the existing causal `_FAIR` block (`dev = ew - p`, fair − mid) and the `vr_gated_fade` rolling variance-ratio machinery, then returns `dev` where VR<0.95, `-dev` where VR>1.05, NaN otherwise. Because `|out| == |dev|`, the harness's top-q entry selection (`evaluate_trades`) is regime-independent; only the side (`sign(out)`) flips. Validation reuses `scripts/era_scalp/bayes_edge.py` unchanged (it resolves `--seed-name` from `FADE_SEED_PROGRAMS`).

**Tech Stack:** Python, numpy, pytest, uv. No new dependencies. NumPyro/JAX already present for `bayes_edge`.

---

## File Structure

- `scripts/era_scalp/fade_seeds.py` — **Modify.** Add `"vr_conditional_direction"` to `FADE_SEED_PROGRAMS`; add one line to `RESEARCH_IDEAS`. Do NOT touch `BASELINE_SEED_NAMES` (no ERA-search expansion).
- `tests/era_scalp/test_fade_seeds.py` — **Modify.** Add the seed name to the existing presence + abstain lists; add three new tests (regime sign-mapping, magnitude invariant, dead-band abstention).
- `docs/analysis/era_fade_vr_conditional_2026-05-31.md` — **Create.** The Bayesian verdict evidence (Task 3, written from the real run's output).

---

### Task 1: Failing tests for the regime-conditional seed

**Files:**
- Test: `tests/era_scalp/test_fade_seeds.py`

The existing file already has `test_all_seeds_run_causal` (loops every seed → covers parse + causality probe + length for the new seed automatically) and `test_gated_seeds_abstain_sometimes`. Add the new seed to the two name lists and add three new tests. These reference `FADE_SEED_PROGRAMS["vr_conditional_direction"]`, which does not exist yet → fail with `KeyError`.

- [ ] **Step 1: Add helper builders and the new tests to the end of the file**

Append to `tests/era_scalp/test_fade_seeds.py`:

```python
def _vel_ctx(vel):
    """A FeatureContext whose vel_pips_h1 column is a chosen series (other columns zero)."""
    vel = np.asarray(vel, float)
    n = vel.shape[0]
    X = np.zeros((n, len(WHITELIST)))
    X[:, list(WHITELIST).index("vel_pips_h1")] = vel
    return FeatureContext(X=X, names=list(WHITELIST), hour=(np.arange(n) % 24).astype(float))


def _dev_ref(vel):
    """Replicate the seed's _FAIR block to get dev = fair - mid for assertions."""
    r = np.asarray(vel, float); n = r.shape[0]; a = 0.05
    p = np.cumsum(np.where(np.isfinite(r), r, 0.0))
    ew = np.empty(n); acc = p[0]
    for i in range(n):
        acc = (1 - a) * acc + a * p[i]; ew[i] = acc
    return ew - p


def test_vr_conditional_fades_in_reverting_regime():
    # Alternating increments => price oscillates => 20-step move ~0 => VR ~0 (<0.95) everywhere.
    # The whole finite set must be the FADE side: out == dev exactly.
    vel = np.where(np.arange(1500) % 2 == 0, 1.0, -1.0)
    sig, err, _ = run_program(FADE_SEED_PROGRAMS["vr_conditional_direction"], _vel_ctx(vel),
                              required_fn="signal")
    assert err is None
    dev = _dev_ref(vel); fin = np.isfinite(sig)
    assert fin.any()
    assert np.allclose(sig[fin], dev[fin]), "reverting regime must return +dev (fade)"


def test_vr_conditional_continues_in_trending_regime():
    # Positively autocorrelated increments (AR(1), phi=0.9) => persistent => VR>1 => CONTINUE side.
    rng = np.random.default_rng(0)
    e = rng.standard_normal(1500); vel = np.zeros(1500)
    for i in range(1, 1500):
        vel[i] = 0.9 * vel[i - 1] + e[i]
    sig, err, _ = run_program(FADE_SEED_PROGRAMS["vr_conditional_direction"], _vel_ctx(vel),
                              required_fn="signal")
    assert err is None
    dev = _dev_ref(vel); fin = np.isfinite(sig)
    assert fin.sum() > 0
    cont = np.isclose(sig[fin], -dev[fin])
    assert cont.mean() > 0.7, f"trending regime should mostly CONTINUE (-dev); got {cont.mean():.2f}"


def test_vr_conditional_magnitude_equals_dev():
    # Invariant: |signal| == |dev| wherever finite (only the side flips by regime).
    ctx = _ctx()
    sig, err, _ = run_program(FADE_SEED_PROGRAMS["vr_conditional_direction"], ctx,
                              required_fn="signal")
    assert err is None
    dev = _dev_ref(ctx.col("vel_pips_h1")); fin = np.isfinite(sig)
    assert fin.any()
    assert np.allclose(np.abs(sig[fin]), np.abs(dev[fin]))


def test_vr_conditional_deadband_abstains_more_than_reverting():
    # A random walk (iid increments) has VR ~1 => most bars land in the [0.95,1.05] dead-band
    # and abstain, so its NaN fraction exceeds the strongly-reverting series' NaN fraction.
    rng = np.random.default_rng(2)
    rw = rng.standard_normal(1500)
    revert = np.where(np.arange(1500) % 2 == 0, 1.0, -1.0)
    src = FADE_SEED_PROGRAMS["vr_conditional_direction"]
    sig_rw, e1, _ = run_program(src, _vel_ctx(rw), required_fn="signal")
    sig_rev, e2, _ = run_program(src, _vel_ctx(revert), required_fn="signal")
    assert e1 is None and e2 is None
    assert np.isnan(sig_rw).mean() > np.isnan(sig_rev).mean()
```

- [ ] **Step 2: Add the new seed to the two existing name lists**

In `test_expected_seeds_present`, extend the tuple passed to the first loop:

```python
def test_expected_seeds_present():
    for name in ("fair_fade", "vr_gated_fade", "autocorr_gated_fade",
                 "efficiency_gated_fade", "extreme_fade", "vr_conditional_direction"):
        assert name in FADE_SEED_PROGRAMS
    for b in BASELINE_SEED_NAMES:
        assert b in FADE_SEED_PROGRAMS
```

In `test_gated_seeds_abstain_sometimes`, add the new seed to the loop tuple:

```python
def test_gated_seeds_abstain_sometimes():
    ctx = _ctx()
    for name in ("vr_gated_fade", "autocorr_gated_fade", "efficiency_gated_fade",
                 "extreme_fade", "vr_conditional_direction"):
        sig, err, _ = run_program(FADE_SEED_PROGRAMS[name], ctx, required_fn="signal")
        assert err is None
        assert np.isnan(sig).any(), f"{name} never abstains"
```

- [ ] **Step 3: Run the new tests to verify they fail**

Run: `uv run pytest tests/era_scalp/test_fade_seeds.py -q`
Expected: FAIL — the four new tests and `test_expected_seeds_present` error with `KeyError: 'vr_conditional_direction'`.

- [ ] **Step 4: Commit the failing tests**

```bash
git add tests/era_scalp/test_fade_seeds.py
git commit -m "test(era-scalp): failing tests for vr_conditional_direction seed

Regime sign-mapping (fade when VR<0.95, continue when VR>1.05), |signal|==|dev| invariant,
dead-band abstention; plus seed added to presence + abstain lists."
```

---

### Task 2: Implement the seed + research idea

**Files:**
- Modify: `scripts/era_scalp/fade_seeds.py`

- [ ] **Step 1: Add the seed to `FADE_SEED_PROGRAMS`**

In `scripts/era_scalp/fade_seeds.py`, add this entry to the `FADE_SEED_PROGRAMS` dict (place it after `"vr_gated_fade"`, since it reuses the same VR machinery). It is the `vr_gated_fade` body with the gate replaced by a dead-band direction switch:

```python
    "vr_conditional_direction": (
        "def signal(ctx):\n" + _FAIR +
        "    W = 240; qv = 20\n"
        "    d1 = np.diff(p, prepend=p[0])\n"
        "    dq = np.empty(n); dq[:qv] = 0.0; dq[qv:] = p[qv:] - p[:-qv]\n"
        "    def rollvar(x):\n"
        "        c1 = np.concatenate(([0.0], np.cumsum(x)))\n"
        "        c2 = np.concatenate(([0.0], np.cumsum(x * x)))\n"
        "        k = np.arange(n); lo = np.maximum(0, k - W); m = (k - lo).astype(float)\n"
        "        ms = np.where(m > 0, m, 1.0)\n"
        "        mu = (c1[k] - c1[lo]) / ms\n"
        "        return (c2[k] - c2[lo]) / ms - mu * mu, m\n"
        "    v1, m = rollvar(d1); vq, _ = rollvar(dq)\n"
        "    vr = vq / (qv * v1 + 1e-12)\n"
        "    out = np.full(n, np.nan); ok = m >= 60\n"
        "    out = np.where(ok & (vr < 0.95), dev, out)   # mean-reverting -> FADE\n"
        "    out = np.where(ok & (vr > 1.05), -dev, out)  # trending -> CONTINUE\n"
        "    return out\n"
    ),
```

- [ ] **Step 2: Add a research-idea line**

Append to the `RESEARCH_IDEAS` list in the same file (after the existing "Combine:" entry):

```python
    "Regime-conditional direction: do not assume reversion. Use the SAME causal trailing variance "
    "ratio to pick the side per bar - fade (toward fair) when VR<1 (mean-reverting), but go WITH the "
    "move (continuation) when VR>1 (trending), abstaining in a dead-band near 1. One causal rule, no "
    "per-symbol direction fitting; recovers EUR/AUD fade and GBP continuation from the regime alone.",
```

- [ ] **Step 3: Run the seed tests to verify they pass**

Run: `uv run pytest tests/era_scalp/test_fade_seeds.py -q`
Expected: PASS (all tests, including `test_all_seeds_run_causal` which now also probes the new seed for causality).

- [ ] **Step 4: Run the full era_scalp suite to confirm no regressions**

Run: `uv run pytest tests/era_scalp -q`
Expected: PASS (all era_scalp tests green).

- [ ] **Step 5: Commit the implementation**

```bash
git add scripts/era_scalp/fade_seeds.py
git commit -m "feat(era-scalp): vr_conditional_direction seed (regime-chosen side)

Single causal program: side = fade if trailing VR<0.95 else continue if VR>1.05, abstain in the
[0.95,1.05] dead-band. |signal|=|dev| so top-q entry selection is regime-independent; only the side
flips. Encodes the EUR/AUD-fade vs GBP-continuation split as a causal rule, no per-symbol PnL peeking.
Reuses the vr_gated_fade VR machinery; added to RESEARCH_IDEAS, not to BASELINE_SEED_NAMES."
```

---

### Task 3: Bayesian verdict across the 5 majors + evidence doc

**Files:**
- Create: `docs/analysis/era_fade_vr_conditional_2026-05-31.md`

This task runs the real velocity data through the unchanged `bayes_edge` CLI and records the result. The numbers below are placeholders to be replaced with the actual run output — do NOT invent them.

- [ ] **Step 1: Run the Bayesian verdict at the headline grid point**

Run:
```bash
uv run python -m scripts.era_scalp.bayes_edge \
  --seed-name vr_conditional_direction --q 0.99 --h 100 \
  --out /tmp/era_fade/vr_conditional_verdict.md
```
Expected: prints `wrote /tmp/era_fade/vr_conditional_verdict.md`. Read that file for the per-symbol + pooled posterior table (P(edge>0), mean, 94% CI).

- [ ] **Step 2: (Optional robustness) Run two more grid points**

Run the same command with `--q 0.95 --h 200` and `--q 0.90 --h 400`, writing to distinct `--out` paths under `/tmp/era_fade/`. Read each. These check the verdict is not knife-edge on a single (q,h).

- [ ] **Step 3: Write the evidence doc**

Create `docs/analysis/era_fade_vr_conditional_2026-05-31.md` using the ACTUAL numbers from Steps 1–2. Structure (fill the table from the real verdict files):

```markdown
# ERA fade — vr_conditional_direction Bayesian verdict (2026-05-31)

Single causal seed: side chosen per-bar by trailing variance ratio — fade (dev) when VR<0.95,
continue (-dev) when VR>1.05, abstain in the [0.95,1.05] dead-band. |signal|=|dev| so entry
selection is regime-independent; only the side flips. No per-symbol direction fitting.

## Headline (q=0.99, h=100), 5 majors

| symbol | P(edge>0) | mean (pips) | 94% CI |
|---|---|---|---|
| EURUSD | <fill> | <fill> | <fill> |
| GBPUSD | <fill> | <fill> | <fill> |
| AUDUSD | <fill> | <fill> | <fill> |
| USDCHF | <fill> | <fill> | <fill> |
| USDJPY | <fill> | <fill> | <fill> |
| **Pooled** | <fill> | <fill> | <fill> |

## Comparison vs prior verdicts

| | pooled P(edge>0) | EUR | AUD | GBP |
|---|---|---|---|---|
| fade (vr_gated_fade)        | 0.410 | 0.994 | 0.983 | 0.072 (neg) |
| continuation (flipped)      | 0.086 | 0.000 | 0.000 | 1.000 |
| **vr_conditional_direction**| <fill>| <fill>| <fill>| <fill> |

## Verdict

<State plainly whether the regime rule recovered credible positives on EUR/AUD (fade) and GBP
(continuation) from VR alone, and whether pooled P(edge>0) beat the single-direction fade's 0.41.
If a symbol lost its edge (dead-band abstained too much / VR mistimed its regime), say so — a null
is a result. Repeat the binding caveat: all nets are mid-to-mid / flat-cost; the tick-exact
realistic-cost gate remains the downstream check.>

## Robustness (other grid points)

<one line each for (q=0.95,h=200) and (q=0.90,h=400): pooled + EUR/AUD/GBP, noting stability.>
```

- [ ] **Step 4: Commit the evidence**

```bash
git add docs/analysis/era_fade_vr_conditional_2026-05-31.md
git commit -m "docs(era-scalp): vr_conditional_direction Bayesian verdict — regime rule across 5 majors

Whether the single causal VR-conditional direction rule recovers EUR/AUD fade + GBP continuation
from the regime alone, and pooled vs the 0.41 single-direction fade. Mid-to-mid/flat-cost caveat
stands; tick-exact gate remains downstream."
```

- [ ] **Step 5: Push**

```bash
git push
```

---

## Self-Review

**1. Spec coverage:**
- Seed added to `FADE_SEED_PROGRAMS`, not `BASELINE_SEED_NAMES` → Task 2 Steps 1, 5. ✓
- `RESEARCH_IDEAS` line → Task 2 Step 2. ✓
- Dead-band switch (fade VR<0.95 / continue VR>1.05 / abstain) → Task 2 Step 1 code. ✓
- `|signal|==|dev|` invariant → Task 1 `test_vr_conditional_magnitude_equals_dev`. ✓
- Causal + parses → covered by existing `test_all_seeds_run_causal` (loops all seeds) — noted in Task 1 preamble. ✓
- Fade-in-reverting / continue-in-trending / dead-band tests → Task 1 Steps 1. ✓
- Bayesian verdict across 5 majors + evidence doc → Task 3. ✓
- bayes_edge reused unchanged → Task 3 uses the CLI as-is. ✓

**2. Placeholder scan:** The only `<fill>` markers are in Task 3's evidence-doc template, which is correct by design — the numbers must come from the real run, and Step 3 explicitly says use actual numbers, do not invent. No placeholders in code or tests.

**3. Type consistency:** `run_program(src, ctx, required_fn="signal") -> (sig, err, logs)` matches sandbox usage throughout. `FeatureContext(X=, names=, hour=)` and `ctx.col(name)` match existing `_ctx`/context.py. `_dev_ref` replicates `_FAIR` exactly (a=0.05, EWMA recursion). Seed entry mirrors `vr_gated_fade` (W=240, qv=20, rollvar) verbatim except the final gate→switch lines. Consistent.
