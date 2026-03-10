#!/usr/bin/env python3
"""Build governance explainability report for active non-green OCO monitoring alerts."""

from __future__ import annotations

import argparse
from contextlib import suppress
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

try:
    import yaml
except Exception:
    yaml = None  # type: ignore[assignment]


METRIC_META: dict[str, dict[str, str]] = {
    "E_DRIFT_FILL_DROP": {
        "definition": "Drop in touch/fill participation versus baseline months.",
        "risk_path": "Lower fill participation can reduce realized expectancy even when gross edge is stable.",
        "threshold_context": "Compared to configured warn/fail fill-drop thresholds in drift alerts.",
        "expected_recovery_signal": "Fill-rate drop returns below warn threshold for two consecutive runs.",
    },
    "E_DRIFT_NO_TOUCH": {
        "definition": "Increase in no-touch rate versus baseline months.",
        "risk_path": "More no-touch events reduce conversion of selected opportunities into trades.",
        "threshold_context": "Compared to configured warn/fail no-touch thresholds in drift alerts.",
        "expected_recovery_signal": "No-touch delta reverts to green band and monthly distribution normalizes.",
    },
    "E_DRIFT_OVERSHOOT_P50": {
        "definition": "Median overshoot drift versus baseline execution regime.",
        "risk_path": "Higher overshoot at median erodes stop-limit capture efficiency and net pips.",
        "threshold_context": "Compared to configured warn/fail overshoot p50 thresholds in drift alerts.",
        "expected_recovery_signal": "Median overshoot delta returns to green and cap policy remains stable.",
    },
    "E_DRIFT_OVERSHOOT_P95": {
        "definition": "Tail overshoot drift (95th percentile) versus baseline.",
        "risk_path": "Tail slippage events can dominate downside and invalidate execution assumptions.",
        "threshold_context": "Compared to configured warn/fail overshoot p95 thresholds in drift alerts.",
        "expected_recovery_signal": "Tail overshoot delta remains below warn threshold for follow-up runs.",
    },
    "TS01_W13_THRESHOLD_FRAGILITY": {
        "definition": "Sensitivity of selected population to threshold perturbations.",
        "risk_path": "High fragility indicates unstable selection behavior under small policy changes.",
        "threshold_context": "Derived from threshold sensitivity grid around active rolling policy.",
        "expected_recovery_signal": "Fragility falls within green band at current policy parameters.",
    },
    "TS02_W14_BRIER_DRIFT_STD": {
        "definition": "Calibration drift proxy for probability quality across policy grid.",
        "risk_path": "Poor calibration drift can weaken rank-quality of selection decisions.",
        "threshold_context": "Computed as drift std under lookback/cadence/window perturbations.",
        "expected_recovery_signal": "Brier drift remains near baseline with low variance across candidates.",
    },
    "TS03_LB95_MONTH_SIGNAL": {
        "definition": "Conservative lower bound of month mean per-signal performance.",
        "risk_path": "Negative/weak LB95 suggests policy may not sustain conservative profitability.",
        "threshold_context": "Evaluated under threshold sensitivity candidate grid.",
        "expected_recovery_signal": "LB95 per-signal returns to positive or target floor.",
    },
    "TS04_SELECTION_TURNOVER": {
        "definition": "Selection set turnover under policy perturbations.",
        "risk_path": "High turnover implies unstable deployment set and operational inconsistency.",
        "threshold_context": "Measured in threshold sensitivity report around active policy.",
        "expected_recovery_signal": "Turnover declines and selected set stabilizes run-over-run.",
    },
    "TS05_POLICY_GAP_LB95": {
        "definition": "LB95 gap between current policy and recommended alternatives.",
        "risk_path": "Large negative gap implies current policy may lag better robust settings.",
        "threshold_context": "Difference metric in threshold sensitivity candidate table.",
        "expected_recovery_signal": "Policy gap narrows or current policy aligns with recommended row.",
    },
    "FTMO_ALLOC_BLOCK_RATE": {
        "definition": "Share of preselected candidates blocked by the FTMO allocator budget layer.",
        "risk_path": "Persistently high block rate indicates reduced live opportunity capture.",
        "threshold_context": "Compared to warn/fail bands in FTMO allocator monitoring alerts.",
        "expected_recovery_signal": "Block rate returns to green with stable admitted coverage.",
    },
    "FTMO_ALLOC_BUDGET_EXCEEDED_RATE": {
        "definition": "Share of preselected candidates blocked due to reserved budget exhaustion.",
        "risk_path": "Frequent budget exhaustion suggests sizing/headroom mismatch under live flow.",
        "threshold_context": "Computed over recent allocator events using monitoring lookback window.",
        "expected_recovery_signal": "Budget-exceeded blocks drop below warn threshold.",
    },
    "FTMO_ALLOC_PIP_VALUE_UNAVAILABLE_RATE": {
        "definition": "Share of preselected candidates blocked by missing FX pip-value conversion.",
        "risk_path": "Conversion failures can suppress valid trades and indicate data path fragility.",
        "threshold_context": "Derived from allocator block reason FTMO_PIP_VALUE_UNAVAILABLE.",
        "expected_recovery_signal": "Conversion-unavailable block rate remains near zero.",
    },
    "FTMO_ALLOC_STALE_PENDING_COUNT": {
        "definition": "Count of pending reservations older than configured pending staleness horizon.",
        "risk_path": "Stale pending reservations can overstate reserved loss and throttle allocator capacity.",
        "threshold_context": "Counted against stale-pending warn/fail count bands.",
        "expected_recovery_signal": "Pending stale count returns to zero after reconciliation.",
    },
    "FTMO_ALLOC_OPEN_WITHOUT_BROKER_POS_COUNT": {
        "definition": "Count of OPEN reservations lacking linked broker position id.",
        "risk_path": "Unlinked open reservations imply lifecycle mismatch between allocator and execution ledger.",
        "threshold_context": "Counted directly from runtime reservation ledger.",
        "expected_recovery_signal": "All open reservations carry broker position linkage.",
    },
    "FTMO_ALLOC_ADMITTED_MISSING_RESERVATION_ID_COUNT": {
        "definition": "Count of admitted allocator decisions without valid reservation linkage.",
        "risk_path": "Missing reservation linkage weakens loss-budget accounting integrity.",
        "threshold_context": "Count includes missing or unknown reservation ids on admitted events.",
        "expected_recovery_signal": "Admitted events consistently map to valid reservations.",
    },
}


