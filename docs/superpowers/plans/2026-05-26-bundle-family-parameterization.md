# Bundle Family Parameterization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Lift the `_oco_` filename baking out of `BUNDLE_LAYOUT` and into a family-keyed registry, so non-OCO mining outcomes can be expressed as bundles. Every lock declares `bundle.family`; producers and validators look up the layout for that family.

**Architecture:** `BUNDLE_LAYOUT: tuple[BundleArtifactSpec, ...]` becomes `BUNDLE_LAYOUTS: dict[str, tuple[BundleArtifactSpec, ...]]` keyed by family name. A new helper `bundle_layout_for(family: str) -> tuple[BundleArtifactSpec, ...]` is the single lookup point. Lock schema bumps to `schema_version: 3` to add a required `bundle.family` field; the existing 2026-02/03/04 locks are migrated in one shot to record `family: "oco_first_touch_clean"`. No fallbacks — `BundlePaths.from_lock` refuses v1 and v2 the same way v2 refused v1.

**Tech Stack:** Python 3.12, `uv`, `pytest`, `ruff`. No new dependencies.

---

## Current State

`src/behemoth/core/bundle_paths.py:31-38` hardcodes `_oco_` filenames in 6 of 8 `BUNDLE_LAYOUT` entries. Every v2 producer (`scripts/freeze_oco_live_governance.py`, `scripts/legacy/freeze_oco_historical_governance.py`, `scripts/migrate_lock_to_v2.py`) consumes that constant. A bundle for a non-OCO mining outcome — single-barrier first-touch, breakout, momentum — has no place to live: the writer side will always emit `_oco_*` filenames.

The reader side is already family-agnostic: `BundlePaths` reads `artifacts.<key>.path` straight out of the lock JSON, so a non-OCO bundle could in principle be loaded. But producers, the migration tool, and the bundle validator cannot construct one.

`state_universe.rows[].family = "oco_first_touch_clean"` exists in current locks as data inside the universe — not as a bundle-level discriminator. We promote it to `bundle.family`.

---

## File Structure

**New files:**
- `docs/adr/0002-multi-family-bundle-contract.md`

**Modified files:**
- `src/behemoth/core/bundle_paths.py` — `BUNDLE_LAYOUT` → `BUNDLE_LAYOUTS`; add `bundle_layout_for()`, `bp.family`; bump schema check to 3.
- `scripts/migrate_lock_to_v2.py` → renamed `scripts/migrate_lock_schema.py` (handles v1→v3 and v2→v3).
- `scripts/freeze_oco_live_governance.py` — emit v3 with `bundle.family`.
- `scripts/legacy/freeze_oco_historical_governance.py` — emit v3 with `bundle.family`.
- `scripts/validate_bundle.py` — fail when `bundle.family` missing or unknown.
- Existing on-disk locks at `configs/research/governance/oco_candidate_builds/2026-{02,03,04}/*_oco_live_lock.json` — migrated in place.
- `tests/test_bundle_paths.py`, `tests/test_validate_bundle.py`, `tests/test_migrate_lock_to_v2.py` (renamed), and producer tests.

---

## Target Lock Shape (schema_version: 3)

```json
{
  "schema_version": 3,
  "symbol": "EURUSD",
  "bundle": {
    "month": "2026-04",
    "dir_relpath": "configs/research/governance/oco_candidate_builds/2026-04",
    "family": "oco_first_touch_clean"
  },
  "artifacts": { ... },
  "provenance": { ... },
  "deployability": { ... },
  ...
}
```

`bundle.family` is required. Reading a lock with `schema_version != 3` raises `BundleIntegrityError`. Reading a lock missing `bundle.family` raises `BundleIntegrityError`. Reading a lock with a family not in `BUNDLE_LAYOUTS` raises `BundleIntegrityError`.

---

## Task 1: ADR 0002

**Files:**
- Create: `docs/adr/0002-multi-family-bundle-contract.md`

- [ ] **Step 1: Write the ADR**

