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

from src.behemoth.core.bundle_paths import (  # noqa: E402
    BUNDLE_LAYOUTS,
    bundle_layout_for,
    sha256_file,
)

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

    state_universe = data.get("state_universe", {})
    if state_universe:
        state_universe = _rewrite_state_universe(state_universe, family)

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
        "state_universe": state_universe,
        "historical_backtest": data.get("historical_backtest", {}),
    }
    _write_lock(lock_path, v3)


def _rewrite_state_universe(
    state_universe: dict[str, Any], canonical_family: str = "oco_first_touch"
) -> dict[str, Any]:
    """Rewrite state_universe to canonicalize family names."""
    rows = list(state_universe.get("rows", []))
    if not rows:
        return state_universe
    new_rows: list[dict[str, Any]] = []
    for row in rows:
        new_row = dict(row)
        # Rewrite family from oco_first_touch_clean to canonical_family
        if new_row.get("family") == "oco_first_touch_clean":
            new_row["family"] = canonical_family
        # Rewrite state_id to drop _clean suffix
        state_id = str(new_row.get("state_id", ""))
        if "oco_first_touch_clean" in state_id:
            new_row["state_id"] = state_id.replace("oco_first_touch_clean", canonical_family)
        new_rows.append(new_row)
    return {**state_universe, "rows": new_rows, "count": len(new_rows)}


def _rename_to_family_naming(bundle_dir: Path, canonical_family: str) -> int:
    renamed = 0
    skipped = 0
    for lock_path in sorted(bundle_dir.glob("*_live_lock.json")):
        name = lock_path.name
        # Skip files already in the family-namespaced form. Heuristic: anything
        # that already has `_<known_family>_live_lock.json` is left alone.
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

        # Also rewrite state_universe content if it uses old family names
        state_universe = body.get("state_universe", {})
        if state_universe:
            body["state_universe"] = _rewrite_state_universe(state_universe, canonical_family)

        new_name = f"{symbol_prefix}_{canonical_family}_live_lock.json"
        new_path = lock_path.with_name(new_name)
        new_path.write_text(json.dumps(body, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        lock_path.unlink()
        renamed += 1
        print(f"[migrate] {name} -> {new_name}")

    print(f"[migrate] renamed={renamed} skipped={skipped} dir={bundle_dir}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bundle_dir", type=Path)
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--family", default="oco_first_touch")
    parser.add_argument(
        "--rename-to-family-naming",
        action="store_true",
        help="Rename old-style <symbol>_oco_live_lock.json files to <symbol>_<family>_live_lock.json.",
    )
    parser.add_argument(
        "--canonical-oco-family",
        default="oco_first_touch",
        help=(
            "Canonical family name to use when rewriting the bundle.family field "
            "of old-style locks. Defaults to the project canonical value."
        ),
    )
    args = parser.parse_args()
    bundle_dir: Path = args.bundle_dir.resolve()
    if args.rename_to_family_naming:
        return _rename_to_family_naming(bundle_dir, args.canonical_oco_family)
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
