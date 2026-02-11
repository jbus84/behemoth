from __future__ import annotations

from pathlib import Path

from .settings import settings
from .validation import PIPELINE_PATHS
from .weights import load_weights


def _validate_pct(name: str, value: float) -> list[str]:
    errors = []
    if value < 0 or value > 1:
        errors.append(f"{name} must be within [0, 1], got {value}")
    return errors


def validate_runtime_config() -> None:
    errors: list[str] = []

    errors += _validate_pct("max_daily_loss_pct", settings.max_daily_loss_pct)
    errors += _validate_pct("max_daily_loss_buffer_pct", settings.max_daily_loss_buffer_pct)
    errors += _validate_pct("max_dd_pct", settings.max_dd_pct)
    errors += _validate_pct("max_dd_buffer_pct", settings.max_dd_buffer_pct)

    if (
        settings.max_daily_loss_buffer_pct
        and settings.max_daily_loss_pct
        and settings.max_daily_loss_buffer_pct > settings.max_daily_loss_pct
    ):
        errors.append("max_daily_loss_buffer_pct must be <= max_daily_loss_pct")
    if (
        settings.max_dd_buffer_pct
        and settings.max_dd_pct
        and settings.max_dd_buffer_pct > settings.max_dd_pct
    ):
        errors.append("max_dd_buffer_pct must be <= max_dd_pct")

    if settings.guardrail_loss_streak < 1:
        errors.append("guardrail_loss_streak must be >= 1")
    if settings.guardrail_cooldown_days < 0:
        errors.append("guardrail_cooldown_days must be >= 0")

    if settings.require_pair_weights:
        weights_path = Path(settings.pair_weights_path)
        if not weights_path.exists():
            errors.append(f"pair_weights_path not found: {weights_path}")

    weights = load_weights(None)
    if weights:
        if any(v < 0 for v in weights.values()):
            errors.append("pair weights must be non-negative")
        if sum(max(v, 0.0) for v in weights.values()) <= 0:
            errors.append("pair weights sum must be > 0")

    if settings.validate_pipeline_files:
        for bar, path in PIPELINE_PATHS.items():
            if not Path(path).exists():
                errors.append(f"pipeline file missing for {bar}: {path}")

    if errors:
        message = "Runtime config validation failed:\n- " + "\n- ".join(errors)
        raise RuntimeError(message)
