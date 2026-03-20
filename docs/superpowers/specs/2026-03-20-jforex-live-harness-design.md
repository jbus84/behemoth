# JForex Live Session Harness Design

## Problem

`JForexLiveRunner` (the `IClient`-based live/demo session bootstrapper) exists as a Java class and Gradle task but has no Python orchestration layer. To run the live strategy you would need to manually start the Python API with the correct environment variables, wait for it to become healthy, then start the Java runner — and manually kill both on exit. There is no Makefile target and no process monitoring.

## Requirements

1. A `scripts/run_jforex_live.py` script that starts the Python API in live governance mode, waits for it to become healthy, then starts `gradle :jforex-adapter:runJForexLive` with all 6 symbols in a single process.
2. Both processes are monitored every 5 seconds; if either exits unexpectedly the other is killed and the script exits non-zero.
3. SIGINT (Ctrl+C) triggers a clean shutdown of both processes.
4. On startup, `active_oco_state.json` is deleted so the lifecycle registry starts clean.
5. A `make jforex-live` Makefile target calls the script with sensible defaults, configurable via `SYMBOLS`, `API_PORT`, and `REPORT_DIR`.
6. No crash-recovery or automatic restart — human-in-the-loop on failure.

## Architecture

### Startup sequence

```
run_jforex_live.py
  → delete active_oco_state.json (clean lifecycle registry)
  → start Python API (governance_mode=live)
  → poll /health until healthy (60s timeout)
  → start gradle :jforex-adapter:runJForexLive (all symbols, one process)
  → monitor loop every 5s:
      if api_proc exits → kill java, exit non-zero
      if java_proc exits → kill api, exit non-zero
  → on SIGINT → kill both, exit 0
```

### Python API environment (live mode)

Variables **set** for live (vs. historical tester):

| Variable | Live value |
|----------|-----------|
| `BEHEMOTH_GOVERNANCE_MODE` | `live` |
| `BEHEMOTH_STATE_DB` | `<report_dir>/runtime/live_state.db` |
| `BEHEMOTH_GOVERNANCE_HISTORY_DIR` | `configs/research/governance/oco_history_dukascopy_candidate` |
| `BEHEMOTH_MODELS_DIR` | `models/oco_dukascopy_candidate` |

Variables **omitted** (not needed in live mode, unlike the historical tester matrix):

- `BEHEMOTH_HISTORICAL_PREDICTION_PAYLOAD_MODE`
- `BEHEMOTH_HISTORICAL_PREDICTIONS_PATH_OVERRIDE`
- `BEHEMOTH_FORCE_MODEL_MONTH`
- `BEHEMOTH_HISTORICAL_PREDICTION_UNIVERSE_MODE`
- `BEHEMOTH_HISTORICAL_PREDICTION_ORDINAL_TOLERANCE`
- `BEHEMOTH_HISTORICAL_PREDICTION_TOLERANCE_SEC`
- `BEHEMOTH_HISTORICAL_PREFLIGHT_MODE`

### JForexLiveRunner environment

| Variable | Value |
|----------|-------|
| `BEHEMOTH_JFOREX_INSTRUMENTS` | All symbols, comma-separated |
| `BEHEMOTH_JFOREX_RISK_ENABLED` | `true` |
| `BEHEMOTH_JFOREX_RUN_ID` | `jforex_live` |
| `BEHEMOTH_JFOREX_REPORT_DIR` | `<report_dir>` |
| `BEHEMOTH_JFOREX_REQUESTED_VOLUME_UNITS` | `10000` (configurable) |
| `BEHEMOTH_JFOREX_TICK_BATCH_SIZE` | `200` (configurable) |
| `BEHEMOTH_JFOREX_ORDER_TTL_SECONDS` | `900` (configurable) |
| `BEHEMOTH_JFOREX_API_TIMEOUT_SECONDS` | `60` (configurable) |
| `BEHEMOTH_API_BASE_URI` | `http://<api_host>:<api_port>` |
| `BEHEMOTH_JFOREX_JNLP_URI` | from environment |
| `BEHEMOTH_JFOREX_USERNAME` | from environment |
| `BEHEMOTH_JFOREX_PASSWORD` | from environment |

No start/end timestamps — the live runner ignores them; `JForexSessionConfig.fromEnvironment` handles their absence.

### Clarifications on coverage and risk

- **Coverage >100% in tester:** In live mode there is no locked prediction set, so the `signal_coverage_ratio` metric does not apply. The ~15% overcount in tester runs is warmup-period bars generating selects outside the eval window. Not blocking.
- **`risk_enabled`:** The dukascopy matrix forces `false` for tester runs (intentional — risk blocks order submission in historical replay mode). `JForexSessionConfig.fromEnvironment` already defaults to `true`, so the live runner inherits `true` from the environment with no code change.

## File Map

| File | Change |
|------|--------|
| `scripts/run_jforex_live.py` | Create — live session orchestrator |
| `Makefile` | Add `jforex-live` target |

## Testing

No automated tests — the live runner requires real Dukascopy credentials. Manual verification:

1. Start with `make jforex-live` and confirm Python API becomes healthy.
2. Confirm Java runner connects and subscribes to all 6 instruments (check log output).
3. Kill the Python API manually; confirm Java runner is also killed and script exits non-zero.
4. Kill the Java runner manually; confirm Python API is also killed and script exits non-zero.
5. Ctrl+C; confirm both processes shut down cleanly.
