# Promote Monthly Freeze Out of `scripts/legacy/` Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Dependency:** None — independent of the other follow-ups. Smallest of the four.

**Goal:** `scripts/legacy/freeze_oco_historical_governance.py` is the active monthly producer — `scripts/run_monthly_build.py` invokes it directly. The `legacy/` directory name is a lie that misleads future maintainers (and any new agent context-loaded into the repo). Move it out, rename it for what it does, update the one call site and any imports/tests, and verify nothing else under `scripts/legacy/` is still load-bearing.

**Architecture:** `git mv` the file to `scripts/freeze_monthly_bundle.py`; update `scripts/run_monthly_build.py`'s subprocess invocation; update any test imports. Then audit the rest of `scripts/legacy/` and either confirm everything else there is genuinely dormant or surface what isn't.

**Tech Stack:** Python 3.12. No new dependencies.

---

## Current State

```bash
ls scripts/legacy/
```

Inspect each file:

```bash
for f in scripts/legacy/*.py; do
  echo "=== $f ==="
  grep -l "$(basename $f .py)" --include="*.py" -r scripts/ src/ tests/ | grep -v __pycache__
done
```

Known active dependency: `scripts/run_monthly_build.py` calls `python scripts/legacy/freeze_oco_historical_governance.py ...` via `_run_step` at around lines 100–130 (verify exact location).

---

## File Structure

**Moved files:**
- `scripts/legacy/freeze_oco_historical_governance.py` → `scripts/freeze_monthly_bundle.py`

**Modified files:**
- `scripts/run_monthly_build.py` — update the subprocess invocation path.
- Any other consumer that imports the script (verify with grep first).
- Top-of-file docstring of the moved script — remove `legacy/` framing.

