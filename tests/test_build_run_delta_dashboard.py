from __future__ import annotations

from pathlib import Path

import pandas as pd

from scripts.build_run_delta_dashboard import run


def _write_snap(run_dir: Path, *, metric_value: float, gate_value: int) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(
        [
            {
                "stage_id": 1,
                "symbol": "EURUSD",
                "metric_id": "D16_spread_regime_shift_z",
                "metric_value": metric_value,
                "note": "x",
            }
        ]
    ).to_csv(run_dir / "edge_clarity_stage_metrics.csv", index=False)
    pd.DataFrame([{"symbol": "EURUSD", "symbol_all_gates_pass": gate_value}]).to_csv(
        run_dir / "oco_bible_stage_status.csv", index=False
    )


def test_build_run_delta_dashboard_outputs_changes(tmp_path: Path) -> None:
    base = tmp_path / "data"
    snap_a = base / "run_snapshots" / "run_a"
    snap_b = base / "run_snapshots" / "run_b"
    _write_snap(snap_a, metric_value=1.0, gate_value=1)
    _write_snap(snap_b, metric_value=1.4, gate_value=0)

    reg = pd.DataFrame(
        [
            {
                "run_id": "run_a",
                "generated_at_utc": "2026-02-26T00:00:00Z",
                "docs_checks_failed": 0,
                "is_baseline": 1,
                "edge_metrics_snapshot": str(snap_a / "edge_clarity_stage_metrics.csv"),
                "stage_status_snapshot": str(snap_a / "oco_bible_stage_status.csv"),
            },
            {
                "run_id": "run_b",
                "generated_at_utc": "2026-02-27T00:00:00Z",
                "docs_checks_failed": 1,
                "is_baseline": 0,
                "edge_metrics_snapshot": str(snap_b / "edge_clarity_stage_metrics.csv"),
                "stage_status_snapshot": str(snap_b / "oco_bible_stage_status.csv"),
            },
        ]
    )
    reg_csv = base / "run_registry.csv"
    reg.to_csv(reg_csv, index=False)

    summary, metric, gate = run(
        registry_csv=reg_csv,
        out_summary_csv=base / "run_delta_summary.csv",
        out_metric_changes_csv=base / "run_delta_metric_changes.csv",
        out_gate_changes_csv=base / "run_delta_gate_changes.csv",
        out_report_md=tmp_path / "run_delta_dashboard.md",
    )

    assert not summary.empty
    assert summary.iloc[0]["baseline_run_id"] == "run_a"
    assert summary.iloc[0]["latest_run_id"] == "run_b"
    assert int(summary.iloc[0]["metric_rows_changed"]) >= 1
    assert int(summary.iloc[0]["gate_rows_changed"]) >= 1
    assert not metric.empty
    assert not gate.empty
    assert (tmp_path / "run_delta_dashboard.md").exists()
