# Verdict Value Alignment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Align all certification script verdict/status string values and CSV column names with the ubiquitous language (`PASS`, `FAIL`, `NO_GO`) and update agent config files to always reference `UBIQUITOUS_LANGUAGE.md`.

**Architecture:** Atomic single-pass migration — update test assertions first (making them fail), then update implementation code to restore green, then migrate checked-in CSVs. All changes land in one branch. No compatibility shims.

**Tech Stack:** Python scripts under `scripts/`, pytest, CSV files under `data/analysis/backtest_reconcile/`, `CLAUDE.md`, `AGENTS.md`.

**Design spec:** `docs/superpowers/specs/2026-04-26-verdict-value-alignment-design.md`

---

## File Structure

- Modify: `CLAUDE.md` — add ubiquitous language section
- Modify: `AGENTS.md` — add ubiquitous language section
- Modify: `scripts/validate_stage14_jforex_runtime_certification.py` — verdict/status emit values, `_nogo` column name, help text
- Modify: `scripts/validate_stage13_dukascopy_testclient.py` — verdict/status emit values, `_nogo` column name, help text
- Modify: `scripts/validate_local_jforex_surrogate.py` — verdict/status emit values, `_nogo` column name, help text
- Modify: `scripts/run_monthly_recert.py` — status readers, printed `NOGO` label
- Modify: `scripts/run_promote_live.py` — status reader guard
- Modify: `data/analysis/backtest_reconcile/stage13_dukascopy_testclient_summary.csv` — column header + values
- Modify: `data/analysis/backtest_reconcile/local_jforex_surrogate_summary.csv` — column header + values
- Modify: `data/analysis/backtest_reconcile/stage14_jforex_runtime_certification_checks.csv` — status values
- Modify: `data/analysis/backtest_reconcile/local_jforex_surrogate_checks.csv` — status values
- Modify: `tests/test_validate_stage14_jforex_runtime_certification.py` — verdict/status assertions
- Modify: `tests/test_validate_stage13_dukascopy_testclient.py` — verdict assertion, column name assertion
- Modify: `tests/test_validate_local_jforex_surrogate.py` — verdict assertion, column name assertions
- Modify: `tests/test_run_monthly_recert.py` — printed NOGO label assertion
- Modify: `tests/test_run_promote_live.py` — nogo status in test fixture

---

## Task 1: Add Ubiquitous Language Rule to Agent Config Files

**Files:**
- Modify: `CLAUDE.md`
- Modify: `AGENTS.md`

- [ ] **Step 1: Add ubiquitous language section to CLAUDE.md**

Append this block to `CLAUDE.md` (after the existing graphify block):

```markdown
## Ubiquitous Language

This project has a canonical vocabulary defined in `UBIQUITOUS_LANGUAGE.md`.

Rules:
- Before using any domain term, verdict value, column name, or operator-facing string — read `UBIQUITOUS_LANGUAGE.md`
- Use only the canonical terms defined there (PASS, FAIL, GO, NO_GO, etc.)
- Do not invent synonyms or use the aliases listed in the "Aliases to avoid" column
```

- [ ] **Step 2: Add ubiquitous language section to AGENTS.md**

Insert a new section after the existing section headers in `AGENTS.md`. Add it as section **0** before the "What Is Actually Active" section:

```markdown
## 0) Ubiquitous Language

This project has a canonical vocabulary defined in `UBIQUITOUS_LANGUAGE.md`.

Before using any domain term, verdict value, column name, or operator-facing string — read `UBIQUITOUS_LANGUAGE.md`. Use only the canonical terms defined there. Do not invent synonyms or use the aliases listed in the "Aliases to avoid" column.

Key deployment decision terms:
- `PASS` — process completed correctly and produced valid evidence
- `FAIL` — process or evidence is invalid and cannot justify promotion
- `GO` — symbol is eligible for deployment
- `NO_GO` — symbol intentionally not deployed; process did not fail

```

- [ ] **Step 3: Commit**

```bash
git add CLAUDE.md AGENTS.md
git commit -m "docs: add ubiquitous language rule to agent config files"
```

