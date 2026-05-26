# Family-Agnostic Lock Globs Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Dependency:** This plan depends on `2026-05-26-bundle-family-parameterization.md` being merged first. It requires every lock to carry `bundle.family`.

**Goal:** Remove the implicit assumption that every governance lock is OCO. Change every `*_oco_live_lock.json` glob to `*_live_lock.json`, filter by `BundlePaths.from_lock(p).family` when family-specific behaviour is required, and centralise lock-filename construction in one helper. After this lands, registering a new family produces bundles that are discovered and processed automatically.

**Architecture:** Two helpers in `src/behemoth/core/bundle_paths.py`:

- `iter_locks(bundle_dir: Path, family: str | None = None) -> Iterator[Path]` — globs `*_live_lock.json` in a directory, optionally filtering by family. Skips invalid locks with a warning rather than raising (registry-style scanning).
- `lock_filename(symbol: str) -> str` — canonical lock filename, currently `f"{symbol.lower()}_oco_live_lock.json"` for OCO and parameterised once we have other families.

Every site that today opens `*_oco_live_lock.json` either calls `iter_locks` (when scanning) or `lock_filename` (when targeting a specific symbol). The OCO-baked filename `f"{symbol.lower()}_oco_live_lock.json"` stops appearing in any non-helper site.

**Tech Stack:** Python 3.12, `uv`, `pytest`, `ruff`. No new dependencies.

---

## Current State

The previous plan made `BundlePaths` family-agnostic on the *read* side. This plan extends that to the *discovery* and *filename construction* sides.

Inventory of glob sites (run `grep -rn '_oco_live_lock' src/ scripts/` to confirm before starting):

- `src/behemoth/core/registry.py:94` — `p_dir.glob("*_oco_live_lock.json")`
- `src/behemoth/core/historical_registry.py:45` — `p_dir.glob("*/*_oco_live_lock.json")`
- `src/behemoth/core/governance_validator.py:97` — `p_dir.glob("*/*_oco_live_lock.json")`
- `src/behemoth/live_restart/reconciliation.py:150` — `governance_dir.glob("*_oco_live_lock.json")`
- `scripts/run_jforex_live.py:213` — `governance_dir.glob("*_oco_live_lock.json")`
- `scripts/run_monthly_recert.py:75` — `root.glob("*_oco_live_lock.json")`
- `scripts/sync_candidate_model_artifacts.py:34, 37, 42` — multiple glob/suffix sites

Inventory of filename-construction sites:

- `src/behemoth/diagnostics/live_governance_deviation.py:287, 392, 457`
- `src/behemoth/parity/checks/risk_gov_live_deployable_lock_present.py:21`
- `src/behemoth/parity/loader.py:43`
- `scripts/run_monthly_recert.py:294`
- `scripts/validate_local_jforex_surrogate.py:82`
- `scripts/reconcile_jforex_outcomes.py:141`
- `scripts/diagnose_live_performance_gap.py:141, 267`
- `scripts/diagnose_jforex_coverage_gaps.py:75`
- `scripts/simulate_api_e2e_replay.py:47`

Total: roughly 7 glob sites + 12 filename sites + 3 `_oco_` filename templates in producers like `scripts/audit_oco_pipeline_logical_issues.py`.

---

## File Structure

**Modified files:**
- `src/behemoth/core/bundle_paths.py` — add `iter_locks()` and `lock_filename()` helpers.
- All 19+ sites listed in "Current State" — switch to the helpers.
- `tests/test_bundle_paths.py` — add helper tests.

---

## Task 1: `iter_locks` and `lock_filename` helpers — failing tests

**Files:**
- Test: `tests/test_bundle_paths.py`

- [ ] **Step 1: Add failing tests**

Append to `tests/test_bundle_paths.py`:

