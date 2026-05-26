# src/behemoth/core/bundle_paths.py
"""Bundle-relative path resolver for schema_version=3 month bundles.

Single source of truth for turning lock keys into filesystem paths. Every
producer and consumer goes through here so the lock file's contract is
enforced in exactly one place.

See docs/adr/0001-deterministic-month-bundles.md and
docs/adr/0002-multi-family-bundle-contract.md for the design decisions.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, NamedTuple


class BundleIntegrityError(RuntimeError):
    pass


class BundleArtifactSpec(NamedTuple):
    v2_key: str
    target_relpath_template: str
    required: bool


BUNDLE_LAYOUTS: dict[str, tuple[BundleArtifactSpec, ...]] = {
    "oco_first_touch_clean": (
        BundleArtifactSpec("predictions", "{symbol_lower}_oco_locked_predictions.parquet", True),
        BundleArtifactSpec("allowed_states_csv", "{symbol_lower}_oco_allowed_states.csv", True),
        BundleArtifactSpec("model_cbm", "models/{symbol_upper}_model_{month}.cbm", True),
        BundleArtifactSpec("model_threshold_json", "models/{symbol_upper}_model_{month}.json", True),
        BundleArtifactSpec("wfo_config", "configs/{symbol_lower}_wfo.yaml", False),
        BundleArtifactSpec("reduced_config", "configs/{symbol_lower}_reduced.yaml", False),
        BundleArtifactSpec("reduced_summary", "{symbol_lower}_oco_reduced_summary.csv", False),
        BundleArtifactSpec("tick_exact_summary", "{symbol_lower}_oco_tick_exact_summary.csv", False),
    ),
}


def bundle_layout_for(family: str) -> tuple[BundleArtifactSpec, ...]:
    if family not in BUNDLE_LAYOUTS:
        raise BundleIntegrityError(f"unknown family: {family!r}")
    return BUNDLE_LAYOUTS[family]


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
    family: str
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
        bundle_layout_for(family)
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
            family=family,
            _artifacts=artifacts,
            _deployability=dict(deploy),
        )

    def _resolve(self, key: str) -> Path:
        if key not in self._artifacts:
            raise BundleIntegrityError(f"{self.lock_path}: required artifact key {key!r} missing")
        art = self._artifacts[key]
        candidate = (self.bundle_dir / art.relpath).resolve()
        try:
            candidate.relative_to(self.bundle_dir)
        except ValueError as exc:
            raise BundleIntegrityError(
                f"{self.lock_path}: artifacts.{key} escapes bundle dir"
            ) from exc
        if not candidate.is_file():
            raise BundleIntegrityError(f"{self.lock_path}: missing artifact for {key}: {candidate}")
        actual = sha256_file(candidate)
        if actual != art.sha256:
            raise BundleIntegrityError(
                f"{self.lock_path}: sha256 mismatch for {key} (expected {art.sha256}, got {actual})"
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


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()
