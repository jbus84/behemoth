# Demo-Live vs Offline Model Comparison

**Date:** 2026-04-17
**Scope:** All 6 symbols (AUDUSD, EURUSD, GBPUSD, USDCAD, USDCHF, USDJPY)
**Type:** One-off investigation

## Goal

Compare what actually happened in the JForex demo-live session against what the offline Python model would have produced — across three dimensions: signal parity, execution parity, and outcome parity.

## Data Sources

| Source | Location | Status |
|--------|----------|--------|
| Per-symbol signal parity CSVs | `data/analysis/backtest_reconcile/*_local_jforex_signal_parity_summary.csv` | Available now |
| Per-symbol execution parity CSVs | `data/analysis/backtest_reconcile/*_local_jforex_execution_parity_summary.csv` | Available now (pre-session state) |
| Per-symbol outcome parity CSVs | `data/analysis/backtest_reconcile/*_local_jforex_outcome_parity_summary.csv` | Stale (2026-04-14); needs post-session refresh |
| Live session DB | `data/analysis/backtest_reconcile/runtime/live_state.db` | Locked while session runs |
| Live position summary | `data/analysis/backtest_reconcile/runtime/live_position_summary.json` | Available now |

**Constraint:** `live_state.db` is held exclusively by the running uvicorn process (PID 4865). Full execution and outcome analysis requires the session to end first.

## Three-Phase Plan

### Phase 1 — Signal parity (immediate)

Read the per-symbol `*_local_jforex_signal_parity_summary.csv` files and produce a signal parity summary table. Already reveals a meaningful split:

| Symbol | Signal Parity | Predict Cycles | Failed Events | Finding |
|--------|--------------|----------------|---------------|---------|
| AUDUSD | **FAIL** | 0 | 165 | Python API received no predict calls despite JForex bar events |
| EURUSD | PASS | 136 | 0 | — |
| GBPUSD | PASS | 116 | 0 | — |
| USDCAD | PASS | 113 | 0 | — |
| USDCHF | **FAIL** | 0 | 82 | Python API received no predict calls despite JForex bar events |
| USDJPY | PASS | 185 | 0 | — |

AUDUSD and USDCHF had zero offline model engagement: JForex generated bars but the Python API predict endpoint was never called for these symbols.

### Phase 2 — Execution parity (post-session)

After `live_state.db` unlocks:
- Read `*_local_jforex_execution_parity_summary.csv` for submitted order counts and failures
- Query `live_state.db` directly for entry price deltas, timing deltas, and order match rates

### Phase 3 — Outcome parity (post-session)

After `live_state.db` unlocks:
- Run `scripts/diagnose_live_performance_gap.py --db data/analysis/backtest_reconcile/runtime/live_state.db` to compare live win rates against reduced-core WFO expectations per symbol
- Read `*_local_jforex_outcome_parity_summary.csv` for overall pass/fail per symbol

## Output

Single consolidated markdown report: `docs/analysis/live_demo_vs_offline_comparison_20260417.md`

Sections:
1. Session summary (symbols live, open positions, session window)
2. Signal parity table (all 6 symbols)
3. Execution parity table (post-session)
4. Outcome parity table vs WFO expectations (post-session)
5. Findings and next steps

## Approach Rationale

Uses existing parity infrastructure (`validate_api_parity.py`, `diagnose_live_performance_gap.py`, per-symbol CSVs) rather than new code. Phase 1 can run immediately; Phases 2+3 run once the session ends and the DB lock is released.
