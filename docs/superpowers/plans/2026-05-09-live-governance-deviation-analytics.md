# Live Governance Deviation Analytics Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a standalone analytics run that compares recent Live Runtime DuckDB evidence against Governance Runtime replay built from canonical Dukascopy Raw Tick Data.

**Architecture:** Add a focused reusable module under `src/behemoth/diagnostics/live_governance_deviation.py` for window discovery, extraction, metric computation, and report rendering. Add a thin CLI wrapper in `scripts/analyze_live_governance_deviation.py`. Reuse existing scripts by importing helper functions where practical, especially `scripts/diagnose_live_replay.py`, `scripts/compare_tick_data_sources.py`, and `scripts/summarize_runtime_db_run.py`.

**Tech Stack:** Python 3.12, DuckDB, pandas, pyarrow/parquet, existing `uv run pytest` test workflow, existing repo script conventions.

---

## File Structure

- Create `src/behemoth/diagnostics/live_governance_deviation.py`
  - Owns dataclasses, Runtime State opening/snapshot support, window discovery, live evidence extraction, canonical tick loading, deviation metrics, findings, and Markdown rendering.
- Create `scripts/analyze_live_governance_deviation.py`
  - CLI-only wrapper that parses arguments and calls the diagnostics module.
- Create `tests/test_live_governance_deviation.py`
  - Unit tests and CLI smoke coverage with synthetic DuckDB and parquet data.
- Modify `scripts/diagnose_live_replay.py`
  - Only if needed to expose existing `_build_bars_from_ticks`, `_score_bars`, `_load_states`, `_load_model`, and `_load_thresholds` functions without duplicating logic. Keep behavior unchanged.
- Modify `scripts/compare_tick_data_sources.py`
  - Only if needed to reuse `_source_stats`, `_bar_summary`, or `_intertick_stats` without duplicating logic. Keep behavior unchanged.

Do not change Promotion, restart, Stage 13, or Stage 14 scripts.

---

### Task 1: Add Core Types And Window Discovery

**Files:**
- Create: `src/behemoth/diagnostics/live_governance_deviation.py`
- Test: `tests/test_live_governance_deviation.py`

- [ ] **Step 1: Write failing tests for recent-window discovery and skip rows**

Add this file:

```python
from __future__ import annotations

from pathlib import Path

import duckdb
import pandas as pd

from src.behemoth.diagnostics.live_governance_deviation import (
    DeviationConfig,
    discover_symbol_windows,
)


def _create_runtime_db(path: Path) -> None:
    con = duckdb.connect(str(path))
    try:
        con.execute(
            """
            CREATE TABLE raw_ticks (
                tick_ts TIMESTAMP WITH TIME ZONE,
                ingest_ts TIMESTAMP WITH TIME ZONE,
                symbol VARCHAR,
                bid DOUBLE,
                ask DOUBLE,
                spread DOUBLE,
                tick_volume DOUBLE,
                source VARCHAR,
                client_tick_seq BIGINT,
                run_id VARCHAR
            )
            """
        )
        con.execute(
            """
            CREATE TABLE tick_bars (
                row_id BIGINT,
                ts TIMESTAMP WITH TIME ZONE,
                close_ts TIMESTAMP WITH TIME ZONE,
                symbol VARCHAR,
                bar_ticks BIGINT,
                open_bid DOUBLE,
                high_bid DOUBLE,
                low_bid DOUBLE,
                close_bid DOUBLE,
                spread DOUBLE,
                tick_volume DOUBLE,
                hl_first BIGINT,
                hl_pos_frac DOUBLE,
                high_ask DOUBLE,
                close_ask DOUBLE
            )
            """
        )
        ticks = pd.DataFrame(
            {
                "tick_ts": pd.date_range("2026-05-02T00:00:00Z", periods=300, freq="s"),
                "ingest_ts": pd.date_range("2026-05-02T00:00:00Z", periods=300, freq="s"),
                "symbol": ["EURUSD"] * 300,
                "bid": [1.1] * 300,
                "ask": [1.1002] * 300,
                "spread": [0.0002] * 300,
                "tick_volume": [1.0] * 300,
                "source": ["jforex"] * 300,
                "client_tick_seq": list(range(300)),
                "run_id": ["jforex_live"] * 300,
            }
        )
        con.register("ticks_df", ticks)
        con.execute("INSERT INTO raw_ticks SELECT * FROM ticks_df")
        bars = pd.DataFrame(
            {
                "row_id": [0, 1, 2],
                "ts": pd.to_datetime(
                    [
                        "2026-05-02T00:00:00Z",
                        "2026-05-02T00:01:40Z",
                        "2026-05-02T00:03:20Z",
                    ],
                    utc=True,
                ),
                "close_ts": pd.to_datetime(
                    [
                        "2026-05-02T00:01:39Z",
                        "2026-05-02T00:03:19Z",
                        "2026-05-02T00:04:59Z",
                    ],
                    utc=True,
                ),
                "symbol": ["EURUSD"] * 3,
                "bar_ticks": [100] * 3,
                "open_bid": [1.1, 1.1001, 1.1002],
                "high_bid": [1.1002, 1.1003, 1.1004],
                "low_bid": [1.0999, 1.1, 1.1001],
                "close_bid": [1.1001, 1.1002, 1.1003],
                "spread": [0.0002] * 3,
                "tick_volume": [100.0] * 3,
                "hl_first": [1, -1, 1],
                "hl_pos_frac": [0.1, 0.2, 0.3],
                "high_ask": [1.1004, 1.1005, 1.1006],
                "close_ask": [1.1003, 1.1004, 1.1005],
            }
        )
        con.register("bars_df", bars)
        con.execute("INSERT INTO tick_bars SELECT * FROM bars_df")
    finally:
        con.close()


def test_discover_symbol_windows_uses_latest_completed_tick_bars(tmp_path: Path) -> None:
    db_path = tmp_path / "runtime.db"
    _create_runtime_db(db_path)
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        cfg = DeviationConfig(
            runtime_db=db_path,
            tick_root=tmp_path / "ticks",
            symbols=("EURUSD", "GBPUSD"),
            lookback_days=7,
            min_bars=2,
            run_id="jforex_live",
            out_dir=tmp_path / "out",
        )
        windows, skips = discover_symbol_windows(con, cfg)
    finally:
        con.close()

    assert len(windows) == 1
    assert windows[0].symbol == "EURUSD"
    assert windows[0].bar_count == 3
    assert windows[0].start_ts.isoformat() == "2026-05-02T00:00:00+00:00"
    assert windows[0].end_ts.isoformat() == "2026-05-02T00:04:59+00:00"
    assert skips.iloc[0]["symbol"] == "GBPUSD"
    assert skips.iloc[0]["reason"] == "missing_recent_tick_bars"
```

- [ ] **Step 2: Run the test and verify it fails**

Run:

```bash
uv run pytest -q tests/test_live_governance_deviation.py::test_discover_symbol_windows_uses_latest_completed_tick_bars
```

Expected: `ModuleNotFoundError` or import failure because `live_governance_deviation.py` does not exist.

- [ ] **Step 3: Implement core types and discovery**

