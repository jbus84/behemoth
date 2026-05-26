# All Mining Families — Bundle Shape Extension Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make governance bundles family-aware on the producer/path side so the other 10 of 11 mining families have a place to live, without onboarding any new family end-to-end (that's sub-projects B/C/D/E).

**Architecture:** Lock granularity becomes (symbol, family, month). `lock_filename(symbol, family)` is the only signature. `BUNDLE_LAYOUTS` grows from 1 entry to 11, each with `{symbol}_{family}_<artifact>` filename templates. Existing OCO lock JSONs are renamed by a one-shot migration without touching the artifacts they point at. Producers gain `--family` (default `oco_first_touch` to preserve current behaviour). Consumers keep their OCO filter — sub-project A makes the infrastructure available, not active.

**Tech Stack:** Python 3.12, `uv`, `pytest`, `ruff`, `ty`. No new dependencies. References ADRs 0001 and 0002.

---

## Source spec

`docs/superpowers/specs/2026-05-26-all-mining-families-bundle-shape-design.md`

Read this first if any task instruction seems ambiguous — the spec has the rationale and constraints.

---

## File Structure

**New files:**
- *None.* All changes are to existing files.

**Modified files:**
- `src/behemoth/core/bundle_paths.py` — `lock_filename` signature; `BUNDLE_LAYOUTS` becomes 11 entries.
- `scripts/migrate_lock_schema.py` — new mode `--rename-to-family-naming`.
- `scripts/freeze_monthly_bundle.py` — `--family` arg.
- `scripts/freeze_oco_live_governance.py` — `--family` arg.
- `scripts/run_monthly_build.py` — wraps freeze in single-family loop.
- Caller sites (`src/`, `scripts/`) that call `lock_filename(symbol)` with one arg — updated to pass family.
- Consumer sites that pass `family="oco_first_touch_clean"` to `iter_locks` — updated to the canonical name decided in Task 1.
- `tests/test_bundle_paths.py` — new parametrised template tests; signature-change tests.
- `tests/test_migrate_lock_schema.py` — new mode tests.
- Existing on-disk lock JSON files (in `configs/research/governance/oco/`, `oco_history/*/`, `oco_candidate_builds/*/`) — renamed to family-namespaced filenames.

---

## Task 1: Resolve canonical family name (investigation only)

**Files:**
- Read-only inspection.

This task produces a documented decision; no code changes. Subsequent tasks reference its outcome.

- [ ] **Step 1: Inspect the production live-OCO locks**

Run from the worktree root:

```bash
uv run python -c "
import json
from pathlib import Path

for lock in sorted(Path('configs/research/governance/oco').glob('*_live_lock.json')):
    d = json.loads(lock.read_text())
    sym = d.get('symbol')
    schema = d.get('schema_version')
    bf = (d.get('bundle') or {}).get('family')
    rows = (d.get('state_universe') or {}).get('rows', [])
    fams = sorted({r.get('family') for r in rows})
    sids = [r.get('state_id') for r in rows[:2]]
    print(f'{sym}  schema={schema}  bundle.family={bf}  row.families={fams}  sample_state_ids={sids}')
"
```

Expected output: one line per symbol. Record what `schema`, `bundle.family`, and `row.families` are.

- [ ] **Step 2: Same inspection on a historical month bundle**

```bash
uv run python -c "
import json
from pathlib import Path

month_dir = Path('configs/research/governance/oco_history/2026-04')
if not month_dir.exists():
    month_dir = sorted(Path('configs/research/governance/oco_history').glob('*'))[-1]
for lock in sorted(month_dir.glob('*_live_lock.json')):
    d = json.loads(lock.read_text())
    sym = d.get('symbol')
    schema = d.get('schema_version')
    bf = (d.get('bundle') or {}).get('family')
    rows = (d.get('state_universe') or {}).get('rows', [])
    fams = sorted({r.get('family') for r in rows})
    sids = [r.get('state_id') for r in rows[:2]]
    print(f'{month_dir.name}/{sym}  schema={schema}  bundle.family={bf}  row.families={fams}  sample_state_ids={sids}')
"
```

- [ ] **Step 3: Inspect `oco_candidate_builds/*/`**

```bash
ls configs/research/governance/oco_candidate_builds/ 2>&1
for d in configs/research/governance/oco_candidate_builds/*/; do
    echo "--- $d ---"
    ls "$d" 2>&1 | head -5
done
```

Note whether each month dir is empty (re-mining required) or populated (locks present).

- [ ] **Step 4: Check the registry filter behaviour**

`src/behemoth/core/registry.py::CandidateSpec.from_row` rejects state_ids containing `"first_touch_clean"`. Run:

```bash
grep -n "first_touch_clean\|first_touch\b" src/behemoth/core/registry.py | head -10
```

Confirm the rejection is still in place. If the production locks' `state_id` values from Step 1 contain `"first_touch_clean"`, the rejection would fire during runtime registry loading.

- [ ] **Step 5: Decide and document the canonical family name**

Pick one of:

- **(a) `oco_first_touch_clean`** — keep the existing family name as-is. The migration renames lock JSONs to `<symbol>_oco_first_touch_clean_live_lock.json` without rewriting any `bundle.family` field. Implies the registry rejection in `from_row` is intentionally degrading the system and a separate plan will address it.
- **(b) `oco_first_touch`** — the locks are mis-labelled; migration renames AND rewrites `bundle.family` from `oco_first_touch_clean` to `oco_first_touch`, AND rewrites `state_universe.rows[].family` and `state_universe.rows[].state_id` to drop the `_clean` suffix.
- **(c) Mixed / something else** — Step 1's output reveals state that doesn't fit (a) or (b). Stop the plan and re-spec.

Write the decision into a file at `docs/adr/0003-canonical-oco-family-name.md`:

```markdown
# ADR 0003: Canonical OCO Family Name

- Status: Accepted
- Date: <today>

## Context

[Paste the actual output of Steps 1–4 from Task 1.]

## Decision

The canonical family name for OCO bracket strategies is `<chosen>`.

Rationale: [brief — why this name, given the inspection results].

## Consequences

- Lock filenames adopt `<symbol>_<chosen>_live_lock.json`.
- BUNDLE_LAYOUTS uses `<chosen>` as the dict key for the OCO row.
- The `family="oco_first_touch_clean"` filter in consumers becomes `family="<chosen>"`.
- [If (b): `state_universe.rows[].family` and `state_id` strings rewritten during migration.]
- [If (b): the registry's `first_touch_clean` rejection becomes unreachable for canonical-family locks; document why it's retained as a guardrail or remove it.]
```

- [ ] **Step 6: Commit**

```bash
git add docs/adr/0003-canonical-oco-family-name.md
git commit -m "docs(adr): 0003 canonical OCO family name decision"
```

For the rest of this plan, this committed value is referenced as `<CANONICAL_OCO_FAMILY>`. **Every subsequent task that mentions `<CANONICAL_OCO_FAMILY>` substitutes the chosen value verbatim.** Implementer note: do a global find-and-replace through the remaining tasks before executing them.

---

## Task 2: `lock_filename` signature change — failing test

**Files:**
- Test: `tests/test_bundle_paths.py`

- [ ] **Step 1: Add a failing test**

Append to `tests/test_bundle_paths.py`:

```python
def test_lock_filename_requires_family() -> None:
    """lock_filename takes (symbol, family); passing one arg is a TypeError."""
    from src.behemoth.core.bundle_paths import lock_filename

    assert lock_filename("EURUSD", "directional") == "eurusd_directional_live_lock.json"
    assert lock_filename("eurusd", "<CANONICAL_OCO_FAMILY>") == "eurusd_<CANONICAL_OCO_FAMILY>_live_lock.json"

    with pytest.raises(TypeError):
        lock_filename("EURUSD")  # type: ignore[call-arg]
```

Substitute `<CANONICAL_OCO_FAMILY>` with the value from Task 1 before saving.

- [ ] **Step 2: Run the test, verify it fails**

```bash
uv run pytest tests/test_bundle_paths.py::test_lock_filename_requires_family -v
```

Expected: FAIL — either the assertion fails (current `lock_filename` takes only symbol) or the test imports succeed but the function doesn't accept two args.

---

## Task 3: `lock_filename` signature change — implementation

**Files:**
- Modify: `src/behemoth/core/bundle_paths.py`

- [ ] **Step 1: Update the function**

In `src/behemoth/core/bundle_paths.py`, find the existing `lock_filename` function. Replace its definition with:

```python
def lock_filename(symbol: str, family: str) -> str:
    """Canonical lock filename for a (symbol, family) pair.

    Every governance lock lives at `<bundle_dir>/<lock_filename(symbol, family)>`.
    Adding a new mining family means registering it in BUNDLE_LAYOUTS and using
    its key as the `family` argument here.
    """
    return f"{symbol.lower()}_{family}_live_lock.json"
```

- [ ] **Step 2: Run the test, verify it passes**

```bash
uv run pytest tests/test_bundle_paths.py::test_lock_filename_requires_family -v
```

Expected: PASS.

- [ ] **Step 3: Lint**

```bash
uv run ruff check src/behemoth/core/bundle_paths.py tests/test_bundle_paths.py
```

Expected: clean.

- [ ] **Step 4: Commit**

```bash
git add src/behemoth/core/bundle_paths.py tests/test_bundle_paths.py
git commit -m "feat(governance): lock_filename takes (symbol, family)"
```

---

## Task 4: Update all `lock_filename` call sites

**Files:**
- Modify: every caller of `lock_filename`.

- [ ] **Step 1: Inventory all callers**

```bash
grep -rn "lock_filename(" src/ scripts/ tests/ 2>/dev/null | grep -v __pycache__ | grep -v "def lock_filename"
```

Expected: a list of ~10 call sites (production caller sites enumerated in `docs/superpowers/specs/2026-05-26-all-mining-families-bundle-shape-design.md`).

- [ ] **Step 2: Update each call site to pass family**

Every call site currently calls `lock_filename(symbol)`. Update each to `lock_filename(symbol, "<CANONICAL_OCO_FAMILY>")`. These are all sites that today implicitly handle OCO bundles only — pinning them to the canonical OCO family is preserving current behaviour.

Read each file before editing. For each, change exactly the one line that calls `lock_filename`.

After all edits:

```bash
grep -rn "lock_filename([^,]*)" src/ scripts/ tests/ 2>/dev/null | grep -v __pycache__ | grep -v "def lock_filename"
```

Expected: no matches (no zero-arg or one-arg call remains).

- [ ] **Step 3: Run the full suite**

```bash
uv run pytest -q
```

Expected: PASS. If anything regresses, the most likely cause is a call site you missed or a test fixture that doesn't pass the new arg — find and fix.

- [ ] **Step 4: Lint**

```bash
uv run ruff check src scripts tests
uv run ty check
```

Expected: both clean.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "refactor(governance): pin existing lock_filename callers to canonical OCO family"
```

---

## Task 5: `BUNDLE_LAYOUTS` grows to 11 entries — failing test

**Files:**
- Test: `tests/test_bundle_paths.py`

- [ ] **Step 1: Add the failing test**

Append to `tests/test_bundle_paths.py`:

```python
@pytest.mark.parametrize(
    "family",
    [
        "oco_first_touch",
        "oco_asymmetric",
        "directional",
        "directional_inverse",
        "directional_run",
        "double_touch",
        "pullback",
        "no_touch",
        "dollar_residual",
        "dispersion_rank",
        "lead_lag",
    ],
)
def test_bundle_layout_registered_for_every_mining_family(family: str) -> None:
    """Each mining family in FAMILY_REGISTRY has a BUNDLE_LAYOUTS row."""
    from src.behemoth.core.bundle_paths import BUNDLE_LAYOUTS, bundle_layout_for

    assert family in BUNDLE_LAYOUTS
    layout = bundle_layout_for(family)

    # Required artifact keys present
    required_keys = {"predictions", "allowed_states_csv", "model_cbm", "model_threshold_json"}
    keys = {spec.v2_key for spec in layout}
    assert required_keys <= keys


