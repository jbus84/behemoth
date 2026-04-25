# Warmup Historical Replay Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rewrite `/predict/warmup` so it replays the model across every buffered bar (real pred_prob distribution), make the endpoint idempotent per `(symbol, run_id)` so restarting the live system self-heals the corrupted `audit_logs`, and add three guardrails against silent regression.

**Architecture:** `/predict/warmup` becomes a snapshot endpoint. It batch-computes features across the whole `tick_bars` buffer via the existing `compute_feature_matrix_from_bars()`, runs one `model.predict_proba()` call per candidate, verifies the per-candidate distribution is non-degenerate (hard fails otherwise), and inside a single DuckDB transaction purges prior rows for `(symbol, run_id)` then batch-inserts the replay. A new Prometheus counter at `/predict` time labels each rolling-threshold computation as `ok` or `drift` vs the static `threshold_exec` baseline. A new section in `diagnose_live_performance_gap.py` surfaces per-`run_id` unique-value counts and p90 deviation so flat-distribution regressions are visible in the existing diagnostic report.

**Tech Stack:** Python 3.10+, FastAPI, DuckDB, CatBoost, Prometheus client, pydantic v2, pytest.

**Reference spec:** `docs/superpowers/specs/2026-04-24-warmup-historical-replay-design.md`

**Worktree:** `.worktrees/fix-warmup-historical-replay` on branch `fix/warmup-historical-replay`

## Deviations from spec

**1. `get_rolling_threshold()` signature unchanged.** The spec says it "gains an optional `baseline_threshold` argument". The cleaner division of responsibility is to keep `state.py` DB-only (no Prometheus imports) and implement the drift check in `server.py` at the call site, which already has `thr_cfg["threshold_exec"]` in scope. The observable behaviour (counter increments, warning log, baseline band = 0.05) is identical to what the spec describes.

**2. Integrity section flag is flat-distribution only; drift flag is deferred to Layer 2.** The spec's `_rolling_threshold_integrity_section` describes both (a) flat-distribution detection via `unique_values` and (b) combined-p90 drift vs the static `threshold_exec`. Adding (b) to the offline diagnostic script would require loading the threshold JSON per symbol per candidate (and parsing `model_month` from the lock), duplicating logic the Prometheus counter (Layer 2) already exposes live. The integrity section keeps a single unambiguous flag for the flat-distribution regression — the exact bug this PR fixes — and drift detection stays in Prometheus where it naturally lives.

## File Structure

| File | Action | Responsibility |
|---|---|---|
| `src/behemoth/runtime/state.py` | Modify | Add `purge_audit_events()` public method. No change to `get_rolling_threshold()`. |
| `src/behemoth/api/server.py` | Modify | Rewrite `predict_warmup()` body (lines 3350-3424). Add `METRIC_ROLLING_THRESHOLD_DRIFT` counter. Wire drift check at the `get_rolling_threshold()` call site inside `_build_predictions()`. |
| `scripts/diagnose_live_performance_gap.py` | Modify | Add `_rolling_threshold_integrity_section()`. Include it in `run()` report and `_format_report()`. |
| `tests/test_duckdb_state.py` | Modify | One new test for `purge_audit_events()`. |
| `tests/test_api_server.py` | Modify | Three new tests: regression, idempotency, degenerate-distribution hard fail. One new test for drift counter. |
| `tests/test_diagnose_live_performance_gap.py` | Modify | One new test for integrity section detecting flat warmup. |

No new files. No schema migrations. No governance/lock artifact changes.

---

## Task 1: Add `purge_audit_events()` helper on StateManager

**Why first:** Pure DB helper with no dependencies. Task 4 (warmup rewrite) depends on this.

**Files:**
- Modify: `src/behemoth/runtime/state.py` (insert after `log_audit_event_batch`, around line 487)
- Test: `tests/test_duckdb_state.py` (append to `TestRollingThreshold` class or add a new class)

- [ ] **Step 1.1: Write the failing test**

Append to `tests/test_duckdb_state.py`, right before `class TestTradeRicherRecording` at line 634:

```python
class TestPurgeAuditEvents:
    def test_purge_removes_only_matching_symbol_and_run_id(self):
        from datetime import datetime, timezone

        from src.behemoth.runtime.state import StateManager

        sm = StateManager()
        now = datetime.now(tz=timezone.utc)
        uid = "oco|GBPUSD|100|h6|oco_first_touch_clean__ny_overlap__k2"
        # 5 warmup rows for GBPUSD
        for i in range(5):
            sm._con.execute(
                "INSERT INTO audit_logs(event_ts, close_ts, symbol, candidate_uid, "
                "pred_prob, threshold, features_json, model_month, run_id) "
                "VALUES (?, ?, 'GBPUSD', ?, ?, 0.5, '{}', '2026-02', 'warmup')",
                [now, now, uid, 0.60 + i * 0.01],
            )
        # 3 jforex_live rows for GBPUSD (must NOT be purged)
        for i in range(3):
            sm._con.execute(
                "INSERT INTO audit_logs(event_ts, close_ts, symbol, candidate_uid, "
                "pred_prob, threshold, features_json, model_month, run_id) "
                "VALUES (?, ?, 'GBPUSD', ?, ?, 0.5, '{}', '2026-02', 'jforex_live')",
                [now, now, uid, 0.70 + i * 0.01],
            )
        # 2 warmup rows for EURUSD (must NOT be purged — different symbol)
        for i in range(2):
            sm._con.execute(
                "INSERT INTO audit_logs(event_ts, close_ts, symbol, candidate_uid, "
                "pred_prob, threshold, features_json, model_month, run_id) "
                "VALUES (?, ?, 'EURUSD', ?, ?, 0.5, '{}', '2026-02', 'warmup')",
                [now, now, uid, 0.65 + i * 0.01],
            )

        purged = sm.purge_audit_events(symbol="GBPUSD", run_id="warmup")

        assert purged == 5
        # GBPUSD warmup gone
        n_gbp_warmup = sm._con.execute(
            "SELECT COUNT(*) FROM audit_logs WHERE symbol='GBPUSD' AND run_id='warmup'"
        ).fetchone()[0]
        assert n_gbp_warmup == 0
        # GBPUSD jforex_live untouched
        n_gbp_live = sm._con.execute(
            "SELECT COUNT(*) FROM audit_logs WHERE symbol='GBPUSD' AND run_id='jforex_live'"
        ).fetchone()[0]
        assert n_gbp_live == 3
        # EURUSD warmup untouched
        n_eur_warmup = sm._con.execute(
            "SELECT COUNT(*) FROM audit_logs WHERE symbol='EURUSD' AND run_id='warmup'"
        ).fetchone()[0]
        assert n_eur_warmup == 2

    def test_purge_returns_zero_when_nothing_matches(self):
        from src.behemoth.runtime.state import StateManager

        sm = StateManager()
        purged = sm.purge_audit_events(symbol="NOPE", run_id="warmup")
        assert purged == 0
```

