# Live Diagnostic Scripts Design

**Date:** 2026-03-25
**Status:** Approved

## Problem

The live JForex system is accumulating bars (327–672 per symbol) but generating too few trades and the trades that do fire are net negative. Two failure modes need diagnosing:

1. **Trade frequency** — EURUSD has 672 bars and zero trades; other symbols have 1–3 trades each. Expected win rates (from WFO eval) are 59–72%.
2. **Trade quality** — the 8 closed trades are all net negative (combined ≈ -17.7 pips).

## Design Constraint: Current DB Schema Visibility

A critical architectural fact shapes both scripts:

- **`audit_logs`** only records predictions where `selected_exec == 1` after all gates (threshold + risk + deduplication). Sub-threshold evaluations are **not persisted**.
- **`account_risk_allocator_events`** only records events where `preselected_exec == 1` (threshold was cleared). Risk-layer visibility only. No `run_id` column — filtering by run must use a join or candidate_uid match.
- Therefore, frequency diagnosis from the DB alone is **partial**: we can see risk blocking but not threshold blocking.

This drives the split: `diagnose_live_audit.py` analyses what the DB records; `diagnose_live_replay.py` does offline model inference directly against parquet bars to score every bar, including sub-threshold ones.

## Approach

Two focused scripts. No shared module — each embeds the lightweight functions it needs.

No live server writes during diagnosis. The replay script loads models and parquet data directly — it does not call `/predict`, so no trades are opened.

## Script 1: `scripts/diagnose_live_audit.py`

Checkpoints the DB, opens it read-only, and reports on what has actually been recorded.

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

### 1. Risk Gate Funnel (per symbol)
Source: `account_risk_allocator_events`.

Per symbol: count of `ADMITTED` vs `BLOCKED` events and the distinct `block_reason` values. This shows how many threshold-clearing predictions were subsequently blocked by the risk allocator.

Note in report: "Sub-threshold evaluations are not persisted in the current schema. Frequency analysis for scores below threshold requires the offline replay script."

### 2. Admitted Score Distribution (per symbol)
Source: `audit_logs` (column: `threshold`, not `threshold_exec`).

Percentile breakdown of `pred_prob` (p25 / p50 / p75 / p90 / p95) alongside `threshold` for admitted predictions only. Useful for understanding whether admitted predictions are uniformly strong or just barely over the bar.

### 3. Risk Block Reason Breakdown (per symbol)
Source: `account_risk_allocator_events.block_reason`.

Counts of each distinct block reason. Note in report: "Threshold-enforcement blocking (e.g. ROLLING_HISTORY_GAP, SCHEDULE_EXPIRED) is only visible in server logs — these rows never reach the risk allocator."

### 4. Trade Outcomes (per symbol)
Source: `trades WHERE run_id = ?`.

Win rate, closed trade count, average winner pips, average loser pips, total P&L pips, and `close_reason` breakdown. Answers whether quality loss is from oversized losers or undersized winners.

## Script 2: `scripts/diagnose_live_replay.py`

Offline model inference against recent parquet tick bars. Scores every bar — including sub-threshold ones — without touching the live server or opening trades.

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

6. **Load threshold**: read `models/oco/<SYMBOL>_model_<month>.json`, field `threshold_schedule` (dict keyed by `YYYY-MM-DD`). For each bar, look up threshold by `close_ts.date()`, falling back to `threshold_exec` if the date is not in the schedule. Do not use the governance directory for threshold values.

7. **Record per bar**: `close_ts`, `state_id`, `pred_prob`, `threshold`, `selected = pred_prob >= threshold`, `gap = threshold - pred_prob`.

Results are reported per `(symbol, state_id)` pair throughout all sections below.

**Report sections:**

### 1. Full Score Distribution (per symbol, per state_id)
Percentile breakdown (p25 / p50 / p75 / p90 / p95 / p99) of ALL `pred_prob` values, alongside threshold. If p99 < threshold, the model is not generating confident predictions on current market data regardless of threshold level.

### 2. Near-Miss Table (per symbol, per state_id)
Top 10 bars where `pred_prob < threshold` but gap was smallest. Columns: close_ts, state_id, pred_prob, threshold, gap. Answers: "how close are we to firing?"

### 3. Threshold Sensitivity Sweep (per symbol, per state_id)
At thresholds 0.50 / 0.55 / 0.60 / 0.65 / 0.70: trade count and implied frequency per 100 bars. Lets you see whether the current threshold is calibrated sensibly against actual live score distribution.

### 4. Score Drift Over Time (per symbol)
Rolling 50-bar average `pred_prob` across all states. If scores trend downward, live market regime may have diverged from training data (model stale or regime shift).

## Data Sources

| Data | Source |
|------|--------|
| Risk blocking events | `account_risk_allocator_events` in `live_state.db` |
| Admitted prediction scores | `audit_logs` in `live_state.db` |
| Trade outcomes | `trades` in `live_state.db` |
| All bar scores (sub-threshold) | Offline inference from parquet + `.cbm` models |

## Testing

Follows the `_make_synthetic_db` pattern from `tests/test_diagnose_live_performance_gap.py`.

`tests/test_diagnose_live_audit.py`:
- Synthetic DuckDB with `audit_logs` (9 columns, `threshold` not `threshold_exec`), `account_risk_allocator_events` (no `run_id`), `trades`
- Assert funnel counts, score percentiles, block reason counts, P&L stats

`tests/test_diagnose_live_replay.py`:
- Construct a bar-level DataFrame directly (≥289 rows) and call `compute_feature_matrix_from_bars()` — do not go through raw ticks or `TickAggregator` in tests, which would require 28,900+ synthetic ticks to clear warmup
- Use a synthetic CatBoost model fixture with known weights (or mock `predict_proba`) so score outputs are deterministic
- Assert score distribution output, near-miss ordering, sensitivity sweep counts at known thresholds

## Files Created

```
scripts/diagnose_live_audit.py
scripts/diagnose_live_replay.py
tests/test_diagnose_live_audit.py
tests/test_diagnose_live_replay.py
```

No existing files modified.