---

## Task 2: Migrate validate_stage14_jforex_runtime_certification.py

**Files:**
- Modify: `scripts/validate_stage14_jforex_runtime_certification.py`
- Modify: `tests/test_validate_stage14_jforex_runtime_certification.py`

- [ ] **Step 1: Update test assertions (making them fail)**

Run this bulk sed to update all status/verdict string assertions in the test file:

```bash
sed -i '' \
  's/== "nogo"/== "NO_GO"/g; s/== "pass"/== "PASS"/g; s/== "fail"/== "FAIL"/g; s/!= "pass"/!= "PASS"/g; s/\["fail"\]/["FAIL"]/g' \
  tests/test_validate_stage14_jforex_runtime_certification.py
```

- [ ] **Step 2: Verify tests now fail**

```bash
uv run pytest tests/test_validate_stage14_jforex_runtime_certification.py -q 2>&1 | tail -10
```

Expected: multiple test failures with messages like `AssertionError: assert 'nogo' == 'NO_GO'`

- [ ] **Step 3: Update emit values in the script**

Make these changes to `scripts/validate_stage14_jforex_runtime_certification.py`:

Line 455: `status = "fail"` → `status = "FAIL"`
Line 459: `status = "pass" if bool(value) else "fail"` → `status = "PASS" if bool(value) else "FAIL"`
Line 462: `status = "fail"` → `status = "FAIL"`
Line 478: `status = "fail"` → `status = "FAIL"`
Line 496: `and status != "pass"` → `and status != "PASS"`
Line 498: `status = "nogo"` → `status = "NO_GO"`
Line 533: `int(thr_status == "pass")` → `int(thr_status == "PASS")`
Line 553: `row["verdict"] = "nogo"` → `row["verdict"] = "NO_GO"`

Update the help text at line 499 area (the `_non_deployable_nogo_details` call comment area) — search for the string and update:

```bash
sed -i '' "s/verdict=nogo/verdict=NO_GO/g" scripts/validate_stage14_jforex_runtime_certification.py
```

Apply the status/verdict value changes:

```bash
sed -i '' \
  's/status = "nogo"/status = "NO_GO"/g; s/status = "fail"/status = "FAIL"/g; s/row\["verdict"\] = "nogo"/row["verdict"] = "NO_GO"/g' \
  scripts/validate_stage14_jforex_runtime_certification.py
sed -i '' \
  's/status = "pass" if bool(value) else "fail"/status = "PASS" if bool(value) else "FAIL"/g' \
  scripts/validate_stage14_jforex_runtime_certification.py
sed -i '' \
  's/and status != "pass"/and status != "PASS"/g; s/int(thr_status == "pass")/int(thr_status == "PASS")/g' \
  scripts/validate_stage14_jforex_runtime_certification.py
```

- [ ] **Step 4: Verify tests now pass**

```bash
uv run pytest tests/test_validate_stage14_jforex_runtime_certification.py -q 2>&1 | tail -5
```

Expected: all tests pass

- [ ] **Step 5: Grep audit — confirm no old values remain in this script (excluding input-parser aliases)**

```bash
grep -n '"nogo"\|"pass"\|"fail"' scripts/validate_stage14_jforex_runtime_certification.py | grep -v "no_go\|no-go\|input\|alias\|\"pass\".*candidate\|\"pass\".*_pick"
```

Expected: no hits outside lines 65–67 (the input-parser alias set `{"no_go", "no-go", "nogo"}` and `{"pass", "green", "go"}`) and lines using `"pass"` as a dict key for the `pass` boolean column (lines 108, 145, 159, 362, 448 — these are a different concept, not the status string).

- [ ] **Step 6: Commit**

```bash
git add scripts/validate_stage14_jforex_runtime_certification.py tests/test_validate_stage14_jforex_runtime_certification.py
git commit -m "fix: align stage14 certification verdict values with ubiquitous language"
```

---

## Task 3: Migrate validate_stage13_dukascopy_testclient.py

**Files:**
- Modify: `scripts/validate_stage13_dukascopy_testclient.py`
- Modify: `tests/test_validate_stage13_dukascopy_testclient.py`

