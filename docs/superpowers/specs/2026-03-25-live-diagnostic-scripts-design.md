# Live Diagnostic Scripts Design

**Date:** 2026-03-25
**Status:** Approved

## Problem

The live JForex system is accumulating bars (327–672 per symbol) but generating too few trades and the trades that do fire are net negative. Two failure modes need diagnosing:

1. **Trade frequency** — EURUSD has 672 bars and zero trades; other symbols have 1–3 trades each. Expected win rates (from WFO eval) are 59–72%.
2. **Trade quality** — the 8 closed trades are all net negative (combined ≈ -17.7 pips).

## Root Cause of Diagnostic Blind Spot

The current DB schema has a fundamental visibility gap: `audit_logs` only records predictions where `selected_exec == 1` (cleared threshold + passed risk + survived deduplication). Sub-threshold evaluations are never persisted. This means we cannot answer "why aren't trades firing?" from the DB alone — we can only see the predictions that already succeeded.

## Approach: Two Phases

**Phase 1 — `predict_evaluations` table**: Extend the DB schema and server to record every prediction evaluation, regardless of outcome. This permanently closes the visibility gap for all future runs.

**Phase 2 — Diagnostic scripts**: Two focused scripts. `diagnose_live_audit.py` analyses the DB (using `predict_evaluations` when available, falling back to existing tables for the current session). `diagnose_live_replay.py` does offline model inference against parquet bars to score the current live session where `predict_evaluations` is not yet populated.

---

## Phase 1: `predict_evaluations` Table

### Schema

```sql
CREATE TABLE IF NOT EXISTS predict_evaluations (
    event_ts        TIMESTAMP WITH TIME ZONE,
    close_ts        TIMESTAMP WITH TIME ZONE,
    symbol          VARCHAR,
    candidate_uid   VARCHAR,
    pred_prob       DOUBLE,
    threshold       DOUBLE,
    preselected_exec INTEGER,
    selected_exec    INTEGER,
    threshold_blocked BOOLEAN,
    threshold_block_reason VARCHAR,
    risk_blocked     BOOLEAN,
    risk_block_reason VARCHAR,
    model_month     VARCHAR,
    run_id          VARCHAR
)
```

`preselected_exec = 1` means `pred_prob >= threshold`. `selected_exec = 1` means it also cleared risk guardrails and deduplication. Together they give the complete funnel for every bar evaluated.

### StateManager Changes (`src/behemoth/runtime/state.py`)

1. Add `predict_evaluations` DDL to `_SCHEMA_SQL` using `CREATE TABLE IF NOT EXISTS`. This is sufficient for both fresh installs and existing live DBs — on next startup, DuckDB's `IF NOT EXISTS` clause creates the table if absent. No `_ensure_runtime_schema` migration entry is needed (that mechanism handles adding columns to existing tables, not creating new tables).
2. Add `log_predict_evaluation(...)` method. Do not mirror `log_audit_event` blindly — notably, `features_json` is deliberately excluded from `predict_evaluations` (no feature vectors here, just gate outcomes). Include: `event_ts`, `close_ts`, `symbol`, `candidate_uid`, `pred_prob`, `threshold` (from `d.curr_threshold`), `preselected_exec`, `selected_exec`, `threshold_blocked`, `threshold_block_reason`, `risk_blocked`, `risk_block_reason`, `model_month`, `run_id`.

### Server Changes (`src/behemoth/api/server.py`)

In the predict endpoint, call `_state.log_predict_evaluation(...)` **inside the existing `for d in decisions:` loop** (which begins at line ~2710), **unconditionally**, before the `if d.selected_exec == 1` reservation/audit block. Do not place the call inside the allocator `if` block (lines ~2638–2706) — that block is conditionally entered and silently skips rows when the allocator is disabled.

`predict_evaluations` covers every candidate that reaches the feature-computation stage. Candidates rejected before that point (e.g. insufficient bar warmup, bar buffer too shallow for features) are not recorded. The "total evaluations" count in the funnel will therefore be lower than the raw bar count for symbols still in warmup.

`audit_logs` is unchanged — it continues to serve its existing purpose as the rolling-threshold seed table (admitted predictions only, which is what the calibration needs).

### Impact on `diagnose_live_audit.py`

When `predict_evaluations` is populated (any run after this change), the audit script uses it for full funnel analysis. For the current live session (no `predict_evaluations` data), the script falls back to `account_risk_allocator_events` and notes the limited visibility in the report.

### Testing

