"""Tests for extract_spotlight_ticks --lock-dir path resolution."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pytest


def _import_main():
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "extract_spotlight_ticks",
        Path(__file__).parents[1] / "scripts" / "extract_spotlight_ticks.py",
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_lock_dir_resolves_locked_parquet(tmp_path):
    """When --lock-dir is given, pred_path uses locked parquet, not monthly."""
    mod = _import_main()

    lock_dir = tmp_path / "lock"
    lock_dir.mkdir()
    locked_parquet = lock_dir / "eurusd_oco_locked_predictions.parquet"
    locked_parquet.touch()

    calls = []

    def fake_extract_symbol(symbol, pred_path, **kwargs):
        calls.append((symbol, pred_path))

    tick_root = tmp_path / "ticks"
    (tick_root / "EURUSD").mkdir(parents=True)
    (tick_root / "EURUSD" / "ticks.parquet").touch()

    with (
        patch.object(mod, "_extract_symbol", side_effect=fake_extract_symbol),
        patch.object(
            sys,
            "argv",
            [
                "extract_spotlight_ticks.py",
                "--symbols",
                "EURUSD",
                "--lock-dir",
                str(lock_dir),
                "--tick-root",
                str(tick_root),
                "--output-dir",
                str(tmp_path / "out"),
                "--model-month",
                "2025-07",
                "--eval-start",
                "",
                "--eval-end",
                "",
            ],
        ),
    ):
        mod.main()

    assert len(calls) == 1
    symbol, pred_path = calls[0]
    assert symbol == "EURUSD"
    assert pred_path == locked_parquet


def test_no_lock_dir_falls_back_to_monthly(tmp_path):
    """When --lock-dir is absent, pred_path uses monthly predictions parquet."""
    mod = _import_main()

    predictions_dir = tmp_path / "preds"
    predictions_dir.mkdir()
    monthly_parquet = predictions_dir / "EURUSD_oco_first_touch_monthly_predictions.parquet"
    monthly_parquet.touch()

    calls = []

    def fake_extract_symbol(symbol, pred_path, **kwargs):
        calls.append((symbol, pred_path))

    tick_root = tmp_path / "ticks"
    (tick_root / "EURUSD").mkdir(parents=True)
    (tick_root / "EURUSD" / "ticks.parquet").touch()

    with (
        patch.object(mod, "_extract_symbol", side_effect=fake_extract_symbol),
        patch.object(
            sys,
            "argv",
            [
                "extract_spotlight_ticks.py",
                "--symbols",
                "EURUSD",
                "--predictions-dir",
                str(predictions_dir),
                "--tick-root",
                str(tick_root),
                "--output-dir",
                str(tmp_path / "out"),
                "--model-month",
                "2025-07",
                "--eval-start",
                "",
                "--eval-end",
                "",
            ],
        ),
    ):
        mod.main()

    assert len(calls) == 1
    symbol, pred_path = calls[0]
    assert symbol == "EURUSD"
    assert pred_path == monthly_parquet


def test_lock_dir_missing_parquet_is_skipped(tmp_path, capsys):
    """Missing locked parquet for a symbol prints a warning and raises SystemExit."""
    mod = _import_main()

    lock_dir = tmp_path / "lock"
    lock_dir.mkdir()
    # Do NOT create the locked parquet

    tick_root = tmp_path / "ticks"
    (tick_root / "EURUSD").mkdir(parents=True)
    (tick_root / "EURUSD" / "ticks.parquet").touch()

    with (
        patch.object(
            sys,
            "argv",
            [
                "extract_spotlight_ticks.py",
                "--symbols",
                "EURUSD",
                "--lock-dir",
                str(lock_dir),
                "--tick-root",
                str(tick_root),
                "--output-dir",
                str(tmp_path / "out"),
                "--model-month",
                "2025-07",
                "--eval-start",
                "",
                "--eval-end",
                "",
            ],
        ),
        pytest.raises(SystemExit),
    ):
        mod.main()

    captured = capsys.readouterr()
    assert "not found" in captured.err.lower() or "eurusd" in captured.err.lower()
