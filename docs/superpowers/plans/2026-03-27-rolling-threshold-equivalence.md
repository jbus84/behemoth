# Rolling Threshold Equivalence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Align WFO and live rolling threshold computation so they produce identical 90th percentile values, with training prediction export, two-phase seeding, and stage 14 parity certification.

**Architecture:** Modify the WFO rolling loop to accumulate prior test-day predictions causally. Export training predictions as a parquet artifact alongside the model. Replace live seeding with two phases (training seed + gap replay). Remove schedule-first threshold lookup in live mode. Add a stage 14 threshold parity check.

**Tech Stack:** Python 3.12, NumPy, pandas, DuckDB, CatBoost, pytest, parquet

---

## File Structure

- Modify: `scripts/run_tick_opportunity_monthly_wfo.py` — accumulate test-day predictions in rolling loop; export training predictions parquet
- Modify: `src/behemoth/runtime/state.py` — add `seed_training_predictions()` bulk insert method
- Modify: `src/behemoth/api/server.py` — two-phase seeding endpoint; remove schedule-first threshold lookup
- Modify: `scripts/run_jforex_live.py` — pass training predictions path to seeding
- Modify: `scripts/freeze_oco_historical_governance.py` — add `train_predictions_path/sha256` and `model_valid_through` to lock JSON
- Modify: `scripts/validate_stage14_jforex_runtime_certification.py` — add `THRESHOLD_PARITY_PASS` check
- Test: `tests/test_monthly_wfo_threshold_causality.py` — extend with accumulation and export tests
- Create: `tests/test_threshold_seeding.py` — two-phase seeding and parity tests
- Create: `tests/test_model_expiry_guard.py` — month expiry block tests

### Task 1: Accumulate Test-Day Predictions in WFO Rolling Loop

**Files:**
- Modify: `scripts/run_tick_opportunity_monthly_wfo.py:298-365`
- Test: `tests/test_monthly_wfo_threshold_causality.py`

- [ ] **Step 1: Write the failing test for test-day accumulation**

```python
def test_rolling_threshold_accumulates_test_day_predictions() -> None:
    """After day D's threshold is computed, day D's test predictions
    should influence day D+1's threshold."""
    train_ts = pd.Series(
        pd.to_datetime(["2025-01-01T00:00:00Z", "2025-01-02T00:00:00Z"], utc=True)
    )
    train_p = np.array([0.3, 0.4], dtype=float)
    test_ts = pd.Series(
        pd.to_datetime(
            [
                "2025-01-03T00:00:00Z",
                "2025-01-04T00:00:00Z",
            ],
            utc=True,
        )
    )
    # Test day 1 has a very high prediction that should shift day 2's threshold
    test_p = np.array([0.95, 0.5], dtype=float)

    thr, src = _rolling_day_threshold_vector(
        train_ts=train_ts,
        train_p=train_p,
        test_ts=test_ts,
        test_p=test_p,
        q=0.9,
        lookback_days=5,
        min_history=1,
    )

    # Day 1 threshold: 90th percentile of [0.3, 0.4] = 0.39
    # Day 2 threshold: 90th percentile of [0.3, 0.4, 0.95] = 0.785
    # Without accumulation, day 2 would also be 0.39
    day1_thr = float(np.quantile([0.3, 0.4], 0.9))
    day2_thr = float(np.quantile([0.3, 0.4, 0.95], 0.9))
    assert np.isclose(thr[0], day1_thr), f"Day 1: {thr[0]} != {day1_thr}"
    assert np.isclose(thr[1], day2_thr), f"Day 2: {thr[1]} != {day2_thr}"
    assert src[0] == "rolling_history"
    assert src[1] == "rolling_history"
```

Add this test to `tests/test_monthly_wfo_threshold_causality.py` after the existing tests.

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_monthly_wfo_threshold_causality.py::test_rolling_threshold_accumulates_test_day_predictions -v`

Expected: FAIL — day 2's threshold will equal day 1's (both 0.39) because test predictions are not accumulated.

- [ ] **Step 3: Write the failing causal boundary test**

```python
def test_rolling_threshold_accumulation_preserves_causal_boundary() -> None:
    """Day D's own test predictions must NOT influence day D's threshold."""
    train_ts = pd.Series(
        pd.to_datetime(["2025-01-01T00:00:00Z"], utc=True)
    )
    train_p = np.array([0.5], dtype=float)
    test_ts = pd.Series(
        pd.to_datetime(["2025-01-03T00:00:00Z"], utc=True)
    )
    # Even with a wildly different test prediction, day 1's threshold
    # should only depend on training data
    test_p_low = np.array([0.01], dtype=float)
    test_p_high = np.array([0.99], dtype=float)

    thr_low, _ = _rolling_day_threshold_vector(
        train_ts=train_ts, train_p=train_p,
        test_ts=test_ts, test_p=test_p_low,
        q=0.9, lookback_days=5, min_history=1,
    )
    thr_high, _ = _rolling_day_threshold_vector(
        train_ts=train_ts, train_p=train_p,
        test_ts=test_ts, test_p=test_p_high,
        q=0.9, lookback_days=5, min_history=1,
    )

    assert np.isclose(thr_low[0], thr_high[0], equal_nan=True)