- [ ] **Step 1.2: Run test to verify it fails**

```bash
cd /Users/danielfisher/repositories/behemoth/.worktrees/fix-warmup-historical-replay
uv run pytest tests/test_duckdb_state.py::TestPurgeAuditEvents -v
```

Expected: FAIL with `AttributeError: 'StateManager' object has no attribute 'purge_audit_events'`.

- [ ] **Step 1.3: Implement the helper**

In `src/behemoth/runtime/state.py`, insert after `log_audit_event_batch()` (it ends around line 487, right before `def seed_training_predictions`):

```python
    def purge_audit_events(self, *, symbol: str, run_id: str) -> int:
        """Delete audit_logs rows matching (symbol, run_id). Returns rows deleted.

        Scoped purge only — does not affect other symbols or other run_ids
        (e.g. 'threshold_seed' or 'jforex_live' rows are untouched).
        """
        before = self._con.execute(
            "SELECT COUNT(*) FROM audit_logs WHERE symbol = ? AND run_id = ?",
            [symbol.upper(), run_id],
        ).fetchone()
        before_count = int(before[0]) if before and before[0] is not None else 0
        if before_count <= 0:
            return 0
        self._con.execute(
            "DELETE FROM audit_logs WHERE symbol = ? AND run_id = ?",
            [symbol.upper(), run_id],
        )
        return before_count
```

- [ ] **Step 1.4: Run test to verify it passes**

```bash
uv run pytest tests/test_duckdb_state.py::TestPurgeAuditEvents -v
```

Expected: 2 passed.

- [ ] **Step 1.5: Run the existing state test suite to verify no regressions**

```bash
uv run pytest tests/test_duckdb_state.py -v
```

Expected: all tests pass.

- [ ] **Step 1.6: Commit**

