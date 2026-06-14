# Microprice + VPIN Seed Branches (Plan C) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the two highest-value missing research families to the fade-seed taxonomy — an imbalance-weighted **microprice fair value** (Stoikov 2018) and a **flow-toxicity / VPIN gate** (Easley–López de Prado–O'Hara) — implemented as causal, numpy-only seed programs over the existing feature whitelist.

**Architecture:** Each new branch needs four coordinated edits in `scripts/era_scalp/fade_seeds.py`: a `BRANCH_TAXONOMY` entry, a `SEED_BRANCH_TAGS` mapping for its seed, a `FADE_SEED_PROGRAMS` reference program, and a `RICH_TEMPLATES` prompt. Because L1 book sizes are not in the whitelist, both seeds use documented bar-level proxies: microprice uses the close-within-range position (`hl_pos_delta_tick`) as an imbalance proxy; VPIN uses an EWMA of |signed flow| / total flow from `bar_return_sign` × `tick_volume`.

**Tech Stack:** numpy-only program source (string), pytest. All changes in `scripts/era_scalp/fade_seeds.py` + a new test file.

---

### Background

`fade_seeds.BRANCH_TAXONOMY` covers 12 literature families but two canonical modern microstructure tools are absent: (1) **microprice** — the imbalance-weighted fair value that replaces mid as the unbiased short-horizon price expectation; every current seed estimates fair value as a plain EWMA of cumulative return. (2) **VPIN** — order-flow toxicity, the standard adverse-selection gate ("don't fade into informed flow"). `flow_intensity` (Hawkes magnitude) is a cousin but does not measure directional toxicity.

Available whitelist features (`scripts/era_scalp/load_splits.py:61`): `bar_return_sign`, `tick_volume`, `hl_pos_delta_tick`, `high_pos_tick`, `low_pos_tick`, `bar_range_pips`, `vel_pips_h1`, etc. The proxies below use only these.

---

### Task 1: Microprice fair-value branch

**Files:**
- Modify: `scripts/era_scalp/fade_seeds.py` (`BRANCH_TAXONOMY`, `SEED_BRANCH_TAGS`, `FADE_SEED_PROGRAMS`, `RICH_TEMPLATES`)
- Test: `tests/era_scalp/test_new_branch_seeds.py` (create)

- [ ] **Step 1: Write the failing test**

```python
# tests/era_scalp/test_new_branch_seeds.py
import numpy as np

from scripts.era_scalp.context import FeatureContext
from scripts.era_scalp.fade_seeds import (
    BRANCH_TAXONOMY,
    FADE_SEED_PROGRAMS,
    RICH_TEMPLATES,
    SEED_BRANCH_TAGS,
)
from scripts.era_scalp.sandbox import causality_probe, run_program

NAMES = [
    "spread_pips", "spread_z", "tick_volume", "tick_rate_hz", "tick_rate_z",
    "tick_burst", "tick_burst_score", "high_pos_tick", "low_pos_tick",
    "hl_pos_delta_tick", "bar_return_sign", "vel_pips_h1", "vel_pips_h2",
    "vel_pips_h5", "vel_pips_h10", "vel_z_h1", "vel_z_h2", "vel_z_h5",
    "vel_z_h10", "accel_pips", "hour_utc", "bar_range_pips",
]


def _ctx(n=1500, seed=0):
    rng = np.random.default_rng(seed)
    X = rng.standard_normal((n, len(NAMES)))
    # keep proxies in plausible ranges
    X[:, NAMES.index("tick_volume")] = np.abs(X[:, NAMES.index("tick_volume")]) * 50 + 1
    X[:, NAMES.index("hl_pos_delta_tick")] = np.clip(X[:, NAMES.index("hl_pos_delta_tick")], -1, 1)
    X[:, NAMES.index("bar_return_sign")] = np.sign(X[:, NAMES.index("bar_return_sign")])
    X[:, NAMES.index("bar_range_pips")] = np.abs(X[:, NAMES.index("bar_range_pips")]) + 0.5
    return FeatureContext(X=X, names=list(NAMES), hour=(np.arange(n) % 24).astype(float))


def test_microprice_branch_registered():
    assert "microprice" in BRANCH_TAXONOMY
    assert "microprice" in RICH_TEMPLATES
    assert SEED_BRANCH_TAGS["microprice_fade"] == "microprice"
    assert "microprice_fade" in FADE_SEED_PROGRAMS


def test_microprice_seed_runs_and_is_causal():
    ctx = _ctx()
    src = FADE_SEED_PROGRAMS["microprice_fade"]
    sig, err, _ = run_program(src, ctx)
    assert err is None, err
    assert sig.shape == (ctx.n_bars,)
    assert np.isfinite(sig).sum() > 0
    ok, reason = causality_probe(src, ctx, sig)
    assert ok, reason
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/era_scalp/test_new_branch_seeds.py::test_microprice_branch_registered -v`
Expected: FAIL with `AssertionError` / `KeyError` (branch not registered).