- [ ] **Step 1: Update test assertions (making them fail)**

```bash
sed -i '' \
  's/== "nogo"/== "NO_GO"/g; s/== "pass"/== "PASS"/g; s/== "fail"/== "FAIL"/g' \
  tests/test_validate_stage13_dukascopy_testclient.py
sed -i '' \
  's/stage13_dukascopy_testclient_nogo/stage13_dukascopy_testclient_no_go/g' \
  tests/test_validate_stage13_dukascopy_testclient.py
```

- [ ] **Step 2: Verify tests now fail**

```bash
uv run pytest tests/test_validate_stage13_dukascopy_testclient.py -q 2>&1 | tail -10
```

Expected: failures on verdict and column name assertions

- [ ] **Step 3: Update emit values and column name in the script**

Status/verdict string values:

```bash
sed -i '' \
  's/status_txt = "pass"/status_txt = "PASS"/g; s/status_txt = "fail"/status_txt = "FAIL"/g' \
  scripts/validate_stage13_dukascopy_testclient.py
sed -i '' \
  's/"status": "pass" if runtime_ok else "fail"/"status": "PASS" if runtime_ok else "FAIL"/g' \
  scripts/validate_stage13_dukascopy_testclient.py
sed -i '' \
  's/status_txt = "pass" if bool(value) else "fail"/status_txt = "PASS" if bool(value) else "FAIL"/g' \
  scripts/validate_stage13_dukascopy_testclient.py
sed -i '' \
  's/"nogo"/"NO_GO"/g' \
  scripts/validate_stage13_dukascopy_testclient.py
```

Column name (rename `stage13_dukascopy_testclient_nogo` → `stage13_dukascopy_testclient_no_go`):

```bash
sed -i '' \
  's/stage13_dukascopy_testclient_nogo/stage13_dukascopy_testclient_no_go/g' \
  scripts/validate_stage13_dukascopy_testclient.py
```

Update the help text string (line 482 area):

```bash
sed -i '' 's/verdict=nogo/verdict=NO_GO/g' scripts/validate_stage13_dukascopy_testclient.py
```

- [ ] **Step 4: Verify tests now pass**

```bash
uv run pytest tests/test_validate_stage13_dukascopy_testclient.py -q 2>&1 | tail -5
```

Expected: all tests pass

- [ ] **Step 5: Grep audit**

```bash
grep -n '"nogo"\|"pass"\|"fail"\|_nogo' scripts/validate_stage13_dukascopy_testclient.py | grep -v "\"pass\".*_pick\|\"pass\".*notna\|\"pass\".*candidate\|no_go\|no-go\|\"1\"\|\"0\""
```

Expected: no hits

- [ ] **Step 6: Commit**

```bash
git add scripts/validate_stage13_dukascopy_testclient.py tests/test_validate_stage13_dukascopy_testclient.py
git commit -m "fix: align stage13 certification verdict values with ubiquitous language"
```

---

## Task 4: Migrate validate_local_jforex_surrogate.py

**Files:**
- Modify: `scripts/validate_local_jforex_surrogate.py`
- Modify: `tests/test_validate_local_jforex_surrogate.py`

- [ ] **Step 1: Update test assertions (making them fail)**

```bash
sed -i '' \
  's/== "nogo"/== "NO_GO"/g; s/== "pass"/== "PASS"/g; s/== "fail"/== "FAIL"/g' \
  tests/test_validate_local_jforex_surrogate.py
sed -i '' \
  's/local_jforex_surrogate_nogo/local_jforex_surrogate_no_go/g' \
  tests/test_validate_local_jforex_surrogate.py
```

- [ ] **Step 2: Verify tests now fail**

```bash
uv run pytest tests/test_validate_local_jforex_surrogate.py -q 2>&1 | tail -10
```

Expected: failures on verdict and column name assertions

- [ ] **Step 3: Update emit values and column name in the script**

