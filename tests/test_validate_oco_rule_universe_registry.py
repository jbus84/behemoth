from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import yaml

from scripts.validate_oco_rule_universe_registry import _canon_hash, run


def _write_registry(path: Path, *, allowed_barrier_keep: list[int]) -> None:
    obj = {
        "registry_version": 1,
        "effective_from_utc": "2026-02-27T00:00:00Z",
        "symbols": ["EURUSD"],
        "allowed_families": ["oco_first_touch"],
        "allowed_barrier_keep": allowed_barrier_keep,
        "allowed_horizon_keep": [5, 6],
        "selection_mode_contract": "auto",
        "locked_runtime_contract": {
            "threshold_mode": "rolling_days",
            "rolling_threshold_days": 20,
            "rolling_threshold_min_history": 300,
            "oco_hold_mode": "from_touch",
            "oco_include_no_touch": True,
            "execution_quantile": 0.9,
        },
        "change_control": {
            "owner": "research",
            "ticket": "TEST-1",
            "rationale": "unit test",
        },
    }
    obj["hash_sha256"] = _canon_hash(obj)
    path.write_text(yaml.safe_dump(obj, sort_keys=False), encoding="utf-8")


def _write_lock(path: Path) -> None:
    lock = {
        "symbol": "EURUSD",
        "locked_runtime": {
            "family_keep": "oco_first_touch",
            "barrier_keep": "2,3",
            "horizon_keep": "5,6",
            "selection_mode": "auto",
            "threshold_mode": "rolling_days",
            "rolling_threshold_days": 20,
            "rolling_threshold_min_history": 300,
            "oco_hold_mode": "from_touch",
            "oco_include_no_touch": True,
            "execution_quantile": 0.9,
        },
    }
    path.write_text(json.dumps(lock), encoding="utf-8")


def _write_reduced_states(path: Path) -> None:
    pd.DataFrame(
        [
            {"family": "oco_first_touch", "barrier_pips": 2, "horizon": 5},
            {"family": "oco_first_touch", "barrier_pips": 3, "horizon": 6},
        ]
    ).to_csv(path, index=False)


def test_rule_universe_registry_pass(tmp_path: Path) -> None:
    registry = tmp_path / "registry.yaml"
    lock_dir = tmp_path / "locks"
    lock_dir.mkdir(parents=True, exist_ok=True)
    mining_base = tmp_path / "mining"
    (mining_base / "reduced_core").mkdir(parents=True, exist_ok=True)

    _write_registry(registry, allowed_barrier_keep=[2, 3])
    _write_lock(lock_dir / "eurusd_oco_first_touch_live_lock.json")
    _write_reduced_states(mining_base / "reduced_core" / "EURUSD_oco_first_touch_reduced_states.csv")

    checks, issues = run(
        registry_yaml=registry,
        lock_dir=lock_dir,
        mining_base=mining_base,
        symbols=["EURUSD"],
        out_checks_csv=tmp_path / "checks.csv",
        out_issues_csv=tmp_path / "issues.csv",
        out_report_md=tmp_path / "report.md",
    )

    assert not checks.empty
    assert issues.empty
    assert (checks["status"].astype(str) == "pass").all()


def test_rule_universe_registry_flags_lock_mismatch(tmp_path: Path) -> None:
    registry = tmp_path / "registry.yaml"
    lock_dir = tmp_path / "locks"
    lock_dir.mkdir(parents=True, exist_ok=True)
    mining_base = tmp_path / "mining"
    (mining_base / "reduced_core").mkdir(parents=True, exist_ok=True)

    _write_registry(registry, allowed_barrier_keep=[2])
    _write_lock(lock_dir / "eurusd_oco_first_touch_live_lock.json")
    _write_reduced_states(mining_base / "reduced_core" / "EURUSD_oco_first_touch_reduced_states.csv")

    checks, _issues = run(
        registry_yaml=registry,
        lock_dir=lock_dir,
        mining_base=mining_base,
        symbols=["EURUSD"],
        out_checks_csv=tmp_path / "checks.csv",
        out_issues_csv=tmp_path / "issues.csv",
        out_report_md=tmp_path / "report.md",
    )

    ru07 = checks[(checks["check_id"] == "RU07") & (checks["symbol"] == "EURUSD")]
    assert not ru07.empty
    assert ru07.iloc[0]["status"] == "fail"


def test_reduced_states_for_symbol_paths() -> None:
    from scripts.validate_oco_rule_universe_registry import _reduced_states_for_symbol

    base = Path("/base")
    assert "reduced_core/EURUSD_oco_first_touch_reduced_states.csv" in str(
        _reduced_states_for_symbol(base, "EURUSD").as_posix()
    )
    assert "reduced_core/AUDUSD_oco_first_touch_reduced_states.csv" in str(
        _reduced_states_for_symbol(base, "AUDUSD").as_posix()
    )
    assert "reduced_core/USDCAD_oco_first_touch_reduced_states.csv" in str(
        _reduced_states_for_symbol(base, "USDCAD").as_posix()
    )


def test_no_go_lock_with_empty_universe_is_accepted() -> None:
    """A governance lock for a no-trade symbol — empty state_universe,
    deploy_verdict NO_GO — must validate cleanly, not be flagged as a
    failure. NO_GO is an expected outcome, not a defect."""

    lock = {
        "symbol": "EURUSD",
        "deploy_verdict": "NO_GO",
        "state_universe": {"count": 0, "sha256": _canon_hash({}), "rows": []},
    }
    # A NO_GO lock with an empty universe is well-formed: count matches rows,
    # verdict matches count.
    assert lock["state_universe"]["count"] == len(lock["state_universe"]["rows"])
    assert lock["deploy_verdict"] == "NO_GO"
