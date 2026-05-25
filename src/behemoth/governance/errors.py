"""Custom exceptions for the governance framework."""

from __future__ import annotations


class GovernanceError(Exception):
    """Base class for governance framework errors."""


class MissingGovernanceFieldError(GovernanceError):
    """Raised when a required governance YAML field is missing."""

    def __init__(self, *, symbol: str, family: str, field: str) -> None:
        super().__init__(
            f"governance YAML for symbol {symbol!r} is missing required "
            f"field {field!r} under family {family!r}"
        )
        self.symbol = symbol
        self.family = family
        self.field = field


class RequiredFamilyMissingThresholdsError(GovernanceError):
    """Raised when a required family has no threshold block."""

    def __init__(self, *, symbol: str, family: str) -> None:
        super().__init__(
            f"symbol {symbol!r} requires family {family!r} but has no "
            "threshold block for it under `families`"
        )
        self.symbol = symbol
        self.family = family


class InvalidModelMonthError(GovernanceError):
    """Raised when `model_month` is not in `YYYY-MM` format."""

    def __init__(self, *, value: str) -> None:
        super().__init__(f"model_month {value!r} is not in YYYY-MM format")
        self.value = value


class UnknownFamilyError(GovernanceError):
    """Raised when a family name is not registered."""

    def __init__(self, *, family: str) -> None:
        super().__init__(f"family {family!r} is not registered")
        self.family = family


class CandidateSchemaError(GovernanceError):
    """Raised when candidate evidence is missing family-required columns."""

    def __init__(self, *, family: str, missing_cols: list[str]) -> None:
        super().__init__(
            f"candidate CSV for family {family!r} is missing required "
            f"columns: {sorted(missing_cols)}"
        )
        self.family = family
        self.missing_cols = missing_cols


class TickStreamGapError(GovernanceError):
    """Raised when a payoff simulator cannot obtain a required tick stream."""

    def __init__(self, *, symbol: str, range_repr: str) -> None:
        super().__init__(f"tick stream gap for symbol {symbol!r} over range {range_repr}")
        self.symbol = symbol
        self.range_repr = range_repr
