from __future__ import annotations

from pathlib import Path

import pandas as pd

from scripts.register_docs_run import run


def _write_inputs(tmp_path: Path) -> tuple[Path, Path, Path, Path]:
    edge = tmp_path / "edge.csv"
    stage = tmp_path / "stage.csv"
    status = tmp_path / "status.csv"
    checks = tmp_path / "checks.csv"
    pd.DataFrame(
        [
            {
                "stage_id": 1,
                "symbol": "EURUSD",
                "metric_id": "D16_spread_regime_shift_z",
                "metric_value": 0.1,
                "generated_at_utc": "2026-02-27T00:00:00Z",
            }
        ]
    ).to_csv(edge, index=False)
    pd.DataFrame(
        [
            {
                "stage_id": 1,
                "metric_id": "events_rows",
                "symbol": "EURUSD",
                "value": 1,
                "generated_at_utc": "2026-02-27T00:00:00Z",
            }
        ]
    ).to_csv(stage, index=False)
    pd.DataFrame([{"symbol": "EURUSD", "symbol_all_gates_pass": True}]).to_csv(status, index=False)
    pd.DataFrame([{"check_id": "C1", "status": "pass", "severity_if_fail": "high"}]).to_csv(
        checks, index=False
    )
    return edge, stage, status, checks


def test_register_docs_run_writes_registry_and_snapshots(tmp_path: Path) -> None:
    edge, stage, status, checks = _write_inputs(tmp_path)
    reg_csv = tmp_path / "run_registry.csv"
    snaps = tmp_path / "run_snapshots"

    reg, row = run(
        run_id="run_a",
        label="smoke",
        edge_metrics_csv=edge,
        stage_metrics_csv=stage,
        stage_status_csv=status,
        docs_checks_csv=checks,
        registry_csv=reg_csv,
        snapshots_root=snaps,
        set_baseline=False,
    )

    assert not reg.empty
    assert row["run_id"] == "run_a"
    assert reg_csv.exists()
    assert (snaps / "run_a" / "edge_clarity_stage_metrics.csv").exists()
    assert int(pd.to_numeric(reg["is_baseline"], errors="coerce").fillna(0).sum()) == 1


def test_register_docs_run_set_baseline_switches_flag(tmp_path: Path) -> None:
    edge, stage, status, checks = _write_inputs(tmp_path)
    reg_csv = tmp_path / "run_registry.csv"
    snaps = tmp_path / "run_snapshots"

    run(
        run_id="run_a",
        label="a",
        edge_metrics_csv=edge,
        stage_metrics_csv=stage,
        stage_status_csv=status,
        docs_checks_csv=checks,
        registry_csv=reg_csv,
        snapshots_root=snaps,
        set_baseline=False,
    )
    reg, _ = run(
        run_id="run_b",
        label="b",
        edge_metrics_csv=edge,
        stage_metrics_csv=stage,
        stage_status_csv=status,
        docs_checks_csv=checks,
        registry_csv=reg_csv,
        snapshots_root=snaps,
        set_baseline=True,
    )

    r = reg.set_index("run_id")
    assert int(r.loc["run_a", "is_baseline"]) == 0
    assert int(r.loc["run_b", "is_baseline"]) == 1
