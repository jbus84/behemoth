"""Feature schema validation to prevent silent feature drift.

Detects mismatches between computed features and model contract at startup,
preventing silent inference errors where feature counts or order diverge.
"""

from __future__ import annotations

from typing import Any

from src.behemoth.core.features import (
    CURRENT_MODEL_FEATURE_CONTRACT,
    CURRENT_FEATURE_SCHEMA,
    ModelFeatureContract,
)
from src.behemoth.core.schemas import ModelFeatures


class FeatureSchemaValidator:
    """Validates that computed features match the model contract.

    Usage:
        validator = FeatureSchemaValidator()
        validator.validate_startup()  # Called once at StateManager.__init__
        validator.validate_feature_count(16)  # Validate each compute_features() output
    """

    def __init__(self, contract: ModelFeatureContract | None = None) -> None:
        """Initialize validator with feature contract.

        Args:
            contract: ModelFeatureContract to validate against.
                     Defaults to CURRENT_MODEL_FEATURE_CONTRACT.
        """
        self._contract = contract or CURRENT_MODEL_FEATURE_CONTRACT
        self._schema = CURRENT_FEATURE_SCHEMA

    def validate_startup(self) -> None:
        """Validate schema at StateManager initialization.

        Called once per startup. Ensures:
        - Feature names match model fields
        - Feature count is consistent
        - Schema version is pinned

        Raises:
            ValueError: If any validation fails
        """
        # Validate feature names match ModelFeatures dataclass
        feature_names = tuple(ModelFeatures.model_fields.keys())
        self._contract.validate_feature_names(feature_names)

        # Validate feature count
        expected_count = len(self._contract.feature_names)
        if len(feature_names) != expected_count:
            raise ValueError(
                f"Feature count mismatch: expected {expected_count}, "
                f"got {len(feature_names)}. "
                f"ModelFeatures may have diverged from contract."
            )

        # Validate schema version is pinned
        if self._schema.version != self._contract.schema_version:
            raise ValueError(
                f"Feature schema version mismatch: "
                f"contract={self._contract.schema_version}, "
                f"schema={self._schema.version}. "
                f"Update contract to match current schema."
            )

    def validate_feature_count(self, feature_count: int) -> None:
        """Validate feature count for each inference.

        Called in compute_features() to detect drift early.

        Args:
            feature_count: Number of features computed

        Raises:
            ValueError: If feature count doesn't match contract
        """
        expected = len(self._contract.feature_names)
        if feature_count != expected:
            raise ValueError(
                f"Feature count drift: expected {expected}, got {feature_count}. "
                f"Feature computation may have changed. "
                f"Contract: {self._contract.feature_names}"
            )

    def validate_feature_vector(self, features: ModelFeatures) -> None:
        """Validate a computed feature vector.

        Called after compute_features_from_bars() to ensure output matches contract.

        Args:
            features: Computed ModelFeatures instance

        Raises:
            ValueError: If feature vector doesn't match contract
        """
        # Validate schema version pin
        if features.model_fields.keys() != self._contract.feature_names:
            computed = tuple(features.model_fields.keys())
            self._contract.validate_feature_names(computed)

        # Validate no NaN/Inf in critical fields
        feature_dict = features.model_dump()
        for name, value in feature_dict.items():
            if isinstance(value, float):
                if value != value:  # NaN check
                    raise ValueError(
                        f"NaN detected in feature '{name}'. "
                        f"Rolling window may be insufficient or data is malformed."
                    )
                if value == float('inf') or value == float('-inf'):
                    raise ValueError(
                        f"Inf detected in feature '{name}'. "
                        f"Computation may have division by zero."
                    )

    def warmup_bars_required(self) -> int:
        """Get the warmup bars required before emitting features.

        Returns:
            Number of bars needed for full-precision rolling statistics
        """
        return self._contract.warmup_bars

    def to_dict(self) -> dict[str, Any]:
        """Serialize validator state for logging/debugging.

        Returns:
            Dict with contract and schema info
        """
        return {
            "schema_version": self._schema.version,
            "contract_version": self._contract.schema_version,
            "feature_count": len(self._contract.feature_names),
            "feature_names": list(self._contract.feature_names),
            "warmup_bars": self._contract.warmup_bars,
        }
