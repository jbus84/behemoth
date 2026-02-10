import os


class Settings:
    def __init__(self):
        self.database_url = os.getenv(
            "DATABASE_URL",
            "postgresql+psycopg2://behemoth:behemoth@localhost:5432/behemoth",
        )
        self.redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
        self.enable_redis = os.getenv("ENABLE_REDIS", "true").lower() in ("1", "true", "yes")
        self.auto_create_tables = os.getenv("AUTO_CREATE_TABLES", "false").lower() in ("1", "true", "yes")
        self.guardrail_enabled = os.getenv("GUARDRAIL_ENABLED", "true").lower() in ("1", "true", "yes")
        self.guardrail_loss_threshold = float(os.getenv("GUARDRAIL_LOSS_THRESHOLD", "0.0"))
        self.guardrail_loss_streak = int(os.getenv("GUARDRAIL_LOSS_STREAK", "3"))
        self.guardrail_cooldown_days = int(os.getenv("GUARDRAIL_COOLDOWN_DAYS", "7"))
        self.account_equity_start = float(os.getenv("ACCOUNT_EQUITY_START", "100000"))
        self.max_daily_loss_pct = float(os.getenv("MAX_DAILY_LOSS_PCT", "0.05"))
        self.max_dd_pct = float(os.getenv("MAX_DD_PCT", "0.10"))
        self.max_consecutive_losses = int(os.getenv("MAX_CONSECUTIVE_LOSSES", "5"))
        self.max_total_exposure_pct = float(os.getenv("MAX_TOTAL_EXPOSURE_PCT", "1.0"))
        self.max_pair_exposure_pct = float(os.getenv("MAX_PAIR_EXPOSURE_PCT", "0.10"))
        self.max_weight_overshoot_pct = float(os.getenv("MAX_WEIGHT_OVERSHOOT_PCT", "0.10"))
        self.pair_weights_path = os.getenv("PAIR_WEIGHTS_PATH", "configs/pair_weights.json")


settings = Settings()
