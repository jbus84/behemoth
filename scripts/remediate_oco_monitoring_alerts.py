#!/usr/bin/env python3
"""Build alert disposition matrix for non-green monitoring alerts."""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pandas as pd

try:
    import yaml
except Exception:
    yaml = None  # type: ignore[assignment]


def _table(df: pd.DataFrame) -> str:
    if df.empty:
        return "_empty_"
    try:
        return df.to_markdown(index=False)
    except Exception:
        return "```\n" + df.to_string(index=False) + "\n```"


def _normalize_source_alert(value: Any, metric_id: str) -> str:
    source_alert = str(value).strip().lower()
    if source_alert in {"", "nan", "none", "null"}:
        if metric_id.startswith("E_DRIFT_"):
            return "execution_drift"
        if metric_id.startswith("TS"):
            return "threshold_sensitivity"
        if metric_id.startswith("FTMO_"):
            return "ftmo_allocator"
        return "other"
    return source_alert


def _read_yaml(path: Path) -> dict[str, Any]:
    if (yaml is None) or (not path.exists()):
        return {}
    obj = yaml.safe_load(path.read_text(encoding="utf-8"))
    return obj if isinstance(obj, dict) else {}


def _read_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    try:
        return pd.read_csv(path)
    except Exception:
        return pd.DataFrame()


def _rule_match(rule: dict[str, Any], *, symbol: str, metric_id: str) -> bool:
    rid = str(rule.get("metric_id", "")).strip()
    if rid != str(metric_id):
        return False
    syms = (
        [str(x).upper() for x in rule.get("symbols", [])]
        if isinstance(rule.get("symbols", []), list)
        else []
    )
    if not syms:
        return True
    return str(symbol).upper() in syms


def _bool_cfg(cfg: dict[str, Any], key: str, default: bool) -> bool:
    raw = cfg.get(key, default)
    if isinstance(raw, bool):
        return raw
    return str(raw).strip().lower() in {"1", "true", "yes", "y", "t"}


def _key(symbol: str, metric_id: str) -> str:
    return f"{symbol.upper()}|{metric_id}"