@pytest.mark.parametrize(
    "family",
    [
        "oco_first_touch", "oco_asymmetric", "directional", "directional_inverse",
        "directional_run", "double_touch", "pullback", "no_touch",
        "dollar_residual", "dispersion_rank", "lead_lag",
    ],
)
def test_bundle_layout_templates_render_bundle_relative(family: str) -> None:
    """Every template in every family layout renders to a bundle-relative path."""
    from src.behemoth.core.bundle_paths import bundle_layout_for

    layout = bundle_layout_for(family)
    fmt = {"symbol_lower": "eurusd", "symbol_upper": "EURUSD", "family": family, "month": "2026-04"}
    rendered_paths = set()
    for spec in layout:
        relpath = spec.target_relpath_template.format(**fmt)
        # Bundle-relative: no leading slash, no parent escapes.
        assert not relpath.startswith("/"), f"{family}/{spec.v2_key}: {relpath}"
        assert ".." not in relpath.split("/"), f"{family}/{spec.v2_key}: {relpath}"
        # No unsubstituted tokens.
        assert "{" not in relpath and "}" not in relpath, f"{family}/{spec.v2_key}: unsubstituted token in {relpath}"
        rendered_paths.add(relpath)


def test_bundle_layout_families_distinct_for_same_symbol_and_month() -> None:
    """Different families produce distinct artifact filenames for the same symbol/month."""
    from src.behemoth.core.bundle_paths import BUNDLE_LAYOUTS

    fmt_base = {"symbol_lower": "eurusd", "symbol_upper": "EURUSD", "month": "2026-04"}
    all_relpaths: list[str] = []
    for family, layout in BUNDLE_LAYOUTS.items():
        fmt = {**fmt_base, "family": family}
        for spec in layout:
            all_relpaths.append(spec.target_relpath_template.format(**fmt))

    # Each rendered path must be unique across families (no collision).
    assert len(all_relpaths) == len(set(all_relpaths)), (
        "duplicate rendered paths across families: "
        f"{[p for p in all_relpaths if all_relpaths.count(p) > 1]}"
    )
```

- [ ] **Step 2: Run, expect failure**

```bash
uv run pytest tests/test_bundle_paths.py -v -k "bundle_layout"
```

Expected: 22+ failures — 11 parametrised `test_bundle_layout_registered_for_every_mining_family` cases fail (most families missing), 11 parametrised `test_bundle_layout_templates_render_bundle_relative` cases fail, and `test_bundle_layout_families_distinct_for_same_symbol_and_month` fails.

---

## Task 6: `BUNDLE_LAYOUTS` grows to 11 entries — implementation

**Files:**
- Modify: `src/behemoth/core/bundle_paths.py`

- [ ] **Step 1: Replace `BUNDLE_LAYOUTS` with the 11-family form**

Find the existing `BUNDLE_LAYOUTS` dict in `src/behemoth/core/bundle_paths.py`. Replace it with:

```python
def _oco_style_layout(family: str) -> tuple[BundleArtifactSpec, ...]:
    """Build the eight-artifact spec tuple for a family that follows the OCO-style
    layout (per-symbol predictions, per-symbol allowed states, per-symbol-per-month
    model + threshold, optional configs + summaries)."""
    return (
        BundleArtifactSpec("predictions",          f"{{symbol_lower}}_{family}_locked_predictions.parquet", True),
        BundleArtifactSpec("allowed_states_csv",   f"{{symbol_lower}}_{family}_allowed_states.csv",         True),
        BundleArtifactSpec("model_cbm",            f"models/{{symbol_upper}}_{family}_model_{{month}}.cbm", True),
        BundleArtifactSpec("model_threshold_json", f"models/{{symbol_upper}}_{family}_model_{{month}}.json", True),
        BundleArtifactSpec("wfo_config",           f"configs/{{symbol_lower}}_{family}_wfo.yaml",           False),
        BundleArtifactSpec("reduced_config",       f"configs/{{symbol_lower}}_{family}_reduced.yaml",       False),
        BundleArtifactSpec("reduced_summary",      f"{{symbol_lower}}_{family}_reduced_summary.csv",        False),
        BundleArtifactSpec("tick_exact_summary",   f"{{symbol_lower}}_{family}_tick_exact_summary.csv",     False),
    )


_MINING_FAMILY_NAMES: tuple[str, ...] = (
    "oco_first_touch",
    "oco_asymmetric",
    "directional",
    "directional_inverse",
    "directional_run",
    "double_touch",
    "pullback",
    "no_touch",
    "dollar_residual",
    "dispersion_rank",
    "lead_lag",
)


BUNDLE_LAYOUTS: dict[str, tuple[BundleArtifactSpec, ...]] = {
    family: _oco_style_layout(family) for family in _MINING_FAMILY_NAMES
}
```

Note: `_MINING_FAMILY_NAMES` is intentionally a tuple of strings rather than an import from `scripts.mining_family`, because `src/behemoth/core/bundle_paths.py` lives below `scripts/` in dependency order. Keep the two lists synchronised manually for now; an integration-time check is added in Task 7.

If Resolution (a) was chosen in Task 1, replace `"oco_first_touch"` with `"oco_first_touch_clean"` everywhere in this constant and the surrounding code.

- [ ] **Step 2: Confirm the existing `bundle_layout_for(family)` function still works**

```bash
grep -n "def bundle_layout_for" src/behemoth/core/bundle_paths.py
```

The helper should already exist from prior sub-projects. If not, it's:

```python
def bundle_layout_for(family: str) -> tuple[BundleArtifactSpec, ...]:
    if family not in BUNDLE_LAYOUTS:
        raise BundleIntegrityError(f"unknown family: {family!r}")
    return BUNDLE_LAYOUTS[family]
