# cTrader / cBot Deletion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove all dead cTrader/cBot code — 13 scripts, 12 tests, `src/cbot/`, and associated Makefile targets — leaving `pytest tests/` green with a reduced test count.

**Architecture:** Pure deletion with two targeted patches: remove a subprocess call in `run_offset_tickbar_robustness.py` that calls a deleted script, and remove a now-dead entry from `check_legacy_drift.py`'s FORBIDDEN_TERMS list. No new code is written.

**Tech Stack:** Python, Make, pytest

---

## File Map

| File | Action |
|------|--------|
| `scripts/build_ctrader_ab_parity_report.py` | Delete |
| `scripts/build_ctrader_debug_bundle.py` | Delete |
| `scripts/evaluate_ftmo_challenge_run.py` | Delete |
| `scripts/export_ctrader_custom_data.py` | Delete |
| `scripts/manage_ctrader_debug_session.py` | Delete |
| `scripts/reconcile_ctrader_vs_research.py` | Delete |
| `scripts/replay_cbot_testclient.py` | Delete |
| `scripts/replay_dukascopy_testclient.py` | Delete |
| `scripts/replay_histdata_cbot_surrogate.py` | Delete |
| `scripts/replay_histdata_cbot_testclient.py` | Delete |
| `scripts/validate_ctrader_execution_parity.py` | Delete |
| `scripts/validate_histdata_ctrader_execution_parity.py` | Delete |
| `scripts/verify_cbot_handshake.py` | Delete |
| `scripts/run_offset_tickbar_robustness.py` | Patch: remove cBot subprocess call at ~line 1019 |
| `scripts/check_legacy_drift.py` | Patch: remove `r"src/cbot"` from FORBIDDEN_TERMS |
| `tests/test_build_ctrader_ab_parity_report.py` | Delete |
| `tests/test_build_ctrader_debug_bundle.py` | Delete |
| `tests/test_build_ftmo_allocator_monitoring_report.py` | Delete |
| `tests/test_evaluate_ftmo_challenge_run.py` | Delete |
| `tests/test_export_ctrader_custom_data.py` | Delete |
| `tests/test_ftmo_risk.py` | Delete |
| `tests/test_manage_ctrader_debug_session.py` | Delete |
| `tests/test_reconcile_ctrader_vs_research.py` | Delete |
| `tests/test_reconcile_ftmo_reservations.py` | Delete |
| `tests/test_replay_histdata_cbot_surrogate.py` | Delete |
| `tests/test_replay_histdata_cbot_testclient.py` | Delete |
| `tests/test_validate_histdata_ctrader_execution_parity.py` | Delete |
| `src/cbot/` | Delete directory (contains `BehemothTradeManager.cs` and `CustomDataSourceHistDataPlugin.cs`) |
| `Makefile` | Remove cTrader/cBot/ftmo-eval targets, variables, `.PHONY` entries |

---

### Task 1: Delete cTrader/cBot scripts

**Files:**
- Delete: `scripts/build_ctrader_ab_parity_report.py`
- Delete: `scripts/build_ctrader_debug_bundle.py`
- Delete: `scripts/evaluate_ftmo_challenge_run.py`
- Delete: `scripts/export_ctrader_custom_data.py`
- Delete: `scripts/manage_ctrader_debug_session.py`
- Delete: `scripts/reconcile_ctrader_vs_research.py`
- Delete: `scripts/replay_cbot_testclient.py`
- Delete: `scripts/replay_dukascopy_testclient.py`
- Delete: `scripts/replay_histdata_cbot_surrogate.py`
- Delete: `scripts/replay_histdata_cbot_testclient.py`
- Delete: `scripts/validate_ctrader_execution_parity.py`
- Delete: `scripts/validate_histdata_ctrader_execution_parity.py`
- Delete: `scripts/verify_cbot_handshake.py`

- [ ] **Step 1: Delete the scripts**

```bash
cd /Users/danielfisher/repositories/behemoth
rm scripts/build_ctrader_ab_parity_report.py
rm scripts/build_ctrader_debug_bundle.py
rm scripts/evaluate_ftmo_challenge_run.py
rm scripts/export_ctrader_custom_data.py
rm scripts/manage_ctrader_debug_session.py
rm scripts/reconcile_ctrader_vs_research.py
rm scripts/replay_cbot_testclient.py
rm scripts/replay_dukascopy_testclient.py
rm scripts/replay_histdata_cbot_surrogate.py
rm scripts/replay_histdata_cbot_testclient.py
rm scripts/validate_ctrader_execution_parity.py
rm scripts/validate_histdata_ctrader_execution_parity.py
rm scripts/verify_cbot_handshake.py
```