```

Add this test to `tests/test_monthly_wfo_threshold_causality.py`.

- [ ] **Step 4: Run the causal boundary test to verify it passes (existing behavior is already causal)**

Run: `uv run pytest tests/test_monthly_wfo_threshold_causality.py::test_rolling_threshold_accumulation_preserves_causal_boundary -v`

Expected: PASS — the existing code already excludes day D's predictions from day D's threshold.

- [ ] **Step 5: Implement accumulation in `_rolling_day_threshold_vector()`**

In `scripts/run_tick_opportunity_monthly_wfo.py`, replace lines 343-364:

```python
    lookback = pd.Timedelta(days=int(max(1, lookback_days)))
    train_items = list(train_by_day.items())
    for day in sorted(test_by_day_idx.keys()):
        start = day - lookback
        parts: list[np.ndarray] = []
        for d, arr in train_items:
            if start <= d < day:
                parts.append(arr)
        hist = np.concatenate(parts) if parts else np.array([], dtype=float)
        src_label = "rolling_history"
        if len(hist) < int(max(1, min_history)):
            if len(train_fallback):
                hist = train_fallback
                src_label = "train_fallback"
            else:
                hist = np.array([], dtype=float)
                src_label = "no_history"
        thr = float(np.quantile(hist, float(q))) if len(hist) else float(train_fallback_thr)
        if (not np.isfinite(thr)) and src_label != "no_history":
            src_label = "no_history"
        out[test_by_day_idx[day]] = thr
        src[test_by_day_idx[day]] = src_label
    return out, src
```

with:

```python
    lookback = pd.Timedelta(days=int(max(1, lookback_days)))
    pool: dict[pd.Timestamp, np.ndarray] = dict(train_by_day)
    pool_items = list(pool.items())
    for day in sorted(test_by_day_idx.keys()):
        start = day - lookback
        parts: list[np.ndarray] = []
        for d, arr in pool_items:
            if start <= d < day:
                parts.append(arr)
        hist = np.concatenate(parts) if parts else np.array([], dtype=float)
        src_label = "rolling_history"
        if len(hist) < int(max(1, min_history)):
            if len(train_fallback):
                hist = train_fallback
                src_label = "train_fallback"
            else:
                hist = np.array([], dtype=float)
                src_label = "no_history"
        thr = float(np.quantile(hist, float(q))) if len(hist) else float(train_fallback_thr)
        if (not np.isfinite(thr)) and src_label != "no_history":
            src_label = "no_history"
        out[test_by_day_idx[day]] = thr
        src[test_by_day_idx[day]] = src_label
        # Accumulate test-day predictions into pool for subsequent days (causal)
        if day in test_by_day_vals:
            pool[day] = test_by_day_vals[day]
            pool_items.append((day, test_by_day_vals[day]))
    return out, src
