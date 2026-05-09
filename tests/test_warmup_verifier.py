"""Test WarmupBoundaryVerifier — observable status instead of silent None."""

from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from src.behemoth.runtime.warmup_verifier import WarmupBoundaryVerifier, WarmupStatus
from scripts._matrix_warmup import compute_required_warmup_ticks


class TestWarmupBoundaryVerifier:
    """Verify warmup gate decisions are observable."""

    def test_ok_when_bar_count_meets_threshold(self) -> None:
        """Check returns ok=True when bar count >= required."""
        verifier = WarmupBoundaryVerifier(warmup_bars=289)
        status = verifier.check(bar_count=289)
        assert status.ok is True
        assert status.deficit == 0
        assert status.bar_count == 289
        assert status.required == 289

    def test_ok_when_bar_count_exceeds_threshold(self) -> None:
        """Check returns ok=True when bar count > required."""
        verifier = WarmupBoundaryVerifier(warmup_bars=289)
        status = verifier.check(bar_count=500)
        assert status.ok is True
        assert status.deficit == 0

    def test_deficit_computed_correctly(self) -> None:
        """Check returns correct deficit when bar count < required."""
        verifier = WarmupBoundaryVerifier(warmup_bars=289)
        status = verifier.check(bar_count=100)
        assert status.ok is False
        assert status.deficit == 189
        assert status.bar_count == 100
        assert status.required == 289

    def test_deficit_zero_when_exactly_at_threshold(self) -> None:
        """Check deficit is always 0 when ok=True."""
        verifier = WarmupBoundaryVerifier(warmup_bars=289)
        status = verifier.check(bar_count=289)
        assert status.ok is True
        assert status.deficit == 0

    def test_deficit_when_zero_bars(self) -> None:
        """Check reports full required count as deficit when no bars."""
        verifier = WarmupBoundaryVerifier(warmup_bars=289)
        status = verifier.check(bar_count=0)
        assert status.ok is False
        assert status.deficit == 289

    def test_status_is_frozen(self) -> None:
        """WarmupStatus is immutable."""
        status = WarmupStatus(ok=True, bar_count=100, required=100, deficit=0)
        with pytest.raises(AttributeError):
            status.ok = False


class TestMatrixWarmupFixedFallback:
    """Verify _matrix_warmup.py no longer silently returns fallback."""

    def test_compute_required_warmup_ticks_raises_when_no_candidates(self) -> None:
        """compute_required_warmup_ticks raises RuntimeError when no locked candidates found."""
        with TemporaryDirectory() as tmpdir:
            empty_dir = Path(tmpdir)
            with pytest.raises(RuntimeError, match="No locked candidates found"):
                compute_required_warmup_ticks(
                    symbols=["EURUSD", "GBPUSD"],
                    locked_predictions_dir=empty_dir,
                )
