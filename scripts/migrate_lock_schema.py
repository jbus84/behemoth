# scripts/migrate_lock_to_v2.py
"""One-shot migration: rewrite every *_oco_live_lock.json in a bundle to schema_version=3.

- Bundle-relative paths only.
- Copies referenced external artifacts into the bundle.
- Records origin paths under `provenance.*`.
- Idempotent: re-running on an already-v3 lock is a no-op.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.behemoth.core.bundle_paths import bundle_layout_for, sha256_file  # noqa: E402

# Mapping from v1 artifact key prefix to bundle artifact key.
_PLAN_KEYS: list[tuple[str, str, str]] = [
    ("predictions_path", "predictions_sha256", "predictions"),
    ("reduced_states_csv_path", "reduced_states_csv_sha256", "allowed_states_csv"),
    ("model_cbm_path", "model_cbm_sha256", "model_cbm"),
    ("model_threshold_json_path", "model_threshold_json_sha256", "model_threshold_json"),
    ("wfo_config_path", "wfo_config_sha256", "wfo_config"),
    ("reduced_config_path", "reduced_config_sha256", "reduced_config"),
    ("reduced_summary_path", "reduced_summary_sha256", "reduced_summary"),
    ("tick_exact_summary_path", "tick_exact_summary_sha256", "tick_exact_summary"),
]


def _resolve_v1(value: str, *, bundle_dir: Path, repo_root: Path) -> Path:
    p = Path(value)
    if p.is_absolute():
        return p
    # v1 paths were either repo-relative or already bundle-relative.
    repo_candidate = (repo_root / p).resolve()
    if repo_candidate.is_file():
        return repo_candidate
    return (bundle_dir / p).resolve()


def _write_lock(lock_path: Path, data: dict[str, Any]) -> None:
    lock_path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _migrate_one(lock_path: Path, repo_root: Path, family: str) -> None:
    data = json.loads(lock_path.read_text(encoding="utf-8"))
    schema_version = int(data.get("schema_version", 0))
    if schema_version == 3:
        return  # idempotent
    if schema_version == 2:
        bundle = data.get("bundle", {}) or {}
        if not isinstance(bundle, dict):
            raise SystemExit(f"{lock_path}: bundle must be an object")
        bundle["family"] = family
        data["bundle"] = bundle
        data["schema_version"] = 3
        _write_lock(lock_path, data)
        return
    if schema_version != 1:
        raise SystemExit(f"{lock_path}: unsupported schema_version {schema_version!r}")

    layout = {spec.v2_key: spec for spec in bundle_layout_for(family)}

    bundle_dir = lock_path.parent.resolve()
    symbol = str(data.get("symbol", "")).upper().strip()
    if not symbol:
        raise SystemExit(f"{lock_path}: missing symbol")
    v1_artifacts: dict[str, Any] = data.get("artifacts", {}) or {}
    month = str(v1_artifacts.get("model_month", "")).strip() or bundle_dir.name

    new_artifacts: dict[str, dict[str, str]] = {}
    provenance: dict[str, dict[str, str]] = {}
    fmt = {"symbol_lower": symbol.lower(), "symbol_upper": symbol, "month": month}

    for v1_path_key, _v1_sha_key, v2_key in _PLAN_KEYS:
        spec = layout[v2_key]
        v1_path_value = str(v1_artifacts.get(v1_path_key, "")).strip()
        if not v1_path_value:
            if spec.required:
                raise SystemExit(f"{lock_path}: required v1 key {v1_path_key} missing")
            continue
        source = _resolve_v1(v1_path_value, bundle_dir=bundle_dir, repo_root=repo_root)
        if not source.is_file():
            raise SystemExit(f"{lock_path}: v1 referenced file missing: {source}")
        target_rel = spec.target_relpath_template.format(**fmt)
        target_abs = bundle_dir / target_rel
        target_abs.parent.mkdir(parents=True, exist_ok=True)
        if source.resolve() != target_abs.resolve():
            shutil.copy2(source, target_abs)
        sha = sha256_file(target_abs)
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
        else:
            # Source is inside the bundle; check for a canonical external source path.
            if v2_key == "predictions" and "source_predictions_path" in v1_artifacts:
                src_path = str(v1_artifacts["source_predictions_path"]).strip()
                if src_path:
                    src = _resolve_v1(src_path, bundle_dir=bundle_dir, repo_root=repo_root)
                    if src.is_file():
                        try:
                            origin_rel = src.resolve().relative_to(repo_root).as_posix()
                        except ValueError:
                            origin_rel = str(src.resolve())
                        provenance[v2_key] = {
                            "origin": origin_rel,
                            "origin_sha256": sha256_file(src),
                        }

    deployability = {
        "live_deployable": bool(v1_artifacts.get("live_deployable", False)),
        "tick_exact_overall_pass": v1_artifacts.get("tick_exact_overall_pass"),
        "capacity_overall_pass": v1_artifacts.get("capacity_overall_pass"),
        "model_month": month,
        "model_valid_through": str(v1_artifacts.get("model_valid_through", "")).strip(),
    }

    v3 = {
        "schema_version": 3,
        "symbol": symbol,
        "frozen_at_utc": data.get("frozen_at_utc"),
        "git": data.get("git", {}),
        "bundle": {
            "dir_relpath": str(bundle_dir.relative_to(repo_root)),
            "family": family,
            "month": month,
        },
        "artifacts": new_artifacts,
        "provenance": provenance,
        "deployability": deployability,
        "locked_runtime": data.get("locked_runtime", {}),
        "retrain_policy": data.get("retrain_policy", {}),
        "state_universe": data.get("state_universe", {}),
        "historical_backtest": data.get("historical_backtest", {}),
    }
    _write_lock(lock_path, v3)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bundle_dir", type=Path)
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--family", default="oco_first_touch_clean")
    args = parser.parse_args()
    bundle_dir: Path = args.bundle_dir.resolve()
    repo_root: Path = args.repo_root.resolve()
    family = str(args.family).strip()
    locks = sorted(bundle_dir.glob("*_oco_live_lock.json"))
    if not locks:
        print(f"[migrate-lock-schema] no locks in {bundle_dir}", file=sys.stderr)
        return 2
    for lock_path in locks:
        _migrate_one(lock_path, repo_root, family)
        print(f"[migrate-lock-schema] migrated {lock_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
