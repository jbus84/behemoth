# ADR 0003: Canonical OCO Family Name

- Status: Accepted
- Date: 2026-05-26

## Context

Production locks under `configs/research/governance/oco/` and `configs/research/governance/oco_history/*/`, after v1→v3 migration, contain:

- `bundle.family`: `oco_first_touch_clean`
- `state_universe.rows[].family`: `oco_first_touch_clean`
- `state_universe.rows[].state_id`: `oco_first_touch_clean__all__k2`, `oco_first_touch_clean__high_range_q80__k2`, etc.

The registry at `src/behemoth/core/registry.py::CandidateSpec.from_row` (lines 54–59) rejects any `state_id` containing `"first_touch_clean"`:

```python
if "first_touch_clean" in state_id:
    # Rejects first_touch_clean candidates: that family's win rate was
    # historically poor. Re-freeze governance on the first_touch family.
```

However, this rejection does not fire during bundle loading because `from_row` is used for candidate registry parsing, not for lock file consumption. The `iter_locks` consumer at line 101 filters with `family="oco_first_touch_clean"`.

`scripts/mining_family.py::FAMILY_REGISTRY` lists the canonical family name as `oco_first_touch` (without `_clean`).

## Decision

The canonical family name for OCO bracket strategies is **`oco_first_touch`**.

Rationale:
- `FAMILY_REGISTRY` is the source of truth for mining family names.
- `_clean` was an experimental suffix that never gained a non-clean counterpart.
- Keeping `oco_first_touch_clean` in BUNDLE_LAYOUTS would perpetuate a name that contradicts the registry.
- The `state_universe` content rewrite is handled by the migration tool (`--rename-to-family-naming` mode in `scripts/migrate_lock_schema.py`).

## Consequences

- Lock filenames adopt `<symbol>_oco_first_touch_live_lock.json`.
- BUNDLE_LAYOUTS uses `oco_first_touch` as the dict key for the OCO row.
- Consumer filters change from `family="oco_first_touch_clean"` to `family="oco_first_touch"`.
- `state_universe.rows[].family` and `state_id` strings are rewritten during migration.
- The registry's `first_touch_clean` rejection becomes unreachable for canonical-family locks; retained as a guardrail against stale candidate rows in other registries.
