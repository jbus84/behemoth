from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import duckdb
import numpy as np
import pandas as pd

from src.behemoth.core.features import compute_feature_matrix_from_bars

DiagnosticClassification = Literal[
    "PARITY_BREACH",
    "THRESHOLD_DRIFT",
    "RUNTIME_VARIANCE",
    "MODEL_VALIDITY_CONCERN",
    "INCONCLUSIVE",
]

FEATURE_PARITY_COLUMNS = [
    "close_ts",
    "candidate_uid",
    "feature",
    "live_value",
    "recomputed_value",
    "abs_diff",
    "status",
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


def _parse_features_json(value: object) -> dict[str, float]:
    import json

    if value is None or pd.isna(value):
        return {}
    try:
        raw = json.loads(str(value))
    except json.JSONDecodeError:
        return {}
    out: dict[str, float] = {}
    for key, item in raw.items():
        try:
            out[str(key)] = float(item)
        except (TypeError, ValueError):
            continue
    return out


def compare_feature_parity(
    live_features: pd.DataFrame,
    recomputed_features: pd.DataFrame,
    *,
    feature_columns: list[str],
    tolerance: float,
) -> pd.DataFrame:
    rows: list[dict[str, object]] = []

    live_rows = live_features.copy()
    if "features_json" not in live_rows.columns:
        live_rows["features_json"] = pd.Series(dtype="object")
    parsed = live_rows["features_json"].map(_parse_features_json)
    for feature in feature_columns:
        live_rows[feature] = parsed.map(lambda payload: payload.get(feature, np.nan))

    recomputed_rows = recomputed_features.copy()
    for column in ["close_ts", "candidate_uid", *feature_columns]:
        if column not in recomputed_rows.columns:
            recomputed_rows[column] = pd.Series(dtype="object")

    merged = live_rows.merge(
        recomputed_rows[["close_ts", "candidate_uid", *feature_columns]],
        on=["close_ts", "candidate_uid"],
        how="outer",
        suffixes=("_live", "_recomputed"),
        indicator=True,
    )
    for _, row in merged.iterrows():
        for feature in feature_columns:
            live_value = row.get(f"{feature}_live", np.nan)
            recomputed_value = row.get(f"{feature}_recomputed", np.nan)
            if pd.isna(live_value) or pd.isna(recomputed_value):
                status = "MISSING"
                abs_diff = np.nan
            else:
                abs_diff = abs(float(live_value) - float(recomputed_value))
                status = "PASS" if abs_diff <= float(tolerance) else "MISMATCH"
            if status != "PASS":
                rows.append(
                    {
                        "close_ts": row.get("close_ts"),
                        "candidate_uid": row.get("candidate_uid"),
                        "feature": feature,
                        "live_value": live_value,
                        "recomputed_value": recomputed_value,
                        "abs_diff": abs_diff,
                        "status": status,
                    }
                )
    return pd.DataFrame(rows, columns=FEATURE_PARITY_COLUMNS)


def _parse_barrier_pips(value: object) -> float:
    text = str(value).strip()
    try:
        return float(text)
    except ValueError:
        pass

    leading_b = re.fullmatch(r"b([+-]?\d+(?:\.\d+)?)", text)
    if leading_b:
        return float(leading_b.group(1))

    trailing_k = re.search(r"(?:^|_)k([+-]?\d+(?:\.\d+)?)$", text)
    if trailing_k:
        return float(trailing_k.group(1))

    raise ValueError(f"barrier_pips cannot be resolved from candidate_uid segment: {value}")


def _parse_canonical_uid(candidate_uid: str) -> tuple[int, int, float]:
    parts = str(candidate_uid).split("|")
    if len(parts) < 5:
        raise ValueError(f"candidate_uid is not canonical: {candidate_uid}")
    bar_ticks = int(parts[2])
    horizon = int(parts[3].removeprefix("h"))
    barrier_pips = _parse_barrier_pips(parts[4])
    return bar_ticks, horizon, barrier_pips


def recompute_features_from_runtime_bars(
    bars: pd.DataFrame,
    *,
    symbol: str,
    candidate_uid: str,
    feature_columns: list[str],
) -> pd.DataFrame:
    bar_ticks, horizon, barrier_pips = _parse_canonical_uid(candidate_uid)
    frame = bars.rename(columns={"ts": "timestamp"}).copy()
    matrix = compute_feature_matrix_from_bars(
        frame,
        symbol=symbol.upper(),
        bar_ticks=bar_ticks,
        horizon=horizon,
        barrier_pips=barrier_pips,
    )
    if matrix is None or matrix.empty:
        return pd.DataFrame(columns=["close_ts", "candidate_uid", *feature_columns])
    out = matrix.loc[:, feature_columns].copy()
    out["close_ts"] = pd.to_datetime(frame.loc[matrix.index, "close_ts"], utc=True).to_numpy()
    out["candidate_uid"] = candidate_uid
    return out[["close_ts", "candidate_uid", *feature_columns]]


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


def _duckdb_quantile(
    con: duckdb.DuckDBPyConnection, values: pd.Series, quantile: float
) -> float:
    row = con.execute(
        """
        SELECT quantile(pred_prob, ?)
        FROM (SELECT unnest(?::DOUBLE[]) AS pred_prob)
        """,
        [float(quantile), values.tolist()],
    ).fetchone()
    return float(row[0])


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
                "replayed_threshold": _duckdb_quantile(con, probs, execution_quantile)
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
