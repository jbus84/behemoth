# Audit Log History Seed Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `POST /state/seed_audit_history` to replay Dukascopy tick parquets through the model and populate `audit_logs` with real historical pred_probs, so `get_rolling_threshold()` returns a calibrated rolling threshold on the first live predict call after server startup.

**Architecture:** A new FastAPI endpoint creates an isolated in-memory `StateManager` + `TickAggregator` per symbol, replays ticks from parquets into bars, computes features and runs inference at each bar, then writes pred_probs to the live DB via `_state.log_audit_event()` (single-writer pattern). `run_jforex_live.py` calls the endpoint once after health-poll before the backfill sleep.

**Tech Stack:** FastAPI, DuckDB, CatBoost, pandas, `src.behemoth.runtime.state.StateManager`, `src.behemoth.runtime.tick_aggregator.TickAggregator`, `src.behemoth.core.schemas.IncomingTick`, pytest.

**Spec:** `docs/superpowers/specs/2026-03-24-audit-log-history-seed-design.md`

---

## File Map

| File | Action | What changes |
|------|--------|-------------|
| `src/behemoth/api/server.py` | Modify | Add `dukascopy_ticks_dir` to `AppConfig`; add `SeedAuditHistoryRequest` model; add `POST /state/seed_audit_history` endpoint |
| `scripts/run_jforex_live.py` | Modify | Add `_seed_audit_history()` helper; insert call after `_poll_health`, before `time.sleep(30)` |
| `tests/test_api_server.py` | Modify | Add `TestSeedAuditHistory` class with 4 tests |

---

## Background: Key Interfaces

Before touching code, understand these:

**`AppConfig`** (`server.py:193`) — Pydantic `BaseModel`. All fields use `Field(default_factory=lambda: os.getenv(...))`. Add `dukascopy_ticks_dir` using the same pattern.

**`_resolve_runtime_contract(sym, close_ts)`** (`server.py:1165`) — returns a `_ResolvedRuntimeContract` with `.candidates` (list of candidate objects), `.model_month` (str), `.cache_key` (str). Each candidate has `.bar_ticks`, `.horizon`, `.barrier_pips`, `.candidate_uid`.

**`_ensure_model_and_threshold(contract)`** (`server.py:1233`) — returns `(model, thr_cfg)`. `model` is a CatBoost object with `.predict_proba(arr)`. `thr_cfg` is a dict with key `threshold_exec` (float).

**`StateManager.log_audit_event`** (`state.py:354`) — signature: `(symbol, candidate_uid, pred_prob, threshold, features: ModelFeatures, model_month, close_ts, run_id)`. `features` must be a `ModelFeatures` instance (not an array). `close_ts` is a `datetime` with timezone.

**`StateManager.compute_features(sym, bar_ticks, horizon, barrier_pips)`** (`state.py:315`) — returns `ModelFeatures | None`. Returns `None` until ≥ 289 bars have been appended.

**`TickAggregator.add_ticks(ticks: list[IncomingTick])`** (`tick_aggregator.py:34`) — emits one `IncomingTickBar` per 100 ticks. The bar's `close_ts` is the timestamp of the last tick in the bar.

**`IncomingTick`** (`core/schemas.py`) — fields: `symbol: str`, `timestamp: datetime`, `bid: float`, `ask: float`, `tick_volume: float = 1.0`.

**Parquet location:** `/Users/danielfisher/Desktop/dukascopy_ticks/{SYMBOL}/{SYMBOL}_YYYYMM_ticks.parquet`
**Parquet columns:** `timestamp, bid, ask, mid, spread, log_return`

---

## Task 1: Add `dukascopy_ticks_dir` to `AppConfig`

**Files:**
- Modify: `src/behemoth/api/server.py` (around line 205, inside `AppConfig`)
- Test: `tests/test_api_server.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_api_server.py` inside a new class `TestSeedAuditHistory`:

