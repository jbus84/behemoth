# Phase 2A — Conditional-Response Seeds + Robustness-Gated Scorer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add entry-conditioned conditional-response direction seeds (side learned per-bar from a causal online mean of how the symbol's own past extreme dislocations resolved) and a robustness-gated `PooledTradeScorer` aggregate, then validate with the existing `bayes_edge` multi-(q,h) gate.

**Architecture:** Seeds are string programs in `FADE_SEED_PROGRAMS` reusing the `_FAIR` block; they emit `out = dev * direction` where `direction = ±1` is set by the sign of a causal running mean `R[k]` of completed-episode fade outcomes. `|out| = |dev|`, so only the side changes. The scorer gains an `aggregate` param (`"max"` default, `"robust"` = `mean−std` across the (q,h) grid) so the search can't reward a knife-edge cell.

**Tech Stack:** Python, numpy, pytest, uv. No new deps. Per the spec, implement **2 of the 3** spec'd variants now — `conditional_response_fade` (base) and `conditional_response_signed` (asymmetric); defer `conditional_response_decay` as a fast-follow (its per-bar EWMA adds risk without testing the core idea).

**Branch:** `era-conditional-response` (already created, spec committed). Do NOT touch main.

---

## File Structure

- `scripts/era_scalp/fade_seeds.py` — **Modify.** Add `conditional_response_fade` + `conditional_response_signed` to `FADE_SEED_PROGRAMS`; add a `RESEARCH_IDEAS` line. Not added to `BASELINE_SEED_NAMES`.
- `scripts/era_scalp/trade_score.py` — **Modify.** Add `aggregate` param to `PooledTradeScorer`.
- `scripts/era_scalp/run_era_fade.py` — **Modify.** Thread `aggregate="robust"` into `run_search`.
- `tests/era_scalp/test_fade_seeds.py` — **Modify.** Add seed behaviour tests + name-list entries.
- `tests/era_scalp/test_trade_score.py` — **Modify.** Add aggregate tests.
- `docs/analysis/era_regime_conditional_response_2026-05-31.md` — **Create.** Verdict evidence.

---

### Task 1: Failing tests for the conditional-response seeds

**Files:** Test: `tests/era_scalp/test_fade_seeds.py`

The file already has helpers `_ctx`, `_vel_ctx`, `_dev_ref` and loops `test_all_seeds_run_causal` / `test_gated_seeds_abstain_sometimes` over every seed. Add the two new names to the literal lists and add three behaviour tests. These fail with `KeyError` until Task 2.

- [ ] **Step 1: Add a level-AR(1) reverting context helper and three tests at the end of the file**