```

- [ ] **Step 3: Run the Task 5 tests**

```bash
uv run pytest tests/test_bundle_paths.py -v -k "bundle_layout"
```

Expected: PASS — all 22+ parametrised cases plus the distinctness test.

- [ ] **Step 4: Lint**

```bash
uv run ruff check src/behemoth/core/bundle_paths.py
```

Expected: clean.

- [ ] **Step 5: Commit**

```bash
git add src/behemoth/core/bundle_paths.py tests/test_bundle_paths.py
git commit -m "feat(governance): BUNDLE_LAYOUTS covers all 11 mining families"
```

---

## Task 7: Sync-check between `BUNDLE_LAYOUTS` and `FAMILY_REGISTRY`

**Files:**
- Test: `tests/test_bundle_paths.py`

Prevents drift between the layout registry in `bundle_paths.py` and the mining family registry in `scripts/mining_family.py`.

- [ ] **Step 1: Add a sync test**

Append to `tests/test_bundle_paths.py`:

```python
def test_bundle_layouts_keys_match_mining_family_registry() -> None:
    """BUNDLE_LAYOUTS must register every family known to mining."""
    from scripts.mining_family import FAMILY_REGISTRY
    from src.behemoth.core.bundle_paths import BUNDLE_LAYOUTS

    layout_families = set(BUNDLE_LAYOUTS.keys())
    mining_families = set(FAMILY_REGISTRY.keys())

    missing_in_layouts = mining_families - layout_families
    extra_in_layouts = layout_families - mining_families

    assert not missing_in_layouts, f"BUNDLE_LAYOUTS missing families: {missing_in_layouts}"
    assert not extra_in_layouts, f"BUNDLE_LAYOUTS has unknown families: {extra_in_layouts}"
```

- [ ] **Step 2: Run the test**

```bash
uv run pytest tests/test_bundle_paths.py::test_bundle_layouts_keys_match_mining_family_registry -v
```

Expected: PASS. If it fails, either Task 6's tuple is wrong or `FAMILY_REGISTRY` has changed — investigate before bypassing.

- [ ] **Step 3: Commit**

```bash
git add tests/test_bundle_paths.py
git commit -m "test(governance): BUNDLE_LAYOUTS stays in sync with FAMILY_REGISTRY"
```

---

## Task 8: Update consumer filter strings

**Files:**
- Modify: every site that calls `iter_locks(..., family="oco_first_touch_clean")`.

This step is conditional. If Task 1 picked Resolution (a), skip this task — no filter strings need to change.

If Resolution (b), proceed.

- [ ] **Step 1: Find all consumer filter strings**

```bash
grep -rn 'family="oco_first_touch_clean"\|family='\''oco_first_touch_clean'\''' src/ scripts/ tests/ 2>/dev/null | grep -v __pycache__
```

Expected: ~5–10 sites in registries, parity checks, etc.

- [ ] **Step 2: Replace each with `<CANONICAL_OCO_FAMILY>`**

Read each file before editing. Change exactly the family string literal — leave everything else alone.

- [ ] **Step 3: Run the full suite**

```bash
uv run pytest -q
```

Expected: PASS. Failures here mean a test fixture is hardcoded to the old family — update the fixture to the new canonical value.

- [ ] **Step 4: Verify no stale references**

```bash
grep -rn 'oco_first_touch_clean' src/ scripts/ tests/ 2>/dev/null | grep -v __pycache__ | grep -v scripts/migrate_lock_schema.py | grep -v "docs/superpowers/"
```

Expected: empty.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "refactor(governance): align consumer filters to canonical OCO family"
```

---

## Task 9: Migration mode — failing test

**Files:**
- Test: `tests/test_migrate_lock_schema.py`

- [ ] **Step 1: Add the failing test**

Append to `tests/test_migrate_lock_schema.py`:

```python
def test_rename_to_family_naming_renames_lock_files(tmp_path: Path) -> None:
    """Old-style `<symbol>_oco_live_lock.json` files rename to family-namespaced form."""
    bundle_dir = tmp_path / "2026-04"
    bundle_dir.mkdir()

    # Build a minimal v3 lock at the OLD filename, with the OLD family value.
    old_lock = bundle_dir / "eurusd_oco_live_lock.json"
    lock_body = {
        "schema_version": 3,
        "symbol": "EURUSD",
        "bundle": {
            "month": "2026-04",
            "dir_relpath": str(bundle_dir),
            "family": "oco_first_touch_clean",  # value before migration
        },
        "artifacts": {},
        "deployability": {"live_deployable": True, "model_month": "2026-04"},
    }
    old_lock.write_text(json.dumps(lock_body))

    # Invoke the migration in --rename-to-family-naming mode.
    result = subprocess.run(
        [
            sys.executable,
            "scripts/migrate_lock_schema.py",
            str(bundle_dir),
            "--rename-to-family-naming",
            "--canonical-oco-family",
            "<CANONICAL_OCO_FAMILY>",
        ],
        capture_output=True,
        text=True,
        cwd=Path(__file__).resolve().parents[1],
    )

    assert result.returncode == 0, result.stderr

    # Old filename gone.
    assert not old_lock.exists()

    # New filename present.
    new_lock = bundle_dir / "eurusd_<CANONICAL_OCO_FAMILY>_live_lock.json"
    assert new_lock.exists()

    new_body = json.loads(new_lock.read_text())
    assert new_body["bundle"]["family"] == "<CANONICAL_OCO_FAMILY>"
    # Schema and other fields preserved.
    assert new_body["schema_version"] == 3
    assert new_body["symbol"] == "EURUSD"


def test_rename_to_family_naming_is_idempotent(tmp_path: Path) -> None:
    """Re-running the migration on an already-renamed bundle is a no-op."""
    bundle_dir = tmp_path / "2026-04"
    bundle_dir.mkdir()
    new_lock = bundle_dir / "eurusd_<CANONICAL_OCO_FAMILY>_live_lock.json"
    new_lock.write_text(json.dumps({
        "schema_version": 3,
        "symbol": "EURUSD",
        "bundle": {"month": "2026-04", "dir_relpath": str(bundle_dir), "family": "<CANONICAL_OCO_FAMILY>"},
        "artifacts": {},
        "deployability": {"live_deployable": True, "model_month": "2026-04"},
    }))
    snapshot = new_lock.read_bytes()

    result = subprocess.run(
        [
            sys.executable,
            "scripts/migrate_lock_schema.py",
            str(bundle_dir),
            "--rename-to-family-naming",
            "--canonical-oco-family",
            "<CANONICAL_OCO_FAMILY>",
        ],
        capture_output=True,
        text=True,
        cwd=Path(__file__).resolve().parents[1],
    )

    assert result.returncode == 0, result.stderr
    assert new_lock.exists()
    assert new_lock.read_bytes() == snapshot, "idempotent run modified file content"
```