def _table(df: pd.DataFrame) -> str:
    if df.empty:
        return "_empty_"
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


def _read_yaml(path: Path) -> dict[str, Any]:
    if (yaml is None) or (not path.exists()):
        return {}
    obj = yaml.safe_load(path.read_text(encoding="utf-8"))
    return obj if isinstance(obj, dict) else {}


def _worst_band(series: pd.Series) -> str:
    ranks = {"red": 3, "amber": 2, "green": 1}
    vals = [str(x).lower() for x in series.dropna().tolist()]
    if not vals:
        return "unknown"
    return max(vals, key=lambda x: ranks.get(x, 0))


def _worst_sev(series: pd.Series) -> str:
    ranks = {"critical": 4, "high": 3, "medium": 2, "info": 1, "low": 1}
    vals = [str(x).lower() for x in series.dropna().tolist()]
    if not vals:
        return "unknown"
    return max(vals, key=lambda x: ranks.get(x, 0))


def run(
    *,
    disposition_csv: Path,
    exceptions_yaml: Path,
    out_csv: Path,
    report_out: Path,
) -> pd.DataFrame:
    disp = _read_csv(disposition_csv)
    cfg = _read_yaml(exceptions_yaml)
    rules = cfg.get("rules", []) if isinstance(cfg.get("rules", []), list) else []

    out_cols = [
        "metric_id",
        "source_alert",
        "definition",
        "risk_path",
        "threshold_context",
        "action_rationale",
        "expected_recovery_signal",
        "band_worst",
        "severity_worst",
        "active_rows",
        "symbol_count",
        "symbols",
        "action_codes",
        "owners",
        "review_cadence_days",
        "evidence_required",
        "example_evidence_link",
        "coverage_status",
        "generated_at_utc",
    ]

    if disp.empty:
        out_csv.parent.mkdir(parents=True, exist_ok=True)
        report_out.parent.mkdir(parents=True, exist_ok=True)
        empty = pd.DataFrame(columns=out_cols)
        empty.to_csv(out_csv, index=False)
        report_out.write_text(
            "# OCO Governance Explainability Report\n\n_empty_\n", encoding="utf-8"
        )
        return empty

    x = disp.copy()
    x["band"] = x.get("band", pd.Series(dtype=str)).astype(str).str.lower()
    x = x[x["band"].isin(["amber", "red"])].copy()
    if x.empty:
        out_csv.parent.mkdir(parents=True, exist_ok=True)
        report_out.parent.mkdir(parents=True, exist_ok=True)
        empty = pd.DataFrame(columns=out_cols)
        empty.to_csv(out_csv, index=False)
        report_out.write_text(
            "# OCO Governance Explainability Report\n\n_no active non-green alerts_\n",
            encoding="utf-8",
        )
        return empty

    now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    rows: list[dict[str, Any]] = []
    for metric_id, g in x.groupby("metric_id"):
        metric_id = str(metric_id)
        meta = METRIC_META.get(metric_id, {})

        rule_days = []
        for rule in rules:
            if not isinstance(rule, dict):
                continue
            if str(rule.get("metric_id", "")) == metric_id:
                with suppress(Exception):
                    rule_days.append(
                        int(rule.get("review_cadence_days", cfg.get("default_expiry_days", 60)))
                    )
        review_days = int(min(rule_days)) if rule_days else int(cfg.get("default_expiry_days", 60))

        action_codes = sorted(
            g.get("action_code", pd.Series(dtype=str)).dropna().astype(str).unique().tolist()
        )
        owners = sorted(g.get("owner", pd.Series(dtype=str)).dropna().astype(str).unique().tolist())
        symbols = sorted(
            g.get("symbol", pd.Series(dtype=str)).dropna().astype(str).str.upper().unique().tolist()
        )
        evidence_required = bool(
            g.get("evidence_required", pd.Series(dtype=bool))
            .astype(str)
            .str.lower()
            .isin(["1", "true", "yes", "y"])
            .any()
        )
        evidence_links = [
            str(s)
            for s in g.get("evidence_link", pd.Series(dtype=str)).astype(str).tolist()
            if str(s).strip() != ""
        ]

        action_rationale = "Action selected from policy mapping for the observed band/severity."
        if any(a.startswith("A2") for a in action_codes):
            action_rationale = "Session-guard style control is used to contain execution drift while preserving coverage."
        elif any(a.startswith("A1") for a in action_codes):
            action_rationale = "Cap/threshold recalibration is preferred for controlled recovery under amber conditions."
        elif any(a.startswith("A3") for a in action_codes):
            action_rationale = (
                "Hard halt/recalibration path is required due to governance-critical degradation."
            )

        source_alert_series = g.get("source_alert", pd.Series(dtype=str)).astype(str).str.strip()
        source_alert_series = source_alert_series[source_alert_series != ""]
        source_alert_mode = source_alert_series.mode()
        source_alert = (
            str(source_alert_mode.iloc[0])
            if not source_alert_mode.empty
            else "unknown"
        )

        rows.append(
            {
                "metric_id": metric_id,
                "source_alert": source_alert,
                "definition": meta.get("definition", "Metric-specific governance diagnostic."),
                "risk_path": meta.get(
                    "risk_path",
                    "Non-green behavior may invalidate execution/governance assumptions.",
                ),
                "threshold_context": meta.get(
                    "threshold_context", "Threshold context from corresponding monitoring report."
                ),
                "action_rationale": action_rationale,
                "expected_recovery_signal": meta.get(
                    "expected_recovery_signal",
                    "Return to green band and stable recurrence profile.",
                ),
                "band_worst": _worst_band(g.get("band", pd.Series(dtype=str))),
                "severity_worst": _worst_sev(g.get("severity", pd.Series(dtype=str))),
                "active_rows": int(len(g)),
                "symbol_count": int(len(symbols)),
                "symbols": ",".join(symbols),
                "action_codes": ",".join(action_codes),
                "owners": ",".join(owners),
                "review_cadence_days": review_days,
                "evidence_required": evidence_required,
                "example_evidence_link": evidence_links[0] if evidence_links else "",
                "coverage_status": "covered",
                "generated_at_utc": now_utc,
            }
        )

    out = pd.DataFrame(rows).sort_values(["source_alert", "metric_id"]).reset_index(drop=True)

    out_csv.parent.mkdir(parents=True, exist_ok=True)
    report_out.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(out_csv, index=False)

    summary = (
        out.groupby(["source_alert", "band_worst", "severity_worst"], as_index=False)
        .agg(metrics=("metric_id", "count"), symbols=("symbol_count", "sum"))
        .sort_values(["source_alert", "band_worst", "severity_worst"])
        if not out.empty
        else pd.DataFrame(
            columns=["source_alert", "band_worst", "severity_worst", "metrics", "symbols"]
        )
    )

    lines: list[str] = []
    lines.append("# OCO Governance Explainability Report")
    lines.append("")
    lines.append(f"- generated_at_utc: `{now_utc}`")
    lines.append(f"- disposition_csv: `{disposition_csv}`")
    lines.append(f"- exceptions_yaml: `{exceptions_yaml}`")
    lines.append(f"- output_csv: `{out_csv}`")
    lines.append("")
    lines.append("## Summary")
    lines.append(_table(summary))
    lines.append("")
    lines.append("## Metric Explainability")
    lines.append(_table(out))
    report_out.write_text("\n".join(lines), encoding="utf-8")

    return out


def main() -> None:
    p = argparse.ArgumentParser(description="Build OCO governance explainability report")
    p.add_argument(
        "--disposition-csv",
        default="data/analysis/tick_opportunity_mining/oco_alert_disposition.csv",
    )
    p.add_argument(
        "--exceptions-yaml", default="configs/research/governance/oco_monitoring_exceptions.yaml"
    )
    p.add_argument(
        "--out-csv",
        default="data/analysis/tick_opportunity_mining/oco_governance_explainability.csv",
    )
    p.add_argument("--report-out", default="docs/analysis/oco_governance_explainability_report.md")
    args = p.parse_args()

    df = run(
        disposition_csv=Path(str(args.disposition_csv)),
        exceptions_yaml=Path(str(args.exceptions_yaml)),
        out_csv=Path(str(args.out_csv)),
        report_out=Path(str(args.report_out)),
    )
    print(f"wrote explainability: {args.out_csv} rows={len(df)}")


if __name__ == "__main__":
    main()
