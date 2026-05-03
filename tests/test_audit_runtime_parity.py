"""Smoke test for scripts/audit_runtime_parity.py."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def test_harness_runs_and_writes_artifacts(tmp_path: Path) -> None:
    reconcile = tmp_path / "reconcile"
    governance = tmp_path / "gov"
    reconcile.mkdir()
    governance.mkdir()
    (reconcile / "EURUSD_jforex_signal_parity_summary.csv").write_text(
        "symbol,jforex_signal_parity_pass,predict_cycles,failed_signal_events\n"
        "EURUSD,true,136,0\n"
    )
    for sym in ["audusd", "eurusd", "gbpusd", "usdcad", "usdchf", "usdjpy"]:
        (governance / f"{sym}_oco_live_lock.json").write_text(
            '{"model_month":"2026-04","lock_hash":"abc"}'
        )

    out_md = tmp_path / "report.md"
    out_csv = tmp_path / "findings.csv"
    live_db = tmp_path / "reconcile" / "runtime" / "live_state.db"
    (tmp_path / "reconcile" / "runtime").mkdir()

    repo_root = Path(__file__).resolve().parents[1]
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)
    result = subprocess.run(
        [
            sys.executable, "scripts/audit_runtime_parity.py",
            "--run-id", "test_run",
            "--model-month", "2026-04",
            "--reconcile-dir", str(reconcile),
            "--governance-lock-dir", str(governance),
            "--live-state-db", str(live_db),
            "--out-report", str(out_md),
            "--out-csv", str(out_csv),
        ],
        capture_output=True, text=True,
        cwd=repo_root,
        env=env,
    )

    assert out_md.exists(), result.stderr
    assert out_csv.exists(), result.stderr
    assert "ModuleNotFoundError: No module named 'behemoth'" not in result.stderr
    report_text = out_md.read_text()
    assert "core.predict_cycles_per_bar" in report_text
    assert "risk_gov.governance_lock_pin" in report_text
    # Exit code is non-zero if any critical failed; in this fixture the
    # `lifecycle.active_oco_reconciled` check will fail (no live_state.db).
    assert result.returncode != 0
