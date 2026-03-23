# Monthly Recert Manual Verification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Execute the remaining real-data verification for the monthly recertification and promotion flow, and capture evidence of what passed, failed, or blocked.

**Architecture:** This is an operational verification plan, not a feature-build plan. Execute it in a dedicated worktree, write all observations into a single audit note, and treat negative-path validation, default recert, override recert, freeze validation, and promotion validation as separate checkpoints. If any command exposes a product defect, stop and write a follow-up bugfix plan instead of improvising code changes during verification.

**Tech Stack:** `make`, `uv`, Python helper scripts, CSV/Markdown artifacts, git worktrees

---

## File Structure

- Create: `docs/superpowers/audits/2026-03-21-monthly-recert-manual-verification.md` — execution log and evidence record for the manual verification run
- Reference: `Makefile`
- Reference: `scripts/run_monthly_recert.py`
- Reference: `scripts/run_promote_live.py`
- Reference: `scripts/freeze_oco_live_governance.py`
- Reference: `scripts/freeze_oco_historical_governance.py`
- Reference: `data/analysis/backtest_reconcile/stage14_jforex_runtime_certification_checks.csv`
- Reference: `docs/analysis/stage14_jforex_runtime_certification_report.md`
- Reference: `docs/strategy_bible/generated/stage_14_snapshot.md`
- Reference: `configs/research/governance/oco_dukascopy_candidate/`
- Reference: `configs/research/governance/oco_history_dukascopy_candidate/`

## Execution Rules

- Run this plan in a dedicated worktree, not on `main`.
- Do not change code during this plan unless the human explicitly redirects from verification into bugfix work.
- Do not delete or rewrite user data under `/Users/danielfisher/Desktop/dukascopy_ticks`.
- Treat `monthly-recert` orchestration success and certification pass/fail as different things:
  - orchestration success means the command derived the right month/window, ran both subprocesses, and printed a summary
  - certification success means the resulting Stage 14 checks are fresh and all critical checks passed
- Do not run the positive `promote-live` step unless same-day critical checks are all passing in the default report directory.

### Task 1: Create The Audit Note And Preflight Snapshot

**Files:**
- Create: `docs/superpowers/audits/2026-03-21-monthly-recert-manual-verification.md`
- Reference: `scripts/run_monthly_recert.py`
- Reference: `scripts/run_promote_live.py`
- Reference: `Makefile`

- [ ] **Step 1: Create the audit note skeleton**

Create `docs/superpowers/audits/2026-03-21-monthly-recert-manual-verification.md` with:

```markdown
# Monthly Recert Manual Verification

## Environment
- Worktree:
- Branch:
- Commit:
- Verification date (UTC):

## Preflight
- Repo status:
- Dukascopy tick root present:
- Candidate governance dir present:
- Candidate history dir present:
- Models dir present:
- Candidate experiment dir present:
- Candidate analysis dir present:

## Negative Promote-Live Guardrail
- Command:
- Exit code:
- Key output:
- Result:

## Freeze OCO Dukascopy Candidate
- Command:
- Exit code:
- Key output:
- Artifact check result:

## Default Monthly Recert
- Command:
- Exit code:
- Derived model month:
- Derived window:
- Step invocation check:
- Certification freshness check:
- Critical-check summary:
- Result:

## Override Monthly Recert (2025-07)
- Command:
- Exit code:
- Derived model month:
- Derived window:
- Step invocation check:
- Critical-check summary:
- Result:

## Promote Live
- Precondition check:
- Command:
- Exit code:
- Key output:
- Archived month:
- History artifact check result:
- Result:

## Git Diff Review
- Changed files:
- Notes:

## Final Outcome
- Overall status:
- Blockers:
- Follow-up required:
```

- [ ] **Step 2: Capture worktree and repo metadata**

Run:

```bash
git branch --show-current
git rev-parse --short HEAD
date -u +"%Y-%m-%dT%H:%M:%SZ"
git status --short
```

Expected:
- branch is the dedicated verification branch, not `main`
- `git status --short` reflects only the expected local state for that worktree before verification starts

- [ ] **Step 3: Verify required inputs and directories exist**

Run:

```bash
test -d /Users/danielfisher/Desktop/dukascopy_ticks && echo DUKASCOPY_TICKS_OK
test -d models/oco && echo MODELS_OK
test -d configs/research/experiments_dukascopy_candidate && echo EXPERIMENTS_OK
test -d data/analysis/tick_opportunity_mining_dukascopy_candidate && echo ANALYSIS_OK
test -d configs/research/governance/oco_dukascopy_candidate && echo LIVE_GOV_OK
test -d configs/research/governance/oco_history_dukascopy_candidate && echo HISTORY_GOV_OK
```

