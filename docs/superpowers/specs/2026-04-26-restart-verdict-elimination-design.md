# RestartVerdict Elimination — Design Spec

**Date:** 2026-04-26
**Goal:** Eliminate the internal `RestartVerdict` enum and replace all usages with the canonical `RestartEligibility` enum, removing a redundant mapping layer and aligning the live restart code with the ubiquitous language.

---

## Context

`src/behemoth/live_restart/reconciliation.py` defines an internal `RestartVerdict` enum with three values that the ubiquitous language explicitly flags as aliases to avoid:

| Current | UL alias to avoid |
|---|---|
| `CLEAN_RESUMABLE = "clean_resumable"` | ✓ flagged |
| `RECONCILABLE = "reconcilable"` | ✓ flagged |
| `INCOMPATIBLE = "incompatible"` | ✓ flagged |

The canonical values already exist in `src/behemoth/ops/verdicts.py` as `RestartEligibility`:

| Canonical | Meaning |
|---|---|
| `RESTART_ELIGIBLE = "RESTART_ELIGIBLE"` | Full restart, new entries allowed |
| `RESTART_ELIGIBLE_DRAIN_ONLY = "RESTART_ELIGIBLE_DRAIN_ONLY"` | Reconcilable, drain only |
| `RESTART_BLOCKED = "RESTART_BLOCKED"` | Hard failure, no restart |

The two enums map 1:1. `RestartVerdict` predates `RestartEligibility` and was never cleaned up. `derive_restart_eligibility` exists solely to translate between them.

---

## Approach

Eliminate `RestartVerdict` entirely. Replace every usage with `RestartEligibility` directly. No compatibility shims — the repo owns all usages and the JSON reconciliation report is write-only (never parsed back).

---

## Value Mapping

| Old | New |
|---|---|
| `RestartVerdict.CLEAN_RESUMABLE` | `RestartEligibility.RESTART_ELIGIBLE` |
| `RestartVerdict.RECONCILABLE` | `RestartEligibility.RESTART_ELIGIBLE_DRAIN_ONLY` |
| `RestartVerdict.INCOMPATIBLE` | `RestartEligibility.RESTART_BLOCKED` |

---

## Changes

### `src/behemoth/live_restart/reconciliation.py`

- Delete the `RestartVerdict` class definition (lines 15–18)
- Change `RuntimeContextComparison.verdict: RestartVerdict` → `verdict: RestartEligibility`
- Change `ReconciliationReport.verdict: RestartVerdict` → `verdict: RestartEligibility`
- Replace all `RestartVerdict.X` assignments and comparisons with `RestartEligibility.X`
- Simplify `derive_restart_eligibility` — the three-branch if/elif collapses to a single return:

```python
def derive_restart_eligibility(
    comparison: RuntimeContextComparison,
) -> RestartEligibilityResult:
    return RestartEligibilityResult(
        eligibility=comparison.verdict,
        allow_new_entries=comparison.verdict is RestartEligibility.RESTART_ELIGIBLE,
        reasons=list(comparison.reasons),
    )
```

### `scripts/run_jforex_live.py`

- Remove `RestartVerdict` from the import at line 39
- Replace `RestartVerdict.RECONCILABLE` at line 707 with `RestartEligibility.RESTART_ELIGIBLE_DRAIN_ONLY`

### `tests/test_live_restart_reconciliation.py`

- Remove `RestartVerdict` from the import at line 13
- Replace all `RestartVerdict.X` references with `RestartEligibility.X`

### `tests/test_run_jforex_live.py`

- Replace all `run_jforex_live.RestartVerdict.X` references with `RestartEligibility.X` (import `RestartEligibility` from `src.behemoth.ops.verdicts` if not already imported)

---

## JSON schema note

`ReconciliationReport` is serialized to JSON via `write_reconciliation_report`. The `verdict` field currently writes `"clean_resumable"`, `"reconcilable"`, or `"incompatible"`. After this change it will write `"RESTART_ELIGIBLE"`, `"RESTART_ELIGIBLE_DRAIN_ONLY"`, or `"RESTART_BLOCKED"`. No code reads these JSON files back programmatically, so this is a safe schema change.

---

## Out of Scope

- Any other legacy labels in docs or scripts — covered by earlier PRs
- `RestartEligibility` enum itself — already canonical, no changes needed
