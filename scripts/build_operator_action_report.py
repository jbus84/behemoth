#!/usr/bin/env python3
"""Build operator action matrix, report, and strategy playbook from metric rules."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import yaml


def _table(df: pd.DataFrame) -> str:
    if df.empty:
        return "_empty_"
    try:
        return df.to_markdown(index=False)
    except Exception:
        return "```\n" + df.to_string(index=False) + "\n```"


def _parse_symbols(raw: str) -> list[str]:
    out = [x.strip().upper() for x in str(raw).split(",") if x.strip()]
    return sorted(list(dict.fromkeys(out)))


def _read_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
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


def _evaluate(value: float, *, mode: str, warn: float, fail: float) -> str:
    if not np.isfinite(value):
        return "gray"
    v = float(value)
    if mode == "abs_ge":
        s = abs(v)
        if s >= float(fail):
            return "red"
        if s >= float(warn):
            return "amber"
        return "green"
    if mode == "ge":
        if v >= float(fail):
            return "red"
        if v >= float(warn):
            return "amber"
        return "green"
    if mode == "gt":
        if v > float(fail):
            return "red"
        if v > float(warn):
            return "amber"
        return "green"
    if mode == "le":
        if v <= float(fail):
            return "red"
        if v <= float(warn):
            return "amber"
        return "green"
    if mode == "lt":
        if v < float(fail):
            return "red"
        if v < float(warn):
            return "amber"
        return "green"
    return "gray"


def _severity_from_band(band: str) -> str:
    b = str(band).lower()
    if b == "green":
        return "info"
    if b == "amber":
        return "medium"
    return "high"


def run(
    *,
    edge_metrics_csv: Path,
    rules_yaml: Path,
    out_status_csv: Path,
    out_report_md: Path,
    out_playbook_md: Path,
    symbols: list[str] | None,
) -> tuple[pd.DataFrame, Path, Path]:
    metrics = _read_csv(edge_metrics_csv)
    if not metrics.empty:
        if "symbol" in metrics.columns:
            metrics["symbol"] = metrics["symbol"].astype(str).str.upper()
        metrics["metric_value"] = pd.to_numeric(metrics.get("metric_value"), errors="coerce")

    cfg = _read_yaml(rules_yaml)
    rules = cfg.get("rules", []) if isinstance(cfg.get("rules", []), list) else []
    rule_map: dict[str, dict[str, Any]] = {}
    for r in rules:
        if not isinstance(r, dict):
            continue
        mid = str(r.get("metric_id", "")).strip()
        if mid:
            rule_map[mid] = r

    action_defs = cfg.get("action_definitions", {}) if isinstance(cfg.get("action_definitions"), dict) else {}

    syms: list[str]
    if symbols:
        syms = sorted(list(dict.fromkeys([s.upper() for s in symbols])))
    elif not metrics.empty and "symbol" in metrics.columns:
        syms = sorted(metrics["symbol"].dropna().astype(str).str.upper().unique().tolist())
    else:
        syms = ["ALL"]

    rows: list[dict[str, Any]] = []
    now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    for sym in syms:
        m_sym = metrics[metrics.get("symbol", pd.Series(dtype=str)).astype(str).str.upper() == sym].copy() if not metrics.empty else pd.DataFrame()
        for metric_id in sorted(rule_map.keys()):
            rule = rule_map[metric_id]
            m = m_sym[m_sym.get("metric_id", pd.Series(dtype=str)).astype(str) == metric_id].copy() if not m_sym.empty else pd.DataFrame()
            if m.empty:
                rows.append(
                    {
                        "symbol": sym,
                        "stage_id": pd.to_numeric(pd.Series([rule.get("stage_id")]), errors="coerce").iloc[0],
                        "metric_id": metric_id,
                        "metric_value": np.nan,
                        "mode": str(rule.get("mode", "")),
                        "warn_threshold": pd.to_numeric(pd.Series([rule.get("warn")]), errors="coerce").iloc[0],
                        "fail_threshold": pd.to_numeric(pd.Series([rule.get("fail")]), errors="coerce").iloc[0],
                        "band": "gray",
                        "severity": "high",
                        "action_code": "A9_DATA_GAP",
                        "action_summary": "metric not present in stage metrics",
                        "owner": str(rule.get("owner", "research")),
                        "rationale": str(rule.get("rationale", "")),
                        "source_path": "",
                        "evaluated_at_utc": now_utc,
                    }
                )
                continue

            x = m.iloc[0]
            val = float(pd.to_numeric(pd.Series([x.get("metric_value")]), errors="coerce").iloc[0])
            mode = str(rule.get("mode", "ge")).strip()
            warn = float(pd.to_numeric(pd.Series([rule.get("warn", np.nan)]), errors="coerce").iloc[0])
            fail = float(pd.to_numeric(pd.Series([rule.get("fail", np.nan)]), errors="coerce").iloc[0])
            band = _evaluate(val, mode=mode, warn=warn, fail=fail)

            if band == "green":
                action_code = str(rule.get("action_green", "A0_MONITOR"))
                action_summary = str(rule.get("summary_green", "within policy band"))
            elif band == "amber":
                action_code = str(rule.get("action_warn", "A1_REVIEW"))
                action_summary = str(rule.get("summary_warn", "review and monitor"))
            elif band == "red":
                action_code = str(rule.get("action_fail", "A3_ESCALATE"))
                action_summary = str(rule.get("summary_fail", "escalate and remediate"))
            else:
                action_code = "A9_DATA_GAP"
                action_summary = "metric unavailable"

            rows.append(
                {
                    "symbol": sym,
                    "stage_id": pd.to_numeric(pd.Series([x.get("stage_id", rule.get("stage_id"))]), errors="coerce").iloc[0],
                    "metric_id": metric_id,
                    "metric_value": val,
                    "mode": mode,
                    "warn_threshold": warn,
                    "fail_threshold": fail,
                    "band": band,
                    "severity": _severity_from_band(band),
                    "action_code": action_code,
                    "action_summary": action_summary,
                    "owner": str(rule.get("owner", "research")),
                    "rationale": str(rule.get("rationale", "")),
                    "source_path": str(x.get("source_path", "")),
                    "evaluated_at_utc": now_utc,
                }
            )

    status = pd.DataFrame(rows)
    if status.empty:
        status = pd.DataFrame(
            columns=[
                "symbol",
                "stage_id",
                "metric_id",
                "metric_value",
                "mode",
                "warn_threshold",
                "fail_threshold",
                "band",
                "severity",
                "action_code",
                "action_summary",
                "owner",
                "rationale",
                "source_path",
                "evaluated_at_utc",
            ]
        )

    summary = (
        status.groupby(["symbol", "band"], as_index=False)
        .agg(metrics=("metric_id", "count"))
        .sort_values(["symbol", "band"])
        if not status.empty
        else pd.DataFrame(columns=["symbol", "band", "metrics"])
    )
    red_amber = status[status["band"].isin(["red", "amber"])].copy().sort_values(["band", "symbol", "metric_id"]) if not status.empty else pd.DataFrame()

    out_status_csv.parent.mkdir(parents=True, exist_ok=True)
    out_report_md.parent.mkdir(parents=True, exist_ok=True)
    out_playbook_md.parent.mkdir(parents=True, exist_ok=True)
    status.to_csv(out_status_csv, index=False)

    report_lines: list[str] = []
    report_lines.append("# OCO Operator Action Report")
    report_lines.append("")
    report_lines.append(f"- generated_at_utc: `{now_utc}`")
    report_lines.append(f"- edge_metrics_csv: `{edge_metrics_csv}`")
    report_lines.append(f"- rules_yaml: `{rules_yaml}`")
    report_lines.append(f"- status_csv: `{out_status_csv}`")
    report_lines.append("")
    report_lines.append("## Action Matrix")
    report_lines.append(_table(summary))
    report_lines.append("")
    report_lines.append("## Escalations (Amber/Red)")
    report_lines.append(_table(red_amber))
    report_lines.append("")
    report_lines.append("## Full Status")
    report_lines.append(_table(status))
    out_report_md.write_text("\n".join(report_lines), encoding="utf-8")

    pb_lines: list[str] = []
    pb_lines.append("# OCO Operator Playbook")
    pb_lines.append("")
    pb_lines.append(f"- generated_at_utc: `{now_utc}`")
    pb_lines.append(f"- source_rules: `{rules_yaml}`")
    pb_lines.append("")
    pb_lines.append("## Action Codes")
    if action_defs:
        rows_defs = []
        for code, desc in sorted(action_defs.items()):
            rows_defs.append({"action_code": str(code), "description": str(desc)})
        pb_lines.append(_table(pd.DataFrame(rows_defs)))
    else:
        pb_lines.append("_empty_")
    pb_lines.append("")
    pb_lines.append("## Operator Checklist")
    pb_lines.append("1. Review `operator_action_status.csv` after each full pipeline run.")
    pb_lines.append("2. Execute all `red` actions before deployment decisions.")
    pb_lines.append("3. Open a remediation task for persistent `amber` metrics (>=3 consecutive runs).")
    pb_lines.append("4. Block deployment if any `A3_` action remains unresolved.")
    pb_lines.append("")
    pb_lines.append("## Current Escalations")
    pb_lines.append(_table(red_amber[["symbol", "metric_id", "band", "action_code", "owner", "action_summary"]] if not red_amber.empty else red_amber))
    out_playbook_md.write_text("\n".join(pb_lines), encoding="utf-8")

    return status, out_report_md, out_playbook_md


def main() -> None:
    p = argparse.ArgumentParser(description="Build operator action report and playbook")
    p.add_argument("--edge-metrics-csv", default="data/analysis/tick_opportunity_mining/edge_clarity_stage_metrics.csv")
    p.add_argument("--rules-yaml", default="configs/research/docs/operator_action_rules.yaml")
    p.add_argument("--symbols", default="EURUSD,GBPUSD,USDJPY")
    p.add_argument("--out-status-csv", default="data/analysis/tick_opportunity_mining/operator_action_status.csv")
    p.add_argument("--report-out", default="docs/analysis/operator_action_report.md")
    p.add_argument("--playbook-out", default="docs/strategy_bible/operator_playbook.md")
    args = p.parse_args()

    symbols = _parse_symbols(args.symbols)
    status, report, playbook = run(
        edge_metrics_csv=Path(str(args.edge_metrics_csv)),
        rules_yaml=Path(str(args.rules_yaml)),
        out_status_csv=Path(str(args.out_status_csv)),
        out_report_md=Path(str(args.report_out)),
        out_playbook_md=Path(str(args.playbook_out)),
        symbols=symbols,
    )
    print(f"wrote status: {args.out_status_csv} rows={len(status)}")
    print(f"wrote report: {report}")
    print(f"wrote playbook: {playbook}")


if __name__ == "__main__":
    main()
