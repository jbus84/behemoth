# Diagnose GBPUSD Predict Slowdown Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Identify why the GBPUSD spotlight run hangs for >31 minutes (individual predict calls appear to take ~1–2 s each vs ~31 ms for EURUSD) while EURUSD completes in ~27 s total.

**Architecture:** Pure diagnostic — add timing probes, collect metrics, and verify hypotheses in cheapest-to-run order. No permanent code changes until the root cause is confirmed; all instrumentation can be added and removed in a single commit.

**Tech Stack:** Python `time.perf_counter`, `logging`, `pandas`, existing `StateManager` / `server.py` / `run_local_jforex_surrogate_matrix.py`.

---

## Context

| Metric | EURUSD | GBPUSD |
|--------|--------|--------|
| Tick rows (parquet) | 116,400 | 181,500 |
| Expected bars | ~1,164 | ~1,815 |
| Expected predict calls (after 289-bar warmup) | ~875 | ~1,526 |
| Elapsed | ~27 s | >31 min (60 s HTTP timeout hit) |
| Implied per-predict @ EURUSD rate | ~47 s | |
| Implied actual per-predict (31 min / 1526) | ~31 ms | ~1.2 s |

The 56 % extra ticks explain at most a ~2× wall-clock difference. The observed >70× slowdown (27 s → >31 min) means something degrades *per-call* as the run progresses. There are four plausible root causes (see Task 1).

---

## File Map

| File | Role |
|------|------|
| `scripts/run_local_jforex_surrogate_matrix.py` | Orchestrator — controls server startup and per-symbol Gradle run |
| `src/behemoth/api/server.py` | FastAPI server — `/predict` and `/ticks/batch` endpoints |
| `src/behemoth/runtime/state.py` | `StateManager` — DuckDB reads/writes and `bar_count()` |
| `data/analysis/spotlight_ticks/{SYM}/spotlight_ticks.parquet` | Tick input files |
| `configs/research/governance/oco_history_dukascopy_candidate/2025-07/{SYM}/` | Locked governance configs used by server |

---

## Hypotheses (ranked by likelihood)

| ID | Hypothesis | Cost to test |
|----|-----------|-------------|
| **H-B** | `bar_count()` is called **once per tick** (181,500× for GBPUSD) inside `_ingest_tick_internal` and `_build_drop_response` — cumulative DuckDB overhead dominates and grows with bar count | Static code read + timing — 10 min |
| **H-A** | `bar_count()` is also O(n) on a growing `raw_ticks` table (181,500 rows if `record_raw_ticks=true`) | Grep config — 5 min |
| **H-C** | The `tick_bars` prune keeps the table capped at ~699 rows between prune cycles, but the DuckDB full-scan for `bar_count` still degrades as the table grows from 0→699 rows repeatedly | Trace row count over time — 15 min |
| **H-D** | GBPUSD's historical prediction candidate index has far more entries, making the cursor scan in `_apply_historical_prediction_universe_gate` much slower | Count entries per symbol — 5 min |
| **H-E** | GBPUSD triggers the tick-batch retry path more often (timeout → 2 retries × 250 ms backoff → single-tick fallback), multiplying HTTP round-trips | Check artifact writer output — 5 min |

> **Note on H-C:** The `tick_bars` prune fires at `(idx + 1) % 100 == 0` using `_row_counters[key]` (per symbol+bar_ticks key, not global). It deletes `row_id < current_idx - 600`. Until 700 rows are inserted, no rows are ever deleted. After that, the table is bounded at ~699 rows. The table does *not* grow to 1,815 rows. H-C is a weaker candidate than H-B.

---

## Task 1: Cheap static checks (no code changes)

**Files:**
- Read: `src/behemoth/api/server.py` (lines 337–340, 3179–3216)
- Read: `scripts/run_local_jforex_surrogate_matrix.py`
- Read: `data/analysis/spotlight_ticks/{SYM}/spotlight_ticks.parquet`
- Read: `configs/research/governance/oco_history_dukascopy_candidate/2025-07/{SYM}/`

- [ ] **Step 1: Verify `record_raw_ticks` is off by default**

  In `server.py` around line 337:
  ```python
  record_raw_ticks: bool = Field(
      default_factory=lambda: str(os.getenv("BEHEMOTH_RECORD_RAW_TICKS", "false")).strip().lower()
      in {"1", "true", "yes", "y"}
  )
  ```
  and line 3179:
  ```python
  if _config.record_raw_ticks and _is_historical_mode():
      _state.record_raw_tick(tick, source="historical_backtest")
  ```
  Confirm the env var is not set in `run_local_jforex_surrogate_matrix.py` or the Makefile.

  Run:
  ```bash
  grep -r "BEHEMOTH_RECORD_RAW_TICKS" Makefile scripts/ configs/ .env* 2>/dev/null
  ```
  Expected: **no output** (the flag is off). If it appears, this alone explains H-A — skip to Task 4 fix.