- [ ] **Step 3: Register the microprice branch**

In `scripts/era_scalp/fade_seeds.py`:

3a. Add to `BRANCH_TAXONOMY` (after the `"seasonality"` entry):

```python
    "microprice": "Imbalance-weighted fair value (Stoikov microprice proxy): shift fair toward the side the bar closed on; fade deviation from microprice rather than from a symmetric EWMA.",
```

3b. Add to `SEED_BRANCH_TAGS`:

```python
    "microprice_fade": "microprice",
```

3c. Add to `FADE_SEED_PROGRAMS`:

```python
    "microprice_fade": (
        "def signal(ctx):\n"
        "    r = ctx.col('vel_pips_h1'); imb = ctx.col('hl_pos_delta_tick')\n"
        "    rng_ = ctx.col('bar_range_pips'); n = r.shape[0]\n"
        "    # Baseline EWMA fair value of cumulative price\n"
        "    a = 0.05; p = np.cumsum(np.where(np.isfinite(r), r, 0.0))\n"
        "    ew = np.empty(n); acc = p[0]\n"
        "    for i in range(n): acc = (1 - a) * acc + a * p[i]; ew[i] = acc\n"
        "    # Microprice adjustment: close-within-range imbalance nudges fair toward\n"
        "    # the pressured side, scaled by the bar's own range (Stoikov microprice proxy).\n"
        "    k = 0.5\n"
        "    adj = np.where(np.isfinite(imb) & np.isfinite(rng_), k * imb * rng_, 0.0)\n"
        "    micro_fair = ew + adj\n"
        "    dev = micro_fair - p  # fade deviation from microprice\n"
        "    return dev\n"
    ),
```

3d. Add to `RICH_TEMPLATES`:

```python
    "microprice": (
        "BRANCH: microprice — imbalance-weighted fair value (Stoikov 2018 proxy)\n"
        "FORMULA: micro_fair = EWMA(cumsum(returns)) + k * imbalance * bar_range;\n"
        "         dev = micro_fair - cumsum(returns); side = sign(dev) (fade).\n"
        "RATIONALE: Stoikov (2018, 'The micro-price'). The mid is a biased estimate of"
        " the short-horizon price; the microprice tilts toward the heavier side of the"
        " book. We lack L1 sizes at 100-tick bars, so we proxy imbalance by where the bar"
        " closed within its high-low range (hl_pos_delta_tick): a close near the high =\n"
        " buy pressure. Fading deviation from microprice (not symmetric EWMA) removes the"
        " systematic bias that makes plain-mid fades lose to informed flow.\n"
        "PROXY LIMITATION: hl_pos_delta_tick is a coarse imbalance proxy; true microprice"
        " needs quote sizes. State this when reasoning about the edge ceiling.\n"
        "ALLOWED VARIATIONS: k ∈ {0.25, 0.5, 1.0}; alpha ∈ {0.03, 0.05, 0.10}\n"
        "REFERENCE IMPLEMENTATION:\n"
        "```python\n"
        "def signal(ctx):\n"
        "    r = ctx.col('vel_pips_h1'); imb = ctx.col('hl_pos_delta_tick')\n"
        "    rng_ = ctx.col('bar_range_pips'); n = r.shape[0]; a = 0.05\n"
        "    p = np.cumsum(np.where(np.isfinite(r), r, 0.0))\n"
        "    ew = np.empty(n); acc = p[0]\n"
        "    for i in range(n): acc = (1 - a) * acc + a * p[i]; ew[i] = acc\n"
        "    adj = np.where(np.isfinite(imb) & np.isfinite(rng_), 0.5 * imb * rng_, 0.0)\n"
        "    return (ew + adj) - p\n"
        "```\n"
        "FAILURE PATTERN: k too large (>1.5) makes the microprice adjustment dominate the"
        " EWMA fair value, turning the signal into a pure close-position momentum proxy.\n"
    ),
