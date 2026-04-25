# Warmup Historical Replay — Design

- **Status:** Approved for planning
- **Date:** 2026-04-24
- **Scope:** Fix `/predict/warmup` to replay model across all buffered bars; remediate the running live system; add guardrails against silent regression.
- **Out of scope:** Re-evaluating the `threshold_seed` + `warmup` + `jforex_live` calibration strategy; tuning `exec_q`, `rolling_threshold_days`, or `rolling_threshold_min_history`; changes to governance locks or threshold JSON artifacts.

## Problem

`get_rolling_threshold()` at `src/behemoth/runtime/state.py:706` computes the live execution threshold as the `exec_q` quantile of `audit_logs.pred_prob` over a `rolling_threshold_days` window. For USDJPY the live threshold has settled at ~0.771 vs the WFO static threshold of 0.686 — a 8.5 pp gap that results in 5/96 signal executions, all four closed trades losses (z = −3.22).

Tracing the `audit_logs` population against the running `live_state.db` reveals three data sources in the rolling window:

| Source (`run_id`) | Population method | USDJPY rows | p90 pred_prob | Unique pred_prob values per candidate |
|---|---|---:|---:|---:|
| `threshold_seed` | Offline Dukascopy replay, 20 days | 423 | 0.786 | ~400 |
| `warmup` | `/predict/warmup` endpoint | 300 | 0.699 (constant) | **1** |
| `jforex_live` | Live evaluations | 96 | 0.755 | ~90 |

The warmup rows are flat — a single pred_prob value stamped 300 times onto historical timestamps. Every other symbol shows the same pattern (1 unique value per candidate). The bug is at `src/behemoth/api/server.py:3396`:

```python
# Compute features once from current buffer state
for cand in contract.candidates:
    feats = _state.compute_features(...)       # features from ONE bar (latest)
    pred_prob = float(model.predict_proba(arr)[:, 1][0])  # ONE inference
    for (close_ts_val,) in rows:               # loops ALL buffered bars
        _state.log_audit_event(
            pred_prob=pred_prob,               # same value written every iteration
            close_ts=close_ts_bar,             # historical timestamps
            ...
        )
```

The endpoint docstring says "Score buffered bars through the model to seed audit_logs for rolling threshold" — the implementation computes features and pred_prob from the *current* buffer state once and stamps that single probability across every historical `close_ts`. The warmup data is therefore useless for calibration and fails to counter-balance the narrow-window `threshold_seed` distribution, which is what is dominating the rolling quantile.

## Goals

1. Make `/predict/warmup` replay the model across every buffered bar, producing one pred_prob per bar per candidate.
2. Remediate the running live system without a DB migration or schema change — restart the API and the fixed endpoint self-heals.
3. Add validation that makes silent regressions of this shape impossible to ship again.

## Non-goals

- Revisiting the three-source audit_logs design (threshold_seed + warmup + jforex_live).
- Changing the offline `threshold_seed` logic or window.
- Changing governance locks, threshold JSON, `exec_q`, `rolling_threshold_days`, or `rolling_threshold_min_history`.
- Changing the `/predict/warmup` URL, request schema, or caller contract beyond the stats added to the response body.

## Design

### Semantic change

`/predict/warmup` becomes a **snapshot operation**, idempotent per `(symbol, run_id)`. Every call purges prior rows for that pair and rewrites them from the current buffer. Contract becomes: "warmup is a snapshot, not an append."

### Surface changes

Two files touched, no new endpoints, no new files:

| File | Change |
|---|---|
| `src/behemoth/api/server.py` | Rewrite the body of `predict_warmup()` (lines 3350–3424) to replay all buffered bars; add per-candidate distribution stats in the response body; hard-fail on degenerate distributions. |
| `src/behemoth/runtime/state.py` | Add `purge_audit_events(symbol, run_id) -> int` helper used inside the warmup transaction. Optionally extend `get_rolling_threshold()` to accept a `baseline_threshold` argument for drift logging. |

The existing `log_audit_event_batch()` is reused. `run_jforex_live.py:482` is untouched — it already calls the endpoint once per symbol at startup; the idempotent semantics mean the existing flow does the right thing after the fix lands.

