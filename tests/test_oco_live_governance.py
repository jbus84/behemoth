from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pandas as pd

from scripts.freeze_oco_live_governance import _state_universe
from scripts.validate_oco_live_governance import run


def test_state_universe_hash_stable_under_row_order(tmp_path: Path) -> None:
    a = pd.DataFrame(
        [
            {
                "symbol": "EURUSD",
                "bar_ticks": 100,
                "horizon": 6,
                "state_id": "s2",
                "family": "oco_first_touch_clean",
                "barrier_pips": 2.0,
                "regime_desc": "r2",
            },
            {
                "symbol": "EURUSD",
                "bar_ticks": 100,
                "horizon": 5,
                "state_id": "s1",
                "family": "oco_first_touch_clean",
                "barrier_pips": 3.0,
                "regime_desc": "r1",
            },
        ]
    )
    b = a.iloc[::-1].reset_index(drop=True)
    p1 = tmp_path / "a.csv"
    p2 = tmp_path / "b.csv"
    a.to_csv(p1, index=False)
    b.to_csv(p2, index=False)

    _, h1 = _state_universe(p1)
    _, h2 = _state_universe(p2)
    assert h1 == h2


def test_validate_lock_deploy_and_retrain_window(tmp_path: Path) -> None:
    wfo = tmp_path / "wfo.yaml"
    reduced = tmp_path / "reduced.yaml"
    states = tmp_path / "states.csv"
    wfo.write_text(
        "\n".join(
            [
                "threshold_mode: rolling_days",
                "rolling_threshold_days: 20",
                "rolling_threshold_min_history: 1000",
                "execution_quantile: 0.9",
                "oco_hold_mode: from_touch",
                "oco_include_no_touch: true",
            ]
        ),
        encoding="utf-8",
    )
    reduced.write_text(
        "\n".join(
            [
                "locked_quantile: 0.9",
                "selection_mode: auto",
                "family_keep: oco_first_touch_clean",
                'barrier_keep: "2,3"',
                'horizon_keep: "5,6"',
            ]
        ),
        encoding="utf-8",
    )
    pd.DataFrame(
        [
            {
                "symbol": "EURUSD",
                "bar_ticks": 100,
                "horizon": 5,
                "state_id": "s1",
                "family": "oco_first_touch_clean",
                "barrier_pips": 2.0,
                "regime_desc": "r1",
            },
            {
                "symbol": "EURUSD",
                "bar_ticks": 100,
                "horizon": 6,
                "state_id": "s2",
                "family": "oco_first_touch_clean",
                "barrier_pips": 3.0,
                "regime_desc": "r2",
            },
        ]
    ).to_csv(states, index=False)
    preds = tmp_path / "predictions.parquet"
    preds.write_bytes(b"dummy_predictions")
    te_summary = tmp_path / "tick_exact_summary.csv"
    te_summary.write_text("overall_pass\nTrue\n", encoding="utf-8")

    def _sha(path: Path) -> str:
        import hashlib

        h = hashlib.sha256()
        h.update(path.read_bytes())
        return h.hexdigest()

    lock = {
        "frozen_at_utc": "2026-02-25T00:00:00+00:00",
        "symbol": "EURUSD",
        "git": {"commit": "abc123", "branch": "main", "dirty": False},
        "artifacts": {
            "wfo_config_path": str(wfo),
            "wfo_config_sha256": _sha(wfo),
            "reduced_config_path": str(reduced),
            "reduced_config_sha256": _sha(reduced),
            "reduced_states_csv_path": str(states),
            "reduced_states_csv_sha256": _sha(states),
            "predictions_path": str(preds),
            "predictions_sha256": _sha(preds),
            "tick_exact_summary_path": str(te_summary),
            "tick_exact_summary_sha256": _sha(te_summary),
            "tick_exact_overall_pass": True,
        },
        "locked_runtime": {
            "threshold_mode": "rolling_days",
            "rolling_threshold_days": 20,
            "rolling_threshold_min_history": 1000,
            "execution_quantile": 0.9,
            "oco_hold_mode": "from_touch",
            "oco_include_no_touch": True,
            "locked_quantile": 0.9,
            "selection_mode": "auto",
            "family_keep": "oco_first_touch_clean",
            "barrier_keep": "2,3",
            "horizon_keep": "5,6",
        },
        "state_universe": {
            "rows": [
                {
                    "symbol": "EURUSD",
                    "bar_ticks": 100,
                    "horizon": 5,
                    "state_id": "s1",
                    "family": "oco_first_touch_clean",
                    "barrier_pips": 2.0,
                    "regime_desc": "r1",
                },
                {
                    "symbol": "EURUSD",
                    "bar_ticks": 100,
                    "horizon": 6,
                    "state_id": "s2",
                    "family": "oco_first_touch_clean",
                    "barrier_pips": 3.0,
                    "regime_desc": "r2",
                },
            ]
        },
        "retrain_policy": {"cadence_days": 30, "window_days": 3},
    }
    lock_path = tmp_path / "lock.json"
    lock_path.write_text(json.dumps(lock), encoding="utf-8")

    ok_deploy, _, _ = run(
        lock_path=lock_path,
        mode="deploy",
        as_of=date(2026, 2, 26),
        state_csv=states,
        wfo_config=wfo,
        reduced_config=reduced,
    )
    assert ok_deploy

    ok_retrain_bad, _, _ = run(
        lock_path=lock_path,
        mode="retrain",
        as_of=date(2026, 2, 26),  # outside due window around 2026-03-27
        state_csv=states,
        wfo_config=wfo,
        reduced_config=reduced,
    )
    assert not ok_retrain_bad


