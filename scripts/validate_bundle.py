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

from src.behemoth.core.bundle_paths import BundleIntegrityError, BundlePaths  # noqa: E402


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
