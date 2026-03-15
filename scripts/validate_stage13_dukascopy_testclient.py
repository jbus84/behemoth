#!/usr/bin/env python3
"""Build Stage 13 Dukascopy TestClient parity artifacts from replay summaries."""

from __future__ import annotations

import argparse
import glob
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
    paths = _resolve_paths(source.summary_glob)
    rows: list[dict[str, Any]] = []
    for path in paths:
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


def build_stage13_artifacts(
    *,
    symbols: list[str],
    stage12_summary_glob: str,
    dukascopy_testclient_summary_glob: str,
    out_summary_csv: Path,
    out_checks_csv: Path,
    report_out: Path,
    snapshot_out: Path,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    sources = [
        InputSource(
            check_id="stage12_api_parity_pass",
            summary_glob=stage12_summary_glob,
            candidate_columns=("stage12_api_parity_pass", "api_parity_pass", "overall_pass"),
        ),
        InputSource(
            check_id="dukascopy_testclient_signal_parity_pass",
            summary_glob=dukascopy_testclient_summary_glob,
            candidate_columns=("selected_parity_pass", "signal_parity_pass", "overall_pass"),
        ),
        InputSource(
            check_id="dukascopy_testclient_execution_parity_pass",
            summary_glob=dukascopy_testclient_summary_glob,
            candidate_columns=("overall_pass", "execution_parity_pass"),
        ),
    ]

    checks_frames = [_load_summary_rows(src) for src in sources]
    checks = pd.concat([df for df in checks_frames if not df.empty], ignore_index=True)
    if checks.empty:
        checks = pd.DataFrame(columns=["symbol", "check_id", "pass", "source_path"])

    symbols = sorted({str(s).strip().upper() for s in symbols if str(s).strip()}) or sorted(
        set(checks.get("symbol", pd.Series(dtype=str)).astype(str))
    )
    symbols = sorted(set(symbols) | set(checks.get("symbol", pd.Series(dtype=str)).astype(str)))

    summary_rows: list[dict[str, Any]] = []
    check_rows: list[dict[str, Any]] = []
    now_utc = _now_utc()
    for symbol in symbols:
        by_symbol = checks[checks["symbol"] == symbol].copy()
        row: dict[str, Any] = {"symbol": symbol}
        missing_inputs = 0
        for src in sources:
            match = by_symbol[by_symbol["check_id"] == src.check_id].copy()
            value = None if match.empty else match.iloc[-1].get("pass")
            if value is None or pd.isna(value):
                missing_inputs += 1
                row[src.check_id] = False
                status = "fail"
                details = "missing input artifact"
            else:
                row[src.check_id] = bool(value)
                status = "pass" if bool(value) else "fail"
                details = ""
            source_path = "" if match.empty else str(match.iloc[-1].get("source_path") or "")
            check_rows.append(
                {
                    "symbol": symbol,
                    "check_id": src.check_id.upper(),
                    "status": status,
                    "severity": "critical",
                    "metric_name": src.check_id,
                    "metric_value": int(bool(row[src.check_id])),
                    "expected": 1,
                    "details": details,
                    "source_path": source_path,
                    "evaluated_at_utc": now_utc,
                }
            )
        row["stage13_dukascopy_testclient_pass"] = all(bool(row[src.check_id]) for src in sources)
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
        "# Stage 13 Dukascopy TestClient Parity",
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
        "- Stage 13 is green only when Stage 12 parity remains green and Dukascopy TestClient signal and execution parity are both green.",
        "- Missing Dukascopy TestClient replay artifacts are treated as certification failures until the replay path is exercised.",
    ]
    report_out.write_text("\n".join(report_lines).strip() + "\n", encoding="utf-8")

    snapshot_lines = [
        "### Auto Snapshot - Stage 13",
        "",
        f"- generated_at: `{now_utc}`",
        "- Stage 13 is a hard gate for Dukascopy source parity via the FastAPI TestClient harness.",
        "- Stage 12 parity, Dukascopy TestClient signal parity, and Dukascopy TestClient execution parity must all be green.",
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
    parser.add_argument(
        "--symbols",
        default="EURUSD,GBPUSD,USDJPY,USDCHF,AUDUSD,USDCAD",
    )
    parser.add_argument(
        "--stage12-summary-glob",
        default="data/analysis/backtest_reconcile/*_stage12_api_parity_summary.csv",
    )
    parser.add_argument(
        "--dukascopy-testclient-summary-glob",
        default="data/analysis/backtest_reconcile/*_dukascopy_testclient_replay_summary.csv",
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
        stage12_summary_glob=str(args.stage12_summary_glob),
        dukascopy_testclient_summary_glob=str(args.dukascopy_testclient_summary_glob),
        out_summary_csv=Path(str(args.out_summary_csv)),
        out_checks_csv=Path(str(args.out_checks_csv)),
        report_out=Path(str(args.report_out)),
        snapshot_out=Path(str(args.snapshot_out)),
    )


if __name__ == "__main__":
    main()