def test_validate_lock_blocks_on_high_data_reliability_fail(tmp_path: Path) -> None:
    wfo = tmp_path / "wfo.yaml"
    reduced = tmp_path / "reduced.yaml"
    states = tmp_path / "states.csv"
    checks_csv = tmp_path / "data_reliability_checks.csv"
    wfo.write_text(
        "\n".join(
            [
                "threshold_mode: rolling_days",
                "rolling_threshold_days: 20",
                "rolling_threshold_min_history: 1000",
                "execution_quantile: 0.9",
                "oco_hold_mode: from_touch",
                "oco_include_no_touch: true",
            ]
        ),
        encoding="utf-8",
    )
    reduced.write_text(
        "\n".join(
            [
                "locked_quantile: 0.9",
                "selection_mode: auto",
                "family_keep: oco_first_touch_clean",
                'barrier_keep: "2,3"',
                'horizon_keep: "5,6"',
            ]
        ),
        encoding="utf-8",
    )
    pd.DataFrame(
        [
            {
                "symbol": "EURUSD",
                "bar_ticks": 100,
                "horizon": 5,
                "state_id": "s1",
                "family": "oco_first_touch_clean",
                "barrier_pips": 2.0,
                "regime_desc": "r1",
            },
            {
                "symbol": "EURUSD",
                "bar_ticks": 100,
                "horizon": 6,
                "state_id": "s2",
                "family": "oco_first_touch_clean",
                "barrier_pips": 3.0,
                "regime_desc": "r2",
            },
        ]
    ).to_csv(states, index=False)

    checks = pd.DataFrame(
        [
            {
                "symbol": "EURUSD",
                "check_id": "DR01",
                "status": "pass",
                "severity_if_fail": "critical",
            },
            {"symbol": "EURUSD", "check_id": "DR07", "status": "fail", "severity_if_fail": "high"},
            {
                "symbol": "EURUSD",
                "check_id": "DR12",
                "status": "fail",
                "severity_if_fail": "medium",
            },
        ]
    )
    checks.to_csv(checks_csv, index=False)

    preds = tmp_path / "predictions.parquet"
    preds.write_bytes(b"dummy_predictions")
    te_summary = tmp_path / "tick_exact_summary.csv"
    te_summary.write_text("overall_pass\nTrue\n", encoding="utf-8")

    def _sha(path: Path) -> str:
        import hashlib

        h = hashlib.sha256()
        h.update(path.read_bytes())
        return h.hexdigest()

    lock = {
        "frozen_at_utc": "2026-02-25T00:00:00+00:00",
        "symbol": "EURUSD",
        "git": {"commit": "abc123", "branch": "main", "dirty": False},
        "artifacts": {
            "wfo_config_path": str(wfo),
            "wfo_config_sha256": _sha(wfo),
            "reduced_config_path": str(reduced),
            "reduced_config_sha256": _sha(reduced),
            "reduced_states_csv_path": str(states),
            "reduced_states_csv_sha256": _sha(states),
            "predictions_path": str(preds),
            "predictions_sha256": _sha(preds),
            "tick_exact_summary_path": str(te_summary),
            "tick_exact_summary_sha256": _sha(te_summary),
            "tick_exact_overall_pass": True,
        },
        "locked_runtime": {
            "threshold_mode": "rolling_days",
            "rolling_threshold_days": 20,
            "rolling_threshold_min_history": 1000,
            "execution_quantile": 0.9,
            "oco_hold_mode": "from_touch",
            "oco_include_no_touch": True,
            "locked_quantile": 0.9,
            "selection_mode": "auto",
            "family_keep": "oco_first_touch_clean",
            "barrier_keep": "2,3",
            "horizon_keep": "5,6",
        },
        "state_universe": {
            "rows": [
                {
                    "symbol": "EURUSD",
                    "bar_ticks": 100,
                    "horizon": 5,
                    "state_id": "s1",
                    "family": "oco_first_touch_clean",
                    "barrier_pips": 2.0,
                    "regime_desc": "r1",
                },
                {
                    "symbol": "EURUSD",
                    "bar_ticks": 100,
                    "horizon": 6,
                    "state_id": "s2",
                    "family": "oco_first_touch_clean",
                    "barrier_pips": 3.0,
                    "regime_desc": "r2",
                },
            ]
        },
        "retrain_policy": {"cadence_days": 30, "window_days": 3},
    }
    lock_path = tmp_path / "lock.json"
    lock_path.write_text(json.dumps(lock), encoding="utf-8")

    ok_deploy, checks_out, _ = run(
        lock_path=lock_path,
        mode="deploy",
        as_of=date(2026, 2, 26),
        state_csv=states,
        wfo_config=wfo,
        reduced_config=reduced,
        data_reliability_checks_csv=checks_csv,
    )
    assert not ok_deploy
    assert any(c.name == "data_reliability_no_high_failures" and (not c.ok) for c in checks_out)