```python
class TestSeedAuditHistory:
    def test_config_has_dukascopy_ticks_dir(self):
        from src.behemoth.api import server
        assert hasattr(server._config, "dukascopy_ticks_dir")
        assert server._config.dukascopy_ticks_dir  # non-empty string
```

- [ ] **Step 2: Run to confirm it fails**

```bash
cd /Users/danielfisher/repositories/behemoth
.venv/bin/pytest tests/test_api_server.py::TestSeedAuditHistory::test_config_has_dukascopy_ticks_dir -v
```

Expected: `FAILED` — `AttributeError: '_config' has no attribute 'dukascopy_ticks_dir'`

- [ ] **Step 3: Add the field to `AppConfig`**

In `src/behemoth/api/server.py`, find `AppConfig` (line ~193). Add after the last field in the class (before the closing of the class body), following the exact same `Field(default_factory=lambda: os.getenv(...))` pattern used by other fields:

```python
    dukascopy_ticks_dir: str = Field(
        default_factory=lambda: os.getenv(
            "BEHEMOTH_DUKASCOPY_TICKS_DIR",
            "/Users/danielfisher/Desktop/dukascopy_ticks",
        )
    )
```

- [ ] **Step 4: Run test to confirm it passes**

```bash
.venv/bin/pytest tests/test_api_server.py::TestSeedAuditHistory::test_config_has_dukascopy_ticks_dir -v
```

Expected: `PASSED`

- [ ] **Step 5: Commit**

```bash
git add src/behemoth/api/server.py tests/test_api_server.py
git commit -m "feat: add dukascopy_ticks_dir to AppConfig (BEHEMOTH_DUKASCOPY_TICKS_DIR)"
```

---

## Task 2: Add `SeedAuditHistoryRequest` model and failing tests

**Files:**
- Modify: `src/behemoth/api/server.py` (near line 1882, after `WarmupRequest`)
- Modify: `tests/test_api_server.py`

- [ ] **Step 1: Add the remaining three failing tests to `TestSeedAuditHistory`**

Add to the existing `TestSeedAuditHistory` class (leave `test_config_has_dukascopy_ticks_dir` in place):

