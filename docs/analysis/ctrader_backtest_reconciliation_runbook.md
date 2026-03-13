# cTrader Backtest Reconciliation Runbook

Use this runbook to reconcile cTrader backtest runs against research outputs and produce a
baseline-vs-custom A/B parity report.

## Fast path: one-command debug session

For the lowest-friction HistData workflow, use the session manager instead of
manually exporting data and booting the API:

```bash
make ctrader-debug-up \
  SYMBOL=EURUSD \
  START_TS=2025-07-07T00:00:00Z \
  END_TS=2025-07-09T00:00:00Z
```

This will:
- export the HistData custom-data package for the requested window
- include at least `30000` ticks before `START_TS` and `30000` ticks from `START_TS`
  onward, so cTrader has both the warmup tail and a comparison segment
- create an isolated DuckDB runtime under `data/db/debug/`
- start the API in historical mode on `127.0.0.1:8000`
- enable debug HTTP tracing for the session and tag runtime rows with the session `run_id`
- update `data/analysis/backtest_reconcile/ctrader_active_custom_data_package.txt`
  so `CustomDataSourceHistDataPlugin.cs` loads the active package automatically

Adjust the defaults if needed:

```bash
make ctrader-debug-up \
  SYMBOL=EURUSD \
  START_TS=2025-07-07T00:00:00Z \
  END_TS=2025-07-09T00:00:00Z \
  WARMUP_TICKS=30000 \
  COMPARISON_TICKS=30000
```

Inspect the active session:

```bash
make ctrader-debug-status
```

Stop the session when the backtest is done:

```bash
make ctrader-debug-down
```

`ctrader-debug-down` now also finalizes a bundle under
`data/analysis/backtest_reconcile/ctrader_debug_runs/<RUN_ID>/` with:
- `session.json`
- `runtime.db`
- `api.log`
- `http_trace.ndjson`
- auto-discovered cTrader artifacts such as `events.json` and `cbot.log` when present
- `joined_timeline.csv`
- `joined_timeline.md`
- `offline_compare.csv`
- `debug_summary.csv`

## Repo-first lane

The preferred debugging order is now:
1. `make cbot-surrogate ...`
2. inspect the surrogate parity outputs under `data/analysis/backtest_reconcile/cbot_surrogate_runs/<RUN_ID>/`
3. only then run `make ctrader-debug-up ...` for final cTrader verification

The surrogate path exercises the real FastAPI/runtime stack directly from the repo,
without deploying to cTrader, and defaults to the same `30000`-tick warmup plus a
30-second tolerant parity window that is appropriate for cTrader-like timestamp drift.

## 0) Build cTrader custom-data package from HistData parquet

```bash
make export-ctrader-custom-data \
  SYMBOL=EURUSD \
  START_TS=2025-07-07T00:00:00Z \
  END_TS=2025-07-09T00:00:00Z \
  OUT_DIR=data/analysis/backtest_reconcile/EURUSD_histdata_custom_20250707_20250709
```

Outputs:
- `data/analysis/backtest_reconcile/EURUSD_histdata_custom_20250707_20250709/manifest.json`
- `data/analysis/backtest_reconcile/EURUSD_histdata_custom_20250707_20250709/ticks/*.csv`
- `data/analysis/backtest_reconcile/EURUSD_histdata_custom_20250707_20250709/export_summary.csv`

Load this package in cTrader through a custom data source plugin (see
`src/cbot/CustomDataSourceHistDataPlugin.cs` scaffold).

## 1) Start API with isolated per-run DB

```bash
# stop any existing API process on 8000 first
for pid in $(lsof -ti tcp:8000 2>/dev/null); do
  kill "$pid"
done

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

## 3) Reconcile one run (A or B) against research

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

## 4) Build A/B parity report (baseline feed vs custom HistData feed)

Run two backtests in cTrader over the same window:
- Run A: broker historical feed, DB = `data/db/backtests/eurusd_20250707_20250709_baseline.db`
- Run B: custom HistData feed, DB = `data/db/backtests/eurusd_20250707_20250709_histdata.db`

Then generate parity:

```bash
make ctrader-ab-parity-report \
  SYMBOL=EURUSD \
  RUNTIME_DB_A=data/db/backtests/eurusd_20250707_20250709_baseline.db \
  RUNTIME_DB_B=data/db/backtests/eurusd_20250707_20250709_histdata.db \
  PRED_PATH=data/analysis/tick_opportunity_mining/wfo_2025_m3to1_oco_fullcap/EURUSD_oco_monthly_predictions.parquet \
  START_TS=2025-07-07T00:00:00Z \
  END_TS=2025-07-09T00:00:00Z \
  TICK_ROOT=/Users/danielfisher/Desktop/tick