Substitute `<CANONICAL_OCO_FAMILY>` with the Task 1 value.

- [ ] **Step 2: Run, expect failure**

```bash
uv run pytest tests/test_migrate_lock_schema.py -v -k "rename_to_family_naming"
```

Expected: FAIL — the new flag doesn't exist yet.

---

## Task 10: Migration mode — implementation

**Files:**
- Modify: `scripts/migrate_lock_schema.py`

- [ ] **Step 1: Add the new mode**

In `scripts/migrate_lock_schema.py`, find the existing argparse setup. Add:

```python
parser.add_argument(
    "--rename-to-family-naming",
    action="store_true",
    help="Rename old-style <symbol>_oco_live_lock.json files to <symbol>_<family>_live_lock.json.",
)
parser.add_argument(
    "--canonical-oco-family",
    default="<CANONICAL_OCO_FAMILY>",
    help=(
        "Canonical family name to use when rewriting the bundle.family field "
        "of old-style locks. Defaults to the project canonical value."
    ),
)
```

Then, in the main function, add a new branch that runs before (or instead of) the existing v1→v3 migration when the flag is set:

```python
def _rename_to_family_naming(bundle_dir: Path, canonical_family: str) -> int:
    renamed = 0
    skipped = 0
    for lock_path in sorted(bundle_dir.glob("*_live_lock.json")):
        name = lock_path.name
        # Skip files already in the family-namespaced form. Heuristic: anything
        # that already has `_<known_family>_live_lock.json` is left alone.
        from src.behemoth.core.bundle_paths import BUNDLE_LAYOUTS  # local import to avoid cycle

        already_family_named = any(
            name.endswith(f"_{family}_live_lock.json") for family in BUNDLE_LAYOUTS
        )
        if already_family_named:
            skipped += 1
            continue

        # Old form: <symbol>_oco_live_lock.json
        if not name.endswith("_oco_live_lock.json"):
            print(f"[migrate] unknown lock filename shape, skipping: {lock_path}", file=sys.stderr)
            continue

        symbol_prefix = name[: -len("_oco_live_lock.json")]

        # Rewrite bundle.family to the canonical family.
        body = json.loads(lock_path.read_text(encoding="utf-8"))
        bundle = body.setdefault("bundle", {})
        bundle["family"] = canonical_family

        new_name = f"{symbol_prefix}_{canonical_family}_live_lock.json"
        new_path = lock_path.with_name(new_name)
        new_path.write_text(json.dumps(body, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        lock_path.unlink()
        renamed += 1
        print(f"[migrate] {name} -> {new_name}")

    print(f"[migrate] renamed={renamed} skipped={skipped} dir={bundle_dir}")
    return 0
```

Wire it into the main path:

```python
if args.rename_to_family_naming:
    return _rename_to_family_naming(Path(args.bundle_dir), args.canonical_oco_family)
# ... existing v1→v3 path stays for other modes
```

- [ ] **Step 2: Run the tests**

```bash
uv run pytest tests/test_migrate_lock_schema.py -v -k "rename_to_family_naming"
```

Expected: PASS.

- [ ] **Step 3: Lint**

```bash
uv run ruff check scripts/migrate_lock_schema.py tests/test_migrate_lock_schema.py
```

Expected: clean.

- [ ] **Step 4: Commit**

```bash
git add scripts/migrate_lock_schema.py tests/test_migrate_lock_schema.py
git commit -m "feat(governance): migrate_lock_schema --rename-to-family-naming"
```

---

## Task 11: Apply migration to on-disk bundles

**Files:**
- Modify: every `*_oco_live_lock.json` in `configs/research/governance/oco/`, `configs/research/governance/oco_history/*/`, and `configs/research/governance/oco_candidate_builds/*/`.

- [ ] **Step 1: Confirm v3 schema across the target dirs**

```bash
uv run python -c "
import json
from pathlib import Path

roots = [
    Path('configs/research/governance/oco'),
    *sorted(Path('configs/research/governance/oco_history').glob('*')),
    *sorted(Path('configs/research/governance/oco_candidate_builds').glob('*')),
]
for r in roots:
    locks = sorted(r.glob('*_live_lock.json')) if r.exists() else []
    if not locks:
        continue
    schemas = {json.loads(p.read_text()).get('schema_version') for p in locks}
    print(f'{r}: {len(locks)} locks, schemas={schemas}')
"
```

Expected: every root reports `schemas={3}`.

**If any root reports a non-3 schema (e.g. {1}), stop and escalate.** The spec assumes v3 on disk; sub-project A doesn't include a v1→v3 migration. The existing migration tool can do it (`uv run python scripts/migrate_lock_schema.py <dir>` with no `--rename-to-family-naming` flag), but applying it here expands sub-project A's scope. Ask the user whether to include it in this PR or split.