```

- [ ] **Step 4: Run the microprice tests**

Run: `uv run pytest tests/era_scalp/test_new_branch_seeds.py -k microprice -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add scripts/era_scalp/fade_seeds.py tests/era_scalp/test_new_branch_seeds.py
git commit -m "feat(era-scalp): microprice fair-value seed branch (Stoikov proxy)"
```

---

### Task 2: VPIN flow-toxicity gate branch

**Files:**
- Modify: `scripts/era_scalp/fade_seeds.py`
- Test: `tests/era_scalp/test_new_branch_seeds.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/era_scalp/test_new_branch_seeds.py`:

```python
def test_vpin_branch_registered():
    assert "flow_toxicity" in BRANCH_TAXONOMY
    assert "flow_toxicity" in RICH_TEMPLATES
    assert SEED_BRANCH_TAGS["vpin_gated_fade"] == "flow_toxicity"
    assert "vpin_gated_fade" in FADE_SEED_PROGRAMS


def test_vpin_seed_runs_and_is_causal():
    ctx = _ctx(seed=1)
    src = FADE_SEED_PROGRAMS["vpin_gated_fade"]
    sig, err, _ = run_program(src, ctx)
    assert err is None, err
    assert sig.shape == (ctx.n_bars,)
    assert np.isfinite(sig).sum() > 0      # the gate must let SOME bars through
    ok, reason = causality_probe(src, ctx, sig)
    assert ok, reason
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/era_scalp/test_new_branch_seeds.py::test_vpin_branch_registered -v`
Expected: FAIL (branch not registered).

- [ ] **Step 3: Register the flow_toxicity (VPIN) branch**

In `scripts/era_scalp/fade_seeds.py`:

3a. `BRANCH_TAXONOMY`:

```python
    "flow_toxicity": "Gate fades by order-flow toxicity (VPIN proxy): abstain when the EWMA of |signed flow| / total flow is high (informed/directional flow); fade only into balanced, uninformed flow.",
```

3b. `SEED_BRANCH_TAGS`:

```python
    "vpin_gated_fade": "flow_toxicity",
