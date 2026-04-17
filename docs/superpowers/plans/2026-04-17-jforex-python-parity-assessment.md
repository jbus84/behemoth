# JForex Live vs Python Backtest Parity Assessment — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Produce a one-shot divergence inventory report for JForex live vs Python backtest across Core trading / Lifecycle / Risk+Governance / Time+Data layers plus three shortlisted failure paths, and ship a durable `scripts/audit_runtime_parity.py` harness that runs per-session and fails Stage 14 cert on known-divergence patterns.

**Architecture:** Two artifacts in one plan cycle: (1) markdown inventory at `docs/analysis/2026-04-17-jforex-python-parity-assessment.md` built from static code audit across `src/behemoth/` and `src/jforex/src/main/java/` plus a 2026-04-15 replay day across AUDUSD + USDCHF + EURUSD; (2) standalone `scripts/audit_runtime_parity.py` driven by a check registry under `src/behemoth/parity/checks/` with 8 seed checks, wired into `make stage14-jforex-cert` and the demo-live wrap-up.

**Tech Stack:** Python 3.12 (pandas, duckdb, pytest), pre-existing Java JForex runtime (read-only for this plan), pre-existing research pipeline scripts (`verify_oco_tick_exact_shortlist.py`, `validate_stage14_jforex_runtime_certification.py`, `build_demo_live_offline_comparison_report.py`).

**Spec:** `docs/superpowers/specs/2026-04-17-jforex-python-parity-assessment-design.md`

**Target branch:** `fix/2026-03-live-promote-and-recert-fixes` (or a worktree branched from it). Per user convention, develop in a worktree and land via PR.

---

## File structure

Files created by this plan:

| Path | Responsibility |
|---|---|
| `docs/analysis/2026-04-17-jforex-python-parity-assessment.md` | The gap inventory report (one-shot). |
| `src/behemoth/parity/__init__.py` | Package marker. |
| `src/behemoth/parity/registry.py` | `register_check` decorator + registry storage. |
| `src/behemoth/parity/types.py` | `CheckContext` and `CheckResult` dataclasses. |
| `src/behemoth/parity/loader.py` | Shared input loaders (CSVs, live_state.db, governance lock, active_oco_state). |
| `src/behemoth/parity/checks/__init__.py` | Imports every check module so decorators register at load time. |
| `src/behemoth/parity/checks/core_predict_cycles_per_bar.py` | Seed check 1. |
| `src/behemoth/parity/checks/risk_gov_governance_lock_pin.py` | Seed check 2. |
| `src/behemoth/parity/checks/core_tick_seq_monotonic.py` | Seed check 3. |
| `src/behemoth/parity/checks/lifecycle_active_oco_reconciled.py` | Seed check 4. |
| `src/behemoth/parity/checks/failure_tick_batch_599_fallback.py` | Seed check 5. |
| `src/behemoth/parity/checks/failure_predict_422_warmup_only.py` | Seed check 6. |
| `src/behemoth/parity/checks/core_entries_allowed_vs_readiness.py` | Seed check 7. |
| `src/behemoth/parity/checks/time_data_bar_close_ts_sorted.py` | Seed check 8. |
| `scripts/audit_runtime_parity.py` | CLI entry point. |
| `scripts/diff_parity_replay.py` | One-shot replay diff (run once, output archived under `data/analysis/backtest_reconcile/replay_diff/2026-04-15/`). |
| `tests/parity/__init__.py` | Package marker. |
| `tests/parity/conftest.py` | Shared fixtures (good + bad CheckContext factories seeded from 2026-04-17 evidence). |
| `tests/parity/checks/__init__.py` | Package marker. |
| `tests/parity/checks/test_<surface>.py` (×8) | One unit test file per seed check — good fixture + bad fixture. |
| `tests/parity/test_registry.py` | Registry tests (decorator + collision + unknown surface_id). |
| `tests/parity/test_loader.py` | Loader tests (missing input, locked DB, empty CSV). |
| `tests/test_audit_runtime_parity.py` | Harness smoke test. |
| `tests/test_parity_audit_inventory.py` | Inventory ↔ registry coverage test. |

Files modified:

| Path | Change |
|---|---|
| `Makefile` | Add `audit-runtime-parity` target; `stage14-jforex-cert` invokes it after the existing validate script. |
| `scripts/build_demo_live_offline_comparison_report.py` | Add Phase 3 hook that runs `audit_runtime_parity.py` after the session ends. |

---

## Task 0: Create the worktree

**Files:** none (infrastructure)

- [ ] **Step 1: Create a worktree branched from the target branch**

Run:

```bash
cd /Users/danielfisher/repositories/behemoth
git fetch origin
git worktree add ../behemoth-parity-assessment fix/2026-03-live-promote-and-recert-fixes
cd ../behemoth-parity-assessment
git checkout -b feat/jforex-python-parity-assessment
```

Expected: new working tree at `../behemoth-parity-assessment` on branch `feat/jforex-python-parity-assessment`.

- [ ] **Step 2: Confirm mise + uv environment loads**

Run:

```bash
mise install
uv run python -c "import pandas, duckdb, pytest; print('ok')"
```

Expected: `ok`.

- [ ] **Step 3: Commit the empty-branch marker**

Run:

```bash
git commit --allow-empty -m "chore: open parity-assessment branch"
```

Expected: commit made.

---

## Task 1: Inventory report skeleton

**Files:**
- Create: `docs/analysis/2026-04-17-jforex-python-parity-assessment.md`

- [ ] **Step 1: Write the skeleton**

Write this exact content to `docs/analysis/2026-04-17-jforex-python-parity-assessment.md`:

```markdown
# JForex Live vs Python Backtest Parity Assessment

**Date:** 2026-04-17
**Spec:** docs/superpowers/specs/2026-04-17-jforex-python-parity-assessment-design.md
**Replay day:** 2026-04-15
**Replay symbols:** AUDUSD, USDCHF, EURUSD
**Harness symbols:** all 6 live symbols

## Executive summary

_Pending. Populated in Task 25._

## Methodology

Static code audit across:
- Python: `src/behemoth/`, `src/behemoth/runtime/`, `src/behemoth/api/server.py`, research scripts.
- JForex: `src/jforex/src/main/java/com/behemoth/jforex/**`.

Replay evidence: 2026-04-15 × 3 symbols. Side A = Stage 14 JForex tester. Side B = `scripts/verify_oco_tick_exact_shortlist.py`. Diff in `data/analysis/backtest_reconcile/replay_diff/2026-04-15/parity_replay_diff.parquet`.

Tolerances:
- `pred_prob`: ≤1e-6 absolute
- `fill_price`: ≤1 pip, symbol-aware (JPY crosses use 0.01 pip_size, others 0.0001)
- `gross_pips_outcome`: ≤2 pips
- Tick/bar timestamps: exact to the millisecond

## Surfaces — Core trading path

_Pending. Populated in Task 2._

## Surfaces — Lifecycle & state

_Pending. Populated in Task 3._

## Surfaces — Risk & governance

_Pending. Populated in Task 4._

## Surfaces — Time & data

_Pending. Populated in Task 5._

## Surfaces — Failure paths

_Pending. Populated in Task 6._

## Replay diff findings

_Pending. Populated in Task 10._

## Harness coverage matrix

_Pending. Populated in Task 25._

## Appendix — Replay diff artifact index

_Pending. Populated in Task 25._
```

- [ ] **Step 2: Commit**

```bash
git add docs/analysis/2026-04-17-jforex-python-parity-assessment.md
git commit -m "docs(parity): inventory report skeleton"
```

Expected: commit made.

---

## Task 2: Populate Core trading path surfaces

**Files:**
- Modify: `docs/analysis/2026-04-17-jforex-python-parity-assessment.md` — replace the "Surfaces — Core trading path" section.

- [ ] **Step 1: Read the relevant Java + Python loci**

Read (don't modify):
- `src/jforex/src/main/java/com/behemoth/jforex/BehemothJForexStrategy.java`
- `src/jforex/src/main/java/com/behemoth/jforex/core/BehemothStrategyCore.java`
- `src/jforex/src/main/java/com/behemoth/jforex/JForexExecutionPort.java`
- `src/behemoth/api/server.py` — find the `/ticks/batch`, `/predict`, `/trades/open`, `/trades/update` handlers.
- `src/behemoth/runtime/tick_aggregator.py`
- `src/behemoth/runtime/barrier_manager.py`

- [ ] **Step 2: Write the Core section**

Replace the `## Surfaces — Core trading path` section with concrete surfaces. For each surface, fill all 11 fields per the spec's template. Minimum surfaces to cover:

- `core.tick_stream_shape` — Java `onTick` → `/ticks/batch` (batched or single-tick-fallback) vs Python backtest ingesting tick parquet directly.
- `core.bar_boundary_alignment` — bar-close semantics: Java waits for `response.barCompleted` from Python; backtest computes bars in-memory.
- `core.bar_completed_tick_ids` — list of tick ids that closed the bar must match what would have been used offline.
- `core.feature_computation_locus` — features computed server-side in Python; Java never computes features. Surface records that this is by design (no divergence possible on feature formulae, only on inputs).
- `core.prediction_request_payload` — fields in `PredictRequestPayload` (symbol, requested_volume_units, completed_bar_ticks, run_id, bar_ordinals) vs the signature the Python API expects.
- `core.selected_exec_decision` — `pred_prob >= threshold - 1e-9` in Python; Java consumes the response as-is.
- `core.barrier_touch_detection` — `BarrierManager.evaluate_bar` is Python-only; Java calls it via `/predict` return actions. Any divergence is in the inputs (bid/ask/high/low/hl_first), not the logic.
- `core.order_open_market_submit` — `BehemothStrategyCore.executeActions` OPEN_MARKET → `JForexExecutionPort.submitMarketOrder`. Volume sizing is `requestedVolumeUnits / 1_000_000` (millions).
- `core.order_close_market_submit` — CLOSE_MARKET → `executionPort.closePosition(symbol, orderLabel)`. Label must exist in `scanToOrderLabel`.
- `core.fill_ack_syncs_trade_open` — `handleFill` calls `/trades/open` with the actual `openPrice` + `fillTs` from the broker.

Each surface must have the following fields filled:

```markdown
### core.tick_stream_shape

- **layer:** core
- **python_locus:** src/behemoth/runtime/tick_aggregator.py:1-129; src/behemoth/api/server.py (tick_batch handler)
- **jforex_locus:** src/jforex/src/main/java/com/behemoth/jforex/BehemothJForexStrategy.java:115-135; src/jforex/src/main/java/com/behemoth/jforex/core/BehemothStrategyCore.java:92-165
- **contract:** Every tick observed in Dukascopy must arrive at the Python tick aggregator exactly once with a monotonically increasing client_tick_seq.
- **observed_state:** Code: Java batches to sessionConfig.tickBatchSize() then calls /ticks/batch; on 599 timeout, falls back to single-tick ingestion. Python dedupes by client_tick_seq. Replay evidence: _pending Task 10._
- **divergence:** latent
- **severity:** critical
- **evidence:** (populated in Task 10 from replay diff)
- **harness_check:** yes — core.tick_seq_monotonic (see Task 15)
- **fix_owner:** future
```

Write all surfaces following this format. For surfaces where the replay evidence is still pending, put `_pending Task 10._` in the `observed_state` / `evidence` fields; Task 10 back-fills them.

- [ ] **Step 3: Commit**

```bash
git add docs/analysis/2026-04-17-jforex-python-parity-assessment.md
git commit -m "docs(parity): inventory core trading path surfaces"
```

---

## Task 3: Populate Lifecycle & state surfaces

**Files:**
- Modify: `docs/analysis/2026-04-17-jforex-python-parity-assessment.md` — replace the "Surfaces — Lifecycle & state" section.

- [ ] **Step 1: Read the relevant loci**

Read:
- `src/jforex/src/main/java/com/behemoth/jforex/state/ExecutionStateStore.java`
- `src/jforex/src/main/java/com/behemoth/jforex/state/OcoGroupState.java`
- `src/behemoth/runtime/state.py`
- `src/behemoth/runtime/barrier_manager.py` (full, for reservation lifecycle)
- `data/analysis/backtest_reconcile/runtime/live_state.db` — inspect schema via `duckdb -c "PRAGMA show_tables" data/analysis/backtest_reconcile/runtime/live_state.db` (open read-only if the session is still running).

- [ ] **Step 2: Write the Lifecycle section**

Minimum surfaces:

- `lifecycle.client_tick_seq_monotonic` — per-symbol seq in Java `SymbolRuntimeState.nextClientTickSeq`; Python stores highest-seen and rejects regressions.
- `lifecycle.reservation_id_lifecycle` — Python issues reservation_id on signal selection; Java carries it in `PendingFillContext`; must be released on expiry or bound to broker position on fill.
- `lifecycle.active_oco_state_json` — `sessionConfig.reportDir().resolve("runtime/active_oco_state.json")` in Java vs `OcoGroupState` records in Python `live_state.db`. Contract: every JSON entry has a row in the DB and vice versa.
- `lifecycle.barrier_scan_status_transitions` — SCANNING → HOLDING → COMPLETED / EXPIRED (see `barrier_manager.py:176-326`). Live restart must not orphan HOLDING scans.
- `lifecycle.scan_to_order_label_map` — Java-only in-memory map `scanToOrderLabel`; lost on JForex restart. Surface records this as a known recovery gap with severity:critical and fix_owner:future.
- `lifecycle.pending_fills_map` — Java-only `pendingFills` map indexed by order label; FILL_OK consumes. Restart between submit and fill loses the reservation_id/horizon. Severity:critical.
- `lifecycle.bar_ordinals_by_bar_ticks` — Java tracks `state.barOrdinalsByBarTicks` and sends to Python on predict; Python expects a monotonically-increasing ordinal per bar_ticks.

Each surface must be fully populated per the template in Task 2 Step 2.

- [ ] **Step 3: Commit**

```bash
git add docs/analysis/2026-04-17-jforex-python-parity-assessment.md
git commit -m "docs(parity): inventory lifecycle and state surfaces"
```

---

## Task 4: Populate Risk & governance surfaces

**Files:**
- Modify: `docs/analysis/2026-04-17-jforex-python-parity-assessment.md`

- [ ] **Step 1: Read the relevant loci**

Read:
- `src/behemoth/risk/account.py`
- `src/jforex/src/main/java/com/behemoth/jforex/config/JForexSessionConfig.java`
- `src/jforex/src/main/java/com/behemoth/jforex/core/BehemothStrategyCore.java:199-217` (`onAccountSnapshot`)
- `configs/research/governance/oco/audusd_oco_live_lock.json` (any example)
- `scripts/validate_oco_live_governance.py`

- [ ] **Step 2: Write the Risk & governance section**

Minimum surfaces:

- `risk_gov.volume_sizing_source` — Java reads `sessionConfig.requestedVolumeUnits()` and converts to millions (`/ 1_000_000`); Python `risk/account.py` computes sizing from account equity + risk limits. Contract: the volume Python reserves via `/predict` must equal the volume Java actually submits. Severity:critical.
- `risk_gov.governance_lock_model_month` — Python API pins `model_month`; Java does not know the model_month (Python owns it). But the `run_id` the Java side passes must map to a run that is on the current locked month. Severity:critical.
- `risk_gov.governance_lock_hash_integrity` — `*_oco_live_lock.json` has a lock hash + file hash. Check the live run's governance hash matches the locked hash at session start (already done by `validate_oco_live_governance.py`; this surface records the cross-check).
- `risk_gov.run_id_plumbing` — `sessionConfig.runId()` travels on every request (`TickBatchRequestPayload`, `PredictRequestPayload`, `AccountSnapshotRequestPayload`, `TradeOpenRequestPayload`, `TradeUpdateRequestPayload`). Python joins by run_id; a missing or inconsistent run_id silently splits the session into two.
- `risk_gov.account_snapshot_cadence` — `onAccount(IAccount)` fires on broker account events; frequency is broker-dependent. Python risk decisions depend on the latest snapshot; stale snapshots can cause under/over-sizing.
- `risk_gov.entries_allowed_gate` — `SymbolRuntimeState.entriesAllowed` (default true). Set by `LiveReadinessCoordinator` when readiness drops. Surface records that the backtest has no equivalent gate and thus cannot simulate blocked entries.

- [ ] **Step 3: Commit**

```bash
git add docs/analysis/2026-04-17-jforex-python-parity-assessment.md
git commit -m "docs(parity): inventory risk and governance surfaces"
```

---

## Task 5: Populate Time & data surfaces

**Files:**
- Modify: `docs/analysis/2026-04-17-jforex-python-parity-assessment.md`

- [ ] **Step 1: Read the relevant loci**

Read:
- `src/jforex/src/main/java/com/behemoth/jforex/BehemothJForexStrategy.java:115-135` (tick timestamp conversion)
- `src/jforex/src/main/java/com/behemoth/jforex/core/BehemothStrategyCore.java:92-111` (IncomingTickPayload construction)
- `src/behemoth/api/server.py` (search for "timestamp", "tz", "bar_close")
- `scripts/build_global_tick_bars.py` — canonical bar boundary logic
- `scripts/build_tick_velocity_dataset.py` — canonical velocity features
- `AGENTS.md` section 3 (data paths and schema)

- [ ] **Step 2: Write the Time & data section**

Minimum surfaces:

- `time_data.tick_timestamp_source` — Java uses `Instant.ofEpochMilli(tick.getTime())` where `tick.getTime()` is UTC millis from Dukascopy; Python backtest uses parquet `timestamp` column (also UTC). Contract: both are UTC, millisecond-precision.
- `time_data.bid_ask_schema` — AGENTS.md mandates explicit bid/ask bar schema on main. Java forwards `tick.getBid()`, `tick.getAsk()` directly; backtest reads the explicit bid/ask columns. Surface records that implicit-mid is unacceptable on both sides.
- `time_data.spread_handling` — spread = ask - bid, computed server-side in Python. Java never computes spread. OCO barrier sides use `signal_close_ask` for the up-barrier and `signal_close_bid` for the down-barrier (see `barrier_manager.py:85-106`). Surface records this asymmetry as the authoritative contract.
- `time_data.weekend_gap_skip` — Dukascopy feed is silent Fri 22:00 UTC → Sun 22:00 UTC. Backtest tick parquets omit the gap. Surface records that the live side may emit the first-tick-after-gap with an unusually large timestamp delta that must not trigger bar closures prematurely.
- `time_data.dst_boundary` — surface records that we do not expect DST-handling divergence because both sides are UTC end-to-end. Marked as `divergence:none` + `harness_check:no`, but kept in the inventory so the next cycle does not re-derive it.
- `time_data.bar_close_ts_per_bar_ticks` — bar_close_ts in the predict response comes from the tick that closed the bar (last tick of the Nth tick-group). Contract: strictly monotonic per (symbol, bar_ticks) within a session.

- [ ] **Step 3: Commit**

```bash
git add docs/analysis/2026-04-17-jforex-python-parity-assessment.md
git commit -m "docs(parity): inventory time and data surfaces"
```

---

## Task 6: Populate Failure-path shortlist surfaces

**Files:**
- Modify: `docs/analysis/2026-04-17-jforex-python-parity-assessment.md`

- [ ] **Step 1: Read the relevant loci**

Read:
- `src/jforex/src/main/java/com/behemoth/jforex/core/BehemothStrategyCore.java:125-165` (retry loop + single-tick fallback)
- `src/jforex/src/main/java/com/behemoth/jforex/core/BehemothStrategyCore.java:269-277` (predict 422 warmup catch)
- `src/jforex/src/main/java/com/behemoth/jforex/core/BehemothStrategyCore.java:175-197` (order event switch, incl. SUBMIT_REJECTED)
- `src/behemoth/api/server.py` — grep for `Insufficient warmup bars` and `422`.

- [ ] **Step 2: Write the Failure paths section**

Three surfaces (all three are in-scope for this cycle):

- `failure.tick_batch_599_fallback` — on Python API timeout (599 status), Java retries up to `MAX_TICK_BATCH_TIMEOUT_RETRIES` (2) with 250ms backoff, then falls back to per-tick `/tick` calls. Contract: every tick in the original batch is either accepted or dropped exactly once across retry + fallback; no duplicates; no gaps.
- `failure.predict_422_warmup` — on 422 with detail containing "Insufficient warmup bars", Java records `recordPredictWarmup` and returns; does not error. Contract: warmup-skip must be the *only* 422 case handled silently; any other 422 must fail loudly.
- `failure.submit_rejected` — SUBMIT_REJECTED event triggers `recordOrderReject` + `markOperationalStep("order_rejected", false, ...)`. Contract: the corresponding `pendingFills` entry is cleaned up and the reservation_id is released on the Python side. Current known gap: `pendingFills` is removed only inside the `submitMarketOrder` catch block, not on SUBMIT_REJECTED — surface records this as `divergence:observed` if the replay diff confirms it, otherwise `latent`.

- [ ] **Step 3: Commit**

```bash
git add docs/analysis/2026-04-17-jforex-python-parity-assessment.md
git commit -m "docs(parity): inventory failure-path surfaces"
```

---

## Task 7: Side A — run Stage 14 tester for 2026-04-15 × 3 symbols

**Files:** none committed (produces data artifacts under `data/analysis/backtest_reconcile/` — these already exist per-symbol, this task reruns with a narrowed window).

- [ ] **Step 1: Verify tick coverage for 2026-04-15 across the 3 symbols**

Run:

```bash
for sym in AUDUSD USDCHF EURUSD; do
  test -f "/Users/danielfisher/Desktop/dukascopy_ticks/$sym/${sym}_202604_ticks.parquet" && echo "$sym ok" || echo "$sym MISSING"
done
```

Expected: three `ok` lines. If any is missing, record in the plan's Deviations log and pick the nearest weekday with coverage for all three.

- [ ] **Step 2: Run the JForex tester narrowed to 2026-04-15 for each symbol**

Run (takes ~40 min per symbol; run sequentially):

```bash
make jforex-dukascopy-matrix SYMBOLS="AUDUSD USDCHF EURUSD" \
  EVAL_START="2026-04-15T00:00:00Z" EVAL_END="2026-04-16T00:00:00Z" \
  RECONCILE_DIR=data/analysis/backtest_reconcile/replay_2026_04_15
```

Expected: per-symbol artifacts land under `data/analysis/backtest_reconcile/replay_2026_04_15/`:
- `<SYM>_jforex_runtime_events.csv`
- `<SYM>_jforex_signal_parity_summary.csv`
- `<SYM>_jforex_execution_parity_summary.csv`
- `<SYM>_jforex_execution_lifecycle_summary.csv`
- `<SYM>_jforex_operational_ready_summary.csv`

Note: if `make jforex-dukascopy-matrix` does not accept `EVAL_START`/`EVAL_END`, fall back to the script's native CLI. Record the exact invocation used in `data/analysis/backtest_reconcile/replay_2026_04_15/INVOCATION.txt`.

- [ ] **Step 3: Archive the Python API HTTP log**

During the matrix run, the Python API server writes access logs. Copy the session's log into the replay directory:

```bash
cp data/analysis/backtest_reconcile/runtime/api_access.log data/analysis/backtest_reconcile/replay_2026_04_15/api_access.log
```

Expected: file present.

- [ ] **Step 4: Commit only the invocation record (artifacts are gitignored by pattern)**

```bash
git add data/analysis/backtest_reconcile/replay_2026_04_15/INVOCATION.txt || true
git commit -m "chore(parity): record side-A replay invocation for 2026-04-15" || echo "nothing to commit"
```

---

## Task 8: Side B — run tick-exact verifier for 2026-04-15 × 3 symbols

**Files:** none committed (produces data artifacts).

- [ ] **Step 1: Inspect the verifier CLI**

Run:

```bash
uv run python scripts/verify_oco_tick_exact_shortlist.py --help | head -40
```

Record the available flags. If the script does not support a day-narrowed run, use `--eval-start` / `--eval-end` equivalents; if none, fall back to `scripts/analyze_oco_stop_limit_tickfill.py` per the spec's flexibility clause and record the substitution.

- [ ] **Step 2: Run per-symbol for 2026-04-15**

For each symbol, run:

```bash
for sym in audusd usdchf eurusd; do
  uv run python scripts/verify_oco_tick_exact_shortlist.py \
    --symbols "${sym^^}" \
    --eval-start 2026-04-15T00:00:00Z \
    --eval-end 2026-04-16T00:00:00Z \
    --out-dir data/analysis/backtest_reconcile/replay_2026_04_15/side_b
done
```

(Adjust flag names if the `--help` output differs.)

Expected: per-symbol tick-exact artifacts under `replay_2026_04_15/side_b/`:
- `<SYM>_tick_exact_predictions.parquet`
- `<SYM>_tick_exact_touches.parquet`
- `<SYM>_tick_exact_outcomes.parquet`

- [ ] **Step 3: Record the invocation**

```bash
echo "side B invocation used at $(date -u +%FT%TZ)" > data/analysis/backtest_reconcile/replay_2026_04_15/side_b/INVOCATION.txt
git add data/analysis/backtest_reconcile/replay_2026_04_15/side_b/INVOCATION.txt
git commit -m "chore(parity): record side-B replay invocation for 2026-04-15"
```

---

## Task 9: Write `scripts/diff_parity_replay.py` and produce the diff parquet

**Files:**
- Create: `scripts/diff_parity_replay.py`
- Create: `tests/test_diff_parity_replay.py`

- [ ] **Step 1: Write the failing test**

Write `tests/test_diff_parity_replay.py`:

```python
"""Tests for scripts/diff_parity_replay.py."""
from __future__ import annotations

from pathlib import Path

import duckdb
import pandas as pd
import pytest


def _write_side_a(tmp: Path, symbol: str, rows: list[dict]) -> Path:
    out = tmp / f"{symbol}_jforex_runtime_events.csv"
    pd.DataFrame(rows).to_csv(out, index=False)
    return out


def _write_side_b(tmp: Path, symbol: str, rows: list[dict]) -> Path:
    out = tmp / f"{symbol}_tick_exact_predictions.parquet"
    pd.DataFrame(rows).to_parquet(out)
    return out


def test_diff_parity_replay_emits_one_row_per_bar_event(tmp_path: Path) -> None:
    from scripts.diff_parity_replay import run

    side_a_dir = tmp_path / "side_a"
    side_b_dir = tmp_path / "side_b"
    side_a_dir.mkdir()
    side_b_dir.mkdir()

    _write_side_a(side_a_dir, "EURUSD", [
        {"event_ts_utc": "2026-04-15T09:00:00Z", "symbol": "EURUSD",
         "category": "prediction", "event_name": "predict_cycle", "pass": "true",
         "detail": "bar_close=2026-04-15T09:00:00Z;pred_prob=0.72;selected=1"},
    ])
    _write_side_b(side_b_dir, "EURUSD", [
        {"symbol": "EURUSD", "close_ts": "2026-04-15T09:00:00Z",
         "pred_prob": 0.72, "selected_exec": 1},
    ])

    out = tmp_path / "parity_replay_diff.parquet"
    run(side_a_dir=side_a_dir, side_b_dir=side_b_dir, out_path=out,
        symbols=["EURUSD"])

    assert out.exists()
    df = pd.read_parquet(out)
    assert len(df) == 1
    row = df.iloc[0]
    assert row["symbol"] == "EURUSD"
    assert row["pred_prob_diff_abs"] == pytest.approx(0.0, abs=1e-12)
    assert row["selected_exec_match"] is True
```

- [ ] **Step 2: Run the test to verify it fails**

Run:

```bash
uv run pytest tests/test_diff_parity_replay.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'scripts.diff_parity_replay'`.

- [ ] **Step 3: Write the script**

Write `scripts/diff_parity_replay.py`:

```python
#!/usr/bin/env python3
"""One-shot diff of Side A (JForex tester) vs Side B (tick-exact verifier).

Produces data/analysis/backtest_reconcile/replay_diff/2026-04-15/parity_replay_diff.parquet
with one row per bar-event per symbol.
"""
from __future__ import annotations

import argparse
import logging
from pathlib import Path

import pandas as pd


logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("diff_parity_replay")


def _load_side_a_events(side_a_dir: Path, symbol: str) -> pd.DataFrame:
    path = side_a_dir / f"{symbol}_jforex_runtime_events.csv"
    if not path.exists():
        return pd.DataFrame()
    df = pd.read_csv(path)
    df = df[df["event_name"] == "predict_cycle"].copy()

    def _extract(detail: str, key: str) -> str:
        for part in str(detail).split(";"):
            if part.startswith(f"{key}="):
                return part[len(key) + 1 :]
        return ""

    df["bar_close_ts"] = df["detail"].apply(lambda d: _extract(d, "bar_close"))
    df["pred_prob"] = df["detail"].apply(
        lambda d: float(_extract(d, "pred_prob") or "nan")
    )
    df["selected_exec"] = df["detail"].apply(
        lambda d: int(_extract(d, "selected") or "0")
    )
    return df[["bar_close_ts", "symbol", "pred_prob", "selected_exec"]]


def _load_side_b_predictions(side_b_dir: Path, symbol: str) -> pd.DataFrame:
    path = side_b_dir / f"{symbol}_tick_exact_predictions.parquet"
    if not path.exists():
        return pd.DataFrame()
    df = pd.read_parquet(path)
    df = df.rename(columns={"close_ts": "bar_close_ts"})
    return df[["bar_close_ts", "symbol", "pred_prob", "selected_exec"]]


def run(*, side_a_dir: Path, side_b_dir: Path, out_path: Path,
        symbols: list[str]) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    frames: list[pd.DataFrame] = []
    for symbol in symbols:
        a = _load_side_a_events(side_a_dir, symbol)
        b = _load_side_b_predictions(side_b_dir, symbol)
        if a.empty and b.empty:
            logger.warning("No data for %s on either side", symbol)
            continue
        merged = pd.merge(
            a, b, on=["bar_close_ts", "symbol"],
            how="outer", suffixes=("_a", "_b"), indicator=True,
        )
        merged["pred_prob_diff_abs"] = (
            merged["pred_prob_a"].fillna(float("nan"))
            - merged["pred_prob_b"].fillna(float("nan"))
        ).abs()
        merged["selected_exec_match"] = (
            merged["selected_exec_a"].fillna(-1) == merged["selected_exec_b"].fillna(-1)
        )
        merged["present_on"] = merged["_merge"].map(
            {"left_only": "side_a", "right_only": "side_b", "both": "both"}
        )
        merged = merged.drop(columns=["_merge"])
        frames.append(merged)
    if not frames:
        logger.error("No diff rows produced")
        pd.DataFrame().to_parquet(out_path)
        return
    out = pd.concat(frames, ignore_index=True)
    out.to_parquet(out_path)
    logger.info("Wrote %s with %d rows", out_path, len(out))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--side-a-dir", type=Path, required=True)
    parser.add_argument("--side-b-dir", type=Path, required=True)
    parser.add_argument("--out-path", type=Path, required=True)
    parser.add_argument("--symbols", nargs="+", default=["AUDUSD", "USDCHF", "EURUSD"])
    args = parser.parse_args()
    run(
        side_a_dir=args.side_a_dir,
        side_b_dir=args.side_b_dir,
        out_path=args.out_path,
        symbols=args.symbols,
    )


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run the test to verify it passes**

Run:

```bash
uv run pytest tests/test_diff_parity_replay.py -v
```

Expected: PASS.

- [ ] **Step 5: Run the diff against real 2026-04-15 artifacts**

Run:

```bash
mkdir -p data/analysis/backtest_reconcile/replay_diff/2026-04-15
uv run python scripts/diff_parity_replay.py \
  --side-a-dir data/analysis/backtest_reconcile/replay_2026_04_15 \
  --side-b-dir data/analysis/backtest_reconcile/replay_2026_04_15/side_b \
  --out-path data/analysis/backtest_reconcile/replay_diff/2026-04-15/parity_replay_diff.parquet \
  --symbols AUDUSD USDCHF EURUSD
```

Expected: parquet written; log reports per-symbol row counts.

- [ ] **Step 6: Commit**

```bash
git add scripts/diff_parity_replay.py tests/test_diff_parity_replay.py
git commit -m "feat(parity): one-shot replay diff script + test"
```

---

## Task 10: Fold replay diff findings into the inventory

**Files:**
- Modify: `docs/analysis/2026-04-17-jforex-python-parity-assessment.md`

- [ ] **Step 1: Summarize the diff**

Run:

```bash
uv run python -c "
import pandas as pd
df = pd.read_parquet('data/analysis/backtest_reconcile/replay_diff/2026-04-15/parity_replay_diff.parquet')
print(df.groupby(['symbol','present_on']).size())
print('pred_prob_diff_abs > 1e-6:', (df['pred_prob_diff_abs'] > 1e-6).sum())
print('selected_exec mismatches:', (~df['selected_exec_match']).sum())
"
```

Record the exact output.

- [ ] **Step 2: Add the "Replay diff findings" section**

Replace the `## Replay diff findings` section with a subsection per symbol including:
- Total bar events on each side
- `present_on` breakdown (`side_a` only / `side_b` only / `both`)
- `pred_prob_diff_abs` distribution summary (max, mean, p95)
- `selected_exec` mismatch count

For each row-count mismatch or tolerance breach, cross-reference the corresponding surface in the Core / Lifecycle / etc. sections and update its `observed_state`, `divergence`, `evidence`, and `severity` fields.

- [ ] **Step 3: Back-fill pending surfaces**

Grep the inventory for `_pending Task 10._` and replace each with the actual observed state from the diff.

```bash
grep -n "_pending Task 10._" docs/analysis/2026-04-17-jforex-python-parity-assessment.md
```

Expected after edit: zero matches.

- [ ] **Step 4: Commit**

```bash
git add docs/analysis/2026-04-17-jforex-python-parity-assessment.md
git commit -m "docs(parity): fold 2026-04-15 replay findings into inventory"
```

---

## Task 11: `src/behemoth/parity/` package skeleton + types + registry

**Files:**
- Create: `src/behemoth/parity/__init__.py`
- Create: `src/behemoth/parity/types.py`
- Create: `src/behemoth/parity/registry.py`
- Create: `tests/parity/__init__.py`
- Create: `tests/parity/test_registry.py`

- [ ] **Step 1: Write the failing registry test**

Write `tests/parity/test_registry.py`:

```python
"""Tests for src/behemoth/parity/registry.py."""
from __future__ import annotations

import pytest

from behemoth.parity import registry
from behemoth.parity.types import CheckContext, CheckResult


def _dummy_ctx() -> CheckContext:
    return CheckContext(
        run_id="test_run",
        model_month="2026-04",
        reconcile_dir=None,
        live_state_db_path=None,
        governance_lock_dir=None,
    )


def test_register_check_stores_callable_by_surface_id():
    registry.clear_for_tests()

    @registry.register_check(surface_id="test.surface", severity="critical")
    def check_foo(ctx: CheckContext) -> CheckResult:
        return CheckResult(passed=True, severity="critical",
                           observed="ok", expected="ok", evidence="")

    assert registry.list_registered() == [("test.surface", "critical")]
    result = registry.call("test.surface", _dummy_ctx())
    assert result.passed is True


def test_register_check_rejects_duplicate_surface_id():
    registry.clear_for_tests()

    @registry.register_check(surface_id="dup", severity="high")
    def _one(ctx): ...

    with pytest.raises(ValueError, match="already registered"):
        @registry.register_check(surface_id="dup", severity="high")
        def _two(ctx): ...


def test_call_unknown_surface_id_raises():
    registry.clear_for_tests()
    with pytest.raises(KeyError, match="not registered"):
        registry.call("does.not.exist", _dummy_ctx())
```

- [ ] **Step 2: Run the test to verify it fails**

Run:

```bash
uv run pytest tests/parity/test_registry.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'behemoth.parity'`.

- [ ] **Step 3: Write the types module**

Write `src/behemoth/parity/types.py`:

```python
"""Shared types for the parity audit harness."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

Severity = Literal["critical", "high", "medium", "low"]


@dataclass(frozen=True)
class CheckContext:
    run_id: str
    model_month: str
    reconcile_dir: Path | None
    live_state_db_path: Path | None
    governance_lock_dir: Path | None


@dataclass(frozen=True)
class CheckResult:
    passed: bool
    severity: Severity
    observed: str
    expected: str
    evidence: str
```

- [ ] **Step 4: Write the registry module**

Write `src/behemoth/parity/registry.py`:

```python
"""Check registry for the parity audit harness."""
from __future__ import annotations

from typing import Callable

from behemoth.parity.types import CheckContext, CheckResult, Severity

_Check = Callable[[CheckContext], CheckResult]
_CHECKS: dict[str, tuple[_Check, Severity]] = {}


def register_check(*, surface_id: str, severity: Severity) -> Callable[[_Check], _Check]:
    def _decorator(fn: _Check) -> _Check:
        if surface_id in _CHECKS:
            raise ValueError(f"Check {surface_id!r} already registered")
        _CHECKS[surface_id] = (fn, severity)
        return fn
    return _decorator


def list_registered() -> list[tuple[str, Severity]]:
    return sorted((sid, sev) for sid, (_, sev) in _CHECKS.items())


def call(surface_id: str, ctx: CheckContext) -> CheckResult:
    if surface_id not in _CHECKS:
        raise KeyError(f"surface_id {surface_id!r} not registered")
    fn, _ = _CHECKS[surface_id]
    return fn(ctx)


def all_surface_ids() -> list[str]:
    return sorted(_CHECKS.keys())


def clear_for_tests() -> None:
    """Reset the registry. Tests only."""
    _CHECKS.clear()
```

- [ ] **Step 5: Write the package init**

Write `src/behemoth/parity/__init__.py`:

```python
"""Parity audit harness package."""
```

Write `tests/parity/__init__.py` (empty file).

- [ ] **Step 6: Run the tests to verify they pass**

Run:

```bash
uv run pytest tests/parity/test_registry.py -v
```

Expected: PASS for all three tests.

- [ ] **Step 7: Commit**

```bash
git add src/behemoth/parity/__init__.py src/behemoth/parity/types.py src/behemoth/parity/registry.py tests/parity/__init__.py tests/parity/test_registry.py
git commit -m "feat(parity): registry + types for parity audit harness"
```

---

## Task 12: Shared loader module

**Files:**
- Create: `src/behemoth/parity/loader.py`
- Create: `tests/parity/test_loader.py`

- [ ] **Step 1: Write the failing test**

Write `tests/parity/test_loader.py`:

```python
"""Tests for src/behemoth/parity/loader.py."""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from behemoth.parity import loader


def test_load_signal_parity_csvs_reads_symbol_rows(tmp_path: Path) -> None:
    (tmp_path / "AUDUSD_jforex_signal_parity_summary.csv").write_text(
        "symbol,jforex_signal_parity_pass,predict_cycles,failed_signal_events\n"
        "AUDUSD,false,0,165\n"
    )
    (tmp_path / "EURUSD_jforex_signal_parity_summary.csv").write_text(
        "symbol,jforex_signal_parity_pass,predict_cycles,failed_signal_events\n"
        "EURUSD,true,136,0\n"
    )
    df = loader.load_signal_parity_csvs(reconcile_dir=tmp_path, pattern="jforex")
    assert set(df["symbol"]) == {"AUDUSD", "EURUSD"}
    assert df.loc[df["symbol"] == "AUDUSD", "predict_cycles"].iloc[0] == 0


def test_load_runtime_events_filters_by_symbol(tmp_path: Path) -> None:
    (tmp_path / "AUDUSD_jforex_runtime_events.csv").write_text(
        "event_ts_utc,symbol,category,event_name,pass,detail\n"
        "2026-04-16T14:25:07.280258Z,AUDUSD,operational,strategy_started,true,x\n"
    )
    df = loader.load_runtime_events(reconcile_dir=tmp_path, symbol="AUDUSD",
                                     pattern="jforex")
    assert len(df) == 1
    assert df.iloc[0]["event_name"] == "strategy_started"


def test_load_governance_lock_returns_dict(tmp_path: Path) -> None:
    lock = tmp_path / "audusd_oco_live_lock.json"
    lock.write_text('{"model_month":"2026-04","lock_hash":"abc","ok":true}')
    out = loader.load_governance_lock(governance_lock_dir=tmp_path, symbol="AUDUSD")
    assert out["model_month"] == "2026-04"


def test_load_signal_parity_csvs_missing_dir_returns_empty(tmp_path: Path) -> None:
    df = loader.load_signal_parity_csvs(
        reconcile_dir=tmp_path / "nope", pattern="jforex"
    )
    assert df.empty
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
uv run pytest tests/parity/test_loader.py -v
```

Expected: FAIL with import error.

- [ ] **Step 3: Write the loader module**

Write `src/behemoth/parity/loader.py`:

```python
"""Shared input loaders for parity checks.

All loaders are pure readers; they do not write to the filesystem and they
open duckdb/sqlite handles read-only.
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd


def load_signal_parity_csvs(*, reconcile_dir: Path, pattern: str) -> pd.DataFrame:
    """Load every *_<pattern>_signal_parity_summary.csv under reconcile_dir.

    `pattern` is either "jforex" (live / tester) or "local_jforex" (surrogate).
    Returns a concatenated DataFrame with all rows, or an empty frame if the
    directory does not exist.
    """
    if not reconcile_dir.exists():
        return pd.DataFrame()
    suffix = f"_{pattern}_signal_parity_summary.csv"
    frames: list[pd.DataFrame] = []
    for path in sorted(reconcile_dir.glob(f"*{suffix}")):
        try:
            frames.append(pd.read_csv(path))
        except Exception:  # noqa: BLE001
            continue
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def load_runtime_events(
    *, reconcile_dir: Path, symbol: str, pattern: str
) -> pd.DataFrame:
    path = reconcile_dir / f"{symbol.upper()}_{pattern}_runtime_events.csv"
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path)


def load_governance_lock(*, governance_lock_dir: Path, symbol: str) -> dict:
    lock = governance_lock_dir / f"{symbol.lower()}_oco_live_lock.json"
    if not lock.exists():
        return {}
    return json.loads(lock.read_text())


def load_active_oco_state(*, runtime_dir: Path, symbol: str) -> list[dict]:
    path = runtime_dir / f"local_jforex_surrogate_{symbol.lower()}_active_oco_state.json"
    if not path.exists():
        return []
    data = json.loads(path.read_text() or "[]")
    return data if isinstance(data, list) else []
```

- [ ] **Step 4: Run the test to verify it passes**

```bash
uv run pytest tests/parity/test_loader.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/behemoth/parity/loader.py tests/parity/test_loader.py
git commit -m "feat(parity): shared input loaders for audit checks"
```

---

## Task 13: Seed check — `core.predict_cycles_per_bar`

**Files:**
- Create: `src/behemoth/parity/checks/__init__.py`
- Create: `src/behemoth/parity/checks/core_predict_cycles_per_bar.py`
- Create: `tests/parity/checks/__init__.py`
- Create: `tests/parity/conftest.py`
- Create: `tests/parity/checks/test_core_predict_cycles_per_bar.py`

- [ ] **Step 1: Write the shared fixtures**

Write `tests/parity/conftest.py`:

```python
"""Shared parity-check fixtures seeded from the 2026-04-17 session.

Two factories: a clean CheckContext and a divergent one.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from behemoth.parity.types import CheckContext


@pytest.fixture
def parity_ctx_factory(tmp_path: Path):
    """Returns a factory that builds a CheckContext rooted at tmp_path."""
    def _build(run_id: str = "jforex_live", model_month: str = "2026-04") -> CheckContext:
        (tmp_path / "reconcile").mkdir(parents=True, exist_ok=True)
        (tmp_path / "reconcile" / "runtime").mkdir(exist_ok=True)
        (tmp_path / "governance").mkdir(exist_ok=True)
        return CheckContext(
            run_id=run_id,
            model_month=model_month,
            reconcile_dir=tmp_path / "reconcile",
            live_state_db_path=tmp_path / "reconcile" / "runtime" / "live_state.db",
            governance_lock_dir=tmp_path / "governance",
        )
    return _build


def write_signal_parity_csv(reconcile_dir: Path, symbol: str, *,
                             passed: bool, predict_cycles: int,
                             failed_signal_events: int) -> None:
    reconcile_dir.mkdir(parents=True, exist_ok=True)
    path = reconcile_dir / f"{symbol}_jforex_signal_parity_summary.csv"
    path.write_text(
        "symbol,jforex_signal_parity_pass,predict_cycles,failed_signal_events\n"
        f"{symbol},{str(passed).lower()},{predict_cycles},{failed_signal_events}\n"
    )
```

Write `tests/parity/checks/__init__.py` (empty) and `src/behemoth/parity/checks/__init__.py` (populated later):

```python
"""Parity check implementations — imported for side effect (register_check)."""
from behemoth.parity.checks import core_predict_cycles_per_bar  # noqa: F401
```

- [ ] **Step 2: Write the failing test**

Write `tests/parity/checks/test_core_predict_cycles_per_bar.py`:

```python
"""Tests for the predict_cycles_per_bar check, seeded from 2026-04-17 evidence."""
from __future__ import annotations

from pathlib import Path

import pytest

from behemoth.parity import registry
from behemoth.parity.checks import core_predict_cycles_per_bar  # noqa: F401
from tests.parity.conftest import write_signal_parity_csv


def test_audusd_2026_04_17_zero_predict_fails(parity_ctx_factory):
    ctx = parity_ctx_factory()
    write_signal_parity_csv(ctx.reconcile_dir, "AUDUSD",
                             passed=False, predict_cycles=0,
                             failed_signal_events=165)
    write_signal_parity_csv(ctx.reconcile_dir, "EURUSD",
                             passed=True, predict_cycles=136,
                             failed_signal_events=0)

    result = registry.call("core.predict_cycles_per_bar", ctx)
    assert result.passed is False
    assert "AUDUSD" in result.observed
    assert result.severity == "critical"


def test_clean_session_passes(parity_ctx_factory):
    ctx = parity_ctx_factory()
    write_signal_parity_csv(ctx.reconcile_dir, "EURUSD",
                             passed=True, predict_cycles=136,
                             failed_signal_events=0)

    result = registry.call("core.predict_cycles_per_bar", ctx)
    assert result.passed is True
```

- [ ] **Step 3: Run the test to verify it fails**

```bash
uv run pytest tests/parity/checks/test_core_predict_cycles_per_bar.py -v
```

Expected: FAIL (module does not exist).

- [ ] **Step 4: Write the check**

Write `src/behemoth/parity/checks/core_predict_cycles_per_bar.py`:

```python
"""Seed check: every symbol with bar events must have at least one predict cycle."""
from __future__ import annotations

from behemoth.parity import loader
from behemoth.parity.registry import register_check
from behemoth.parity.types import CheckContext, CheckResult


@register_check(surface_id="core.predict_cycles_per_bar", severity="critical")
def check(ctx: CheckContext) -> CheckResult:
    if ctx.reconcile_dir is None or not ctx.reconcile_dir.exists():
        return CheckResult(
            passed=False, severity="critical",
            observed="reconcile_dir missing",
            expected="directory with *_jforex_signal_parity_summary.csv files",
            evidence=str(ctx.reconcile_dir),
        )
    df = loader.load_signal_parity_csvs(reconcile_dir=ctx.reconcile_dir,
                                         pattern="jforex")
    if df.empty:
        return CheckResult(
            passed=False, severity="critical",
            observed="no signal parity CSVs found",
            expected="at least one CSV",
            evidence=f"glob under {ctx.reconcile_dir}",
        )
    bad = df[(df["predict_cycles"] == 0) & (df["failed_signal_events"] > 0)]
    if not bad.empty:
        offenders = ", ".join(
            f"{row.symbol}({int(row.failed_signal_events)} events)"
            for row in bad.itertuples()
        )
        return CheckResult(
            passed=False, severity="critical",
            observed=f"zero predict cycles with bar events: {offenders}",
            expected="predict_cycles >= 1 wherever failed_signal_events > 0",
            evidence=f"rows in {ctx.reconcile_dir}",
        )
    return CheckResult(
        passed=True, severity="critical",
        observed=f"{len(df)} symbols checked; all have predict cycles where bars fired",
        expected="predict_cycles >= 1 wherever failed_signal_events > 0",
        evidence="",
    )
```

- [ ] **Step 5: Run the test to verify it passes**

```bash
uv run pytest tests/parity/checks/test_core_predict_cycles_per_bar.py -v
```

Expected: PASS for both tests.

- [ ] **Step 6: Commit**

```bash
git add src/behemoth/parity/checks/__init__.py src/behemoth/parity/checks/core_predict_cycles_per_bar.py tests/parity/conftest.py tests/parity/checks/__init__.py tests/parity/checks/test_core_predict_cycles_per_bar.py
git commit -m "feat(parity): seed check core.predict_cycles_per_bar"
```

---

## Task 14: Seed check — `risk_gov.governance_lock_pin`

**Files:**
- Create: `src/behemoth/parity/checks/risk_gov_governance_lock_pin.py`
- Create: `tests/parity/checks/test_risk_gov_governance_lock_pin.py`
- Modify: `src/behemoth/parity/checks/__init__.py` — append import.

- [ ] **Step 1: Write the failing test**

Write `tests/parity/checks/test_risk_gov_governance_lock_pin.py`:

```python
"""Tests for risk_gov.governance_lock_pin."""
from __future__ import annotations

from behemoth.parity import registry
from behemoth.parity.checks import risk_gov_governance_lock_pin  # noqa: F401


def _write_lock(path, model_month: str, lock_hash: str) -> None:
    path.write_text(
        '{"model_month":"' + model_month + '","lock_hash":"' + lock_hash + '"}'
    )


def test_matching_month_passes(parity_ctx_factory):
    ctx = parity_ctx_factory(model_month="2026-04")
    _write_lock(ctx.governance_lock_dir / "audusd_oco_live_lock.json",
                "2026-04", "abc")
    _write_lock(ctx.governance_lock_dir / "eurusd_oco_live_lock.json",
                "2026-04", "def")

    result = registry.call("risk_gov.governance_lock_pin", ctx)
    assert result.passed is True


def test_mismatched_month_fails(parity_ctx_factory):
    ctx = parity_ctx_factory(model_month="2026-04")
    _write_lock(ctx.governance_lock_dir / "audusd_oco_live_lock.json",
                "2026-03", "abc")

    result = registry.call("risk_gov.governance_lock_pin", ctx)
    assert result.passed is False
    assert "2026-03" in result.observed
```

- [ ] **Step 2: Run to verify fail**

```bash
uv run pytest tests/parity/checks/test_risk_gov_governance_lock_pin.py -v
```

Expected: FAIL (module missing).

- [ ] **Step 3: Write the check**

Write `src/behemoth/parity/checks/risk_gov_governance_lock_pin.py`:

```python
"""Seed check: every per-symbol live lock pins the expected model_month."""
from __future__ import annotations

from behemoth.parity import loader
from behemoth.parity.registry import register_check
from behemoth.parity.types import CheckContext, CheckResult

_SYMBOLS = ["AUDUSD", "EURUSD", "GBPUSD", "USDCAD", "USDCHF", "USDJPY"]


@register_check(surface_id="risk_gov.governance_lock_pin", severity="critical")
def check(ctx: CheckContext) -> CheckResult:
    if ctx.governance_lock_dir is None:
        return CheckResult(
            passed=False, severity="critical",
            observed="governance_lock_dir missing",
            expected="directory with *_oco_live_lock.json files",
            evidence="",
        )
    mismatches: list[str] = []
    missing: list[str] = []
    for symbol in _SYMBOLS:
        lock = loader.load_governance_lock(
            governance_lock_dir=ctx.governance_lock_dir, symbol=symbol
        )
        if not lock:
            missing.append(symbol)
            continue
        if lock.get("model_month") != ctx.model_month:
            mismatches.append(
                f"{symbol}: lock={lock.get('model_month')!r} ctx={ctx.model_month!r}"
            )
    if missing or mismatches:
        parts = []
        if missing:
            parts.append(f"missing locks: {', '.join(missing)}")
        if mismatches:
            parts.append(f"month mismatches: {'; '.join(mismatches)}")
        return CheckResult(
            passed=False, severity="critical",
            observed="; ".join(parts),
            expected=f"every lock pinned to model_month={ctx.model_month}",
            evidence=str(ctx.governance_lock_dir),
        )
    return CheckResult(
        passed=True, severity="critical",
        observed=f"all 6 symbols pinned to {ctx.model_month}",
        expected=f"every lock pinned to model_month={ctx.model_month}",
        evidence="",
    )
```

- [ ] **Step 4: Register check in package init**

Edit `src/behemoth/parity/checks/__init__.py`:

```python
"""Parity check implementations — imported for side effect (register_check)."""
from behemoth.parity.checks import core_predict_cycles_per_bar  # noqa: F401
from behemoth.parity.checks import risk_gov_governance_lock_pin  # noqa: F401
```

- [ ] **Step 5: Run tests to verify pass**

```bash
uv run pytest tests/parity/checks/ -v
```

Expected: PASS for all tests.

- [ ] **Step 6: Commit**

```bash
git add src/behemoth/parity/checks/risk_gov_governance_lock_pin.py src/behemoth/parity/checks/__init__.py tests/parity/checks/test_risk_gov_governance_lock_pin.py
git commit -m "feat(parity): seed check risk_gov.governance_lock_pin"
```

---

## Task 15: Seed check — `core.tick_seq_monotonic`

**Files:**
- Create: `src/behemoth/parity/checks/core_tick_seq_monotonic.py`
- Create: `tests/parity/checks/test_core_tick_seq_monotonic.py`
- Modify: `src/behemoth/parity/checks/__init__.py`

- [ ] **Step 1: Write the failing test**

Write `tests/parity/checks/test_core_tick_seq_monotonic.py`:

```python
"""Tests for core.tick_seq_monotonic."""
from __future__ import annotations

from behemoth.parity import registry
from behemoth.parity.checks import core_tick_seq_monotonic  # noqa: F401


def _write_events_csv(path, rows):
    import pandas as pd
    pd.DataFrame(rows).to_csv(path, index=False)


def test_monotonic_seq_passes(parity_ctx_factory):
    ctx = parity_ctx_factory()
    _write_events_csv(
        ctx.reconcile_dir / "EURUSD_jforex_runtime_events.csv",
        [
            {"event_ts_utc": "2026-04-15T09:00:00Z", "symbol": "EURUSD",
             "category": "feed", "event_name": "tick_accepted",
             "pass": "true", "detail": "client_tick_seq=1"},
            {"event_ts_utc": "2026-04-15T09:00:01Z", "symbol": "EURUSD",
             "category": "feed", "event_name": "tick_accepted",
             "pass": "true", "detail": "client_tick_seq=2"},
        ],
    )
    result = registry.call("core.tick_seq_monotonic", ctx)
    assert result.passed is True


def test_regressing_seq_fails(parity_ctx_factory):
    ctx = parity_ctx_factory()
    _write_events_csv(
        ctx.reconcile_dir / "EURUSD_jforex_runtime_events.csv",
        [
            {"event_ts_utc": "2026-04-15T09:00:00Z", "symbol": "EURUSD",
             "category": "feed", "event_name": "tick_accepted",
             "pass": "true", "detail": "client_tick_seq=2"},
            {"event_ts_utc": "2026-04-15T09:00:01Z", "symbol": "EURUSD",
             "category": "feed", "event_name": "tick_accepted",
             "pass": "true", "detail": "client_tick_seq=1"},
        ],
    )
    result = registry.call("core.tick_seq_monotonic", ctx)
    assert result.passed is False
    assert "regression" in result.observed.lower()
```

- [ ] **Step 2: Verify fail**

```bash
uv run pytest tests/parity/checks/test_core_tick_seq_monotonic.py -v
```

Expected: FAIL.

- [ ] **Step 3: Write the check**

Write `src/behemoth/parity/checks/core_tick_seq_monotonic.py`:

```python
"""Seed check: client_tick_seq is strictly monotonic per symbol within a session."""
from __future__ import annotations

import re

from behemoth.parity import loader
from behemoth.parity.registry import register_check
from behemoth.parity.types import CheckContext, CheckResult

_SYMBOLS = ["AUDUSD", "EURUSD", "GBPUSD", "USDCAD", "USDCHF", "USDJPY"]
_SEQ_RE = re.compile(r"client_tick_seq=(\d+)")


@register_check(surface_id="core.tick_seq_monotonic", severity="critical")
def check(ctx: CheckContext) -> CheckResult:
    if ctx.reconcile_dir is None or not ctx.reconcile_dir.exists():
        return CheckResult(
            passed=False, severity="critical",
            observed="reconcile_dir missing",
            expected="directory present",
            evidence=str(ctx.reconcile_dir),
        )
    regressions: list[str] = []
    checked = 0
    for symbol in _SYMBOLS:
        df = loader.load_runtime_events(
            reconcile_dir=ctx.reconcile_dir, symbol=symbol, pattern="jforex"
        )
        if df.empty:
            continue
        checked += 1
        last = -1
        for _, row in df.iterrows():
            match = _SEQ_RE.search(str(row.get("detail") or ""))
            if not match:
                continue
            seq = int(match.group(1))
            if seq <= last:
                regressions.append(f"{symbol} seq={seq} after {last}")
                break
            last = seq
    if regressions:
        return CheckResult(
            passed=False, severity="critical",
            observed="client_tick_seq regression: " + "; ".join(regressions),
            expected="strictly monotonic client_tick_seq per symbol",
            evidence="",
        )
    return CheckResult(
        passed=True, severity="critical",
        observed=f"{checked} symbols scanned, no regressions",
        expected="strictly monotonic client_tick_seq per symbol",
        evidence="",
    )
```

- [ ] **Step 4: Register + verify pass**

Append to `src/behemoth/parity/checks/__init__.py`:

```python
from behemoth.parity.checks import core_tick_seq_monotonic  # noqa: F401
```

Run:

```bash
uv run pytest tests/parity/checks/ -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/behemoth/parity/checks/core_tick_seq_monotonic.py src/behemoth/parity/checks/__init__.py tests/parity/checks/test_core_tick_seq_monotonic.py
git commit -m "feat(parity): seed check core.tick_seq_monotonic"
```

---

## Task 16: Seed check — `lifecycle.active_oco_reconciled`

**Files:**
- Create: `src/behemoth/parity/checks/lifecycle_active_oco_reconciled.py`
- Create: `tests/parity/checks/test_lifecycle_active_oco_reconciled.py`
- Modify: `src/behemoth/parity/checks/__init__.py`

- [ ] **Step 1: Write the failing test**

Write `tests/parity/checks/test_lifecycle_active_oco_reconciled.py`:

```python
"""Tests for lifecycle.active_oco_reconciled."""
from __future__ import annotations

import json

import duckdb

from behemoth.parity import registry
from behemoth.parity.checks import lifecycle_active_oco_reconciled  # noqa: F401


def _prime_db(db_path) -> None:
    con = duckdb.connect(str(db_path))
    con.execute(
        "CREATE TABLE barrier_scans (scan_id VARCHAR, symbol VARCHAR, status VARCHAR)"
    )
    con.execute(
        "INSERT INTO barrier_scans VALUES ('scan_a', 'EURUSD', 'HOLDING')"
    )
    con.close()


def test_matching_json_and_db_passes(parity_ctx_factory):
    ctx = parity_ctx_factory()
    _prime_db(ctx.live_state_db_path)
    (ctx.reconcile_dir / "runtime").mkdir(exist_ok=True)
    (ctx.reconcile_dir / "runtime" / "active_oco_state.json").write_text(
        json.dumps([{"scan_id": "scan_a", "symbol": "EURUSD", "status": "HOLDING"}])
    )
    result = registry.call("lifecycle.active_oco_reconciled", ctx)
    assert result.passed is True


def test_orphan_in_json_fails(parity_ctx_factory):
    ctx = parity_ctx_factory()
    _prime_db(ctx.live_state_db_path)
    (ctx.reconcile_dir / "runtime").mkdir(exist_ok=True)
    (ctx.reconcile_dir / "runtime" / "active_oco_state.json").write_text(
        json.dumps([
            {"scan_id": "scan_a", "symbol": "EURUSD", "status": "HOLDING"},
            {"scan_id": "scan_missing", "symbol": "EURUSD", "status": "HOLDING"},
        ])
    )
    result = registry.call("lifecycle.active_oco_reconciled", ctx)
    assert result.passed is False
    assert "scan_missing" in result.observed
```

- [ ] **Step 2: Verify fail**

```bash
uv run pytest tests/parity/checks/test_lifecycle_active_oco_reconciled.py -v
```

Expected: FAIL.

- [ ] **Step 3: Write the check**

Write `src/behemoth/parity/checks/lifecycle_active_oco_reconciled.py`:

```python
"""Seed check: every active_oco_state.json entry has a matching barrier_scans row."""
from __future__ import annotations

import json

import duckdb

from behemoth.parity.registry import register_check
from behemoth.parity.types import CheckContext, CheckResult


@register_check(surface_id="lifecycle.active_oco_reconciled", severity="critical")
def check(ctx: CheckContext) -> CheckResult:
    if ctx.live_state_db_path is None or not ctx.live_state_db_path.exists():
        return CheckResult(
            passed=False, severity="critical",
            observed="live_state.db missing",
            expected="duckdb file present",
            evidence=str(ctx.live_state_db_path),
        )
    if ctx.reconcile_dir is None:
        return CheckResult(
            passed=False, severity="critical",
            observed="reconcile_dir missing",
            expected="runtime/active_oco_state.json present",
            evidence="",
        )
    json_path = ctx.reconcile_dir / "runtime" / "active_oco_state.json"
    if not json_path.exists():
        return CheckResult(
            passed=True, severity="critical",
            observed="no active_oco_state.json — empty live state",
            expected="matching entries between JSON and DB",
            evidence="",
        )
    entries = json.loads(json_path.read_text() or "[]")
    con = duckdb.connect(str(ctx.live_state_db_path), read_only=True)
    try:
        db_ids = {
            row[0] for row in con.execute(
                "SELECT scan_id FROM barrier_scans WHERE status IN ('SCANNING','HOLDING')"
            ).fetchall()
        }
    finally:
        con.close()
    json_ids = {e["scan_id"] for e in entries}
    orphans_in_json = json_ids - db_ids
    orphans_in_db = db_ids - json_ids
    if orphans_in_json or orphans_in_db:
        parts = []
        if orphans_in_json:
            parts.append(f"JSON-only: {sorted(orphans_in_json)}")
        if orphans_in_db:
            parts.append(f"DB-only: {sorted(orphans_in_db)}")
        return CheckResult(
            passed=False, severity="critical",
            observed="; ".join(parts),
            expected="every active scan appears in both JSON and DB",
            evidence=str(json_path),
        )
    return CheckResult(
        passed=True, severity="critical",
        observed=f"{len(json_ids)} active scans reconciled",
        expected="every active scan appears in both JSON and DB",
        evidence="",
    )
```

- [ ] **Step 4: Register + verify pass**

Append to `src/behemoth/parity/checks/__init__.py`:

```python
from behemoth.parity.checks import lifecycle_active_oco_reconciled  # noqa: F401
```

Run:

```bash
uv run pytest tests/parity/checks/ -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/behemoth/parity/checks/lifecycle_active_oco_reconciled.py src/behemoth/parity/checks/__init__.py tests/parity/checks/test_lifecycle_active_oco_reconciled.py
git commit -m "feat(parity): seed check lifecycle.active_oco_reconciled"
```

---

## Task 17: Seed check — `failure.tick_batch_599_fallback_consistency`

**Files:**
- Create: `src/behemoth/parity/checks/failure_tick_batch_599_fallback.py`
- Create: `tests/parity/checks/test_failure_tick_batch_599_fallback.py`
- Modify: `src/behemoth/parity/checks/__init__.py`

- [ ] **Step 1: Write the failing test**

Write `tests/parity/checks/test_failure_tick_batch_599_fallback.py`:

```python
"""Tests for failure.tick_batch_599_fallback_consistency."""
from __future__ import annotations

import pandas as pd

from behemoth.parity import registry
from behemoth.parity.checks import failure_tick_batch_599_fallback  # noqa: F401


def _write(path, rows):
    pd.DataFrame(rows).to_csv(path, index=False)


def test_no_fallback_rows_passes(parity_ctx_factory):
    ctx = parity_ctx_factory()
    _write(
        ctx.reconcile_dir / "EURUSD_jforex_runtime_events.csv",
        [
            {"event_ts_utc": "2026-04-15T09:00:00Z", "symbol": "EURUSD",
             "category": "operational", "event_name": "feed_status",
             "pass": "true", "detail": "accepted=50;attempt=1"},
        ],
    )
    result = registry.call("failure.tick_batch_599_fallback_consistency", ctx)
    assert result.passed is True


def test_fallback_without_success_fails(parity_ctx_factory):
    ctx = parity_ctx_factory()
    _write(
        ctx.reconcile_dir / "EURUSD_jforex_runtime_events.csv",
        [
            {"event_ts_utc": "2026-04-15T09:00:00Z", "symbol": "EURUSD",
             "category": "operational", "event_name": "feed_status",
             "pass": "false", "detail": "mode=single_tick_fallback;accepted=0"},
        ],
    )
    result = registry.call("failure.tick_batch_599_fallback_consistency", ctx)
    assert result.passed is False
```

- [ ] **Step 2: Verify fail**

```bash
uv run pytest tests/parity/checks/test_failure_tick_batch_599_fallback.py -v
```

Expected: FAIL.

- [ ] **Step 3: Write the check**

Write `src/behemoth/parity/checks/failure_tick_batch_599_fallback.py`:

```python
"""Seed check: every single-tick fallback produced a matching accepted count."""
from __future__ import annotations

import re

from behemoth.parity import loader
from behemoth.parity.registry import register_check
from behemoth.parity.types import CheckContext, CheckResult

_SYMBOLS = ["AUDUSD", "EURUSD", "GBPUSD", "USDCAD", "USDCHF", "USDJPY"]
_ACCEPTED_RE = re.compile(r"accepted=(\d+)")


@register_check(
    surface_id="failure.tick_batch_599_fallback_consistency",
    severity="high",
)
def check(ctx: CheckContext) -> CheckResult:
    if ctx.reconcile_dir is None or not ctx.reconcile_dir.exists():
        return CheckResult(
            passed=False, severity="high",
            observed="reconcile_dir missing",
            expected="directory present",
            evidence="",
        )
    bad: list[str] = []
    checked = 0
    for symbol in _SYMBOLS:
        df = loader.load_runtime_events(
            reconcile_dir=ctx.reconcile_dir, symbol=symbol, pattern="jforex"
        )
        if df.empty:
            continue
        checked += 1
        fallback = df[df["detail"].astype(str).str.contains(
            "single_tick_fallback", na=False
        )]
        for _, row in fallback.iterrows():
            match = _ACCEPTED_RE.search(str(row.get("detail") or ""))
            accepted = int(match.group(1)) if match else 0
            passed_flag = str(row.get("pass", "")).strip().lower()
            if accepted == 0 or passed_flag == "false":
                bad.append(
                    f"{symbol}@{row['event_ts_utc']} fallback accepted={accepted} "
                    f"pass={passed_flag}"
                )
    if bad:
        return CheckResult(
            passed=False, severity="high",
            observed="; ".join(bad[:5]) + (f" (+{len(bad)-5} more)" if len(bad) > 5 else ""),
            expected="every single_tick_fallback event has accepted>0 and pass=true",
            evidence="",
        )
    return CheckResult(
        passed=True, severity="high",
        observed=f"{checked} symbols scanned, fallback rows consistent",
        expected="every single_tick_fallback event has accepted>0 and pass=true",
        evidence="",
    )
```

- [ ] **Step 4: Register + verify pass**

Append to `src/behemoth/parity/checks/__init__.py`:

```python
from behemoth.parity.checks import failure_tick_batch_599_fallback  # noqa: F401
```

Run:

```bash
uv run pytest tests/parity/checks/ -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/behemoth/parity/checks/failure_tick_batch_599_fallback.py src/behemoth/parity/checks/__init__.py tests/parity/checks/test_failure_tick_batch_599_fallback.py
git commit -m "feat(parity): seed check failure.tick_batch_599_fallback_consistency"
```

---

## Task 18: Seed check — `failure.predict_422_warmup_only`

**Files:**
- Create: `src/behemoth/parity/checks/failure_predict_422_warmup_only.py`
- Create: `tests/parity/checks/test_failure_predict_422_warmup_only.py`
- Modify: `src/behemoth/parity/checks/__init__.py`

- [ ] **Step 1: Write the failing test**

Write `tests/parity/checks/test_failure_predict_422_warmup_only.py`:

```python
"""Tests for failure.predict_422_warmup_only."""
from __future__ import annotations

import pandas as pd

from behemoth.parity import registry
from behemoth.parity.checks import failure_predict_422_warmup_only  # noqa: F401


def _write(path, rows):
    pd.DataFrame(rows).to_csv(path, index=False)


def test_only_warmup_failures_passes(parity_ctx_factory):
    ctx = parity_ctx_factory()
    _write(
        ctx.reconcile_dir / "EURUSD_jforex_runtime_events.csv",
        [
            {"event_ts_utc": "2026-04-15T09:00:00Z", "symbol": "EURUSD",
             "category": "prediction", "event_name": "predict_warmup_skipped",
             "pass": "true", "detail": "Insufficient warmup bars"},
        ],
    )
    result = registry.call("failure.predict_422_warmup_only", ctx)
    assert result.passed is True


def test_non_warmup_422_fails(parity_ctx_factory):
    ctx = parity_ctx_factory()
    _write(
        ctx.reconcile_dir / "EURUSD_jforex_runtime_events.csv",
        [
            {"event_ts_utc": "2026-04-15T09:00:00Z", "symbol": "EURUSD",
             "category": "prediction", "event_name": "predict_failure",
             "pass": "false", "detail": "HTTP 422: model artifact mismatch"},
        ],
    )
    result = registry.call("failure.predict_422_warmup_only", ctx)
    assert result.passed is False
    assert "model artifact mismatch" in result.observed
```

- [ ] **Step 2: Verify fail**

```bash
uv run pytest tests/parity/checks/test_failure_predict_422_warmup_only.py -v
```

Expected: FAIL.

- [ ] **Step 3: Write the check**

Write `src/behemoth/parity/checks/failure_predict_422_warmup_only.py`:

```python
"""Seed check: every predict failure is either warmup-skip or classified critically.

If a predict_failure row exists with detail that is NOT 'Insufficient warmup bars',
that is a silent non-warmup failure and the check fails.
"""
from __future__ import annotations

from behemoth.parity import loader
from behemoth.parity.registry import register_check
from behemoth.parity.types import CheckContext, CheckResult

_SYMBOLS = ["AUDUSD", "EURUSD", "GBPUSD", "USDCAD", "USDCHF", "USDJPY"]


@register_check(surface_id="failure.predict_422_warmup_only", severity="critical")
def check(ctx: CheckContext) -> CheckResult:
    if ctx.reconcile_dir is None or not ctx.reconcile_dir.exists():
        return CheckResult(
            passed=False, severity="critical",
            observed="reconcile_dir missing",
            expected="directory present",
            evidence="",
        )
    offenders: list[str] = []
    checked = 0
    for symbol in _SYMBOLS:
        df = loader.load_runtime_events(
            reconcile_dir=ctx.reconcile_dir, symbol=symbol, pattern="jforex"
        )
        if df.empty:
            continue
        checked += 1
        fails = df[df["event_name"] == "predict_failure"]
        for _, row in fails.iterrows():
            detail = str(row.get("detail") or "")
            if "Insufficient warmup bars" not in detail:
                offenders.append(f"{symbol}: {detail[:80]}")
    if offenders:
        return CheckResult(
            passed=False, severity="critical",
            observed="; ".join(offenders[:5]),
            expected="every predict_failure detail contains 'Insufficient warmup bars'",
            evidence="",
        )
    return CheckResult(
        passed=True, severity="critical",
        observed=f"{checked} symbols scanned, no non-warmup predict failures",
        expected="every predict_failure detail contains 'Insufficient warmup bars'",
        evidence="",
    )
```

- [ ] **Step 4: Register + verify pass**

Append to `src/behemoth/parity/checks/__init__.py`:

```python
from behemoth.parity.checks import failure_predict_422_warmup_only  # noqa: F401
```

Run:

```bash
uv run pytest tests/parity/checks/ -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/behemoth/parity/checks/failure_predict_422_warmup_only.py src/behemoth/parity/checks/__init__.py tests/parity/checks/test_failure_predict_422_warmup_only.py
git commit -m "feat(parity): seed check failure.predict_422_warmup_only"
```

---

## Task 19: Seed check — `core.entries_allowed_vs_readiness`

**Files:**
- Create: `src/behemoth/parity/checks/core_entries_allowed_vs_readiness.py`
- Create: `tests/parity/checks/test_core_entries_allowed_vs_readiness.py`
- Modify: `src/behemoth/parity/checks/__init__.py`

- [ ] **Step 1: Write the failing test**

Write `tests/parity/checks/test_core_entries_allowed_vs_readiness.py`:

```python
"""Tests for core.entries_allowed_vs_readiness."""
from __future__ import annotations

import json

import pandas as pd

from behemoth.parity import registry
from behemoth.parity.checks import core_entries_allowed_vs_readiness  # noqa: F401


def _write_events(path, rows):
    pd.DataFrame(rows).to_csv(path, index=False)


def _write_readiness(path, entries):
    path.write_text(json.dumps({"symbols": entries}))


def test_blocked_entry_with_not_ready_passes(parity_ctx_factory):
    ctx = parity_ctx_factory()
    (ctx.reconcile_dir / "runtime").mkdir(exist_ok=True)
    _write_events(
        ctx.reconcile_dir / "EURUSD_jforex_runtime_events.csv",
        [
            {"event_ts_utc": "2026-04-15T09:00:00Z", "symbol": "EURUSD",
             "category": "operational", "event_name": "entry_blocked_not_ready",
             "pass": "false", "detail": "entries not allowed"},
        ],
    )
    _write_readiness(
        ctx.reconcile_dir / "runtime" / "live_symbol_readiness.json",
        [{"symbol": "EURUSD", "state": "WARMING_UP"}],
    )
    result = registry.call("core.entries_allowed_vs_readiness", ctx)
    assert result.passed is True


def test_blocked_entry_while_ready_fails(parity_ctx_factory):
    ctx = parity_ctx_factory()
    (ctx.reconcile_dir / "runtime").mkdir(exist_ok=True)
    _write_events(
        ctx.reconcile_dir / "EURUSD_jforex_runtime_events.csv",
        [
            {"event_ts_utc": "2026-04-15T09:00:00Z", "symbol": "EURUSD",
             "category": "operational", "event_name": "entry_blocked_not_ready",
             "pass": "false", "detail": "entries not allowed"},
        ],
    )
    _write_readiness(
        ctx.reconcile_dir / "runtime" / "live_symbol_readiness.json",
        [{"symbol": "EURUSD", "state": "READY"}],
    )
    result = registry.call("core.entries_allowed_vs_readiness", ctx)
    assert result.passed is False
```

- [ ] **Step 2: Verify fail**

```bash
uv run pytest tests/parity/checks/test_core_entries_allowed_vs_readiness.py -v
```

Expected: FAIL.

- [ ] **Step 3: Write the check**

Write `src/behemoth/parity/checks/core_entries_allowed_vs_readiness.py`:

```python
"""Seed check: entry_blocked_not_ready events must correlate with non-READY readiness."""
from __future__ import annotations

import json

from behemoth.parity import loader
from behemoth.parity.registry import register_check
from behemoth.parity.types import CheckContext, CheckResult

_SYMBOLS = ["AUDUSD", "EURUSD", "GBPUSD", "USDCAD", "USDCHF", "USDJPY"]


@register_check(surface_id="core.entries_allowed_vs_readiness", severity="high")
def check(ctx: CheckContext) -> CheckResult:
    if ctx.reconcile_dir is None:
        return CheckResult(
            passed=False, severity="high",
            observed="reconcile_dir missing",
            expected="present",
            evidence="",
        )
    readiness_path = ctx.reconcile_dir / "runtime" / "live_symbol_readiness.json"
    if not readiness_path.exists():
        return CheckResult(
            passed=True, severity="high",
            observed="no readiness snapshot — nothing to cross-check",
            expected="readiness states match blocked-entry events",
            evidence="",
        )
    readiness_blob = json.loads(readiness_path.read_text() or "{}")
    ready_by_symbol: dict[str, str] = {}
    for entry in readiness_blob.get("symbols", []):
        sym = str(entry.get("symbol") or "").upper()
        state = str(entry.get("state") or "").upper()
        if sym:
            ready_by_symbol[sym] = state
    offenders: list[str] = []
    for symbol in _SYMBOLS:
        df = loader.load_runtime_events(
            reconcile_dir=ctx.reconcile_dir, symbol=symbol, pattern="jforex"
        )
        if df.empty:
            continue
        blocked = df[df["event_name"] == "entry_blocked_not_ready"]
        if blocked.empty:
            continue
        state = ready_by_symbol.get(symbol, "UNKNOWN")
        if state == "READY":
            offenders.append(f"{symbol}: {len(blocked)} blocked events while state=READY")
    if offenders:
        return CheckResult(
            passed=False, severity="high",
            observed="; ".join(offenders),
            expected="entry_blocked_not_ready only while state != READY",
            evidence=str(readiness_path),
        )
    return CheckResult(
        passed=True, severity="high",
        observed="all entry_blocked_not_ready events correlate with non-READY states",
        expected="entry_blocked_not_ready only while state != READY",
        evidence="",
    )
```

- [ ] **Step 4: Register + verify pass**

Append to `src/behemoth/parity/checks/__init__.py`:

```python
from behemoth.parity.checks import core_entries_allowed_vs_readiness  # noqa: F401
```

Run:

```bash
uv run pytest tests/parity/checks/ -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/behemoth/parity/checks/core_entries_allowed_vs_readiness.py src/behemoth/parity/checks/__init__.py tests/parity/checks/test_core_entries_allowed_vs_readiness.py
git commit -m "feat(parity): seed check core.entries_allowed_vs_readiness"
```

---

## Task 20: Seed check — `time_data.bar_close_ts_sorted_per_symbol`

**Files:**
- Create: `src/behemoth/parity/checks/time_data_bar_close_ts_sorted.py`
- Create: `tests/parity/checks/test_time_data_bar_close_ts_sorted.py`
- Modify: `src/behemoth/parity/checks/__init__.py`

- [ ] **Step 1: Write the failing test**

Write `tests/parity/checks/test_time_data_bar_close_ts_sorted.py`:

```python
"""Tests for time_data.bar_close_ts_sorted_per_symbol."""
from __future__ import annotations

import pandas as pd

from behemoth.parity import registry
from behemoth.parity.checks import time_data_bar_close_ts_sorted  # noqa: F401


def _write(path, rows):
    pd.DataFrame(rows).to_csv(path, index=False)


def test_monotonic_bar_close_passes(parity_ctx_factory):
    ctx = parity_ctx_factory()
    _write(
        ctx.reconcile_dir / "EURUSD_jforex_runtime_events.csv",
        [
            {"event_ts_utc": "2026-04-15T09:00:00Z", "symbol": "EURUSD",
             "category": "prediction", "event_name": "predict_cycle",
             "pass": "true", "detail": "bar_close=2026-04-15T09:00:00Z"},
            {"event_ts_utc": "2026-04-15T09:01:00Z", "symbol": "EURUSD",
             "category": "prediction", "event_name": "predict_cycle",
             "pass": "true", "detail": "bar_close=2026-04-15T09:01:00Z"},
        ],
    )
    result = registry.call("time_data.bar_close_ts_sorted_per_symbol", ctx)
    assert result.passed is True


def test_out_of_order_bar_close_fails(parity_ctx_factory):
    ctx = parity_ctx_factory()
    _write(
        ctx.reconcile_dir / "EURUSD_jforex_runtime_events.csv",
        [
            {"event_ts_utc": "2026-04-15T09:01:00Z", "symbol": "EURUSD",
             "category": "prediction", "event_name": "predict_cycle",
             "pass": "true", "detail": "bar_close=2026-04-15T09:01:00Z"},
            {"event_ts_utc": "2026-04-15T09:02:00Z", "symbol": "EURUSD",
             "category": "prediction", "event_name": "predict_cycle",
             "pass": "true", "detail": "bar_close=2026-04-15T09:00:00Z"},
        ],
    )
    result = registry.call("time_data.bar_close_ts_sorted_per_symbol", ctx)
    assert result.passed is False
```

- [ ] **Step 2: Verify fail**

```bash
uv run pytest tests/parity/checks/test_time_data_bar_close_ts_sorted.py -v
```

Expected: FAIL.

- [ ] **Step 3: Write the check**

Write `src/behemoth/parity/checks/time_data_bar_close_ts_sorted.py`:

```python
"""Seed check: bar_close timestamps are weakly monotonic per symbol per session."""
from __future__ import annotations

import re

import pandas as pd

from behemoth.parity import loader
from behemoth.parity.registry import register_check
from behemoth.parity.types import CheckContext, CheckResult

_SYMBOLS = ["AUDUSD", "EURUSD", "GBPUSD", "USDCAD", "USDCHF", "USDJPY"]
_BAR_CLOSE_RE = re.compile(r"bar_close=([0-9T:Z\-.]+)")


@register_check(surface_id="time_data.bar_close_ts_sorted_per_symbol", severity="high")
def check(ctx: CheckContext) -> CheckResult:
    if ctx.reconcile_dir is None:
        return CheckResult(
            passed=False, severity="high",
            observed="reconcile_dir missing",
            expected="present",
            evidence="",
        )
    offenders: list[str] = []
    checked = 0
    for symbol in _SYMBOLS:
        df = loader.load_runtime_events(
            reconcile_dir=ctx.reconcile_dir, symbol=symbol, pattern="jforex"
        )
        if df.empty:
            continue
        cycles = df[df["event_name"] == "predict_cycle"].copy()
        if cycles.empty:
            continue
        checked += 1
        cycles["bar_close_ts"] = cycles["detail"].apply(
            lambda d: _BAR_CLOSE_RE.search(str(d)).group(1)
            if _BAR_CLOSE_RE.search(str(d)) else None
        )
        cycles = cycles.dropna(subset=["bar_close_ts"])
        if cycles.empty:
            continue
        ts = pd.to_datetime(cycles["bar_close_ts"], utc=True, errors="coerce").dropna()
        if len(ts) < 2:
            continue
        diffs = ts.diff().dt.total_seconds().dropna()
        if (diffs < 0).any():
            negative_count = int((diffs < 0).sum())
            offenders.append(f"{symbol}: {negative_count} out-of-order bar closes")
    if offenders:
        return CheckResult(
            passed=False, severity="high",
            observed="; ".join(offenders),
            expected="bar_close_ts weakly monotonic per symbol",
            evidence="",
        )
    return CheckResult(
        passed=True, severity="high",
        observed=f"{checked} symbols scanned, bar_close_ts monotonic",
        expected="bar_close_ts weakly monotonic per symbol",
        evidence="",
    )
```

- [ ] **Step 4: Register + verify pass**

Append to `src/behemoth/parity/checks/__init__.py`:

```python
from behemoth.parity.checks import time_data_bar_close_ts_sorted  # noqa: F401
```

Run:

```bash
uv run pytest tests/parity/checks/ -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/behemoth/parity/checks/time_data_bar_close_ts_sorted.py src/behemoth/parity/checks/__init__.py tests/parity/checks/test_time_data_bar_close_ts_sorted.py
git commit -m "feat(parity): seed check time_data.bar_close_ts_sorted_per_symbol"
```

---

## Task 21: `scripts/audit_runtime_parity.py` CLI

**Files:**
- Create: `scripts/audit_runtime_parity.py`
- Create: `tests/test_audit_runtime_parity.py`

- [ ] **Step 1: Write the failing smoke test**

Write `tests/test_audit_runtime_parity.py`:

```python
"""Smoke test for scripts/audit_runtime_parity.py."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def test_harness_runs_and_writes_artifacts(tmp_path: Path) -> None:
    reconcile = tmp_path / "reconcile"
    governance = tmp_path / "gov"
    reconcile.mkdir()
    governance.mkdir()
    (reconcile / "EURUSD_jforex_signal_parity_summary.csv").write_text(
        "symbol,jforex_signal_parity_pass,predict_cycles,failed_signal_events\n"
        "EURUSD,true,136,0\n"
    )
    # Write a matching lock for all 6 symbols
    for sym in ["audusd", "eurusd", "gbpusd", "usdcad", "usdchf", "usdjpy"]:
        (governance / f"{sym}_oco_live_lock.json").write_text(
            '{"model_month":"2026-04","lock_hash":"abc"}'
        )

    out_md = tmp_path / "report.md"
    out_csv = tmp_path / "findings.csv"
    live_db = tmp_path / "reconcile" / "runtime" / "live_state.db"
    (tmp_path / "reconcile" / "runtime").mkdir()

    result = subprocess.run(
        [
            sys.executable, "scripts/audit_runtime_parity.py",
            "--run-id", "test_run",
            "--model-month", "2026-04",
            "--reconcile-dir", str(reconcile),
            "--governance-lock-dir", str(governance),
            "--live-state-db", str(live_db),
            "--out-report", str(out_md),
            "--out-csv", str(out_csv),
        ],
        capture_output=True, text=True,
    )

    assert out_md.exists(), result.stderr
    assert out_csv.exists(), result.stderr
    report_text = out_md.read_text()
    assert "core.predict_cycles_per_bar" in report_text
    assert "risk_gov.governance_lock_pin" in report_text
    # Exit code is non-zero if any critical failed; in this fixture the
    # `lifecycle.active_oco_reconciled` check will fail (no live_state.db).
    assert result.returncode != 0
```

- [ ] **Step 2: Verify fail**

```bash
uv run pytest tests/test_audit_runtime_parity.py -v
```

Expected: FAIL (script doesn't exist yet).

- [ ] **Step 3: Write the CLI**

Write `scripts/audit_runtime_parity.py`:

```python
#!/usr/bin/env python3
"""Durable parity-contract harness.

Runs every registered check against a session's artifacts and emits a
markdown report plus a CSV of findings. Non-zero exit on any critical failure.

See docs/superpowers/specs/2026-04-17-jforex-python-parity-assessment-design.md.
"""
from __future__ import annotations

import argparse
import csv
import logging
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path

from behemoth.parity import checks as _checks  # noqa: F401 — triggers registration
from behemoth.parity import registry
from behemoth.parity.types import CheckContext, CheckResult


logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("audit_runtime_parity")


def _run_all_checks(ctx: CheckContext) -> list[tuple[str, CheckResult | Exception]]:
    rows: list[tuple[str, CheckResult | Exception]] = []
    for sid in registry.all_surface_ids():
        try:
            rows.append((sid, registry.call(sid, ctx)))
        except Exception as exc:  # noqa: BLE001
            rows.append((sid, exc))
    return rows


def _write_report(
    out_report: Path, run_id: str, rows: list[tuple[str, CheckResult | Exception]]
) -> None:
    out_report.parent.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    lines = [
        f"# Parity Audit — {run_id}",
        "",
        f"_Generated {ts}_",
        "",
        "| Surface | Severity | Pass | Observed | Expected |",
        "|---|---|---|---|---|",
    ]
    for sid, result in rows:
        if isinstance(result, Exception):
            lines.append(f"| `{sid}` | ERROR | ❌ | {type(result).__name__}: {result} | — |")
        else:
            mark = "✅" if result.passed else "❌"
            lines.append(
                f"| `{sid}` | {result.severity} | {mark} | {result.observed} | {result.expected} |"
            )
    out_report.write_text("\n".join(lines) + "\n")


def _write_csv(
    out_csv: Path, run_id: str, rows: list[tuple[str, CheckResult | Exception]]
) -> None:
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    with out_csv.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            "run_id", "surface_id", "severity", "passed",
            "observed", "expected", "evidence",
        ])
        for sid, result in rows:
            if isinstance(result, Exception):
                writer.writerow([
                    run_id, sid, "ERROR", False,
                    f"{type(result).__name__}: {result}",
                    "",
                    "".join(traceback.format_exception_only(type(result), result)),
                ])
            else:
                writer.writerow([
                    run_id, sid, result.severity, result.passed,
                    result.observed, result.expected, result.evidence,
                ])


def _exit_code(rows: list[tuple[str, CheckResult | Exception]]) -> int:
    for _, result in rows:
        if isinstance(result, Exception):
            return 2
        if not result.passed and result.severity in {"critical", "high"}:
            return 1
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--model-month", required=True)
    parser.add_argument("--reconcile-dir", type=Path, required=True)
    parser.add_argument("--governance-lock-dir", type=Path, required=True)
    parser.add_argument("--live-state-db", type=Path, required=True)
    parser.add_argument("--out-report", type=Path, required=True)
    parser.add_argument("--out-csv", type=Path, required=True)
    args = parser.parse_args()

    ctx = CheckContext(
        run_id=args.run_id,
        model_month=args.model_month,
        reconcile_dir=args.reconcile_dir,
        live_state_db_path=args.live_state_db,
        governance_lock_dir=args.governance_lock_dir,
    )
    rows = _run_all_checks(ctx)
    _write_report(args.out_report, args.run_id, rows)
    _write_csv(args.out_csv, args.run_id, rows)
    code = _exit_code(rows)
    if code != 0:
        logger.error("Parity audit FAILED (exit %d) for run_id=%s", code, args.run_id)
    else:
        logger.info("Parity audit PASSED for run_id=%s", args.run_id)
    return code


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Verify test passes**

```bash
uv run pytest tests/test_audit_runtime_parity.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/audit_runtime_parity.py tests/test_audit_runtime_parity.py
git commit -m "feat(parity): durable audit_runtime_parity harness"
```

---

## Task 22: Inventory ↔ registry coverage test

**Files:**
- Create: `tests/test_parity_audit_inventory.py`

- [ ] **Step 1: Write the test**

Write `tests/test_parity_audit_inventory.py`:

```python
"""Assert the inventory markdown and the check registry agree on surface_ids."""
from __future__ import annotations

import re
from pathlib import Path

from behemoth.parity import checks as _checks  # noqa: F401 — triggers registration
from behemoth.parity import registry


INVENTORY = Path("docs/analysis/2026-04-17-jforex-python-parity-assessment.md")
_HARNESS_LINE_RE = re.compile(r"^\s*-\s*\*\*harness_check:\*\*\s*yes\s*—\s*([\w.]+)")
_HEADING_RE = re.compile(r"^###\s+([\w.]+)\s*$")


def _parse_inventory() -> list[tuple[str, str | None]]:
    """Return a list of (surface_id, referenced_check_name) tuples."""
    out: list[tuple[str, str | None]] = []
    current: str | None = None
    for line in INVENTORY.read_text().splitlines():
        m = _HEADING_RE.match(line)
        if m:
            current = m.group(1)
            continue
        m2 = _HARNESS_LINE_RE.match(line)
        if m2 and current is not None:
            out.append((current, m2.group(1)))
    return out


def test_every_yes_surface_has_a_registered_check() -> None:
    refs = _parse_inventory()
    registered = set(registry.all_surface_ids())
    for surface_id, check_name in refs:
        assert check_name == surface_id, (
            f"Inventory {surface_id} harness_check references "
            f"{check_name!r} but must equal {surface_id!r}"
        )
        assert surface_id in registered, (
            f"Inventory claims {surface_id} has a harness check but "
            f"no check is registered"
        )


def test_every_registered_check_is_in_the_inventory() -> None:
    refs = {sid for sid, _ in _parse_inventory()}
    registered = set(registry.all_surface_ids())
    missing = registered - refs
    assert not missing, (
        f"Checks registered in code but not declared in inventory: {sorted(missing)}"
    )
```

- [ ] **Step 2: Run the test**

```bash
uv run pytest tests/test_parity_audit_inventory.py -v
```

Expected: PASS (assuming Tasks 2-6 populated the inventory with the 8 `harness_check: yes — <surface_id>` lines that match the registry). If FAIL, the inventory is out of sync — fix the inventory.

- [ ] **Step 3: Commit**

```bash
git add tests/test_parity_audit_inventory.py
git commit -m "test(parity): inventory and registry must stay in sync"
```

---

## Task 23: Wire into `make stage14-jforex-cert`

**Files:**
- Modify: `Makefile`

- [ ] **Step 1: Add a new target**

In `Makefile`, locate the `.PHONY:` list at line 63-69 and add `audit-runtime-parity` to it:

```makefile
.PHONY: ... audit-runtime-parity
```

Locate the existing `stage14-jforex-cert:` target (line 405). Immediately after it, add a new target and make `stage14-jforex-cert` depend on it:

```makefile
audit-runtime-parity:
	uv run python scripts/audit_runtime_parity.py \
		--run-id $(or $(RUN_ID),jforex_live) \
		--model-month $(or $(MODEL_MONTH),2026-04) \
		--reconcile-dir $(or $(RECONCILE_DIR),data/analysis/backtest_reconcile) \
		--governance-lock-dir $(or $(GOV_LOCK_DIR),configs/research/governance/oco) \
		--live-state-db $(or $(LIVE_STATE_DB),data/analysis/backtest_reconcile/runtime/live_state.db) \
		--out-report $(or $(AUDIT_OUT_REPORT),docs/analysis/runtime_parity_audit/$(or $(RUN_ID),jforex_live)_audit.md) \
		--out-csv $(or $(AUDIT_OUT_CSV),docs/analysis/runtime_parity_audit/$(or $(RUN_ID),jforex_live)_findings.csv)
```

Then modify `stage14-jforex-cert:` to also run the audit after the existing script. Change:

```makefile
stage14-jforex-cert:
	uv run python scripts/validate_stage14_jforex_runtime_certification.py \
		...
```

to:

```makefile
stage14-jforex-cert: audit-runtime-parity
	uv run python scripts/validate_stage14_jforex_runtime_certification.py \
		...
```

- [ ] **Step 2: Verify Makefile still parses**

Run:

```bash
make -n audit-runtime-parity
make -n stage14-jforex-cert | head -3
```

Expected: first command prints the `audit_runtime_parity.py` invocation; second prints the audit invocation followed by the existing validate script.

- [ ] **Step 3: Create the output directory**

Run:

```bash
mkdir -p docs/analysis/runtime_parity_audit
echo '*_audit.md' > docs/analysis/runtime_parity_audit/.gitignore
echo '*_findings.csv' >> docs/analysis/runtime_parity_audit/.gitignore
```

(Per-run outputs are timestamped and not committed; the retention policy is the open question from the spec — start with "not committed by default" and refine later.)

- [ ] **Step 4: Commit**

```bash
git add Makefile docs/analysis/runtime_parity_audit/.gitignore
git commit -m "feat(parity): wire audit-runtime-parity into stage14 cert"
```

---

## Task 24: Demo-live wrap-up hook

**Files:**
- Modify: `scripts/build_demo_live_offline_comparison_report.py`

- [ ] **Step 1: Read the current phase-3 hook point**

Run:

```bash
uv run grep -n "phase" scripts/build_demo_live_offline_comparison_report.py | head -20
```

Record where `--phase 2` (and any `--phase 3`) is handled.

- [ ] **Step 2: Add a phase-3 hook**

Add a `_phase3_parity_audit` function and wire it into the CLI. Paste this into the file just before `main()`:

```python
def _phase3_parity_audit(run_id: str, model_month: str) -> str:
    """Run audit_runtime_parity.py as the session wrap-up's Phase 3."""
    import subprocess
    import sys as _sys

    audit_dir = ROOT / "docs/analysis/runtime_parity_audit"
    audit_dir.mkdir(parents=True, exist_ok=True)
    out_md = audit_dir / f"{run_id}_audit.md"
    out_csv = audit_dir / f"{run_id}_findings.csv"

    cmd = [
        _sys.executable, str(ROOT / "scripts" / "audit_runtime_parity.py"),
        "--run-id", run_id,
        "--model-month", model_month,
        "--reconcile-dir", str(RECONCILE_DIR),
        "--governance-lock-dir", str(ROOT / "configs/research/governance/oco"),
        "--live-state-db", str(LIVE_STATE_DB),
        "--out-report", str(out_md),
        "--out-csv", str(out_csv),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    status = "PASS" if result.returncode == 0 else f"FAIL (exit {result.returncode})"
    snippet = out_md.read_text() if out_md.exists() else result.stderr
    return (
        "\n## Parity Audit (Phase 3)\n\n"
        f"- Status: **{status}**\n"
        f"- Report: `{out_md}`\n"
        f"- Findings CSV: `{out_csv}`\n\n"
        "### Report excerpt\n\n"
        + "\n".join(snippet.splitlines()[:30])
    )
```

Then in `main()`, add a `--phase 3` branch that calls `_phase3_parity_audit(...)` and appends its return value to the output markdown. The exact wiring depends on the existing phase-2 branch; follow the same pattern. Record the exact line numbers edited in the commit body.

- [ ] **Step 3: Add a test**

Append to `tests/test_build_demo_live_offline_comparison_report.py`:

```python
def test_phase3_invokes_audit_runtime_parity(monkeypatch, tmp_path):
    """Phase 3 should shell out to audit_runtime_parity.py and append a section."""
    from scripts.build_demo_live_offline_comparison_report import _phase3_parity_audit
    import subprocess

    calls = {}

    def _fake_run(cmd, capture_output, text):
        calls["cmd"] = cmd
        class R:
            returncode = 0
            stdout = ""
            stderr = ""
        return R()

    monkeypatch.setattr(subprocess, "run", _fake_run)
    out = _phase3_parity_audit("test_run", "2026-04")
    assert "Parity Audit" in out
    assert "audit_runtime_parity.py" in " ".join(calls["cmd"])
```

- [ ] **Step 4: Verify**

```bash
uv run pytest tests/test_build_demo_live_offline_comparison_report.py -v
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add scripts/build_demo_live_offline_comparison_report.py tests/test_build_demo_live_offline_comparison_report.py
git commit -m "feat(parity): add phase-3 parity-audit hook to demo-live wrap-up"
```

---

## Task 25: Finalize the inventory

**Files:**
- Modify: `docs/analysis/2026-04-17-jforex-python-parity-assessment.md`

- [ ] **Step 1: Write the executive summary**

Replace the `## Executive summary` section with:

```markdown
## Executive summary

**Scope:** static code audit + 2026-04-15 replay day across AUDUSD + USDCHF + EURUSD.
**Symbols covered by the harness:** all 6 live symbols.
**Seed harness checks:** 8 (see coverage matrix).

### Severity tally

| Layer | Critical | High | Medium | Low |
|---|---|---|---|---|
| core | X | X | X | X |
| lifecycle | X | X | X | X |
| risk_gov | X | X | X | X |
| time_data | X | X | X | X |
| failure | X | X | X | X |

(Replace each X with the count from the populated sections.)

### Top findings

1. (top finding from Core layer)
2. (top finding from Lifecycle layer)
3. (top finding from Risk & gov)
4. (top finding from Time & data)
5. (top finding from Failure paths)

### AUDUSD/USDCHF zero-predict (motivating example)

_(Narrative: describe the 2026-04-17 session evidence, point at `core.predict_cycles_per_bar` in the Harness coverage matrix, and link the follow-up plan that addresses the root cause.)_
```

Replace every X and every placeholder with the actual counts / findings from Tasks 2-6 + Task 10.

- [ ] **Step 2: Write the coverage matrix**

Replace the `## Harness coverage matrix` section:

```markdown
## Harness coverage matrix

| surface_id | severity | check module |
|---|---|---|
| core.predict_cycles_per_bar | critical | src/behemoth/parity/checks/core_predict_cycles_per_bar.py |
| risk_gov.governance_lock_pin | critical | src/behemoth/parity/checks/risk_gov_governance_lock_pin.py |
| core.tick_seq_monotonic | critical | src/behemoth/parity/checks/core_tick_seq_monotonic.py |
| lifecycle.active_oco_reconciled | critical | src/behemoth/parity/checks/lifecycle_active_oco_reconciled.py |
| failure.tick_batch_599_fallback_consistency | high | src/behemoth/parity/checks/failure_tick_batch_599_fallback.py |
| failure.predict_422_warmup_only | critical | src/behemoth/parity/checks/failure_predict_422_warmup_only.py |
| core.entries_allowed_vs_readiness | high | src/behemoth/parity/checks/core_entries_allowed_vs_readiness.py |
| time_data.bar_close_ts_sorted_per_symbol | high | src/behemoth/parity/checks/time_data_bar_close_ts_sorted.py |

### Surfaces with `harness_check: no`

(List surfaces that have no harness check, grouped by rationale: "static contract only", "not yet parameterizable", "low severity".)
```

- [ ] **Step 3: Write the appendix**

Replace the `## Appendix — Replay diff artifact index` section:

```markdown
## Appendix — Replay diff artifact index

- Side A artifacts: `data/analysis/backtest_reconcile/replay_2026_04_15/`
- Side B artifacts: `data/analysis/backtest_reconcile/replay_2026_04_15/side_b/`
- Combined diff parquet: `data/analysis/backtest_reconcile/replay_diff/2026-04-15/parity_replay_diff.parquet`
- One-shot diff script: `scripts/diff_parity_replay.py`
- Side A invocation record: `data/analysis/backtest_reconcile/replay_2026_04_15/INVOCATION.txt`
- Side B invocation record: `data/analysis/backtest_reconcile/replay_2026_04_15/side_b/INVOCATION.txt`
```

- [ ] **Step 4: Verify coverage test passes**

```bash
uv run pytest tests/test_parity_audit_inventory.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add docs/analysis/2026-04-17-jforex-python-parity-assessment.md
git commit -m "docs(parity): finalize inventory exec summary + coverage matrix"
```

---

## Task 26: End-to-end verification against 2026-04-17 evidence

**Files:** none (verification).

- [ ] **Step 1: Run the harness against the actual 2026-04-17 artifacts**

Run:

```bash
mkdir -p /tmp/parity_smoke
uv run python scripts/audit_runtime_parity.py \
  --run-id jforex_live_20260417 \
  --model-month 2026-04 \
  --reconcile-dir data/analysis/backtest_reconcile \
  --governance-lock-dir configs/research/governance/oco \
  --live-state-db data/analysis/backtest_reconcile/runtime/live_state.db \
  --out-report /tmp/parity_smoke/report.md \
  --out-csv /tmp/parity_smoke/findings.csv \
  || echo "non-zero exit as expected"
```

Expected:
- Non-zero exit.
- Report contains a FAIL row for `core.predict_cycles_per_bar` citing AUDUSD and USDCHF.
- Other seed checks either pass or explain their own failures.

- [ ] **Step 2: Inspect**

Run:

```bash
cat /tmp/parity_smoke/report.md
```

Record the output. If `core.predict_cycles_per_bar` does NOT flag AUDUSD/USDCHF on the real 2026-04-17 data, the check is broken — go back to Task 13 and fix.

- [ ] **Step 3: Run the full test suite**

Run:

```bash
uv run pytest tests/parity/ tests/test_audit_runtime_parity.py tests/test_parity_audit_inventory.py tests/test_diff_parity_replay.py -v
```

Expected: all pass.

- [ ] **Step 4: Run the pre-existing test suite that touches adjacent code**

Run:

```bash
uv run pytest tests/test_build_demo_live_offline_comparison_report.py tests/test_validate_stage14_jforex_runtime_certification.py -v
```

Expected: all pass.

- [ ] **Step 5: Dry-run the Makefile target**

Run:

```bash
make -n audit-runtime-parity
```

Expected: prints a `uv run python scripts/audit_runtime_parity.py ...` invocation with the expected flags.

- [ ] **Step 6: Commit a verification note if any touch-ups were needed**

If steps 1-5 surfaced anything, fix and commit. Otherwise skip.

---

## Task 27: Open the PR

**Files:** none (infrastructure).

- [ ] **Step 1: Push the branch**

Run:

```bash
git push -u origin feat/jforex-python-parity-assessment
```

- [ ] **Step 2: Open the PR**

Run (replace base if your fork differs):

```bash
gh pr create \
  --base fix/2026-03-live-promote-and-recert-fixes \
  --title "JForex live vs Python backtest parity assessment + durable harness" \
  --body "$(cat <<'EOF'
## Summary

- One-shot gap inventory at docs/analysis/2026-04-17-jforex-python-parity-assessment.md covering core / lifecycle / risk+gov / time+data / failure-path surfaces.
- Durable harness scripts/audit_runtime_parity.py with 8 seed checks under src/behemoth/parity/checks/.
- Wired into make stage14-jforex-cert and the demo-live wrap-up Phase 3.

## Motivating example

2026-04-17 demo-live session: AUDUSD (165 bar events) and USDCHF (82 bar events) had zero /predict cycles. A static code audit or a one-shot report alone would not catch this on recurrence; the core.predict_cycles_per_bar check does.

## Test plan

- [ ] uv run pytest tests/parity/ tests/test_audit_runtime_parity.py tests/test_parity_audit_inventory.py tests/test_diff_parity_replay.py
- [ ] make -n audit-runtime-parity
- [ ] make -n stage14-jforex-cert
- [ ] Run audit against real 2026-04-17 artifacts; confirm FAIL on AUDUSD/USDCHF

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

Expected: PR URL returned. Post it in the conversation.

---

## Self-review completed inline

- Every spec section is implemented by at least one task: inventory skeleton (Task 1), 4 layer sections (Tasks 2-5), failure shortlist (Task 6), replay Side A/B/diff (Tasks 7-10), registry+types (Task 11), loader (Task 12), 8 seed checks (Tasks 13-20), CLI (Task 21), inventory-coverage test (Task 22), Makefile (Task 23), demo-live hook (Task 24), finalize (Task 25), verification (Task 26), PR (Task 27).
- No TBD/TODO/"implement later" placeholders in the plan.
- Registry/types/loader signatures are used consistently across all 8 check task bodies (`CheckContext`, `CheckResult`, `register_check`, `registry.call`, `loader.load_signal_parity_csvs`, `loader.load_runtime_events`, `loader.load_governance_lock`).
- Every `surface_id` referenced in a check module matches the `surface_id` declared in the matching inventory section (enforced by Task 22's coverage test).
- Severity values are consistent: `critical` for `core.predict_cycles_per_bar`, `risk_gov.governance_lock_pin`, `core.tick_seq_monotonic`, `lifecycle.active_oco_reconciled`, `failure.predict_422_warmup_only`; `high` for `failure.tick_batch_599_fallback_consistency`, `core.entries_allowed_vs_readiness`, `time_data.bar_close_ts_sorted_per_symbol`.
