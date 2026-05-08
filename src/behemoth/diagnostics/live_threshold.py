from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import duckdb
import numpy as np
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


def _source_period(run_id: object, live_run_id: str) -> str:
    value = "" if run_id is None or pd.isna(run_id) else str(run_id).strip().lower()
    if value == "threshold_seed":
        return "seed"
    if value == "warmup":
        return "warmup"
    if value == live_run_id.lower():
        return "live"
    if "live" in value:
        return "live"
    if "warmup" in value:
        return "warmup"
    if "seed" in value:
        return "seed"
    return "other"


def audit_threshold_pool(
    con: duckdb.DuckDBPyConnection,
    *,
    symbol: str,
    execution_quantile: float,
    lookback_days: int,
    min_history: int,
    as_of: pd.Timestamp,
    live_run_id: str,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    as_of_ts = pd.Timestamp(as_of)
    as_of_utc = (
        as_of_ts.tz_convert("UTC")
        if as_of_ts.tzinfo
        else as_of_ts.tz_localize("UTC")
    )
    cutoff = as_of_utc - pd.Timedelta(days=int(lookback_days))
    detail = con.execute(
        """
        SELECT close_ts, upper(symbol) AS symbol, candidate_uid, pred_prob, threshold, model_month, run_id
        FROM audit_logs
        WHERE upper(symbol) = upper(?)
          AND close_ts >= ?
          AND close_ts <= ?
          AND pred_prob IS NOT NULL
        ORDER BY candidate_uid, close_ts, run_id
        """,
        [symbol.upper(), cutoff.to_pydatetime(), as_of_utc.to_pydatetime()],
    ).fetchdf()
    if detail.empty:
        columns = [
            "symbol",
            "candidate_uid",
            "pool_rows",
            "seed_rows",
            "warmup_rows",
            "live_rows",
            "other_rows",
            "p50",
            "p75",
            "p90",
            "p95",
            "replayed_threshold",
            "min_history_met",
            "first_close_ts",
            "last_close_ts",
        ]
        return detail.assign(source_period=pd.Series(dtype="object")), pd.DataFrame(
            columns=columns
        )

    detail["source_period"] = detail["run_id"].map(
        lambda value: _source_period(value, live_run_id)
    )
    detail["pred_prob"] = pd.to_numeric(detail["pred_prob"], errors="coerce")
    rows: list[dict[str, object]] = []
    for (sym, candidate_uid), group in detail.groupby(
        ["symbol", "candidate_uid"], dropna=False
    ):
        probs = group["pred_prob"].dropna()
        source_counts = group["source_period"].value_counts()
        rows.append(
            {
                "symbol": sym,
                "candidate_uid": candidate_uid,
                "pool_rows": int(len(probs)),
                "seed_rows": int(source_counts.get("seed", 0)),
                "warmup_rows": int(source_counts.get("warmup", 0)),
                "live_rows": int(source_counts.get("live", 0)),
                "other_rows": int(source_counts.get("other", 0)),
                "p50": float(probs.quantile(0.50)) if len(probs) else np.nan,
                "p75": float(probs.quantile(0.75)) if len(probs) else np.nan,
                "p90": float(probs.quantile(0.90)) if len(probs) else np.nan,
                "p95": float(probs.quantile(0.95)) if len(probs) else np.nan,
                "replayed_threshold": float(probs.quantile(float(execution_quantile)))
                if len(probs)
                else np.nan,
                "min_history_met": bool(len(probs) >= int(min_history)),
                "first_close_ts": group["close_ts"].min(),
                "last_close_ts": group["close_ts"].max(),
            }
        )
    return detail, pd.DataFrame(rows).sort_values(
        ["symbol", "candidate_uid"]
    ).reset_index(drop=True)
