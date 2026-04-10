# Seed File Governance Fingerprint Check

## Problem

`scripts/seed_rolling_threshold.py` caches per-symbol threshold seed files in
`data/runtime/seed/`. The freshness check (`_is_fresh`) only verifies that the
seed covers data up to yesterday — it does not verify that the seed was generated
with the current governance candidates.

When a new governance bundle is promoted (e.g. `2026-03`), the old seed files
remain "fresh" by the recency check and are never regenerated. The API then
looks up rolling thresholds against candidate UIDs that don't exist in the stale
seeds, falls back to `threshold=2.0` (`ROLLING_HISTORY_GAP`) for every new UID,
and symbols trade with wrong thresholds or not at all.

## Fix

Embed the governance candidate UIDs as parquet schema metadata at write time.
At freshness-check time, compare the stored UID set against the current
governance. Any mismatch forces regeneration.

## Changes

### `_is_fresh(seed_file, expected_candidates=None)`

New signature:

```python
def _is_fresh(seed_file: Path, expected_candidates: list[str] | None = None) -> bool
```

After the existing recency check passes, if `expected_candidates` is provided:

1. Read only the parquet footer via `pyarrow.parquet.read_schema(seed_file).metadata`
   (no row data loaded).
2. Extract `b"governance_candidates"`, JSON-decode to a list.
3. Compare `set(stored) == set(expected_candidates)`.
4. Return `False` on mismatch, missing key, or any exception.

### `_seed_symbol` — write metadata

After building `out_df`, write via pyarrow instead of pandas so schema metadata
can be attached:

```python
canonical_uids = [
    f"oco|{symbol}|{cand.bar_ticks}|h{cand.horizon}|{cand.candidate_uid}"
    for cand in candidates
]
table = pa.Table.from_pandas(out_df, preserve_index=False)
existing_meta = table.schema.metadata or {}
new_meta = {b"governance_candidates": json.dumps(sorted(set(canonical_uids))).encode()}
table = table.replace_schema_metadata({**existing_meta, **new_meta})
pq.write_table(table, out_path)
```

`pyarrow` is already a transitive dependency via pandas — no new package required.

### `main` — pass expected candidates

Before calling `_is_fresh`, resolve the current governance UIDs for the symbol:

```python
candidates = registry.get_candidates(sym)
expected_uids = [
    f"oco|{sym}|{c.bar_ticks}|h{c.horizon}|{c.candidate_uid}"
    for c in candidates
] or None
if _is_fresh(seed_file, expected_candidates=expected_uids):
    print(f"  {sym}: seed file is fresh — skipping", flush=True)
    continue
```

Passing `None` when a symbol has no candidates leaves `_is_fresh` behaviour
unchanged for that case.

## Immediate One-Time Action

Delete existing stale seed files before the next session restart:

```bash
rm data/runtime/seed/*.parquet
```

This forces regeneration on next run with the correct 2026-03 governance UIDs.

## Tests

Two new unit tests in `tests/test_threshold_seeding.py`:

- **`test_is_fresh_returns_false_on_governance_mismatch`** — write a parquet
  with `governance_candidates = ["oco|GBPUSD|100|h6|old__k2"]` in metadata and a
  recent `close_ts`; assert `_is_fresh(path, ["oco|GBPUSD|100|h6|new__k2"])` is
  `False`.

- **`test_is_fresh_returns_true_on_governance_match`** — same setup, pass the
  matching UID; assert `True`.

## Error Handling

- Missing metadata key → `False` (regenerate). Covers seeds written before this
  change.
- Any exception during metadata read → `False` with a warning print (same
  pattern as the existing recency-check exception handler).
- `expected_candidates=None` → fingerprint check skipped entirely.
