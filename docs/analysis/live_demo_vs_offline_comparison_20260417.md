# Demo-Live vs Offline Model Comparison — 2026-04-17

_Generated: 2026-04-17T10:19:23Z UTC_

## Session Summary

- **Run ID:** `jforex_live`
- **Session started (UTC):** `2026-04-16T16:47:20.264123Z`
- **Report generated (UTC):** `2026-04-17T10:19:23Z`
- **Symbols live:** 6 / 6

- **Open positions at report time:** 3

| Symbol | Status | Open Since (UTC) | Last Tick |
|--------|--------|-----------------|-----------|
| GBPUSD | OPEN | 2026-04-17T09:54:30.426952+00:00 | 1.35346 |
| GBPUSD | PENDING | 2026-04-17T10:15:31.267341+00:00 | 1.35346 |
| USDCAD | PENDING | 2026-04-17T10:01:40.556401+00:00 | 1.36783 |

## Signal Parity

Compares JForex bar events against offline Python model predict calls.

| Symbol | Pass | Predict Cycles | Failed Events | Finding |
|--------|------|----------------|---------------|---------|
| AUDUSD | ❌ | 0 | 165 | Python API received no predict calls despite JForex bar events |
| EURUSD | ✅ | 136 | 0 | — |
| GBPUSD | ✅ | 116 | 0 | — |
| USDCAD | ✅ | 113 | 0 | — |
| USDCHF | ❌ | 0 | 82 | Python API received no predict calls despite JForex bar events |
| USDJPY | ✅ | 185 | 0 | — |

## Execution Parity

_Pending: requires `live_state.db` to unlock after session end. Run with `--phase 2`._

## Outcome Parity

_Pending: requires `live_state.db` to unlock after session end. Run with `--phase 2`._

## Findings and Next Steps

**Signal failures:** AUDUSD and USDCHF show 0 predict cycles with failed signal events, indicating the Python API was not called for these symbols during the session. EURUSD, GBPUSD, USDCAD, USDJPY all passed signal parity.

_Execution and outcome analysis pending. Re-run with `--phase 2` after session ends._