# Live Diagnostic Scripts Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `predict_evaluations` table that records every prediction outcome regardless of gate result, then build two diagnostic scripts to identify why the live system has low trade frequency and negative P&L.

**Architecture:** Phase 1 extends `StateManager` with a new `predict_evaluations` table (DDL + insert method) and wires a call in the predict endpoint inside the existing `for d in decisions` loop — unconditionally, before the `selected_exec==1` audit block. Phase 2 builds `diagnose_live_audit.py` (checkpoint → read DB → markdown report) and `diagnose_live_replay.py` (offline parquet → Polars bar build → CatBoost inference → markdown report).

**Tech Stack:** Python 3.12, DuckDB, Polars, CatBoost, requests, pytest

---

## File Map

| File | Role |
|------|------|
| `src/behemoth/runtime/state.py` | Add `predict_evaluations` DDL to `_CREATE_SQL`; add `_PREDICT_EVAL_INSERT_SQL` constant; add `log_predict_evaluation()` method |
| `src/behemoth/api/server.py` | Call `_state.log_predict_evaluation(...)` unconditionally inside `for d in decisions` loop (~line 2710), before the `if d.selected_exec == 1` block |
| `tests/test_state_predict_evaluations.py` | Unit tests for `log_predict_evaluation` |
| `scripts/diagnose_live_audit.py` | Checkpoint DB → read-only DuckDB → 4-section markdown report |
| `tests/test_diagnose_live_audit.py` | Tests using `_make_synthetic_db` pattern |
| `scripts/diagnose_live_replay.py` | Load parquet ticks → Polars bar build → feature compute → CatBoost inference → 4-section markdown report |
| `tests/test_diagnose_live_replay.py` | Tests using pre-built bar DataFrame + mocked model |

---

## Task 1: Add `predict_evaluations` DDL and insert method to StateManager

**Files:**
- Modify: `src/behemoth/runtime/state.py`

### Background

`_CREATE_SQL` is a module-level string starting at line 29. `StateManager.__init__` calls `self._con.execute(_CREATE_SQL)` at line 212, so adding a `CREATE TABLE IF NOT EXISTS` block there is sufficient — DuckDB's `IF NOT EXISTS` handles both fresh and existing DBs. No migration entry needed.

`log_audit_event` (line 361) is the model to follow structurally but `features_json` must be excluded from `predict_evaluations`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_state_predict_evaluations.py
from __future__ import annotations
from datetime import datetime, timezone
import pytest
from src.behemoth.runtime.state import StateManager


def _now():
    return datetime.now(tz=timezone.utc)


def test_log_predict_evaluation_writes_row():
    sm = StateManager()
    sm.log_predict_evaluation(
        symbol="EURUSD",
        candidate_uid="EURUSD_b100_h6_test",
        pred_prob=0.55,
        threshold=0.62,
        preselected_exec=0,
        selected_exec=0,
        threshold_blocked=False,
        threshold_block_reason=None,
        risk_blocked=False,
        risk_block_reason=None,
        model_month="2026-02",
        close_ts=_now(),
        run_id="test_run",
    )
    rows = sm._con.execute("SELECT * FROM predict_evaluations").fetchall()
    assert len(rows) == 1
    row = rows[0]
    # columns: event_ts, close_ts, symbol, candidate_uid, pred_prob, threshold,
    #          preselected_exec, selected_exec, threshold_blocked, threshold_block_reason,
    #          risk_blocked, risk_block_reason, model_month, run_id
    assert row[2] == "EURUSD"
    assert row[4] == pytest.approx(0.55)
    assert row[5] == pytest.approx(0.62)
    assert row[6] == 0   # preselected_exec
    assert row[7] == 0   # selected_exec


def test_log_predict_evaluation_does_not_touch_audit_logs():
    sm = StateManager()
    sm.log_predict_evaluation(
        symbol="GBPUSD",
        candidate_uid="GBPUSD_b100_h6_test",
        pred_prob=0.70,
        threshold=0.62,
        preselected_exec=1,
        selected_exec=1,
        threshold_blocked=False,
        threshold_block_reason=None,
        risk_blocked=False,
        risk_block_reason=None,
        model_month="2026-02",
        close_ts=_now(),
        run_id="test_run",
    )
    audit_rows = sm._con.execute("SELECT * FROM audit_logs").fetchall()
    assert audit_rows == []


def test_log_predict_evaluation_all_gate_outcomes():
    """Three rows covering all gate paths."""
    sm = StateManager()
    cases = [
        # sub-threshold
        dict(symbol="EURUSD", candidate_uid="c1", pred_prob=0.40, threshold=0.62,
             preselected_exec=0, selected_exec=0,
             threshold_blocked=False, threshold_block_reason=None,
             risk_blocked=False, risk_block_reason=None,
             model_month="2026-02", close_ts=_now(), run_id="r1"),
        # cleared threshold, blocked by risk
        dict(symbol="EURUSD", candidate_uid="c2", pred_prob=0.65, threshold=0.62,
             preselected_exec=1, selected_exec=0,
             threshold_blocked=False, threshold_block_reason=None,
             risk_blocked=True, risk_block_reason="BUDGET_EXCEEDED",
             model_month="2026-02", close_ts=_now(), run_id="r1"),
        # fully admitted
        dict(symbol="EURUSD", candidate_uid="c3", pred_prob=0.68, threshold=0.62,
             preselected_exec=1, selected_exec=1,
             threshold_blocked=False, threshold_block_reason=None,
             risk_blocked=False, risk_block_reason=None,
             model_month="2026-02", close_ts=_now(), run_id="r1"),
    ]
    for c in cases:
        sm.log_predict_evaluation(**c)
    rows = sm._con.execute(
        "SELECT preselected_exec, selected_exec FROM predict_evaluations ORDER BY event_ts"
    ).fetchall()
    assert rows == [(0, 0), (1, 0), (1, 1)]
