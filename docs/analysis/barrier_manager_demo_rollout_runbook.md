# Barrier Manager Demo Rollout Runbook

## Scope

This runbook covers the live-demo rollout for the barrier-manager JForex path. It is an operator procedure, not a strategy-design document.

## Start Conditions

Before starting a demo session, confirm all of the following:

- Stage 13 is green in `docs/strategy_bible/generated/stage_13_snapshot.md`.
- Stage 14 is green in `docs/strategy_bible/generated/stage_14_snapshot.md`.
- `docs/analysis/stage14_jforex_runtime_certification_report.md` shows no failing `execution_lifecycle_pass`, `jforex_outcome_parity_pass`, or `local_jforex_surrogate_pass` rows for the symbol.
- The canonical evidence files exist for the symbol:
  - `data/analysis/backtest_reconcile/<SYMBOL>_jforex_runtime_events.csv`
  - `data/analysis/backtest_reconcile/<SYMBOL>_local_jforex_runtime_events.csv`
- No unresolved high or critical blockers remain in:
  - `docs/analysis/operator_action_report.md`
  - `docs/analysis/oco_alert_remediation_report.md`

## During Session Checks

Check these paths during the demo session:

- JForex metrics endpoint: `127.0.0.1:9464/metrics`
- Runtime evidence stream: `data/analysis/backtest_reconcile/<SYMBOL>_jforex_runtime_events.csv`

Watch for these failure signatures:

- `market_order_submit_failure`
- `market_order_blocked`
- `barrier_close_failure`
- `order_rejected`

Session is no longer rollout-safe if any of the following appear:

- `market_order_blocked` for a symbol expected to be executable in the current session window
- `barrier_close_failure` caused by missing or unknown broker position state
- repeated `feed_status=false`
- missing growth in the canonical runtime-events file while the session is active

## Post-Session Review

After the demo session:

1. Regenerate or refresh Stage 14 certification artifacts.
2. Review `docs/analysis/stage14_jforex_runtime_certification_report.md`.
3. Review `docs/strategy_bible/generated/stage_14_snapshot.md`.
4. Inspect symbol-level evidence:
   - `data/analysis/backtest_reconcile/<SYMBOL>_jforex_runtime_events.csv`
   - `data/analysis/backtest_reconcile/<SYMBOL>_jforex_execution_lifecycle_summary.csv`
   - `data/analysis/backtest_reconcile/jforex_outcome_parity_summary.csv`
   - `data/analysis/backtest_reconcile/local_jforex_surrogate_summary.csv`
5. Confirm the lifecycle summary reports:
   - `submit_failures == 0`
   - `blocked_orders == 0`
   - `close_anomalies == 0`

## Triage Paths

Use these paths when Stage 14 fails after a demo session:

- Lifecycle failure:
  - inspect `data/analysis/backtest_reconcile/<SYMBOL>_jforex_execution_lifecycle_summary.csv`
  - inspect `data/analysis/backtest_reconcile/<SYMBOL>_jforex_runtime_events.csv`
- Outcome parity failure:
  - inspect `data/analysis/backtest_reconcile/jforex_outcome_parity_summary.csv`
  - inspect `data/analysis/backtest_reconcile/<SYMBOL>_jforex_runtime_events.csv`
- Local surrogate failure:
  - inspect `data/analysis/backtest_reconcile/local_jforex_surrogate_summary.csv`
  - inspect `data/analysis/backtest_reconcile/<SYMBOL>_local_jforex_runtime_events.csv`

Do not advance the rollout when Stage 14 is red. Resolve the failing artifact path first, then rerun certification.