- [ ] **Step 2: Verify deletions**

```bash
ls scripts/ | grep -E "ctrader|cbot|evaluate_ftmo"
```

Expected: no output (all matching files deleted).

- [ ] **Step 3: Commit**

```bash
git add -A
git commit -m "chore: delete dead cTrader/cBot scripts"
```

---

### Task 2: Delete cTrader/cBot and ftmo tests

**Files:**
- Delete: `tests/test_build_ctrader_ab_parity_report.py`
- Delete: `tests/test_build_ctrader_debug_bundle.py`
- Delete: `tests/test_build_ftmo_allocator_monitoring_report.py`
- Delete: `tests/test_evaluate_ftmo_challenge_run.py`
- Delete: `tests/test_export_ctrader_custom_data.py`
- Delete: `tests/test_ftmo_risk.py`
- Delete: `tests/test_manage_ctrader_debug_session.py`
- Delete: `tests/test_reconcile_ctrader_vs_research.py`
- Delete: `tests/test_reconcile_ftmo_reservations.py`
- Delete: `tests/test_replay_histdata_cbot_surrogate.py`
- Delete: `tests/test_replay_histdata_cbot_testclient.py`
- Delete: `tests/test_validate_histdata_ctrader_execution_parity.py`

- [ ] **Step 1: Delete the test files**

```bash
cd /Users/danielfisher/repositories/behemoth
rm tests/test_build_ctrader_ab_parity_report.py
rm tests/test_build_ctrader_debug_bundle.py
rm tests/test_build_ftmo_allocator_monitoring_report.py
rm tests/test_evaluate_ftmo_challenge_run.py
rm tests/test_export_ctrader_custom_data.py
rm tests/test_ftmo_risk.py
rm tests/test_manage_ctrader_debug_session.py
rm tests/test_reconcile_ctrader_vs_research.py
rm tests/test_reconcile_ftmo_reservations.py
rm tests/test_replay_histdata_cbot_surrogate.py
rm tests/test_replay_histdata_cbot_testclient.py
rm tests/test_validate_histdata_ctrader_execution_parity.py
```

- [ ] **Step 2: Run pytest to verify no errors introduced yet**

```bash
uv run pytest tests/ -x -q 2>&1 | tail -5
```

Expected: all remaining tests pass (some tests import deleted scripts — those are caught here; the remaining tests should be green).

- [ ] **Step 3: Commit**

```bash
git add -A
git commit -m "chore: delete dead cTrader/cBot and legacy ftmo tests"
```

---

### Task 3: Delete src/cbot/ directory

**Files:**
- Delete: `src/cbot/BehemothTradeManager.cs`
- Delete: `src/cbot/CustomDataSourceHistDataPlugin.cs`
- Delete: `src/cbot/` (directory)

- [ ] **Step 1: Delete the directory**

```bash
rm -rf src/cbot/
```

- [ ] **Step 2: Verify**

```bash
ls src/ | grep cbot
```

Expected: no output.

- [ ] **Step 3: Commit**

```bash
git add -A
git commit -m "chore: delete src/cbot C# robot source (dead platform)"
```

---

### Task 4: Patch run_offset_tickbar_robustness.py

The script calls `replay_histdata_cbot_testclient.py` as a subprocess around line 1019. With that script deleted, this call would fail at runtime. Replace the subprocess invocation with a `NotImplementedError` guard.

**Files:**
- Modify: `scripts/run_offset_tickbar_robustness.py`

- [ ] **Step 1: Read the relevant section**

Open `scripts/run_offset_tickbar_robustness.py` around line 1010–1030 to see the exact subprocess call context.

- [ ] **Step 2: Replace the cBot subprocess call**

Find the block that calls `replay_histdata_cbot_testclient.py` as a subprocess. It will look something like:

```python
subprocess.run([
    sys.executable,
    str(ROOT / "scripts/replay_histdata_cbot_testclient.py"),
    ...
])
```

Replace the entire subprocess invocation (including any surrounding `if`/`else` that feeds it) with:

```python
raise NotImplementedError(
    "cBot testclient replay was removed. JForex equivalent is a future task."
)
```

- [ ] **Step 3: Run the test suite to confirm nothing broke**

```bash
uv run pytest tests/ -x -q 2>&1 | tail -5
```

Expected: all tests pass (this script has no tests of its own after Task 2 deletions).

- [ ] **Step 4: Commit**

