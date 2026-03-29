from __future__ import annotations

from pathlib import Path

import pandas as pd

from scripts.audit_oco_pipeline_logical_issues import SymbolConfig, audit_symbol, run_audit


def _uid(state: str, i: int) -> str:
    return f"oco|EURUSD|100|h5|{state}_{i}"


def _build_fixture(tmp_path: Path) -> SymbolConfig:
    pred_rows: list[dict] = []
    detail_rows: list[dict] = []

    months = ["2025-04", "2025-05", "2025-06", "2025-07"]
    fills = {
        "state_a": {
            "2025-04": [1, 0, 0],
            "2025-05": [1, 1, 0],
            "2025-06": [1, 1, 1],
            "2025-07": [1, 1, 0],
        },
        "state_b": {
            "2025-04": [1, 1, 1],
            "2025-05": [1, 1, 0],
            "2025-06": [1, 0, 0],
            "2025-07": [1, 0, 0],
        },
    }
    for month in months:
        for state in ["state_a", "state_b"]:
            for i in range(3):
                ts = pd.Timestamp(f"{month}-01 00:{i:02d}:00+00:00")
                uid = _uid(state, i)
                pred_rows.append(
                    {
                        "test_month": month,
                        "close_ts": ts,
                        "candidate_uid": uid,
                        "pred_prob": 0.95,
                        "target_gross_pips": 2.0,
                        "threshold_mode": "rolling",
                        "threshold_days": 20,
                        "threshold_exec": 0.90,
                        "selected_exec": 1,
                    }
                )
                is_fill = fills[state][month][i] == 1
                detail_rows.append(
                    {
                        "close_ts": ts,
                        "candidate_uid": uid,
                        "touch_open_ts": ts + pd.Timedelta(minutes=1),
                        "touch_close_ts": ts + pd.Timedelta(minutes=2),
                        "touch_month": ts.strftime("%Y%m"),
                        "touch_found_tick": 1,
                        "overshoot_tick_pips": 0.2 if is_fill else 2.0,
                    }
                )

    pred_path = tmp_path / "pred.parquet"
    pd.DataFrame(pred_rows).to_parquet(pred_path, index=False)

    detail_path = tmp_path / "detail.csv"
    pd.DataFrame(detail_rows).to_csv(detail_path, index=False)

    monthly = pd.DataFrame(
        [
            {
                "symbol": "EURUSD",
                "test_month": "2025-04",
                "train_months": "",
                "states_selected": 0,
                "rows": 0,
                "signal_rows": 0,
                "fill_rate": None,
                "mean_gross_pips": None,
                "mean_signal_pips": None,
                "median_gross_pips": None,
                "pos_rate": None,
                "status": "warmup_skip",
            },
            {
                "symbol": "EURUSD",
                "test_month": "2025-05",
                "train_months": "2025-04",
                "states_selected": 0,
                "rows": 0,
                "signal_rows": 0,
                "fill_rate": None,
                "mean_gross_pips": None,
                "mean_signal_pips": None,
                "median_gross_pips": None,
                "pos_rate": None,
                "status": "warmup_skip",
            },
            {
                "symbol": "EURUSD",
                "test_month": "2025-06",
                "train_months": "2025-04,2025-05",
                "states_selected": 0,
                "rows": 0,
                "signal_rows": 0,
                "fill_rate": None,
                "mean_gross_pips": None,
                "mean_signal_pips": None,
                "median_gross_pips": None,
                "pos_rate": None,
                "status": "warmup_skip",
            },
            {
                "symbol": "EURUSD",
                "test_month": "2025-07",
                "train_months": "2025-04,2025-05,2025-06",
                "states_selected": 2,
                "rows": 12,
                "signal_rows": 18,
                "fill_rate": 12 / 18,
                "mean_gross_pips": 1.8,
                "mean_signal_pips": 1.2,
                "median_gross_pips": 1.8,
                "pos_rate": 0.60,
                "status": "ok",
            },
        ]
    )
    monthly_path = tmp_path / "monthly.csv"
    monthly.to_csv(monthly_path, index=False)

    summary = pd.DataFrame(
        [
            {
                "symbol": "EURUSD",
                "rows_total": 12,
                "signal_rows_total": 18,
                "fill_rate_overall": 12 / 18,
                "lb95_month_mean_gross_pips": 1.8,
                "lb95_month_mean_signal_pips": 1.2,
            }
        ]
    )
    summary_path = tmp_path / "summary.csv"
    summary.to_csv(summary_path, index=False)

    schedule = pd.DataFrame(
        [
            {
                "symbol": "EURUSD",
                "test_month": "2025-07",
                "state_id": "state_a_0",
                "gate_pass": True,
            },
            {
                "symbol": "EURUSD",
                "test_month": "2025-07",
                "state_id": "state_b_0",
                "gate_pass": False,
            },
        ]
    )
    schedule_path = tmp_path / "schedule.csv"
    schedule.to_csv(schedule_path, index=False)

    caps = pd.DataFrame(
        [
            {"symbol": "EURUSD", "cap_pips": 0.8, "fill_rate": 0.95},
            {"symbol": "EURUSD", "cap_pips": 1.2, "fill_rate": 0.90},
        ]
    )
    caps_path = tmp_path / "caps.csv"
    caps.to_csv(caps_path, index=False)

    return SymbolConfig(
        symbol="EURUSD",
        pred_path=pred_path,
        monthly_path=monthly_path,
        summary_path=summary_path,
        schedule_path=schedule_path,
        stop_detail_path=detail_path,
        stop_caps_path=caps_path,
    )


def test_audit_symbol_flags_expected_failures(tmp_path: Path):
    cfg = _build_fixture(tmp_path)
    checks, issues = audit_symbol(cfg)

    by_id = {r["check_id"]: r["status"] for _, r in checks.iterrows()}
    assert by_id["C03"] == "fail"
    assert by_id["C06"] == "fail"
    assert by_id["C01"] == "pass"
    assert by_id["C02"] == "pass"
    assert by_id["C07"] == "pass"
    assert by_id["C08"] == "pass"
    assert by_id["C09"] == "pass"
    assert "EURUSD_C03" in set(issues["issue_id"].astype(str))
    assert "EURUSD_C06" in set(issues["issue_id"].astype(str))


def test_run_audit_writes_outputs(tmp_path: Path, monkeypatch):
    cfg = _build_fixture(tmp_path)
    monkeypatch.setattr(
        "scripts.audit_oco_pipeline_logical_issues._default_configs",
        lambda base_dir=None: {"EURUSD": cfg},
    )
    out_checks = tmp_path / "checks.csv"
    out_issues = tmp_path / "issues.csv"
    out_report = tmp_path / "report.md"
    checks, issues = run_audit(
        ["EURUSD"],
        base_dir=tmp_path,
        out_checks_csv=out_checks,
        out_issues_csv=out_issues,
        report_out=out_report,
    )
    assert len(checks) == 10
    assert len(issues) >= 2
    assert out_checks.exists()
    assert out_issues.exists()
    assert out_report.exists()


def test_default_configs_includes_all_symbols() -> None:
    from scripts.audit_oco_pipeline_logical_issues import _default_configs

    configs = _default_configs()
    assert set(configs.keys()) == {"EURUSD", "GBPUSD", "USDJPY", "USDCHF", "AUDUSD", "USDCAD"}
    assert "reduced_core_rolling/EURUSD" in str(configs["EURUSD"].monthly_path.as_posix())
    assert "reduced_core_rolling/USDCAD" in str(configs["USDCAD"].monthly_path.as_posix())
