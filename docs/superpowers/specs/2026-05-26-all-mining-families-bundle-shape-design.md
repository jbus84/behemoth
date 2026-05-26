# All Mining Families — Bundle Shape Extension (Sub-Project A)

- Status: Draft
- Date: 2026-05-26
- Parent project: Live-deploy all 11 mining families through governance.
- Position: Sub-project **A** of a planned A→B→C→D→E (+ F→G→H) sequence.

---

## Purpose

The codebase already mines 11 strategy families (`scripts/mining_family.py::FAMILY_REGISTRY`). Governance currently routes only `oco_first_touch_clean` end-to-end. The blocker to live-deploying the other 10 starts at the bundle layer: today every lock is implicitly OCO — one lock per symbol per month, with OCO-shaped filename templates baked into `BUNDLE_LAYOUTS`.

This sub-project changes the bundle layer to be family-aware end-to-end on the producer side, and authors the 11 `BUNDLE_LAYOUTS` rows so subsequent sub-projects (B, C, D, E) can onboard real families without touching the lock contract again.

**Out of scope for A** (deferred to later sub-projects):
- Stage 5/6 logic generalisation — sub-project B
- WFO config restructure — sub-project C
- Actually running any new family end-to-end — sub-project D
- Consumers dropping their OCO family filter — sub-project G
- Runtime predict/account-risk/portfolio handling — sub-projects G, H

After A merges: 11 BUNDLE_LAYOUTS rows exist; on disk, only OCO bundles exist; runtime consumers still hardcoded to OCO. The non-OCO infrastructure is dormant but tested.

---

## Architecture

Bundle granularity changes from **one lock per (symbol, month)** to **one lock per (symbol, family, month)**.

Concretely:

- `BUNDLE_LAYOUTS: dict[str, tuple[BundleArtifactSpec, ...]]` grows from 1 entry (`oco_first_touch_clean`) to 11 — one per family registered in `scripts/mining_family.py::FAMILY_REGISTRY`.
- Every artifact filename template in every layout uses the pattern `{symbol_lower}_{family}_<artifact>.<ext>` for symbol-local artifacts and `models/{symbol_upper}_{family}_model_{month}.<ext>` for model artifacts. OCO templates change to match.
- `lock_filename(symbol: str)` becomes `lock_filename(symbol: str, family: str) -> str`, returning `f"{symbol.lower()}_{family}_live_lock.json"`.
- `iter_locks(bundle_dir, family=None)` keeps its current signature; the existing `*_live_lock.json` glob already picks up family-named locks without code change.
- Producer scripts (`freeze_monthly_bundle.py`, `freeze_oco_live_governance.py`) accept `--family <name>` (default: `oco_first_touch` to preserve current behaviour for un-modified callers).
- `run_monthly_build.py` enumerates families and invokes the freeze once per family. Sub-project A keeps the enumeration as a fixed list containing only `oco_first_touch`. Sub-projects D/E flip on the other families.
- Existing OCO bundle lock JSONs are renamed by a one-shot migration; the artifacts they point at are untouched.

The schema version of the lock content does **not** change — this remains `schema_version: 3`. Only filenames and producer-side layout templates change.

---

## Components and their changes

### `src/behemoth/core/bundle_paths.py`

**`lock_filename` signature change.**

```python
def lock_filename(symbol: str, family: str) -> str:
    return f"{symbol.lower()}_{family}_live_lock.json"
```

Every existing call site (per `git grep lock_filename`) must pass `family`. The change is non-additive — callers that don't know which family they want must be examined and made family-aware (typically by passing the family they were implicitly hardcoded to: `oco_first_touch`).

**`BUNDLE_LAYOUTS` grows to 11 entries.**

Every entry follows the same shape. Example for the OCO row going forward:

```python
"oco_first_touch": (
    BundleArtifactSpec("predictions",          "{symbol_lower}_oco_first_touch_locked_predictions.parquet", True),
    BundleArtifactSpec("allowed_states_csv",   "{symbol_lower}_oco_first_touch_allowed_states.csv",         True),
    BundleArtifactSpec("model_cbm",            "models/{symbol_upper}_oco_first_touch_model_{month}.cbm",   True),
    BundleArtifactSpec("model_threshold_json", "models/{symbol_upper}_oco_first_touch_model_{month}.json",  True),
    BundleArtifactSpec("wfo_config",           "configs/{symbol_lower}_oco_first_touch_wfo.yaml",           False),
    BundleArtifactSpec("reduced_config",       "configs/{symbol_lower}_oco_first_touch_reduced.yaml",       False),
    BundleArtifactSpec("reduced_summary",      "{symbol_lower}_oco_first_touch_reduced_summary.csv",        False),
    BundleArtifactSpec("tick_exact_summary",   "{symbol_lower}_oco_first_touch_tick_exact_summary.csv",     False),
),
```