Create `src/behemoth/diagnostics/live_governance_deviation.py`:

```python
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd


ACTIVE_SYMBOLS = ("EURUSD", "GBPUSD", "USDJPY", "USDCHF", "AUDUSD", "USDCAD")


@dataclass(frozen=True)
class DeviationConfig:
    runtime_db: Path
    tick_root: Path
    symbols: tuple[str, ...]
    lookback_days: int
    min_bars: int
    run_id: str
    out_dir: Path
    start_ts: pd.Timestamp | None = None
    end_ts: pd.Timestamp | None = None
    governance_dir: Path = Path("configs/research/governance/oco")
    models_dir: Path = Path("models/oco")
    api: str = ""
    copy_report_to_docs: bool = False


@dataclass(frozen=True)
class SymbolWindow:
    symbol: str
    start_ts: pd.Timestamp
    end_ts: pd.Timestamp
    raw_tick_count: int
    bar_count: int
    bar_ticks: int


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _to_timestamp(value: Any) -> pd.Timestamp | None:
    if value is None:
        return None
    ts = pd.Timestamp(value)
    if pd.isna(ts):
        return None
    if ts.tzinfo is None:
        return ts.tz_localize("UTC")
    return ts.tz_convert("UTC")


def _table_exists(con: duckdb.DuckDBPyConnection, table_name: str) -> bool:
    row = con.execute(
        """
        SELECT 1
        FROM information_schema.tables
        WHERE lower(table_name) = lower(?)
        LIMIT 1
        """,
        [table_name],
    ).fetchone()
    return row is not None


def _skip(symbol: str, reason: str) -> dict[str, str]:
    return {"symbol": symbol, "reason": reason}


def discover_symbol_windows(
    con: duckdb.DuckDBPyConnection, cfg: DeviationConfig
) -> tuple[list[SymbolWindow], pd.DataFrame]:
    if not _table_exists(con, "tick_bars"):
        return [], pd.DataFrame([_skip(sym, "missing_tick_bars_table") for sym in cfg.symbols])
    if not _table_exists(con, "raw_ticks"):
        return [], pd.DataFrame([_skip(sym, "missing_raw_ticks_table") for sym in cfg.symbols])

    windows: list[SymbolWindow] = []
    skips: list[dict[str, str]] = []
    for symbol in cfg.symbols:
        sym = symbol.upper().strip()
        explicit_start = _to_timestamp(cfg.start_ts)
        explicit_end = _to_timestamp(cfg.end_ts)
        if explicit_start is not None and explicit_end is not None:
            start = explicit_start
            end = explicit_end
        else:
            latest_row = con.execute(
                """
                SELECT max(close_ts)
                FROM tick_bars
                WHERE upper(symbol) = ?
                """,
                [sym],
            ).fetchone()
            latest = _to_timestamp(latest_row[0] if latest_row else None)
            if latest is None:
                skips.append(_skip(sym, "missing_recent_tick_bars"))
                continue
            end = latest
            start = end - pd.Timedelta(days=int(cfg.lookback_days))

        bar_row = con.execute(
            """
            SELECT count(*) AS bar_count, min(ts) AS start_ts, max(close_ts) AS end_ts,
                   min(bar_ticks) AS min_bar_ticks, max(bar_ticks) AS max_bar_ticks
            FROM tick_bars
            WHERE upper(symbol) = ?
              AND close_ts >= ?::TIMESTAMPTZ
              AND close_ts <= ?::TIMESTAMPTZ
            """,
            [sym, start.isoformat(), end.isoformat()],
        ).fetchone()
        bar_count = int(bar_row[0] or 0)
        if bar_count < int(cfg.min_bars):
            skips.append(_skip(sym, "insufficient_recent_tick_bars"))
            continue
        min_bar_ticks = int(bar_row[3] or 0)
        max_bar_ticks = int(bar_row[4] or 0)
        if min_bar_ticks != max_bar_ticks:
            skips.append(_skip(sym, "mixed_bar_ticks_in_window"))
            continue
        raw_row = con.execute(
            """
            SELECT count(*)
            FROM raw_ticks
            WHERE upper(symbol) = ?
              AND tick_ts >= ?::TIMESTAMPTZ
              AND tick_ts <= ?::TIMESTAMPTZ
            """,
            [sym, start.isoformat(), end.isoformat()],
        ).fetchone()
        raw_count = int(raw_row[0] or 0)
        if raw_count == 0:
            skips.append(_skip(sym, "missing_recent_raw_ticks"))
            continue
        windows.append(
            SymbolWindow(
                symbol=sym,
                start_ts=_to_timestamp(bar_row[1]) or start,
                end_ts=_to_timestamp(bar_row[2]) or end,
                raw_tick_count=raw_count,
                bar_count=bar_count,
                bar_ticks=max_bar_ticks,
            )
        )
    return windows, pd.DataFrame(skips, columns=["symbol", "reason"])
```

- [ ] **Step 4: Run the test and verify it passes**

Run:

```bash
uv run pytest -q tests/test_live_governance_deviation.py::test_discover_symbol_windows_uses_latest_completed_tick_bars
```

Expected: `1 passed`.

- [ ] **Step 5: Commit**

```bash
git add src/behemoth/diagnostics/live_governance_deviation.py tests/test_live_governance_deviation.py
git commit -m "feat: discover live governance deviation windows"
```

---

### Task 2: Add Live Evidence Extraction And Tick/Bar Metrics

**Files:**
- Modify: `src/behemoth/diagnostics/live_governance_deviation.py`
- Modify: `tests/test_live_governance_deviation.py`

- [ ] **Step 1: Write failing tests for live extraction and bar deviation metrics**

Append to `tests/test_live_governance_deviation.py`:

```python
from src.behemoth.diagnostics.live_governance_deviation import (
    compute_bar_deviation,
    compute_tick_coverage,
    extract_live_evidence,
)


def test_extract_live_evidence_and_compute_live_metrics(tmp_path: Path) -> None:
    db_path = tmp_path / "runtime.db"
    _create_runtime_db(db_path)
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        window = discover_symbol_windows(
            con,
            DeviationConfig(
                runtime_db=db_path,
                tick_root=tmp_path / "ticks",
                symbols=("EURUSD",),
                lookback_days=7,
                min_bars=2,
                run_id="jforex_live",
                out_dir=tmp_path / "out",
            ),
        )[0][0]
        evidence = extract_live_evidence(con, window, run_id="jforex_live")
    finally:
        con.close()

    assert len(evidence.raw_ticks) == 300
    assert len(evidence.tick_bars) == 3
    tick_metrics = compute_tick_coverage("EURUSD", evidence.raw_ticks, evidence.raw_ticks)
    assert tick_metrics.loc[0, "live_rows"] == 300
    assert tick_metrics.loc[0, "governance_rows"] == 300
    bar_metrics = compute_bar_deviation("EURUSD", evidence.tick_bars, evidence.tick_bars)
    assert bar_metrics.loc[0, "live_bar_count"] == 3
    assert bar_metrics.loc[0, "missing_live_bars"] == 0
    assert bar_metrics.loc[0, "extra_live_bars"] == 0
    assert bar_metrics.loc[0, "max_abs_close_delta_pips"] == 0.0
```