```bash
git add scripts/run_offset_tickbar_robustness.py
git commit -m "chore: remove cBot subprocess call from run_offset_tickbar_robustness"
```

---

### Task 5: Patch check_legacy_drift.py

Remove the now-dead `r"src/cbot"` entry from FORBIDDEN_TERMS.

**Files:**
- Modify: `scripts/check_legacy_drift.py`

- [ ] **Step 1: Read the FORBIDDEN_TERMS list**

Open `scripts/check_legacy_drift.py` lines 7–14. Current content:

```python
FORBIDDEN_TERMS = [
    r"\bkalman\b",
    r"services/api",
    r"src/cbot",
    r"src/behemoth",
    r"pipelines/build_events",
    r"pipelines/simulate"
]
```

- [ ] **Step 2: Remove the src/cbot entry**

Edit to:

```python
FORBIDDEN_TERMS = [
    r"\bkalman\b",
    r"services/api",
    r"src/behemoth",
    r"pipelines/build_events",
    r"pipelines/simulate"
]
```

- [ ] **Step 3: Commit**

```bash
git add scripts/check_legacy_drift.py
git commit -m "chore: remove src/cbot from check_legacy_drift FORBIDDEN_TERMS"
```

---

### Task 6: Clean up Makefile

Remove all cTrader/cBot targets, their variable definitions, `.PHONY` entries, and the help-text strings. Also remove the `ftmo-eval` target (calls the now-deleted `evaluate_ftmo_challenge_run.py`). The `--ftmo-*` flags in the `jforex-live` and other remaining targets are handled in Sub-project B.

**Files:**
- Modify: `Makefile`

Targets to remove from `.PHONY` and as target blocks:
`deploy-cbot`, `deploy-ctrader`, `reconcile-ctrader-run`, `export-ctrader-custom-data`, `ctrader-debug-up`, `ctrader-debug-down`, `ctrader-debug-status`, `cbot-surrogate`, `ctrader-ab-parity-report`, `ctrader-parity`, `histdata-ctrader-parity`, `testclient-parity`, `dukascopy-testclient-parity`, `histdata-testclient-parity`, `ftmo-eval`

Also remove variable definitions: `CTRADER_ROBOT_DST`, `CTRADER_PLUGIN_DST` (if present), and any `CTRADER_*` or `CBOT_*` variable blocks.

Also remove the help-text lines in the `help` target for all deleted targets (lines ~760–797 range).

- [ ] **Step 1: Read the Makefile sections to be removed**

Read `Makefile` around lines 24 (`.PHONY`), 280–295 (`deploy-cbot`, `deploy-ctrader`), 394–420 (`reconcile-ctrader-run`, `export-ctrader-custom-data`), 426–470 (`ctrader-debug-up/down/status`), 469–476 (`cbot-surrogate`), 509–515 (`ftmo-eval`), 518–566 (`ctrader-ab-parity-report`, `ctrader-parity`, `histdata-ctrader-parity`), 760–800 (help strings).

- [ ] **Step 2: Remove all identified blocks**

Use the Edit tool for each block. Remove:
- All `CTRADER_*` and `CBOT_*` variable definitions near the top
- Each of the 12 target blocks listed above (target name, recipe, blank line)
- Each target name from the `.PHONY` line
- Each help-text string entry for these targets

- [ ] **Step 3: Verify Makefile is syntactically valid**

```bash
make help 2>&1 | head -30
```

Expected: help output prints without errors; deleted targets are absent.

- [ ] **Step 4: Run pytest to confirm nothing broke**

```bash
uv run pytest tests/ -x -q 2>&1 | tail -5
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add Makefile
git commit -m "chore: remove cTrader/cBot Makefile targets and ftmo-eval target"
```

---

### Task 7: Final verification

- [ ] **Step 1: Run full pytest suite**

```bash
uv run pytest tests/ -q 2>&1 | tail -10
```

Expected: green. Test count should be ~12 fewer than before Sub-project A began.

- [ ] **Step 2: Verify no stale cTrader/cBot imports remain**

```bash
grep -r "ctrader\|cbot\|replay_histdata_cbot\|replay_cbot\|evaluate_ftmo_challenge" \
  scripts/ tests/ src/ Makefile --include="*.py" -l
```

Expected: no matches (or only within comments in unrelated files — check any matches carefully).

- [ ] **Step 3: Commit if anything was missed**

If the grep finds stale references, fix them, then:

```bash
git add -A
git commit -m "chore: clean up remaining cTrader/cBot stray references"
```
