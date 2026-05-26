# Deterministic Month Bundles Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make every month build bundle (`configs/research/governance/oco_candidate_builds/<YYYY-MM>/`) self-contained and deterministic so governance certification reads only bundle-relative, hash-verified paths from the lock, with zero fallback to mutable mining outputs or absolute machine-specific paths.

**Architecture:** Introduce a versioned lock schema (`schema_version: 2`) where every `*_path` in `artifacts` is **bundle-relative** and the file is physically inside the bundle. Origin metadata for files that started life elsewhere (e.g. WFO mining outputs) is preserved in a new `provenance` block — as hash + origin path strings, not load paths. A single resolver module `src/behemoth/core/bundle_paths.py` is the only place that turns lock keys into filesystem paths; all producers and consumers go through it. A one-shot migration script converts existing v1 locks to v2 and copies referenced external artifacts into the bundle. Stage 12/13, `run_monthly_recert`, `freeze_oco_live_governance`, the legacy historical freeze, and all `*lock loader` consumers are switched over in one PR so no fallback code remains. Bundle integrity is enforced by `scripts/validate_bundle.py` invoked from CI.

**Tech Stack:** Python 3.12, `uv`, `pytest`, `ruff`. No new third-party dependencies. `pathlib.Path`, `json`, `hashlib`.

---

## Current State (read this first)

The current lock (`configs/research/governance/oco_candidate_builds/2026-04/eurusd_oco_live_lock.json`) mixes:

- **Absolute machine paths:** `model_cbm_path` is `/Users/danielfisher/repositories/behemoth/configs/...` — written by `scripts/run_monthly_build.py::_materialize_bundle_models`.
- **Bundle-relative paths:** `predictions_path`, `reduced_states_csv_path` — repo-relative pointers into the bundle dir.
- **Mutable repo paths:** `source_predictions_path`, `reduced_summary_path`, `tick_exact_summary_path` point into `data/analysis/tick_opportunity_mining_dukascopy_candidate/...` which `make retrain-all` regenerates.
- **External-to-bundle paths:** `train_predictions_path` lives in `models/oco_dukascopy_candidate/`.

Producers:
- `scripts/freeze_oco_live_governance.py::_build_manifest` (lines 272–325) writes the live lock with `str(paths[...])` (repo-relative-ish strings).
- `scripts/legacy/freeze_oco_historical_governance.py` (lines 477, 485) writes `source_predictions_path` + `train_predictions_path`.
- `scripts/run_monthly_build.py::_materialize_bundle_models` (lines 47–86) copies model files into `<bundle>/models/oco_dukascopy_candidate/` and then **rewrites the lock paths to absolute strings** — this is the source of machine-specific paths.

