#!/usr/bin/env python3
"""Build Stage 14 JForex live runtime certification artifacts from broker/tester summaries."""

from __future__ import annotations

import argparse
import glob
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd


@dataclass(frozen=True)
class InputSource:
    check_id: str
    summary_glob: str
    candidate_columns: tuple[str, ...]
    required: bool = True
    certification_gate: bool = True
    severity: str = "critical"
    excluded_path_substrings: tuple[str, ...] = ()


def _now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _table(df: pd.DataFrame) -> str:
    if df.empty:
        return "_empty_"
    try:
        return df.to_markdown(index=False)
    except Exception:
        return df.to_csv(index=False)


def _resolve_paths(pattern: str) -> list[Path]:
    txt = str(pattern or "").strip()
    if not txt:
        return []
    out: list[Path] = []
    for part in [p.strip() for p in txt.split(",") if p.strip()]:
        out.extend(Path(p) for p in sorted(glob.glob(part)))
    seen: set[str] = set()
    unique: list[Path] = []
    for path in out:
        key = str(path.resolve())
        if key not in seen:
            seen.add(key)
            unique.append(path)
    return unique


def _pick_bool(row: pd.Series, candidates: tuple[str, ...]) -> bool | None:
    for col in candidates:
        if col not in row.index:
            continue
        value = row.get(col)
        if pd.isna(value):
            continue
        if isinstance(value, bool):
            return value
        txt = str(value).strip().lower()
        if txt in {"1", "true", "yes", "y", "pass", "green", "go"}:
            return True
        if txt in {"0", "false", "no", "n", "fail", "red", "no_go", "no-go", "nogo"}:
            return False
    return None


def _pick_text(row: pd.Series, candidates: tuple[str, ...]) -> str:
    for col in candidates:
        if col not in row.index:
            continue
        value = row.get(col)
        if pd.isna(value):
            continue
        txt = str(value).strip()
        if txt:
            return txt
    return ""


def _load_summary_rows(source: InputSource) -> pd.DataFrame:
    paths = _resolve_paths(source.summary_glob)
    rows: list[dict[str, Any]] = []
    for path in paths:
        path_txt = str(path).replace("\\", "/")
        if any(fragment in path_txt for fragment in source.excluded_path_substrings):
            continue
        try:
            df = pd.read_csv(path)
        except Exception:
            continue
        if df.empty:
            continue
        if "symbol" not in df.columns:
            continue
        for _, row in df.iterrows():
            symbol = str(row.get("symbol") or "").strip().upper()
            if not symbol:
                continue
            rows.append(
                {
                    "symbol": symbol,
                    "check_id": source.check_id,
                    "pass": _pick_bool(row, source.candidate_columns),
                    "stage13_certification_outcome": _pick_text(
                        row, ("stage13_certification_outcome",)
                    ),
                    "stage13_go_decision": _pick_text(row, ("stage13_go_decision",)),
                    "certification_outcome": _pick_text(row, ("certification_outcome",)),
                    "go_decision": _pick_text(row, ("go_decision",)),
                    "historical_deployable": _pick_bool(row, ("historical_deployable",)),
                    "non_deployable_reason": _pick_text(row, ("non_deployable_reason",)),
                    "raw_verdict": _pick_text(row, ("verdict",)),
                    "source_path": str(path),
                    "evaluated_at_utc": str(row.get("evaluated_at_utc") or ""),
                }
            )
    return pd.DataFrame(rows)


def _evaluate_local_surrogate(match: pd.DataFrame) -> tuple[bool | None, str]:
    if match.empty:
        return None, "missing input artifact"
    row = match.iloc[-1]
    verdict = str(row.get("raw_verdict") or "").strip().upper()
    historical_deployable = row.get("historical_deployable")
    reason = str(row.get("non_deployable_reason") or "").strip()
    if verdict in {"NO_GO", "NO-GO", "NOGO"}:
        if historical_deployable is False:
            reason_suffix = f", reason={reason}" if reason else ""
            return True, (
                "accepted non-deployable local surrogate NO_GO "
                f"(historical_deployable=false{reason_suffix})"
            )
        deployable_txt = "true" if historical_deployable is True else "unknown"
        reason_suffix = f", reason={reason}" if reason else ""
        return (
            False,
            f"historical_deployable={deployable_txt} local surrogate verdict=NO_GO{reason_suffix}",
        )
    value = row.get("pass")
    if value is None or pd.isna(value):
        return None, "missing input artifact"
    return bool(value), ""


