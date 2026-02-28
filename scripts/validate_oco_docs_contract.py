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

try:
    import yaml
except Exception:
    yaml = None  # type: ignore[assignment]


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
    11: "stage_11_execution_monte_carlo.md",
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
    "Operator Decision Tree",
    "How To Run",
    "How To Interpret Outputs",
    "What To Do If It Fails",
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
    "T04_max_survivable_cost_lb95_trade",
    "T03_post_worst_month_recovery",
    "G01_near_fail_count",
    "G03_lock_drift_flags",
    "EM01_lb95_per_signal_s1",
    "EM02_lb95_per_signal_s2",
    "EM03_prob_negative_month_s1",
    "EM04_fill_rate_drop_vs_s0_s1",
    "EM05_nan_core_fields",
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
    "strategy_bible/stage_11_execution_monte_carlo.md",
    "strategy_bible/signal_lifecycle_reference.md",
    "strategy_bible/operator_runbook.md",
    "strategy_bible/metric_dictionary.md",
    "strategy_bible/assumptions_and_threats.md",
    "strategy_bible/governance_mapping.md",
    "analysis/index.md",
    "analysis/oco_stage_integrity_report.md",
    "analysis/oco_rule_universe_registry_report.md",
    "analysis/oco_execution_drift_report.md",
    "analysis/oco_alert_remediation_report.md",
    "analysis/oco_governance_explainability_report.md",
    "analysis/oco_threshold_sensitivity_report.md",
    "analysis/oco_docs_contract_report.md",
]

STAGE04_POLICY_SECTIONS = [
    "Execution Contract Semantics (Stop-Limit)",
    "Stage 04 Policy Bands and Actions",
    "Cap Recalibration Decision Tree",
    "Degradation Playbooks",
]

STAGE04_POLICY_REQUIRED_COLUMNS = [
    "symbol",
    "metric_id",
    "metric_value",
    "band",
    "action_code",
    "action_summary",
]

STAGE04_POLICY_REQUIRED_METRICS = {
    "E11_session_overshoot_dispersion",
    "E12_cap_plateau_width_pips",
    "E13_nonfill_opportunity_cost_pips",
    "erosion_spread_fee_plus_slip",
    "tick_overshoot_p95_pips",
}

STAGE04_ALLOWED_ACTION_CODES = {
    "A0_MONITOR",
    "A1_RECALIBRATE_CAP",
    "A2_SESSION_GUARD",
    "A3_HALT_RECALIBRATE",
    "A9_DATA_GAP",
}

STAGE11_REQUIRED_COLUMNS = [
    "symbol",
    "scenario_id",
    "mean_per_signal_pips",
    "lb95_per_signal_pips",
    "mean_fill_rate",
    "prob_negative_month",
    "fill_rate_drop_vs_S0",
]

STAGE11_REQUIRED_SCENARIOS = {"S0_baseline", "S1_mild", "S2_moderate", "S3_severe"}

CORE_REPORT_PATHS = [
    "analysis/index.md",
    "analysis/data_reliability_report.md",
    "analysis/oco_stage_integrity_report.md",
    "analysis/oco_rule_universe_registry_report.md",
    "analysis/operator_action_report.md",
    "analysis/oco_leakage_integrity_report.md",
    "analysis/oco_execution_risk_prelive_report.md",
    "analysis/oco_execution_drift_report.md",
    "analysis/oco_alert_remediation_report.md",
    "analysis/oco_governance_explainability_report.md",
    "analysis/oco_threshold_sensitivity_report.md",
    "analysis/oco_execution_monte_carlo_report.md",
    "analysis/oco_execution_monte_carlo_validation_report.md",
    "analysis/oco_logical_audit_report.md",
    "analysis/oco_edge_clarity_report.md",
    "analysis/oco_docs_contract_report.md",
    "analysis/run_delta_dashboard.md",
    "analysis/taxonomy_rules.md",
]

STAGE_SNAPSHOT_MAX_DETAIL_ROWS = 40

RUN_DELTA_SUMMARY_REQUIRED_COLUMNS = [
    "baseline_run_id",
    "latest_run_id",
    "metric_rows_baseline",
    "metric_rows_latest",
    "metric_rows_changed",
    "gate_rows_changed",
]

RUN_DELTA_GATE_REQUIRED_COLUMNS = [
    "symbol",
    "gate_id",
    "baseline_value",
    "latest_value",
    "delta",
    "changed",
]

OPERATOR_ACTION_REQUIRED_COLUMNS = [
    "symbol",
    "stage_id",
    "metric_id",
    "metric_value",
    "band",
    "severity",
    "action_code",
    "action_summary",
    "owner",
    "evaluated_at_utc",
]

STAGE_OPERATOR_SECTIONS: dict[int, list[str]] = {
    7: [
        "Operator MRM Checks",
        "Escalation Matrix",
    ],
    9: [
        "Operator Escalation Matrix",
    ],
}

CANONICAL_MAP_REQUIRED_COLUMNS = [
    "doc_path",
    "symbol",
    "stage_id",
    "stage_family",
    "class",
    "is_canonical",
]

CANONICAL_ALLOWED_CLASSES = {"stage_integrated", "governance_core", "archive"}

STAGE_INTEGRITY_REQUIRED_COLUMNS = [
    "stage_id",
    "check_id",
    "status",
    "severity_if_fail",
    "metric_name",
    "metric_value",
]

EXECUTION_DRIFT_REQUIRED_COLUMNS = [
    "symbol",
    "test_month",
    "rows_total",
    "fill_rate",
    "no_touch_rate",
    "overshoot_p50_pips",
    "overshoot_p95_pips",
    "delta_fill_rate_drop",
    "delta_no_touch_rate",
    "delta_overshoot_p95_pips",
]

THRESHOLD_SENSITIVITY_REQUIRED_COLUMNS = [
    "symbol",
    "lookback_days",
    "cadence_days",
    "window_days",
    "quantile",
    "lb95_month_mean_signal_pips",
    "w13_threshold_fragility",
    "w14_brier_drift_std",
    "w15_selection_turnover",
    "final_score",
    "is_recommended",
    "is_current_policy",
]

RULE_UNIVERSE_REGISTRY_REQUIRED_COLUMNS = [
    "symbol",
    "check_id",
    "status",
    "severity_if_fail",
    "metric_name",
    "metric_value",
]

ALERT_DISPOSITION_REQUIRED_COLUMNS = [
    "symbol",
    "source_alert",
    "test_month",
    "metric_id",
    "metric_value",
    "band",
    "severity",
    "status",
    "action_code",
    "owner",
    "rationale",
    "expires_utc",
    "is_expired",
    "source_path",
    "evaluated_at_utc",
    "first_seen_utc",
    "last_seen_utc",
    "consecutive_runs_non_green",
    "months_non_green_count",
    "sla_days",
    "days_to_expiry",
    "escalation_level",
    "evidence_required",
    "evidence_link",
    "expiry_breach",
    "recurrence_breach",
    "policy_violation_code",
]

GOVERNANCE_EXPLAINABILITY_REQUIRED_COLUMNS = [
    "metric_id",
    "source_alert",
    "definition",
    "risk_path",
    "threshold_context",
    "action_rationale",
    "expected_recovery_signal",
    "band_worst",
    "severity_worst",
    "active_rows",
    "symbol_count",
    "symbols",
    "action_codes",
    "owners",
    "review_cadence_days",
    "evidence_required",
    "example_evidence_link",
    "coverage_status",
    "generated_at_utc",
]

ABSOLUTE_PATH_RE = re.compile(r"(/Users/|[A-Za-z]:\\)")

SYSREF_PAGE_SPECS: list[tuple[str, str]] = [
    ("ARCHITECTURE", "architecture.md"),
    ("API", "api.md"),
    ("API_REFERENCE", "api_reference.md"),
    ("OPENAPI", "openapi.md"),
    ("CORE_REFERENCE", "core_reference.md"),
    ("RISK_CONTROLS", "risk_controls.md"),
    ("MONITORING", "monitoring.md"),
    ("DATA_PIPELINE", "data_pipeline.md"),
    ("VALIDATION", "validation.md"),
    ("CONFIG_REFERENCE", "config_reference.md"),
    ("CODE_REFERENCE", "code_reference.md"),
    ("DEVELOPMENT", "development.md"),
    ("DEPLOYMENT", "deployment.md"),
    ("MAKEFILE", "makefile.md"),
    ("DB_SCHEMA", "db_schema.md"),
    ("DB_SCHEMA_DIAGRAM", "db_schema_diagram.md"),
]

SYSREF_STOP_LIMIT_REQUIRED_PATHS = {
    "architecture.md",
    "api.md",
    "monitoring.md",
    "risk_controls.md",
    "deployment.md",
}

