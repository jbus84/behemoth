#!/usr/bin/env python3
"""Build Stage 13 Dukascopy certification artifacts from active matrix outputs."""

from __future__ import annotations

import argparse
import glob
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd


@dataclass(frozen=True)
class InputSource:
    check_id: str
    summary_glob: str
    candidate_columns: tuple[str, ...]
    excluded_path_tokens: tuple[str, ...] = ()


def _now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _table(df: pd.DataFrame) -> str:
    if df.empty:
        return "_empty_"
    try:
        return df.to_markdown(index=False)
    except Exception:
        return df.to_csv(index=False)


def _resolve_paths(pattern: str) -> list[Path]:
    txt = str(pattern or "").strip()
    if not txt:
        return []
    out: list[Path] = []
    for part in [p.strip() for p in txt.split(",") if p.strip()]:
        out.extend(Path(p) for p in sorted(glob.glob(part)))
    seen: set[str] = set()
    unique: list[Path] = []
    for path in out:
        key = str(path.resolve())
        if key not in seen:
            seen.add(key)
            unique.append(path)
    return unique


def _pick_bool(row: pd.Series, candidates: tuple[str, ...]) -> bool | None:
    for col in candidates:
        if col not in row.index:
            continue
        value = row.get(col)
        if pd.isna(value):
            continue
        if isinstance(value, bool):
            return value
        txt = str(value).strip().lower()
        if txt in {"1", "true", "yes", "y", "pass", "green"}:
            return True
        if txt in {"0", "false", "no", "n", "fail", "red"}:
            return False
    return None


def _load_summary_rows(source: InputSource) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for path in _resolve_paths(source.summary_glob):
        path_name = path.name.lower()
        if any(token in path_name for token in source.excluded_path_tokens):
            continue
        try:
            df = pd.read_csv(path)
        except Exception:
            continue
        if df.empty or "symbol" not in df.columns:
            continue
        for _, row in df.iterrows():
            symbol = str(row.get("symbol") or "").strip().upper()
            if not symbol:
                continue
            rows.append(
                {
                    "symbol": symbol,
                    "check_id": source.check_id,
                    "pass": _pick_bool(row, source.candidate_columns),
                    "source_path": str(path),
                }
            )
    return pd.DataFrame(rows)


def _latest_match(frames: list[pd.DataFrame], symbol: str, check_id: str) -> pd.DataFrame:
    first_non_concrete = pd.DataFrame(columns=["symbol", "check_id", "pass", "source_path"])
    for frame in frames:
        if frame.empty:
            continue
        match = frame[(frame["symbol"] == symbol) & (frame["check_id"] == check_id)].copy()
        if not match.empty:
            concrete = match[match["pass"].notna()].copy()
            if not concrete.empty:
                return concrete
            if first_non_concrete.empty:
                first_non_concrete = match
    return first_non_concrete


def _expected_source_path(reconcile_dir: Path, symbol: str, check_id: str) -> Path:
    if check_id == "stage12_api_parity_pass":
        return reconcile_dir / f"{symbol}_stage12_api_parity_summary.csv"
    if check_id in {
        "dukascopy_testclient_signal_parity_pass",
        "dukascopy_testclient_execution_parity_pass",
    }:
        return reconcile_dir / f"{symbol}_dukascopy_testclient_replay_summary.csv"
    if check_id == "dukascopy_runtime_artifacts_complete_pass":
        return reconcile_dir / f"{symbol}_jforex_runtime_events.csv"
    return reconcile_dir / f"{symbol}_{check_id}.csv"


def _missing_details(check_id: str, source_path: Path) -> str:
    if check_id == "dukascopy_runtime_artifacts_complete_pass":
        return (
            "missing current Dukascopy replay runtime-events artifact "
            f"(legacy filename retained): {source_path}"
        )
    if check_id == "stage12_api_parity_pass":
        return f"missing Stage 12 API parity summary: {source_path}"
    if check_id == "dukascopy_testclient_signal_parity_pass":
        return f"missing Dukascopy/TestClient signal parity summary: {source_path}"
    if check_id == "dukascopy_testclient_execution_parity_pass":
        return f"missing Dukascopy/TestClient execution parity summary: {source_path}"
    return f"missing input artifact: {source_path}"


