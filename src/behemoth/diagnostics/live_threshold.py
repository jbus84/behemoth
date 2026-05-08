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
LIVE_FEATURE_COLUMNS = ["close_ts", "symbol", "candidate_uid", "features_json"]
RUNTIME_BAR_COLUMNS = ["ts", "close_ts", "symbol", "bar_ticks"]


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


def _ensure_columns(frame: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    out = frame.copy()
    for column in columns:
        if column not in out.columns:
            out[column] = pd.Series(dtype="object")
    return out


def compare_feature_parity(
    live_features: pd.DataFrame,
    recomputed_features: pd.DataFrame,
    *,
    feature_columns: list[str],
    tolerance: float,
) -> pd.DataFrame:
    rows: list[dict[str, object]] = []

    live_rows = _ensure_columns(
        live_features, ["close_ts", "candidate_uid", "features_json", *feature_columns]
    )
    parsed = live_rows["features_json"].map(_parse_features_json)
    for feature in feature_columns:
        live_rows[feature] = parsed.map(lambda payload: payload.get(feature, np.nan))

    recomputed_rows = _ensure_columns(
        recomputed_features, ["close_ts", "candidate_uid", *feature_columns]
    )

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


def _as_utc_pydatetime(value: pd.Timestamp) -> object:
    ts = pd.Timestamp(value)
    ts = ts.tz_localize("UTC") if ts.tzinfo is None else ts.tz_convert("UTC")
    return ts.to_pydatetime()


def load_live_feature_rows(
    con: duckdb.DuckDBPyConnection,
    *,
    symbol: str,
    start_ts: pd.Timestamp,
    end_ts: pd.Timestamp,
    live_run_id: str,
) -> pd.DataFrame:
    try:
        return con.execute(
            """
            SELECT close_ts, upper(symbol) AS symbol, candidate_uid, features_json
            FROM audit_logs
            WHERE upper(symbol) = upper(?)
              AND close_ts >= ?
              AND close_ts <= ?
              AND lower(run_id) = lower(?)
              AND features_json IS NOT NULL
              AND trim(features_json) <> ''
            ORDER BY close_ts, candidate_uid
            """,
            [
                symbol.upper(),
                _as_utc_pydatetime(start_ts),
                _as_utc_pydatetime(end_ts),
                live_run_id,
            ],
        ).fetchdf()
    except duckdb.Error:
        return pd.DataFrame(columns=LIVE_FEATURE_COLUMNS)


def load_runtime_bars(
    con: duckdb.DuckDBPyConnection,
    *,
    symbol: str,
    bar_ticks: int,
    start_ts: pd.Timestamp,
    end_ts: pd.Timestamp,
) -> pd.DataFrame:
    try:
        return con.execute(
            """
            SELECT *
            FROM tick_bars
            WHERE upper(symbol) = upper(?)
              AND bar_ticks = ?
              AND close_ts >= ?
              AND close_ts <= ?
            ORDER BY close_ts
            """,
            [
                symbol.upper(),
                int(bar_ticks),
                _as_utc_pydatetime(start_ts),
                _as_utc_pydatetime(end_ts),
            ],
        ).fetchdf()
    except duckdb.Error:
        return pd.DataFrame(columns=RUNTIME_BAR_COLUMNS)


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


def summarize_distribution_shift(
    observations: pd.DataFrame,
    *,
    value_columns: list[str],
) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for (symbol, candidate_uid), group in observations.groupby(
        ["symbol", "candidate_uid"], dropna=False
    ):
        history = group[group["period"] == "history"]
        live = group[group["period"] == "live"]
        for metric in value_columns:
            hist_values = pd.to_numeric(history[metric], errors="coerce").dropna()
            live_values = pd.to_numeric(live[metric], errors="coerce").dropna()
            rows.append(
                {
                    "symbol": symbol,
                    "candidate_uid": candidate_uid,
                    "metric": metric,
                    "history_rows": int(len(hist_values)),
                    "live_rows": int(len(live_values)),
                    "history_q50": float(hist_values.quantile(0.50))
                    if len(hist_values)
                    else np.nan,
                    "history_q90": float(hist_values.quantile(0.90))
                    if len(hist_values)
                    else np.nan,
                    "live_q50": float(live_values.quantile(0.50))
                    if len(live_values)
                    else np.nan,
                    "live_q90": float(live_values.quantile(0.90))
                    if len(live_values)
                    else np.nan,
                    "q90_delta_live_minus_history": (
                        float(live_values.quantile(0.90) - hist_values.quantile(0.90))
                        if len(hist_values) and len(live_values)
                        else np.nan
                    ),
                }
            )
    return pd.DataFrame(rows)


def _weighted_quantile(values: np.ndarray, weights: np.ndarray, q: float) -> float:
    mask = np.isfinite(values) & np.isfinite(weights) & (weights > 0)
    values = values[mask]
    weights = weights[mask]
    if len(values) == 0:
        return np.nan
    order = np.argsort(values)
    sorted_values = values[order]
    sorted_weights = weights[order]
    cumulative = np.cumsum(sorted_weights)
    cutoff = float(q) * cumulative[-1]
    return float(sorted_values[np.searchsorted(cumulative, cutoff, side="left")])


def run_threshold_estimator_bakeoff(
    threshold_pool: pd.DataFrame,
    *,
    execution_quantile: float,
    as_of: pd.Timestamp,
) -> pd.DataFrame:
    if threshold_pool.empty:
        return pd.DataFrame(columns=["candidate_uid", "estimator", "threshold", "rows"])
    as_of_ts = pd.Timestamp(as_of)
    as_of_utc = (
        as_of_ts.tz_convert("UTC") if as_of_ts.tzinfo else as_of_ts.tz_localize("UTC")
    )
    pool = threshold_pool.copy()
    pool["close_ts"] = pd.to_datetime(pool["close_ts"], utc=True)
    pool["pred_prob"] = pd.to_numeric(pool["pred_prob"], errors="coerce")
    rows: list[dict[str, object]] = []
    for candidate_uid, group in pool.groupby("candidate_uid", dropna=False):
        values = group["pred_prob"].dropna()
        rows.append(
            {
                "candidate_uid": candidate_uid,
                "estimator": "current_equal_weight",
                "threshold": float(values.quantile(float(execution_quantile)))
                if len(values)
                else np.nan,
                "rows": int(len(values)),
            }
        )
        short = group[group["close_ts"] >= as_of_utc - pd.Timedelta(days=7)][
            "pred_prob"
        ].dropna()
        rows.append(
            {
                "candidate_uid": candidate_uid,
                "estimator": "short_7d_equal_weight",
                "threshold": float(short.quantile(float(execution_quantile)))
                if len(short)
                else np.nan,
                "rows": int(len(short)),
            }
        )
        age_days = (
            (as_of_utc - group["close_ts"]).dt.total_seconds().to_numpy(dtype=float)
            / 86400.0
        )
        weights = np.power(0.5, age_days / 3.0)
        rows.append(
            {
                "candidate_uid": candidate_uid,
                "estimator": "recency_weighted_half_life_3d",
                "threshold": _weighted_quantile(
                    group["pred_prob"].to_numpy(dtype=float),
                    weights,
                    float(execution_quantile),
                ),
                "rows": int(group["pred_prob"].notna().sum()),
            }
        )
        seed_decay_weights = np.where(
            group["source_period"].astype(str).eq("seed"), 0.25, 1.0
        )
        rows.append(
            {
                "candidate_uid": candidate_uid,
                "estimator": "seed_decay_25pct",
                "threshold": _weighted_quantile(
                    group["pred_prob"].to_numpy(dtype=float),
                    seed_decay_weights.astype(float),
                    float(execution_quantile),
                ),
                "rows": int(group["pred_prob"].notna().sum()),
            }
        )
    return pd.DataFrame(rows)


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
