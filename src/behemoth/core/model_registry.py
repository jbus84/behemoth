"""Model loading and caching registry for CatBoost inference models.

Encapsulates all model lifecycle management: loading, caching, validation,
and threshold config. Supports both live (locked) and historical (lazy) modes.
"""
from __future__ import annotations

import json
import logging
from typing import Any

from src.behemoth.core.bundle_paths import BundlePaths

logger = logging.getLogger(__name__)


class ModelRegistry:
    """Manages model cache, threshold configs, and model availability checks.

    Interface handles:
    - Loading models from governance-locked bindings (live mode)
    - Lazy per-(symbol,month) loading (historical mode)
    - SHA256 validation for artifact integrity
    - Threshold config merging with runtime overrides
    - Cache key generation for symbol and symbol|month
    """

    def __init__(self):
        self._models: dict[str, object] = {}
        self._thresholds: dict[str, dict] = {}
        self._model_months: dict[str, str] = {}

    def has_model(self, symbol: str, family: str | None = None) -> bool:
        """Check if any model is loaded for symbol (exact family or aggregate)."""
        sym = str(symbol).upper().strip()
        if family is not None:
            fam = str(family).strip()
            # Live: SYMBOL|FAMILY, Historical: SYMBOL|MONTH|FAMILY
            for k in self._models:
                parts = k.split("|")
                if parts[0] == sym and parts[-1] == fam:
                    return True
            return False
        # Aggregate: explicit key parsing instead of prefix matching
        for k in self._models:
            parts = k.split("|")
            if parts[0] == sym:
                return True
        return False

    def has_threshold(self, symbol: str, family: str | None = None) -> bool:
        """Check if any threshold config is loaded for symbol (exact family or aggregate)."""
        sym = str(symbol).upper().strip()
        if family is not None:
            fam = str(family).strip()
            for k in self._thresholds:
                parts = k.split("|")
                if parts[0] == sym and parts[-1] == fam:
                    return True
            return False
        # Aggregate: explicit key parsing instead of prefix matching
        for k in self._thresholds:
            parts = k.split("|")
            if parts[0] == sym:
                return True
        return False

    def get_latest_month(self, symbol: str, family: str | None = None) -> str | None:
        """Get latest loaded month for symbol (exact family or aggregate).

        When multiple months exist without a family filter, returns the
        latest month (no error) so status/health paths remain stable.
        """
        sym = str(symbol).upper().strip()
        if family is not None:
            fam = str(family).strip()
            months: set[str] = set()
            for k, m in self._model_months.items():
                parts = k.split("|")
                if parts[0] == sym and parts[-1] == fam:
                    months.add(m)
            if not months:
                return None
            return sorted(months)[-1]
        # Aggregate: explicit key parsing instead of prefix matching
        months: set[str] = set()
        for k, m in self._model_months.items():
            parts = k.split("|")
            if parts[0] == sym:
                months.add(m)
        if not months:
            return None
        return sorted(months)[-1]

    def get_model_and_threshold(
        self, cache_key: str
    ) -> tuple[object | None, dict[str, Any] | None]:
        """Retrieve cached model and threshold config by exact cache key only."""
        model = self._models.get(cache_key)
        thr = self._thresholds.get(cache_key)
        return model, thr

    def set_model_and_threshold(
        self, cache_key: str, model: object, threshold_config: dict, month: str
    ) -> None:
        """Store model, threshold config, and month in cache."""
        self._models[cache_key] = model
        self._thresholds[cache_key] = threshold_config
        self._model_months[cache_key] = month

    def clear(self) -> None:
        """Reset all caches. Called on startup in live mode."""
        self._models.clear()
        self._thresholds.clear()
        self._model_months.clear()

    def cache_size(self) -> int:
        """Return number of models in cache."""
        return len(self._models)

    def models_loaded(self) -> dict[str, str]:
        """Return dict of cache_key -> model_month for status reporting."""
        return dict(self._model_months)

    def load_bundle_paths(
        self,
        *,
        symbol: str,
        bundle_paths: BundlePaths,
        cache_key: str,
        locked_runtime_overrides: dict[str, Any] | None = None,
        expected_month: str | None = None,
        catboost_cls: type | None = None,
    ) -> tuple[bool, str]:
        """Load and validate a governance-locked bundle paths.

        Args:
            symbol: Trading symbol (e.g., "GBPUSD")
            bundle_paths: BundlePaths instance with model artifact accessors
            cache_key: Cache key (symbol or symbol|month)
            locked_runtime_overrides: Optional overrides from locked_runtime
            expected_month: Optional expected month; if mismatch, fail
            catboost_cls: CatBoost class to instantiate; if None, returns False

        Returns:
            (success, reason_or_month): If success=True, reason is the loaded month.
                                       If success=False, reason is error code.
        """
        if catboost_cls is None:
            return False, "catboost_unavailable"

        model_path = bundle_paths.model_cbm()
        thr_path = bundle_paths.model_threshold_json()
        lock_month = bundle_paths.model_month

        if (not model_path.exists()) or (not thr_path.exists()):
            logger.error(
                "Locked artifacts missing for %s: model=%s threshold=%s",
                symbol,
                model_path,
                thr_path,
            )
            return False, "artifact_missing"

        # BundlePaths.model_cbm() and model_threshold_json() verify sha256 on call
        month = model_path.stem.split("_")[-1]
        if lock_month and (month != lock_month):
            logger.error(
                "Locked model month mismatch for %s: lock=%s file=%s",
                symbol,
                lock_month,
                month,
            )
            return False, "lock_month_mismatch"
        if expected_month and month != expected_month:
            logger.error(
                "Expected model month mismatch for %s: expected=%s file=%s",
                symbol,
                expected_month,
                month,
            )
            return False, "expected_month_mismatch"

        model = catboost_cls()
        model.load_model(str(model_path))
        thr_cfg = json.loads(thr_path.read_text())

        # Validate feature schema version
        feature_schema_version = str(thr_cfg.get("feature_schema_version", "")).strip()
        if not feature_schema_version:
            logger.warning(
                "Threshold JSON missing feature_schema_version for %s — "
                "this artifact may be incompatible with current feature contract",
                symbol
            )
        else:
            # Expected version should be documented in governance locks
            # Current version: 1.0 (16-feature set per CURRENT_FEATURE_SCHEMA)
            if feature_schema_version != "1.0":
                logger.error(
                    "Feature schema version mismatch for %s: threshold=%s expected=1.0",
                    symbol,
                    feature_schema_version,
                )
                return False, "feature_schema_version_mismatch"

        if locked_runtime_overrides and isinstance(locked_runtime_overrides, dict):
            thr_cfg.update(
                {
                    str(k): v
                    for k, v in locked_runtime_overrides.items()
                    if str(k).strip() and v is not None
                }
            )
        thr_month = str(thr_cfg.get("model_month", "")).strip()
        if thr_month and thr_month != month:
            logger.error(
                "Threshold JSON model month mismatch for %s: model=%s threshold=%s",
                symbol,
                month,
                thr_month,
            )
            return False, "threshold_month_mismatch"
        self.set_model_and_threshold(cache_key, model, thr_cfg, month)
        logger.info("Loaded lock-bound model for %s (month %s): %s", symbol, month, model_path.name)
        return True, month

    @staticmethod
    def make_cache_key(symbol: str, model_month: str | None = None, family: str | None = None) -> str:
        """Generate cache key: symbol, symbol|month, symbol|month|family, or symbol|family."""
        sym = str(symbol).upper().strip()
        parts = [sym]
        if model_month:
            parts.append(str(model_month).strip())
        fam = str(family or "").strip()
        if fam:
            parts.append(fam)
        return "|".join(parts)
