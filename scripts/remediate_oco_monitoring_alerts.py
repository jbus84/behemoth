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
    syms = [str(x).upper() for x in rule.get("symbols", [])] if isinstance(rule.get("symbols", []), list) else []
    if not syms:
        return True
    return str(symbol).upper() in syms


def run(
    *,
    drift_alerts_csv: Path,
    threshold_alerts_csv: Path,
    exceptions_yaml: Path,
    out_disposition_csv: Path,
    report_out: Path,
) -> pd.DataFrame:
    d1 = _read_csv(drift_alerts_csv)
    d2 = _read_csv(threshold_alerts_csv)
    alerts = pd.concat([d1, d2], ignore_index=True) if (not d1.empty or not d2.empty) else pd.DataFrame()
    if alerts.empty:
        out_disposition_csv.parent.mkdir(parents=True, exist_ok=True)
        report_out.parent.mkdir(parents=True, exist_ok=True)
        empty = pd.DataFrame(
            columns=[
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
            ]
        )
        empty.to_csv(out_disposition_csv, index=False)
        report_out.write_text("# OCO Alert Remediation Report\n\n_empty_\n", encoding="utf-8")
        return empty

    alerts = alerts.copy()
    alerts["symbol"] = alerts.get("symbol", pd.Series(dtype=str)).astype(str).str.upper()
    alerts["metric_id"] = alerts.get("metric_id", pd.Series(dtype=str)).astype(str)
    alerts["band"] = alerts.get("band", pd.Series(dtype=str)).astype(str).str.lower()
    alerts["severity"] = alerts.get("severity", pd.Series(dtype=str)).astype(str).str.lower()
    alerts["test_month"] = alerts.get("test_month", pd.Series(dtype=str)).astype(str)
    alerts = alerts[alerts["band"] != "green"].copy()

    cfg = _read_yaml(exceptions_yaml)
    default_days = int(cfg.get("default_expiry_days", 60))
    rules = cfg.get("rules", []) if isinstance(cfg.get("rules", []), list) else []
    now = datetime.now(timezone.utc)

    out_rows: list[dict[str, Any]] = []
    for _, r in alerts.iterrows():
        symbol = str(r.get("symbol", "")).upper()
        metric_id = str(r.get("metric_id", ""))
        matched: dict[str, Any] | None = None
        for rule in rules:
            if isinstance(rule, dict) and _rule_match(rule, symbol=symbol, metric_id=metric_id):
                matched = rule
                break
        if matched is None:
            status = "remediated"
            owner = "research"
            rationale = "No explicit exception rule; treat as remediation-required."
            action_code = "A1_RECALIBRATE_CAP" if metric_id.startswith("E_DRIFT_") else "A2_RECALIBRATE_THRESHOLD"
            exp = now + timedelta(days=int(default_days))
        else:
            status = str(matched.get("disposition", "accepted_exception")).strip().lower()
            owner = str(matched.get("owner", "research"))
            rationale = str(matched.get("rationale", "approved monitoring exception"))
            if metric_id.startswith("E_DRIFT_"):
                action_code = "A2_SESSION_GUARD"
            elif metric_id.startswith("TS03"):
                action_code = "A1_RECALIBRATE_CAP"
            else:
                action_code = "A0_MONITOR"
            exp_days = int(matched.get("review_cadence_days", default_days))
            exp = now + timedelta(days=max(1, exp_days))
        expires_utc = exp.strftime("%Y-%m-%dT%H:%M:%SZ")
        out_rows.append(
            {
                "symbol": symbol,
                "source_alert": "execution_drift" if metric_id.startswith("E_DRIFT_") else "threshold_sensitivity",
                "test_month": str(r.get("test_month", "")),
                "metric_id": metric_id,
                "metric_value": pd.to_numeric(pd.Series([r.get("metric_value")]), errors="coerce").iloc[0],
                "band": str(r.get("band", "")),
                "severity": str(r.get("severity", "")),
                "status": status,
                "action_code": action_code,
                "owner": owner,
                "rationale": rationale,
                "expires_utc": expires_utc,
                "is_expired": False,
                "source_path": str(r.get("source_path", "")),
                "evaluated_at_utc": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
            }
        )

    disposition = pd.DataFrame(out_rows)
    if not disposition.empty:
        exp = pd.to_datetime(disposition["expires_utc"], utc=True, errors="coerce")
        disposition["is_expired"] = exp.notna() & (exp < now)

    out_disposition_csv.parent.mkdir(parents=True, exist_ok=True)
    report_out.parent.mkdir(parents=True, exist_ok=True)
    disposition.to_csv(out_disposition_csv, index=False)

    summary = (
        disposition.groupby(["source_alert", "status", "band"], as_index=False).agg(rows=("metric_id", "count")).sort_values(["source_alert", "status", "band"])
        if not disposition.empty
        else pd.DataFrame(columns=["source_alert", "status", "band", "rows"])
    )
    lines: list[str] = []
    lines.append("# OCO Alert Remediation Report")
    lines.append("")
    lines.append(f"- generated_at_utc: `{now.strftime('%Y-%m-%dT%H:%M:%SZ')}`")
    lines.append(f"- drift_alerts_csv: `{drift_alerts_csv}`")
    lines.append(f"- threshold_alerts_csv: `{threshold_alerts_csv}`")
    lines.append(f"- exceptions_yaml: `{exceptions_yaml}`")
    lines.append(f"- disposition_csv: `{out_disposition_csv}`")
    lines.append("")
    lines.append("## Summary")
    lines.append(_table(summary))
    lines.append("")
    lines.append("## Dispositions")
    lines.append(_table(disposition))
    report_out.write_text("\n".join(lines), encoding="utf-8")
    return disposition


def main() -> None:
    p = argparse.ArgumentParser(description="Build OCO alert disposition report")
    p.add_argument("--drift-alerts-csv", default="data/analysis/tick_opportunity_mining/oco_execution_drift_alerts.csv")
    p.add_argument("--threshold-alerts-csv", default="data/analysis/tick_opportunity_mining/oco_threshold_sensitivity_alerts.csv")
    p.add_argument("--exceptions-yaml", default="configs/research/governance/oco_monitoring_exceptions.yaml")
    p.add_argument("--out-disposition-csv", default="data/analysis/tick_opportunity_mining/oco_alert_disposition.csv")
    p.add_argument("--report-out", default="docs/analysis/oco_alert_remediation_report.md")
    args = p.parse_args()

    d = run(
        drift_alerts_csv=Path(str(args.drift_alerts_csv)),
        threshold_alerts_csv=Path(str(args.threshold_alerts_csv)),
        exceptions_yaml=Path(str(args.exceptions_yaml)),
        out_disposition_csv=Path(str(args.out_disposition_csv)),
        report_out=Path(str(args.report_out)),
    )
    print(f"wrote disposition: {args.out_disposition_csv} rows={len(d)}")


if __name__ == "__main__":
    main()
