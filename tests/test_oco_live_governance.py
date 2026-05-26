from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pandas as pd

from scripts.freeze_oco_live_governance import (
    _state_universe,
    _subset_omissions,
    _symbols_from_registry,
    _sync_threshold_json_runtime_fields,
)
from scripts.validate_oco_live_governance import run


def test_state_universe_hash_stable_under_row_order(tmp_path: Path) -> None:
    a = pd.DataFrame(
        [
            {
                "symbol": "EURUSD",
                "bar_ticks": 100,
                "horizon": 6,
                "state_id": "s2",
                "family": "oco_first_touch",
                "barrier_pips": 2.0,
                "regime_desc": "r2",
            },
            {
                "symbol": "EURUSD",
                "bar_ticks": 100,
                "horizon": 5,
                "state_id": "s1",
                "family": "oco_first_touch",
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


def test_symbols_from_registry_parses_and_normalizes(tmp_path: Path) -> None:
    registry = tmp_path / "registry.yaml"
    registry.write_text(
        "\n".join(
            [
                "symbols:",
                "  - eurusd",
                "  - GBPUSD",
                "  - EURUSD",
                "  - usdcad",
            ]
        ),
        encoding="utf-8",
    )
    symbols = _symbols_from_registry(registry)
    assert symbols == ["EURUSD", "GBPUSD", "USDCAD"]


def test_subset_omissions_reports_missing_registry_symbols() -> None:
    omitted = _subset_omissions(
        selected=["EURUSD", "GBPUSD"],
        universe=["EURUSD", "GBPUSD", "USDJPY", "AUDUSD"],
    )
    assert omitted == ["AUDUSD", "USDJPY"]


def test_sync_threshold_json_runtime_fields_overwrites_stale_runtime_values(tmp_path: Path) -> None:
    threshold_json = tmp_path / "EURUSD_model_2026-03.json"
    threshold_json.write_text(
        json.dumps(
            {
                "model_month": "2026-03",
                "threshold_source": "rolling_days",
                "rolling_threshold_days": 20,
                "rolling_threshold_min_history": 1000,
                "execution_quantile": 0.9,
                "oco_hold_mode": "from_touch",
                "oco_include_no_touch": True,
            }
        ),
        encoding="utf-8",
    )

    _sync_threshold_json_runtime_fields(
        threshold_json,
        {
            "threshold_mode": "rolling_days",
            "rolling_threshold_days": 20,
            "rolling_threshold_min_history": 300,
            "execution_quantile": 0.9,
            "oco_hold_mode": "from_touch",
            "oco_include_no_touch": True,
        },
    )

    updated = json.loads(threshold_json.read_text(encoding="utf-8"))
    assert updated["rolling_threshold_min_history"] == 300
    assert updated["rolling_threshold_days"] == 20
    assert updated["threshold_source"] == "rolling_days"


def test_validate_lock_deploy_and_retrain_window(tmp_path: Path) -> None:
    wfo = tmp_path / "wfo.yaml"
    reduced = tmp_path / "reduced.yaml"
    states = tmp_path / "states.csv"
    wfo.write_text(
        "\n".join(
            [
                "threshold_mode: rolling_days",
                "rolling_threshold_days: 20",
                "rolling_threshold_min_history: 300",
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
                "family_keep: oco_first_touch",
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
                "family": "oco_first_touch",
                "barrier_pips": 2.0,
                "regime_desc": "r1",
            },
            {
                "symbol": "EURUSD",
                "bar_ticks": 100,
                "horizon": 6,
                "state_id": "s2",
                "family": "oco_first_touch",
                "barrier_pips": 3.0,
                "regime_desc": "r2",
            },
        ]
    ).to_csv(states, index=False)
    preds = tmp_path / "predictions.parquet"
    preds.write_bytes(b"dummy_predictions")
    model_cbm = tmp_path / "EURUSD_model_2026-02.cbm"
    model_cbm.write_bytes(b"dummy_model")
    model_thr = tmp_path / "EURUSD_model_2026-02.json"
    model_thr.write_text('{"model_month":"2026-02"}', encoding="utf-8")
    te_summary = tmp_path / "tick_exact_summary.csv"
    te_summary.write_text("overall_pass\nTrue\n", encoding="utf-8")

    def _sha(path: Path) -> str:
        import hashlib

        h = hashlib.sha256()
        h.update(path.read_bytes())
        return h.hexdigest()

    lock = {
        "schema_version": 2,
        "frozen_at_utc": "2026-02-25T00:00:00+00:00",
        "symbol": "EURUSD",
        "git": {"commit": "abc123", "branch": "main", "dirty": False},
        "artifacts": {
            "wfo_config": {"path": "wfo.yaml", "sha256": _sha(wfo)},
            "reduced_config": {"path": "reduced.yaml", "sha256": _sha(reduced)},
            "allowed_states_csv": {"path": "states.csv", "sha256": _sha(states)},
            "predictions": {"path": "predictions.parquet", "sha256": _sha(preds)},
            "model_cbm": {"path": "EURUSD_model_2026-02.cbm", "sha256": _sha(model_cbm)},
            "model_threshold_json": {
                "path": "EURUSD_model_2026-02.json",
                "sha256": _sha(model_thr),
            },
            "tick_exact_summary": {
                "path": "tick_exact_summary.csv",
                "sha256": _sha(te_summary),
            },
        },
        "deployability": {
            "model_month": "2026-02",
            "tick_exact_overall_pass": True,
            "capacity_overall_pass": True,
            "live_deployable": True,
        },
        "locked_runtime": {
            "threshold_mode": "rolling_days",
            "rolling_threshold_days": 20,
            "rolling_threshold_min_history": 300,
            "execution_quantile": 0.9,
            "oco_hold_mode": "from_touch",
            "oco_include_no_touch": True,
            "locked_quantile": 0.9,
            "selection_mode": "auto",
            "family_keep": "oco_first_touch",
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
                    "family": "oco_first_touch",
                    "barrier_pips": 2.0,
                    "regime_desc": "r1",
                },
                {
                    "symbol": "EURUSD",
                    "bar_ticks": 100,
                    "horizon": 6,
                    "state_id": "s2",
                    "family": "oco_first_touch",
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


def test_validate_lock_state_csv_defaults_to_lock_artifact_latest_month(tmp_path: Path) -> None:
    wfo = tmp_path / "wfo.yaml"
    reduced = tmp_path / "reduced.yaml"
    states_schedule = tmp_path / "states_schedule.csv"
    wfo.write_text(
        "\n".join(
            [
                "threshold_mode: rolling_days",
                "rolling_threshold_days: 20",
                "rolling_threshold_min_history: 300",
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
                "family_keep: oco_first_touch",
                'barrier_keep: "2,3"',
                'horizon_keep: "5,6"',
            ]
        ),
        encoding="utf-8",
    )
    pd.DataFrame(
        [
            {
                "test_month": "2026-01",
                "symbol": "EURUSD",
                "bar_ticks": 100,
                "horizon": 5,
                "state_id": "s1",
                "family": "oco_first_touch",
                "barrier_pips": 2.0,
                "regime_desc": "r1",
            },
            {
                "test_month": "2026-01",
                "symbol": "EURUSD",
                "bar_ticks": 100,
                "horizon": 6,
                "state_id": "s2",
                "family": "oco_first_touch",
                "barrier_pips": 3.0,
                "regime_desc": "r2",
            },
            {
                "test_month": "2025-12",
                "symbol": "EURUSD",
                "bar_ticks": 100,
                "horizon": 6,
                "state_id": "legacy_extra",
                "family": "oco_first_touch",
                "barrier_pips": 2.0,
                "regime_desc": "legacy",
            },
            {
                "test_month": "2026-01",
                "symbol": "GBPUSD",
                "bar_ticks": 100,
                "horizon": 6,
                "state_id": "other_symbol",
                "family": "oco_first_touch",
                "barrier_pips": 2.0,
                "regime_desc": "other",
            },
        ]
    ).to_csv(states_schedule, index=False)
    preds = tmp_path / "predictions.parquet"
    preds.write_bytes(b"dummy_predictions")
    model_cbm = tmp_path / "EURUSD_model_2026-02.cbm"
    model_cbm.write_bytes(b"dummy_model")
    model_thr = tmp_path / "EURUSD_model_2026-02.json"
    model_thr.write_text('{"model_month":"2026-02"}', encoding="utf-8")
    te_summary = tmp_path / "tick_exact_summary.csv"
    te_summary.write_text("overall_pass\nTrue\n", encoding="utf-8")

    def _sha(path: Path) -> str:
        import hashlib

        h = hashlib.sha256()
        h.update(path.read_bytes())
        return h.hexdigest()

    lock = {
        "schema_version": 2,
        "frozen_at_utc": "2026-02-25T00:00:00+00:00",
        "symbol": "EURUSD",
        "git": {"commit": "abc123", "branch": "main", "dirty": False},
        "artifacts": {
            "wfo_config": {"path": str(wfo), "sha256": _sha(wfo)},
            "reduced_config": {"path": str(reduced), "sha256": _sha(reduced)},
            "allowed_states_csv": {"path": str(states_schedule), "sha256": _sha(states_schedule)},
            "predictions": {"path": str(preds), "sha256": _sha(preds)},
            "model_cbm": {"path": str(model_cbm), "sha256": _sha(model_cbm)},
            "model_threshold_json": {"path": str(model_thr), "sha256": _sha(model_thr)},
            "tick_exact_summary": {"path": str(te_summary), "sha256": _sha(te_summary)},
        },
        "deployability": {
            "model_month": "2026-02",
            "tick_exact_overall_pass": True,
            "capacity_overall_pass": True,
            "live_deployable": True,
        },
        "locked_runtime": {
            "threshold_mode": "rolling_days",
            "rolling_threshold_days": 20,
            "rolling_threshold_min_history": 300,
            "execution_quantile": 0.9,
            "oco_hold_mode": "from_touch",
            "oco_include_no_touch": True,
            "locked_quantile": 0.9,
            "selection_mode": "auto",
            "family_keep": "oco_first_touch",
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
                    "family": "oco_first_touch",
                    "barrier_pips": 2.0,
                    "regime_desc": "r1",
                },
                {
                    "symbol": "EURUSD",
                    "bar_ticks": 100,
                    "horizon": 6,
                    "state_id": "s2",
                    "family": "oco_first_touch",
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
        state_csv=None,
        wfo_config=wfo,
        reduced_config=reduced,
    )
    assert ok_deploy
    assert any(c.name == "state_universe_exact_match" and c.ok for c in checks_out)


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
                "rolling_threshold_min_history: 300",
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
                "family_keep: oco_first_touch",
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
                "family": "oco_first_touch",
                "barrier_pips": 2.0,
                "regime_desc": "r1",
            },
            {
                "symbol": "EURUSD",
                "bar_ticks": 100,
                "horizon": 6,
                "state_id": "s2",
                "family": "oco_first_touch",
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
    model_cbm = tmp_path / "EURUSD_model_2026-02.cbm"
    model_cbm.write_bytes(b"dummy_model")
    model_thr = tmp_path / "EURUSD_model_2026-02.json"
    model_thr.write_text('{"model_month":"2026-02"}', encoding="utf-8")
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
            "model_cbm_path": str(model_cbm),
            "model_cbm_sha256": _sha(model_cbm),
            "model_threshold_json_path": str(model_thr),
            "model_threshold_json_sha256": _sha(model_thr),
            "model_month": "2026-02",
            "tick_exact_summary_path": str(te_summary),
            "tick_exact_summary_sha256": _sha(te_summary),
            "tick_exact_overall_pass": True,
        },
        "locked_runtime": {
            "threshold_mode": "rolling_days",
            "rolling_threshold_days": 20,
            "rolling_threshold_min_history": 300,
            "execution_quantile": 0.9,
            "oco_hold_mode": "from_touch",
            "oco_include_no_touch": True,
            "locked_quantile": 0.9,
            "selection_mode": "auto",
            "family_keep": "oco_first_touch",
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
                    "family": "oco_first_touch",
                    "barrier_pips": 2.0,
                    "regime_desc": "r1",
                },
                {
                    "symbol": "EURUSD",
                    "bar_ticks": 100,
                    "horizon": 6,
                    "state_id": "s2",
                    "family": "oco_first_touch",
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
                "rolling_threshold_min_history: 300",
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
                "family_keep: oco_first_touch",
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
                "family": "oco_first_touch",
                "barrier_pips": 2.0,
                "regime_desc": "r1",
            },
            {
                "symbol": "EURUSD",
                "bar_ticks": 100,
                "horizon": 6,
                "state_id": "s2",
                "family": "oco_first_touch",
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
    model_cbm = tmp_path / "EURUSD_model_2026-02.cbm"
    model_cbm.write_bytes(b"dummy_model")
    model_thr = tmp_path / "EURUSD_model_2026-02.json"
    model_thr.write_text('{"model_month":"2026-02"}', encoding="utf-8")
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
            "model_cbm_path": str(model_cbm),
            "model_cbm_sha256": _sha(model_cbm),
            "model_threshold_json_path": str(model_thr),
            "model_threshold_json_sha256": _sha(model_thr),
            "model_month": "2026-02",
            "tick_exact_summary_path": str(te_summary),
            "tick_exact_summary_sha256": _sha(te_summary),
            "tick_exact_overall_pass": True,
        },
        "locked_runtime": {
            "threshold_mode": "rolling_days",
            "rolling_threshold_days": 20,
            "rolling_threshold_min_history": 300,
            "execution_quantile": 0.9,
            "oco_hold_mode": "from_touch",
            "oco_include_no_touch": True,
            "locked_quantile": 0.9,
            "selection_mode": "auto",
            "family_keep": "oco_first_touch",
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
                    "family": "oco_first_touch",
                    "barrier_pips": 2.0,
                    "regime_desc": "r1",
                },
                {
                    "symbol": "EURUSD",
                    "bar_ticks": 100,
                    "horizon": 6,
                    "state_id": "s2",
                    "family": "oco_first_touch",
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
                "rolling_threshold_min_history: 300",
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
                "family_keep: oco_first_touch",
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
                "family": "oco_first_touch",
                "barrier_pips": 2.0,
                "regime_desc": "r1",
            },
            {
                "symbol": "EURUSD",
                "bar_ticks": 100,
                "horizon": 6,
                "state_id": "s2",
                "family": "oco_first_touch",
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
    model_cbm = tmp_path / "EURUSD_model_2026-02.cbm"
    model_cbm.write_bytes(b"dummy_model")
    model_thr = tmp_path / "EURUSD_model_2026-02.json"
    model_thr.write_text('{"model_month":"2026-02"}', encoding="utf-8")
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
            "model_cbm_path": str(model_cbm),
            "model_cbm_sha256": _sha(model_cbm),
            "model_threshold_json_path": str(model_thr),
            "model_threshold_json_sha256": _sha(model_thr),
            "model_month": "2026-02",
            "tick_exact_summary_path": str(te_summary),
            "tick_exact_summary_sha256": _sha(te_summary),
            "tick_exact_overall_pass": True,
        },
        "locked_runtime": {
            "threshold_mode": "rolling_days",
            "rolling_threshold_days": 20,
            "rolling_threshold_min_history": 300,
            "execution_quantile": 0.9,
            "oco_hold_mode": "from_touch",
            "oco_include_no_touch": True,
            "locked_quantile": 0.9,
            "selection_mode": "auto",
            "family_keep": "oco_first_touch",
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
                    "family": "oco_first_touch",
                    "barrier_pips": 2.0,
                    "regime_desc": "r1",
                },
                {
                    "symbol": "EURUSD",
                    "bar_ticks": 100,
                    "horizon": 6,
                    "state_id": "s2",
                    "family": "oco_first_touch",
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
