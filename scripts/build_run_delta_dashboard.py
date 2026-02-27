#!/usr/bin/env python3
"""Build run-to-baseline delta artifacts and markdown dashboard."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd


def _table(df: pd.DataFrame) -> str:
    if df.empty:
        return "_empty_"
    try:
        return df.to_markdown(index=False)
    except Exception:
        return "```\n" + df.to_string(index=False) + "\n```"


def _dt_utc(s: pd.Series) -> pd.Series:
    try:
        return pd.to_datetime(s, utc=True, errors="coerce", format="mixed")
    except TypeError:
        return pd.to_datetime(s, utc=True, errors="coerce")


def _read_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    try:
        return pd.read_csv(path)
    except Exception:
        return pd.DataFrame()


def _bool01(x: object) -> int:
    if pd.isna(x):
        return 0
    s = str(x).strip().lower()
    if s in {"1", "true", "t", "yes", "y"}:
        return 1
    try:
        return 1 if float(s) > 0 else 0
    except Exception:
        return 0


def _resolve_row_csv(row: pd.Series, key: str) -> Path | None:
    raw = str(row.get(key, "") or "").strip()
    if not raw:
        return None
    p = Path(raw)
    return p if p.exists() else None


def _pick_runs(reg: pd.DataFrame) -> tuple[pd.Series, pd.Series]:
    if reg.empty:
        raise ValueError("run registry is empty")
    work = reg.copy()
    if "generated_at_utc" in work.columns:
        work["_ts"] = _dt_utc(work["generated_at_utc"])
    else:
        work["_ts"] = pd.NaT
    work = work.sort_values(["_ts", "run_id"], kind="stable").reset_index(drop=True)
    latest = work.iloc[-1]
    b = work[pd.to_numeric(work.get("is_baseline", pd.Series(index=work.index, dtype=float)), errors="coerce").fillna(0).astype(int) == 1].copy()
    baseline = b.iloc[-1] if not b.empty else latest
    return baseline, latest


def _metric_delta(baseline_edge: pd.DataFrame, latest_edge: pd.DataFrame) -> pd.DataFrame:
    key_cols = ["stage_id", "symbol", "metric_id"]

    def prep(df: pd.DataFrame, suffix: str) -> pd.DataFrame:
        if df.empty:
            return pd.DataFrame(columns=key_cols + [f"metric_value_{suffix}", f"note_{suffix}"])
        x = df.copy()
        for c in key_cols:
            if c not in x.columns:
                x[c] = np.nan
        x["metric_value"] = pd.to_numeric(x.get("metric_value"), errors="coerce")
        keep = key_cols + ["metric_value", "note"]
        for c in keep:
            if c not in x.columns:
                x[c] = np.nan
        x = x[keep].copy()
        x = x.rename(columns={"metric_value": f"metric_value_{suffix}", "note": f"note_{suffix}"})
        return x

    b = prep(baseline_edge, "baseline")
    l = prep(latest_edge, "latest")
    m = b.merge(l, on=key_cols, how="outer")
    vb = pd.to_numeric(m.get("metric_value_baseline"), errors="coerce")
    vl = pd.to_numeric(m.get("metric_value_latest"), errors="coerce")
    m["delta"] = vl - vb
    m["abs_delta"] = m["delta"].abs()
    m["changed"] = (
        (vb.isna() & vl.notna())
        | (vb.notna() & vl.isna())
        | ((vb.notna()) & (vl.notna()) & ((vl - vb).abs() > 1e-12))
    )
    return m.sort_values(["changed", "abs_delta", "symbol", "stage_id", "metric_id"], ascending=[False, False, True, True, True]).reset_index(drop=True)


def _gate_delta(baseline_status: pd.DataFrame, latest_status: pd.DataFrame) -> pd.DataFrame:
    b = baseline_status.copy()
    l = latest_status.copy()
    for df in [b, l]:
        if "symbol" not in df.columns:
            df["symbol"] = ""
        df["symbol"] = df["symbol"].astype(str).str.upper()

    gate_cols = sorted(list((set(b.columns) | set(l.columns)) - {"symbol"}))
    rows: list[dict[str, object]] = []
    symbols = sorted(set(b.get("symbol", pd.Series(dtype=str)).astype(str)) | set(l.get("symbol", pd.Series(dtype=str)).astype(str)))
    for sym in symbols:
        rb = b[b["symbol"] == sym]
        rl = l[l["symbol"] == sym]
        for g in gate_cols:
            vb = rb.iloc[0][g] if (not rb.empty and g in rb.columns) else np.nan
            vl = rl.iloc[0][g] if (not rl.empty and g in rl.columns) else np.nan
            ib = _bool01(vb)
            il = _bool01(vl)
            rows.append(
                {
                    "symbol": sym,
                    "gate_id": g,
                    "baseline_value": ib,
                    "latest_value": il,
                    "delta": il - ib,
                    "changed": int(ib != il),
                }
            )
    out = pd.DataFrame(rows)
    if out.empty:
        return pd.DataFrame(columns=["symbol", "gate_id", "baseline_value", "latest_value", "delta", "changed"])
    return out.sort_values(["changed", "symbol", "gate_id"], ascending=[False, True, True]).reset_index(drop=True)


def run(
    *,
    registry_csv: Path,
    out_summary_csv: Path,
    out_metric_changes_csv: Path,
    out_gate_changes_csv: Path,
    out_report_md: Path,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    reg = _read_csv(registry_csv)
    baseline_row, latest_row = _pick_runs(reg)

    b_edge = _read_csv(_resolve_row_csv(baseline_row, "edge_metrics_snapshot") or Path())
    l_edge = _read_csv(_resolve_row_csv(latest_row, "edge_metrics_snapshot") or Path())
    b_status = _read_csv(_resolve_row_csv(baseline_row, "stage_status_snapshot") or Path())
    l_status = _read_csv(_resolve_row_csv(latest_row, "stage_status_snapshot") or Path())

    metric_changes = _metric_delta(b_edge, l_edge)
    gate_changes = _gate_delta(b_status, l_status)

    b_sym_pass = 0
    l_sym_pass = 0
    b_sym_total = 0
    l_sym_total = 0
    if not b_status.empty:
        b_sym_total = int(b_status["symbol"].astype(str).nunique()) if "symbol" in b_status.columns else 0
        if "symbol_all_gates_pass" in b_status.columns:
            b_sym_pass = int(pd.to_numeric(b_status["symbol_all_gates_pass"], errors="coerce").fillna(0).astype(int).sum())
    if not l_status.empty:
        l_sym_total = int(l_status["symbol"].astype(str).nunique()) if "symbol" in l_status.columns else 0
        if "symbol_all_gates_pass" in l_status.columns:
            l_sym_pass = int(pd.to_numeric(l_status["symbol_all_gates_pass"], errors="coerce").fillna(0).astype(int).sum())

    summary = pd.DataFrame(
        [
            {
                "baseline_run_id": str(baseline_row.get("run_id", "")),
                "latest_run_id": str(latest_row.get("run_id", "")),
                "baseline_generated_at_utc": str(baseline_row.get("generated_at_utc", "")),
                "latest_generated_at_utc": str(latest_row.get("generated_at_utc", "")),
                "metric_rows_baseline": int(len(b_edge)),
                "metric_rows_latest": int(len(l_edge)),
                "metric_rows_changed": int(pd.to_numeric(metric_changes.get("changed", pd.Series(dtype=float)), errors="coerce").fillna(0).astype(int).sum()),
                "gate_rows_changed": int(pd.to_numeric(gate_changes.get("changed", pd.Series(dtype=float)), errors="coerce").fillna(0).astype(int).sum()),
                "symbols_total_baseline": int(b_sym_total),
                "symbols_total_latest": int(l_sym_total),
                "symbols_pass_baseline": int(b_sym_pass),
                "symbols_pass_latest": int(l_sym_pass),
                "docs_failed_baseline": int(pd.to_numeric(pd.Series([baseline_row.get("docs_checks_failed", np.nan)]), errors="coerce").fillna(0).iloc[0]),
                "docs_failed_latest": int(pd.to_numeric(pd.Series([latest_row.get("docs_checks_failed", np.nan)]), errors="coerce").fillna(0).iloc[0]),
            }
        ]
    )

    out_summary_csv.parent.mkdir(parents=True, exist_ok=True)
    out_metric_changes_csv.parent.mkdir(parents=True, exist_ok=True)
    out_gate_changes_csv.parent.mkdir(parents=True, exist_ok=True)
    out_report_md.parent.mkdir(parents=True, exist_ok=True)
    summary.to_csv(out_summary_csv, index=False)
    metric_changes.to_csv(out_metric_changes_csv, index=False)
    gate_changes.to_csv(out_gate_changes_csv, index=False)

    top_metrics = metric_changes[metric_changes.get("changed", pd.Series(dtype=bool)).astype(bool)].copy()
    if not top_metrics.empty:
        top_metrics = top_metrics.sort_values("abs_delta", ascending=False).head(40)

    gate_flip = gate_changes[gate_changes.get("changed", pd.Series(dtype=bool)).astype(bool)].copy()
    if not gate_flip.empty:
        gate_flip = gate_flip.sort_values(["symbol", "gate_id"]).head(40)

    lines: list[str] = []
    lines.append("# Run Delta Dashboard")
    lines.append("")
    lines.append(f"- generated_at_utc: `{datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}`")
    lines.append(f"- registry_csv: `{registry_csv}`")
    lines.append(f"- summary_csv: `{out_summary_csv}`")
    lines.append(f"- metric_changes_csv: `{out_metric_changes_csv}`")
    lines.append(f"- gate_changes_csv: `{out_gate_changes_csv}`")
    lines.append("")
    lines.append("## Summary")
    lines.append(_table(summary))
    lines.append("")
    lines.append("## Gate Changes")
    lines.append(_table(gate_flip))
    lines.append("")
    lines.append("## Top Metric Changes")
    lines.append(_table(top_metrics))
    out_report_md.write_text("\n".join(lines), encoding="utf-8")

    return summary, metric_changes, gate_changes


def main() -> None:
    p = argparse.ArgumentParser(description="Build run delta dashboard")
    p.add_argument("--registry-csv", default="data/analysis/tick_opportunity_mining/run_registry.csv")
    p.add_argument("--out-summary-csv", default="data/analysis/tick_opportunity_mining/run_delta_summary.csv")
    p.add_argument("--out-metric-changes-csv", default="data/analysis/tick_opportunity_mining/run_delta_metric_changes.csv")
    p.add_argument("--out-gate-changes-csv", default="data/analysis/tick_opportunity_mining/run_delta_gate_changes.csv")
    p.add_argument("--report-out", default="docs/analysis/run_delta_dashboard.md")
    args = p.parse_args()

    summary, metric_changes, gate_changes = run(
        registry_csv=Path(str(args.registry_csv)),
        out_summary_csv=Path(str(args.out_summary_csv)),
        out_metric_changes_csv=Path(str(args.out_metric_changes_csv)),
        out_gate_changes_csv=Path(str(args.out_gate_changes_csv)),
        out_report_md=Path(str(args.report_out)),
    )
    print(f"wrote summary: {args.out_summary_csv} rows={len(summary)}")
    print(f"wrote metric changes: {args.out_metric_changes_csv} rows={len(metric_changes)}")
    print(f"wrote gate changes: {args.out_gate_changes_csv} rows={len(gate_changes)}")


if __name__ == "__main__":
    main()