```python
    def test_seed_503_when_state_uninitialized(self, client):
        from src.behemoth.api import server
        original = server._state
        server._state = None
        try:
            r = client.post("/state/seed_audit_history", json={})
            assert r.status_code == 503
        finally:
            server._state = original

    def test_seed_returns_201_with_few_ticks(self, client, tmp_path):
        """500 ticks = 5 bars < 289 warmup → valid 201 with total_events=0."""
        import numpy as np
        import pandas as pd
        from datetime import timedelta

        sym = "GBPUSD"
        sym_dir = tmp_path / sym
        sym_dir.mkdir()
        now = datetime.now(tz=timezone.utc)
        ts = pd.date_range(start=now - timedelta(days=25), periods=500, freq="1s", tz="UTC")
        df = pd.DataFrame({
            "timestamp": ts,
            "bid": np.full(500, 1.3000),
            "ask": np.full(500, 1.3001),
            "mid": np.full(500, 1.30005),
            "spread": np.full(500, 0.0001),
            "log_return": np.zeros(500),
        })
        month_str = (now - timedelta(days=25)).strftime("%Y%m")
        df.to_parquet(sym_dir / f"{sym}_{month_str}_ticks.parquet", index=False)

        from src.behemoth.api import server
        original_dir = server._config.dukascopy_ticks_dir
        server._config.dukascopy_ticks_dir = str(tmp_path)
        try:
            r = client.post("/state/seed_audit_history",
                            json={"symbols": [sym], "days_back": 30})
            assert r.status_code == 201
            body = r.json()
            assert body["ok"] is True
            assert isinstance(body["total_events"], int)
            assert body["total_events"] >= 0
        finally:
            server._config.dukascopy_ticks_dir = original_dir

    def test_seed_writes_events_when_sufficient_ticks(self, client, tmp_path):
        """30,000 ticks = 300 bars > 289 warmup → events written to audit_logs."""
        import numpy as np
        import pandas as pd
        from datetime import timedelta

        sym = "GBPUSD"
        sym_dir = tmp_path / sym
        sym_dir.mkdir()
        n = 30_000
        now = datetime.now(tz=timezone.utc)
        ts = pd.date_range(start=now - timedelta(days=25), periods=n, freq="1s", tz="UTC")
        df = pd.DataFrame({
            "timestamp": ts,
            "bid": np.full(n, 1.3000),
            "ask": np.full(n, 1.3001),
            "mid": np.full(n, 1.30005),
            "spread": np.full(n, 0.0001),
            "log_return": np.zeros(n),
        })
        month_str = (now - timedelta(days=25)).strftime("%Y%m")
        df.to_parquet(sym_dir / f"{sym}_{month_str}_ticks.parquet", index=False)

        from src.behemoth.api import server
        original_dir = server._config.dukascopy_ticks_dir
        server._config.dukascopy_ticks_dir = str(tmp_path)
        try:
            r = client.post("/state/seed_audit_history",
                            json={"symbols": [sym], "days_back": 30})
            assert r.status_code == 201
            body = r.json()
            assert body["ok"] is True
            assert body["total_events"] > 0
            assert body["events_by_symbol"][sym] > 0
            # Verify rows were actually persisted to audit_logs (single-writer path)
            rows = server._state._con.execute(
                "SELECT COUNT(*) FROM audit_logs WHERE symbol=? AND run_id=?",
                [sym, "audit_seed"],
            ).fetchone()
            assert rows[0] > 0
        finally:
            server._config.dukascopy_ticks_dir = original_dir

    def test_seed_skips_missing_symbol_gracefully(self, client, tmp_path):
        """Symbol with no parquet dir → 201 with 0 events for that symbol."""
        from src.behemoth.api import server
        original_dir = server._config.dukascopy_ticks_dir
        server._config.dukascopy_ticks_dir = str(tmp_path)
        try:
            r = client.post("/state/seed_audit_history",
                            json={"symbols": ["GBPUSD"], "days_back": 20})
            assert r.status_code == 201
            body = r.json()
            assert body["ok"] is True
            assert body["events_by_symbol"].get("GBPUSD", 0) == 0
        finally:
            server._config.dukascopy_ticks_dir = original_dir
```

Note: `datetime`, `timezone`, and `timedelta` must be imported at the top of the test file. Check with `grep "^from datetime\|^import datetime" tests/test_api_server.py` — if not present, add `from datetime import datetime, timedelta, timezone` to the imports. If `timedelta` is missing from an existing import line, add it.

- [ ] **Step 2: Run all four tests to confirm they fail**

```bash
.venv/bin/pytest tests/test_api_server.py::TestSeedAuditHistory -v
```

Expected: `test_config_has_dukascopy_ticks_dir` PASSED, the other three FAILED with 404 or 405.

- [ ] **Step 3: Add `SeedAuditHistoryRequest` model**

In `src/behemoth/api/server.py`, find `WarmupRequest` (line ~1882). Add immediately after it:

```python
class SeedAuditHistoryRequest(BaseModel):
    symbols: list[str] | None = None
    days_back: int = 20
    run_id: str = "audit_seed"
```

- [ ] **Step 4: Re-run tests — still expect 3 failures (endpoint not added yet)**

```bash
.venv/bin/pytest tests/test_api_server.py::TestSeedAuditHistory -v
```

Expected: still 404 on the three endpoint tests. No new errors.

---

## Task 3: Implement `POST /state/seed_audit_history`

**Files:**
- Modify: `src/behemoth/api/server.py` (after `/state/checkpoint` endpoint, around line 2813)

- [ ] **Step 1: Add the endpoint**

Find the `/state/checkpoint` endpoint in `server.py`. Add the following immediately after it (before `@app.post("/trades/touch")`):