```markdown
# ADR 0002: Multi-Family Bundle Contract

- Status: Accepted
- Date: 2026-05-26
- Supersedes parts of: ADR 0001

## Context

ADR 0001 fixed bundle pathing but baked the OCO family into `BUNDLE_LAYOUT` (`{symbol_lower}_oco_locked_predictions.parquet`, etc.). Non-OCO mining outcomes — single-barrier first-touch, breakout, momentum — cannot be expressed as bundles today, even though the reader side (`BundlePaths.from_lock`) is already family-agnostic.

## Decision

1. Every `*_live_lock.json` conforms to `schema_version: 3`.
2. v3 adds a required `bundle.family: str` field identifying the mining outcome the bundle was produced for.
3. `BUNDLE_LAYOUT` is replaced by `BUNDLE_LAYOUTS: dict[str, tuple[BundleArtifactSpec, ...]]`, keyed by family. Filename templates within each layout MAY include the family name; they MUST NOT hardcode any family they don't claim.
4. A new helper `bundle_layout_for(family: str) -> tuple[BundleArtifactSpec, ...]` is the only sanctioned lookup. Unknown families raise `BundleIntegrityError`.
5. Producers (`freeze_oco_live_governance.py`, `freeze_oco_historical_governance.py`) accept the family they are freezing for and use the matching layout.
6. The lock filename suffix remains `_live_lock.json` (no family in the filename); discrimination happens via `bundle.family` after reading.
7. There is no fallback for missing or unknown families. Stale v1 or v2 locks fail loud and must be migrated.

## Consequences

- One-shot migration converts existing v2 locks to v3 by inserting `bundle.family: "oco_first_touch_clean"`.
- Adding a new family means adding one row to `BUNDLE_LAYOUTS` and producing bundles via the existing freeze tooling. No consumer changes required.
- The OCO assumption is removed from path resolution; it remains only in glob/filename patterns at consumer sites — those are handled in a separate ADR.
```

- [ ] **Step 2: Commit**

```bash
git add docs/adr/0002-multi-family-bundle-contract.md
git commit -m "docs(adr): add 0002 multi-family bundle contract"
```

---

## Task 2: BUNDLE_LAYOUTS registry — failing test

**Files:**
- Test: `tests/test_bundle_paths.py`

- [ ] **Step 1: Add failing tests**

Append to `tests/test_bundle_paths.py`:

```python
def test_bundle_layouts_exposes_oco_family() -> None:
    from src.behemoth.core.bundle_paths import BUNDLE_LAYOUTS, bundle_layout_for

    assert "oco_first_touch_clean" in BUNDLE_LAYOUTS
    layout = bundle_layout_for("oco_first_touch_clean")
    keys = {spec.v2_key for spec in layout}
    assert {"predictions", "allowed_states_csv", "model_cbm", "model_threshold_json"} <= keys


def test_bundle_layouts_rejects_unknown_family() -> None:
    from src.behemoth.core.bundle_paths import bundle_layout_for, BundleIntegrityError

    with pytest.raises(BundleIntegrityError, match="unknown family"):
        bundle_layout_for("not_a_real_family")


def test_bundle_paths_exposes_family(tmp_path: Path) -> None:
    """from_lock surfaces bundle.family on the resolver."""
    lock_path = _write_v3_bundle(tmp_path, family="oco_first_touch_clean")  # helper to add in this task
    bp = BundlePaths.from_lock(lock_path)
    assert bp.family == "oco_first_touch_clean"


def test_bundle_paths_rejects_v2_lock(tmp_path: Path) -> None:
    """A v2 lock (no schema_version=3, no bundle.family) must fail loud."""
    lock_path = _write_v3_bundle(tmp_path, family="oco_first_touch_clean")
    data = json.loads(lock_path.read_text())
    data["schema_version"] = 2
    data["bundle"].pop("family", None)
    lock_path.write_text(json.dumps(data))
    with pytest.raises(BundleIntegrityError, match="schema_version=3"):
        BundlePaths.from_lock(lock_path)


def test_bundle_paths_rejects_missing_family(tmp_path: Path) -> None:
    lock_path = _write_v3_bundle(tmp_path, family="oco_first_touch_clean")
    data = json.loads(lock_path.read_text())
    data["bundle"].pop("family", None)
    lock_path.write_text(json.dumps(data))
    with pytest.raises(BundleIntegrityError, match="bundle.family"):
        BundlePaths.from_lock(lock_path)
```