```

3c. `FADE_SEED_PROGRAMS`:

```python
    "vpin_gated_fade": (
        "def signal(ctx):\n"
        "    r = ctx.col('vel_pips_h1'); sgn = ctx.col('bar_return_sign')\n"
        "    vol = ctx.col('tick_volume'); n = r.shape[0]\n"
        "    # Baseline EWMA fair-value deviation\n"
        "    a = 0.05; p = np.cumsum(np.where(np.isfinite(r), r, 0.0))\n"
        "    ew = np.empty(n); acc = p[0]\n"
        "    for i in range(n): acc = (1 - a) * acc + a * p[i]; ew[i] = acc\n"
        "    dev = ew - p\n"
        "    # VPIN proxy: EWMA(|signed volume|) / EWMA(total volume) (Easley-LdP-O'Hara).\n"
        "    v = np.where(np.isfinite(vol), vol, 0.0)\n"
        "    sg = np.where(np.isfinite(sgn), sgn, 0.0)\n"
        "    signed = np.abs(sg * v)\n"
        "    b = 0.05\n"
        "    es = np.empty(n); et = np.empty(n); accs = signed[0]; acct = v[0] + 1e-9\n"
        "    for i in range(n):\n"
        "        accs = (1 - b) * accs + b * signed[i]; es[i] = accs\n"
        "        acct = (1 - b) * acct + b * v[i]; et[i] = acct\n"
        "    vpin = es / (et + 1e-9)\n"
        "    # Gate: fade only when toxicity is low (balanced flow). Abstain above 0.6.\n"
        "    gate_ok = vpin <= 0.6\n"
        "    out = np.where(gate_ok, dev, np.nan)\n"
        "    return out\n"
    ),
```

3d. `RICH_TEMPLATES`:

```python
    "flow_toxicity": (
        "BRANCH: flow_toxicity — VPIN order-flow toxicity gate\n"
        "FORMULA: VPIN ≈ EWMA(|sign·volume|) / EWMA(volume); gate opens when VPIN <= thr.\n"
        "RATIONALE: Easley, López de Prado & O'Hara (2012, RFS, 'Flow Toxicity and"
        " Liquidity'). High VPIN = order flow is one-sided/informed; fading into informed"
        " flow is adverse selection and loses. We proxy bucketed VPIN with a causal EWMA"
        " of |signed flow| over total flow from bar_return_sign × tick_volume, and fade"
        " only when toxicity is low (balanced, uninformed two-sided flow).\n"
        "WHY thr=0.6: toxicity above ~0.6 marks sustained one-sided pressure where the"
        " fade has no counterparty edge; below it the flow is balanced enough to revert.\n"
        "ALLOWED VARIATIONS: thr ∈ {0.5, 0.6, 0.7}; b (EWMA) ∈ {0.02, 0.05, 0.10}\n"
        "REFERENCE IMPLEMENTATION:\n"
        "```python\n"
        "def signal(ctx):\n"
        "    r = ctx.col('vel_pips_h1'); sgn = ctx.col('bar_return_sign')\n"
        "    vol = ctx.col('tick_volume'); n = r.shape[0]; a = 0.05; b = 0.05\n"
        "    p = np.cumsum(np.where(np.isfinite(r), r, 0.0))\n"
        "    ew = np.empty(n); acc = p[0]\n"
        "    for i in range(n): acc = (1 - a) * acc + a * p[i]; ew[i] = acc\n"
        "    dev = ew - p\n"
        "    v = np.where(np.isfinite(vol), vol, 0.0); sg = np.where(np.isfinite(sgn), sgn, 0.0)\n"
        "    signed = np.abs(sg * v)\n"
        "    es = np.empty(n); et = np.empty(n); accs = signed[0]; acct = v[0] + 1e-9\n"
        "    for i in range(n):\n"
        "        accs = (1-b)*accs + b*signed[i]; es[i] = accs\n"
        "        acct = (1-b)*acct + b*v[i]; et[i] = acct\n"
        "    vpin = es / (et + 1e-9)\n"
        "    return np.where(vpin <= 0.6, dev, np.nan)\n"
        "```\n"
        "FAILURE PATTERN: thr too low (<0.4) gates out almost every bar (no trades);"
        " thr too high (>0.85) is effectively no gate and reverts to the baseline fade.\n"
    ),