```python
@app.post("/state/seed_audit_history", status_code=201)
async def seed_audit_history(req: SeedAuditHistoryRequest) -> dict:
    """Replay Dukascopy parquets through the model to seed audit_logs.

    Creates a rolling pred_prob distribution so get_rolling_threshold()
    returns a calibrated value on the first live predict call after startup.
    Uses an isolated in-memory StateManager for replay; writes to the live
    DB via _state.log_audit_event() (single-writer pattern).
    """
    import numpy as np
    import pandas as pd

    if _state is None:
        raise HTTPException(status_code=503, detail="State manager not initialized")

    ticks_dir = Path(_config.dukascopy_ticks_dir)
    if not ticks_dir.exists():
        raise HTTPException(
            status_code=422,
            detail=f"dukascopy_ticks_dir not found: {ticks_dir}",
        )

    symbols = [s.upper() for s in (req.symbols or _config.symbols)]
    now_ts = datetime.now(tz=timezone.utc)
    start_dt = now_ts - timedelta(days=req.days_back)
    events_by_symbol: dict[str, int] = {}

    for sym in symbols:
        sym_dir = ticks_dir / sym
        if not sym_dir.exists():
            logger.warning("seed_audit_history: no parquet dir for %s at %s", sym, sym_dir)
            events_by_symbol[sym] = 0
            continue

        # Find monthly parquet files that overlap [start_dt, now_ts]
        start_ym = start_dt.strftime("%Y%m")
        end_ym = now_ts.strftime("%Y%m")
        relevant = sorted(
            f for f in sym_dir.glob(f"{sym}_*_ticks.parquet")
            if (ym := f.stem.removeprefix(f"{sym}_").removesuffix("_ticks"))
            and start_ym <= ym <= end_ym
        )

        if not relevant:
            logger.warning(
                "seed_audit_history: no parquets for %s in %s–%s", sym, start_ym, end_ym
            )
            events_by_symbol[sym] = 0
            continue

        try:
            frames = [pd.read_parquet(f, columns=["timestamp", "bid", "ask"]) for f in relevant]
            df = pd.concat(frames, ignore_index=True)
            # Normalise to UTC-aware
            if df["timestamp"].dt.tz is None:
                df["timestamp"] = df["timestamp"].dt.tz_localize("UTC")
            else:
                df["timestamp"] = df["timestamp"].dt.tz_convert("UTC")
            df = (
                df[(df["timestamp"] >= start_dt) & (df["timestamp"] <= now_ts)]
                .sort_values("timestamp")
                .reset_index(drop=True)
            )
        except Exception as exc:
            logger.warning("seed_audit_history: failed to read parquets for %s: %s", sym, exc)
            events_by_symbol[sym] = 0
            continue

        if df.empty:
            events_by_symbol[sym] = 0
            continue

        # Resolve live model contract — uses identical canonical_uid format as /predict
        contract = _resolve_runtime_contract(sym, now_ts)
        if not contract.candidates:
            events_by_symbol[sym] = 0
            continue
        model, thr_cfg = _ensure_model_and_threshold(contract)
        if model is None:
            events_by_symbol[sym] = 0
            continue

        static_thr = float(thr_cfg.get("threshold_exec", 0.5))
        bar_ticks = int(contract.candidates[0].bar_ticks)

        # Isolated replay — never writes to live tick_bars
        replay_state = StateManager(
            vol_window=_config.vol_window,
            cost_window=_config.cost_window,
        )
        replay_agg = TickAggregator(bar_ticks=bar_ticks)
        n_written = 0

        try:
            # Batch-convert to IncomingTick and aggregate in one pass
            ticks = [
                IncomingTick(
                    symbol=sym,
                    timestamp=row.timestamp.to_pydatetime(),
                    bid=float(row.bid),
                    ask=float(row.ask),
                )
                for row in df.itertuples(index=False)
            ]
            bars = replay_agg.add_ticks(ticks)

            for bar in bars:
                replay_state.append_bar(bar)
                for cand in contract.candidates:
                    feats = replay_state.compute_features(
                        sym,
                        bar_ticks,
                        cand.horizon,
                        cand.barrier_pips,
                    )
                    if feats is None:
                        continue
                    arr = np.array([feats.to_array()], dtype=float)
                    with METRIC_INFERENCE_LATENCY.labels(symbol=sym).time():
                        pred_prob = float(model.predict_proba(arr)[:, 1][0])
                    canonical_uid = (
                        f"oco|{sym}|{cand.bar_ticks}|h{cand.horizon}|{cand.candidate_uid}"
                    )
                    _state.log_audit_event(
                        symbol=sym,
                        candidate_uid=canonical_uid,
                        pred_prob=pred_prob,
                        threshold=static_thr,
                        features=feats,
                        model_month=contract.model_month,
                        close_ts=bar.close_ts,
                        run_id=req.run_id,
                    )
                    n_written += 1
        finally:
            replay_state.close()

        events_by_symbol[sym] = n_written
        logger.info("seed_audit_history: wrote %d events for %s", n_written, sym)

    total = sum(events_by_symbol.values())
    return {"ok": True, "events_by_symbol": events_by_symbol, "total_events": total}
```

