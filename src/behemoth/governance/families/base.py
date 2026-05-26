"""Family governance config and hook base classes."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, Protocol

import pandas as pd

PayoffSimulator = Literal["barrier_touch", "forward_return", "cross_symbol_residual"]


@dataclass(frozen=True)
class FamilyGovernanceConfig:
    """Declarative metadata for a governance family."""

    name: str
    state_key_cols: tuple[str, ...]
    wfo_target_col: str
    payoff_simulator: PayoffSimulator
    selection_gate_cols: tuple[str, ...]
    schema_version: str

    def __post_init__(self) -> None:
        valid = ("barrier_touch", "forward_return", "cross_symbol_residual")
        if self.payoff_simulator not in valid:
            raise ValueError(f"payoff_simulator {self.payoff_simulator!r} must be one of {valid}")


class FamilyGovernanceHooksProtocol(Protocol):
    """Protocol describing the family hook surface."""

    config: FamilyGovernanceConfig

    def derive_state_id(self, row: pd.Series) -> str: ...

    def selection_gate(self, row: pd.Series, thresholds: dict[str, float]) -> bool: ...

    def simulate_one_entry(
        self,
        tick_stream: pd.DataFrame,
        entry_bar: pd.Series,
        params: dict[str, Any],
    ) -> float: ...

    def encode_freeze_artifact(
        self, qualified_states: pd.DataFrame, model_month: str
    ) -> dict[str, Any]: ...


class BaseFamilyGovernanceHooks:
    """Default implementations for family adapters."""

    def __init__(self, config: FamilyGovernanceConfig) -> None:
        self.config = config

    def derive_state_id(self, row: pd.Series) -> str:
        parts: list[str] = []
        for col in self.config.state_key_cols:
            val = row[col]
            if isinstance(val, (int, float)) and not isinstance(val, bool):
                parts.append(format(val, "g"))
            else:
                parts.append(str(val))
        return self.config.name + "__" + "_".join(parts)

    def selection_gate(self, row: pd.Series, thresholds: dict[str, float]) -> bool:
        return True

    def simulate_one_entry(
        self,
        tick_stream: pd.DataFrame,
        entry_bar: pd.Series,
        params: dict[str, Any],
    ) -> float:
        raise NotImplementedError(
            f"adapter for {self.config.name!r} must override simulate_one_entry"
        )

    def encode_freeze_artifact(
        self, qualified_states: pd.DataFrame, model_month: str
    ) -> dict[str, Any]:
        return {
            "family": self.config.name,
            "schema_version": self.config.schema_version,
            "model_month": model_month,
            "qualified_states": qualified_states.to_dict(orient="records"),
        }
