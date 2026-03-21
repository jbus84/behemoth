# Monthly Recert Manual Verification

## Environment
- Worktree: `/Users/danielfisher/repositories/behemoth/.worktrees/monthly-recert-manual-verification`
- Branch: `monthly-recert-manual-verification`
- Commit: branch HEAD at preflight-capture time (`81918a6`)
- Verification date (UTC): `2026-03-21T13:40:12Z`

## Preflight
- Repo status: clean (`git status --short` returned no output)
- Dukascopy tick root present: `/Users/danielfisher/Desktop/dukascopy_ticks` exists
- Candidate governance dir present: `configs/research/governance/oco_dukascopy_candidate` exists
- Candidate history dir present: `configs/research/governance/oco_history_dukascopy_candidate` exists
- Models dir present: missing (`test -d models/oco` exited non-zero)
- Candidate experiment dir present: `configs/research/experiments_dukascopy_candidate` exists
- Candidate analysis dir present: missing (`test -d data/analysis/tick_opportunity_mining_dukascopy_candidate` exited non-zero)
- Stage 14 cert CSV snapshot (source: `data/analysis/backtest_reconcile/stage14_jforex_runtime_certification_checks.csv`):
  - exists: `True`
  - row_count: `42`
  - evaluated_days: `['2026-03-20']`
  - critical_failure_count: `0`

## Negative Promote-Live Guardrail
- Temp-dir creation command: `TMP_EMPTY_REPORT_DIR=$(mktemp -d /tmp/promote-live-empty.XXXXXX); printf '%s\n' "$TMP_EMPTY_REPORT_DIR"`
- Temp-dir path: `/tmp/promote-live-empty.sl4DN8`
- Exact command form from plan: `make promote-live REPORT_DIR="$TMP_EMPTY_REPORT_DIR"`
- Executed command: `make promote-live REPORT_DIR=/tmp/promote-live-empty.sl4DN8 >/tmp/promote-live-negative.log 2>&1; rc=$?; cat /tmp/promote-live-negative.log; exit $rc`
- Exit code: `2`
- Key output:
  - `[promote-live] no cert results found at /tmp/promote-live-empty.sl4DN8/stage14_jforex_runtime_certification_checks.csv; run make monthly-recert first`
  - `make: *** [promote-live] Error 1`
- Result: `promote-live` fails against a freshly created empty report directory because the cert CSV is missing

## Freeze OCO Dukascopy Candidate
- Command: not run yet
- Exit code: not run yet
- Key output: not run yet
- Artifact check result: pending

## Default Monthly Recert
- Command: not run yet
- Exit code: not run yet
- Derived model month: not run yet
- Derived window: not run yet
- Step invocation check: pending
- Certification freshness check: pending
- Critical-check summary: pending
- Result: pending

## Override Monthly Recert (2025-07)
- Command: not run yet
- Exit code: not run yet
- Derived model month: not run yet
- Derived window: not run yet
- Step invocation check: pending
- Critical-check summary: pending
- Result: pending

## Promote Live
- Precondition check: not run yet
- Command: not run yet
- Exit code: not run yet
- Key output: not run yet
- Archived month: not run yet
- History artifact check result: pending
- Result: pending

## Git Diff Review
- Changed files: `docs/superpowers/audits/2026-03-21-monthly-recert-manual-verification.md`
- Notes: task 1 only; later verification steps remain pending

## Final Outcome
- Overall status: in progress
- Blockers: `models/oco` missing; `data/analysis/tick_opportunity_mining_dukascopy_candidate` missing
- Follow-up required: run the remaining recertification and promote-live verification steps once the required candidate artifacts are available