### Algorithm

For the given symbol:

1. **Preconditions** (unchanged): reject with 503 if `_state is None`; reject with 422 if no candidates or no model; return 201 with `audit_events_written: 0, skipped_reason: "insufficient_bars:..."` if the buffer has fewer than `full_warmup_bars` rows. Preconditions run before any purge — on failure, prior rows are untouched.
2. Read all rows for the symbol from `tick_bars` into a DataFrame (existing query at `server.py:3383`).
3. For each candidate `c`:
   - `matrix = compute_feature_matrix_from_bars(df, horizon=c.horizon, barrier_pips=c.barrier_pips, ...)` — existing function at `src/behemoth/core/features.py:137`.
   - `valid = matrix.dropna()` — drops the first ~288 bars that fall inside the feature builder's own rolling warmup window.
   - `probs = model.predict_proba(valid.values)[:, 1]` — one batch inference call per candidate.
   - Build a list of `(close_ts, pred_prob, features_json)` tuples aligned by row index.
4. **Per-candidate sanity check** before writing:
   - If any candidate satisfies `len(probs) >= MIN_VALID_ROWS (30)` and `nunique(probs) < MIN_UNIQUE_PROBS (10)` → fail the entire request with `HTTPException(500, "warmup replay produced degenerate distribution for {candidate_uid}: ...")`. The transaction is never opened; prior rows for all candidates of this symbol remain untouched. One bad candidate fails the whole symbol — partial writes are never surfaced.
5. **Atomic swap** inside a single DuckDB transaction:
   - `DELETE FROM audit_logs WHERE symbol=? AND run_id=?` — purge scope limited to `(symbol, run_id)`; `threshold_seed` and `jforex_live` rows are never touched.
   - `log_audit_event_batch(events)` — batch insert.
   - Commit.
6. Respond with enriched JSON:

```json
{
  "ok": true,
  "symbol": "USDJPY",
  "audit_events_purged": 300,
  "audit_events_written": 12,
  "stats": {
    "oco|USDJPY|1000|h6|oco_first_touch_clean__all__k2": {
      "n": 12,
      "unique_values": 12,
      "p10": 0.48, "p50": 0.67, "p90": 0.71, "p100": 0.83
    }
  }
}
```

### Concurrency

The `DELETE` + batch `INSERT` run in a single DuckDB transaction. A concurrent `/predict` call reading `audit_logs` via `get_rolling_threshold()` sees either the pre-fix state or the post-fix state, never a partial mix. Two concurrent warmup calls for the same symbol serialise; the second sees the clean post-commit state and re-purges + re-inserts safely.

## Edge cases

| Case | Behavior |
|---|---|
| `compute_feature_matrix_from_bars()` returns `None` for a candidate | Skip that candidate, log warning, continue with others. Matches current no-op semantics for `feats is None`. |
| Matrix returned but all rows are NaN after `.dropna()` for every candidate | Still run the DELETE (snapshot semantics). Respond `audit_events_written: 0, skipped_reason: "no_valid_feature_rows"`. |
| Matrix has partial NaN rows (first ~288 bars) | Drop them silently — expected and correct. |
| `model.predict_proba` raises | Transaction rolls back; prior rows preserved; respond 500 with error detail. |
| Two concurrent `/predict/warmup` calls for the same symbol | DuckDB serialises; both complete safely, final state reflects whichever commits last. |
| Caller passes `run_id` other than `"warmup"` | Purge scope is `(symbol, run_id)` only; other run_ids are never affected. |
| Per-candidate sanity check trips (degenerate distribution) | Transaction not started; prior rows preserved; respond 500 with the offending candidate's stats. |

## Validation and guardrails

### Layer 1 — Inline sanity check (hard fail)

The per-candidate check in step 4 above. Constants: `MIN_VALID_ROWS = 30`, `MIN_UNIQUE_PROBS = 10`. If a future refactor reintroduces the flat-distribution bug, warmup calls fail loudly instead of writing bad data.

### Layer 2 — Rolling threshold drift warning at `/predict` time

