# OCO Look-Ahead Bias Removal — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove the `~both` look-ahead conditioning from the OCO candidate mining pipeline so every metric the pipeline reports is achievable in live trading.

**Architecture:** The mining pipeline emits candidate families and per-candidate quality tiers. Two places condition on `both` (whether both barriers were touched within the horizon — future information): the `first_touch_clean` family universe and the `_assign_quality_tier` A/B gates. Both are removed. Structural guardrails (a renamed field with docstrings, a family allowlist contract test, and a lock-loader rejection) prevent recurrence.

**Tech Stack:** Python, numpy, pandas, pytest. Mining entry point `scripts/run_tick_opportunity_mining.py`; candidate loading `src/behemoth/core/registry.py`.

**Spec:** `docs/superpowers/specs/2026-05-15-oco-lookahead-bias-removal-design.md`

**Audit findings (verified during planning):**
- Regime masks (`_regime_masks`) — **clean**. Quantile thresholds come from the train frame (past); per-bar regime membership compares the bar's own causal features against those thresholds. No fix needed.
- `quality_tier` — gates A/B tiers on `both_window_rate_train`. Train-only (no test-set leakage), but it still conditions on `both`. **Fixed in Task 2.**
- `selection_pass` — set to a literal `True` in the test-stage row build; not computed from look-ahead. No fix needed.

---

## Task 1: Excise the `first_touch_clean` family from mining

**Files:**
- Modify: `scripts/run_tick_opportunity_mining.py` (family loop ~line 633)
- Test: `tests/test_tick_opportunity_mining.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_tick_opportunity_mining.py`:

```python
def test_mining_emits_only_first_touch_family(tmp_path):
    """The mining pipeline must not emit any look-ahead-conditioned family.

    oco_first_touch_clean was conditioned on ~both (both barriers touched
    within the horizon — future information). Only oco_first_touch, whose
    universe is decided & reg_mask, is look-ahead-free.
    """
    from scripts.run_tick_opportunity_mining import _oco_candidates

    # _build_synthetic_oco_frame is the existing helper used by the other
    # mining tests in this file; reuse it for a frame large enough to mine.
    train = _build_synthetic_oco_frame(n=4000, seed=1)
    test = _build_synthetic_oco_frame(n=4000, seed=2)
    out = _oco_candidates(
        train=train, test=test, symbol="EURUSD", bar_ticks=1000,
        horizons=[6], barrier_grid_pips=[2.0],
    )
    families = set(out["family"].unique())
    assert families == {"oco_first_touch"}, f"unexpected families: {families}"
    assert not out["state_id"].str.contains("first_touch_clean").any()
```

If `_build_synthetic_oco_frame` / `_oco_candidates` have different names in the file, match the existing test helpers and the actual mining function name — check the top of `tests/test_tick_opportunity_mining.py` and the `def _oco_candidates`/`def _oco_*` signature in the script before writing.

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_tick_opportunity_mining.py::test_mining_emits_only_first_touch_family -v`
Expected: FAIL — output still contains `oco_first_touch_clean` rows.

- [ ] **Step 3: Remove the family from the loop**

In `scripts/run_tick_opportunity_mining.py`, the family loop currently reads:

```python
                    for fam, fam_mask in [
                        ("first_touch", decided & reg_mask),
                        ("first_touch_clean", decided & reg_mask & (~both)),
                    ]:
```

Change to:

```python
                    for fam, fam_mask in [
                        ("first_touch", decided & reg_mask),
                    ]:
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_tick_opportunity_mining.py::test_mining_emits_only_first_touch_family -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/run_tick_opportunity_mining.py tests/test_tick_opportunity_mining.py
git commit -m "fix: remove look-ahead first_touch_clean family from OCO mining"
```

---

## Task 2: Remove `both` conditioning from quality tiering

**Files:**
- Modify: `scripts/run_tick_opportunity_mining.py` (`_assign_quality_tier`, ~line 439)
- Test: `tests/test_tick_opportunity_mining.py`

- [ ] **Step 1: Write the failing test**

```python
def test_quality_tier_does_not_condition_on_both():
    """Quality tiers must not gate on both_window_rate (look-ahead).

    A candidate with strong train metrics but a high both-touch rate must
    still be eligible for tier A — the both rate is not knowable per-trade.
    """
    import pandas as pd
    from scripts.run_tick_opportunity_mining import _assign_quality_tier

    df = pd.DataFrame([{
        "mean_gross_pips_train": 2.0,
        "median_gross_pips_train": 0.5,
        "train_count": 50000,
        "both_window_rate_train": 0.95,   # high whipsaw — previously blocked tier A
        "selection_pass": True,
    }])
    out = _assign_quality_tier(df, library="oco")
    assert out.loc[0, "quality_tier"] == "A"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_tick_opportunity_mining.py::test_quality_tier_does_not_condition_on_both -v`
Expected: FAIL — tier is "C" because `both <= 0.55` gate blocks A.

- [ ] **Step 3: Remove `both` from the tier gates**

In `_assign_quality_tier`, delete the `both` series construction and the `both <=` clauses. The block:

```python
    if "both_window_rate_train" in out.columns:
        both = pd.to_numeric(out["both_window_rate_train"], errors="coerce").fillna(1.0)
    else:
        both = pd.Series(1.0, index=out.index)
    sel = out["selection_pass"].astype(bool)

    if str(library).lower() == "directional":
        a = (mean_g >= 0.25) & (med_g >= 0.05) & (tc >= 40000)
        b = (mean_g >= 0.10) & (med_g >= 0.0) & (tc >= 20000)
    else:
        a = (mean_g >= 1.0) & (med_g >= 0.3) & (both <= 0.55) & (tc >= 40000)
        b = (mean_g >= 0.40) & (med_g >= 0.1) & (both <= 0.70) & (tc >= 20000)
```

becomes:

```python
    sel = out["selection_pass"].astype(bool)

    if str(library).lower() == "directional":
        a = (mean_g >= 0.25) & (med_g >= 0.05) & (tc >= 40000)
        b = (mean_g >= 0.10) & (med_g >= 0.0) & (tc >= 20000)
    else:
        a = (mean_g >= 1.0) & (med_g >= 0.3) & (tc >= 40000)
        b = (mean_g >= 0.40) & (med_g >= 0.1) & (tc >= 20000)
```

Update the function docstring: replace the first line with
`"""Assign quality tiers (A/B/C/D) from look-ahead-free train metrics only."""`
and keep the test-leakage sentence.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_tick_opportunity_mining.py::test_quality_tier_does_not_condition_on_both -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/run_tick_opportunity_mining.py tests/test_tick_opportunity_mining.py
git commit -m "fix: drop both_window_rate from OCO quality-tier gates"
```

---

## Task 3: Rename `both` → `both_touched_lookahead` with field docstrings

**Files:**
- Modify: `scripts/run_tick_opportunity_mining.py` (`_oco_precompute_candidates` return ~line 429, consumers ~625 and ~678)
- Test: `tests/test_tick_opportunity_mining.py`

- [ ] **Step 1: Write the failing test**

```python
def test_precompute_labels_lookahead_field_explicitly():
    """The both-touch field must be named to make its look-ahead nature
    self-evident, so it cannot be used as a filter by mistake."""
    import numpy as np
    from scripts.run_tick_opportunity_mining import _oco_precompute_candidates

    frame = _build_synthetic_oco_frame(n=4000, seed=3)
    prep = _oco_precompute_candidates(frame, symbol="EURUSD", horizon=6, barrier_pips=2.0)
    assert "both_touched_lookahead" in prep
    assert "both" not in prep
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_tick_opportunity_mining.py::test_precompute_labels_lookahead_field_explicitly -v`
Expected: FAIL — key is still `both`.

- [ ] **Step 3: Rename the field and document the return**

In `_oco_precompute_candidates`, the return dict:

```python
    return {
        "i0": i0,
        "gross": gross,
        "side": side,
        "both": both,
        "decided": decided,
        "touch_step": touch_step,
    }
```

becomes:

```python
    # Return fields are partitioned by when they become knowable:
    #   decision-time (safe to filter the candidate universe on):
    #     i0       — signal bar index
    #     decided  — a barrier was touched within the horizon (live expires
    #                un-touched scans, so the traded population matches)
    #     side     — first-touch direction (live enters the side that touches)
    #   labelling-only (require forward information — outcome/metrics ONLY,
    #   MUST NOT be used to filter the candidate universe):
    #     gross                 — enter-at-touch, hold-h-bars P&L
    #     both_touched_lookahead — both barriers touched within the horizon
    #     touch_step            — bars from signal to first touch
    return {
        "i0": i0,
        "gross": gross,
        "side": side,
        "both_touched_lookahead": both,
        "decided": decided,
        "touch_step": touch_step,
    }
```

Update the two consumers in the mining loop:
- `~line 625`: `both = prep["both"]` → `both = prep["both_touched_lookahead"]`
- `~line 678`: `float(np.mean(both[reg_mask]))` — unchanged (the local `both` variable still holds the value; only the dict key changed). Confirm the local name still resolves.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_tick_opportunity_mining.py::test_precompute_labels_lookahead_field_explicitly -v`
Expected: PASS.

- [ ] **Step 5: Run the full mining test file**

Run: `uv run pytest tests/test_tick_opportunity_mining.py -q`
Expected: all pass (the family/tier tests from Tasks 1–2 and pre-existing tests).

- [ ] **Step 6: Commit**

```bash
git add scripts/run_tick_opportunity_mining.py tests/test_tick_opportunity_mining.py
git commit -m "refactor: rename both -> both_touched_lookahead; document precompute fields"
```

---

## Task 4: Family-allowlist contract test

**Files:**
- Create: `tests/test_oco_candidate_family_allowlist.py`

- [ ] **Step 1: Write the test**

```python
"""Contract: the OCO mining pipeline emits only look-ahead-free families.

oco_first_touch_clean was removed because its universe was conditioned on
~both (both barriers touched within the horizon — future information). Any
new family must be audited for look-ahead before being added to ALLOWED.
See docs/superpowers/specs/2026-05-15-oco-lookahead-bias-removal-design.md.
"""
from __future__ import annotations

ALLOWED_OCO_FAMILIES = {"oco_first_touch"}


def test_mining_family_definitions_are_allowlisted():
    import re
    src = open("scripts/run_tick_opportunity_mining.py", encoding="utf-8").read()
    # The family loop lists ("<name>", <mask>) tuples; extract the names.
    block = src.split('for fam, fam_mask in [', 1)[1].split(']:', 1)[0]
    names = set(re.findall(r'\("([a-z_]+)"', block))
    families = {f"oco_{n}" for n in names}
    assert families <= ALLOWED_OCO_FAMILIES, (
        f"non-allowlisted OCO family emitted: {families - ALLOWED_OCO_FAMILIES}. "
        f"Audit it for look-ahead conditioning before adding to ALLOWED_OCO_FAMILIES."
    )
    assert families == ALLOWED_OCO_FAMILIES, (
        f"expected exactly {ALLOWED_OCO_FAMILIES}, got {families}"
    )
```

- [ ] **Step 2: Run test to verify it passes**

Run: `uv run pytest tests/test_oco_candidate_family_allowlist.py -v`
Expected: PASS (Task 1 already removed the second family).

- [ ] **Step 3: Verify it catches a regression**

Temporarily re-add a `("first_touch_clean", decided & reg_mask & (~both))` line to the family loop, run the test, confirm it FAILS with the allowlist message, then revert the temporary line.

- [ ] **Step 4: Commit**

```bash
git add tests/test_oco_candidate_family_allowlist.py
git commit -m "test: contract test allowlisting look-ahead-free OCO families"
```

---

## Task 5: Governance lock loader rejects `first_touch_clean` state_ids

**Files:**
- Modify: `src/behemoth/core/registry.py` (`CandidateSpec.from_row`, ~line 44)
- Test: `tests/test_registry.py`

`CandidateSpec.from_row` is the common chokepoint — both `GovernanceLockLoader._parse_lock` and `CandidateRegistry.load` build candidates through it, so rejecting here covers both loaders.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_registry.py`:

```python
def test_candidate_spec_rejects_lookahead_clean_family():
    """A lock that deploys a first_touch_clean candidate must be rejected
    at load time — its win rate is look-ahead-biased and not live-achievable.
    See docs/superpowers/specs/2026-05-15-oco-lookahead-bias-removal-design.md.
    """
    import pytest
    from src.behemoth.core.registry import CandidateSpec

    row = {
        "symbol": "EURUSD", "bar_ticks": 1000, "horizon": 6,
        "barrier_pips": 2.0,
        "state_id": "oco_first_touch_clean__all__k2",
        "regime_desc": "all;barrier=2.0",
    }
    with pytest.raises(ValueError, match="first_touch_clean"):
        CandidateSpec.from_row(row)


def test_candidate_spec_accepts_first_touch_family():
    from src.behemoth.core.registry import CandidateSpec
    row = {
        "symbol": "EURUSD", "bar_ticks": 1000, "horizon": 6,
        "barrier_pips": 2.0,
        "state_id": "oco_first_touch__all__k2",
        "regime_desc": "all;barrier=2.0",
    }
    spec = CandidateSpec.from_row(row)
    assert spec.candidate_uid == "oco_first_touch__all__k2"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_registry.py::test_candidate_spec_rejects_lookahead_clean_family -v`
Expected: FAIL — no exception raised.

- [ ] **Step 3: Add the rejection to `CandidateSpec.from_row`**

In `src/behemoth/core/registry.py`, `from_row` currently reads:

```python
    @staticmethod
    def from_row(row: dict) -> CandidateSpec:
        """Build from a state_universe row in the live lock JSON."""
        return CandidateSpec(
            symbol=row["symbol"],
            bar_ticks=row["bar_ticks"],
            horizon=row["horizon"],
            barrier_pips=float(row["barrier_pips"]),
            candidate_uid=row["state_id"],
            regime_desc=row.get("regime_desc", ""),
        )
```

Change to:

```python
    @staticmethod
    def from_row(row: dict) -> CandidateSpec:
        """Build from a state_universe row in the live lock JSON.

        Rejects first_touch_clean candidates: that family's win rate was
        conditioned on ~both (look-ahead) and is not live-achievable. See
        docs/superpowers/specs/2026-05-15-oco-lookahead-bias-removal-design.md.
        """
        state_id = str(row["state_id"])
        if "first_touch_clean" in state_id:
            raise ValueError(
                f"refusing look-ahead-biased candidate '{state_id}': the "
                "first_touch_clean family conditions its win rate on ~both "
                "(future information) and must not be deployed. Re-mine and "
                "re-freeze governance on the first_touch family."
            )
        return CandidateSpec(
            symbol=row["symbol"],
            bar_ticks=row["bar_ticks"],
            horizon=row["horizon"],
            barrier_pips=float(row["barrier_pips"]),
            candidate_uid=state_id,
            regime_desc=row.get("regime_desc", ""),
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_registry.py::test_candidate_spec_rejects_lookahead_clean_family tests/test_registry.py::test_candidate_spec_accepts_first_touch_family -v`
Expected: both PASS.

- [ ] **Step 5: Commit**

```bash
git add src/behemoth/core/registry.py tests/test_registry.py
git commit -m "feat: reject first_touch_clean candidates at lock-load time"
```

---

## Task 6: Repair test fixtures broken by the lock-loader rejection

**Files:**
- Modify: test files that build candidate rows / locks with `first_touch_clean` state_ids and load them through `CandidateSpec.from_row`.
- Test: the affected files.

The Task 5 rejection breaks any test whose fixture deploys a `first_touch_clean` state_id through a registry/lock loader. Tests that merely use the string elsewhere (e.g. a candidate-UID column not parsed by `from_row`) are unaffected.

- [ ] **Step 1: Find the actually-broken tests**

Run the candidate set that references the family:

```bash
uv run pytest tests/test_registry.py tests/test_historical_registry.py \
  tests/test_oco_historical_governance.py tests/test_oco_live_governance.py \
  tests/test_validate_oco_rule_universe_registry.py \
  tests/test_api_server.py tests/test_api_server_historical.py \
  tests/test_duckdb_state.py tests/test_live_threshold_diagnostics.py \
  tests/test_tick_opportunity_ml_dataset.py tests/test_feature_parity.py \
  tests/test_oco_reduced_core_rolling.py tests/test_diagnose_live_performance_gap.py \
  tests/test_verify_oco_tick_exact_shortlist.py -q
```

Expected: some FAIL with `ValueError: refusing look-ahead-biased candidate 'oco_first_touch_clean...'`.

- [ ] **Step 2: Fix each broken fixture**

For every failure traced to the rejection: in the test fixture, replace the
`first_touch_clean` state_id with the look-ahead-free equivalent — change
`oco_first_touch_clean__<regime>__k<n>` to `oco_first_touch__<regime>__k<n>`
(and the bare `oco_first_touch_clean_k2` form in `tests/test_tick_opportunity_mining.py`
lines ~167/197/212 to `oco_first_touch_k2`). The candidate is otherwise
identical — only the family name changes. Do **not** weaken or delete the
rejection to make a test pass.

If a test's *purpose* is specifically to assert `first_touch_clean` behaviour
(rather than using it as an incidental fixture), delete that test — the
family no longer exists.

- [ ] **Step 3: Re-run until green**

Run the Step 1 command again. Expected: all PASS.

- [ ] **Step 4: Commit**

```bash
git add tests/
git commit -m "test: migrate fixtures from first_touch_clean to first_touch"
```

---

## Task 7: Update documentation

**Files:**
- Modify: `UBIQUITOUS_LANGUAGE.md`, and any docs-contract source that names the family. Do NOT edit generated analysis reports under `docs/analysis/` or `docs/archive/` or `docs/strategy_bible/generated*` — those are historical artefacts regenerated by their own pipelines.

- [ ] **Step 1: Check the docs-contract test for the family name**

Run: `uv run pytest tests/test_oco_docs_contract.py -q`
Expected: PASS, or FAIL pointing at a doc that must name only `oco_first_touch`.

- [ ] **Step 2: Update `UBIQUITOUS_LANGUAGE.md`**

If `UBIQUITOUS_LANGUAGE.md` defines the OCO candidate families, remove the
`oco_first_touch_clean` entry and add a one-line note: `oco_first_touch_clean`
was removed 2026-05 — its win rate was conditioned on `~both` (look-ahead);
see `docs/superpowers/specs/2026-05-15-oco-lookahead-bias-removal-design.md`.
If the file does not mention the families, make no change.

- [ ] **Step 3: Update hand-written strategy-bible source if needed**

`docs/strategy_bible/stage_02_opportunity_mining.md` and
`docs/strategy_bible/signal_lifecycle_reference.md` are hand-written (not
generated). If either describes `first_touch_clean` as a deployable family,
correct it to state only `first_touch` is mined and why. Leave
`docs/strategy_bible/generated*` untouched.

- [ ] **Step 4: Commit**

```bash
git add UBIQUITOUS_LANGUAGE.md docs/strategy_bible/
git commit -m "docs: record removal of look-ahead first_touch_clean family"
```

---

## Task 8: Full verification

- [ ] **Step 1: Run the full test suite**

Run: `uv run pytest -q`
Expected: all pass (modulo the pre-existing `requires_models` skips). No failure mentioning `first_touch_clean`.

- [ ] **Step 2: Run quality checks**

Run: `make quality`
Expected: exit 0.

- [ ] **Step 3: Final commit if anything was adjusted**

```bash
git add -A
git commit -m "chore: finalise OCO look-ahead bias removal"
```

---

## Out of scope — operator actions after merge

`make retrain-all` → `make monthly-build` → `make monthly-recert` → `make promote-live`. These re-mine on the look-ahead-free `first_touch` family, re-train, and re-freeze governance locks. If no `first_touch` candidate clears the selection gates, nothing deploys and the live system trades nothing — the intended, accepted outcome. The lock-loader rejection (Task 5) ensures any stale `first_touch_clean` lock is refused in the interim.
