#!/usr/bin/env python3
"""Build OCO system-reference docs with rolling historical evidence blocks."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

SYMBOLS = ["EURUSD", "GBPUSD", "USDJPY"]

PAGES: list[dict[str, Any]] = [
    {
        "key": "ARCHITECTURE",
        "path": "architecture.md",
        "title": "Architecture",
        "summary": [
            "The active system is a stage-governed OCO research pipeline.",
            "Stop-limit execution realism and governance contracts are mandatory controls.",
        ],
    },
    {
        "key": "API",
        "path": "api.md",
        "title": "API",
        "summary": [
            "API runtime is optional; core OCO governance runs from artifacts and stage scripts.",
            "Any execution adapter must honor Stage 4 stop-limit and Stage 9 lock contracts.",
        ],
    },
    {
        "key": "API_REFERENCE",
        "path": "api_reference.md",
        "title": "API Reference",
        "summary": [
            "Reference modules under services/api are integration support, not strategy source of truth.",
            "Strategy behavior is defined by stage contracts and rolling evidence artifacts.",
        ],
    },
    {
        "key": "OPENAPI",
        "path": "openapi.md",
        "title": "OpenAPI",
        "summary": [
            "OpenAPI is optional and only needed for integration deployments.",
            "OCO strategy governance remains artifact-first with stop-limit execution evidence.",
        ],
    },
    {
        "key": "CORE_REFERENCE",
        "path": "core_reference.md",
        "title": "Core Reference",
        "summary": [
            "Core behavior is controlled by OCO stage scripts and governance checks.",
            "Stop-limit realism and rolling WFO controls define execution suitability.",
        ],
    },
    {
        "key": "RISK_CONTROLS",
        "path": "risk_controls.md",
        "title": "Risk Controls",
        "summary": [
            "Risk controls are stage-based gates (execution drift, robustness, governance remediation).",
            "Stop-limit degradation and governance exceptions are explicit block/review pathways.",
        ],
    },
    {
        "key": "MONITORING",
        "path": "monitoring.md",
        "title": "Monitoring",
        "summary": [
            "Monitoring is driven by rolling artifact diagnostics and remediation ownership.",
            "Stop-limit execution drift metrics are daily critical signals.",
        ],
    },
    {
        "key": "DATA_PIPELINE",
        "path": "data_pipeline.md",
        "title": "Data Pipeline",
        "summary": [
            "Pipeline is raw ticks -> candidate mining -> monthly WFO -> stop-limit realism -> governance.",
            "Causality is enforced by rolling historical ordering and contract checks.",
        ],
    },
    {
        "key": "VALIDATION",
        "path": "validation.md",
        "title": "Validation",
        "summary": [
            "Validation combines stage integrity, docs contract gates, and execution robustness.",
            "Rolling evidence recency is required before operational interpretation.",
        ],
    },
    {
        "key": "CONFIG_REFERENCE",
        "path": "config_reference.md",
        "title": "Config Reference",
        "summary": [
            "Research/governance configs drive the active OCO system.",
            "Policy changes require refreshed rolling evidence and docs-contract pass.",
        ],
    },
    {
        "key": "CODE_REFERENCE",
        "path": "code_reference.md",
        "title": "Code Reference",
        "summary": [
            "Active code path is script-orchestrated OCO stage execution.",
            "Legacy API/DB modules are optional integration components.",
        ],
    },
    {
        "key": "DEVELOPMENT",
        "path": "development.md",
        "title": "Development",
        "summary": [
            "Default development loop is change -> regenerate artifacts -> validate contracts -> rebuild docs.",
            "Stop-limit and rolling governance checks are part of standard acceptance.",
        ],
    },
    {
        "key": "DEPLOYMENT",
        "path": "deployment.md",
        "title": "Deployment",
        "summary": [
            "Promotion requires Stage 4 stop-limit realism + Stage 9 governance lock alignment.",
            "Rolling evidence and remediation status must be current at deploy decision time.",
        ],
    },
    {
        "key": "MAKEFILE",
        "path": "makefile.md",
        "title": "Makefile Reference",
        "summary": [
            "Make targets enforce docs-contract and governance regeneration flow.",
            "CI-safe runs are expected for recurring rolling evidence updates.",
        ],
    },
    {
        "key": "DB_SCHEMA",
        "path": "db_schema.md",
        "title": "Persistence Schema",
        "summary": [
            "Active persistence is artifact-based (CSV/Parquet/Markdown) for OCO governance.",
            "Relational schema remains optional integration support.",
        ],
    },
    {
        "key": "DB_SCHEMA_DIAGRAM",
        "path": "db_schema_diagram.md",
        "title": "Persistence Diagram",
        "summary": [
            "Artifact contract path is the mandatory operational flow for OCO governance.",
            "Optional DB path does not supersede stop-limit and stage-contract evidence.",
        ],
    },
]

MANDATORY_ARTIFACTS = [
    "data/analysis/tick_opportunity_mining/oco_execution_drift_monthly.csv",
    "data/analysis/tick_opportunity_mining/oco_threshold_sensitivity.csv",
    "data/analysis/tick_opportunity_mining/operator_action_status.csv",
    "data/analysis/tick_opportunity_mining/oco_alert_disposition.csv",
    "data/analysis/tick_opportunity_mining/execution_mc_symbol_scenarios.csv",
    "data/analysis/tick_opportunity_mining/docs_contract_checks.csv",
    "data/analysis/tick_opportunity_mining/run_delta_summary.csv",
]


def _table(df: pd.DataFrame) -> str:
    if df.empty:
        return "| status | detail |\n| --- | --- |\n| unavailable | no rolling data available |"
    try:
        return df.to_markdown(index=False)
    except Exception:
        return "```\n" + df.to_string(index=False) + "\n```"


def _read_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    try:
        return pd.read_csv(path)
    except Exception:
        return pd.DataFrame()


def _fmt(v: Any, digits: int = 4) -> Any:
    try:
        x = float(v)
    except Exception:
        return ""
    if pd.isna(x):
        return ""
    return round(x, digits)


def _latest_by_symbol(df: pd.DataFrame, month_col: str) -> pd.DataFrame:
    if df.empty or month_col not in df.columns or "symbol" not in df.columns:
        return pd.DataFrame()
    x = df.copy()
    x["symbol"] = x["symbol"].astype(str).str.upper()
    x[month_col] = x[month_col].astype(str)
    x = x.sort_values(["symbol", month_col])
    return x.groupby("symbol", as_index=False).tail(1).reset_index(drop=True)


def _reduced_core_latest_rows(data_root: Path) -> pd.DataFrame:
    patterns = [
        "reduced_core_rolling/*_oco_reduced_monthly.csv",
        "reduced_core_rolling_gbpusd/*_oco_reduced_monthly.csv",
        "reduced_core_rolling_usdjpy/*_oco_reduced_monthly.csv",
    ]
    rows: list[pd.DataFrame] = []
    for pat in patterns:
        for p in sorted((data_root / "tick_opportunity_mining").glob(pat)):
            df = _read_csv(p)
            if df.empty:
                continue
            if "symbol" not in df.columns or "test_month" not in df.columns:
                continue
            df["symbol"] = df["symbol"].astype(str).str.upper()
            df["test_month"] = df["test_month"].astype(str)
            rows.append(df.sort_values(["symbol", "test_month"]).groupby("symbol", as_index=False).tail(1))
    if not rows:
        return pd.DataFrame()
    out = pd.concat(rows, ignore_index=True)
    out = out.sort_values(["symbol", "test_month"]).groupby("symbol", as_index=False).tail(1).reset_index(drop=True)
    return out


def _build_snapshot_tables(*, repo_root: Path, data_root: Path) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, list[str]]:
    drift = _read_csv(data_root / "tick_opportunity_mining" / "oco_execution_drift_monthly.csv")
    threshold = _read_csv(data_root / "tick_opportunity_mining" / "oco_threshold_sensitivity.csv")
    actions = _read_csv(data_root / "tick_opportunity_mining" / "operator_action_status.csv")
    disposition = _read_csv(data_root / "tick_opportunity_mining" / "oco_alert_disposition.csv")
    mc = _read_csv(data_root / "tick_opportunity_mining" / "execution_mc_symbol_scenarios.csv")
    checks = _read_csv(data_root / "tick_opportunity_mining" / "docs_contract_checks.csv")
    run_delta = _read_csv(data_root / "tick_opportunity_mining" / "run_delta_summary.csv")
    reduced = _reduced_core_latest_rows(data_root)

    drift_last = _latest_by_symbol(drift, "test_month")
    if not threshold.empty:
        t = threshold.copy()
        t["symbol"] = t.get("symbol", pd.Series(dtype=str)).astype(str).str.upper()
        t["is_current_policy"] = pd.to_numeric(t.get("is_current_policy"), errors="coerce").fillna(0)
        cur = t[t["is_current_policy"] > 0].copy()
        if cur.empty:
            cur = (
                t.sort_values(["symbol", "final_score"], ascending=[True, False]).groupby("symbol", as_index=False).head(1)
                if {"symbol", "final_score"}.issubset(set(t.columns))
                else pd.DataFrame()
            )
        threshold_cur = cur
    else:
        threshold_cur = pd.DataFrame()

    if not mc.empty:
        m = mc.copy()
        m["symbol"] = m.get("symbol", pd.Series(dtype=str)).astype(str).str.upper()
        m["scenario_id"] = m.get("scenario_id", pd.Series(dtype=str)).astype(str)
        mc_s1 = m[m["scenario_id"] == "S1_mild"].copy()
    else:
        mc_s1 = pd.DataFrame()

    if not actions.empty:
        a = actions.copy()
        a["symbol"] = a.get("symbol", pd.Series(dtype=str)).astype(str).str.upper()
        a["band"] = a.get("band", pd.Series(dtype=str)).astype(str).str.lower()
        a = a[a["band"].isin(["amber", "red"])].copy()
        action_counts = a.groupby("symbol", as_index=False).agg(non_green_actions=("metric_id", "count"))
    else:
        action_counts = pd.DataFrame(columns=["symbol", "non_green_actions"])

    if not disposition.empty:
        d = disposition.copy()
        d["symbol"] = d.get("symbol", pd.Series(dtype=str)).astype(str).str.upper()
        d["band"] = d.get("band", pd.Series(dtype=str)).astype(str).str.lower()
        d = d[d["band"].isin(["amber", "red"])].copy()
        disp_counts = d.groupby("symbol", as_index=False).agg(non_green_alerts=("metric_id", "count"))
    else:
        disp_counts = pd.DataFrame(columns=["symbol", "non_green_alerts"])

    def _symbol_row(df: pd.DataFrame, sym: str) -> pd.DataFrame:
        if df.empty or "symbol" not in df.columns:
            return pd.DataFrame()
        return df[df["symbol"] == sym].head(1)

    rows: list[dict[str, Any]] = []
    for sym in SYMBOLS:
        row: dict[str, Any] = {"symbol": sym}

        dr = _symbol_row(drift_last, sym)
        if not dr.empty:
            row["latest_month"] = str(dr.iloc[0].get("test_month", ""))
            row["drift_fill_rate"] = _fmt(dr.iloc[0].get("fill_rate"), 4)
            row["drift_overshoot_p95"] = _fmt(dr.iloc[0].get("overshoot_p95_pips"), 4)
        else:
            row["latest_month"] = ""
            row["drift_fill_rate"] = ""
            row["drift_overshoot_p95"] = ""

        tr = _symbol_row(threshold_cur, sym)
        row["w13_fragility"] = _fmt(tr.iloc[0].get("w13_threshold_fragility"), 4) if not tr.empty else ""
        row["policy_quantile"] = _fmt(tr.iloc[0].get("quantile"), 2) if not tr.empty else ""

        mr = _symbol_row(mc_s1, sym)
        row["mc_s1_lb95"] = _fmt(mr.iloc[0].get("lb95_per_signal_pips"), 4) if not mr.empty else ""

        rr = _symbol_row(reduced, sym)
        row["reduced_mean_gross"] = _fmt(rr.iloc[0].get("mean_gross_pips"), 4) if not rr.empty else ""

        ar = _symbol_row(action_counts, sym)
        row["non_green_actions"] = int(ar.iloc[0].get("non_green_actions", 0)) if not ar.empty else 0

        nr = _symbol_row(disp_counts, sym)
        row["non_green_alerts"] = int(nr.iloc[0].get("non_green_alerts", 0)) if not nr.empty else 0

        rows.append(row)

    by_symbol = pd.DataFrame(rows)

    trend_rows: list[dict[str, Any]] = []
    if not drift.empty and {"symbol", "test_month", "fill_rate", "overshoot_p95_pips"}.issubset(set(drift.columns)):
        dd = drift.copy()
        dd["symbol"] = dd["symbol"].astype(str).str.upper()
        dd["test_month"] = dd["test_month"].astype(str)
        for sym in SYMBOLS:
            g = dd[dd["symbol"] == sym].sort_values("test_month").tail(3)
            if g.empty:
                trend_rows.append({"symbol": sym, "months_used": 0, "fill_rate_mean_3m": "", "overshoot_p95_mean_3m": ""})
                continue
            trend_rows.append(
                {
                    "symbol": sym,
                    "months_used": int(len(g)),
                    "fill_rate_mean_3m": _fmt(g["fill_rate"].mean(), 4),
                    "overshoot_p95_mean_3m": _fmt(g["overshoot_p95_pips"].mean(), 4),
                }
            )
    else:
        trend_rows = [{"symbol": s, "months_used": 0, "fill_rate_mean_3m": "", "overshoot_p95_mean_3m": ""} for s in SYMBOLS]
    trend = pd.DataFrame(trend_rows)

    failed = 0
    high_critical_failed = 0
    max_age_c6 = ""
    if not checks.empty and "status" in checks.columns:
        c = checks.copy()
        c["status"] = c["status"].astype(str).str.lower()
        failed = int((c["status"] != "pass").sum())
        if "severity_if_fail" in c.columns:
            high_critical_failed = int(
                ((c["status"] != "pass") & c["severity_if_fail"].astype(str).str.lower().isin(["high", "critical"])).sum()
            )
        c6 = c[c.get("check_id", pd.Series(dtype=str)).astype(str) == "C6"]
        if not c6.empty:
            max_age_c6 = _fmt(c6.iloc[0].get("metric_value"), 6)

    delta_row = run_delta.head(1) if not run_delta.empty else pd.DataFrame()
    gov = pd.DataFrame(
        [
            {
                "checks_failed": failed,
                "high_critical_failed": high_critical_failed,
                "max_age_hours_c6": max_age_c6,
                "run_delta_metric_rows_changed": int(delta_row.iloc[0].get("metric_rows_changed", 0))
                if not delta_row.empty
                else 0,
                "run_delta_gate_rows_changed": int(delta_row.iloc[0].get("gate_rows_changed", 0))
                if not delta_row.empty
                else 0,
            }
        ]
    )

    artifact_sources = [p for p in MANDATORY_ARTIFACTS if (repo_root / p).exists()]
    return by_symbol, trend, gov, artifact_sources


def _generated_block(
    *,
    key: str,
    by_symbol: pd.DataFrame,
    trend: pd.DataFrame,
    gov: pd.DataFrame,
    artifact_sources: list[str],
    generated_at_utc: str,
) -> str:
    lines: list[str] = []
    lines.append(f"- generated_at_utc: `{generated_at_utc}`")
    lines.append(f"- symbols_covered: `{','.join(SYMBOLS)}`")
    lines.append("- stop-limit_reference: `stage_04_execution_realism`")
    lines.append("- artifact_sources:")
    if artifact_sources:
        for p in artifact_sources:
            lines.append(f"  - `{p}`")
    else:
        lines.append("  - `unavailable`")
    lines.append("")
    lines.append("#### Rolling Snapshot By Symbol")
    lines.append(_table(by_symbol))
    lines.append("")
    lines.append("#### Rolling Trend (Last 3 Months)")
    lines.append(_table(trend))
    lines.append("")
    lines.append("#### Governance Snapshot")
    lines.append(_table(gov))
    start = f"<!-- GENERATED:SYSREF:{key}:START -->"
    end = f"<!-- GENERATED:SYSREF:{key}:END -->"
    return start + "\n" + "\n".join(lines).strip() + "\n" + end


def _inject_block(path: Path, key: str, block: str) -> None:
    start = f"<!-- GENERATED:SYSREF:{key}:START -->"
    end = f"<!-- GENERATED:SYSREF:{key}:END -->"
    text = path.read_text(encoding="utf-8", errors="ignore") if path.exists() else ""
    if start in text and end in text and text.find(start) < text.find(end):
        i = text.find(start)
        new_text = text[:i].rstrip() + "\n\n" + block + "\n"
    else:
        base = text.rstrip()
        if not base:
            base = f"# {path.stem.replace('_', ' ').title()}"
        new_text = (
            base
            + "\n\n## Rolling Historical Evidence\n\n"
            + block
            + "\n"
        )
    path.write_text(new_text, encoding="utf-8")


def _ensure_page_shell(path: Path, title: str, summary: list[str]) -> None:
    if path.exists() and path.read_text(encoding="utf-8", errors="ignore").strip():
        return
    lines = [f"# {title}", "", "## Scope", ""]
    lines.extend([f"- {x}" for x in summary])
    lines.extend(
        [
            "",
            "## Operational Contract",
            "",
            "- stop-limit execution realism is mandatory for OCO suitability.",
            "- rolling evidence must be refreshed before decision use.",
            "",
            "## Rolling Historical Evidence",
            "",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def run(*, docs_root: Path, analysis_root: Path, out_status_csv: Path) -> pd.DataFrame:
    docs_dir = docs_root.resolve()
    repo_root = docs_dir.parent
    generated_at_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    by_symbol, trend, gov, artifact_sources = _build_snapshot_tables(repo_root=repo_root, data_root=analysis_root.parent)
    rows: list[dict[str, Any]] = []

    for spec in PAGES:
        path = Path(str(spec["path"]))
        if not path.is_absolute():
            path = (docs_dir / path).resolve()
        _ensure_page_shell(path, str(spec["title"]), list(spec["summary"]))
        block = _generated_block(
            key=str(spec["key"]),
            by_symbol=by_symbol,
            trend=trend,
            gov=gov,
            artifact_sources=artifact_sources,
            generated_at_utc=generated_at_utc,
        )
        _inject_block(path, str(spec["key"]), block)
        rows.append(
            {
                "page_key": str(spec["key"]),
                "doc_path": str(path.relative_to(repo_root).as_posix()),
                "generated_at_utc": generated_at_utc,
                "snapshot_rows": int(len(by_symbol)),
                "trend_rows": int(len(trend)),
                "governance_rows": int(len(gov)),
                "artifact_source_count": int(len(artifact_sources)),
            }
        )

    out = pd.DataFrame(rows)
    out_status_csv.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(out_status_csv, index=False)
    return out


def main() -> None:
    p = argparse.ArgumentParser(description="Build OCO system reference docs with rolling evidence blocks")
    p.add_argument("--docs-root", default="docs")
    p.add_argument("--analysis-root", default="data/analysis")
    p.add_argument(
        "--out-status-csv",
        default="data/analysis/tick_opportunity_mining/system_reference_build_status.csv",
    )
    args = p.parse_args()

    out = run(
        docs_root=Path(str(args.docs_root)),
        analysis_root=Path(str(args.analysis_root)),
        out_status_csv=Path(str(args.out_status_csv)),
    )
    print(f"wrote system reference status: {args.out_status_csv} rows={len(out)}")


if __name__ == "__main__":
    main()
