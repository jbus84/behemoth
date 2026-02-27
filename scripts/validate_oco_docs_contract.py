#!/usr/bin/env python3
"""Validate OCO strategy bible documentation contract."""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd


@dataclass(frozen=True)
class Thresholds:
    max_age_hours: float = 24.0 * 7.0


REQUIRED_STAGE_DOCS = {
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

REQUIRED_HEADINGS = [
    "Objective",
    "Inputs",
    "Process",
    "Exact Calculations",
    "Causality / Leakage Controls",
    "Failure Modes",
    "Interpretation Guide",
    "Validation Gates",
    "Reproduction Commands",
    "Traceability",
]

CORE_METRIC_IDS = {
    "D16_spread_regime_shift_z",
    "D17_gap_burst_ratio",
    "D18_clock_jitter_cv",
    "M01_top3_contrib_share",
    "M02_smoothness_abs_jump",
    "M03_positive_density",
    "W13_threshold_fragility",
    "W14_brier_drift_std",
    "W15_selection_turnover",
    "E11_session_overshoot_dispersion",
    "E12_cap_plateau_width_pips",
    "E13_nonfill_opportunity_cost_pips",
    "R01_post_pre_row_ratio",
    "R02_top_state_dependency",
    "R03_reselection_stability",
    "X01_portable_family_count",
    "X02_family_std_mean",
    "X03_family_spread_mean",
    "S01_lb95_dependence_gap",
    "S02_practical_lb95_gt0",
    "S03_multiplicity_survival",
    "T01_stress_elasticity",
    "T02_first_negative_costplus",
    "T03_post_worst_month_recovery",
    "G01_near_fail_count",
    "G03_lock_drift_flags",
}

CANONICAL_NAV_PATHS = [
    "strategy_bible/stage_01_data_foundation.md",
    "strategy_bible/stage_02_opportunity_mining.md",
    "strategy_bible/stage_03_monthly_wfo.md",
    "strategy_bible/stage_04_execution_realism.md",
    "strategy_bible/stage_05_reduced_core.md",
    "strategy_bible/stage_06_tick_exact_and_portability.md",
    "strategy_bible/stage_07_logical_and_statistical_audit.md",
    "strategy_bible/stage_08_robustness_and_stress.md",
    "strategy_bible/stage_09_live_governance_and_deployment.md",
    "strategy_bible/stage_10_known_risks_and_backlog.md",
    "strategy_bible/metric_dictionary.md",
    "strategy_bible/assumptions_and_threats.md",
    "strategy_bible/governance_mapping.md",
    "analysis/oco_docs_contract_report.md",
]


def _table(df: pd.DataFrame) -> str:
    if df.empty:
        return "_empty_"
    try:
        return df.to_markdown(index=False)
    except Exception:
        return "```\n" + df.to_string(index=False) + "\n```"


def _parse_symbols(raw: str) -> list[str]:
    return [x.strip().upper() for x in str(raw).split(",") if x.strip()]


def _add_check(
    rows: list[dict[str, Any]],
    *,
    check_id: str,
    check_name: str,
    passed: bool,
    severity_if_fail: str,
    metric_name: str,
    metric_value: Any,
    threshold: Any,
    comparator: str,
    source_path: Path | None,
    details: str = "",
) -> None:
    rows.append(
        {
            "symbol": "ALL",
            "check_id": str(check_id),
            "check_name": str(check_name),
            "status": "pass" if bool(passed) else "fail",
            "severity_if_fail": str(severity_if_fail).lower(),
            "component": "docs_contract",
            "metric_name": str(metric_name),
            "metric_value": metric_value,
            "threshold": threshold,
            "comparator": str(comparator),
            "details": str(details),
            "source_path": str(source_path) if source_path is not None else "",
            "evaluated_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
    )


def _extract_metric_ids_from_dictionary(path: Path) -> set[str]:
    if not path.exists():
        return set()
    ids: set[str] = set()
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        s = line.strip()
        if not s.startswith("|"):
            continue
        parts = [p.strip() for p in s.split("|")]
        if len(parts) < 3:
            continue
        first = parts[1]
        if not first or first in {"metric_id", "---"}:
            continue
        if re.match(r"^[A-Z][0-9]{2}_", first) or first.startswith(("erosion_", "B", "G", "R", "S", "T", "W", "M", "D", "E", "X")):
            ids.add(first)
    return ids


def _extract_headings(path: Path) -> set[str]:
    if not path.exists():
        return set()
    out: set[str] = set()
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        m = re.match(r"^##\s+(.+?)\s*$", line)
        if m:
            out.add(str(m.group(1)).strip())
    return out


def _stage_doc_path(docs_root: Path, stage_id: int) -> Path:
    return docs_root / REQUIRED_STAGE_DOCS[stage_id]


def _extract_symbols_from_stage09_snapshot(path: Path) -> set[str]:
    if not path.exists():
        return set()
    txt = path.read_text(encoding="utf-8", errors="ignore")
    return set(re.findall(r"\|\s*(EURUSD|GBPUSD|USDJPY)\s*\|", txt))


def _extract_symbols_from_edge_report(path: Path) -> set[str]:
    if not path.exists():
        return set()
    txt = path.read_text(encoding="utf-8", errors="ignore")
    return set(re.findall(r"\|\s*[0-9]+\s*\|\s*(EURUSD|GBPUSD|USDJPY)\s*\|", txt))


def run(
    *,
    docs_root: Path,
    generated_root: Path,
    edge_metrics_csv: Path,
    stage_status_csv: Path,
    metric_dictionary_md: Path,
    edge_report_md: Path,
    mkdocs_yml: Path,
    out_checks_csv: Path,
    out_issues_csv: Path,
    out_report_md: Path,
    thresholds: Thresholds,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    checks_rows: list[dict[str, Any]] = []

    # C1: Stage spec presence.
    missing_stage_docs: list[str] = []
    for i in range(1, 11):
        p = _stage_doc_path(docs_root, i)
        ok = p.exists()
        if not ok:
            missing_stage_docs.append(str(p))
        _add_check(
            checks_rows,
            check_id=f"C1_{i:02d}",
            check_name=f"stage_{i:02d}_spec_exists",
            passed=ok,
            severity_if_fail="high",
            metric_name="exists",
            metric_value=int(ok),
            threshold=1,
            comparator="==",
            source_path=p,
            details="",
        )

    # C2: Required section headings.
    for i in range(1, 11):
        p = _stage_doc_path(docs_root, i)
        if not p.exists():
            continue
        heads = _extract_headings(p)
        missing = [h for h in REQUIRED_HEADINGS if h not in heads]
        _add_check(
            checks_rows,
            check_id=f"C2_{i:02d}",
            check_name=f"stage_{i:02d}_required_headings",
            passed=len(missing) == 0,
            severity_if_fail="high",
            metric_name="missing_required_headings",
            metric_value=int(len(missing)),
            threshold=0,
            comparator="==",
            source_path=p,
            details=",".join(missing),
        )

    edge = pd.read_csv(edge_metrics_csv) if edge_metrics_csv.exists() else pd.DataFrame()
    dict_ids = _extract_metric_ids_from_dictionary(metric_dictionary_md)

    # C3: Metric dictionary coverage.
    edge_ids = set(edge.get("metric_id", pd.Series(dtype=str)).dropna().astype(str).unique().tolist())
    missing_metric_defs = sorted(list(edge_ids - dict_ids))
    _add_check(
        checks_rows,
        check_id="C3",
        check_name="metric_dictionary_covers_observed_metrics",
        passed=len(missing_metric_defs) == 0,
        severity_if_fail="critical",
        metric_name="missing_metric_definitions",
        metric_value=int(len(missing_metric_defs)),
        threshold=0,
        comparator="==",
        source_path=metric_dictionary_md,
        details=",".join(missing_metric_defs),
    )

    # C4a: No NaNs in emitted edge metrics.
    nan_count = int(pd.to_numeric(edge.get("metric_value", pd.Series(dtype=float)), errors="coerce").isna().sum()) if not edge.empty else 0
    _add_check(
        checks_rows,
        check_id="C4A",
        check_name="edge_metrics_no_nan_values",
        passed=nan_count == 0,
        severity_if_fail="high",
        metric_name="nan_metric_values",
        metric_value=nan_count,
        threshold=0,
        comparator="==",
        source_path=edge_metrics_csv,
    )

    # C4b: Core metric ids present and non-nan.
    core_missing_or_nan: list[str] = []
    if edge.empty:
        core_missing_or_nan = sorted(list(CORE_METRIC_IDS))
    else:
        for mid in sorted(CORE_METRIC_IDS):
            m = edge[edge["metric_id"].astype(str) == mid].copy()
            if m.empty:
                core_missing_or_nan.append(mid)
                continue
            vals = pd.to_numeric(m.get("metric_value"), errors="coerce")
            if vals.isna().all():
                core_missing_or_nan.append(mid)
    _add_check(
        checks_rows,
        check_id="C4B",
        check_name="core_metric_ids_present_and_non_nan",
        passed=len(core_missing_or_nan) == 0,
        severity_if_fail="critical",
        metric_name="core_missing_or_nan",
        metric_value=int(len(core_missing_or_nan)),
        threshold=0,
        comparator="==",
        source_path=edge_metrics_csv,
        details=",".join(core_missing_or_nan),
    )

    # C5: Snapshot/report consistency.
    stage_status = pd.read_csv(stage_status_csv) if stage_status_csv.exists() else pd.DataFrame()
    status_syms = set(stage_status.get("symbol", pd.Series(dtype=str)).astype(str).str.upper().tolist())
    s09_syms = _extract_symbols_from_stage09_snapshot(generated_root / "stage_09_snapshot.md")
    edge_syms = set(edge.get("symbol", pd.Series(dtype=str)).astype(str).str.upper().tolist())
    edge_report_syms = _extract_symbols_from_edge_report(edge_report_md)
    sym_consistent = bool(status_syms) and status_syms.issubset(s09_syms) and status_syms.issubset(edge_syms) and status_syms.issubset(edge_report_syms)
    _add_check(
        checks_rows,
        check_id="C5",
        check_name="snapshot_report_symbol_consistency",
        passed=sym_consistent,
        severity_if_fail="high",
        metric_name="consistent_symbol_sets",
        metric_value=int(sym_consistent),
        threshold=1,
        comparator="==",
        source_path=generated_root / "stage_09_snapshot.md",
        details=json.dumps(
            {
                "stage_status": sorted(list(status_syms)),
                "stage09_snapshot": sorted(list(s09_syms)),
                "edge_metrics": sorted(list(edge_syms)),
                "edge_report": sorted(list(edge_report_syms)),
            },
            sort_keys=True,
        ),
    )

    # C6: Recency check.
    max_age_h = float("inf")
    if not edge.empty and "generated_at_utc" in edge.columns:
        ts = pd.to_datetime(edge["generated_at_utc"], utc=True, errors="coerce")
        if ts.notna().any():
            latest = ts.max()
            now = datetime.now(timezone.utc)
            max_age_h = float((now - latest.to_pydatetime()).total_seconds() / 3600.0)
    recency_ok = max_age_h <= float(thresholds.max_age_hours)
    _add_check(
        checks_rows,
        check_id="C6",
        check_name="generated_artifacts_recency",
        passed=bool(recency_ok),
        severity_if_fail="medium",
        metric_name="max_age_hours",
        metric_value=max_age_h,
        threshold=float(thresholds.max_age_hours),
        comparator="<=",
        source_path=edge_metrics_csv,
    )

    # C7: Nav coverage for canonical pages.
    nav_missing: list[str] = []
    mk_text = mkdocs_yml.read_text(encoding="utf-8", errors="ignore") if mkdocs_yml.exists() else ""
    for p in CANONICAL_NAV_PATHS:
        if p not in mk_text:
            nav_missing.append(p)
    _add_check(
        checks_rows,
        check_id="C7",
        check_name="mkdocs_nav_canonical_coverage",
        passed=len(nav_missing) == 0,
        severity_if_fail="high",
        metric_name="missing_nav_paths",
        metric_value=int(len(nav_missing)),
        threshold=0,
        comparator="==",
        source_path=mkdocs_yml,
        details=",".join(nav_missing),
    )

    checks = pd.DataFrame(checks_rows)
    checks = checks.sort_values(["check_id"]).reset_index(drop=True)

    issues_rows: list[dict[str, Any]] = []
    if not checks.empty:
        fail = checks[checks["status"].astype(str).str.lower() != "pass"].copy()
        for _, r in fail.iterrows():
            issues_rows.append(
                {
                    "issue_id": f"DOC_{r['check_id']}",
                    "symbol": "ALL",
                    "check_id": str(r["check_id"]),
                    "severity": str(r["severity_if_fail"]).lower(),
                    "component": "docs_contract",
                    "summary": str(r["check_name"]),
                    "details_json": json.dumps(
                        {
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
    issues = pd.DataFrame(issues_rows)

    out_checks_csv.parent.mkdir(parents=True, exist_ok=True)
    out_issues_csv.parent.mkdir(parents=True, exist_ok=True)
    out_report_md.parent.mkdir(parents=True, exist_ok=True)
    checks.to_csv(out_checks_csv, index=False)
    issues.to_csv(out_issues_csv, index=False)

    lines: list[str] = []
    lines.append("# OCO Docs Contract Report")
    lines.append("")
    lines.append(f"- generated_at_utc: `{datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}`")
    lines.append(f"- checks_csv: `{out_checks_csv}`")
    lines.append(f"- issues_csv: `{out_issues_csv}`")
    lines.append("")
    if not checks.empty:
        status = checks["status"].astype(str).str.lower()
        lines.append("## Summary")
        lines.append(f"- checks_total: `{int(len(checks))}`")
        lines.append(f"- failed: `{int((status != 'pass').sum())}`")
        lines.append(f"- high_or_critical_failed: `{int(((status != 'pass') & checks['severity_if_fail'].astype(str).str.lower().isin(['high','critical'])).sum())}`")
        lines.append("")
        lines.append("## Checks")
        lines.append(_table(checks))
        lines.append("")
    lines.append("## Issues")
    lines.append(_table(issues))
    out_report_md.write_text("\n".join(lines), encoding="utf-8")

    return checks, issues


def main() -> None:
    p = argparse.ArgumentParser(description="Validate OCO docs contract")
    p.add_argument("--docs-root", default="docs/strategy_bible")
    p.add_argument("--generated-root", default="docs/strategy_bible/generated")
    p.add_argument("--edge-metrics-csv", default="data/analysis/tick_opportunity_mining/edge_clarity_stage_metrics.csv")
    p.add_argument("--stage-status-csv", default="data/analysis/tick_opportunity_mining/oco_bible_stage_status.csv")
    p.add_argument("--metric-dictionary-md", default="docs/strategy_bible/metric_dictionary.md")
    p.add_argument("--edge-report-md", default="docs/analysis/oco_edge_clarity_report.md")
    p.add_argument("--mkdocs-yml", default="mkdocs.yml")
    p.add_argument("--max-age-hours", type=float, default=24.0 * 7.0)
    p.add_argument("--out-checks-csv", default="data/analysis/tick_opportunity_mining/docs_contract_checks.csv")
    p.add_argument("--out-issues-csv", default="data/analysis/tick_opportunity_mining/docs_contract_issues.csv")
    p.add_argument("--report-out", default="docs/analysis/oco_docs_contract_report.md")
    args = p.parse_args()

    checks, issues = run(
        docs_root=Path(str(args.docs_root)),
        generated_root=Path(str(args.generated_root)),
        edge_metrics_csv=Path(str(args.edge_metrics_csv)),
        stage_status_csv=Path(str(args.stage_status_csv)),
        metric_dictionary_md=Path(str(args.metric_dictionary_md)),
        edge_report_md=Path(str(args.edge_report_md)),
        mkdocs_yml=Path(str(args.mkdocs_yml)),
        out_checks_csv=Path(str(args.out_checks_csv)),
        out_issues_csv=Path(str(args.out_issues_csv)),
        out_report_md=Path(str(args.report_out)),
        thresholds=Thresholds(max_age_hours=float(args.max_age_hours)),
    )

    failed = int((checks["status"].astype(str).str.lower() != "pass").sum()) if not checks.empty else 0
    print(f"wrote checks: {args.out_checks_csv} rows={len(checks)}")
    print(f"wrote issues: {args.out_issues_csv} rows={len(issues)}")
    print(f"failed_checks={failed}")


if __name__ == "__main__":
    main()