def test_validate_lock_blocks_on_high_leakage_fail(tmp_path: Path) -> None:
    wfo = tmp_path / "wfo.yaml"
    reduced = tmp_path / "reduced.yaml"
    states = tmp_path / "states.csv"
    leakage_csv = tmp_path / "oco_leakage_checks.csv"
    wfo.write_text(
        "\n".join(
            [
                "threshold_mode: rolling_days",
                "rolling_threshold_days: 20",
                "rolling_threshold_min_history: 1000",
                "execution_quantile: 0.9",
                "oco_hold_mode: from_touch",
                "oco_include_no_touch: true",
            ]
        ),
        encoding="utf-8",
    )
    reduced.write_text(
        "\n".join(
            [
                "locked_quantile: 0.9",
                "selection_mode: auto",
                "family_keep: oco_first_touch_clean",
                'barrier_keep: "2,3"',
                'horizon_keep: "5,6"',
            ]
        ),
        encoding="utf-8",
    )
    pd.DataFrame(
        [
            {
                "symbol": "EURUSD",
                "bar_ticks": 100,
                "horizon": 5,
                "state_id": "s1",
                "family": "oco_first_touch_clean",
                "barrier_pips": 2.0,
                "regime_desc": "r1",
            },
            {
                "symbol": "EURUSD",
                "bar_ticks": 100,
                "horizon": 6,
                "state_id": "s2",
                "family": "oco_first_touch_clean",
                "barrier_pips": 3.0,
                "regime_desc": "r2",
            },
        ]
    ).to_csv(states, index=False)

    pd.DataFrame(
        [
            {
                "symbol": "EURUSD",
                "check_id": "L01",
                "status": "pass",
                "severity_if_fail": "critical",
            },
            {"symbol": "EURUSD", "check_id": "L06", "status": "fail", "severity_if_fail": "high"},
        ]
    ).to_csv(leakage_csv, index=False)

    preds = tmp_path / "predictions.parquet"
    preds.write_bytes(b"dummy_predictions")
    te_summary = tmp_path / "tick_exact_summary.csv"
    te_summary.write_text("overall_pass\nTrue\n", encoding="utf-8")

    def _sha(path: Path) -> str:
        import hashlib

        h = hashlib.sha256()
        h.update(path.read_bytes())
        return h.hexdigest()

    lock = {
        "frozen_at_utc": "2026-02-25T00:00:00+00:00",
        "symbol": "EURUSD",
        "git": {"commit": "abc123", "branch": "main", "dirty": False},
        "artifacts": {
            "wfo_config_path": str(wfo),
            "wfo_config_sha256": _sha(wfo),
            "reduced_config_path": str(reduced),
            "reduced_config_sha256": _sha(reduced),
            "reduced_states_csv_path": str(states),
            "reduced_states_csv_sha256": _sha(states),
            "predictions_path": str(preds),
            "predictions_sha256": _sha(preds),
            "tick_exact_summary_path": str(te_summary),
            "tick_exact_summary_sha256": _sha(te_summary),
            "tick_exact_overall_pass": True,
        },
        "locked_runtime": {
            "threshold_mode": "rolling_days",
            "rolling_threshold_days": 20,
            "rolling_threshold_min_history": 1000,
            "execution_quantile": 0.9,
            "oco_hold_mode": "from_touch",
            "oco_include_no_touch": True,
            "locked_quantile": 0.9,
            "selection_mode": "auto",
            "family_keep": "oco_first_touch_clean",
            "barrier_keep": "2,3",
            "horizon_keep": "5,6",
        },
        "state_universe": {
            "rows": [
                {
                    "symbol": "EURUSD",
                    "bar_ticks": 100,
                    "horizon": 5,
                    "state_id": "s1",
                    "family": "oco_first_touch_clean",
                    "barrier_pips": 2.0,
                    "regime_desc": "r1",
                },
                {
                    "symbol": "EURUSD",
                    "bar_ticks": 100,
                    "horizon": 6,
                    "state_id": "s2",
                    "family": "oco_first_touch_clean",
                    "barrier_pips": 3.0,
                    "regime_desc": "r2",
                },
            ]
        },
        "retrain_policy": {"cadence_days": 30, "window_days": 3},
    }
    lock_path = tmp_path / "lock.json"
    lock_path.write_text(json.dumps(lock), encoding="utf-8")

    ok_deploy, checks_out, _ = run(
        lock_path=lock_path,
        mode="deploy",
        as_of=date(2026, 2, 26),
        state_csv=states,
        wfo_config=wfo,
        reduced_config=reduced,
        leakage_checks_csv=leakage_csv,
    )
    assert not ok_deploy
    assert any(c.name == "leakage_no_high_failures" and (not c.ok) for c in checks_out)