```

- [ ] **Step 6: Run all threshold tests**

Run: `uv run pytest tests/test_monthly_wfo_threshold_causality.py -v`

Expected: all 6 tests pass (4 existing + 2 new).

- [ ] **Step 7: Commit**

```bash
git add scripts/run_tick_opportunity_monthly_wfo.py tests/test_monthly_wfo_threshold_causality.py
git commit -m "fix: accumulate test-day predictions in WFO rolling threshold"
```

### Task 2: Export Training Predictions as Parquet Artifact

**Files:**
- Modify: `scripts/run_tick_opportunity_monthly_wfo.py:460-519`
- Test: `tests/test_monthly_wfo_threshold_causality.py`

- [ ] **Step 1: Write the failing test for training predictions export**

Add to `tests/test_monthly_wfo_threshold_causality.py`:

```python
def test_export_train_predictions_parquet(tmp_path: Path) -> None:
    """Training predictions export should contain (day, pred_prob) rows
    matching the training data used by the rolling threshold."""
    from scripts.run_tick_opportunity_monthly_wfo import _export_train_predictions

    train_ts = pd.Series(
        pd.to_datetime(
            ["2025-01-01T10:00:00Z", "2025-01-01T11:00:00Z", "2025-01-02T10:00:00Z"],
            utc=True,
        )
    )
    train_p = np.array([0.3, 0.4, 0.7], dtype=float)
    out_path = tmp_path / "EURUSD_train_predictions_2025-02.parquet"

    _export_train_predictions(
        train_ts=train_ts,
        train_p=train_p,
        out_path=out_path,
    )

    assert out_path.exists()
    df = pd.read_parquet(out_path)
    assert list(df.columns) == ["day", "pred_prob"]
    assert len(df) == 3
    assert df["pred_prob"].tolist() == [0.3, 0.4, 0.7]
    # Days should be date objects, floored from timestamps
    assert str(df["day"].iloc[0]) == "2025-01-01"
    assert str(df["day"].iloc[2]) == "2025-01-02"
```

Add `from pathlib import Path` to the imports at the top of the test file.

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_monthly_wfo_threshold_causality.py::test_export_train_predictions_parquet -v`

Expected: FAIL — `ImportError: cannot import name '_export_train_predictions'`

- [ ] **Step 3: Implement `_export_train_predictions()`**

Add to `scripts/run_tick_opportunity_monthly_wfo.py` after the `_rolling_day_threshold_vector` function (after line 365):

```python
def _export_train_predictions(
    *,
    train_ts: pd.Series,
    train_p: np.ndarray,
    out_path: Path,
) -> None:
    """Export training predictions as a parquet artifact for live seeding."""
    tr_t = pd.to_datetime(train_ts, utc=True, errors="coerce")
    tr_v = np.asarray(train_p, dtype=float)
    ok = np.isfinite(tr_v) & tr_t.notna().to_numpy()
    df = pd.DataFrame({
        "day": tr_t[ok].dt.floor("D").dt.date,
        "pred_prob": tr_v[ok],
    })
    out_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out_path, index=False)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_monthly_wfo_threshold_causality.py::test_export_train_predictions_parquet -v`

Expected: PASS

- [ ] **Step 5: Wire export into model export block**

In `scripts/run_tick_opportunity_monthly_wfo.py`, after the existing `thr_path.write_text(...)` line (line 518), add:

```python
            # Export training predictions for live seeding
            train_pred_path = model_export_dir / f"{symbol}_train_predictions_{month_tag}.parquet"
            _export_train_predictions(
                train_ts=tr["close_ts"],
                train_p=p_tr,
                out_path=train_pred_path,
            )
            print(f"exported: {train_pred_path}")
```

- [ ] **Step 6: Commit**

```bash
git add scripts/run_tick_opportunity_monthly_wfo.py tests/test_monthly_wfo_threshold_causality.py
git commit -m "feat: export training predictions parquet for live seeding"
```

### Task 3: Add Training Predictions to Lock JSON

**Files:**
- Modify: `scripts/freeze_oco_historical_governance.py:408-472`

- [ ] **Step 1: Add `train_predictions_path`, `train_predictions_sha256`, and `model_valid_through` to the artifacts section**

In `scripts/freeze_oco_historical_governance.py`, find the artifacts dict assembly (around line 413). After the `"model_threshold_json_sha256"` entry, add:

```python
    "train_predictions_path": str(train_pred),
    "train_predictions_sha256": _sha256(train_pred) if train_pred.exists() else "",
    "model_valid_through": model_valid_through,
```

Before the artifacts assembly, resolve the new paths. Find where `model_cbm` and `model_thr` are resolved (look for `model_cbm = ` near the artifacts block) and add:

```python
    train_pred = model_export_dir / f"{str(sym).upper()}_train_predictions_{month}.parquet"
```

For `model_valid_through`, compute it from the threshold schedule:

```python
    thr_data = json.loads(model_thr.read_text(encoding="utf-8")) if model_thr.exists() else {}
    schedule = thr_data.get("threshold_schedule", {})
    if schedule:
        last_schedule_day = max(schedule.keys())
        model_valid_through = last_schedule_day
    else:
        model_valid_through = ""
```

- [ ] **Step 2: Verify the lock builder still runs**

Run: `uv run python scripts/freeze_oco_historical_governance.py --help`

Expected: help text prints without error.

- [ ] **Step 3: Commit**