- [ ] **Step 2: Run the test and verify it fails**

Run:

```bash
uv run pytest -q tests/test_live_governance_deviation.py::test_extract_live_evidence_and_compute_live_metrics
```

Expected: import failure for `extract_live_evidence`, `compute_tick_coverage`, or `compute_bar_deviation`.

- [ ] **Step 3: Implement extraction and metrics**

Append to `src/behemoth/diagnostics/live_governance_deviation.py`:

```python
@dataclass(frozen=True)
class LiveEvidence:
    raw_ticks: pd.DataFrame
    tick_bars: pd.DataFrame
    predictions: pd.DataFrame
    prediction_source: str
    trades: pd.DataFrame


def _read_df(
    con: duckdb.DuckDBPyConnection, sql: str, params: list[Any]
) -> pd.DataFrame:
    try:
        return con.execute(sql, params).fetchdf()
    except Exception:
        return pd.DataFrame()


def _normalise_ts_column(df: pd.DataFrame, column: str) -> pd.DataFrame:
    if column in df.columns:
        df[column] = pd.to_datetime(df[column], utc=True, errors="coerce")
    return df


def extract_live_evidence(
    con: duckdb.DuckDBPyConnection, window: SymbolWindow, *, run_id: str
) -> LiveEvidence:
    sym = window.symbol.upper()
    start = window.start_ts.isoformat()
    end = window.end_ts.isoformat()
    raw_ticks = _read_df(
        con,
        """
        SELECT tick_ts, ingest_ts, symbol, bid, ask, spread, tick_volume, source,
               client_tick_seq, run_id
        FROM raw_ticks
        WHERE upper(symbol) = ?
          AND tick_ts >= ?::TIMESTAMPTZ
          AND tick_ts <= ?::TIMESTAMPTZ
        ORDER BY tick_ts, client_tick_seq
        """,
        [sym, start, end],
    )
    raw_ticks = _normalise_ts_column(raw_ticks, "tick_ts")
    tick_bars = _read_df(
        con,
        """
        SELECT row_id, ts, close_ts, symbol, bar_ticks, open_bid, high_bid, low_bid,
               close_bid, spread, tick_volume, hl_first, hl_pos_frac, high_ask, close_ask
        FROM tick_bars
        WHERE upper(symbol) = ?
          AND close_ts >= ?::TIMESTAMPTZ
          AND close_ts <= ?::TIMESTAMPTZ
        ORDER BY close_ts, row_id
        """,
        [sym, start, end],
    )
    tick_bars = _normalise_ts_column(_normalise_ts_column(tick_bars, "ts"), "close_ts")

    prediction_source = "none"
    predictions = pd.DataFrame()
    if _table_exists(con, "predict_evaluations"):
        predictions = _read_df(
            con,
            """
            SELECT event_ts, close_ts, symbol, candidate_uid, pred_prob, threshold,
                   preselected_exec, selected_exec, model_month, run_id
            FROM predict_evaluations
            WHERE upper(symbol) = ?
              AND lower(coalesce(run_id, '')) = lower(?)
              AND close_ts >= ?::TIMESTAMPTZ
              AND close_ts <= ?::TIMESTAMPTZ
            ORDER BY close_ts, candidate_uid
            """,
            [sym, run_id, start, end],
        )
        if not predictions.empty:
            prediction_source = "predict_evaluations"
    if predictions.empty and _table_exists(con, "audit_logs"):
        predictions = _read_df(
            con,
            """
            SELECT event_ts, close_ts, symbol, candidate_uid, pred_prob, threshold,
                   model_month, run_id
            FROM audit_logs
            WHERE upper(symbol) = ?
              AND lower(coalesce(run_id, '')) = lower(?)
              AND close_ts >= ?::TIMESTAMPTZ
              AND close_ts <= ?::TIMESTAMPTZ
            ORDER BY close_ts, candidate_uid
            """,
            [sym, run_id, start, end],
        )
        if not predictions.empty:
            prediction_source = "audit_logs"
    predictions = _normalise_ts_column(_normalise_ts_column(predictions, "event_ts"), "close_ts")

    trades = pd.DataFrame()
    if _table_exists(con, "trades"):
        trades = _read_df(
            con,
            """
            SELECT *
            FROM trades
            WHERE upper(symbol) = ?
              AND lower(coalesce(run_id, '')) = lower(?)
            """,
            [sym, run_id],
        )
    return LiveEvidence(
        raw_ticks=raw_ticks,
        tick_bars=tick_bars,
        predictions=predictions,
        prediction_source=prediction_source,
        trades=trades,
    )


def _pip_size(symbol: str) -> float:
    return 0.01 if symbol.upper().endswith("JPY") else 0.0001


def _series_quantile(series: pd.Series, q: float) -> float:
    vals = pd.to_numeric(series, errors="coerce").dropna()
    if vals.empty:
        return float("nan")
    return float(vals.quantile(q))


def compute_tick_coverage(
    symbol: str, live_ticks: pd.DataFrame, governance_ticks: pd.DataFrame
) -> pd.DataFrame:
    def _stats(df: pd.DataFrame, prefix: str) -> dict[str, Any]:
        if df.empty:
            return {
                f"{prefix}_rows": 0,
                f"{prefix}_first_ts": "",
                f"{prefix}_last_ts": "",
                f"{prefix}_duplicate_ts_ratio": float("nan"),
                f"{prefix}_spread_p50": float("nan"),
                f"{prefix}_spread_p95": float("nan"),
            }
        ts_col = "tick_ts" if "tick_ts" in df.columns else "timestamp"
        ts = pd.to_datetime(df[ts_col], utc=True, errors="coerce")
        spread = pd.to_numeric(df.get("spread", pd.Series(dtype=float)), errors="coerce")
        return {
            f"{prefix}_rows": int(len(df)),
            f"{prefix}_first_ts": ts.min().isoformat() if ts.notna().any() else "",
            f"{prefix}_last_ts": ts.max().isoformat() if ts.notna().any() else "",
            f"{prefix}_duplicate_ts_ratio": float(ts.duplicated().mean()),
            f"{prefix}_spread_p50": _series_quantile(spread, 0.50),
            f"{prefix}_spread_p95": _series_quantile(spread, 0.95),
        }

    row = {"symbol": symbol.upper()}
    row.update(_stats(live_ticks, "live"))
    row.update(_stats(governance_ticks, "governance"))
    row["row_delta"] = int(row["live_rows"]) - int(row["governance_rows"])
    return pd.DataFrame([row])


def compute_bar_deviation(
    symbol: str, live_bars: pd.DataFrame, governance_bars: pd.DataFrame
) -> pd.DataFrame:
    pip = _pip_size(symbol)
    live = live_bars.copy()
    gov = governance_bars.copy()
    for df in (live, gov):
        if "close_ts" in df.columns:
            df["close_ts"] = pd.to_datetime(df["close_ts"], utc=True, errors="coerce")
    merged = live.merge(
        gov,
        on="close_ts",
        how="outer",
        suffixes=("_live", "_governance"),
        indicator=True,
    )
    both = merged[merged["_merge"] == "both"].copy()
    if both.empty:
        max_abs_close = float("nan")
        max_abs_spread = float("nan")
    else:
        max_abs_close = float(
            ((both["close_bid_live"] - both["close_bid_governance"]) / pip).abs().max()
        )
        max_abs_spread = float(
            ((both["spread_live"] - both["spread_governance"]) / pip).abs().max()
        )
    return pd.DataFrame(
        [
            {
                "symbol": symbol.upper(),
                "live_bar_count": int(len(live)),
                "governance_bar_count": int(len(gov)),
                "matched_bars": int((merged["_merge"] == "both").sum()),
                "missing_live_bars": int((merged["_merge"] == "right_only").sum()),
                "extra_live_bars": int((merged["_merge"] == "left_only").sum()),
                "max_abs_close_delta_pips": max_abs_close,
                "max_abs_spread_delta_pips": max_abs_spread,
            }
        ]
    )
```