- [ ] **Step 2: Run the rename across every target dir**

```bash
for dir in \
    configs/research/governance/oco \
    configs/research/governance/oco_history/*/ \
    configs/research/governance/oco_candidate_builds/*/
do
    [ -d "$dir" ] || continue
    uv run python scripts/migrate_lock_schema.py "$dir" --rename-to-family-naming
done
```

Expected: each invocation prints `renamed=N skipped=M`. After all complete, no `*_oco_live_lock.json` (the old form) should remain.

- [ ] **Step 3: Verify**

```bash
command find configs/research/governance -name "*_oco_live_lock.json" 2>&1 | head
```

Expected: empty (the old form is gone).

```bash
command find configs/research/governance -name "*_<CANONICAL_OCO_FAMILY>_live_lock.json" 2>&1 | wc -l
```

Expected: the same number of locks that existed before, now at the new filenames.

- [ ] **Step 4: Validate every bundle**

```bash
for dir in \
    configs/research/governance/oco \
    configs/research/governance/oco_history/*/ \
    configs/research/governance/oco_candidate_builds/*/
do
    [ -d "$dir" ] || continue
    uv run python scripts/validate_bundle.py "$dir" || echo "FAIL: $dir"
done
```

Expected: every dir prints `[validate-bundle] OK: N locks in <dir>`. Any FAIL means the migration left an inconsistent bundle — investigate.

- [ ] **Step 5: Commit**

```bash
git add configs/research/governance
git commit -m "chore(governance): rename OCO locks to family-namespaced filenames"
```

---

## Task 12: Producer `--family` arg — `freeze_monthly_bundle.py`

**Files:**
- Modify: `scripts/freeze_monthly_bundle.py`
- Modify: `tests/test_freeze_monthly_bundle.py`

- [ ] **Step 1: Failing test**

Append to `tests/test_freeze_monthly_bundle.py`:

```python
def test_freeze_monthly_bundle_accepts_family_argument() -> None:
    """The freeze script's argparse accepts --family with a default of <CANONICAL_OCO_FAMILY>."""
    import subprocess
    import sys
    from pathlib import Path

    result = subprocess.run(
        [sys.executable, "scripts/freeze_monthly_bundle.py", "--help"],
        capture_output=True,
        text=True,
        cwd=Path(__file__).resolve().parents[1],
    )
    assert result.returncode == 0
    assert "--family" in result.stdout
```

Substitute `<CANONICAL_OCO_FAMILY>` if you need it in the assertion (the test above only checks the flag exists; default-value testing is below).

- [ ] **Step 2: Run, expect failure**

```bash
uv run pytest tests/test_freeze_monthly_bundle.py::test_freeze_monthly_bundle_accepts_family_argument -v
```

Expected: FAIL — `--family` is not registered.

- [ ] **Step 3: Add the argument**

In `scripts/freeze_monthly_bundle.py`, find the argparse setup. Add:

```python
parser.add_argument(
    "--family",
    default="<CANONICAL_OCO_FAMILY>",
    help="Mining family to freeze. Must match a key in BUNDLE_LAYOUTS.",
)
```

Then, inside the function that builds the lock manifest and writes the lock file, replace any hardcoded `oco_first_touch_clean` (or whatever the OCO family was) with `args.family`. Replace any hardcoded reference to the OCO layout (e.g. `bundle_layout_for("oco_first_touch_clean")`) with `bundle_layout_for(args.family)`. Replace any call to `lock_filename(symbol)` with `lock_filename(symbol, args.family)`.

If the script doesn't yet call `lock_filename` directly (it may construct the filename inline), introduce the call now using the helper.

- [ ] **Step 4: Run the test**

```bash
uv run pytest tests/test_freeze_monthly_bundle.py -v
```

Expected: PASS, full file. Failures elsewhere in `test_freeze_monthly_bundle.py` are likely from the family substitution — fix by updating the test fixture to also pass the new arg.

- [ ] **Step 5: Lint**

```bash
uv run ruff check scripts/freeze_monthly_bundle.py tests/test_freeze_monthly_bundle.py
```

Expected: clean.

- [ ] **Step 6: Commit**

```bash
git add scripts/freeze_monthly_bundle.py tests/test_freeze_monthly_bundle.py
git commit -m "feat(governance): freeze_monthly_bundle accepts --family"
```

---

## Task 13: Producer `--family` arg — `freeze_oco_live_governance.py`

**Files:**
- Modify: `scripts/freeze_oco_live_governance.py`
- Modify: `tests/test_freeze_oco_live_governance.py` (or its current equivalent — read first)

Mirror Task 12 on the live-governance freeze script.

- [ ] **Step 1: Failing test**

In whichever test file currently covers `freeze_oco_live_governance.py` (find via `grep -rln "freeze_oco_live_governance" tests/`), append:

```python
def test_freeze_oco_live_governance_accepts_family_argument() -> None:
    import subprocess
    import sys
    from pathlib import Path

    result = subprocess.run(
        [sys.executable, "scripts/freeze_oco_live_governance.py", "--help"],
        capture_output=True,
        text=True,
        cwd=Path(__file__).resolve().parents[1],
    )
    assert result.returncode == 0
    assert "--family" in result.stdout
```

- [ ] **Step 2: Run, expect failure**

```bash
uv run pytest -k "freeze_oco_live_governance_accepts_family_argument" -v
```

Expected: FAIL.

- [ ] **Step 3: Add the argument**

In `scripts/freeze_oco_live_governance.py`, mirror the change from Task 12 Step 3: argparse arg with default `<CANONICAL_OCO_FAMILY>`, replace hardcoded family/layout/lock_filename references.

- [ ] **Step 4: Run**