`tests/test_account_risk.py` or a new `tests/test_state_predict_evaluations.py`:
- Create a StateManager with in-memory DuckDB
- Call `log_predict_evaluation` with known values (preselected=1/selected=0, preselected=0/selected=0, etc.)
- Assert rows are written with correct column values
- Assert `audit_logs` is unaffected

---

## Phase 2: Diagnostic Scripts

### Script 1: `scripts/diagnose_live_audit.py`

Checkpoints the DB, opens it read-only, and reports on what has been recorded.

**CLI:**
```
python scripts/diagnose_live_audit.py \
    --db data/analysis/backtest_reconcile/runtime/live_state.db \
    --api http://localhost:8000 \
    --run-id jforex_live \
    --out data/analysis/live_audit_report.md
```

**Checkpoint helper** (inline at top of script):
```python
def checkpoint_and_connect(api_base: str, db_path: str) -> duckdb.DuckDBPyConnection:
    try:
        requests.get(f"{api_base}/state/checkpoint", timeout=5).raise_for_status()
    except requests.RequestException as e:
        print(f"Warning: checkpoint failed ({e}). Reading DB as-is (WAL may be incomplete).")
    return duckdb.connect(db_path, read_only=True)
```

Uses `requests` (consistent with other scripts in `scripts/`).

**Report sections:**

#### 1. Full Prediction Funnel (per symbol)
Primary source: `predict_evaluations` (if table exists and has rows for `run_id`).
Fallback source: `account_risk_allocator_events` (risk layer only).

With `predict_evaluations`: total evaluations → `preselected_exec=1` (cleared threshold) → `selected_exec=1` (cleared risk + dedup) → became trades (join to `trades`). Shows threshold miss rate explicitly.

With fallback: count of `ADMITTED` vs `BLOCKED` from `account_risk_allocator_events`. Note in report: "predict_evaluations not populated for this session — sub-threshold misses not visible. Re-run after Phase 1 schema extension." Also note: `account_risk_allocator_events` has no `run_id` column, so fallback results span all sessions in the DB — warn the user if multiple run IDs are present in `trades`.

#### 2. Score Distribution (per symbol)
Primary source: `predict_evaluations.pred_prob` (all evaluations).
Fallback: `audit_logs.pred_prob` (admitted only, with note).

Percentile breakdown (p25 / p50 / p75 / p90 / p95) alongside `threshold`. If p99 < threshold with `predict_evaluations` populated, models are not generating confident predictions on live data.

#### 3. Block Reason Breakdown (per symbol)
Source: `predict_evaluations.threshold_block_reason` and `predict_evaluations.risk_block_reason` (when available).
Fallback: `account_risk_allocator_events.block_reason` for risk layer. Note that threshold-enforcement blocking (ROLLING_HISTORY_GAP, SCHEDULE_EXPIRED) is only visible in server logs when using fallback.

Counts of each distinct block reason value.

#### 4. Trade Outcomes (per symbol)
Source: `trades WHERE run_id = ?`.

Win rate, closed trade count, average winner pips, average loser pips, total P&L pips, `close_reason` breakdown. Answers whether quality loss is from oversized losers or undersized winners.

---

### Script 2: `scripts/diagnose_live_replay.py`

Offline model inference against recent parquet tick bars. Scores every bar — including sub-threshold ones — without touching the live server or opening trades. Provides full score visibility for the current live session where `predict_evaluations` is not yet populated.

**CLI:**
```
python scripts/diagnose_live_replay.py \
    --ticks-dir /Users/danielfisher/Desktop/dukascopy_ticks \
    --models-dir models/oco \
    --governance-dir configs/research/governance/oco \
    --model-month 2026-02 \
    --lookback-months 1 \
    --out data/analysis/live_replay_report.md
```

**Inference pipeline** (all offline, no server calls):

1. **Load ticks**: for each symbol, load parquet files for the most recent `--lookback-months` from `ticks-dir/<SYMBOL>/` (e.g. `EURUSD_202603_ticks.parquet`). Columns: `timestamp, bid, ask, mid, spread, log_return`.

2. **Build 100-tick bars via vectorised Polars** (do NOT use `TickAggregator` — constructing 2M+ `IncomingTick` Pydantic objects is impractical):
   - Group by `row_number // 100`
   - `open` = first `bid`, `high` = max `bid`, `low` = min `bid`, `close` = last `bid`
   - `spread` = mean `ask - bid` over the bar
   - `hl_first` = +1 if `argmax(bid) < argmin(bid)`, -1 if reversed, 0 if tied
   - `hl_pos_frac` = `(argmin(bid) - argmax(bid)) / 99`
   - `tick_volume` = count of ticks in the group (`pl.len()`); drop any trailing partial bar with fewer than 100 ticks
   - `timestamp` = first tick's timestamp, `close_ts` = last tick's timestamp