def run(
    *,
    drift_alerts_csv: Path,
    threshold_alerts_csv: Path,
    ftmo_alerts_csv: Path | None,
    exceptions_yaml: Path,
    out_disposition_csv: Path,
    report_out: Path,
) -> pd.DataFrame:
    d1 = _read_csv(drift_alerts_csv)
    d2 = _read_csv(threshold_alerts_csv)
    d3 = _read_csv(ftmo_alerts_csv) if ftmo_alerts_csv is not None else pd.DataFrame()
    alerts = (
        pd.concat([d1, d2, d3], ignore_index=True)
        if (not d1.empty or not d2.empty or not d3.empty)
        else pd.DataFrame()
    )

    expected_cols = [
        "symbol",
        "source_alert",
        "test_month",
        "metric_id",
        "metric_value",
        "band",
        "severity",
        "status",
        "action_code",
        "owner",
        "rationale",
        "expires_utc",
        "is_expired",
        "source_path",
        "evaluated_at_utc",
        "first_seen_utc",
        "last_seen_utc",
        "consecutive_runs_non_green",
        "months_non_green_count",
        "sla_days",
        "days_to_expiry",
        "escalation_level",
        "evidence_required",
        "evidence_link",
        "expiry_breach",
        "recurrence_breach",
        "policy_violation_code",
    ]

    if alerts.empty:
        out_disposition_csv.parent.mkdir(parents=True, exist_ok=True)
        report_out.parent.mkdir(parents=True, exist_ok=True)
        empty = pd.DataFrame(columns=expected_cols)
        empty.to_csv(out_disposition_csv, index=False)
        report_out.write_text("# OCO Alert Remediation Report\n\n_empty_\n", encoding="utf-8")
        return empty

    alerts = alerts.copy()
    alerts["symbol"] = alerts.get("symbol", pd.Series(dtype=str)).astype(str).str.upper()
    alerts["metric_id"] = alerts.get("metric_id", pd.Series(dtype=str)).astype(str)
    alerts["band"] = alerts.get("band", pd.Series(dtype=str)).astype(str).str.lower()
    alerts["severity"] = alerts.get("severity", pd.Series(dtype=str)).astype(str).str.lower()
    alerts["test_month"] = alerts.get("test_month", pd.Series(dtype=str)).astype(str)
    alerts["source_alert"] = [
        _normalize_source_alert(v, metric_id)
        for v, metric_id in zip(
            alerts.get("source_alert", pd.Series([""] * len(alerts))),
            alerts["metric_id"],
            strict=False,
        )
    ]
    all_alerts = alerts.copy()
    alerts = alerts[alerts["band"] != "green"].copy()

    cfg = _read_yaml(exceptions_yaml)
    default_days = int(cfg.get("default_expiry_days", 60))
    max_amber_consecutive = int(cfg.get("max_amber_consecutive_runs", 3))
    max_amber_months = int(cfg.get("max_amber_months", 6))
    require_owner = _bool_cfg(cfg, "require_owner", True)
    require_rationale = _bool_cfg(cfg, "require_rationale", True)
    require_evidence_link = _bool_cfg(cfg, "require_evidence_link", True)
    hard_fail_expired = _bool_cfg(cfg, "hard_fail_on_expired_exception", True)
    hard_fail_recurrence = _bool_cfg(cfg, "hard_fail_on_recurrence_breach", True)
    rules = cfg.get("rules", []) if isinstance(cfg.get("rules", []), list) else []
    now = datetime.now(timezone.utc)

    prev = _read_csv(out_disposition_csv)
    prev_stats: dict[str, dict[str, Any]] = {}
    if not prev.empty and {"symbol", "metric_id"}.issubset(set(prev.columns)):
        p = prev.copy()
        p["symbol"] = p["symbol"].astype(str).str.upper()
        p["metric_id"] = p["metric_id"].astype(str)
        if "consecutive_runs_non_green" not in p.columns:
            p["consecutive_runs_non_green"] = 1
        if "months_non_green_count" not in p.columns:
            p["months_non_green_count"] = 1
        if "first_seen_utc" not in p.columns:
            p["first_seen_utc"] = ""
        if "last_seen_utc" not in p.columns:
            p["last_seen_utc"] = ""
        for (sym, mid), g in p.groupby(["symbol", "metric_id"]):
            key = _key(sym, mid)
            prev_stats[key] = {
                "consecutive": int(
                    pd.to_numeric(g["consecutive_runs_non_green"], errors="coerce").fillna(1).max()
                ),
                "months": int(
                    pd.to_numeric(g["months_non_green_count"], errors="coerce").fillna(1).max()
                ),
                "first_seen_utc": str(g["first_seen_utc"].dropna().astype(str).iloc[0])
                if g["first_seen_utc"].notna().any()
                else "",
                "last_seen_utc": str(g["last_seen_utc"].dropna().astype(str).iloc[-1])
                if g["last_seen_utc"].notna().any()
                else "",
            }

    months_by_key: dict[str, int] = {}
    if not alerts.empty:
        for (sym, mid), g in alerts.groupby(["symbol", "metric_id"]):
            non_empty_months = g["test_month"].astype(str)
            non_empty_months = non_empty_months[non_empty_months.str.strip() != ""]
            months_by_key[_key(sym, mid)] = int(non_empty_months.nunique())

    latest_test_month_by_scope: dict[tuple[str, str], str] = {}
    if not all_alerts.empty:
        for (source_alert, sym), g in all_alerts.groupby(["source_alert", "symbol"]):
            months = pd.to_datetime(g["test_month"], format="%Y-%m", errors="coerce")
            if months.notna().any():
                latest_test_month_by_scope[(str(source_alert), str(sym))] = months.max().strftime(
                    "%Y-%m"
                )

    out_rows: list[dict[str, Any]] = []
    for _, r in alerts.iterrows():
        symbol = str(r.get("symbol", "")).upper()
        metric_id = str(r.get("metric_id", ""))
        k = _key(symbol, metric_id)

        matched: dict[str, Any] | None = None
        for rule in rules:
            if isinstance(rule, dict) and _rule_match(rule, symbol=symbol, metric_id=metric_id):
                matched = rule
                break

        if matched is None:
            status = "remediated"
            owner = "research"
            rationale = "No explicit exception rule; remediation required."
            evidence_link = str(r.get("source_path", "")).strip()
            action_code = (
                "A1_RECALIBRATE_CAP"
                if metric_id.startswith("E_DRIFT_")
                else "A2_RECALIBRATE_THRESHOLD"
            )
            sla_days = int(default_days)
        else:
            status = str(matched.get("disposition", "accepted_exception")).strip().lower()
            owner = str(matched.get("owner", "research")).strip()
            rationale = str(matched.get("rationale", "approved monitoring exception")).strip()
            evidence_link = (
                str(matched.get("evidence_link", "")).strip()
                or str(r.get("source_path", "")).strip()
            )
            if metric_id.startswith("E_DRIFT_"):
                action_code = "A2_SESSION_GUARD"
            elif metric_id.startswith("TS03"):
                action_code = "A1_RECALIBRATE_CAP"
            else:
                action_code = "A0_MONITOR"
            sla_days = int(matched.get("review_cadence_days", default_days))

        prev_rec = prev_stats.get(k, {})
        prev_consecutive = int(prev_rec.get("consecutive", 0))
        prev_last_seen_raw = str(prev_rec.get("last_seen_utc", "")).strip()
        prev_last_seen = (
            pd.to_datetime(pd.Series([prev_last_seen_raw]), utc=True, errors="coerce").iloc[0]
            if prev_last_seen_raw
            else pd.NaT
        )
        increment_run = True
        if pd.notna(prev_last_seen):
            increment_run = bool(prev_last_seen.date() < now.date())
        consecutive_runs = (prev_consecutive + 1) if increment_run else max(1, prev_consecutive)
        months_non_green = max(int(prev_rec.get("months", 0)), int(months_by_key.get(k, 1)))
        first_seen_utc = str(prev_rec.get("first_seen_utc", "")).strip() or now.strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )
        last_seen_utc = now.strftime("%Y-%m-%dT%H:%M:%SZ")

        exp = now + timedelta(days=max(1, int(sla_days)))
        expires_utc = exp.strftime("%Y-%m-%dT%H:%M:%SZ")
        is_expired = exp < now

        source_alert = _normalize_source_alert(r.get("source_alert", ""), metric_id)
        latest_scope_month = latest_test_month_by_scope.get((source_alert, symbol), "")
        row_test_month = str(r.get("test_month", "")).strip()
        is_current_scope_row = (
            row_test_month == ""
            or latest_scope_month == ""
            or row_test_month == latest_scope_month
        )
        recurrence_applies = status != "accepted_exception" and is_current_scope_row
        recurrence_breach = recurrence_applies and (
            (consecutive_runs > max_amber_consecutive) or (months_non_green > max_amber_months)
        )
        expiry_breach = bool(status == "accepted_exception" and is_expired)

        block = (expiry_breach and hard_fail_expired) or (
            recurrence_breach and hard_fail_recurrence
        )
        if block:
            escalation_level = "block"
        elif str(r.get("band", "")).lower() in {"amber", "red"}:
            escalation_level = "warn"
        else:
            escalation_level = "monitor"

        evidence_required = bool(require_evidence_link or escalation_level == "block")

        violations: list[str] = []
        if require_owner and (owner == ""):
            violations.append("missing_owner")
        if require_rationale and (rationale == ""):
            violations.append("missing_rationale")
        if evidence_required and (evidence_link == ""):
            violations.append("missing_evidence_link")
        if expiry_breach:
            violations.append("expired_exception")
        if recurrence_breach:
            violations.append("recurrence_limit_exceeded")

        days_to_expiry = float((exp - now).total_seconds() / 86400.0)
        out_rows.append(
            {
                "symbol": symbol,
                "source_alert": source_alert,
                "test_month": str(r.get("test_month", "")),
                "metric_id": metric_id,
                "metric_value": pd.to_numeric(
                    pd.Series([r.get("metric_value")]), errors="coerce"
                ).iloc[0],
                "band": str(r.get("band", "")),
                "severity": str(r.get("severity", "")),
                "status": status,
                "action_code": action_code,
                "owner": owner,
                "rationale": rationale,
                "expires_utc": expires_utc,
                "is_expired": bool(is_expired),
                "source_path": str(r.get("source_path", "")),
                "evaluated_at_utc": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "first_seen_utc": first_seen_utc,
                "last_seen_utc": last_seen_utc,
                "consecutive_runs_non_green": int(consecutive_runs),
                "months_non_green_count": int(months_non_green),
                "sla_days": int(sla_days),
                "days_to_expiry": days_to_expiry,
                "escalation_level": escalation_level,
                "evidence_required": evidence_required,
                "evidence_link": evidence_link,
                "expiry_breach": bool(expiry_breach),
                "recurrence_breach": bool(recurrence_breach),
                "policy_violation_code": ";".join(violations),
            }
        )

    disposition = pd.DataFrame(out_rows)

    out_disposition_csv.parent.mkdir(parents=True, exist_ok=True)
    report_out.parent.mkdir(parents=True, exist_ok=True)
    disposition.to_csv(out_disposition_csv, index=False)

    summary = (
        disposition.groupby(["source_alert", "status", "band", "escalation_level"], as_index=False)
        .agg(rows=("metric_id", "count"))
        .sort_values(["source_alert", "status", "band", "escalation_level"])
        if not disposition.empty
        else pd.DataFrame(columns=["source_alert", "status", "band", "escalation_level", "rows"])
    )
    violations = (
        disposition[disposition["policy_violation_code"].astype(str).str.strip() != ""]
        if not disposition.empty
        else pd.DataFrame(columns=disposition.columns.tolist())
    )

    lines: list[str] = []
    lines.append("# OCO Alert Remediation Report")
    lines.append("")
    lines.append(f"- generated_at_utc: `{now.strftime('%Y-%m-%dT%H:%M:%SZ')}`")
    lines.append(f"- drift_alerts_csv: `{drift_alerts_csv}`")
    lines.append(f"- threshold_alerts_csv: `{threshold_alerts_csv}`")
    lines.append(f"- ftmo_alerts_csv: `{ftmo_alerts_csv}`")
    lines.append(f"- exceptions_yaml: `{exceptions_yaml}`")
    lines.append(f"- disposition_csv: `{out_disposition_csv}`")
    lines.append("")
    lines.append("## Summary")
    lines.append(_table(summary))
    lines.append("")
    lines.append("## Policy Violations")
    lines.append(_table(violations))
    lines.append("")
    lines.append("## Dispositions")
    lines.append(_table(disposition))
    report_out.write_text("\n".join(lines), encoding="utf-8")
    return disposition


