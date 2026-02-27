from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from scripts.validate_oco_docs_contract import CORE_METRIC_IDS, STAGE04_POLICY_REQUIRED_METRICS, Thresholds, run


def _stage_doc_text() -> str:
    return """# Stage X\n\n## Objective\n\n## Inputs\n\n## Process\n\n## Exact Calculations\n\n## Causality / Leakage Controls\n\n## Failure Modes\n\n## Interpretation Guide\n\n## Validation Gates\n\n## Reproduction Commands\n\n## Traceability\n"""


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
    }
    for i, n in names.items():
        txt = _stage_doc_text()
        if i == 4:
            txt = txt + _stage04_policy_sections_text()
        (root / n).write_text(txt, encoding="utf-8")


def _write_stage04_policy_artifacts(*, generated_root: Path, edge_metrics_csv: Path) -> None:
    (generated_root / "stage_04_snapshot.md").write_text("#### Policy Status\n| symbol | status |\n|---|---|\n| EURUSD | green |\n", encoding="utf-8")
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


def _mkdocs_text() -> str:
    paths = [
        "analysis/index.md",
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
        "strategy_bible/metric_dictionary.md",
        "strategy_bible/assumptions_and_threats.md",
        "strategy_bible/governance_mapping.md",
        "analysis/data_reliability_report.md",
        "analysis/oco_leakage_integrity_report.md",
        "analysis/oco_execution_risk_prelive_report.md",
        "analysis/oco_execution_monte_carlo_report.md",
        "analysis/oco_execution_monte_carlo_validation_report.md",
        "analysis/oco_logical_audit_report.md",
        "analysis/oco_edge_clarity_report.md",
        "analysis/oco_docs_contract_report.md",
    ]
    return "\n".join(["nav:"] + [f"  - {p}" for p in paths])


def _write_analysis_catalog_artifacts(docs_root: Path) -> None:
    analysis = docs_root.parent / "analysis"
    analysis.mkdir(parents=True, exist_ok=True)
    files = [
        "data_reliability_report.md",
        "oco_leakage_integrity_report.md",
        "oco_execution_risk_prelive_report.md",
        "oco_execution_monte_carlo_report.md",
        "oco_execution_monte_carlo_validation_report.md",
        "oco_logical_audit_report.md",
        "oco_edge_clarity_report.md",
        "oco_docs_contract_report.md",
    ]
    for name in files:
        (analysis / name).write_text(f"# {name}\n", encoding="utf-8")
    (analysis / "index.md").write_text("# Analysis Catalog\n", encoding="utf-8")
    (analysis / "catalog_gaps_report.md").write_text("# gaps\n", encoding="utf-8")
    manifest_rows = [{"doc_path": f"analysis/{name}", "title": name, "group": "core"} for name in files]
    pd.DataFrame(manifest_rows).to_csv(analysis / "catalog_manifest.csv", index=False)


def test_docs_contract_smoke_pass(tmp_path: Path) -> None:
    docs_root = tmp_path / "docs" / "strategy_bible"
    docs_root.mkdir(parents=True, exist_ok=True)
    generated_root = docs_root / "generated"
    generated_root.mkdir(parents=True, exist_ok=True)

    _write_stage_docs(docs_root)
    _write_analysis_catalog_artifacts(docs_root)

    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    rows = [{"stage_id": 1, "symbol": "EURUSD", "metric_id": m, "metric_value": 1.0, "generated_at_utc": now} for m in sorted(CORE_METRIC_IDS)]
    edge_metrics = pd.DataFrame(rows)
    edge_metrics_csv = tmp_path / "edge_metrics.csv"
    edge_metrics.to_csv(edge_metrics_csv, index=False)
    _write_stage04_policy_artifacts(generated_root=generated_root, edge_metrics_csv=edge_metrics_csv)
    _write_stage11_mc_artifacts(generated_root=generated_root, edge_metrics_csv=edge_metrics_csv)

    stage_status_csv = tmp_path / "stage_status.csv"
    pd.DataFrame([{"symbol": "EURUSD", "symbol_all_gates_pass": True}]).to_csv(stage_status_csv, index=False)

    stage09 = generated_root / "stage_09_snapshot.md"
    stage09.write_text("| EURUSD | pass |\n", encoding="utf-8")

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

    assert not checks.empty
    assert issues.empty
    assert (checks["status"].astype(str) == "pass").all()


