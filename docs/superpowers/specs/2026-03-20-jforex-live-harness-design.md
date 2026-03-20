# JForex Live Session Harness Design

## Problem

`JForexLiveRunner` (the `IClient`-based live/demo session bootstrapper) exists as a Java class and Gradle task but has no Python orchestration layer. To run the live strategy you would need to manually start the Python API with the correct environment variables, wait for it to become healthy, then start the Java runner — and manually kill both on exit. There is no Makefile target and no process monitoring.

## Requirements

1. A `scripts/run_jforex_live.py` script that:
   - Validates `BEHEMOTH_JFOREX_JNLP_URI`, `BEHEMOTH_JFOREX_USERNAME`, `BEHEMOTH_JFOREX_PASSWORD` are present before starting anything.
   - Deletes `<report_dir>/runtime/active_oco_state.json` on startup to start with a clean lifecycle registry.
   - Starts the Python API in live governance mode, logging to `logs/api_live.log`.
   - Waits for `/health` to return 200 (60s timeout).
   - Starts `mise exec -- gradle :jforex-adapter:runJForexLive` with all 6 symbols in a single process.
2. Both processes are monitored every 5 seconds; if either exits unexpectedly the other is killed and the script exits non-zero.
3. SIGINT (Ctrl+C) triggers a clean shutdown of both processes.
4. A `make jforex-live` Makefile target (added to `.PHONY`) calls the script with sensible defaults, configurable via `SYMBOLS`, `API_PORT`, and `REPORT_DIR`. The target sets `UV_CACHE_DIR=.uv_cache`.
5. No crash-recovery or automatic restart — human-in-the-loop on failure.

## Architecture

### Startup sequence

```
run_jforex_live.py
  → validate BEHEMOTH_JFOREX_JNLP_URI, USERNAME, PASSWORD present
  → delete <report_dir>/runtime/active_oco_state.json (clean lifecycle registry)
  → start Python API (governance_mode=live), stdout/stderr → logs/api_live.log
  → poll /health until 200 (60s timeout; abort if API process exits first)
  → start mise exec -- gradle :jforex-adapter:runJForexLive (all symbols, one process)
  → monitor loop every 5s:
      if api_proc exits → kill java, exit non-zero
      if java_proc exits → kill api, exit non-zero
  → on SIGINT → kill both, exit 0
```

### Python API environment (live mode)

The API is started via `sys.executable -m uvicorn src.behemoth.api.server:app` with `UV_CACHE_DIR=.uv_cache` in the subprocess environment.

Variables **set** for live:

| Variable | Live value |
|----------|-----------|
| `BEHEMOTH_GOVERNANCE_MODE` | `live` |
| `BEHEMOTH_STATE_DB` | `<report_dir>/runtime/live_state.db` |
| `BEHEMOTH_GOVERNANCE_HISTORY_DIR` | `configs/research/governance/oco_history_dukascopy_candidate` |
| `BEHEMOTH_MODELS_DIR` | `models/oco_dukascopy_candidate` |
| `UV_CACHE_DIR` | `.uv_cache` |

Variables **omitted** (not applicable in live mode, unlike the historical tester matrix):

- `BEHEMOTH_HISTORICAL_PREDICTION_PAYLOAD_MODE`
- `BEHEMOTH_HISTORICAL_PREDICTIONS_PATH_OVERRIDE`
- `BEHEMOTH_FORCE_MODEL_MONTH`
- `BEHEMOTH_HISTORICAL_PREDICTION_UNIVERSE_MODE`
- `BEHEMOTH_HISTORICAL_PREDICTION_ORDINAL_TOLERANCE`
- `BEHEMOTH_HISTORICAL_PREDICTION_TOLERANCE_SEC`
- `BEHEMOTH_HISTORICAL_PREFLIGHT_MODE`

### JForexLiveRunner environment

The runner is started via `mise exec -- gradle :jforex-adapter:runJForexLive`.

| Variable | Value | Notes |
|----------|-------|-------|
| `BEHEMOTH_JFOREX_INSTRUMENTS` | All symbols, comma-separated | |
| `BEHEMOTH_JFOREX_RISK_ENABLED` | `true` | **Safety note:** this is intentionally `true` for live execution. Setting it `false` disables order submission. All tester runs force `false`; the live harness is the only context that uses `true`. |
| `BEHEMOTH_JFOREX_RUN_ID` | `jforex_live` | |
| `BEHEMOTH_JFOREX_REPORT_DIR` | `<report_dir>` | |
| `BEHEMOTH_JFOREX_REQUESTED_VOLUME_UNITS` | `10000` (configurable) | |
| `BEHEMOTH_JFOREX_TICK_BATCH_SIZE` | `200` (configurable) | |
| `BEHEMOTH_JFOREX_ORDER_TTL_SECONDS` | `900` (configurable) | |
| `BEHEMOTH_JFOREX_API_TIMEOUT_SECONDS` | `60` (configurable) | |
| `BEHEMOTH_JFOREX_METRICS_ENABLED` | `true` | |
| `BEHEMOTH_JFOREX_METRICS_HOST` | `127.0.0.1` | Required when metrics enabled; Java throws if empty. |
| `BEHEMOTH_JFOREX_METRICS_PORT` | `9464` (configurable) | Single port; no per-symbol offset needed (one process). |
| `BEHEMOTH_JFOREX_NATIVE_OCO_ENABLED` | `false` | Explicitly set to prevent ambient shell env from enabling native OCO mode unexpectedly. |
| `BEHEMOTH_API_BASE_URI` | `http://<api_host>:<api_port>` | |
| `BEHEMOTH_JFOREX_JNLP_URI` | from environment | Pre-flight checked before startup. |
| `BEHEMOTH_JFOREX_USERNAME` | from environment | Pre-flight checked before startup. |
| `BEHEMOTH_JFOREX_PASSWORD` | from environment | Pre-flight checked before startup. |

`JForexSessionConfig.fromEnvironment(false)` synthesises `startUtc = Instant.now()` and `endUtc = startUtc.plusSeconds(60)` internally when not provided; the live runner ignores these fields.

### Clarifications on coverage and risk

- **Coverage >100% in tester:** In live mode there is no locked prediction set, so the `signal_coverage_ratio` metric does not apply. The ~15% overcount in tester runs is warmup-period bars generating selects outside the eval window. Not blocking.
- **`risk_enabled`:** The dukascopy matrix forces `false` for tester runs (intentional — risk blocks order submission in historical replay mode). `JForexSessionConfig.fromEnvironment` already defaults to `true`, so the live runner inherits `true` from the environment with no code change.

## File Map

| File | Change |
|------|--------|
| `scripts/run_jforex_live.py` | Create — live session orchestrator |
| `Makefile` | Add `jforex-live` target; add `jforex-live` to `.PHONY` line |

## Testing

No automated tests — the live runner requires real Dukascopy credentials. Manual verification:

1. Run `make jforex-live` and confirm `logs/api_live.log` shows the API becoming healthy (look for `Application startup complete`).
2. Confirm the Java runner connects: Gradle stdout should contain `subscribed` log lines for all 6 instruments (logged by `BehemothStrategyCore` on `start()`).
3. Kill the Python API process manually (`kill <api_pid>`); confirm the Java runner is also killed and the script exits non-zero.
4. Kill the Java/Gradle process manually; confirm the Python API is also killed and the script exits non-zero.
5. Run `make jforex-live` and press Ctrl+C; confirm both processes shut down cleanly and the script exits 0.
6. Run without `BEHEMOTH_JFOREX_JNLP_URI` set; confirm the script exits immediately with a clear error before starting any process.
