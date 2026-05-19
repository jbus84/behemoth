# Candidate Fill Logging — Design

**Status:** Approved (design)
**Date:** 2026-05-19

## Goal

The tick opportunity mining pipeline currently persists only *aggregate per-candidate*
rows (`{symbol}_candidate_summary.csv` and the per-library CSVs). Each row collapses
a whole candidate's fills into ~20 summary statistics. This is enough to *rank*
candidates but not to understand *why* a strategy behaves as it does — there are no
per-trade records, so equity curves, drawdown, win/loss clustering, regime-conditional
performance, and cross-family overlap are all invisible.

This feature adds a per-fill log: one row per individual fill, for every positive-EV
candidate, capturing the fill outcome and a snapshot of the entry-time features.

## Scope

- **Which candidates:** `selection_pass` candidates plus *near-misses*.
  near_miss := `mean_train > 0 and not selection_pass` (profitable in-sample but
  short of the activity threshold). Negative-EV candidates log nothing.
- **Which fills:** both train and test fills, tagged with a `split` column.
- **Activation:** always-on. Every mining run writes the per-fill log.

## Output Artifact

A new parquet file per symbol:

```
data/analysis/tick_opportunity_mining/candidate_fills/{symbol}_candidate_fills.parquet
```

Written at the end of `mine()` alongside the existing `{symbol}_candidate_summary.csv`.
One row per fill. Parquet is used for columnar compression and fast analytical slicing.

A `candidate_id` column joins each fill back to its summary row. The same
`candidate_id` column is added to the existing summary CSVs so the two artifacts are
linkable.

## Per-Fill Schema

Each row carries three groups of columns.

**Identity**

| Column | Type | Notes |
|---|---|---|
| `candidate_id` | str | Deterministic short hash — see below |
| `symbol` | str | |
| `family` | str | Mining family name |
| `library_type` | str | `separate`/`directional`/`oco`/`double_touch`/`pullback`/`no_touch` |
| `bar_ticks` | int | |
| `horizon` | int | |
| `regime` | str | Regime name |
| `split` | str | `train` or `test` |

**Fill**

| Column | Type | Notes |
|---|---|---|
| `entry_index` | int | Row index into the split's prepared frame |
| `entry_ts` | datetime (UTC) | `close_ts` at `entry_index` |
| `gross_pips` | float | Per-fill gross from `family.measure_gross` |

**Entry-time feature snapshot** (values read at `entry_index`)

| Column | Type | Notes |
|---|---|---|
| `tick_burst_score` | float | NaN if column absent on the frame |
| `directional_persistence_8` | float | NaN if column absent |
| `vol_cluster_score` | float | NaN if column absent |
| `session_marker` | str | empty if column absent |

**Denormalized flags** (for easy filtering without joining the summary)

| Column | Type | Notes |
|---|---|---|
| `selection_pass` | bool | |
| `near_miss` | bool | |

### `candidate_id`

A deterministic identifier: the first 12 hex characters of the sha1 of the tuple
`(symbol, library_type, family, bar_ticks, horizon, regime, sorted param items)`.
Stable across runs, so a candidate's fills can be diffed between retrains.

## Emission Gate

`selection_pass` is computed per candidate (`run_tick_opportunity_mining.py:1026-1036`):
positive in-sample EV **and** clearing an activity bar
(`train_annual >= min_annual_fills`, or `train_n >= 500` for OCO).

`near_miss := mean_train > 0 and not selection_pass`.

The emission gate is `selection_pass or near_miss`. The already-computed `entries`/
`gross` (test) and `train_entries`/`train_gross` (train) arrays are held until the
gate decision, then expanded into per-fill rows. No fills are recomputed.

## Code Structure

### New module: `scripts/candidate_fills.py`

A focused, independently testable module. Internal helpers operate on already-prepared
DataFrames and arrays.

- `candidate_id(symbol, library_type, family, bar_ticks, horizon, regime, params) -> str`
  — the deterministic hash.
- `expand_fills(frame, entries, gross, *, split, identity) -> list[dict]`
  — produce one dict per fill: identity columns, fill columns, and the entry-time
  feature snapshot pulled at each `entry_index`. Missing feature columns yield NaN
  (or empty string for `session_marker`).
- `write_candidate_fills(rows, out_dir, symbol) -> Path`
  — assemble the rows into a DataFrame and write the parquet.

### Changes to `scripts/run_tick_opportunity_mining.py`

- Add a `per_family_fills` accumulator alongside the existing `per_family_rows`.
- At the emission gate, call `expand_fills` for the train split and the test split,
  and extend the accumulator.
- Add `candidate_id` to each summary row.
- In `mine()`, call `write_candidate_fills` to write the parquet under the new
  `candidate_fills/` subdirectory.

No existing summary columns change except for the added `candidate_id`.

## Testing

**Unit — `scripts/candidate_fills.py`**

- `candidate_id` is deterministic for identical inputs and distinct for differing
  params.
- `expand_fills` produces the correct row count, correct `gross_pips` values, a
  correct entry-time feature snapshot, and the correct `split` tag.
- Missing feature columns degrade to NaN / empty string rather than raising.

**Unit — emission gate**

- A `selection_pass` candidate emits fills.
- A near-miss candidate emits fills.
- A negative-EV candidate emits no fills.

**Integration**

- Run `mine()` on synthetic velocity data; assert the per-fill parquet exists,
  has the expected schema, and joins cleanly to the summary CSV on `candidate_id`.

## Out of Scope

- Equity-curve / drawdown computation — that is downstream analysis built *on* this
  log, not part of logging itself.
- Logging fills for negative-EV candidates.
- An opt-in flag — logging is always-on.
