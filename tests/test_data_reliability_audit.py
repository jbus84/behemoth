from __future__ import annotations

from pathlib import Path

import pandas as pd

from scripts.audit_data_reliability import Thresholds, run


def _build_frame(n: int = 400) -> pd.DataFrame:
    ts = pd.date_range("2025-01-01", periods=n, freq="15min", tz="UTC")
    base = 1.10 + (pd.Series(range(n), dtype=float) * 1e-5)
    d = pd.DataFrame(
        {
            "close_ts": ts,
            "open": base,
            "high": base + 0.0002,
            "low": base - 0.0002,
            "close": base + 0.0001,
            "cost_est_pips": 0.8,
            "range_pips": 2.0,
            "hour_utc": ts.hour,
            "spread_z": 0.0,
            "tick_rate_z": 0.0,
            "vel_cost_units_h1": 0.2,
            "hl_first": 1.0,
            "ret1_pips": 0.2,
        }
    )
    return d


def test_data_reliability_audit_passes_smoke(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "data" / "analysis" / "tick_opportunity_mining" / "wfo_test"
    root.mkdir(parents=True, exist_ok=True)
    p = root / "EURUSD_oco_events_eval2025.parquet"
    _build_frame().to_parquet(p, index=False)

    checks_csv = tmp_path / "checks.csv"
    issues_csv = tmp_path / "issues.csv"
    report_md = tmp_path / "report.md"
    monkeypatch.chdir(tmp_path)
    checks, issues = run(
        symbols=["EURUSD"],
        source_pattern="data/analysis/tick_opportunity_mining/wfo_*/*{symbol}_oco_events_eval*.parquet",
        thresholds=Thresholds(min_rows=100, min_trading_days=1),
        out_checks_csv=checks_csv,
        out_issues_csv=issues_csv,
        out_report_md=report_md,
    )
    assert not checks.empty
    assert issues.empty
    assert (checks["status"].astype(str) == "pass").all()


def test_data_reliability_audit_flags_failures(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "data" / "analysis" / "tick_opportunity_mining" / "wfo_test"
    root.mkdir(parents=True, exist_ok=True)
    p = root / "EURUSD_oco_events_eval2025.parquet"
    d = _build_frame()
    d.loc[0:10, "close_ts"] = d.loc[0, "close_ts"]  # duplicates
    d.loc[5:8, "cost_est_pips"] = -1.0  # invalid costs
    d.to_parquet(p, index=False)

    checks_csv = tmp_path / "checks.csv"
    issues_csv = tmp_path / "issues.csv"
    report_md = tmp_path / "report.md"
    monkeypatch.chdir(tmp_path)
    checks, issues = run(
        symbols=["EURUSD"],
        source_pattern="data/analysis/tick_opportunity_mining/wfo_*/*{symbol}_oco_events_eval*.parquet",
        thresholds=Thresholds(min_rows=100, min_trading_days=1, max_duplicate_close_ts_rate=0.0, max_nonneg_violation_rate=0.0),
        out_checks_csv=checks_csv,
        out_issues_csv=issues_csv,
        out_report_md=report_md,
    )
    assert not checks.empty
    assert not issues.empty
    fail_ids = set(checks.loc[checks["status"].astype(str) != "pass", "check_id"].astype(str).tolist())
    assert "DR05" in fail_ids
    assert "DR09" in fail_ids