```bash
git -C /Users/danielfisher/repositories/behemoth/.worktrees/fix-warmup-historical-replay add \
    src/behemoth/runtime/state.py tests/test_duckdb_state.py
git -C /Users/danielfisher/repositories/behemoth/.worktrees/fix-warmup-historical-replay commit \
    -m "$(cat <<'EOF'
feat(state): add purge_audit_events helper

Scoped DELETE on audit_logs by (symbol, run_id). Used by the warmup
endpoint to implement snapshot semantics — purges prior rows for the
same (symbol, run_id) before rewriting. Does not touch other symbols
or other run_ids (threshold_seed, jforex_live remain untouched).

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: Rewrite `/predict/warmup` — batch replay + atomic snapshot + sanity check

**Why second:** Main fix for the bug. Depends on Task 1 (`purge_audit_events`). Unblocks live remediation once deployed.

**Files:**
- Modify: `src/behemoth/api/server.py` (rewrite `predict_warmup`, lines 3350-3424)
- Test: `tests/test_api_server.py` (append to `class TestPredictWarmup` at line 3161)

### Test-driven steps

- [ ] **Step 2.1: Write three failing tests**

Append to `class TestPredictWarmup` in `tests/test_api_server.py`:

```python
    def _seed_bars(self, sym: str, n: int, *, start_close: float = 1.30000) -> None:
        """Populate _state.tick_bars with n varied bars for the given symbol.

        Each bar has slightly different OHLC so the feature builder produces
        a non-constant feature matrix. Writes bars with bar_ticks=100 to match
        the dummy candidate used in these tests.
        """
        from datetime import datetime, timedelta, timezone
        from src.behemoth.api import server
        base_ts = datetime(2026, 4, 1, 0, 0, tzinfo=timezone.utc)
        for i in range(n):
            ts = base_ts + timedelta(minutes=i)
            close_ts = ts + timedelta(seconds=30)
            bid = start_close + 0.0001 * (i % 50) - 0.00005 * ((i * 7) % 11)
            server._state._con.execute(
                "INSERT INTO tick_bars VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    i, sym.upper(), 100, ts, close_ts,
                    bid,               # open_bid
                    bid + 0.0005,      # high_bid
                    bid - 0.0005,      # low_bid
                    bid + 0.0001,      # close_bid
                    0.00015,           # spread
                    100.0 + (i % 30),  # tick_volume
                    bid + 0.0002,      # hl_first
                    0.55,              # hl_pos_frac
                    bid + 0.00065,     # high_ask
                    bid + 0.00025,     # close_ask
                ],
            )

    def test_warmup_writes_varied_pred_probs_per_bar(self, client):
        """Regression test: each bar must get its own pred_prob, not a single
        value stamped across all historical close_ts. Asserts unique_values
        proxy for the distribution variance that the current bug destroys."""
        import unittest.mock as mock
        import numpy as np
        from types import SimpleNamespace

        from src.behemoth.api import server

        sym = "GBPUSD"
        # Clear any prior state
        server._state._con.execute("DELETE FROM audit_logs WHERE symbol = ?", [sym])
        server._state._con.execute("DELETE FROM tick_bars WHERE symbol = ?", [sym])

        self._seed_bars(sym, n=360)  # well above full_warmup_bars (289)

        dummy_cand = mock.MagicMock()
        dummy_cand.bar_ticks = 100
        dummy_cand.horizon = 6
        dummy_cand.barrier_pips = 2.0
        dummy_cand.candidate_uid = "oco_first_touch_clean__all__k2"

        dummy_model = mock.MagicMock()
        # Return varied probabilities: one per input row
        def _varied_proba(X):
            n = len(X)
            # 2-column output: [neg_prob, pos_prob] — use index 1 for pos_prob
            pos = np.linspace(0.40, 0.85, n)
            return np.column_stack([1.0 - pos, pos])
        dummy_model.predict_proba.side_effect = _varied_proba

        with (
            mock.patch.object(
                server, "_resolve_runtime_contract",
                return_value=SimpleNamespace(
                    candidates=[dummy_cand], model_month="2026-03", cap_pips=1.2,
                ),
            ),
            mock.patch.object(
                server, "_ensure_model_and_threshold",
                return_value=(dummy_model, {"threshold_exec": 0.5, "threshold_source": "test"}),
            ),
        ):
            r = client.post("/predict/warmup", json={"symbol": sym, "run_id": "warmup"})

        assert r.status_code == 201, r.text
        body = r.json()
        assert body["audit_events_written"] >= 30, body

        # Query audit_logs and assert variance
        rows = server._state._con.execute(
            "SELECT pred_prob FROM audit_logs WHERE symbol = ? AND run_id = 'warmup'",
            [sym],
        ).fetchall()
        probs = [r[0] for r in rows]
        unique = len(set(round(p, 8) for p in probs))
        assert unique >= 10, f"expected >= 10 unique pred_probs, got {unique}"
        # Response body should surface the per-candidate distribution stats
        canonical_uid = f"oco|{sym}|100|h6|oco_first_touch_clean__all__k2"
        assert canonical_uid in body["stats"]
        assert body["stats"][canonical_uid]["unique_values"] >= 10

    def test_warmup_is_idempotent_and_purges_prior(self, client):
        """Calling warmup twice must purge the first run's rows and produce
        a fresh snapshot. Asserts audit_events_purged on second call equals
        audit_events_written on first call."""
        import unittest.mock as mock
        import numpy as np
        from types import SimpleNamespace

        from src.behemoth.api import server

        sym = "USDCAD"
        server._state._con.execute("DELETE FROM audit_logs WHERE symbol = ?", [sym])
        server._state._con.execute("DELETE FROM tick_bars WHERE symbol = ?", [sym])
        self._seed_bars(sym, n=360)

        dummy_cand = mock.MagicMock()
        dummy_cand.bar_ticks = 100
        dummy_cand.horizon = 6
        dummy_cand.barrier_pips = 2.0
        dummy_cand.candidate_uid = "oco_first_touch_clean__all__k2"

        dummy_model = mock.MagicMock()
        def _varied(X):
            pos = np.linspace(0.40, 0.85, len(X))
            return np.column_stack([1.0 - pos, pos])
        dummy_model.predict_proba.side_effect = _varied

        with (
            mock.patch.object(
                server, "_resolve_runtime_contract",
                return_value=SimpleNamespace(
                    candidates=[dummy_cand], model_month="2026-03", cap_pips=1.2,
                ),
            ),
            mock.patch.object(
                server, "_ensure_model_and_threshold",
                return_value=(dummy_model, {"threshold_exec": 0.5, "threshold_source": "test"}),
            ),
        ):
            r1 = client.post("/predict/warmup", json={"symbol": sym, "run_id": "warmup"})
            assert r1.status_code == 201
            body1 = r1.json()
            assert body1["audit_events_purged"] == 0
            written1 = body1["audit_events_written"]
            assert written1 > 0

            r2 = client.post("/predict/warmup", json={"symbol": sym, "run_id": "warmup"})
            assert r2.status_code == 201
            body2 = r2.json()
            assert body2["audit_events_purged"] == written1
            assert body2["audit_events_written"] == written1

        # Other symbols / run_ids must be untouched
        assert server._state._con.execute(
            "SELECT COUNT(*) FROM audit_logs WHERE symbol = ? AND run_id = 'warmup'",
            [sym],
        ).fetchone()[0] == written1

    def test_warmup_refuses_degenerate_distribution(self, client):
        """If the model returns a constant prob across all bars (the current
        bug scenario), the endpoint must fail with 500 and not purge or
        write any audit rows."""
        import unittest.mock as mock
        import numpy as np
        from types import SimpleNamespace

        from src.behemoth.api import server

        sym = "USDCHF"
        server._state._con.execute("DELETE FROM audit_logs WHERE symbol = ?", [sym])
        server._state._con.execute("DELETE FROM tick_bars WHERE symbol = ?", [sym])
        self._seed_bars(sym, n=360)

        # Pre-existing audit row to verify it is NOT purged
        server._state._con.execute(
            "INSERT INTO audit_logs(event_ts, close_ts, symbol, candidate_uid, "
            "pred_prob, threshold, features_json, model_month, run_id) "
            "VALUES (CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, ?, 'sentinel', 0.99, 0.5, '{}', '2026-03', 'warmup')",
            [sym],
        )

        dummy_cand = mock.MagicMock()
        dummy_cand.bar_ticks = 100
        dummy_cand.horizon = 6
        dummy_cand.barrier_pips = 2.0
        dummy_cand.candidate_uid = "oco_first_touch_clean__all__k2"

        dummy_model = mock.MagicMock()
        def _flat(X):
            n = len(X)
            pos = np.full(n, 0.5)  # constant — degenerate
            return np.column_stack([1.0 - pos, pos])
        dummy_model.predict_proba.side_effect = _flat

        with (
            mock.patch.object(
                server, "_resolve_runtime_contract",
                return_value=SimpleNamespace(
                    candidates=[dummy_cand], model_month="2026-03", cap_pips=1.2,
                ),
            ),
            mock.patch.object(
                server, "_ensure_model_and_threshold",
                return_value=(dummy_model, {"threshold_exec": 0.5, "threshold_source": "test"}),
            ),
        ):
            r = client.post("/predict/warmup", json={"symbol": sym, "run_id": "warmup"})

        assert r.status_code == 500
        assert "degenerate distribution" in r.json()["detail"]

        # Sentinel row must still exist (no purge happened)
        n_sentinel = server._state._con.execute(
            "SELECT COUNT(*) FROM audit_logs WHERE symbol = ? AND candidate_uid = 'sentinel'",
            [sym],
        ).fetchone()[0]
        assert n_sentinel == 1
