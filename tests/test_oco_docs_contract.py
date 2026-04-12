from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import pytest

from scripts.audit_data_reliability import Thresholds as ReliabilityThresholds
from scripts.audit_data_reliability import run as run_data_reliability_audit
from scripts.build_oco_system_reference_docs import run as build_system_reference_docs
from scripts.validate_oco_docs_contract import (
    CORE_METRIC_IDS,
    STAGE04_POLICY_REQUIRED_METRICS,
    Thresholds,
    run,
)


def _stage_doc_text() -> str:
    return """# Stage X\n\n## Objective\n\n## Inputs\n\n## Process\n\n## Exact Calculations\n\n## Causality / Leakage Controls\n\n## Failure Modes\n\n## Interpretation Guide\n\n## Validation Gates\n\n## Operator Decision Tree\n\n## How To Run\n\n## How To Interpret Outputs\n\n## What To Do If It Fails\n\n## Reproduction Commands\n\n## Traceability\n"""


def _stage04_policy_sections_text() -> str:
    return """
### Execution Contract Semantics (Stop-Limit)

### Stage 04 Policy Bands and Actions

### Cap Recalibration Decision Tree

### Degradation Playbooks
"""


def _write_stage_docs(root: Path) -> None:
    names = {
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
        12: "stage_12_api_parity.md",
        13: "stage_13_dukascopy_testclient_parity.md",
        14: "stage_14_jforex_runtime_certification.md",
    }
    for i, n in names.items():
        txt = _stage_doc_text()
        if i == 1:
            txt = (
                txt
                + "\n\n## Tick Build Contract\n"
                + "raw ticks are transformed via build_global_tick_bars.py and build_tick_velocity_dataset.py into tick_velocity datasets.\n"
                + "canonical bars use open_bid high_bid low_bid close_bid high_ask close_ask spread.\n"
            )
        if i == 3:
            txt = (
                txt
                + "\n\n## CatBoost Model Specification (Critical)\n"
                + "catboost one-month validity monthly retrain selected_exec threshold_exec auc brier w13 w14 w15 operating bands.\n"
                + "train-only fallback threshold_source no_history and never uses unseen same-month test pools.\n"
            )
        if i == 4:
            txt = txt + _stage04_policy_sections_text()
        if i == 5:
            txt = (
                txt
                + "\n\n## Dependency on Stage 3 (CatBoost Outputs)\nstage 3 selected_exec selection_mode\n"
            )
        if i == 7:
            txt = txt + "\n\n## Operator MRM Checks\n\n## Escalation Matrix\n"
        if i == 9:
            txt = txt + "\n\n## Operator Escalation Matrix\n"
        (root / n).write_text(txt, encoding="utf-8")


def _write_stage04_policy_artifacts(*, generated_root: Path, edge_metrics_csv: Path) -> None:
    (generated_root / "stage_04_snapshot.md").write_text(
        "#### Policy Status\n| symbol | status |\n|---|---|\n| EURUSD | green |\n", encoding="utf-8"
    )
    policy_rows = [
        {
            "symbol": "EURUSD",
            "metric_id": metric_id,
            "metric_value": 1.0,
            "band": "green",
            "action_code": "A0_MONITOR",
            "action_summary": "ok",
        }
        for metric_id in sorted(STAGE04_POLICY_REQUIRED_METRICS)
    ]
    (edge_metrics_csv.parent / "stage04_execution_policy_status.csv").write_text(
        pd.DataFrame(policy_rows).to_csv(index=False),
        encoding="utf-8",
    )


def _write_stage11_mc_artifacts(*, generated_root: Path, edge_metrics_csv: Path) -> None:
    symbol_rows = [
        {
            "symbol": "EURUSD",
            "scenario_id": sid,
            "mean_per_signal_pips": 0.8,
            "lb95_per_signal_pips": 0.5,
            "mean_fill_rate": 0.98,
            "prob_negative_month": 0.1,
            "fill_rate_drop_vs_S0": 0.01 if sid != "S0_baseline" else 0.0,
        }
        for sid in ["S0_baseline", "S1_mild", "S2_moderate", "S3_severe"]
    ]
    month_rows = [
        {
            "symbol": "EURUSD",
            "scenario_id": "S1_mild",
            "test_month": "2025-01",
            "session_bucket": "LONDON",
            "signals": 100,
            "mean_per_signal_pips": 0.8,
            "lb95_per_signal_pips": 0.5,
            "mean_fill_rate": 0.98,
        }
    ]
    check_rows = [
        {"symbol": "EURUSD", "check_id": c, "status": "pass", "metric_value": 0.0}
        for c in ["EM01", "EM02", "EM03", "EM04", "EM05"]
    ]
    base = edge_metrics_csv.parent
    pd.DataFrame(symbol_rows).to_csv(base / "execution_mc_symbol_scenarios.csv", index=False)
    pd.DataFrame(month_rows).to_csv(base / "execution_mc_month_session_summary.csv", index=False)
    pd.DataFrame(check_rows).to_csv(base / "execution_mc_checks.csv", index=False)
    (generated_root / "stage_11_snapshot.md").write_text(
        "#### Key Results\n| symbol | ok |\n|---|---|\n| EURUSD | 1 |\n\n#### Monte Carlo Governance Checks\n| check | status |\n|---|---|\n| EM01 | pass |\n",
        encoding="utf-8",
    )


def _write_stage12_api_parity_artifacts(*, docs_root: Path, edge_metrics_csv: Path) -> None:
    base = docs_root.parent.parent / "data" / "analysis" / "backtest_reconcile"
    base.mkdir(parents=True, exist_ok=True)
    summary = pd.DataFrame(
        [
            {
                "symbol": "EURUSD",
                "signal_parity_pass": True,
                "execution_parity_pass": True,
                "stage12_api_parity_pass": True,
                "selected_missing_expected": 0,
                "selected_extra_runtime": 0,
                "execution_failed_checks_high_critical": 0,
                "stage12_api_parity_verdict": "green",
            }
        ]
    )
    summary.to_csv(base / "EURUSD_stage12_api_parity_summary.csv", index=False)
    pd.DataFrame(
        [{"symbol": "EURUSD", "check_family": "signal", "check_id": "AP03", "status": "pass"}]
    ).to_csv(base / "EURUSD_stage12_api_parity_checks.csv", index=False)
    pd.DataFrame(columns=["symbol", "type"]).to_csv(
        base / "EURUSD_stage12_api_parity_mismatches.csv", index=False
    )
    report = docs_root.parent / "analysis" / "EURUSD_stage12_api_parity_report.md"
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text("# Stage 12 API Parity\n", encoding="utf-8")


