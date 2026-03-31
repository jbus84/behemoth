# Health Endpoint Readiness Gate Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `/health` return 503 until FastAPI lifespan initialization is fully complete, fixing the startup race condition that causes the JForex adapter's `feed_status` step to timeout.

**Architecture:** Add a module-level `_lifespan_ready` boolean to `server.py`. Set it `True` at the end of lifespan init (before `yield`), gate `/health` on it. Three touch points in one file plus one new test.

**Tech Stack:** Python, FastAPI, pytest, httpx TestClient

---

### Task 1: Add test for health endpoint lifespan readiness gate

**Files:**
- Modify: `tests/test_api_server.py:41-52` (add test after existing `test_health_uninitialized_state`)

- [ ] **Step 1: Write the failing test**

Add this test to the `TestHealthEndpoint` class in `tests/test_api_server.py`, after the existing `test_health_uninitialized_state` method:

```python
def test_health_returns_503_before_lifespan_ready(self, client):
    """Health must return 503 while lifespan initialization is in progress."""
    from src.behemoth.api import server

    original = server._lifespan_ready
    server._lifespan_ready = False
    try:
        r = client.get("/health")
        assert r.status_code == 503
        assert "Lifespan initialization in progress" in r.json()["detail"]
    finally:
        server._lifespan_ready = original
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run python -m pytest tests/test_api_server.py::TestHealthEndpoint::test_health_returns_503_before_lifespan_ready -v`

Expected: FAIL — `AttributeError: module 'src.behemoth.api.server' has no attribute '_lifespan_ready'`

---

### Task 2: Add `_lifespan_ready` global and gate `/health`

**Files:**
- Modify: `src/behemoth/api/server.py:97` (add global after `_feed_state`)
- Modify: `src/behemoth/api/server.py:3304-3307` (add guard in `health()`)

- [ ] **Step 3: Declare the global**

In `src/behemoth/api/server.py`, add after line 97 (`_feed_state: dict[str, dict[str, Any]] = {}`):

```python
_lifespan_ready: bool = False
```

- [ ] **Step 4: Add the guard to `health()`**

In the `health()` function (currently at line 3304), add the readiness check before the existing `_state is None` check:

```python
@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    """System health: model validity, buffer depths."""
    if not _lifespan_ready:
        raise HTTPException(status_code=503, detail="Lifespan initialization in progress")
    if _state is None:
        raise HTTPException(status_code=503, detail="State manager not initialized")
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run python -m pytest tests/test_api_server.py::TestHealthEndpoint::test_health_returns_503_before_lifespan_ready -v`

Expected: PASS

- [ ] **Step 6: Run all health tests to check for regressions**

Run: `uv run python -m pytest tests/test_api_server.py::TestHealthEndpoint -v`

Expected: All 4 tests PASS. The existing tests use `TestClient(app)` which runs the full lifespan before tests execute, so `_lifespan_ready` will be `True` by the time they run.

---

### Task 3: Set `_lifespan_ready` in the lifespan function

**Files:**
- Modify: `src/behemoth/api/server.py:424-532` (lifespan function)

- [ ] **Step 7: Add `_lifespan_ready` to the globals list in `lifespan()`**

In the `lifespan()` function, add `_lifespan_ready` to the existing `global` declaration at line 426:

```python
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    """Modern lifespan handler replacing deprecated on_event."""
    global _state, _aggregators, _registry, _historical_registry, _feed_state
    global _models_dir, _account_risk_rules_path, _account_risk_profile
    global _historical_entries_loaded, _historical_preflight_failed_checks, _historical_preflight_summary
    global _historical_prediction_universes, _historical_prediction_candidate_index
    global _historical_prediction_candidate_ordinal_index
    global _historical_prediction_candidate_cursor, _historical_prediction_payload_rows
    global _historical_prediction_payload_cursor
    global _lifespan_ready
```

- [ ] **Step 8: Set `_lifespan_ready = True` before `yield`**

Find the line `logger.info("Behemoth API started. Models dir: %s", _models_dir)` (currently line 524) followed by `yield` (line 525). Add the flag set between them:

```python
    logger.info("Behemoth API started. Models dir: %s", _models_dir)
    _lifespan_ready = True
    yield
```

- [ ] **Step 9: Reset `_lifespan_ready = False` after `yield`**

In the shutdown path, immediately after `yield` and before `monitor_task.cancel()`, add:

```python
    _lifespan_ready = True
    yield
    _lifespan_ready = False
    monitor_task.cancel()
```

- [ ] **Step 10: Run all health endpoint tests**

Run: `uv run python -m pytest tests/test_api_server.py::TestHealthEndpoint -v`

Expected: All 4 tests PASS

- [ ] **Step 11: Run the full test suite**

Run: `uv run python -m pytest tests/test_api_server.py -v`

Expected: All tests PASS

- [ ] **Step 12: Commit**

```bash
git add src/behemoth/api/server.py tests/test_api_server.py
git commit -m "fix: gate /health on lifespan completion to prevent startup race condition

The /health endpoint returned 200 as soon as StateManager was initialized,
before model loading and registry setup completed. Orchestration scripts
started the Java adapter prematurely, causing feed_status to timeout (599).

Add _lifespan_ready flag set after all initialization completes. /health
returns 503 until then, so orchestration scripts naturally wait."
```