- [ ] **Step 2: Count bars per symbol in the parquet tick files**

  Run:
  ```bash
  uv run python -c "
  import pandas as pd
  for sym in ['EURUSD', 'GBPUSD', 'USDJPY', 'USDCHF', 'AUDUSD', 'USDCAD']:
      try:
          df = pd.read_parquet(f'data/analysis/spotlight_ticks/{sym}/spotlight_ticks.parquet')
          n_ticks = len(df)
          est_bars = n_ticks // 100
          est_predict = max(0, est_bars - 289)
          print(f'{sym}: {n_ticks:>8} ticks  ~{est_bars:>5} bars  ~{est_predict:>5} predicts')
      except FileNotFoundError:
          print(f'{sym}: not found')
  "
  ```
  Expected output (approximate):
  ```
  EURUSD:   116400 ticks  ~ 1164 bars  ~  875 predicts
  GBPUSD:   181500 ticks  ~ 1815 bars  ~ 1526 predicts
  ```
  Record the actual numbers. A ~70 % predict-count difference still can't explain >70× slowdown alone — confirms something degrades per-call.

- [ ] **Step 3: Count locked prediction entries per symbol**

  Run:
  ```bash
  uv run python -c "
  from pathlib import Path
  import json, os
  base = Path('configs/research/governance/oco_history_dukascopy_candidate/2025-07')
  for sym in ['EURUSD', 'GBPUSD']:
      d = base / sym
      if not d.exists():
          print(f'{sym}: dir not found')
          continue
      for f in sorted(d.iterdir()):
          print(f'{sym}/{f.name}:', end=' ')
          if f.suffix in {'.json', '.yaml', '.yml'}:
              try:
                  data = json.loads(f.read_text()) if f.suffix == '.json' else f.read_text()
                  print(f'{len(str(data))} chars')
              except Exception as e:
                  print(e)
          else:
              print(f'{f.stat().st_size} bytes')
  "
  ```

- [ ] **Step 4: Count rows in the locked predictions parquet (the candidate universe)**

  ```bash
  uv run python -c "
  from pathlib import Path
  import pandas as pd
  # Find predictions parquet paths referenced in the lock configs
  for sym in ['EURUSD','GBPUSD']:
      base = Path('configs/research/governance/oco_history_dukascopy_candidate/2025-07') / sym
      for f in base.glob('*.json'):
          import json
          cfg = json.loads(f.read_text())
          ppath = cfg.get('predictions_path','') or cfg.get('model_binding',{}).get('predictions_path','')
          if ppath and Path(ppath).exists():
              df = pd.read_parquet(ppath)
              print(f'{sym} {f.name}: {len(df)} rows, candidates={df[\"candidate_uid\"].nunique() if \"candidate_uid\" in df.columns else \"?\"}, cols={list(df.columns)[:5]}')
  "
  ```
  If GBPUSD has significantly more prediction rows than EURUSD, that narrows to H-D.

- [ ] **Step 5: Commit findings as a comment in the plan**

  No code commit needed. Record the numbers discovered and which hypotheses are still live.

---

## Task 2: Instrument `bar_count()` call frequency

**Files:**
- Modify: `src/behemoth/runtime/state.py` (add counter)
- Modify: `src/behemoth/api/server.py` (log counter at end of tick batch)

The `bar_count()` method is called from many places. The hot-path call sites (contributing the most calls) are:

| Call site | Frequency |
|-----------|-----------|
| `_ingest_tick_internal()` line ~3216 | **once per accepted tick** (181,500× for GBPUSD) |
| `_build_drop_response()` line ~3087 | **once per dropped tick** (count unknown; drops inflate the total) |
| `/ticks/batch` response line ~3323 | once per 200-tick batch (~908× for GBPUSD) |
| `_check_warmup()` | once per predict call per candidate (~1,526× for GBPUSD) |
| `compute_features()` | once per predict call |
| `compute_regime_quantiles()` | once per predict call |
| `_monitor_ledger()` background loop | once per ~60 s (negligible) |

The dominant contributor is `_ingest_tick_internal()` — 181,500 DuckDB round-trips for GBPUSD vs 116,400 for EURUSD.

- [ ] **Step 1: Add a call counter to `StateManager`**

  In `state.py`, add to `__init__`:
  ```python
  self._bar_count_calls: int = 0
  self._bar_count_ns: int = 0
  ```
  Wrap `bar_count()`:
  ```python
  def bar_count(self, symbol: str, bar_ticks: int) -> int:
      import time
      t0 = time.perf_counter_ns()
      r = self._con.execute(
          "SELECT COUNT(*) FROM tick_bars WHERE symbol = ? AND bar_ticks = ?",
          [symbol.upper(), bar_ticks],
      ).fetchone()
      self._bar_count_ns += time.perf_counter_ns() - t0
      self._bar_count_calls += 1
      return int(r[0]) if r else 0
  ```