Add this helper near the existing `_write_v2_bundle` helper in the same file:

```python
def _write_v3_bundle(tmp_path: Path, family: str = "oco_first_touch_clean", symbol: str = "EURUSD") -> Path:
    """Builds a minimal v3 bundle for tests; mirrors the v2 helper shape."""
    bundle_dir = tmp_path / "configs/research/governance/oco_candidate_builds/2026-04"
    (bundle_dir / "models").mkdir(parents=True)
    pred = b"prediction-bytes"; states = b"states-bytes"; cbm = b"cbm-bytes"; thr = b"thr-bytes"
    (bundle_dir / f"{symbol.lower()}_oco_locked_predictions.parquet").write_bytes(pred)
    (bundle_dir / f"{symbol.lower()}_oco_allowed_states.csv").write_bytes(states)
    (bundle_dir / "models" / f"{symbol}_model_2026-04.cbm").write_bytes(cbm)
    (bundle_dir / "models" / f"{symbol}_model_2026-04.json").write_bytes(thr)
    lock = {
        "schema_version": 3,
        "symbol": symbol,
        "bundle": {"month": "2026-04", "dir_relpath": str(bundle_dir), "family": family},
        "artifacts": {
            "predictions":          {"path": f"{symbol.lower()}_oco_locked_predictions.parquet", "sha256": _sha256(pred)},
            "allowed_states_csv":   {"path": f"{symbol.lower()}_oco_allowed_states.csv",         "sha256": _sha256(states)},
            "model_cbm":            {"path": f"models/{symbol}_model_2026-04.cbm",               "sha256": _sha256(cbm)},
            "model_threshold_json": {"path": f"models/{symbol}_model_2026-04.json",              "sha256": _sha256(thr)},
        },
        "deployability": {"live_deployable": True, "model_month": "2026-04"},
    }
    lock_path = bundle_dir / f"{symbol.lower()}_oco_live_lock.json"
    lock_path.write_text(json.dumps(lock))
    return lock_path
```

