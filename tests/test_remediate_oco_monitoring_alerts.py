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
        "max_amber_consecutive_runs": 3,
        "max_amber_months": 6,
        "require_owner": True,
        "require_rationale": True,
        "require_evidence_link": True,
        "hard_fail_on_expired_exception": True,
        "hard_fail_on_recurrence_breach": True,
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
        ftmo_alerts_csv=None,
        exceptions_yaml=exceptions_path,
        out_disposition_csv=tmp_path / "disposition.csv",
        report_out=tmp_path / "report.md",
    )
    assert not disposition.empty
    assert {
        "symbol",
        "metric_id",
        "status",
        "action_code",
        "is_expired",
        "consecutive_runs_non_green",
        "months_non_green_count",
        "escalation_level",
        "evidence_link",
        "policy_violation_code",
    }.issubset(set(disposition.columns))
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
    assert (disposition["escalation_level"].astype(str) == "warn").any()


def test_remediation_recurrence_increments_across_runs(tmp_path: Path) -> None:
    drift_path, threshold_path, exceptions_path = _write_alert_inputs(tmp_path)
    out_csv = tmp_path / "disposition.csv"
    report = tmp_path / "report.md"
    d1 = run(
        drift_alerts_csv=drift_path,
        threshold_alerts_csv=threshold_path,
        ftmo_alerts_csv=None,
        exceptions_yaml=exceptions_path,
        out_disposition_csv=out_csv,
        report_out=report,
    )
    prev = pd.read_csv(out_csv)
    prev["last_seen_utc"] = "2025-01-01T00:00:00Z"
    prev.to_csv(out_csv, index=False)
    d2 = run(
        drift_alerts_csv=drift_path,
        threshold_alerts_csv=threshold_path,
        ftmo_alerts_csv=None,
        exceptions_yaml=exceptions_path,
        out_disposition_csv=out_csv,
        report_out=report,
    )
    r1 = d1[d1["metric_id"].astype(str) == "E_DRIFT_OVERSHOOT_P95"].iloc[0]
    r2 = d2[d2["metric_id"].astype(str) == "E_DRIFT_OVERSHOOT_P95"].iloc[0]
    assert int(r2["consecutive_runs_non_green"]) >= int(r1["consecutive_runs_non_green"]) + 1


def test_remediation_accepted_exception_does_not_trigger_recurrence_breach(tmp_path: Path) -> None:
    drift_path, threshold_path, exceptions_path = _write_alert_inputs(tmp_path)
    out_csv = tmp_path / "disposition.csv"
    report = tmp_path / "report.md"
    run(
        drift_alerts_csv=drift_path,
        threshold_alerts_csv=threshold_path,
        ftmo_alerts_csv=None,
        exceptions_yaml=exceptions_path,
        out_disposition_csv=out_csv,
        report_out=report,
    )
    prev = pd.read_csv(out_csv)
    prev["last_seen_utc"] = "2025-01-01T00:00:00Z"
    prev.loc[
        prev["metric_id"].astype(str) == "E_DRIFT_OVERSHOOT_P95", "consecutive_runs_non_green"
    ] = 99
    prev.to_csv(out_csv, index=False)

    disposition = run(
        drift_alerts_csv=drift_path,
        threshold_alerts_csv=threshold_path,
        ftmo_alerts_csv=None,
        exceptions_yaml=exceptions_path,
        out_disposition_csv=out_csv,
        report_out=report,
    )
    row = disposition[disposition["metric_id"].astype(str) == "E_DRIFT_OVERSHOOT_P95"].iloc[0]
    assert row["status"] == "accepted_exception"
    assert bool(row["recurrence_breach"]) is False
    assert row["escalation_level"] == "warn"


def test_remediation_recurrence_only_applies_to_current_scope_month(tmp_path: Path) -> None:
    drift_path, threshold_path, exceptions_path = _write_alert_inputs(tmp_path)
    drift = pd.read_csv(drift_path)
    drift = pd.concat(
        [
            drift,
            pd.DataFrame(
                [
                    {
                        "symbol": "USDCHF",
                        "test_month": "2025-12",
                        "metric_id": "E_DRIFT_FILL_DROP",
                        "metric_value": 0.03,
                        "band": "amber",
                        "severity": "medium",
                        "source_path": "x",
                    },
                    {
                        "symbol": "USDCHF",
                        "test_month": "2026-02",
                        "metric_id": "E_DRIFT_FILL_DROP",
                        "metric_value": 0.0,
                        "band": "green",
                        "severity": "info",
                        "source_path": "x",
                    },
                ]
            ),
        ],
        ignore_index=True,
    )
    drift.to_csv(drift_path, index=False)
    out_csv = tmp_path / "disposition.csv"
    report = tmp_path / "report.md"
    disposition = run(
        drift_alerts_csv=drift_path,
        threshold_alerts_csv=threshold_path,
        ftmo_alerts_csv=None,
        exceptions_yaml=exceptions_path,
        out_disposition_csv=out_csv,
        report_out=report,
    )
    row = disposition[disposition["metric_id"].astype(str) == "E_DRIFT_FILL_DROP"].iloc[0]
    assert row["status"] == "remediated"
    assert bool(row["recurrence_breach"]) is False
    assert row["escalation_level"] == "warn"


def test_remediation_handles_empty_alerts(tmp_path: Path) -> None:
    disposition = run(
        drift_alerts_csv=tmp_path / "missing_drift.csv",
        threshold_alerts_csv=tmp_path / "missing_threshold.csv",
        ftmo_alerts_csv=tmp_path / "missing_ftmo.csv",
        exceptions_yaml=tmp_path / "missing_exceptions.yaml",
        out_disposition_csv=tmp_path / "disposition.csv",
        report_out=tmp_path / "report.md",
    )
    assert disposition.empty
    assert (tmp_path / "disposition.csv").exists()
    assert (tmp_path / "report.md").exists()


def test_remediation_includes_ftmo_alerts_source(tmp_path: Path) -> None:
    drift_path, threshold_path, exceptions_path = _write_alert_inputs(tmp_path)
    ftmo = pd.DataFrame(
        [
            {
                "source_alert": "ftmo_allocator",
                "symbol": "USDCHF",
                "test_month": "2026-02",
                "metric_id": "FTMO_ALLOC_STALE_PENDING_COUNT",
                "metric_value": 2.0,
                "band": "amber",
                "severity": "medium",
                "source_path": "runtime.db",
            }
        ]
    )
    ftmo_path = tmp_path / "ftmo_alerts.csv"
    ftmo.to_csv(ftmo_path, index=False)

    disposition = run(
        drift_alerts_csv=drift_path,
        threshold_alerts_csv=threshold_path,
        ftmo_alerts_csv=ftmo_path,
        exceptions_yaml=exceptions_path,
        out_disposition_csv=tmp_path / "disposition.csv",
        report_out=tmp_path / "report.md",
    )
    row = disposition[disposition["metric_id"].astype(str) == "FTMO_ALLOC_STALE_PENDING_COUNT"]
    assert not row.empty
    assert row.iloc[0]["source_alert"] == "ftmo_allocator"
