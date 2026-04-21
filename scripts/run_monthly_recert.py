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
MONTHLY_RECERT_RUN_DIRNAME = "monthly_recert"


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
            if (
                row["severity"] == "critical"
                and row["status"] != "pass"
                and not _is_expected_critical_nogo(row)
            ):
                failures.setdefault(row["symbol"], []).append(row)
    return failures


def _is_expected_critical_nogo(row: dict[str, str]) -> bool:
    status = str(row.get("status") or "").strip().lower()
    details = str(row.get("details") or "").strip().lower()
    return (
        "accepted historical non-deployable" in details
        or "accepted non-deployable" in details
        or (
            status in {"nogo", "no_go", "no-go"}
            and (
                "historical_deployable=false" in details
                or "deployable=false" in details
                or "non-deployable" in details
            )
        )
    )


def _read_acceptable_nogos(report_dir: str) -> dict[str, list[dict[str, str]]]:
    csv_path = _repo_root() / report_dir / CERT_CHECKS_FILENAME
    if not csv_path.exists():
        raise SystemExit(f"[monthly-recert] cert checks CSV not found: {csv_path}")
    acceptable: dict[str, list[dict[str, str]]] = {}
    with csv_path.open() as f:
        for row in csv.DictReader(f):
            if (
                row["severity"] == "critical"
                and row["status"] != "pass"
                and _is_expected_critical_nogo(row)
            ):
                acceptable.setdefault(row["symbol"], []).append(row)
    return acceptable


def _bundle_models_dir(bundle_dir: Path) -> Path:
    return bundle_dir / BUNDLE_MODELS_SUBDIR


def _run_report_dir(report_root: str, model_month: str) -> str:
    run_dir = Path(report_root) / model_month / MONTHLY_RECERT_RUN_DIRNAME
    (_repo_root() / run_dir).mkdir(parents=True, exist_ok=True)
    return str(run_dir)


def _validate_stage14_scope(run_report_dir: str, make_vars: dict[str, str]) -> None:
    run_prefix = run_report_dir.rstrip("/")
    allowed_exact = {"RECONCILE_DIR"}
    for key, value in make_vars.items():
        if key in {"LOCK_DIR", "EVAL_START", "EVAL_END"}:
            continue
        normalized = value.split("*", 1)[0].rstrip("/")
        expected_prefix = run_prefix + "/"
        is_valid = normalized == run_prefix or normalized.startswith(expected_prefix)
        if key in allowed_exact:
            is_valid = normalized == run_prefix
        if not is_valid:
            raise SystemExit(
                f"[monthly-recert] Stage 14 inputs/outputs must be bundle-scoped under "
                f"{run_report_dir}: {key}={value}"
            )


def _stage14_make_vars(run_report_dir: str, eval_start: str, eval_end: str) -> dict[str, str]:
    vars_map = {
        "RECONCILE_DIR": run_report_dir,
        "OUT_CSV": f"{run_report_dir}/jforex_outcome_parity_summary.csv",
        "LOCAL_SIGNAL_SUMMARY_GLOB": f"{run_report_dir}/*_local_jforex_signal_parity_summary.csv",
        "LOCAL_EXECUTION_SUMMARY_GLOB": (
            f"{run_report_dir}/*_local_jforex_execution_parity_summary.csv"
        ),
        "LOCAL_LIFECYCLE_SUMMARY_GLOB": (
            f"{run_report_dir}/*_local_jforex_execution_lifecycle_summary.csv"
        ),
        "LOCAL_OPERATIONAL_SUMMARY_GLOB": (
            f"{run_report_dir}/*_local_jforex_operational_ready_summary.csv"
        ),
        "LOCAL_OUTCOME_SUMMARY_GLOB": (
            f"{run_report_dir}/*_local_jforex_outcome_parity_summary.csv"
        ),
        "LOCAL_OUT_SUMMARY_CSV": f"{run_report_dir}/local_jforex_surrogate_summary.csv",
        "LOCAL_OUT_CHECKS_CSV": f"{run_report_dir}/local_jforex_surrogate_checks.csv",
        "STAGE13_SUMMARY_GLOB": f"{run_report_dir}/stage12_stage13_certification_summary.csv",
        "JFOREX_SIGNAL_SUMMARY_GLOB": f"{run_report_dir}/*_jforex_signal_parity_summary.csv",
        "JFOREX_EXECUTION_SUMMARY_GLOB": f"{run_report_dir}/*_jforex_execution_parity_summary.csv",
        "JFOREX_LIFECYCLE_SUMMARY_GLOB": (
            f"{run_report_dir}/*_jforex_execution_lifecycle_summary.csv"
        ),
        "JFOREX_OPERATIONAL_SUMMARY_GLOB": (
            f"{run_report_dir}/*_jforex_operational_ready_summary.csv"
        ),
        "JFOREX_OUTCOME_SUMMARY_GLOB": f"{run_report_dir}/jforex_outcome_parity_summary.csv",
        "LOCAL_SURROGATE_SUMMARY_GLOB": f"{run_report_dir}/local_jforex_surrogate_summary.csv",
        "STAGE14_OUT_SUMMARY_CSV": (
            f"{run_report_dir}/stage14_jforex_runtime_certification_summary.csv"
        ),
        "STAGE14_OUT_CHECKS_CSV": (
            f"{run_report_dir}/stage14_jforex_runtime_certification_checks.csv"
        ),
        "EVAL_START": eval_start,
        "EVAL_END": eval_end,
    }
    _validate_stage14_scope(run_report_dir, vars_map)
    return vars_map


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
            seen_rows.add(
                (str(row.get("symbol", "")).upper().strip(), str(row.get("month", "")).strip())
            )
    missing_rows = sorted(
        symbol for symbol, month in expected_rows if (symbol, month) not in seen_rows
    )
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


