#!/usr/bin/env python3
"""Run the unified Stage 12 -> Stage 13 certification flow.

The orchestration layer is intentionally small:
- Stage 12 is generated per symbol first.
- Stage 13 is then evaluated from the Stage 12 outputs plus Dukascopy/TestClient evidence.
- Final outputs resolve to PASS/FAIL and GO/NO_GO only.
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.generate_dukascopy_testclient_artifacts import (
    DukascopyTestClientArtifactOutputs,
    generate_dukascopy_testclient_artifacts,
)
from scripts.validate_api_parity import run as validate_api_parity_run
from scripts.validate_stage13_dukascopy_testclient import build_stage13_artifacts

DEFAULT_SYMBOLS = ["EURUSD", "GBPUSD", "USDJPY", "USDCHF", "AUDUSD", "USDCAD"]
DEFAULT_PREDICTIONS_DIR = Path("data/analysis/tick_opportunity_mining/wfo_m3to1_oco_fullcap")
DEFAULT_MODELS_DIR = Path("models/oco")
DEFAULT_TICK_ROOT = Path("/Users/danielfisher/Desktop/dukascopy_ticks")
DEFAULT_START_TS = "2025-07-07T00:00:00Z"
DEFAULT_END_TS = "2025-07-09T00:00:00Z"
DEFAULT_RECONCILE_DIR = Path("data/analysis/backtest_reconcile")
DEFAULT_HISTORY_DIR = Path("configs/research/governance/oco_history_dukascopy_candidate")
FINAL_SUMMARY_FILENAME = "stage12_stage13_certification_summary.csv"


def _now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _normalize_symbol(symbol: str) -> str:
    cleaned = str(symbol).strip().upper()
    if not cleaned:
        raise ValueError("symbol must be non-empty")
    return cleaned


def _normalize_symbols(symbols: list[str]) -> list[str]:
    seen: set[str] = set()
    normalized: list[str] = []
    for symbol in symbols:
        cleaned = _normalize_symbol(symbol)
        if cleaned in seen:
            continue
        seen.add(cleaned)
        normalized.append(cleaned)
    return normalized


def _normalize_outcome(value: Any, default: str = "FAIL") -> str:
    txt = str(value).strip().upper()
    if txt in {"PASS", "FAIL"}:
        return txt
    return default


def _normalize_go_decision(value: Any, default: str = "NO_GO") -> str:
    txt = str(value).strip().upper()
    if txt in {"GO", "NO_GO"}:
        return txt
    return default


def _as_mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    return {}


def _stage12_summary_path(out_dir: Path, symbol: str) -> Path:
    return out_dir / f"{symbol}_stage12_api_parity_summary.csv"


def _stage13_summary_path(out_dir: Path) -> Path:
    return out_dir / "stage13_dukascopy_testclient_summary.csv"


def _write_stage12_failure_summary(path: Path, symbol: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(
        [
            {
                "symbol": symbol,
                "signal_parity_pass": False,
                "execution_parity_pass": True,
                "stage12_api_parity_pass": False,
                "selected_missing_expected": 1,
                "selected_extra_runtime": 0,
                "execution_failed_checks_high_critical": 0,
                "stage12_api_parity_verdict": "red",
                "evaluated_at_utc": _now_utc(),
            }
        ]
    ).to_csv(path, index=False)


def _latest_model_json(models_dir: Path, symbol: str) -> Path | None:
    candidates = sorted(models_dir.glob(f"{symbol}_model_*.json"))
    return candidates[-1] if candidates else None


def _resolve_model_json(models_dir: Path, symbol: str, model_month: str | None) -> Path | None:
    if model_month:
        explicit = models_dir / f"{symbol}_model_{model_month}.json"
        if explicit.exists():
            return explicit
    return _latest_model_json(models_dir, symbol)


def _extract_model_month(path: Path, symbol: str) -> str | None:
    match = re.fullmatch(rf"{re.escape(symbol)}_model_(\d{{4}}-\d{{2}})\.json", path.name)
    if match:
        return match.group(1)
    return None


def _resolve_model_month(
    requested_model_month: str | None,
    models_dir: Path,
    symbols: list[str],
) -> str | None:
    if requested_model_month:
        return str(requested_model_month)

    months: list[str] = []
    for symbol in _normalize_symbols(symbols):
        latest = _latest_model_json(models_dir, symbol)
        if latest is None:
            continue
        month = _extract_model_month(latest, symbol)
        if month:
            months.append(month)
    return max(months) if months else None


def _stage12_default_runner(
    *,
    symbol: str,
    predictions_dir: Path,
    models_dir: Path,
    model_month: str | None,
    out_dir: Path,
    tolerance: float = 0.0,
) -> dict[str, Any]:
    symbol = _normalize_symbol(symbol)
    summary_path = _stage12_summary_path(out_dir, symbol)
    predictions_path = predictions_dir / f"{symbol}_oco_monthly_predictions.parquet"
    threshold_json = _resolve_model_json(models_dir, symbol, model_month)

    if not predictions_path.exists() or threshold_json is None:
        _write_stage12_failure_summary(summary_path, symbol)
        return {
            "symbol": symbol,
            "certification_outcome": "FAIL",
            "go_decision": "NO_GO",
            "summary_path": str(summary_path),
        }

    success = validate_api_parity_run(
        symbol=symbol,
        predictions_parquet=predictions_path,
        threshold_json=threshold_json,
        tolerance=tolerance,
        allow_empty_month=False,
        out_summary=summary_path,
    )

    if not summary_path.exists():
        _write_stage12_failure_summary(summary_path, symbol)

    try:
        summary_df = pd.read_csv(summary_path)
        row = summary_df.iloc[-1].to_dict() if not summary_df.empty else {}
    except Exception:
        row = {}

    stage12_pass = bool(row.get("stage12_api_parity_pass", success))
    return {
        "symbol": symbol,
        "certification_outcome": "PASS" if stage12_pass else "FAIL",
        "go_decision": "GO" if stage12_pass else "NO_GO",
        "summary_path": str(summary_path),
        "stage12_api_parity_pass": stage12_pass,
        "stage12_summary_row": row,
    }


def _stage13_default_runner(
    *,
    symbols: list[str],
    lock_dir: Path,
    out_dir: Path,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    stage12_glob = str(out_dir / "*_stage12_api_parity_summary.csv")
    replay_glob = str(out_dir / "*_dukascopy_testclient_replay_summary.csv")
    return build_stage13_artifacts(
        symbols=symbols,
        lock_dir=lock_dir,
        stage12_api_parity_summary_glob=stage12_glob,
        dukascopy_testclient_replay_summary_glob=replay_glob,
        reconcile_dir=out_dir,
        out_summary_csv=_stage13_summary_path(out_dir),
        out_checks_csv=out_dir / "stage13_dukascopy_testclient_checks.csv",
        report_out=out_dir / "stage13_dukascopy_testclient_report.md",
        snapshot_out=out_dir / "stage_13_snapshot.md",
    )


def _bool_from_summary(path: Path, candidates: tuple[str, ...]) -> bool:
    try:
        df = pd.read_csv(path)
    except Exception:
        return False
    if df.empty:
        return False
    row = df.iloc[-1]
    for candidate in candidates:
        if candidate not in row.index:
            continue
        value = row.get(candidate)
        if pd.isna(value):
            continue
        if isinstance(value, bool):
            return value
        txt = str(value).strip().lower()
        if txt in {"1", "true", "yes", "y", "pass", "green"}:
            return True
        if txt in {"0", "false", "no", "n", "fail", "red"}:
            return False
    return False


def _runtime_events_rows(path: Path) -> list[dict[str, Any]]:
    try:
        df = pd.read_csv(path)
    except Exception:
        return []
    if df.empty:
        return []
    return df.to_dict(orient="records")


def _run_stage13_matrix_replay(
    *,
    symbol: str,
    start_ts: str,
    end_ts: str,
    model_month: str,
    models_dir: Path,
    history_dir: Path,
    predictions_dir: Path,
    tick_root: Path,
    report_dir: Path,
) -> dict[str, Any]:
    required_env = (
        "BEHEMOTH_JFOREX_JNLP_URI",
        "BEHEMOTH_JFOREX_USERNAME",
        "BEHEMOTH_JFOREX_PASSWORD",
    )
    missing = [name for name in required_env if not os.environ.get(name)]
    if missing:
        return {
            "signal_pass": False,
            "execution_pass": False,
            "runtime_events_rows": [],
            "details": "missing required JForex credentials: " + ", ".join(missing),
        }

    cmd = [
        sys.executable,
        "scripts/run_jforex_dukascopy_matrix.py",
        "--symbols",
        symbol,
        "--start-ts",
        start_ts,
        "--end-ts",
        end_ts,
        "--model-month",
        model_month,
        "--models-dir",
        str(models_dir),
        "--history-dir",
        str(history_dir),
        "--predictions-dir",
        str(predictions_dir),
        "--tick-root",
        str(tick_root),
        "--report-dir",
        str(report_dir),
    ]
    completed = subprocess.run(cmd, check=False, capture_output=True, text=True)
    signal_summary = report_dir / f"{symbol}_jforex_signal_parity_summary.csv"
    execution_summary = report_dir / f"{symbol}_jforex_execution_parity_summary.csv"
    runtime_events = report_dir / f"{symbol}_jforex_runtime_events.csv"

    if completed.returncode != 0:
        return {
            "signal_pass": False,
            "execution_pass": False,
            "runtime_events_rows": _runtime_events_rows(runtime_events),
            "details": completed.stderr.strip() or completed.stdout.strip(),
        }

    return {
        "signal_pass": _bool_from_summary(
            signal_summary,
            ("jforex_signal_parity_pass", "signal_parity_pass", "overall_pass"),
        ),
        "execution_pass": _bool_from_summary(
            execution_summary,
            ("jforex_execution_parity_pass", "execution_parity_pass", "overall_pass"),
        ),
        "runtime_events_rows": _runtime_events_rows(runtime_events),
    }


def _generate_stage13_replay_artifacts(
    *,
    symbols: list[str],
    start_ts: str,
    end_ts: str,
    model_month: str,
    models_dir: Path,
    history_dir: Path,
    predictions_dir: Path,
    tick_root: Path,
    out_dir: Path,
) -> dict[str, DukascopyTestClientArtifactOutputs]:
    outputs: dict[str, DukascopyTestClientArtifactOutputs] = {}
    for symbol in symbols:
        outputs[symbol] = generate_dukascopy_testclient_artifacts(
            symbol=symbol,
            tick_root=tick_root,
            out_dir=out_dir,
            start_ts=start_ts,
            end_ts=end_ts,
            replay_impl=lambda **_: _run_stage13_matrix_replay(
                symbol=symbol,
                start_ts=start_ts,
                end_ts=end_ts,
                model_month=model_month,
                models_dir=models_dir,
                history_dir=history_dir,
                predictions_dir=predictions_dir,
                tick_root=tick_root,
                report_dir=out_dir,
            ),
        )
    return outputs


def _resolved_stage_row(
    *,
    symbol: str,
    stage12_row: Mapping[str, Any],
    stage13_row: Mapping[str, Any] | None,
) -> dict[str, Any]:
    stage12_outcome = _normalize_outcome(stage12_row.get("certification_outcome"))
    stage12_go = _normalize_go_decision(stage12_row.get("go_decision"))

    if stage12_outcome != "PASS":
        return {
            "symbol": symbol,
            "stage12_certification_outcome": stage12_outcome,
            "stage12_go_decision": stage12_go,
            "stage13_attempted": False,
            "stage13_certification_outcome": "FAIL",
            "stage13_go_decision": "NO_GO",
            "certification_outcome": "FAIL",
            "go_decision": "NO_GO",
        }

    stage13_row = _as_mapping(stage13_row)
    stage13_outcome = _normalize_outcome(stage13_row.get("certification_outcome"))
    stage13_go = _normalize_go_decision(stage13_row.get("go_decision"))

    return {
        "symbol": symbol,
        "stage12_certification_outcome": stage12_outcome,
        "stage12_go_decision": stage12_go,
        "stage13_attempted": True,
        "stage13_certification_outcome": stage13_outcome,
        "stage13_go_decision": stage13_go,
        "certification_outcome": stage13_outcome,
        "go_decision": stage13_go,
    }


def run_stage12_stage13_certification(
    *,
    symbols: list[str],
    stage12_runner: Callable[[str], Mapping[str, Any]],
    stage13_runner: Callable[[str], Mapping[str, Any]],
    out_dir: Path,
) -> list[dict[str, Any]]:
    """Run Stage 12 first, then Stage 13 for Stage 12-passing symbols only."""
    normalized_symbols = _normalize_symbols(symbols)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    rows: list[dict[str, Any]] = []
    for symbol in normalized_symbols:
        stage12_row = _as_mapping(stage12_runner(symbol))
        stage12_outcome = _normalize_outcome(stage12_row.get("certification_outcome"))
        if stage12_outcome != "PASS":
            rows.append(_resolved_stage_row(symbol=symbol, stage12_row=stage12_row, stage13_row=None))
            continue
        stage13_row = _as_mapping(stage13_runner(symbol))
        rows.append(_resolved_stage_row(symbol=symbol, stage12_row=stage12_row, stage13_row=stage13_row))

    final_summary = pd.DataFrame(rows)
    final_summary.to_csv(out_dir / FINAL_SUMMARY_FILENAME, index=False)
    return rows


def _combine_final_rows(
    *,
    symbols: list[str],
    stage12_rows: dict[str, dict[str, Any]],
    stage13_rows: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for symbol in symbols:
        rows.append(
            _resolved_stage_row(
                symbol=symbol,
                stage12_row=stage12_rows.get(symbol, {}),
                stage13_row=stage13_rows.get(symbol, {}),
            )
        )
    return rows


def _parse_symbols(raw: str) -> list[str]:
    return _normalize_symbols([part for part in str(raw).split(",") if part.strip()])


def _resolve_lock_dir(lock_dir: Path | None, history_dir: Path, model_month: str) -> Path:
    if lock_dir is not None:
        return Path(lock_dir)
    return Path(history_dir) / str(model_month)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbols", default=",".join(DEFAULT_SYMBOLS))
    parser.add_argument("--predictions-dir", type=Path, default=DEFAULT_PREDICTIONS_DIR)
    parser.add_argument("--models-dir", type=Path, default=DEFAULT_MODELS_DIR)
    parser.add_argument("--tick-root", type=Path, default=DEFAULT_TICK_ROOT)
    parser.add_argument("--start-ts", default=DEFAULT_START_TS)
    parser.add_argument("--end-ts", default=DEFAULT_END_TS)
    parser.add_argument("--model-month")
    parser.add_argument("--history-dir", type=Path, default=DEFAULT_HISTORY_DIR)
    parser.add_argument("--lock-dir", type=Path)
    parser.add_argument("--reconcile-dir", type=Path, default=DEFAULT_RECONCILE_DIR)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_RECONCILE_DIR)
    parser.add_argument("--stage12-tolerance", type=float, default=0.0)
    args = parser.parse_args(argv)

    symbols = _parse_symbols(args.symbols)
    resolved_model_month = _resolve_model_month(args.model_month, Path(args.models_dir), symbols)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    reconcile_dir = Path(args.reconcile_dir)
    reconcile_dir.mkdir(parents=True, exist_ok=True)
    lock_dir = _resolve_lock_dir(
        args.lock_dir,
        Path(args.history_dir),
        resolved_model_month or "",
    )

    stage12_rows: dict[str, dict[str, Any]] = {}
    for symbol in symbols:
        stage12_rows[symbol] = _stage12_default_runner(
            symbol=symbol,
            predictions_dir=Path(args.predictions_dir),
            models_dir=Path(args.models_dir),
            model_month=resolved_model_month,
            out_dir=reconcile_dir,
            tolerance=args.stage12_tolerance,
        )

    eligible_stage13_symbols = [
        symbol
        for symbol in symbols
        if _normalize_outcome(stage12_rows.get(symbol, {}).get("certification_outcome")) == "PASS"
    ]
    if eligible_stage13_symbols:
        _generate_stage13_replay_artifacts(
            symbols=eligible_stage13_symbols,
            start_ts=args.start_ts,
            end_ts=args.end_ts,
            model_month=resolved_model_month or "",
            models_dir=Path(args.models_dir),
            history_dir=Path(args.history_dir),
            predictions_dir=Path(args.predictions_dir),
            tick_root=Path(args.tick_root),
            out_dir=reconcile_dir,
        )

    stage13_summary, stage13_checks = _stage13_default_runner(
        symbols=symbols,
        lock_dir=lock_dir,
        out_dir=reconcile_dir,
    )

    stage13_rows: dict[str, dict[str, Any]] = {}
    if not stage13_summary.empty and "symbol" in stage13_summary.columns:
        for _, row in stage13_summary.iterrows():
            symbol = _normalize_symbol(str(row.get("symbol", "")))
            stage13_pass = bool(row.get("stage13_dukascopy_testclient_pass"))
            stage13_rows[symbol] = {
                "certification_outcome": "PASS" if stage13_pass else "FAIL",
                "go_decision": "GO" if stage13_pass else "NO_GO",
                "stage13_dukascopy_testclient_pass": stage13_pass,
                "stage13_verdict": row.get("verdict"),
            }

    final_rows = _combine_final_rows(symbols=symbols, stage12_rows=stage12_rows, stage13_rows=stage13_rows)
    final_summary_path = out_dir / FINAL_SUMMARY_FILENAME
    pd.DataFrame(final_rows).to_csv(final_summary_path, index=False)

    print(f"Wrote Stage 12 summary rows for {len(stage12_rows)} symbols to {reconcile_dir}")
    print(f"Wrote Stage 13 summary to {(_stage13_summary_path(reconcile_dir)).as_posix()}")
    print(f"Wrote Stage 13 checks to {(reconcile_dir / 'stage13_dukascopy_testclient_checks.csv').as_posix()}")
    print(f"Wrote final normalized summary to {final_summary_path.as_posix()}")
    if not stage13_checks.empty:
        print(f"Stage 13 checks rows: {len(stage13_checks)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