- [ ] **Step 2: Log the cumulative counter inside `bar_count()` itself**

  In `state.py`, inside `bar_count()` after updating the counters, add:
  ```python
  if self._bar_count_calls % 10000 == 0 and self._bar_count_calls > 0:
      import logging as _logging
      _logging.getLogger("behemoth.state").warning(
          "bar_count perf: calls=%d total_ms=%.1f mean_us=%.1f",
          self._bar_count_calls,
          self._bar_count_ns / 1e6,
          self._bar_count_ns / max(1, self._bar_count_calls) / 1e3,
      )
  ```
  This fires approximately every 10,000 calls regardless of which endpoint triggered them.

- [ ] **Step 3: Run a quick GBPUSD-only test**

  In a separate terminal, start the server (follow the normal `make local-jforex-parity-spotlight` process for a single symbol), then:
  ```bash
  SYMBOLS=GBPUSD make local-jforex-parity-spotlight 2>&1 | tail -50
  ```
  Watch server logs for `bar_count perf` lines. Record mean_us at 10k, 50k, 100k, 150k calls.

  If mean_us is growing (e.g. 0.05 µs at 10k → 0.5 µs at 150k), it confirms DuckDB scan degradation (H-B/H-C).

- [ ] **Step 4: Check tick_bars table size at various bar counts**

  Add a one-time log at predict time:
  ```python
  # In server.py predict endpoint, just before compute_features:
  if _state is not None:
      actual_count = _state._con.execute(
          "SELECT COUNT(*) FROM tick_bars WHERE symbol = ? AND bar_ticks = 100", [sym]
      ).fetchone()[0]
      logger.warning("tick_bars actual row count for %s: %d", sym, actual_count)
  ```
  Log every 100 predict calls. If this grows beyond 700 (the expected prune ceiling), H-C is confirmed.

- [ ] **Step 5: Revert instrumentation, commit findings**

  ```bash
  git stash  # or revert the two files
  ```
  Record the timing numbers in the plan as comments.

---

## Task 3: Instrument predict endpoint latency

**Files:**
- Modify: `src/behemoth/api/server.py` (`predict` endpoint)

- [ ] **Step 1: Add per-phase timing to `predict`**

  At the top of the `predict` async function, add:
  ```python
  import time as _time
  _t_predict_start = _time.perf_counter()
  ```
  After `close_ts = ...`:
  ```python
  _t_close_ts = _time.perf_counter()
  ```
  After `_apply_historical_prediction_universe_gate(...)`:
  ```python
  _t_gate = _time.perf_counter()
  ```
  After the `base_features_by_ticks` loop (compute_features calls):
  ```python
  _t_features = _time.perf_counter()
  ```
  After `_build_predictions(...)`:
  ```python
  _t_build = _time.perf_counter()
  total_ms = (_time.perf_counter() - _t_predict_start) * 1000
  if total_ms > 500:  # log slow calls only
      logger.warning(
          "SLOW predict %s: total=%.0fms close_ts=%.1fms gate=%.1fms features=%.1fms build=%.1fms",
          sym,
          total_ms,
          (_t_close_ts - _t_predict_start) * 1000,
          (_t_gate - _t_close_ts) * 1000,
          (_t_features - _t_gate) * 1000,
          (_t_build - _t_features) * 1000,
      )
  ```

- [ ] **Step 2: Run GBPUSD only and observe logs**

  ```bash
  SYMBOLS=GBPUSD make local-jforex-parity-spotlight 2>&1 | grep "SLOW predict"
  ```
  From the log output, identify which phase is slow:
  - `close_ts` slow → `get_latest_close_ts()` DuckDB query is slow
  - `gate` slow → historical prediction universe gate is slow (H-D)
  - `features` slow → `compute_features()` / `bar_count()` is slow (H-B/H-C)
  - `build` slow → CatBoost inference is slow

- [ ] **Step 3: Revert instrumentation**

  ```bash
  git stash
  ```

---

## Task 4: Fix based on findings

After Tasks 1–3 identify the root cause, apply the correct fix from the menu below. Only implement the fix that matches the confirmed hypothesis.

### Fix A: `bar_count()` called per-tick (H-B)

The `bar_count()` calls in the tick ingest path are cosmetic — the value is only returned in the HTTP response payload and is not used by the Java adapter for any logic. Replace all three hot-path call sites with `0`.

- [ ] **Step 1: Verify Java ignores bar_count in tick batch response**

  Note: confirm the Java source path exists before running grep:
  ```bash
  ls src/jforex/src/main/java/com/behemoth/jforex/runtime/dto/ 2>/dev/null | grep -i batch
  ```
  Then:
  ```bash
  grep -r "barCount\|getBarCount\|bar_count" src/jforex/src/main/java/ --include="*.java" 2>/dev/null
  ```
  A no-output result could mean "path not found" rather than "field unused" — confirm the path exists first.

