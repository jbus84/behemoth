from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from scripts.validate_oco_docs_contract import CORE_METRIC_IDS, Thresholds, run


def _stage_doc_text() -> str:
    return """# Stage X\n\n## Objective\n\n## Inputs\n\n## Process\n\n## Exact Calculations\n\n## Causality / Leakage Controls\n\n## Failure Modes\n\n## Interpretation Guide\n\n## Validation Gates\n\n## Reproduction Commands\n\n## Traceability\n"""


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
    }
    for _, n in names.items():
        (root / n).write_text(_stage_doc_text(), encoding="utf-8")


def _mkdocs_text() -> str:
    paths = [
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
    return "\n".join(["nav:"] + [f"  - {p}" for p in paths])


def test_docs_contract_smoke_pass(tmp_path: Path) -> None:
    docs_root = tmp_path / "docs" / "strategy_bible"
    docs_root.mkdir(parents=True, exist_ok=True)
    generated_root = docs_root / "generated"
    generated_root.mkdir(parents=True, exist_ok=True)

    _write_stage_docs(docs_root)

    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    rows = [{"stage_id": 1, "symbol": "EURUSD", "metric_id": m, "metric_value": 1.0, "generated_at_utc": now} for m in sorted(CORE_METRIC_IDS)]
    edge_metrics = pd.DataFrame(rows)
    edge_metrics_csv = tmp_path / "edge_metrics.csv"
    edge_metrics.to_csv(edge_metrics_csv, index=False)

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

    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    rows = [{"stage_id": 1, "symbol": "EURUSD", "metric_id": "D16_spread_regime_shift_z", "metric_value": 1.0, "generated_at_utc": now}]
    edge_metrics = pd.DataFrame(rows)
    edge_metrics_csv = tmp_path / "edge_metrics.csv"
    edge_metrics.to_csv(edge_metrics_csv, index=False)

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
