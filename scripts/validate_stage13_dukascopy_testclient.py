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


def _load_historical_lock_status(lock_dir: Path, symbol: str) -> dict[str, str | bool]:
    path = lock_dir / f"{symbol.lower()}_oco_live_lock.json"
    if not path.exists():
        return {"historical_deployable": True, "non_deployable_reason": ""}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"historical_deployable": True, "non_deployable_reason": ""}
    hist = payload.get("historical_backtest", {})
    if not isinstance(hist, dict):
        hist = {}
    return {
        "historical_deployable": bool(hist.get("deployable", True)),
        "non_deployable_reason": str(hist.get("non_deployable_reason", "")).strip(),
    }


def _runtime_events_ok(reconcile_dir: Path, symbol: str) -> tuple[bool, str]:
    path = reconcile_dir / f"{symbol}_jforex_runtime_events.csv"
    if not path.exists():
        return False, f"missing runtime events file: {path}"
    if path.stat().st_size <= 0:
        return False, f"empty runtime events file: {path}"
    return True, ""


def build_stage13_artifacts(
    *,
    symbols: list[str],
    lock_dir: Path,
    jforex_signal_summary_glob: str,
    jforex_operational_summary_glob: str,
    reconcile_dir: Path,
    out_summary_csv: Path,
    out_checks_csv: Path,
    report_out: Path,
    snapshot_out: Path,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    sources = [
        InputSource(
            check_id="dukascopy_signal_path_exercised_pass",
            summary_glob=jforex_signal_summary_glob,
            candidate_columns=("jforex_signal_parity_pass", "signal_parity_pass", "overall_pass"),
        ),
        InputSource(
            check_id="dukascopy_operational_ready_pass",
            summary_glob=jforex_operational_summary_glob,
            candidate_columns=("operational_ready_pass", "demo_ready_pass", "overall_pass"),
        ),
    ]

    checks_frames = [_load_summary_rows(src) for src in sources]
    checks = pd.concat([df for df in checks_frames if not df.empty], ignore_index=True)
    if checks.empty:
        checks = pd.DataFrame(columns=["symbol", "check_id", "pass", "source_path"])

    symbol_list = sorted({str(s).strip().upper() for s in symbols if str(s).strip()}) or sorted(
        set(checks.get("symbol", pd.Series(dtype=str)).astype(str))
    )
    symbol_list = sorted(
        set(symbol_list) | set(checks.get("symbol", pd.Series(dtype=str)).astype(str))
    )

    summary_rows: list[dict[str, Any]] = []
    check_rows: list[dict[str, Any]] = []
    now_utc = _now_utc()
    for symbol in symbol_list:
        by_symbol = checks[checks["symbol"] == symbol].copy()
        status = _load_historical_lock_status(lock_dir, symbol)
        historical_deployable = bool(status["historical_deployable"])
        non_deployable_reason = str(status["non_deployable_reason"])
        row: dict[str, Any] = {
            "symbol": symbol,
            "historical_deployable": historical_deployable,
            "non_deployable_reason": non_deployable_reason,
        }
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

        for src in sources:
            match = by_symbol[by_symbol["check_id"] == src.check_id].copy()
            value = None if match.empty else match.iloc[-1].get("pass")
            details = ""
            if src.check_id == "dukascopy_signal_path_exercised_pass" and not historical_deployable:
                row[src.check_id] = True
                details = f"non-deployable historical month: {non_deployable_reason or 'no reason provided'}"
                status_txt = "pass"
            elif value is None or pd.isna(value):
                row[src.check_id] = False
                missing_inputs += 1
                status_txt = "fail"
                details = "missing input artifact"
            else:
                row[src.check_id] = bool(value)
                status_txt = "pass" if bool(value) else "fail"
            source_path = "" if match.empty else str(match.iloc[-1].get("source_path") or "")
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
                "dukascopy_runtime_artifacts_complete_pass",
                "dukascopy_signal_path_exercised_pass",
                "dukascopy_operational_ready_pass",
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
        "- Stage 13 is green only when the Dukascopy tester produced complete runtime artifacts and the operational path is healthy.",
        "- Deployable symbols must also exercise the signal path via the tester artifacts before Stage 14 is trusted.",
        "- Historical non-deployable symbols may pass Stage 13 without signal-path exercise when their lock explicitly marks them non-deployable.",
    ]
    report_out.write_text("\n".join(report_lines).strip() + "\n", encoding="utf-8")

    snapshot_lines = [
        "### Auto Snapshot - Stage 13",
        "",
        f"- generated_at: `{now_utc}`",
        "- Stage 13 is the Dukascopy-source prerequisite gate for Stage 14.",
        "- It verifies runtime artifact completeness, operational readiness, and deployable-symbol signal-path exercise.",
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
        "--jforex-signal-summary-glob",
        default="data/analysis/backtest_reconcile/*_jforex_signal_parity_summary.csv",
    )
    parser.add_argument(
        "--jforex-operational-summary-glob",
        default="data/analysis/backtest_reconcile/*_jforex_operational_ready_summary.csv",
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
        jforex_signal_summary_glob=str(args.jforex_signal_summary_glob),
        jforex_operational_summary_glob=str(args.jforex_operational_summary_glob),
        reconcile_dir=Path(str(args.reconcile_dir)),
        out_summary_csv=Path(str(args.out_summary_csv)),
        out_checks_csv=Path(str(args.out_checks_csv)),
        report_out=Path(str(args.report_out)),
        snapshot_out=Path(str(args.snapshot_out)),
    )


if __name__ == "__main__":
    main()