```bash
uv run pytest -k "freeze_oco_live_governance" -v
```

Expected: PASS.

- [ ] **Step 5: Lint + commit**

```bash
uv run ruff check scripts/freeze_oco_live_governance.py
git add scripts/freeze_oco_live_governance.py tests/
git commit -m "feat(governance): freeze_oco_live_governance accepts --family"
```

---

## Task 14: `run_monthly_build.py` single-family loop

**Files:**
- Modify: `scripts/run_monthly_build.py`
- Modify: `tests/test_run_monthly_build.py`

- [ ] **Step 1: Inspect existing test**

```bash
grep -n "freeze_monthly_bundle\|step 2/2" tests/test_run_monthly_build.py | head
```

There's a test asserting the subprocess command includes `scripts/freeze_monthly_bundle.py`. After this task, the assertion needs to include `--family` and `<CANONICAL_OCO_FAMILY>`.

- [ ] **Step 2: Add a failing test**

Append to `tests/test_run_monthly_build.py`:

```python
def test_run_monthly_build_passes_family_to_freeze(monkeypatch) -> None:
    """run_monthly_build invokes freeze with --family <CANONICAL_OCO_FAMILY>."""
    from scripts import run_monthly_build

    captured: list[list[str]] = []

    class _Result:
        returncode = 0

    def _fake_run(cmd, cwd=None):
        captured.append(list(cmd))
        return _Result()

    monkeypatch.setattr(run_monthly_build.subprocess, "run", _fake_run)
    monkeypatch.setattr(run_monthly_build, "_materialize_bundle_models", lambda _bundle_dir: None)
    monkeypatch.setattr(run_monthly_build, "_derive_model_month", lambda _arg: "2026-04")

    run_monthly_build.main_with_args(["--model-month", "2026-04"])

    freeze_invocations = [
        c for c in captured
        if any("freeze_monthly_bundle.py" in part for part in c)
    ]
    assert freeze_invocations, "expected at least one freeze invocation"
    for cmd in freeze_invocations:
        assert "--family" in cmd, f"freeze invocation missing --family: {cmd}"
        family_index = cmd.index("--family")
        assert cmd[family_index + 1] == "<CANONICAL_OCO_FAMILY>", cmd
```

This test relies on `run_monthly_build.main_with_args(...)` being callable with a list — if the script's `main` only accepts `argparse.Namespace`, refactor it in this task to a tiny `main_with_args(argv)` wrapper that's testable.

- [ ] **Step 3: Run, expect failure**

```bash
uv run pytest tests/test_run_monthly_build.py::test_run_monthly_build_passes_family_to_freeze -v
```

Expected: FAIL.

- [ ] **Step 4: Implement the loop**

In `scripts/run_monthly_build.py`, near the existing `_run_step([..., "scripts/freeze_monthly_bundle.py", ...])` call, replace with:

```python
FAMILIES_TO_FREEZE: tuple[str, ...] = ("<CANONICAL_OCO_FAMILY>",)  # extended in sub-projects D/E

for family in FAMILIES_TO_FREEZE:
    _run_step(
        [
            "uv", "run", "python", "scripts/freeze_monthly_bundle.py",
            "--family", family,
            # ... existing args (--allow-dirty, --symbols, --out-dir, --months, etc.)
        ],
        f"step 2/2: freeze_monthly_bundle ({family})",
    )
```

Read the surrounding code first to keep the rest of the argument list correct.

If the script's existing `main` is monolithic, factor out:

```python
def main_with_args(argv: list[str] | None = None) -> None:
    args = parser.parse_args(argv)
    # ... existing main body
```

so the test can drive it without mocking sys.argv.

- [ ] **Step 5: Run the test**

```bash
uv run pytest tests/test_run_monthly_build.py -v
```

Expected: PASS.

- [ ] **Step 6: Lint + commit**

```bash
uv run ruff check scripts/run_monthly_build.py tests/test_run_monthly_build.py
git add scripts/run_monthly_build.py tests/test_run_monthly_build.py
git commit -m "refactor(governance): run_monthly_build loops over family list (currently single)"
```

---

## Task 15: Round-trip non-OCO family via fixture-registered synthetic family

**Files:**
- Test: `tests/test_bundle_paths.py`

Plan A already shipped a similar test (`test_non_oco_family_round_trip`). Confirm it still passes; add a new test that uses an already-registered family (e.g. `directional`) rather than a synthetic one, since this PR registers all 11.

- [ ] **Step 1: Add the failing test**

Append to `tests/test_bundle_paths.py`:

```python
def test_directional_family_round_trip(tmp_path: Path) -> None:
    """A directional-family lock can be written, read, and validated end-to-end."""
    import hashlib
    import json
    import subprocess
    import sys

    from src.behemoth.core.bundle_paths import BundlePaths, bundle_layout_for

    bundle_dir = tmp_path / "2026-04"
    (bundle_dir / "models").mkdir(parents=True)

    layout = bundle_layout_for("directional")
    fmt = {"symbol_lower": "eurusd", "symbol_upper": "EURUSD", "family": "directional", "month": "2026-04"}

    # Build a synthetic file per required artifact.
    artifacts_block = {}
    for spec in layout:
        if not spec.required:
            continue
        relpath = spec.target_relpath_template.format(**fmt)
        abs_path = bundle_dir / relpath
        abs_path.parent.mkdir(parents=True, exist_ok=True)
        content = f"synthetic-{spec.v2_key}".encode()
        abs_path.write_bytes(content)
        artifacts_block[spec.v2_key] = {
            "path": relpath,
            "sha256": hashlib.sha256(content).hexdigest(),
        }

    lock = {
        "schema_version": 3,
        "symbol": "EURUSD",
        "bundle": {"month": "2026-04", "dir_relpath": str(bundle_dir), "family": "directional"},
        "artifacts": artifacts_block,
        "deployability": {"live_deployable": True, "model_month": "2026-04"},
    }
    lock_path = bundle_dir / "eurusd_directional_live_lock.json"
    lock_path.write_text(json.dumps(lock))

    # Resolver works.
    parsed = BundlePaths.from_lock(lock_path)
    assert parsed.family == "directional"
    assert parsed.predictions().name == "eurusd_directional_locked_predictions.parquet"
    assert parsed.model_cbm().name == "EURUSD_directional_model_2026-04.cbm"

    # validate_bundle accepts the dir.
    result = subprocess.run(
        [sys.executable, "scripts/validate_bundle.py", str(bundle_dir)],
        capture_output=True,
        text=True,
        cwd=Path(__file__).resolve().parents[1],
    )
    assert result.returncode == 0, result.stderr
```

