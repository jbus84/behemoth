#!/usr/bin/env python3
"""Run the definitive monthly Dukascopy-candidate recertification gate.

Auto-derives the model month (last complete calendar month) and test window,
runs the definitive matrix and parity checks, followed by
`make full-stage14-cert`, then reads the stage14 certification checks CSV and
prints a per-symbol go/no-go summary.

Prerequisites:
  1. make retrain-all                    — retrain models to models/oco/
  2. make monthly-build                  — build
       configs/research/governance/oco_candidate_builds/<YYYY-MM>

Exits 0 if all critical checks pass, exits 1 if any fail.
"""

from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
from datetime import date, datetime, timezone
from pathlib import Path

DEFAULT_SYMBOLS = ("EURUSD", "GBPUSD", "USDJPY", "USDCHF", "AUDUSD", "USDCAD")
MONTHLY_BUILD_ROOT = "configs/research/governance/oco_candidate_builds"
CERT_TICK_BATCH_SIZE = "1"
CERT_CHECKS_FILENAME = "stage14_jforex_runtime_certification_checks.csv"
MONTHLY_RECERT_STATUS_FILENAME = "monthly_recert_status.json"
BUNDLE_MODELS_SUBDIR = Path("models/oco_dukascopy_candidate")


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _derive_params(
    model_month_override: str | None = None,
    start_ts_override: str | None = None,
    end_ts_override: str | None = None,
    eval_start_override: str | None = None,
    eval_end_override: str | None = None,
) -> tuple[str, str, str, str, str]:
    """Return (model_month, start_ts, end_ts, eval_start, eval_end)."""
    if model_month_override:
        year_s, month_s = model_month_override.split("-")
        year, month = int(year_s), int(month_s)
    else:
        today = date.today()
        year, month = (today.year - 1, 12) if today.month == 1 else (today.year, today.month - 1)

    model_month = f"{year:04d}-{month:02d}"
    start_ts = start_ts_override or f"{year:04d}-{month:02d}-04T00:00:00Z"
    end_ts = end_ts_override or f"{year:04d}-{month:02d}-09T00:00:00Z"
    eval_start = eval_start_override or f"{year:04d}-{month:02d}-07T00:00:00Z"
    eval_end = eval_end_override or f"{year:04d}-{month:02d}-09T00:00:00Z"
    return model_month, start_ts, end_ts, eval_start, eval_end


def _run_step(cmd: list[str], label: str) -> None:
    print(f"[monthly-recert] {label}", flush=True)
    result = subprocess.run(cmd, cwd=_repo_root())
    if result.returncode != 0:
        print(
            f"[monthly-recert] {label} failed (rc={result.returncode})",
            file=sys.stderr,
            flush=True,
        )
        raise SystemExit(1)


def _read_failures(report_dir: str) -> dict[str, list[dict[str, str]]]:
    """Return {symbol: [failing critical check rows]}."""
    csv_path = _repo_root() / report_dir / CERT_CHECKS_FILENAME
    if not csv_path.exists():
        raise SystemExit(f"[monthly-recert] cert checks CSV not found: {csv_path}")
    failures: dict[str, list[dict[str, str]]] = {}
    with csv_path.open() as f:
        for row in csv.DictReader(f):
            if row["severity"] == "critical" and row["status"] != "pass":
                failures.setdefault(row["symbol"], []).append(row)
    return failures


def _bundle_models_dir(bundle_dir: Path) -> Path:
    return bundle_dir / BUNDLE_MODELS_SUBDIR


def _validate_month_bundle(bundle_dir: Path) -> None:
    index_path = bundle_dir.parent / "index.csv"
    if not index_path.is_file():
        raise SystemExit(f"[monthly-recert] incomplete month build bundle: missing {index_path}")

    model_dir = _bundle_models_dir(bundle_dir)
    if not model_dir.is_dir():
        raise SystemExit(f"[monthly-recert] incomplete month build bundle: missing {model_dir}")

    expected_rows = {(symbol, bundle_dir.name) for symbol in DEFAULT_SYMBOLS}
    seen_rows: set[tuple[str, str]] = set()
    with index_path.open() as f:
        for row in csv.DictReader(f):
            seen_rows.add((str(row.get("symbol", "")).upper().strip(), str(row.get("month", "")).strip()))
    missing_rows = sorted(symbol for symbol, month in expected_rows if (symbol, month) not in seen_rows)
    if missing_rows:
        raise SystemExit(
            "[monthly-recert] incomplete month build bundle: missing index rows for "
            + ",".join(missing_rows)
        )

    for symbol in DEFAULT_SYMBOLS:
        lock_path = bundle_dir / f"{symbol.lower()}_oco_live_lock.json"
        if not lock_path.is_file():
            raise SystemExit(f"[monthly-recert] incomplete month build bundle: missing {lock_path}")
        manifest = json.loads(lock_path.read_text(encoding="utf-8"))
        artifacts = manifest.get("artifacts", {})
        cbm_path = Path(str(artifacts.get("model_cbm_path", "")).strip())
        thr_path = Path(str(artifacts.get("model_threshold_json_path", "")).strip())
        if (not cbm_path.is_file()) or (not thr_path.is_file()):
            raise SystemExit(
                f"[monthly-recert] incomplete month build bundle: missing bundled model artifacts for {symbol}"
            )
        bundle_prefix = bundle_dir.resolve().as_posix().rstrip("/") + "/"
        if (not str(cbm_path.resolve()).startswith(bundle_prefix)) or (
            not str(thr_path.resolve()).startswith(bundle_prefix)
        ):
            raise SystemExit(
                f"[monthly-recert] incomplete month build bundle: non-local model artifact path for {symbol}"
            )


