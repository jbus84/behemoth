#!/usr/bin/env python3
"""Run the monthly JForex dukascopy-candidate sync-and-recertification pipeline.

Auto-derives the model month (last complete calendar month) and test window,
runs the candidate artifact sync, then `make jforex-dukascopy-matrix`
followed by `make full-stage14-cert`, then reads the stage14 certification
checks CSV and prints a per-symbol go/no-go summary.

Prerequisites:
  1. make retrain-all                    — retrain models to models/oco/
  2. make freeze-oco-dukascopy-candidate — freeze governance lock to
       configs/research/governance/oco_dukascopy_candidate/

This script now runs the candidate model sync directly before certification,
so the dukascopy candidate directory no longer needs to be prepared manually.

Exits 0 if all critical checks pass, exits 1 if any fail.
"""

from __future__ import annotations

import argparse
import csv
import subprocess
import sys
from datetime import date
from pathlib import Path

DEFAULT_SYMBOLS = ("EURUSD", "GBPUSD", "USDJPY", "USDCHF", "AUDUSD", "USDCAD")
SYNC_LOCK_DIR = "configs/research/governance/oco"
SYNC_SOURCE_MODELS_DIR = "models/oco"
SYNC_TARGET_MODELS_DIR = "models/oco_dukascopy_candidate"
CERT_CHECKS_FILENAME = "stage14_jforex_runtime_certification_checks.csv"


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


def _sync_candidate_models() -> None:
    _run_step(
        [
            "uv",
            "run",
            "python",
            "scripts/sync_candidate_model_artifacts.py",
            "--lock-dir",
            SYNC_LOCK_DIR,
            "--source-models-dir",
            SYNC_SOURCE_MODELS_DIR,
            "--target-models-dir",
            SYNC_TARGET_MODELS_DIR,
            "--symbols",
            ",".join(DEFAULT_SYMBOLS),
        ],
        "step 1/3: sync_candidate_model_artifacts",
    )


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
    lock_dir = f"configs/research/governance/oco_history_dukascopy_candidate/{model_month}"

    print(
        f"[monthly-recert] running for MODEL_MONTH={model_month} "
        f"window={start_ts[:10]}→{end_ts[:10]}",
        flush=True,
    )

    _sync_candidate_models()
    _run_step(
        ["make", "jforex-dukascopy-matrix", f"MODEL_MONTH={model_month}", f"START_TS={start_ts}", f"END_TS={end_ts}"],
        "step 2/3: jforex-dukascopy-matrix",
    )
    _run_step(
        ["make", "full-stage14-cert", f"LOCK_DIR={lock_dir}", f"EVAL_START={eval_start}", f"EVAL_END={eval_end}"],
        "step 3/3: full-stage14-cert",
    )

    failures = _read_failures(args.report_dir)
    all_pass = _print_summary(model_month, failures)
    if not all_pass:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