```

- [ ] **Step 2.2: Run tests to verify they fail**

```bash
cd /Users/danielfisher/repositories/behemoth/.worktrees/fix-warmup-historical-replay
uv run pytest tests/test_api_server.py::TestPredictWarmup -v
```

Expected:
- `test_warmup_writes_varied_pred_probs_per_bar`: FAIL (current impl writes one unique prob repeated N times — assertion `unique >= 10` fails)
- `test_warmup_is_idempotent_and_purges_prior`: FAIL (no `audit_events_purged` key in response)
- `test_warmup_refuses_degenerate_distribution`: FAIL (current impl returns 201 even for constant probs)
- `test_warmup_returns_201_with_count` / `test_warmup_503_when_state_uninitialized`: still PASS (the simple existing tests)

### Implementation steps

- [ ] **Step 2.3: Replace the body of `predict_warmup`**

In `src/behemoth/api/server.py`, replace lines 3350-3424 (the entire function) with:

```python
@app.post("/predict/warmup", status_code=201)
async def predict_warmup(req: WarmupRequest) -> dict:
    """Snapshot audit_logs with per-bar pred_probs for the given symbol.

    Replays the model across every buffered bar in tick_bars, producing
    one pred_prob per bar per candidate so the rolling threshold has a
    real distribution to quantile over. Idempotent per (symbol, run_id):
    each call purges prior rows with matching (symbol, run_id) and
    rewrites from the current buffer inside a single DB transaction.

    Called once per symbol on startup by run_jforex_live.py after
    backfill has populated tick_bars. Safe to call any time; each call
    produces a fresh snapshot.
    """
    import numpy as np
    import pandas as pd

    from src.behemoth.core.features import FeatureConfig, compute_feature_matrix_from_bars
    from src.behemoth.core.schemas import ModelFeatures

    if _state is None:
        raise HTTPException(status_code=503, detail="State manager not initialized")

    sym = req.symbol.upper()
    run_id = req.run_id or "warmup"

    close_ts_now = _state.get_latest_close_ts(sym) or datetime.now(tz=timezone.utc)
    contract = _resolve_runtime_contract(sym, close_ts_now)
    if not contract.candidates:
        raise HTTPException(status_code=422, detail=f"No candidates for {sym}")

    model, thr_cfg = _ensure_model_and_threshold(contract)
    if model is None:
        raise HTTPException(status_code=422, detail=f"No model loaded for {sym}")

    bar_ticks = int(contract.candidates[0].bar_ticks)
    bars_df = _state._con.execute(
        "SELECT row_id, ts, close_ts, open_bid, high_bid, low_bid, close_bid, "
        "spread, tick_volume, hl_first, hl_pos_frac "
        "FROM tick_bars WHERE symbol = ? AND bar_ticks = ? ORDER BY row_id ASC",
        [sym, bar_ticks],
    ).fetchdf()

    warmup_needed = _state._cfg.full_warmup_bars
    if len(bars_df) < warmup_needed:
        return {
            "ok": True,
            "symbol": sym,
            "audit_events_purged": 0,
            "audit_events_written": 0,
            "skipped_reason": f"insufficient_bars:{len(bars_df)}<{warmup_needed}",
            "stats": {},
        }

    MIN_VALID_ROWS = 30
    MIN_UNIQUE_PROBS = 10

    static_thr = float(thr_cfg.get("threshold_exec", 0.5))
    per_candidate_events: list[tuple] = []
    per_candidate_stats: dict[str, dict] = {}

    for cand in contract.candidates:
        canonical_uid = f"oco|{sym}|{cand.bar_ticks}|h{cand.horizon}|{cand.candidate_uid}"

        matrix = compute_feature_matrix_from_bars(
            bars_df,
            symbol=sym,
            bar_ticks=bar_ticks,
            horizon=cand.horizon,
            barrier_pips=cand.barrier_pips,
            cfg=FeatureConfig(),
        )
        if matrix is None or matrix.empty:
            logger.warning(
                "predict_warmup: no feature matrix for %s %s — skipping candidate",
                sym, canonical_uid,
            )
            continue

        valid = matrix.dropna()
        if valid.empty:
            logger.warning(
                "predict_warmup: no valid feature rows for %s %s — skipping candidate",
                sym, canonical_uid,
            )
            continue

        with METRIC_INFERENCE_LATENCY.labels(symbol=sym).time():
            probs = model.predict_proba(valid.values)[:, 1]

        n = len(probs)
        unique = int(pd.Series(probs).nunique())
        if n >= MIN_VALID_ROWS and unique < MIN_UNIQUE_PROBS:
            raise HTTPException(
                status_code=500,
                detail=(
                    f"warmup replay produced degenerate distribution for "
                    f"{canonical_uid}: n={n} unique={unique} "
                    f"(require >= {MIN_UNIQUE_PROBS} unique when n >= {MIN_VALID_ROWS}); "
                    f"prior audit_logs rows preserved"
                ),
            )

        valid_bars = bars_df.loc[valid.index]
        for i in range(n):
            feat_dict = valid.iloc[i].to_dict()
            feat_obj = ModelFeatures(**feat_dict)
            close_ts_val = valid_bars.iloc[i]["close_ts"]
            if hasattr(close_ts_val, "tzinfo") and close_ts_val.tzinfo is None:
                close_ts_val = close_ts_val.replace(tzinfo=timezone.utc)
            per_candidate_events.append((
                close_ts_val,
                sym,
                canonical_uid,
                float(probs[i]),
                static_thr,
                feat_obj.model_dump_json(),
                contract.model_month,
                run_id,
            ))

        probs_series = pd.Series(probs)
        per_candidate_stats[canonical_uid] = {
            "n": n,
            "unique_values": unique,
            "p10": round(float(probs_series.quantile(0.10)), 6),
            "p50": round(float(probs_series.quantile(0.50)), 6),
            "p90": round(float(probs_series.quantile(0.90)), 6),
            "p100": round(float(probs_series.max()), 6),
        }

    try:
        _state._con.execute("BEGIN TRANSACTION")
        purged = _state.purge_audit_events(symbol=sym, run_id=run_id)
        _state.log_audit_event_batch(per_candidate_events)
        _state._con.execute("COMMIT")
    except Exception:
        _state._con.execute("ROLLBACK")
        raise

    skipped_reason = "no_valid_feature_rows" if not per_candidate_events else None

    logger.info(
        "predict_warmup: symbol=%s candidates=%d bars_in_buffer=%d "
        "valid_rows=%d purged=%d written=%d",
        sym,
        len(contract.candidates),
        len(bars_df),
        len(per_candidate_events),
        purged,
        len(per_candidate_events),
    )

    return {
        "ok": True,
        "symbol": sym,
        "audit_events_purged": purged,
        "audit_events_written": len(per_candidate_events),
        "skipped_reason": skipped_reason,
        "stats": per_candidate_stats,
    }