Expected: all six `*_OK` lines print.

- [ ] **Step 4: Record the current cert CSV state before any commands**

Run:

```bash
UV_CACHE_DIR=.uv_cache uv run python - <<'PY'
import csv
from pathlib import Path

path = Path("data/analysis/backtest_reconcile/stage14_jforex_runtime_certification_checks.csv")
print(f"exists={path.exists()}")
if path.exists():
    rows = list(csv.DictReader(path.open()))
    days = sorted({row.get("evaluated_at_utc", "")[:10] for row in rows if row.get("evaluated_at_utc")})
    critical_failures = [
        (row["symbol"], row["check_id"])
        for row in rows
        if row.get("severity") == "critical" and row.get("status") != "pass"
    ]
    print(f"row_count={len(rows)}")
    print(f"evaluated_days={days}")
    print(f"critical_failure_count={len(critical_failures)}")
    if critical_failures:
        print(f"sample_failures={critical_failures[:5]}")
PY
```

Expected:
- the command prints whether the CSV already exists
- if it exists, the command prints evaluated days and current critical failure count

- [ ] **Step 5: Update the audit note with the preflight results**

Expected: the audit note now contains enough context for someone else to tell what environment the rest of the run used.

### Task 2: Prove The Negative `promote-live` Guardrail

**Files:**
- Modify: `docs/superpowers/audits/2026-03-21-monthly-recert-manual-verification.md`
- Reference: `scripts/run_promote_live.py`
- Reference: `Makefile`

- [ ] **Step 1: Create a deterministic empty report directory**

Run:

```bash
TMP_EMPTY_REPORT_DIR=$(mktemp -d /tmp/promote-live-empty.XXXXXX)
printf '%s\n' "$TMP_EMPTY_REPORT_DIR"
```

Expected: prints a new temp directory path under `/tmp/`.

- [ ] **Step 2: Run `promote-live` against the empty report directory**

Run:

```bash
make promote-live REPORT_DIR="$TMP_EMPTY_REPORT_DIR" >/tmp/promote-live-negative.log 2>&1; rc=$?; cat /tmp/promote-live-negative.log; exit $rc
```

Expected:
- exits non-zero
- output contains `no cert results found`

- [ ] **Step 3: Record the negative-path result in the audit note**

Expected: the audit note captures the exact exit status and the key error text.

### Task 3: Run And Validate `freeze-oco-dukascopy-candidate`

**Files:**
- Modify: `docs/superpowers/audits/2026-03-21-monthly-recert-manual-verification.md`
- Reference: `Makefile`
- Reference: `configs/research/governance/oco_dukascopy_candidate/`

- [ ] **Step 1: Snapshot the candidate governance file list before the run**

Run:

```bash
find configs/research/governance/oco_dukascopy_candidate -maxdepth 1 -type f | sort > /tmp/oco-dukascopy-candidate-before.txt
wc -l /tmp/oco-dukascopy-candidate-before.txt
head -20 /tmp/oco-dukascopy-candidate-before.txt
```

Expected: a sorted file list is written to `/tmp/oco-dukascopy-candidate-before.txt`.

- [ ] **Step 2: Run the candidate freeze target**

Run:

```bash
make freeze-oco-dukascopy-candidate >/tmp/freeze-oco-dukascopy-candidate.log 2>&1; rc=$?; cat /tmp/freeze-oco-dukascopy-candidate.log; exit $rc
```

Expected:
- exits `0`
- output contains `Dukascopy-candidate governance locks frozen`

- [ ] **Step 3: Verify the expected per-symbol candidate artifacts exist**

Run:

```bash
UV_CACHE_DIR=.uv_cache uv run python - <<'PY'
from pathlib import Path

symbols = ["eurusd", "gbpusd", "usdjpy", "usdchf", "audusd", "usdcad"]
base = Path("configs/research/governance/oco_dukascopy_candidate")
missing = []
for sym in symbols:
    for suffix in ("_oco_live_lock.json", "_oco_allowed_states.csv"):
        path = base / f"{sym}{suffix}"
        if not path.exists():
            missing.append(str(path))
if missing:
    print("MISSING")
    for item in missing:
        print(item)
    raise SystemExit(1)
print("OK")
PY
```

Expected: prints `OK`.

- [ ] **Step 4: Record the freeze result and any git diff in the audit note**

Run:

```bash
git status --short configs/research/governance/oco_dukascopy_candidate
```

Expected: any changed candidate governance files are visible and recorded in the audit note.

### Task 4: Run The Default `monthly-recert`

**Files:**
- Modify: `docs/superpowers/audits/2026-03-21-monthly-recert-manual-verification.md`
- Reference: `Makefile`
- Reference: `scripts/run_monthly_recert.py`
- Reference: `data/analysis/backtest_reconcile/stage14_jforex_runtime_certification_checks.csv`

- [ ] **Step 1: Run the default monthly recert command**

Run:

```bash
make monthly-recert >/tmp/monthly-recert-default.log 2>&1; rc=$?; cat /tmp/monthly-recert-default.log; printf '\nRC=%s\n' "$rc"; exit 0
```

Expected:
- output contains `[monthly-recert] running for MODEL_MONTH=`
- output contains `step 1/2: jforex-dukascopy-matrix`
- output contains `step 2/2: full-stage14-cert`
- output ends with a per-symbol summary

- [ ] **Step 2: Verify the derived month and window were printed**

Run:

```bash
rg -n "\\[monthly-recert\\] running for MODEL_MONTH=|step 1/2|step 2/2|go/no-go:" /tmp/monthly-recert-default.log
```

Expected:
- the log contains the top-level start line
- the log contains both step labels
- the log contains the final `go/no-go:` line

- [ ] **Step 3: Verify the Stage 14 checks CSV is fresh after the default run**

Run:

```bash
UV_CACHE_DIR=.uv_cache uv run python - <<'PY'
import csv
from datetime import date
from pathlib import Path

today = date.today().isoformat()
path = Path("data/analysis/backtest_reconcile/stage14_jforex_runtime_certification_checks.csv")
if not path.exists():
    raise SystemExit("missing checks csv")
rows = list(csv.DictReader(path.open()))
days = sorted({row.get("evaluated_at_utc", "")[:10] for row in rows if row.get("evaluated_at_utc")})
critical_failures = [
    (row["symbol"], row["check_id"])
    for row in rows
    if row.get("severity") == "critical" and row.get("status") != "pass"
]
print(f"today={today}")
print(f"evaluated_days={days}")
print(f"critical_failure_count={len(critical_failures)}")
if critical_failures:
    print(f"sample_failures={critical_failures[:10]}")
PY
```

Expected:
- the checks CSV exists
- `evaluated_days` includes today
- the command prints whether there are any critical failures

- [ ] **Step 4: Apply the stop rule before proceeding**

Stop and write a follow-up bugfix plan if any of these are true:
- the default run log does not show both subprocess labels
- the checks CSV is missing after the run
- the command failed before printing a summary

If the orchestration worked but the summary is `NO-GO`, record that fact and continue to Task 5. Promotion still remains blocked unless a later same-day run produces all-pass critical checks.

### Task 5: Run The `MODEL_MONTH=2025-07` Override Path

**Files:**
- Modify: `docs/superpowers/audits/2026-03-21-monthly-recert-manual-verification.md`
- Reference: `Makefile`
- Reference: `scripts/run_monthly_recert.py`

- [ ] **Step 1: Run the override command**

Run:

```bash
make monthly-recert MODEL_MONTH=2025-07 >/tmp/monthly-recert-2025-07.log 2>&1; rc=$?; cat /tmp/monthly-recert-2025-07.log; printf '\nRC=%s\n' "$rc"; exit 0
```

Expected:
- output contains `MODEL_MONTH=2025-07`
- output contains `window=2025-07-04→2025-07-09`
- output contains both step labels and a final summary

- [ ] **Step 2: Verify the override window explicitly**

Run:

```bash
rg -n "MODEL_MONTH=2025-07|window=2025-07-04→2025-07-09|step 1/2|step 2/2|go/no-go:" /tmp/monthly-recert-2025-07.log
```

Expected: all five patterns appear in the log.

- [ ] **Step 3: Record the override result in the audit note**

Expected: the audit note makes it clear whether the override path worked even if the certification result was `NO-GO`.

### Task 6: Run The Positive `promote-live` Path Only If Precondition Passes

**Files:**
- Modify: `docs/superpowers/audits/2026-03-21-monthly-recert-manual-verification.md`
- Reference: `scripts/run_promote_live.py`
- Reference: `configs/research/governance/oco_history_dukascopy_candidate/`

- [ ] **Step 1: Verify the default report directory has a same-day all-pass critical cert**

Run:

```bash
UV_CACHE_DIR=.uv_cache uv run python - <<'PY'
import csv
from datetime import date
from pathlib import Path

today = date.today().isoformat()
path = Path("data/analysis/backtest_reconcile/stage14_jforex_runtime_certification_checks.csv")
if not path.exists():
    raise SystemExit("BLOCKED: missing checks csv")
rows = list(csv.DictReader(path.open()))
stale = any((row.get("evaluated_at_utc", "")[:10] not in ("", today)) for row in rows)
critical_failures = [
    (row["symbol"], row["check_id"])
    for row in rows
    if row.get("severity") == "critical" and row.get("status") != "pass"
]
print(f"today={today}")
print(f"stale={stale}")
print(f"critical_failure_count={len(critical_failures)}")
if critical_failures:
    print(f"sample_failures={critical_failures[:10]}")
if stale or critical_failures:
    raise SystemExit(1)
print("PROMOTION_PRECONDITION_OK")
PY
```

Expected:
- prints `PROMOTION_PRECONDITION_OK` only when the positive promotion path is safe to test

- [ ] **Step 2: Stop here if the promotion precondition is not met**

Expected:
- if the precondition command fails, do not run `make promote-live`
- record the block in the audit note and hand the failure back as a system/readiness issue rather than forcing a promotion

- [ ] **Step 3: Run `promote-live` after a passing same-day recert**

Run:

```bash
make promote-live >/tmp/promote-live-positive.log 2>&1; rc=$?; cat /tmp/promote-live-positive.log; printf '\nRC=%s\n' "$rc"; exit $rc
```

Expected:
- exits `0`
- output contains `[promote-live] verifying cert`
- output contains `[promote-live] archiving locks for`
- output contains `locks archived for`
- output contains `make jforex-live`

- [ ] **Step 4: Verify the archived history month contains all expected per-symbol artifacts**

First derive the expected model month:

```bash
UV_CACHE_DIR=.uv_cache uv run python - <<'PY'
from datetime import date
today = date.today()
if today.month == 1:
    print(f"{today.year - 1:04d}-12")
else:
    print(f"{today.year:04d}-{today.month - 1:02d}")
PY
```

Then replace `<MODEL_MONTH>` below with that printed value and run:

```bash
UV_CACHE_DIR=.uv_cache uv run python - <<'PY'
from pathlib import Path

model_month = "<MODEL_MONTH>"
symbols = ["eurusd", "gbpusd", "usdjpy", "usdchf", "audusd", "usdcad"]
base = Path("configs/research/governance/oco_history_dukascopy_candidate") / model_month
missing = []
for sym in symbols:
    for suffix in ("_oco_live_lock.json", "_oco_allowed_states.csv", "_oco_locked_predictions.parquet"):
        path = base / f"{sym}{suffix}"
        if not path.exists():
            missing.append(str(path))
if missing:
    print("MISSING")
    for item in missing:
        print(item)
    raise SystemExit(1)
print("OK")
PY
```

Expected: prints `OK`.

- [ ] **Step 5: Record the promotion result and archived month in the audit note**

Expected: the audit note makes it obvious whether live promotion actually happened or remained blocked.

### Task 7: Review Diffs And Close Out The Verification Run

**Files:**
- Modify: `docs/superpowers/audits/2026-03-21-monthly-recert-manual-verification.md`
- Reference: `git status`

- [ ] **Step 1: Review the final diff footprint**

Run:

```bash
git status --short
git diff --stat
```

Expected:
- you can identify every tracked artifact changed by freeze, recert, and promotion

- [ ] **Step 2: Update the audit note with final outcome and follow-up**

Expected:
- the audit note clearly states one of:
  - verification complete and promotion validated
  - verification complete but promotion blocked by cert failures
  - verification blocked by tooling/runtime defect requiring a bugfix plan

- [ ] **Step 3: Do not auto-commit generated artifacts in this plan**

Expected:
- stop after evidence capture and diff review
- if the output artifacts are intended to become authoritative repo state, handle that in a separate integration step after human review

---

## Success Criteria

This plan is complete when:

- the audit note exists and contains preflight, command, artifact, and result evidence for every remaining manual step
- the negative `promote-live` guardrail has been observed deterministically
- `freeze-oco-dukascopy-candidate` has been run and its per-symbol outputs verified
- the default `monthly-recert` path has been observed with real data
- the `MODEL_MONTH=2025-07` override path has been observed with real data
- the positive `promote-live` path has either been validated end-to-end or explicitly blocked by same-day certification state
- any defect uncovered during manual verification has been documented for follow-up instead of patched ad hoc
