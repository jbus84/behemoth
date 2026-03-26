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
import shutil
from datetime import date
from pathlib import Path

CERT_CHECKS_FILENAME = "stage14_jforex_runtime_certification_checks.csv"
MONTHLY_BUILD_ROOT = "configs/research/governance/oco_candidate_builds"
HISTORY_ROOT = "configs/research/governance/oco_history_dukascopy_candidate"


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _last_complete_month(override: str | None = None) -> str:
    if override:
        return override
    today = date.today()
    if today.month == 1:
        return f"{today.year - 1:04d}-12"
    return f"{today.year:04d}-{today.month - 1:02d}"


def _verify_cert(report_dir: str) -> None:
    """Raise SystemExit if cert CSV is missing, stale, or has critical failures."""
    csv_path = _repo_root() / report_dir / CERT_CHECKS_FILENAME
    if not csv_path.exists():
        raise SystemExit(
            f"[promote-live] no cert results found at {csv_path}; "
            "run make monthly-recert first"
        )

    today_str = date.today().isoformat()
    failures: list[str] = []
    stale = False

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
    _verify_cert(args.report_dir)

    print(f"[promote-live] archiving build bundle for {model_month}", flush=True)
    _archive_build_bundle(model_month)

    print(f"[promote-live] locks archived for {model_month}")
    print("Next step: restart the live runner with:")
    print("  make jforex-live")


if __name__ == "__main__":
    main()
