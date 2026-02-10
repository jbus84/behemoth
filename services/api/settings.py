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


settings = Settings()