```python
def test_iter_locks_yields_all_live_locks(tmp_path: Path) -> None:
    from src.behemoth.core.bundle_paths import iter_locks

    bundle = tmp_path / "2026-04"
    bundle.mkdir()
    a = bundle / "eurusd_oco_live_lock.json"
    b = bundle / "gbpusd_oco_live_lock.json"
    a.write_text("{}")  # malformed but caught by parser, not glob
    b.write_text("{}")
    (bundle / "not_a_lock.json").write_text("{}")

    paths = sorted(iter_locks(bundle))
    assert paths == sorted([a, b])


def test_iter_locks_filters_by_family(tmp_path: Path) -> None:
    """Yield only locks whose bundle.family matches."""
    from src.behemoth.core.bundle_paths import iter_locks

    bundle = tmp_path / "2026-04"
    bundle.mkdir()
    # Two valid v3 locks with different families.
    oco_lock = _write_v3_bundle_at(bundle, symbol="EURUSD", family="oco_first_touch_clean")
    # Register a fake second family for the test.
    from src.behemoth.core.bundle_paths import BUNDLE_LAYOUTS, BundleArtifactSpec
    BUNDLE_LAYOUTS["test_breakout"] = (
        BundleArtifactSpec("predictions",          "gbpusd_breakout_predictions.parquet", True),
        BundleArtifactSpec("allowed_states_csv",   "gbpusd_breakout_states.csv",          True),
        BundleArtifactSpec("model_cbm",            "models/GBPUSD_model_2026-04.cbm",     True),
        BundleArtifactSpec("model_threshold_json", "models/GBPUSD_model_2026-04.json",    True),
    )
    try:
        breakout_lock = _write_v3_bundle_at(bundle, symbol="GBPUSD", family="test_breakout",
                                            artifact_basenames={"predictions": "gbpusd_breakout_predictions.parquet",
                                                                "allowed_states_csv": "gbpusd_breakout_states.csv"})

        assert sorted(iter_locks(bundle, family="oco_first_touch_clean")) == [oco_lock]
        assert sorted(iter_locks(bundle, family="test_breakout")) == [breakout_lock]
    finally:
        BUNDLE_LAYOUTS.pop("test_breakout", None)


def test_iter_locks_skips_invalid_locks_with_warning(tmp_path: Path, caplog) -> None:
    """A malformed lock does not break the scan."""
    from src.behemoth.core.bundle_paths import iter_locks

    bundle = tmp_path / "2026-04"
    bundle.mkdir()
    good = _write_v3_bundle_at(bundle, symbol="EURUSD", family="oco_first_touch_clean")
    bad = bundle / "broken_oco_live_lock.json"
    bad.write_text("{not json")

    # iter_locks unfiltered returns every match (no parse).
    assert good in iter_locks(bundle)
    assert bad in iter_locks(bundle)

    # iter_locks with family filter parses, and skips bad ones.
    with caplog.at_level("WARNING", logger="behemoth.governance"):
        filtered = list(iter_locks(bundle, family="oco_first_touch_clean"))
    assert good in filtered
    assert bad not in filtered
    assert any("failed to parse" in record.message for record in caplog.records)


def test_lock_filename_returns_canonical_form() -> None:
    from src.behemoth.core.bundle_paths import lock_filename

    assert lock_filename("EURUSD") == "eurusd_oco_live_lock.json"
    assert lock_filename("eurusd") == "eurusd_oco_live_lock.json"
```

You will also need a fixture helper `_write_v3_bundle_at(bundle_dir, symbol, family, artifact_basenames=None)` that builds a v3 lock at the *given* bundle dir (the existing `_write_v3_bundle` creates its own subdir). Add it to the same test file.

- [ ] **Step 2: Run failing tests**

Run: `uv run pytest tests/test_bundle_paths.py -v`
Expected: FAIL on the four new tests because `iter_locks` and `lock_filename` don't exist.

---

## Task 2: `iter_locks` and `lock_filename` — implementation

**Files:**
- Modify: `src/behemoth/core/bundle_paths.py`

- [ ] **Step 1: Add the helpers**

```python
# At the bottom of src/behemoth/core/bundle_paths.py, before the trailing newline:

import logging
from collections.abc import Iterator

_LOG = logging.getLogger("behemoth.governance")


def lock_filename(symbol: str) -> str:
    """Canonical lock filename for a symbol. Currently OCO-shaped; new families
    must either reuse this name or update this helper to dispatch on family."""
    return f"{symbol.lower()}_oco_live_lock.json"


def iter_locks(bundle_dir: Path, family: str | None = None) -> Iterator[Path]:
    """Yield every *_live_lock.json in bundle_dir, optionally filtering by family.

    Unfiltered: returns every glob match without parsing.
    Filtered:   parses each and yields only those whose bundle.family matches.
                Malformed locks are skipped with a warning.
    """
    matches = sorted(Path(bundle_dir).glob("*_live_lock.json"))
    if family is None:
        yield from matches
        return
    for lock_path in matches:
        try:
            bp = BundlePaths.from_lock(lock_path)
        except BundleIntegrityError as exc:
            _LOG.warning("failed to parse %s: %s", lock_path, exc)
            continue
        if bp.family == family:
            yield lock_path
```