```bash
sed -i '' \
  's/status = "pass"/status = "PASS"/g; s/status = "nogo"/status = "NO_GO"/g; s/status = "fail"/status = "FAIL"/g' \
  scripts/validate_local_jforex_surrogate.py
sed -i '' \
  's/status = "pass" if bool(value) else "fail"/status = "PASS" if bool(value) else "FAIL"/g' \
  scripts/validate_local_jforex_surrogate.py
sed -i '' \
  's/"nogo"/"NO_GO"/g' \
  scripts/validate_local_jforex_surrogate.py
sed -i '' \
  's/local_jforex_surrogate_nogo/local_jforex_surrogate_no_go/g' \
  scripts/validate_local_jforex_surrogate.py
sed -i '' \
  's/verdict=nogo/verdict=NO_GO/g' \
  scripts/validate_local_jforex_surrogate.py
```

- [ ] **Step 4: Verify tests now pass**

```bash
uv run pytest tests/test_validate_local_jforex_surrogate.py -q 2>&1 | tail -5
```

Expected: all tests pass

- [ ] **Step 5: Grep audit**

```bash
grep -n '"nogo"\|"pass"\|"fail"\|_nogo' scripts/validate_local_jforex_surrogate.py | grep -v "\"pass\".*_pick\|\"pass\".*notna\|\"pass\".*candidate\|no_go\|no-go\|\"1\"\|\"0\""
```

Expected: no hits

- [ ] **Step 6: Commit**

```bash
git add scripts/validate_local_jforex_surrogate.py tests/test_validate_local_jforex_surrogate.py
git commit -m "fix: align local jforex surrogate verdict values with ubiquitous language"
```

---

## Task 5: Migrate Reader Scripts

**Files:**
- Modify: `scripts/run_monthly_recert.py`
- Modify: `scripts/run_promote_live.py`
- Modify: `tests/test_run_monthly_recert.py`
- Modify: `tests/test_run_promote_live.py`

- [ ] **Step 1: Update test assertions (making them fail)**

In `tests/test_run_monthly_recert.py` line 247, the assertion `"USDCAD  NOGO"` tests the printed summary output from `_print_summary`. The script currently prints `NOGO` (no underscore) on line 374. Both the script and the test need updating to `NO_GO`:

```bash
sed -i '' 's/"USDCAD  NOGO"/"USDCAD  NO_GO"/g' tests/test_run_monthly_recert.py
```

In `tests/test_run_promote_live.py` line 256, the test fixture CSV row contains `nogo` as a status value:

```bash
sed -i '' 's/,nogo,critical,/,NO_GO,critical,/g' tests/test_run_promote_live.py
```

- [ ] **Step 2: Verify tests now fail**

```bash
uv run pytest tests/test_run_monthly_recert.py tests/test_run_promote_live.py -q 2>&1 | tail -10
```

Expected: failures on the updated assertions

- [ ] **Step 3: Update run_monthly_recert.py**

Line 137 and 170 — guard on `"pass"`:

```bash
sed -i '' \
  's/row\["status"\] != "pass"/row["status"] != "PASS"/g' \
  scripts/run_monthly_recert.py
```

Line 151 — status set check:

```bash
sed -i '' \
  's/status in {"nogo", "no_go", "no-go"}/status in {"NO_GO", "no_go", "no-go"}/g' \
  scripts/run_monthly_recert.py
```

Line 374 — printed symbol row label (change `NOGO` → `NO_GO`):

```bash
sed -i '' 's/}NOGO  expected/}NO_GO  expected/g' scripts/run_monthly_recert.py
```

- [ ] **Step 4: Update run_promote_live.py**

Line 156 — guard on status values:

```bash
sed -i '' \
  's/not in ("pass", "nogo")/not in ("PASS", "NO_GO")/g' \
  scripts/run_promote_live.py
```

- [ ] **Step 5: Verify tests now pass**

```bash
uv run pytest tests/test_run_monthly_recert.py tests/test_run_promote_live.py -q 2>&1 | tail -5
```

Expected: all tests pass

- [ ] **Step 6: Run full test suite to confirm no regressions**

```bash
uv run pytest -q 2>&1 | tail -5
```

Expected: all 636+ tests pass

- [ ] **Step 7: Commit**