```python
def _ar_level_ctx(n=3000, phi=0.95, seed=0):
    # Mean-reverting PRICE level (AR(1), phi<1): extreme deviations revert => fading them pays.
    rng = np.random.default_rng(seed)
    p = np.zeros(n)
    for t in range(1, n):
        p[t] = phi * p[t - 1] + rng.standard_normal()
    vel = np.diff(p, prepend=p[0])
    return _vel_ctx(vel)


def _ar_increment_ctx(n=3000, phi=0.9, seed=0):
    # Positively autocorrelated INCREMENTS (momentum): extreme moves continue => fading them loses.
    rng = np.random.default_rng(seed)
    e = rng.standard_normal(n)
    vel = np.zeros(n)
    for t in range(1, n):
        vel[t] = phi * vel[t - 1] + e[t]
    return _vel_ctx(vel)


def _fade_fraction(seed_name, ctx):
    sig, err, _ = run_program(FADE_SEED_PROGRAMS[seed_name], ctx, required_fn="signal")
    assert err is None
    dev = _dev_ref(ctx.col("vel_pips_h1"))
    fin = np.isfinite(sig)
    assert fin.sum() > 0
    # fraction of finite bars where the seed chose the FADE side (sign(out) == sign(dev))
    return float(np.mean(np.sign(sig[fin]) == np.sign(dev[fin]))), fin


def test_conditional_response_fades_on_reverting_history():
    # When extreme dislocations have historically reverted, the learned direction is FADE.
    frac, _ = _fade_fraction("conditional_response_fade", _ar_level_ctx())
    assert frac > 0.6, f"reverting history should learn FADE; fade-fraction={frac:.2f}"


def test_conditional_response_learns_direction_from_history():
    # Relative, robust property: the seed fades MORE on a reverting history than on a
    # momentum/continuation history. This is the core 'learns direction from the event' claim and
    # does not depend on fragile absolute phase arithmetic.
    frac_revert, _ = _fade_fraction("conditional_response_fade", _ar_level_ctx())
    frac_trend, _ = _fade_fraction("conditional_response_fade", _ar_increment_ctx())
    assert frac_revert > frac_trend, (
        f"should fade more on reverting ({frac_revert:.2f}) than trending ({frac_trend:.2f})")


def test_conditional_response_magnitude_equals_dev():
    # Invariant: |signal| == |dev| wherever finite (only the side flips).
    ctx = _ar_level_ctx()
    sig, err, _ = run_program(FADE_SEED_PROGRAMS["conditional_response_fade"], ctx,
                              required_fn="signal")
    assert err is None
    dev = _dev_ref(ctx.col("vel_pips_h1"))
    fin = np.isfinite(sig)
    assert fin.any()
    assert np.allclose(np.abs(sig[fin]), np.abs(dev[fin]))
```

- [ ] **Step 2: Add the two new seed names to the existing literal lists**

In `test_expected_seeds_present`, extend the first loop's tuple with `"conditional_response_fade", "conditional_response_signed"`.
In `test_gated_seeds_abstain_sometimes`, add both names to its loop tuple (they abstain via the `nep >= MINEP` / `mwin >= 60` guards).

- [ ] **Step 3: Run to verify failure**

Run: `uv run pytest tests/era_scalp/test_fade_seeds.py -q`
Expected: FAIL with `KeyError: 'conditional_response_fade'` in the new tests + the two list tests.

- [ ] **Step 4: Commit**

```bash
git add tests/era_scalp/test_fade_seeds.py
git commit -m "test(era-scalp): failing tests for conditional-response seeds

Reverting-history => learns FADE; relative fade-fraction(reverting) > fade-fraction(trending);
|signal|==|dev| invariant; plus seed names added to presence + abstain lists."
```

---

### Task 2: Implement the conditional-response seeds

**Files:** Modify: `scripts/era_scalp/fade_seeds.py`

- [ ] **Step 1: Add both seeds to `FADE_SEED_PROGRAMS` (after `extreme_fade`)**

The base seed. Every term is causal (depends only on bars ≤ k) and O(n) (cumsum; no nested loop). `pf[j] = p[j+H]-p[j]` is known at bar `j+H`, so each episode's outcome is written at its RESOLUTION index `j+H`; the cumulative mean at `k` therefore sees only episodes resolved by `k`.

```python
    "conditional_response_fade": (
        "def signal(ctx):\n" + _FAIR +
        "    H = 100; W = 240; MINEP = 20\n"
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
    ),
```

The signed variant — separate running response for up- vs down-dislocations (they can resolve asymmetrically), selected by the current dislocation's sign:

```python
    "conditional_response_signed": (
        "def signal(ctx):\n" + _FAIR +
        "    H = 100; W = 240; MINEP = 20\n"
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
        "    def runmean(mask):\n"
        "        rs = np.full(n, np.nan); j = np.nonzero(mask & np.isfinite(fr))[0]\n"
        "        rs[j + H] = fr[j]; fn = np.isfinite(rs)\n"
        "        ct = np.cumsum(np.where(fn, 1.0, 0.0))\n"
        "        return np.cumsum(np.where(fn, rs, 0.0)) / np.maximum(ct, 1.0), ct\n"
        "    Rp, ep = runmean(ext & (dev > 0)); Rn, en = runmean(ext & (dev <= 0))\n"
        "    use_p = dev > 0\n"
        "    R = np.where(use_p, Rp, Rn); nep = np.where(use_p, ep, en)\n"
        "    direction = np.where(R >= 0.0, 1.0, -1.0)\n"
        "    out = np.where(nep >= MINEP, dev * direction, np.nan)\n"
        "    return out\n"
    ),
```