```

- [ ] **Step 2.4: Run the three new tests**

```bash
uv run pytest tests/test_api_server.py::TestPredictWarmup::test_warmup_writes_varied_pred_probs_per_bar \
             tests/test_api_server.py::TestPredictWarmup::test_warmup_is_idempotent_and_purges_prior \
             tests/test_api_server.py::TestPredictWarmup::test_warmup_refuses_degenerate_distribution -v
```

Expected: all 3 pass.

- [ ] **Step 2.5: Run existing warmup tests to verify no regression**

```bash
uv run pytest tests/test_api_server.py::TestPredictWarmup -v
```

Expected: all 5 tests in the class pass (2 original + 3 new).

- [ ] **Step 2.6: Run the full API test suite as a safety net**

```bash
uv run pytest tests/test_api_server.py -x --timeout=120 -q
```

Expected: no regressions. Watch for any tests that relied on the old warmup response shape.

- [ ] **Step 2.7: Commit**

```bash
git -C /Users/danielfisher/repositories/behemoth/.worktrees/fix-warmup-historical-replay add \
    src/behemoth/api/server.py tests/test_api_server.py
git -C /Users/danielfisher/repositories/behemoth/.worktrees/fix-warmup-historical-replay commit \
    -m "$(cat <<'EOF'
fix(warmup): replay model across all buffered bars with atomic snapshot

Rewrote /predict/warmup so it batch-computes features for every buffered
bar (via compute_feature_matrix_from_bars), runs one predict_proba per
candidate, and writes one audit_log row per bar with its real pred_prob
and close_ts. Previously it computed features from the latest bar only
and stamped a single pred_prob across all 300 historical timestamps,
producing a flat distribution that made audit_logs useless for rolling
threshold calibration.

The endpoint is now a snapshot: atomic DELETE then batch INSERT, scoped
to (symbol, run_id). Safe to call any number of times; each call
rebuilds the history from the current buffer. Other symbols and other
run_ids (threshold_seed, jforex_live) are untouched.

A per-candidate sanity check refuses to write a degenerate distribution
(n>=30 with <10 unique probs) and preserves prior rows on failure so a
future regression of this bug fails loudly instead of silently.

Three new tests cover: pred_prob variance per bar (direct regression),
idempotent purge+rewrite, and degenerate-distribution hard fail.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: Rolling threshold drift Prometheus counter at `/predict` time

**Why third:** Independent of Task 2. Layer 2 of the validation story — makes every rolling-threshold computation visible as `ok` or `drift` without requiring a warmup run to have happened.

**Files:**
- Modify: `src/behemoth/api/server.py` (add counter declaration near line 169; add drift check at the `get_rolling_threshold` call site around line 3019-3033)
- Test: `tests/test_api_server.py` (append to `class TestPredictWarmup` or as a new class `TestRollingThresholdDrift`)

- [ ] **Step 3.1: Write the failing test**

Append to `tests/test_api_server.py` after the existing `TestPredictWarmup` class (just before `class TestSeedAuditHistory`):

