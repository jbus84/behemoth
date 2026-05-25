import subprocess


def test_onboard_symbol_dry_run_uses_unified_governance_orchestrator():
    result = subprocess.run(
        [
            "uv",
            "run",
            "python",
            "scripts/onboard_symbol.py",
            "--symbol",
            "EURUSD",
            "--months",
            "202601",
            "--dry-run",
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    assert "Stage 2f-4: Unified governance" in result.stdout
    assert "scripts/governance/run_governance_all.py" in result.stdout
    assert "select_oco_reduced_core_rolling.py" not in result.stdout
    assert "verify_oco_tick_exact_shortlist.py" not in result.stdout