- [ ] **Step 4: Run the focused tests**

Run:

```bash
uv run pytest -q tests/test_live_governance_deviation.py
```

Expected: both tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/behemoth/diagnostics/live_governance_deviation.py tests/test_live_governance_deviation.py
git commit -m "feat: extract live deviation evidence"
```

---

### Task 3: Add Canonical Tick Loading And Governance Bar Replay

**Files:**
- Modify: `src/behemoth/diagnostics/live_governance_deviation.py`
- Modify: `tests/test_live_governance_deviation.py`

- [ ] **Step 1: Write failing test for canonical tick loading and governance bars**

Append to `tests/test_live_governance_deviation.py`:

```python
from src.behemoth.diagnostics.live_governance_deviation import (
    build_governance_bars_for_window,
    load_canonical_ticks_for_window,
)


def test_load_canonical_ticks_and_build_governance_bars(tmp_path: Path) -> None:
    tick_root = tmp_path / "dukascopy_ticks"
    sym_dir = tick_root / "EURUSD"
    sym_dir.mkdir(parents=True)
    ticks = pd.DataFrame(
        {
            "timestamp": pd.date_range("2026-05-02T00:00:00Z", periods=250, freq="s"),
            "bid": [1.1 + i * 0.000001 for i in range(250)],
            "ask": [1.1002 + i * 0.000001 for i in range(250)],
            "mid": [1.1001 + i * 0.000001 for i in range(250)],
            "spread": [0.0002] * 250,
            "log_return": [0.0] * 250,
        }
    )
    ticks.to_parquet(sym_dir / "EURUSD_202605_ticks.parquet", index=False)

    loaded = load_canonical_ticks_for_window(
        tick_root=tick_root,
        symbol="EURUSD",
        start_ts=pd.Timestamp("2026-05-02T00:00:00Z"),
        end_ts=pd.Timestamp("2026-05-02T00:04:10Z"),
    )
    bars = build_governance_bars_for_window(loaded, bar_ticks=100)

    assert len(loaded) == 250
    assert len(bars) == 2
    assert {"close_ts", "open_bid", "high_bid", "low_bid", "close_bid", "high_ask", "close_ask"}.issubset(bars.columns)
```

- [ ] **Step 2: Run the test and verify it fails**

Run:

```bash
uv run pytest -q tests/test_live_governance_deviation.py::test_load_canonical_ticks_and_build_governance_bars
```

Expected: import failure for `load_canonical_ticks_for_window`.

- [ ] **Step 3: Implement canonical tick loading and reuse `diagnose_live_replay` bar builder**

Append to `src/behemoth/diagnostics/live_governance_deviation.py`:

```python
def _month_tokens(start_ts: pd.Timestamp, end_ts: pd.Timestamp) -> list[str]:
    start = _to_timestamp(start_ts)
    end = _to_timestamp(end_ts)
    if start is None or end is None:
        return []
    months = pd.period_range(start=start.to_period("M"), end=end.to_period("M"), freq="M")
    return [p.strftime("%Y%m") for p in months]


def load_canonical_ticks_for_window(
    *, tick_root: Path, symbol: str, start_ts: pd.Timestamp, end_ts: pd.Timestamp
) -> pd.DataFrame:
    sym = symbol.upper().strip()
    frames: list[pd.DataFrame] = []
    for month in _month_tokens(start_ts, end_ts):
        path = tick_root / sym / f"{sym}_{month}_ticks.parquet"
        if path.exists():
            frames.append(pd.read_parquet(path))
    if not frames:
        return pd.DataFrame(columns=["timestamp", "bid", "ask", "mid", "spread", "log_return"])
    out = pd.concat(frames, ignore_index=True)
    out["timestamp"] = pd.to_datetime(out["timestamp"], utc=True, errors="coerce")
    start = _to_timestamp(start_ts)
    end = _to_timestamp(end_ts)
    out = out[(out["timestamp"] >= start) & (out["timestamp"] <= end)].copy()
    return out.sort_values("timestamp").reset_index(drop=True)


def build_governance_bars_for_window(
    canonical_ticks: pd.DataFrame, *, bar_ticks: int
) -> pd.DataFrame:
    if canonical_ticks.empty:
        return pd.DataFrame()
    if int(bar_ticks) != 100:
        return pd.DataFrame()
    import polars as pl
    from scripts.diagnose_live_replay import _build_bars_from_ticks

    pl_ticks = pl.from_pandas(canonical_ticks)
    bars = _build_bars_from_ticks(pl_ticks)
    return bars.to_pandas() if not bars.is_empty() else pd.DataFrame()
```

- [ ] **Step 4: Run the focused tests**

Run:

```bash
uv run pytest -q tests/test_live_governance_deviation.py
```

Expected: all current `test_live_governance_deviation.py` tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/behemoth/diagnostics/live_governance_deviation.py tests/test_live_governance_deviation.py
git commit -m "feat: load canonical ticks for deviation replay"
```

---

### Task 4: Add Signal, Outcome, Findings, And Report Rendering

**Files:**
- Modify: `src/behemoth/diagnostics/live_governance_deviation.py`
- Modify: `tests/test_live_governance_deviation.py`

- [ ] **Step 1: Write failing tests for signal/outcome metrics and report rendering**

Append to `tests/test_live_governance_deviation.py`:

```python
from src.behemoth.diagnostics.live_governance_deviation import (
    build_findings,
    compute_outcome_deviation,
    compute_signal_deviation,
    render_report,
)


def test_signal_outcome_findings_and_report() -> None:
    live_predictions = pd.DataFrame(
        {
            "symbol": ["EURUSD", "EURUSD"],
            "candidate_uid": ["oco|EURUSD|100|h6|a", "oco|EURUSD|100|h6|a"],
            "pred_prob": [0.7, 0.8],
            "threshold": [0.75, 0.75],
            "selected_exec": [0, 1],
        }
    )
    governance_predictions = pd.DataFrame(
        {
            "symbol": ["EURUSD", "EURUSD", "EURUSD"],
            "candidate_uid": ["oco|EURUSD|100|h6|a"] * 3,
            "pred_prob": [0.7, 0.8, 0.9],
            "threshold": [0.75, 0.75, 0.75],
            "selected": [0, 1, 1],
        }
    )
    signal = compute_signal_deviation(
        "EURUSD", live_predictions, governance_predictions, live_source="predict_evaluations"
    )
    assert signal.loc[0, "live_prediction_rows"] == 2
    assert signal.loc[0, "governance_prediction_rows"] == 3
    assert signal.loc[0, "live_selected_signal_count"] == 1
    assert signal.loc[0, "governance_selected_signal_count"] == 2

    trades = pd.DataFrame({"status": ["CLOSED", "OPEN"], "pnl_pips": [3.0, 0.0]})
    outcome = compute_outcome_deviation("EURUSD", trades, governance_selected_signal_count=2)
    assert outcome.loc[0, "runtime_trade_count"] == 2
    assert outcome.loc[0, "runtime_realized_pnl_pips"] == 3.0

    findings = build_findings(
        bar_deviation=pd.DataFrame(
            [
                {
                    "symbol": "EURUSD",
                    "missing_live_bars": 1,
                    "extra_live_bars": 0,
                    "max_abs_close_delta_pips": 0.0,
                }
            ]
        ),
        signal_deviation=signal,
        incomplete_rows=pd.DataFrame(),
    )
    assert "Material Drift" in set(findings["classification"])
    report = render_report(
        manifest={"run_id": "unit", "generated_at_utc": "2026-05-09T00:00:00Z"},
        window_summary=pd.DataFrame([{"symbol": "EURUSD", "bar_count": 2}]),
        findings=findings,
        tick_coverage=pd.DataFrame(),
        bar_deviation=pd.DataFrame(),
        signal_deviation=signal,
        outcome_deviation=outcome,
        skips=pd.DataFrame(),
    )
    assert "# Live Governance Deviation Report" in report
    assert "not a Promotion gate" in report
```

- [ ] **Step 2: Run the test and verify it fails**

Run:

```bash
uv run pytest -q tests/test_live_governance_deviation.py::test_signal_outcome_findings_and_report
```

Expected: import failure for signal/report functions.

- [ ] **Step 3: Implement metrics, findings, and report renderer**

Append to `src/behemoth/diagnostics/live_governance_deviation.py`:

```python
def _selected_count(df: pd.DataFrame) -> int:
    if df.empty:
        return 0
    if "selected_exec" in df.columns:
        return int(pd.to_numeric(df["selected_exec"], errors="coerce").fillna(0).sum())
    if "selected" in df.columns:
        return int(pd.to_numeric(df["selected"], errors="coerce").fillna(0).sum())
    return int(len(df))


def compute_signal_deviation(
    symbol: str,
    live_predictions: pd.DataFrame,
    governance_predictions: pd.DataFrame,
    *,
    live_source: str,
) -> pd.DataFrame:
    live_prob = pd.to_numeric(live_predictions.get("pred_prob", pd.Series(dtype=float)), errors="coerce")
    gov_prob = pd.to_numeric(governance_predictions.get("pred_prob", pd.Series(dtype=float)), errors="coerce")
    live_thr = pd.to_numeric(live_predictions.get("threshold", pd.Series(dtype=float)), errors="coerce")
    gov_thr = pd.to_numeric(governance_predictions.get("threshold", pd.Series(dtype=float)), errors="coerce")
    live_selected = _selected_count(live_predictions)
    gov_selected = _selected_count(governance_predictions)
    return pd.DataFrame(
        [
            {
                "symbol": symbol.upper(),
                "live_source": live_source,
                "live_prediction_rows": int(len(live_predictions)),
                "governance_prediction_rows": int(len(governance_predictions)),
                "prediction_row_delta": int(len(live_predictions)) - int(len(governance_predictions)),
                "live_selected_signal_count": live_selected,
                "governance_selected_signal_count": gov_selected,
                "selected_signal_delta": live_selected - gov_selected,
                "live_pred_prob_p50": _series_quantile(live_prob, 0.50),
                "governance_pred_prob_p50": _series_quantile(gov_prob, 0.50),
                "live_threshold_p50": _series_quantile(live_thr, 0.50),
                "governance_threshold_p50": _series_quantile(gov_thr, 0.50),
            }
        ]
    )


def compute_outcome_deviation(
    symbol: str, trades: pd.DataFrame, *, governance_selected_signal_count: int
) -> pd.DataFrame:
    if trades.empty:
        runtime_trade_count = 0
        closed_count = 0
        realized = 0.0
    else:
        status = trades.get("status", pd.Series(dtype=str)).astype(str).str.upper()
        pnl = pd.to_numeric(trades.get("pnl_pips", pd.Series(dtype=float)), errors="coerce").fillna(0.0)
        runtime_trade_count = int(len(trades))
        closed_count = int((status == "CLOSED").sum())
        realized = float(pnl[status == "CLOSED"].sum())
    return pd.DataFrame(
        [
            {
                "symbol": symbol.upper(),
                "governance_selected_signal_count": int(governance_selected_signal_count),
                "runtime_trade_count": runtime_trade_count,
                "runtime_closed_trade_count": closed_count,
                "runtime_realized_pnl_pips": realized,
            }
        ]
    )


def build_findings(
    *,
    bar_deviation: pd.DataFrame,
    signal_deviation: pd.DataFrame,
    incomplete_rows: pd.DataFrame,
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for _, row in bar_deviation.iterrows():
        missing = int(row.get("missing_live_bars", 0) or 0)
        extra = int(row.get("extra_live_bars", 0) or 0)
        if missing or extra:
            rows.append(
                {
                    "symbol": row.get("symbol", ""),
                    "layer": "bar construction",
                    "finding_id": "BAR_ALIGNMENT_DELTA",
                    "classification": "Material Drift",
                    "metric_name": "missing_or_extra_bars",
                    "metric_value": float(missing + extra),
                    "reference_value": 0.0,
                    "details": f"missing_live_bars={missing}; extra_live_bars={extra}",
                    "source_path": "",
                }
            )
    for _, row in signal_deviation.iterrows():
        delta = int(row.get("selected_signal_delta", 0) or 0)
        if delta:
            rows.append(
                {
                    "symbol": row.get("symbol", ""),
                    "layer": "selected signal behavior",
                    "finding_id": "SELECTED_SIGNAL_COUNT_DELTA",
                    "classification": "Runtime Variance",
                    "metric_name": "selected_signal_delta",
                    "metric_value": float(delta),
                    "reference_value": 0.0,
                    "details": f"live_source={row.get('live_source', '')}",
                    "source_path": "",
                }
            )
    for _, row in incomplete_rows.iterrows():
        rows.append(
            {
                "symbol": row.get("symbol", ""),
                "layer": row.get("layer", "evidence"),
                "finding_id": row.get("finding_id", "INCOMPLETE_EVIDENCE"),
                "classification": "incomplete_evidence",
                "metric_name": "available",
                "metric_value": 0.0,
                "reference_value": 1.0,
                "details": row.get("reason", ""),
                "source_path": row.get("source_path", ""),
            }
        )
    if not rows:
        rows.append(
            {
                "symbol": "ALL",
                "layer": "summary",
                "finding_id": "NO_MATERIAL_FINDINGS",
                "classification": "info",
                "metric_name": "findings",
                "metric_value": 0.0,
                "reference_value": 0.0,
                "details": "No Material Drift findings were produced by this analytics run.",
                "source_path": "",
            }
        )
    return pd.DataFrame(rows)


def _markdown_table(df: pd.DataFrame) -> str:
    if df.empty:
        return "_empty_"
    try:
        return df.to_markdown(index=False)
    except Exception:
        return "```\n" + df.to_string(index=False) + "\n```"


def render_report(
    *,
    manifest: dict[str, Any],
    window_summary: pd.DataFrame,
    findings: pd.DataFrame,
    tick_coverage: pd.DataFrame,
    bar_deviation: pd.DataFrame,
    signal_deviation: pd.DataFrame,
    outcome_deviation: pd.DataFrame,
    skips: pd.DataFrame,
) -> str:
    lines = [
        "# Live Governance Deviation Report",
        "",
        f"- generated_at_utc: `{manifest.get('generated_at_utc', '')}`",
        f"- run_id: `{manifest.get('run_id', '')}`",
        "- authority: standalone analytics run; not a Promotion gate, restart gate, Stage 13 verdict, or Stage 14 verdict",
        "",
        "## Findings",
        _markdown_table(findings),
        "",
        "## Window Summary",
        _markdown_table(window_summary),
        "",
        "## Tick Coverage Deviation",
        _markdown_table(tick_coverage),
        "",
        "## Bar Deviation",
        _markdown_table(bar_deviation),
        "",
        "## Signal Deviation",
        _markdown_table(signal_deviation),
        "",
        "## Outcome Context",
        "Runtime Realized P&L is not treated as equivalent to Independent Label P&L.",
        "",
        _markdown_table(outcome_deviation),
        "",
        "## Skipped Symbols",
        _markdown_table(skips),
        "",
    ]
    return "\n".join(lines)
```