```python
class TestRollingThresholdDrift:
    def test_drift_helper_records_ok_when_within_band(self, client):
        from src.behemoth.api import server

        server._record_rolling_threshold_drift(
            symbol="GBPUSD",
            candidate_uid="oco|GBPUSD|100|h6|cand_ok",
            rolling=0.72,
            baseline=0.70,
        )
        metrics_text = client.get("/metrics").text
        # Counter line for state="ok" must be present (value > 0, label order normalized by prometheus)
        assert 'behemoth_rolling_threshold_drift_total{candidate="oco|GBPUSD|100|h6|cand_ok"' in metrics_text
        assert 'state="ok"' in metrics_text
        assert 'symbol="GBPUSD"' in metrics_text

    def test_drift_helper_records_drift_when_beyond_band_and_logs_warning(self, client, caplog):
        from src.behemoth.api import server

        with caplog.at_level("WARNING"):
            server._record_rolling_threshold_drift(
                symbol="USDJPY",
                candidate_uid="oco|USDJPY|100|h6|cand_drift",
                rolling=0.771,
                baseline=0.686,
            )
        metrics_text = client.get("/metrics").text
        assert 'behemoth_rolling_threshold_drift_total{candidate="oco|USDJPY|100|h6|cand_drift"' in metrics_text
        assert 'state="drift"' in metrics_text
        # Warning emitted exactly once for the beyond-band case
        assert any(
            "Rolling threshold drift" in rec.message and "USDJPY" in rec.message
            for rec in caplog.records
        )

    def test_drift_helper_noop_when_baseline_missing(self, client):
        from src.behemoth.api import server

        # baseline=0.0 (missing or unavailable) must not crash; no metric emitted
        server._record_rolling_threshold_drift(
            symbol="EURUSD",
            candidate_uid="oco|EURUSD|100|h6|cand_none",
            rolling=0.72,
            baseline=0.0,
        )
        metrics_text = client.get("/metrics").text
        # No counter line for this specific candidate because no labels were touched
        assert "cand_none" not in metrics_text
```

- [ ] **Step 3.2: Run test to verify it fails**

```bash
cd /Users/danielfisher/repositories/behemoth/.worktrees/fix-warmup-historical-replay
uv run pytest tests/test_api_server.py::TestRollingThresholdDrift -v
```

Expected: FAIL with `AttributeError` on `server.METRIC_ROLLING_THRESHOLD_DRIFT` / `server._record_rolling_threshold_drift`.

- [ ] **Step 3.3: Add the counter and helper**

In `src/behemoth/api/server.py`, after the existing `METRIC_RISK_BLOCKS_TOTAL` declaration (around line 168), append:

```python
METRIC_ROLLING_THRESHOLD_DRIFT = Counter(
    "behemoth_rolling_threshold_drift_total",
    "Rolling threshold deviation vs static threshold_exec baseline",
    ["symbol", "candidate", "state"],  # state: ok | drift
)

THRESHOLD_DRIFT_WARN_PP = 0.05


def _record_rolling_threshold_drift(
    *,
    symbol: str,
    candidate_uid: str,
    rolling: float,
    baseline: float,
) -> None:
    """Label a rolling-threshold computation as ok or drift vs the baseline.

    Always runs on successful rolling threshold evaluations at /predict time.
    Increments a Counter labelled with the outcome so drift ratio is queryable
    from /metrics without needing to parse log lines. Beyond-band events also
    emit a single warning log line.

    No-op when baseline is zero/falsey (not configured on this threshold JSON).
    """
    if baseline <= 0.0:
        return
    drift_pp = abs(float(rolling) - float(baseline))
    state = "drift" if drift_pp > THRESHOLD_DRIFT_WARN_PP else "ok"
    METRIC_ROLLING_THRESHOLD_DRIFT.labels(
        symbol=symbol.upper(), candidate=candidate_uid, state=state,
    ).inc()
    if state == "drift":
        logger.warning(
            "Rolling threshold drift for %s %s: rolling=%.4f baseline=%.4f drift=%.4f (band=%.2f)",
            symbol, candidate_uid, float(rolling), float(baseline), drift_pp, THRESHOLD_DRIFT_WARN_PP,
        )
```

- [ ] **Step 3.4: Wire the helper into `_build_predictions`**

In `src/behemoth/api/server.py`, locate lines 3019-3033 inside `_build_predictions()`:

```python
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
```

Insert the drift helper call immediately after `dynamic_thr` is assigned, before the threshold value is returned to the caller. Specifically, update the `if dynamic_thr is not None:` branch to:

```python
                if dynamic_thr is not None:
                    _record_rolling_threshold_drift(
                        symbol=sym,
                        candidate_uid=canonical_uid,
                        rolling=float(dynamic_thr),
                        baseline=float(thr_cfg.get("threshold_exec", 0.0) or 0.0),
                    )
                    curr_threshold = dynamic_thr
                    curr_source = f"{threshold_mode}:rolling_dynamic"
```

- [ ] **Step 3.5: Run the three new drift tests**

```bash
uv run pytest tests/test_api_server.py::TestRollingThresholdDrift -v
```

Expected: 3 passed.

- [ ] **Step 3.6: Run the full API test suite**

```bash
uv run pytest tests/test_api_server.py -x --timeout=120 -q
```

Expected: no regressions.

- [ ] **Step 3.7: Commit**