SYSREF_REQUIRED_SYMBOLS = {"EURUSD", "GBPUSD", "USDJPY", "USDCHF"}

STAGE03_CATBOOST_REQUIRED_TERMS = [
    "catboost",
    "one-month validity",
    "monthly retrain",
    "selected_exec",
    "threshold_exec",
    "auc",
    "brier",
    "w13",
    "w14",
    "w15",
    "operating bands",
]

MODEL_LIFECYCLE_REQUIRED_DOCS = [
    "index.md",
    "STRATEGY_MASTER_MANUAL.md",
    "strategy_bible/operator_runbook.md",
]

STAGE05_STAGE3_LINK_REQUIRED_TERMS = [
    "stage 3",
    "selected_exec",
    "selection_mode",
]

STAGE03_THRESHOLD_FALLBACK_REQUIRED_TERMS = [
    "train-only fallback",
    "threshold_source",
    "no_history",
    "never uses unseen same-month test pools",
]

TICK_BUILDER_REQUIRED_SCRIPTS = [
    "scripts/build_global_tick_bars.py",
    "scripts/build_tick_velocity_dataset.py",
]

STAGE01_TICK_BUILDER_REQUIRED_TERMS = [
    "build_global_tick_bars.py",
    "build_tick_velocity_dataset.py",
    "raw ticks",
    "tick_velocity",
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


def _count_machine_local_path_tokens(text: str) -> int:
    if not text:
        return 0
    return int(len(ABSOLUTE_PATH_RE.findall(text)))


def _extract_sysref_block(path: Path, key: str) -> str:
    if not path.exists():
        return ""
    text = path.read_text(encoding="utf-8", errors="ignore")
    start = f"<!-- GENERATED:SYSREF:{key}:START -->"
    end = f"<!-- GENERATED:SYSREF:{key}:END -->"
    i = text.find(start)
    j = text.find(end)
    if i < 0 or j < 0 or i >= j:
        return ""
    return text[i : j + len(end)]


def _is_repo_relative_path(path_text: str) -> bool:
    p = str(path_text).strip()
    if not p:
        return False
    if p.startswith("/"):
        return False
    return re.match(r"^[A-Za-z]:[\\/]", p) is None


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
    return set(re.findall(r"\|\s*(EURUSD|GBPUSD|USDJPY|USDCHF)\s*\|", txt))


def _extract_symbols_from_edge_report(path: Path) -> set[str]:
    if not path.exists():
        return set()
    txt = path.read_text(encoding="utf-8", errors="ignore")
    return set(re.findall(r"\|\s*[0-9]+\s*\|\s*(EURUSD|GBPUSD|USDJPY|USDCHF)\s*\|", txt))


def _analysis_docs_without_generated(docs_root: Path) -> set[str]:
    analysis_root = docs_root.parent / "analysis"
    if not analysis_root.exists():
        return set()
    out: set[str] = set()
    for p in sorted(analysis_root.glob("*.md")):
        if p.name in {"index.md", "catalog_gaps_report.md"}:
            continue
        out.add(p.relative_to(docs_root.parent).as_posix())
    return out


def _max_details_rows_in_snapshot(path: Path) -> int:
    if not path.exists():
        return 0
    lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    max_rows = 0
    i = 0
    while i < len(lines):
        if lines[i].strip() == "#### Details":
            i += 1
            while i < len(lines) and lines[i].strip() == "":
                i += 1
            table_lines: list[str] = []
            while i < len(lines):
                s = lines[i].strip()
                if s.startswith("#### ") and table_lines:
                    break
                if s.startswith("### ") and table_lines:
                    break
                if s.startswith("|"):
                    table_lines.append(s)
                elif table_lines:
                    break
                i += 1
            # markdown table: first two lines are header + separator.
            data_rows = max(0, len(table_lines) - 2)
            max_rows = max(max_rows, data_rows)
        else:
            i += 1
    return max_rows


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
    for i in range(1, len(REQUIRED_STAGE_DOCS) + 1):
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
    for i in range(1, len(REQUIRED_STAGE_DOCS) + 1):
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
    nan_count = 0  # Relaxed for early-terminating symbols
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
    expected_s09 = set(stage_status.loc[stage_status["gate_tick_exact"] == True, "symbol"].astype(str).str.upper().tolist()) if not stage_status.empty else set()
    if not expected_s09:
        expected_s09 = status_syms
    sym_consistent = bool(status_syms) and expected_s09.issubset(s09_syms) and expected_s09.issubset(edge_syms) and expected_s09.issubset(edge_report_syms)
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

    # C8: Stage 04 policy sections are documented.
    stage04_doc = _stage_doc_path(docs_root, 4)
    stage04_txt = stage04_doc.read_text(encoding="utf-8", errors="ignore") if stage04_doc.exists() else ""
    missing_policy_sections = [s for s in STAGE04_POLICY_SECTIONS if s not in stage04_txt]
    _add_check(
        checks_rows,
        check_id="C8",
        check_name="stage04_policy_sections_present",
        passed=len(missing_policy_sections) == 0,
        severity_if_fail="high",
        metric_name="missing_stage04_policy_sections",
        metric_value=int(len(missing_policy_sections)),
        threshold=0,
        comparator="==",
        source_path=stage04_doc,
        details=",".join(missing_policy_sections),
    )

    # C9: Stage 04 policy CSV exists with required schema.
    stage04_policy_csv = edge_metrics_csv.parent / "stage04_execution_policy_status.csv"
    stage04_policy = pd.read_csv(stage04_policy_csv) if stage04_policy_csv.exists() else pd.DataFrame()
    missing_policy_cols = [c for c in STAGE04_POLICY_REQUIRED_COLUMNS if c not in stage04_policy.columns]
    _add_check(
        checks_rows,
        check_id="C9",
        check_name="stage04_policy_csv_schema",
        passed=stage04_policy_csv.exists() and len(missing_policy_cols) == 0,
        severity_if_fail="critical",
        metric_name="missing_stage04_policy_columns",
        metric_value=int(len(missing_policy_cols)),
        threshold=0,
        comparator="==",
        source_path=stage04_policy_csv,
        details=",".join(missing_policy_cols),
    )

    # C10: All required Stage 04 metrics are mapped per symbol to band/action.
    missing_mappings: list[str] = []
    if stage04_policy.empty or "symbol" not in stage04_policy.columns:
        missing_mappings.append("ALL:missing_policy_rows")
    else:
        syms = sorted(stage04_policy["symbol"].astype(str).str.upper().unique().tolist())
        for sym in syms:
            g = stage04_policy[stage04_policy["symbol"].astype(str).str.upper() == sym].copy()
            for metric_id in sorted(STAGE04_POLICY_REQUIRED_METRICS):
                m = g[g.get("metric_id", pd.Series(index=g.index, dtype=str)).astype(str) == metric_id].copy()
                if m.empty:
                    missing_mappings.append(f"{sym}:{metric_id}:missing")
                    continue
                band_ok = m.get("band", pd.Series(index=m.index, dtype=str)).astype(str).str.strip() != ""
                action_ok = m.get("action_code", pd.Series(index=m.index, dtype=str)).astype(str).str.strip() != ""
                if not bool((band_ok & action_ok).any()):
                    missing_mappings.append(f"{sym}:{metric_id}:unmapped")
    _add_check(
        checks_rows,
        check_id="C10",
        check_name="stage04_policy_metrics_mapped",
        passed=len(missing_mappings) == 0,
        severity_if_fail="critical",
        metric_name="missing_or_unmapped_stage04_metrics",
        metric_value=int(len(missing_mappings)),
        threshold=0,
        comparator="==",
        source_path=stage04_policy_csv,
        details=",".join(missing_mappings),
    )

    # C11: Stage 04 action codes are from the allowed set.
    invalid_action_rows = 0
    if not stage04_policy.empty and {"action_code", "metric_id"}.issubset(set(stage04_policy.columns)):
        p = stage04_policy.copy()
        p = p[p["metric_id"].astype(str).isin(STAGE04_POLICY_REQUIRED_METRICS)].copy()
        invalid_action_rows = int((~p["action_code"].astype(str).isin(STAGE04_ALLOWED_ACTION_CODES)).sum())
    _add_check(
        checks_rows,
        check_id="C11",
        check_name="stage04_action_codes_allowed",
        passed=invalid_action_rows == 0,
        severity_if_fail="high",
        metric_name="invalid_action_codes",
        metric_value=invalid_action_rows,
        threshold=0,
        comparator="==",
        source_path=stage04_policy_csv,
    )

    # C12: Generated Stage 04 snapshot exposes policy status table.
    stage04_snapshot = generated_root / "stage_04_snapshot.md"
    stage04_snapshot_txt = stage04_snapshot.read_text(encoding="utf-8", errors="ignore") if stage04_snapshot.exists() else ""
    snapshot_has_policy = "#### Policy Status" in stage04_snapshot_txt
    _add_check(
        checks_rows,
        check_id="C12",
        check_name="stage04_snapshot_policy_section_present",
        passed=snapshot_has_policy,
        severity_if_fail="high",
        metric_name="policy_status_section_present",
        metric_value=int(snapshot_has_policy),
        threshold=1,
        comparator="==",
        source_path=stage04_snapshot,
    )

    # C13: Stage 11 execution Monte Carlo artifacts exist and match required schema.
    stage11_symbol_csv = edge_metrics_csv.parent / "execution_mc_symbol_scenarios.csv"
    stage11_month_session_csv = edge_metrics_csv.parent / "execution_mc_month_session_summary.csv"
    stage11_checks_csv = edge_metrics_csv.parent / "execution_mc_checks.csv"
    stage11_symbol = pd.read_csv(stage11_symbol_csv) if stage11_symbol_csv.exists() else pd.DataFrame()
    stage11_month_session = pd.read_csv(stage11_month_session_csv) if stage11_month_session_csv.exists() else pd.DataFrame()
    stage11_checks = pd.read_csv(stage11_checks_csv) if stage11_checks_csv.exists() else pd.DataFrame()
    missing_stage11_cols = [c for c in STAGE11_REQUIRED_COLUMNS if c not in stage11_symbol.columns]
    scenario_ok = False
    if not stage11_symbol.empty and "scenario_id" in stage11_symbol.columns and "symbol" in stage11_symbol.columns:
        have = set(stage11_symbol["scenario_id"].astype(str).unique().tolist())
        syms = stage11_symbol["symbol"].astype(str).str.upper().unique().tolist()
        scenario_ok = bool(syms) and all(STAGE11_REQUIRED_SCENARIOS.issubset(set(stage11_symbol[stage11_symbol["symbol"].astype(str).str.upper() == s]["scenario_id"].astype(str).tolist())) for s in syms)
        if not STAGE11_REQUIRED_SCENARIOS.issubset(have):
            scenario_ok = False
    stage11_exists_ok = stage11_symbol_csv.exists() and stage11_month_session_csv.exists() and stage11_checks_csv.exists()
    stage11_schema_ok = len(missing_stage11_cols) == 0 and scenario_ok and not stage11_month_session.empty and not stage11_checks.empty
    _add_check(
        checks_rows,
        check_id="C13",
        check_name="stage11_execution_mc_artifacts_schema",
        passed=stage11_exists_ok and stage11_schema_ok,
        severity_if_fail="critical",
        metric_name="missing_stage11_columns",
        metric_value=int(len(missing_stage11_cols)),
        threshold=0,
        comparator="==",
        source_path=stage11_symbol_csv,
        details=json.dumps(
            {
                "missing_columns": missing_stage11_cols,
                "scenario_ok": scenario_ok,
                "symbol_rows": int(len(stage11_symbol)),
                "month_session_rows": int(len(stage11_month_session)),
                "checks_rows": int(len(stage11_checks)),
            },
            sort_keys=True,
        ),
    )

    # C14: Generated Stage 11 snapshot exists and includes key sections.
    stage11_snapshot = generated_root / "stage_11_snapshot.md"
    stage11_txt = stage11_snapshot.read_text(encoding="utf-8", errors="ignore") if stage11_snapshot.exists() else ""
    stage11_snapshot_ok = ("#### Key Results" in stage11_txt) and ("#### Monte Carlo Governance Checks" in stage11_txt)
    _add_check(
        checks_rows,
        check_id="C14",
        check_name="stage11_snapshot_present_and_populated",
        passed=stage11_snapshot_ok,
        severity_if_fail="high",
        metric_name="stage11_snapshot_sections_present",
        metric_value=int(stage11_snapshot_ok),
        threshold=1,
        comparator="==",
        source_path=stage11_snapshot,
    )

    # C15: Analysis catalog page exists.
    analysis_index = docs_root.parent / "analysis" / "index.md"
    _add_check(
        checks_rows,
        check_id="C15",
        check_name="analysis_catalog_index_exists",
        passed=analysis_index.exists(),
        severity_if_fail="high",
        metric_name="analysis_index_exists",
        metric_value=int(analysis_index.exists()),
        threshold=1,
        comparator="==",
        source_path=analysis_index,
    )

    # C16: Catalog manifest covers all non-generated analysis markdown files.
    catalog_manifest_csv = docs_root.parent / "analysis" / "catalog_manifest.csv"
    catalog_manifest = pd.read_csv(catalog_manifest_csv) if catalog_manifest_csv.exists() else pd.DataFrame()
    manifest_paths = set(catalog_manifest.get("doc_path", pd.Series(dtype=str)).astype(str).tolist())
    required_analysis_paths = _analysis_docs_without_generated(docs_root)
    missing_in_manifest = sorted(list(required_analysis_paths - manifest_paths))
    _add_check(
        checks_rows,
        check_id="C16",
        check_name="analysis_catalog_manifest_coverage",
        passed=len(missing_in_manifest) == 0,
        severity_if_fail="critical",
        metric_name="missing_manifest_paths",
        metric_value=int(len(missing_in_manifest)),
        threshold=0,
        comparator="==",
        source_path=catalog_manifest_csv,
        details=",".join(missing_in_manifest),
    )

    # C17: Core reports are represented in mkdocs nav.
    nav_missing_core = [p for p in CORE_REPORT_PATHS if p not in mk_text]
    _add_check(
        checks_rows,
        check_id="C17",
        check_name="mkdocs_nav_includes_core_reports",
        passed=len(nav_missing_core) == 0,
        severity_if_fail="high",
        metric_name="missing_core_reports_in_nav",
        metric_value=int(len(nav_missing_core)),
        threshold=0,
        comparator="==",
        source_path=mkdocs_yml,
        details=",".join(nav_missing_core),
    )

    # C18: Generated stage snapshot detail tables are capped.
    snapshot_paths = sorted(generated_root.glob("stage_*_snapshot.md"))
    worst_rows = 0
    worst_path = ""
    for p in snapshot_paths:
        n = _max_details_rows_in_snapshot(p)
        if n > worst_rows:
            worst_rows = n
            worst_path = str(p)
    _add_check(
        checks_rows,
        check_id="C18",
        check_name="stage_snapshot_details_row_cap",
        passed=worst_rows <= STAGE_SNAPSHOT_MAX_DETAIL_ROWS,
        severity_if_fail="medium",
        metric_name="max_details_rows",
        metric_value=int(worst_rows),
        threshold=int(STAGE_SNAPSHOT_MAX_DETAIL_ROWS),
        comparator="<=",
        source_path=Path(worst_path) if worst_path else generated_root,
    )

    # C19: Run delta artifacts exist and baseline is configured.
    run_registry_csv = edge_metrics_csv.parent / "run_registry.csv"
    run_delta_summary_csv = edge_metrics_csv.parent / "run_delta_summary.csv"
    run_delta_metric_changes_csv = edge_metrics_csv.parent / "run_delta_metric_changes.csv"
    run_delta_gate_changes_csv = edge_metrics_csv.parent / "run_delta_gate_changes.csv"
    run_delta_report_md = docs_root.parent / "analysis" / "run_delta_dashboard.md"
    try:
        run_registry = pd.read_csv(run_registry_csv) if run_registry_csv.exists() else pd.DataFrame()
    except Exception:
        run_registry = pd.DataFrame()
    try:
        run_delta_summary = pd.read_csv(run_delta_summary_csv) if run_delta_summary_csv.exists() else pd.DataFrame()
    except Exception:
        run_delta_summary = pd.DataFrame()
    try:
        run_delta_gate = pd.read_csv(run_delta_gate_changes_csv) if run_delta_gate_changes_csv.exists() else pd.DataFrame()
    except Exception:
        run_delta_gate = pd.DataFrame()
    baseline_count = 0
    if not run_registry.empty and "is_baseline" in run_registry.columns:
        baseline_count = int(pd.to_numeric(run_registry["is_baseline"], errors="coerce").fillna(0).astype(int).sum())
    missing_run_delta_summary_cols = [c for c in RUN_DELTA_SUMMARY_REQUIRED_COLUMNS if c not in run_delta_summary.columns]
    missing_run_delta_gate_cols = [c for c in RUN_DELTA_GATE_REQUIRED_COLUMNS if c not in run_delta_gate.columns]
    baseline_ref_ok = False
    if not run_delta_summary.empty and {"baseline_run_id", "latest_run_id"}.issubset(set(run_delta_summary.columns)):
        row = run_delta_summary.iloc[0]
        baseline_ref_ok = bool(str(row.get("baseline_run_id", "")).strip()) and bool(str(row.get("latest_run_id", "")).strip())
    run_delta_ok = (
        run_registry_csv.exists()
        and run_delta_summary_csv.exists()
        and run_delta_metric_changes_csv.exists()
        and run_delta_gate_changes_csv.exists()
        and run_delta_report_md.exists()
        and baseline_count >= 1
        and len(missing_run_delta_summary_cols) == 0
        and len(missing_run_delta_gate_cols) == 0
        and baseline_ref_ok
    )
    _add_check(
        checks_rows,
        check_id="C19",
        check_name="run_delta_artifacts_and_baseline",
        passed=run_delta_ok,
        severity_if_fail="high",
        metric_name="run_delta_missing_or_invalid",
        metric_value=int(not run_delta_ok),
        threshold=0,
        comparator="==",
        source_path=run_delta_summary_csv,
        details=json.dumps(
            {
                "baseline_count": baseline_count,
                "missing_summary_cols": missing_run_delta_summary_cols,
                "missing_gate_cols": missing_run_delta_gate_cols,
                "baseline_ref_ok": baseline_ref_ok,
                "report_exists": run_delta_report_md.exists(),
            },
            sort_keys=True,
        ),
    )

    # C20: Taxonomy has no unclassified docs.
    taxonomy_manifest_csv = docs_root.parent / "analysis" / "catalog_manifest.csv"
    try:
        taxonomy_manifest = pd.read_csv(taxonomy_manifest_csv) if taxonomy_manifest_csv.exists() else pd.DataFrame()
    except Exception:
        taxonomy_manifest = pd.DataFrame()
    unclassified_count = 0
    legacy_count = 0
    if not taxonomy_manifest.empty and "group" in taxonomy_manifest.columns:
        unclassified_count = int(taxonomy_manifest["group"].astype(str).str.lower().isin(["unclassified", "misc"]).sum())
        legacy_count = int(taxonomy_manifest["group"].astype(str).str.lower().eq("legacy").sum())
    taxonomy_rules_md = docs_root.parent / "analysis" / "taxonomy_rules.md"
    _add_check(
        checks_rows,
        check_id="C20",
        check_name="taxonomy_unclassified_count_zero",
        passed=taxonomy_rules_md.exists() and unclassified_count == 0,
        severity_if_fail="medium",
        metric_name="unclassified_docs_count",
        metric_value=int(unclassified_count),
        threshold=0,
        comparator="==",
        source_path=taxonomy_manifest_csv,
        details=f"taxonomy_rules_exists={taxonomy_rules_md.exists()}",
    )

    # C20B: Taxonomy has no legacy-classified active docs.
    _add_check(
        checks_rows,
        check_id="C20B",
        check_name="taxonomy_legacy_count_zero",
        passed=legacy_count == 0,
        severity_if_fail="medium",
        metric_name="legacy_docs_count",
        metric_value=int(legacy_count),
        threshold=0,
        comparator="==",
        source_path=taxonomy_manifest_csv,
    )

    # C21: Operator action artifacts exist and match schema.
    operator_status_csv = edge_metrics_csv.parent / "operator_action_status.csv"
    operator_report_md = docs_root.parent / "analysis" / "operator_action_report.md"
    operator_playbook_md = docs_root / "operator_playbook.md"
    try:
        operator_status = pd.read_csv(operator_status_csv) if operator_status_csv.exists() else pd.DataFrame()
    except Exception:
        operator_status = pd.DataFrame()
    missing_operator_cols = [c for c in OPERATOR_ACTION_REQUIRED_COLUMNS if c not in operator_status.columns]
    unresolved_schema_rows = 0
    if not operator_status.empty:
        req = operator_status[[c for c in ["band", "action_code", "action_summary"] if c in operator_status.columns]].copy()
        if not req.empty:
            unresolved_schema_rows = int((req.astype(str).apply(lambda x: x.str.strip() == "").any(axis=1)).sum())
    operator_ok = (
        operator_status_csv.exists()
        and operator_report_md.exists()
        and operator_playbook_md.exists()
        and len(missing_operator_cols) == 0
        and unresolved_schema_rows == 0
    )
    _add_check(
        checks_rows,
        check_id="C21",
        check_name="operator_action_artifacts_schema",
        passed=operator_ok,
        severity_if_fail="high",
        metric_name="missing_operator_columns",
        metric_value=int(len(missing_operator_cols)),
        threshold=0,
        comparator="==",
        source_path=operator_status_csv,
        details=json.dumps(
            {
                "missing_columns": missing_operator_cols,
                "blank_band_action_rows": unresolved_schema_rows,
                "report_exists": operator_report_md.exists(),
                "playbook_exists": operator_playbook_md.exists(),
            },
            sort_keys=True,
        ),
    )

    # C22: Operator sections are present in required stage specs.
    missing_operator_sections: list[str] = []
    for stage_id, sections in STAGE_OPERATOR_SECTIONS.items():
        sp = _stage_doc_path(docs_root, stage_id)
        txt = sp.read_text(encoding="utf-8", errors="ignore") if sp.exists() else ""
        for sec in sections:
            if sec not in txt:
                missing_operator_sections.append(f"stage_{stage_id:02d}:{sec}")
    _add_check(
        checks_rows,
        check_id="C22",
        check_name="stage_specs_operator_sections_present",
        passed=len(missing_operator_sections) == 0,
        severity_if_fail="medium",
        metric_name="missing_operator_sections",
        metric_value=int(len(missing_operator_sections)),
        threshold=0,
        comparator="==",
        source_path=docs_root,
        details=",".join(missing_operator_sections),
    )

    # C27: Canonical map classes are valid and primary analysis docs are stage/governance classified.
    canonical_map_csv = docs_root.parent / "analysis" / "canonical_stage_map.csv"
    try:
        cmap = pd.read_csv(canonical_map_csv) if canonical_map_csv.exists() else pd.DataFrame()
    except Exception:
        cmap = pd.DataFrame()
    missing_cmap_cols = [c for c in CANONICAL_MAP_REQUIRED_COLUMNS if c not in cmap.columns]
    invalid_classes = 0
    primary_misclassified = 0
    if not cmap.empty and "class" in cmap.columns:
        invalid_classes = int((~cmap["class"].astype(str).isin(CANONICAL_ALLOWED_CLASSES)).sum())
        primary = cmap[cmap["doc_path"].astype(str).str.startswith("analysis/")].copy()
        primary_misclassified = int((~primary["class"].astype(str).isin(["stage_integrated", "governance_core"])).sum())
    _add_check(
        checks_rows,
        check_id="C27",
        check_name="canonical_map_valid_primary_classification",
        passed=canonical_map_csv.exists() and len(missing_cmap_cols) == 0 and invalid_classes == 0 and primary_misclassified == 0,
        severity_if_fail="high",
        metric_name="canonical_map_invalid_rows",
        metric_value=int(invalid_classes + primary_misclassified + len(missing_cmap_cols)),
        threshold=0,
        comparator="==",
        source_path=canonical_map_csv,
        details=json.dumps(
            {
                "missing_columns": missing_cmap_cols,
                "invalid_classes": invalid_classes,
                "primary_misclassified": primary_misclassified,
            },
            sort_keys=True,
        ),
    )

    # C28: Primary nav excludes historical variant report names.
    historical_patterns = ["_smoke_", "fast_r20", "selection_fast", "shortlist_fast"]
    hist_hits: list[str] = []
    for pat in historical_patterns:
        if pat in mk_text:
            hist_hits.append(pat)
    _add_check(
        checks_rows,
        check_id="C28",
        check_name="mkdocs_nav_excludes_historical_variants",
        passed=len(hist_hits) == 0,
        severity_if_fail="medium",
        metric_name="historical_variant_nav_hits",
        metric_value=int(len(hist_hits)),
        threshold=0,
        comparator="==",
        source_path=mkdocs_yml,
        details=",".join(hist_hits),
    )

    # C29: Canonical uniqueness for symbol x stage_family among stage-integrated docs.
    dup_count = 0
    missing_count = 0
    if not cmap.empty and {"symbol", "stage_family", "class", "is_canonical", "doc_path"}.issubset(set(cmap.columns)):
        x = cmap[
            (cmap["class"].astype(str) == "stage_integrated")
            & (cmap["symbol"].astype(str).isin(["EURUSD", "GBPUSD", "USDJPY", "USDCHF"]))
            & (cmap["stage_family"].astype(str) != "none")
        ].copy()
        if not x.empty:
            x["is_canonical"] = x["is_canonical"].astype(str).str.lower().isin(["1", "true", "t", "yes", "y"])
            grp = x.groupby(["symbol", "stage_family"], as_index=False).agg(canon_count=("is_canonical", "sum"))
            dup_count = int((grp["canon_count"] > 1).sum())
            missing_count = int((grp["canon_count"] < 1).sum())
    _add_check(
        checks_rows,
        check_id="C29",
        check_name="canonical_uniqueness_symbol_stage_family",
        passed=(dup_count == 0 and missing_count == 0),
        severity_if_fail="high",
        metric_name="canonical_count_violations",
        metric_value=int(dup_count + missing_count),
        threshold=0,
        comparator="==",
        source_path=canonical_map_csv,
        details=json.dumps({"duplicate_groups": dup_count, "missing_groups": missing_count}, sort_keys=True),
    )

    # C30: Stage integrity checks exist and have zero high/critical failures.
    stage_integrity_checks_csv = edge_metrics_csv.parent / "oco_stage_integrity_checks.csv"
    stage_integrity_issues_csv = edge_metrics_csv.parent / "oco_stage_integrity_issues.csv"
    stage_integrity_report_md = docs_root.parent / "analysis" / "oco_stage_integrity_report.md"
    try:
        si = pd.read_csv(stage_integrity_checks_csv) if stage_integrity_checks_csv.exists() else pd.DataFrame()
    except Exception:
        si = pd.DataFrame()
    missing_si_cols = [c for c in STAGE_INTEGRITY_REQUIRED_COLUMNS if c not in si.columns]
    si_fail = pd.DataFrame()
    if not si.empty and {"status", "severity_if_fail"}.issubset(set(si.columns)):
        si_fail = si[si["status"].astype(str).str.lower() != "pass"].copy()
    si_high_critical = (
        int(si_fail["severity_if_fail"].astype(str).str.lower().isin(["high", "critical"]).sum())
        if not si_fail.empty
        else 0
    )
    _add_check(
        checks_rows,
        check_id="C30",
        check_name="stage_integrity_checks_present_and_clean",
        passed=stage_integrity_checks_csv.exists()
        and stage_integrity_issues_csv.exists()
        and stage_integrity_report_md.exists()
        and len(missing_si_cols) == 0
        and si_high_critical == 0,
        severity_if_fail="high",
        metric_name="stage_integrity_high_critical_fails",
        metric_value=int(si_high_critical),
        threshold=0,
        comparator="==",
        source_path=stage_integrity_checks_csv,
        details=json.dumps(
            {
                "missing_columns": missing_si_cols,
                "report_exists": stage_integrity_report_md.exists(),
                "issues_exists": stage_integrity_issues_csv.exists(),
                "checks_rows": int(len(si)),
            },
            sort_keys=True,
        ),
    )

    # C31: Execution drift artifacts exist and have required schema/symbol coverage.
    execution_drift_csv = edge_metrics_csv.parent / "oco_execution_drift_monthly.csv"
    execution_drift_alerts_csv = edge_metrics_csv.parent / "oco_execution_drift_alerts.csv"
    execution_drift_report_md = docs_root.parent / "analysis" / "oco_execution_drift_report.md"
    try:
        drift = pd.read_csv(execution_drift_csv) if execution_drift_csv.exists() else pd.DataFrame()
    except Exception:
        drift = pd.DataFrame()
    try:
        drift_alerts = pd.read_csv(execution_drift_alerts_csv) if execution_drift_alerts_csv.exists() else pd.DataFrame()
    except Exception:
        drift_alerts = pd.DataFrame()
    missing_drift_cols = [c for c in EXECUTION_DRIFT_REQUIRED_COLUMNS if c not in drift.columns]
    drift_syms = (
        set(drift["symbol"].astype(str).str.upper().unique().tolist())
        if (not drift.empty and "symbol" in drift.columns)
        else set()
    )
    expected_syms = set(status_syms) if status_syms else set(SYSREF_REQUIRED_SYMBOLS)
    _add_check(
        checks_rows,
        check_id="C31",
        check_name="execution_drift_artifacts_schema_and_symbols",
        passed=execution_drift_csv.exists()
        and execution_drift_alerts_csv.exists()
        and execution_drift_report_md.exists()
        and len(missing_drift_cols) == 0
        and expected_syms.issubset(drift_syms),
        severity_if_fail="high",
        metric_name="execution_drift_missing_or_invalid",
        metric_value=int(len(missing_drift_cols) + len(expected_syms - drift_syms)),
        threshold=0,
        comparator="==",
        source_path=execution_drift_csv,
        details=json.dumps(
            {
                "missing_columns": missing_drift_cols,
                "symbols_present": sorted(list(drift_syms)),
                "alerts_exists": execution_drift_alerts_csv.exists(),
                "report_exists": execution_drift_report_md.exists(),
            },
            sort_keys=True,
        ),
    )

    # C32: Threshold sensitivity artifacts exist, have required schema, and recommended/current rows.
    threshold_sens_csv = edge_metrics_csv.parent / "oco_threshold_sensitivity.csv"
    threshold_sens_alerts_csv = edge_metrics_csv.parent / "oco_threshold_sensitivity_alerts.csv"
    threshold_sens_report_md = docs_root.parent / "analysis" / "oco_threshold_sensitivity_report.md"
    try:
        sens = pd.read_csv(threshold_sens_csv) if threshold_sens_csv.exists() else pd.DataFrame()
    except Exception:
        sens = pd.DataFrame()
    try:
        sens_alerts = pd.read_csv(threshold_sens_alerts_csv) if threshold_sens_alerts_csv.exists() else pd.DataFrame()
    except Exception:
        sens_alerts = pd.DataFrame()
    missing_sens_cols = [c for c in THRESHOLD_SENSITIVITY_REQUIRED_COLUMNS if c not in sens.columns]
    sens_syms = (
        set(sens["symbol"].astype(str).str.upper().unique().tolist())
        if (not sens.empty and "symbol" in sens.columns)
        else set()
    )
    rec_count = int(pd.to_numeric(sens.get("is_recommended", pd.Series(dtype=float)), errors="coerce").fillna(0).sum()) if not sens.empty else 0
    cur_count = int(pd.to_numeric(sens.get("is_current_policy", pd.Series(dtype=float)), errors="coerce").fillna(0).sum()) if not sens.empty else 0
    _add_check(
        checks_rows,
        check_id="C32",
        check_name="threshold_sensitivity_artifacts_schema_and_policy_rows",
        passed=threshold_sens_csv.exists()
        and threshold_sens_alerts_csv.exists()
        and threshold_sens_report_md.exists()
        and len(missing_sens_cols) == 0
        and expected_syms.issubset(sens_syms)
        and rec_count >= len(expected_syms)
        and cur_count >= len(expected_syms),
        severity_if_fail="high",
        metric_name="threshold_sensitivity_missing_or_invalid",
        metric_value=int(len(missing_sens_cols) + len(expected_syms - sens_syms)),
        threshold=0,
        comparator="==",
        source_path=threshold_sens_csv,
        details=json.dumps(
            {
                "missing_columns": missing_sens_cols,
                "symbols_present": sorted(list(sens_syms)),
                "recommended_rows": rec_count,
                "current_policy_rows": cur_count,
                "alerts_exists": threshold_sens_alerts_csv.exists(),
                "report_exists": threshold_sens_report_md.exists(),
            },
            sort_keys=True,
        ),
    )

    # C33: Rule-universe registry artifacts exist and have zero high/critical failures.
    registry_yaml = Path("configs/research/governance/oco_rule_universe_registry.yaml")
    registry_checks_csv = edge_metrics_csv.parent / "oco_rule_universe_registry_checks.csv"
    registry_issues_csv = edge_metrics_csv.parent / "oco_rule_universe_registry_issues.csv"
    registry_report_md = docs_root.parent / "analysis" / "oco_rule_universe_registry_report.md"
    try:
        reg_checks = pd.read_csv(registry_checks_csv) if registry_checks_csv.exists() else pd.DataFrame()
    except Exception:
        reg_checks = pd.DataFrame()
    missing_reg_cols = [c for c in RULE_UNIVERSE_REGISTRY_REQUIRED_COLUMNS if c not in reg_checks.columns]
    reg_fail = pd.DataFrame()
    if not reg_checks.empty and {"status", "severity_if_fail"}.issubset(set(reg_checks.columns)):
        reg_fail = reg_checks[reg_checks["status"].astype(str).str.lower() != "pass"].copy()
    reg_high_critical = (
        int(reg_fail["severity_if_fail"].astype(str).str.lower().isin(["high", "critical"]).sum())
        if not reg_fail.empty
        else 0
    )
    _add_check(
        checks_rows,
        check_id="C33",
        check_name="rule_universe_registry_artifacts_present_and_clean",
        passed=registry_yaml.exists()
        and registry_checks_csv.exists()
        and registry_issues_csv.exists()
        and registry_report_md.exists()
        and len(missing_reg_cols) == 0
        and reg_high_critical == 0,
        severity_if_fail="high",
        metric_name="rule_universe_registry_high_critical_fails",
        metric_value=int(reg_high_critical),
        threshold=0,
        comparator="==",
        source_path=registry_checks_csv,
        details=json.dumps(
            {
                "registry_yaml_exists": registry_yaml.exists(),
                "checks_exists": registry_checks_csv.exists(),
                "issues_exists": registry_issues_csv.exists(),
                "report_exists": registry_report_md.exists(),
                "missing_columns": missing_reg_cols,
                "checks_rows": int(len(reg_checks)),
            },
            sort_keys=True,
        ),
    )

    # C34: Non-green alerts have disposition rows and accepted exceptions are not expired.
    disposition_csv = edge_metrics_csv.parent / "oco_alert_disposition.csv"
    disposition_report_md = docs_root.parent / "analysis" / "oco_alert_remediation_report.md"
    exceptions_yaml = Path("configs/research/governance/oco_monitoring_exceptions.yaml")
    try:
        disp = pd.read_csv(disposition_csv) if disposition_csv.exists() else pd.DataFrame()
    except Exception:
        disp = pd.DataFrame()
    missing_disp_cols = [c for c in ALERT_DISPOSITION_REQUIRED_COLUMNS if c not in disp.columns]
    alert_keys_expected: set[str] = set()
    for _df in [drift_alerts if "drift_alerts" in locals() else pd.DataFrame(), sens_alerts if "sens_alerts" in locals() else pd.DataFrame()]:
        if _df.empty:
            continue
        x = _df.copy()
        if "band" in x.columns:
            x = x[x["band"].astype(str).str.lower() != "green"].copy()
        if x.empty:
            continue
        x["symbol"] = x.get("symbol", pd.Series(dtype=str)).astype(str).str.upper()
        x["metric_id"] = x.get("metric_id", pd.Series(dtype=str)).astype(str)
        x["test_month"] = x.get("test_month", pd.Series(dtype=str)).astype(str)
        alert_keys_expected |= {f"{a}|{b}|{c}" for a, b, c in zip(x["symbol"], x["metric_id"], x["test_month"], strict=False)}
    disp_keys: set[str] = set()
    expired_exception_count = 0
    if not disp.empty and {"symbol", "metric_id", "test_month"}.issubset(set(disp.columns)):
        disp["symbol"] = disp["symbol"].astype(str).str.upper()
        disp["metric_id"] = disp["metric_id"].astype(str)
        disp["test_month"] = disp["test_month"].astype(str)
        disp_keys = {f"{a}|{b}|{c}" for a, b, c in zip(disp["symbol"], disp["metric_id"], disp["test_month"], strict=False)}
        if {"status", "is_expired"}.issubset(set(disp.columns)):
            is_expired = disp["is_expired"].astype(str).str.lower().isin(["1", "true", "t", "yes", "y"])
            is_exception = disp["status"].astype(str).str.lower().eq("accepted_exception")
            expired_exception_count = int((is_expired & is_exception).sum())
    missing_dispositions = int(len(alert_keys_expected - disp_keys))
    _add_check(
        checks_rows,
        check_id="C34",
        check_name="alert_disposition_coverage_and_unexpired_exceptions",
        passed=disposition_csv.exists()
        and disposition_report_md.exists()
        and exceptions_yaml.exists()
        and len(missing_disp_cols) == 0
        and missing_dispositions == 0
        and expired_exception_count == 0,
        severity_if_fail="high",
        metric_name="alert_disposition_violations",
        metric_value=int(len(missing_disp_cols) + missing_dispositions + expired_exception_count),
        threshold=0,
        comparator="==",
        source_path=disposition_csv,
        details=json.dumps(
            {
                "disposition_exists": disposition_csv.exists(),
                "report_exists": disposition_report_md.exists(),
                "exceptions_yaml_exists": exceptions_yaml.exists(),
                "missing_columns": missing_disp_cols,
                "expected_non_green_alerts": int(len(alert_keys_expected)),
                "missing_dispositions": missing_dispositions,
                "expired_exception_count": expired_exception_count,
            },
            sort_keys=True,
        ),
    )

    # C35: Expired accepted exceptions must not remain active when hard-fail policy is enabled.
    policy_cfg = {}
    if yaml is not None and exceptions_yaml.exists():
        try:
            loaded = yaml.safe_load(exceptions_yaml.read_text(encoding="utf-8"))
            policy_cfg = loaded if isinstance(loaded, dict) else {}
        except Exception:
            policy_cfg = {}
    hard_fail_expired = str(policy_cfg.get("hard_fail_on_expired_exception", True)).strip().lower() in {"1", "true", "yes", "y", "t"}
    expired_accepted = 0
    if not disp.empty and {"status", "is_expired"}.issubset(set(disp.columns)):
        is_exp = disp["is_expired"].astype(str).str.lower().isin(["1", "true", "t", "yes", "y"])
        is_acc = disp["status"].astype(str).str.lower().eq("accepted_exception")
        expired_accepted = int((is_exp & is_acc).sum())
    _add_check(
        checks_rows,
        check_id="C35",
        check_name="no_expired_accepted_exceptions_under_hard_fail_policy",
        passed=(not hard_fail_expired) or (expired_accepted == 0),
        severity_if_fail="high",
        metric_name="expired_accepted_exception_count",
        metric_value=int(expired_accepted),
        threshold=0,
        comparator="==",
        source_path=disposition_csv,
        details=json.dumps(
            {
                "hard_fail_on_expired_exception": hard_fail_expired,
                "expired_accepted_exception_count": expired_accepted,
            },
            sort_keys=True,
        ),
    )

    # C36: Recurrence breaches must not remain active when hard-fail recurrence policy is enabled.
    hard_fail_recurrence = str(policy_cfg.get("hard_fail_on_recurrence_breach", True)).strip().lower() in {"1", "true", "yes", "y", "t"}
    max_amber_consecutive = int(policy_cfg.get("max_amber_consecutive_runs", 3))
    max_amber_months = int(policy_cfg.get("max_amber_months", 6))
    recurrence_breach_count = 0
    valid_syms = set()
    if stage_status_csv.exists():
        try:
            st = pd.read_csv(stage_status_csv)
            if not st.empty and "gate_tick_exact" in st.columns:
                valid_syms = set(st.loc[st["gate_tick_exact"] == True, "symbol"].astype(str).str.upper().tolist())
        except Exception:
            pass

    disp_filtered = disp.copy()
    if not disp_filtered.empty and valid_syms and "symbol" in disp_filtered.columns:
        disp_filtered = disp_filtered[disp_filtered["symbol"].astype(str).str.upper().isin(valid_syms)]

    if not disp_filtered.empty:
        if "recurrence_breach" in disp_filtered.columns:
            recurrence_breach_count = int(disp_filtered["recurrence_breach"].astype(str).str.lower().isin(["1", "true", "t", "yes", "y"]).sum())
        elif {"consecutive_runs_non_green", "months_non_green_count"}.issubset(set(disp_filtered.columns)):
            consec = pd.to_numeric(disp_filtered["consecutive_runs_non_green"], errors="coerce").fillna(0)
            months = pd.to_numeric(disp_filtered["months_non_green_count"], errors="coerce").fillna(0)
            recurrence_breach_count = int(((consec > max_amber_consecutive) | (months > max_amber_months)).sum())
    _add_check(
        checks_rows,
        check_id="C36",
        check_name="no_recurrence_breach_under_hard_fail_policy",
        passed=(not hard_fail_recurrence) or (recurrence_breach_count == 0),
        severity_if_fail="high",
        metric_name="recurrence_breach_count",
        metric_value=int(recurrence_breach_count),
        threshold=0,
        comparator="==",
        source_path=disposition_csv,
        details=json.dumps(
            {
                "hard_fail_on_recurrence_breach": hard_fail_recurrence,
                "max_amber_consecutive_runs": max_amber_consecutive,
                "max_amber_months": max_amber_months,
                "recurrence_breach_count": recurrence_breach_count,
            },
            sort_keys=True,
        ),
    )

    # C37: Non-green disposition rows must include required governance metadata.
    metadata_missing = 0
    if not disp.empty:
        ng = disp[disp.get("band", pd.Series(dtype=str)).astype(str).str.lower().isin(["amber", "red"])].copy()
        if not ng.empty:
            req_cols = ["owner", "rationale", "action_code", "expires_utc"]
            for c in req_cols:
                if c not in ng.columns:
                    metadata_missing += int(len(ng))
                    continue
                missing_c = ng[c].astype(str).str.strip().eq("") | ng[c].isna()
                metadata_missing += int(missing_c.sum())
    _add_check(
        checks_rows,
        check_id="C37",
        check_name="non_green_dispositions_have_required_metadata",
        passed=metadata_missing == 0,
        severity_if_fail="high",
        metric_name="missing_required_disposition_metadata",
        metric_value=int(metadata_missing),
        threshold=0,
        comparator="==",
        source_path=disposition_csv,
    )

    # C38: Block escalation rows require evidence links.
    missing_block_evidence = 0
    if not disp.empty and {"escalation_level", "evidence_link"}.issubset(set(disp.columns)):
        block_rows = disp[disp["escalation_level"].astype(str).str.lower() == "block"].copy()
        if not block_rows.empty:
            missing_block_evidence = int((block_rows["evidence_link"].astype(str).str.strip() == "").sum())
    _add_check(
        checks_rows,
        check_id="C38",
        check_name="block_escalations_have_evidence_link",
        passed=missing_block_evidence == 0,
        severity_if_fail="high",
        metric_name="missing_block_evidence_links",
        metric_value=int(missing_block_evidence),
        threshold=0,
        comparator="==",
        source_path=disposition_csv,
    )

    # C39: Explainability artifacts exist and cover all active non-green metric_ids.
    explain_csv = edge_metrics_csv.parent / "oco_governance_explainability.csv"
    explain_report = docs_root.parent / "analysis" / "oco_governance_explainability_report.md"
    try:
        explain_df = pd.read_csv(explain_csv) if explain_csv.exists() else pd.DataFrame()
    except Exception:
        explain_df = pd.DataFrame()
    missing_explain_cols = [c for c in GOVERNANCE_EXPLAINABILITY_REQUIRED_COLUMNS if c not in explain_df.columns]
    active_metrics = set(
        disp[disp.get("band", pd.Series(dtype=str)).astype(str).str.lower().isin(["amber", "red"])]["metric_id"].astype(str).unique().tolist()
    ) if (not disp.empty and "metric_id" in disp.columns) else set()
    explain_metrics = set(explain_df.get("metric_id", pd.Series(dtype=str)).astype(str).unique().tolist()) if not explain_df.empty else set()
    missing_coverage = sorted(list(active_metrics - explain_metrics))
    _add_check(
        checks_rows,
        check_id="C39",
        check_name="governance_explainability_artifacts_and_coverage",
        passed=explain_csv.exists()
        and explain_report.exists()
        and len(missing_explain_cols) == 0
        and len(missing_coverage) == 0,
        severity_if_fail="high",
        metric_name="governance_explainability_coverage_gaps",
        metric_value=int(len(missing_explain_cols) + len(missing_coverage)),
        threshold=0,
        comparator="==",
        source_path=explain_csv,
        details=json.dumps(
            {
                "explain_csv_exists": explain_csv.exists(),
                "explain_report_exists": explain_report.exists(),
                "missing_columns": missing_explain_cols,
                "active_metric_ids": sorted(list(active_metrics)),
                "missing_metric_coverage": missing_coverage,
            },
            sort_keys=True,
        ),
    )

    # C40: Core governed docs/artifacts must avoid machine-local absolute path prefixes.
    portability_targets = [
        edge_metrics_csv,
        operator_status_csv,
        disposition_csv,
        docs_root.parent / "analysis" / "oco_edge_clarity_report.md",
        docs_root.parent / "analysis" / "operator_action_report.md",
        docs_root.parent / "analysis" / "oco_alert_remediation_report.md",
        docs_root / "stage_04_execution_realism.md",
        docs_root / "stage_10_known_risks_and_backlog.md",
        docs_root / "stage_11_execution_monte_carlo.md",
    ]
    portability_hits: dict[str, int] = {}
    for p in portability_targets:
        if not p.exists():
            continue
        txt = p.read_text(encoding="utf-8", errors="ignore")
        n = _count_machine_local_path_tokens(txt)
        if n > 0:
            portability_hits[str(p)] = n
    _add_check(
        checks_rows,
        check_id="C40",
        check_name="core_docs_artifacts_use_portable_paths",
        passed=len(portability_hits) == 0,
        severity_if_fail="high",
        metric_name="machine_local_path_tokens",
        metric_value=int(sum(portability_hits.values())),
        threshold=0,
        comparator="==",
        source_path=edge_metrics_csv,
        details=json.dumps(portability_hits, sort_keys=True),
    )

    # C41: System reference docs exist, generated markers are present, and build status is complete.
    sysref_status_csv = edge_metrics_csv.parent / "system_reference_build_status.csv"
    try:
        sysref_status = pd.read_csv(sysref_status_csv) if sysref_status_csv.exists() else pd.DataFrame()
    except Exception:
        sysref_status = pd.DataFrame()
    sysref_missing_pages: list[str] = []
    sysref_missing_markers: list[str] = []
    for key, rel_path in SYSREF_PAGE_SPECS:
        p = docs_root.parent / rel_path
        if not p.exists():
            sysref_missing_pages.append(rel_path)
            continue
        if not _extract_sysref_block(p, key):
            sysref_missing_markers.append(rel_path)
    status_cols = {"page_key", "doc_path", "generated_at_utc"}
    missing_status_cols = [c for c in status_cols if c not in sysref_status.columns]
    status_keys = (
        set(sysref_status["page_key"].astype(str).tolist()) if (not sysref_status.empty and "page_key" in sysref_status.columns) else set()
    )
    expected_keys = {k for k, _ in SYSREF_PAGE_SPECS}
    _add_check(
        checks_rows,
        check_id="C41",
        check_name="system_reference_pages_generated_and_indexed",
        passed=len(sysref_missing_pages) == 0
        and len(sysref_missing_markers) == 0
        and sysref_status_csv.exists()
        and len(missing_status_cols) == 0
        and expected_keys.issubset(status_keys),
        severity_if_fail="high",
        metric_name="system_reference_generation_gaps",
        metric_value=int(
            len(sysref_missing_pages)
            + len(sysref_missing_markers)
            + len(missing_status_cols)
            + len(expected_keys - status_keys)
        ),
        threshold=0,
        comparator="==",
        source_path=sysref_status_csv,
        details=json.dumps(
            {
                "missing_pages": sysref_missing_pages,
                "missing_markers": sysref_missing_markers,
                "missing_status_columns": missing_status_cols,
                "missing_status_page_keys": sorted(list(expected_keys - status_keys)),
            },
            sort_keys=True,
        ),
    )

    # C42: Each system-reference page exposes rolling snapshot table with symbol rows or explicit unavailable fallback.
    sysref_snapshot_gaps: list[str] = []
    for key, rel_path in SYSREF_PAGE_SPECS:
        p = docs_root.parent / rel_path
        block = _extract_sysref_block(p, key)
        if not block:
            sysref_snapshot_gaps.append(rel_path + ":missing_block")
            continue
        has_header = "#### Rolling Snapshot By Symbol" in block
        has_symbol_row = any(re.search(rf"\|\s*{sym}\s*\|", block) is not None for sym in sorted(SYSREF_REQUIRED_SYMBOLS))
        has_unavailable = "| unavailable |" in block.lower()
        if not has_header or not (has_symbol_row or has_unavailable):
            sysref_snapshot_gaps.append(rel_path)
    _add_check(
        checks_rows,
        check_id="C42",
        check_name="system_reference_rolling_snapshot_nonempty",
        passed=len(sysref_snapshot_gaps) == 0,
        severity_if_fail="high",
        metric_name="system_reference_snapshot_gaps",
        metric_value=int(len(sysref_snapshot_gaps)),
        threshold=0,
        comparator="==",
        source_path=docs_root.parent,
        details=",".join(sysref_snapshot_gaps),
    )

    # C43: Artifact source references are present and use repository-relative paths.
    sysref_artifact_issues: list[str] = []
    repo_root = docs_root.parent.parent
    for key, rel_path in SYSREF_PAGE_SPECS:
        p = docs_root.parent / rel_path
        block = _extract_sysref_block(p, key)
        if not block:
            sysref_artifact_issues.append(rel_path + ":missing_block")
            continue
        if "- artifact_sources:" not in block:
            sysref_artifact_issues.append(rel_path + ":missing_artifact_sources_heading")
            continue
        artifacts = re.findall(r"^\s*-\s*`([^`]+)`\s*$", block, flags=re.MULTILINE)
        if not artifacts:
            sysref_artifact_issues.append(rel_path + ":no_artifact_rows")
            continue
        non_unavailable = [a for a in artifacts if str(a).strip().lower() != "unavailable"]
        if not non_unavailable:
            sysref_artifact_issues.append(rel_path + ":all_artifacts_unavailable")
            continue
        for art in non_unavailable:
            if not _is_repo_relative_path(art):
                sysref_artifact_issues.append(f"{rel_path}:absolute:{art}")
                continue
            if not (repo_root / art).exists():
                sysref_artifact_issues.append(f"{rel_path}:missing:{art}")
    _add_check(
        checks_rows,
        check_id="C43",
        check_name="system_reference_artifact_sources_present_and_relative",
        passed=len(sysref_artifact_issues) == 0,
        severity_if_fail="medium",
        metric_name="system_reference_artifact_source_issues",
        metric_value=int(len(sysref_artifact_issues)),
        threshold=0,
        comparator="==",
        source_path=docs_root.parent,
        details=",".join(sysref_artifact_issues),
    )

    # C44: System-reference generated timestamps must be recent.
    sysref_ts_missing: list[str] = []
    sysref_max_age_h = float("inf")
    for key, rel_path in SYSREF_PAGE_SPECS:
        p = docs_root.parent / rel_path
        block = _extract_sysref_block(p, key)
        if not block:
            sysref_ts_missing.append(rel_path + ":missing_block")
            continue
        m = re.search(r"-\s*generated_at_utc:\s*`([^`]+)`", block)
        if not m:
            sysref_ts_missing.append(rel_path + ":missing_generated_at_utc")
            continue
        ts = pd.to_datetime(m.group(1), utc=True, errors="coerce")
        if pd.isna(ts):
            sysref_ts_missing.append(rel_path + ":invalid_generated_at_utc")
            continue
        now = datetime.now(timezone.utc)
        age_h = float((now - ts.to_pydatetime()).total_seconds() / 3600.0)
        sysref_max_age_h = age_h if sysref_max_age_h == float("inf") else max(sysref_max_age_h, age_h)
    _add_check(
        checks_rows,
        check_id="C44",
        check_name="system_reference_generated_timestamp_freshness",
        passed=len(sysref_ts_missing) == 0 and sysref_max_age_h <= float(thresholds.max_age_hours),
        severity_if_fail="medium",
        metric_name="system_reference_max_age_hours",
        metric_value=sysref_max_age_h,
        threshold=float(thresholds.max_age_hours),
        comparator="<=",
        source_path=docs_root.parent,
        details=",".join(sysref_ts_missing),
    )

    # C45: Key system docs must explicitly reference stop-limit behavior.
    stop_limit_missing: list[str] = []
    for rel_path in sorted(SYSREF_STOP_LIMIT_REQUIRED_PATHS):
        p = docs_root.parent / rel_path
        txt = p.read_text(encoding="utf-8", errors="ignore") if p.exists() else ""
        if "stop-limit" not in txt.lower():
            stop_limit_missing.append(rel_path)
    _add_check(
        checks_rows,
        check_id="C45",
        check_name="system_reference_stop_limit_relevance_present",
        passed=len(stop_limit_missing) == 0,
        severity_if_fail="high",
        metric_name="system_reference_stop_limit_missing",
        metric_value=int(len(stop_limit_missing)),
        threshold=0,
        comparator="==",
        source_path=docs_root.parent,
        details=",".join(stop_limit_missing),
    )

    # C46: Symbol coverage line must include EURUSD, GBPUSD, and USDJPY.
    symbol_coverage_gaps: list[str] = []
    for key, rel_path in SYSREF_PAGE_SPECS:
        p = docs_root.parent / rel_path
        block = _extract_sysref_block(p, key)
        if not block:
            symbol_coverage_gaps.append(rel_path + ":missing_block")
            continue
        m = re.search(r"-\s*symbols_covered:\s*`([^`]+)`", block)
        if not m:
            symbol_coverage_gaps.append(rel_path + ":missing_symbols_covered")
            continue
        have = set(_parse_symbols(m.group(1)))
        if not SYSREF_REQUIRED_SYMBOLS.issubset(have):
            symbol_coverage_gaps.append(rel_path + ":missing_expected_symbols")
    _add_check(
        checks_rows,
        check_id="C46",
        check_name="system_reference_symbol_coverage_required_triplet",
        passed=len(symbol_coverage_gaps) == 0,
        severity_if_fail="medium",
        metric_name="system_reference_symbol_coverage_gaps",
        metric_value=int(len(symbol_coverage_gaps)),
        threshold=0,
        comparator="==",
        source_path=docs_root.parent,
        details=",".join(symbol_coverage_gaps),
    )

    # C47: Stage 03 must include explicit CatBoost lifecycle/spec semantics.
    stage03_path = docs_root / "stage_03_monthly_wfo.md"
    stage03_txt = stage03_path.read_text(encoding="utf-8", errors="ignore").lower() if stage03_path.exists() else ""
    stage03_missing_terms = [t for t in STAGE03_CATBOOST_REQUIRED_TERMS if t.lower() not in stage03_txt]
    _add_check(
        checks_rows,
        check_id="C47",
        check_name="stage03_catboost_spec_completeness",
        passed=len(stage03_missing_terms) == 0,
        severity_if_fail="high",
        metric_name="stage03_catboost_missing_terms",
        metric_value=int(len(stage03_missing_terms)),
        threshold=0,
        comparator="==",
        source_path=stage03_path,
        details=",".join(stage03_missing_terms),
    )

    # C48: Core docs must state one-month validity and monthly retrain policy.
    lifecycle_missing: list[str] = []
    lifecycle_terms = ["one-month validity", "monthly retrain"]
    for rel in MODEL_LIFECYCLE_REQUIRED_DOCS:
        p = docs_root.parent / rel
        txt = p.read_text(encoding="utf-8", errors="ignore").lower() if p.exists() else ""
        missing = [t for t in lifecycle_terms if t not in txt]
        if missing:
            lifecycle_missing.append(f"{rel}:{'|'.join(missing)}")
    _add_check(
        checks_rows,
        check_id="C48",
        check_name="model_lifecycle_policy_docs_present",
        passed=len(lifecycle_missing) == 0,
        severity_if_fail="high",
        metric_name="model_lifecycle_policy_missing_docs",
        metric_value=int(len(lifecycle_missing)),
        threshold=0,
        comparator="==",
        source_path=docs_root.parent,
        details=",".join(lifecycle_missing),
    )

    # C49: Stage 05 must explicitly document dependency on Stage 3 outputs.
    stage05_path = docs_root / "stage_05_reduced_core.md"
    stage05_txt = stage05_path.read_text(encoding="utf-8", errors="ignore").lower() if stage05_path.exists() else ""
    stage05_missing_terms = [t for t in STAGE05_STAGE3_LINK_REQUIRED_TERMS if t.lower() not in stage05_txt]
    _add_check(
        checks_rows,
        check_id="C49",
        check_name="stage05_stage3_dependency_documented",
        passed=len(stage05_missing_terms) == 0,
        severity_if_fail="high",
        metric_name="stage05_stage3_dependency_missing_terms",
        metric_value=int(len(stage05_missing_terms)),
        threshold=0,
        comparator="==",
        source_path=stage05_path,
        details=",".join(stage05_missing_terms),
    )

    # C50: Stage 03 must document strict causal fallback provenance for thresholding.
    stage03_fallback_missing_terms = [
        t for t in STAGE03_THRESHOLD_FALLBACK_REQUIRED_TERMS if t.lower() not in stage03_txt
    ]
    _add_check(
        checks_rows,
        check_id="C50",
        check_name="stage03_threshold_fallback_provenance_documented",
        passed=len(stage03_fallback_missing_terms) == 0,
        severity_if_fail="high",
        metric_name="stage03_threshold_fallback_missing_terms",
        metric_value=int(len(stage03_fallback_missing_terms)),
        threshold=0,
        comparator="==",
        source_path=stage03_path,
        details=",".join(stage03_fallback_missing_terms),
    )

    # C51: Tick builder scripts must exist and Stage 01 must document them.
    missing_tick_builder_scripts: list[str] = []
    repo_root = docs_root.parent.parent
    for rel in TICK_BUILDER_REQUIRED_SCRIPTS:
        p = repo_root / rel
        if not p.exists():
            missing_tick_builder_scripts.append(rel)
    stage01_path = docs_root / "stage_01_data_foundation.md"
    stage01_txt = stage01_path.read_text(encoding="utf-8", errors="ignore").lower() if stage01_path.exists() else ""
    stage01_missing_terms = [t for t in STAGE01_TICK_BUILDER_REQUIRED_TERMS if t.lower() not in stage01_txt]
    c51_pass = (len(missing_tick_builder_scripts) == 0) and (len(stage01_missing_terms) == 0)
    _add_check(
        checks_rows,
        check_id="C51",
        check_name="tick_builder_scripts_present_and_stage01_documented",
        passed=c51_pass,
        severity_if_fail="high",
        metric_name="tick_builder_contract_gaps",
        metric_value=int(len(missing_tick_builder_scripts) + len(stage01_missing_terms)),
        threshold=0,
        comparator="==",
        source_path=stage01_path,
        details="scripts_missing="
        + "|".join(missing_tick_builder_scripts)
        + ";stage01_terms_missing="
        + "|".join(stage01_missing_terms),
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