Note: the glob changes from `*_oco_live_lock.json` to `*_live_lock.json`. Any future lock that uses a different suffix beyond `_live_lock.json` would not be picked up — that's intentional. `_live_lock.json` is the contract.

- [ ] **Step 2: Run tests**

Run: `uv run pytest tests/test_bundle_paths.py -v`
Expected: PASS.

- [ ] **Step 3: Lint**

Run: `uv run ruff check src/behemoth/core/bundle_paths.py tests/test_bundle_paths.py`
Expected: clean.

- [ ] **Step 4: Commit**

```bash
git add src/behemoth/core/bundle_paths.py tests/test_bundle_paths.py
git commit -m "feat(governance): add iter_locks/lock_filename helpers"
```

---

## Task 3: Switch scanning sites to `iter_locks`

**Files:**
- Modify: `src/behemoth/core/registry.py`
- Modify: `src/behemoth/core/historical_registry.py`
- Modify: `src/behemoth/core/governance_validator.py`
- Modify: `src/behemoth/live_restart/reconciliation.py`
- Modify: `scripts/run_jforex_live.py`
- Modify: `scripts/run_monthly_recert.py`
- Modify: `scripts/sync_candidate_model_artifacts.py`

These all do `dir.glob("*_oco_live_lock.json")`.

- [ ] **Step 1: For each file, replace the glob**

Pattern:

```python
# BEFORE
for lock_path in sorted(bundle_dir.glob("*_oco_live_lock.json")):
    ...

# AFTER
from src.behemoth.core.bundle_paths import iter_locks
for lock_path in iter_locks(bundle_dir):
    ...
```

For registries that today only handle OCO bundles, pass `family="oco_first_touch_clean"` to keep behaviour identical until those registries grow multi-family support. Document the filter with a brief comment: `# Filtered to OCO until {registry name} supports multi-family lookup`.

For `sync_candidate_model_artifacts.py`, the three sites are:
- `lock_dir.glob("*_oco_live_lock.json")` (line 34) → `iter_locks(lock_dir)` (no filter; sync handles whichever family is present).
- `lock_dir.glob("*_oco_live_lock.json")` filter loop (line 37) → use `iter_locks(lock_dir)` and filter membership in `wanted_names`.
- `suffix = "_oco_live_lock.json"` (line 42) → `from src.behemoth.core.bundle_paths import lock_filename; suffix = lock_filename("X")[len("x"):]` is awkward — simpler: delete the suffix variable, use `lock_filename(sym)` directly where the suffix was used.

- [ ] **Step 2: Run targeted tests**

```bash
uv run pytest -q tests/test_registry.py tests/test_historical_registry.py tests/test_governance_validator.py tests/test_run_jforex_live.py tests/test_run_monthly_recert.py tests/test_sync_candidate_model_artifacts.py
```
Expected: PASS.

- [ ] **Step 3: Lint + commit**

```bash
uv run ruff check src scripts
git add src/behemoth/core/registry.py src/behemoth/core/historical_registry.py \
        src/behemoth/core/governance_validator.py src/behemoth/live_restart/reconciliation.py \
        scripts/run_jforex_live.py scripts/run_monthly_recert.py scripts/sync_candidate_model_artifacts.py
git commit -m "refactor(governance): scan locks via iter_locks (family-agnostic)"
```

---

## Task 4: Switch filename-construction sites to `lock_filename`

**Files:**
- Modify: `src/behemoth/diagnostics/live_governance_deviation.py`
- Modify: `src/behemoth/parity/checks/risk_gov_live_deployable_lock_present.py`
- Modify: `src/behemoth/parity/loader.py`
- Modify: `scripts/run_monthly_recert.py`
- Modify: `scripts/validate_local_jforex_surrogate.py`
- Modify: `scripts/reconcile_jforex_outcomes.py`
- Modify: `scripts/diagnose_live_performance_gap.py`
- Modify: `scripts/diagnose_jforex_coverage_gaps.py`
- Modify: `scripts/simulate_api_e2e_replay.py`

These all do `f"{symbol.lower()}_oco_live_lock.json"` inline.

- [ ] **Step 1: For each file, replace the inline f-string**

Pattern:

```python
# BEFORE
lock_path = governance_dir / f"{symbol.lower()}_oco_live_lock.json"

# AFTER
from src.behemoth.core.bundle_paths import lock_filename
lock_path = governance_dir / lock_filename(symbol)
```

Apply once per occurrence. Do not introduce a local helper; use the canonical one.

