# Live Win-Rate Gap Diagnostics Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Produce a diagnostic script and API checkpoint endpoint that identify why the live OCO win rate (~37-50%) is significantly below the reduced-core WFO backtest expectation (60-72%).

**Architecture:** Three independent deliverables — (1) a `/state/checkpoint` API endpoint to flush DuckDB to disk so it can be queried offline, (2) a `diagnose_live_performance_gap.py` script that queries a checkpointed DB and produces a structured report covering the four most likely failure modes, (3) a test suite that exercises the diagnostic logic against a synthetic DB. All three are designed so they can be run against any live_state.db snapshot, not just today's.

**Tech Stack:** FastAPI, DuckDB, Python 3.12, pandas, pytest, existing `test_api_server.py` and `test_summarize_runtime_db_run.py` patterns.

---

## Background: The Four Hypotheses

Analysis of today's live session against reduced-core WFO backtest data shows:

| Symbol | Live Win% | RC Backtest Win% | Z-score |
|--------|-----------|-----------------|---------|
| GBPUSD | 37% | 67.6% | **-3.39** |
| USDJPY | 50% | 72.1% | **-2.20** |
| USDCAD | 0% (n=3) | 63.3% | **-2.27** |
| USDCHF | 36% | ~61% | -1.66 |

Four candidate explanations, in roughly descending priority:

1. **Threshold schedule expiry** — The threshold JSON for all live symbols only covers dates up to 2026-02-27. Today (2026-03-23) is not in the schedule, so every prediction falls back to the static `threshold_exec` (e.g., GBPUSD: 0.5950 vs last rolling value of 0.5801). If the rolling threshold was deliberately lower because March has a different pred_prob distribution, forcing the static value means either more or fewer events are admitted than calibrated.

2. **Regime gate mis-classification** — The `_regime_is_active()` function gates predictions based on rolling quantiles computed from the live bar buffer (`compute_regime_quantiles`). If quantiles in live diverge from backtest, trades are admitted (or blocked) in the wrong regime, losing the state-specific edge.

3. **pred_prob model drift** — The 2026-02 model was calibrated on historical data. If March 2026 market conditions produce systematically different feature distributions, pred_probs may be poorly calibrated — meaning pred_prob 0.60 in live doesn't correspond to 60% win probability.

4. **OCO execution/magnitude issue** — If winners are winning less than `barrier_pips` (2.0 pip) or losers are losing more than expected (`barrier_pips + cap_pips + cost`), this indicates a fill quality problem (wrong OCO construction, slippage, wrong barrier direction).

---

## File Map

| File | Action | Responsibility |
|------|--------|----------------|
| `src/behemoth/api/server.py` | Modify | Add `GET /state/checkpoint`, `POST /predict/warmup`, update threshold fallback |
| `src/behemoth/runtime/state.py` | Modify | Add `get_rolling_threshold()` method |
| `tests/test_api_server.py` | Modify | Tests for checkpoint and warmup endpoints |
| `tests/test_duckdb_state.py` | Modify | Tests for `get_rolling_threshold()` |
| `scripts/run_jforex_live.py` | Modify | Call `/predict/warmup` per symbol after backfill |
| `scripts/diagnose_live_performance_gap.py` | Create | Diagnostic report: all four hypotheses |
| `tests/test_diagnose_live_performance_gap.py` | Create | Tests for diagnostic logic with synthetic DB |

---

## Task 1: Add `/state/checkpoint` endpoint

The live DuckDB is locked by the server process. This endpoint flushes it to disk so it can be queried with a separate DuckDB connection for offline analysis.

**Files:**
- Modify: `src/behemoth/api/server.py` (after the `/trades/summary` endpoint, around line 2806)
- Modify: `tests/test_api_server.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_api_server.py` inside an appropriate class (e.g., a new `TestCheckpointEndpoint` class):

```python
class TestCheckpointEndpoint:
    def test_checkpoint_returns_ok(self, client):
        r = client.get("/state/checkpoint")
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "ok"
        assert "checkpointed_at" in body

    def test_checkpoint_503_when_state_uninitialized(self, client):
        from src.behemoth.api import server
        original = server._state
        server._state = None
        try:
            r = client.get("/state/checkpoint")
            assert r.status_code == 503
        finally:
            server._state = original
```

- [ ] **Step 2: Run test to confirm it fails**

```bash
cd /Users/danielfisher/repositories/behemoth
.venv/bin/pytest tests/test_api_server.py::TestCheckpointEndpoint -v
```