```

- [ ] **Step 2: Run test to confirm failure**

```bash
pytest tests/test_state_predict_evaluations.py -v
```
Expected: `AttributeError: 'StateManager' object has no attribute 'log_predict_evaluation'`

- [ ] **Step 3: Add DDL to `_CREATE_SQL` and insert constant**

In `src/behemoth/runtime/state.py`, append to the `_CREATE_SQL` string (after the last existing `CREATE TABLE IF NOT EXISTS` block, before the closing `"""`):

```sql
CREATE TABLE IF NOT EXISTS predict_evaluations (
    event_ts        TIMESTAMP WITH TIME ZONE,
    close_ts        TIMESTAMP WITH TIME ZONE,
    symbol          VARCHAR,
    candidate_uid   VARCHAR,
    pred_prob       DOUBLE,
    threshold       DOUBLE,
    preselected_exec INTEGER,
    selected_exec    INTEGER,
    threshold_blocked BOOLEAN,
    threshold_block_reason VARCHAR,
    risk_blocked     BOOLEAN,
    risk_block_reason VARCHAR,
    model_month     VARCHAR,
    run_id          VARCHAR
);
```

Add a new module-level constant after `_AUDIT_INSERT_SQL`:

```python
_PREDICT_EVAL_INSERT_SQL = """
INSERT INTO predict_evaluations (
    event_ts, close_ts, symbol, candidate_uid, pred_prob, threshold,
    preselected_exec, selected_exec, threshold_blocked, threshold_block_reason,
    risk_blocked, risk_block_reason, model_month, run_id
) VALUES (
    CURRENT_TIMESTAMP,
    ?, ?, ?, ?, ?,
    ?, ?, ?, ?,
    ?, ?, ?, ?
)
"""
```

Add method to `StateManager` after `log_audit_event_batch`:

```python
def log_predict_evaluation(
    self,
    symbol: str,
    candidate_uid: str,
    pred_prob: float,
    threshold: float,
    preselected_exec: int,
    selected_exec: int,
    threshold_blocked: bool,
    threshold_block_reason: str | None,
    risk_blocked: bool,
    risk_block_reason: str | None,
    model_month: str,
    close_ts: datetime | None = None,
    run_id: str | None = None,
) -> None:
    """Record every prediction evaluation regardless of gate outcome."""
    self._con.execute(
        _PREDICT_EVAL_INSERT_SQL,
        [
            close_ts,
            symbol.upper(),
            candidate_uid,
            float(pred_prob),
            float(threshold),
            int(preselected_exec),
            int(selected_exec),
            bool(threshold_blocked),
            threshold_block_reason,
            bool(risk_blocked),
            risk_block_reason,
            model_month,
            run_id,
        ],
    )
```

- [ ] **Step 4: Run tests to confirm pass**

```bash
pytest tests/test_state_predict_evaluations.py -v
```
Expected: 3 tests PASSED

- [ ] **Step 5: Commit**

```bash
git add src/behemoth/runtime/state.py tests/test_state_predict_evaluations.py
git commit -m "feat: add predict_evaluations table and log_predict_evaluation() to StateManager"
```

---

## Task 2: Wire `log_predict_evaluation` into the predict endpoint

**Files:**
- Modify: `src/behemoth/api/server.py:2710-2737`

### Background

The `for d in decisions:` loop begins at line 2710. The `if d.selected_exec == 1 and _state is not None:` block starts at line 2711. The new call must be unconditional (not inside any `if` block) and must come before line 2711, so it records every candidate.

`_CandidateDecision` fields used: `d.candidate_uid`, `d.pred_prob`, `d.curr_threshold`, `d.preselected_exec`, `d.selected_exec`, `d.threshold_blocked`, `d.threshold_block_reason`, `d.risk_blocked`, `d.risk_block_reason`. The variables `close_ts`, `model_month`, `run_id`, `sym` are in scope at that point.

- [ ] **Step 1: Write the failing test**

There is an existing integration test file for the predict endpoint. Add a targeted test to `tests/test_duckdb_state.py` instead (simpler — tests the StateManager directly, which we already verified):

```python
def test_predict_evaluation_table_exists_after_init():
    """Smoke test: predict_evaluations table is created by StateManager init."""
    sm = StateManager()
    tables = sm._con.execute(
        "SELECT table_name FROM information_schema.tables WHERE table_name = 'predict_evaluations'"
    ).fetchall()
    assert len(tables) == 1
```

- [ ] **Step 2: Run test**

```bash
pytest tests/test_duckdb_state.py::test_predict_evaluation_table_exists_after_init -v
```
Expected: PASSED (the DDL is already in place from Task 1)

- [ ] **Step 3: Add the call in `server.py`**

In `src/behemoth/api/server.py`, locate the `for d in decisions:` loop at line ~2710. Insert the following block as the **first statement inside the loop**, before `if d.selected_exec == 1 and _state is not None:`:

```python
        if _state is not None:
            _state.log_predict_evaluation(
                symbol=sym,
                candidate_uid=d.candidate_uid,
                pred_prob=d.pred_prob,
                threshold=d.curr_threshold,
                preselected_exec=d.preselected_exec,
                selected_exec=d.selected_exec,
                threshold_blocked=bool(getattr(d, "threshold_blocked", False)),
                threshold_block_reason=getattr(d, "threshold_block_reason", None),
                risk_blocked=d.risk_blocked,
                risk_block_reason=d.risk_block_reason,
                model_month=model_month,
                close_ts=close_ts,
                run_id=run_id,
            )
```

- [ ] **Step 4: Run the full state test suite**

```bash
pytest tests/test_duckdb_state.py tests/test_state_predict_evaluations.py -v
```
Expected: all PASSED

- [ ] **Step 5: Commit**

```bash
git add src/behemoth/api/server.py
git commit -m "feat: wire log_predict_evaluation into predict endpoint for all candidates"
```

---

## Task 3: `diagnose_live_audit.py` — scaffold and checkpoint helper

**Files:**
- Create: `scripts/diagnose_live_audit.py`
- Create: `tests/test_diagnose_live_audit.py`

- [ ] **Step 1: Write the failing test for checkpoint helper and CLI**

```python
# tests/test_diagnose_live_audit.py
from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path
import duckdb
import pytest
from unittest.mock import patch, MagicMock


def _make_synthetic_db(path: Path) -> None:
    con = duckdb.connect(str(path))
    con.execute("""
        CREATE TABLE predict_evaluations (
            event_ts TIMESTAMP WITH TIME ZONE,
            close_ts TIMESTAMP WITH TIME ZONE,
            symbol VARCHAR,
            candidate_uid VARCHAR,
            pred_prob DOUBLE,
            threshold DOUBLE,
            preselected_exec INTEGER,
            selected_exec INTEGER,
            threshold_blocked BOOLEAN,
            threshold_block_reason VARCHAR,
            risk_blocked BOOLEAN,
            risk_block_reason VARCHAR,
            model_month VARCHAR,
            run_id VARCHAR
        )
    """)
    con.execute("""
        CREATE TABLE audit_logs (
            event_ts TIMESTAMP WITH TIME ZONE,
            close_ts TIMESTAMP WITH TIME ZONE,
            symbol VARCHAR,
            candidate_uid VARCHAR,
            pred_prob DOUBLE,
            threshold DOUBLE,
            features_json VARCHAR,
            model_month VARCHAR,
            run_id VARCHAR
        )
    """)
    con.execute("""
        CREATE TABLE account_risk_allocator_events (
            event_ts TIMESTAMP WITH TIME ZONE,
            symbol VARCHAR,
            candidate_uid VARCHAR,
            status VARCHAR,
            block_reason VARCHAR,
            reserved_loss_ccy DOUBLE,
            requested_volume_units DOUBLE,
            pred_prob DOUBLE,
            threshold_exec DOUBLE,
            risk_rank_score DOUBLE,
            reservation_id VARCHAR
        )
    """)
    con.execute("""
        CREATE TABLE trades (
            internal_trade_id VARCHAR,
            symbol VARCHAR,
            candidate_uid VARCHAR,
            side VARCHAR,
            entry_price DOUBLE,
            entry_ts TIMESTAMP WITH TIME ZONE,
            exit_price DOUBLE,
            exit_ts TIMESTAMP WITH TIME ZONE,
            pnl_pips DOUBLE,
            status VARCHAR,
            close_reason VARCHAR,
            run_id VARCHAR
        )
    """)
    con.close()


def test_checkpoint_helper_warns_on_failure(tmp_path):
    db = tmp_path / "state.db"
    _make_synthetic_db(db)
    with patch("requests.get", side_effect=Exception("connection refused")):
        import importlib, sys
        # script not yet created — will fail with ModuleNotFoundError
        with pytest.raises((ModuleNotFoundError, ImportError, Exception)):
            import scripts.diagnose_live_audit  # noqa
```

- [ ] **Step 2: Run test to confirm failure (module missing)**

```bash
pytest tests/test_diagnose_live_audit.py::test_checkpoint_helper_warns_on_failure -v
```
Expected: `ModuleNotFoundError` or `ImportError`

- [ ] **Step 3: Create `scripts/diagnose_live_audit.py` with scaffold and checkpoint helper**

```python
#!/usr/bin/env python3
"""Diagnose live trading system from checkpointed live_state.db.

