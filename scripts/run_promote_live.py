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
import re
import shutil
import subprocess
import sys
from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.behemoth.core.bundle_paths import BundleIntegrityError, BundlePaths  # noqa: E402

CERT_CHECKS_FILENAME = "stage14_jforex_runtime_certification_checks.csv"
CERT_SUMMARY_FILENAME = "stage14_jforex_runtime_certification_summary.csv"
MONTHLY_BUILD_ROOT = "configs/research/governance/oco_candidate_builds"
HISTORY_ROOT = "configs/research/governance/oco_history_dukascopy_candidate"
ACTIVE_ROOT = "configs/research/governance/oco"
MONTHLY_RECERT_STATUS_FILENAME = "monthly_recert_status.json"
COMMIT_SHA_RE = re.compile(r"^[0-9a-fA-F]{40}$")
DEFAULT_REQUIRED_GO_SYMBOLS = ("EURUSD", "GBPUSD", "USDJPY", "USDCHF", "AUDUSD", "USDCAD")


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _last_complete_month(override: str | None = None) -> str:
    if override:
        return override
    today = date.today()
    if today.month == 1:
        return f"{today.year - 1:04d}-12"
    return f"{today.year:04d}-{today.month - 1:02d}"


def _verify_dag_provenance(
    status: dict[str, object],
    model_month: str,
    repo_root: Path | None = None,
    *,
    current_commit: str | None = None,
) -> None:
    required = {
        "dag_node_id",
        "model_month",
        "overall_pass",
        "process_verdict",
        "release_decision",
        "required_go_symbols",
        "target_branch",
        "target_commit",
        "git_dirty",
        "symbol_decisions",
        "lock_fingerprint",
    }
    missing = sorted(key for key in required if key not in status)
    if missing:
        raise SystemExit(
            "[promote-live] missing DAG provenance in monthly recert status: " + ",".join(missing)
        )
    if str(status["dag_node_id"]) != "monthly_recert":
        raise SystemExit(f"[promote-live] unexpected DAG node id: {status['dag_node_id']}")
    if str(status["model_month"]) != model_month:
        raise SystemExit(
            f"[promote-live] cert status month mismatch: requested {model_month}, got {status['model_month']}"
        )
    if str(status["process_verdict"]).upper() != "PASS":
        raise SystemExit("[promote-live] monthly recert process_verdict is not PASS")
    if str(status["release_decision"]).upper() != "GO":
        raise SystemExit("[promote-live] monthly recert release_decision is not GO")
    if str(status["target_branch"]) != "main":
        raise SystemExit(
            f"[promote-live] target_branch must be main for promotion, got {status['target_branch']}"
        )
    if bool(status["git_dirty"]):
        raise SystemExit("[promote-live] monthly recert was produced from dirty git state")
    if not isinstance(status["symbol_decisions"], dict) or not status["symbol_decisions"]:
        raise SystemExit("[promote-live] monthly recert symbol_decisions missing or empty")
    _verify_required_go_symbols(status)

    certified = str(status["target_commit"]).strip()
    if not certified:
        raise SystemExit("[promote-live] target_commit missing in monthly recert status")
    if not COMMIT_SHA_RE.fullmatch(certified):
        raise SystemExit(
            f"[promote-live] target_commit must be a full 40-character git SHA, got {certified!r}"
        )
    if current_commit is not None:
        repo_root_for_git = repo_root or _repo_root()
        result = subprocess.run(
            ["git", "-C", str(repo_root_for_git), "merge-base", certified, current_commit],
            capture_output=True,
            text=True,
        )
        merge_base = result.stdout.strip()
        if merge_base != certified:
            raise SystemExit(
                f"[promote-live] certified commit {certified[:8]} is not an ancestor of "
                f"current HEAD {current_commit[:8]}; re-run make monthly-recert"
            )


