#!/usr/bin/env python3
"""Register an OCO docs/analysis run and snapshot key CSV artifacts."""

from __future__ import annotations

import argparse
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd


def _dt_utc(s: pd.Series) -> pd.Series:
    try:
        return pd.to_datetime(s, utc=True, errors="coerce", format="mixed")
    except TypeError:
        return pd.to_datetime(s, utc=True, errors="coerce")


def _table(df: pd.DataFrame) -> str:
    if df.empty:
        return "_empty_"
    try:
        return df.to_markdown(index=False)
    except Exception:
        return "```\n" + df.to_string(index=False) + "\n```"


def _copy_if_exists(src: Path, dst: Path) -> Path | None:
    if not src.exists():
        return None
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    return dst


def _read_csv_safe(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    try:
        return pd.read_csv(path)
    except Exception:
        return pd.DataFrame()


def run(
    *,
    run_id: str,
    label: str,
    edge_metrics_csv: Path,
    stage_metrics_csv: Path,
    stage_status_csv: Path,
    docs_checks_csv: Path,
    registry_csv: Path,
    snapshots_root: Path,
    set_baseline: bool,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    snap_dir = snapshots_root / run_id
    snap_dir.mkdir(parents=True, exist_ok=True)

    edge_snap = _copy_if_exists(edge_metrics_csv, snap_dir / "edge_clarity_stage_metrics.csv")
    stage_snap = _copy_if_exists(stage_metrics_csv, snap_dir / "oco_bible_stage_metrics.csv")
    status_snap = _copy_if_exists(stage_status_csv, snap_dir / "oco_bible_stage_status.csv")
    docs_snap = _copy_if_exists(docs_checks_csv, snap_dir / "docs_contract_checks.csv")

    edge = _read_csv_safe(edge_metrics_csv)
    stage = _read_csv_safe(stage_metrics_csv)
    status = _read_csv_safe(stage_status_csv)
    checks = _read_csv_safe(docs_checks_csv)

    generated_at = now_utc
    for candidate in [edge, stage]:
        if not candidate.empty and "generated_at_utc" in candidate.columns:
            ts = _dt_utc(candidate["generated_at_utc"])
            if ts.notna().any():
                generated_at = ts.max().strftime("%Y-%m-%dT%H:%M:%SZ")
                break

    checks_fail = 0
    checks_hc_fail = 0
    if not checks.empty and "status" in checks.columns:
        s = checks["status"].astype(str).str.lower()
        sev = (
            checks.get("severity_if_fail", pd.Series(index=checks.index, dtype=str))
            .astype(str)
            .str.lower()
        )
        checks_fail = int((s != "pass").sum())
        checks_hc_fail = int(((s != "pass") & sev.isin(["high", "critical"]).fillna(False)).sum())

    sym_total = 0
    sym_pass = 0
    if not status.empty and "symbol" in status.columns:
        sym_total = int(status["symbol"].astype(str).nunique())
        if "symbol_all_gates_pass" in status.columns:
            sym_pass = int(
                pd.to_numeric(status["symbol_all_gates_pass"], errors="coerce")
                .fillna(0)
                .astype(int)
                .sum()
            )

    row = {
        "run_id": str(run_id),
        "run_label": str(label),
        "generated_at_utc": str(generated_at),
        "registered_at_utc": str(now_utc),
        "edge_metrics_rows": int(len(edge)),
        "stage_metrics_rows": int(len(stage)),
        "stage_status_rows": int(len(status)),
        "docs_checks_failed": int(checks_fail),
        "docs_checks_high_critical_failed": int(checks_hc_fail),
        "symbols_total": int(sym_total),
        "symbols_pass_count": int(sym_pass),
        "edge_metrics_snapshot": str(edge_snap) if edge_snap else "",
        "stage_metrics_snapshot": str(stage_snap) if stage_snap else "",
        "stage_status_snapshot": str(status_snap) if status_snap else "",
        "docs_checks_snapshot": str(docs_snap) if docs_snap else "",
        "snapshot_dir": str(snap_dir),
        "is_baseline": False,
    }

    reg = _read_csv_safe(registry_csv)
    if reg.empty:
        reg = pd.DataFrame(columns=list(row.keys()))

    if "run_id" in reg.columns:
        reg = reg[reg["run_id"].astype(str) != str(run_id)].copy()
    else:
        reg["run_id"] = ""

    if "is_baseline" not in reg.columns:
        reg["is_baseline"] = False

    reg = pd.concat([reg, pd.DataFrame([row])], ignore_index=True)

    if set_baseline:
        reg["is_baseline"] = False
        reg.loc[reg["run_id"].astype(str) == str(run_id), "is_baseline"] = True
    elif int(pd.to_numeric(reg["is_baseline"], errors="coerce").fillna(0).astype(int).sum()) == 0:
        reg.loc[reg["run_id"].astype(str) == str(run_id), "is_baseline"] = True

    if "generated_at_utc" in reg.columns:
        ts = _dt_utc(reg["generated_at_utc"])
        reg = (
            reg.assign(_ts=ts)
            .sort_values(["_ts", "run_id"], kind="stable")
            .drop(columns=["_ts"])
            .reset_index(drop=True)
        )

    registry_csv.parent.mkdir(parents=True, exist_ok=True)
    reg.to_csv(registry_csv, index=False)
    return reg, row


def main() -> None:
    p = argparse.ArgumentParser(description="Register docs run and snapshot key artifacts")
    p.add_argument("--run-id", default="")
    p.add_argument("--label", default="manual")
    p.add_argument(
        "--edge-metrics-csv",
        default="data/analysis/tick_opportunity_mining/edge_clarity_stage_metrics.csv",
    )
    p.add_argument(
        "--stage-metrics-csv",
        default="data/analysis/tick_opportunity_mining/oco_bible_stage_metrics.csv",
    )
    p.add_argument(
        "--stage-status-csv",
        default="data/analysis/tick_opportunity_mining/oco_bible_stage_status.csv",
    )
    p.add_argument(
        "--docs-checks-csv",
        default="data/analysis/tick_opportunity_mining/docs_contract_checks.csv",
    )
    p.add_argument(
        "--registry-csv", default="data/analysis/tick_opportunity_mining/run_registry.csv"
    )
    p.add_argument(
        "--snapshots-root", default="data/analysis/tick_opportunity_mining/run_snapshots"
    )
    p.add_argument("--set-baseline", action="store_true")
    args = p.parse_args()

    run_id = str(args.run_id).strip()
    if not run_id:
        run_id = "run_" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    reg, row = run(
        run_id=run_id,
        label=str(args.label),
        edge_metrics_csv=Path(str(args.edge_metrics_csv)),
        stage_metrics_csv=Path(str(args.stage_metrics_csv)),
        stage_status_csv=Path(str(args.stage_status_csv)),
        docs_checks_csv=Path(str(args.docs_checks_csv)),
        registry_csv=Path(str(args.registry_csv)),
        snapshots_root=Path(str(args.snapshots_root)),
        set_baseline=bool(args.set_baseline),
    )

    baseline_rows = reg[
        pd.to_numeric(reg.get("is_baseline", pd.Series(dtype=float)), errors="coerce")
        .fillna(0)
        .astype(int)
        == 1
    ].copy()
    print(f"registered run: {row['run_id']}")
    print(f"registry rows: {len(reg)}")
    print(f"baseline runs: {len(baseline_rows)}")
    print(_table(reg.tail(5)))


if __name__ == "__main__":
    main()
