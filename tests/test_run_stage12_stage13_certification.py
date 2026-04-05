from __future__ import annotations

from pathlib import Path

import pandas as pd

from scripts.run_stage12_stage13_certification import run_stage12_stage13_certification


def test_orchestrator_skips_stage13_when_stage12_fails(tmp_path: Path) -> None:
    result = run_stage12_stage13_certification(
        symbols=["EURUSD"],
        stage12_runner=lambda symbol: {"certification_outcome": "FAIL", "go_decision": "NO_GO"},
        stage13_runner=lambda symbol: (_ for _ in ()).throw(AssertionError("should not run")),
        out_dir=tmp_path,
    )

    assert result[0]["symbol"] == "EURUSD"
    assert result[0]["stage12_certification_outcome"] == "FAIL"
    assert result[0]["stage13_attempted"] is False
    assert result[0]["certification_outcome"] == "FAIL"
    assert result[0]["go_decision"] == "NO_GO"
    summary = pd.read_csv(tmp_path / "stage12_stage13_certification_summary.csv")
    assert summary.loc[0, "certification_outcome"] == "FAIL"
    assert summary.loc[0, "go_decision"] == "NO_GO"


def test_orchestrator_resolves_final_outputs_without_unknown(tmp_path: Path) -> None:
    result = run_stage12_stage13_certification(
        symbols=["GBPUSD"],
        stage12_runner=lambda symbol: {"certification_outcome": "PASS", "go_decision": "GO"},
        stage13_runner=lambda symbol: {"certification_outcome": "PASS", "go_decision": "NO_GO"},
        out_dir=tmp_path,
    )

    row = result[0]
    assert row["certification_outcome"] in {"PASS", "FAIL"}
    assert row["go_decision"] in {"GO", "NO_GO"}
    assert row["go_decision"] == "NO_GO"
    summary = pd.read_csv(tmp_path / "stage12_stage13_certification_summary.csv")
    assert summary.loc[0, "certification_outcome"] == "PASS"
    assert summary.loc[0, "go_decision"] == "NO_GO"