def _required_go_symbols(status: dict[str, object]) -> tuple[str, ...]:
    raw = status.get("required_go_symbols", DEFAULT_REQUIRED_GO_SYMBOLS)
    if not isinstance(raw, list) or not raw:
        raise SystemExit("[promote-live] monthly recert required_go_symbols missing or empty")
    symbols = tuple(str(item).strip().upper() for item in raw if str(item).strip())
    if not symbols:
        raise SystemExit("[promote-live] monthly recert required_go_symbols missing or empty")
    return symbols


def _verify_required_go_symbols(status: dict[str, object]) -> None:
    decisions = status.get("symbol_decisions", {})
    if not isinstance(decisions, dict):
        raise SystemExit("[promote-live] monthly recert symbol_decisions missing or invalid")
    required = _required_go_symbols(status)
    missing_or_no_go = [
        symbol for symbol in required if str(decisions.get(symbol, "")).strip().upper() != "GO"
    ]
    if missing_or_no_go:
        raise SystemExit(
            "[promote-live] required GO symbols are not GO: " + ",".join(missing_or_no_go)
        )


def _verify_cert(
    report_dir: str,
    model_month: str,
    repo_root: Path | None = None,
    *,
    current_commit: str | None = None,
) -> None:
    """Raise SystemExit if cert CSV is missing, stale, or has critical failures."""
    repo_root = repo_root or _repo_root()
    csv_path = repo_root / report_dir / CERT_CHECKS_FILENAME
    if not csv_path.exists():
        raise SystemExit(
            f"[promote-live] no cert results found at {csv_path}; run make monthly-recert first"
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
    _verify_dag_provenance(status, model_month, repo_root, current_commit=current_commit)
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
            if row["severity"] == "critical" and row["status"] not in ("PASS", "NO_GO"):
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


def _load_go_symbols(report_dir: str, model_month: str, repo_root: Path | None = None) -> list[str]:
    repo_root = repo_root or _repo_root()
    summary_path = repo_root / report_dir / CERT_SUMMARY_FILENAME
    if not summary_path.exists():
        raise SystemExit(
            f"[promote-live] no cert summary found at {summary_path}; run make monthly-recert first"
        )
    with summary_path.open() as f:
        rows = list(csv.DictReader(f))
    if not rows:
        raise SystemExit(
            f"[promote-live] empty cert summary at {summary_path}; rerun make monthly-recert"
        )
    process_statuses = {str(row.get("process_status", "")).strip().upper() for row in rows}
    if process_statuses != {"PASS"}:
        raise SystemExit(
            f"[promote-live] process_status is not PASS for {model_month}; rerun make monthly-recert"
        )
    return sorted(
        {
            str(row.get("symbol", "")).strip().upper()
            for row in rows
            if str(row.get("go_decision", "")).strip().upper() == "GO"
        }
    )


def _copy_candidate_models(model_month: str) -> None:
    """Copy model .cbm and .json files into models/oco_dukascopy_candidate/.

    Reads model paths from the promoted lock files in oco_history_dukascopy_candidate
    so the source of truth is always the lock manifest.
    """
    dest_dir = _repo_root() / "models" / "oco_dukascopy_candidate"
    dest_dir.mkdir(parents=True, exist_ok=True)
    lock_dir = _repo_root() / HISTORY_ROOT / model_month
    copied: list[str] = []
    for lock_path in sorted(lock_dir.glob("*_oco_live_lock.json")):
        try:
            bp = BundlePaths.from_lock(lock_path)
            src = bp.model_cbm()
            dest = dest_dir / src.name
            shutil.copy2(src, dest)
            copied.append(src.name)
            src_thr = bp.model_threshold_json()
            dest_thr = dest_dir / src_thr.name
            shutil.copy2(src_thr, dest_thr)
            copied.append(src_thr.name)
        except BundleIntegrityError:
            # Legacy v1 fallback
            with lock_path.open() as f:
                manifest = json.load(f)
            artifacts = manifest.get("artifacts", {})
            for key in ("model_cbm_path", "model_threshold_json_path"):
                rel = artifacts.get(key, "")
                if not rel:
                    continue
                src = _repo_root() / rel
                if not src.exists():
                    raise SystemExit(f"[promote-live] model file not found: {src}")
                dest = dest_dir / src.name
                shutil.copy2(src, dest)
                copied.append(src.name)
    if not copied:
        raise SystemExit(
            f"[promote-live] no model files found for {model_month}; "
            "check that monthly-build ran successfully"
        )
    print(f"[promote-live] copied {len(copied)} model files to models/oco_dukascopy_candidate/")


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
    _copy_candidate_models(model_month)


def _update_active_governance(model_month: str, go_symbols: list[str]) -> None:
    source_dir = _repo_root() / HISTORY_ROOT / model_month
    active_dir = _repo_root() / ACTIVE_ROOT
    active_dir.mkdir(parents=True, exist_ok=True)

    for path in active_dir.glob("*_oco_live_lock.json"):
        path.unlink()
    for path in active_dir.glob("*_oco_allowed_states.csv"):
        path.unlink()

    for symbol in go_symbols:
        lower = symbol.lower()
        source_lock = source_dir / f"{lower}_oco_live_lock.json"
        if not source_lock.exists():
            raise SystemExit(
                f"[promote-live] missing archived lock for GO symbol {symbol}: {source_lock}"
            )
        shutil.copy2(source_lock, active_dir / source_lock.name)
        source_states = source_dir / f"{lower}_oco_allowed_states.csv"
        if source_states.exists():
            shutil.copy2(source_states, active_dir / source_states.name)


def _rewrite_path_prefix(path_value: str, source_dir: Path, target_dir: Path) -> str:
    source_prefix = source_dir.as_posix().rstrip("/") + "/"
    if path_value == source_dir.as_posix():
        return target_dir.as_posix()
    if path_value.startswith(source_prefix):
        return target_dir.as_posix() + path_value[len(source_dir.as_posix()) :]
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
        if int(manifest.get("schema_version", 0)) == 2:
            # v3 locks use bundle-relative paths; no rewriting needed.
            continue
        rewritten = _rewrite_manifest_paths(manifest, source_dir, target_dir)
        with lock_path.open("w") as f:
            json.dump(rewritten, f, indent=2)
            f.write("\n")


def _rebuild_promoted_index(target_root: Path) -> None:
    rows: list[dict[str, object]] = []
    for lock_path in sorted(target_root.glob("*/*_oco_live_lock.json")):
        try:
            bp = BundlePaths.from_lock(lock_path)
            rows.append(
                {
                    "symbol": bp.symbol,
                    "month": lock_path.parent.name,
                    "lock_path": str(lock_path),
                    "allowed_states_path": str(bp.allowed_states_csv()),
                    "model_cbm_path": str(bp.model_cbm()),
                    "threshold_json_path": str(bp.model_threshold_json()),
                    "candidates_count": int(
                        json.loads(lock_path.read_text(encoding="utf-8"))
                        .get("state_universe", {})
                        .get("count", 0)
                        or 0
                    ),
                    "production_cap_pips": float(
                        json.loads(lock_path.read_text(encoding="utf-8"))
                        .get("locked_runtime", {})
                        .get("production_cap_pips", 0.0)
                        or 0.0
                    ),
                    "live_deployable": bp.live_deployable,
                }
            )
        except BundleIntegrityError:
            # Legacy v1 fallback
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
                    "production_cap_pips": float(
                        locked_runtime.get("production_cap_pips", 0.0) or 0.0
                    ),
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
    current_commit = subprocess.run(
        ["git", "-C", str(_repo_root()), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    _verify_cert(args.report_dir, model_month, current_commit=current_commit)

    print(f"[promote-live] archiving build bundle for {model_month}", flush=True)
    _archive_build_bundle(model_month)
    go_symbols = _load_go_symbols(args.report_dir, model_month)
    _update_active_governance(model_month, go_symbols)

    print(f"[promote-live] locks archived for {model_month}")
    print("Next step: restart the live runner with:")
    print("  make jforex-live")


if __name__ == "__main__":
    main()
