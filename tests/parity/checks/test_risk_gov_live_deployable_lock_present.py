"""Tests for risk_gov.live_deployable_lock_present_for_active_month."""
from __future__ import annotations

import json
from pathlib import Path

from behemoth.parity.checks.risk_gov_live_deployable_lock_present import check
from behemoth.parity.types import CheckContext


def _write_lock(history_dir: Path, month: str, symbol: str, *, live_deployable: bool) -> None:
    month_dir = history_dir / month
    month_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": 3,
        "symbol": symbol,
        "bundle": {
            "month": month,
            "dir_relpath": str(month_dir),
            "family": "oco_first_touch_clean",
        },
        "deployability": {
            "model_month": month,
            "live_deployable": live_deployable,
        },
        "artifacts": {},
    }
    (month_dir / f"{symbol.lower()}_oco_first_touch_live_lock.json").write_text(json.dumps(payload))


def test_passes_when_deployable_lock_present(tmp_path: Path) -> None:
    history = tmp_path / "history"
    _write_lock(history, "2026-03", "EURUSD", live_deployable=True)
    ctx = CheckContext(
        history_dir=history,
        active_model_months={"EURUSD": "2026-03"},
        symbols=["EURUSD"],
    )
    result = check(ctx)
    assert result.passed is True
    assert result.failures == []


def test_fails_when_only_non_deployable_lock_present(tmp_path: Path) -> None:
    history = tmp_path / "history"
    _write_lock(history, "2026-03", "AUDUSD", live_deployable=False)
    _write_lock(history, "2026-02", "AUDUSD", live_deployable=True)
    ctx = CheckContext(
        history_dir=history,
        active_model_months={"AUDUSD": "2026-03"},
        symbols=["AUDUSD"],
    )
    result = check(ctx)
    assert result.passed is False
    assert len(result.failures) == 1
    f = result.failures[0]
    assert f["symbol"] == "AUDUSD"
    assert f["active_model_month"] == "2026-03"
    assert f["available_deployable_months"] == ["2026-02"]


def test_fails_when_no_lock_at_all_for_active_month(tmp_path: Path) -> None:
    history = tmp_path / "history"
    _write_lock(history, "2026-02", "USDCHF", live_deployable=True)
    ctx = CheckContext(
        history_dir=history,
        active_model_months={"USDCHF": "2026-03"},
        symbols=["USDCHF"],
    )
    result = check(ctx)
    assert result.passed is False
    assert result.failures[0]["symbol"] == "USDCHF"
