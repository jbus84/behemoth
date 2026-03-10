# cTrader Backtest Reconciliation Runbook

Use this runbook to reconcile one cTrader backtest run against research outputs.

## 1) Start API with isolated per-run DB

```bash
RUN_ID=eurusd_20250701_20251231
DB_PATH=data/db/backtests/${RUN_ID}.db

BEHEMOTH_GOVERNANCE_MODE=historical_auto \
BEHEMOTH_GOVERNANCE_HISTORY_DIR=configs/research/governance/oco_history \
BEHEMOTH_GOVERNANCE_MISSING_MONTH_POLICY=error \
BEHEMOTH_MODELS_DIR=models/oco \
BEHEMOTH_RECORD_RAW_TICKS=true \
BEHEMOTH_STATE_DB=${DB_PATH} \
uv run uvicorn src.behemoth.api.server:app --host 127.0.0.1 --port 8000
```

Run cTrader backtest with `API Base URL=http://127.0.0.1:8000`.
Recommended cBot ingest settings for parity:
- `Enable Tick Batch=Yes`
- `Tick Batch Size=20`
- `Tick Flush Ms=100`
- `Tick Queue Cap=20000`

Optional live feed sanity check during run:

```bash
curl -s http://127.0.0.1:8000/runtime/feed/status | jq
```

For the active symbol, `total_dropped` should stay near zero (or much lower than `total_accepted`).

## 2) Summarize runtime DB slice

```bash
make summarize-runtime-db-run \
  SYMBOL=EURUSD \
  RUNTIME_DB=${DB_PATH} \
  START_TS=2025-07-01T00:00:00Z \
  END_TS=2026-01-01T00:00:00Z
```

Outputs:
- `data/analysis/backtest_reconcile/EURUSD_runtime_db_run_summary.csv`
- `docs/analysis/EURUSD_runtime_db_run_summary.md`

## 3) Reconcile runtime signals vs research

```bash
make reconcile-ctrader-run \
  SYMBOL=EURUSD \
  RUNTIME_DB=${DB_PATH} \
  PRED_PATH=data/analysis/tick_opportunity_mining/wfo_2025_m3to1_oco_fullcap/EURUSD_oco_monthly_predictions.parquet \
  HISTORY_DIR=configs/research/governance/oco_history \
  START_TS=2025-07-01T00:00:00Z \
  END_TS=2026-01-01T00:00:00Z \
  STRICT_WINDOW=true \
  TOL_SEC=2.0
```

Outputs:
- `data/analysis/backtest_reconcile/EURUSD_ctrader_vs_research_checks.csv`
- `data/analysis/backtest_reconcile/EURUSD_ctrader_vs_research_mismatches.csv`
- `docs/analysis/EURUSD_ctrader_vs_research_reconciliation.md`

## Notes

- `audit_logs.event_ts` is wall-clock time; if this differs from backtest time window, checks will flag `audit_event_window_ratio` failures.
- New runs should use isolated DB files to avoid mixed historical/test/live rows.
- `/predict` is now cadence-scoped by `completed_bar_ticks`; cBot sends this automatically from `/ticks` responses.
- When reconciling historical-mode runs, pass `HISTORY_DIR=configs/research/governance/oco_history` so research rows are filtered to the same locked state universe.
- High/critical failures from reconciliation should block interpretation of cTrader-vs-research alignment.
- `raw_ticks` capture is off by default; set `BEHEMOTH_RECORD_RAW_TICKS=true` for deep timing diagnostics.
- Stop the API process before running offline DB analysis commands to avoid DuckDB file lock conflicts.