```bash
git add scripts/run_monthly_recert.py scripts/run_promote_live.py \
        tests/test_run_monthly_recert.py tests/test_run_promote_live.py
git commit -m "fix: update reader scripts to match canonical verdict values"
```

---

## Task 6: Migrate Checked-in CSVs

**Files:**
- Modify: `data/analysis/backtest_reconcile/stage13_dukascopy_testclient_summary.csv`
- Modify: `data/analysis/backtest_reconcile/local_jforex_surrogate_summary.csv`
- Modify: `data/analysis/backtest_reconcile/stage14_jforex_runtime_certification_checks.csv`
- Modify: `data/analysis/backtest_reconcile/local_jforex_surrogate_checks.csv`

- [ ] **Step 1: Patch all four CSVs atomically**

```bash
# Rename column headers and update verdict/status values
sed -i '' 's/stage13_dukascopy_testclient_nogo/stage13_dukascopy_testclient_no_go/g' \
  data/analysis/backtest_reconcile/stage13_dukascopy_testclient_summary.csv
sed -i '' 's/,nogo,/,NO_GO,/g; s/,nogo$/,NO_GO/g' \
  data/analysis/backtest_reconcile/stage13_dukascopy_testclient_summary.csv

sed -i '' 's/local_jforex_surrogate_nogo/local_jforex_surrogate_no_go/g' \
  data/analysis/backtest_reconcile/local_jforex_surrogate_summary.csv
sed -i '' 's/,nogo,/,NO_GO,/g; s/,nogo$/,NO_GO/g' \
  data/analysis/backtest_reconcile/local_jforex_surrogate_summary.csv

sed -i '' 's/,nogo,/,NO_GO,/g; s/,nogo$/,NO_GO/g' \
  data/analysis/backtest_reconcile/stage14_jforex_runtime_certification_checks.csv

sed -i '' 's/,nogo,/,NO_GO,/g; s/,nogo$/,NO_GO/g' \
  data/analysis/backtest_reconcile/local_jforex_surrogate_checks.csv
```

- [ ] **Step 2: Verify no old values remain**

```bash
grep -rn "nogo" data/analysis/backtest_reconcile/
```

Expected: no hits

- [ ] **Step 3: Spot-check headers are correct**

```bash
head -1 data/analysis/backtest_reconcile/stage13_dukascopy_testclient_summary.csv
head -1 data/analysis/backtest_reconcile/local_jforex_surrogate_summary.csv
```

Expected: column headers contain `stage13_dukascopy_testclient_no_go` and `local_jforex_surrogate_no_go` respectively

- [ ] **Step 4: Commit**

```bash
git add data/analysis/backtest_reconcile/
git commit -m "data: update certification CSVs to canonical verdict values and column names"
```

---

## Task 7: Final Verification

- [ ] **Step 1: Run full test suite**

```bash
uv run pytest -q 2>&1 | tail -5
```

Expected: all tests pass

- [ ] **Step 2: Final grep audit across all source and data**

```bash
grep -rn "\"nogo\"\|'nogo'\|,nogo,\|,nogo$" scripts/ src/ tests/ data/analysis/backtest_reconcile/ 2>/dev/null
```

Expected: no hits

```bash
grep -rn "_nogo\b" scripts/ src/ tests/ data/analysis/backtest_reconcile/ 2>/dev/null
```

Expected: no hits

- [ ] **Step 3: Confirm input-parser aliases are intact (should still accept old inputs)**

```bash
grep -n "no-go\|no_go\|nogo" scripts/validate_stage14_jforex_runtime_certification.py
```

Expected: line 67 still contains `{"0", "false", "no", "n", "fail", "red", "no_go", "no-go", "nogo"}` — the user input tolerance is preserved

- [ ] **Step 4: Build docs**

```bash
uv run mkdocs build --quiet 2>&1 | grep -v "^warning:"
```

Expected: clean output (no errors)

- [ ] **Step 5: Commit if any stragglers; otherwise confirm clean**

```bash
git status --short
```

Expected: nothing uncommitted (all changes landed in Tasks 1–6)
