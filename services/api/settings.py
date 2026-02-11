from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def _yaml_settings_source() -> dict[str, Any]:
    path = Path(os.getenv("CONFIG_PATH", "configs/api.yaml"))
    if not path.exists():
        return {}
    data = yaml.safe_load(path.read_text())
    return data or {}


class Settings(BaseSettings):
    database_url: str = Field(
        default="postgresql+psycopg2://behemoth:behemoth@localhost:5432/behemoth",
        validation_alias=AliasChoices("DATABASE_URL", "database_url"),
    )
    redis_url: str = Field(
        default="redis://localhost:6379/0",
        validation_alias=AliasChoices("REDIS_URL", "redis_url"),
    )
    enable_redis: bool = Field(default=True)
    auto_create_tables: bool = Field(default=False)
    log_level: str = Field(default="INFO")
    metrics_enabled: bool = Field(default=True)
    validate_pipeline_files: bool = Field(default=True)
    require_pair_weights: bool = Field(default=True)

    guardrail_enabled: bool = Field(default=True)
    guardrail_loss_threshold: float = Field(default=0.0)
    guardrail_loss_streak: int = Field(default=3)
    guardrail_cooldown_days: int = Field(default=7)

    account_equity_start: float = Field(default=100000.0)
    max_daily_loss_pct: float = Field(default=0.05)
    max_dd_pct: float = Field(default=0.10)
    max_consecutive_losses: int = Field(default=5)
    max_total_exposure_pct: float = Field(default=1.0)
    max_pair_exposure_pct: float = Field(default=0.10)
    max_weight_overshoot_pct: float = Field(default=0.10)
    pair_weights_path: str = Field(default="configs/pair_weights.yaml")

    model_config = SettingsConfigDict(env_prefix="", extra="ignore")

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls,
        init_settings,
        env_settings,
        dotenv_settings,
        file_secret_settings,
    ):
        return (
            init_settings,
            _yaml_settings_source,
            env_settings,
            file_secret_settings,
        )


settings = Settings()
