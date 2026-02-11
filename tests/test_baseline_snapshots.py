from __future__ import annotations

import hashlib
import json
from pathlib import Path

from services.api.settings import settings
from services.api.validation import compute_summary


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load(bar: str) -> dict:
    path = Path("data/baselines") / f"baseline_{bar}.json"
    if not path.exists():
        raise AssertionError(f"Missing baseline file: {path}")
    return json.loads(path.read_text())


def _assert_close(actual: float, expected: float, tol: float = 1e-6) -> None:
    if abs(actual - expected) > tol:
        raise AssertionError(f"{actual} != {expected} (tol {tol})")


def _check_guardrail_settings(payload: dict) -> None:
    guard = payload["guardrail_settings"]
    assert settings.guardrail_loss_threshold == guard["loss_threshold"]
    assert settings.guardrail_loss_streak == guard["loss_streak"]
    assert settings.guardrail_cooldown_days == guard["cooldown_days"]


def _compare_summary(actual: dict, expected: dict) -> None:
    for key in (
        "trades",
        "win_rate",
        "mean_pnl",
        "total_pnl",
        "max_dd",
        "sharpe",
        "sharpe_active",
        "sharpe_trade",
    ):
        _assert_close(float(actual[key]), float(expected[key]))


def _run(bar: str, bar_minutes: int) -> None:
    payload = _load(bar)
    pipeline_path = Path(payload["pipeline_path"])
    if not pipeline_path.exists():
        raise AssertionError(f"Pipeline file missing: {pipeline_path}")

    assert payload["pipeline_sha256"] == _sha256(pipeline_path)
    guard = payload["guardrail_settings"]
    prev = (
        settings.guardrail_loss_threshold,
        settings.guardrail_loss_streak,
        settings.guardrail_cooldown_days,
    )
    settings.guardrail_loss_threshold = guard["loss_threshold"]
    settings.guardrail_loss_streak = guard["loss_streak"]
    settings.guardrail_cooldown_days = guard["cooldown_days"]
    try:
        _check_guardrail_settings(payload)

        summary = compute_summary(str(pipeline_path), bar_minutes, guardrail=False)
        summary_guardrail = compute_summary(str(pipeline_path), bar_minutes, guardrail=True)

        _compare_summary(summary, payload["summary"])
        _compare_summary(summary_guardrail, payload["summary_guardrail"])
    finally:
        (
            settings.guardrail_loss_threshold,
            settings.guardrail_loss_streak,
            settings.guardrail_cooldown_days,
        ) = prev


def test_baseline_m5():
    _run("m5", 5)


def test_baseline_m15():
    _run("m15", 15)
