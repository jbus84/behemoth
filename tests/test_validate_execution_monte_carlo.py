from __future__ import annotations

from pathlib import Path

import pandas as pd

from scripts.validate_execution_monte_carlo import run


def _rows_for_symbol(symbol: str) -> list[dict[str, object]]:
    return [
        {
            "symbol": symbol,
            "scenario_id": "S0_baseline",
            "mean_per_signal_pips": 1.0,
            "lb95_per_signal_pips": 0.9,
            "mean_fill_rate": 0.99,
            "prob_negative_month": 0.05,
            "fill_rate_drop_vs_S0": 0.0,
        },
        {
            "symbol": symbol,
            "scenario_id": "S1_mild",
            "mean_per_signal_pips": 0.8,
            "lb95_per_signal_pips": 0.3,
            "mean_fill_rate": 0.97,
            "prob_negative_month": 0.10,
            "fill_rate_drop_vs_S0": 0.02,
        },
        {
            "symbol": symbol,
            "scenario_id": "S2_moderate",
            "mean_per_signal_pips": 0.5,
            "lb95_per_signal_pips": 0.05,
            "mean_fill_rate": 0.95,
            "prob_negative_month": 0.15,
            "fill_rate_drop_vs_S0": 0.04,
        },
        {
            "symbol": symbol,
            "scenario_id": "S3_severe",
            "mean_per_signal_pips": 0.2,
            "lb95_per_signal_pips": -0.1,
            "mean_fill_rate": 0.90,
            "prob_negative_month": 0.25,
            "fill_rate_drop_vs_S0": 0.09,
        },
    ]


def test_execution_mc_validator_passes_happy_path(tmp_path: Path) -> None:
    csv = tmp_path / "execution_mc_symbol_scenarios.csv"
    rows = _rows_for_symbol("EURUSD") + _rows_for_symbol("GBPUSD") + _rows_for_symbol("USDJPY")
    pd.DataFrame(rows).to_csv(csv, index=False)

    checks, issues = run(
        symbol_scenarios_csv=csv,
        out_checks_csv=tmp_path / "checks.csv",
        out_issues_csv=tmp_path / "issues.csv",
        out_report_md=tmp_path / "report.md",
        symbols=["EURUSD", "GBPUSD", "USDJPY"],
    )

    assert not checks.empty
    assert issues.empty
    assert (checks["status"].astype(str) == "pass").all()


def test_execution_mc_validator_flags_missing_data(tmp_path: Path) -> None:
    csv = tmp_path / "execution_mc_symbol_scenarios.csv"
    rows = _rows_for_symbol("EURUSD")
    bad = pd.DataFrame(rows)
    bad.loc[bad["scenario_id"] == "S1_mild", "lb95_per_signal_pips"] = -0.2
    bad.to_csv(csv, index=False)

    checks, issues = run(
        symbol_scenarios_csv=csv,
        out_checks_csv=tmp_path / "checks.csv",
        out_issues_csv=tmp_path / "issues.csv",
        out_report_md=tmp_path / "report.md",
        symbols=["EURUSD", "GBPUSD", "USDJPY"],
    )

    em01 = checks[(checks["symbol"] == "EURUSD") & (checks["check_id"] == "EM01")]
    assert not em01.empty
    assert (em01["status"].astype(str) == "fail").all()
    assert not issues.empty