def _require_month_bundle(model_month: str) -> Path:
    bundle_dir = Path(MONTHLY_BUILD_ROOT) / model_month
    if not (_repo_root() / bundle_dir).is_dir():
        raise SystemExit(
            f"[monthly-recert] missing month build bundle: {_repo_root() / bundle_dir}. "
            "run make monthly-build first."
        )
    _validate_month_bundle(_repo_root() / bundle_dir)
    return bundle_dir


def _write_recert_status(model_month: str, report_dir: str, bundle_dir: Path, overall_pass: bool) -> None:
    status_path = _repo_root() / report_dir / MONTHLY_RECERT_STATUS_FILENAME
    status_path.parent.mkdir(parents=True, exist_ok=True)
    status_path.write_text(
        json.dumps(
            {
                "model_month": model_month,
                "bundle_dir": str((_repo_root() / bundle_dir).resolve()),
                "overall_pass": bool(overall_pass),
                "evaluated_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )


def _print_summary(model_month: str, failures: dict[str, list[dict[str, str]]]) -> bool:
    """Print per-symbol summary. Returns True if all critical checks pass."""
    print(f"\n[monthly-recert] {model_month} results")
    all_pass = True
    for symbol in DEFAULT_SYMBOLS:
        if symbol in failures:
            all_pass = False
            for row in failures[symbol]:
                detail = row.get("details", "").strip()
                suffix = f": {detail}" if detail else ""
                print(f"  {symbol:<8}FAIL  {row['check_id']}{suffix}")
        else:
            print(f"  {symbol:<8}PASS")
    if all_pass:
        print("go/no-go: GO — run make promote-live to archive locks")
    else:
        print(f"go/no-go: NO-GO — {len(failures)} symbol(s) failed")
    return all_pass


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-month", help="Override model month YYYY-MM (default: last complete month)")
    parser.add_argument("--start-ts", help="Override matrix start timestamp")
    parser.add_argument("--end-ts", help="Override matrix end timestamp")
    parser.add_argument("--eval-start", help="Override outcome parity eval start timestamp")
    parser.add_argument("--eval-end", help="Override outcome parity eval end timestamp")
    parser.add_argument("--report-dir", default="data/analysis/backtest_reconcile")
    args = parser.parse_args()

    model_month, start_ts, end_ts, eval_start, eval_end = _derive_params(
        model_month_override=args.model_month,
        start_ts_override=args.start_ts,
        end_ts_override=args.end_ts,
        eval_start_override=args.eval_start,
        eval_end_override=args.eval_end,
    )
    bundle_dir = _require_month_bundle(model_month)
    bundle_models_dir = _bundle_models_dir(_repo_root() / bundle_dir)

    print(
        f"[monthly-recert] running for MODEL_MONTH={model_month} "
        f"window={start_ts[:10]}→{end_ts[:10]}",
        flush=True,
    )

    _run_step(
        [
            "make",
            "jforex-dukascopy-matrix",
            f"HISTORY_DIR={MONTHLY_BUILD_ROOT}",
            f"MODELS_DIR={bundle_models_dir}",
            f"MODEL_MONTH={model_month}",
            f"START_TS={start_ts}",
            f"END_TS={end_ts}",
            f"TICK_BATCH_SIZE={CERT_TICK_BATCH_SIZE}",
        ],
        "step 1/4: jforex-dukascopy-matrix",
    )
    _run_step(
        [
            "make",
            "stage13-dukascopy-cert",
            f"LOCK_DIR={bundle_dir}",
            f"RECONCILE_DIR={args.report_dir}",
        ],
        "step 2/4: stage13-dukascopy-cert",
    )
    _run_step(
        [
            "make",
            "local-jforex-parity-matrix",
            f"HISTORY_DIR={MONTHLY_BUILD_ROOT}",
            f"MODELS_DIR={bundle_models_dir}",
            f"MODEL_MONTH={model_month}",
            f"START_TS={eval_start}",
            f"END_TS={eval_end}",
            f"TICK_BATCH_SIZE={CERT_TICK_BATCH_SIZE}",
        ],
        "step 3/4: local-jforex-parity-matrix",
    )
    _run_step(
        [
            "make",
            "full-stage14-cert",
            f"LOCK_DIR={bundle_dir}",
            f"EVAL_START={eval_start}",
            f"EVAL_END={eval_end}",
        ],
        "step 4/4: full-stage14-cert",
    )

    failures = _read_failures(args.report_dir)
    all_pass = _print_summary(model_month, failures)
    _write_recert_status(model_month, args.report_dir, bundle_dir, all_pass)
    if not all_pass:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
