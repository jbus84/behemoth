from pathlib import Path
import subprocess, sys

def test_phase1_runs_and_produces_signal_section(tmp_path):
    out = tmp_path / "report.md"
    result = subprocess.run(
        [sys.executable, "scripts/build_demo_live_offline_comparison_report.py",
         "--out", str(out), "--phase", "1"],
        capture_output=True, text=True
    )
    assert result.returncode == 0, result.stderr
    content = out.read_text()
    assert "## Signal Parity" in content
    assert "AUDUSD" in content
    assert "USDCHF" in content
    assert "## Session Summary" in content