- [ ] **Step 2: Verify no inline `_oco_live_lock.json` strings remain outside `bundle_paths.py`**

```bash
grep -rn '"_oco_live_lock.json"\|f"{[^}]*}_oco_live_lock.json"' src/ scripts/ | grep -v src/behemoth/core/bundle_paths.py | grep -v __pycache__ | grep -v scripts/legacy
```
Expected: no hits.

- [ ] **Step 3: Run tests**

Run: `uv run pytest -q`
Expected: PASS, 1264+ tests.

- [ ] **Step 4: Lint**

Run: `uv run ruff check src scripts`
Expected: clean.

- [ ] **Step 5: Commit**

```bash
git add src scripts
git commit -m "refactor(governance): construct lock filenames via lock_filename helper"
```

---

## Task 5: Filename templates inside producers and audits

**Files:**
- Modify: `scripts/audit_oco_pipeline_logical_issues.py`
- Modify: `scripts/run_local_jforex_surrogate_matrix.py`
- Modify: `scripts/run_jforex_dukascopy_matrix.py`
- Modify: `scripts/build_oco_strategy_bible.py`
- Modify: `scripts/diagnose_jforex_coverage_gaps.py`

These contain inline templates like `f"{s}_oco_monthly_predictions.parquet"`, `f"{s}_oco_reduced_summary.csv"`, `f"{symbol.lower()}_oco_locked_predictions.parquet"`.

These are *outputs of the mining pipeline*, not bundle artifacts. They still produce OCO-shaped files because OCO is what the pipeline mines. But the OCO baking should be in one constant per producer, not inline at every use.

- [ ] **Step 1: Per file, lift the family-specific suffix to a module constant**

```python
# Top of file
_MINING_FAMILY = "oco"  # mining outcome family this script handles
_PREDICTIONS_SUFFIX = f"_{_MINING_FAMILY}_monthly_predictions.parquet"
_REDUCED_SUMMARY_SUFFIX = f"_{_MINING_FAMILY}_reduced_summary.csv"
```

Then replace inline `_oco_monthly_predictions.parquet` with the constant. The goal is that introducing a new mining family means one constant per producer instead of N inline occurrences. Skip files that have only one occurrence — the lift is not worth it.

- [ ] **Step 2: Run targeted tests**

Run: `uv run pytest -q tests/ -k "oco_pipeline or jforex_surrogate or strategy_bible or coverage_gaps"`
Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add scripts
git commit -m "refactor(governance): lift mining-family suffixes to module constants"
```

---

## Task 6: Final verification

- [ ] **Step 1: Full suite**

Run: `uv run pytest -q`
Expected: green.

- [ ] **Step 2: Lint**

Run: `uv run ruff check`
Expected: clean.

- [ ] **Step 3: No stale `_oco_live_lock` filename construction outside `bundle_paths.py`**

```bash
grep -rn '_oco_live_lock.json' src/ scripts/ tests/ \
  | grep -v __pycache__ \
  | grep -v src/behemoth/core/bundle_paths.py \
  | grep -v scripts/legacy \
  | grep -v scripts/migrate_lock_schema.py
```

Expected: hits only inside test fixtures that intentionally build lock files (those construct full filenames; the canonical helper is for production code).

- [ ] **Step 4: Bundle scan with the new globs still finds every existing lock**

```bash
uv run python -c "
from pathlib import Path
from src.behemoth.core.bundle_paths import iter_locks
total = sum(1 for _ in iter_locks(Path('configs/research/governance/oco_candidate_builds/2026-04')))
print(f'locks discovered: {total}')
"
```
Expected: `locks discovered: 6` (one per symbol).

- [ ] **Step 5: Open the PR**

PR title: `refactor(governance): family-agnostic lock globs and filenames`. Reference ADR 0002.

---

## Notes for the Implementer

- **`iter_locks(dir)` (no filter) returns matches without parsing.** Used when the caller wants to handle any-family bundles uniformly (e.g. validate, sync). `iter_locks(dir, family=...)` parses each; use it only when you genuinely need to filter — parsing is the expensive part.
- **`lock_filename(symbol)` is currently OCO-shaped.** When a real second family arrives, decide whether to parameterise it on family (changing the suffix) or keep `_oco_` as the conventional suffix for all locks. That decision lives in a follow-up ADR, not in this PR.
- **Do not propagate family discrimination beyond the resolver.** Consumers that today only handle OCO can pass `family="oco_first_touch_clean"` and that's sufficient. Adding multi-family logic to every registry is a separate, larger change.
