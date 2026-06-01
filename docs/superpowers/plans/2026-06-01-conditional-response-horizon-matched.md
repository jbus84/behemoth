# Horizon-matched Conditional-Response Family Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refactor `conditional_response_fade` through a `_cond_response_src(H)` generator and add `_h200`/`_h400` members so each learns its conditional response over its own horizon, then test the horizon-mismatch hypothesis with a matched-horizon `bayes_edge` gate.

**Architecture:** The parent seed body is identical except for the `H` literal. Extract it to a generator function; register `conditional_response_fade = _cond_response_src(100)` (unchanged behaviour), `conditional_response_fade_h200`, `conditional_response_fade_h400`. The dynamic per-symbol fade-vs-continue learning is unchanged; only the learning horizon varies. No scorer/engine change.

**Tech Stack:** Python, numpy, pytest, uv. No new deps. `bayes_edge` CLI reused unchanged.

**Branch:** `era-condresp-horizon` (created, spec committed). Do NOT touch main.

---

## File Structure

- `scripts/era_scalp/fade_seeds.py` — **Modify.** Add `_cond_response_src(H)` generator; replace the `conditional_response_fade` dict entry with `_cond_response_src(100)`; add `_h200`/`_h400` entries; add a `RESEARCH_IDEAS` line. `conditional_response_signed` and `BASELINE_SEED_NAMES` untouched.
- `tests/era_scalp/test_fade_seeds.py` — **Modify.** Add the two names to presence/abstain lists; add a generator-embeds-H test and a family-behaviour test.
- `docs/analysis/era_conditional_response_horizon_matched_2026-05-31.md` — **Create.** Matched-horizon verdict evidence.

---

### Task 1: Failing tests for the horizon-matched family

**Files:** Test: `tests/era_scalp/test_fade_seeds.py`

The file already has `_ar_level_ctx`, `_fade_fraction`, `_dev_ref`, `run_program`, `causality_probe`, and the loops `test_all_seeds_run_causal` / `test_gated_seeds_abstain_sometimes`. Add two new tests and extend the two literal name lists. They fail with `KeyError` until Task 2.

- [ ] **Step 1: Append two tests to the end of the file**

```python
def test_cond_response_family_embeds_horizon():
    # Each family member must hard-code its own learning horizon H.
    assert "H = 100" in FADE_SEED_PROGRAMS["conditional_response_fade"]
    assert "H = 200" in FADE_SEED_PROGRAMS["conditional_response_fade_h200"]
    assert "H = 400" in FADE_SEED_PROGRAMS["conditional_response_fade_h400"]


def test_cond_response_family_learns_fade_and_preserves_magnitude():
    # The dynamic fade-on-reverting-history behaviour and |signal|==|dev| invariant survive the H change.
    for name in ("conditional_response_fade", "conditional_response_fade_h200",
                 "conditional_response_fade_h400"):
        ctx = _ar_level_ctx(n=5000)
        sig, err, _ = run_program(FADE_SEED_PROGRAMS[name], ctx, required_fn="signal")
        assert err is None, f"{name}: {err}"
        dev = _dev_ref(ctx.col("vel_pips_h1"))
        fin = np.isfinite(sig)
        assert fin.sum() > 0, f"{name} never trades on reverting history"
        assert np.allclose(np.abs(sig[fin]), np.abs(dev[fin])), f"{name} broke |signal|==|dev|"
        frac = float(np.mean(np.sign(sig[fin]) == np.sign(dev[fin])))
        assert frac > 0.6, f"{name} should learn FADE on reverting history; fade-fraction={frac:.2f}"
```

(Note `_ar_level_ctx(n=5000)` uses a longer series so the longer-horizon members H=200/400 still accumulate ≥ MINEP completed episodes after warmup.)

- [ ] **Step 2: Add the two names to the literal lists**

In `test_expected_seeds_present`, add `"conditional_response_fade_h200", "conditional_response_fade_h400"` to the first loop's tuple.
In `test_gated_seeds_abstain_sometimes`, add the same two names to its loop tuple.

- [ ] **Step 3: Run to verify failure**

Run: `uv run pytest tests/era_scalp/test_fade_seeds.py -q`
Expected: FAIL — `KeyError: 'conditional_response_fade_h200'` in the new tests and the two list tests.

- [ ] **Step 4: Commit**

```bash
git add tests/era_scalp/test_fade_seeds.py
git commit -m "test(era-scalp): failing tests for horizon-matched conditional-response family

Generator embeds H per member (100/200/400); family preserves dynamic fade-on-reverting-history and
|signal|==|dev|; presence + abstain lists extended."
```