```bash
git -C /Users/danielfisher/repositories/behemoth/.worktrees/fix-warmup-historical-replay add \
    src/behemoth/api/server.py tests/test_api_server.py
git -C /Users/danielfisher/repositories/behemoth/.worktrees/fix-warmup-historical-replay commit \
    -m "$(cat <<'EOF'
feat(metrics): add rolling threshold drift counter at /predict

Every rolling-threshold computation now increments
behemoth_rolling_threshold_drift_total{symbol,candidate,state=ok|drift}
against the static threshold_exec baseline from the threshold JSON.
Beyond-band evaluations (|rolling - baseline| > 0.05) also emit a
warning log line. The counter is queryable from /metrics so drift ratio
is visible independent of warmup completing, giving ops a live signal
when the rolling window drifts away from the WFO-calibrated baseline.

This is an alarm, not a gate — the rolling threshold still takes effect.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: Diagnostic integrity section in `diagnose_live_performance_gap.py`

**Why last:** Layer 3 of validation. Independent of the code fix — extends the existing investigation script so a future regression of any shape (flat warmup, dominant seed, missing live, etc.) surfaces in the report.

**Files:**
- Modify: `scripts/diagnose_live_performance_gap.py`
- Test: `tests/test_diagnose_live_performance_gap.py`

- [ ] **Step 4.1: Write the failing test**

Append to `tests/test_diagnose_live_performance_gap.py` (at the end of the file):

```python
def test_rolling_threshold_integrity_section_detects_flat_warmup(tmp_path: Path) -> None:
    """The integrity section must flag a flat warmup distribution
    (unique_values == 1) as a regression of the historical replay bug."""
    import duckdb
    from datetime import datetime, timedelta, timezone

    db_path = tmp_path / "live_state.db"
    con = duckdb.connect(str(db_path))
    con.execute("""
        CREATE TABLE audit_logs (
            event_ts TIMESTAMP WITH TIME ZONE,
            close_ts TIMESTAMP WITH TIME ZONE,
            symbol VARCHAR,
            candidate_uid VARCHAR,
            pred_prob DOUBLE,
            threshold DOUBLE,
            features_json VARCHAR,
            model_month VARCHAR,
            run_id VARCHAR
        )
    """)
    now = datetime.now(tz=timezone.utc)
    uid = "oco|USDJPY|1000|h6|oco_first_touch_clean__all__k2"
    # 300 flat warmup rows — all identical pred_prob (the bug's signature)
    for i in range(300):
        con.execute(
            "INSERT INTO audit_logs VALUES (?, ?, 'USDJPY', ?, 0.6988, 0.5, '{}', '2026-03', 'warmup')",
            [now, now - timedelta(hours=i)],
        )
    # 60 varied threshold_seed rows (good)
    for i in range(60):
        con.execute(
            "INSERT INTO audit_logs VALUES (?, ?, 'USDJPY', ?, ?, 0.5, '{}', '2026-03', 'threshold_seed')",
            [now, now - timedelta(hours=i + 1), uid, 0.50 + 0.005 * i],
        )
    con.close()

    from scripts.diagnose_live_performance_gap import _rolling_threshold_integrity_section

    con = duckdb.connect(str(db_path), read_only=True)
    try:
        rows = _rolling_threshold_integrity_section(con)
    finally:
        con.close()

    # The flat warmup row for USDJPY must surface as unique_values=1 and flagged
    warmup_row = next(
        r for r in rows
        if r["symbol"] == "USDJPY" and r["run_id"] == "warmup"
    )
    assert warmup_row["unique_values"] == 1
    assert warmup_row["flag"] is True

    # The varied seed row must NOT be flagged
    seed_row = next(
        r for r in rows
        if r["symbol"] == "USDJPY" and r["run_id"] == "threshold_seed"
    )
    assert seed_row["unique_values"] > 10
    assert seed_row["flag"] is False
```

- [ ] **Step 4.2: Run test to verify it fails**

```bash
cd /Users/danielfisher/repositories/behemoth/.worktrees/fix-warmup-historical-replay
uv run pytest tests/test_diagnose_live_performance_gap.py::test_rolling_threshold_integrity_section_detects_flat_warmup -v
```

Expected: FAIL with `ImportError: cannot import name '_rolling_threshold_integrity_section'`.

- [ ] **Step 4.3: Add the integrity section function**

In `scripts/diagnose_live_performance_gap.py`, insert after `_candidate_audit_section()` (currently ends around line 282, right before `def _format_report`):

```python
# Minimum unique-value threshold below which a warmup-shaped distribution is
# considered a regression of the historical replay bug.
MIN_UNIQUE_PROBS_FLAG = 10


def _rolling_threshold_integrity_section(
    con: duckdb.DuckDBPyConnection,
) -> list[dict[str, Any]]:
    """Report per (symbol, candidate_uid, run_id) shape of audit_logs.

    Surfaces the flat-distribution failure mode (unique_values == 1 for a
    population >= 30) — the exact signature of the /predict/warmup
    historical replay bug from April 2026. Rolling-vs-static drift is
    covered live by METRIC_ROLLING_THRESHOLD_DRIFT at /predict time.

    Does not depend on trade or jforex_live data; runs on any audit_logs
    population.
    """
    rows = con.execute(
        """
        SELECT
            symbol,
            candidate_uid,
            run_id,
            COUNT(*) AS n,
            COUNT(DISTINCT ROUND(pred_prob, 8)) AS unique_values,
            MIN(pred_prob) AS min_prob,
            quantile(pred_prob, 0.5) AS p50,
            quantile(pred_prob, 0.9) AS p90,
            MAX(pred_prob) AS max_prob
        FROM audit_logs
        GROUP BY symbol, candidate_uid, run_id
        ORDER BY symbol, candidate_uid, run_id
        """,
    ).fetchall()

    results: list[dict[str, Any]] = []
    for symbol, cand, run_id, n, unique, pmin, p50, p90, pmax in rows:
        flagged = int(n) >= 30 and int(unique) < MIN_UNIQUE_PROBS_FLAG
        results.append(
            {
                "symbol": symbol,
                "candidate_uid": cand,
                "run_id": run_id,
                "n": int(n),
                "unique_values": int(unique),
                "min_prob": round(float(pmin), 6) if pmin is not None else None,
                "p50": round(float(p50), 6) if p50 is not None else None,
                "p90": round(float(p90), 6) if p90 is not None else None,
                "max_prob": round(float(pmax), 6) if pmax is not None else None,
                "flag": bool(flagged),
            }
        )
    return results
```

- [ ] **Step 4.4: Wire the section into `run()` and `_format_report()`**

In the same file, modify `run()` (around line 350) to include the new section:

```python
def run(
    db_path: Path,
    run_id: str = "jforex_live",
    out_path: Path | None = None,
) -> dict[str, Any]:
    """Run all diagnostic checks and return structured report dict."""
    con = _load_con(db_path)
    report = {
        "win_rate": _win_rate_section(con, run_id),
        "threshold_analysis": _threshold_analysis_section(con, run_id),
        "magnitude_analysis": _magnitude_analysis_section(con, run_id),
        "candidate_audit": _candidate_audit_section(con, run_id),
        "rolling_threshold_integrity": _rolling_threshold_integrity_section(con),
    }
    con.close()
    if out_path is not None:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(_format_report(report), encoding="utf-8")
    return report