- [ ] **Step 2: Add a `RESEARCH_IDEAS` line**

```python
    "Entry-conditioned conditional response: do not gate direction by a trailing-average regime "
    "(which misclassifies the mean-reverting majors at the tail dislocations). Instead maintain a "
    "causal online mean of how the symbol's OWN past EXTREME dislocations resolved over the next H "
    "bars (completed episodes only), and fade when reversion has paid, continue when it has not. "
    "Empirical conditional-response/reversion function; learns direction per symbol with no peeking.",
```

- [ ] **Step 3: Run the seed tests**

Run: `uv run pytest tests/era_scalp/test_fade_seeds.py -q`
Expected: PASS. If `test_conditional_response_fades_on_reverting_history` is marginally under 0.6 due to synthetic noise, STRENGTHEN the series (increase `n` to 5000 or `phi` to 0.97 in `_ar_level_ctx`) — do NOT weaken the assertion. The relative test (`..._learns_direction_from_history`) must hold; if it does not, the seed logic is wrong (debug the seed, not the test).

- [ ] **Step 4: Run the full era_scalp suite**

Run: `uv run pytest tests/era_scalp -q`
Expected: PASS (incl. `test_all_seeds_run_causal` probing the two new seeds for causality, and the perf-sensitive tests — the seeds are O(n)).

- [ ] **Step 5: Commit**

```bash
git add scripts/era_scalp/fade_seeds.py
git commit -m "feat(era-scalp): conditional-response direction seeds (entry-conditioned)

Side learned per-bar from a causal online mean R[k] of how the symbol's own past EXTREME dislocations
resolved over H bars (completed episodes only, written at resolution index j+H; O(n) cumsum). Fade when
reversion has paid, continue when it has not. base + signed (up/down-asymmetric) variants; |signal|=|dev|.
Fixes the vr_conditional null (local regime != average regime). Not in BASELINE_SEED_NAMES."
```

---

### Task 3: Robustness-gated scorer aggregate

**Files:** Modify: `scripts/era_scalp/trade_score.py`, `tests/era_scalp/test_trade_score.py`

- [ ] **Step 1: Write failing aggregate tests**

Append to `tests/era_scalp/test_trade_score.py`:

```python
def test_robust_aggregate_penalises_knife_edge(monkeypatch):
    import scripts.era_scalp.trade_score as ts
    # Inject a deterministic per-cell score: one cell great, the rest poor.
    cells = iter([5.0] + [-1.0] * (len(ts.GRID_Q) * len(ts.GRID_H) - 1))
    monkeypatch.setattr(ts, "pooled_task_score", lambda frames: next(cells))
    sc = ts.PooledTradeScorer(_by_sym(), symbols=["EURUSD", "GBPUSD"], aggregate="robust")
    s, _ = sc.score("def signal(ctx):\n    return ctx.col('vel_pips_h1')\n", "validation")
    # robust = mean - std; a 1-good-8-bad vector must score BELOW its max (5.0) and below its mean.
    assert s < 5.0
    import numpy as np
    vals = np.array([5.0] + [-1.0] * (len(ts.GRID_Q) * len(ts.GRID_H) - 1))
    assert np.isclose(s, vals.mean() - vals.std())


def test_max_aggregate_is_default_and_unchanged(monkeypatch):
    import numpy as np
    import scripts.era_scalp.trade_score as ts
    vals = [2.0, -1.0, 0.5, 3.0, -2.0, 1.0, 0.0, 4.0, -0.5][: len(ts.GRID_Q) * len(ts.GRID_H)]
    monkeypatch.setattr(ts, "pooled_task_score", lambda frames, _it=iter(vals): next(_it))
    sc = ts.PooledTradeScorer(_by_sym(), symbols=["EURUSD", "GBPUSD"])  # default aggregate
    s, _ = sc.score("def signal(ctx):\n    return ctx.col('vel_pips_h1')\n", "validation")
    assert np.isclose(s, max(vals))
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/era_scalp/test_trade_score.py -q`
Expected: FAIL — `PooledTradeScorer.__init__` has no `aggregate` kwarg / robust path not implemented.