- [ ] **Step 2: Run**

```bash
uv run pytest tests/test_bundle_paths.py::test_directional_family_round_trip -v
```

Expected: PASS — `directional` is now a real registered family with valid templates.

- [ ] **Step 3: Commit**

```bash
git add tests/test_bundle_paths.py
git commit -m "test(governance): round-trip directional family through BundlePaths"
```

---

## Task 16: Final verification

- [ ] **Step 1: Full suite**

```bash
uv run pytest -q
```

Expected: green.

- [ ] **Step 2: Lint**

```bash
uv run ruff check src scripts tests
uv run ty check
```

Expected: both clean.

- [ ] **Step 3: Every bundle still validates**

```bash
for dir in \
    configs/research/governance/oco \
    configs/research/governance/oco_history/*/ \
    configs/research/governance/oco_candidate_builds/*/
do
    [ -d "$dir" ] || continue
    uv run python scripts/validate_bundle.py "$dir"
done
```

Expected: every dir prints `OK`. If `oco_candidate_builds/<month>/` is empty (per Task 1 inspection), validate_bundle's "no locks in <dir>" behaviour is acceptable — note in the PR body.

- [ ] **Step 4: No old-style filenames remain**

```bash
command find configs/research/governance -name "*_oco_live_lock.json" 2>&1 | head
```

Expected: empty.

- [ ] **Step 5: No zero-arg `lock_filename` calls remain**

```bash
grep -rn "lock_filename([^,]*)" src/ scripts/ tests/ 2>/dev/null | grep -v __pycache__ | grep -v "def lock_filename"
```

Expected: empty.

- [ ] **Step 6: BUNDLE_LAYOUTS still in sync with FAMILY_REGISTRY**

```bash
uv run pytest tests/test_bundle_paths.py::test_bundle_layouts_keys_match_mining_family_registry -v
```

Expected: PASS.

- [ ] **Step 7: Open the PR**

Use `superpowers:finishing-a-development-branch`. PR title: `feat(governance): all 11 mining families have bundle layouts (sub-project A)`. Body must reference:
- ADR 0003 (the canonical OCO family decision committed in Task 1).
- The on-disk migration scope (`oco/`, `oco_history/*/`, `oco_candidate_builds/*/`).
- The fact that consumers still hardcode-filter to OCO; sub-projects D/E onboard real families.

---

## Self-Review

**Spec coverage:**

| Spec section | Plan task |
|---|---|
| `lock_filename(symbol, family)` signature change | Tasks 2–4 |
| `BUNDLE_LAYOUTS` grows to 11 entries | Tasks 5–7 |
| Existing `oco_first_touch_clean` row's fate | Task 1 decision + Task 6 implementation + Task 8 consumer updates |
| Producer `--family` argument (freeze_monthly_bundle) | Task 12 |
| Producer `--family` argument (freeze_oco_live_governance) | Task 13 |
| `run_monthly_build.py` single-family loop | Task 14 |
| `validate_bundle.py` no code change | Verified in Task 11 Step 4 and Task 16 Step 3 |
| Consumers keep OCO filter — no code change beyond Task 8's family-string update | Task 8 |
| Migration: rename JSONs, untouched artifacts | Tasks 9–11 |
| Open issue: canonical family name | Task 1 |
| Testing: round-trip non-OCO family | Task 15 |
| Testing: parametrised template render | Task 5–6 |
| Testing: lock_filename signature | Task 2–3 |
| Testing: migration idempotency | Task 9–10 |

**Placeholder scan:** Every `<CANONICAL_OCO_FAMILY>` placeholder is required to be substituted by the implementer after Task 1 — flagged explicitly in the Task 1 final step. No other placeholders.

**Type consistency:** `BUNDLE_LAYOUTS: dict[str, tuple[BundleArtifactSpec, ...]]` used consistently across tasks. `lock_filename(symbol, family) -> str` used consistently. The 11 family names match across Task 5's parametrize list and Task 6's `_MINING_FAMILY_NAMES` tuple.

---

## Risks for the Implementer

- **Task 11 Step 1 might surface v1 schema on disk.** The spec assumed v3. If v1 is found, stop and escalate — adding v1→v3 migration to this PR expands scope materially.
- **Task 1's resolution shapes Tasks 6, 8, 9–11, 12, 13, 14.** Doing Task 1 properly is non-negotiable. Don't proceed without committing ADR 0003.
- **State-id rewrites under Resolution (b).** If Task 1 picks (b), the migration also needs to rewrite every `state_universe.rows[].state_id` and `.family` string inside the lock body. That's not in the current migration mode — extend Task 10's implementation to handle it (it's a content rewrite, not just a rename). The Task 9 test should already exercise this (it asserts `bundle.family` is rewritten); add an additional assertion for state-id rewrite if (b) is picked.
- **`run_monthly_build.py` testability.** The script may not have a `main_with_args` entry point today — Task 14 introduces one. Keep the refactor minimal: extract the body of `if __name__ == "__main__"` into a function callable from a test.
- **Task 4's "update every call site" is wide.** The plan assumes ~10 sites; reality may be more. Run the grep audit at Step 1 and add any missed sites to a follow-up commit before merging.