> **Import check:** `Path`, `timedelta`, `StateManager`, `TickAggregator`, `IncomingTick`, `METRIC_INFERENCE_LATENCY` must all be imported at the top of `server.py`. Run `grep "^from\|^import" src/behemoth/api/server.py | grep -E "Path|timedelta|StateManager|TickAggregator|IncomingTick|METRIC_INFERENCE"` to verify. If `TickAggregator` is missing, add `from src.behemoth.runtime.tick_aggregator import TickAggregator`.

- [ ] **Step 2: Run all four endpoint tests**

```bash
.venv/bin/pytest tests/test_api_server.py::TestSeedAuditHistory -v --tb=short
```

Expected: All 5 tests (including the config test from Task 1) `PASSED`.

If `test_seed_writes_events_when_sufficient_ticks` fails with `total_events == 0`, check:
- Does the test client have a model loaded for GBPUSD? (check `server._models`)
- Is `compute_features` returning `None` for all bars? (may need more than 300 bars if bar timestamps are too close together — 30,000 ticks at 1-second intervals with constant bid/ask may cause vol computation to return NaN)
- If constant prices cause NaN features, vary the bid slightly: `bid = np.linspace(1.2990, 1.3010, n)`

- [ ] **Step 3: Run the full test suite to check for regressions**

```bash
.venv/bin/pytest tests/test_api_server.py tests/test_duckdb_state.py -v --tb=short 2>&1 | tail -15
```

Expected: All tests pass.

- [ ] **Step 4: Commit**

```bash
git add src/behemoth/api/server.py tests/test_api_server.py
git commit -m "feat: add POST /state/seed_audit_history endpoint for rolling threshold bootstrap"
```

---

## Task 4: Add `_seed_audit_history()` to `run_jforex_live.py`

**Files:**
- Modify: `scripts/run_jforex_live.py`

No automated test for this task — the startup orchestration is integration-only. Verify manually via log output.

- [ ] **Step 1: Add the helper function**

In `scripts/run_jforex_live.py`, find `_warmup_symbols` (line ~108). Add the following immediately before it:

```python
def _seed_audit_history(symbols: list[str], base_url: str, days_back: int = 20) -> None:
    """Call /state/seed_audit_history to populate audit_logs from Dukascopy parquets.

    This seeds the rolling threshold distribution so that get_rolling_threshold()
    returns a calibrated value on the first live predict call.
    Must be called after _poll_health() but before time.sleep(30) / _warmup_symbols().
    """
    import requests

    print(f"[seed] seeding audit_logs from last {days_back} days of parquet data...", flush=True)
    try:
        r = requests.post(
            f"{base_url}/state/seed_audit_history",
            json={"symbols": symbols, "days_back": days_back, "run_id": "audit_seed"},
            timeout=600,  # replay can take several minutes for 20 days × 6 symbols
        )
        body = r.json()
        if body.get("ok"):
            print(f"[seed] done — total events: {body['total_events']}", flush=True)
            for sym, count in body.get("events_by_symbol", {}).items():
                print(f"[seed]   {sym}: {count} events", flush=True)
        else:
            print(f"[seed] WARNING: unexpected response: {body}", flush=True)
    except Exception as exc:
        print(f"[seed] WARNING: seed_audit_history failed: {exc}", flush=True)
        print("[seed] continuing without historical seed — first predict calls may block", flush=True)
```

- [ ] **Step 2: Insert the call in `main()`**

Find the startup block in `main()` (line ~247):

```python
        _poll_health(api_proc, f"http://{cfg.api_host}:{cfg.api_port}", timeout_sec=60.0)
        print("[jforex-live] API healthy", flush=True)
        print("[jforex-live] waiting for backfill + warming up threshold history", flush=True)
        # Give JForex time to complete initial backfill before warmup scoring
        time.sleep(30)
        _warmup_symbols(list(cfg.symbols), base_url=f"http://{cfg.api_host}:{cfg.api_port}")
```

Replace with:

```python
        _poll_health(api_proc, f"http://{cfg.api_host}:{cfg.api_port}", timeout_sec=60.0)
        print("[jforex-live] API healthy", flush=True)
        _seed_audit_history(list(cfg.symbols), base_url=f"http://{cfg.api_host}:{cfg.api_port}")
        print("[jforex-live] waiting for backfill + warming up threshold history", flush=True)
        # Give JForex time to complete initial backfill before warmup scoring
        time.sleep(30)
        _warmup_symbols(list(cfg.symbols), base_url=f"http://{cfg.api_host}:{cfg.api_port}")
```

- [ ] **Step 3: Commit**

```bash
git add scripts/run_jforex_live.py
git commit -m "feat: call /state/seed_audit_history at startup before backfill sleep"
```

---

## Task 5: Smoke test against the live server

- [ ] **Step 1: Call the endpoint manually**

```bash
curl -s -X POST "http://127.0.0.1:8000/state/seed_audit_history" \
  -H "Content-Type: application/json" \
  -d '{"days_back": 20, "run_id": "audit_seed"}' | python3 -m json.tool
```

Expected response shape:
```json
{
  "ok": true,
  "events_by_symbol": {
    "EURUSD": 0,
    "GBPUSD": 6000,
    ...
  },
  "total_events": 30000
}
```

Note: EURUSD/other symbols with no parquets in the default dir will show 0 — that's correct.

- [ ] **Step 2: Verify rolling threshold is now computable**

```bash
.venv/bin/python3 -c "
from src.behemoth.runtime.state import StateManager
from pathlib import Path
sm = StateManager(db_path='data/analysis/backtest_reconcile/runtime/live_state.db')
result = sm.get_rolling_threshold(
    symbol='GBPUSD',
    candidate_uid='oco|GBPUSD|100|h6|oco_first_touch_clean__ny_overlap__k2',
    exec_q=0.9,
    lookback_days=20,
    min_history=1000,
)
print('rolling threshold:', result)
sm.close()
"
```

Expected: a float (e.g. `0.6231`), not `None`.

- [ ] **Step 3: Commit the smoke test result as a note in the plan**

No code change — update the plan checkbox only.

---

## Task 6: Final verification

- [ ] **Step 1: Run the full affected test suites**

```bash
.venv/bin/pytest tests/test_api_server.py tests/test_duckdb_state.py tests/test_diagnose_live_performance_gap.py -v --tb=short 2>&1 | tail -20
```

Expected: All tests pass (90+ tests).

- [ ] **Step 2: Commit if any fixup changes were needed**

```bash
git add -p
git commit -m "fix: <describe any fixups>"
```
