#!/usr/bin/env python3
"""Validate execution Monte Carlo artifacts with EM01..EM05 checks."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


def _table(df: pd.DataFrame) -> str:
    if df.empty:
        return "_empty_"
    try:
        return df.to_markdown(index=False)
    except Exception:
        return "```\n" + df.to_string(index=False) + "\n```"


def _parse_symbols(raw: str) -> list[str]:
    return [x.strip().upper() for x in str(raw).split(",") if x.strip()]


def _add_check(
    rows: list[dict[str, Any]],
    *,
    symbol: str,
    check_id: str,
    check_name: str,
    passed: bool,
    severity_if_fail: str,
    metric_name: str,
    metric_value: Any,
    threshold: Any,
    comparator: str,
    details: dict[str, Any] | None = None,
) -> None:
    rows.append(
        {
            "symbol": symbol,
            "check_id": check_id,
            "check_name": check_name,
            "status": "pass" if bool(passed) else "fail",
            "severity_if_fail": str(severity_if_fail).lower(),
            "component": "execution_monte_carlo",
            "metric_name": str(metric_name),
            "metric_value": metric_value,
            "threshold": threshold,
            "comparator": str(comparator),
            "details_json": json.dumps(details or {}, sort_keys=True),
            "evaluated_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
    )


def run(
    *,
    symbol_scenarios_csv: Path,
    out_checks_csv: Path,
    out_issues_csv: Path,
    out_report_md: Path,
    symbols: list[str],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    s = pd.read_csv(symbol_scenarios_csv) if symbol_scenarios_csv.exists() else pd.DataFrame()
    if not s.empty and "symbol" in s.columns:
        s["symbol"] = s["symbol"].astype(str).str.upper()
    checks_rows: list[dict[str, Any]] = []

    core_cols = [
        "symbol",
        "scenario_id",
        "mean_per_signal_pips",
        "lb95_per_signal_pips",
        "mean_fill_rate",
        "prob_negative_month",
        "fill_rate_drop_vs_S0",
    ]

    for sym in symbols:
        x = (
            s[s.get("symbol", pd.Series(dtype=str)).astype(str) == sym].copy()
            if not s.empty
            else pd.DataFrame()
        )
        s1 = x[x.get("scenario_id", pd.Series(dtype=str)).astype(str) == "S1_mild"].copy()
        s2 = x[x.get("scenario_id", pd.Series(dtype=str)).astype(str) == "S2_moderate"].copy()

        lb95_s1 = (
            float(pd.to_numeric(s1.get("lb95_per_signal_pips"), errors="coerce").iloc[0])
            if not s1.empty
            else float("nan")
        )
        lb95_s2 = (
            float(pd.to_numeric(s2.get("lb95_per_signal_pips"), errors="coerce").iloc[0])
            if not s2.empty
            else float("nan")
        )
        pneg_s1 = (
            float(pd.to_numeric(s1.get("prob_negative_month"), errors="coerce").iloc[0])
            if not s1.empty
            else float("nan")
        )
        drop_s1 = (
            float(pd.to_numeric(s1.get("fill_rate_drop_vs_S0"), errors="coerce").iloc[0])
            if not s1.empty
            else float("nan")
        )

        _add_check(
            checks_rows,
            symbol=sym,
            check_id="EM01",
            check_name="lb95_per_signal_positive_mild",
            passed=np.isfinite(lb95_s1) and lb95_s1 > 0.0,
            severity_if_fail="high",
            metric_name="lb95_per_signal_pips_s1",
            metric_value=lb95_s1,
            threshold=0.0,
            comparator=">",
            details={"scenario_id": "S1_mild"},
        )
        _add_check(
            checks_rows,
            symbol=sym,
            check_id="EM02",
            check_name="lb95_per_signal_nonnegative_moderate",
            passed=np.isfinite(lb95_s2) and lb95_s2 >= 0.0,
            severity_if_fail="high",
            metric_name="lb95_per_signal_pips_s2",
            metric_value=lb95_s2,
            threshold=0.0,
            comparator=">=",
            details={"scenario_id": "S2_moderate"},
        )
        _add_check(
            checks_rows,
            symbol=sym,
            check_id="EM03",
            check_name="prob_negative_month_bound_mild",
            passed=np.isfinite(pneg_s1) and pneg_s1 <= 0.35,
            severity_if_fail="medium",
            metric_name="prob_negative_month_s1",
            metric_value=pneg_s1,
            threshold=0.35,
            comparator="<=",
            details={"scenario_id": "S1_mild"},
        )
        _add_check(
            checks_rows,
            symbol=sym,
            check_id="EM04",
            check_name="fill_rate_drop_bound_mild",
            passed=np.isfinite(drop_s1) and drop_s1 <= 0.12,
            severity_if_fail="medium",
            metric_name="fill_rate_drop_vs_s0_s1",
            metric_value=drop_s1,
            threshold=0.12,
            comparator="<=",
            details={"scenario_id": "S1_mild"},
        )

        x_core = (
            x[[c for c in core_cols if c in x.columns]].copy() if not x.empty else pd.DataFrame()
        )
        nan_cnt = int(x_core.isna().sum().sum()) if not x_core.empty else int(10**9)
        _add_check(
            checks_rows,
            symbol=sym,
            check_id="EM05",
            check_name="core_mc_fields_no_nan",
            passed=nan_cnt == 0,
            severity_if_fail="critical",
            metric_name="nan_core_fields",
            metric_value=nan_cnt,
            threshold=0,
            comparator="==",
            details={"required_columns": core_cols},
        )

    checks = pd.DataFrame(checks_rows).sort_values(["symbol", "check_id"]).reset_index(drop=True)
    fail = (
        checks[checks["status"].astype(str).str.lower() != "pass"].copy()
        if not checks.empty
        else pd.DataFrame()
    )
    issues_rows: list[dict[str, Any]] = []
    for _, r in fail.iterrows():
        issues_rows.append(
            {
                "issue_id": f"{r['symbol']}_{r['check_id']}",
                "symbol": str(r["symbol"]),
                "check_id": str(r["check_id"]),
                "severity": str(r["severity_if_fail"]).lower(),
                "component": "execution_monte_carlo",
                "summary": str(r["check_name"]),
                "details_json": json.dumps(
                    {
                        "metric_name": r.get("metric_name"),
                        "metric_value": r.get("metric_value"),
                        "threshold": r.get("threshold"),
                        "details_json": r.get("details_json"),
                    },
                    sort_keys=True,
                ),
            }
        )
    issues = pd.DataFrame(issues_rows)

    out_checks_csv.parent.mkdir(parents=True, exist_ok=True)
    out_issues_csv.parent.mkdir(parents=True, exist_ok=True)
    out_report_md.parent.mkdir(parents=True, exist_ok=True)
    checks.to_csv(out_checks_csv, index=False)
    issues.to_csv(out_issues_csv, index=False)

    lines: list[str] = []
    lines.append("# OCO Execution Monte Carlo Validation Report")
    lines.append("")
    lines.append(
        f"- generated_at_utc: `{datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}`"
    )
    lines.append(f"- symbol_scenarios_csv: `{symbol_scenarios_csv}`")
    lines.append(f"- checks_csv: `{out_checks_csv}`")
    lines.append(f"- issues_csv: `{out_issues_csv}`")
    lines.append("")
    lines.append("## Checks")
    lines.append(_table(checks))
    lines.append("")
    lines.append("## Issues")
    lines.append(_table(issues))
    out_report_md.write_text("\n".join(lines), encoding="utf-8")

    return checks, issues


def main() -> None:
    p = argparse.ArgumentParser(description="Validate execution Monte Carlo checks EM01..EM05")
    p.add_argument(
        "--symbol-scenarios-csv",
        default="data/analysis/tick_opportunity_mining/execution_mc_symbol_scenarios.csv",
    )
    p.add_argument("--symbols", default="EURUSD,GBPUSD,USDJPY,USDCHF,AUDUSD,USDCAD")
    p.add_argument(
        "--out-checks-csv", default="data/analysis/tick_opportunity_mining/execution_mc_checks.csv"
    )
    p.add_argument(
        "--out-issues-csv", default="data/analysis/tick_opportunity_mining/execution_mc_issues.csv"
    )
    p.add_argument(
        "--report-out", default="docs/analysis/oco_execution_monte_carlo_validation_report.md"
    )
    args = p.parse_args()

    checks, issues = run(
        symbol_scenarios_csv=Path(str(args.symbol_scenarios_csv)),
        out_checks_csv=Path(str(args.out_checks_csv)),
        out_issues_csv=Path(str(args.out_issues_csv)),
        out_report_md=Path(str(args.report_out)),
        symbols=_parse_symbols(args.symbols),
    )
    failed = (
        int((checks["status"].astype(str).str.lower() != "pass").sum()) if not checks.empty else 0
    )
    print(f"wrote checks: {args.out_checks_csv} rows={len(checks)}")
    print(f"wrote issues: {args.out_issues_csv} rows={len(issues)}")
    print(f"failed_checks={failed}")


if __name__ == "__main__":
    main()