def _write_recert_status(
    model_month: str, report_dir: str, bundle_dir: Path, overall_pass: bool
) -> None:
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


def _print_summary(
    model_month: str,
    failures: dict[str, list[dict[str, str]]],
    acceptable_nogos: dict[str, list[dict[str, str]]] | None = None,
) -> bool:
    """Print per-symbol summary. Returns True if all critical checks pass."""
    print(f"\n[monthly-recert] {model_month} results")
    acceptable_nogos = acceptable_nogos or {}
    all_pass = True
    for symbol in DEFAULT_SYMBOLS:
        if symbol in failures:
            all_pass = False
            for row in failures[symbol]:
                detail = row.get("details", "").strip()
                suffix = f": {detail}" if detail else ""
                print(f"  {symbol:<8}FAIL  {row['check_id']}{suffix}")
        elif symbol in acceptable_nogos:
            for row in acceptable_nogos[symbol]:
                detail = row.get("details", "").strip()
                suffix = f": {detail}" if detail else ""
                print(f"  {symbol:<8}NOGO  expected {row['check_id']}{suffix}")
        else:
            print(f"  {symbol:<8}PASS")
    if all_pass:
        print("go/no-go: GO — run make promote-live to archive locks")
    else:
        print(f"go/no-go: NO-GO — {len(failures)} symbol(s) failed")
    return all_pass


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--model-month", help="Override model month YYYY-MM (default: last complete month)"
    )
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
    run_report_dir = _run_report_dir(args.report_dir, model_month)

    print(
        f"[monthly-recert] running for MODEL_MONTH={model_month} "
        f"window={start_ts[:10]}→{end_ts[:10]}",
        flush=True,
    )

    _run_step(
        [
            "make",
            "stage13-dukascopy-cert",
            f"HISTORY_DIR={MONTHLY_BUILD_ROOT}",
            f"MODELS_DIR={bundle_models_dir}",
            f"MODEL_MONTH={model_month}",
            (
                "PREDICTIONS_DIR="
                "data/analysis/tick_opportunity_mining_dukascopy_candidate/wfo_m3to1_oco_fullcap"
            ),
            f"START_TS={start_ts}",
            f"END_TS={end_ts}",
            f"LOCK_DIR={bundle_dir}",
            f"RECONCILE_DIR={run_report_dir}",
            f"OUT_DIR={run_report_dir}",
        ],
        "step 1/4: stage13-dukascopy-cert",
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
            f"REPORT_DIR={run_report_dir}",
        ],
        "step 2/4: jforex-dukascopy-matrix",
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
            f"REPORT_DIR={run_report_dir}",
        ],
        "step 3/4: local-jforex-parity-matrix",
    )
    stage14_vars = _stage14_make_vars(run_report_dir, eval_start, eval_end)
    _run_step(
        ["make", "full-stage14-cert", f"LOCK_DIR={bundle_dir}"]
        + [
            f"TARGET_BUNDLE_DIR={(_repo_root() / bundle_dir).resolve()}",
            f"TARGET_MODEL_MONTH={model_month}",
            "REQUIRE_PROVENANCE=1",
        ]
        + [f"{key}={value}" for key, value in stage14_vars.items()],
        "step 4/4: full-stage14-cert",
    )

    failures = _read_failures(run_report_dir)
    acceptable_nogos = _read_acceptable_nogos(run_report_dir)
    all_pass = _print_summary(model_month, failures, acceptable_nogos)
    _write_recert_status(model_month, run_report_dir, bundle_dir, all_pass)
    if not all_pass:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
