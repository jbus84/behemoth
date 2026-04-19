"""Shared parity-check fixtures seeded from the 2026-04-17 session.

Two factories: a clean CheckContext and a divergent one.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from behemoth.parity.types import CheckContext


@pytest.fixture
def parity_ctx_factory(tmp_path: Path):
    """Returns a factory that builds a CheckContext rooted at tmp_path."""
    def _build(run_id: str = "jforex_live", model_month: str = "2026-04") -> CheckContext:
        (tmp_path / "reconcile").mkdir(parents=True, exist_ok=True)
        (tmp_path / "reconcile" / "runtime").mkdir(exist_ok=True)
        (tmp_path / "governance").mkdir(exist_ok=True)
        return CheckContext(
            run_id=run_id,
            model_month=model_month,
            reconcile_dir=tmp_path / "reconcile",
            live_state_db_path=tmp_path / "reconcile" / "runtime" / "live_state.db",
            governance_lock_dir=tmp_path / "governance",
        )
    return _build


def write_signal_parity_csv(reconcile_dir: Path, symbol: str, *,
                             passed: bool, predict_cycles: int,
                             failed_signal_events: int) -> None:
    reconcile_dir.mkdir(parents=True, exist_ok=True)
    path = reconcile_dir / f"{symbol}_jforex_signal_parity_summary.csv"
    path.write_text(
        "symbol,jforex_signal_parity_pass,predict_cycles,failed_signal_events\n"
        f"{symbol},{str(passed).lower()},{predict_cycles},{failed_signal_events}\n"
    )