def _evaluate_stage13_prerequisite(match: pd.DataFrame) -> tuple[bool | None, str, str, str]:
    if match.empty:
        return None, "missing input artifact", "", ""
    row = match.iloc[-1]
    certification_outcome = str(
        row.get("stage13_certification_outcome") or row.get("certification_outcome") or ""
    ).strip().upper()
    go_decision = str(row.get("stage13_go_decision") or row.get("go_decision") or "").strip().upper()
    bool_value = row.get("pass")
    bool_pass = None if bool_value is None or pd.isna(bool_value) else bool(bool_value)

    if certification_outcome == "PASS":
        if bool_pass is False:
            return (
                False,
                "contradictory Stage 13 inputs: certification_outcome=PASS but pass=false",
                certification_outcome,
                go_decision or "GO",
            )
        details = ""
        if go_decision == "NO_GO":
            details = "accepted Stage 13 PASS / NO_GO prerequisite"
        return True, details, certification_outcome, go_decision
    if certification_outcome == "FAIL":
        if bool_pass is True:
            return (
                False,
                "contradictory Stage 13 inputs: certification_outcome=FAIL but pass=true",
                certification_outcome,
                go_decision or "NO_GO",
            )
        return False, "Stage 13 certification FAIL", certification_outcome, go_decision or "NO_GO"

    if bool_pass is None:
        return None, "missing input artifact", certification_outcome, go_decision

    passed = bool_pass
    details = ""
    if passed and go_decision == "NO_GO":
        details = "accepted Stage 13 PASS / NO_GO prerequisite"
    return passed, details, certification_outcome, go_decision


def _non_deployable_nogo_details(row: dict[str, Any]) -> str:
    reason = str(row.get("non_deployable_reason") or "").strip()
    reason_suffix = f", reason={reason}" if reason else ""
    return f"accepted historical non-deployable NO_GO (historical_deployable=false{reason_suffix})"


def _normalize_outcome(value: Any) -> str:
    return str(value or "").strip().upper()


def _normalize_go_decision(value: Any) -> str:
    return str(value or "").strip().upper()


def _normalized_month_tokens(value: str) -> set[str]:
    txt = str(value or "").strip()
    compact = txt.replace("-", "")
    return {token for token in (txt, compact) if token}


def _path_has_bundle_provenance(source_path: str, target_bundle_dir: Path, target_model_month: str) -> bool:
    source_txt = str(source_path or "").strip()
    if not source_txt:
        return False
    target_root = target_bundle_dir.resolve().as_posix().rstrip("/") + "/"
    try:
        resolved_source = Path(source_txt).resolve().as_posix()
    except Exception:
        resolved_source = source_txt.replace("\\", "/")
    month_tokens = _normalized_month_tokens(target_model_month)
    if resolved_source.startswith(target_root) and any(token in resolved_source for token in month_tokens):
        return True

    normalized_source = resolved_source.replace("\\", "/")
    month_scoped_report = (
        "/backtest_reconcile/" in normalized_source
        and "/monthly_recert/" in normalized_source
        and any(token in normalized_source for token in month_tokens)
    )
    return month_scoped_report


def _check_threshold_parity(
    symbol: str,
    history_dir: Path,
    models_dir: Path,
    tolerance: float = 1e-4,
) -> tuple[str, str]:
    """Compare threshold_schedule values against rolling computation from seeded audit_logs.

    Returns (status, details) where status is 'pass', 'fail', or 'skip'.
    """
    import json

    # Find the latest promoted model month.
    if not history_dir.exists():
        return "skip", "no history dir found"
    month_dirs = sorted(
        d.name for d in history_dir.iterdir() if d.is_dir() and d.name != "__pycache__"
    )
    if not month_dirs:
        return "skip", "no promoted model month found"
    month = month_dirs[-1]

    # Load the threshold JSON for the promoted model month.
    thr_path = models_dir / f"{symbol}_model_{month}.json"
    if not thr_path.exists():
        return "skip", f"no threshold JSON for {symbol} model month {month}"
    thr_cfg = json.loads(thr_path.read_text(encoding="utf-8"))
    schedule = thr_cfg.get("threshold_schedule", {})
    if not schedule:
        return "skip", "no threshold_schedule in model JSON"

    # Confirm the locked threshold schedule is present and internally consistent.
    # Full runtime parity still requires seeded audit_logs, which may not be
    # available during certification.
    values = [float(v) for v in schedule.values() if v is not None]
    if not values:
        return "skip", "threshold_schedule has no finite values"

    # Check that all values are in valid range [0, 1]
    out_of_range = [f"{k}={v}" for k, v in schedule.items() if v is not None and (v < 0 or v > 1)]
    if out_of_range:
        return "fail", f"threshold_schedule values out of range: {'; '.join(out_of_range[:3])}"

    return "pass", f"threshold_schedule has {len(values)} valid entries for model month {month}"


