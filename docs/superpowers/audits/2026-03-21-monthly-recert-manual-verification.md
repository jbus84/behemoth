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
- Clarification: the `make` wrapper reported `Error 1`, while the full shell command exited `2` after the log capture pipeline propagated the wrapper's failure status.
- Result: `promote-live` fails against a freshly created empty report directory because the cert CSV is missing

## Freeze OCO Dukascopy Candidate
- Pre-run snapshot command: `find configs/research/governance/oco_dukascopy_candidate -maxdepth 1 -type f | sort > /tmp/oco-dukascopy-candidate-before.txt`
- Pre-run snapshot count: `6`
- Pre-run snapshot first files:
  - `configs/research/governance/oco_dukascopy_candidate/audusd_oco_live_lock.json`
  - `configs/research/governance/oco_dukascopy_candidate/eurusd_oco_live_lock.json`
  - `configs/research/governance/oco_dukascopy_candidate/gbpusd_oco_live_lock.json`
  - `configs/research/governance/oco_dukascopy_candidate/usdcad_oco_live_lock.json`
  - `configs/research/governance/oco_dukascopy_candidate/usdchf_oco_live_lock.json`
  - `configs/research/governance/oco_dukascopy_candidate/usdjpy_oco_live_lock.json`
- Freeze command: `make freeze-oco-dukascopy-candidate >/tmp/freeze-oco-dukascopy-candidate.log 2>&1; rc=$?; cat /tmp/freeze-oco-dukascopy-candidate.log; exit $rc`
- Exit code: `0`
- Key output:
  - `wrote: configs/research/governance/oco_dukascopy_candidate/eurusd_oco_live_lock.json`
  - `wrote: configs/research/governance/oco_dukascopy_candidate/eurusd_oco_allowed_states.csv`
  - `wrote: configs/research/governance/oco_dukascopy_candidate/usdcad_oco_live_lock.json`
  - `wrote: configs/research/governance/oco_dukascopy_candidate/usdcad_oco_allowed_states.csv`
  - `6 lock JSONs and 6 allowed-states CSVs were written`
  - `✅ Dukascopy-candidate governance locks frozen.`
- Artifact check result: `OK`
- Runtime note: `UV_CACHE_DIR=.uv_cache uv run` emitted a non-blocking `VIRTUAL_ENV` mismatch warning, but the freeze and artifact checks completed successfully
- Repo-state traceability: the Environment commit (`81918a6`) is the preflight-capture HEAD. The freeze artifacts were generated later from the then-current repo state, and the generated lock JSON metadata records that later commit rather than the earlier preflight snapshot.

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
- Changed files:
  - `configs/research/governance/oco_dukascopy_candidate/audusd_oco_live_lock.json`
  - `configs/research/governance/oco_dukascopy_candidate/eurusd_oco_live_lock.json`
  - `configs/research/governance/oco_dukascopy_candidate/gbpusd_oco_live_lock.json`
  - `configs/research/governance/oco_dukascopy_candidate/usdcad_oco_live_lock.json`
  - `configs/research/governance/oco_dukascopy_candidate/usdchf_oco_live_lock.json`
  - `configs/research/governance/oco_dukascopy_candidate/usdjpy_oco_live_lock.json`
- Notes: The freeze rewrote the six candidate live-lock JSON files in place. The candidate allowed-states CSVs were verified to exist for all six symbols and did not show up in `git status`, so they appear unchanged relative to the worktree baseline. These six modified governance lock JSONs are intentionally left uncommitted for this verification flow.

## Final Outcome
- Overall status: done
- Blockers: none for this task
- Follow-up required: none for Task 3. The generated governance artifacts remain uncommitted by design; only this markdown cleanup will be committed.