- [ ] **Step 3: Implement the aggregate param**

In `scripts/era_scalp/trade_score.py`, add `numpy` import if absent (`import numpy as np`), extend `__init__`, and replace the grid-aggregation tail of `score`:

```python
    def __init__(self, splits_by_symbol: dict, symbols: list[str], timeout: float = 10.0,
                 aggregate: str = "max"):
        self.splits = splits_by_symbol
        self.symbols = symbols
        self.pip = {s: _pip_size(s) for s in symbols}
        self.timeout = timeout
        assert aggregate in ("max", "robust"), aggregate
        self.aggregate = aggregate
```

Replace the final scoring loop (the `best = -1e9` block) with cell collection + aggregation:

```python
        cells = []
        for q in GRID_Q:
            for h in GRID_H:
                frames = []
                for sym in self.symbols:
                    d = self.splits[sym][split]
                    frames.append(evaluate_trades(sigs[sym], d.mid, d.cost, d.test_month,
                                                  self.pip[sym], q, h))
                cells.append(pooled_task_score(frames))
        arr = np.asarray(cells, float)
        if self.aggregate == "robust":
            agg = float(arr.mean() - arr.std())
        else:
            agg = float(arr.max())
        return agg, first_logs
```

- [ ] **Step 4: Run scorer tests + existing scorer tests**

Run: `uv run pytest tests/era_scalp/test_trade_score.py -q`
Expected: PASS (new tests + the pre-existing `test_pooled_scorer_runs_causal` / `test_pooled_scorer_rejects_noncausal`).

- [ ] **Step 5: Thread `aggregate="robust"` into the fade driver**

In `scripts/era_scalp/run_era_fade.py` `run_search`, add an `aggregate: str = "robust"` parameter to the signature and pass it through:

```python
def run_search(splits_by_symbol, symbols, budget, writer=propose_program, ideas=None,
               seed: int = 0, cache_dir: str = "/tmp/era_fade_cache", p_recombine: float = 0.3,
               seed_programs=None, aggregate: str = "robust"):
    ideas = ideas or RESEARCH_IDEAS
    seed_programs = seed_programs or FADE_SEED_PROGRAMS
    scorer = PooledTradeScorer(splits_by_symbol, symbols=symbols, aggregate=aggregate)
```

- [ ] **Step 6: Run full era_scalp suite**

Run: `uv run pytest tests/era_scalp -q`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add scripts/era_scalp/trade_score.py scripts/era_scalp/run_era_fade.py tests/era_scalp/test_trade_score.py
git commit -m "feat(era-scalp): robustness-gated scorer aggregate (mean-std over q,h grid)

PooledTradeScorer gains aggregate=('max' default | 'robust'); robust = mean-std across the (q,h) grid so
the search cannot reward a knife-edge cell (the bias behind the vr_conditional q99/h100 mirage).
run_era_fade.run_search now uses aggregate='robust'. Default preserved for back-compat."
```

---

### Task 4: Bayesian verdict across the 5 majors + evidence doc

**Files:** Create: `docs/analysis/era_regime_conditional_response_2026-05-31.md`

Numbers below are filled from the REAL runs — do not invent them.

- [ ] **Step 1: Run the multi-(q,h) verdict for both seeds**

For `seed` in `conditional_response_fade`, `conditional_response_signed`, and for `(q,h)` in `(0.99,100)`, `(0.95,200)`, `(0.90,400)`:
```bash
uv run python -m scripts.era_scalp.bayes_edge --seed-name <seed> --q <q> --h <h> \
  --out /tmp/era_fade/<seed>_q<q>_h<h>.md
