#!/usr/bin/env python3
"""Durable parity-contract harness.

Runs every registered check against a session's artifacts and emits a
markdown report plus a CSV of findings. Non-zero exit on any critical failure.

See docs/superpowers/specs/2026-04-17-jforex-python-parity-assessment-design.md.
"""
from __future__ import annotations

import argparse
import csv
import logging
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
for _path in (REPO_ROOT, SRC_ROOT):
    _path_str = str(_path)
    if _path_str not in sys.path:
        sys.path.insert(0, _path_str)

from behemoth.parity import checks as _checks  # noqa: E402, F401 — sys.path setup above; triggers registration  # isort:skip
from behemoth.parity import registry  # noqa: E402  # isort:skip
from behemoth.parity.types import CheckContext, CheckResult  # noqa: E402  # isort:skip

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("audit_runtime_parity")


def _run_all_checks(ctx: CheckContext) -> list[tuple[str, CheckResult | Exception]]:
    rows: list[tuple[str, CheckResult | Exception]] = []
    for sid in registry.all_surface_ids():
        try:
            rows.append((sid, registry.call(sid, ctx)))
        except Exception as exc:  # noqa: BLE001
            rows.append((sid, exc))
    return rows


def _write_report(
    out_report: Path, run_id: str, rows: list[tuple[str, CheckResult | Exception]]
) -> None:
    out_report.parent.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    lines = [
        f"# Parity Audit — {run_id}",
        "",
        f"_Generated {ts}_",
        "",
        "| Surface | Severity | Pass | Observed | Expected |",
        "|---|---|---|---|---|",
    ]
    for sid, result in rows:
        if isinstance(result, Exception):
            lines.append(f"| `{sid}` | ERROR | ❌ | {type(result).__name__}: {result} | — |")
        else:
            mark = "✅" if result.passed else "❌"
            lines.append(
                f"| `{sid}` | {result.severity} | {mark} | {result.observed} | {result.expected} |"
            )
    out_report.write_text("\n".join(lines) + "\n")


def _write_csv(
    out_csv: Path, run_id: str, rows: list[tuple[str, CheckResult | Exception]]
) -> None:
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    with out_csv.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            "run_id", "surface_id", "severity", "passed",
            "observed", "expected", "evidence",
        ])
        for sid, result in rows:
            if isinstance(result, Exception):
                writer.writerow([
                    run_id, sid, "ERROR", False,
                    f"{type(result).__name__}: {result}",
                    "",
                    "".join(traceback.format_exception_only(type(result), result)),
                ])
            else:
                writer.writerow([
                    run_id, sid, result.severity, result.passed,
                    result.observed, result.expected, result.evidence,
                ])


def _exit_code(rows: list[tuple[str, CheckResult | Exception]]) -> int:
    for _, result in rows:
        if isinstance(result, Exception):
            return 2
        if not result.passed and result.severity in {"critical", "high"}:
            return 1
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--model-month", required=True)
    parser.add_argument("--reconcile-dir", type=Path, required=True)
    parser.add_argument("--governance-lock-dir", type=Path, required=True)
    parser.add_argument("--live-state-db", type=Path, required=True)
    parser.add_argument("--out-report", type=Path, required=True)
    parser.add_argument("--out-csv", type=Path, required=True)
    args = parser.parse_args()

    ctx = CheckContext(
        run_id=args.run_id,
        model_month=args.model_month,
        reconcile_dir=args.reconcile_dir,
        live_state_db_path=args.live_state_db,
        governance_lock_dir=args.governance_lock_dir,
    )
    rows = _run_all_checks(ctx)
    _write_report(args.out_report, args.run_id, rows)
    _write_csv(args.out_csv, args.run_id, rows)
    code = _exit_code(rows)
    if code != 0:
        logger.error("Parity audit FAILED (exit %d) for run_id=%s", code, args.run_id)
    else:
        logger.info("Parity audit PASSED for run_id=%s", args.run_id)
    return code


if __name__ == "__main__":
    sys.exit(main())
