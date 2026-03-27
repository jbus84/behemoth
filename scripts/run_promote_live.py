#!/usr/bin/env python3
"""Promote the monthly recertification to live by archiving governance locks.

Verifies the stage14 cert passed today for the derived model month, then copies
the built monthly certification bundle from
configs/research/governance/oco_candidate_builds/<YYYY-MM> into
configs/research/governance/oco_history_dukascopy_candidate/<YYYY-MM>.

After this script completes successfully, restart the live runner with:
  make jforex-live
"""

from __future__ import annotations

import argparse
import csv
import json
import shutil
from datetime import date
from pathlib import Path

CERT_CHECKS_FILENAME = "stage14_jforex_runtime_certification_checks.csv"
MONTHLY_BUILD_ROOT = "configs/research/governance/oco_candidate_builds"
HISTORY_ROOT = "configs/research/governance/oco_history_dukascopy_candidate"
MONTHLY_RECERT_STATUS_FILENAME = "monthly_recert_status.json"


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _last_complete_month(override: str | None = None) -> str:
    if override:
        return override
    today = date.today()
    if today.month == 1:
        return f"{today.year - 1:04d}-12"
    return f"{today.year:04d}-{today.month - 1:02d}"


def _verify_cert(report_dir: str, model_month: str, repo_root: Path | None = None) -> None:
    """Raise SystemExit if cert CSV is missing, stale, or has critical failures."""
    repo_root = repo_root or _repo_root()
    csv_path = repo_root / report_dir / CERT_CHECKS_FILENAME
    if not csv_path.exists():
        raise SystemExit(
            f"[promote-live] no cert results found at {csv_path}; "
            "run make monthly-recert first"
        )
    status_path = repo_root / report_dir / MONTHLY_RECERT_STATUS_FILENAME
    if not status_path.exists():
        raise SystemExit(
            f"[promote-live] monthly recert status not found at {status_path}; "
            "run make monthly-recert first"
        )

    today_str = date.today().isoformat()
    failures: list[str] = []
    stale = False
    status = json.loads(status_path.read_text(encoding="utf-8"))
    status_month = str(status.get("model_month", "")).strip()
    status_pass = bool(status.get("overall_pass", False))
    status_day = str(status.get("evaluated_at_utc", ""))[:10]

    if status_month != model_month:
        raise SystemExit(
            f"[promote-live] cert status month mismatch: requested {model_month}, got {status_month or 'unknown'}"
        )
    if not status_pass:
        raise SystemExit(
            f"[promote-live] monthly recert status for {model_month} is not passing; rerun make monthly-recert"
        )
    if status_day != today_str:
        raise SystemExit(
            f"[promote-live] cert status is stale (not from today {today_str}); rerun make monthly-recert"
        )

    with csv_path.open() as f:
        for row in csv.DictReader(f):
            evaluated = row.get("evaluated_at_utc", "")[:10]
            if evaluated and evaluated != today_str:
                stale = True
            if row["severity"] == "critical" and row["status"] != "pass":
                failures.append(f"  {row['symbol']}: {row['check_id']}")

    if stale:
        raise SystemExit(
            f"[promote-live] cert results are stale (not from today {today_str}); "
            "rerun make monthly-recert"
        )
    if failures:
        lines = "\n".join(failures)
        raise SystemExit(
            f"[promote-live] cert failed for {len(failures)} check(s); cannot promote:\n{lines}"
        )


def _archive_build_bundle(model_month: str) -> None:
    source_dir = _repo_root() / MONTHLY_BUILD_ROOT / model_month
    target_root = _repo_root() / HISTORY_ROOT
    target_dir = target_root / model_month

    if not source_dir.is_dir():
        raise SystemExit(
            f"[promote-live] missing monthly build bundle: {source_dir}. "
            "run make monthly-build and make monthly-recert first"
        )

    target_root.mkdir(parents=True, exist_ok=True)
    if target_dir.exists():
        if target_dir.is_dir():
            shutil.rmtree(target_dir)
        else:
            target_dir.unlink()
    shutil.copytree(source_dir, target_dir)
    _rewrite_promoted_lock_paths(source_dir, target_dir)
    _rebuild_promoted_index(target_root)


def _rewrite_path_prefix(path_value: str, source_dir: Path, target_dir: Path) -> str:
    source_prefix = source_dir.as_posix().rstrip("/") + "/"
    if path_value == source_dir.as_posix():
        return target_dir.as_posix()
    if path_value.startswith(source_prefix):
        return target_dir.as_posix() + path_value[len(source_dir.as_posix()):]
    return path_value


def _rewrite_manifest_paths(value, source_dir: Path, target_dir: Path):
    if isinstance(value, dict):
        return {
            key: _rewrite_manifest_paths(item, source_dir, target_dir)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_rewrite_manifest_paths(item, source_dir, target_dir) for item in value]
    if isinstance(value, str):
        return _rewrite_path_prefix(value, source_dir, target_dir)
    return value


def _rewrite_promoted_lock_paths(source_dir: Path, target_dir: Path) -> None:
    for lock_path in target_dir.rglob("*_oco_live_lock.json"):
        with lock_path.open() as f:
            manifest = json.load(f)
        rewritten = _rewrite_manifest_paths(manifest, source_dir, target_dir)
        with lock_path.open("w") as f:
            json.dump(rewritten, f, indent=2)
            f.write("\n")


def _rebuild_promoted_index(target_root: Path) -> None:
    rows: list[dict[str, object]] = []
    for lock_path in sorted(target_root.glob("*/*_oco_live_lock.json")):
        with lock_path.open() as f:
            manifest = json.load(f)
        artifacts = manifest.get("artifacts", {})
        state_universe = manifest.get("state_universe", {})
        locked_runtime = manifest.get("locked_runtime", {})
        rows.append(
            {
                "symbol": str(manifest.get("symbol", "")).upper(),
                "month": lock_path.parent.name,
                "lock_path": str(lock_path),
                "allowed_states_path": str(artifacts.get("reduced_states_csv_path", "")),
                "model_cbm_path": str(artifacts.get("model_cbm_path", "")),
                "threshold_json_path": str(artifacts.get("model_threshold_json_path", "")),
                "candidates_count": int(state_universe.get("count", 0) or 0),
                "production_cap_pips": float(locked_runtime.get("production_cap_pips", 0.0) or 0.0),
                "live_deployable": bool(artifacts.get("live_deployable", False)),
            }
        )

    index_path = target_root / "index.csv"
    columns = [
        "symbol",
        "month",
        "lock_path",
        "allowed_states_path",
        "model_cbm_path",
        "threshold_json_path",
        "candidates_count",
        "production_cap_pips",
        "live_deployable",
    ]
    with index_path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        writer.writeheader()
        for row in sorted(rows, key=lambda item: (str(item["symbol"]), str(item["month"]))):
            writer.writerow(row)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--model-month",
        help="Override model month YYYY-MM (default: last complete month)",
    )
    parser.add_argument("--report-dir", default="data/analysis/backtest_reconcile")
    args = parser.parse_args()

    model_month = _last_complete_month(args.model_month)

    print(f"[promote-live] verifying cert for {model_month}", flush=True)
    _verify_cert(args.report_dir, model_month)

    print(f"[promote-live] archiving build bundle for {model_month}", flush=True)
    _archive_build_bundle(model_month)

    print(f"[promote-live] locks archived for {model_month}")
    print("Next step: restart the live runner with:")
    print("  make jforex-live")


if __name__ == "__main__":
    main()
