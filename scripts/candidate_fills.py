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

    Hot-path-optimised: the prior version called `frame[col].iloc[i]` for
    every feature on every fill. On a high-pass-rate family (e.g.
    directional_inverse at 93/102 pass) that pandas `.iloc[]` overhead
    dominated mining wall-clock — 22 minutes for 102 candidates. This
    version pulls each column to numpy once per candidate, then the
    per-row dict construction is plain Python indexing on numpy arrays.
    """
    entries = np.asarray(entries, dtype=np.int64)
    gross = np.asarray(gross, dtype=float)
    if entries.size == 0:
        return []
    finite = np.isfinite(gross)
    if not finite.any():
        return []
    sel = entries[finite]
    gross_sel = gross[finite]

    # Vectorised column lookups: one .to_numpy() per column, then fancy
    # index by the kept entry positions. Replaces O(n_fills * n_columns)
    # pandas .iloc[] calls.
    close_ts_arr = pd.to_datetime(
        frame["close_ts"], utc=True, errors="coerce"
    ).to_numpy()
    entry_ts = close_ts_arr[sel]

    feature_arrays: dict[str, np.ndarray] = {}
    for col in _FEATURE_FLOAT_COLS:
        if col in frame.columns:
            feature_arrays[col] = pd.to_numeric(
                frame[col], errors="coerce"
            ).to_numpy(dtype=float)[sel]
        else:
            feature_arrays[col] = np.full(sel.size, np.nan, dtype=float)

    if _SESSION_COL in frame.columns:
        session_arr = frame[_SESSION_COL].astype(str).to_numpy()[sel]
    else:
        session_arr = np.full(sel.size, "", dtype=object)

    rows: list[dict[str, Any]] = []
    for k in range(sel.size):
        row = dict(identity)
        row["split"] = split
        row["entry_index"] = int(sel[k])
        row["entry_ts"] = entry_ts[k]
        row["gross_pips"] = float(gross_sel[k])
        for col in _FEATURE_FLOAT_COLS:
            row[col] = float(feature_arrays[col][k])
        row[_SESSION_COL] = str(session_arr[k])
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