3. **Load states**: for each symbol, read `governance-dir/<symbol_lower>_oco_live_lock.json`, extract `state_universe.rows`. Each row has `bar_ticks`, `horizon`, `barrier_pips`, `state_id`.

4. **Compute features**: for each `(symbol, state)` pair, call `compute_feature_matrix_from_bars(bars_df, symbol=symbol, bar_ticks=100, horizon=state["horizon"], barrier_pips=state["barrier_pips"])` from `src/behemoth/core/features.py`. Requires 289 bars minimum (full precision); skip earlier bars.

5. **Load model**: `catboost.CatBoostClassifier.load_model(f"{models_dir}/{SYMBOL}_model_{model_month}.cbm")`.

6. **Load threshold**: read `models/oco/<SYMBOL>_model_<month>.json`, field `threshold_schedule` (dict keyed by `YYYY-MM-DD`). For each bar, look up threshold by `close_ts.date()`, falling back to `threshold_exec` if the date is not in the schedule.

7. **Record per bar**: `close_ts`, `state_id`, `pred_prob`, `threshold`, `selected = pred_prob >= threshold`, `gap = threshold - pred_prob`.

Results are reported per `(symbol, state_id)` pair throughout all sections below.

**Report sections:**

#### 1. Full Score Distribution (per symbol, per state_id)
Percentile breakdown (p25 / p50 / p75 / p90 / p95 / p99) of ALL `pred_prob` values, alongside threshold. If p99 < threshold, the model is not generating confident predictions on current market data regardless of threshold level.

#### 2. Near-Miss Table (per symbol, per state_id)
Top 10 bars where `pred_prob < threshold` but gap was smallest. Columns: close_ts, state_id, pred_prob, threshold, gap. Answers: "how close are we to firing?"

#### 3. Threshold Sensitivity Sweep (per symbol, per state_id)
At thresholds 0.50 / 0.55 / 0.60 / 0.65 / 0.70: trade count and implied frequency per 100 bars. Lets you see whether the current threshold is calibrated sensibly against actual live score distribution.

#### 4. Score Drift Over Time (per symbol)
Rolling 50-bar average `pred_prob` across all states. If scores trend downward, live market regime may have diverged from training data (model stale or regime shift).

---

## Data Sources

| Data | Source |
|------|--------|
| Full prediction funnel (future runs) | `predict_evaluations` in `live_state.db` |
| Risk blocking events (current session fallback) | `account_risk_allocator_events` in `live_state.db` |
| Admitted prediction scores (current session fallback) | `audit_logs` in `live_state.db` |
| Trade outcomes | `trades` in `live_state.db` |
| All bar scores for current session | Offline inference from parquet + `.cbm` models |

---

## Testing

**Phase 1** (`tests/test_state_predict_evaluations.py` or added to `tests/test_account_risk.py`):
- In-memory DuckDB via StateManager
- `log_predict_evaluation` with all gate combinations (preselected=0, preselected=1/selected=0, preselected=1/selected=1)
- Assert rows written correctly; assert `audit_logs` unaffected

**Phase 2** — follows the `_make_synthetic_db` pattern from `tests/test_diagnose_live_performance_gap.py`.

`tests/test_diagnose_live_audit.py`:
- Synthetic DuckDB with `predict_evaluations`, `audit_logs` (9 columns, `threshold` not `threshold_exec`), `account_risk_allocator_events` (no `run_id`), `trades`
- Assert funnel counts when `predict_evaluations` is populated vs fallback behaviour when it is absent
- Assert score percentiles, block reason counts, P&L stats

`tests/test_diagnose_live_replay.py`:
- Construct a bar-level DataFrame directly (≥289 rows) — do not go through raw ticks or `TickAggregator`, which would require 28,900+ ticks to clear warmup
- Use a synthetic CatBoost model fixture with known weights (or mock `predict_proba`) so score outputs are deterministic
- Assert score distribution output, near-miss ordering, sensitivity sweep counts at known thresholds

---

## Files Created

```
scripts/diagnose_live_audit.py
scripts/diagnose_live_replay.py
tests/test_diagnose_live_audit.py
tests/test_diagnose_live_replay.py
tests/test_state_predict_evaluations.py
```

## Files Modified

```
src/behemoth/runtime/state.py   — add predict_evaluations DDL to _SCHEMA_SQL, add log_predict_evaluation()
src/behemoth/api/server.py      — call log_predict_evaluation() for every candidate after all gates
```
