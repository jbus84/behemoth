"""End-to-end smoke test for the governance orchestrator."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pandas as pd


def test_run_governance_all_emits_symbol_verdict(tmp_path):
    repo_root = Path(__file__).resolve().parents[2]
    out_dir = tmp_path / "governance"

    result = subprocess.run(
        [
            sys.executable,
            str(repo_root / "scripts/governance/run_governance_all.py"),
            "--symbol-yaml",
            str(repo_root / "configs/research/experiments/eurusd_governance.yaml"),
            "--candidate-dir",
            str(tmp_path / "candidates"),
            "--out-dir",
            str(out_dir),
            "--tick-root",
            str(tmp_path / "ticks"),
        ],
        check=True,
        capture_output=True,
        text=True,
        cwd=repo_root,
    )

    assert "[gov] EURUSD: symbol_verdict=NO_GO" in result.stdout

    summary = pd.read_csv(out_dir / "2026-05/verdicts/EURUSD_symbol_verdict.csv")
    assert summary.to_dict(orient="records") == [
        {
            "symbol": "EURUSD",
            "model_month": "2026-05",
            "verdict": "NO_GO",
            "oco_first_touch_verdict": "NO_GO",
        }
    ]
