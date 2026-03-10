from __future__ import annotations

from pathlib import Path

import pandas as pd
import yaml

from scripts.build_oco_governance_explainability_report import run


def _write_inputs(tmp_path: Path) -> tuple[Path, Path]:
    disp = pd.DataFrame(
        [
            {
                "symbol": "EURUSD",
                "source_alert": "execution_drift",
                "test_month": "2025-12",
                "metric_id": "E_DRIFT_OVERSHOOT_P95",
                "metric_value": 0.11,
                "band": "amber",
                "severity": "medium",
                "status": "accepted_exception",
                "action_code": "A2_SESSION_GUARD",
                "owner": "execution_research",
                "rationale": "approved",
                "expires_utc": "2099-01-01T00:00:00Z",
                "is_expired": False,
                "source_path": "x",
                "evaluated_at_utc": "2026-01-01T00:00:00Z",
                "first_seen_utc": "2026-01-01T00:00:00Z",
                "last_seen_utc": "2026-01-01T00:00:00Z",
                "consecutive_runs_non_green": 2,
                "months_non_green_count": 2,
                "sla_days": 30,
                "days_to_expiry": 29.0,
                "escalation_level": "warn",
                "evidence_required": True,
                "evidence_link": "docs/analysis/oco_execution_drift_report.md",
                "expiry_breach": False,
                "recurrence_breach": False,
                "policy_violation_code": "",
            }
        ]
    )
    cfg = {
        "version": 1,
        "default_expiry_days": 60,
        "rules": [
            {
                "metric_id": "E_DRIFT_OVERSHOOT_P95",
                "symbols": ["EURUSD"],
                "review_cadence_days": 30,
            }
        ],
    }
    disp_path = tmp_path / "disposition.csv"
    cfg_path = tmp_path / "exceptions.yaml"
    disp.to_csv(disp_path, index=False)
    cfg_path.write_text(yaml.safe_dump(cfg, sort_keys=False), encoding="utf-8")
    return disp_path, cfg_path


def test_governance_explainability_outputs(tmp_path: Path) -> None:
    disp_path, cfg_path = _write_inputs(tmp_path)
    out = run(
        disposition_csv=disp_path,
        exceptions_yaml=cfg_path,
        out_csv=tmp_path / "explain.csv",
        report_out=tmp_path / "report.md",
    )
    assert not out.empty
    assert {
        "metric_id",
        "definition",
        "risk_path",
        "action_rationale",
        "expected_recovery_signal",
        "owners",
        "coverage_status",
    }.issubset(set(out.columns))
    assert "E_DRIFT_OVERSHOOT_P95" in set(out["metric_id"].astype(str))
    assert (tmp_path / "report.md").exists()


def test_governance_explainability_handles_empty(tmp_path: Path) -> None:
    out = run(
        disposition_csv=tmp_path / "missing.csv",
        exceptions_yaml=tmp_path / "missing.yaml",
        out_csv=tmp_path / "explain.csv",
        report_out=tmp_path / "report.md",
    )
    assert out.empty
    assert (tmp_path / "explain.csv").exists()
    assert (tmp_path / "report.md").exists()


def test_governance_explainability_handles_blank_source_alert(tmp_path: Path) -> None:
    disp = pd.DataFrame(
        [
            {
                "symbol": "EURUSD",
                "source_alert": "",
                "test_month": "2026-02",
                "metric_id": "FTMO_ALLOC_BLOCK_RATE",
                "metric_value": 0.4,
                "band": "amber",
                "severity": "medium",
                "status": "remediated",
                "action_code": "A1_REVIEW",
                "owner": "risk",
                "rationale": "monitor",
                "expires_utc": "2099-01-01T00:00:00Z",
                "is_expired": False,
                "source_path": "x",
                "evaluated_at_utc": "2026-02-01T00:00:00Z",
                "first_seen_utc": "2026-02-01T00:00:00Z",
                "last_seen_utc": "2026-02-01T00:00:00Z",
                "consecutive_runs_non_green": 1,
                "months_non_green_count": 1,
                "sla_days": 30,
                "days_to_expiry": 29.0,
                "escalation_level": "warn",
                "evidence_required": False,
                "evidence_link": "",
                "expiry_breach": False,
                "recurrence_breach": False,
                "policy_violation_code": "",
            }
        ]
    )
    disp_path = tmp_path / "disp.csv"
    disp.to_csv(disp_path, index=False)
    cfg_path = tmp_path / "exceptions.yaml"
    cfg_path.write_text("version: 1\n", encoding="utf-8")
    out = run(
        disposition_csv=disp_path,
        exceptions_yaml=cfg_path,
        out_csv=tmp_path / "explain.csv",
        report_out=tmp_path / "report.md",
    )
    assert not out.empty
    assert out.iloc[0]["source_alert"] == "unknown"
