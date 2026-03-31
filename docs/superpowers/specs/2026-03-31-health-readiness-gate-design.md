# Health Endpoint Readiness Gate

## Context

The JForex adapter (both tester and live) fails at the `feed_status` operational step with `status=599 detail=request timed out`. Root cause: a startup race condition.

The orchestration scripts (`run_jforex_live.py`, `run_jforex_dukascopy_matrix.py`) poll `GET /health` and proceed as soon as it returns HTTP 200. But `/health` returns 200 as soon as `StateManager` is initialized — before the FastAPI lifespan has finished loading models, governance registries, and risk profiles. FastAPI cannot serve any other request until `yield` in the lifespan context manager, so the Java adapter's `GET /runtime/feed/status` hangs until the 60-second timeout fires.

## Goal

Make `/health` not return 200 until lifespan initialization is fully complete, so orchestration scripts don't start the Java adapter prematurely.

## Non-Goals

- Adding a separate `/readyz` endpoint
- Changing the Java adapter's startup sequence
- Modifying orchestration script polling logic

## Design

Add a module-level boolean `_lifespan_ready: bool = False` to `server.py`. Set it to `True` immediately before `yield` in the lifespan function. In the `/health` endpoint, return HTTP 503 when `_lifespan_ready` is `False`.

### Changes

**`src/behemoth/api/server.py`:**

1. Declare `_lifespan_ready: bool = False` alongside the other module-level globals.

2. In `lifespan()`, add `global _lifespan_ready` to the globals list and set `_lifespan_ready = True` immediately before `yield` (after all model loading, registry initialization, and risk profile loading is complete). Reset to `False` in the shutdown path after `yield`.

3. In `health()`, add a guard at the top:
   ```python
   if not _lifespan_ready:
       raise HTTPException(status_code=503, detail="Lifespan initialization in progress")
   ```
   This goes before the existing `_state is None` check, since `_state` may already be set while models are still loading.

### Test

Add a unit test that verifies `/health` returns 503 when `_lifespan_ready` is `False` and 200 when `True`. The existing health endpoint tests should continue to pass since the test fixtures initialize the app fully (lifespan completes before tests run).

### Impact

- Orchestration scripts (`_poll_health`) will naturally wait longer — they already retry in a loop with 0.5s sleep until the 60s deadline. No script changes needed.
- The Java adapter will not be started until the API is genuinely ready to serve requests.
- No new endpoints, no new configuration, no breaking changes.