def _mkdocs_text() -> str:
    paths = [
        "analysis/index.md",
        "analysis/oco_stage_integrity_report.md",
        "analysis/oco_rule_universe_registry_report.md",
        "analysis/oco_execution_drift_report.md",
        "analysis/oco_alert_remediation_report.md",
        "analysis/oco_governance_explainability_report.md",
        "analysis/oco_threshold_sensitivity_report.md",
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
        "strategy_bible/stage_12_api_parity.md",
        "strategy_bible/signal_lifecycle_reference.md",
        "strategy_bible/operator_runbook.md",
        "strategy_bible/metric_dictionary.md",
        "strategy_bible/assumptions_and_threats.md",
        "strategy_bible/governance_mapping.md",
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
    return "\n".join(["nav:"] + [f"  - {p}" for p in paths])


def _write_analysis_catalog_artifacts(docs_root: Path) -> None:
    analysis = docs_root.parent / "analysis"
    analysis.mkdir(parents=True, exist_ok=True)
    files = [
        "data_reliability_report.md",
        "oco_stage_integrity_report.md",
        "oco_rule_universe_registry_report.md",
        "operator_action_report.md",
        "oco_leakage_integrity_report.md",
        "oco_execution_risk_prelive_report.md",
        "oco_execution_drift_report.md",
        "oco_alert_remediation_report.md",
        "oco_governance_explainability_report.md",
        "oco_threshold_sensitivity_report.md",
        "oco_execution_monte_carlo_report.md",
        "oco_execution_monte_carlo_validation_report.md",
        "oco_logical_audit_report.md",
        "oco_edge_clarity_report.md",
        "oco_docs_contract_report.md",
        "run_delta_dashboard.md",
        "taxonomy_rules.md",
    ]
    for name in files:
        (analysis / name).write_text(f"# {name}\n", encoding="utf-8")
    (docs_root / "signal_lifecycle_reference.md").write_text(
        "# Signal Lifecycle\n", encoding="utf-8"
    )
    (docs_root / "operator_runbook.md").write_text(
        "# Operator Runbook\none-month validity monthly retrain\n", encoding="utf-8"
    )
    (docs_root.parent / "index.md").write_text(
        "# Index\none-month validity monthly retrain\n", encoding="utf-8"
    )
    (docs_root.parent / "STRATEGY_MASTER_MANUAL.md").write_text(
        "# Manual\none-month validity monthly retrain\n",
        encoding="utf-8",
    )
    scripts_dir = docs_root.parent.parent / "scripts"
    scripts_dir.mkdir(parents=True, exist_ok=True)
    (scripts_dir / "build_global_tick_bars.py").write_text("# fixture script\n", encoding="utf-8")
    (scripts_dir / "build_tick_velocity_dataset.py").write_text(
        "# fixture script\n", encoding="utf-8"
    )
    (analysis / "index.md").write_text("# Analysis Catalog\n", encoding="utf-8")
    (analysis / "catalog_gaps_report.md").write_text("# gaps\n", encoding="utf-8")
    manifest_rows = [
        {"doc_path": f"analysis/{name}", "title": name, "group": "core"} for name in files
    ]
    manifest_rows.append(
        {
            "doc_path": "analysis/EURUSD_stage12_api_parity_report.md",
            "title": "EURUSD Stage 12 API Parity",
            "group": "core",
        }
    )
    pd.DataFrame(manifest_rows).to_csv(analysis / "catalog_manifest.csv", index=False)
    canonical_rows = [
        {
            "doc_path": "analysis/eurusd_tick_opportunity_mining_report.md",
            "symbol": "EURUSD",
            "stage_id": 2,
            "stage_family": "stage02_mining",
            "class": "stage_integrated",
            "is_canonical": True,
        },
        {
            "doc_path": "analysis/gbpusd_tick_opportunity_mining_report.md",
            "symbol": "GBPUSD",
            "stage_id": 2,
            "stage_family": "stage02_mining",
            "class": "stage_integrated",
            "is_canonical": True,
        },
        {
            "doc_path": "analysis/usdjpy_tick_opportunity_mining_report.md",
            "symbol": "USDJPY",
            "stage_id": 2,
            "stage_family": "stage02_mining",
            "class": "stage_integrated",
            "is_canonical": True,
        },
        {
            "doc_path": "analysis/run_delta_dashboard.md",
            "symbol": "ALL",
            "stage_id": 9,
            "stage_family": "none",
            "class": "stage_integrated",
            "is_canonical": True,
        },
    ]
    pd.DataFrame(canonical_rows).to_csv(analysis / "canonical_stage_map.csv", index=False)


def _write_run_delta_artifacts(*, docs_root: Path, edge_metrics_csv: Path) -> None:
    base = edge_metrics_csv.parent
    snap = base / "run_snapshots" / "run_baseline"
    snap.mkdir(parents=True, exist_ok=True)
    edge = pd.read_csv(edge_metrics_csv)
    edge.to_csv(snap / "edge_clarity_stage_metrics.csv", index=False)
    pd.DataFrame(
        [
            {
                "symbol": "EURUSD",
                "symbol_all_gates_pass": 1,
                "gate_api_signal_parity": 1,
                "gate_api_execution_parity": 1,
                "gate_api_parity": 1,
            }
        ]
    ).to_csv(snap / "oco_bible_stage_status.csv", index=False)
    reg = pd.DataFrame(
        [
            {
                "run_id": "run_baseline",
                "run_label": "baseline",
                "generated_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "registered_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "edge_metrics_rows": int(len(edge)),
                "stage_metrics_rows": int(len(edge)),
                "stage_status_rows": 1,
                "docs_checks_failed": 0,
                "docs_checks_high_critical_failed": 0,
                "symbols_total": 1,
                "symbols_pass_count": 1,
                "edge_metrics_snapshot": str(snap / "edge_clarity_stage_metrics.csv"),
                "stage_metrics_snapshot": str(snap / "oco_bible_stage_metrics.csv"),
                "stage_status_snapshot": str(snap / "oco_bible_stage_status.csv"),
                "docs_checks_snapshot": str(snap / "docs_contract_checks.csv"),
                "snapshot_dir": str(snap),
                "is_baseline": 1,
            }
        ]
    )
    reg.to_csv(base / "run_registry.csv", index=False)
    pd.DataFrame(
        [
            {
                "baseline_run_id": "run_baseline",
                "latest_run_id": "run_baseline",
                "metric_rows_baseline": len(edge),
                "metric_rows_latest": len(edge),
                "metric_rows_changed": 0,
                "gate_rows_changed": 0,
            }
        ]
    ).to_csv(base / "run_delta_summary.csv", index=False)
    pd.DataFrame(
        [
            {
                "stage_id": 1,
                "symbol": "EURUSD",
                "metric_id": "D16_spread_regime_shift_z",
                "metric_value_baseline": 1.0,
                "metric_value_latest": 1.0,
                "delta": 0.0,
                "abs_delta": 0.0,
                "changed": False,
            }
        ]
    ).to_csv(base / "run_delta_metric_changes.csv", index=False)
    pd.DataFrame(
        [
            {
                "symbol": "EURUSD",
                "gate_id": "symbol_all_gates_pass",
                "baseline_value": 1,
                "latest_value": 1,
                "delta": 0,
                "changed": 0,
            }
        ]
    ).to_csv(base / "run_delta_gate_changes.csv", index=False)
    (docs_root.parent / "analysis" / "run_delta_dashboard.md").write_text(
        "# Run Delta\n", encoding="utf-8"
    )


def _write_operator_action_artifacts(*, docs_root: Path, edge_metrics_csv: Path) -> None:
    base = edge_metrics_csv.parent
    pd.DataFrame(
        [
            {
                "symbol": "EURUSD",
                "stage_id": 1,
                "metric_id": "D16_spread_regime_shift_z",
                "metric_value": 0.1,
                "band": "green",
                "severity": "info",
                "action_code": "A0_MONITOR",
                "action_summary": "ok",
                "owner": "research",
                "evaluated_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            }
        ]
    ).to_csv(base / "operator_action_status.csv", index=False)
    (docs_root.parent / "analysis" / "operator_action_report.md").write_text(
        "# Operator Action\n", encoding="utf-8"
    )
    (docs_root / "operator_playbook.md").write_text("# Operator Playbook\n", encoding="utf-8")
    (docs_root.parent / "analysis" / "taxonomy_rules.md").write_text(
        "# Taxonomy\n", encoding="utf-8"
    )


def _write_stage_integrity_artifacts(*, docs_root: Path, edge_metrics_csv: Path) -> None:
    base = edge_metrics_csv.parent
    rows = []
    for stage_id in range(1, 13):
        rows.append(
            {
                "symbol": "ALL",
                "stage_id": stage_id,
                "check_id": f"SI01_{stage_id:02d}",
                "check_name": "ok",
                "status": "pass",
                "severity_if_fail": "high",
                "component": "stage_integrity",
                "metric_name": "exists",
                "metric_value": 1,
                "threshold": 1,
                "comparator": "==",
                "details": "",
                "source_path": str(docs_root),
                "evaluated_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            }
        )
    pd.DataFrame(rows).to_csv(base / "oco_stage_integrity_checks.csv", index=False)
    pd.DataFrame(
        columns=[
            "issue_id",
            "symbol",
            "check_id",
            "severity",
            "component",
            "summary",
            "details_json",
        ]
    ).to_csv(base / "oco_stage_integrity_issues.csv", index=False)
    (docs_root.parent / "analysis" / "oco_stage_integrity_report.md").write_text(
        "# Stage Integrity\n", encoding="utf-8"
    )


def _write_execution_drift_artifacts(*, docs_root: Path, edge_metrics_csv: Path) -> None:
    base = edge_metrics_csv.parent
    monthly_rows = []
    for sym in ["EURUSD", "GBPUSD", "USDJPY", "USDCHF", "AUDUSD", "USDCAD"]:
        monthly_rows.append(
            {
                "symbol": sym,
                "test_month": "2025-12",
                "rows_total": 1000,
                "fill_rate": 0.98,
                "no_touch_rate": 0.01,
                "overshoot_p50_pips": 0.1,
                "overshoot_p95_pips": 0.4,
                "delta_fill_rate_drop": 0.0,
                "delta_no_touch_rate": 0.0,
                "delta_overshoot_p95_pips": 0.0,
            }
        )
    pd.DataFrame(monthly_rows).to_csv(base / "oco_execution_drift_monthly.csv", index=False)
    pd.DataFrame(
        [
            {
                "symbol": "EURUSD",
                "test_month": "2025-12",
                "metric_id": "E_DRIFT_OVERSHOOT_P95",
                "metric_value": 0.0,
                "warn_threshold": 0.1,
                "fail_threshold": 0.2,
                "band": "green",
                "severity": "info",
                "source_path": "x",
                "details_json": "{}",
                "evaluated_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            }
        ]
    ).to_csv(base / "oco_execution_drift_alerts.csv", index=False)
    (docs_root.parent / "analysis" / "oco_execution_drift_report.md").write_text(
        "# Drift\n", encoding="utf-8"
    )


def _write_threshold_sensitivity_artifacts(*, docs_root: Path, edge_metrics_csv: Path) -> None:
    base = edge_metrics_csv.parent
    rows = []
    for sym in ["EURUSD", "GBPUSD", "USDJPY", "USDCHF", "AUDUSD", "USDCAD"]:
        rows.append(
            {
                "symbol": sym,
                "lookback_days": 20,
                "cadence_days": 30,
                "window_days": 3,
                "quantile": 0.9,
                "lb95_month_mean_signal_pips": 0.5,
                "w13_threshold_fragility": 1.0,
                "w14_brier_drift_std": 0.001,
                "w15_selection_turnover": 0.05,
                "final_score": 0.8,
                "is_recommended": 1,
                "is_current_policy": 1,
            }
        )
    pd.DataFrame(rows).to_csv(base / "oco_threshold_sensitivity.csv", index=False)
    pd.DataFrame(
        [
            {
                "symbol": "EURUSD",
                "test_month": "",
                "metric_id": "TS01_W13_THRESHOLD_FRAGILITY",
                "metric_value": 1.0,
                "warn_threshold": 2.5,
                "fail_threshold": 4.0,
                "band": "green",
                "severity": "info",
                "source_path": "x",
                "details_json": "{}",
                "evaluated_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            }
        ]
    ).to_csv(base / "oco_threshold_sensitivity_alerts.csv", index=False)
    (docs_root.parent / "analysis" / "oco_threshold_sensitivity_report.md").write_text(
        "# Threshold Sensitivity\n", encoding="utf-8"
    )


def _write_registry_artifacts(*, docs_root: Path, edge_metrics_csv: Path) -> None:
    base = edge_metrics_csv.parent
    rows = []
    for sym in ["EURUSD", "GBPUSD", "USDJPY", "USDCHF", "AUDUSD", "USDCAD"]:
        rows.append(
            {
                "symbol": sym,
                "check_id": "RU07",
                "status": "pass",
                "severity_if_fail": "critical",
                "metric_name": "runtime_match",
                "metric_value": 1,
            }
        )
    pd.DataFrame(rows).to_csv(base / "oco_rule_universe_registry_checks.csv", index=False)
    pd.DataFrame(
        columns=[
            "issue_id",
            "symbol",
            "check_id",
            "severity",
            "component",
            "summary",
            "details_json",
        ]
    ).to_csv(base / "oco_rule_universe_registry_issues.csv", index=False)
    (docs_root.parent / "analysis" / "oco_rule_universe_registry_report.md").write_text(
        "# Rule Registry\n", encoding="utf-8"
    )


def _write_alert_remediation_artifacts(*, docs_root: Path, edge_metrics_csv: Path) -> None:
    base = edge_metrics_csv.parent
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    rows = [
        {
            "symbol": "EURUSD",
            "source_alert": "execution_drift",
            "test_month": "2025-12",
            "metric_id": "E_DRIFT_OVERSHOOT_P95",
            "metric_value": 0.1,
            "band": "amber",
            "severity": "medium",
            "status": "accepted_exception",
            "action_code": "A2_SESSION_GUARD",
            "owner": "execution_research",
            "rationale": "approved",
            "expires_utc": "2099-01-01T00:00:00Z",
            "is_expired": False,
            "source_path": "x",
            "evaluated_at_utc": now,
            "first_seen_utc": now,
            "last_seen_utc": now,
            "consecutive_runs_non_green": 1,
            "months_non_green_count": 1,
            "sla_days": 30,
            "days_to_expiry": 30.0,
            "escalation_level": "warn",
            "evidence_required": True,
            "evidence_link": "docs/analysis/oco_execution_drift_report.md",
            "expiry_breach": False,
            "recurrence_breach": False,
            "policy_violation_code": "",
        },
        {
            "symbol": "EURUSD",
            "source_alert": "threshold_sensitivity",
            "test_month": "",
            "metric_id": "TS01_W13_THRESHOLD_FRAGILITY",
            "metric_value": 1.0,
            "band": "green",
            "severity": "info",
            "status": "remediated",
            "action_code": "A0_MONITOR",
            "owner": "research",
            "rationale": "ok",
            "expires_utc": "2099-01-01T00:00:00Z",
            "is_expired": False,
            "source_path": "x",
            "evaluated_at_utc": now,
            "first_seen_utc": now,
            "last_seen_utc": now,
            "consecutive_runs_non_green": 1,
            "months_non_green_count": 1,
            "sla_days": 30,
            "days_to_expiry": 30.0,
            "escalation_level": "monitor",
            "evidence_required": False,
            "evidence_link": "docs/analysis/oco_threshold_sensitivity_report.md",
            "expiry_breach": False,
            "recurrence_breach": False,
            "policy_violation_code": "",
        },
    ]
    pd.DataFrame(rows).to_csv(base / "oco_alert_disposition.csv", index=False)
    (docs_root.parent / "analysis" / "oco_alert_remediation_report.md").write_text(
        "# Alert Remediation\n", encoding="utf-8"
    )


def _write_governance_explainability_artifacts(*, docs_root: Path, edge_metrics_csv: Path) -> None:
    base = edge_metrics_csv.parent
    rows = [
        {
            "metric_id": "E_DRIFT_OVERSHOOT_P95",
            "source_alert": "execution_drift",
            "definition": "Tail overshoot drift",
            "risk_path": "Execution tail risk",
            "threshold_context": "warn/fail thresholds",
            "action_rationale": "Session guard selected",
            "expected_recovery_signal": "returns green",
            "band_worst": "amber",
            "severity_worst": "medium",
            "active_rows": 1,
            "symbol_count": 1,
            "symbols": "EURUSD",
            "action_codes": "A2_SESSION_GUARD",
            "owners": "execution_research",
            "review_cadence_days": 30,
            "evidence_required": True,
            "example_evidence_link": "docs/analysis/oco_execution_drift_report.md",
            "coverage_status": "covered",
            "generated_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        },
        {
            "metric_id": "TS01_W13_THRESHOLD_FRAGILITY",
            "source_alert": "threshold_sensitivity",
            "definition": "Threshold fragility",
            "risk_path": "Selection instability risk",
            "threshold_context": "threshold grid",
            "action_rationale": "monitor",
            "expected_recovery_signal": "stabilizes",
            "band_worst": "amber",
            "severity_worst": "medium",
            "active_rows": 1,
            "symbol_count": 1,
            "symbols": "EURUSD",
            "action_codes": "A0_MONITOR",
            "owners": "research",
            "review_cadence_days": 30,
            "evidence_required": False,
            "example_evidence_link": "docs/analysis/oco_threshold_sensitivity_report.md",
            "coverage_status": "covered",
            "generated_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        },
    ]
    pd.DataFrame(rows).to_csv(base / "oco_governance_explainability.csv", index=False)
    (docs_root.parent / "analysis" / "oco_governance_explainability_report.md").write_text(
        "# Governance Explainability\n", encoding="utf-8"
    )


def _write_system_reference_docs(*, docs_root: Path, edge_metrics_csv: Path) -> None:
    artifact_root = edge_metrics_csv.parent
    docs_contract_checks = artifact_root / "docs_contract_checks.csv"
    if not docs_contract_checks.exists():
        pd.DataFrame(
            [
                {
                    "check_id": "C0",
                    "status": "pass",
                    "severity_if_fail": "low",
                    "metric_value": 0.0,
                }
            ]
        ).to_csv(docs_contract_checks, index=False)

    analysis_root = docs_root.parent.parent / "data" / "analysis"
    tick_analysis_root = analysis_root / "tick_opportunity_mining"
    tick_analysis_root.mkdir(parents=True, exist_ok=True)
    required = [
        "oco_execution_drift_monthly.csv",
        "oco_threshold_sensitivity.csv",
        "operator_action_status.csv",
        "oco_alert_disposition.csv",
        "execution_mc_symbol_scenarios.csv",
        "docs_contract_checks.csv",
        "run_delta_summary.csv",
    ]
    for name in required:
        src = artifact_root / name
        dst = tick_analysis_root / name
        if src.exists():
            dst.write_bytes(src.read_bytes())
        elif not dst.exists():
            pd.DataFrame().to_csv(dst, index=False)

    build_system_reference_docs(
        docs_root=docs_root.parent,
        analysis_root=analysis_root,
        out_status_csv=tick_analysis_root / "system_reference_build_status.csv",
    )
    (artifact_root / "system_reference_build_status.csv").write_bytes(
        (tick_analysis_root / "system_reference_build_status.csv").read_bytes()
    )


def _build_smoke_fixture(tmp_path: Path, *, with_system_reference: bool = True) -> dict[str, Path]:
    docs_root = tmp_path / "docs" / "strategy_bible"
    docs_root.mkdir(parents=True, exist_ok=True)
    generated_root = docs_root / "generated"
    generated_root.mkdir(parents=True, exist_ok=True)
    artifact_root = tmp_path / "data" / "analysis" / "tick_opportunity_mining"
    artifact_root.mkdir(parents=True, exist_ok=True)

    _write_stage_docs(docs_root)
    _write_analysis_catalog_artifacts(docs_root)

    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    rows = [
        {
            "stage_id": 1,
            "symbol": sym,
            "metric_id": m,
            "metric_value": 1.0,
            "generated_at_utc": now,
        }
        for sym in ["EURUSD", "GBPUSD", "USDJPY", "USDCHF", "AUDUSD", "USDCAD"]
        for m in sorted(CORE_METRIC_IDS)
    ]
    edge_metrics_csv = artifact_root / "edge_metrics.csv"
    pd.DataFrame(rows).to_csv(edge_metrics_csv, index=False)
    _write_stage04_policy_artifacts(
        generated_root=generated_root, edge_metrics_csv=edge_metrics_csv
    )
    _write_stage11_mc_artifacts(generated_root=generated_root, edge_metrics_csv=edge_metrics_csv)
    _write_stage12_api_parity_artifacts(docs_root=docs_root, edge_metrics_csv=edge_metrics_csv)
    _write_run_delta_artifacts(docs_root=docs_root, edge_metrics_csv=edge_metrics_csv)
    _write_operator_action_artifacts(docs_root=docs_root, edge_metrics_csv=edge_metrics_csv)
    _write_stage_integrity_artifacts(docs_root=docs_root, edge_metrics_csv=edge_metrics_csv)
    _write_execution_drift_artifacts(docs_root=docs_root, edge_metrics_csv=edge_metrics_csv)
    _write_threshold_sensitivity_artifacts(docs_root=docs_root, edge_metrics_csv=edge_metrics_csv)
    _write_registry_artifacts(docs_root=docs_root, edge_metrics_csv=edge_metrics_csv)
    _write_alert_remediation_artifacts(docs_root=docs_root, edge_metrics_csv=edge_metrics_csv)
    _write_governance_explainability_artifacts(
        docs_root=docs_root, edge_metrics_csv=edge_metrics_csv
    )
    if with_system_reference:
        _write_system_reference_docs(docs_root=docs_root, edge_metrics_csv=edge_metrics_csv)

    stage_status_csv = tmp_path / "stage_status.csv"
    sym_rows = [
        {
            "symbol": s,
            "symbol_all_gates_pass": True,
            "gate_tick_exact": True,
            "gate_api_signal_parity": True,
            "gate_api_execution_parity": True,
            "gate_api_parity": True,
        }
        for s in ["EURUSD", "GBPUSD", "USDJPY", "USDCHF", "AUDUSD", "USDCAD"]
    ]
    pd.DataFrame(sym_rows).to_csv(stage_status_csv, index=False)

    mock_s09_md = "".join(
        f"| {s} | pass |\n" for s in ["EURUSD", "GBPUSD", "USDJPY", "USDCHF", "AUDUSD", "USDCAD"]
    )
    (generated_root / "stage_09_snapshot.md").write_text(mock_s09_md, encoding="utf-8")

    edge_report = tmp_path / "edge_report.md"
    mock_edge_md = "".join(
        f"| 1 | {s} | D16_spread_regime_shift_z | 1.0 |\n"
        for s in ["EURUSD", "GBPUSD", "USDJPY", "USDCHF", "AUDUSD", "USDCAD"]
    )
    edge_report.write_text(mock_edge_md, encoding="utf-8")
    metric_dictionary = docs_root / "metric_dictionary.md"
    metric_dictionary.write_text(
        "\n".join(
            [
                "# Dict",
                "| metric_id | stage | formula | unit | interpretation bands | missing policy |",
                "| --- | --- | --- | --- | --- | --- |",
            ]
            + [f"| {m} | 1 | x | u | b | disallow |" for m in sorted(CORE_METRIC_IDS)]
        ),
        encoding="utf-8",
    )
    mkdocs_yml = tmp_path / "mkdocs.yml"
    mkdocs_yml.write_text(_mkdocs_text(), encoding="utf-8")
    return {
        "docs_root": docs_root,
        "generated_root": generated_root,
        "edge_metrics_csv": edge_metrics_csv,
        "stage_status_csv": stage_status_csv,
        "edge_report_md": edge_report,
        "metric_dictionary_md": metric_dictionary,
        "mkdocs_yml": mkdocs_yml,
    }


def test_docs_contract_smoke_pass(tmp_path: Path) -> None:
    f = _build_smoke_fixture(tmp_path, with_system_reference=True)

    out_checks = tmp_path / "checks.csv"
    out_issues = tmp_path / "issues.csv"
    out_report = tmp_path / "report.md"

    checks, issues = run(
        docs_root=f["docs_root"],
        generated_root=f["generated_root"],
        edge_metrics_csv=f["edge_metrics_csv"],
        stage_status_csv=f["stage_status_csv"],
        metric_dictionary_md=f["metric_dictionary_md"],
        edge_report_md=f["edge_report_md"],
        mkdocs_yml=f["mkdocs_yml"],
        out_checks_csv=out_checks,
        out_issues_csv=out_issues,
        out_report_md=out_report,
        thresholds=Thresholds(max_age_hours=24.0),
    )

    assert not checks.empty
    assert issues.empty
    assert (checks["status"].astype(str) == "pass").all()


def test_docs_contract_flags_missing_explicit_bar_schema_terms_in_stage01(tmp_path: Path) -> None:
    f = _build_smoke_fixture(tmp_path, with_system_reference=True)
    stage01 = f["docs_root"] / "stage_01_data_foundation.md"
    stage01.write_text(
        _stage_doc_text()
        + "\n\n## Tick Build Contract\n"
        + "raw ticks are transformed via build_global_tick_bars.py and build_tick_velocity_dataset.py into tick_velocity datasets.\n",
        encoding="utf-8",
    )

    checks, _issues = run(
        docs_root=f["docs_root"],
        generated_root=f["generated_root"],
        edge_metrics_csv=f["edge_metrics_csv"],
        stage_status_csv=f["stage_status_csv"],
        metric_dictionary_md=f["metric_dictionary_md"],
        edge_report_md=f["edge_report_md"],
        mkdocs_yml=f["mkdocs_yml"],
        out_checks_csv=tmp_path / "checks.csv",
        out_issues_csv=tmp_path / "issues.csv",
        out_report_md=tmp_path / "report.md",
        thresholds=Thresholds(max_age_hours=24.0),
    )

    c51 = checks[checks["check_id"].astype(str) == "C51"]
    assert not c51.empty
    assert (c51["status"].astype(str) == "fail").all()


def test_data_reliability_audit_rejects_legacy_ambiguous_bar_schema(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    base = tmp_path / "data" / "analysis" / "tick_velocity"
    base.mkdir(parents=True, exist_ok=True)
    ts = pd.date_range("2025-01-01", periods=32, freq="30min", tz="UTC")
    close = 1.10 + pd.Series(range(len(ts)), dtype=float) * 0.0001
    legacy = pd.DataFrame(
        {
            "close_ts": ts,
            "open": close.shift(1).fillna(close.iloc[0]),
            "high": close + 0.0002,
            "low": close - 0.0002,
            "close": close,
            "ask": close + 0.0001,
            "cost_est_pips": 0.2,
            "range_pips": 4.0,
            "hour_utc": ts.hour.astype(int),
            "spread_z": 0.0,
            "tick_rate_z": 0.0,
            "vel_cost_units_h1": 0.0,
            "hl_first": 1.0,
        }
    )
    legacy.to_parquet(base / "EURUSD_1000tick_velocity.parquet", index=False)

    with pytest.raises(ValueError, match="legacy ambiguous bar schema unsupported"):
        run_data_reliability_audit(
            symbols=["EURUSD"],
            source_pattern="data/analysis/tick_velocity/{symbol}_1000tick_velocity.parquet",
            thresholds=ReliabilityThresholds(min_rows=1, min_trading_days=1, min_hours_covered=1),
            out_checks_csv=tmp_path / "checks.csv",
            out_issues_csv=tmp_path / "issues.csv",
            out_report_md=tmp_path / "report.md",
        )


def test_docs_contract_flags_nan_metric_values(tmp_path: Path) -> None:
    f = _build_smoke_fixture(tmp_path, with_system_reference=True)

    edge_df = pd.read_csv(f["edge_metrics_csv"])
    edge_df.loc[0, "metric_value"] = float("nan")
    edge_df.to_csv(f["edge_metrics_csv"], index=False)

    out_checks = tmp_path / "checks.csv"
    out_issues = tmp_path / "issues.csv"
    out_report = tmp_path / "report.md"

    checks, issues = run(
        docs_root=f["docs_root"],
        generated_root=f["generated_root"],
        edge_metrics_csv=f["edge_metrics_csv"],
        stage_status_csv=f["stage_status_csv"],
        metric_dictionary_md=f["metric_dictionary_md"],
        edge_report_md=f["edge_report_md"],
        mkdocs_yml=f["mkdocs_yml"],
        out_checks_csv=out_checks,
        out_issues_csv=out_issues,
        out_report_md=out_report,
        thresholds=Thresholds(max_age_hours=24.0),
    )

    c4a = checks[checks["check_id"] == "C4A"]
    assert not c4a.empty
    assert c4a.iloc[0]["status"] == "fail"


def test_docs_contract_flags_missing_metric_definition(tmp_path: Path) -> None:
    docs_root = tmp_path / "docs" / "strategy_bible"
    docs_root.mkdir(parents=True, exist_ok=True)
    generated_root = docs_root / "generated"
    generated_root.mkdir(parents=True, exist_ok=True)

    _write_stage_docs(docs_root)
    _write_analysis_catalog_artifacts(docs_root)

    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    rows = [
        {
            "stage_id": 1,
            "symbol": "EURUSD",
            "metric_id": "D16_spread_regime_shift_z",
            "metric_value": 1.0,
            "generated_at_utc": now,
        }
    ]
    edge_metrics = pd.DataFrame(rows)
    edge_metrics_csv = tmp_path / "edge_metrics.csv"
    edge_metrics.to_csv(edge_metrics_csv, index=False)
    _write_stage04_policy_artifacts(
        generated_root=generated_root, edge_metrics_csv=edge_metrics_csv
    )
    _write_stage11_mc_artifacts(generated_root=generated_root, edge_metrics_csv=edge_metrics_csv)
    _write_run_delta_artifacts(docs_root=docs_root, edge_metrics_csv=edge_metrics_csv)
    _write_operator_action_artifacts(docs_root=docs_root, edge_metrics_csv=edge_metrics_csv)
    _write_stage_integrity_artifacts(docs_root=docs_root, edge_metrics_csv=edge_metrics_csv)
    _write_execution_drift_artifacts(docs_root=docs_root, edge_metrics_csv=edge_metrics_csv)
    _write_threshold_sensitivity_artifacts(docs_root=docs_root, edge_metrics_csv=edge_metrics_csv)
    _write_registry_artifacts(docs_root=docs_root, edge_metrics_csv=edge_metrics_csv)
    _write_alert_remediation_artifacts(docs_root=docs_root, edge_metrics_csv=edge_metrics_csv)
    _write_governance_explainability_artifacts(
        docs_root=docs_root, edge_metrics_csv=edge_metrics_csv
    )

    stage_status_csv = tmp_path / "stage_status.csv"
    pd.DataFrame(
        [
            {
                "symbol": "EURUSD",
                "symbol_all_gates_pass": True,
                "gate_tick_exact": True,
                "gate_api_signal_parity": True,
                "gate_api_execution_parity": True,
                "gate_api_parity": True,
            }
        ]
    ).to_csv(stage_status_csv, index=False)

    (generated_root / "stage_09_snapshot.md").write_text("| EURUSD | pass |\n", encoding="utf-8")
    edge_report = tmp_path / "edge_report.md"
    edge_report.write_text("| 1 | EURUSD | D16_spread_regime_shift_z | 1.0 |\n", encoding="utf-8")

    metric_dictionary = docs_root / "metric_dictionary.md"
    metric_dictionary.write_text(
        "\n".join(
            [
                "# Dict",
                "| metric_id | stage | formula | unit | interpretation bands | missing policy |",
                "| --- | --- | --- | --- | --- | --- |",
                "| M01_top3_contrib_share | 2 | x | u | b | disallow |",
            ]
        ),
        encoding="utf-8",
    )

    mkdocs_yml = tmp_path / "mkdocs.yml"
    mkdocs_yml.write_text(_mkdocs_text(), encoding="utf-8")

    out_checks = tmp_path / "checks.csv"
    out_issues = tmp_path / "issues.csv"
    out_report = tmp_path / "report.md"

    checks, issues = run(
        docs_root=docs_root,
        generated_root=generated_root,
        edge_metrics_csv=edge_metrics_csv,
        stage_status_csv=stage_status_csv,
        metric_dictionary_md=metric_dictionary,
        edge_report_md=edge_report,
        mkdocs_yml=mkdocs_yml,
        out_checks_csv=out_checks,
        out_issues_csv=out_issues,
        out_report_md=out_report,
        thresholds=Thresholds(max_age_hours=24.0),
    )

    c3 = checks[checks["check_id"].astype(str) == "C3"]
    assert not c3.empty
    assert (c3["status"].astype(str) == "fail").all()
    assert not issues.empty


def test_docs_contract_flags_invalid_stage04_action_code(tmp_path: Path) -> None:
    docs_root = tmp_path / "docs" / "strategy_bible"
    docs_root.mkdir(parents=True, exist_ok=True)
    generated_root = docs_root / "generated"
    generated_root.mkdir(parents=True, exist_ok=True)
    _write_stage_docs(docs_root)
    _write_analysis_catalog_artifacts(docs_root)

    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    edge_metrics_csv = tmp_path / "edge_metrics.csv"
    pd.DataFrame(
        [
            {
                "stage_id": 1,
                "symbol": "EURUSD",
                "metric_id": m,
                "metric_value": 1.0,
                "generated_at_utc": now,
            }
            for m in sorted(CORE_METRIC_IDS)
        ]
    ).to_csv(edge_metrics_csv, index=False)
    _write_stage04_policy_artifacts(
        generated_root=generated_root, edge_metrics_csv=edge_metrics_csv
    )
    _write_stage11_mc_artifacts(generated_root=generated_root, edge_metrics_csv=edge_metrics_csv)
    _write_run_delta_artifacts(docs_root=docs_root, edge_metrics_csv=edge_metrics_csv)
    _write_operator_action_artifacts(docs_root=docs_root, edge_metrics_csv=edge_metrics_csv)
    _write_stage_integrity_artifacts(docs_root=docs_root, edge_metrics_csv=edge_metrics_csv)
    _write_execution_drift_artifacts(docs_root=docs_root, edge_metrics_csv=edge_metrics_csv)
    _write_threshold_sensitivity_artifacts(docs_root=docs_root, edge_metrics_csv=edge_metrics_csv)
    _write_registry_artifacts(docs_root=docs_root, edge_metrics_csv=edge_metrics_csv)
    _write_alert_remediation_artifacts(docs_root=docs_root, edge_metrics_csv=edge_metrics_csv)
    _write_governance_explainability_artifacts(
        docs_root=docs_root, edge_metrics_csv=edge_metrics_csv
    )

    bad_policy = pd.read_csv(edge_metrics_csv.parent / "stage04_execution_policy_status.csv")
    bad_policy.loc[0, "action_code"] = "BAD_CODE"
    bad_policy.to_csv(edge_metrics_csv.parent / "stage04_execution_policy_status.csv", index=False)

    stage_status_csv = tmp_path / "stage_status.csv"
    pd.DataFrame(
        [
            {
                "symbol": "EURUSD",
                "symbol_all_gates_pass": True,
                "gate_tick_exact": True,
                "gate_api_signal_parity": True,
                "gate_api_execution_parity": True,
                "gate_api_parity": True,
            }
        ]
    ).to_csv(stage_status_csv, index=False)
    (generated_root / "stage_09_snapshot.md").write_text("| EURUSD | pass |\n", encoding="utf-8")

    edge_report = tmp_path / "edge_report.md"
    edge_report.write_text("| 1 | EURUSD | D16_spread_regime_shift_z | 1.0 |\n", encoding="utf-8")
    metric_dictionary = docs_root / "metric_dictionary.md"
    metric_dictionary.write_text(
        "\n".join(
            [
                "# Dict",
                "| metric_id | stage | formula | unit | interpretation bands | missing policy |",
                "| --- | --- | --- | --- | --- | --- |",
            ]
            + [f"| {m} | 1 | x | u | b | disallow |" for m in sorted(CORE_METRIC_IDS)]
        ),
        encoding="utf-8",
    )
    mkdocs_yml = tmp_path / "mkdocs.yml"
    mkdocs_yml.write_text(_mkdocs_text(), encoding="utf-8")

    checks, _issues = run(
        docs_root=docs_root,
        generated_root=generated_root,
        edge_metrics_csv=edge_metrics_csv,
        stage_status_csv=stage_status_csv,
        metric_dictionary_md=metric_dictionary,
        edge_report_md=edge_report,
        mkdocs_yml=mkdocs_yml,
        out_checks_csv=tmp_path / "checks.csv",
        out_issues_csv=tmp_path / "issues.csv",
        out_report_md=tmp_path / "report.md",
        thresholds=Thresholds(max_age_hours=24.0),
    )

    c11 = checks[checks["check_id"].astype(str) == "C11"]
    assert not c11.empty
    assert (c11["status"].astype(str) == "fail").all()


def test_docs_contract_flags_snapshot_details_over_cap(tmp_path: Path) -> None:
    docs_root = tmp_path / "docs" / "strategy_bible"
    docs_root.mkdir(parents=True, exist_ok=True)
    generated_root = docs_root / "generated"
    generated_root.mkdir(parents=True, exist_ok=True)
    _write_stage_docs(docs_root)
    _write_analysis_catalog_artifacts(docs_root)

    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    edge_metrics_csv = tmp_path / "edge_metrics.csv"
    pd.DataFrame(
        [
            {
                "stage_id": 1,
                "symbol": "EURUSD",
                "metric_id": m,
                "metric_value": 1.0,
                "generated_at_utc": now,
            }
            for m in sorted(CORE_METRIC_IDS)
        ]
    ).to_csv(edge_metrics_csv, index=False)
    _write_stage04_policy_artifacts(
        generated_root=generated_root, edge_metrics_csv=edge_metrics_csv
    )
    _write_stage11_mc_artifacts(generated_root=generated_root, edge_metrics_csv=edge_metrics_csv)
    _write_run_delta_artifacts(docs_root=docs_root, edge_metrics_csv=edge_metrics_csv)
    _write_operator_action_artifacts(docs_root=docs_root, edge_metrics_csv=edge_metrics_csv)
    _write_stage_integrity_artifacts(docs_root=docs_root, edge_metrics_csv=edge_metrics_csv)
    _write_execution_drift_artifacts(docs_root=docs_root, edge_metrics_csv=edge_metrics_csv)
    _write_threshold_sensitivity_artifacts(docs_root=docs_root, edge_metrics_csv=edge_metrics_csv)
    _write_registry_artifacts(docs_root=docs_root, edge_metrics_csv=edge_metrics_csv)
    _write_alert_remediation_artifacts(docs_root=docs_root, edge_metrics_csv=edge_metrics_csv)
    _write_governance_explainability_artifacts(
        docs_root=docs_root, edge_metrics_csv=edge_metrics_csv
    )

    # Build a large details table (>40 rows) to trigger C18 failure.
    lines = ["#### Details", "| a | b |", "| --- | --- |"] + [f"| {i} | x |" for i in range(45)]
    (generated_root / "stage_03_snapshot.md").write_text("\n".join(lines), encoding="utf-8")
    (generated_root / "stage_09_snapshot.md").write_text("| EURUSD | pass |\n", encoding="utf-8")

    stage_status_csv = tmp_path / "stage_status.csv"
    pd.DataFrame(
        [
            {
                "symbol": "EURUSD",
                "symbol_all_gates_pass": True,
                "gate_tick_exact": True,
                "gate_api_signal_parity": True,
                "gate_api_execution_parity": True,
                "gate_api_parity": True,
            }
        ]
    ).to_csv(stage_status_csv, index=False)
    edge_report = tmp_path / "edge_report.md"
    edge_report.write_text("| 1 | EURUSD | D16_spread_regime_shift_z | 1.0 |\n", encoding="utf-8")
    metric_dictionary = docs_root / "metric_dictionary.md"
    metric_dictionary.write_text(
        "\n".join(
            [
                "# Dict",
                "| metric_id | stage | formula | unit | interpretation bands | missing policy |",
                "| --- | --- | --- | --- | --- | --- |",
            ]
            + [f"| {m} | 1 | x | u | b | disallow |" for m in sorted(CORE_METRIC_IDS)]
        ),
        encoding="utf-8",
    )
    mkdocs_yml = tmp_path / "mkdocs.yml"
    mkdocs_yml.write_text(_mkdocs_text(), encoding="utf-8")

    checks, _issues = run(
        docs_root=docs_root,
        generated_root=generated_root,
        edge_metrics_csv=edge_metrics_csv,
        stage_status_csv=stage_status_csv,
        metric_dictionary_md=metric_dictionary,
        edge_report_md=edge_report,
        mkdocs_yml=mkdocs_yml,
        out_checks_csv=tmp_path / "checks.csv",
        out_issues_csv=tmp_path / "issues.csv",
        out_report_md=tmp_path / "report.md",
        thresholds=Thresholds(max_age_hours=24.0),
    )
    c18 = checks[checks["check_id"].astype(str) == "C18"]
    assert not c18.empty
    assert (c18["status"].astype(str) == "fail").all()


def test_docs_contract_flags_missing_run_delta_baseline(tmp_path: Path) -> None:
    docs_root = tmp_path / "docs" / "strategy_bible"
    docs_root.mkdir(parents=True, exist_ok=True)
    generated_root = docs_root / "generated"
    generated_root.mkdir(parents=True, exist_ok=True)
    _write_stage_docs(docs_root)
    _write_analysis_catalog_artifacts(docs_root)

    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    edge_metrics_csv = tmp_path / "edge_metrics.csv"
    pd.DataFrame(
        [
            {
                "stage_id": 1,
                "symbol": "EURUSD",
                "metric_id": m,
                "metric_value": 1.0,
                "generated_at_utc": now,
            }
            for m in sorted(CORE_METRIC_IDS)
        ]
    ).to_csv(edge_metrics_csv, index=False)
    _write_stage04_policy_artifacts(
        generated_root=generated_root, edge_metrics_csv=edge_metrics_csv
    )
    _write_stage11_mc_artifacts(generated_root=generated_root, edge_metrics_csv=edge_metrics_csv)
    _write_run_delta_artifacts(docs_root=docs_root, edge_metrics_csv=edge_metrics_csv)
    _write_operator_action_artifacts(docs_root=docs_root, edge_metrics_csv=edge_metrics_csv)
    _write_stage_integrity_artifacts(docs_root=docs_root, edge_metrics_csv=edge_metrics_csv)
    _write_execution_drift_artifacts(docs_root=docs_root, edge_metrics_csv=edge_metrics_csv)
    _write_threshold_sensitivity_artifacts(docs_root=docs_root, edge_metrics_csv=edge_metrics_csv)
    _write_registry_artifacts(docs_root=docs_root, edge_metrics_csv=edge_metrics_csv)
    _write_alert_remediation_artifacts(docs_root=docs_root, edge_metrics_csv=edge_metrics_csv)
    _write_governance_explainability_artifacts(
        docs_root=docs_root, edge_metrics_csv=edge_metrics_csv
    )

    reg = pd.read_csv(edge_metrics_csv.parent / "run_registry.csv")
    reg["is_baseline"] = 0
    reg.to_csv(edge_metrics_csv.parent / "run_registry.csv", index=False)

    (generated_root / "stage_09_snapshot.md").write_text("| EURUSD | pass |\n", encoding="utf-8")
    stage_status_csv = tmp_path / "stage_status.csv"
    pd.DataFrame(
        [
            {
                "symbol": "EURUSD",
                "symbol_all_gates_pass": True,
                "gate_tick_exact": True,
                "gate_api_signal_parity": True,
                "gate_api_execution_parity": True,
                "gate_api_parity": True,
            }
        ]
    ).to_csv(stage_status_csv, index=False)
    edge_report = tmp_path / "edge_report.md"
    edge_report.write_text("| 1 | EURUSD | D16_spread_regime_shift_z | 1.0 |\n", encoding="utf-8")
    metric_dictionary = docs_root / "metric_dictionary.md"
    metric_dictionary.write_text(
        "\n".join(
            [
                "# Dict",
                "| metric_id | stage | formula | unit | interpretation bands | missing policy |",
                "| --- | --- | --- | --- | --- | --- |",
            ]
            + [f"| {m} | 1 | x | u | b | disallow |" for m in sorted(CORE_METRIC_IDS)]
        ),
        encoding="utf-8",
    )
    mkdocs_yml = tmp_path / "mkdocs.yml"
    mkdocs_yml.write_text(_mkdocs_text(), encoding="utf-8")

    checks, _issues = run(
        docs_root=docs_root,
        generated_root=generated_root,
        edge_metrics_csv=edge_metrics_csv,
        stage_status_csv=stage_status_csv,
        metric_dictionary_md=metric_dictionary,
        edge_report_md=edge_report,
        mkdocs_yml=mkdocs_yml,
        out_checks_csv=tmp_path / "checks.csv",
        out_issues_csv=tmp_path / "issues.csv",
        out_report_md=tmp_path / "report.md",
        thresholds=Thresholds(max_age_hours=24.0),
    )
    c19 = checks[checks["check_id"].astype(str) == "C19"]
    assert not c19.empty
    assert (c19["status"].astype(str) == "fail").all()


def test_docs_contract_flags_unclassified_taxonomy_docs(tmp_path: Path) -> None:
    docs_root = tmp_path / "docs" / "strategy_bible"
    docs_root.mkdir(parents=True, exist_ok=True)
    generated_root = docs_root / "generated"
    generated_root.mkdir(parents=True, exist_ok=True)
    _write_stage_docs(docs_root)
    _write_analysis_catalog_artifacts(docs_root)

    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    edge_metrics_csv = tmp_path / "edge_metrics.csv"
    pd.DataFrame(
        [
            {
                "stage_id": 1,
                "symbol": "EURUSD",
                "metric_id": m,
                "metric_value": 1.0,
                "generated_at_utc": now,
            }
            for m in sorted(CORE_METRIC_IDS)
        ]
    ).to_csv(edge_metrics_csv, index=False)
    _write_stage04_policy_artifacts(
        generated_root=generated_root, edge_metrics_csv=edge_metrics_csv
    )
    _write_stage11_mc_artifacts(generated_root=generated_root, edge_metrics_csv=edge_metrics_csv)
    _write_run_delta_artifacts(docs_root=docs_root, edge_metrics_csv=edge_metrics_csv)
    _write_operator_action_artifacts(docs_root=docs_root, edge_metrics_csv=edge_metrics_csv)
    _write_stage_integrity_artifacts(docs_root=docs_root, edge_metrics_csv=edge_metrics_csv)
    _write_execution_drift_artifacts(docs_root=docs_root, edge_metrics_csv=edge_metrics_csv)
    _write_threshold_sensitivity_artifacts(docs_root=docs_root, edge_metrics_csv=edge_metrics_csv)
    _write_registry_artifacts(docs_root=docs_root, edge_metrics_csv=edge_metrics_csv)
    _write_alert_remediation_artifacts(docs_root=docs_root, edge_metrics_csv=edge_metrics_csv)
    _write_governance_explainability_artifacts(
        docs_root=docs_root, edge_metrics_csv=edge_metrics_csv
    )

    manifest = pd.read_csv(docs_root.parent / "analysis" / "catalog_manifest.csv")
    manifest = pd.concat(
        [
            manifest,
            pd.DataFrame(
                [
                    {
                        "doc_path": "analysis/random_note.md",
                        "title": "Random",
                        "group": "unclassified",
                    }
                ]
            ),
        ],
        ignore_index=True,
    )
    manifest.to_csv(docs_root.parent / "analysis" / "catalog_manifest.csv", index=False)

    (generated_root / "stage_09_snapshot.md").write_text("| EURUSD | pass |\n", encoding="utf-8")
    stage_status_csv = tmp_path / "stage_status.csv"
    pd.DataFrame(
        [
            {
                "symbol": "EURUSD",
                "symbol_all_gates_pass": True,
                "gate_tick_exact": True,
                "gate_api_signal_parity": True,
                "gate_api_execution_parity": True,
                "gate_api_parity": True,
            }
        ]
    ).to_csv(stage_status_csv, index=False)
    edge_report = tmp_path / "edge_report.md"
    edge_report.write_text("| 1 | EURUSD | D16_spread_regime_shift_z | 1.0 |\n", encoding="utf-8")
    metric_dictionary = docs_root / "metric_dictionary.md"
    metric_dictionary.write_text(
        "\n".join(
            [
                "# Dict",
                "| metric_id | stage | formula | unit | interpretation bands | missing policy |",
                "| --- | --- | --- | --- | --- | --- |",
            ]
            + [f"| {m} | 1 | x | u | b | disallow |" for m in sorted(CORE_METRIC_IDS)]
        ),
        encoding="utf-8",
    )
    mkdocs_yml = tmp_path / "mkdocs.yml"
    mkdocs_yml.write_text(_mkdocs_text(), encoding="utf-8")

    checks, _issues = run(
        docs_root=docs_root,
        generated_root=generated_root,
        edge_metrics_csv=edge_metrics_csv,
        stage_status_csv=stage_status_csv,
        metric_dictionary_md=metric_dictionary,
        edge_report_md=edge_report,
        mkdocs_yml=mkdocs_yml,
        out_checks_csv=tmp_path / "checks.csv",
        out_issues_csv=tmp_path / "issues.csv",
        out_report_md=tmp_path / "report.md",
        thresholds=Thresholds(max_age_hours=24.0),
    )
    c20 = checks[checks["check_id"].astype(str) == "C20"]
    assert not c20.empty
    assert (c20["status"].astype(str) == "fail").all()


def test_docs_contract_flags_legacy_taxonomy_docs(tmp_path: Path) -> None:
    docs_root = tmp_path / "docs" / "strategy_bible"
    docs_root.mkdir(parents=True, exist_ok=True)
    generated_root = docs_root / "generated"
    generated_root.mkdir(parents=True, exist_ok=True)
    _write_stage_docs(docs_root)
    _write_analysis_catalog_artifacts(docs_root)

    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    edge_metrics_csv = tmp_path / "edge_metrics.csv"
    pd.DataFrame(
        [
            {
                "stage_id": 1,
                "symbol": "EURUSD",
                "metric_id": m,
                "metric_value": 1.0,
                "generated_at_utc": now,
            }
            for m in sorted(CORE_METRIC_IDS)
        ]
    ).to_csv(edge_metrics_csv, index=False)
    _write_stage04_policy_artifacts(
        generated_root=generated_root, edge_metrics_csv=edge_metrics_csv
    )
    _write_stage11_mc_artifacts(generated_root=generated_root, edge_metrics_csv=edge_metrics_csv)
    _write_run_delta_artifacts(docs_root=docs_root, edge_metrics_csv=edge_metrics_csv)
    _write_operator_action_artifacts(docs_root=docs_root, edge_metrics_csv=edge_metrics_csv)
    _write_stage_integrity_artifacts(docs_root=docs_root, edge_metrics_csv=edge_metrics_csv)
    _write_execution_drift_artifacts(docs_root=docs_root, edge_metrics_csv=edge_metrics_csv)
    _write_threshold_sensitivity_artifacts(docs_root=docs_root, edge_metrics_csv=edge_metrics_csv)
    _write_registry_artifacts(docs_root=docs_root, edge_metrics_csv=edge_metrics_csv)
    _write_alert_remediation_artifacts(docs_root=docs_root, edge_metrics_csv=edge_metrics_csv)
    _write_governance_explainability_artifacts(
        docs_root=docs_root, edge_metrics_csv=edge_metrics_csv
    )

    manifest = pd.read_csv(docs_root.parent / "analysis" / "catalog_manifest.csv")
    manifest = pd.concat(
        [
            manifest,
            pd.DataFrame(
                [{"doc_path": "analysis/old_note.md", "title": "Legacy", "group": "legacy"}]
            ),
        ],
        ignore_index=True,
    )
    manifest.to_csv(docs_root.parent / "analysis" / "catalog_manifest.csv", index=False)

    (generated_root / "stage_09_snapshot.md").write_text("| EURUSD | pass |\n", encoding="utf-8")
    stage_status_csv = tmp_path / "stage_status.csv"
    pd.DataFrame(
        [
            {
                "symbol": "EURUSD",
                "symbol_all_gates_pass": True,
                "gate_tick_exact": True,
                "gate_api_signal_parity": True,
                "gate_api_execution_parity": True,
                "gate_api_parity": True,
            }
        ]
    ).to_csv(stage_status_csv, index=False)
    edge_report = tmp_path / "edge_report.md"
    edge_report.write_text("| 1 | EURUSD | D16_spread_regime_shift_z | 1.0 |\n", encoding="utf-8")
    metric_dictionary = docs_root / "metric_dictionary.md"
    metric_dictionary.write_text(
        "\n".join(
            [
                "# Dict",
                "| metric_id | stage | formula | unit | interpretation bands | missing policy |",
                "| --- | --- | --- | --- | --- | --- |",
            ]
            + [f"| {m} | 1 | x | u | b | disallow |" for m in sorted(CORE_METRIC_IDS)]
        ),
        encoding="utf-8",
    )
    mkdocs_yml = tmp_path / "mkdocs.yml"
    mkdocs_yml.write_text(_mkdocs_text(), encoding="utf-8")

    checks, _issues = run(
        docs_root=docs_root,
        generated_root=generated_root,
        edge_metrics_csv=edge_metrics_csv,
        stage_status_csv=stage_status_csv,
        metric_dictionary_md=metric_dictionary,
        edge_report_md=edge_report,
        mkdocs_yml=mkdocs_yml,
        out_checks_csv=tmp_path / "checks.csv",
        out_issues_csv=tmp_path / "issues.csv",
        out_report_md=tmp_path / "report.md",
        thresholds=Thresholds(max_age_hours=24.0),
    )
    c20b = checks[checks["check_id"].astype(str) == "C20B"]
    assert not c20b.empty
    assert (c20b["status"].astype(str) == "fail").all()


def test_docs_contract_flags_expired_accepted_exception(tmp_path: Path) -> None:
    docs_root = tmp_path / "docs" / "strategy_bible"
    docs_root.mkdir(parents=True, exist_ok=True)
    generated_root = docs_root / "generated"
    generated_root.mkdir(parents=True, exist_ok=True)
    _write_stage_docs(docs_root)
    _write_analysis_catalog_artifacts(docs_root)

    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    edge_metrics_csv = tmp_path / "edge_metrics.csv"
    pd.DataFrame(
        [
            {
                "stage_id": 1,
                "symbol": "EURUSD",
                "metric_id": m,
                "metric_value": 1.0,
                "generated_at_utc": now,
            }
            for m in sorted(CORE_METRIC_IDS)
        ]
    ).to_csv(edge_metrics_csv, index=False)
    _write_stage04_policy_artifacts(
        generated_root=generated_root, edge_metrics_csv=edge_metrics_csv
    )
    _write_stage11_mc_artifacts(generated_root=generated_root, edge_metrics_csv=edge_metrics_csv)
    _write_run_delta_artifacts(docs_root=docs_root, edge_metrics_csv=edge_metrics_csv)
    _write_operator_action_artifacts(docs_root=docs_root, edge_metrics_csv=edge_metrics_csv)
    _write_stage_integrity_artifacts(docs_root=docs_root, edge_metrics_csv=edge_metrics_csv)
    _write_execution_drift_artifacts(docs_root=docs_root, edge_metrics_csv=edge_metrics_csv)
    _write_threshold_sensitivity_artifacts(docs_root=docs_root, edge_metrics_csv=edge_metrics_csv)
    _write_registry_artifacts(docs_root=docs_root, edge_metrics_csv=edge_metrics_csv)
    _write_alert_remediation_artifacts(docs_root=docs_root, edge_metrics_csv=edge_metrics_csv)
    _write_governance_explainability_artifacts(
        docs_root=docs_root, edge_metrics_csv=edge_metrics_csv
    )

    disp = pd.read_csv(edge_metrics_csv.parent / "oco_alert_disposition.csv")
    disp.loc[0, "status"] = "accepted_exception"
    disp.loc[0, "is_expired"] = True
    disp.to_csv(edge_metrics_csv.parent / "oco_alert_disposition.csv", index=False)

    (generated_root / "stage_09_snapshot.md").write_text("| EURUSD | pass |\n", encoding="utf-8")
    stage_status_csv = tmp_path / "stage_status.csv"
    pd.DataFrame(
        [
            {
                "symbol": "EURUSD",
                "symbol_all_gates_pass": True,
                "gate_tick_exact": True,
                "gate_api_signal_parity": True,
                "gate_api_execution_parity": True,
                "gate_api_parity": True,
            }
        ]
    ).to_csv(stage_status_csv, index=False)
    edge_report = tmp_path / "edge_report.md"
    edge_report.write_text("| 1 | EURUSD | D16_spread_regime_shift_z | 1.0 |\n", encoding="utf-8")
    metric_dictionary = docs_root / "metric_dictionary.md"
    metric_dictionary.write_text(
        "\n".join(
            [
                "# Dict",
                "| metric_id | stage | formula | unit | interpretation bands | missing policy |",
                "| --- | --- | --- | --- | --- | --- |",
            ]
            + [f"| {m} | 1 | x | u | b | disallow |" for m in sorted(CORE_METRIC_IDS)]
        ),
        encoding="utf-8",
    )
    mkdocs_yml = tmp_path / "mkdocs.yml"
    mkdocs_yml.write_text(_mkdocs_text(), encoding="utf-8")

    checks, _issues = run(
        docs_root=docs_root,
        generated_root=generated_root,
        edge_metrics_csv=edge_metrics_csv,
        stage_status_csv=stage_status_csv,
        metric_dictionary_md=metric_dictionary,
        edge_report_md=edge_report,
        mkdocs_yml=mkdocs_yml,
        out_checks_csv=tmp_path / "checks.csv",
        out_issues_csv=tmp_path / "issues.csv",
        out_report_md=tmp_path / "report.md",
        thresholds=Thresholds(max_age_hours=24.0),
    )
    c35 = checks[checks["check_id"].astype(str) == "C35"]
    assert not c35.empty
    assert (c35["status"].astype(str) == "fail").all()


def test_docs_contract_ignores_recurrence_for_accepted_exception(tmp_path: Path) -> None:
    fixture = _build_smoke_fixture(tmp_path)
    disp_csv = fixture["edge_metrics_csv"].parent / "oco_alert_disposition.csv"
    disp = pd.read_csv(disp_csv)
    disp.loc[0, "status"] = "accepted_exception"
    disp.loc[0, "recurrence_breach"] = True
    disp.loc[0, "consecutive_runs_non_green"] = 99
    disp.loc[0, "months_non_green_count"] = 99
    disp.to_csv(disp_csv, index=False)

    checks, _issues = run(
        docs_root=fixture["docs_root"],
        generated_root=fixture["generated_root"],
        edge_metrics_csv=fixture["edge_metrics_csv"],
        stage_status_csv=fixture["stage_status_csv"],
        metric_dictionary_md=fixture["metric_dictionary_md"],
        edge_report_md=fixture["edge_report_md"],
        mkdocs_yml=fixture["mkdocs_yml"],
        out_checks_csv=tmp_path / "checks.csv",
        out_issues_csv=tmp_path / "issues.csv",
        out_report_md=tmp_path / "report.md",
        thresholds=Thresholds(max_age_hours=24.0),
    )
    c36 = checks[checks["check_id"].astype(str) == "C36"]
    assert not c36.empty
    assert (c36["status"].astype(str) == "pass").all()


def test_docs_contract_flags_missing_explainability_coverage(tmp_path: Path) -> None:
    docs_root = tmp_path / "docs" / "strategy_bible"
    docs_root.mkdir(parents=True, exist_ok=True)
    generated_root = docs_root / "generated"
    generated_root.mkdir(parents=True, exist_ok=True)
    _write_stage_docs(docs_root)
    _write_analysis_catalog_artifacts(docs_root)

    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    edge_metrics_csv = tmp_path / "edge_metrics.csv"
    pd.DataFrame(
        [
            {
                "stage_id": 1,
                "symbol": "EURUSD",
                "metric_id": m,
                "metric_value": 1.0,
                "generated_at_utc": now,
            }
            for m in sorted(CORE_METRIC_IDS)
        ]
    ).to_csv(edge_metrics_csv, index=False)
    _write_stage04_policy_artifacts(
        generated_root=generated_root, edge_metrics_csv=edge_metrics_csv
    )
    _write_stage11_mc_artifacts(generated_root=generated_root, edge_metrics_csv=edge_metrics_csv)
    _write_run_delta_artifacts(docs_root=docs_root, edge_metrics_csv=edge_metrics_csv)
    _write_operator_action_artifacts(docs_root=docs_root, edge_metrics_csv=edge_metrics_csv)
    _write_stage_integrity_artifacts(docs_root=docs_root, edge_metrics_csv=edge_metrics_csv)
    _write_execution_drift_artifacts(docs_root=docs_root, edge_metrics_csv=edge_metrics_csv)
    _write_threshold_sensitivity_artifacts(docs_root=docs_root, edge_metrics_csv=edge_metrics_csv)
    _write_registry_artifacts(docs_root=docs_root, edge_metrics_csv=edge_metrics_csv)
    _write_alert_remediation_artifacts(docs_root=docs_root, edge_metrics_csv=edge_metrics_csv)
    _write_governance_explainability_artifacts(
        docs_root=docs_root, edge_metrics_csv=edge_metrics_csv
    )

    explain = pd.read_csv(edge_metrics_csv.parent / "oco_governance_explainability.csv")
    explain = explain[explain["metric_id"].astype(str) != "E_DRIFT_OVERSHOOT_P95"].copy()
    explain.to_csv(edge_metrics_csv.parent / "oco_governance_explainability.csv", index=False)

    (generated_root / "stage_09_snapshot.md").write_text("| EURUSD | pass |\n", encoding="utf-8")
    stage_status_csv = tmp_path / "stage_status.csv"
    pd.DataFrame(
        [
            {
                "symbol": "EURUSD",
                "symbol_all_gates_pass": True,
                "gate_tick_exact": True,
                "gate_api_signal_parity": True,
                "gate_api_execution_parity": True,
                "gate_api_parity": True,
            }
        ]
    ).to_csv(stage_status_csv, index=False)
    edge_report = tmp_path / "edge_report.md"
    edge_report.write_text("| 1 | EURUSD | D16_spread_regime_shift_z | 1.0 |\n", encoding="utf-8")
    metric_dictionary = docs_root / "metric_dictionary.md"
    metric_dictionary.write_text(
        "\n".join(
            [
                "# Dict",
                "| metric_id | stage | formula | unit | interpretation bands | missing policy |",
                "| --- | --- | --- | --- | --- | --- |",
            ]
            + [f"| {m} | 1 | x | u | b | disallow |" for m in sorted(CORE_METRIC_IDS)]
        ),
        encoding="utf-8",
    )
    mkdocs_yml = tmp_path / "mkdocs.yml"
    mkdocs_yml.write_text(_mkdocs_text(), encoding="utf-8")

    checks, _issues = run(
        docs_root=docs_root,
        generated_root=generated_root,
        edge_metrics_csv=edge_metrics_csv,
        stage_status_csv=stage_status_csv,
        metric_dictionary_md=metric_dictionary,
        edge_report_md=edge_report,
        mkdocs_yml=mkdocs_yml,
        out_checks_csv=tmp_path / "checks.csv",
        out_issues_csv=tmp_path / "issues.csv",
        out_report_md=tmp_path / "report.md",
        thresholds=Thresholds(max_age_hours=24.0),
    )
    c39 = checks[checks["check_id"].astype(str) == "C39"]
    assert not c39.empty
    assert (c39["status"].astype(str) == "fail").all()


def test_docs_contract_flags_machine_local_paths(tmp_path: Path) -> None:
    docs_root = tmp_path / "docs" / "strategy_bible"
    docs_root.mkdir(parents=True, exist_ok=True)
    generated_root = docs_root / "generated"
    generated_root.mkdir(parents=True, exist_ok=True)
    _write_stage_docs(docs_root)
    _write_analysis_catalog_artifacts(docs_root)

    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    edge_metrics_csv = tmp_path / "edge_metrics.csv"
    pd.DataFrame(
        [
            {
                "stage_id": 1,
                "symbol": "EURUSD",
                "metric_id": m,
                "metric_value": 1.0,
                "generated_at_utc": now,
            }
            for m in sorted(CORE_METRIC_IDS)
        ]
    ).to_csv(edge_metrics_csv, index=False)
    _write_stage04_policy_artifacts(
        generated_root=generated_root, edge_metrics_csv=edge_metrics_csv
    )
    _write_stage11_mc_artifacts(generated_root=generated_root, edge_metrics_csv=edge_metrics_csv)
    _write_run_delta_artifacts(docs_root=docs_root, edge_metrics_csv=edge_metrics_csv)
    _write_operator_action_artifacts(docs_root=docs_root, edge_metrics_csv=edge_metrics_csv)
    _write_stage_integrity_artifacts(docs_root=docs_root, edge_metrics_csv=edge_metrics_csv)
    _write_execution_drift_artifacts(docs_root=docs_root, edge_metrics_csv=edge_metrics_csv)
    _write_threshold_sensitivity_artifacts(docs_root=docs_root, edge_metrics_csv=edge_metrics_csv)
    _write_registry_artifacts(docs_root=docs_root, edge_metrics_csv=edge_metrics_csv)
    _write_alert_remediation_artifacts(docs_root=docs_root, edge_metrics_csv=edge_metrics_csv)
    _write_governance_explainability_artifacts(
        docs_root=docs_root, edge_metrics_csv=edge_metrics_csv
    )

    (docs_root.parent / "analysis" / "oco_alert_remediation_report.md").write_text(
        "# Alert Remediation\n\nsource: /Users/tester/fake/path.csv\n",
        encoding="utf-8",
    )

    (generated_root / "stage_09_snapshot.md").write_text("| EURUSD | pass |\n", encoding="utf-8")
    stage_status_csv = tmp_path / "stage_status.csv"
    pd.DataFrame(
        [
            {
                "symbol": "EURUSD",
                "symbol_all_gates_pass": True,
                "gate_tick_exact": True,
                "gate_api_signal_parity": True,
                "gate_api_execution_parity": True,
                "gate_api_parity": True,
            }
        ]
    ).to_csv(stage_status_csv, index=False)
    edge_report = tmp_path / "edge_report.md"
    edge_report.write_text("| 1 | EURUSD | D16_spread_regime_shift_z | 1.0 |\n", encoding="utf-8")
    metric_dictionary = docs_root / "metric_dictionary.md"
    metric_dictionary.write_text(
        "\n".join(
            [
                "# Dict",
                "| metric_id | stage | formula | unit | interpretation bands | missing policy |",
                "| --- | --- | --- | --- | --- | --- |",
            ]
            + [f"| {m} | 1 | x | u | b | disallow |" for m in sorted(CORE_METRIC_IDS)]
        ),
        encoding="utf-8",
    )
    mkdocs_yml = tmp_path / "mkdocs.yml"
    mkdocs_yml.write_text(_mkdocs_text(), encoding="utf-8")

    checks, _issues = run(
        docs_root=docs_root,
        generated_root=generated_root,
        edge_metrics_csv=edge_metrics_csv,
        stage_status_csv=stage_status_csv,
        metric_dictionary_md=metric_dictionary,
        edge_report_md=edge_report,
        mkdocs_yml=mkdocs_yml,
        out_checks_csv=tmp_path / "checks.csv",
        out_issues_csv=tmp_path / "issues.csv",
        out_report_md=tmp_path / "report.md",
        thresholds=Thresholds(max_age_hours=24.0),
    )
    c40 = checks[checks["check_id"].astype(str) == "C40"]
    assert not c40.empty
    assert (c40["status"].astype(str) == "fail").all()


def test_docs_contract_flags_missing_system_reference_pages(tmp_path: Path) -> None:
    f = _build_smoke_fixture(tmp_path, with_system_reference=False)
    checks, _issues = run(
        docs_root=f["docs_root"],
        generated_root=f["generated_root"],
        edge_metrics_csv=f["edge_metrics_csv"],
        stage_status_csv=f["stage_status_csv"],
        metric_dictionary_md=f["metric_dictionary_md"],
        edge_report_md=f["edge_report_md"],
        mkdocs_yml=f["mkdocs_yml"],
        out_checks_csv=tmp_path / "checks.csv",
        out_issues_csv=tmp_path / "issues.csv",
        out_report_md=tmp_path / "report.md",
        thresholds=Thresholds(max_age_hours=24.0),
    )
    c41 = checks[checks["check_id"].astype(str) == "C41"]
    assert not c41.empty
    assert (c41["status"].astype(str) == "fail").all()


def test_docs_contract_flags_system_reference_symbol_coverage_gap(tmp_path: Path) -> None:
    f = _build_smoke_fixture(tmp_path, with_system_reference=True)
    api_md = f["docs_root"].parent / "api.md"
    txt = api_md.read_text(encoding="utf-8")
    txt = txt.replace("EURUSD,GBPUSD,USDJPY,USDCHF", "EURUSD,GBPUSD")
    api_md.write_text(txt, encoding="utf-8")

    checks, _issues = run(
        docs_root=f["docs_root"],
        generated_root=f["generated_root"],
        edge_metrics_csv=f["edge_metrics_csv"],
        stage_status_csv=f["stage_status_csv"],
        metric_dictionary_md=f["metric_dictionary_md"],
        edge_report_md=f["edge_report_md"],
        mkdocs_yml=f["mkdocs_yml"],
        out_checks_csv=tmp_path / "checks.csv",
        out_issues_csv=tmp_path / "issues.csv",
        out_report_md=tmp_path / "report.md",
        thresholds=Thresholds(max_age_hours=24.0),
    )
    c46 = checks[checks["check_id"].astype(str) == "C46"]
    assert not c46.empty
    assert (c46["status"].astype(str) == "fail").all()


def test_docs_contract_flags_missing_stage09_predeploy_coverage(tmp_path: Path) -> None:
    f = _build_smoke_fixture(tmp_path, with_system_reference=True)
    base = f["edge_metrics_csv"].parent
    all_syms = ["EURUSD", "GBPUSD", "USDJPY", "USDCHF", "AUDUSD", "USDCAD"]

    for sym in all_syms:
        if sym == "AUDUSD":
            continue
        (base / f"{sym.lower()}_governance_predeploy.json").write_text("{}", encoding="utf-8")

    (f["generated_root"] / "stage_09_snapshot.md").write_text(
        "\n".join(
            [
                "#### Predeploy Validator Status",
                "| symbol | status | blocker | checks_total | checks_failed | leakage_high_critical_issues | execution_risk_high_critical_issues | g01_near_fail_count | g03_lock_drift_flags | as_of | window_end | failed_checks |",
                "|:--|:--|:--|--:|--:|--:|--:|--:|--:|:--|:--|:--|",
                "| EURUSD | pass | False | 25 | 0 | 0 | 0 | 0 | 0 | 2026-02-26 | 2026-03-31 | |",
                "| GBPUSD | pass | False | 25 | 0 | 0 | 0 | 0 | 0 | 2026-02-26 | 2026-03-31 | |",
                "| AUDUSD | missing | True | 1 | 1 | 0 | 0 | 0 | 0 | nan | nan | missing_predeploy_json |",
                "| USDJPY | pass | False | 25 | 0 | 0 | 0 | 0 | 0 | 2026-02-26 | 2026-03-31 | |",
                "| USDCHF | pass | False | 25 | 0 | 0 | 0 | 0 | 0 | 2026-02-26 | 2026-03-31 | |",
                "| USDCAD | pass | False | 25 | 0 | 0 | 0 | 0 | 0 | 2026-02-26 | 2026-03-31 | |",
            ]
        ),
        encoding="utf-8",
    )

    checks, _issues = run(
        docs_root=f["docs_root"],
        generated_root=f["generated_root"],
        edge_metrics_csv=f["edge_metrics_csv"],
        stage_status_csv=f["stage_status_csv"],
        metric_dictionary_md=f["metric_dictionary_md"],
        edge_report_md=f["edge_report_md"],
        mkdocs_yml=f["mkdocs_yml"],
        out_checks_csv=tmp_path / "checks.csv",
        out_issues_csv=tmp_path / "issues.csv",
        out_report_md=tmp_path / "report.md",
        thresholds=Thresholds(max_age_hours=24.0),
    )
    c52 = checks[checks["check_id"].astype(str) == "C52"]
    assert not c52.empty
    assert (c52["status"].astype(str) == "fail").all()


def test_docs_contract_flags_nan_stage09_governance_diagnostics(tmp_path: Path) -> None:
    f = _build_smoke_fixture(tmp_path, with_system_reference=True)
    base = f["edge_metrics_csv"].parent
    all_syms = ["EURUSD", "GBPUSD", "USDJPY", "USDCHF", "AUDUSD", "USDCAD"]
    for sym in all_syms:
        (base / f"{sym.lower()}_governance_predeploy.json").write_text("{}", encoding="utf-8")

    (f["generated_root"] / "stage_09_snapshot.md").write_text(
        "\n".join(
            [
                "#### Predeploy Validator Status",
                "| symbol | status | blocker | checks_total | checks_failed | leakage_high_critical_issues | execution_risk_high_critical_issues | g01_near_fail_count | g03_lock_drift_flags | as_of | window_end | failed_checks |",
                "|:--|:--|:--|--:|--:|--:|--:|--:|--:|:--|:--|:--|",
                "| EURUSD | pass | False | 25 | 0 | 0 | 0 | 0 | 0 | 2026-02-26 | 2026-03-31 | |",
                "| GBPUSD | pass | False | 25 | 0 | 0 | 0 | 0 | 0 | 2026-02-26 | 2026-03-31 | |",
                "| AUDUSD | pass | False | 25 | 0 | 0 | 0 | nan | nan | 2026-02-26 | 2026-03-31 | |",
                "| USDJPY | pass | False | 25 | 0 | 0 | 0 | 0 | 0 | 2026-02-26 | 2026-03-31 | |",
                "| USDCHF | pass | False | 25 | 0 | 0 | 0 | 0 | 0 | 2026-02-26 | 2026-03-31 | |",
                "| USDCAD | pass | False | 25 | 0 | 0 | 0 | 0 | 0 | 2026-02-26 | 2026-03-31 | |",
            ]
        ),
        encoding="utf-8",
    )

    checks, _issues = run(
        docs_root=f["docs_root"],
        generated_root=f["generated_root"],
        edge_metrics_csv=f["edge_metrics_csv"],
        stage_status_csv=f["stage_status_csv"],
        metric_dictionary_md=f["metric_dictionary_md"],
        edge_report_md=f["edge_report_md"],
        mkdocs_yml=f["mkdocs_yml"],
        out_checks_csv=tmp_path / "checks.csv",
        out_issues_csv=tmp_path / "issues.csv",
        out_report_md=tmp_path / "report.md",
        thresholds=Thresholds(max_age_hours=24.0),
    )
    c53 = checks[checks["check_id"].astype(str) == "C53"]
    assert not c53.empty
    assert (c53["status"].astype(str) == "fail").all()


def test_docs_contract_optional_strict_symbol_gate_mode(tmp_path: Path) -> None:
    f = _build_smoke_fixture(tmp_path, with_system_reference=True)
    stage_status = pd.read_csv(f["stage_status_csv"])
    stage_status.loc[stage_status["symbol"] == "USDCHF", "symbol_all_gates_pass"] = False
    stage_status.to_csv(f["stage_status_csv"], index=False)

    checks, _issues = run(
        docs_root=f["docs_root"],
        generated_root=f["generated_root"],
        edge_metrics_csv=f["edge_metrics_csv"],
        stage_status_csv=f["stage_status_csv"],
        metric_dictionary_md=f["metric_dictionary_md"],
        edge_report_md=f["edge_report_md"],
        mkdocs_yml=f["mkdocs_yml"],
        out_checks_csv=tmp_path / "checks.csv",
        out_issues_csv=tmp_path / "issues.csv",
        out_report_md=tmp_path / "report.md",
        thresholds=Thresholds(max_age_hours=24.0, fail_if_any_symbol_gate_fails=True),
    )
    c54 = checks[checks["check_id"].astype(str) == "C54"]
    assert not c54.empty
    assert (c54["status"].astype(str) == "fail").all()


def test_docs_contract_flags_stage12_api_parity_failure(tmp_path: Path) -> None:
    f = _build_smoke_fixture(tmp_path, with_system_reference=True)
    stage_status = pd.read_csv(f["stage_status_csv"])
    stage_status.loc[stage_status["symbol"] == "USDCHF", "gate_api_signal_parity"] = False
    stage_status.loc[stage_status["symbol"] == "USDCHF", "gate_api_parity"] = False
    stage_status.loc[stage_status["symbol"] == "USDCHF", "symbol_all_gates_pass"] = False
    stage_status.to_csv(f["stage_status_csv"], index=False)

    checks, _issues = run(
        docs_root=f["docs_root"],
        generated_root=f["generated_root"],
        edge_metrics_csv=f["edge_metrics_csv"],
        stage_status_csv=f["stage_status_csv"],
        metric_dictionary_md=f["metric_dictionary_md"],
        edge_report_md=f["edge_report_md"],
        mkdocs_yml=f["mkdocs_yml"],
        out_checks_csv=tmp_path / "checks.csv",
        out_issues_csv=tmp_path / "issues.csv",
        out_report_md=tmp_path / "report.md",
        thresholds=Thresholds(max_age_hours=24.0),
    )
    c56 = checks[checks["check_id"].astype(str) == "C56"]
    assert not c56.empty
    assert (c56["status"].astype(str) == "fail").all()