```bash
git add scripts/freeze_oco_historical_governance.py
git commit -m "feat: add train_predictions and model_valid_through to lock JSON"
```

### Task 4: Add `seed_training_predictions()` to StateManager

**Files:**
- Modify: `src/behemoth/runtime/state.py`
- Create: `tests/test_threshold_seeding.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_threshold_seeding.py`:

```python
from __future__ import annotations

from datetime import datetime, timezone

import numpy as np
import pandas as pd
import pytest

from src.behemoth.runtime.state import StateManager


def test_seed_training_predictions_populates_audit_logs(tmp_path) -> None:
    """Phase 1 seeding loads training predictions parquet into audit_logs."""
    sm = StateManager(vol_window=20, cost_window=20)
    try:
        # Create a training predictions parquet
        train_df = pd.DataFrame({
            "day": pd.to_datetime(["2025-01-01", "2025-01-01", "2025-01-02"], utc=True).date,
            "pred_prob": [0.3, 0.4, 0.7],
        })
        pq_path = tmp_path / "EURUSD_train_predictions_2025-02.parquet"
        train_df.to_parquet(pq_path, index=False)

        sm.seed_training_predictions(
            parquet_path=pq_path,
            symbol="EURUSD",
            candidate_uid="oco|EURUSD|200|h6|test",
            model_month="2025-02",
            run_id="seed_test",
        )

        # Verify audit_logs was populated
        row = sm._con.execute(
            "SELECT COUNT(*), quantile(pred_prob, 0.9) FROM audit_logs WHERE symbol = 'EURUSD'"
        ).fetchone()
        assert row[0] == 3
        assert np.isclose(row[1], float(np.quantile([0.3, 0.4, 0.7], 0.9)))
    finally:
        sm.close()


def test_seed_training_predictions_sets_close_ts_from_day(tmp_path) -> None:
    """Each row's close_ts should be derived from the day column so
    the rolling window lookback works correctly."""
    sm = StateManager(vol_window=20, cost_window=20)
    try:
        train_df = pd.DataFrame({
            "day": pd.to_datetime(["2025-01-15", "2025-01-16"], utc=True).date,
            "pred_prob": [0.5, 0.6],
        })
        pq_path = tmp_path / "train.parquet"
        train_df.to_parquet(pq_path, index=False)

        sm.seed_training_predictions(
            parquet_path=pq_path,
            symbol="EURUSD",
            candidate_uid="oco|EURUSD|200|h6|test",
            model_month="2025-02",
            run_id="seed_test",
        )

        rows = sm._con.execute(
            "SELECT close_ts FROM audit_logs ORDER BY close_ts"
        ).fetchall()
        assert len(rows) == 2
        # close_ts should be midnight UTC of the day
        assert rows[0][0].date().isoformat() == "2025-01-15"
        assert rows[1][0].date().isoformat() == "2025-01-16"
    finally:
        sm.close()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_threshold_seeding.py -v`

Expected: FAIL — `AttributeError: 'StateManager' object has no attribute 'seed_training_predictions'`

- [ ] **Step 3: Implement `seed_training_predictions()` in StateManager**

Add to `src/behemoth/runtime/state.py` after the `log_audit_event_batch` method:

```python
    def seed_training_predictions(
        self,
        *,
        parquet_path: Path,
        symbol: str,
        candidate_uid: str,
        model_month: str,
        run_id: str,
    ) -> int:
        """Seed audit_logs with exported training predictions (phase 1).

        Loads the training predictions parquet and inserts rows into audit_logs
        with close_ts set to midnight UTC of each day. This gives the rolling
        threshold the same starting pool that WFO had on test day 1.

        Returns the number of rows inserted.
        """
        import pandas as pd

        df = pd.read_parquet(parquet_path)
        if df.empty:
            return 0
        events = []
        for row in df.itertuples(index=False):
            day_ts = datetime(row.day.year, row.day.month, row.day.day, tzinfo=timezone.utc)
            events.append((
                day_ts,           # close_ts
                symbol.upper(),   # symbol
                candidate_uid,    # candidate_uid
                float(row.pred_prob),  # pred_prob
                0.0,              # threshold (not meaningful for seed)
                "{}",             # features_json
                model_month,      # model_month
                run_id,           # run_id
            ))
        self.log_audit_event_batch(events)
        return len(events)
```