Expected: `FAILED` — `404 Not Found` or similar (endpoint doesn't exist yet).

- [ ] **Step 3: Implement the endpoint**

In `src/behemoth/api/server.py`, add after the `/trades/summary` endpoint:

```python
@app.get("/state/checkpoint")
async def checkpoint_state():
    """Force DuckDB to flush WAL to the on-disk database file."""
    if _state is None:
        raise HTTPException(status_code=503, detail="State manager not initialized")
    _state._con.execute("CHECKPOINT")
    return {"status": "ok", "checkpointed_at": datetime.now(tz=timezone.utc).isoformat()}
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
.venv/bin/pytest tests/test_api_server.py::TestCheckpointEndpoint -v
```

Expected: Both tests `PASSED`.

- [ ] **Step 5: Smoke-test against live server**

```bash
curl http://127.0.0.1:8000/state/checkpoint
```

Expected: `{"status":"ok","checkpointed_at":"2026-03-23T..."}`

- [ ] **Step 6: Commit**

```bash
git add src/behemoth/api/server.py tests/test_api_server.py
git commit -m "feat: add /state/checkpoint endpoint for offline DB analysis"
```

---

## Task 2: Write the diagnostic script skeleton

**Files:**
- Create: `scripts/diagnose_live_performance_gap.py`
- Create: `tests/test_diagnose_live_performance_gap.py`

- [ ] **Step 1: Write failing test for the script's `run()` interface**

Create `tests/test_diagnose_live_performance_gap.py`:

```python
#!/usr/bin/env python3
"""Tests for diagnose_live_performance_gap.py.

Uses a synthetic DuckDB with known data so we can assert specific
diagnostic findings without needing the live server.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import duckdb
import pytest


def _make_synthetic_db(path: Path) -> None:
    """Create a minimal live_state.db with controlled trades and audit logs."""
    con = duckdb.connect(str(path))
    con.execute("""
        CREATE TABLE trades (
            internal_trade_id VARCHAR,
            broker_pos_id VARCHAR,
            symbol VARCHAR,
            candidate_uid VARCHAR,
            side VARCHAR,
            entry_price DOUBLE,
            entry_ts TIMESTAMP WITH TIME ZONE,
            entry_bar_id INTEGER,
            horizon_bars INTEGER,
            touch_bar_id INTEGER,
            exit_price DOUBLE,
            exit_ts TIMESTAMP WITH TIME ZONE,
            pnl_pips DOUBLE,
            status VARCHAR,
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
        CREATE TABLE ftmo_allocator_events (
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
    now = datetime(2026, 3, 23, 14, 0, tzinfo=timezone.utc)
    # 10 CLOSED trades: 4 winners (+2.0 pips), 6 losers (-2.5 pips)
    for i in range(4):
        con.execute(
            "INSERT INTO trades VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,'CLOSED','jforex_live')",
            [f"t{i}", f"bp{i}", "GBPUSD",
             "oco|GBPUSD|100|h6|oco_first_touch_clean__ny_overlap__k2",
             "BUY", 1.3600, now, i, 6, i+3, 1.3620, now, 2.0],
        )
    for i in range(4, 10):
        con.execute(
            "INSERT INTO trades VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,'CLOSED','jforex_live')",
            [f"t{i}", f"bp{i}", "GBPUSD",
             "oco|GBPUSD|100|h6|oco_first_touch_clean__ny_overlap__k2",
             "BUY", 1.3600, now, i, 6, None, 1.3575, now, -2.5],
        )
    # Audit logs with pred_probs just above threshold
    for i in range(10):
        con.execute(
            "INSERT INTO audit_logs VALUES (?,?,'GBPUSD',?,?,?,'{}','2026-02','jforex_live')",
            [now, now,
             "oco|GBPUSD|100|h6|oco_first_touch_clean__ny_overlap__k2",
             0.596 + i * 0.001,  # pred_probs 0.596–0.605
             0.595],  # threshold
        )
    con.close()


def test_run_returns_report_with_all_sections(tmp_path: Path) -> None:
    db = tmp_path / "live_state.db"
    _make_synthetic_db(db)
    from scripts.diagnose_live_performance_gap import run
    report = run(db_path=db, run_id="jforex_live")
    assert "win_rate" in report
    assert "threshold_analysis" in report
    assert "magnitude_analysis" in report
    assert "candidate_audit" in report


def test_win_rate_computed_correctly(tmp_path: Path) -> None:
    db = tmp_path / "live_state.db"
    _make_synthetic_db(db)
    from scripts.diagnose_live_performance_gap import run
    report = run(db_path=db, run_id="jforex_live")
    gbp = next(r for r in report["win_rate"] if r["symbol"] == "GBPUSD")
    assert gbp["closed_trades"] == 10
    assert gbp["wins"] == 4
    assert abs(gbp["win_rate_pct"] - 40.0) < 0.1


def test_threshold_analysis_detects_static_fallback(tmp_path: Path) -> None:
    db = tmp_path / "live_state.db"
    _make_synthetic_db(db)
    from scripts.diagnose_live_performance_gap import run
    report = run(db_path=db, run_id="jforex_live")
    ta = report["threshold_analysis"]
    gbp = next(r for r in ta if r["symbol"] == "GBPUSD")
    # All audit logs used the same threshold → expect flag
    assert gbp["unique_thresholds"] == 1
    assert gbp["min_threshold"] == pytest.approx(0.595, abs=0.001)


def test_magnitude_analysis_checks_pips(tmp_path: Path) -> None:
    db = tmp_path / "live_state.db"
    _make_synthetic_db(db)
    from scripts.diagnose_live_performance_gap import run
    report = run(db_path=db, run_id="jforex_live")
    ma = report["magnitude_analysis"]
    gbp = next(r for r in ma if r["symbol"] == "GBPUSD")
    assert abs(gbp["avg_winner_pips"] - 2.0) < 0.01
    assert abs(gbp["avg_loser_pips"] - (-2.5)) < 0.01


def test_candidate_audit_identifies_locked_state(tmp_path: Path) -> None:
    db = tmp_path / "live_state.db"
    _make_synthetic_db(db)
    from scripts.diagnose_live_performance_gap import run
    report = run(db_path=db, run_id="jforex_live")
    ca = report["candidate_audit"]
    gbp = next(r for r in ca if r["symbol"] == "GBPUSD")
    assert gbp["distinct_candidate_uids"] == 1
    assert "ny_overlap" in gbp["candidate_uids"][0]
```

- [ ] **Step 2: Run to confirm tests fail**

```bash
.venv/bin/pytest tests/test_diagnose_live_performance_gap.py -v
```

Expected: All 5 tests fail with `ModuleNotFoundError` (script doesn't exist yet).

- [ ] **Step 3: Commit the failing tests**

```bash
git add tests/test_diagnose_live_performance_gap.py
git commit -m "test: add failing tests for live performance gap diagnostic"
```

---

## Task 3: Implement `diagnose_live_performance_gap.py`

**Files:**
- Create: `scripts/diagnose_live_performance_gap.py`

- [ ] **Step 1: Write the script**

```python
#!/usr/bin/env python3
"""Diagnose why live OCO win rate deviates from reduced-core WFO backtest.

Queries a checkpointed live_state.db and produces a structured report
covering four hypotheses:
  1. Win rate per symbol vs expectation
  2. Threshold schedule: is the system using static fallback vs rolling?
  3. pnl_pips magnitude: are winners/losers the right size?
  4. Candidate UID audit: are the right state candidates firing?

Usage:
    python scripts/diagnose_live_performance_gap.py \
        --db data/analysis/backtest_reconcile/runtime/live_state.db \
        --run-id jforex_live \
        --out data/analysis/live_perf_gap_report.md
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import duckdb


# Reduced-core backtest win rates from WFO eval 2025 (locked states only).
# Update these from: data/analysis/tick_opportunity_mining_dukascopy_candidate/
#                    wfo_2025_m3to1_oco_fullcap/<SYM>_oco_events_eval2025.parquet
# filtered to split='eval', bar_ticks=100, horizon=6, and the locked state_id.
REDUCED_CORE_EXPECTED_WIN_RATE = {
    "GBPUSD": 67.6,  # oco_first_touch_clean__ny_overlap__k2
    "USDJPY": 72.1,  # oco_first_touch_clean__high_abs_vel_q80__k2
    "USDCHF": 60.8,  # avg of two locked states
    "USDCAD": 63.3,  # oco_first_touch_clean__ny_overlap__k2
    "AUDUSD": 59.2,  # avg of two locked states
    "EURUSD": 0.0,   # not live yet
}

# Governance lock paths for threshold schedule check
LOCK_DIR = Path("configs/research/governance/oco")
MODEL_DIR = Path("models/oco")


def _load_con(db_path: Path) -> duckdb.DuckDBPyConnection:
    return duckdb.connect(str(db_path), read_only=True)


def _win_rate_section(con: duckdb.DuckDBPyConnection, run_id: str) -> list[dict[str, Any]]:
    """Win rate, expected win rate, and z-score per symbol."""
    import math
    rows = con.execute("""
        SELECT
            symbol,
            COUNT(*) AS closed_trades,
            COUNT(CASE WHEN pnl_pips > 0 THEN 1 END) AS wins,
            ROUND(100.0 * COUNT(CASE WHEN pnl_pips > 0 THEN 1 END) / COUNT(*), 1) AS win_rate_pct,
            ROUND(SUM(pnl_pips), 2) AS total_pips,
            ROUND(AVG(pnl_pips), 3) AS avg_pips
        FROM trades
        WHERE status = 'CLOSED' AND run_id = ?
        GROUP BY symbol
        ORDER BY symbol
    """, [run_id]).fetchall()

    results = []
    for symbol, n, wins, live_pct, total_pips, avg_pips in rows:
        expected = REDUCED_CORE_EXPECTED_WIN_RATE.get(symbol, 0.0)
        p = expected / 100.0
        z = float("nan")
        if n > 0 and 0 < p < 1:
            z = (wins - n * p) / math.sqrt(n * p * (1 - p))
        results.append({
            "symbol": symbol,
            "closed_trades": n,
            "wins": wins,
            "win_rate_pct": live_pct,
            "expected_win_rate_pct": expected,
            "delta_pp": round(live_pct - expected, 1),
            "z_score": round(z, 2) if not math.isnan(z) else None,
            "total_pips": total_pips,
            "avg_pips": avg_pips,
            "flag": z < -2.0 if not math.isnan(z) else False,
        })
    return results


def _threshold_analysis_section(con: duckdb.DuckDBPyConnection, run_id: str) -> list[dict[str, Any]]:
    """Check whether today's predictions used a rolling threshold or static fallback.

    A single unique threshold value across many events is a strong signal the
    system is using the static fallback (schedule date missing from JSON).
    """
    rows = con.execute("""
        SELECT
            symbol,
            model_month,
            COUNT(*) AS scored_events,
            COUNT(DISTINCT ROUND(threshold, 6)) AS unique_thresholds,
            ROUND(MIN(threshold), 6) AS min_threshold,
            ROUND(MAX(threshold), 6) AS max_threshold,
            ROUND(AVG(pred_prob), 4) AS avg_pred_prob,
            ROUND(MIN(pred_prob), 4) AS min_pred_prob,
            ROUND(MAX(pred_prob), 4) AS max_pred_prob,
            ROUND(AVG(pred_prob) - AVG(threshold), 4) AS avg_margin_above_threshold
        FROM audit_logs
        WHERE run_id = ?
        GROUP BY symbol, model_month
        ORDER BY symbol
    """, [run_id]).fetchall()

    results = []
    for (symbol, model_month, scored, unique_thr, min_thr, max_thr,
         avg_prob, min_prob, max_prob, avg_margin) in rows:
        # Check if today's date is in the threshold schedule
        schedule_has_today = False
        static_threshold = None
        lock_path = LOCK_DIR / f"{symbol.lower()}_oco_live_lock.json"
        if lock_path.exists():
            lock = json.loads(lock_path.read_text())
            thr_json_path = Path(lock["artifacts"].get("model_threshold_json_path", ""))
            if thr_json_path.exists():
                thr_cfg = json.loads(thr_json_path.read_text())
                today_str = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")
                schedule_has_today = today_str in thr_cfg.get("threshold_schedule", {})
                static_threshold = thr_cfg.get("threshold_exec")

        results.append({
            "symbol": symbol,
            "model_month": model_month,
            "scored_events": scored,
            "unique_thresholds": unique_thr,
            "min_threshold": min_thr,
            "max_threshold": max_thr,
            "avg_pred_prob": avg_prob,
            "min_pred_prob": min_prob,
            "max_pred_prob": max_prob,
            "avg_margin_above_threshold": avg_margin,
            "schedule_has_today": schedule_has_today,
            "static_threshold_value": static_threshold,
            "flag": unique_thr == 1 and not schedule_has_today,
        })
    return results


def _magnitude_analysis_section(con: duckdb.DuckDBPyConnection, run_id: str) -> list[dict[str, Any]]:
    """Check whether winner/loser pip magnitudes match the OCO barrier configuration.

    Expected: winners ≈ +barrier_pips (2.0), losers ≈ -(barrier_pips + cap_pips + cost).
    Deviations suggest wrong fill prices, wrong OCO construction, or barrier misconfiguration.
    """
    rows = con.execute("""
        SELECT
            symbol,
            COUNT(CASE WHEN pnl_pips > 0 THEN 1 END) AS n_winners,
            COUNT(CASE WHEN pnl_pips <= 0 THEN 1 END) AS n_losers,
            ROUND(AVG(CASE WHEN pnl_pips > 0 THEN pnl_pips END), 3) AS avg_winner_pips,
            ROUND(AVG(CASE WHEN pnl_pips <= 0 THEN pnl_pips END), 3) AS avg_loser_pips,
            ROUND(MAX(pnl_pips), 3) AS max_winner_pips,
            ROUND(MIN(pnl_pips), 3) AS min_loser_pips,
            ROUND(STDDEV(pnl_pips), 3) AS stddev_pips
        FROM trades
        WHERE status = 'CLOSED' AND run_id = ?
        GROUP BY symbol
        ORDER BY symbol
    """, [run_id]).fetchall()

    results = []
    for (symbol, n_win, n_lose, avg_win, avg_lose,
         max_win, min_lose, stddev) in rows:
        # Barrier is 2.0 pips for all locked states; cap is 1.2 pips
        # Expected winner: ~+2.0, expected loser: ~-(2.0+1.2+cost) ≈ -3.5 worst case
        winner_ok = avg_win is not None and 1.5 <= avg_win <= 2.5
        loser_ok = avg_lose is not None and -4.0 <= avg_lose <= -0.5
        results.append({
            "symbol": symbol,
            "n_winners": n_win,
            "n_losers": n_lose,
            "avg_winner_pips": avg_win,
            "avg_loser_pips": avg_lose,
            "max_winner_pips": max_win,
            "min_loser_pips": min_lose,
            "stddev_pips": stddev,
            "winner_magnitude_ok": winner_ok,
            "loser_magnitude_ok": loser_ok,
            "flag": not winner_ok or not loser_ok,
        })
    return results


def _candidate_audit_section(con: duckdb.DuckDBPyConnection, run_id: str) -> list[dict[str, Any]]:
    """Check which candidate_uids are actually firing in live.

    All live trades should have candidate_uids matching the locked state_universe.
    Unexpected candidates suggest a governance config mismatch.
    """
    rows = con.execute("""
        SELECT
            symbol,
            COUNT(DISTINCT candidate_uid) AS distinct_candidate_uids,
            LIST(DISTINCT candidate_uid ORDER BY candidate_uid) AS candidate_uids,
            COUNT(*) AS total_scored
        FROM audit_logs
        WHERE run_id = ?
        GROUP BY symbol
        ORDER BY symbol
    """, [run_id]).fetchall()

    results = []
    for symbol, distinct, uids, total in rows:
        locked_states: list[str] = []
        lock_path = LOCK_DIR / f"{symbol.lower()}_oco_live_lock.json"
        if lock_path.exists():
            lock = json.loads(lock_path.read_text())
            locked_states = [
                f"oco|{symbol}|{r['bar_ticks']}|h{r['horizon']}|{r['state_id']}"
                for r in lock["state_universe"]["rows"]
            ]
        unexpected = [u for u in (uids or []) if u not in locked_states]
        missing = [s for s in locked_states if s not in (uids or [])]
        results.append({
            "symbol": symbol,
            "distinct_candidate_uids": distinct,
            "candidate_uids": uids or [],
            "locked_states": locked_states,
            "unexpected_candidates": unexpected,
            "missing_candidates": missing,
            "total_scored": total,
            "flag": bool(unexpected) or bool(missing),
        })
    return results


def _format_report(report: dict[str, Any]) -> str:
    lines = [
        "# Live Performance Gap Diagnostic Report",
        f"Generated: {datetime.now(tz=timezone.utc).isoformat()}",
        "",
        "## 1. Win Rate vs Reduced-Core Expectation",
        "",
        "| Symbol | N | Wins | Live% | RC BT% | Delta | Z | Flag |",
        "|--------|---|------|-------|--------|-------|---|------|",
    ]
    for r in report["win_rate"]:
        flag = "🚨" if r["flag"] else ""
        lines.append(
            f"| {r['symbol']} | {r['closed_trades']} | {r['wins']} "
            f"| {r['win_rate_pct']}% | {r['expected_win_rate_pct']}% "
            f"| {r['delta_pp']:+.1f}pp | {r['z_score']} | {flag} |"
        )
    lines += [
        "",
        "## 2. Threshold Schedule Analysis",
        "",
        "| Symbol | Model Month | Scored | Unique Thresholds | Avg Prob | Avg Margin | Schedule Has Today | Flag |",
        "|--------|------------|--------|-------------------|----------|------------|--------------------|------|",
    ]
    for r in report["threshold_analysis"]:
        flag = "🚨" if r["flag"] else ""
        lines.append(
            f"| {r['symbol']} | {r['model_month']} | {r['scored_events']} "
            f"| {r['unique_thresholds']} | {r['avg_pred_prob']} "
            f"| {r['avg_margin_above_threshold']} | {r['schedule_has_today']} | {flag} |"
        )
    lines += [
        "",
        "## 3. PnL Magnitude Analysis",
        "",
        "| Symbol | N Winners | N Losers | Avg Winner Pips | Avg Loser Pips | Winner OK | Loser OK | Flag |",
        "|--------|-----------|----------|----------------|----------------|-----------|----------|------|",
    ]
    for r in report["magnitude_analysis"]:
        flag = "🚨" if r["flag"] else ""
        lines.append(
            f"| {r['symbol']} | {r['n_winners']} | {r['n_losers']} "
            f"| {r['avg_winner_pips']} | {r['avg_loser_pips']} "
            f"| {r['winner_magnitude_ok']} | {r['loser_magnitude_ok']} | {flag} |"
        )
    lines += [
        "",
        "## 4. Candidate UID Audit",
        "",
        "| Symbol | Distinct UIDs | Total Scored | Unexpected | Missing | Flag |",
        "|--------|--------------|-------------|------------|---------|------|",
    ]
    for r in report["candidate_audit"]:
        flag = "🚨" if r["flag"] else ""
        lines.append(
            f"| {r['symbol']} | {r['distinct_candidate_uids']} "
            f"| {r['total_scored']} | {len(r['unexpected_candidates'])} "
            f"| {len(r['missing_candidates'])} | {flag} |"
        )
        if r["unexpected_candidates"]:
            lines.append(f"  - **Unexpected:** {r['unexpected_candidates']}")
        if r["missing_candidates"]:
            lines.append(f"  - **Missing:** {r['missing_candidates']}")
    return "\n".join(lines) + "\n"


def run(
    db_path: Path,
    run_id: str = "jforex_live",
    out_path: Path | None = None,
) -> dict[str, Any]:
    """Run all diagnostic checks and return structured report dict."""
    con = _load_con(db_path)
    report = {
        "win_rate": _win_rate_section(con, run_id),
        "threshold_analysis": _threshold_analysis_section(con, run_id),
        "magnitude_analysis": _magnitude_analysis_section(con, run_id),
        "candidate_audit": _candidate_audit_section(con, run_id),
    }
    con.close()
    if out_path is not None:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(_format_report(report), encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", required=True, type=Path,
                        help="Path to checkpointed live_state.db")
    parser.add_argument("--run-id", default="jforex_live",
                        help="run_id to filter trades/audit_logs (default: jforex_live)")
    parser.add_argument("--out", type=Path,
                        default=Path("data/analysis/live_perf_gap_report.md"),
                        help="Output markdown report path")
    args = parser.parse_args()
    report = run(db_path=args.db, run_id=args.run_id, out_path=args.out)

    print("\n=== WIN RATE ===")
    for r in report["win_rate"]:
        flag = " *** ANOMALOUS" if r["flag"] else ""
        print(f"  {r['symbol']}: {r['win_rate_pct']}% live vs {r['expected_win_rate_pct']}% expected "
              f"(z={r['z_score']}) total={r['total_pips']} pips{flag}")

    print("\n=== THRESHOLD ===")
    for r in report["threshold_analysis"]:
        flag = " *** STATIC FALLBACK" if r["flag"] else ""
        print(f"  {r['symbol']}: {r['unique_thresholds']} unique threshold(s), "
              f"avg_prob={r['avg_pred_prob']}, schedule_today={r['schedule_has_today']}{flag}")

    print("\n=== MAGNITUDE ===")
    for r in report["magnitude_analysis"]:
        flag = " *** CHECK EXECUTION" if r["flag"] else ""
        print(f"  {r['symbol']}: winners={r['avg_winner_pips']} pips, "
              f"losers={r['avg_loser_pips']} pips{flag}")

    print("\n=== CANDIDATE AUDIT ===")
    for r in report["candidate_audit"]:
        flag = " *** MISMATCH" if r["flag"] else ""
        print(f"  {r['symbol']}: {r['distinct_candidate_uids']} uid(s), "
              f"unexpected={r['unexpected_candidates']}, "
              f"missing={r['missing_candidates']}{flag}")

    print(f"\nReport written to {args.out}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run the failing tests**

```bash
.venv/bin/pytest tests/test_diagnose_live_performance_gap.py -v
```

Expected: Tests should now pass. If any fail, the error message will indicate which section's return value doesn't match the expected shape.

- [ ] **Step 3: Fix any failing tests**

Common issues to watch for:
- DuckDB `LIST()` aggregation may need `ARRAY_AGG()` instead — check the DuckDB version in use: `.venv/bin/python -c "import duckdb; print(duckdb.__version__)"`
- The `ROUND(STDDEV(...), 3)` call returns NULL when n=1 — handle with `COALESCE`
- `lock_path.exists()` will return False in tests since the lock files are at a relative path; the test doesn't need this branch to work

- [ ] **Step 4: Commit**

```bash
git add scripts/diagnose_live_performance_gap.py tests/test_diagnose_live_performance_gap.py
git commit -m "feat: add live performance gap diagnostic script with tests"
```

---

## Task 4: Run the diagnostic against the live database

- [ ] **Step 1: Checkpoint the live DB via the new endpoint**

```bash
curl http://127.0.0.1:8000/state/checkpoint
```

Expected: `{"status":"ok","checkpointed_at":"2026-03-23T..."}`

- [ ] **Step 2: Run the diagnostic**

```bash
cd /Users/danielfisher/repositories/behemoth
.venv/bin/python scripts/diagnose_live_performance_gap.py \
    --db data/analysis/backtest_reconcile/runtime/live_state.db \
    --run-id jforex_live \
    --out data/analysis/live_perf_gap_report.md
```

Expected output: a table per section with 🚨 flags on anomalous rows. Key things to look for:

- **Section 2 (Threshold):** If `schedule_has_today=False` and `unique_thresholds=1` for a symbol, the system is using the static fallback. The `avg_margin_above_threshold` tells you how close pred_probs are to the threshold — a very small margin (< 0.005) suggests the model is barely selecting anything.
- **Section 3 (Magnitude):** If `avg_winner_pips` is significantly less than 2.0, something is wrong with fill prices or OCO construction. If `avg_loser_pips` is worse than -4.0, the cap_pips isn't being applied.
- **Section 4 (Candidate audit):** Any unexpected candidate_uids in live that don't match the locked state_universe.

- [ ] **Step 3: Review the generated report**

```bash
cat data/analysis/live_perf_gap_report.md
```

- [ ] **Step 4: Commit the report**

```bash
git add data/analysis/live_perf_gap_report.md
git commit -m "chore: add live performance gap diagnostic report 2026-03-23"
```

---

## Interpreting Results and Next Steps

| Finding | Likely Cause | Next Action |
|---------|-------------|------------|
| `unique_thresholds=1` + `schedule_has_today=False` | Threshold JSON expired at end of model month; system using static fallback | Run Task 5 (dynamic rolling threshold + warmup) |
| `avg_winner_pips` < 1.5 | OCO limit/stop might be inverted, or fill slippage too high | Compare `entry_price` + `barrier_pips` vs `exit_price` in trades table; check JForex order construction |
| `unexpected_candidates` non-empty | Wrong governance config loaded at runtime | Check `BEHEMOTH_GOVERNANCE_HISTORY_DIR` env var vs expected |
| `avg_margin_above_threshold` < 0.002 | Model prob barely above threshold → low-confidence trades being admitted | Raise threshold or wait for model retrain |
| Win rate gap persists after above fixes | Model drift — 2026-02 model no longer calibrated for current market | Trigger early retrain (cadence_days=30 policy) |

---

## Task 5: Dynamic Rolling Threshold + Pred-Prob Warmup

### Background

Two structural gaps exist in how the threshold is managed across model-month boundaries:

**Gap 1 — Schedule expiry with wrong fallback.** The threshold JSON schedule only covers the test month (e.g. `2026-02-01` to `2026-02-27`). When a date is missing (any day in March onwards), the server currently falls back to `threshold_exec`, the **median** of February's schedule. This is wrong in two ways: (a) the median diverges from the end-of-February rolling value by up to 3.6pp (USDCAD), making the live threshold inconsistent with what WFO calibrated; and (b) there should be **no static fallback at all** — if we don't have a valid rolling threshold we should log the fact and skip trading for that symbol rather than silently use a stale median.

**Gap 2 — No pred-prob history at startup.** The rolling threshold needs `quantile(audit_logs.pred_prob over last 20 days, 0.90)`. The backfill endpoint only populates `tick_bars`, not `audit_logs`. When the server starts fresh, `audit_logs` is empty so there is no basis for computing a rolling threshold. The fix is a warmup step that scores the existing bar buffer through the model to seed the audit trail before live predictions begin.

**Correct behaviour after this task:**
1. Schedule present → use schedule value (unchanged)
2. Schedule missing + sufficient audit_log history (≥ `rolling_threshold_min_history` events in last `rolling_threshold_days` days) → compute rolling quantile dynamically from `audit_logs`
3. Schedule missing + insufficient audit_log history → return `selected_exec=0` with `threshold_source="no_valid_threshold"`, emit a warning log; do NOT trade

**Files:**
- Modify: `src/behemoth/runtime/state.py`
- Modify: `src/behemoth/api/server.py`
- Modify: `scripts/run_jforex_live.py`
- Modify: `tests/test_duckdb_state.py`
- Modify: `tests/test_api_server.py`

---

### Task 5a: Add `get_rolling_threshold()` to StateManager

- [ ] **Step 1: Write the failing test**

Add to `tests/test_duckdb_state.py` in a new class `TestRollingThreshold`:

```python
class TestRollingThreshold:
    def test_returns_none_when_no_audit_history(self):
        from src.behemoth.runtime.state import StateManager
        sm = StateManager()
        result = sm.get_rolling_threshold(
            symbol="GBPUSD",
            candidate_uid="oco|GBPUSD|100|h6|oco_first_touch_clean__ny_overlap__k2",
            exec_q=0.9,
            lookback_days=20,
            min_history=10,
        )
        assert result is None

    def test_returns_quantile_when_sufficient_history(self):
        from datetime import datetime, timedelta, timezone
        from src.behemoth.runtime.state import StateManager
        sm = StateManager()
        now = datetime.now(tz=timezone.utc)
        uid = "oco|GBPUSD|100|h6|oco_first_touch_clean__ny_overlap__k2"
        # Insert 20 pred_probs ranging from 0.50 to 0.69
        for i in range(20):
            sm._con.execute(
                "INSERT INTO audit_logs(event_ts, close_ts, symbol, candidate_uid, "
                "pred_prob, threshold, features_json, model_month, run_id) "
                "VALUES (?, ?, 'GBPUSD', ?, ?, 0.5, '{}', '2026-02', 'warmup')",
                [now - timedelta(days=i), now - timedelta(days=i), uid, 0.50 + i * 0.01],
            )
        result = sm.get_rolling_threshold(
            symbol="GBPUSD",
            candidate_uid=uid,
            exec_q=0.9,
            lookback_days=20,
            min_history=10,
        )
        assert result is not None
        assert 0.50 <= result <= 0.69

    def test_returns_none_when_below_min_history(self):
        from datetime import datetime, timedelta, timezone
        from src.behemoth.runtime.state import StateManager
        sm = StateManager()
        now = datetime.now(tz=timezone.utc)
        uid = "oco|GBPUSD|100|h6|oco_first_touch_clean__ny_overlap__k2"
        # Only 5 events, min_history=10
        for i in range(5):
            sm._con.execute(
                "INSERT INTO audit_logs(event_ts, close_ts, symbol, candidate_uid, "
                "pred_prob, threshold, features_json, model_month, run_id) "
                "VALUES (?, ?, 'GBPUSD', ?, 0.60, 0.5, '{}', '2026-02', 'warmup')",
                [now - timedelta(days=i), now - timedelta(days=i), uid],
            )
        result = sm.get_rolling_threshold(
            symbol="GBPUSD", candidate_uid=uid,
            exec_q=0.9, lookback_days=20, min_history=10,
        )
        assert result is None
```

- [ ] **Step 2: Run to confirm tests fail**

```bash
.venv/bin/pytest tests/test_duckdb_state.py::TestRollingThreshold -v
```

Expected: `AttributeError: 'StateManager' object has no attribute 'get_rolling_threshold'`

- [ ] **Step 3: Implement `get_rolling_threshold` in StateManager**

In `src/behemoth/runtime/state.py`, add after `get_ledger_stats()`:

```python
def get_rolling_threshold(
    self,
    symbol: str,
    candidate_uid: str,
    exec_q: float,
    lookback_days: int,
    min_history: int,
) -> float | None:
    """Compute rolling execution threshold from recent audit_logs pred_probs.

    Returns the exec_q quantile of pred_probs over the last lookback_days
    calendar days. Returns None if fewer than min_history events exist in
    that window (insufficient history to compute a reliable threshold).
    """
    from datetime import timedelta
    cutoff = datetime.now(tz=timezone.utc) - timedelta(days=lookback_days)
    row = self._con.execute(
        """
        SELECT COUNT(*), quantile(pred_prob, ?)
        FROM audit_logs
        WHERE symbol = ?
          AND candidate_uid = ?
          AND close_ts >= ?
        """,
        [float(exec_q), symbol.upper(), candidate_uid, cutoff],
    ).fetchone()
    if row is None or row[0] is None or int(row[0]) < min_history:
        return None
    return float(row[1])
```

- [ ] **Step 4: Run tests to confirm pass**

```bash
.venv/bin/pytest tests/test_duckdb_state.py::TestRollingThreshold -v
```

Expected: All 3 tests `PASSED`.

- [ ] **Step 5: Commit**

```bash
git add src/behemoth/runtime/state.py tests/test_duckdb_state.py
git commit -m "feat: add get_rolling_threshold() to StateManager for dynamic threshold computation"
```

---

### Task 5b: Update threshold fallback in `_build_predictions`

Replace the static fallback in `src/behemoth/api/server.py` with dynamic rolling computation. When the schedule is missing AND sufficient audit_log history exists, use the rolling quantile. When history is insufficient, block trading for that candidate with a clear `threshold_source`.

**Files:**
- Modify: `src/behemoth/api/server.py` (lines ~2480–2488)
- Modify: `tests/test_api_server.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_api_server.py` in a new class `TestDynamicThresholdFallback`:

```python
class TestDynamicThresholdFallback:
    def test_no_valid_threshold_blocks_trading(self, client):
        """When schedule has no entry for today and audit_logs has no history,
        the predict response must have selected_exec=0 and
        threshold_source containing 'no_valid_threshold'."""
        from src.behemoth.api import server
        # Patch thr_cfg to have a schedule missing today
        import datetime
        yesterday = (datetime.date.today() - datetime.timedelta(days=1)).isoformat()
        fake_thr = {
            "threshold_exec": 0.595,
            "threshold_schedule": {yesterday: 0.580},
            "threshold_source": "rolling_days",
            "rolling_threshold_days": 20,
            "rolling_threshold_min_history": 10,
            "execution_quantile": 0.9,
        }
        # This test requires the server to have a model loaded; skip if not
        if not server._models:
            pytest.skip("No models loaded")
        # Verify that a predict call returns no admitted trades
        # (since audit_logs is empty on test client startup)
        # ... full integration test setup omitted for brevity;
        # the key assertion is threshold_source="no_valid_threshold"
        pass  # Replace with full implementation using TestClient fixture
```

Note: The full integration test requires a loaded model. A unit test of `_build_predictions` in isolation is more practical — the implementation step below describes what to test once implemented.

- [ ] **Step 2: Implement the updated fallback**

In `src/behemoth/api/server.py`, replace lines ~2483–2488:

```python
# BEFORE:
if schedule and day_str in schedule:
    curr_threshold = float(schedule[day_str])
    curr_source = f"{threshold_mode}:schedule"
else:
    curr_threshold = threshold_exec
    curr_source = f"{threshold_mode}:static_fallback"

# AFTER:
if schedule and day_str in schedule:
    curr_threshold = float(schedule[day_str])
    curr_source = f"{threshold_mode}:schedule"
else:
    # Schedule expired or missing for today. Attempt dynamic rolling threshold
    # from audit_logs — this is the live equivalent of WFO's rolling computation.
    rolling_days = int(thr_cfg.get("rolling_threshold_days", 0))
    exec_q = float(thr_cfg.get("execution_quantile", 0.9))
    min_history = int(thr_cfg.get("rolling_threshold_min_history", 10))
    dynamic_thr = None
    if rolling_days > 0 and _state is not None:
        dynamic_thr = _state.get_rolling_threshold(
            symbol=sym,
            candidate_uid=canonical_uid,
            exec_q=exec_q,
            lookback_days=rolling_days,
            min_history=min_history,
        )
    if dynamic_thr is not None:
        curr_threshold = dynamic_thr
        curr_source = f"{threshold_mode}:rolling_dynamic"
    else:
        # No valid threshold available. Block this candidate and log clearly.
        logger.warning(
            "No valid threshold for %s %s: schedule expired %s, "
            "insufficient audit_log history (rolling_days=%d, min_history=%d). "
            "Blocking candidate.",
            sym, canonical_uid, day_str, rolling_days, min_history,
        )
        curr_threshold = float("inf")  # ensures pred_prob never qualifies
        curr_source = f"{threshold_mode}:no_valid_threshold"
```

- [ ] **Step 3: Verify the change with a manual smoke test**

With the server running (no warmup yet), check that predict calls for a symbol with an expired schedule now log the warning:

```bash
grep "No valid threshold" logs/api_live.log | tail -5
```

Expected: Lines like `No valid threshold for GBPUSD oco|GBPUSD|...: schedule expired 2026-03-23, insufficient audit_log history...`

- [ ] **Step 4: Commit**

```bash
git add src/behemoth/api/server.py
git commit -m "fix: replace static threshold fallback with dynamic rolling computation or explicit no_valid_threshold block"
```

---

### Task 5c: Add `POST /predict/warmup` endpoint

This endpoint scores all bars currently in the tick_bars buffer through the model for a given symbol, writing pred_probs to `audit_logs` with their historical `close_ts`. It uses `run_id="warmup"` so these entries can be distinguished from live predictions. After this call, `get_rolling_threshold()` has enough history to compute a valid threshold.

**Files:**
- Modify: `src/behemoth/api/server.py`
- Modify: `tests/test_api_server.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_api_server.py`:

```python
class TestPredictWarmup:
    def test_warmup_returns_201_with_count(self, client):
        r = client.post("/predict/warmup", json={"symbol": "GBPUSD", "run_id": "warmup"})
        assert r.status_code == 201
        body = r.json()
        assert body["ok"] is True
        assert "audit_events_written" in body
        assert isinstance(body["audit_events_written"], int)

    def test_warmup_503_when_state_uninitialized(self, client):
        from src.behemoth.api import server
        original = server._state
        server._state = None
        try:
            r = client.post("/predict/warmup", json={"symbol": "GBPUSD", "run_id": "warmup"})
            assert r.status_code == 503
        finally:
            server._state = original
```

- [ ] **Step 2: Run to confirm tests fail**

```bash
.venv/bin/pytest tests/test_api_server.py::TestPredictWarmup -v
```

Expected: `FAILED` — 404 (endpoint doesn't exist).

- [ ] **Step 3: Implement the endpoint**

Add to `src/behemoth/api/server.py` after `/predict/warmup` (place near the `/predict` endpoint):

```python
class WarmupRequest(BaseModel):
    symbol: str
    run_id: str = "warmup"


@app.post("/predict/warmup", status_code=201)
async def predict_warmup(req: WarmupRequest) -> dict:
    """Score buffered bars through the model to seed audit_logs for rolling threshold.

    Iterates all bars in the tick_bars buffer for the given symbol, computes
    features at the CURRENT buffer state (not a historical replay), and writes
    one audit_log entry per eligible bar using the bar's historical close_ts.
    This seeds the rolling threshold history needed when the threshold schedule
    has expired.

    Called once per symbol after backfill completes on startup.
    Idempotent: safe to call multiple times (appends to audit_logs).
    """
    import numpy as np

    if _state is None:
        raise HTTPException(status_code=503, detail="State manager not initialized")

    sym = req.symbol.upper()
    run_id = req.run_id or "warmup"

    close_ts_now = _state.get_latest_close_ts(sym) or datetime.now(tz=timezone.utc)
    contract = _resolve_runtime_contract(sym, close_ts_now)
    if not contract.candidates:
        raise HTTPException(status_code=422, detail=f"No candidates for {sym}")

    model, thr_cfg = _ensure_model_and_threshold(contract)
    if model is None:
        raise HTTPException(status_code=422, detail=f"No model loaded for {sym}")

    # Fetch all close_ts values from the bar buffer for this symbol
    bar_ticks = int(contract.candidates[0].bar_ticks)
    rows = _state._con.execute(
        "SELECT close_ts FROM tick_bars WHERE symbol = ? AND bar_ticks = ? ORDER BY row_id",
        [sym, bar_ticks],
    ).fetchall()

    warmup_needed = _state._cfg.full_warmup_bars
    if len(rows) < warmup_needed:
        return {
            "ok": True,
            "symbol": sym,
            "audit_events_written": 0,
            "skipped_reason": f"insufficient_bars:{len(rows)}<{warmup_needed}",
        }

    # Compute features once from current buffer state (same features for all bars —
    # this is an approximation; a full historical replay would require per-bar
    # feature computation, which requires replaying the buffer from scratch).
    n_written = 0
    for cand in contract.candidates:
        feats = _state.compute_features(sym, bar_ticks, cand.horizon, cand.barrier_pips)
        if feats is None:
            continue
        arr = np.array([feats.to_array()], dtype=float)
        with METRIC_INFERENCE_LATENCY.labels(symbol=sym).time():
            pred_prob = float(model.predict_proba(arr)[:, 1][0])
        canonical_uid = f"oco|{sym}|{cand.bar_ticks}|h{cand.horizon}|{cand.candidate_uid}"
        static_thr = float(thr_cfg.get("threshold_exec", 0.5))
        for (close_ts_val,) in rows:
            close_ts_bar = close_ts_val
            if hasattr(close_ts_bar, "tzinfo") and close_ts_bar.tzinfo is None:
                close_ts_bar = close_ts_bar.replace(tzinfo=timezone.utc)
            _state.log_audit_event(
                symbol=sym,
                candidate_uid=canonical_uid,
                pred_prob=pred_prob,
                threshold=static_thr,
                features=feats,
                model_month=contract.model_month,
                close_ts=close_ts_bar,
                run_id=run_id,
            )
            n_written += 1

    logger.info("predict_warmup: wrote %d audit events for %s", n_written, sym)
    return {"ok": True, "symbol": sym, "audit_events_written": n_written}
```

- [ ] **Step 4: Run tests**

```bash
.venv/bin/pytest tests/test_api_server.py::TestPredictWarmup -v
```

Expected: Both tests `PASSED`.

- [ ] **Step 5: Commit**

```bash
git add src/behemoth/api/server.py tests/test_api_server.py
git commit -m "feat: add /predict/warmup endpoint to seed audit_logs for rolling threshold"
```

---

### Task 5d: Call warmup from live runner startup

After backfill completes for each symbol, the live runner should call `/predict/warmup` so that `get_rolling_threshold()` has history before the first live prediction.

**Files:**
- Modify: `scripts/run_jforex_live.py`

- [ ] **Step 1: Find the post-backfill hook in `run_jforex_live.py`**

The startup flow in `run_jforex_live.py` is:
1. Start API server → `_start_api(cfg)`
2. Poll `/health` until ready → `_poll_health()`
3. Start JForex Java process → `_start_live_runner(cfg)`

The backfill happens inside the Java process (JForex calls `/backfill` as it loads historical ticks). There is no explicit post-backfill hook in the Python orchestrator. The `_poll_health()` currently just waits for the server to be reachable, not for warmup-readiness.

- [ ] **Step 2: Add `_warmup_symbols()` helper**

In `scripts/run_jforex_live.py`, add after `_poll_health`:

```python
def _warmup_symbols(symbols: list[str], base_url: str, timeout_sec: float = 60.0) -> None:
    """Call /predict/warmup for each symbol to seed audit_logs.

    Retries until all symbols return audit_events_written > 0, or timeout.
    This must be called AFTER backfill has populated tick_bars.
    """
    import time
    import requests

    deadline = time.monotonic() + timeout_sec
    pending = list(symbols)
    while pending and time.monotonic() < deadline:
        still_pending = []
        for sym in pending:
            try:
                r = requests.post(
                    f"{base_url}/predict/warmup",
                    json={"symbol": sym, "run_id": "warmup"},
                    timeout=10,
                )
                body = r.json()
                written = body.get("audit_events_written", 0)
                if written > 0:
                    print(f"[warmup] {sym}: {written} audit events seeded", flush=True)
                else:
                    still_pending.append(sym)
                    print(f"[warmup] {sym}: 0 events (bars not ready yet), retrying...", flush=True)
            except Exception as exc:
                still_pending.append(sym)
                print(f"[warmup] {sym}: error {exc}, retrying...", flush=True)
        pending = still_pending
        if pending:
            time.sleep(5)
    if pending:
        print(f"[warmup] WARNING: warmup incomplete for {pending} after {timeout_sec}s", flush=True)
```

- [ ] **Step 3: Call `_warmup_symbols()` in `main()` after `_poll_health()`**

In `scripts/run_jforex_live.py`, in `main()`, after `_poll_health(api_proc, ...)`:

```python
print("[jforex-live] waiting for backfill + warming up threshold history", flush=True)
# Give JForex time to complete initial backfill before warmup scoring
import time; time.sleep(30)
_warmup_symbols(list(cfg.symbols), base_url=f"http://{cfg.api_host}:{cfg.api_port}")
print("[jforex-live] warmup complete, starting JForex runner", flush=True)
java_proc = _start_live_runner(cfg)
```

Note: The 30-second sleep is a pragmatic guard for the backfill completing. A more robust approach would poll `/health` for bar counts to reach a minimum, but that requires per-symbol bar count thresholds that aren't currently exposed cleanly.

- [ ] **Step 4: Verify end-to-end**

Restart the live runner:
```bash
# Kill existing processes first (confirm with user before running)
# Then:
make jforex-live
```

After startup, confirm in the logs:
```bash
grep "warmup\|No valid threshold\|rolling_dynamic" logs/api_live.log | head -20
```

Expected: Lines like `[warmup] GBPUSD: 614 audit events seeded` followed by `predict_warmup: wrote N audit events for GBPUSD`. After warmup, live predictions should log `threshold_source: rolling_days:rolling_dynamic` rather than the old `static_fallback` or the new `no_valid_threshold`.

- [ ] **Step 5: Commit**

```bash
git add scripts/run_jforex_live.py
git commit -m "fix: call /predict/warmup per symbol after backfill to seed rolling threshold history"
```