def _runtime_events_ok(reconcile_dir: Path, symbol: str) -> tuple[bool, str]:
    path = reconcile_dir / f"{symbol}_jforex_runtime_events.csv"
    if not path.exists():
        return False, (
            "missing current Dukascopy replay runtime-events artifact "
            f"(legacy filename retained): {path}"
        )
    if path.stat().st_size <= 0:
        return False, (
            "empty current Dukascopy replay runtime-events artifact "
            f"(legacy filename retained): {path}"
        )
    try:
        df = pd.read_csv(path)
    except Exception:
        return False, (
            "unreadable current Dukascopy replay runtime-events artifact "
            f"(legacy filename retained): {path}"
        )
    if df.empty:
        return False, (
            "header-only current Dukascopy replay runtime-events artifact "
            f"(legacy filename retained): {path}"
        )
    return True, ""


def build_stage13_artifacts(
    *,
    symbols: list[str],
    lock_dir: Path,
    stage12_api_parity_summary_glob: str,
    dukascopy_testclient_replay_summary_glob: str = "",
    dukascopy_testclient_signal_summary_glob: str = "",
    dukascopy_testclient_execution_summary_glob: str = "",
    reconcile_dir: Path,
    out_summary_csv: Path,
    out_checks_csv: Path,
    report_out: Path,
    snapshot_out: Path,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    stage12_source = InputSource(
        check_id="stage12_api_parity_pass",
        summary_glob=stage12_api_parity_summary_glob,
        candidate_columns=("stage12_api_parity_pass", "api_parity_pass", "overall_pass"),
    )
    replay_sources = [
        InputSource(
            check_id="dukascopy_testclient_signal_parity_pass",
            summary_glob="",
            candidate_columns=(
                "dukascopy_testclient_signal_parity_pass",
                "jforex_signal_parity_pass",
                "signal_parity_pass",
                "overall_pass",
            ),
            excluded_path_tokens=("local_jforex",),
        ),
        InputSource(
            check_id="dukascopy_testclient_execution_parity_pass",
            summary_glob="",
            candidate_columns=(
                "dukascopy_testclient_execution_parity_pass",
                "jforex_execution_parity_pass",
                "execution_parity_pass",
                "overall_pass",
            ),
            excluded_path_tokens=("local_jforex",),
        ),
    ]
    replay_glob = str(dukascopy_testclient_replay_summary_glob).strip()
    signal_glob = str(dukascopy_testclient_signal_summary_glob).strip()
    execution_glob = str(dukascopy_testclient_execution_summary_glob).strip()
    stage12_checks = _load_summary_rows(stage12_source)
    replay_signal_checks = (
        _load_summary_rows(
            InputSource(
                check_id="dukascopy_testclient_signal_parity_pass",
                summary_glob=replay_glob,
                candidate_columns=replay_sources[0].candidate_columns,
                excluded_path_tokens=replay_sources[0].excluded_path_tokens,
            )
        )
        if replay_glob
        else pd.DataFrame(columns=["symbol", "check_id", "pass", "source_path"])
    )
    replay_execution_checks = (
        _load_summary_rows(
            InputSource(
                check_id="dukascopy_testclient_execution_parity_pass",
                summary_glob=replay_glob,
                candidate_columns=replay_sources[1].candidate_columns,
                excluded_path_tokens=replay_sources[1].excluded_path_tokens,
            )
        )
        if replay_glob
        else pd.DataFrame(columns=["symbol", "check_id", "pass", "source_path"])
    )
    fallback_signal_checks = (
        _load_summary_rows(
            InputSource(
                check_id="dukascopy_testclient_signal_parity_pass",
                summary_glob=signal_glob,
                candidate_columns=replay_sources[0].candidate_columns,
                excluded_path_tokens=replay_sources[0].excluded_path_tokens,
            )
        )
        if signal_glob
        else pd.DataFrame(columns=["symbol", "check_id", "pass", "source_path"])
    )
    fallback_execution_checks = (
        _load_summary_rows(
            InputSource(
                check_id="dukascopy_testclient_execution_parity_pass",
                summary_glob=execution_glob,
                candidate_columns=replay_sources[1].candidate_columns,
                excluded_path_tokens=replay_sources[1].excluded_path_tokens,
            )
        )
        if execution_glob
        else pd.DataFrame(columns=["symbol", "check_id", "pass", "source_path"])
    )

    requested_symbols = {str(s).strip().upper() for s in symbols if str(s).strip()}
    if requested_symbols:
        symbol_list = sorted(requested_symbols)
    else:
        all_frames = [
            stage12_checks,
            replay_signal_checks,
            replay_execution_checks,
            fallback_signal_checks,
            fallback_execution_checks,
        ]
        known_symbols = set()
        for frame in all_frames:
            if not frame.empty:
                known_symbols.update(frame.get("symbol", pd.Series(dtype=str)).astype(str))
        symbol_list = sorted(str(s).strip().upper() for s in known_symbols if str(s).strip())

    summary_rows: list[dict[str, Any]] = []
    check_rows: list[dict[str, Any]] = []
    now_utc = _now_utc()
    for symbol in symbol_list:
        row: dict[str, Any] = {"symbol": symbol}
        missing_inputs = 0

        runtime_ok, runtime_details = _runtime_events_ok(reconcile_dir, symbol)
        row["dukascopy_runtime_artifacts_complete_pass"] = runtime_ok
        if not runtime_ok:
            missing_inputs += 1
        check_rows.append(
            {
                "symbol": symbol,
                "check_id": "DUKASCOPY_RUNTIME_ARTIFACTS_COMPLETE_PASS",
                "status": "pass" if runtime_ok else "fail",
                "severity": "critical",
                "metric_name": "dukascopy_runtime_artifacts_complete_pass",
                "metric_value": int(runtime_ok),
                "expected": 1,
                "details": runtime_details,
                "source_path": str(reconcile_dir / f"{symbol}_jforex_runtime_events.csv"),
                "evaluated_at_utc": now_utc,
            }
        )

        for src, candidate_frames in (
            (stage12_source, [stage12_checks]),
            (
                replay_sources[0],
                [replay_signal_checks, fallback_signal_checks],
            ),
            (
                replay_sources[1],
                [replay_execution_checks, fallback_execution_checks],
            ),
        ):
            match = _latest_match(candidate_frames, symbol, src.check_id)
            value = None if match.empty else match.iloc[-1].get("pass")
            details = ""
            expected_source_path = _expected_source_path(reconcile_dir, symbol, src.check_id)
            if value is None or pd.isna(value):
                row[src.check_id] = False
                missing_inputs += 1
                status_txt = "fail"
                details = _missing_details(src.check_id, expected_source_path)
            else:
                row[src.check_id] = bool(value)
                status_txt = "pass" if bool(value) else "fail"
            source_path = (
                str(expected_source_path) if match.empty else str(match.iloc[-1].get("source_path") or "")
            )
            if not source_path:
                source_path = str(expected_source_path)
            check_rows.append(
                {
                    "symbol": symbol,
                    "check_id": src.check_id.upper(),
                    "status": status_txt,
                    "severity": "critical",
                    "metric_name": src.check_id,
                    "metric_value": int(bool(row[src.check_id])),
                    "expected": 1,
                    "details": details,
                    "source_path": source_path,
                    "evaluated_at_utc": now_utc,
                }
            )

        row["stage13_dukascopy_testclient_pass"] = all(
            bool(row[name])
            for name in (
                "stage12_api_parity_pass",
                "dukascopy_runtime_artifacts_complete_pass",
                "dukascopy_testclient_signal_parity_pass",
                "dukascopy_testclient_execution_parity_pass",
            )
        )
        row["missing_inputs"] = missing_inputs
        row["verdict"] = "green" if row["stage13_dukascopy_testclient_pass"] else "red"
        row["evaluated_at_utc"] = now_utc
        summary_rows.append(row)

    summary = pd.DataFrame(summary_rows)
    checks_out = pd.DataFrame(check_rows)

    out_summary_csv.parent.mkdir(parents=True, exist_ok=True)
    out_checks_csv.parent.mkdir(parents=True, exist_ok=True)
    report_out.parent.mkdir(parents=True, exist_ok=True)
    snapshot_out.parent.mkdir(parents=True, exist_ok=True)
    summary.to_csv(out_summary_csv, index=False)
    checks_out.to_csv(out_checks_csv, index=False)

    report_lines = [
        "# Stage 13 Dukascopy Source Certification",
        "",
        f"- generated_at: `{now_utc}`",
        f"- summary_csv: `{out_summary_csv.as_posix()}`",
        f"- checks_csv: `{out_checks_csv.as_posix()}`",
        "",
        "## Summary",
        _table(summary),
        "",
        "## Checks",
        _table(checks_out),
        "",
        "## Interpretation",
        "- Stage 13 is green only when Stage 12 API parity, the current Dukascopy replay runtime-events artifact, Dukascopy/TestClient signal parity, and Dukascopy/TestClient execution parity are all green.",
        "- Local-surrogate artifacts are excluded from Stage 13 hard-gate consumption even when broad file globs are provided.",
    ]
    report_out.write_text("\n".join(report_lines).strip() + "\n", encoding="utf-8")

    snapshot_lines = [
        "### Auto Snapshot - Stage 13",
        "",
        f"- generated_at: `{now_utc}`",
        "- Stage 13 is the Dukascopy-source prerequisite gate for Stage 14.",
        "- It verifies Stage 12 API parity plus the current Dukascopy replay runtime-events artifact, signal parity, and execution parity.",
        "",
        "#### Key Results",
        _table(summary),
        "",
        "#### Checks",
        _table(checks_out),
    ]
    snapshot_out.write_text("\n".join(snapshot_lines).strip() + "\n", encoding="utf-8")
    return summary, checks_out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbols", default="EURUSD,GBPUSD,USDJPY,USDCHF,AUDUSD,USDCAD")
    parser.add_argument(
        "--lock-dir",
        default="configs/research/governance/oco_history_dukascopy_candidate/2025-07",
    )
    parser.add_argument(
        "--stage12-api-parity-summary-glob",
        default="data/analysis/backtest_reconcile/*_stage12_api_parity_summary.csv",
    )
    parser.add_argument(
        "--dukascopy-testclient-replay-summary-glob",
        default="data/analysis/backtest_reconcile/*_dukascopy_testclient_replay_summary.csv",
    )
    parser.add_argument(
        "--dukascopy-testclient-signal-summary-glob",
        default="",
    )
    parser.add_argument(
        "--dukascopy-testclient-execution-summary-glob",
        default="",
    )
    parser.add_argument(
        "--reconcile-dir",
        default="data/analysis/backtest_reconcile",
    )
    parser.add_argument(
        "--out-summary-csv",
        default="data/analysis/backtest_reconcile/stage13_dukascopy_testclient_summary.csv",
    )
    parser.add_argument(
        "--out-checks-csv",
        default="data/analysis/backtest_reconcile/stage13_dukascopy_testclient_checks.csv",
    )
    parser.add_argument(
        "--report-out",
        default="docs/analysis/stage13_dukascopy_testclient_report.md",
    )
    parser.add_argument(
        "--snapshot-out",
        default="docs/strategy_bible/generated/stage_13_snapshot.md",
    )
    args = parser.parse_args()
    build_stage13_artifacts(
        symbols=[s.strip().upper() for s in str(args.symbols).split(",") if s.strip()],
        lock_dir=Path(str(args.lock_dir)),
        stage12_api_parity_summary_glob=str(args.stage12_api_parity_summary_glob),
        dukascopy_testclient_replay_summary_glob=str(args.dukascopy_testclient_replay_summary_glob),
        dukascopy_testclient_signal_summary_glob=str(args.dukascopy_testclient_signal_summary_glob),
        dukascopy_testclient_execution_summary_glob=str(args.dukascopy_testclient_execution_summary_glob),
        reconcile_dir=Path(str(args.reconcile_dir)),
        out_summary_csv=Path(str(args.out_summary_csv)),
        out_checks_csv=Path(str(args.out_checks_csv)),
        report_out=Path(str(args.report_out)),
        snapshot_out=Path(str(args.snapshot_out)),
    )


if __name__ == "__main__":
    main()
