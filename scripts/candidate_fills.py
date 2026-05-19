"""Per-fill logging for the tick opportunity mining pipeline.

One row per individual fill for every positive-EV candidate, capturing the
fill outcome and a snapshot of the entry-time features. See
docs/superpowers/specs/2026-05-19-candidate-fill-logging-design.md.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


def candidate_id(
    symbol: str,
    library_type: str,
    family: str,
    bar_ticks: int,
    horizon: int,
    regime: str,
    params: dict[str, Any],
) -> str:
    """A deterministic 12-hex-char identifier for one mining candidate.

    Stable across runs, so a candidate's fills can be diffed between retrains.
    The param dict is sorted so dict ordering does not affect the hash.
    """
    payload = repr((
        str(symbol),
        str(library_type),
        str(family),
        int(bar_ticks),
        int(horizon),
        str(regime),
        sorted((str(k), repr(v)) for k, v in params.items()),
    ))
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()[:12]


_FEATURE_FLOAT_COLS = (
    "tick_burst_score",
    "directional_persistence_8",
    "vol_cluster_score",
)
_SESSION_COL = "session_marker"


def expand_fills(
    frame: pd.DataFrame,
    entries: np.ndarray,
    gross: np.ndarray,
    *,
    split: str,
    identity: dict[str, Any],
) -> list[dict[str, Any]]:
    """Expand one candidate's fills into per-fill row dicts.

    `gross` must be the raw, unfiltered array aligned 1:1 with `entries`;
    fills whose gross is non-finite are dropped per-row so the entry-to-gross
    correspondence is never broken. Missing feature columns degrade to NaN
    (or empty string for session_marker) rather than raising.
    """
    entries = np.asarray(entries, dtype=np.int64)
    gross = np.asarray(gross, dtype=float)
    close_ts = pd.to_datetime(frame["close_ts"], utc=True, errors="coerce")
    rows: list[dict[str, Any]] = []
    for k, idx in enumerate(entries):
        g = float(gross[k])
        if not np.isfinite(g):
            continue
        i = int(idx)
        row = dict(identity)
        row["split"] = split
        row["entry_index"] = i
        row["entry_ts"] = close_ts.iloc[i]
        row["gross_pips"] = g
        for col in _FEATURE_FLOAT_COLS:
            row[col] = (
                float(frame[col].iloc[i])
                if col in frame.columns
                else float("nan")
            )
        row[_SESSION_COL] = (
            str(frame[_SESSION_COL].iloc[i])
            if _SESSION_COL in frame.columns
            else ""
        )
        rows.append(row)
    return rows


# Canonical per-fill column order; also the schema of an empty fills parquet.
FILL_COLUMNS: tuple[str, ...] = (
    "candidate_id",
    "symbol",
    "family",
    "library_type",
    "bar_ticks",
    "horizon",
    "regime",
    "split",
    "entry_index",
    "entry_ts",
    "gross_pips",
    "tick_burst_score",
    "directional_persistence_8",
    "vol_cluster_score",
    "session_marker",
    "selection_pass",
    "near_miss",
)


def write_candidate_fills(
    rows: list[dict[str, Any]],
    out_dir: Path | str,
    symbol: str,
) -> Path:
    """Write per-fill rows to `<out_dir>/candidate_fills/<symbol>_candidate_fills.parquet`.

    An empty `rows` list still produces a parquet with the canonical schema so
    downstream readers never have to handle a missing file.
    """
    fills_dir = Path(out_dir) / "candidate_fills"
    fills_dir.mkdir(parents=True, exist_ok=True)
    path = fills_dir / f"{symbol}_candidate_fills.parquet"
    if rows:
        df = pd.DataFrame(rows).reindex(columns=list(FILL_COLUMNS))
    else:
        df = pd.DataFrame({c: [] for c in FILL_COLUMNS})
    df.to_parquet(path, index=False)
    return path
