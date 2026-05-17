# Clean-Slate `rebuild-all` + Fail-Loud Mining

**Date:** 2026-05-17
**Status:** Approved (design)

## Problem

`make retrain-all` runs `onboard_symbol.py --skip-data`, which skips Stage 0
(data acquisition). It assumes the velocity dataset at
`data/analysis/tick_velocity` already exists. When `data/` is empty, mining
reads a non-existent input directory, prints
`dataset_dir does not exist ... returning empty candidates (no-trade condition)`,
and writes header-only candidate CSVs. Stage 2f selection then reports
`NO_TRADE: No candidates available` for every symbol.

This produced two failures:

1. **No clean rebuild path that starts from scratch.** `rebuild-all` exists
   and runs the full Stage 0–5, but it does not clear stale artifacts first,
   so a run can mix fresh and leftover data.
2. **A missing-input failure masquerades as a tuning problem.** Mining treats
   a missing input directory as a graceful "no-trade", so empty data
   propagated silently to `NO_TRADE` summaries and looked like over-tight
   gates.

## Goals

- A clean-slate rebuild is the default behaviour of `rebuild-all`.
- An opt-out flag skips the clean (to resume a partial rebuild).
- Missing or empty input data fails loudly, distinct from a genuine
  no-signal result.

## Non-Goals

- No change to `onboard_symbol.py` stage logic.
- No change to mining/selection gate thresholds.
- No auto-download of raw ticks outside the existing `rebuild-all` Stage 0a.
- No change to `retrain-all`'s fast Stage 2–5 path.

## Design

### 1. New `clean-data` Makefile target

A standalone target that removes everything under `data/` and recreates an
empty `data/` directory. It does **not** touch raw Dukascopy ticks at
`~/Desktop/dukascopy_ticks` (the expensive download, re-fetchable but kept as
a cache).

`data/*` is gitignored, so the wipe loses nothing tracked. Governance locks
live in `configs/research/governance/` (tracked) and are unaffected.

```make
clean-data:
	@echo "Cleaning data/ (raw ticks at $$HOME/Desktop/dukascopy_ticks are kept)"
	rm -rf data
	mkdir -p data
```

### 2. `rebuild-all` cleans by default

`rebuild-all` invokes `clean-data` before the Stage 0–5 loop, unless
`SKIP_CLEAN=1` is passed.

- `MONTHS=` stays **required** — a full rebuild needs an explicit data
  window; a baked-in default would silently go stale.
- The rest of `rebuild-all` is unchanged: per-symbol
  `onboard_symbol.py --months $(MONTHS) --force ...`, then the data
  reliability audit, docs-contract, and mkdocs build.

```make
rebuild-all:
	@test -n "$(MONTHS)" || (echo "error: MONTHS required, e.g. make rebuild-all MONTHS=201801-202602" && exit 1)
	@if [ -z "$(SKIP_CLEAN)" ]; then $(MAKE) clean-data; else echo "SKIP_CLEAN set — keeping existing data/"; fi
	... (existing Stage 0-5 loop unchanged) ...
```

### 3. `retrain-all` unchanged

`retrain-all` remains the fast path: `--skip-data`, Stages 2–5 only, no
clean. Used when inputs are already present and only models need retraining.

### 4. Fail loudly on missing input data

In `scripts/run_tick_opportunity_mining.py`, the branch that currently prints
`dataset_dir does not exist ... returning empty candidates (no-trade
condition)` is changed:

- **Missing input** — `dataset_dir` does not exist, or exists but contains no
  usable input rows for the symbol: raise a hard error
  (`FileNotFoundError` / `RuntimeError`) with a clear message pointing the
  operator at `make rebuild-all`.
- **Genuine no-signal** — input data is present and read successfully, but
  honest mining yields zero candidates: unchanged, still emits an empty
  candidate set / NO_TRADE downstream.

The distinction is: *absent input* is an operator error and must crash;
*present input, no opportunities* is a legitimate research outcome.

## Error Handling

| Condition | Behaviour |
|---|---|
| `rebuild-all` without `MONTHS` | Errors before any work (existing check) |
| `rebuild-all` default | Wipes `data/`, then full Stage 0–5 |
| `rebuild-all SKIP_CLEAN=1` | Keeps `data/`, runs Stage 0–5 over it |
| Mining, input dir missing/empty | Hard error, clear message |
| Mining, input present, 0 candidates | Empty candidates → NO_TRADE (unchanged) |

## Testing

- **pytest** for the mining change: a missing `dataset_dir` raises; a
  `dataset_dir` with no velocity files for the symbol raises; input present
  with rows but yielding zero qualifying candidates still resolves to
  NO_TRADE without crashing.
- **Manual** for the Makefile targets: `make clean-data` empties `data/`;
  `make rebuild-all` without `MONTHS` errors; `SKIP_CLEAN=1` skips the wipe.

## Files

- `Makefile` — add `clean-data`; modify `rebuild-all`.
- `scripts/run_tick_opportunity_mining.py` — missing-input hard error.
- `tests/test_tick_opportunity_mining.py` — mining hard-error / NO_TRADE tests.