Consumers that currently read these path keys (must all migrate):
- `scripts/run_stage12_stage13_certification.py` (PR #238 added a "prefer bundle, fall back to mining" branch — to be deleted)
- `scripts/run_monthly_recert.py` (PR #238 added existence checks — to be replaced with resolver call)
- `scripts/validate_oco_live_governance.py`
- `scripts/run_promote_live.py`
- `scripts/run_jforex_live.py`
- `scripts/audit_oco_leakage_label_integrity.py`
- `scripts/run_offset_tickbar_frozen_screen.py`
- `scripts/seed_rolling_threshold.py`
- `scripts/simulate_api_e2e_replay.py`
- `scripts/sync_candidate_model_artifacts.py`
- `scripts/reconcile_historical_prediction_artifacts.py`
- `src/behemoth/api/server.py`
- `src/behemoth/core/governance_lock_loader.py`
- `src/behemoth/core/governance_validator.py`
- `src/behemoth/core/historical_prediction_stage.py`
- `src/behemoth/core/historical_registry.py`
- `src/behemoth/core/model_registry.py`
- `src/behemoth/core/registry.py`

---

## Target Lock Shape (schema_version: 2)

A v2 lock for `EURUSD 2026-04` will look like:

```json
{
  "schema_version": 2,
  "symbol": "EURUSD",
  "frozen_at_utc": "2026-05-01T16:08:12.216116+00:00",
  "git": { "branch": "main", "commit": "34cc29e...", "dirty": true },
  "bundle": {
    "month": "2026-04",
    "dir_relpath": "configs/research/governance/oco_candidate_builds/2026-04"
  },
  "artifacts": {
    "predictions":            { "path": "eurusd_oco_locked_predictions.parquet", "sha256": "764c..." },
    "allowed_states_csv":     { "path": "eurusd_oco_allowed_states.csv",         "sha256": "5853..." },
    "model_cbm":              { "path": "models/EURUSD_model_2026-04.cbm",       "sha256": "700f..." },
    "model_threshold_json":   { "path": "models/EURUSD_model_2026-04.json",      "sha256": "1f2b..." },
    "wfo_config":             { "path": "configs/eurusd_wfo.yaml",               "sha256": "f761..." },
    "reduced_config":         { "path": "configs/eurusd_reduced.yaml",           "sha256": "eb4d..." },
    "reduced_summary":        { "path": "eurusd_oco_reduced_summary.csv",        "sha256": "6143..." },
    "tick_exact_summary":     { "path": "eurusd_oco_tick_exact_summary.csv",     "sha256": "5920..." }
  },
  "provenance": {
    "predictions":     { "origin": "data/analysis/tick_opportunity_mining_dukascopy_candidate/wfo_m3to1_oco_fullcap/EURUSD_oco_monthly_predictions.parquet", "origin_sha256": "909d..." },
    "model_cbm":       { "origin": "models/oco/EURUSD_model_2026-04.cbm",      "origin_sha256": "700f..." },
    "reduced_summary": { "origin": "data/analysis/.../reduced_core_rolling/EURUSD_oco_reduced_summary.csv", "origin_sha256": "6143..." }
  },
  "deployability": {
    "live_deployable":           true,
    "tick_exact_overall_pass":   true,
    "capacity_overall_pass":     true,
    "model_month":               "2026-04",
    "model_valid_through":       "2026-04-30"
  },
  "locked_runtime": { /* unchanged from v1 */ },
  "retrain_policy": { /* unchanged from v1 */ },
  "state_universe": { /* unchanged from v1 */ },
  "historical_backtest": { /* unchanged from v1 */ }
}
```

**Rules enforced by validator:**
1. Every `artifacts.<key>.path` is a **bundle-relative** path (no leading `/`, no `..`).
2. Every `artifacts.<key>.path` resolves (under `bundle.dir_relpath`) to an existing file whose sha256 matches `artifacts.<key>.sha256`.
3. `provenance.*` entries are metadata only — never opened at certification or runtime.
4. No top-level keys ending in `_path` (legacy shape removed).
5. Bundle dir physically contains: `<symbol>_oco_locked_predictions.parquet`, `<symbol>_oco_allowed_states.csv`, `<symbol>_oco_reduced_summary.csv`, `<symbol>_oco_tick_exact_summary.csv`, `<symbol>_oco_live_lock.json`, `configs/<symbol>_wfo.yaml`, `configs/<symbol>_reduced.yaml`, `models/<symbol>_model_<YYYY-MM>.cbm`, `models/<symbol>_model_<YYYY-MM>.json`.

---

## File Structure

**New files:**
- `docs/adr/0001-deterministic-month-bundles.md` — architectural decision record.
- `src/behemoth/core/bundle_paths.py` — single resolver: `BundlePaths.from_lock(lock_path) -> BundlePaths`, with typed accessors (`.predictions()`, `.allowed_states_csv()`, `.model_cbm()`, …) that each verify sha256 on first read.
- `tests/test_bundle_paths.py`
- `scripts/validate_bundle.py` — CLI: `validate_bundle.py <bundle_dir>` returns non-zero on any rule violation.
- `tests/test_validate_bundle.py`
- `scripts/migrate_lock_to_v2.py` — CLI: `migrate_lock_to_v2.py <bundle_dir>` rewrites every `*_oco_live_lock.json` in place, copies any externally-referenced artifact into the bundle, and records origin in `provenance`.
- `tests/test_migrate_lock_to_v2.py`

**Modified files:**
- `scripts/freeze_oco_live_governance.py` — write v2 directly.
- `scripts/legacy/freeze_oco_historical_governance.py` — write v2 directly.
- `scripts/run_monthly_build.py::_materialize_bundle_models` — replace path-rewrite logic with a single `validate_bundle` call.
- `scripts/run_stage12_stage13_certification.py` — replace lock-key lookups with `BundlePaths` resolver; delete PR #238 fallback branch.
- `scripts/run_monthly_recert.py` — replace existence checks with `validate_bundle` call.
- `scripts/validate_oco_live_governance.py` — read v2 shape.
- `scripts/run_promote_live.py`, `scripts/run_jforex_live.py`, `scripts/audit_oco_leakage_label_integrity.py`, `scripts/run_offset_tickbar_frozen_screen.py`, `scripts/seed_rolling_threshold.py`, `scripts/simulate_api_e2e_replay.py`, `scripts/sync_candidate_model_artifacts.py`, `scripts/reconcile_historical_prediction_artifacts.py` — switch to `BundlePaths`.
- `src/behemoth/core/governance_lock_loader.py`, `governance_validator.py`, `historical_prediction_stage.py`, `historical_registry.py`, `model_registry.py`, `registry.py`, `src/behemoth/api/server.py` — read via `BundlePaths`.
- `.github/workflows/ci.yml` (or equivalent) — add `validate_bundle` step over all bundles.
- `CLAUDE.md`, `AGENTS.md`, `CONTEXT.md` — pointer to ADR 0001.

**Bundle data changes (applied by migration):**
- `configs/research/governance/oco_candidate_builds/2026-02/`, `2026-03/`, `2026-04/` — locks rewritten to v2; missing artifacts copied in; `models/` subdir reorganized to `<bundle>/models/<symbol>_model_<MONTH>.{cbm,json}` (drop the redundant `oco_dukascopy_candidate/` nesting); WFO + reduced config YAMLs copied into `<bundle>/configs/`.

---

## Task 1: Add ADR for deterministic bundles

**Files:**
- Create: `docs/adr/0001-deterministic-month-bundles.md`

- [ ] **Step 1: Create the ADR directory and file**

```bash
mkdir -p docs/adr
```

Write `docs/adr/0001-deterministic-month-bundles.md` with this exact content:

````markdown
# ADR 0001: Deterministic Month Bundles

- Status: Accepted
- Date: 2026-05-25

## Context

Month build bundles under `configs/research/governance/oco_candidate_builds/<YYYY-MM>/` historically mixed three different path conventions in a single `*_oco_live_lock.json`:

1. Absolute machine-specific paths (e.g. `/Users/<name>/repositories/behemoth/...`), inserted by `run_monthly_build.py::_materialize_bundle_models`.
2. Bundle-relative paths to frozen artifacts (`predictions_path`, `reduced_states_csv_path`).
3. Repo-relative paths to mutable mining outputs under `data/analysis/tick_opportunity_mining_dukascopy_candidate/` and `models/oco_dukascopy_candidate/`.

Stage 12 and `run_monthly_recert` evolved fallback branches that would prefer the bundle copy and fall back to the mining output. The fallback masked the fact that a "frozen" lock was not actually frozen, and led to PR #238 hardening existence checks instead of fixing the contract.

## Decision

1. Every `*_oco_live_lock.json` conforms to `schema_version: 2`.
2. In v2 every `artifacts.<key>.path` is **bundle-relative** (relative to the directory containing the lock).
3. Every referenced artifact physically lives inside the bundle directory; bundles are self-contained.
4. The lock stores **only** the load path in `artifacts.*`; the original source location is preserved as metadata in a separate `provenance.*` block and is never opened by certification or runtime code.
5. All path resolution goes through `src/behemoth/core/bundle_paths.py::BundlePaths`. No script may concatenate a lock string with a repo root.
6. `scripts/validate_bundle.py` is the single source of truth for bundle integrity and runs in CI on every bundle.
7. There is no fallback to mining outputs at certification time. Missing artifacts fail loudly with `incomplete bundle` errors.

## Consequences

- One-shot migration is required for existing bundles (2026-02, 2026-03, 2026-04).
- The legacy `source_predictions_path` and `train_predictions_path` keys are removed; their values are preserved under `provenance.predictions.origin` and `provenance.train_predictions.origin`.
- The PR #238 fallback in `run_stage12_stage13_certification.py` and the existence checks in `run_monthly_recert.py` are deleted in the same change that introduces v2.
- Bundles become byte-stable and portable: any developer can reproduce certification from a bundle alone.
````

- [ ] **Step 2: Commit**

```bash
git add docs/adr/0001-deterministic-month-bundles.md
git commit -m "docs(adr): add 0001 deterministic month bundles"
```

---

## Task 2: BundlePaths resolver — failing test

**Files:**
- Test: `tests/test_bundle_paths.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_bundle_paths.py
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from src.behemoth.core.bundle_paths import BundlePaths, BundleIntegrityError


def _sha256(payload: bytes) -> str:
    h = hashlib.sha256()
    h.update(payload)
    return h.hexdigest()


def _write_v2_bundle(tmp_path: Path, symbol: str = "EURUSD") -> Path:
    bundle_dir = tmp_path / "configs/research/governance/oco_candidate_builds/2026-04"
    (bundle_dir / "models").mkdir(parents=True)
    (bundle_dir / "configs").mkdir(parents=True)

    pred_bytes = b"prediction-bytes"
    states_bytes = b"states-bytes"
    cbm_bytes = b"cbm-bytes"
    thr_bytes = b"thr-bytes"

    (bundle_dir / f"{symbol.lower()}_oco_locked_predictions.parquet").write_bytes(pred_bytes)
    (bundle_dir / f"{symbol.lower()}_oco_allowed_states.csv").write_bytes(states_bytes)
    (bundle_dir / "models" / f"{symbol}_model_2026-04.cbm").write_bytes(cbm_bytes)
    (bundle_dir / "models" / f"{symbol}_model_2026-04.json").write_bytes(thr_bytes)

    lock = {
        "schema_version": 2,
        "symbol": symbol,
        "bundle": {"month": "2026-04", "dir_relpath": str(bundle_dir)},
        "artifacts": {
            "predictions": {
                "path": f"{symbol.lower()}_oco_locked_predictions.parquet",
                "sha256": _sha256(pred_bytes),
            },
            "allowed_states_csv": {
                "path": f"{symbol.lower()}_oco_allowed_states.csv",
                "sha256": _sha256(states_bytes),
            },
            "model_cbm": {
                "path": f"models/{symbol}_model_2026-04.cbm",
                "sha256": _sha256(cbm_bytes),
            },
            "model_threshold_json": {
                "path": f"models/{symbol}_model_2026-04.json",
                "sha256": _sha256(thr_bytes),
            },
        },
        "deployability": {"live_deployable": True, "model_month": "2026-04"},
    }
    lock_path = bundle_dir / f"{symbol.lower()}_oco_live_lock.json"
    lock_path.write_text(json.dumps(lock, indent=2))
    return lock_path


def test_from_lock_resolves_predictions(tmp_path: Path) -> None:
    lock_path = _write_v2_bundle(tmp_path)

    bp = BundlePaths.from_lock(lock_path)

    expected = lock_path.parent / "eurusd_oco_locked_predictions.parquet"
    assert bp.predictions() == expected
    assert bp.allowed_states_csv() == lock_path.parent / "eurusd_oco_allowed_states.csv"
    assert bp.model_cbm() == lock_path.parent / "models" / "EURUSD_model_2026-04.cbm"
    assert bp.model_threshold_json() == lock_path.parent / "models" / "EURUSD_model_2026-04.json"


def test_rejects_absolute_path_in_artifact(tmp_path: Path) -> None:
    lock_path = _write_v2_bundle(tmp_path)
    data = json.loads(lock_path.read_text())
    data["artifacts"]["predictions"]["path"] = str(lock_path.parent / "x.parquet")
    lock_path.write_text(json.dumps(data))

    with pytest.raises(BundleIntegrityError, match="must be bundle-relative"):
        BundlePaths.from_lock(lock_path)


def test_rejects_parent_escape(tmp_path: Path) -> None:
    lock_path = _write_v2_bundle(tmp_path)
    data = json.loads(lock_path.read_text())
    data["artifacts"]["predictions"]["path"] = "../escape.parquet"
    lock_path.write_text(json.dumps(data))

    with pytest.raises(BundleIntegrityError, match="must be bundle-relative"):
        BundlePaths.from_lock(lock_path)


def test_rejects_schema_v1(tmp_path: Path) -> None:
    lock_path = _write_v2_bundle(tmp_path)
    data = json.loads(lock_path.read_text())
    data["schema_version"] = 1
    lock_path.write_text(json.dumps(data))

    with pytest.raises(BundleIntegrityError, match="schema_version=2"):
        BundlePaths.from_lock(lock_path)


def test_predictions_call_verifies_sha(tmp_path: Path) -> None:
    lock_path = _write_v2_bundle(tmp_path)
    bp = BundlePaths.from_lock(lock_path)
    # Corrupt the on-disk file after construction.
    (lock_path.parent / "eurusd_oco_locked_predictions.parquet").write_bytes(b"corrupted")
    with pytest.raises(BundleIntegrityError, match="sha256 mismatch"):
        bp.predictions()


def test_missing_file_raises(tmp_path: Path) -> None:
    lock_path = _write_v2_bundle(tmp_path)
    (lock_path.parent / "eurusd_oco_locked_predictions.parquet").unlink()
    bp = BundlePaths.from_lock(lock_path)
    with pytest.raises(BundleIntegrityError, match="missing artifact"):
        bp.predictions()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_bundle_paths.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.behemoth.core.bundle_paths'`.

---

## Task 3: BundlePaths resolver — implementation

**Files:**
- Create: `src/behemoth/core/bundle_paths.py`

- [ ] **Step 1: Write the resolver**

```python
# src/behemoth/core/bundle_paths.py
"""Bundle-relative path resolver for schema_version=2 month bundles.

Single source of truth for turning lock keys into filesystem paths. Every
producer and consumer goes through here so the lock file's contract is
enforced in exactly one place.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class BundleIntegrityError(RuntimeError):
    pass


@dataclass(frozen=True)
class _Artifact:
    relpath: str
    sha256: str


@dataclass(frozen=True)
class BundlePaths:
    lock_path: Path
    bundle_dir: Path
    symbol: str
    model_month: str
    _artifacts: dict[str, _Artifact]
    _deployability: dict[str, Any]

    @classmethod
    def from_lock(cls, lock_path: Path) -> "BundlePaths":
        lock_path = Path(lock_path)
        data = json.loads(lock_path.read_text(encoding="utf-8"))
        if int(data.get("schema_version", 0)) != 2:
            raise BundleIntegrityError(
                f"{lock_path}: requires schema_version=2 (got {data.get('schema_version')!r})"
            )
        bundle_dir = lock_path.parent.resolve()
        artifacts_block = data.get("artifacts", {})
        if not isinstance(artifacts_block, dict) or not artifacts_block:
            raise BundleIntegrityError(f"{lock_path}: empty artifacts block")
        artifacts: dict[str, _Artifact] = {}
        for key, entry in artifacts_block.items():
            if not isinstance(entry, dict):
                raise BundleIntegrityError(f"{lock_path}: artifacts.{key} not an object")
            rel = str(entry.get("path", "")).strip()
            sha = str(entry.get("sha256", "")).strip()
            if not rel or not sha:
                raise BundleIntegrityError(f"{lock_path}: artifacts.{key} missing path/sha256")
            if rel.startswith("/") or rel.startswith("\\") or ".." in Path(rel).parts:
                raise BundleIntegrityError(
                    f"{lock_path}: artifacts.{key}.path must be bundle-relative: {rel!r}"
                )
            artifacts[key] = _Artifact(relpath=rel, sha256=sha)
        deploy = data.get("deployability", {}) or {}
        return cls(
            lock_path=lock_path,
            bundle_dir=bundle_dir,
            symbol=str(data.get("symbol", "")).upper().strip(),
            model_month=str(deploy.get("model_month", "")).strip(),
            _artifacts=artifacts,
            _deployability=dict(deploy),
        )

    def _resolve(self, key: str) -> Path:
        if key not in self._artifacts:
            raise BundleIntegrityError(
                f"{self.lock_path}: required artifact key {key!r} missing"
            )
        art = self._artifacts[key]
        candidate = (self.bundle_dir / art.relpath).resolve()
        try:
            candidate.relative_to(self.bundle_dir)
        except ValueError as exc:
            raise BundleIntegrityError(
                f"{self.lock_path}: artifacts.{key} escapes bundle dir"
            ) from exc
        if not candidate.is_file():
            raise BundleIntegrityError(
                f"{self.lock_path}: missing artifact for {key}: {candidate}"
            )
        actual = _sha256_file(candidate)
        if actual != art.sha256:
            raise BundleIntegrityError(
                f"{self.lock_path}: sha256 mismatch for {key} "
                f"(expected {art.sha256}, got {actual})"
            )
        return candidate

    def predictions(self) -> Path:
        return self._resolve("predictions")

    def allowed_states_csv(self) -> Path:
        return self._resolve("allowed_states_csv")

    def model_cbm(self) -> Path:
        return self._resolve("model_cbm")

    def model_threshold_json(self) -> Path:
        return self._resolve("model_threshold_json")

    def wfo_config(self) -> Path:
        return self._resolve("wfo_config")

    def reduced_config(self) -> Path:
        return self._resolve("reduced_config")

    def reduced_summary(self) -> Path:
        return self._resolve("reduced_summary")

    def tick_exact_summary(self) -> Path:
        return self._resolve("tick_exact_summary")

    @property
    def live_deployable(self) -> bool:
        return bool(self._deployability.get("live_deployable", False))


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()
```

- [ ] **Step 2: Run tests to verify they pass**

Run: `uv run pytest tests/test_bundle_paths.py -v`
Expected: PASS — 6 passed.

- [ ] **Step 3: Lint**

Run: `uv run ruff check src/behemoth/core/bundle_paths.py tests/test_bundle_paths.py`
Expected: `All checks passed!`

- [ ] **Step 4: Commit**

```bash
git add src/behemoth/core/bundle_paths.py tests/test_bundle_paths.py
git commit -m "feat(governance): add BundlePaths resolver for schema v2 locks"
```

---

## Task 4: validate_bundle.py — failing test

**Files:**
- Test: `tests/test_validate_bundle.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_validate_bundle.py
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path


def _sha256(b: bytes) -> str:
    h = hashlib.sha256(); h.update(b); return h.hexdigest()


def _make_valid_bundle(tmp_path: Path) -> Path:
    bundle = tmp_path / "2026-04"
    (bundle / "models").mkdir(parents=True)
    pred = b"p"; states = b"s"; cbm = b"c"; thr = b"t"
    (bundle / "eurusd_oco_locked_predictions.parquet").write_bytes(pred)
    (bundle / "eurusd_oco_allowed_states.csv").write_bytes(states)
    (bundle / "models" / "EURUSD_model_2026-04.cbm").write_bytes(cbm)
    (bundle / "models" / "EURUSD_model_2026-04.json").write_bytes(thr)
    lock = {
        "schema_version": 2,
        "symbol": "EURUSD",
        "bundle": {"month": "2026-04", "dir_relpath": str(bundle)},
        "artifacts": {
            "predictions":          {"path": "eurusd_oco_locked_predictions.parquet", "sha256": _sha256(pred)},
            "allowed_states_csv":   {"path": "eurusd_oco_allowed_states.csv",         "sha256": _sha256(states)},
            "model_cbm":            {"path": "models/EURUSD_model_2026-04.cbm",       "sha256": _sha256(cbm)},
            "model_threshold_json": {"path": "models/EURUSD_model_2026-04.json",      "sha256": _sha256(thr)},
        },
        "deployability": {"live_deployable": True, "model_month": "2026-04"},
    }
    (bundle / "eurusd_oco_live_lock.json").write_text(json.dumps(lock, indent=2))
    return bundle


def _run(bundle: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "scripts/validate_bundle.py", str(bundle)],
        capture_output=True, text=True,
    )


def test_passes_for_valid_bundle(tmp_path: Path) -> None:
    bundle = _make_valid_bundle(tmp_path)
    result = _run(bundle)
    assert result.returncode == 0, result.stderr


def test_fails_when_artifact_missing(tmp_path: Path) -> None:
    bundle = _make_valid_bundle(tmp_path)
    (bundle / "eurusd_oco_locked_predictions.parquet").unlink()
    result = _run(bundle)
    assert result.returncode != 0
    assert "missing artifact" in result.stderr


def test_fails_when_sha_drifts(tmp_path: Path) -> None:
    bundle = _make_valid_bundle(tmp_path)
    (bundle / "eurusd_oco_allowed_states.csv").write_bytes(b"drift")
    result = _run(bundle)
    assert result.returncode != 0
    assert "sha256 mismatch" in result.stderr


def test_fails_for_v1_lock(tmp_path: Path) -> None:
    bundle = _make_valid_bundle(tmp_path)
    lock_path = bundle / "eurusd_oco_live_lock.json"
    data = json.loads(lock_path.read_text())
    data["schema_version"] = 1
    lock_path.write_text(json.dumps(data))
    result = _run(bundle)
    assert result.returncode != 0
    assert "schema_version=2" in result.stderr
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_validate_bundle.py -v`
Expected: FAIL — script does not exist; subprocess returns non-zero with "can't open file".

---

## Task 5: validate_bundle.py — implementation

**Files:**
- Create: `scripts/validate_bundle.py`

- [ ] **Step 1: Write the script**

```python
# scripts/validate_bundle.py
"""Validate one month bundle against ADR 0001 (schema_version=2).

Exit 0 on success; non-zero with a precise error on the first failure.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.behemoth.core.bundle_paths import BundlePaths, BundleIntegrityError


def _validate_one_lock(lock_path: Path) -> None:
    bp = BundlePaths.from_lock(lock_path)
    bp.predictions()
    bp.allowed_states_csv()
    bp.model_cbm()
    bp.model_threshold_json()
    # Optional artifacts: only check if declared in the lock.
    for optional_key in ("wfo_config", "reduced_config", "reduced_summary", "tick_exact_summary"):
        if optional_key in bp._artifacts:  # noqa: SLF001 — intentional integrity probe
            getattr(bp, optional_key)()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bundle_dir", type=Path)
    args = parser.parse_args()
    bundle_dir: Path = args.bundle_dir.resolve()
    if not bundle_dir.is_dir():
        print(f"[validate-bundle] not a directory: {bundle_dir}", file=sys.stderr)
        return 2
    locks = sorted(bundle_dir.glob("*_oco_live_lock.json"))
    if not locks:
        print(f"[validate-bundle] no locks in {bundle_dir}", file=sys.stderr)
        return 2
    for lock_path in locks:
        try:
            _validate_one_lock(lock_path)
        except BundleIntegrityError as exc:
            print(f"[validate-bundle] {exc}", file=sys.stderr)
            return 1
    print(f"[validate-bundle] OK: {len(locks)} locks in {bundle_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 2: Run tests to verify they pass**

Run: `uv run pytest tests/test_validate_bundle.py -v`
Expected: PASS — 4 passed.

- [ ] **Step 3: Lint**

Run: `uv run ruff check scripts/validate_bundle.py tests/test_validate_bundle.py`
Expected: `All checks passed!`

- [ ] **Step 4: Commit**

```bash
git add scripts/validate_bundle.py tests/test_validate_bundle.py
git commit -m "feat(governance): add validate_bundle CLI for schema v2 locks"
```

---

## Task 6: Migration tool — failing test

**Files:**
- Test: `tests/test_migrate_lock_to_v2.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_migrate_lock_to_v2.py
from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path


def _sha256(b: bytes) -> str:
    h = hashlib.sha256(); h.update(b); return h.hexdigest()


def _make_v1_bundle(root: Path) -> Path:
    """Build a fixture mirroring the real 2026-04 layout, repo-relative."""
    bundle = root / "configs/research/governance/oco_candidate_builds/2026-04"
    legacy_models = root / "configs/research/governance/oco_candidate_builds/2026-04/models/oco_dukascopy_candidate"
    mining_dir = root / "data/analysis/tick_opportunity_mining_dukascopy_candidate/wfo_m3to1_oco_fullcap"
    reduced_dir = root / "data/analysis/tick_opportunity_mining_dukascopy_candidate/reduced_core_rolling"
    tick_dir = root / "data/analysis/tick_opportunity_mining_dukascopy_candidate/reduced_core"
    cfg_dir = root / "configs/research/experiments_dukascopy_candidate"
    bundle.mkdir(parents=True)
    legacy_models.mkdir(parents=True)
    mining_dir.mkdir(parents=True)
    reduced_dir.mkdir(parents=True)
    tick_dir.mkdir(parents=True)
    cfg_dir.mkdir(parents=True)

    pred_b = b"pred"; states_b = b"states"; cbm_b = b"cbm"; thr_b = b"thr"
    src_pred_b = b"src-pred"; red_sum_b = b"red-sum"; tick_sum_b = b"tick-sum"
    wfo_b = b"wfo: 1\n"; red_cfg_b = b"red: 1\n"

    (bundle / "eurusd_oco_locked_predictions.parquet").write_bytes(pred_b)
    (bundle / "eurusd_oco_allowed_states.csv").write_bytes(states_b)
    (legacy_models / "EURUSD_model_2026-04.cbm").write_bytes(cbm_b)
    (legacy_models / "EURUSD_model_2026-04.json").write_bytes(thr_b)
    (mining_dir / "EURUSD_oco_monthly_predictions.parquet").write_bytes(src_pred_b)
    (reduced_dir / "EURUSD_oco_reduced_summary.csv").write_bytes(red_sum_b)
    (tick_dir / "EURUSD_oco_tick_exact_summary.csv").write_bytes(tick_sum_b)
    (cfg_dir / "eurusd_tick_opportunity_monthly_wfo_oco_fullcap.yaml").write_bytes(wfo_b)
    (cfg_dir / "eurusd_oco_reduced_core_rolling.yaml").write_bytes(red_cfg_b)

    v1 = {
        "schema_version": 1,
        "symbol": "EURUSD",
        "frozen_at_utc": "2026-05-01T16:08:12+00:00",
        "git": {"branch": "main", "commit": "deadbeef", "dirty": False},
        "artifacts": {
            "live_deployable": True,
            "model_cbm_path":            str(legacy_models / "EURUSD_model_2026-04.cbm"),
            "model_cbm_sha256":          _sha256(cbm_b),
            "model_threshold_json_path": str(legacy_models / "EURUSD_model_2026-04.json"),
            "model_threshold_json_sha256": _sha256(thr_b),
            "model_month":               "2026-04",
            "model_valid_through":       "2026-04-30",
            "predictions_path":          "configs/research/governance/oco_candidate_builds/2026-04/eurusd_oco_locked_predictions.parquet",
            "predictions_sha256":        _sha256(pred_b),
            "reduced_states_csv_path":   "configs/research/governance/oco_candidate_builds/2026-04/eurusd_oco_allowed_states.csv",
            "reduced_states_csv_sha256": _sha256(states_b),
            "source_predictions_path":   "data/analysis/tick_opportunity_mining_dukascopy_candidate/wfo_m3to1_oco_fullcap/EURUSD_oco_monthly_predictions.parquet",
            "source_predictions_sha256": _sha256(src_pred_b),
            "reduced_summary_path":      "data/analysis/tick_opportunity_mining_dukascopy_candidate/reduced_core_rolling/EURUSD_oco_reduced_summary.csv",
            "reduced_summary_sha256":    _sha256(red_sum_b),
            "tick_exact_summary_path":   "data/analysis/tick_opportunity_mining_dukascopy_candidate/reduced_core/EURUSD_oco_tick_exact_summary.csv",
            "tick_exact_summary_sha256": _sha256(tick_sum_b),
            "wfo_config_path":           "configs/research/experiments_dukascopy_candidate/eurusd_tick_opportunity_monthly_wfo_oco_fullcap.yaml",
            "wfo_config_sha256":         _sha256(wfo_b),
            "reduced_config_path":       "configs/research/experiments_dukascopy_candidate/eurusd_oco_reduced_core_rolling.yaml",
            "reduced_config_sha256":     _sha256(red_cfg_b),
            "tick_exact_overall_pass":   True,
            "capacity_overall_pass":     True,
        },
        "locked_runtime": {"production_cap_pips": 1.2},
        "state_universe": {"count": 0, "rows": [], "sha256": ""},
    }
    (bundle / "eurusd_oco_live_lock.json").write_text(json.dumps(v1, indent=2))
    return bundle


def _run(bundle: Path, repo_root: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "scripts/migrate_lock_to_v2.py", str(bundle), "--repo-root", str(repo_root)],
        capture_output=True, text=True,
        cwd=Path(__file__).resolve().parents[1],
    )


def test_migration_produces_v2_lock(tmp_path: Path) -> None:
    bundle = _make_v1_bundle(tmp_path)
    result = _run(bundle, tmp_path)
    assert result.returncode == 0, result.stderr

    data = json.loads((bundle / "eurusd_oco_live_lock.json").read_text())
    assert data["schema_version"] == 2
    assert "artifacts" in data
    for legacy_key in (
        "model_cbm_path", "predictions_path", "reduced_states_csv_path",
        "source_predictions_path", "train_predictions_path",
        "reduced_summary_path", "tick_exact_summary_path",
    ):
        assert legacy_key not in data["artifacts"], legacy_key

    for key in ("predictions", "allowed_states_csv", "model_cbm", "model_threshold_json"):
        entry = data["artifacts"][key]
        assert not entry["path"].startswith("/")
        assert ".." not in entry["path"].split("/")


def test_migration_copies_external_artifacts(tmp_path: Path) -> None:
    bundle = _make_v1_bundle(tmp_path)
    _run(bundle, tmp_path)
    # Reduced summary and tick-exact summary originated under data/analysis, must now exist in bundle.
    assert (bundle / "eurusd_oco_reduced_summary.csv").is_file()
    assert (bundle / "eurusd_oco_tick_exact_summary.csv").is_file()
    # Configs are copied under bundle/configs/.
    assert (bundle / "configs/eurusd_oco_reduced_core_rolling.yaml").is_file()


def test_migration_records_provenance(tmp_path: Path) -> None:
    bundle = _make_v1_bundle(tmp_path)
    _run(bundle, tmp_path)
    data = json.loads((bundle / "eurusd_oco_live_lock.json").read_text())
    prov = data["provenance"]
    assert prov["predictions"]["origin"].endswith("EURUSD_oco_monthly_predictions.parquet")
    assert prov["reduced_summary"]["origin"].startswith("data/analysis/")


def test_migration_validates_after_write(tmp_path: Path) -> None:
    bundle = _make_v1_bundle(tmp_path)
    _run(bundle, tmp_path)
    # The bundle should pass validate_bundle.
    result = subprocess.run(
        [sys.executable, "scripts/validate_bundle.py", str(bundle)],
        capture_output=True, text=True,
        cwd=Path(__file__).resolve().parents[1],
    )
    assert result.returncode == 0, result.stderr


def test_migration_is_idempotent(tmp_path: Path) -> None:
    bundle = _make_v1_bundle(tmp_path)
    first = _run(bundle, tmp_path)
    assert first.returncode == 0
    before = (bundle / "eurusd_oco_live_lock.json").read_text()
    second = _run(bundle, tmp_path)
    assert second.returncode == 0, second.stderr
    after = (bundle / "eurusd_oco_live_lock.json").read_text()
    assert before == after
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_migrate_lock_to_v2.py -v`
Expected: FAIL — `scripts/migrate_lock_to_v2.py` does not exist.

---

## Task 7: Migration tool — implementation

**Files:**
- Create: `scripts/migrate_lock_to_v2.py`

- [ ] **Step 1: Write the script**

```python
# scripts/migrate_lock_to_v2.py
"""One-shot migration: rewrite every *_oco_live_lock.json in a bundle to schema_version=2.

- Bundle-relative paths only.
- Copies referenced external artifacts into the bundle.
- Records origin paths under `provenance.*`.
- Idempotent: re-running on an already-v2 lock is a no-op.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from pathlib import Path
from typing import Any


# Mapping from v1 artifact key prefix to v2 key, target bundle-relative path, and provenance.
# Each tuple = (v1_path_key, v1_sha_key, v2_key, target_relpath_template, is_required)
# `{symbol_lower}` and `{month}` are formatted at runtime.
_PLAN: list[tuple[str, str, str, str, bool]] = [
    ("predictions_path",           "predictions_sha256",           "predictions",          "{symbol_lower}_oco_locked_predictions.parquet", True),
    ("reduced_states_csv_path",    "reduced_states_csv_sha256",    "allowed_states_csv",   "{symbol_lower}_oco_allowed_states.csv",         True),
    ("model_cbm_path",             "model_cbm_sha256",             "model_cbm",            "models/{symbol_upper}_model_{month}.cbm",       True),
    ("model_threshold_json_path",  "model_threshold_json_sha256",  "model_threshold_json", "models/{symbol_upper}_model_{month}.json",      True),
    ("wfo_config_path",            "wfo_config_sha256",            "wfo_config",           "configs/{symbol_lower}_wfo.yaml",               False),
    ("reduced_config_path",        "reduced_config_sha256",        "reduced_config",       "configs/{symbol_lower}_reduced.yaml",           False),
    ("reduced_summary_path",       "reduced_summary_sha256",       "reduced_summary",      "{symbol_lower}_oco_reduced_summary.csv",        False),
    ("tick_exact_summary_path",    "tick_exact_summary_sha256",    "tick_exact_summary",   "{symbol_lower}_oco_tick_exact_summary.csv",     False),
]


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _resolve_v1(value: str, *, bundle_dir: Path, repo_root: Path) -> Path:
    p = Path(value)
    if p.is_absolute():
        return p
    # v1 paths were either repo-relative or already bundle-relative.
    repo_candidate = (repo_root / p).resolve()
    if repo_candidate.is_file():
        return repo_candidate
    return (bundle_dir / p).resolve()


def _migrate_one(lock_path: Path, repo_root: Path) -> None:
    data = json.loads(lock_path.read_text(encoding="utf-8"))
    if int(data.get("schema_version", 0)) == 2:
        return  # idempotent

    bundle_dir = lock_path.parent.resolve()
    symbol = str(data.get("symbol", "")).upper().strip()
    if not symbol:
        raise SystemExit(f"{lock_path}: missing symbol")
    v1_artifacts: dict[str, Any] = data.get("artifacts", {}) or {}
    month = str(v1_artifacts.get("model_month", "")).strip() or bundle_dir.name

    new_artifacts: dict[str, dict[str, str]] = {}
    provenance: dict[str, dict[str, str]] = {}
    fmt = {"symbol_lower": symbol.lower(), "symbol_upper": symbol, "month": month}

    for v1_path_key, v1_sha_key, v2_key, target_tmpl, required in _PLAN:
        v1_path_value = str(v1_artifacts.get(v1_path_key, "")).strip()
        if not v1_path_value:
            if required:
                raise SystemExit(f"{lock_path}: required v1 key {v1_path_key} missing")
            continue
        source = _resolve_v1(v1_path_value, bundle_dir=bundle_dir, repo_root=repo_root)
        if not source.is_file():
            raise SystemExit(f"{lock_path}: v1 referenced file missing: {source}")
        target_rel = target_tmpl.format(**fmt)
        target_abs = bundle_dir / target_rel
        target_abs.parent.mkdir(parents=True, exist_ok=True)
        if source.resolve() != target_abs.resolve():
            shutil.copy2(source, target_abs)
        sha = _sha256_file(target_abs)
        new_artifacts[v2_key] = {"path": target_rel, "sha256": sha}
        # Provenance — only record when the source lived outside the bundle.
        try:
            source.resolve().relative_to(bundle_dir)
        except ValueError:
            try:
                origin_rel = source.resolve().relative_to(repo_root).as_posix()
            except ValueError:
                origin_rel = str(source.resolve())
            provenance[v2_key] = {"origin": origin_rel, "origin_sha256": sha}

    deployability = {
        "live_deployable":        bool(v1_artifacts.get("live_deployable", False)),
        "tick_exact_overall_pass": v1_artifacts.get("tick_exact_overall_pass"),
        "capacity_overall_pass":  v1_artifacts.get("capacity_overall_pass"),
        "model_month":            month,
        "model_valid_through":    str(v1_artifacts.get("model_valid_through", "")).strip(),
    }

    v2 = {
        "schema_version": 2,
        "symbol": symbol,
        "frozen_at_utc": data.get("frozen_at_utc"),
        "git": data.get("git", {}),
        "bundle": {"month": month, "dir_relpath": str(bundle_dir.relative_to(repo_root))},
        "artifacts": new_artifacts,
        "provenance": provenance,
        "deployability": deployability,
        "locked_runtime": data.get("locked_runtime", {}),
        "retrain_policy": data.get("retrain_policy", {}),
        "state_universe": data.get("state_universe", {}),
        "historical_backtest": data.get("historical_backtest", {}),
    }
    lock_path.write_text(json.dumps(v2, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bundle_dir", type=Path)
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    bundle_dir: Path = args.bundle_dir.resolve()
    repo_root: Path = args.repo_root.resolve()
    locks = sorted(bundle_dir.glob("*_oco_live_lock.json"))
    if not locks:
        print(f"[migrate-lock-v2] no locks in {bundle_dir}", file=sys.stderr)
        return 2
    for lock_path in locks:
        _migrate_one(lock_path, repo_root)
        print(f"[migrate-lock-v2] migrated {lock_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 2: Run tests to verify they pass**

Run: `uv run pytest tests/test_migrate_lock_to_v2.py -v`
Expected: PASS — 5 passed.

- [ ] **Step 3: Lint**

Run: `uv run ruff check scripts/migrate_lock_to_v2.py tests/test_migrate_lock_to_v2.py`
Expected: `All checks passed!`

- [ ] **Step 4: Commit**

```bash
git add scripts/migrate_lock_to_v2.py tests/test_migrate_lock_to_v2.py
git commit -m "feat(governance): add v1->v2 lock migration tool"
```

---

## Task 8: Migrate existing on-disk bundles

**Files:**
- Modify: `configs/research/governance/oco_candidate_builds/2026-02/*.json`
- Modify: `configs/research/governance/oco_candidate_builds/2026-03/*.json`
- Modify: `configs/research/governance/oco_candidate_builds/2026-04/*.json`

- [ ] **Step 1: Run migration on each existing bundle**

```bash
for month in 2026-02 2026-03 2026-04; do
  uv run python scripts/migrate_lock_to_v2.py "configs/research/governance/oco_candidate_builds/${month}"
done
```

Expected: stdout lines `[migrate-lock-v2] migrated configs/research/governance/oco_candidate_builds/<month>/<symbol>_oco_live_lock.json` for every lock.

- [ ] **Step 2: Validate each migrated bundle**

```bash
for month in 2026-02 2026-03 2026-04; do
  uv run python scripts/validate_bundle.py "configs/research/governance/oco_candidate_builds/${month}"
done
```

Expected: each prints `[validate-bundle] OK: N locks in <path>` with exit code 0. If any bundle reports `missing artifact`, **stop and address the missing on-disk file before proceeding** — the migration found a real gap.

- [ ] **Step 3: Inspect a sample lock to confirm shape**

```bash
uv run python -c "import json; d = json.load(open('configs/research/governance/oco_candidate_builds/2026-04/eurusd_oco_live_lock.json')); print('schema:', d['schema_version']); print('keys:', sorted(d['artifacts'].keys())); print('predictions:', d['artifacts']['predictions'])"
```

Expected: `schema: 2`, `keys: ['allowed_states_csv', 'model_cbm', 'model_threshold_json', 'predictions', ...]`, and `predictions['path']` is `eurusd_oco_locked_predictions.parquet` (no leading slash, no `..`).

- [ ] **Step 4: Commit**

```bash
git add configs/research/governance/oco_candidate_builds
git commit -m "chore(governance): migrate 2026-02/03/04 bundles to schema v2"
```

---

## Task 9: Update freeze_oco_live_governance.py to emit v2 — failing test

**Files:**
- Test: `tests/test_freeze_oco_live_governance.py` (add a new test; keep file if it exists, otherwise create)

- [ ] **Step 1: Identify the test target**

Run: `ls tests | grep -i freeze`
If `tests/test_freeze_oco_live_governance.py` exists, add the test below to it. Otherwise create the file with the imports needed.

- [ ] **Step 2: Add the failing test**

```python
def test_live_freeze_emits_schema_v2_with_bundle_relative_paths(tmp_path, monkeypatch):
    """Freeze must produce a v2 lock whose artifact paths are bundle-relative."""
    from scripts import freeze_oco_live_governance as freeze

    # Stage a minimal repo-shaped tmp_path so freeze writes into it.
    monkeypatch.chdir(tmp_path)
    bundle_dir = tmp_path / "configs/research/governance/oco_candidate_builds/2026-05"
    bundle_dir.mkdir(parents=True)

    # ... arrange fixture artifacts the way the existing freeze tests do.
    # (Mirror the pattern used by existing freeze_oco_live_governance tests.)
    lock_path = bundle_dir / "eurusd_oco_live_lock.json"

    # Invoke whichever public entrypoint the existing tests use; e.g.:
    freeze.freeze_symbol(symbol="EURUSD", out_dir=bundle_dir, ...)

    import json
    data = json.loads(lock_path.read_text())
    assert data["schema_version"] == 2
    for key, entry in data["artifacts"].items():
        assert not entry["path"].startswith("/"), key
        assert ".." not in entry["path"].split("/"), key
```

Note: replace `freeze_symbol(...)` and the fixture arrangement with the same calls/fixtures the existing freeze tests use. The agent **must read** `tests/test_freeze_oco_live_governance*.py` (if present) and mirror its setup; do not invent a fresh fixture pipeline.

- [ ] **Step 3: Run test to verify it fails**

Run: `uv run pytest tests/test_freeze_oco_live_governance.py::test_live_freeze_emits_schema_v2_with_bundle_relative_paths -v`
Expected: FAIL — current freeze writes `schema_version: 1` and absolute-ish path strings.

---

## Task 10: Update freeze_oco_live_governance.py to emit v2 — implementation

**Files:**
- Modify: `scripts/freeze_oco_live_governance.py::_build_manifest`

- [ ] **Step 1: Replace the manifest builder**

Open `scripts/freeze_oco_live_governance.py`. Find `_build_manifest` (currently around lines 272–325). Replace the `manifest = { ... "schema_version": 1, ... "artifacts": { ... } }` block with v2 shape. The replacement must:

1. Set `"schema_version": 2`.
2. For every input path in `paths` (`predictions`, `reduced_states`, `reduced_summary`, `tick_exact_summary`, `wfo_config`, `reduced_config`), copy the file into the bundle (`out_dir / target_relpath` from the same map used in `migrate_lock_to_v2.py::_PLAN`) and record `{path: target_relpath, sha256: sha}` under `artifacts.<v2_key>`.
3. Same for `model_cbm` / `model_threshold_json` (copy into `<bundle>/models/<symbol>_model_<month>.{cbm,json}`).
4. Build the `provenance` block recording each origin path (repo-relative to `_repo_root()`) and its sha256.
5. Build `deployability = {"live_deployable": tick_ok and cap_ok, "tick_exact_overall_pass": tick_ok, "capacity_overall_pass": cap_ok, "model_month": model_month, "model_valid_through": ...}`.

The simplest implementation imports `_PLAN` from `scripts.migrate_lock_to_v2` and reuses it (DRY). To avoid a script-to-script import, lift `_PLAN` and `_sha256_file` into `src/behemoth/core/bundle_paths.py` as `BUNDLE_LAYOUT` and `sha256_file`, then import from there in both scripts.

If you lift the constants, also:
- Add a small helper `src/behemoth/core/bundle_paths.py::BUNDLE_LAYOUT: tuple[BundleArtifactSpec, ...]` where each spec is a `NamedTuple(v2_key, target_relpath_template, required)`.
- Update `scripts/migrate_lock_to_v2.py` to import `BUNDLE_LAYOUT` and remove its local `_PLAN`.
- Add a test in `tests/test_bundle_paths.py` asserting `BUNDLE_LAYOUT` covers each required key.

- [ ] **Step 2: Run the freeze test**

Run: `uv run pytest tests/test_freeze_oco_live_governance.py -v`
Expected: PASS, including the new assertion plus all existing tests.

- [ ] **Step 3: Re-run migration tool test (it must still pass after BUNDLE_LAYOUT lift)**

Run: `uv run pytest tests/test_migrate_lock_to_v2.py tests/test_bundle_paths.py -v`
Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add src/behemoth/core/bundle_paths.py scripts/freeze_oco_live_governance.py scripts/migrate_lock_to_v2.py tests/test_freeze_oco_live_governance.py tests/test_bundle_paths.py
git commit -m "feat(governance): freeze_oco_live_governance emits schema v2 directly"
```

---

## Task 11: Update legacy historical freeze to emit v2

**Files:**
- Modify: `scripts/legacy/freeze_oco_historical_governance.py` (around lines 477, 485, 495, 549, 570)

This script is the active path used by `run_monthly_build.py` to write the bundle locks. It currently writes `source_predictions_path`, `train_predictions_path`, and `live_deployable` in v1 shape. It must emit v2.

- [ ] **Step 1: Identify the manifest construction**

Run: `grep -n '"schema_version"\|"artifacts"\|"source_predictions_path"\|"train_predictions_path"' scripts/legacy/freeze_oco_historical_governance.py`

- [ ] **Step 2: Replace the manifest block**

Mirror the change from Task 10 — build the `artifacts`/`provenance`/`deployability` v2 shape using `BUNDLE_LAYOUT` and `sha256_file` from `src/behemoth/core/bundle_paths.py`. For the keys that are unique to the legacy freeze (`source_predictions_path` → `provenance.predictions.origin`, `train_predictions_path` → `provenance.train_predictions.origin`), keep them under `provenance.*` only — do **not** add a `train_predictions` entry to `artifacts` (training predictions are not consumed at certification).

- [ ] **Step 3: Update or add a test asserting v2 output**

If `tests/legacy/test_freeze_oco_historical_governance.py` exists, add an assertion `assert manifest["schema_version"] == 2 and "source_predictions_path" not in manifest["artifacts"]`. Otherwise add one minimal test that drives the function with a tmp_path fixture similar to the one in `tests/test_migrate_lock_to_v2.py`.

- [ ] **Step 4: Run the affected tests**

Run: `uv run pytest tests/legacy -v` (if present) and `uv run pytest tests/ -k "freeze_oco_historical" -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/legacy/freeze_oco_historical_governance.py tests/
git commit -m "feat(governance): legacy historical freeze emits schema v2"
```

---

## Task 12: Simplify run_monthly_build to drop path rewriting

**Files:**
- Modify: `scripts/run_monthly_build.py::_materialize_bundle_models` (lines 47–86)

With v2, the freeze already writes the model files into `<bundle>/models/<symbol>_model_<month>.{cbm,json}` using bundle-relative paths. `_materialize_bundle_models` therefore no longer needs to copy files or rewrite paths — it only needs to call `validate_bundle` to fail fast if the freeze produced an inconsistent bundle.

- [ ] **Step 1: Replace `_materialize_bundle_models`**

Replace the body of `_materialize_bundle_models` with:

```python
def _materialize_bundle_models(bundle_dir: Path) -> None:
    """Schema-v2 bundles are self-contained; validate and proceed."""
    result = subprocess.run(
        [sys.executable, "scripts/validate_bundle.py", str(bundle_dir)],
        cwd=_repo_root(),
    )
    if result.returncode != 0:
        raise SystemExit(
            f"[monthly-build] bundle failed validation: {bundle_dir}"
        )
```

Add `import sys` at the top if missing. Remove the unused `shutil`, `csv` imports if nothing else uses them in this file (check first; do not strip imports that other functions rely on).

- [ ] **Step 2: Add a regression test**

Append to `tests/test_run_monthly_build.py` (create if missing):

```python
def test_materialize_bundle_models_calls_validator(tmp_path, monkeypatch):
    from scripts import run_monthly_build

    called: list[list[str]] = []

    class _Result:
        returncode = 0

    def _fake_run(cmd, cwd=None):
        called.append(list(cmd))
        return _Result()

    monkeypatch.setattr(run_monthly_build.subprocess, "run", _fake_run)
    bundle = tmp_path / "2026-04"
    bundle.mkdir()
    run_monthly_build._materialize_bundle_models(bundle)
    assert any("validate_bundle.py" in part for part in called[0])
```

- [ ] **Step 3: Run the test**

Run: `uv run pytest tests/test_run_monthly_build.py -v`
Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add scripts/run_monthly_build.py tests/test_run_monthly_build.py
git commit -m "refactor(governance): monthly_build delegates bundle integrity to validate_bundle"
```

---

## Task 13: Switch run_stage12_stage13_certification to BundlePaths — failing test

**Files:**
- Test: `tests/test_run_stage12_stage13_certification.py`

- [ ] **Step 1: Add a failing test**

```python
def test_stage12_reads_predictions_via_bundle_paths(tmp_path, monkeypatch):
    """Stage 12 must load predictions only from BundlePaths.predictions(); no fallback."""
    from scripts import run_stage12_stage13_certification as cert
    from src.behemoth.core.bundle_paths import BundlePaths

    # Build a v2 bundle fixture (reuse helper from tests/test_bundle_paths.py if you import it,
    # otherwise inline the helper here).
    lock_path = _write_v2_bundle(tmp_path)  # see tests/test_bundle_paths.py
    seen: list[Path] = []

    real_predictions = BundlePaths.predictions

    def _spy(self):
        p = real_predictions(self)
        seen.append(p)
        return p

    monkeypatch.setattr(BundlePaths, "predictions", _spy)

    # Drive the function that loads predictions (use the same entrypoint
    # already covered by test_run_stage12_stage13_certification.py).
    cert.load_frozen_predictions(lock_path=lock_path)
    assert len(seen) == 1
```

Note: the exact entrypoint name (`load_frozen_predictions`) is illustrative; read `scripts/run_stage12_stage13_certification.py` and bind the test to the function that PR #238 modified to add the fallback.

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/test_run_stage12_stage13_certification.py -v -k bundle_paths`
Expected: FAIL — current code path still calls a manual `Path(...)` constructor or reads `source_predictions_path` on fallback.

---

## Task 14: Switch run_stage12_stage13_certification to BundlePaths — implementation

**Files:**
- Modify: `scripts/run_stage12_stage13_certification.py`

- [ ] **Step 1: Replace lock-key reads with BundlePaths**

In `scripts/run_stage12_stage13_certification.py`:

1. At the top, add `from src.behemoth.core.bundle_paths import BundlePaths` (mirroring how PR #238 imports today; use `sys.path` shim if the file already has one).
2. Find every read of `artifacts["predictions_path"]`, `artifacts.get("predictions_path")`, `artifacts["source_predictions_path"]`, `artifacts["reduced_states_csv_path"]`, `artifacts["model_cbm_path"]`, `artifacts["model_threshold_json_path"]`.
3. Replace each with the corresponding `BundlePaths.from_lock(lock_path).predictions()` / `.allowed_states_csv()` / `.model_cbm()` / `.model_threshold_json()`.
4. **Delete the PR #238 fallback branch** that prefers the bundle and falls back to mining outputs — there is no fallback in v2.
5. Delete the now-unused `_resolve_repo_path` helper if it was added by PR #238 and is no longer referenced.

- [ ] **Step 2: Run the test**

Run: `uv run pytest tests/test_run_stage12_stage13_certification.py -v`
Expected: PASS — including the new `bundle_paths` test and all preexisting ones.

- [ ] **Step 3: Lint**

Run: `uv run ruff check scripts/run_stage12_stage13_certification.py`
Expected: `All checks passed!`

- [ ] **Step 4: Commit**

```bash
git add scripts/run_stage12_stage13_certification.py tests/test_run_stage12_stage13_certification.py
git commit -m "refactor(governance): stage12/13 loads artifacts via BundlePaths"
```

---

## Task 15: Switch run_monthly_recert to BundlePaths

**Files:**
- Modify: `scripts/run_monthly_recert.py`

- [ ] **Step 1: Replace existence-check loop with validator**

In `scripts/run_monthly_recert.py::_validate_month_bundle`, replace the post-PR-238 block that loops over `live_deployable`, `prediction_path_raw`, `states_path_raw` (added in lines 313–334 by PR #238) with a single delegation:

```python
# Validate every lock in the bundle via the v2 contract.
result = subprocess.run(
    [sys.executable, "scripts/validate_bundle.py", str(build_bundle_dir)],
    cwd=_repo_root(),
)
if result.returncode != 0:
    raise SystemExit(
        f"[monthly-recert] incomplete month build bundle: {build_bundle_dir}"
    )
```

Then delete the now-unused `_resolve_repo_path` helper (added by PR #238).

- [ ] **Step 2: Update the existing test**

`tests/test_run_monthly_recert.py::test_validate_month_bundle_requires_live_deployable_prediction_artifacts` (added in PR #238) currently asserts the specific PR-238 error message. Replace its assertion with:

```python
with pytest.raises(SystemExit, match=r"incomplete month build bundle"):
    run_monthly_recert._validate_month_bundle(build_bundle_dir)
```

The fixture should write a v2 lock missing its predictions file — adapt `_write_bundle_fixture` to emit v2 shape.

- [ ] **Step 3: Run the test**

Run: `uv run pytest tests/test_run_monthly_recert.py -v`
Expected: PASS.

- [ ] **Step 4: Lint**

Run: `uv run ruff check scripts/run_monthly_recert.py tests/test_run_monthly_recert.py`
Expected: `All checks passed!`

- [ ] **Step 5: Commit**

```bash
git add scripts/run_monthly_recert.py tests/test_run_monthly_recert.py
git commit -m "refactor(governance): monthly_recert delegates bundle integrity to validate_bundle"
```

---

## Task 16: Migrate remaining consumers to BundlePaths

The following files each read one or more legacy lock keys directly. Switch them in one task because each touches one or two lines and they share the same edit pattern.

**Files:**
- Modify: `scripts/validate_oco_live_governance.py`
- Modify: `scripts/run_promote_live.py`
- Modify: `scripts/run_jforex_live.py`
- Modify: `scripts/audit_oco_leakage_label_integrity.py`
- Modify: `scripts/run_offset_tickbar_frozen_screen.py`
- Modify: `scripts/seed_rolling_threshold.py`
- Modify: `scripts/simulate_api_e2e_replay.py`
- Modify: `scripts/sync_candidate_model_artifacts.py`
- Modify: `scripts/reconcile_historical_prediction_artifacts.py`
- Modify: `src/behemoth/core/governance_lock_loader.py::_parse_lock`
- Modify: `src/behemoth/core/governance_validator.py`
- Modify: `src/behemoth/core/historical_prediction_stage.py`
- Modify: `src/behemoth/core/historical_registry.py`
- Modify: `src/behemoth/core/model_registry.py`
- Modify: `src/behemoth/core/registry.py`
- Modify: `src/behemoth/api/server.py`

- [ ] **Step 1: Find every remaining direct lock-key access**

Run:

```bash
grep -rnE 'artifacts(\[|\.get\()("(predictions_path|source_predictions_path|reduced_states_csv_path|model_cbm_path|model_threshold_json_path|reduced_summary_path|tick_exact_summary_path|wfo_config_path|reduced_config_path|train_predictions_path)"' src/ scripts/ tests/ | grep -v __pycache__
```

Expected: one or more matches per file in the list above (excluding migration & validation scripts already updated, and the legacy freeze).

- [ ] **Step 2: For each match, replace the direct artifact access**

In each file:

1. Add `from src.behemoth.core.bundle_paths import BundlePaths` (use existing sys-path bootstrap if any).
2. Replace `artifacts["predictions_path"]` (and friends) with the appropriate `BundlePaths.from_lock(lock_path).<accessor>()` call. The lock path is already in scope wherever the artifacts dict is — pass it through if needed.
3. For `governance_lock_loader._parse_lock`: replace the direct `model_binding` reads with `bp = BundlePaths.from_lock(path)` and derive `model_binding` from `bp.model_cbm()`, `bp.model_threshold_json()`, etc. Keep the `CandidateContract` shape the same.

- [ ] **Step 3: Run the full governance test suite**

Run: `uv run pytest -q tests/test_run_monthly_recert.py tests/test_run_stage12_stage13_certification.py tests/test_bundle_paths.py tests/test_validate_bundle.py tests/test_migrate_lock_to_v2.py tests/governance tests/test_governance_lock_loader.py tests/test_governance_validator.py tests/test_historical_registry.py tests/test_model_registry.py tests/test_registry.py tests/test_api_server.py tests/test_run_promote_live.py tests/test_run_jforex_live.py`
Expected: PASS. If any test file in the list does not exist, skip it. If any preexisting test fails because it used a v1 lock fixture, update the fixture to v2 — do **not** add a compat shim.

- [ ] **Step 4: Verify no legacy keys remain**

Run: `grep -rnE '"(predictions_path|source_predictions_path|reduced_states_csv_path|model_cbm_path|model_threshold_json_path|train_predictions_path)"' src/ scripts/ | grep -v scripts/legacy | grep -v scripts/migrate_lock_to_v2.py | grep -v __pycache__`
Expected: **no output**. Legacy keys live only in `scripts/legacy/*` and `scripts/migrate_lock_to_v2.py`.

- [ ] **Step 5: Lint touched files**

Run: `uv run ruff check src scripts`
Expected: `All checks passed!`

- [ ] **Step 6: Commit**

```bash
git add src scripts tests
git commit -m "refactor(governance): all consumers read locks via BundlePaths"
```

---

## Task 17: Add bundle validation to CI

**Files:**
- Modify: `.github/workflows/ci.yml` (or whichever workflow runs governance checks — discover with `ls .github/workflows`)

- [ ] **Step 1: Discover the workflow file**

Run: `ls .github/workflows/`
Pick the workflow that runs `uv run pytest` for governance (look inside each candidate). Call it `<workflow>.yml`.

- [ ] **Step 2: Add a validation step**

Add this step to `<workflow>.yml` after the dependency-install step and before `pytest`:

```yaml
      - name: Validate month bundles
        run: |
          for month_dir in configs/research/governance/oco_candidate_builds/[0-9]*-[0-9]*; do
            uv run python scripts/validate_bundle.py "$month_dir"
          done
```

- [ ] **Step 3: Verify the script works against all on-disk bundles locally**

Run:

```bash
for d in configs/research/governance/oco_candidate_builds/*-*/; do
  uv run python scripts/validate_bundle.py "$d" || exit 1
done
```

Expected: each bundle prints `[validate-bundle] OK: N locks in <path>` with exit code 0.

- [ ] **Step 4: Commit**

```bash
git add .github/workflows/
git commit -m "ci: validate every month bundle against schema v2"
```

---

## Task 18: Documentation pointers to ADR 0001

**Files:**
- Modify: `CLAUDE.md`
- Modify: `AGENTS.md`
- Modify: `CONTEXT.md`

- [ ] **Step 1: Add ADR pointer to CLAUDE.md**

In `CLAUDE.md`, under the `## Essential` section, add the bullet:

```markdown
- Month bundles follow **ADR 0001** (`docs/adr/0001-deterministic-month-bundles.md`): schema_version 2, bundle-relative paths, sha-verified via `src/behemoth/core/bundle_paths.py`
```

- [ ] **Step 2: Add the same pointer to AGENTS.md and CONTEXT.md**

Wherever each file describes the governance pipeline or bundle layout, add: `> Bundle contract: see ADR 0001 (docs/adr/0001-deterministic-month-bundles.md). All path resolution goes through src/behemoth/core/bundle_paths.py::BundlePaths.`

- [ ] **Step 3: Commit**

```bash
git add CLAUDE.md AGENTS.md CONTEXT.md
git commit -m "docs: link governance bundle ADR from operator guides"
```

---

## Task 19: Final verification

- [ ] **Step 1: Full test suite**

Run: `uv run pytest -q`
Expected: all green.

- [ ] **Step 2: Lint**

Run: `uv run ruff check`
Expected: `All checks passed!`

- [ ] **Step 3: All bundles validate**

Run:
```bash
for d in configs/research/governance/oco_candidate_builds/*-*/; do
  uv run python scripts/validate_bundle.py "$d"
done
```
Expected: every bundle prints `OK`.

- [ ] **Step 4: No legacy keys outside `scripts/legacy/` and the migration tool**

Run:
```bash
grep -rnE '"(predictions_path|source_predictions_path|reduced_states_csv_path|model_cbm_path|model_threshold_json_path|train_predictions_path)"' src/ scripts/ | grep -v scripts/legacy | grep -v scripts/migrate_lock_to_v2.py | grep -v __pycache__
```
Expected: empty.

- [ ] **Step 5: Open the PR**

Use `superpowers:finishing-a-development-branch` to push and open the PR. PR title: `feat(governance): deterministic month bundles (schema v2)`. PR body should reference ADR 0001 and call out that PR #238's fallback branches are deleted in favor of fail-loud.

---

## Risks and Notes for the Implementer

- **Bundle contents may be missing on disk.** The 2026-04 bundle in particular was reported (PR #238 session) as missing `eurusd_oco_locked_predictions.parquet`. Recent `ls` shows it present, but if Task 8 reports `missing artifact`, **stop and surface the gap to the user before regenerating** — silently regenerating the artifact would destroy provenance.
- **Train predictions are not in `artifacts`.** They are runtime-irrelevant for certification; only the provenance origin + sha is kept. If any consumer (`reconcile_historical_prediction_artifacts.py` is the obvious one) genuinely needs `train_predictions`, add a `BundlePaths.train_predictions()` accessor and a matching `BUNDLE_LAYOUT` row before completing Task 16 — don't bring back the legacy key.
- **`scripts/legacy/freeze_oco_historical_governance.py` is still in active use.** Despite the `legacy/` path, `run_monthly_build.py` invokes it. Treat it as a first-class producer in this plan, not as dead code.
- **PR #238 will be effectively reverted within this PR.** That is the intended outcome — the fallback branch was a patch over the broken contract. The fail-loud behavior remains; the path-fallback dies.
- **Do not write a compatibility shim that auto-migrates v1 → v2 at read time.** `BundlePaths.from_lock` must refuse v1. The migration is a one-shot run in Task 8.

---

## Self-Review

**Spec coverage:**
- Schema v2 contract → ADR (Task 1), resolver (Tasks 2–3), validator (Tasks 4–5).
- Migration of existing locks → migration tool (Tasks 6–7) + applied to disk (Task 8).
- Producers emit v2 → freeze_oco_live (Tasks 9–10), legacy historical freeze (Task 11), run_monthly_build cleanup (Task 12).
- Consumers read v2 → Stage 12/13 (Tasks 13–14), monthly_recert (Task 15), everything else (Task 16).
- CI enforces → Task 17.
- Operator docs updated → Task 18.
- Verification → Task 19.

**Placeholder scan:** Task 9 contains an illustrative test stub (`freeze.freeze_symbol(...)`) and explicitly tells the implementer to bind it to whatever entrypoint the existing freeze tests use; that is intentional because the freeze test fixture is non-trivial and already established. Task 13 similarly flags `load_frozen_predictions` as illustrative. Both are called out with explicit instructions to read the surrounding code first. No `TODO` / `TBD` strings remain.

**Type consistency:** `BundlePaths.from_lock(lock_path) -> BundlePaths` used identically across Tasks 2, 3, 5, 14, 15, 16. Accessor names (`predictions()`, `allowed_states_csv()`, `model_cbm()`, `model_threshold_json()`, `wfo_config()`, `reduced_config()`, `reduced_summary()`, `tick_exact_summary()`) match the v2 key names in `BUNDLE_LAYOUT` and the lock shape diagram.