- [ ] **Step 4: Run the focused tests**

Run:

```bash
uv run pytest -q tests/test_live_governance_deviation.py
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/behemoth/diagnostics/live_governance_deviation.py tests/test_live_governance_deviation.py
git commit -m "feat: summarize live governance deviation findings"
```

---

### Task 5: Add Orchestration Run Function And File Outputs

**Files:**
- Modify: `src/behemoth/diagnostics/live_governance_deviation.py`
- Modify: `tests/test_live_governance_deviation.py`

- [ ] **Step 1: Write failing end-to-end module test**

Append to `tests/test_live_governance_deviation.py`:

```python
from src.behemoth.diagnostics.live_governance_deviation import run_analysis


def test_run_analysis_writes_required_outputs(tmp_path: Path) -> None:
    db_path = tmp_path / "runtime.db"
    _create_runtime_db(db_path)
    tick_root = tmp_path / "dukascopy_ticks"
    sym_dir = tick_root / "EURUSD"
    sym_dir.mkdir(parents=True)
    canonical = pd.DataFrame(
        {
            "timestamp": pd.date_range("2026-05-02T00:00:00Z", periods=300, freq="s"),
            "bid": [1.1] * 300,
            "ask": [1.1002] * 300,
            "mid": [1.1001] * 300,
            "spread": [0.0002] * 300,
            "log_return": [0.0] * 300,
        }
    )
    canonical.to_parquet(sym_dir / "EURUSD_202605_ticks.parquet", index=False)
    out_dir = tmp_path / "out"

    result = run_analysis(
        DeviationConfig(
            runtime_db=db_path,
            tick_root=tick_root,
            symbols=("EURUSD",),
            lookback_days=7,
            min_bars=2,
            run_id="jforex_live",
            out_dir=out_dir,
        )
    )

    assert result["manifest_path"].exists()
    assert (result["run_dir"] / "window_summary.csv").exists()
    assert (result["run_dir"] / "tick_coverage_deviation.csv").exists()
    assert (result["run_dir"] / "bar_deviation.csv").exists()
    assert (result["run_dir"] / "signal_deviation.csv").exists()
    assert (result["run_dir"] / "outcome_deviation.csv").exists()
    assert (result["run_dir"] / "findings.csv").exists()
    assert (result["run_dir"] / "live_governance_deviation_report.md").exists()
```

- [ ] **Step 2: Run the test and verify it fails**

Run:

```bash
uv run pytest -q tests/test_live_governance_deviation.py::test_run_analysis_writes_required_outputs
```

Expected: import failure for `run_analysis`.

- [ ] **Step 3: Implement orchestration and file writing**

Append to `src/behemoth/diagnostics/live_governance_deviation.py`:

```python
import json


def _run_dir(out_dir: Path) -> Path:
    stamp = utc_now().strftime("%Y%m%dT%H%M%SZ")
    return out_dir / stamp


def _window_summary_frame(windows: list[SymbolWindow]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "symbol": w.symbol,
                "start_ts": w.start_ts.isoformat(),
                "end_ts": w.end_ts.isoformat(),
                "raw_tick_count": w.raw_tick_count,
                "bar_count": w.bar_count,
                "bar_ticks": w.bar_ticks,
            }
            for w in windows
        ],
        columns=["symbol", "start_ts", "end_ts", "raw_tick_count", "bar_count", "bar_ticks"],
    )


def _write_df(path: Path, df: pd.DataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False)


def run_analysis(cfg: DeviationConfig) -> dict[str, Path]:
    run_dir = _run_dir(cfg.out_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(cfg.runtime_db), read_only=True)
    try:
        windows, skips = discover_symbol_windows(con, cfg)
        window_summary = _window_summary_frame(windows)
        tick_parts: list[pd.DataFrame] = []
        bar_parts: list[pd.DataFrame] = []
        signal_parts: list[pd.DataFrame] = []
        outcome_parts: list[pd.DataFrame] = []
        incomplete_rows: list[dict[str, str]] = []
        for window in windows:
            live = extract_live_evidence(con, window, run_id=cfg.run_id)
            canonical_ticks = load_canonical_ticks_for_window(
                tick_root=cfg.tick_root,
                symbol=window.symbol,
                start_ts=window.start_ts,
                end_ts=window.end_ts,
            )
            if canonical_ticks.empty:
                incomplete_rows.append(
                    {
                        "symbol": window.symbol,
                        "layer": "tick coverage",
                        "finding_id": "MISSING_CANONICAL_TICKS",
                        "reason": "canonical Dukascopy Raw Tick Data unavailable for window",
                        "source_path": str(cfg.tick_root / window.symbol),
                    }
                )
            governance_bars = build_governance_bars_for_window(
                canonical_ticks, bar_ticks=window.bar_ticks
            )
            tick_parts.append(compute_tick_coverage(window.symbol, live.raw_ticks, canonical_ticks))
            bar_parts.append(compute_bar_deviation(window.symbol, live.tick_bars, governance_bars))
            governance_predictions = pd.DataFrame()
            signal = compute_signal_deviation(
                window.symbol,
                live.predictions,
                governance_predictions,
                live_source=live.prediction_source,
            )
            signal_parts.append(signal)
            outcome_parts.append(
                compute_outcome_deviation(
                    window.symbol,
                    live.trades,
                    governance_selected_signal_count=int(
                        signal.loc[0, "governance_selected_signal_count"]
                    ),
                )
            )
            live.raw_ticks.to_parquet(run_dir / f"{window.symbol}_live_raw_ticks.parquet")
            live.tick_bars.to_parquet(run_dir / f"{window.symbol}_live_tick_bars.parquet")
            canonical_ticks.to_parquet(run_dir / f"{window.symbol}_governance_raw_ticks.parquet")
            governance_bars.to_parquet(run_dir / f"{window.symbol}_governance_tick_bars.parquet")
    finally:
        con.close()

    tick_coverage = pd.concat(tick_parts, ignore_index=True) if tick_parts else pd.DataFrame()
    bar_deviation = pd.concat(bar_parts, ignore_index=True) if bar_parts else pd.DataFrame()
    signal_deviation = pd.concat(signal_parts, ignore_index=True) if signal_parts else pd.DataFrame()
    outcome_deviation = pd.concat(outcome_parts, ignore_index=True) if outcome_parts else pd.DataFrame()
    incomplete = pd.DataFrame(incomplete_rows)
    findings = build_findings(
        bar_deviation=bar_deviation,
        signal_deviation=signal_deviation,
        incomplete_rows=incomplete,
    )
    manifest = {
        "generated_at_utc": utc_now().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "run_id": cfg.run_id,
        "runtime_db": str(cfg.runtime_db),
        "tick_root": str(cfg.tick_root),
        "symbols": list(cfg.symbols),
        "lookback_days": cfg.lookback_days,
        "min_bars": cfg.min_bars,
    }
    report = render_report(
        manifest=manifest,
        window_summary=window_summary,
        findings=findings,
        tick_coverage=tick_coverage,
        bar_deviation=bar_deviation,
        signal_deviation=signal_deviation,
        outcome_deviation=outcome_deviation,
        skips=skips,
    )
    manifest_path = run_dir / "run_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    _write_df(run_dir / "window_summary.csv", window_summary)
    _write_df(run_dir / "symbol_skips.csv", skips)
    _write_df(run_dir / "tick_coverage_deviation.csv", tick_coverage)
    _write_df(run_dir / "bar_deviation.csv", bar_deviation)
    _write_df(run_dir / "signal_deviation.csv", signal_deviation)
    _write_df(run_dir / "outcome_deviation.csv", outcome_deviation)
    _write_df(run_dir / "findings.csv", findings)
    report_path = run_dir / "live_governance_deviation_report.md"
    report_path.write_text(report, encoding="utf-8")
    if cfg.copy_report_to_docs:
        docs_path = Path("docs/analysis/live_governance_deviation_report.md")
        docs_path.parent.mkdir(parents=True, exist_ok=True)
        docs_path.write_text(report, encoding="utf-8")
    return {"run_dir": run_dir, "manifest_path": manifest_path, "report_path": report_path}
```

- [ ] **Step 4: Run the module tests**

Run:

```bash
uv run pytest -q tests/test_live_governance_deviation.py
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/behemoth/diagnostics/live_governance_deviation.py tests/test_live_governance_deviation.py
git commit -m "feat: write live governance deviation outputs"
```

---

### Task 6: Add CLI Wrapper

**Files:**
- Create: `scripts/analyze_live_governance_deviation.py`
- Modify: `tests/test_live_governance_deviation.py`

- [ ] **Step 1: Write failing CLI smoke test**

Append to `tests/test_live_governance_deviation.py`:

```python
import subprocess
import sys


def test_cli_smoke_writes_report(tmp_path: Path) -> None:
    db_path = tmp_path / "runtime.db"
    _create_runtime_db(db_path)
    tick_root = tmp_path / "dukascopy_ticks"
    sym_dir = tick_root / "EURUSD"
    sym_dir.mkdir(parents=True)
    canonical = pd.DataFrame(
        {
            "timestamp": pd.date_range("2026-05-02T00:00:00Z", periods=300, freq="s"),
            "bid": [1.1] * 300,
            "ask": [1.1002] * 300,
            "mid": [1.1001] * 300,
            "spread": [0.0002] * 300,
            "log_return": [0.0] * 300,
        }
    )
    canonical.to_parquet(sym_dir / "EURUSD_202605_ticks.parquet", index=False)
    out_dir = tmp_path / "out"
    result = subprocess.run(
        [
            sys.executable,
            "scripts/analyze_live_governance_deviation.py",
            "--runtime-db",
            str(db_path),
            "--tick-root",
            str(tick_root),
            "--symbols",
            "EURUSD",
            "--lookback-days",
            "7",
            "--min-bars",
            "2",
            "--run-id",
            "jforex_live",
            "--out-dir",
            str(out_dir),
        ],
        check=False,
        text=True,
        capture_output=True,
    )
    assert result.returncode == 0, result.stderr
    assert "report=" in result.stdout
    assert list(out_dir.glob("*/live_governance_deviation_report.md"))
```

- [ ] **Step 2: Run the test and verify it fails**

Run:

```bash
uv run pytest -q tests/test_live_governance_deviation.py::test_cli_smoke_writes_report
```

Expected: script file not found.

- [ ] **Step 3: Implement CLI wrapper**

Create `scripts/analyze_live_governance_deviation.py`:

```python
#!/usr/bin/env python3
"""Analyze recent Live Runtime versus Governance Runtime deviation."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.behemoth.diagnostics.live_governance_deviation import (  # noqa: E402
    ACTIVE_SYMBOLS,
    DeviationConfig,
    run_analysis,
)


def _parse_symbols(raw: str) -> tuple[str, ...]:
    if not raw.strip():
        return tuple(ACTIVE_SYMBOLS)
    return tuple(dict.fromkeys(s.strip().upper() for s in raw.split(",") if s.strip()))


def _parse_ts(raw: str) -> pd.Timestamp | None:
    txt = str(raw or "").strip()
    if not txt:
        return None
    return pd.Timestamp(txt, tz="UTC") if pd.Timestamp(txt).tzinfo is None else pd.Timestamp(txt).tz_convert("UTC")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime-db", type=Path, default=Path("data/analysis/backtest_reconcile/runtime/live_state.db"))
    parser.add_argument("--tick-root", type=Path, default=Path("/Users/danielfisher/Desktop/dukascopy_ticks"))
    parser.add_argument("--symbols", default=",".join(ACTIVE_SYMBOLS))
    parser.add_argument("--lookback-days", type=int, default=7)
    parser.add_argument("--min-bars", type=int, default=100)
    parser.add_argument("--run-id", default="jforex_live")
    parser.add_argument("--out-dir", type=Path, default=Path("data/analysis/live_governance_deviation"))
    parser.add_argument("--start-ts", default="")
    parser.add_argument("--end-ts", default="")
    parser.add_argument("--governance-dir", type=Path, default=Path("configs/research/governance/oco"))
    parser.add_argument("--models-dir", type=Path, default=Path("models/oco"))
    parser.add_argument("--api", default="")
    parser.add_argument("--copy-report-to-docs", action="store_true")
    args = parser.parse_args()

    result = run_analysis(
        DeviationConfig(
            runtime_db=args.runtime_db,
            tick_root=args.tick_root,
            symbols=_parse_symbols(args.symbols),
            lookback_days=int(args.lookback_days),
            min_bars=int(args.min_bars),
            run_id=str(args.run_id),
            out_dir=args.out_dir,
            start_ts=_parse_ts(args.start_ts),
            end_ts=_parse_ts(args.end_ts),
            governance_dir=args.governance_dir,
            models_dir=args.models_dir,
            api=str(args.api or ""),
            copy_report_to_docs=bool(args.copy_report_to_docs),
        )
    )
    print(f"run_dir={result['run_dir']}")
    print(f"manifest={result['manifest_path']}")
    print(f"report={result['report_path']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run CLI smoke test**

Run:

```bash
uv run pytest -q tests/test_live_governance_deviation.py::test_cli_smoke_writes_report
```

Expected: test passes.

- [ ] **Step 5: Commit**

```bash
git add scripts/analyze_live_governance_deviation.py tests/test_live_governance_deviation.py
git commit -m "feat: add live governance deviation cli"
```

---

### Task 7: Integrate Existing Diagnostic Scripts As Optional Subreports

**Files:**
- Modify: `src/behemoth/diagnostics/live_governance_deviation.py`
- Modify: `tests/test_live_governance_deviation.py`

- [ ] **Step 1: Write failing test for optional existing diagnostic references**

Append to `tests/test_live_governance_deviation.py`:

```python
def test_report_mentions_existing_diagnostic_subreports() -> None:
    report = render_report(
        manifest={
            "run_id": "unit",
            "generated_at_utc": "2026-05-09T00:00:00Z",
            "subreports": {
                "live_audit": "live_audit.md",
                "performance_gap": "performance_gap.md",
                "runtime_summary": "runtime_summary.csv",
            },
        },
        window_summary=pd.DataFrame(),
        findings=pd.DataFrame(),
        tick_coverage=pd.DataFrame(),
        bar_deviation=pd.DataFrame(),
        signal_deviation=pd.DataFrame(),
        outcome_deviation=pd.DataFrame(),
        skips=pd.DataFrame(),
    )
    assert "Existing Diagnostic Subreports" in report
    assert "live_audit.md" in report
    assert "performance_gap.md" in report
```

- [ ] **Step 2: Run the test and verify it fails**

Run:

```bash
uv run pytest -q tests/test_live_governance_deviation.py::test_report_mentions_existing_diagnostic_subreports
```

Expected: assertion failure because the report lacks the subreports section.

- [ ] **Step 3: Add subreport manifest support**

Modify `render_report` in `src/behemoth/diagnostics/live_governance_deviation.py` by inserting this block after the `authority` line:

```python
    subreports = manifest.get("subreports", {})
    if isinstance(subreports, dict) and subreports:
        lines.extend(["", "## Existing Diagnostic Subreports"])
        for name, path in sorted(subreports.items()):
            lines.append(f"- {name}: `{path}`")
```

Modify `run_analysis` before report rendering to populate paths for existing diagnostics that the workflow can call safely in later refinements:

```python
    manifest["subreports"] = {
        "runtime_summary": str(run_dir / "window_summary.csv"),
        "live_audit": str(run_dir / "live_audit_report.md"),
        "performance_gap": str(run_dir / "live_performance_gap_report.md"),
    }
```

Do not shell out to the existing scripts in this task. This task only creates stable report slots. Actual execution can be added after the core analytics is verified against real Runtime State.

- [ ] **Step 4: Run focused tests**

Run:

```bash
uv run pytest -q tests/test_live_governance_deviation.py::test_report_mentions_existing_diagnostic_subreports tests/test_live_governance_deviation.py::test_run_analysis_writes_required_outputs
```

Expected: both tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/behemoth/diagnostics/live_governance_deviation.py tests/test_live_governance_deviation.py
git commit -m "feat: reference existing deviation diagnostics"
```

---

### Task 8: Verification Against Local Runtime Evidence

**Files:**
- No code changes expected unless verification reveals a defect in the new workflow.

- [ ] **Step 1: Run focused unit tests**

Run:

```bash
uv run pytest -q tests/test_live_governance_deviation.py
```

Expected: all tests pass.

- [ ] **Step 2: Run related existing tests**

Run:

```bash
uv run pytest -q tests/test_compare_tick_data_sources.py tests/test_feature_engine.py
```

Expected: all tests pass.

- [ ] **Step 3: Run the standalone analytics CLI on the local Runtime State**

Use a low `--min-bars` only if the last-week window has too few completed bars during local verification:

```bash
uv run python scripts/analyze_live_governance_deviation.py \
  --runtime-db data/analysis/backtest_reconcile/runtime/live_state.db \
  --tick-root /Users/danielfisher/Desktop/dukascopy_ticks \
  --symbols EURUSD,GBPUSD,USDJPY,USDCHF,AUDUSD,USDCAD \
  --lookback-days 7 \
  --min-bars 100 \
  --run-id jforex_live \
  --out-dir data/analysis/live_governance_deviation \
  --copy-report-to-docs
```

Expected: command exits `0` and prints `run_dir=...`, `manifest=...`, and `report=...`.

- [ ] **Step 4: Inspect generated findings**

Run:

```bash
latest_dir="$(ls -td data/analysis/live_governance_deviation/* | head -n 1)"
sed -n '1,180p' "$latest_dir/live_governance_deviation_report.md"
python - <<'PY'
from pathlib import Path
import pandas as pd
latest = sorted(Path("data/analysis/live_governance_deviation").iterdir(), reverse=True)[0]
for name in ["window_summary.csv", "symbol_skips.csv", "findings.csv"]:
    path = latest / name
    print(f"\n{name}")
    print(pd.read_csv(path).head(20).to_string(index=False))
PY
```

Expected: report exists, findings are readable, and skipped symbols have explicit reasons.

- [ ] **Step 5: Check docs build only if report was copied to docs**

Run:

```bash
uv run mkdocs build
```

Expected: mkdocs build succeeds.

- [ ] **Step 6: Commit final generated docs report only if intentionally copied**

If `docs/analysis/live_governance_deviation_report.md` was created and should be versioned:

```bash
git add docs/analysis/live_governance_deviation_report.md
git commit -m "docs: add live governance deviation report"
```

If the report is local evidence only, leave generated `data/analysis/live_governance_deviation/` uncommitted or ignored according to repo policy.

---

## Self-Review

- Spec coverage: The plan covers a standalone CLI, recent DuckDB window discovery, live evidence extraction, canonical Dukascopy replay bars, tick/bar/signal/outcome metrics, structured findings, required outputs, non-gating report language, and tests.
- Reuse coverage: The plan reuses `diagnose_live_replay.py` for bar building immediately and leaves stable subreport slots for existing diagnostics. It avoids changes to Stage 13, Stage 14, Promotion, and restart tooling.
- Placeholder scan: No task uses deferred-work markers or open-ended "add tests" language. Each code task includes concrete test and implementation snippets.
- Type consistency: `DeviationConfig`, `SymbolWindow`, `LiveEvidence`, and the public functions introduced in early tasks are used consistently in later tasks.
