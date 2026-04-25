# PR #95 Post-Review Bug Fixes

- **Status:** Approved; implementation plan pending.
- **Date:** 2026-04-25
- **Target branch:** `docs/live-stage-commonality-dag`
- **Scope:** Fix three issues identified in code review of PR #95 (live-stage commonality DAG implementation). Two high-severity process correctness bugs and one medium-severity test breakage.

## Problem Summary

PR #95 introduced restart eligibility, DAG provenance, and the `allow_new_entries` gate. Three issues survived review:

1. **Reset startup inherits stale drain-only state.** `restart_eligibility` is computed from old metadata before `_cleanup_runtime_state` runs. After reset, the old `allow_new_entries=False` value is passed to JForex even though the whole purpose of a reset startup was to clear incompatible state.

2. **Commit divergence is recorded but not enforced.** `live_stage_dag.yaml` has no `target_commit` field in the DAG contract, and promotion only checks `target_branch == "main"`. This still allows certifying on an earlier `main` commit and promoting from a newer one — exactly the process drift the spec was meant to prevent.

3. **Two tests in `tests/test_run_jforex_live.py` are broken.** The `_reconcile_startup` return type grew from a 3-tuple to a 4-tuple, and `_start_live_runner` now requires an `allow_new_entries` keyword argument. Both test stubs predate these changes and cause test failures.

## Fix 1: Reset Startup allow_new_entries Override

### Location

`scripts/run_jforex_live.py`, `main()` function, after the reset cleanup block and before `_start_live_runner` is called.

### Design

After `_cleanup_runtime_state` completes successfully on a reset startup, override the `allow_new_entries` value derived from the pre-reset eligibility check:

```python
effective_allow_new_entries = (
    True if cfg.startup_mode == "reset"
    else restart_eligibility.allow_new_entries
)
```

Pass `effective_allow_new_entries` to `_start_live_runner` instead of `restart_eligibility.allow_new_entries`.

**Rationale:** A reset startup by definition cleared the incompatible state. Preserving the old drain-only verdict after cleanup contradicts the intent of the reset. Forcing `True` only applies when `startup_mode == "reset"` and cleanup actually ran; normal and reconcile startups are unaffected.

**No new state or parameters are needed.** `cfg.startup_mode` is already available in `main()`.

## Fix 2: Lenient Commit Ancestor Check in Promotion

### Location

`scripts/run_promote_live.py`, `_verify_cert()` and `_verify_dag_provenance()`.

### Design

Add an injectable `current_commit` parameter to `_verify_cert`:

```python
def _verify_cert(report_dir, model_month, repo_root=None, *, current_commit: str | None = None):
    if current_commit is None:
        current_commit = subprocess.run(
            ["git", "-C", str(repo_root), "rev-parse", "HEAD"],
            capture_output=True, text=True, check=True
        ).stdout.strip()
    ...
    _verify_dag_provenance(status, model_month, repo_root, current_commit=current_commit)
```

In `_verify_dag_provenance`, after verifying that `target_branch == "main"`, add a lenient ancestor check:

```python
certified = str(status["target_commit"]).strip()
result = subprocess.run(
    ["git", "-C", str(repo_root_for_git), "merge-base", certified, current_commit],
    capture_output=True, text=True
)
merge_base = result.stdout.strip()
if merge_base != certified:
    raise SystemExit(
        f"[promote-live] certified commit {certified[:8]} is not an ancestor of "
        f"current HEAD {current_commit[:8]}; re-run make monthly-recert"
    )
```

**Lenient vs. strict:** The check is lenient (ancestor, not exact match) to allow non-code changes (docs, config, graphify output) on top of a certified commit without requiring a full recert cycle. Strict equality would block every commit that lands after recert, which is operationally untenable on main.

**Dev branch compatibility:** `current_commit` is injectable so tests and development workflows can pass a known commit SHA without requiring a real git checkout. This also makes CI validation of the promotion gate straightforward.

**`repo_root` fallback:** When `repo_root` is `None`, the git command falls back to CWD, preserving existing behavior for callers that do not pass it.

## Fix 3: Update Broken Test Stubs

### Location

`tests/test_run_jforex_live.py`

### Design

Two stubs need updating:

**Stub 1 — `_reconcile_startup` returns 3-tuple:**  
Change the return value from `(report, allow_new_entries, mode)` to `(report, restart_eligibility_result, allow_new_entries, mode)` where `restart_eligibility_result` is a `RestartEligibilityResult` instance consistent with the fake report. The exact fields should match what `derive_restart_eligibility` would produce for the stubbed comparison result.

**Stub 2 — `_start_live_runner` does not accept `allow_new_entries`:**  
Add `allow_new_entries: bool = True` to the fake `_start_live_runner` signature so the call site does not raise `TypeError`.

No test logic changes are needed beyond the signature and return value corrections.

## Testing

| Fix | Verification |
|---|---|
| Fix 1 | Add a test that stubs a reset startup with a `RestartEligibilityResult(allow_new_entries=False, ...)` and asserts `_start_live_runner` is called with `allow_new_entries=True`. |
| Fix 2 | Add a test that passes `current_commit` equal to the certified commit (exact match, passes), a commit that is a descendant of certified (passes), and a commit that is unrelated (fails). Use `subprocess.run` mock to control `merge-base` output. |
| Fix 3 | The two previously failing tests will pass once stubs are updated. No new tests needed. |

## Acceptance Criteria

1. `uv run pytest -q tests/test_run_jforex_live.py` passes with no failures.
2. A reset startup with a prior drain-only eligibility result calls `_start_live_runner(allow_new_entries=True)`.
3. Promoting from a commit that is not an ancestor of the certified commit raises `SystemExit` with a message naming both SHAs.
4. Promoting from the same or a descendant commit succeeds.
5. All existing tests continue to pass.
