from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from scripts._matrix_warmup import (
    DEFAULT_MARGIN,
    WARMUP_TICKS_AUTO,
    compute_required_warmup_ticks,
    max_bar_ticks_for_symbols,
    parse_bar_ticks_from_uid,
)
from src.behemoth.core.features import FeatureConfig


def _write_locked(path: Path, candidate_uids: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame({"candidate_uid": candidate_uids})
    df.to_parquet(path, index=False)


class TestParseBarTicks:
    def test_canonical_uid(self) -> None:
        assert parse_bar_ticks_from_uid("oco|EURUSD|1000|h6|state_id") == 1000

    def test_different_bar_size(self) -> None:
        assert parse_bar_ticks_from_uid("oco|GBPUSD|500|h12|x") == 500

    def test_too_few_parts(self) -> None:
        assert parse_bar_ticks_from_uid("oco|EURUSD") is None

    def test_non_integer(self) -> None:
        assert parse_bar_ticks_from_uid("oco|EURUSD|abc|h6|x") is None

    def test_empty(self) -> None:
        assert parse_bar_ticks_from_uid("") is None


class TestMaxBarTicksForSymbols:
    def test_single_symbol(self, tmp_path: Path) -> None:
        _write_locked(
            tmp_path / "2026-04" / "eurusd_oco_locked_predictions.parquet",
            ["oco|EURUSD|1000|h6|s1"] * 3,
        )
        assert (
            max_bar_ticks_for_symbols(
                symbols=["EURUSD"], locked_predictions_dir=tmp_path, model_month="2026-04"
            )
            == 1000
        )

    def test_takes_max_across_symbols(self, tmp_path: Path) -> None:
        _write_locked(
            tmp_path / "2026-04" / "eurusd_oco_locked_predictions.parquet",
            ["oco|EURUSD|500|h6|a"],
        )
        _write_locked(
            tmp_path / "2026-04" / "gbpusd_oco_locked_predictions.parquet",
            ["oco|GBPUSD|2000|h12|b"],
        )
        assert (
            max_bar_ticks_for_symbols(
                symbols=["EURUSD", "GBPUSD"],
                locked_predictions_dir=tmp_path,
                model_month="2026-04",
            )
            == 2000
        )

    def test_missing_files_return_zero(self, tmp_path: Path) -> None:
        assert (
            max_bar_ticks_for_symbols(
                symbols=["EURUSD"], locked_predictions_dir=tmp_path, model_month="2026-04"
            )
            == 0
        )

    def test_flat_layout_when_model_month_empty(self, tmp_path: Path) -> None:
        # The local surrogate runner passes --locked-predictions-dir as a flat
        # directory (no model_month subdir). Helper must support both layouts.
        _write_locked(
            tmp_path / "eurusd_oco_locked_predictions.parquet",
            ["oco|EURUSD|1500|h6|s1"],
        )
        assert (
            max_bar_ticks_for_symbols(
                symbols=["EURUSD"], locked_predictions_dir=tmp_path, model_month=""
            )
            == 1500
        )

    def test_skips_unparseable_uids(self, tmp_path: Path) -> None:
        _write_locked(
            tmp_path / "2026-04" / "eurusd_oco_locked_predictions.parquet",
            ["oco|EURUSD|1000|h6|s1", "garbage", "oco|EURUSD|abc|h6|s2"],
        )
        assert (
            max_bar_ticks_for_symbols(
                symbols=["EURUSD"], locked_predictions_dir=tmp_path, model_month="2026-04"
            )
            == 1000
        )


class TestComputeRequiredWarmupTicks:
    def test_returns_full_warmup_bars_times_max_bt_times_margin(self, tmp_path: Path) -> None:
        _write_locked(
            tmp_path / "2026-04" / "eurusd_oco_locked_predictions.parquet",
            ["oco|EURUSD|1000|h6|s1"],
        )
        cfg = FeatureConfig()
        expected = int(cfg.full_warmup_bars * 1000 * DEFAULT_MARGIN)
        actual = compute_required_warmup_ticks(
            symbols=["EURUSD"],
            locked_predictions_dir=tmp_path,
            model_month="2026-04",
        )
        assert actual == expected

    def test_clears_runtime_warmup_gate(self, tmp_path: Path) -> None:
        # The whole point: returned tick count must yield >= full_warmup_bars
        # bars at the largest candidate bar_ticks, so the runtime gate clears.
        _write_locked(
            tmp_path / "2026-04" / "eurusd_oco_locked_predictions.parquet",
            ["oco|EURUSD|1000|h6|s1"],
        )
        cfg = FeatureConfig()
        ticks = compute_required_warmup_ticks(
            symbols=["EURUSD"],
            locked_predictions_dir=tmp_path,
            model_month="2026-04",
        )
        bars_at_largest = ticks // 1000
        assert bars_at_largest >= cfg.full_warmup_bars

    def test_custom_margin(self, tmp_path: Path) -> None:
        _write_locked(
            tmp_path / "2026-04" / "eurusd_oco_locked_predictions.parquet",
            ["oco|EURUSD|1000|h6|s1"],
        )
        cfg = FeatureConfig()
        ticks = compute_required_warmup_ticks(
            symbols=["EURUSD"],
            locked_predictions_dir=tmp_path,
            model_month="2026-04",
            margin=1.5,
        )
        assert ticks == int(cfg.full_warmup_bars * 1000 * 1.5)

    def test_falls_back_when_no_candidates_found(self, tmp_path: Path) -> None:
        # No parquet files written
        assert (
            compute_required_warmup_ticks(
                symbols=["EURUSD"],
                locked_predictions_dir=tmp_path,
                model_month="2026-04",
            )
            == 30_000
        )

    def test_auto_sentinel_value(self) -> None:
        # The sentinel that argparse defaults to must be a non-positive integer
        # so the runner can detect "auto" without confusing it with a real
        # user-supplied value.
        assert WARMUP_TICKS_AUTO <= 0


class TestComputeBarAlignTicks:
    def test_returns_max_bar_ticks_when_candidates_present(self, tmp_path: Path) -> None:
        from scripts._matrix_warmup import compute_bar_align_ticks
        _write_locked(
            tmp_path / "2026-04" / "eurusd_oco_locked_predictions.parquet",
            ["oco|EURUSD|1000|h6|s1"],
        )
        assert (
            compute_bar_align_ticks(
                symbols=["EURUSD"],
                locked_predictions_dir=tmp_path,
                model_month="2026-04",
            )
            == 1000
        )

    def test_returns_zero_when_no_candidates(self, tmp_path: Path) -> None:
        from scripts._matrix_warmup import compute_bar_align_ticks

        # Sentinel return; the runner is expected to fail fast on this.
        assert (
            compute_bar_align_ticks(
                symbols=["EURUSD"],
                locked_predictions_dir=tmp_path,
                model_month="2026-04",
            )
            == 0
        )

    def test_flat_layout_when_model_month_empty(self, tmp_path: Path) -> None:
        from scripts._matrix_warmup import compute_bar_align_ticks
        _write_locked(
            tmp_path / "audusd_oco_locked_predictions.parquet",
            ["oco|AUDUSD|1500|h6|s1"],
        )
        assert (
            compute_bar_align_ticks(
                symbols=["AUDUSD"],
                locked_predictions_dir=tmp_path,
                model_month="",
            )
            == 1500
        )


def test_makefile_local_matrix_targets_request_auto_warmup() -> None:
    makefile = Path(__file__).resolve().parents[1] / "Makefile"
    text = makefile.read_text()
    matrix_block = text.split("local-jforex-parity-matrix:", 1)[1].split(
        "local-jforex-parity-ordinal:", 1
    )[0]
    ordinal_block = text.split("local-jforex-parity-ordinal:", 1)[1].split(
        "local-jforex-parity-spotlight:", 1
    )[0]

    assert "--warmup-ticks $(or $(WARMUP_TICKS),0)" in matrix_block
    assert "--warmup-ticks $(or $(WARMUP_TICKS),0)" in ordinal_block