Also update **every existing test** in this file that uses `_write_v2_bundle` to call `_write_v3_bundle` instead (rename in-place is fine since the v2 helper's role is replaced by v3). The `schema_version: 2` assertion in `test_rejects_schema_v1` becomes `schema_version: 3` (assert that v2 is also rejected per the new contract).

- [ ] **Step 2: Run failing tests**

Run: `uv run pytest tests/test_bundle_paths.py -v`
Expected: FAIL on the four new tests because `BUNDLE_LAYOUTS`, `bundle_layout_for`, `bp.family` don't exist yet, and the v2-rejection test fails because current code accepts v2.

---

## Task 3: BUNDLE_LAYOUTS registry — implementation

**Files:**
- Modify: `src/behemoth/core/bundle_paths.py`

- [ ] **Step 1: Replace `BUNDLE_LAYOUT` with `BUNDLE_LAYOUTS` + helper**

In `src/behemoth/core/bundle_paths.py`:

```python
# Replace the existing `BUNDLE_LAYOUT` constant with:

BUNDLE_LAYOUTS: dict[str, tuple[BundleArtifactSpec, ...]] = {
    "oco_first_touch_clean": (
        BundleArtifactSpec("predictions",          "{symbol_lower}_oco_locked_predictions.parquet", True),
        BundleArtifactSpec("allowed_states_csv",   "{symbol_lower}_oco_allowed_states.csv",         True),
        BundleArtifactSpec("model_cbm",            "models/{symbol_upper}_model_{month}.cbm",       True),
        BundleArtifactSpec("model_threshold_json", "models/{symbol_upper}_model_{month}.json",      True),
        BundleArtifactSpec("wfo_config",           "configs/{symbol_lower}_wfo.yaml",               False),
        BundleArtifactSpec("reduced_config",       "configs/{symbol_lower}_reduced.yaml",           False),
        BundleArtifactSpec("reduced_summary",      "{symbol_lower}_oco_reduced_summary.csv",        False),
        BundleArtifactSpec("tick_exact_summary",   "{symbol_lower}_oco_tick_exact_summary.csv",     False),
    ),
}


def bundle_layout_for(family: str) -> tuple[BundleArtifactSpec, ...]:
    if family not in BUNDLE_LAYOUTS:
        raise BundleIntegrityError(f"unknown family: {family!r}")
    return BUNDLE_LAYOUTS[family]
```

Delete the old `BUNDLE_LAYOUT` symbol entirely. Any caller (e.g. `migrate_lock_to_v2.py`, freeze scripts) will fail import — fixing those is later tasks.

- [ ] **Step 2: Update `BundlePaths` to require schema 3 and expose `family`**

In `BundlePaths`:

```python
@dataclass(frozen=True)
class BundlePaths:
    lock_path: Path
    bundle_dir: Path
    symbol: str
    model_month: str
    family: str            # new
    _artifacts: dict[str, _Artifact]
    _deployability: dict[str, Any]

    @classmethod
    def from_lock(cls, lock_path: Path) -> BundlePaths:
        lock_path = Path(lock_path)
        data = json.loads(lock_path.read_text(encoding="utf-8"))
        if int(data.get("schema_version", 0)) != 3:
            raise BundleIntegrityError(
                f"{lock_path}: requires schema_version=3 (got {data.get('schema_version')!r})"
            )
        bundle = data.get("bundle", {}) or {}
        family = str(bundle.get("family", "")).strip()
        if not family:
            raise BundleIntegrityError(f"{lock_path}: missing bundle.family")
        # Confirm the family is known to this build of the resolver.
        bundle_layout_for(family)  # raises BundleIntegrityError on unknown
        # ... rest of from_lock unchanged ...
        return cls(
            lock_path=lock_path,
            bundle_dir=bundle_dir,
            symbol=str(data.get("symbol", "")).upper().strip(),
            model_month=str(deploy.get("model_month", "")).strip(),
            family=family,
            _artifacts=artifacts,
            _deployability=dict(deploy),
        )
```

- [ ] **Step 3: Run tests**

Run: `uv run pytest tests/test_bundle_paths.py -v`
Expected: PASS. All new tests + existing tests (which now use `_write_v3_bundle`) green.

- [ ] **Step 4: Lint**

Run: `uv run ruff check src/behemoth/core/bundle_paths.py tests/test_bundle_paths.py`
Expected: `All checks passed!`

- [ ] **Step 5: Commit**

```bash
git add src/behemoth/core/bundle_paths.py tests/test_bundle_paths.py
git commit -m "feat(governance): family-keyed BUNDLE_LAYOUTS + schema v3 in BundlePaths"
```

---

## Task 4: Rename migrate_lock_to_v2 → migrate_lock_schema and emit v3

**Files:**
- Rename: `scripts/migrate_lock_to_v2.py` → `scripts/migrate_lock_schema.py`
- Rename: `tests/test_migrate_lock_to_v2.py` → `tests/test_migrate_lock_schema.py`

- [ ] **Step 1: Rename via git**

```bash
git mv scripts/migrate_lock_to_v2.py scripts/migrate_lock_schema.py
git mv tests/test_migrate_lock_to_v2.py tests/test_migrate_lock_schema.py
```

- [ ] **Step 2: Update the script to emit v3 with family**

In `scripts/migrate_lock_schema.py`:

1. Replace the import `from src.behemoth.core.bundle_paths import BUNDLE_LAYOUT` (if present) with `from src.behemoth.core.bundle_paths import bundle_layout_for`.
2. Change the `--family` CLI argument: add it with default `"oco_first_touch_clean"`.
3. In `_migrate_one`, accept `family: str`, look up `layout = bundle_layout_for(family)`, iterate `layout` instead of the deleted `_PLAN`. Update target paths via the layout templates.
4. When constructing the v3 lock dict, set `"schema_version": 3` and include `"family": family` inside the `bundle` block.
5. Idempotence check: if the lock is already v3, no-op (do not bump again).
6. If the lock is v2 (post-ADR 0001), accept it and only inject `bundle.family`. If the lock is v1, do the full v1→v3 migration. Use a single switch on `schema_version`.

```python
def _migrate_one(lock_path: Path, repo_root: Path, family: str) -> None:
    data = json.loads(lock_path.read_text(encoding="utf-8"))
    version = int(data.get("schema_version", 0))
    if version == 3:
        return
    if version == 2:
        bundle = data.setdefault("bundle", {})
        bundle["family"] = family
        data["schema_version"] = 3
        lock_path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return
    if version != 1:
        raise SystemExit(f"{lock_path}: unsupported schema_version={version!r}")
    # ... v1 → v3 full migration using bundle_layout_for(family) ...
```

- [ ] **Step 3: Update the tests**

In `tests/test_migrate_lock_schema.py`:

- Replace every `scripts/migrate_lock_to_v2.py` invocation with `scripts/migrate_lock_schema.py`.
- Add the `--family oco_first_touch_clean` argument to each subprocess call.
- Update `test_migration_produces_v2_lock` to assert `data["schema_version"] == 3` and `data["bundle"]["family"] == "oco_first_touch_clean"`.
- Rename the test function to `test_migration_produces_v3_lock`.
- Add a new test `test_migration_v2_to_v3_idempotent`: build a v2 fixture lock, run migration, assert `schema_version: 3`, run again, assert no change.

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_migrate_lock_schema.py -v`
Expected: PASS.

- [ ] **Step 5: Lint**

Run: `uv run ruff check scripts/migrate_lock_schema.py tests/test_migrate_lock_schema.py`
Expected: `All checks passed!`

- [ ] **Step 6: Commit**

```bash
git add scripts/migrate_lock_schema.py tests/test_migrate_lock_schema.py
git commit -m "feat(governance): migrate_lock_schema handles v1->v3 and v2->v3"
```

---

## Task 5: Update producers to emit v3 + family

**Files:**
- Modify: `scripts/freeze_oco_live_governance.py`
- Modify: `scripts/legacy/freeze_oco_historical_governance.py`

- [ ] **Step 1: Live freeze**

In `scripts/freeze_oco_live_governance.py`:

1. Add an argparse argument `--family` (default `"oco_first_touch_clean"`).
2. Replace any `BUNDLE_LAYOUT` import/reference with `bundle_layout_for(args.family)`.
3. In the manifest dict, set `"schema_version": 3` and `"bundle": {"month": ..., "dir_relpath": ..., "family": args.family}`.

- [ ] **Step 2: Historical freeze**

Same edits in `scripts/legacy/freeze_oco_historical_governance.py`.

- [ ] **Step 3: Update freeze tests**

If `tests/test_freeze_oco_live_governance.py` exists, update its assertions:
- `assert data["schema_version"] == 3`
- `assert data["bundle"]["family"] == "oco_first_touch_clean"`

Same for any `tests/legacy/test_freeze_oco_historical_governance*.py`.

- [ ] **Step 4: Run tests**

Run: `uv run pytest -q tests/ -k "freeze"`
Expected: PASS.

- [ ] **Step 5: Lint + commit**

```bash
uv run ruff check scripts/
git add scripts/freeze_oco_live_governance.py scripts/legacy/freeze_oco_historical_governance.py tests/
git commit -m "feat(governance): freeze scripts emit schema v3 with bundle.family"
```

---

## Task 6: validate_bundle enforces family

**Files:**
- Modify: `scripts/validate_bundle.py`
- Modify: `tests/test_validate_bundle.py`

- [ ] **Step 1: Add a failing test**

In `tests/test_validate_bundle.py`, add (and update existing fixture helper to emit v3):

```python
def test_fails_when_family_missing(tmp_path: Path) -> None:
    bundle = _make_valid_bundle(tmp_path)  # this helper now emits v3
    lock_path = next(bundle.glob("*_oco_live_lock.json"))
    data = json.loads(lock_path.read_text())
    data["bundle"].pop("family", None)
    lock_path.write_text(json.dumps(data))
    result = _run(bundle)
    assert result.returncode != 0
    assert "bundle.family" in result.stderr


def test_fails_when_family_unknown(tmp_path: Path) -> None:
    bundle = _make_valid_bundle(tmp_path)
    lock_path = next(bundle.glob("*_oco_live_lock.json"))
    data = json.loads(lock_path.read_text())
    data["bundle"]["family"] = "not_a_real_family"
    lock_path.write_text(json.dumps(data))
    result = _run(bundle)
    assert result.returncode != 0
    assert "unknown family" in result.stderr
```

- [ ] **Step 2: Run failing tests**

Run: `uv run pytest tests/test_validate_bundle.py -v`
Expected: FAIL (validator currently accepts v2 / missing family).

- [ ] **Step 3: Implement**

`validate_bundle.py` already calls `BundlePaths.from_lock` for every lock. Once `BundlePaths.from_lock` requires v3 + family (Task 3), `validate_bundle` inherits the check for free. The only change needed is updating the helper `_make_valid_bundle` in the test to emit v3 shape (mirror `_write_v3_bundle` from `test_bundle_paths.py`).

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_validate_bundle.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/validate_bundle.py tests/test_validate_bundle.py
git commit -m "test(governance): validate_bundle enforces family via BundlePaths"
```

---

## Task 7: Migrate existing on-disk bundles

**Files:**
- Modify: `configs/research/governance/oco_candidate_builds/2026-{02,03,04}/*.json`

- [ ] **Step 1: Migrate**

```bash
for month in 2026-02 2026-03 2026-04; do
  uv run python scripts/migrate_lock_schema.py \
    "configs/research/governance/oco_candidate_builds/${month}" \
    --family oco_first_touch_clean
done
```

Expected: each lock prints `[migrate-lock] migrated <path>`.

- [ ] **Step 2: Validate**

```bash
for month in 2026-02 2026-03 2026-04; do
  uv run python scripts/validate_bundle.py "configs/research/governance/oco_candidate_builds/${month}"
done
```

Expected: each prints `OK`.

- [ ] **Step 3: Spot-check shape**

```bash
uv run python -c "
import json
p = 'configs/research/governance/oco_candidate_builds/2026-04/eurusd_oco_live_lock.json'
d = json.load(open(p))
print('schema:', d['schema_version'])
print('family:', d['bundle']['family'])
"
```

Expected: `schema: 3`, `family: oco_first_touch_clean`.

- [ ] **Step 4: Commit**

```bash
git add configs/research/governance/oco_candidate_builds
git commit -m "chore(governance): migrate 2026-02/03/04 bundles to schema v3"
```

---

## Task 8: Non-OCO smoke test

**Files:**
- Modify: `tests/test_bundle_paths.py`

Proves the abstraction works for a non-OCO family without shipping a real new strategy.

- [ ] **Step 1: Add a fixture-scoped layout + round-trip test**

Append to `tests/test_bundle_paths.py`:

```python
def test_non_oco_family_round_trip(tmp_path: Path, monkeypatch) -> None:
    """A registered non-OCO family can be written, read, and validated."""
    from src.behemoth.core import bundle_paths as bp_module
    from src.behemoth.core.bundle_paths import (
        BUNDLE_LAYOUTS, BundleArtifactSpec, BundlePaths, _sha256_file,
    )

    test_layout = (
        BundleArtifactSpec("predictions",          "{symbol_lower}_breakout_predictions.parquet", True),
        BundleArtifactSpec("model_cbm",            "models/{symbol_upper}_model_{month}.cbm",     True),
        BundleArtifactSpec("model_threshold_json", "models/{symbol_upper}_model_{month}.json",    True),
        BundleArtifactSpec("allowed_states_csv",   "{symbol_lower}_breakout_states.csv",          True),
    )
    monkeypatch.setitem(BUNDLE_LAYOUTS, "test_breakout", test_layout)

    bundle_dir = tmp_path / "test_bundle"
    (bundle_dir / "models").mkdir(parents=True)
    pred = b"p"; cbm = b"c"; thr = b"t"; states = b"s"
    (bundle_dir / "eurusd_breakout_predictions.parquet").write_bytes(pred)
    (bundle_dir / "eurusd_breakout_states.csv").write_bytes(states)
    (bundle_dir / "models" / "EURUSD_model_2026-04.cbm").write_bytes(cbm)
    (bundle_dir / "models" / "EURUSD_model_2026-04.json").write_bytes(thr)

    lock = {
        "schema_version": 3,
        "symbol": "EURUSD",
        "bundle": {"month": "2026-04", "dir_relpath": str(bundle_dir), "family": "test_breakout"},
        "artifacts": {
            "predictions":          {"path": "eurusd_breakout_predictions.parquet", "sha256": _sha256(pred)},
            "allowed_states_csv":   {"path": "eurusd_breakout_states.csv",          "sha256": _sha256(states)},
            "model_cbm":            {"path": "models/EURUSD_model_2026-04.cbm",     "sha256": _sha256(cbm)},
            "model_threshold_json": {"path": "models/EURUSD_model_2026-04.json",    "sha256": _sha256(thr)},
        },
        "deployability": {"live_deployable": True, "model_month": "2026-04"},
    }
    lock_path = bundle_dir / "eurusd_breakout_live_lock.json"
    lock_path.write_text(json.dumps(lock))

    parsed = BundlePaths.from_lock(lock_path)
    assert parsed.family == "test_breakout"
    assert parsed.predictions().name == "eurusd_breakout_predictions.parquet"
    assert parsed.model_cbm().name == "EURUSD_model_2026-04.cbm"
```

- [ ] **Step 2: Run the test**

Run: `uv run pytest tests/test_bundle_paths.py::test_non_oco_family_round_trip -v`
Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add tests/test_bundle_paths.py
git commit -m "test(governance): round-trip non-OCO family through BundlePaths"
```

---

## Task 9: Final verification

- [ ] **Step 1: Full suite**

Run: `uv run pytest -q`
Expected: green.

- [ ] **Step 2: Lint**

Run: `uv run ruff check`
Expected: `All checks passed!`

- [ ] **Step 3: Every bundle validates**

```bash
for d in configs/research/governance/oco_candidate_builds/*-*/; do
  uv run python scripts/validate_bundle.py "$d"
done
```
Expected: every bundle prints `OK`.

- [ ] **Step 4: No stale BUNDLE_LAYOUT references**

```bash
grep -rn 'BUNDLE_LAYOUT[^S]' src/ scripts/ tests/ | grep -v __pycache__
```
Expected: no hits (the singular constant is gone; only `BUNDLE_LAYOUTS` and `bundle_layout_for` remain).

- [ ] **Step 5: Open the PR**

Use `superpowers:finishing-a-development-branch`. PR title: `feat(governance): multi-family bundle contract (schema v3)`. Body references ADR 0002.

---

## Notes for the Implementer

- **No fallbacks.** If a lock arrives without `bundle.family`, fail loud. The migration tool is the only path that handles missing-family input. Do not add reader-side defaults.
- **Family validity is enforced at parse time.** `BundlePaths.from_lock` calls `bundle_layout_for(family)` to confirm the family is known — this is intentional, so unknown families surface immediately at the resolver, not deep in a downstream consumer.
- **Filename templates within a layout can but need not mention the family.** OCO keeps `_oco_` in its filenames for backward continuity with on-disk artifacts (don't rename files that are already frozen). A new family is free to choose any naming.
