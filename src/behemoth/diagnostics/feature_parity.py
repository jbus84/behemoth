"""Feature parity check: compare stored live features to recomputed features.

Reads ``features_json`` payloads from ``audit_logs`` and compares each named
feature against the value that would be produced by re-running the feature
pipeline against the underlying ``tick_bars`` rows. A diagnostic exposes the
delta per (close_ts, candidate_uid, feature) tuple.

Extracted from ``live_threshold.py`` so the parity logic has its own narrow
seam and the tz-mismatch bug (live close_ts came in as Europe/London, recomputed
close_ts as UTC; pandas merge silently produced all-NaN live columns) can be
caught by a focused test.
"""

from __future__ import annotations

import json
from typing import Any

import duckdb
import numpy as np
import pandas as pd

from src.behemoth.core.features import compute_feature_matrix_from_bars

FEATURE_PARITY_COLUMNS: list[str] = [
    "close_ts",
    "candidate_uid",
    "feature",
    "live_value",
    "recomputed_value",
    "abs_diff",
    "status",
]
LIVE_FEATURE_COLUMNS: list[str] = ["close_ts", "symbol", "candidate_uid", "features_json"]
RUNTIME_BAR_COLUMNS: list[str] = ["ts", "close_ts", "symbol", "bar_ticks"]


def parse_features_json(value: object) -> dict[str, float]:
    """Parse a ``features_json`` payload into a flat dict of floats.

    Tolerant: returns ``{}`` on null, NaN, malformed JSON, or any value that
    can't be coerced to ``float``.
    """
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


def _normalize_close_ts_to_utc(frame: pd.DataFrame) -> pd.DataFrame:
    """Coerce ``close_ts`` to UTC tz-aware so merges are safe.

    Without this, a ``close_ts`` column read from DuckDB localized to
    ``Europe/London`` would not merge with one set via
    ``pd.to_datetime(..., utc=True)``: same instants but different tz
    representations. pandas treats them as different keys → all-NaN merge
    rows → false ``MISSING`` parity verdict.
    """
    if "close_ts" not in frame.columns:
        return frame
    out = frame.copy()
    out["close_ts"] = pd.to_datetime(out["close_ts"], utc=True)
    return out


def feature_columns_from_live_rows(live_features: pd.DataFrame) -> list[str]:
    """Extract the union of feature names that appear in any ``features_json`` payload."""
    if live_features.empty or "features_json" not in live_features.columns:
        return []
    columns: set[str] = set()
    for payload in live_features["features_json"]:
        columns.update(parse_features_json(payload).keys())
    return sorted(columns)


def compare_feature_parity(
    live_features: pd.DataFrame,
    recomputed_features: pd.DataFrame,
    *,
    feature_columns: list[str],
    tolerance: float,
) -> pd.DataFrame:
    """Merge live and recomputed feature frames, return rows where the values disagree.

    Both inputs must have ``close_ts`` and ``candidate_uid``. ``close_ts`` on
    each side is normalized to UTC before merging so timezone differences
    don't cause spurious ``MISSING`` rows. ``live_features`` must have a
    ``features_json`` column whose payloads contain the named features.

    A row is included in the result iff its ``status != PASS``:
    ``PASS``, ``MISMATCH`` (numerical delta > tolerance), or ``MISSING`` (one
    side absent at the merge key).
    """
    rows: list[dict[str, object]] = []

    live_rows = _ensure_columns(
        live_features, ["close_ts", "candidate_uid", "features_json", *feature_columns]
    )
    live_rows = _normalize_close_ts_to_utc(live_rows)
    parsed = live_rows["features_json"].map(parse_features_json)
    for feature in feature_columns:
        live_rows[feature] = parsed.map(lambda payload, _f=feature: payload.get(_f, np.nan))

    recomputed_rows = _ensure_columns(
        recomputed_features, ["close_ts", "candidate_uid", *feature_columns]
    )
    recomputed_rows = _normalize_close_ts_to_utc(recomputed_rows)

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


def load_live_feature_rows(
    con: duckdb.DuckDBPyConnection,
    *,
    symbol: str,
    candidate_uid: str | None,
    start_ts: pd.Timestamp,
    end_ts: pd.Timestamp,
    live_run_id: str | None = None,
) -> pd.DataFrame:
    """Load live ``audit_logs`` rows with ``features_json`` populated for the parity check."""
    if candidate_uid is None:
        return pd.DataFrame(columns=LIVE_FEATURE_COLUMNS)
    sql = """
        SELECT close_ts, upper(symbol) AS symbol, candidate_uid, features_json
        FROM audit_logs
        WHERE symbol = ?
          AND candidate_uid = ?
          AND close_ts BETWEEN ? AND ?
          AND features_json IS NOT NULL
          AND trim(features_json) <> ''
    """
    params: list[Any] = [symbol.upper(), candidate_uid, start_ts.to_pydatetime(), end_ts.to_pydatetime()]
    if live_run_id is not None:
        sql += " AND run_id = ?"
        params.append(live_run_id)
    sql += " ORDER BY close_ts"
    return con.execute(sql, params).df()


def load_runtime_bars(
    con: duckdb.DuckDBPyConnection,
    *,
    symbol: str,
    bar_ticks: int,
    start_ts: pd.Timestamp,
    end_ts: pd.Timestamp,
) -> pd.DataFrame:
    """Load tick_bars rows for recomputing features."""
    return con.execute(
        """
        SELECT row_id, ts, close_ts, symbol, bar_ticks,
               open_bid, high_bid, low_bid, close_bid,
               high_ask, close_ask, spread, tick_volume,
               hl_first, hl_pos_frac
        FROM tick_bars
        WHERE symbol = ? AND bar_ticks = ?
          AND close_ts BETWEEN ? AND ?
        ORDER BY close_ts
        """,
        [symbol.upper(), int(bar_ticks), start_ts.to_pydatetime(), end_ts.to_pydatetime()],
    ).df()


def _parse_barrier_pips(value: object) -> float:
    """Extract a numeric ``barrier_pips`` from a candidate_uid rule segment.

    Accepts a literal float, a ``b<n>`` prefix, or a trailing ``_k<n>``
    convention used by the rule UIDs (e.g. ``oco_first_touch__all__k2``
    → 2.0).
    """
    import re

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


def parse_canonical_uid(candidate_uid: str) -> tuple[int, int, float]:
    """Extract ``(bar_ticks, horizon, barrier_pips)`` from canonical UID.

    Canonical form: ``oco|SYM|<bar_ticks>|h<horizon>|<rule>`` where ``<rule>``
    encodes ``barrier_pips`` via a trailing ``_k<n>`` convention.
    """
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
    """Recompute features from ``tick_bars`` and tag with the candidate UID + close_ts."""
    bar_ticks, horizon, barrier_pips = parse_canonical_uid(candidate_uid)
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