def main() -> None:
    p = argparse.ArgumentParser(description="Build OCO alert disposition report")
    p.add_argument(
        "--drift-alerts-csv",
        default="data/analysis/tick_opportunity_mining/oco_execution_drift_alerts.csv",
    )
    p.add_argument(
        "--threshold-alerts-csv",
        default="data/analysis/tick_opportunity_mining/oco_threshold_sensitivity_alerts.csv",
    )
    p.add_argument(
        "--ftmo-alerts-csv",
        default="data/analysis/tick_opportunity_mining/ftmo_allocator_monitoring_alerts.csv",
    )
    p.add_argument(
        "--exceptions-yaml", default="configs/research/governance/oco_monitoring_exceptions.yaml"
    )
    p.add_argument(
        "--out-disposition-csv",
        default="data/analysis/tick_opportunity_mining/oco_alert_disposition.csv",
    )
    p.add_argument("--report-out", default="docs/analysis/oco_alert_remediation_report.md")
    args = p.parse_args()

    d = run(
        drift_alerts_csv=Path(str(args.drift_alerts_csv)),
        threshold_alerts_csv=Path(str(args.threshold_alerts_csv)),
        ftmo_alerts_csv=Path(str(args.ftmo_alerts_csv)),
        exceptions_yaml=Path(str(args.exceptions_yaml)),
        out_disposition_csv=Path(str(args.out_disposition_csv)),
        report_out=Path(str(args.report_out)),
    )
    print(f"wrote disposition: {args.out_disposition_csv} rows={len(d)}")


if __name__ == "__main__":
    main()
