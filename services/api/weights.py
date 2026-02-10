import json
import os
from pathlib import Path
from typing import Dict

from .settings import settings


def _default_pairs() -> list[str]:
    try:
        from pipelines.build_events_m5 import PAIRS as PAIRS_M5
    except Exception:
        return []
    return [name for name, *_ in PAIRS_M5]


def load_weights(strategy_id: str | None = None) -> Dict[str, float]:
    path = Path(settings.pair_weights_path)
    if path.exists():
        data = json.loads(path.read_text())
        if isinstance(data, dict):
            if strategy_id and strategy_id in data and isinstance(data[strategy_id], dict):
                return data[strategy_id]
            if "default" in data and isinstance(data["default"], dict):
                return data["default"]
            if all(isinstance(v, (int, float)) for v in data.values()):
                return {k: float(v) for k, v in data.items()}
    # fallback: equal weights over known pairs
    pairs = _default_pairs()
    if not pairs:
        return {}
    return {p: 1.0 for p in pairs}