def test_validate_lock_blocks_on_high_execution_risk_fail(tmp_path: Path) -> None:
    wfo = tmp_path / "wfo.yaml"
    reduced = tmp_path / "reduced.yaml"
    states = tmp_path / "states.csv"
    exec_csv = tmp_path / "oco_execution_risk_checks.csv"
    wfo.write_text(
        "\n".join(
            [
                "threshold_mode: rolling_days",
                "rolling_threshold_days: 20",
                "rolling_threshold_min_history: 1000",
                "execution_quantile: 0.9",
                "oco_hold_mode: from_touch",
                "oco_include_no_touch: true",
            ]
        ),
        encoding="utf-8",
    )
    reduced.write_text(
        "\n".join(
            [
                "locked_quantile: 0.9",
                "selection_mode: auto",
                "family_keep: oco_first_touch_clean",
                'barrier_keep: "2,3"',
                'horizon_keep: "5,6"',
            ]
        ),
        encoding="utf-8",
    )
    pd.DataFrame(
        [
            {
                "symbol": "EURUSD",
                "bar_ticks": 100,
                "horizon": 5,
                "state_id": "s1",
                "family": "oco_first_touch_clean",
                "barrier_pips": 2.0,
                "regime_desc": "r1",
            },
            {
                "symbol": "EURUSD",
                "bar_ticks": 100,
                "horizon": 6,
                "state_id": "s2",
                "family": "oco_first_touch_clean",
                "barrier_pips": 3.0,
                "regime_desc": "r2",
            },
        ]
    ).to_csv(states, index=False)

    pd.DataFrame(
        [
            {
                "symbol": "EURUSD",
                "check_id": "E01",
                "status": "pass",
                "severity_if_fail": "critical",
            },
            {"symbol": "EURUSD", "check_id": "E06", "status": "fail", "severity_if_fail": "high"},
        ]
    ).to_csv(exec_csv, index=False)

    preds = tmp_path / "predictions.parquet"
    preds.write_bytes(b"dummy_predictions")
    te_summary = tmp_path / "tick_exact_summary.csv"
    te_summary.write_text("overall_pass\nTrue\n", encoding="utf-8")

    def _sha(path: Path) -> str:
        import hashlib

        h = hashlib.sha256()
        h.update(path.read_bytes())
        return h.hexdigest()

    lock = {
        "frozen_at_utc": "2026-02-25T00:00:00+00:00",
        "symbol": "EURUSD",
        "git": {"commit": "abc123", "branch": "main", "dirty": False},
        "artifacts": {
            "wfo_config_path": str(wfo),
            "wfo_config_sha256": _sha(wfo),
            "reduced_config_path": str(reduced),
            "reduced_config_sha256": _sha(reduced),
            "reduced_states_csv_path": str(states),
            "reduced_states_csv_sha256": _sha(states),
            "predictions_path": str(preds),
            "predictions_sha256": _sha(preds),
            "tick_exact_summary_path": str(te_summary),
            "tick_exact_summary_sha256": _sha(te_summary),
            "tick_exact_overall_pass": True,
        },
        "locked_runtime": {
            "threshold_mode": "rolling_days",
            "rolling_threshold_days": 20,
            "rolling_threshold_min_history": 1000,
            "execution_quantile": 0.9,
            "oco_hold_mode": "from_touch",
            "oco_include_no_touch": True,
            "locked_quantile": 0.9,
            "selection_mode": "auto",
            "family_keep": "oco_first_touch_clean",
            "barrier_keep": "2,3",
            "horizon_keep": "5,6",
        },
        "state_universe": {
            "rows": [
                {
                    "symbol": "EURUSD",
                    "bar_ticks": 100,
                    "horizon": 5,
                    "state_id": "s1",
                    "family": "oco_first_touch_clean",
                    "barrier_pips": 2.0,
                    "regime_desc": "r1",
                },
                {
                    "symbol": "EURUSD",
                    "bar_ticks": 100,
                    "horizon": 6,
                    "state_id": "s2",
                    "family": "oco_first_touch_clean",
                    "barrier_pips": 3.0,
                    "regime_desc": "r2",
                },
            ]
        },
        "retrain_policy": {"cadence_days": 30, "window_days": 3},
    }
    lock_path = tmp_path / "lock.json"
    lock_path.write_text(json.dumps(lock), encoding="utf-8")

    ok_deploy, checks_out, _ = run(
        lock_path=lock_path,
        mode="deploy",
        as_of=date(2026, 2, 26),
        state_csv=states,
        wfo_config=wfo,
        reduced_config=reduced,
        execution_risk_checks_csv=exec_csv,
    )
    assert not ok_deploy
    assert any(c.name == "execution_risk_no_high_failures" and (not c.ok) for c in checks_out)