```
Read each output (per-symbol + pooled posterior).

- [ ] **Step 2: Write the evidence doc**

Create `docs/analysis/era_regime_conditional_response_2026-05-31.md` with the ACTUAL numbers. Structure:

```markdown
# ERA fade — conditional-response (entry-conditioned) Bayesian verdict (2026-05-31)

Side learned per-bar from a causal online mean of how the symbol's own past EXTREME dislocations
resolved over H=100 bars (completed episodes only). Fixes the vr_conditional null: the regime is
measured at the event, not as a trailing average, and learned per symbol with no peeking.

## conditional_response_fade — multi-(q,h)

| grid | pooled P(edge>0) | EUR | AUD | GBP | CHF | JPY |
|---|---|---|---|---|---|---|
| q=0.99,h=100 | <fill> | <fill> | <fill> | <fill> | <fill> | <fill> |
| q=0.95,h=200 | <fill> | ... | | | | |
| q=0.90,h=400 | <fill> | ... | | | | |

## conditional_response_signed — multi-(q,h)
<same table>

## Comparison vs prior verdicts (q=0.99,h=100)
| | pooled | EUR | AUD | GBP |
|---|---|---|---|---|
| vr_gated_fade | 0.410 | 0.994 | 0.983 | 0.072 |
| vr_conditional_direction | 0.511 | 0.508 | 0.050 | 0.985 |
| conditional_response_fade | <fill> | | | |
| conditional_response_signed | <fill> | | | |

## Verdict
<State plainly: is either seed credibly positive AND robust across (q,h) — i.e. it does NOT collapse to
credibly-negative at a different cell the way vr_conditional did? Did the learned conditional response
recover EUR/AUD-fade and GBP-continue from the event alone? If it is another knife-edge or a null, say so
— a null is a result. Repeat the binding caveat: mid-to-mid/flat-cost; tick-exact cost gate downstream.>
```

- [ ] **Step 3: Commit + push**

```bash
git add docs/analysis/era_regime_conditional_response_2026-05-31.md
git commit -m "docs(era-scalp): conditional-response Bayesian verdict — entry-conditioned direction across 5 majors"
git push
```

---

## Self-Review

**1. Spec coverage:**
- Conditional-response seeds (causal online R[k], O(n), |out|=|dev|) → Task 2 Step 1. Spec named 3 variants; plan implements 2 (base + signed) and explicitly defers `decay` (YAGNI, noted in Tech Stack). ✓
- RESEARCH_IDEAS line → Task 2 Step 2. ✓
- Not in BASELINE_SEED_NAMES → Task 2 (only FADE_SEED_PROGRAMS edited). ✓
- Robustness-gated scorer (`mean-std`, default `max`) → Task 3 Steps 3. ✓
- Driver uses robust → Task 3 Step 5. ✓
- Causality/parse → existing `test_all_seeds_run_causal` loop (Task 1 preamble). ✓
- Seed behaviour (learns-fade on reverting, relative learns-direction, magnitude) → Task 1. ✓
- Scorer tests (robust penalises knife-edge; max back-compat) → Task 3 Step 1. ✓
- Multi-(q,h) bayes_edge verdict + evidence → Task 4. ✓

**2. Placeholder scan:** Only `<fill>` / `<seed>` / `<q>` / `<h>` in Task 4's evidence template and CLI loop — correct by design (filled from real runs). No placeholders in code/tests.

**3. Type consistency:** `run_program(src, ctx, required_fn="signal") -> (sig, err, logs)`; `PooledTradeScorer(splits, symbols=, timeout=, aggregate=)`; `pooled_task_score(frames)` monkeypatched as the single per-cell call — matches the real `score` body (one `pooled_task_score` call per cell). `_dev_ref`/`_vel_ctx`/`_by_sym`/`_split` are existing helpers. Seed strings reuse `_FAIR` (defines `r,n,a,p,ew,dev`) consistently. `GRID_Q`,`GRID_H` referenced from the module in tests. Consistent.
