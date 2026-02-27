#!/usr/bin/env python3
"""Validate stage-spec documentation integrity for OCO strategy bible."""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

STAGE_DOCS = {
    1: "stage_01_data_foundation.md",
    2: "stage_02_opportunity_mining.md",
    3: "stage_03_monthly_wfo.md",
    4: "stage_04_execution_realism.md",
    5: "stage_05_reduced_core.md",
    6: "stage_06_tick_exact_and_portability.md",
    7: "stage_07_logical_and_statistical_audit.md",
    8: "stage_08_robustness_and_stress.md",
    9: "stage_09_live_governance_and_deployment.md",
    10: "stage_10_known_risks_and_backlog.md",
}


def _table(df: pd.DataFrame) -> str:
    if df.empty:
        return "_empty_"
    try:
        return df.to_markdown(index=False)
    except Exception:
        return "```\n" + df.to_string(index=False) + "\n```"


def _add_check(
    rows: list[dict[str, Any]],
    *,
    stage_id: int,
    check_id: str,
    check_name: str,
    passed: bool,
    severity_if_fail: str,
    metric_name: str,
    metric_value: Any,
    threshold: Any,
    comparator: str,
    source_path: Path,
    details: str = "",
) -> None:
    rows.append(
        {
            "symbol": "ALL",
            "stage_id": int(stage_id),
            "check_id": str(check_id),
            "check_name": str(check_name),
            "status": "pass" if bool(passed) else "fail",
            "severity_if_fail": str(severity_if_fail).lower(),
            "component": "stage_integrity",
            "metric_name": str(metric_name),
            "metric_value": metric_value,
            "threshold": threshold,
            "comparator": str(comparator),
            "details": str(details),
            "source_path": str(source_path),
            "evaluated_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
    )


def _extract_generated_block(text: str, *, stage_id: int) -> str:
    start = f"<!-- GENERATED:STAGE_{int(stage_id):02d}:START -->"
    end = f"<!-- GENERATED:STAGE_{int(stage_id):02d}:END -->"
    i = text.find(start)
    j = text.find(end)
    if i < 0 or j < 0 or j <= i:
        return ""
    return text[i + len(start) : j]


def _count_key_results_rows(block_text: str) -> int:
    if not block_text:
        return 0
    marker = "#### Key Results"
    i = block_text.find(marker)
    if i < 0:
        return 0
    tail = block_text[i + len(marker) :]
    lines = tail.splitlines()
    table_lines: list[str] = []
    started = False
    for line in lines:
        s = line.strip()
        if s.startswith("#### ") and started:
            break
        if s.startswith("|"):
            table_lines.append(s)
            started = True
            continue
        if started and s == "":
            break
    return max(0, len(table_lines) - 2)


def _canonical_report_paths(text: str) -> list[str]:
    m = re.search(r"^##\s+Canonical Analysis Reports\s*$", text, flags=re.MULTILINE)
    if not m:
        return []
    start = m.end()
    tail = text[start:]
    next_h = re.search(r"^##\s+.+$", tail, flags=re.MULTILINE)
    section = tail if next_h is None else tail[: next_h.start()]
    paths = re.findall(r"`(docs/analysis/[^`]+\.md)`", section)
    return sorted(list(dict.fromkeys(paths)))


def run(
    *,
    docs_root: Path,
    out_checks_csv: Path,
    out_issues_csv: Path,
    out_report_md: Path,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    checks_rows: list[dict[str, Any]] = []
    for stage_id, name in STAGE_DOCS.items():
        path = docs_root / name
        exists = path.exists()
        _add_check(
            checks_rows,
            stage_id=stage_id,
            check_id=f"SI01_{stage_id:02d}",
            check_name=f"stage_{stage_id:02d}_doc_exists",
            passed=exists,
            severity_if_fail="critical",
            metric_name="exists",
            metric_value=int(exists),
            threshold=1,
            comparator="==",
            source_path=path,
        )
        if not exists:
            continue
        txt = path.read_text(encoding="utf-8", errors="ignore")

        start_tag = f"<!-- GENERATED:STAGE_{stage_id:02d}:START -->"
        end_tag = f"<!-- GENERATED:STAGE_{stage_id:02d}:END -->"
        markers_ok = (start_tag in txt) and (end_tag in txt) and (txt.find(start_tag) < txt.find(end_tag))
        _add_check(
            checks_rows,
            stage_id=stage_id,
            check_id=f"SI02_{stage_id:02d}",
            check_name=f"stage_{stage_id:02d}_generated_markers_present",
            passed=markers_ok,
            severity_if_fail="high",
            metric_name="generated_markers_present",
            metric_value=int(markers_ok),
            threshold=1,
            comparator="==",
            source_path=path,
            details=f"start={start_tag};end={end_tag}",
        )

        block = _extract_generated_block(txt, stage_id=stage_id)
        key_rows = _count_key_results_rows(block)
        _add_check(
            checks_rows,
            stage_id=stage_id,
            check_id=f"SI03_{stage_id:02d}",
            check_name=f"stage_{stage_id:02d}_key_results_non_empty_table",
            passed=key_rows > 0,
            severity_if_fail="high",
            metric_name="key_results_table_rows",
            metric_value=int(key_rows),
            threshold=1,
            comparator=">=",
            source_path=path,
        )

        canon_paths = _canonical_report_paths(txt)
        _add_check(
            checks_rows,
            stage_id=stage_id,
            check_id=f"SI04_{stage_id:02d}",
            check_name=f"stage_{stage_id:02d}_canonical_analysis_links",
            passed=len(canon_paths) >= 1,
            severity_if_fail="medium",
            metric_name="canonical_analysis_report_count",
            metric_value=int(len(canon_paths)),
            threshold=1,
            comparator=">=",
            source_path=path,
            details=",".join(canon_paths),
        )

    checks = pd.DataFrame(checks_rows).sort_values(["check_id"]).reset_index(drop=True)

    issues_rows: list[dict[str, Any]] = []
    fail = checks[checks["status"].astype(str).str.lower() != "pass"].copy() if not checks.empty else pd.DataFrame()
    for _, r in fail.iterrows():
        issues_rows.append(
            {
                "issue_id": f"SI_{r['check_id']}",
                "symbol": "ALL",
                "check_id": str(r["check_id"]),
                "severity": str(r["severity_if_fail"]).lower(),
                "component": "stage_integrity",
                "summary": str(r["check_name"]),
                "details_json": json.dumps(
                    {
                        "stage_id": int(r.get("stage_id", 0)),
                        "metric_name": r.get("metric_name"),
                        "metric_value": r.get("metric_value"),
                        "threshold": r.get("threshold"),
                        "details": r.get("details", ""),
                        "source_path": r.get("source_path", ""),
                    },
                    sort_keys=True,
                ),
            }
        )
    issues = (
        pd.DataFrame(issues_rows)
        if issues_rows
        else pd.DataFrame(columns=["issue_id", "symbol", "check_id", "severity", "component", "summary", "details_json"])
    )

    out_checks_csv.parent.mkdir(parents=True, exist_ok=True)
    out_issues_csv.parent.mkdir(parents=True, exist_ok=True)
    out_report_md.parent.mkdir(parents=True, exist_ok=True)
    checks.to_csv(out_checks_csv, index=False)
    issues.to_csv(out_issues_csv, index=False)

    sev_counts = (
        issues.groupby(["severity"], as_index=False).agg(count=("issue_id", "count")).sort_values("severity")
        if not issues.empty
        else pd.DataFrame(columns=["severity", "count"])
    )
    stage_counts = (
        checks.groupby(["stage_id", "status"], as_index=False).agg(count=("check_id", "count")).sort_values(["stage_id", "status"])
        if not checks.empty
        else pd.DataFrame(columns=["stage_id", "status", "count"])
    )
    lines: list[str] = []
    lines.append("# OCO Stage Integrity Report")
    lines.append("")
    lines.append(f"- generated_at_utc: `{datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}`")
    lines.append(f"- checks_csv: `{out_checks_csv}`")
    lines.append(f"- issues_csv: `{out_issues_csv}`")
    lines.append("")
    lines.append("## Severity Counts")
    lines.append(_table(sev_counts))
    lines.append("")
    lines.append("## Check Status By Stage")
    lines.append(_table(stage_counts))
    lines.append("")
    lines.append("## Failed Issues")
    lines.append(_table(issues))
    lines.append("")
    lines.append("## Full Check Table")
    lines.append(_table(checks))
    out_report_md.write_text("\n".join(lines), encoding="utf-8")

    return checks, issues


def main() -> None:
    p = argparse.ArgumentParser(description="Validate Stage 01-10 docs integrity")
    p.add_argument("--docs-root", default="docs/strategy_bible")
    p.add_argument("--out-checks-csv", default="data/analysis/tick_opportunity_mining/oco_stage_integrity_checks.csv")
    p.add_argument("--out-issues-csv", default="data/analysis/tick_opportunity_mining/oco_stage_integrity_issues.csv")
    p.add_argument("--report-out", default="docs/analysis/oco_stage_integrity_report.md")
    args = p.parse_args()

    checks, issues = run(
        docs_root=Path(str(args.docs_root)),
        out_checks_csv=Path(str(args.out_checks_csv)),
        out_issues_csv=Path(str(args.out_issues_csv)),
        out_report_md=Path(str(args.report_out)),
    )
    failed = int((checks["status"].astype(str).str.lower() != "pass").sum()) if not checks.empty else 0
    print(f"wrote checks: {args.out_checks_csv} rows={len(checks)}")
    print(f"wrote issues: {args.out_issues_csv} rows={len(issues)}")
    print(f"failed_checks={failed}")


if __name__ == "__main__":
    main()