**Deleted (if confirmed empty after the move):**
- `scripts/legacy/` directory (only if it's empty after Task 4).

---

## Task 1: Audit the rest of `scripts/legacy/`

**Files:**
- Read-only inventory.

- [ ] **Step 1: List files**

```bash
ls -la scripts/legacy/
```

- [ ] **Step 2: For each file, check whether it is referenced anywhere active**

```bash
for f in scripts/legacy/*.py; do
  name=$(basename "$f" .py)
  echo "=== $name ==="
  grep -rn "scripts/legacy/$name\|from scripts.legacy.$name\|import scripts.legacy.$name" \
    src/ scripts/ tests/ Makefile docs/ 2>/dev/null | grep -v __pycache__
done
```

Build a list of:
- **Active dependencies** (referenced by something not under `scripts/legacy/` or `tests/legacy/`).
- **Genuinely dormant** (referenced only by tests, or not at all).

If anything **other than `freeze_oco_historical_governance.py`** is active, surface it to the user before continuing. This plan handles only the freeze script; other promotions are out of scope.

- [ ] **Step 3: Record findings**

Write the audit results into a brief checklist comment on the PR description so the reviewer can confirm.

---

## Task 2: Move the script

**Files:**
- Move: `scripts/legacy/freeze_oco_historical_governance.py` → `scripts/freeze_monthly_bundle.py`

- [ ] **Step 1: Git move**

```bash
git mv scripts/legacy/freeze_oco_historical_governance.py scripts/freeze_monthly_bundle.py
```

`git mv` preserves history; future `git blame` and `git log --follow` work as expected.

- [ ] **Step 2: Update the script's docstring**

Open the moved file. Replace any "legacy" framing in the top-of-file docstring with the current reality. Suggested replacement of the first docstring:

```python
"""Freeze a month bundle: produce per-symbol *_live_lock.json under
configs/research/governance/oco_candidate_builds/<YYYY-MM>/ from the latest
mining outputs.

Active producer used by `scripts/run_monthly_build.py`. Emits schema_version: 3
locks per ADR 0001 (deterministic bundles) and ADR 0002 (multi-family).

Previously located at scripts/legacy/freeze_oco_historical_governance.py.
"""
```

Adjust the wording but keep these two pointers: (1) it's active and called by `run_monthly_build.py`, (2) it emits the current schema version.

---

## Task 3: Update `scripts/run_monthly_build.py`

**Files:**
- Modify: `scripts/run_monthly_build.py`

- [ ] **Step 1: Find the subprocess invocation**

```bash
grep -n "freeze_oco_historical_governance" scripts/run_monthly_build.py
```

- [ ] **Step 2: Replace the path**

Change `"scripts/legacy/freeze_oco_historical_governance.py"` → `"scripts/freeze_monthly_bundle.py"` in the argument list passed to `_run_step` (or whichever helper).

- [ ] **Step 3: Update the step label if it mentions the old path**

If the step label printed by `_run_step` references the old name, update it: e.g. `"step 2/2: legacy_freeze"` → `"step 2/2: freeze_monthly_bundle"`.

- [ ] **Step 4: Run the monthly-build's tests**

```bash
uv run pytest -q tests/test_run_monthly_build.py
```
Expected: PASS.

---

## Task 4: Update any other references

- [ ] **Step 1: Find every remaining mention of the old path**

```bash
grep -rn "freeze_oco_historical_governance\|scripts/legacy/freeze" src/ scripts/ tests/ docs/ Makefile 2>/dev/null | grep -v __pycache__
```

- [ ] **Step 2: Update each hit**

For each hit:
- If it's a Python import `from scripts.legacy.freeze_oco_historical_governance import ...` → change to `from scripts.freeze_monthly_bundle import ...`.
- If it's a docstring, comment, or markdown reference → update or remove as appropriate.
- Tests under `tests/legacy/test_freeze_oco_historical_governance*.py`: rename to `tests/test_freeze_monthly_bundle.py` with `git mv` and update imports inside.

- [ ] **Step 3: Run the impacted test files**

```bash
uv run pytest -q tests/test_freeze_monthly_bundle.py tests/test_run_monthly_build.py
```
Expected: PASS.

- [ ] **Step 4: Lint**

```bash
uv run ruff check scripts tests
```
Expected: clean.

---

## Task 5: Remove the now-empty `scripts/legacy/` (only if empty)

**Files:**
- Possibly: delete `scripts/legacy/` directory.

- [ ] **Step 1: Check whether the directory is empty**

```bash
ls -la scripts/legacy/
```

- [ ] **Step 2: If empty, remove**

```bash
git rm -r scripts/legacy
```

If `__init__.py` is the only file remaining and is empty, remove it as well.

- [ ] **Step 3: If not empty, leave it alone**

Per Task 1's audit, anything else in `scripts/legacy/` is genuinely dormant — that's fine. The directory name remains accurate for what remains.

---

## Task 6: Final verification

- [ ] **Step 1: Full suite**

Run: `uv run pytest -q`
Expected: green.

- [ ] **Step 2: Lint**

Run: `uv run ruff check`
Expected: clean.

- [ ] **Step 3: Run a dry monthly-build smoke**

```bash
uv run python scripts/freeze_monthly_bundle.py --help
```
Expected: argparse help text prints; no import errors.

- [ ] **Step 4: Confirm no stale `scripts/legacy/freeze` references**

```bash
grep -rn "scripts/legacy/freeze\|scripts\.legacy\.freeze" src/ scripts/ tests/ docs/ Makefile 2>/dev/null | grep -v __pycache__
```
Expected: empty.

- [ ] **Step 5: Open the PR**

PR title: `chore(governance): promote monthly freeze out of scripts/legacy/`.

Body:
- Confirms `scripts/legacy/freeze_oco_historical_governance.py` was the active monthly producer despite its name.
- Includes the Task 1 audit findings for the rest of `scripts/legacy/`.
- States whether the `scripts/legacy/` directory was removed entirely or only the one file.

---

## Notes for the Implementer

- **Use `git mv`, not delete-and-create.** History continuity matters for `git log --follow` on the file.
- **Do not refactor while moving.** The diff should be 100% rename + path updates + docstring touch-up. Any logic change goes in a separate PR.
- **The rest of `scripts/legacy/` may genuinely be legacy.** This plan does not claim otherwise. The only claim is that the freeze script doesn't belong there. If Task 1 reveals other actives, name them in the PR body but leave them in place — they're a separate cleanup.
