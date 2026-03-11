#!/usr/bin/env python3
"""Build an A/B parity report for cTrader baseline vs custom-data runs."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

try:
    from scripts.reconcile_ctrader_vs_research import run as reconcile_run
except ModuleNotFoundError:
    # Supports direct execution via `python scripts/build_ctrader_ab_parity_report.py`.
    from reconcile_ctrader_vs_research import run as reconcile_run


@dataclass
class ParityCheck:
    check_id: str
    status: str
    severity: str
    metric: str
    value_a: float
    value_b: float
    delta: float
    expected: str
    operator: str
    detail: str


def _to_num(raw: Any) -> float:
    try:
        out = float(raw)
    except Exception:
        return float("nan")
    return out


def _to_int(raw: Any) -> int:
    try:
        return int(raw)
    except Exception:
        return 0


def _metric_value(checks_df: pd.DataFrame, metric: str) -> float:
    rows = checks_df[checks_df["metric"].astype(str) == metric]
    if rows.empty:
        return float("nan")
    return _to_num(rows.iloc[0]["value"])


def _failed_hc_count(checks_df: pd.DataFrame) -> int:
    if checks_df.empty:
        return 0
    bad = checks_df[
        (checks_df["status"].astype(str) == "fail")
        & (checks_df["severity"].astype(str).str.lower().isin({"critical", "high"}))
    ]
    return int(len(bad))


def _table(df: pd.DataFrame) -> str:
    if df.empty:
        return "_empty_"
    try:
        return df.to_markdown(index=False)
    except Exception:
        return "```\n" + df.to_string(index=False) + "\n```"


def _build_checks(
    *,
    checks_a: pd.DataFrame,
    checks_b: pd.DataFrame,
    label_a: str,
    label_b: str,
) -> pd.DataFrame:
    specs = [
        (
            "AB_SELECTED_KEY_JACCARD_DELTA_LE_0_05",
            "selected_key_jaccard",
            0.05,
            "high",
            "<=",
            f"abs({label_b}-{label_a})",
        ),
        (
            "AB_SELECTED_COUNT_RATIO_DELTA_LE_0_20",
            "selected_count_ratio_runtime_vs_research",
            0.20,
            "high",
            "<=",
            f"abs({label_b}-{label_a})",
        ),
        (
            "AB_TIMESTAMP_MATCH_RATIO_DELTA_LE_0_20",
            "timestamp_match_ratio",
            0.20,
            "medium",
            "<=",
            f"abs({label_b}-{label_a})",
        ),
        (
            "AB_RAW_TICK_COVERAGE_DELTA_LE_0_15",
            "raw_tick_coverage_ratio_runtime_vs_hist",
            0.15,
            "high",
            "<=",
            f"abs({label_b}-{label_a})",
        ),
        (
            "AB_INTERTICK_RATIO_DELTA_LE_0_50",
            "median_intertick_ratio_runtime_vs_hist",
            0.50,
            "high",
            "<=",
            f"abs({label_b}-{label_a})",
        ),
    ]

    out: list[ParityCheck] = []
    for check_id, metric, threshold, severity, op, detail in specs:
        va = _metric_value(checks_a, metric)
        vb = _metric_value(checks_b, metric)
        delta = abs(vb - va) if pd.notna(va) and pd.notna(vb) else float("nan")
        ok = pd.notna(delta) and (float(delta) <= float(threshold))
        out.append(
            ParityCheck(
                check_id=check_id,
                status="pass" if ok else "fail",
                severity=severity,
                metric=metric,
                value_a=va,
                value_b=vb,
                delta=delta,
                expected=str(threshold),
                operator=op,
                detail=detail,
            )
        )

    hc_a = _failed_hc_count(checks_a)
    hc_b = _failed_hc_count(checks_b)
    out.append(
        ParityCheck(
            check_id="AB_HC_FAILURES_BOTH_EQ_0",
            status="pass" if (hc_a == 0 and hc_b == 0) else "fail",
            severity="critical",
            metric="high_critical_failures_count",
            value_a=float(hc_a),
            value_b=float(hc_b),
            delta=float(abs(hc_b - hc_a)),
            expected="0 for both runs",
            operator="==",
            detail=f"{label_a} and {label_b} must both have zero high/critical failures",
        )
    )
    return pd.DataFrame([c.__dict__ for c in out])


def _parity_verdict(parity_checks: pd.DataFrame) -> str:
    if parity_checks.empty:
        return "red"
    fails = parity_checks[parity_checks["status"].astype(str) == "fail"]
    if fails.empty:
        return "green"
    fail_hc = fails[fails["severity"].astype(str).str.lower().isin({"critical", "high"})]
    if not fail_hc.empty:
        return "red"
    return "yellow"


def _mismatch_top(mismatches: pd.DataFrame) -> pd.DataFrame:
    if mismatches.empty:
        return pd.DataFrame(columns=["type", "count"])
    out = (
        mismatches.groupby("type", as_index=False)
        .size()
        .rename(columns={"size": "count"})
        .sort_values("count", ascending=False)
    )
    return out.head(10)


def run(
    *,
    symbol: str,
    runtime_db_a: Path,
    runtime_db_b: Path,
    predictions_parquet: Path,
    tick_root: Path | None,
    history_dir: Path | None,
    start_ts: str,
    end_ts: str,
    strict_window: bool,
    timestamp_tolerance_sec: float,
    out_summary_csv: Path,
    out_checks_csv: Path,
    report_out: Path,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    sym = str(symbol).upper().strip()
    out_summary_csv.parent.mkdir(parents=True, exist_ok=True)
    out_checks_csv.parent.mkdir(parents=True, exist_ok=True)
    report_out.parent.mkdir(parents=True, exist_ok=True)

    base_name = out_summary_csv.stem
    work_dir = out_summary_csv.parent
    a_checks_path = work_dir / f"{base_name}_A_ctrader_vs_research_checks.csv"
    a_mismatch_path = work_dir / f"{base_name}_A_ctrader_vs_research_mismatches.csv"
    a_report_path = report_out.parent / f"{base_name}_A_ctrader_vs_research.md"
    b_checks_path = work_dir / f"{base_name}_B_ctrader_vs_research_checks.csv"
    b_mismatch_path = work_dir / f"{base_name}_B_ctrader_vs_research_mismatches.csv"
    b_report_path = report_out.parent / f"{base_name}_B_ctrader_vs_research.md"

    checks_a, mismatches_a = reconcile_run(
        symbol=sym,
        runtime_db_path=runtime_db_a,
        predictions_parquet=predictions_parquet,
        history_dir=history_dir,
        tick_root=tick_root,
        start_ts=start_ts,
        end_ts=end_ts,
        strict_window=strict_window,
        timestamp_tolerance_sec=timestamp_tolerance_sec,
        out_checks_csv=a_checks_path,
        out_mismatches_csv=a_mismatch_path,
        report_out=a_report_path,
    )
    checks_b, mismatches_b = reconcile_run(
        symbol=sym,
        runtime_db_path=runtime_db_b,
        predictions_parquet=predictions_parquet,
        history_dir=history_dir,
        tick_root=tick_root,
        start_ts=start_ts,
        end_ts=end_ts,
        strict_window=strict_window,
        timestamp_tolerance_sec=timestamp_tolerance_sec,
        out_checks_csv=b_checks_path,
        out_mismatches_csv=b_mismatch_path,
        report_out=b_report_path,
    )

    parity_checks = _build_checks(
        checks_a=checks_a,
        checks_b=checks_b,
        label_a="run_a",
        label_b="run_b",
    )
    overall_verdict = _parity_verdict(parity_checks)
    ctrader_only_checks = parity_checks[
        parity_checks["check_id"].astype(str) != "AB_HC_FAILURES_BOTH_EQ_0"
    ].copy()
    ctrader_side_verdict = _parity_verdict(ctrader_only_checks)
    run_health_gate_pass = bool(
        (
            parity_checks[
                parity_checks["check_id"].astype(str) == "AB_HC_FAILURES_BOTH_EQ_0"
            ]["status"].astype(str)
            == "pass"
        ).all()
    )

    summary = pd.DataFrame(
        [
            {
                "symbol": sym,
                "runtime_db_a": str(runtime_db_a),
                "runtime_db_b": str(runtime_db_b),
                "predictions_parquet": str(predictions_parquet),
                "history_dir": str(history_dir) if history_dir is not None else "",
                "tick_root": str(tick_root) if tick_root is not None else "",
                "start_ts": str(start_ts),
                "end_ts": str(end_ts),
                "strict_window": bool(strict_window),
                "timestamp_tolerance_sec": float(timestamp_tolerance_sec),
                "a_high_critical_failures": _failed_hc_count(checks_a),
                "b_high_critical_failures": _failed_hc_count(checks_b),
                "a_selected_key_jaccard": _metric_value(checks_a, "selected_key_jaccard"),
                "b_selected_key_jaccard": _metric_value(checks_b, "selected_key_jaccard"),
                "a_selected_count_ratio_runtime_vs_research": _metric_value(
                    checks_a, "selected_count_ratio_runtime_vs_research"
                ),
                "b_selected_count_ratio_runtime_vs_research": _metric_value(
                    checks_b, "selected_count_ratio_runtime_vs_research"
                ),
                "a_timestamp_match_ratio": _metric_value(checks_a, "timestamp_match_ratio"),
                "b_timestamp_match_ratio": _metric_value(checks_b, "timestamp_match_ratio"),
                "a_raw_tick_coverage_ratio_runtime_vs_hist": _metric_value(
                    checks_a, "raw_tick_coverage_ratio_runtime_vs_hist"
                ),
                "b_raw_tick_coverage_ratio_runtime_vs_hist": _metric_value(
                    checks_b, "raw_tick_coverage_ratio_runtime_vs_hist"
                ),
                "a_median_intertick_ratio_runtime_vs_hist": _metric_value(
                    checks_a, "median_intertick_ratio_runtime_vs_hist"
                ),
                "b_median_intertick_ratio_runtime_vs_hist": _metric_value(
                    checks_b, "median_intertick_ratio_runtime_vs_hist"
                ),
                "a_missing_selected_key_rows": _to_int(
                    _metric_value(checks_a, "selected_key_missing_count")
                ),
                "b_missing_selected_key_rows": _to_int(
                    _metric_value(checks_b, "selected_key_missing_count")
                ),
                "a_extra_selected_key_rows": _to_int(
                    _metric_value(checks_a, "selected_key_extra_count")
                ),
                "b_extra_selected_key_rows": _to_int(
                    _metric_value(checks_b, "selected_key_extra_count")
                ),
                "a_mismatches_rows": int(len(mismatches_a)),
                "b_mismatches_rows": int(len(mismatches_b)),
                "parity_fail_count_overall": int(
                    (parity_checks["status"].astype(str) == "fail").sum()
                    if not parity_checks.empty
                    else 0
                ),
                "parity_fail_count_ctrader_side": int(
                    (ctrader_only_checks["status"].astype(str) == "fail").sum()
                    if not ctrader_only_checks.empty
                    else 0
                ),
                "run_health_gate_pass": bool(run_health_gate_pass),
                "parity_verdict_ctrader_side": ctrader_side_verdict,
                "parity_verdict_overall": overall_verdict,
                "parity_verdict": overall_verdict,
                "evaluated_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            }
        ]
    )
    summary.to_csv(out_summary_csv, index=False)
    parity_checks.to_csv(out_checks_csv, index=False)

    parity_fails = parity_checks[parity_checks["status"].astype(str) == "fail"].copy()
    report = [
        "# cTrader A/B Parity Report",
        "",
        f"- symbol: `{sym}`",
        f"- run_a (baseline): `{runtime_db_a}`",
        f"- run_b (custom data): `{runtime_db_b}`",
        f"- predictions_parquet: `{predictions_parquet}`",
        f"- history_dir: `{history_dir if history_dir is not None else ''}`",
        f"- tick_root: `{tick_root if tick_root is not None else ''}`",
        f"- start_ts: `{start_ts}`",
        f"- end_ts: `{end_ts}`",
        f"- strict_window: `{strict_window}`",
        f"- timestamp_tolerance_sec: `{timestamp_tolerance_sec}`",
        "",
        "## Verdicts",
        f"- cTrader-side parity: `{ctrader_side_verdict.upper()}`",
        f"- overall (includes research health gate): `{overall_verdict.upper()}`",
        f"- run health gate pass: `{run_health_gate_pass}`",
        "",
        "## Summary",
        _table(summary),
        "",
        "## Failed Parity Checks",
        _table(parity_fails),
        "",
        "## All Parity Checks",
        _table(parity_checks),
        "",
        "## Mismatch Types (Run A)",
        _table(_mismatch_top(mismatches_a)),
        "",
        "## Mismatch Types (Run B)",
        _table(_mismatch_top(mismatches_b)),
        "",
        "## Run A Reconciliation Outputs",
        f"- checks: `{a_checks_path}`",
        f"- mismatches: `{a_mismatch_path}`",
        f"- report: `{a_report_path}`",
        "",
        "## Run B Reconciliation Outputs",
        f"- checks: `{b_checks_path}`",
        f"- mismatches: `{b_mismatch_path}`",
        f"- report: `{b_report_path}`",
        "",
    ]
    report_out.write_text("\n".join(report), encoding="utf-8")
    return summary, parity_checks


def _bool_arg(raw: str) -> bool:
    return str(raw).strip().lower() in {"1", "true", "yes", "y"}


def main() -> None:
    p = argparse.ArgumentParser(description="Build cTrader baseline-vs-custom A/B parity report")
    p.add_argument("--symbol", required=True)
    p.add_argument("--runtime-db-a", required=True, help="baseline run DB (broker feed)")
    p.add_argument("--runtime-db-b", required=True, help="custom-data run DB (HistData feed)")
    p.add_argument("--predictions-parquet", required=True)
    p.add_argument("--tick-root", default="/Users/danielfisher/Desktop/tick")
    p.add_argument("--history-dir", default="")
    p.add_argument("--start-ts", required=True)
    p.add_argument("--end-ts", required=True)
    p.add_argument("--strict-window", default="true", choices=["true", "false"])
    p.add_argument("--timestamp-tolerance-sec", type=float, default=2.0)
    p.add_argument(
        "--out-summary-csv",
        default="data/analysis/backtest_reconcile/ctrader_ab_parity_summary.csv",
    )
    p.add_argument(
        "--out-checks-csv",
        default="data/analysis/backtest_reconcile/ctrader_ab_parity_checks.csv",
    )
    p.add_argument(
        "--report-out",
        default="docs/analysis/ctrader_ab_parity_report.md",
    )
    args = p.parse_args()

    summary, checks = run(
        symbol=str(args.symbol),
        runtime_db_a=Path(str(args.runtime_db_a)),
        runtime_db_b=Path(str(args.runtime_db_b)),
        predictions_parquet=Path(str(args.predictions_parquet)),
        tick_root=(Path(str(args.tick_root)) if str(args.tick_root).strip() else None),
        history_dir=(Path(str(args.history_dir)) if str(args.history_dir).strip() else None),
        start_ts=str(args.start_ts),
        end_ts=str(args.end_ts),
        strict_window=_bool_arg(str(args.strict_window)),
        timestamp_tolerance_sec=float(args.timestamp_tolerance_sec),
        out_summary_csv=Path(str(args.out_summary_csv)),
        out_checks_csv=Path(str(args.out_checks_csv)),
        report_out=Path(str(args.report_out)),
    )

    print(f"wrote summary: {args.out_summary_csv} rows={len(summary)}")
    print(f"wrote checks: {args.out_checks_csv} rows={len(checks)}")
    print(f"wrote report: {args.report_out}")
    print(f"parity_verdict_ctrader_side={str(summary.iloc[0]['parity_verdict_ctrader_side']).upper()}")
    print(f"parity_verdict_overall={str(summary.iloc[0]['parity_verdict_overall']).upper()}")


if __name__ == "__main__":
    main()
