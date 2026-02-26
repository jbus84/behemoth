from __future__ import annotations

from pathlib import Path

import pandas as pd

from scripts.audit_oco_execution_risk_prelive import SymbolConfig, run_audit


def _write_bundle(tmp_path: Path, *, bad_join: bool = False, bad_tail: bool = False, bad_viability: bool = False) -> SymbolConfig:
    pred = pd.DataFrame(
        [
            {
                "test_month": "2025-05",
                "close_ts": "2025-05-01T00:00:00Z",
                "candidate_uid": "oco|EURUSD|100|h6|s1",
                "target_gross_pips": 1.0,
                "selected_exec": 1,
            },
            {
                "test_month": "2025-05",
                "close_ts": "2025-05-01T08:01:00Z",
                "candidate_uid": "oco|EURUSD|100|h6|s2",
                "target_gross_pips": 1.2,
                "selected_exec": 1,
            },
            {
                "test_month": "2025-06",
                "close_ts": "2025-06-01T13:00:00Z",
                "candidate_uid": "oco|EURUSD|100|h6|s1",
                "target_gross_pips": 0.9 if not bad_viability else -1.2,
                "selected_exec": 1,
            },
            {
                "test_month": "2025-06",
                "close_ts": "2025-06-01T18:01:00Z",
                "candidate_uid": "oco|EURUSD|100|h6|s2",
                "target_gross_pips": 1.1 if not bad_viability else -1.0,
                "selected_exec": 1,
            },
        ]
    )
    pred_path = tmp_path / "pred.parquet"
    pred.to_parquet(pred_path, index=False)

    monthly = pd.DataFrame(
        [
            {"symbol": "EURUSD", "test_month": "2025-04", "status": "warmup_skip"},
            {"symbol": "EURUSD", "test_month": "2025-05", "status": "ok"},
            {"symbol": "EURUSD", "test_month": "2025-06", "status": "ok"},
        ]
    )
    monthly_path = tmp_path / "monthly.csv"
    monthly.to_csv(monthly_path, index=False)

    detail = pd.DataFrame(
        [
            {
                "close_ts": "2025-05-01T00:00:00Z",
                "candidate_uid": "oco|EURUSD|100|h6|s1",
                "target_gross_pips": 1.0,
                "touch_open_ts": "2025-05-01T00:00:02Z",
                "touch_close_ts": "2025-05-01T00:00:10Z",
                "touch_found_tick": 1,
                "overshoot_tick_pips": 0.1 if not bad_tail else 2.0,
            },
            {
                "close_ts": "2025-05-01T08:01:00Z",
                "candidate_uid": "oco|EURUSD|100|h6|s2",
                "target_gross_pips": 1.2,
                "touch_open_ts": "2025-05-01T00:01:02Z",
                "touch_close_ts": "2025-05-01T00:01:08Z",
                "touch_found_tick": 1,
                "overshoot_tick_pips": 0.1 if not bad_tail else 2.0,
            },
            {
                "close_ts": "2025-06-01T13:00:00Z",
                "candidate_uid": "oco|EURUSD|100|h6|s1",
                "target_gross_pips": 0.9 if not bad_viability else -1.2,
                "touch_open_ts": "2025-06-01T00:00:02Z",
                "touch_close_ts": "2025-06-01T00:00:06Z",
                "touch_found_tick": 1,
                "overshoot_tick_pips": 0.1,
            },
            {
                "close_ts": "2025-06-01T18:01:00Z",
                "candidate_uid": "oco|EURUSD|100|h6|s2",
                "target_gross_pips": 1.1 if not bad_viability else -1.0,
                "touch_open_ts": "2025-06-01T00:01:02Z",
                "touch_close_ts": "2025-06-01T00:01:06Z",
                "touch_found_tick": 1,
                "overshoot_tick_pips": 0.1,
            },
        ]
    )
    if bad_join:
        detail = detail.iloc[:-1].copy()
    detail_path = tmp_path / "detail.csv"
    detail.to_csv(detail_path, index=False)

    caps = pd.DataFrame(
        [
            {"symbol": "EURUSD", "cap_pips": 0.8, "fill_rate": 0.95, "mean_per_signal_full_overshoot": 0.8},
            {"symbol": "EURUSD", "cap_pips": 1.0, "fill_rate": 0.97, "mean_per_signal_full_overshoot": 0.85},
            {"symbol": "EURUSD", "cap_pips": 1.2, "fill_rate": 0.98, "mean_per_signal_full_overshoot": 0.87},
            {"symbol": "EURUSD", "cap_pips": 1.5, "fill_rate": 0.99, "mean_per_signal_full_overshoot": 0.88},
        ]
    )
    caps_path = tmp_path / "caps.csv"
    caps.to_csv(caps_path, index=False)

    return SymbolConfig(
        symbol="EURUSD",
        pred_path=pred_path,
        monthly_path=monthly_path,
        detail_path=detail_path,
        caps_path=caps_path,
        min_state_rows=1,
        min_total_rows_for_viability=1,
    )


def test_execution_risk_smoke_pass(tmp_path: Path) -> None:
    cfg = _write_bundle(tmp_path)
    checks, issues = run_audit(
        ["EURUSD"],
        out_checks_csv=tmp_path / "checks.csv",
        out_issues_csv=tmp_path / "issues.csv",
        report_out=tmp_path / "report.md",
        config_map={"EURUSD": cfg},
    )
    assert not checks.empty
    assert issues.empty
    assert (checks["status"].astype(str) == "pass").all()


def test_execution_risk_flags_join_fail(tmp_path: Path) -> None:
    cfg = _write_bundle(tmp_path, bad_join=True)
    checks, issues = run_audit(
        ["EURUSD"],
        out_checks_csv=tmp_path / "checks.csv",
        out_issues_csv=tmp_path / "issues.csv",
        report_out=tmp_path / "report.md",
        config_map={"EURUSD": cfg},
    )
    e01 = checks[checks["check_id"] == "E01"].iloc[0]
    assert e01["status"] == "fail"
    assert not issues.empty


def test_execution_risk_flags_tail_fail(tmp_path: Path) -> None:
    cfg = _write_bundle(tmp_path, bad_tail=True)
    checks, _ = run_audit(
        ["EURUSD"],
        out_checks_csv=tmp_path / "checks.csv",
        out_issues_csv=tmp_path / "issues.csv",
        report_out=tmp_path / "report.md",
        config_map={"EURUSD": cfg},
    )
    e03 = checks[checks["check_id"] == "E03"].iloc[0]
    assert e03["status"] == "fail"


def test_execution_risk_flags_net_viability_fail(tmp_path: Path) -> None:
    cfg = _write_bundle(tmp_path, bad_viability=True)
    checks, _ = run_audit(
        ["EURUSD"],
        out_checks_csv=tmp_path / "checks.csv",
        out_issues_csv=tmp_path / "issues.csv",
        report_out=tmp_path / "report.md",
        config_map={"EURUSD": cfg},
    )
    e10 = checks[checks["check_id"] == "E10"].iloc[0]
    assert e10["status"] == "fail"