Add `from pathlib import Path` to the imports at the top of `state.py`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_threshold_seeding.py -v`

Expected: 2 passed

- [ ] **Step 5: Commit**

```bash
git add src/behemoth/runtime/state.py tests/test_threshold_seeding.py
git commit -m "feat: add seed_training_predictions to StateManager"
```

### Task 5: Update Seeding Endpoint for Two-Phase Flow

**Files:**
- Modify: `src/behemoth/api/server.py:1888-1891` (request schema)
- Modify: `src/behemoth/api/server.py:2966-3168` (seeding endpoint)

- [ ] **Step 1: Update `SeedAuditHistoryRequest` schema**

Replace the existing schema at line 1888:

```python
class SeedAuditHistoryRequest(BaseModel):
    symbols: list[str] | None = None
    days_back: int = 20
    run_id: str = "audit_seed"
```

with:

```python
class SeedAuditHistoryRequest(BaseModel):
    symbols: list[str] | None = None
    days_back: int = 20
    run_id: str = "audit_seed"
    train_predictions_dir: str | None = None
    test_month_start: str | None = None
```

- [ ] **Step 2: Add phase 1 (training seed) to the seeding endpoint**

In the `seed_audit_history` function body, before the existing per-symbol loop, add the phase 1 logic. Find the `for sym in symbols:` loop and add before it:

```python
    # ── Phase 1: Seed training predictions from exported artifact ──
    train_pred_dir = Path(req.train_predictions_dir) if req.train_predictions_dir else None
    phase1_events: dict[str, int] = {}

    if train_pred_dir is not None:
        for sym in symbols:
            try:
                contract = _resolve_runtime_contract(sym, now_ts)
                if not contract.candidates:
                    phase1_events[sym] = 0
                    continue
                month_tag = contract.model_month
                pred_path = train_pred_dir / f"{sym}_train_predictions_{month_tag}.parquet"
                if not pred_path.exists():
                    logger.warning(
                        "seed_audit_history phase1: no training predictions at %s", pred_path
                    )
                    phase1_events[sym] = 0
                    continue
                total_for_sym = 0
                for cand in contract.candidates:
                    canonical_uid = (
                        f"oco|{sym}|{cand.bar_ticks}|h{cand.horizon}|{cand.candidate_uid}"
                    )
                    n = _state.seed_training_predictions(
                        parquet_path=pred_path,
                        symbol=sym,
                        candidate_uid=canonical_uid,
                        model_month=month_tag,
                        run_id=f"{req.run_id}_phase1",
                    )
                    total_for_sym += n
                phase1_events[sym] = total_for_sym
                logger.info("seed_audit_history phase1: %d events for %s", total_for_sym, sym)
            except Exception as exc:
                logger.warning("seed_audit_history phase1 failed for %s: %s", sym, exc)
                phase1_events[sym] = 0
```

- [ ] **Step 3: Update phase 2 (gap replay) to use `test_month_start` instead of `days_back`**

In the existing per-symbol replay loop, find where `start_dt` is computed. Change:

```python
    start_dt = now_ts - timedelta(days=req.days_back)
```

to:

```python
    if req.test_month_start:
        start_dt = datetime.fromisoformat(req.test_month_start).replace(tzinfo=timezone.utc)
    else:
        start_dt = now_ts - timedelta(days=req.days_back)
```

- [ ] **Step 4: Update the return value to include phase 1 counts**

Find the return statement at the end of the function:

```python
    total = sum(events_by_symbol.values())
    return {"ok": True, "events_by_symbol": events_by_symbol, "total_events": total}
```

Replace with:

```python
    total = sum(events_by_symbol.values()) + sum(phase1_events.values())
    return {
        "ok": True,
        "phase1_events": phase1_events,
        "phase2_events": events_by_symbol,
        "total_events": total,
    }
```

Also ensure `phase1_events` is initialized to `{}` if `train_pred_dir is None`:

After the `if train_pred_dir is not None:` block, add:

```python
    else:
        phase1_events = {}
```

Wait — `phase1_events` is already initialized as `phase1_events: dict[str, int] = {}` before the if block. So the else is not needed. But the `phase1_events` variable needs to exist even when `train_pred_dir` is None. It's already initialized on the line `phase1_events: dict[str, int] = {}`, so this is fine.

- [ ] **Step 5: Commit**

```bash
git add src/behemoth/api/server.py
git commit -m "feat: two-phase seeding endpoint with training predictions"
```

### Task 6: Remove Schedule-First Threshold Lookup in Live Mode

**Files:**
- Modify: `src/behemoth/api/server.py:2472-2532`

- [ ] **Step 1: Replace the threshold lookup logic**

Find the threshold lookup block (lines 2472-2532). Replace:

```python
            # Dynamic threshold lookup. If the model export includes a per-day
            # schedule, use it; otherwise, fall back to the static scalar.
            schedule = thr_cfg.get("threshold_schedule", {})
            day_str = close_ts.strftime("%Y-%m-%d")

            if schedule and day_str in schedule:
                curr_threshold = float(schedule[day_str])
                curr_source = f"{threshold_mode}:schedule"
            else:
```

with:

```python
            schedule = thr_cfg.get("threshold_schedule", {})
            day_str = close_ts.strftime("%Y-%m-%d")

            # Model expiry check: block immediately if past valid-through date.
            model_valid_through = thr_cfg.get("model_valid_through", "")
            if model_valid_through and day_str > model_valid_through:
                logger.warning(
                    "Model expired for %s %s: valid through %s, current day %s. Blocking.",
                    sym, canonical_uid, model_valid_through, day_str,
                )
                curr_threshold = 2.0
                curr_source = f"{threshold_mode}:model_expired"
                threshold_blocked = True
                threshold_block_reason = "MODEL_EXPIRED"
            else:
```

Then remove the `if schedule and day_str in schedule:` branch entirely. The `else:` now falls directly into the rolling threshold lookup. The rolling computation is the sole authority — schedule is only used for stage 14 validation.

The remaining block should be (inside the else of the expiry check):

```python
            else:
                rolling_days = int(thr_cfg.get("rolling_threshold_days", 0))
                exec_q = float(thr_cfg.get("execution_quantile", 0.9))
                min_history = int(thr_cfg.get("rolling_threshold_min_history", 10))
                dynamic_thr = None
                if rolling_days > 0 and _state is not None:
                    dynamic_thr = _state.get_rolling_threshold(
                        symbol=sym,
                        candidate_uid=canonical_uid,
                        exec_q=exec_q,
                        lookback_days=rolling_days,
                        min_history=min_history,
                    )

                is_live = _config.governance_mode == "live"

                if dynamic_thr is not None:
                    curr_threshold = dynamic_thr
                    curr_source = f"{threshold_mode}:rolling_dynamic"
                elif rolling_days > 0:
                    logger.warning(
                        "No valid threshold for %s %s: "
                        "insufficient audit_log history (rolling_days=%d, min_history=%d). "
                        "Blocking candidate.",
                        sym, canonical_uid, rolling_days, min_history,
                    )
                    curr_threshold = 2.0
                    curr_source = f"{threshold_mode}:no_valid_threshold"
                    threshold_blocked = True
                    threshold_block_reason = "ROLLING_HISTORY_GAP"
                elif is_live:
                    logger.warning(
                        "No valid threshold for %s %s: no rolling config in live mode. Blocking.",
                        sym, canonical_uid,
                    )
                    curr_threshold = 2.0
                    curr_source = f"{threshold_mode}:no_rolling_config"
                    threshold_blocked = True
                    threshold_block_reason = "NO_ROLLING_CONFIG"
                else:
                    curr_threshold = threshold_exec
                    curr_source = f"{threshold_mode}:static_fallback"
```

- [ ] **Step 2: Commit**

```bash
git add src/behemoth/api/server.py
git commit -m "fix: rolling computation is sole threshold authority in live mode"
```

### Task 7: Update Live Runner to Pass Training Predictions

**Files:**
- Modify: `scripts/run_jforex_live.py:108-133`

- [ ] **Step 1: Update `_seed_audit_history()` to pass training predictions dir and test month start**

Replace the `_seed_audit_history` function:

```python
def _seed_audit_history(
    symbols: list[str],
    base_url: str,
    days_back: int = 20,
    train_predictions_dir: str | None = None,
    model_month: str | None = None,
) -> None:
    """Call /state/seed_audit_history to populate audit_logs.

    Phase 1: Load exported training predictions (WFO-equivalent pool).
    Phase 2: Replay test-month parquet to bridge any gap since month start.
    """
    import requests

    # Determine test month start from model_month (test month = month after model_month)
    test_month_start = None
    if model_month:
        from datetime import datetime as dt
        from dateutil.relativedelta import relativedelta
        mm = dt.strptime(model_month, "%Y-%m")
        test_month_start = (mm + relativedelta(months=1)).strftime("%Y-%m-%dT00:00:00")

    print(f"[seed] seeding audit_logs (train_pred_dir={train_predictions_dir}, "
          f"test_month_start={test_month_start})...", flush=True)
    try:
        r = requests.post(
            f"{base_url}/state/seed_audit_history",
            json={
                "symbols": symbols,
                "days_back": days_back,
                "run_id": "audit_seed",
                "train_predictions_dir": train_predictions_dir,
                "test_month_start": test_month_start,
            },
            timeout=600,
        )
        body = r.json()
        if body.get("ok"):
            p1 = sum(body.get("phase1_events", {}).values())
            p2 = sum(body.get("phase2_events", {}).values())
            print(f"[seed] done — phase1: {p1}, phase2: {p2}, total: {body['total_events']}", flush=True)
            for sym, count in body.get("phase1_events", {}).items():
                print(f"[seed]   {sym} phase1: {count} events", flush=True)
            for sym, count in body.get("phase2_events", {}).items():
                print(f"[seed]   {sym} phase2: {count} events", flush=True)
        else:
            print(f"[seed] WARNING: unexpected response: {body}", flush=True)
    except Exception as exc:
        print(f"[seed] WARNING: seed_audit_history failed: {exc}", flush=True)
        print("[seed] continuing without historical seed — first predict calls may block", flush=True)