---

### Task 2: Generator + family members

**Files:** Modify: `scripts/era_scalp/fade_seeds.py`

- [ ] **Step 1: Add the `_cond_response_src(H)` generator**

Add this function ABOVE the `FADE_SEED_PROGRAMS` dict definition (just after `_FAIR` is defined). It is the current `conditional_response_fade` body with the `H` literal interpolated:

```python
def _cond_response_src(H: int) -> str:
    return (
        "def signal(ctx):\n" + _FAIR +
        f"    H = {H}; W = 240; MINEP = 20\n"
        "    ad = np.abs(np.where(np.isfinite(dev), dev, 0.0))\n"
        "    c1 = np.concatenate(([0.0], np.cumsum(ad)))\n"
        "    c2 = np.concatenate(([0.0], np.cumsum(ad * ad)))\n"
        "    k = np.arange(n); lo = np.maximum(0, k - W); mwin = (k - lo).astype(float)\n"
        "    ms = np.where(mwin > 0, mwin, 1.0)\n"
        "    mu = (c1[k] - c1[lo]) / ms; var = (c2[k] - c2[lo]) / ms - mu * mu\n"
        "    sd = np.sqrt(np.clip(var, 1e-12, None))\n"
        "    ext = (mwin >= 60) & (ad > mu + 2.0 * sd)\n"
        "    pf = np.full(n, np.nan); pf[:n - H] = p[H:] - p[:n - H]\n"
        "    fr = np.sign(dev) * pf\n"
        "    valid = ext & np.isfinite(fr)\n"
        "    resolved = np.full(n, np.nan)\n"
        "    j = np.nonzero(valid)[0]; resolved[j + H] = fr[j]\n"
        "    fin = np.isfinite(resolved)\n"
        "    rv = np.where(fin, resolved, 0.0); cnt = np.where(fin, 1.0, 0.0)\n"
        "    nep = np.cumsum(cnt)\n"
        "    R = np.cumsum(rv) / np.maximum(nep, 1.0)\n"
        "    direction = np.where(R >= 0.0, 1.0, -1.0)\n"
        "    out = np.where(nep >= MINEP, dev * direction, np.nan)\n"
        "    return out\n"
    )
```

- [ ] **Step 2: Replace the `conditional_response_fade` dict entry and add the family**

In `FADE_SEED_PROGRAMS`, replace the entire existing `"conditional_response_fade": ( ... ),` entry (the multi-line string block, currently ~lines 92–115) with these three entries:

```python
    "conditional_response_fade": _cond_response_src(100),
    "conditional_response_fade_h200": _cond_response_src(200),
    "conditional_response_fade_h400": _cond_response_src(400),
```

Leave `"conditional_response_signed": ( ... )` exactly as-is.

- [ ] **Step 3: Add a `RESEARCH_IDEAS` line**

Append to the `RESEARCH_IDEAS` list:

```python
    "Horizon-matched conditional response: learn the conditional reversion outcome over the SAME horizon "
    "the trade is held (internal H == exit h), not a fixed H. The fixed-H seed was strong only where its "
    "learning horizon coincided with the holding horizon; matching them tests whether the (q,h) collapse "
    "was a horizon mismatch rather than a horizon-specific edge.",
```

- [ ] **Step 4: Run the seed tests**

Run: `uv run pytest tests/era_scalp/test_fade_seeds.py -q`
Expected: PASS (the two new tests + all existing). If a family member's fade-fraction is marginally under 0.6, the cause would be too few completed episodes at the longer H — confirm the test uses `_ar_level_ctx(n=5000)`; do NOT weaken the assertion or change the seed logic.

- [ ] **Step 5: Run the full era_scalp suite + lint**

Run: `uv run pytest tests/era_scalp -q` (all pass; `test_all_seeds_run_causal` now probes all three family members for causality).
Run: `make lint` (Expected: `All checks passed!`).

- [ ] **Step 6: Commit**

```bash
git add scripts/era_scalp/fade_seeds.py
git commit -m "feat(era-scalp): horizon-matched conditional-response family (H=100/200/400)

Refactor conditional_response_fade through _cond_response_src(H); add h200/h400 members so each learns R
over its own horizon. conditional_response_fade == _cond_response_src(100), behaviour unchanged. Dynamic
per-symbol fade/continue learning unchanged; only the learning horizon varies. Not in BASELINE_SEED_NAMES."
```

---

### Task 3: Matched-horizon Bayesian gate + evidence doc