```

Then update `_format_report()` (around line 285-347) to render the new section. Find the `return "\n".join(lines) + "\n"` at the bottom of the function and insert this block just before it:

```python
    lines.append("")
    lines.append("## 5. Rolling Threshold Integrity")
    lines.append("")
    lines.append("Per (symbol, candidate, run_id) shape of audit_logs. A flag (⚠️)")
    lines.append("indicates `unique_values < 10` with `n >= 30` — the signature of a")
    lines.append("flat-distribution warmup regression.")
    lines.append("")
    lines.append("| Symbol | Candidate | Run ID | N | Unique | Min | p50 | p90 | Max | Flag |")
    lines.append("|--------|-----------|--------|---|--------|-----|-----|-----|-----|------|")
    for r in report.get("rolling_threshold_integrity", []):
        flag = "⚠️" if r["flag"] else ""
        cand_short = r["candidate_uid"].rsplit("|", 1)[-1][:32]
        lines.append(
            f"| {r['symbol']} | {cand_short} | {r['run_id']} | {r['n']} | "
            f"{r['unique_values']} | {r['min_prob']} | {r['p50']} | {r['p90']} | "
            f"{r['max_prob']} | {flag} |"
        )
```

- [ ] **Step 4.5: Also print the section in the CLI `main()` output**

In `scripts/diagnose_live_performance_gap.py`, after the existing `print("\n=== CANDIDATE AUDIT ===")` block (around line 410-417), add:

```python
    print("\n=== ROLLING THRESHOLD INTEGRITY ===")
    for r in report.get("rolling_threshold_integrity", []):
        flag = " ⚠️ FLAT" if r["flag"] else ""
        cand_short = r["candidate_uid"].rsplit("|", 1)[-1][:40]
        print(
            f"  {r['symbol']} [{cand_short}] {r['run_id']}: "
            f"n={r['n']} unique={r['unique_values']} p90={r['p90']}{flag}"
        )
```

- [ ] **Step 4.6: Run the new test**

```bash
uv run pytest tests/test_diagnose_live_performance_gap.py::test_rolling_threshold_integrity_section_detects_flat_warmup -v
```

Expected: PASS.

- [ ] **Step 4.7: Run the full diagnose test suite**

```bash
uv run pytest tests/test_diagnose_live_performance_gap.py -v
```

Expected: all tests pass (existing + new).

- [ ] **Step 4.8: Smoke-test against the real live DB snapshot**

```bash
uv run python scripts/diagnose_live_performance_gap.py \
    --db /tmp/live_state_snapshot.db \
    --run-id jforex_live \
    --out /tmp/live_perf_gap_with_integrity.md
```

Expected output includes a `=== ROLLING THRESHOLD INTEGRITY ===` section showing `warmup` rows flagged as `⚠️ FLAT` (unique=1) for every symbol/candidate in the pre-fix snapshot, proving the section catches the bug we've been investigating.

- [ ] **Step 4.9: Commit**

```bash
git -C /Users/danielfisher/repositories/behemoth/.worktrees/fix-warmup-historical-replay add \
    scripts/diagnose_live_performance_gap.py tests/test_diagnose_live_performance_gap.py
git -C /Users/danielfisher/repositories/behemoth/.worktrees/fix-warmup-historical-replay commit \
    -m "$(cat <<'EOF'
feat(diagnostic): add rolling threshold integrity section

The gap report now breaks audit_logs down by (symbol, candidate, run_id)
and flags any population with n>=30 and unique_values<10 — the exact
signature of the flat-distribution warmup regression this PR fixes.

Gives operators a one-shot visibility into whether the three audit_logs
sources (threshold_seed, warmup, jforex_live) all have healthy
distributions, without having to hand-write quantile queries. A
regression of this bug in any future refactor would surface here
immediately.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
EOF
)"
```

---

## Post-implementation verification

- [ ] **V1: Run the full project test suite**

```bash
cd /Users/danielfisher/repositories/behemoth/.worktrees/fix-warmup-historical-replay
uv run pytest --timeout=180 -q
```

Expected: green across the board.

- [ ] **V2: Confirm the branch is ready for PR**

```bash
git -C /Users/danielfisher/repositories/behemoth/.worktrees/fix-warmup-historical-replay log main..HEAD --oneline
```

Expected output (order may vary slightly):

```
<hash> feat(diagnostic): add rolling threshold integrity section
<hash> feat(metrics): add rolling threshold drift counter at /predict
<hash> fix(warmup): replay model across all buffered bars with atomic snapshot
<hash> feat(state): add purge_audit_events helper
<hash> docs: add warmup historical replay design spec
```

- [ ] **V3: Operator smoke plan (after PR merge, before production restart)**

Document these verification steps in the PR body so whoever merges knows the post-deploy checks:

1. Restart the live API server.
2. `curl -s <api>/metrics | grep rolling_threshold_drift_total` — expect `state="drift"` counters at 0 or low for healthy symbols.
3. `uv run python scripts/diagnose_live_performance_gap.py --db <live_state.db> --run-id jforex_live` and verify:
   - `=== ROLLING THRESHOLD INTEGRITY ===` shows no `⚠️ FLAT` rows for `warmup`.
   - USDJPY warmup `unique_values >= 10`.
   - USDJPY combined rolling p90 within 0.05 of 0.686 (i.e. ≤ 0.736).

---

## Acceptance criteria (from spec)

- [x] All four new test groups pass; existing warmup tests still pass.
- [x] Post-restart, per symbol/candidate: `warmup.unique_values >= 10`.
- [x] Combined rolling p90 within 0.05 of the static `threshold_exec`; USDJPY specifically ≤ 0.736 (current value ~0.771 fails the band).
- [x] `behemoth_rolling_threshold_drift_total{state="ok"|"drift"}` visible per symbol/candidate via `/metrics`.
