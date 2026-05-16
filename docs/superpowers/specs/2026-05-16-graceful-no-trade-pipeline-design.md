# Graceful No-Trade Pipeline — Design Spec

**Date:** 2026-05-16
**Status:** Approved design, pending implementation plan

## Problem

After #173 removed the look-ahead-conditioned `first_touch_clean` family, the
look-ahead-free `oco_first_touch` universe for some symbols genuinely clears no
selection gates — a true negative. The plan for #173 explicitly accepted this:
"if no `first_touch` candidate clears the selection gates, nothing deploys and
the live system trades nothing — the intended, accepted outcome."

The pipeline cannot express that outcome. It crashes instead:

- `run_tick_opportunity_monthly_wfo.py` writes its per-library predictions
  parquet only `if not p.empty`. When a WFO produces zero predictions it
  **skips the write**, leaving a stale file from a previous run in place.
- `select_oco_reduced_core_rolling.py` (Stage 2f) has hard `raise RuntimeError`
  guards at every empty-data junction (`candidate filter empty`,
  `no predictions left after candidate metadata merge`, `selection empty`).
- `make retrain-all` runs each symbol with `... || exit 1`, so the first
  symbol that finds nothing kills the entire multi-symbol run.

Observed on 2026-05-16: EURUSD's OCO fullcap WFO produced 0 predictions. The
write was skipped, so Stage 2f read a stale 2026-05-01 predictions parquet
(1.2M rows, pre-#173 `first_touch_clean` UIDs), failed to join it against the
fresh `oco_first_touch` candidate CSV, and raised `no predictions left after
candidate metadata merge` — aborting `retrain-all` before any other symbol ran.

The stale file is the more dangerous half: had its UIDs happened to match, the
pipeline would have silently selected and frozen a governance lock on 15-day-old,
look-ahead-biased predictions.

## Goal

A genuine per-symbol no-trade outcome must flow cleanly through the whole
pipeline — WFO, reduced-core selection, freeze, promote-live, registry
validation, certification — producing a well-formed `NO_GO` governance lock
that deploys nothing. A no-trade symbol must not abort the run or block other
symbols. Genuine bugs must still fail loud.

## Scope

Whole pipeline including `promote-live`, registry validation, and
certification stages.

## Approach: empty-artifact convention

The no-trade signal propagates as empty (schema-correct) artifacts cascading
down the existing file-passing contract between stages. No new per-stage
artifact type is introduced. A single explicit outcome record exists only at
the `retrain-all` aggregation level.

### Section 1 — Artifact-writer contract

Every stage writer always emits its output artifact with the correct schema,
even at 0 rows, overwriting any prior file.

Concrete fix: `run_tick_opportunity_monthly_wfo.py:850-869` guards each write
(`metrics`, `thresholds`, `predictions`, `importance`) with `if not X.empty:`.
Drop the guards — always write the four `{symbol}_{lib}_monthly_*` artifacts.
An empty write must still carry the correct columns so downstream schema checks
can distinguish "empty" from "malformed".

Audit the other in-scope writers (opportunity mining → `oco_candidates.csv`,
stop-limit tickfill, reduced-core) for the same skip-on-empty pattern and apply
the same rule.

**Invariant:** a stage that ran produces a current artifact. A *missing*
artifact means the stage did not run — always a hard error.

### Section 2 — Reader classification rule

Every stage reader classifies each input artifact into exactly one of three
states:

| State | Meaning | Action |
|---|---|---|
| Missing | upstream stage did not run | hard error, exit 1 |
| Present, malformed — or rows present but fail to join / schema-mismatch | a bug (stale file, UID drift, wrong path) | hard error, exit 1 |
| Present, well-formed, 0 rows | genuine no-trade | write own empty output, exit 0 |

The merge failure observed on 2026-05-16 (predictions have rows but do not join
the candidate CSV) stays a **hard error**. Emptiness is graceful only when the
*input artifact itself* is empty — never when two non-empty inputs disagree.

### Section 3 — Per-stage no-trade behaviour

When a stage classifies its input as genuine no-trade it writes empty,
schema-correct outputs and exits 0, so the next stage sees a clean empty input
and does the same.

- **Stage 2f** (`select_oco_reduced_core_rolling.py`) — empty
  `*_oco_reduced_state_schedule.csv` and `*_oco_reduced_summary.csv`; one
  summary row with `status = NO_TRADE`. The three `raise RuntimeError` sites
  (`candidate filter empty`, `no predictions left after candidate metadata
  merge`, `selection empty`) are reclassified per Section 2: empty *input*
  → graceful; non-empty inputs that fail to join → still raise.
- **freeze** (`freeze_oco_live_governance.py`) — a valid governance lock with
  an empty `state_universe` and verdict `NO_GO` (canonical value). The lock is
  well-formed and hashed; it simply deploys nothing.
- **promote-live** — accepts the `NO_GO` lock, records the symbol as not
  deployed, trades nothing.
- **registry validation / certification** — a `NO_GO` lock with an empty
  `state_universe` is a valid, expected state, not a validation failure.

A no-trade symbol thus flows from WFO to a `NO_GO` live lock, fully auditable,
never crashing.

### Section 4 — `retrain-all` loop and operator summary

Today `Makefile:195` runs each symbol with `... || exit 1`; the first failure
kills the run.

New behaviour:

- Each symbol's `onboard_symbol.py` run resolves to one outcome: `DEPLOY`
  (states selected), `NO_TRADE` (genuine no-trade, exit 0), or `FAILED` (hard
  error, exit 1).
- The loop runs all 6 symbols regardless — a `FAILED` symbol is recorded, not
  fatal.
- After the loop, `retrain-all` prints a per-symbol summary table (symbol →
  outcome → one-line reason).
- Exit code: non-zero if any symbol is `FAILED`; `NO_TRADE` does not cause a
  non-zero exit.

Mechanism: drop `|| exit 1`; capture each symbol's exit code; a symbol exiting
0 is `DEPLOY` or `NO_TRADE`, distinguished by reading its Stage 2f summary
`status`; non-zero is `FAILED`. This is the only place an explicit outcome
record lives. The downstream audit / docs-contract / mkdocs steps run only if
no symbol `FAILED`.

The outcome-classification logic is kept as an extractable, shell-callable
helper so it is unit-testable without running the full pipeline.

### Section 5 — Testing strategy

Per-component tests, following the existing `tests/` layout:

- **WFO writer** — empty predictions still write a schema-correct empty
  parquet; a current empty file overwrites a stale one. Extends
  `tests/test_run_tick_opportunity_monthly_wfo.py`.
- **Reader classification** — a 3-case test for Stage 2f: missing input →
  error; non-empty inputs that do not join → error; present empty input →
  empty output and exit 0. This is the regression test for the 2026-05-16
  stale-file bug.
- **freeze** — a symbol with an empty reduced-core schedule produces a
  well-formed `NO_GO` lock with an empty `state_universe` that passes registry
  validation.
- **promote-live / registry** — a `NO_GO` empty-universe lock is accepted, not
  a validation failure.
- **retrain-all summary** — a unit test of the outcome-classification helper
  (`DEPLOY` / `NO_TRADE` / `FAILED` from exit code plus Stage 2f status).

**Verification gate:** a full local `make retrain-all` completes across all 6
symbols, with EURUSD showing `NO_TRADE`, and the run exits 0.

## Out of scope

- Re-mining or changing the mining logic itself — #173 already did that.
- Research into whether a different signal could restore an edge for symbols
  that come back `NO_TRADE` — that is a separate research effort.