Produces a markdown report covering:
  1. Prediction funnel (predict_evaluations if available, else fallback)
  2. Score distribution
  3. Block reason breakdown
  4. Trade outcomes

Usage:
    python scripts/diagnose_live_audit.py \
        --db data/analysis/backtest_reconcile/runtime/live_state.db \
        --api http://localhost:8000 \
        --run-id jforex_live \
        --out data/analysis/live_audit_report.md
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path

import duckdb
import requests


def checkpoint_and_connect(api_base: str, db_path: str) -> duckdb.DuckDBPyConnection:
    try:
        requests.get(f"{api_base}/state/checkpoint", timeout=5).raise_for_status()
    except requests.RequestException as e:
        print(f"Warning: checkpoint failed ({e}). Reading DB as-is (WAL may be incomplete).")
    return duckdb.connect(db_path, read_only=True)


def _has_predict_evaluations(con: duckdb.DuckDBPyConnection, run_id: str) -> bool:
    tables = {r[0] for r in con.execute(
        "SELECT table_name FROM information_schema.tables"
    ).fetchall()}
    if "predict_evaluations" not in tables:
        return False
    count = con.execute(
        "SELECT COUNT(*) FROM predict_evaluations WHERE run_id = ?", [run_id]
    ).fetchone()[0]
    return count > 0


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", required=True)
    parser.add_argument("--api", default="http://localhost:8000")
    parser.add_argument("--run-id", default="jforex_live")
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    con = checkpoint_and_connect(args.api, args.db)
    run_id = args.run_id
    use_eval = _has_predict_evaluations(con, run_id)

    lines: list[str] = [
        f"# Live Audit Report",
        f"",
        f"**Generated:** {datetime.now(tz=timezone.utc).isoformat()}  ",
        f"**Run ID:** {run_id}  ",
        f"**Data source:** {'predict_evaluations' if use_eval else 'account_risk_allocator_events (fallback)'}  ",
        f"",
    ]

    lines += _section_funnel(con, run_id, use_eval)
    lines += _section_score_distribution(con, run_id, use_eval)
    lines += _section_block_reasons(con, run_id, use_eval)
    lines += _section_trade_outcomes(con, run_id)

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text("\n".join(lines))
    print(f"Report written to {args.out}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run test again (will still fail — functions not yet defined)**

```bash
pytest tests/test_diagnose_live_audit.py -v
```
Expected: `ImportError` resolved but test may still fail depending on mock scope — confirm scaffold imports cleanly: `python -c "import scripts.diagnose_live_audit"`

---

## Task 4: `diagnose_live_audit.py` — implement all four report sections

**Files:**
- Modify: `scripts/diagnose_live_audit.py`
- Modify: `tests/test_diagnose_live_audit.py`

- [ ] **Step 1: Write tests for the four sections**

Add to `tests/test_diagnose_live_audit.py`:

```python
from scripts.diagnose_live_audit import (
    _has_predict_evaluations,
    _section_funnel,
    _section_score_distribution,
    _section_block_reasons,
    _section_trade_outcomes,
)


@pytest.fixture
def db_with_eval(tmp_path):
    """DB with predict_evaluations populated."""
    p = tmp_path / "state.db"
    _make_synthetic_db(p)
    con = duckdb.connect(str(p))
    # 10 sub-threshold, 5 cleared threshold / blocked by risk, 3 fully admitted
    now = datetime.now(tz=timezone.utc)
    for i in range(10):
        con.execute(
            "INSERT INTO predict_evaluations VALUES (?, ?, 'EURUSD', 'c1', 0.40, 0.62, 0, 0, false, NULL, false, NULL, '2026-02', 'run1')",
            [now, now]
        )
    for i in range(5):
        con.execute(
            "INSERT INTO predict_evaluations VALUES (?, ?, 'EURUSD', 'c2', 0.65, 0.62, 1, 0, false, NULL, true, 'BUDGET_EXCEEDED', '2026-02', 'run1')",
            [now, now]
        )
    for i in range(3):
        con.execute(
            "INSERT INTO predict_evaluations VALUES (?, ?, 'EURUSD', 'c3', 0.70, 0.62, 1, 1, false, NULL, false, NULL, '2026-02', 'run1')",
            [now, now]
        )
    # 2 closed trades: 1 win, 1 loss
    con.execute(
        "INSERT INTO trades VALUES ('t1', 'EURUSD', 'c3', 'BUY', 1.1, ?, 1.105, ?, 5.0, 'CLOSED', 'HORIZON_EXIT', 'run1')",
        [now, now]
    )
    con.execute(
        "INSERT INTO trades VALUES ('t2', 'EURUSD', 'c3', 'BUY', 1.1, ?, 1.095, ?, -5.0, 'CLOSED', 'STOP_HIT', 'run1')",
        [now, now]
    )
    con.close()
    return duckdb.connect(str(p), read_only=True)


@pytest.fixture
def db_fallback(tmp_path):
    """DB without predict_evaluations (fallback path)."""
    p = tmp_path / "state.db"
    _make_synthetic_db(p)
    con = duckdb.connect(str(p))
    now = datetime.now(tz=timezone.utc)
    con.execute(
        "INSERT INTO account_risk_allocator_events VALUES (?, 'EURUSD', 'c1', 'ADMITTED', NULL, 10.0, 0.01, 0.65, 0.62, 0.9, 'res1')",
        [now]
    )
    con.execute(
        "INSERT INTO account_risk_allocator_events VALUES (?, 'EURUSD', 'c2', 'BLOCKED', 'BUDGET_EXCEEDED', NULL, 0.01, 0.64, 0.62, 0.8, NULL)",
        [now]
    )
    con.close()
    return duckdb.connect(str(p), read_only=True)


def test_has_predict_evaluations_true(db_with_eval):
    assert _has_predict_evaluations(db_with_eval, "run1") is True


def test_has_predict_evaluations_false(db_fallback):
    assert _has_predict_evaluations(db_fallback, "run1") is False


def test_funnel_with_eval(db_with_eval):
    lines = _section_funnel(db_with_eval, "run1", use_eval=True)
    text = "\n".join(lines)
    assert "EURUSD" in text
    assert "18" in text  # total: 10+5+3
    assert "8" in text   # preselected: 5+3
    assert "3" in text   # selected: 3


def test_funnel_fallback(db_fallback):
    lines = _section_funnel(db_fallback, "run1", use_eval=False)
    text = "\n".join(lines)
    assert "ADMITTED" in text or "admitted" in text.lower()
    assert "BUDGET_EXCEEDED" in text or "fallback" in text.lower()


def test_score_distribution_with_eval(db_with_eval):
    lines = _section_score_distribution(db_with_eval, "run1", use_eval=True)
    text = "\n".join(lines)
    assert "EURUSD" in text
    assert "p50" in text or "50" in text


def test_block_reasons_with_eval(db_with_eval):
    lines = _section_block_reasons(db_with_eval, "run1", use_eval=True)
    text = "\n".join(lines)
    assert "BUDGET_EXCEEDED" in text


def test_trade_outcomes(db_with_eval):
    lines = _section_trade_outcomes(db_with_eval, "run1")
    text = "\n".join(lines)
    assert "EURUSD" in text
    assert "50" in text   # 50% win rate
    assert "2" in text    # 2 closed trades
```

- [ ] **Step 2: Run tests to confirm failure**

```bash
pytest tests/test_diagnose_live_audit.py -v
```
Expected: `ImportError` for the section functions (not yet defined)

- [ ] **Step 3: Implement the four section functions**

Add to `scripts/diagnose_live_audit.py` (before `main()`):

```python
def _section_funnel(
    con: duckdb.DuckDBPyConnection, run_id: str, use_eval: bool
) -> list[str]:
    lines = ["## 1. Prediction Funnel", ""]
    if use_eval:
        rows = con.execute("""
            SELECT
                symbol,
                COUNT(*) AS total,
                SUM(preselected_exec) AS cleared_threshold,
                SUM(selected_exec) AS cleared_risk
            FROM predict_evaluations
            WHERE run_id = ?
            GROUP BY symbol ORDER BY symbol
        """, [run_id]).fetchall()
        trade_counts = dict(con.execute("""
            SELECT symbol, COUNT(*) FROM trades
            WHERE status = 'CLOSED' AND run_id = ?
            GROUP BY symbol
        """, [run_id]).fetchall())
        lines += ["| Symbol | Total Evals | Cleared Threshold | Cleared Risk | Became Trades |",
                  "|--------|------------|-------------------|--------------|---------------|"]
        for sym, total, pre, sel in rows:
            trades = trade_counts.get(sym, 0)
            lines.append(f"| {sym} | {total} | {pre} | {sel} | {trades} |")
    else:
        # Check for multiple run IDs (no run_id on this table)
        run_ids = con.execute("SELECT DISTINCT run_id FROM trades").fetchall()
        if len(run_ids) > 1:
            lines.append(f"> ⚠️ Multiple run IDs found in trades ({[r[0] for r in run_ids]}). "
                         f"account_risk_allocator_events has no run_id — results span all sessions.")
        rows = con.execute("""
            SELECT symbol, status, block_reason, COUNT(*) AS cnt
            FROM account_risk_allocator_events
            GROUP BY symbol, status, block_reason ORDER BY symbol, status
        """).fetchall()
        lines += ["| Symbol | Status | Block Reason | Count |",
                  "|--------|--------|--------------|-------|"]
        for sym, status, reason, cnt in rows:
            lines.append(f"| {sym} | {status} | {reason or '-'} | {cnt} |")
        lines += ["", "> ℹ️ `predict_evaluations` not populated for this session — "
                  "sub-threshold misses not visible. Re-run after Phase 1 schema extension."]
    lines.append("")
    return lines


def _section_score_distribution(
    con: duckdb.DuckDBPyConnection, run_id: str, use_eval: bool
) -> list[str]:
    lines = ["## 2. Score Distribution", ""]
    if use_eval:
        src = "predict_evaluations"
    else:
        src = "audit_logs"
        lines.append("> ℹ️ Showing admitted predictions only (predict_evaluations not available).")
        lines.append("")
    rows = con.execute(f"""
        SELECT
            symbol,
            ROUND(PERCENTILE_CONT(0.25) WITHIN GROUP (ORDER BY pred_prob), 4) AS p25,
            ROUND(PERCENTILE_CONT(0.50) WITHIN GROUP (ORDER BY pred_prob), 4) AS p50,
            ROUND(PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY pred_prob), 4) AS p75,
            ROUND(PERCENTILE_CONT(0.90) WITHIN GROUP (ORDER BY pred_prob), 4) AS p90,
            ROUND(PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY pred_prob), 4) AS p95,
            ROUND(AVG(threshold), 4) AS avg_threshold,
            COUNT(*) AS n
        FROM {src}
        WHERE run_id = ?
        GROUP BY symbol ORDER BY symbol
    """, [run_id]).fetchall()
    lines += ["| Symbol | p25 | p50 | p75 | p90 | p95 | threshold | n |",
              "|--------|-----|-----|-----|-----|-----|-----------|---|"]
    for sym, p25, p50, p75, p90, p95, thr, n in rows:
        lines.append(f"| {sym} | {p25} | {p50} | {p75} | {p90} | {p95} | {thr} | {n} |")
    lines.append("")
    return lines


def _section_block_reasons(
    con: duckdb.DuckDBPyConnection, run_id: str, use_eval: bool
) -> list[str]:
    lines = ["## 3. Block Reason Breakdown", ""]
    if use_eval:
        thr_rows = con.execute("""
            SELECT symbol, threshold_block_reason, COUNT(*) AS cnt
            FROM predict_evaluations
            WHERE run_id = ? AND threshold_block_reason IS NOT NULL
            GROUP BY symbol, threshold_block_reason ORDER BY symbol, cnt DESC
        """, [run_id]).fetchall()
        risk_rows = con.execute("""
            SELECT symbol, risk_block_reason, COUNT(*) AS cnt
            FROM predict_evaluations
            WHERE run_id = ? AND risk_block_reason IS NOT NULL
            GROUP BY symbol, risk_block_reason ORDER BY symbol, cnt DESC
        """, [run_id]).fetchall()
        if thr_rows:
            lines += ["**Threshold blocks:**", "",
                      "| Symbol | Reason | Count |", "|--------|--------|-------|"]
            for sym, reason, cnt in thr_rows:
                lines.append(f"| {sym} | {reason} | {cnt} |")
            lines.append("")
        else:
            lines.append("No threshold blocks recorded.")
            lines.append("")
        if risk_rows:
            lines += ["**Risk blocks:**", "",
                      "| Symbol | Reason | Count |", "|--------|--------|-------|"]
            for sym, reason, cnt in risk_rows:
                lines.append(f"| {sym} | {reason} | {cnt} |")
        else:
            lines.append("No risk blocks recorded.")
    else:
        rows = con.execute("""
            SELECT symbol, block_reason, COUNT(*) AS cnt
            FROM account_risk_allocator_events
            WHERE block_reason IS NOT NULL
            GROUP BY symbol, block_reason ORDER BY symbol, cnt DESC
        """).fetchall()
        if rows:
            lines += ["| Symbol | Risk Block Reason | Count |",
                      "|--------|-------------------|-------|"]
            for sym, reason, cnt in rows:
                lines.append(f"| {sym} | {reason} | {cnt} |")
        else:
            lines.append("No risk block reasons recorded.")
        lines += ["", "> ℹ️ Threshold-enforcement blocking (ROLLING_HISTORY_GAP, SCHEDULE_EXPIRED) "
                  "is only visible in server logs when using fallback."]
    lines.append("")
    return lines


def _section_trade_outcomes(
    con: duckdb.DuckDBPyConnection, run_id: str
) -> list[str]:
    lines = ["## 4. Trade Outcomes", ""]
    rows = con.execute("""
        SELECT
            symbol,
            COUNT(*) AS closed,
            COUNT(CASE WHEN pnl_pips > 0 THEN 1 END) AS wins,
            ROUND(100.0 * COUNT(CASE WHEN pnl_pips > 0 THEN 1 END) / COUNT(*), 1) AS win_pct,
            ROUND(AVG(CASE WHEN pnl_pips > 0 THEN pnl_pips END), 2) AS avg_win,
            ROUND(AVG(CASE WHEN pnl_pips <= 0 THEN pnl_pips END), 2) AS avg_loss,
            ROUND(SUM(pnl_pips), 2) AS total_pips
        FROM trades
        WHERE status = 'CLOSED' AND run_id = ?
        GROUP BY symbol ORDER BY symbol
    """, [run_id]).fetchall()
    if not rows:
        lines.append("No closed trades for this run.")
        lines.append("")
        return lines
    lines += ["| Symbol | Closed | Win% | Avg Win | Avg Loss | Total P&L |",
              "|--------|--------|------|---------|----------|-----------|"]
    for sym, closed, wins, win_pct, avg_win, avg_loss, total in rows:
        lines.append(
            f"| {sym} | {closed} | {win_pct}% | {avg_win or '-'} | {avg_loss or '-'} | {total} |"
        )
    lines.append("")
    # close_reason breakdown
    reason_rows = con.execute("""
        SELECT symbol, close_reason, COUNT(*) AS cnt
        FROM trades WHERE status = 'CLOSED' AND run_id = ?
        GROUP BY symbol, close_reason ORDER BY symbol, cnt DESC
    """, [run_id]).fetchall()
    if reason_rows:
        lines += ["**Close reason breakdown:**", "",
                  "| Symbol | Reason | Count |", "|--------|--------|-------|"]
        for sym, reason, cnt in reason_rows:
            lines.append(f"| {sym} | {reason or '-'} | {cnt} |")
    lines.append("")
    return lines
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_diagnose_live_audit.py -v
```
Expected: all PASSED

- [ ] **Step 5: Commit**

```bash
git add scripts/diagnose_live_audit.py tests/test_diagnose_live_audit.py
git commit -m "feat: add diagnose_live_audit.py with 4-section prediction funnel report"
```

---

## Task 5: `diagnose_live_replay.py` — offline bar build + inference pipeline

**Files:**
- Create: `scripts/diagnose_live_replay.py`
- Create: `tests/test_diagnose_live_replay.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_diagnose_live_replay.py
from __future__ import annotations
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch
import numpy as np
import polars as pl
import pytest

from scripts.diagnose_live_replay import (
    _build_bars_from_ticks,
    _load_states,
    _score_bars,
    _section_score_distribution,
    _section_near_miss,
    _section_sensitivity_sweep,
    _section_score_drift,
)


def _make_tick_df(n_ticks: int = 30000) -> pl.DataFrame:
    """Minimal synthetic tick DataFrame with required columns."""
    rng = np.random.default_rng(42)
    bid = 1.10000 + np.cumsum(rng.normal(0, 0.0001, n_ticks))
    ask = bid + 0.00020
    ts = [datetime(2026, 3, 1, tzinfo=timezone.utc) + timedelta(seconds=i) for i in range(n_ticks)]
    return pl.DataFrame({
        "timestamp": ts,
        "bid": bid,
        "ask": ask,
        "mid": (bid + ask) / 2,
        "spread": ask - bid,
        "log_return": np.concatenate([[0.0], np.diff(np.log(bid))]),
    })


def _make_bars_df(n_bars: int = 350) -> pl.DataFrame:
    """Pre-built bar DataFrame (≥289 needed for feature warmup)."""
    rng = np.random.default_rng(42)
    closes = 1.10000 + np.cumsum(rng.normal(0, 0.0005, n_bars))
    ts = [datetime(2026, 3, 1, tzinfo=timezone.utc) + timedelta(minutes=i * 10) for i in range(n_bars)]
    close_ts = [t + timedelta(minutes=9) for t in ts]
    highs = closes + rng.uniform(0.0002, 0.0010, n_bars)
    lows = closes - rng.uniform(0.0002, 0.0010, n_bars)
    opens = closes - rng.normal(0, 0.0003, n_bars)
    return pl.DataFrame({
        "timestamp": ts,
        "close_ts": close_ts,
        "open": opens,
        "high": highs,
        "low": lows,
        "close": closes,
        "spread": np.full(n_bars, 0.0002),
        "tick_volume": np.full(n_bars, 100.0),
        "hl_first": rng.choice([-1.0, 0.0, 1.0], n_bars),
        "hl_pos_frac": rng.uniform(-1, 1, n_bars),
    })


def test_build_bars_from_ticks_produces_correct_bar_count():
    ticks = _make_tick_df(1000)
    bars = _build_bars_from_ticks(ticks)
    assert len(bars) == 10  # 1000 ticks / 100 = 10 bars


def test_build_bars_from_ticks_drops_partial_bar():
    ticks = _make_tick_df(150)  # 1 complete + 50 leftover
    bars = _build_bars_from_ticks(ticks)
    assert len(bars) == 1


def test_build_bars_has_required_columns():
    ticks = _make_tick_df(300)
    bars = _build_bars_from_ticks(ticks)
    for col in ["open", "high", "low", "close", "spread", "hl_first", "hl_pos_frac", "tick_volume", "timestamp", "close_ts"]:
        assert col in bars.columns, f"Missing column: {col}"


def test_load_states(tmp_path):
    lock = {
        "state_universe": {
            "count": 1,
            "rows": [{"bar_ticks": 100, "horizon": 6, "barrier_pips": 2.0, "state_id": "state_A"}]
        }
    }
    (tmp_path / "eurusd_oco_live_lock.json").write_text(json.dumps(lock))
    states = _load_states("EURUSD", str(tmp_path))
    assert len(states) == 1
    assert states[0]["state_id"] == "state_A"
    assert states[0]["horizon"] == 6


def test_score_bars_returns_correct_columns(tmp_path):
    bars = _make_bars_df(350)
    mock_model = MagicMock()
    mock_model.predict_proba.return_value = np.column_stack([
        np.full(350, 0.40),
        np.full(350, 0.60),
    ])
    thresholds = {"2026-03-01": 0.62}
    threshold_exec = 0.62

    with patch("src.behemoth.core.features.compute_feature_matrix_from_bars") as mock_feat:
        import pandas as pd
        feat_df = pd.DataFrame({
            "bar_idx": range(350),
            "dummy_feat": np.ones(350),
        })
        mock_feat.return_value = feat_df
        mock_model.predict_proba.return_value = np.column_stack([
            np.full(len(feat_df), 0.40), np.full(len(feat_df), 0.60)
        ])
        result = _score_bars(
            bars=bars,
            symbol="EURUSD",
            state={"bar_ticks": 100, "horizon": 6, "barrier_pips": 2.0, "state_id": "state_A"},
            model=mock_model,
            thresholds=thresholds,
            threshold_exec=threshold_exec,
        )
    assert "pred_prob" in result.columns
    assert "threshold" in result.columns
    assert "selected" in result.columns
    assert "gap" in result.columns


def test_section_near_miss_ordering():
    """Top 10 near-misses should be sorted by gap ascending."""
    import pandas as pd
    scored = pl.from_pandas(pd.DataFrame({
        "close_ts": [datetime(2026, 3, 1, tzinfo=timezone.utc)] * 15,
        "state_id": ["state_A"] * 15,
        "pred_prob": [0.60 - i * 0.001 for i in range(15)],
        "threshold": [0.62] * 15,
        "selected": [False] * 15,
        "gap": [0.02 + i * 0.001 for i in range(15)],
    }))
    lines = _section_near_miss({"EURUSD": {"state_A": scored}})
    text = "\n".join(lines)
    # gap=0.02 should appear before gap=0.029
    assert text.index("0.02") < text.index("0.029")


def test_section_sensitivity_sweep():
    import pandas as pd
    scored = pl.from_pandas(pd.DataFrame({
        "close_ts": [datetime(2026, 3, 1, tzinfo=timezone.utc)] * 100,
        "state_id": ["state_A"] * 100,
        "pred_prob": [0.55] * 40 + [0.60] * 40 + [0.65] * 20,
        "threshold": [0.62] * 100,
        "selected": [False] * 80 + [True] * 20,
        "gap": [0.07] * 40 + [0.02] * 40 + [-0.03] * 20,
    }))
    lines = _section_sensitivity_sweep({"EURUSD": {"state_A": scored}})
    text = "\n".join(lines)
    assert "0.50" in text
    assert "0.65" in text
```

- [ ] **Step 2: Run tests to confirm failure**

```bash
pytest tests/test_diagnose_live_replay.py -v
```
Expected: `ModuleNotFoundError: No module named 'scripts.diagnose_live_replay'`

- [ ] **Step 3: Implement `scripts/diagnose_live_replay.py`**

```python
#!/usr/bin/env python3
"""Offline model replay against parquet tick bars.

Scores every bar including sub-threshold predictions without touching
the live server or opening trades.

Usage:
    python scripts/diagnose_live_replay.py \
        --ticks-dir /Users/danielfisher/Desktop/dukascopy_ticks \
        --models-dir models/oco \
        --governance-dir configs/research/governance/oco \
        --model-month 2026-02 \
        --lookback-months 1 \
        --out data/analysis/live_replay_report.md
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import polars as pl

from src.behemoth.core.features import compute_feature_matrix_from_bars


def _build_bars_from_ticks(ticks: pl.DataFrame) -> pl.DataFrame:
    """Aggregate raw ticks to 100-tick bars via vectorised Polars."""
    ticks = ticks.with_columns(
        (pl.int_range(pl.len(), dtype=pl.Int64) // 100).alias("bar_group")
    )
    # Drop partial final bar
    counts = ticks.group_by("bar_group").agg(pl.len().alias("n"))
    complete = counts.filter(pl.col("n") == 100).select("bar_group")
    ticks = ticks.join(complete, on="bar_group")

    def _hl_first(bid_series: list[float]) -> float:
        hi = int(np.argmax(bid_series))
        lo = int(np.argmin(bid_series))
        if hi < lo:
            return 1.0
        elif hi > lo:
            return -1.0
        return 0.0

    def _hl_pos_frac(bid_series: list[float]) -> float:
        hi = int(np.argmax(bid_series))
        lo = int(np.argmin(bid_series))
        return (lo - hi) / 99.0

    bars = (
        ticks.group_by("bar_group")
        .agg([
            pl.first("timestamp").alias("timestamp"),
            pl.last("timestamp").alias("close_ts"),
            pl.first("bid").alias("open"),
            pl.max("bid").alias("high"),
            pl.min("bid").alias("low"),
            pl.last("bid").alias("close"),
            pl.mean("spread").alias("spread"),
            pl.len().alias("tick_volume"),
            pl.col("bid").map_elements(_hl_first, return_dtype=pl.Float64).alias("hl_first"),
            pl.col("bid").map_elements(_hl_pos_frac, return_dtype=pl.Float64).alias("hl_pos_frac"),
        ])
        .sort("bar_group")
        .drop("bar_group")
    )
    return bars


def _load_states(symbol: str, governance_dir: str) -> list[dict]:
    lock_path = Path(governance_dir) / f"{symbol.lower()}_oco_live_lock.json"
    data = json.loads(lock_path.read_text())
    return data["state_universe"]["rows"]


def _load_thresholds(symbol: str, models_dir: str, model_month: str) -> tuple[dict, float]:
    meta_path = Path(models_dir) / f"{symbol}_model_{model_month}.json"
    meta = json.loads(meta_path.read_text())
    return meta.get("threshold_schedule", {}), float(meta["threshold_exec"])


def _score_bars(
    bars: pl.DataFrame,
    symbol: str,
    state: dict,
    model,
    thresholds: dict,
    threshold_exec: float,
) -> pl.DataFrame:
    bars_pd = bars.to_pandas()
    feat_df = compute_feature_matrix_from_bars(
        bars_pd,
        symbol=symbol,
        bar_ticks=int(state["bar_ticks"]),
        horizon=int(state["horizon"]),
        barrier_pips=float(state["barrier_pips"]),
    )
    if feat_df is None or len(feat_df) == 0:
        return pl.DataFrame(schema={
            "close_ts": pl.Datetime(time_unit="us", time_zone="UTC"),
            "state_id": pl.Utf8,
            "pred_prob": pl.Float64,
            "threshold": pl.Float64,
            "selected": pl.Boolean,
            "gap": pl.Float64,
        })

    probs = model.predict_proba(feat_df)[:, 1]
    close_ts_col = feat_df.index if "close_ts" not in feat_df.columns else feat_df["close_ts"]
    # align close_ts from bars by position (feat_df rows correspond to tail of bars)
    bar_close_ts = bars_pd["close_ts"].iloc[-len(feat_df):].values

    thr_values = np.array([
        thresholds.get(str(ts)[:10], threshold_exec) for ts in bar_close_ts
    ])

    return pl.DataFrame({
        "close_ts": bar_close_ts.tolist(),
        "state_id": [state["state_id"]] * len(probs),
        "pred_prob": probs.tolist(),
        "threshold": thr_values.tolist(),
        "selected": (probs >= thr_values).tolist(),
        "gap": (thr_values - probs).tolist(),
    })


def _section_score_distribution(results: dict[str, dict[str, pl.DataFrame]]) -> list[str]:
    lines = ["## 1. Full Score Distribution", ""]
    lines += ["| Symbol | State | p25 | p50 | p75 | p90 | p95 | p99 | Threshold | n |",
              "|--------|-------|-----|-----|-----|-----|-----|-----|-----------|---|"]
    for sym, states in sorted(results.items()):
        for state_id, df in sorted(states.items()):
            if len(df) == 0:
                continue
            p = df["pred_prob"]
            thr = float(df["threshold"].mean())
            lines.append(
                f"| {sym} | {state_id} "
                f"| {p.quantile(0.25):.4f} | {p.quantile(0.50):.4f} "
                f"| {p.quantile(0.75):.4f} | {p.quantile(0.90):.4f} "
                f"| {p.quantile(0.95):.4f} | {p.quantile(0.99):.4f} "
                f"| {thr:.4f} | {len(df)} |"
            )
    lines.append("")
    return lines


def _section_near_miss(results: dict[str, dict[str, pl.DataFrame]]) -> list[str]:
    lines = ["## 2. Near-Miss Table (top 10 per symbol/state)", ""]
    for sym, states in sorted(results.items()):
        for state_id, df in sorted(states.items()):
            misses = df.filter(~pl.col("selected")).sort("gap").head(10)
            if len(misses) == 0:
                continue
            lines += [f"### {sym} / {state_id}", "",
                      "| close_ts | pred_prob | threshold | gap |",
                      "|----------|-----------|-----------|-----|"]
            for row in misses.iter_rows(named=True):
                lines.append(
                    f"| {row['close_ts']} | {row['pred_prob']:.4f} "
                    f"| {row['threshold']:.4f} | {row['gap']:.4f} |"
                )
            lines.append("")
    return lines


def _section_sensitivity_sweep(results: dict[str, dict[str, pl.DataFrame]]) -> list[str]:
    lines = ["## 3. Threshold Sensitivity Sweep", ""]
    thresholds = [0.50, 0.55, 0.60, 0.65, 0.70]
    for sym, states in sorted(results.items()):
        for state_id, df in sorted(states.items()):
            if len(df) == 0:
                continue
            lines += [f"### {sym} / {state_id}", "",
                      "| Threshold | Trades | Per 100 bars |",
                      "|-----------|--------|--------------|"]
            probs = df["pred_prob"].to_numpy()
            for thr in thresholds:
                count = int((probs >= thr).sum())
                per_100 = round(100.0 * count / len(df), 1)
                lines.append(f"| {thr:.2f} | {count} | {per_100} |")
            lines.append("")
    return lines


def _section_score_drift(results: dict[str, dict[str, pl.DataFrame]]) -> list[str]:
    lines = ["## 4. Score Drift (rolling 50-bar avg pred_prob)", ""]
    for sym, states in sorted(results.items()):
        all_probs = []
        for df in states.values():
            if len(df) > 0:
                all_probs.extend(df["pred_prob"].to_list())
        if not all_probs:
            continue
        window = 50
        rolling = [
            round(float(np.mean(all_probs[max(0, i - window):i])), 4)
            for i in range(window, len(all_probs) + 1, window)
        ]
        lines.append(f"**{sym}:** " + " → ".join(str(v) for v in rolling))
        lines.append("")
    return lines


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ticks-dir", required=True)
    parser.add_argument("--models-dir", default="models/oco")
    parser.add_argument("--governance-dir", default="configs/research/governance/oco")
    parser.add_argument("--model-month", required=True)
    parser.add_argument("--lookback-months", type=int, default=1)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    from catboost import CatBoostClassifier

    symbols = ["EURUSD", "GBPUSD", "USDJPY", "USDCHF", "AUDUSD", "USDCAD"]
    results: dict[str, dict[str, pl.DataFrame]] = {}

    for sym in symbols:
        sym_dir = Path(args.ticks_dir) / sym
        if not sym_dir.exists():
            continue
        parquet_files = sorted(sym_dir.glob(f"{sym}_*.parquet"))[-args.lookback_months:]
        if not parquet_files:
            continue

        ticks = pl.concat([pl.read_parquet(f) for f in parquet_files])
        bars = _build_bars_from_ticks(ticks)

        try:
            states = _load_states(sym, args.governance_dir)
            thresholds, threshold_exec = _load_thresholds(sym, args.models_dir, args.model_month)
            model = CatBoostClassifier()
            model.load_model(str(Path(args.models_dir) / f"{sym}_model_{args.model_month}.cbm"))
        except FileNotFoundError as e:
            print(f"Skipping {sym}: {e}")
            continue

        results[sym] = {}
        for state in states:
            scored = _score_bars(bars, sym, state, model, thresholds, threshold_exec)
            results[sym][state["state_id"]] = scored
            n_selected = int(scored["selected"].sum()) if len(scored) > 0 else 0
            print(f"  {sym}/{state['state_id']}: {len(scored)} bars scored, {n_selected} would fire")

    lines = [
        "# Live Replay Report",
        "",
        f"**Generated:** {datetime.now(tz=timezone.utc).isoformat()}  ",
        f"**Model month:** {args.model_month}  ",
        "",
    ]
    lines += _section_score_distribution(results)
    lines += _section_near_miss(results)
    lines += _section_sensitivity_sweep(results)
    lines += _section_score_drift(results)

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text("\n".join(lines))
    print(f"Report written to {args.out}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_diagnose_live_replay.py -v
```
Expected: all PASSED

- [ ] **Step 5: Commit**

```bash
git add scripts/diagnose_live_replay.py tests/test_diagnose_live_replay.py
git commit -m "feat: add diagnose_live_replay.py with offline CatBoost inference and 4-section report"
```

---

## Task 6: Full test run and smoke test against live system

- [ ] **Step 1: Run the full test suite**

```bash
pytest tests/test_state_predict_evaluations.py tests/test_diagnose_live_audit.py tests/test_diagnose_live_replay.py -v
```
Expected: all PASSED

- [ ] **Step 2: Run the audit script against the live DB**

```bash
python scripts/diagnose_live_audit.py \
    --db data/analysis/backtest_reconcile/runtime/live_state.db \
    --api http://localhost:8000 \
    --run-id jforex_live \
    --out data/analysis/live_audit_report.md
cat data/analysis/live_audit_report.md
```
Expected: markdown report with fallback note ("predict_evaluations not populated")

- [ ] **Step 3: Run the replay script against live parquet data**

```bash
python scripts/diagnose_live_replay.py \
    --ticks-dir /Users/danielfisher/Desktop/dukascopy_ticks \
    --models-dir models/oco \
    --governance-dir configs/research/governance/oco \
    --model-month 2026-02 \
    --lookback-months 1 \
    --out data/analysis/live_replay_report.md
cat data/analysis/live_replay_report.md
```
Expected: per-symbol/state score distributions, near-miss tables, sensitivity sweep

- [ ] **Step 4: Final commit**

```bash
git add data/analysis/live_audit_report.md data/analysis/live_replay_report.md
git commit -m "chore: add initial live diagnostic reports from 2026-03-25 session"
```
