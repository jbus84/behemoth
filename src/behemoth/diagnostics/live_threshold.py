from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import pandas as pd

DiagnosticClassification = Literal[
    "PARITY_BREACH",
    "THRESHOLD_DRIFT",
    "RUNTIME_VARIANCE",
    "MODEL_VALIDITY_CONCERN",
    "INCONCLUSIVE",
]


@dataclass(frozen=True)
class DiagnosticInputs:
    threshold_pool_complete: bool
    threshold_replay_matches: bool
    feature_parity_passed: bool
    feature_parity_checked: bool
    current_pool_lag_detected: bool
    live_distribution_unusual: bool
    model_validity_concern: bool
    evidence_missing: bool


@dataclass(frozen=True)
class LiveThresholdConfig:
    symbol: str
    run_id: str
    live_run_id: str
    lookback_days: int
    execution_quantile: float
    min_history: int
    start_ts: pd.Timestamp
    end_ts: pd.Timestamp
    out_dir: Path


def classify_diagnostic(inputs: DiagnosticInputs) -> DiagnosticClassification:
    if inputs.evidence_missing:
        return "INCONCLUSIVE"
    if not inputs.threshold_pool_complete or not inputs.feature_parity_checked:
        return "INCONCLUSIVE"
    if (not inputs.feature_parity_passed) or (not inputs.threshold_replay_matches):
        return "PARITY_BREACH"
    if inputs.current_pool_lag_detected:
        return "THRESHOLD_DRIFT"
    if inputs.model_validity_concern:
        return "MODEL_VALIDITY_CONCERN"
    if inputs.live_distribution_unusual:
        return "RUNTIME_VARIANCE"
    return "RUNTIME_VARIANCE"
