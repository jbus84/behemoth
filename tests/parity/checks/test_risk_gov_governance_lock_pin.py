"""Tests for risk_gov.governance_lock_pin."""
from __future__ import annotations

from behemoth.parity import registry
from behemoth.parity.checks import risk_gov_governance_lock_pin  # noqa: F401
from behemoth.parity.checks.risk_gov_governance_lock_pin import _SYMBOLS


def _write_lock(path, model_month: str, lock_hash: str) -> None:
    path.write_text(
        '{"model_month":"' + model_month + '","lock_hash":"' + lock_hash + '"}'
    )


def test_matching_month_passes(parity_ctx_factory):
    ctx = parity_ctx_factory(model_month="2026-04")
    for symbol in _SYMBOLS:
        _write_lock(
            ctx.governance_lock_dir / f"{symbol.lower()}_oco_live_lock.json",
            "2026-04", f"hash-{symbol.lower()}",
        )

    result = registry.call("risk_gov.governance_lock_pin", ctx)
    assert result.passed is True


def test_mismatched_month_fails(parity_ctx_factory):
    ctx = parity_ctx_factory(model_month="2026-04")
    for symbol in _SYMBOLS:
        _write_lock(
            ctx.governance_lock_dir / f"{symbol.lower()}_oco_live_lock.json",
            "2026-04", f"hash-{symbol.lower()}",
        )
    _write_lock(
        ctx.governance_lock_dir / "audusd_oco_live_lock.json",
        "2026-03", "abc",
    )

    result = registry.call("risk_gov.governance_lock_pin", ctx)
    assert result.passed is False
    assert "2026-03" in result.observed
    assert "missing" not in result.observed


def test_missing_lock_fails(parity_ctx_factory):
    ctx = parity_ctx_factory(model_month="2026-04")

    result = registry.call("risk_gov.governance_lock_pin", ctx)
    assert result.passed is False
    assert "missing locks" in result.observed
    for symbol in _SYMBOLS:
        assert symbol in result.observed
