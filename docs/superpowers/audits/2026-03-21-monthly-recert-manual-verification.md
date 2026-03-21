# Monthly Recert Manual Verification

## Environment
- Worktree: `/Users/danielfisher/repositories/behemoth/.worktrees/monthly-recert-manual-verification`
- Branch: `monthly-recert-manual-verification`
- Commit: branch HEAD at preflight-capture time for this verification run
- Verification date (UTC): `2026-03-21T13:40:12Z`

## Preflight
- Repo status: clean (`git status --short` returned no output)
- Dukascopy tick root present: `DUKASCOPY_TICKS_OK`
- Candidate governance dir present: `LIVE_GOV_OK`
- Candidate history dir present: `HISTORY_GOV_OK`
- Models dir present: missing (`test -d models/oco` exited non-zero)
- Candidate experiment dir present: `EXPERIMENTS_OK`
- Candidate analysis dir present: missing (`test -d data/analysis/tick_opportunity_mining_dukascopy_candidate` exited non-zero)
- Stage 14 cert CSV snapshot (source: `data/analysis/backtest_reconcile/stage14_jforex_runtime_certification_checks.csv`):
  - exists: `True`
  - row_count: `42`
  - evaluated_days: `['2026-03-20']`
  - critical_failure_count: `0`

## Negative Promote-Live Guardrail
- Command: not run yet
- Exit code: not run yet
- Key output: not run yet
- Result: pending

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