```

- [ ] **Step 4: Run the VPIN tests**

Run: `uv run pytest tests/era_scalp/test_new_branch_seeds.py -k vpin -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add scripts/era_scalp/fade_seeds.py tests/era_scalp/test_new_branch_seeds.py
git commit -m "feat(era-scalp): VPIN flow-toxicity gate seed branch (Easley-LdP-O'Hara)"
```

---

### Task 3: Cross-branch recombination prompts for the two new branches

**Files:**
- Modify: `scripts/era_scalp/fade_seeds.py` (`CROSS_BRANCH_PROMPTS`)
- Test: `tests/era_scalp/test_new_branch_seeds.py`

- [ ] **Step 1: Write the failing test**

Append:

```python
from scripts.era_scalp.fade_seeds import CROSS_BRANCH_INDEX


def test_new_branches_have_cross_prompts():
    # Each new branch should pair with mean_reversion_gate for recombination.
    assert ("microprice", "mean_reversion_gate") in CROSS_BRANCH_INDEX
    assert ("flow_toxicity", "mean_reversion_gate") in CROSS_BRANCH_INDEX
    # Index is symmetric.
    assert ("mean_reversion_gate", "microprice") in CROSS_BRANCH_INDEX
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/era_scalp/test_new_branch_seeds.py::test_new_branches_have_cross_prompts -v`
Expected: FAIL (pairs absent from index).

- [ ] **Step 3: Add the cross-branch prompts**

Add these two entries to the `CROSS_BRANCH_PROMPTS` dict in `scripts/era_scalp/fade_seeds.py` (before the closing `}` near line 909). `CROSS_BRANCH_INDEX` is built from this dict and adds the reverse pairs automatically, so only the forward pair is needed:

```python
    ("microprice", "mean_reversion_gate"): (
        "COMBINATION: microprice + mean_reversion_gate\n"
        "SYNERGY: The variance-ratio gate decides WHEN to fade (mean-reverting regimes);"
        " the microprice decides the unbiased fair value to fade TOWARD. Plain-mid fades"
        " are biased by order-flow imbalance even inside a reverting regime; using the"
        " microprice as the fair anchor removes that bias so the gated fade reverts to the"
        " true short-horizon price rather than a flow-distorted mid.\n"
        "Write a single `signal(ctx)` that combines both ideas.\n"
    ),
    ("flow_toxicity", "mean_reversion_gate"): (
        "COMBINATION: flow_toxicity + mean_reversion_gate\n"
        "SYNERGY: The VR gate identifies mean-reverting regimes but is blind to WHO is"
        " trading. A statistically reverting window driven by toxic one-sided flow still"
        " loses to adverse selection. Adding the VPIN gate blocks high-toxicity bars so"
        " the fade only fires when the regime reverts AND the flow is balanced.\n"
        "Write a single `signal(ctx)` that combines both ideas.\n"
    ),
```

- [ ] **Step 4: Run the full new-branch suite**

Run: `uv run pytest tests/era_scalp/test_new_branch_seeds.py -v`
Expected: PASS (all).

- [ ] **Step 5: Commit**

```bash
git add scripts/era_scalp/fade_seeds.py tests/era_scalp/test_new_branch_seeds.py
git commit -m "feat(era-scalp): cross-branch recombination prompts for microprice + flow_toxicity"
```

---

### Self-Review checklist

- **Spec coverage:** microprice branch (Task 1: taxonomy + tag + seed + template) ✓; VPIN branch (Task 2, same four edits) ✓; cross-branch prompts (Task 3) ✓.
- **Type consistency:** seed names `microprice_fade` / `vpin_gated_fade` and branch keys `microprice` / `flow_toxicity` used identically across `SEED_BRANCH_TAGS`, `FADE_SEED_PROGRAMS`, `RICH_TEMPLATES`, `BRANCH_TAXONOMY`, and `CROSS_BRANCH_PROMPTS`.
- **Causality:** both seeds use only causal EWMA / cumulative ops and pass `causality_probe` (asserted in tests) — they remain causal under the hardened probe from Plan B.
- **Placeholders:** none.
- **Follow-up (out of scope):** score the two new seeds on real holdout via `bayes_edge` / `per_symbol_sweep` and report whether either survives BH-FDR; ship findings as a verdict doc.
