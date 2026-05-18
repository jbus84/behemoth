# Mining Family Framework + Random-Entry Baseline

**Date:** 2026-05-18
**Status:** Approved (design)
**Roadmap:** Sub-project 0 of `2026-05-18-microstructure-research-roadmap.md`

## Problem

`scripts/run_tick_opportunity_mining.py` (1,115 lines) hardcodes two
candidate families. `run()` branches on `library_type` and calls
`_directional_candidates` / `_oco_candidates` directly. The roadmap requires
five new research families; adding each by editing the core mining loop does
not scale and offers no shared way to judge whether a family carries signal.

This sub-project delivers the shared foundation: a registration seam for
candidate families and a random-entry baseline that scores any family's
candidates against random timing on the same bars.

## Goals

- A `MiningFamily` Protocol so a new family supplies its own entry trigger,
  outcome measurement, parameter grid, and candidate metadata without
  editing the core mining loop.
- The existing `oco_first_touch` and `directional` families ported onto the
  seam — one mechanism, no dual code paths.
- A random-entry baseline: for any candidate, a count-matched whole-frame
  control distribution of gross EV, scored as a z-value and percentile.

## Non-Goals

- No new research families (those are roadmap sub-projects 1-5).
- The baseline columns are diagnostic only — they do not change
  `selection_pass` or `quality_tier` in this sub-project. Each research
  family's own spec decides the z-threshold that gates it.
- No change to mining gate thresholds, the ml-dataset, or the WFO beyond the
  candidate-schema column additions.

## Design

### 1. The `MiningFamily` Protocol & registry

A new module (`scripts/mining_family.py`, or a `scripts/mining_families/`
package — the plan picks based on resulting file sizes) defines:

```python
class MiningFamily(Protocol):
    name: str
    def param_grid(self, cfg: dict) -> list[dict]: ...
    def entry_indices(self, frame: pd.DataFrame, regime_mask: np.ndarray,
                      params: dict) -> np.ndarray: ...
    def measure_gross(self, frame: pd.DataFrame, entries: np.ndarray,
                      params: dict) -> np.ndarray: ...
    def candidate_metadata(self, regime_name: str, params: dict) -> dict: ...

FAMILY_REGISTRY: dict[str, MiningFamily] = {
    "oco_first_touch": OcoFirstTouchFamily(),
    "directional": DirectionalFamily(),
}
```

- `param_grid` — family-specific parameter axes (OCO: barrier widths;
  directional: a single empty-param entry).
- `entry_indices` — look-ahead-free entry bar indices for one regime mask +
  param combo.
- `measure_gross` — gross pips realised per entry. **Must accept any entry
  index array**, because the same method scores both the family's real
  entries and the random-baseline's count-matched draws.
- `candidate_metadata` — `family`, `state_id`, `regime_desc`, and
  `ml_ready_target_type` for the candidate row.

The decoupling of `measure_gross` from `entry_indices` is the key invariant:
it makes the random-entry baseline an apples-to-apples comparison.

### 2. Random-entry baseline

A new module `scripts/mining_random_baseline.py`:

```python
def random_entry_baseline(
    family: MiningFamily, frame: pd.DataFrame, params: dict,
    n_entries: int, n_draws: int, rng: np.random.Generator,
) -> dict: ...
```

For a candidate with `N` real entries, draw `N` random entry indices from the
entire valid bar set, run the family's own `measure_gross` on them, record
that draw's gross EV. Repeat `n_draws` times (default **200**) to build a
control distribution of gross EV under random timing.

Score the candidate against the control:

```
random_baseline_z = (candidate_gross_ev - control_mean) / control_std
random_baseline_p = fraction of control draws with gross EV >= candidate's
```

Three new columns land on every candidate row: `random_baseline_z`,
`random_baseline_p`, `random_baseline_control_mean`. They are diagnostic in
this sub-project — they do not affect `selection_pass` or `quality_tier`.

A `--baseline-seed` config key seeds the `rng` so re-runs reproduce identical
control distributions (required for governance-locked mining).

### 3. Refactor of existing families

`_oco_candidates` and `_directional_candidates` are removed; their logic
moves into `OcoFirstTouchFamily` and `DirectionalFamily` implementing the
Protocol. Shared helpers — `_oco_precompute_candidates`, `_regime_masks`,
`_quantiles`, `_directional_family_states` — remain module-level functions
that families call.

`run()`'s `library_type` branch becomes a loop over `cfg["families"]`.
`library_type` is kept as a thin compatibility alias so existing configs and
the ml-dataset / WFO callers do not break:

- `oco` → `["oco_first_touch"]`
- `directional` → `["directional"]`
- `separate` → `["oco_first_touch", "directional"]`

### 4. Data flow

```
velocity parquet
  → run(): for family in resolved families:
        param_grid × regime × {train, test}
          → entry_indices → measure_gross → candidate row
          → random_entry_baseline(...) → 3 baseline columns
  → {symbol}_{family}_candidates.csv  (+ candidate_summary)
```

The candidate CSV schema gains `random_baseline_z`, `random_baseline_p`,
`random_baseline_control_mean`. `MINING_CANDIDATE_SCHEMA_VERSION` is bumped;
the ml-dataset's `REQUIRED_CANDIDATE_COLUMNS` and the OCO docs-contract test
are updated to match.

## Error Handling

- Unknown family name in `cfg["families"]` → raise `ValueError` listing the
  registered family names.
- `random_entry_baseline`: if `N` exceeds the valid bar set, or
  `control_std` is zero (degenerate), the three baseline columns are written
  as `NaN` with a logged warning — a measurement gap, not a pipeline failure.
- The fail-loud guards from PR #184 (missing dataset dir, no velocity files
  for the symbol) are preserved unchanged.

## Testing

- **Protocol conformance:** every entry in `FAMILY_REGISTRY` implements all
  four methods with the expected signatures.
- **Refactor parity:** a regression test asserting `OcoFirstTouchFamily` and
  `DirectionalFamily` produce candidate rows identical to a frozen
  pre-refactor fixture (same synthetic velocity frame → same gross, counts,
  metadata) — proves the port is behaviour-preserving.
- **Random baseline:** with a fixed seed the control distribution is
  deterministic; a candidate whose entries are deliberately the best-N bars
  scores `z > 0`; a random-subset candidate scores `z ≈ 0`; degenerate cases
  (`N` > frame size, zero std) return `NaN` rather than crashing.
- **Regression:** the existing `tests/test_tick_opportunity_mining.py` suite
  passes after the `library_type` alias shim.

## File Map

- Create: `scripts/mining_family.py` (or `scripts/mining_families/` package)
  — `MiningFamily` Protocol, `OcoFirstTouchFamily`, `DirectionalFamily`,
  `FAMILY_REGISTRY`.
- Create: `scripts/mining_random_baseline.py` — `random_entry_baseline`.
- Modify: `scripts/run_tick_opportunity_mining.py` — remove
  `_oco_candidates` / `_directional_candidates`; rewrite `run()` as a
  registry loop; add baseline columns; bump schema version; add the
  `library_type` alias.
- Modify: `scripts/build_tick_opportunity_ml_dataset.py` — update
  `REQUIRED_CANDIDATE_COLUMNS` and `EXPECTED_CANDIDATE_SCHEMA_VERSION`.
- Test: `tests/test_tick_opportunity_mining.py` (extend),
  `tests/test_mining_family.py` (new),
  `tests/test_mining_random_baseline.py` (new).