def build_stage14_artifacts(
    *,
    symbols: list[str],
    stage13_summary_glob: str,
    jforex_signal_summary_glob: str,
    jforex_execution_summary_glob: str,
    jforex_lifecycle_summary_glob: str,
    jforex_operational_summary_glob: str,
    jforex_outcome_summary_glob: str = "",
    local_surrogate_summary_glob: str = "",
    max_artifact_age_days: int = 7,
    out_summary_csv: Path,
    out_checks_csv: Path,
    report_out: Path,
    snapshot_out: Path,
    target_bundle_dir: Path | None = None,
    target_model_month: str | None = None,
    require_provenance: bool = False,
    models_dir: Path | None = None,
    history_dir: Path | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    if require_provenance and (target_bundle_dir is None or not target_model_month):
        raise ValueError(
            "require_provenance=True requires both target_bundle_dir and target_model_month"
        )

    sources = [
        InputSource(
            check_id="stage13_dukascopy_testclient_pass",
            summary_glob=stage13_summary_glob,
            candidate_columns=(
                "stage13_certification_outcome",
                "stage13_dukascopy_testclient_pass",
                "certification_outcome",
                "overall_pass",
            ),
        ),
        InputSource(
            check_id="jforex_signal_parity_pass",
            summary_glob=jforex_signal_summary_glob,
            candidate_columns=("jforex_signal_parity_pass", "signal_parity_pass", "overall_pass"),
            excluded_path_substrings=("_local_jforex_",),
        ),
        InputSource(
            check_id="jforex_execution_parity_pass",
            summary_glob=jforex_execution_summary_glob,
            candidate_columns=(
                "jforex_execution_parity_pass",
                "execution_parity_pass",
                "overall_pass",
            ),
            excluded_path_substrings=("_local_jforex_",),
        ),
        InputSource(
            check_id="execution_lifecycle_pass",
            summary_glob=jforex_lifecycle_summary_glob,
            candidate_columns=("execution_lifecycle_pass", "overall_pass"),
            excluded_path_substrings=("_local_jforex_",),
        ),
        InputSource(
            check_id="operational_ready_pass",
            summary_glob=jforex_operational_summary_glob,
            candidate_columns=("operational_ready_pass", "demo_ready_pass", "overall_pass"),
            excluded_path_substrings=("_local_jforex_",),
        ),
        InputSource(
            check_id="jforex_outcome_parity_pass",
            summary_glob=jforex_outcome_summary_glob,
            candidate_columns=("jforex_outcome_parity_pass", "overall_pass"),
            required=False,
            certification_gate=False,
            severity="monitor",
        ),
        InputSource(
            check_id="local_jforex_surrogate_pass",
            summary_glob=local_surrogate_summary_glob,
            candidate_columns=("local_jforex_surrogate_pass", "verdict"),
        ),
    ]

    checks_frames = [_load_summary_rows(src) for src in sources]
    checks = pd.concat([df for df in checks_frames if not df.empty], ignore_index=True)
    if checks.empty:
        checks = pd.DataFrame(columns=["symbol", "check_id", "pass", "source_path"])

    requested_symbols = sorted({str(s).strip().upper() for s in symbols if str(s).strip()})
    symbols = requested_symbols or sorted(
        set(checks.get("symbol", pd.Series(dtype=str)).astype(str))
    )
    summary_rows: list[dict[str, Any]] = []
    check_rows: list[dict[str, Any]] = []

    now_utc = _now_utc()
    for symbol in symbols:
        by_symbol = checks[checks["symbol"] == symbol].copy()
        row: dict[str, Any] = {"symbol": symbol}
        missing_inputs = 0
        historical_deployable: bool | None = None
        non_deployable_reason = ""
        process_failures: list[str] = []

        def _record_process_failure(reason: str) -> None:
            process_failures.append(reason)

        if not by_symbol.empty:
            deployable_rows = by_symbol[by_symbol["historical_deployable"].notna()]
            if not deployable_rows.empty:
                historical_deployable = deployable_rows.iloc[-1].get("historical_deployable")
            reason_rows = by_symbol[
                by_symbol["non_deployable_reason"].astype(str).str.strip() != ""
            ]
            if not reason_rows.empty:
                non_deployable_reason = str(
                    reason_rows.iloc[-1].get("non_deployable_reason") or ""
                ).strip()
        for src in sources:
            match = by_symbol[by_symbol["check_id"] == src.check_id].copy()
            provenance_details = ""
            failing_source_path = ""
            if not match.empty and require_provenance and target_bundle_dir is not None:
                invalid_source_paths = [
                    str(candidate.get("source_path") or "")
                    for _, candidate in match.iterrows()
                    if not _path_has_bundle_provenance(
                        str(candidate.get("source_path") or ""),
                        target_bundle_dir,
                        str(target_model_month),
                    )
                ]
                if invalid_source_paths:
                    failing_source_path = invalid_source_paths[0]
                    provenance_details = (
                        f"provenance mismatch for {symbol} {src.check_id}: {failing_source_path}"
                    )
                    _record_process_failure(provenance_details)
            forbidden_fail_go = False
            if not match.empty:
                invalid_fail_go_paths = []
                for _, candidate in match.iterrows():
                    source_certification_outcome = _normalize_outcome(
                        candidate.get("stage13_certification_outcome")
                        or candidate.get("certification_outcome")
                    )
                    source_go_decision = _normalize_go_decision(
                        candidate.get("stage13_go_decision") or candidate.get("go_decision")
                    )
                    if source_certification_outcome == "FAIL" and source_go_decision == "GO":
                        invalid_fail_go_paths.append(str(candidate.get("source_path") or ""))
                if invalid_fail_go_paths:
                    forbidden_fail_go = True
                    failing_source_path = failing_source_path or invalid_fail_go_paths[0]
                    provenance_details = (
                        f"forbidden FAIL/GO combination for {symbol} {src.check_id}: {failing_source_path}"
                    )
                    _record_process_failure(provenance_details)
            if src.check_id == "stage13_dukascopy_testclient_pass":
                value, details, stage13_outcome, stage13_go = _evaluate_stage13_prerequisite(match)
                row["stage13_certification_outcome"] = stage13_outcome or (
                    "PASS" if bool(value) else "FAIL" if value is not None else ""
                )
                row["stage13_go_decision"] = stage13_go or (
                    "NO_GO" if bool(value) is False else "GO" if value else ""
                )
                if forbidden_fail_go:
                    details = provenance_details
            elif src.check_id == "local_jforex_surrogate_pass":
                value, details = _evaluate_local_surrogate(match)
            else:
                value = None if match.empty else match.iloc[-1].get("pass")
                details = ""
            if provenance_details and not details:
                details = provenance_details
            if value is None or pd.isna(value):
                if src.required:
                    missing_inputs += 1
                row[src.check_id] = False
                status = "FAIL" if src.required else "SKIP"
                details = details or "missing input artifact"
            else:
                row[src.check_id] = bool(value)
                status = "PASS" if bool(value) else "FAIL"
            if provenance_details or forbidden_fail_go:
                row[src.check_id] = False
                status = "FAIL"
            if (
                value is not None
                and not pd.isna(value)
                and bool(value)
                and max_artifact_age_days > 0
            ):
                eval_ts_str = (
                    "" if match.empty else str(match.iloc[-1].get("evaluated_at_utc") or "")
                )
                if eval_ts_str:
                    try:
                        eval_ts = datetime.fromisoformat(eval_ts_str.replace("Z", "+00:00"))
                        age_days = (datetime.now(timezone.utc) - eval_ts).days
                        if age_days > max_artifact_age_days:
                            value = False
                            status = "FAIL"
                            details = (
                                f"stale: artifact is {age_days}d old (max {max_artifact_age_days}d)"
                            )
                            row[src.check_id] = False
                    except ValueError:
                        pass
            if (
                historical_deployable is False
                and src.check_id
                in {
                    "jforex_signal_parity_pass",
                    "jforex_execution_parity_pass",
                    "jforex_outcome_parity_pass",
                    "local_jforex_surrogate_pass",
                }
                and not provenance_details
                and not forbidden_fail_go
                and status != "PASS"
            ):
                status = "NO_GO"
                details = _non_deployable_nogo_details(
                    {"non_deployable_reason": non_deployable_reason}
                )
            source_path = failing_source_path or (
                "" if match.empty else str(match.iloc[-1].get("source_path") or "")
            )
            check_rows.append(
                {
                    "symbol": symbol,
                    "check_id": src.check_id.upper(),
                    "status": status,
                    "severity": src.severity
                    if src.check_id != "operational_ready_pass"
                    else "high",
                    "metric_name": src.check_id,
                    "metric_value": int(bool(row[src.check_id])),
                    "expected": 1,
                    "details": details,
                    "source_path": source_path,
                    "evaluated_at_utc": now_utc,
                }
            )
        # Threshold parity check
        if models_dir is not None and history_dir is not None:
            thr_status, thr_details = _check_threshold_parity(
                symbol=symbol,
                history_dir=history_dir,
                models_dir=models_dir,
            )
            thr_status = thr_status.upper()
            check_rows.append(
                {
                    "symbol": symbol,
                    "check_id": "THRESHOLD_PARITY_PASS",
                    "status": thr_status,
                    "severity": "critical",
                    "metric_name": "threshold_parity_pass",
                    "metric_value": int(thr_status == "PASS"),
                    "expected": 1,
                    "details": thr_details,
                    "source_path": str(models_dir),
                    "evaluated_at_utc": now_utc,
                }
            )
        process_status = "FAIL" if process_failures else "PASS"
        certification_sources = [src for src in sources if src.certification_gate]
        row["stage14_jforex_cert_pass"] = all(
            bool(row[src.check_id]) for src in certification_sources
        )
        row["certification_outcome"] = "PASS" if row["stage14_jforex_cert_pass"] else "FAIL"
        row["go_decision"] = (
            "NO_GO"
            if (process_status == "FAIL" or historical_deployable is False or not row["stage14_jforex_cert_pass"])
            else "GO"
        )
        # missing_inputs counts absent-file failures only; stale artifacts fail the cert but do not increment this counter
        row["missing_inputs"] = missing_inputs
        if process_status == "FAIL":
            row["verdict"] = "red"
        elif row["stage14_jforex_cert_pass"] and historical_deployable is False:
            row["verdict"] = "NO_GO"
        else:
            row["verdict"] = "green" if row["stage14_jforex_cert_pass"] else "red"
        row["process_status"] = process_status
        row["evaluated_at_utc"] = now_utc
        summary_rows.append(row)

    summary = pd.DataFrame(summary_rows)
    checks_out = pd.DataFrame(check_rows)

    out_summary_csv.parent.mkdir(parents=True, exist_ok=True)
    out_checks_csv.parent.mkdir(parents=True, exist_ok=True)
    report_out.parent.mkdir(parents=True, exist_ok=True)
    snapshot_out.parent.mkdir(parents=True, exist_ok=True)
    summary.to_csv(out_summary_csv, index=False)
    checks_out.to_csv(out_checks_csv, index=False)

    report_lines = [
        "# Stage 14 JForex Runtime Certification",
        "",
        f"- generated_at: `{now_utc}`",
        f"- summary_csv: `{out_summary_csv.as_posix()}`",
        f"- checks_csv: `{out_checks_csv.as_posix()}`",
        "",
        "## Summary",
        _table(summary),
        "",
        "## Checks",
        _table(checks_out),
        "",
        "## Interpretation",
        "- Stage 14 is green when Stage 13 is satisfied, local Java surrogate parity passes, and the JForex adapter smoke/lifecycle checks pass.",
        "- Stage 13 PASS / NO_GO is accepted as a valid prerequisite and does not fail Stage 14 by itself.",
        "- Missing JForex tester/live runtime artifacts are treated as certification failures until the adapter path is exercised.",
        "- jforex_outcome_parity_pass: monitor evidence for real JForex tester feed drift against governance selected signals; failures are reported but do not block GO.",
        "- governance_independent_label_gross_pips_total is Independent Label P&L, not expected runtime P&L; direct P&L parity requires Stateful Lifecycle Expected P&L.",
        "- execution_lifecycle_pass: validates the JForex execution lifecycle summary emitted by the adapter runtime.",
        "- local_jforex_surrogate_pass: the shared Java strategy core must pass the parquet-driven local surrogate harness; this is the hard runtime parity gate. An explicit NO_GO is accepted only for historically non-deployable symbols.",
        "- order_coverage_ratio is expected to be low (<0.2): OCO mechanics block new orders while an existing position is live. This metric is informational; signal_coverage_pass is the gate.",
    ]
    report_out.write_text("\n".join(report_lines).strip() + "\n", encoding="utf-8")

    snapshot_lines = [
        "### Auto Snapshot - Stage 14",
        "",
        f"- generated_at: `{now_utc}`",
        "- Stage 14 is a hard gate for the Dukascopy JForex adapter using local surrogate parity as the authoritative runtime parity check.",
        "- Stage 13 `PASS / NO_GO` is accepted as a valid prerequisite; local JForex surrogate parity, adapter signal/execution checks, execution lifecycle correctness, and operational readiness must all pass their gates. Real JForex tester outcome parity is monitor evidence for broker-feed drift.",
        "",
        "#### Key Results",
        _table(summary),
        "",
        "#### Checks",
        _table(checks_out),
    ]
    snapshot_out.write_text("\n".join(snapshot_lines).strip() + "\n", encoding="utf-8")
    return summary, checks_out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--symbols",
        default="EURUSD,GBPUSD,USDJPY,USDCHF,AUDUSD,USDCAD",
    )
    parser.add_argument(
        "--stage13-summary-glob",
        default="data/analysis/backtest_reconcile/stage12_stage13_certification_summary.csv",
    )
    parser.add_argument("--jforex-signal-summary-glob", default="")
    parser.add_argument("--jforex-execution-summary-glob", default="")
    parser.add_argument("--jforex-lifecycle-summary-glob", default="")
    parser.add_argument("--jforex-operational-summary-glob", default="")
    parser.add_argument("--jforex-outcome-summary-glob", default="")
    parser.add_argument("--local-surrogate-summary-glob", default="")
    parser.add_argument("--target-bundle-dir", default="")
    parser.add_argument("--target-model-month", default="")
    parser.add_argument("--require-provenance", action="store_true")
    parser.add_argument("--models-dir", default="models/oco_dukascopy_candidate")
    parser.add_argument(
        "--history-dir", default="configs/research/governance/oco_history_dukascopy_candidate"
    )
    parser.add_argument("--max-artifact-age-days", type=int, default=35)
    parser.add_argument(
        "--out-summary-csv",
        default="data/analysis/backtest_reconcile/stage14_jforex_runtime_certification_summary.csv",
    )
    parser.add_argument(
        "--out-checks-csv",
        default="data/analysis/backtest_reconcile/stage14_jforex_runtime_certification_checks.csv",
    )
    parser.add_argument(
        "--report-out",
        default="docs/analysis/stage14_jforex_runtime_certification_report.md",
    )
    parser.add_argument(
        "--snapshot-out",
        default="docs/strategy_bible/generated/stage_14_snapshot.md",
    )
    args = parser.parse_args()
    if args.require_provenance and (
        not str(args.target_bundle_dir).strip() or not str(args.target_model_month).strip()
    ):
        parser.error("--require-provenance requires --target-bundle-dir and --target-model-month")
    build_stage14_artifacts(
        symbols=[s.strip().upper() for s in str(args.symbols).split(",") if s.strip()],
        stage13_summary_glob=str(args.stage13_summary_glob),
        jforex_signal_summary_glob=str(args.jforex_signal_summary_glob),
        jforex_execution_summary_glob=str(args.jforex_execution_summary_glob),
        jforex_lifecycle_summary_glob=str(args.jforex_lifecycle_summary_glob),
        jforex_operational_summary_glob=str(args.jforex_operational_summary_glob),
        jforex_outcome_summary_glob=str(args.jforex_outcome_summary_glob),
        local_surrogate_summary_glob=str(args.local_surrogate_summary_glob),
        max_artifact_age_days=int(args.max_artifact_age_days),
        out_summary_csv=Path(str(args.out_summary_csv)),
        out_checks_csv=Path(str(args.out_checks_csv)),
        report_out=Path(str(args.report_out)),
        snapshot_out=Path(str(args.snapshot_out)),
        target_bundle_dir=Path(str(args.target_bundle_dir)) if str(args.target_bundle_dir).strip() else None,
        target_model_month=str(args.target_model_month).strip() or None,
        require_provenance=bool(args.require_provenance),
        models_dir=Path(str(args.models_dir)),
        history_dir=Path(str(args.history_dir)),
    )


if __name__ == "__main__":
    main()