**Files:** Create: `docs/analysis/era_conditional_response_horizon_matched_2026-05-31.md`

Numbers are filled from the REAL runs — do not invent them.

- [ ] **Step 1: Run the matched-horizon gate (9 runs)**

For each `(seed, h)` in `(conditional_response_fade, 100)`, `(conditional_response_fade_h200, 200)`, `(conditional_response_fade_h400, 400)`, and each `q` in `0.90, 0.95, 0.99`:
```bash
uv run python -m scripts.era_scalp.bayes_edge --seed-name <seed> --h <h> --q <q> \
  --out /tmp/era_fade/hm_<seed>_q<q>.md
```
Read each output file (pooled + per-symbol posterior). The seed's internal H always equals the `--h` it is run at (that is the whole point — only matched pairs are run).

- [ ] **Step 2: Write the evidence doc**

Create `docs/analysis/era_conditional_response_horizon_matched_2026-05-31.md` with the ACTUAL numbers:

```markdown
# ERA fade — horizon-matched conditional-response Bayesian verdict (2026-06-01)

Each seed learns its conditional response R over its OWN horizon H and is evaluated at the matching exit
h (internal-H == exit-h). Tests whether the parent's (q,h) collapse was a horizon mismatch. The dynamic
per-symbol fade-vs-continue learning is unchanged from PR #284.

## Matched-horizon results (each seed at its own h; q swept)

### H=100 (conditional_response_fade @ h=100)
| q | pooled P(edge>0) | EUR | AUD | GBP | CHF | JPY |
|---|---|---|---|---|---|---|
| 0.99 | <fill> | <fill> | <fill> | <fill> | <fill> | <fill> |
| 0.95 | <fill> | ... | | | | |
| 0.90 | <fill> | ... | | | | |

### H=200 (conditional_response_fade_h200 @ h=200)
<same table>

### H=400 (conditional_response_fade_h400 @ h=400)
<same table>

## Verdict
<State plainly: does the matched-horizon strength hold across q AND across all three horizons (pooled
stays high, no symbol credibly negative)? If yes => the parent's collapse was the internal-H != exit-h
mismatch, and the h-matched family is the first horizon-robust entry-conditioned rule (under the
matched-horizon deployment model). If matched runs still degrade => the edge was ~100-bar-specific; say
so. A null is a result.>

## Honesty note on the gate
This is a MORE LENIENT criterion than the Phase-2A gate: instead of one signal robust across all (q,h),
it allows a different h-matched seed per holding horizon. Defensible (deploy the seed for the horizon you
trade) but explicitly weaker than "one robust signal".

## Caveat
Mid-to-mid / flat-cost; the tick-exact realistic-round-trip-cost gate remains the binding downstream check.
```

- [ ] **Step 3: Commit + push**

```bash
git add docs/analysis/era_conditional_response_horizon_matched_2026-05-31.md
git commit -m "docs(era-scalp): horizon-matched conditional-response verdict (internal-H == exit-h)"
git push
```

---

## Self-Review

**1. Spec coverage:**
- `_cond_response_src(H)` generator → Task 2 Step 1. ✓
- `conditional_response_fade=_cond_response_src(100)` + `_h200` + `_h400` → Task 2 Step 2. ✓
- `RESEARCH_IDEAS` line → Task 2 Step 3. ✓
- `signed` + `BASELINE_SEED_NAMES` untouched → only the named edits in Task 2. ✓
- generator-embeds-H test → Task 1 `test_cond_response_family_embeds_horizon`. ✓
- family causal + |signal|=|dev| + fades-on-reverting → Task 1 `test_cond_response_family_learns_fade_and_preserves_magnitude` (+ existing `test_all_seeds_run_causal` for causality). ✓
- presence/abstain lists → Task 1 Step 2. ✓
- matched-horizon bayes_edge gate + evidence → Task 3. ✓
- gate-leniency honesty note → Task 3 evidence template. ✓

**2. Placeholder scan:** Only `<fill>` / `<seed>` / `<h>` / `<q>` in Task 3's evidence template + CLI loop — correct by design (filled from real runs). Generator body in Task 2 is complete (no `...`). No code placeholders.

**3. Type consistency:** `_cond_response_src(H: int) -> str`; `run_program(src, ctx, required_fn="signal") -> (sig, err, logs)`; `_ar_level_ctx(n=...)`, `_dev_ref`, `_fade_fraction` are existing helpers; the generator body is byte-identical to the current `conditional_response_fade` except `f"    H = {H}; ..."`. Family names consistent across Task 1 (tests), Task 2 (registration), Task 3 (runs). Consistent.