- [ ] **Step 2: Apply fix to `server.py` — remove all 3 hot-path call sites**

  Three places to fix (search for `_state.bar_count` and replace the response-payload instances only):

  1. `_build_drop_response()` (~line 3087): `"bar_count": _state.bar_count(sym, 100)` → `"bar_count": 0`
  2. `_ingest_tick_internal()` (~line 3216): same
  3. `ingest_ticks_batch()` (~line 3323): same

  Do **not** touch `bar_count()` calls inside `compute_features()`, `compute_regime_quantiles()`, or `_check_warmup()` — those are correctness-critical.

- [ ] **Step 3: Run GBPUSD and confirm it completes in <2 minutes**

  ```bash
  SYMBOLS=GBPUSD make local-jforex-parity-spotlight 2>&1 | tail -20
  ```

- [ ] **Step 4: Run all symbols**

  ```bash
  make local-jforex-parity-spotlight 2>&1 | tail -30
  ```

- [ ] **Step 5: Commit**

  ```bash
  git add src/behemoth/api/server.py
  git commit -m "fix: remove per-tick bar_count() DuckDB query from tick ingest hot path"
  ```

### Fix B: `tick_bars` table grows unboundedly (H-C)

If the prune fires at `(idx + 1) % 100 == 0` but `idx` is the *inserted* row_id (not the count), and if multiple symbols share the same DuckDB connection, row_ids for different symbols are interleaved. The prune deletes rows by row_id threshold but row_ids may not be monotonic per-symbol. Verify:

```python
# Check if row_id is per-key or global
# In state.py append_bar():
key = f"{sym}_{bar.bar_ticks}"
idx = self._row_counters.get(key, 0)  # ← per (symbol, bar_ticks) key ✓
```

The counters *are* per (symbol, bar_ticks) key, so this should be fine. If H-C is confirmed by Task 2 Step 4, the fix is to add an explicit DuckDB index:

```python
# In _CREATE_SQL, after CREATE TABLE tick_bars:
CREATE INDEX IF NOT EXISTS idx_tick_bars_sym_ticks ON tick_bars (symbol, bar_ticks, row_id);
```

- [ ] **Step 1: Add index to `_CREATE_SQL`**

  In `state.py`, append to the `_CREATE_SQL` string after the `tick_bars` table definition.

- [ ] **Step 2: Run GBPUSD and confirm timing improvement**

- [ ] **Step 3: Commit**

  ```bash
  git add src/behemoth/runtime/state.py
  git commit -m "fix: add index on tick_bars(symbol, bar_ticks, row_id) to speed up bar_count queries"
  ```

### Fix C: Historical prediction cursor scan is slow (H-D)

If GBPUSD has many more historical prediction entries and the `bisect_left` scan over `ts_rows` (which is already sorted) is a bottleneck, add timing inside `_apply_historical_prediction_universe_gate` (Task 3 already exposes this via the `gate` phase).

The gate is already O(log n) per candidate via `bisect_left`. If it's still slow, the issue may be the number of candidates (C × log N where C is candidate count). Log candidate count:

```python
logger.warning("gate: %d candidates, %d candidates after gate, elapsed %.1fms", ...)
```

If C is large (>50), consider pre-filtering candidates before the gate.

### Fix D: Retry storm (H-E)

If the tick batch timeout is hitting `isRetriableTickBatchFailure`, Java retries 2× then falls back to individual ticks. Each individual tick is a separate HTTP round-trip — for a 200-tick batch that would be 200 extra requests per batch. With 908 batches for GBPUSD, that's 181,600 extra round-trips at ~1ms each = ~3 minutes.

To verify: search server logs for `mode=single_tick_fallback` in the artifact writer output:
```bash
find data/analysis/backtest_reconcile -name "*GBPUSD*" | xargs grep -l "single_tick_fallback" 2>/dev/null
```

Fix: Increase Java timeout or reduce batch size to prevent timeouts.

---

## Task 5: Verify all symbols complete and results are correct

- [ ] **Step 1: Run full pipeline after fix is applied**

  ```bash
  make local-jforex-parity-spotlight 2>&1 | tee /tmp/spotlight_run.log
  ```
  Expected: all 6 symbols complete without timeouts.

- [ ] **Step 2: Confirm parity summary CSVs are updated**

  ```bash
  ls -la data/analysis/backtest_reconcile/*parity_summary.csv
  ```

- [ ] **Step 3: Commit final state**

  ```bash
  git add data/analysis/backtest_reconcile/
  git commit -m "data: update parity summary CSVs after GBPUSD slowdown fix"
  ```