`get_rolling_threshold()` gains an optional `baseline_threshold` argument (the static `threshold_exec` from the threshold JSON). The caller at `server.py:3021` passes `thr_cfg["threshold_exec"]`. Every time a rolling threshold is computed, compare `abs(rolling - baseline)` against `THRESHOLD_DRIFT_WARN_PP (0.05)`:

- If within band: increment `behemoth_rolling_threshold_drift_total{symbol, candidate, state="ok"}`.
- If beyond band: increment `behemoth_rolling_threshold_drift_total{symbol, candidate, state="drift"}` and emit one `logger.warning` line per evaluation.

The rolling threshold still takes effect either way — this is an alarm, not a gate. Labeling every evaluation (ok or drift) means the drift ratio is queryable from `/metrics` without requiring warmup to succeed first. Rationale: aligns with the recent `fail fast on live artifact drift` pattern, but keeps live-trading drift visible as an ops signal rather than a hard block (drift may reflect legitimate market-regime variation).

### Layer 3 — Diagnostic report extension

Add `_rolling_threshold_integrity_section(con, run_id)` to `scripts/diagnose_live_performance_gap.py`. Per symbol and candidate it reports:

- Row counts in the rolling window broken down by `run_id`.
- `nunique(pred_prob)` per `run_id` — flat-distribution regressions surface immediately as `unique_values=1`.
- `quantile(pred_prob, 0.9)` per `run_id` and combined.
- `combined_p90 - static_threshold_exec` deviation, with a ⚠️ marker when it exceeds the configured drift band.

## Tests

New tests in `tests/test_api_server.py`:

1. **`test_warmup_writes_varied_pred_probs_per_bar`** — synthetic buffer of `full_warmup_bars + 30` varied bars, POST warmup, assert the resulting `audit_logs.pred_prob` rows have `nunique() >= 10` and `close_ts` values map 1-to-1 to input bars by count. **Direct regression test for the bug being fixed.**
2. **`test_warmup_is_idempotent_and_purges_prior`** — POST warmup twice with different buffers; assert second call's `audit_events_purged` equals first call's `audit_events_written`; assert final state reflects only the second buffer.
3. **`test_warmup_refuses_degenerate_distribution`** — patch the model to return a constant probability; assert the endpoint returns 500 and does *not* purge existing rows.

New test in `tests/test_diagnose_live_performance_gap.py`:

4. **`test_rolling_threshold_integrity_section_detects_flat_warmup`** — synthetic DB with flat warmup rows; assert the diagnostic script flags `unique_values=1` in the integrity section.

The two existing tests at `tests/test_api_server.py:3180-3208` stay — they remain valid status-code coverage, but they are no longer the only coverage.

## Rollout

1. Implement and merge via PR from this worktree (`fix/warmup-historical-replay`).
2. Restart the live API server. `run_jforex_live.py` already calls `/predict/warmup` for each symbol on startup; the fixed endpoint produces real distributions and purges the 300 flat rows per candidate.
3. Operator verification after restart (manual or via `scripts/diagnose_live_performance_gap.py`):
   - Per symbol and candidate: `warmup.unique_values >= 10` — proves the replay ran correctly.
   - Combined p90 within ~5 pp of each symbol's static WFO threshold — proves the rolling threshold is calibrated to the expected band (USDJPY target ~0.69, not ~0.77).
4. No governance lock or threshold JSON edits. No schema migration. No data migration beyond the endpoint's own idempotent purge.

## Acceptance

- All four new tests pass; existing warmup tests still pass.
- On the running live system post-restart, per symbol/candidate:
  - `warmup.unique_values >= 10` — proves the replay executed correctly.
  - Combined rolling p90 within `THRESHOLD_DRIFT_WARN_PP (0.05)` of the static `threshold_exec`. For USDJPY specifically, that means combined p90 ≤ 0.736 (static 0.686 + 0.05) — the current value ~0.771 fails this bound.
- `behemoth_rolling_threshold_drift_total{state="ok"|"drift"}` visible per symbol/candidate via `/metrics`, with the `drift` counter at 0 for symbols whose rolling p90 is within band and non-zero for those that aren't.
