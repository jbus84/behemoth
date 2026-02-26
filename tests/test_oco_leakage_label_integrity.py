from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd

from scripts.audit_oco_leakage_label_integrity import SymbolConfig, run_audit


def _sha(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def _build_minimal_bundle(tmp_path: Path, *, bad_time_order: bool = False) -> SymbolConfig:
    pred_path = tmp_path / "pred.parquet"
    metrics_path = tmp_path / "metrics.csv"
    thresholds_path = tmp_path / "thresholds.csv"
    events_path = tmp_path / "events.parquet"
    schedule_path = tmp_path / "schedule.csv"
    monthly_path = tmp_path / "monthly.csv"
    lock_path = tmp_path / "lock.json"

    pred = pd.DataFrame(
        [
            {
                "test_month": "2025-05",
                "close_ts": "2025-05-02T00:00:00Z",
                "candidate_uid": "oco|EURUSD|100|h6|state_a",
                "pred_prob": 0.8,
                "target_gross_pips": 1.2,
                "target_gross_pos": 1,
                "threshold_mode": "rolling_days",
                "threshold_days": 20,
                "threshold_exec": 0.6,
                "selected_exec": 1,
            },
            {
                "test_month": "2025-05",
                "close_ts": "2025-05-03T00:00:00Z",
                "candidate_uid": "oco|EURUSD|100|h6|state_b",
                "pred_prob": 0.7,
                "target_gross_pips": 0.6,
                "target_gross_pos": 1,
                "threshold_mode": "rolling_days",
                "threshold_days": 20,
                "threshold_exec": 0.55,
                "selected_exec": 1,
            },
        ]
    )
    pred.to_parquet(pred_path, index=False)

    metrics = pd.DataFrame(
        [
            {
                "test_month": "2025-05",
                "train_start": "2025-04-01",
                "train_end": "2025-05-01" if not bad_time_order else "2025-05-02",
                "test_start": "2025-05-01",
                "test_end": "2025-06-01",
            }
        ]
    )
    metrics.to_csv(metrics_path, index=False)
    thresholds = pd.DataFrame([{"test_month": "2025-05", "quantile": 0.9, "selected_rows": 2}])
    thresholds.to_csv(thresholds_path, index=False)

    events = pd.DataFrame(
        [
            {
                "close_ts": "2025-05-02T00:00:00Z",
                "candidate_uid": "oco|EURUSD|100|h6|state_a",
                "target_gross_pips": 1.2,
                "target_gross_pos": 1,
                "cost_est_pips": 0.8,
                "range_pips": 2.0,
                "ret1_pips": 0.1,
                "ret_z": 0.2,
                "ret_abs_z": 0.2,
                "vel_cost_units_h1": 0.3,
                "vel_abs_cost_units_h1": 0.3,
                "spread_z": 0.0,
                "tick_rate_z": 0.1,
                "hour_utc": 0,
                "hl_first": 1.0,
                "hl_first_mean_24": 0.1,
                "hl_pos_frac_mean_24": 0.5,
                "bar_ticks": 100,
                "horizon": 6,
                "barrier_pips": 2.0,
            },
            {
                "close_ts": "2025-05-03T00:00:00Z",
                "candidate_uid": "oco|EURUSD|100|h6|state_b",
                "target_gross_pips": 0.6,
                "target_gross_pos": 1,
                "cost_est_pips": 0.9,
                "range_pips": 2.1,
                "ret1_pips": 0.15,
                "ret_z": 0.25,
                "ret_abs_z": 0.25,
                "vel_cost_units_h1": 0.35,
                "vel_abs_cost_units_h1": 0.35,
                "spread_z": 0.0,
                "tick_rate_z": 0.1,
                "hour_utc": 0,
                "hl_first": 1.0,
                "hl_first_mean_24": 0.1,
                "hl_pos_frac_mean_24": 0.5,
                "bar_ticks": 100,
                "horizon": 6,
                "barrier_pips": 2.0,
            },
        ]
    )
    events.to_parquet(events_path, index=False)

    schedule = pd.DataFrame(
        [
            {
                "symbol": "EURUSD",
                "test_month": "2025-05",
                "train_months": "2025-04",
                "state_key": "state_a|100|6",
            }
        ]
    )
    schedule.to_csv(schedule_path, index=False)

    monthly = pd.DataFrame(
        [
            {"symbol": "EURUSD", "test_month": "2025-04", "status": "warmup_skip"},
            {"symbol": "EURUSD", "test_month": "2025-05", "status": "ok"},
        ]
    )
    monthly.to_csv(monthly_path, index=False)

    wfo_cfg = tmp_path / "wfo.yaml"
    red_cfg = tmp_path / "reduced.yaml"
    states = tmp_path / "states.csv"
    wfo_cfg.write_text("execution_quantile: 0.9\n", encoding="utf-8")
    red_cfg.write_text("locked_quantile: 0.9\n", encoding="utf-8")
    pd.DataFrame([{"symbol": "EURUSD", "bar_ticks": 100, "horizon": 6, "state_id": "state_a"}]).to_csv(states, index=False)

    lock = {
        "symbol": "EURUSD",
        "artifacts": {
            "wfo_config_path": str(wfo_cfg),
            "wfo_config_sha256": _sha(wfo_cfg),
            "reduced_config_path": str(red_cfg),
            "reduced_config_sha256": _sha(red_cfg),
            "reduced_states_csv_path": str(states),
            "reduced_states_csv_sha256": _sha(states),
        },
    }
    lock_path.write_text(json.dumps(lock), encoding="utf-8")

    return SymbolConfig(
        symbol="EURUSD",
        pred_path=pred_path,
        metrics_path=metrics_path,
        thresholds_path=thresholds_path,
        events_path=events_path,
        schedule_path=schedule_path,
        monthly_path=monthly_path,
        lock_path=lock_path,
        min_train_months=1,
        max_null_shift=0.2,
    )


def test_leakage_audit_passes_smoke(tmp_path: Path) -> None:
    cfg = _build_minimal_bundle(tmp_path, bad_time_order=False)
    checks_csv = tmp_path / "checks.csv"
    issues_csv = tmp_path / "issues.csv"
    report_md = tmp_path / "report.md"
    checks, issues = run_audit(
        ["EURUSD"],
        out_checks_csv=checks_csv,
        out_issues_csv=issues_csv,
        report_out=report_md,
        config_map={"EURUSD": cfg},
    )
    assert not checks.empty
    assert issues.empty
    assert (checks["status"].astype(str) == "pass").all()


def test_leakage_audit_flags_bad_time_order(tmp_path: Path) -> None:
    cfg = _build_minimal_bundle(tmp_path, bad_time_order=True)
    checks_csv = tmp_path / "checks.csv"
    issues_csv = tmp_path / "issues.csv"
    report_md = tmp_path / "report.md"
    checks, issues = run_audit(
        ["EURUSD"],
        out_checks_csv=checks_csv,
        out_issues_csv=issues_csv,
        report_out=report_md,
        config_map={"EURUSD": cfg},
    )
    assert not checks.empty
    l01 = checks[checks["check_id"] == "L01"].iloc[0]
    assert l01["status"] == "fail"
    assert not issues.empty
