# Tick Vault Weekend Gap Handling Design

## Summary

`scripts/download_tick_vault_data.py` currently treats the normal Dukascopy weekend closure as a missing-data hole. That causes repeated month-end and current-month refills starting from the first Friday close boundary found in a parquet file. The fix is to make session-boundary logic explicit and DST-aware in UTC, then use that logic consistently for gap detection and current-month incremental append decisions.

This change is limited to downloader range selection and lockfile hygiene. It does not change the parquet schema, output locations, symbol universe, or tick decoding logic.

## Problem Statement

The current behavior has two root causes:

1. `is_fx_market_open()` uses a fixed UTC rule of Sunday `22:00` to Friday `22:00`.
2. `find_first_market_gap()` flags any gap greater than two hours whose starting timestamp is considered "market open".

Observed Dukascopy data does not follow a fixed `22:00 UTC` weekly close/open year-round. The close/open boundary shifts by one hour in UTC during DST periods:

- winter regime: final Friday tradable hour ends near `21:59:59 UTC`, Sunday reopens near `22:00 UTC`
- DST regime: final Friday tradable hour ends near `20:59:59 UTC`, Sunday reopens near `21:00 UTC`

Because the script does not model that shift, it treats the scheduled weekend closure as a missing hole. `get_missing_months()` then uses that false positive before current-month append logic, so a Friday run can schedule refills from the first normal weekend boundary earlier in the month.

## Goals

- Ignore scheduled weekend closures when detecting data gaps.
- Keep detecting true unexpected intra-session gaps.
- Make current-month append stop at the effective session end instead of `datetime.now()` when the market is closed.
- Prevent Friday-after-close, Saturday, and pre-open Sunday runs from trying to fetch unavailable hours.
- Remove stale lockfiles automatically when they are clearly orphaned.

## Non-Goals

- No rewrite of the downloader around a new scheduling system.
- No changes to tick_vault internals or external cache layout.
- No backfill policy changes beyond better gap classification.
- No parquet migration or artifact rewrite outside normal downloader behavior.

## Recommended Approach

Implement a small session-boundary helper inside `scripts/download_tick_vault_data.py` and route both gap detection and current-month append through it.

This is preferred over a Friday-only cutoff because the real issue is not "the last Friday hour is unavailable". The data shows that the final tradable Friday hour exists, but its UTC hour changes with DST. The script needs to understand the scheduled weekly closure window rather than suppress a hardcoded hour.

## Design

### 1. Session Boundary Model

Add a helper with one clear responsibility: classify whether a timestamp is in-session and whether a gap falls entirely inside a scheduled weekend closure.

Required behavior:

- Determine the effective weekly close hour in UTC for a given date.
- Determine the effective weekly reopen hour in UTC for the corresponding Sunday.
- Return whether a timestamp is inside an expected open session.
- Return whether a gap from `prev_ts` to `next_ts` is an expected weekend closure rather than a missing-data hole.
- Return the latest timestamp that should be considered fetchable at the moment of the run.

The model should be based on DST-aware UTC boundaries, matching the observed Dukascopy parquet tails:

- winter session boundary: close near `22:00 UTC`, reopen near `22:00 UTC`
- DST session boundary: close near `21:00 UTC`, reopen near `21:00 UTC`

The implementation should keep the logic in one place so the downloader does not duplicate close/open assumptions across multiple branches.

### 2. Gap Detection

Update `find_first_market_gap()` so it examines each `>2h` gap as a pair of timestamps:

- `prev_ts`: last observed tick before the gap
- `next_ts`: first observed tick after the gap

The function should return a gap only when:

- the gap is not an expected weekend closure, and
- it occurs during a scheduled open session

Expected weekend closures should be ignored even if the gap begins during the final tradable Friday hour. This is the key regression fix.

Unexpected gaps that must still be surfaced:

- weekday intra-session holes
- Sunday/Monday holes after the expected reopen window
- shortened month files that stop before the expected end of the active trading session while the market should still be open

### 3. Current-Month Append Logic

Update `get_missing_months()` so current-month handling does not get preempted by the first normal weekend closure in the file.

Required order:

1. If the month file does not exist, schedule the whole month range as today.
2. If the month is the current month, calculate `fetchable_end` from the new session helper.
3. Append from `last_ts + 1ms` only if that start is before `fetchable_end`.
4. Only use historical gap scanning for the current month when checking for unexpected gaps, not scheduled weekend closures.
5. For past months, continue scanning for unexpected gaps and suspicious early endings.

This keeps the intended incremental-upsert behavior while preserving real gap detection.

### 4. Historical Boundary Check

Keep the "file ends early on a market day" check, but route it through the session helper so it uses expected session boundaries instead of the current `last_ts.hour < 21` heuristic.

This check should only trigger when:

- the file ends before the expected end of an open session, and
- the missing tail is not explained by the normal weekend closure

### 5. Stale Lockfile Handling

Keep the existing lockfile guard, but add a conservative orphan check:

- if the lockfile exists and a process whose command line includes `scripts/download_tick_vault_data.py` is active, fail as today unless `--force` is set
- if the lockfile exists and no matching downloader process is active, remove the stale lockfile and continue
- if process ownership cannot be determined reliably, preserve the current safe behavior and require `--force`

This is intentionally small in scope. It prevents obvious false blocking without turning the lockfile into a complex process registry.

## Error Handling

- If session-boundary classification cannot be computed for a timestamp, fail safe by logging and treating the range as not fetchable rather than downloading beyond the expected close.
- If stale-lock detection raises an error, keep the current lockfile failure path unless `--force` is set.
- Gap detection should continue to swallow parquet-read exceptions as it does today, but log enough context to distinguish unreadable files from true "no gap" results if that path is touched during implementation.

## Testing Strategy

Add focused tests for `scripts/download_tick_vault_data.py` helper behavior. The tests should not require live network access.

Required coverage:

- winter Friday close and Sunday reopen classification
- DST Friday close and Sunday reopen classification
- weekend gap is ignored when it matches the scheduled closure window
- weekday intra-session gap is still flagged
- current-month Friday-after-close run does not schedule a refill beyond the effective close
- Saturday run schedules no current-month append
- Sunday pre-open run schedules no current-month append
- stale lockfile is removed when clearly orphaned
- active lockfile is still respected

Use synthetic timestamps and small temporary parquet fixtures rather than real production parquet files.

## Implementation Notes

- Keep the new helper functions in this script unless they become large enough to justify extraction.
- Prefer names that describe scheduled session behavior, not trading strategy behavior.
- Avoid burying DST logic in multiple boolean branches. One source of truth is the main maintainability requirement.
- Do not change external file paths or the canonical parquet schema.

## Validation

Before calling the change complete:

- run targeted tests for the downloader helper logic
- run at least one dry or bounded downloader execution that shows no repeated refill triggered by a normal Friday close boundary
- verify a known synthetic weekday gap still produces a refill range
- confirm the stale-lock path behaves correctly for both orphaned and active cases

## Risks

- The DST boundary could still be encoded incorrectly if the helper uses the wrong calendar convention. Tests must cover both winter and DST examples from the observed parquet data.
- A too-broad "ignore weekend gaps" rule could hide real missing data near reopen. The implementation must classify the whole gap window, not just the starting timestamp.
- Reordering current-month logic could accidentally skip a genuine unexpected gap unless tests cover both append and gap-detection paths.
