"""Historical prediction payload staging for exact replay parity in backtesting.

Encapsulates lazy loading and caching of locked historical prediction data:
- Universe of predictions per (symbol, month)
- Per-candidate timestamps for tolerant replay gating
- Per-candidate ordinal indices for tick-perfect replay
- Payload rows for attribute injection
- Cursor state for row enumeration
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from src.behemoth.core.bundle_paths import BundlePaths

logger = logging.getLogger(__name__)

_HISTORICAL_PREDICTION_TOLERANCE_SEC = 30.0


class HistoricalPredictionLoadError(RuntimeError):
    """Raised when historical prediction staging cannot satisfy its load contract."""


class MissingHistoricalPredictionArtifact(HistoricalPredictionLoadError):
    """Raised when a locked predictions parquet artifact is missing."""


@dataclass(frozen=True)
class HistoricalPredictionLoadStatus:
    cache_key: str
    predictions_path: str
    status: str
    detail: str = ""


class HistoricalPredictionStage:
    """Manages lazy-loaded historical prediction artifacts for backtesting.

    Loads locked prediction data from parquet files on-demand per (symbol, month).
    Caches results to avoid repeated disk I/O during bar evaluation.
    """

    def __init__(self, *, strict_missing: bool = False):
        self._strict_missing = bool(strict_missing)
        self._universes: dict[str, dict[datetime, set[str]]] = {}
        self._candidate_index: dict[str, dict[str, list[datetime]]] = {}
        self._candidate_ordinal_index: dict[str, dict[str, list[int]]] = {}
        self._candidate_cursor: dict[str, dict[str, int]] = {}
        self._payload_rows: dict[str, dict[str, list[dict[str, Any]]]] = {}
        self._payload_cursor: dict[str, dict[str, int]] = {}
        self._load_status: dict[str, HistoricalPredictionLoadStatus] = {}

    def clear(self) -> None:
        """Reset all caches. Called on startup."""
        self._universes.clear()
        self._candidate_index.clear()
        self._candidate_ordinal_index.clear()
        self._candidate_cursor.clear()
        self._payload_rows.clear()
        self._payload_cursor.clear()
        self._load_status.clear()

    def load_status(self, cache_key: str) -> HistoricalPredictionLoadStatus | None:
        """Return the most recent load status for a cache key."""
        return self._load_status.get(cache_key)

    def load_universe(
        self,
        cache_key: str,
        symbol: str,
        model_month: str,
        bundle_paths: BundlePaths,
    ) -> dict[datetime, set[str]]:
        """Load or retrieve cached universe of prediction candidates by timestamp."""
        cached = self._universes.get(cache_key)
        if cached is not None:
            return cached

        pred_path = self._prediction_path(cache_key, bundle_paths)
        if pred_path is None:
            self._universes[cache_key] = {}
            return {}

        try:
            import duckdb
        except Exception:
            self._record_status(cache_key, pred_path, "dependency_unavailable", "duckdb import failed")
            self._universes[cache_key] = {}
            return {}

        con = duckdb.connect()
        try:
            rows = con.execute(
                """
                SELECT
                    try_cast(close_ts AS TIMESTAMP WITH TIME ZONE) AS close_ts,
                    candidate_uid
                FROM read_parquet(?)
                WHERE test_month = ?
                  AND upper(split_part(candidate_uid, '|', 2)) = ?
                ORDER BY close_ts
                """,
                [
                    str(pred_path),
                    str(model_month),
                    str(symbol).upper().strip(),
                ],
            ).fetchall()
        finally:
            con.close()

        out: dict[datetime, set[str]] = {}
        for close_ts, candidate_uid in rows:
            if close_ts is None:
                continue
            ts_utc = self._as_utc_ts(close_ts)
            uid = str(candidate_uid or "").strip()
            if not uid:
                continue
            bucket = out.setdefault(ts_utc, set())
            bucket.add(uid)
        self._universes[cache_key] = out
        self._record_status(cache_key, pred_path, "loaded", f"rows={len(rows)}")
        return out

    def load_candidate_index(
        self,
        cache_key: str,
        symbol: str,
        model_month: str,
        bundle_paths: BundlePaths,
    ) -> dict[str, list[datetime]]:
        """Load or retrieve cached per-candidate timestamps for tolerant replay gating."""
        cached = self._candidate_index.get(cache_key)
        if cached is not None:
            return cached

        pred_path = self._prediction_path(cache_key, bundle_paths)
        if pred_path is None:
            self._candidate_index[cache_key] = {}
            return {}

        try:
            import duckdb
        except Exception:
            self._record_status(cache_key, pred_path, "dependency_unavailable", "duckdb import failed")
            self._candidate_index[cache_key] = {}
            return {}

        con = duckdb.connect()
        try:
            rows = con.execute(
                """
                SELECT
                    candidate_uid,
                    try_cast(close_ts AS TIMESTAMP WITH TIME ZONE) AS close_ts
                FROM read_parquet(?)
                WHERE test_month = ?
                  AND upper(split_part(candidate_uid, '|', 2)) = ?
                ORDER BY candidate_uid, close_ts
                """,
                [
                    str(pred_path),
                    str(model_month),
                    str(symbol).upper().strip(),
                ],
            ).fetchall()
        finally:
            con.close()

        out: dict[str, list[datetime]] = {}
        for candidate_uid, close_ts in rows:
            if close_ts is None:
                continue
            ts_utc = self._as_utc_ts(close_ts)
            uid = str(candidate_uid or "").strip()
            if not uid:
                continue
            if uid not in out:
                out[uid] = []
            out[uid].append(ts_utc)
        self._candidate_index[cache_key] = out
        self._record_status(cache_key, pred_path, "loaded", f"rows={len(rows)}")
        return out

    def load_candidate_ordinal_index(
        self,
        cache_key: str,
        symbol: str,
        model_month: str,
        bundle_paths: BundlePaths,
    ) -> dict[str, list[int]]:
        """Load or retrieve cached per-candidate tick ordinals for tick-perfect replay."""
        cached = self._candidate_ordinal_index.get(cache_key)
        if cached is not None:
            return cached

        pred_path = self._prediction_path(cache_key, bundle_paths)
        if pred_path is None:
            self._candidate_ordinal_index[cache_key] = {}
            return {}

        try:
            import duckdb
        except Exception:
            self._record_status(cache_key, pred_path, "dependency_unavailable", "duckdb import failed")
            self._candidate_ordinal_index[cache_key] = {}
            return {}

        con = duckdb.connect()
        try:
            rows = con.execute(
                """
                SELECT
                    candidate_uid,
                    cast(bar_ordinal AS INTEGER) AS bar_ordinal
                FROM read_parquet(?)
                WHERE test_month = ?
                  AND upper(split_part(candidate_uid, '|', 2)) = ?
                ORDER BY candidate_uid, bar_ordinal
                """,
                [
                    str(pred_path),
                    str(model_month),
                    str(symbol).upper().strip(),
                ],
            ).fetchall()
        finally:
            con.close()

        out: dict[str, list[int]] = {}
        for candidate_uid, bar_ordinal in rows:
            uid = str(candidate_uid or "").strip()
            if not uid:
                continue
            if uid not in out:
                out[uid] = []
            out[uid].append(bar_ordinal)
        self._candidate_ordinal_index[cache_key] = out
        self._record_status(cache_key, pred_path, "loaded", f"rows={len(rows)}")
        return out

    def load_payload_rows(
        self,
        cache_key: str,
        symbol: str,
        model_month: str,
        bundle_paths: BundlePaths,
    ) -> dict[str, list[dict[str, Any]]]:
        """Load or retrieve cached payload rows for attribute injection."""
        cached = self._payload_rows.get(cache_key)
        if cached is not None:
            return cached

        pred_path = self._prediction_path(cache_key, bundle_paths)
        if pred_path is None:
            self._payload_rows[cache_key] = {}
            return {}

        try:
            import duckdb
        except Exception:
            self._record_status(cache_key, pred_path, "dependency_unavailable", "duckdb import failed")
            self._payload_rows[cache_key] = {}
            return {}

        con = duckdb.connect()
        try:
            rows = con.execute(
                """
                SELECT
                    candidate_uid,
                    cast(bar_ordinal AS INTEGER) AS bar_ordinal,
                    cast(pred_prob AS DOUBLE) AS pred_prob,
                    cast(threshold AS DOUBLE) AS threshold,
                    features_json,
                    close_ts
                FROM read_parquet(?)
                WHERE test_month = ?
                  AND upper(split_part(candidate_uid, '|', 2)) = ?
                ORDER BY candidate_uid, bar_ordinal
                """,
                [
                    str(pred_path),
                    str(model_month),
                    str(symbol).upper().strip(),
                ],
            ).fetchall()
        finally:
            con.close()

        out: dict[str, list[dict[str, Any]]] = {}
        for candidate_uid, bar_ordinal, pred_prob, threshold, features_json, close_ts in rows:
            uid = str(candidate_uid or "").strip()
            if not uid:
                continue
            if uid not in out:
                out[uid] = []
            out[uid].append({
                "bar_ordinal": bar_ordinal,
                "pred_prob": pred_prob,
                "threshold": threshold,
                "features_json": features_json,
                "close_ts": close_ts,
            })
        self._payload_rows[cache_key] = out
        self._record_status(cache_key, pred_path, "loaded", f"rows={len(rows)}")
        return out

    def get_cursor(self, cache_key: str, candidate_uid: str) -> int:
        """Get current ordinal index cursor for candidate. Defaults to 0 if not set."""
        return self._candidate_cursor.get(cache_key, {}).get(candidate_uid, 0)

    def set_cursor(self, cache_key: str, candidate_uid: str, cursor: int) -> None:
        """Set current ordinal index cursor for candidate.

        Validates that cursor does not exceed the size of the loaded ordinal index.
        """
        ordinal_index = self._candidate_ordinal_index.get(cache_key, {})
        ordinals = ordinal_index.get(candidate_uid, [])
        if cursor < 0 or cursor > len(ordinals):
            raise ValueError(
                f"Cursor {cursor} out of bounds for {candidate_uid} "
                f"(ordinal index size: {len(ordinals)})"
            )
        if cache_key not in self._candidate_cursor:
            self._candidate_cursor[cache_key] = {}
        self._candidate_cursor[cache_key][candidate_uid] = cursor

    def get_payload_cursor(self, cache_key: str, candidate_uid: str) -> int:
        """Get current payload row cursor for candidate. Defaults to 0 if not set."""
        return self._payload_cursor.get(cache_key, {}).get(candidate_uid, 0)

    def set_payload_cursor(self, cache_key: str, candidate_uid: str, cursor: int) -> None:
        """Set current payload row cursor for candidate.

        Validates that cursor does not exceed the size of the loaded payload rows.
        """
        payload_rows = self._payload_rows.get(cache_key, {})
        rows = payload_rows.get(candidate_uid, [])
        if cursor < 0 or cursor > len(rows):
            raise ValueError(
                f"Payload cursor {cursor} out of bounds for {candidate_uid} "
                f"(payload rows size: {len(rows)})"
            )
        if cache_key not in self._payload_cursor:
            self._payload_cursor[cache_key] = {}
        self._payload_cursor[cache_key][candidate_uid] = cursor

    def reset_cursors(self, cache_key: str, candidate_uid: str) -> None:
        """Reset both ordinal and payload cursors to 0 for a candidate.

        Ensures atomic reset of synchronized cursor state.
        """
        if cache_key in self._candidate_cursor:
            self._candidate_cursor[cache_key][candidate_uid] = 0
        if cache_key in self._payload_cursor:
            self._payload_cursor[cache_key][candidate_uid] = 0

    def _prediction_path(self, cache_key: str, bundle_paths: BundlePaths) -> Path | None:
        override_path = str(os.getenv("BEHEMOTH_HISTORICAL_PREDICTIONS_PATH_OVERRIDE", "")).strip()
        if override_path:
            pred_path = Path(override_path)
        else:
            try:
                pred_path = bundle_paths.predictions()
            except Exception:
                # BundlePaths.predictions() may raise if artifact is missing or hash mismatch
                detail = "bundle_paths.predictions() failed to resolve"
                self._record_status(cache_key, Path(""), "missing_artifact", detail)
                if self._strict_missing:
                    raise MissingHistoricalPredictionArtifact(detail)
                return None

        if pred_path.exists():
            return pred_path

        detail = f"predictions_path={pred_path}"
        self._record_status(cache_key, pred_path, "missing_artifact", detail)
        if self._strict_missing:
            raise MissingHistoricalPredictionArtifact(detail)
        return None

    def _record_status(
        self,
        cache_key: str,
        pred_path: Path,
        status: str,
        detail: str = "",
    ) -> None:
        self._load_status[cache_key] = HistoricalPredictionLoadStatus(
            cache_key=cache_key,
            predictions_path=str(pred_path),
            status=status,
            detail=detail,
        )

    @staticmethod
    def _as_utc_ts(ts: Any) -> datetime:
        """Convert to UTC datetime."""
        from datetime import timezone

        if isinstance(ts, datetime):
            if ts.tzinfo is None:
                return ts.replace(tzinfo=timezone.utc)
            return ts.astimezone(timezone.utc)
        return ts
