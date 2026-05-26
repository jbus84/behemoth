"""Freeze artifact writer for governed family payloads."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from src.behemoth.governance.families.base import BaseFamilyGovernanceHooks


def write_freeze_artifact(
    *,
    out_dir: Path,
    symbol: str,
    adapter: BaseFamilyGovernanceHooks,
    qualified_states: pd.DataFrame,
    model_month: str,
) -> Path:
    """Write one per-symbol, per-family governance freeze JSON artifact."""
    payload = adapter.encode_freeze_artifact(
        qualified_states=qualified_states,
        model_month=model_month,
    )
    payload.setdefault("symbol", symbol)

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    path = out_dir / f"{symbol}_{adapter.config.name}_governance_frozen.json"
    path.write_text(json.dumps(payload, sort_keys=True, indent=2, default=str))
    return path
