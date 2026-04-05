#!/usr/bin/env python3
"""Run the unified Stage 12 -> Stage 13 certification flow.

The orchestration layer is intentionally small:
- Stage 12 is generated per symbol first.
- Stage 13 is then evaluated from the Stage 12 outputs plus Dukascopy/TestClient evidence.
- Final outputs resolve to PASS/FAIL and GO/NO_GO only.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping

import pandas as pd

from scripts.validate_api_parity import run as validate_api_parity_run
from scripts.validate_stage13_dukascopy_testclient import build_stage13_artifacts

DEFAULT_SYMBOLS = ["EURUSD", "GBPUSD", "USDJPY", "USDCHF", "AUDUSD", "USDCAD"]
DEFAULT_PREDICTIONS_DIR = Path("data/analysis/tick_opportunity_mining/wfo_m3to1_oco_fullcap")
DEFAULT_MODELS_DIR = Path("models/oco")
DEFAULT_RECONCILE_DIR = Path("data/analysis/backtest_reconcile")
DEFAULT_LOCK_DIR = Path("configs/research/governance/oco_history_dukascopy_candidate/2025-07")
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


def _stage12_default_runner(
    *,
    symbol: str,
    predictions_dir: Path,
    models_dir: Path,
    out_dir: Path,
    tolerance: float = 0.0,
) -> dict[str, Any]:
    symbol = _normalize_symbol(symbol)
    summary_path = _stage12_summary_path(out_dir, symbol)
    predictions_path = predictions_dir / f"{symbol}_oco_monthly_predictions.parquet"
    threshold_json = _latest_model_json(models_dir, symbol)

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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbols", default=",".join(DEFAULT_SYMBOLS))
    parser.add_argument("--predictions-dir", type=Path, default=DEFAULT_PREDICTIONS_DIR)
    parser.add_argument("--models-dir", type=Path, default=DEFAULT_MODELS_DIR)
    parser.add_argument("--lock-dir", type=Path, default=DEFAULT_LOCK_DIR)
    parser.add_argument("--reconcile-dir", type=Path, default=DEFAULT_RECONCILE_DIR)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_RECONCILE_DIR)
    parser.add_argument("--stage12-tolerance", type=float, default=0.0)
    args = parser.parse_args(argv)

    symbols = _parse_symbols(args.symbols)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    reconcile_dir = Path(args.reconcile_dir)
    reconcile_dir.mkdir(parents=True, exist_ok=True)

    stage12_rows: dict[str, dict[str, Any]] = {}
    for symbol in symbols:
        stage12_rows[symbol] = _stage12_default_runner(
            symbol=symbol,
            predictions_dir=Path(args.predictions_dir),
            models_dir=Path(args.models_dir),
            out_dir=reconcile_dir,
            tolerance=args.stage12_tolerance,
        )

    stage13_summary, stage13_checks = _stage13_default_runner(
        symbols=symbols,
        lock_dir=Path(args.lock_dir),
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