def test_docs_contract_flags_missing_metric_definition(tmp_path: Path) -> None:
    docs_root = tmp_path / "docs" / "strategy_bible"
    docs_root.mkdir(parents=True, exist_ok=True)
    generated_root = docs_root / "generated"
    generated_root.mkdir(parents=True, exist_ok=True)

    _write_stage_docs(docs_root)
    _write_analysis_catalog_artifacts(docs_root)

    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    rows = [{"stage_id": 1, "symbol": "EURUSD", "metric_id": "D16_spread_regime_shift_z", "metric_value": 1.0, "generated_at_utc": now}]
    edge_metrics = pd.DataFrame(rows)
    edge_metrics_csv = tmp_path / "edge_metrics.csv"
    edge_metrics.to_csv(edge_metrics_csv, index=False)
    _write_stage04_policy_artifacts(generated_root=generated_root, edge_metrics_csv=edge_metrics_csv)
    _write_stage11_mc_artifacts(generated_root=generated_root, edge_metrics_csv=edge_metrics_csv)

    stage_status_csv = tmp_path / "stage_status.csv"
    pd.DataFrame([{"symbol": "EURUSD", "symbol_all_gates_pass": True}]).to_csv(stage_status_csv, index=False)

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
        [{"stage_id": 1, "symbol": "EURUSD", "metric_id": m, "metric_value": 1.0, "generated_at_utc": now} for m in sorted(CORE_METRIC_IDS)]
    ).to_csv(edge_metrics_csv, index=False)
    _write_stage04_policy_artifacts(generated_root=generated_root, edge_metrics_csv=edge_metrics_csv)
    _write_stage11_mc_artifacts(generated_root=generated_root, edge_metrics_csv=edge_metrics_csv)

    bad_policy = pd.read_csv(edge_metrics_csv.parent / "stage04_execution_policy_status.csv")
    bad_policy.loc[0, "action_code"] = "BAD_CODE"
    bad_policy.to_csv(edge_metrics_csv.parent / "stage04_execution_policy_status.csv", index=False)

    stage_status_csv = tmp_path / "stage_status.csv"
    pd.DataFrame([{"symbol": "EURUSD", "symbol_all_gates_pass": True}]).to_csv(stage_status_csv, index=False)
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
        [{"stage_id": 1, "symbol": "EURUSD", "metric_id": m, "metric_value": 1.0, "generated_at_utc": now} for m in sorted(CORE_METRIC_IDS)]
    ).to_csv(edge_metrics_csv, index=False)
    _write_stage04_policy_artifacts(generated_root=generated_root, edge_metrics_csv=edge_metrics_csv)
    _write_stage11_mc_artifacts(generated_root=generated_root, edge_metrics_csv=edge_metrics_csv)

    # Build a large details table (>40 rows) to trigger C18 failure.
    lines = ["#### Details", "| a | b |", "| --- | --- |"] + [f"| {i} | x |" for i in range(45)]
    (generated_root / "stage_03_snapshot.md").write_text("\n".join(lines), encoding="utf-8")
    (generated_root / "stage_09_snapshot.md").write_text("| EURUSD | pass |\n", encoding="utf-8")

    stage_status_csv = tmp_path / "stage_status.csv"
    pd.DataFrame([{"symbol": "EURUSD", "symbol_all_gates_pass": True}]).to_csv(stage_status_csv, index=False)
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