```

Outputs:
- `data/analysis/backtest_reconcile/EURUSD_ctrader_ab_parity_summary.csv`
- `data/analysis/backtest_reconcile/EURUSD_ctrader_ab_parity_checks.csv`
- `docs/analysis/EURUSD_ctrader_ab_parity_report.md`

Interpretation:
- `parity_verdict_ctrader_side`: feed/run A-vs-B parity only (what we use for cTrader-side equivalence).
- `parity_verdict_overall`: includes research high/critical health gate from both runs.

## 5) HistData-only execution parity (repo vs cTrader)

When you only care about HistData equivalence, run this instead of A/B:
- Repo reference: `stop_limit_tickfill_fullcap/<SYMBOL>_stop_limit_tickfill_detail.csv`
- Truth filter: `reduced_core_rolling/<SYMBOL>_oco_reduced_state_schedule.csv` (month-scoped selected states)
- cTrader reference: runtime DB + `events.json` from the same HistData backtest window

```bash
make histdata-ctrader-parity \
  SYMBOL=EURUSD \
  RUNTIME_DB=data/db/backtests/eurusd_20250707_20250709_histdata.db \
  CTRADER_EVENTS_JSON=/Users/danielfisher/cAlgo/Data/cBots/BehemothTradeManager/d719f157-f4ad-4fd3-bfa9-b7e4c67f8b16/Backtesting/events.json \
  REPO_DETAIL_CSV=data/analysis/tick_opportunity_mining/stop_limit_tickfill_fullcap/EURUSD_stop_limit_tickfill_detail.csv \
  REDUCED_STATE_SCHEDULE_CSV=data/analysis/tick_opportunity_mining/reduced_core_rolling/EURUSD_oco_reduced_state_schedule.csv \
  START_TS=2025-07-07T00:00:00Z \
  END_TS=2025-07-09T00:00:00Z \
  TICK_ROOT=/Users/danielfisher/Desktop/tick \
  TIME_TOL_SEC=1.0 \
  PRICE_TOL_PIPS=0.1
```

Outputs:
- `data/analysis/backtest_reconcile/EURUSD_histdata_ctrader_execution_parity_summary.csv`
- `data/analysis/backtest_reconcile/EURUSD_histdata_ctrader_execution_parity_checks.csv`
- `data/analysis/backtest_reconcile/EURUSD_histdata_ctrader_execution_parity_mismatches.csv`
- `docs/analysis/EURUSD_histdata_ctrader_execution_parity_report.md`

## 6) No-cTrader local replay parity (TestClient harness)

Use this when you want to iterate quickly without launching cTrader.  
It replays HistData ticks through the FastAPI app in-process, triggers `/predict`
only on completed bars, synthesizes matched trade lifecycle events, and then runs
the same HistData execution parity validator.

For bar-boundary parity, the harness defaults to `WARMUP_SOURCE=month_start`
(it backfills all pre-window ticks from the month start instead of a fixed tail).
It also defaults to `ENABLE_SEQUENCE_FALLBACK=true` for trade synthesis when
strict `(candidate_uid, close_ts)` key alignment drifts but state ordering matches.
Default gate behavior is execution parity; set `REQUIRE_SELECTED_PARITY=true`
if you want strict selected-key parity to be blocking too.

```bash
make histdata-testclient-parity \
  SYMBOL=EURUSD \
  RUNTIME_DB=data/db/backtests/eurusd_20250707_20250709_testclient.db \
  EVENTS_JSON=data/analysis/backtest_reconcile/EURUSD_testclient_events_20250707_20250709.json \
  REPO_DETAIL_CSV=data/analysis/tick_opportunity_mining/stop_limit_tickfill_fullcap/EURUSD_stop_limit_tickfill_detail.csv \
  REDUCED_STATE_SCHEDULE_CSV=data/analysis/tick_opportunity_mining/reduced_core_rolling/EURUSD_oco_reduced_state_schedule.csv \
  START_TS=2025-07-07T00:00:00Z \
  END_TS=2025-07-09T00:00:00Z \
  TICK_ROOT=/Users/danielfisher/Desktop/tick
```

Primary outputs:
- `data/analysis/backtest_reconcile/EURUSD_histdata_testclient_replay_summary.csv`
- `data/analysis/backtest_reconcile/EURUSD_histdata_testclient_selected_mismatches.csv`
- `data/analysis/backtest_reconcile/EURUSD_histdata_testclient_execution_parity_summary.csv`
- `data/analysis/backtest_reconcile/EURUSD_histdata_testclient_execution_parity_checks.csv`
- `data/analysis/backtest_reconcile/EURUSD_histdata_testclient_execution_parity_mismatches.csv`
- `docs/analysis/EURUSD_histdata_testclient_execution_parity_report.md`

Hard hygiene gate:
- Runtime DB must be single-run clean for the target window (no duplicate raw tick triplets).
- Runtime `candidate_uid` in `trades` must be canonical (`oco|SYMBOL|BT|hH|state_id`), otherwise reduced-core parity cannot be matched.

## Notes

- `audit_logs.event_ts` is wall-clock time; if this differs from backtest time window, checks will flag `audit_event_window_ratio` failures.
- New runs should use isolated DB files to avoid mixed historical/test/live rows.
- `/predict` is now cadence-scoped by `completed_bar_ticks`; cBot sends this automatically from `/ticks` responses.
- When reconciling historical-mode runs, pass `HISTORY_DIR=configs/research/governance/oco_history` so research rows are filtered to the same locked state universe.
- High/critical failures from reconciliation should block interpretation of cTrader-vs-research alignment.
- `raw_ticks` capture is off by default; set `BEHEMOTH_RECORD_RAW_TICKS=true` for deep timing diagnostics.
- Stop the API process before running offline DB analysis commands to avoid DuckDB file lock conflicts.
- A/B report now emits two verdicts:
  - `cTrader-side parity` (A/B delta checks only)
  - `overall` (A/B deltas plus research high/critical gate).
