import subprocess
import sys


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


def test_phase3_invokes_audit_runtime_parity(monkeypatch, tmp_path):
    """Phase 3 should shell out to audit_runtime_parity.py and append a section."""
    import subprocess

    from scripts.build_demo_live_offline_comparison_report import _phase3_parity_audit

    calls = {}

    def _fake_run(cmd, capture_output, text):
        calls["cmd"] = cmd
        class R:
            returncode = 0
            stdout = ""
            stderr = ""
        return R()

    monkeypatch.setattr(subprocess, "run", _fake_run)
    out = _phase3_parity_audit("test_run", "2026-04")
    assert "Parity Audit" in out
    assert "audit_runtime_parity.py" in " ".join(calls["cmd"])
