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


_FILLS_FRAME_CTX_ATTR = "__mining_fills_ctx"


def prepare_fills_frame_context(frame: pd.DataFrame) -> dict[str, Any]:
    """Pre-convert the columns expand_fills needs into numpy arrays.

    expand_fills was running `pd.to_datetime` (~500ms), three
    `pd.to_numeric` (~50ms each), and one `astype(str)` (~100ms) on the
    full ~850k-row frame on EVERY call. For high-pass families that's
    ~750ms × 2 splits × 86 passes ≈ 130s of pure column conversion on
    GBPUSD's directional_inverse alone. These columns are read-only
    across all expand_fills calls within one _mine_frame_pair invocation,
    so compute them once and stash the result on `frame.attrs`. Subsequent
    expand_fills calls index into the cached arrays in ~microseconds."""
    cached = frame.attrs.get(_FILLS_FRAME_CTX_ATTR)
    if cached is not None:
        return cached
    ctx: dict[str, Any] = {
        "close_ts": pd.to_datetime(
            frame["close_ts"], utc=True, errors="coerce"
        ).to_numpy(),
    }
    for col in _FEATURE_FLOAT_COLS:
        if col in frame.columns:
            ctx[col] = pd.to_numeric(
                frame[col], errors="coerce"
            ).to_numpy(dtype=float)
        else:
            ctx[col] = None
    if _SESSION_COL in frame.columns:
        ctx[_SESSION_COL] = frame[_SESSION_COL].astype(str).to_numpy()
    else:
        ctx[_SESSION_COL] = None
    frame.attrs[_FILLS_FRAME_CTX_ATTR] = ctx
    return ctx


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

    Hot-path-optimised: column conversions are memoised on `frame.attrs`
    via `prepare_fills_frame_context` (compute once per frame, reused
    across all candidates). Per-row dict construction is plain Python
    indexing on cached numpy arrays.
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

    ctx = prepare_fills_frame_context(frame)
    entry_ts = ctx["close_ts"][sel]

    feature_arrays: dict[str, np.ndarray] = {}
    for col in _FEATURE_FLOAT_COLS:
        col_arr = ctx[col]
        if col_arr is not None:
            feature_arrays[col] = col_arr[sel]
        else:
            feature_arrays[col] = np.full(sel.size, np.nan, dtype=float)

    session_full = ctx[_SESSION_COL]
    if session_full is not None:
        session_arr = session_full[sel]
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

    For the mining hot path, prefer `CandidateFillsWriter` (chunked,
    streams to disk per family). This batch entry point materialises the
    whole list as a single DataFrame and is used by callers that already
    have the full row list in memory (tests, small datasets).
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


class CandidateFillsWriter:
    """Chunked parquet writer for per-fill rows.

    The mining loop accumulates fill rows into one list across all 11
    families within one bar_ticks iteration. For high-pass families
    (directional_inverse ~95%, directional_run ~50%) that list grows to
    several GB before the next bar_ticks frees it, OOM-killing 8 GB
    machines part-way through `double_touch` (the largest grid).

    This writer flushes a chunk of rows to a pyarrow ParquetWriter and
    drops them from memory. Open one writer per (symbol, bar_ticks), call
    `append(rows)` after each family completes, then `close()` at the end
    of the symbol. Peak memory is bounded by one family's pass-rate
    rather than the whole symbol's.
    """

    def __init__(self, out_dir: Path | str, symbol: str) -> None:
        import pyarrow as pa

        fills_dir = Path(out_dir) / "candidate_fills"
        fills_dir.mkdir(parents=True, exist_ok=True)
        self._path = fills_dir / f"{symbol}_candidate_fills.parquet"
        self._schema = pa.schema([
            (c, pa.string()) if c in {
                "candidate_id", "symbol", "family", "library_type",
                "regime", "split", "session_marker",
            } else (c, pa.int64()) if c in {
                "bar_ticks", "horizon", "entry_index",
            } else (c, pa.timestamp("ns", tz="UTC")) if c == "entry_ts"
            else (c, pa.bool_()) if c in {"selection_pass", "near_miss"}
            else (c, pa.float64())
            for c in FILL_COLUMNS
        ])
        self._writer: Any = None
        self._pa = pa

    @property
    def path(self) -> Path:
        return self._path

    def append(self, rows: list[dict[str, Any]]) -> None:
        if not rows:
            return
        df = pd.DataFrame(rows).reindex(columns=list(FILL_COLUMNS))
        # Coerce to expected dtypes; missing/None becomes NaT/NaN as appropriate.
        df["entry_ts"] = pd.to_datetime(
            df["entry_ts"], utc=True, errors="coerce"
        )
        for c in ("selection_pass", "near_miss"):
            df[c] = df[c].astype("boolean").fillna(False).astype(bool)
        for c in ("bar_ticks", "horizon", "entry_index"):
            df[c] = pd.to_numeric(df[c], errors="coerce").astype("Int64")
        table = self._pa.Table.from_pandas(
            df, schema=self._schema, preserve_index=False
        )
        if self._writer is None:
            import pyarrow.parquet as pq

            self._writer = pq.ParquetWriter(str(self._path), self._schema)
        self._writer.write_table(table)

    def close(self) -> None:
        if self._writer is not None:
            self._writer.close()
            self._writer = None
            return
        # No rows ever appended — emit empty file with canonical schema so
        # downstream readers don't have to handle a missing file.
        empty = pd.DataFrame({c: [] for c in FILL_COLUMNS})
        empty.to_parquet(self._path, index=False)

    def __enter__(self) -> CandidateFillsWriter:
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()
