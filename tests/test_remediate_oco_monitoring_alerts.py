from __future__ import annotations

from pathlib import Path

import pandas as pd
import yaml

from scripts.remediate_oco_monitoring_alerts import run


def _write_alert_inputs(tmp_path: Path) -> tuple[Path, Path, Path]:
    drift = pd.DataFrame(
        [
            {
                "symbol": "EURUSD",
                "test_month": "2025-12",
                "metric_id": "E_DRIFT_OVERSHOOT_P95",
                "metric_value": 0.12,
                "band": "amber",
                "severity": "medium",
                "source_path": "x",
            },
            {
                "symbol": "EURUSD",
                "test_month": "2025-12",
                "metric_id": "E_DRIFT_OVERSHOOT_P50",
                "metric_value": 0.02,
                "band": "green",
                "severity": "info",
                "source_path": "x",
            },
        ]
    )
    threshold = pd.DataFrame(
        [
            {
                "symbol": "GBPUSD",
                "test_month": "",
                "metric_id": "TS03_LB95_MONTH_SIGNAL",
                "metric_value": 0.4,
                "band": "amber",
                "severity": "medium",
                "source_path": "y",
            }
        ]
    )
    exceptions = {
        "version": 1,
        "default_expiry_days": 60,
        "rules": [
            {
                "metric_id": "E_DRIFT_OVERSHOOT_P95",
                "symbols": ["EURUSD"],
                "disposition": "accepted_exception",
                "owner": "execution_research",
                "rationale": "approved",
                "review_cadence_days": 30,
            }
        ],
    }
    drift_path = tmp_path / "drift.csv"
    threshold_path = tmp_path / "threshold.csv"
    exceptions_path = tmp_path / "exceptions.yaml"
    drift.to_csv(drift_path, index=False)
    threshold.to_csv(threshold_path, index=False)
    exceptions_path.write_text(yaml.safe_dump(exceptions, sort_keys=False), encoding="utf-8")
    return drift_path, threshold_path, exceptions_path


def test_remediation_outputs_dispositions(tmp_path: Path) -> None:
    drift_path, threshold_path, exceptions_path = _write_alert_inputs(tmp_path)
    disposition = run(
        drift_alerts_csv=drift_path,
        threshold_alerts_csv=threshold_path,
        exceptions_yaml=exceptions_path,
        out_disposition_csv=tmp_path / "disposition.csv",
        report_out=tmp_path / "report.md",
    )
    assert not disposition.empty
    assert {"symbol", "metric_id", "status", "action_code", "is_expired"}.issubset(set(disposition.columns))
    # green alert is filtered out
    assert "E_DRIFT_OVERSHOOT_P50" not in set(disposition["metric_id"].astype(str))
    # exception-matched alert stays accepted
    eur = disposition[disposition["metric_id"].astype(str) == "E_DRIFT_OVERSHOOT_P95"]
    assert not eur.empty
    assert eur.iloc[0]["status"] == "accepted_exception"
    # unmatched alert is remediation-required
    gbp = disposition[disposition["metric_id"].astype(str) == "TS03_LB95_MONTH_SIGNAL"]
    assert not gbp.empty
    assert gbp.iloc[0]["status"] == "remediated"


def test_remediation_handles_empty_alerts(tmp_path: Path) -> None:
    disposition = run(
        drift_alerts_csv=tmp_path / "missing_drift.csv",
        threshold_alerts_csv=tmp_path / "missing_threshold.csv",
        exceptions_yaml=tmp_path / "missing_exceptions.yaml",
        out_disposition_csv=tmp_path / "disposition.csv",
        report_out=tmp_path / "report.md",
    )
    assert disposition.empty
    assert (tmp_path / "disposition.csv").exists()
    assert (tmp_path / "report.md").exists()