```

- [ ] **Step 2: Update the call site to pass the new arguments**

Find where `_seed_audit_history` is called in the script. Update the call to pass the models directory and model month. Look for the call site (around line 278) and update:

```python
    _seed_audit_history(
        symbols=symbols,
        base_url=base_url,
        train_predictions_dir=str(args.models_dir),
        model_month=_resolve_model_month(args),
    )
```

Add a helper to resolve the model month from the history dir:

```python
def _resolve_model_month(args) -> str | None:
    """Resolve the model month from the promoted history directory."""
    history_dir = Path(args.history_dir)
    if not history_dir.exists():
        return None
    months = sorted(d.name for d in history_dir.iterdir() if d.is_dir() and d.name != "__pycache__")
    return months[-1] if months else None
```

- [ ] **Step 3: Commit**

```bash
git add scripts/run_jforex_live.py
git commit -m "feat: pass training predictions dir to two-phase seeding"
```

### Task 8: Add `THRESHOLD_PARITY_PASS` to Stage 14

**Files:**
- Modify: `scripts/validate_stage14_jforex_runtime_certification.py`

- [ ] **Step 1: Write the parity check function**

Add a new function to the validation script:

```python
def _check_threshold_parity(
    symbol: str,
    report_dir: Path,
    models_dir: Path,
    tolerance: float = 1e-4,
) -> tuple[str, str]:
    """Compare threshold_schedule values against rolling computation from seeded audit_logs.

    Returns (status, details) where status is 'pass', 'fail', or 'skip'.
    """
    import duckdb

    # Load threshold schedule from model JSON
    month_dirs = sorted(
        d.name for d in (report_dir.parent / "configs" / "research" / "governance" /
                         "oco_history_dukascopy_candidate").iterdir()
        if d.is_dir()
    )
    if not month_dirs:
        return "skip", "no promoted month found"
    month = month_dirs[-1]

    thr_files = list(models_dir.glob(f"{symbol}_model_{month}.json"))
    if not thr_files:
        return "skip", f"no threshold JSON for {symbol} {month}"
    import json
    thr_cfg = json.loads(thr_files[0].read_text())
    schedule = thr_cfg.get("threshold_schedule", {})
    if not schedule:
        return "skip", "no threshold_schedule in model JSON"

    rolling_days = int(thr_cfg.get("rolling_threshold_days", 20))
    exec_q = float(thr_cfg.get("execution_quantile", 0.9))
    min_history = int(thr_cfg.get("rolling_threshold_min_history", 1000))

    # Find the live state DB
    state_db = report_dir / "runtime" / "live_state.db"
    if not state_db.exists():
        return "skip", f"no live state DB at {state_db}"

    con = duckdb.connect(str(state_db), read_only=True)
    mismatches = []
    try:
        for day_str, expected_thr in sorted(schedule.items()):
            cutoff = f"{day_str}T00:00:00+00:00"
            lookback_start = (
                datetime.fromisoformat(cutoff) - timedelta(days=rolling_days)
            ).isoformat()
            row = con.execute(
                """
                SELECT COUNT(*), quantile(pred_prob, ?)
                FROM audit_logs
                WHERE symbol = ?
                  AND close_ts >= ?
                  AND close_ts < ?
                """,
                [exec_q, symbol, lookback_start, cutoff],
            ).fetchone()
            if row is None or row[0] < min_history:
                continue  # insufficient history for this day
            actual_thr = float(row[1])
            if abs(actual_thr - expected_thr) > tolerance:
                mismatches.append(
                    f"{day_str}: expected={expected_thr:.6f}, actual={actual_thr:.6f}"
                )
    finally:
        con.close()

    if mismatches:
        return "fail", f"{len(mismatches)} day(s) diverge: {'; '.join(mismatches[:3])}"
    return "pass", "all schedule days match within tolerance"
