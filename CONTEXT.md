# CONTEXT.md

Architecture and design context for this repository. Used by `/improve-codebase-architecture` to identify refactoring opportunities.

---

## What This Is

A trading-system repo with two working surfaces:

1. **Straddle logic** (`scripts/boostlss_xs/`) — a standalone BoostLSS cross-symbol straddle meta-labeler. Features → flagging → meta-labeler → model → walk-forward runner. Self-contained, writes to `/tmp`, not imported by the live runtime.
2. **Live JForex scaffold** (`src/behemoth/{api,runtime,core,risk}` + `src/jforex/`) — a FastAPI runtime + Dukascopy JForex (Kotlin/Gradle) broker adapter. The `/predict` endpoint is a placeholder returning empty predictions pending wiring to the straddle logic.

- **Runtime**: Python (FastAPI decision runtime) + Kotlin/JForex (Dukascopy broker)
- **Authority**: source under `src/` and `scripts/boostlss_xs/`; the prior governed-artifact truth surface has been removed (GitHub retains history)
- **Symbols**: EURUSD, GBPUSD, USDJPY, USDCHF, AUDUSD, USDCAD

---

## Core Abstractions

### Straddle logic (`scripts/boostlss_xs/`)
- `features.py` — tick-bar feature computation (uses `scipy.stats`, sklearn, numpy/pandas/polars)
- `flagging.py` — channel/straddle flagging
- `meta_labeler.py` / `meta_label_v2.py` — meta-labeling (de Prado-style side+size)
- `model.py` (`BoostLssWFO`) — BoostLSS walk-forward model (uses `boostlss_py`)
- `universe.py` — symbol universe loading (parquet)
- `run.py`, `reversion_straddle.py`, `meta_label_straddle.py`, `causal_validation.py` — runners / validation

### Live JForex scaffold
- `src/behemoth/api/server.py` — FastAPI app; `/predict` placeholder, `/health`, `/status`, `/metrics`, `/ticks`, `/bars`, `/trades`, `/risk/account*`, `/checkpoint`, `/open-summary`
- `src/behemoth/api/predict_orchestrator.py` — `PredictionOrchestrator`; `_step_resolve_candidates` returns `[]` (placeholder short-circuit → empty `PredictResponse`)
- `src/behemoth/api/runtime_app_state.py` — runtime app state container
- `src/behemoth/runtime/` — `state.py` (StateManager, DuckDB), `state_store.py`, tick aggregation, bar building
- `src/behemoth/core/` — `schemas`, `features`, `feature_engine`, `feature_pipeline`, `feature_validator`, `regime_quantile_contract`, `horizon_feature_config` (live primitives; governance/registry modules removed)
- `src/behemoth/risk/` — account risk allocation (`account.py`, barrier manager)
- `src/jforex/` — Kotlin/Gradle broker adapter; `BehemothJForexStrategy`, `JForexLiveRunner`, `LocalJForexTesterRunner`, `JForexTesterRunner`

---

## Architectural Properties

### 1. Worktree-Native Git
- All feature work happens in isolated git worktrees; merge via PR, never commit directly to `main`.
- Specs and plans should name target branch AND commit hash.

### 2. Explicit Bid/Ask Bar Schema
- Bar fields: `open_bid`, `close_bid`, `high_ask`, `close_ask` (not `mid` or generic `close`).
- Entry pricing is side-aware (BUY uses ask-side barriers, SELL uses bid-side).
- Feature computation and barrier detection are side-aware.

### 3. Per-Symbol State Isolation
- Each symbol has a dedicated `SymbolWorker` thread (owns its queue, bars, predictions).
- `StateManager` is global but indexed by symbol.
- Account risk allocation is per-symbol (with a global equity pool).

### 4. Verdict Canonicalization
Canonical values (from `UBIQUITOUS_LANGUAGE.md`):
- `PASS` — process completed, evidence valid
- `FAIL` — process or evidence invalid
- `GO` — symbol eligible for deployment
- `NO_GO` — symbol intentionally not deployed

All reporting, CSV exports, and decision points must use only these 4 terms.

---

## Known Tightly-Coupled Modules

### `BarrierManager` ↔ `StateManager` ↔ `IncomingTickBar`
- Barrier manager evaluates bars and updates OCO state; state manager persists barrier state and position lifecycle; both depend on the explicit bid/ask bar schema.
- **Opportunity**: extract a shared "bar context" interface so each module doesn't need full StateManager/TickBar awareness.

### `SymbolWorker` ↔ `BehemothStrategyCore` ↔ `ExecutionPort`
- Worker thread drains ticks, calls the Python runtime, submits orders; core logic is Kotlin-side; execution is polymorphic (JForex, Local, Noop stubs).
- **Opportunity**: extract an order-submission protocol so core doesn't depend on `ExecutionPort` directly.

### `AccountRiskAllocator` ↔ `SymbolWorker` ↔ Entry Gate
- Worker checks account risk before submitting orders; allocator manages per-symbol reservations + global equity pool; reservation lifecycle is implicit in order state.
- **Opportunity**: explicit reservation state machine (reserved → submitted → filled → released).

---

## Tech Stack & Constraints

- **Python**: 3.10+, Pydantic v2, FastAPI, DuckDB (in-process state), polars/numpy/pandas/scikit-learn/scipy, boostlss (git source)
- **Kotlin/JForex**: Gradle, JUnit 5, Dukascopy SDK (broker client)
- **Data**: Parquet (tick storage), YAML (config), JSON (state snapshots)
- **Queue**: `LinkedTransferQueue` (unbounded, in-memory, no persistence)
- **Metrics**: `prometheus-client` (Python `/metrics`), Prometheus + Grafana + Alertmanager stack (`docker-compose.yml`) scraping the live scaffold

**Constraints**:
- No async Python (blocking I/O in worker thread is acceptable)
- No message broker or event log (state is authoritative)
- The `/predict` path is a placeholder; the runtime scaffold (state, barriers, risk, metrics) is live