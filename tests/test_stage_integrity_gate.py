from __future__ import annotations

from pathlib import Path

from scripts.check_oco_docs_stage_integrity import STAGE_DOCS, run


def _stage_text(stage_id: int, *, with_markers: bool = True) -> str:
    marker = ""
    if with_markers:
        marker = (
            f"\n<!-- GENERATED:STAGE_{stage_id:02d}:START -->\n"
            "#### Key Results\n"
            "| k | v |\n"
            "| --- | --- |\n"
            "| a | 1 |\n"
            "\n#### Interpretation Notes\n"
            "- note\n"
            "\n#### Action Trigger Summary\n"
            "| trigger | action |\n"
            "| --- | --- |\n"
            "| x | y |\n"
            "\n#### Plots\n"
            "![fig](../figures/oco_bible/fig.png)\n"
            f"<!-- GENERATED:STAGE_{stage_id:02d}:END -->\n"
        )
    return (
        f"# Stage {stage_id}\n\n"
        "## Objective\n"
        "## Inputs\n"
        "## Process\n"
        "## Exact Calculations\n"
        "## Causality / Leakage Controls\n"
        "## Failure Modes\n"
        "## Interpretation Guide\n"
        "## Validation Gates\n"
        "## Operator Decision Tree\n"
        "## How To Run\n"
        "## How To Interpret Outputs\n"
        "## What To Do If It Fails\n"
        "## Canonical Analysis Reports\n"
        "- `docs/analysis/example_report.md`\n"
        "## Reproduction Commands\n"
        "## Traceability\n"
        + marker
    )


def test_stage_integrity_smoke_pass(tmp_path: Path) -> None:
    docs_root = tmp_path / "docs" / "strategy_bible"
    docs_root.mkdir(parents=True, exist_ok=True)
    for stage_id, name in STAGE_DOCS.items():
        (docs_root / name).write_text(_stage_text(stage_id, with_markers=True), encoding="utf-8")

    checks, issues = run(
        docs_root=docs_root,
        out_checks_csv=tmp_path / "checks.csv",
        out_issues_csv=tmp_path / "issues.csv",
        out_report_md=tmp_path / "report.md",
    )
    assert not checks.empty
    assert issues.empty
    assert (checks["status"].astype(str) == "pass").all()


def test_stage_integrity_flags_missing_generated_markers(tmp_path: Path) -> None:
    docs_root = tmp_path / "docs" / "strategy_bible"
    docs_root.mkdir(parents=True, exist_ok=True)
    for stage_id, name in STAGE_DOCS.items():
        txt = _stage_text(stage_id, with_markers=(stage_id != 3))
        (docs_root / name).write_text(txt, encoding="utf-8")

    checks, _issues = run(
        docs_root=docs_root,
        out_checks_csv=tmp_path / "checks.csv",
        out_issues_csv=tmp_path / "issues.csv",
        out_report_md=tmp_path / "report.md",
    )
    c = checks[checks["check_id"].astype(str) == "SI02_03"]
    assert not c.empty
    assert c.iloc[0]["status"] == "fail"