```

- [ ] **Step 2: Wire the check into the existing check_rows assembly**

Find where `check_rows` is assembled for each symbol. After the existing checks, add:

```python
        # Threshold parity check
        thr_status, thr_details = _check_threshold_parity(
            symbol=symbol,
            report_dir=report_dir,
            models_dir=models_dir,
        )
        check_rows.append(
            {
                "symbol": symbol,
                "check_id": "THRESHOLD_PARITY_PASS",
                "status": thr_status,
                "severity": "critical",
                "metric_name": "threshold_parity_pass",
                "metric_value": int(thr_status == "pass"),
                "expected": 1,
                "details": thr_details,
                "source_path": str(report_dir / "runtime" / "live_state.db"),
                "evaluated_at_utc": now_utc,
            }
        )
```

Ensure the `models_dir` path is available in the function scope. Add a `--models-dir` argument to the script's argument parser if it doesn't exist, defaulting to `models/oco_dukascopy_candidate`.

- [ ] **Step 3: Commit**

```bash
git add scripts/validate_stage14_jforex_runtime_certification.py
git commit -m "feat: add THRESHOLD_PARITY_PASS to stage 14 certification"
```

### Task 9: Add Model Expiry Guard Test

**Files:**
- Create: `tests/test_model_expiry_guard.py`

- [ ] **Step 1: Write the expiry guard test**

Create `tests/test_model_expiry_guard.py`:

```python
from __future__ import annotations


def test_model_valid_through_blocks_expired_models() -> None:
    """When day_str > model_valid_through, the threshold should block."""
    thr_cfg = {
        "threshold_schedule": {"2025-02-01": 0.6, "2025-02-28": 0.6},
        "model_valid_through": "2025-02-28",
        "rolling_threshold_days": 20,
        "execution_quantile": 0.9,
        "rolling_threshold_min_history": 1000,
    }
    day_str = "2025-03-01"
    model_valid_through = thr_cfg.get("model_valid_through", "")

    assert model_valid_through != ""
    assert day_str > model_valid_through, "Should detect expiry"


def test_model_valid_through_allows_valid_day() -> None:
    """When day_str <= model_valid_through, the threshold should not block."""
    thr_cfg = {
        "threshold_schedule": {"2025-02-01": 0.6, "2025-02-28": 0.6},
        "model_valid_through": "2025-02-28",
    }
    day_str = "2025-02-15"
    model_valid_through = thr_cfg.get("model_valid_through", "")

    assert day_str <= model_valid_through, "Should allow valid day"


def test_model_valid_through_empty_does_not_block() -> None:
    """When model_valid_through is empty, no expiry check applies."""
    thr_cfg = {
        "threshold_schedule": {},
    }
    model_valid_through = thr_cfg.get("model_valid_through", "")

    assert not model_valid_through, "Empty string is falsy — no block"
```

- [ ] **Step 2: Run tests**

Run: `uv run pytest tests/test_model_expiry_guard.py -v`

Expected: 3 passed

- [ ] **Step 3: Commit**

```bash
git add tests/test_model_expiry_guard.py
git commit -m "test: add model expiry guard tests"
```

### Task 10: Run Full Verification

**Files:**
- No modifications

- [ ] **Step 1: Run all new and modified test files**

Run: `uv run pytest tests/test_monthly_wfo_threshold_causality.py tests/test_threshold_seeding.py tests/test_model_expiry_guard.py -v`

Expected: all tests pass.

- [ ] **Step 2: Run the broader test suite to check for regressions**

Run: `uv run pytest tests/ -q --ignore=tests/test_jforex`

Expected: no failures in non-JForex tests.

- [ ] **Step 3: Verify the WFO script still loads cleanly**

Run: `uv run python -c "from scripts.run_tick_opportunity_monthly_wfo import _rolling_day_threshold_vector, _export_train_predictions; print('OK')"`

Expected: `OK`

- [ ] **Step 4: Commit final verification state**

```bash
git add -A
git commit -m "chore: rolling threshold equivalence implementation complete"
```