The same eight-artifact shape is reused for all 11 families. The `{family}` token in templates is the dict key. The 11 family names — copied verbatim from `scripts/mining_family.py::FAMILY_REGISTRY` — are:

```
oco_first_touch
oco_asymmetric
directional
directional_inverse
directional_run
double_touch
pullback
no_touch
dollar_residual
dispersion_rank
lead_lag
```

The implementer authors all 11 rows in this PR, each following the eight-artifact pattern shown above with `{family}` substituted by the row's key.

**The existing `oco_first_touch_clean` row's fate depends on the open-issue resolution:**
- Resolution (a): the row stays and is renamed to `oco_first_touch_clean` formally — no on-disk filename change is needed (existing locks already point at files matching the old templates).
- Resolutions (b) or (c): the row is replaced by the new `oco_first_touch` row (and the old templates with bare `_oco_` filenames don't survive in code). Files already on disk continue to resolve correctly because locks record absolute resolved paths, not patterns.

### `scripts/migrate_lock_schema.py`

A new mode renames existing OCO lock JSONs to the family-namespaced form.

```bash
uv run python scripts/migrate_lock_schema.py \
    configs/research/governance/oco_candidate_builds/2026-04 \
    --rename-to-family-naming
```

Behaviour:
- Scans `<bundle_dir>/*_live_lock.json`.
- For each lock matching the old name `<symbol>_oco_live_lock.json`, reads `bundle.family` and renames to `<symbol>_<bundle.family>_live_lock.json`.
- **Does not** touch any other file in the bundle.
- Idempotent: a lock already at the family-namespaced name is left alone.
- Refuses to operate if the canonical family name issue (below) has not been resolved — the migration script needs to know what to rewrite `bundle.family` to during the rename.

### Producer scripts

**`scripts/freeze_monthly_bundle.py`** and **`scripts/freeze_oco_live_governance.py`** each gain `--family <name>` (default `oco_first_touch`):

```python
parser.add_argument("--family", default="oco_first_touch")
...
layout = bundle_layout_for(args.family)
lock_name = lock_filename(symbol, args.family)
```

Internally, the producer:
1. Looks up `bundle_layout_for(args.family)`.
2. Resolves source artifacts from `data/analysis/tick_opportunity_mining/...` for that family (existing mining outputs already segregate by family).
3. Copies them into the bundle dir using the template filenames.
4. Writes the lock at `lock_filename(symbol, args.family)` with `bundle.family = args.family`.

The producer does **not** make Stage 5/6 work for non-OCO families in this sub-project (that's B). The artifact-source-resolution step in step 2 may raise `FileNotFoundError` for non-OCO families today; that's acceptable — the producer is exercised only with `--family oco_first_touch` until B lands.

### `scripts/run_monthly_build.py`

Wraps the freeze in a loop over a families list. For sub-project A:

```python
FAMILIES_TO_FREEZE = ("oco_first_touch",)  # extended in sub-project D/E
for family in FAMILIES_TO_FREEZE:
    _run_step(
        ["uv", "run", "python", "scripts/freeze_monthly_bundle.py", "--family", family, ...],
        f"step 2/2: freeze_monthly_bundle ({family})",
    )
```

Single-family today, ready to extend.

### `scripts/validate_bundle.py`

No code change. The validator iterates `*_live_lock.json` in a bundle dir and runs `BundlePaths.from_lock` on each — the new family-namespaced lock filenames match the existing glob unmodified.

### Consumers (registry, parity checks, runtime, etc.)

**No code change in sub-project A.** Existing call sites:

```python
iter_locks(p_dir, family="oco_first_touch_clean")
```

…stay as-is during sub-project A. After the migration resolves the canonical family name (open issue below), these strings change once across all consumer sites (in a small follow-on commit within sub-project A, since otherwise the migration leaves the consumers pointing at a no-longer-existing family).

Other families' locks land in the bundle dir but are silently ignored by every consumer that filters via `family=`. They're picked up by `validate_bundle` (which intentionally doesn't filter) and by any future consumer that asks for them.

---

## Data flow

```
mining outputs (already exist for all 11 families)
    └── data/analysis/tick_opportunity_mining/...
        ├── <family>/<symbol>_<family>_*  (per-family subdirs, populated by mining today)
        └── ...

run_monthly_build.py
    └── for family in FAMILIES_TO_FREEZE (= ["oco_first_touch"] in A):
        └── freeze_monthly_bundle.py --family <family> --symbols ... --out-dir <bundle_dir>
            ├── reads mining outputs for (symbol, family)
            ├── copies into bundle_dir using bundle_layout_for(family) templates
            └── writes <symbol>_<family>_live_lock.json (schema_version 3, bundle.family = family)

validate_bundle.py <bundle_dir>
    └── iter_locks(<bundle_dir>)  # no family filter
        └── BundlePaths.from_lock(each) → verify sha + paths

consumers (stage12, monthly_recert, registries, parity)
    └── iter_locks(<bundle_dir>, family="oco_first_touch")
        └── only OCO locks returned; other-family locks silently skipped
```

---

## Migration

### Step 1: Resolve open issue (below)
Cannot proceed without an answer to "what is the canonical family for existing OCO locks?"

### Step 2: Run rename migration on each existing bundle
```bash
for month in 2026-02 2026-03 2026-04; do
    uv run python scripts/migrate_lock_schema.py \
        "configs/research/governance/oco_candidate_builds/${month}" \
        --rename-to-family-naming
done
```

Each `<symbol>_oco_live_lock.json` renames to `<symbol>_<canonical_family>_live_lock.json` (e.g. `eurusd_oco_first_touch_live_lock.json`). Artifact filenames inside the bundle dir do not change; lock-recorded paths still resolve.

### Step 3: Update consumer filter strings
Single grep + replace across `src/` and `scripts/` to change every `iter_locks(..., family="oco_first_touch_clean")` to `family="<canonical_family>"`. Targeted commit, no logic change.

### Step 4: Validate
```bash
for month in 2026-02 2026-03 2026-04; do
    uv run python scripts/validate_bundle.py "configs/research/governance/oco_candidate_builds/${month}"
done
```
Expected: every bundle prints OK. Failure here means the migration left bundles in an inconsistent state — investigate before merging.

### Step 5: Commit migrated locks
The renamed JSON files are checked into git alongside the code change.

---

## Open issue — canonical family name for existing OCO locks

Current locks declare `bundle.family: "oco_first_touch_clean"`. But `src/behemoth/core/registry.py::CandidateSpec.from_row` rejects any state_id containing `"first_touch_clean"` as look-ahead-biased:

```python
if "first_touch_clean" in state_id:
    raise ValueError(
        f"refusing look-ahead-biased candidate '{state_id}': the "
        "first_touch_clean family conditions its win rate on ~both "
        "(future information) and must not be deployed. Re-mine and "
        "re-freeze governance on the first_touch family."
    )
```

This is internally contradictory: every lock declares the family that the rejecter blocks. If the rejection actually fired in production, no candidate would have ever traded.

**Required before sub-project A implementation begins:** answer one of the following:

- **(a)** The locks are correctly `oco_first_touch_clean`, the rejector is operative, and the system is in a degraded no-trade state for these months. Migration renames to `<symbol>_oco_first_touch_clean_live_lock.json` and onboarding `oco_first_touch` (the deployable family) requires a re-freeze.
- **(b)** The locks are mis-labelled — their actual canonical family is `oco_first_touch`. The migration rewrites `bundle.family` from `oco_first_touch_clean` to `oco_first_touch` in addition to renaming the file. The state_ids in `state_universe.rows` need to be checked to confirm they don't contain `"first_touch_clean"` strings.
- **(c)** The state_ids use a third naming convention not captured by the family field, and the `from_row` filter has been an unreachable guard. Migration treats existing locks as `oco_first_touch` (the canonical family of `FAMILY_REGISTRY`), the registry's filter remains an inactive guardrail.

**Pre-implementation task:** inspect `state_universe.rows[].state_id` values in `configs/research/governance/oco_candidate_builds/2026-04/<symbol>_oco_live_lock.json` for all symbols. The answer to which resolution applies follows from what's actually in there.

---

## Testing

1. **Round-trip a synthetic non-OCO family through BundlePaths.** Reuse the pattern from `tests/test_bundle_paths.py::test_non_oco_family_round_trip`. Register `"test_synthetic"` in `BUNDLE_LAYOUTS` via `monkeypatch.setitem`, write a v3 lock with that family, call `BundlePaths.from_lock`, assert it resolves all artifacts.

2. **Parametrised template-render test.** For every family in `BUNDLE_LAYOUTS`, render each `BundleArtifactSpec.target_relpath_template` with sample `{symbol_lower}`, `{symbol_upper}`, `{family}`, `{month}` values. Assert:
   - No `{` or `}` characters remain (all tokens substituted).
   - The path is bundle-relative (no `/` prefix, no `..`).
   - Distinct families produce distinct filenames for the same symbol/month.

3. **`lock_filename` signature change.** Add a test that calls `lock_filename("EURUSD", "directional")` and asserts `"eurusd_directional_live_lock.json"`. Add a separate test that confirms passing only one argument raises `TypeError` — guards against silent regression.

4. **Migration idempotency.** Build a fixture bundle dir with an old-style `eurusd_oco_live_lock.json`. Run the migration. Assert the new filename exists, the old does not, the lock JSON content matches the expected canonical-family rewrite. Run the migration again on the post-migration bundle dir. Assert no change.

5. **Freeze producer with `--family`.** Build a fixture mining-output tree with synthetic per-family artifacts. Invoke `freeze_monthly_bundle.py --family <family>` for `oco_first_touch` and for a registered synthetic family. Assert:
   - The produced lock filename matches `{symbol}_{family}_live_lock.json`.
   - The lock body has `bundle.family == args.family`.
   - All `artifacts.*.path` values are bundle-relative and resolve to files in the bundle dir.

6. **Consumer-filter-string update.** Grep test: `grep -rn 'family="oco_first_touch_clean"' src/ scripts/` returns no results after sub-project A's commit that updates filter strings. Codifies the constraint.

7. **`validate_bundle` over a multi-family fixture.** Build a bundle dir containing two valid locks (one OCO, one synthetic non-OCO via fixture). Run `validate_bundle` — expect OK. Corrupt one; expect failure.

---

## Risks

- **Family-name resolution drifts.** If the open issue is answered as (b) — bundles mis-labelled — every lock's `bundle.family` gets rewritten during migration. That's a content change that propagates downstream into anything that recorded the family elsewhere. Search for downstream caches/manifests/test fixtures that hold the family name.
- **Producer's source-resolution step breaks for non-OCO.** `freeze_monthly_bundle.py` reads mining outputs from a path conventionally derived from the family. If the convention drift between mining and freeze isn't visible until sub-project D, A's producer test must use a fixture that asserts the conventional path it expects — not just success on OCO.
- **Consumers we forgot.** A grep for `_oco_live_lock` or hardcoded `oco_first_touch_clean` strings across the codebase is the audit. Anything missed leaks legacy expectations.
- **Lock filename collisions.** With 11 families × 6 symbols, the month dir has ~66 lock files instead of 6. Confirm `validate_bundle.py` doesn't degrade noticeably (it iterates locks and verifies shas — should be linear in the number of locks, single-digit seconds even at 66).

---

## Acceptance criteria

A is done when:

- `BUNDLE_LAYOUTS` has exactly 11 entries matching `FAMILY_REGISTRY`'s keys (case-sensitive equality).
- All template renders parametrised over `{symbol_lower}`, `{symbol_upper}`, `{family}`, `{month}` pass the validation test.
- `lock_filename(symbol, family)` is the only signature; no zero-arg or one-arg call sites remain.
- Existing 2026-02/03/04 bundles validate cleanly with the renamed lock filenames.
- `freeze_monthly_bundle.py --family oco_first_touch` produces a bundle that round-trips through `validate_bundle` and matches the bytes of the post-migration existing OCO bundle (modulo non-deterministic timestamps).
- Round-trip test for at least one non-OCO family passes via fixture-registered synthetic family.
- Full pytest suite green; ruff and ty clean.
- No `oco_first_touch_clean` string remaining in `src/` or `scripts/` (legacy/migrate exempt).
