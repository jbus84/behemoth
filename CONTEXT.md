# CONTEXT.md

Architecture and design context for this repository. Used by `/improve-codebase-architecture` to identify refactoring opportunities.

---

## What This Is

**Tick-based OCO governance pipeline**: A stage-gated, docs-driven system for researching and certifying one-cancels-other (OCO) stop-limit trading strategies.

- **Stages**: 14 sequential gates per symbol-month (data ingestion → mining → WFO → realism → governance → certification)
- **Runtime**: Python (research + governance) + Dukascopy JForex (live broker)
- **Authority**: Governed artifacts in `data/analysis/tick_opportunity_mining/` (truth); narrative docs defer to this
- **Symbols**: EURUSD, GBPUSD, USDJPY, USDCHF, AUDUSD, USDCAD

---

## Core Abstractions (from Graphify: 1166 nodes, 61 communities)

**God Nodes** (most-connected, touch many modules):

1. **`ModelFeatures`** (145 edges) — canonical 16-feature vector for CatBoost OCO classifier
2. **`IncomingTick`** (137 edges) — raw broker tick payload (bid, ask, timestamp, spread)
3. **`IncomingTickBar`** (137 edges) — aggregated tick bar (close_bid, close_ask, high_ask, spreads)
4. **`StateManager`** (132 edges) — DuckDB-backed execution state (trades, OCO groups, tick bars, predictions)
5. **`FeatureConfig`** (130 edges) — rolling window + regime config (feature computation parameter)
6. **`BarrierManager`** (82 edges) — OCO barrier touch detection + position lifecycle
7. **`TickAggregator`** (78 edges) — real-time tick-to-bar aggregation (100, 1000, 2000 tick bars)
8. **`CandidateRegistry`** (74 edges) — deployed OCO family catalog (with selection logic)
9. **`OcoPrediction`** (72 edges) — per-bar model output (entry probability, horizon, direction)

These 9 nodes are highly interconnected. Consolidation opportunities exist if several are used together in a specific context.

---

## Architectural Communities (Major Domains)

| Community | Role | God Nodes Involved | Concern |
|-----------|------|-------------------|---------|
| **Risk & Barrier Management** | Position lifecycle, touch detection, equity gates | `BarrierManager`, `StateManager`, `AccountRiskProfile` | Entry validation, horizon completion, order submission |
| **Feature Computation** | CatBoost input pipeline | `ModelFeatures`, `FeatureConfig`, `IncomingTickBar` | 16-feature matrix from tick bars |
| **Execution State Store** | DuckDB state (trades, OCO groups, ticks) | `StateManager`, `IncomingTick`, `IncomingTickBar` | Persistence, event log, bar caching |
| **JForex Strategy Bridge** | Live broker integration | `BehemothJForexStrategy`, `BrokerBridgeLoader`, `JForexMetrics` | Async tick decoupling, order submission |
| **Strategy Core & Metrics** | Per-symbol runtime, metrics | `BehemothStrategyCore`, `SymbolWorker`, `SymbolRuntimeState` | Worker thread model, Prometheus emission |
| **Account Risk Allocator** | Equity reservation + cost gates | `AccountRiskAllocator`, `AccountRiskProfile`, `AccountRiskBuffers` | Per-symbol allocation, guard thresholds |
| **Historical Warmup & Replay** | Parquet load + bar alignment | `HistoricalWarmupLoader`, `ParquetTickLoader`, `TickAggregator` | Initial state load, alignment verification |
| **Live Readiness** | Per-symbol warmup & broker bridge | `SymbolReadinessState`, `LiveReadinessMetrics`, `BrokerBridgeLoader` | Readiness status, startup gates |
| **Execution Ports** | Broker order I/O abstraction | `ExecutionPort`, `JForexExecutionPort`, `LocalExecutionPort` | Order submission, testing stubs |

---

## Thread Model (Async Tick Decoupling)

**Three execution contexts:**

1. **Strategy Thread** (Dukascopy callback)
   - Entry: `onTick(RuntimeTick)`
   - Action: Enqueue `TickEvent` to `SymbolWorker`
   - Return: Immediately (target < 1 µs)
   - **Constraint**: No blocking I/O, no `/predict` calls, no order submissions

2. **Worker Thread** (one per symbol, named `behemoth-worker-<SYMBOL>`)
   - Drain tick queue (from strategy thread)
   - Aggregate ticks → bars (via `TickAggregator`)
   - Call `/predict` (HTTP to Python API)
   - Call `/orders` (HTTP to order engine)
   - Submit orders inline (via `ExecutionPort`)
   - Update state (via `StateManager`)

3. **Test Thread** (determinism)
   - `LocalJForexTesterRunner` calls `symbolWorker.drain()` after each tick injection
   - No background thread leakage between ticks

**God node involvement**: `IncomingTick` → `TickAggregator` → `IncomingTickBar` → state persistence + `/predict` calls.

---

## Design Decisions

### 1. Docs-Driven Governance (Artifact-First Truth)

- Governed artifacts under `data/analysis/tick_opportunity_mining/` are the authoritative source
- `scripts/validate_oco_docs_contract.py` enforces schema, freshness, and coherence
- Artifacts are regenerated (never manually edited) via `make retrain-all`
- Symbol universe changes require regeneration of all dependent reports

**Implication**: If consolidating schemas or adding new artifact types, update the docs contract validator.

### 2. Worktree-Native Git (Branch + Commit Specificity)

- All feature work happens in isolated git worktrees
- Specs and plans must name target **branch AND commit hash**
- **Exception**: Stage 12–14 certification runs from root checkout (requires broker creds + authoritative evidence)

**Implication**: Tests pass in worktree ≠ stage certification passes (different environment).

### 3. Explicit Bid/Ask Bar Schema

Recent refactor (Apr 2026):
- Bar fields: `open_bid`, `close_bid`, `high_ask`, `close_ask` (not `mid` or generic `close`)
- Reason: OCO entry pricing depends on side (BUY uses ask-side barriers, SELL uses bid-side)
- All analysis and runtime code updated to use explicit fields

**Implication**: Feature computation and barrier detection are side-aware; consolidating these requires careful schema migration.

### 4. Per-Symbol State Isolation

- Each symbol has a dedicated `SymbolWorker` thread (owns its queue, its bars, its predictions)
- `StateManager` is global but indexed by symbol
- Account risk allocation is per-symbol (with global equity pool)

**Implication**: Cross-symbol operations (like global rebalancing) require explicit coordination; worker isolation currently prevents this.

### 5. Verdict Canonicalization

Canonical values (from `UBIQUITOUS_LANGUAGE.md`):
- `PASS` — process completed, evidence valid
- `FAIL` — process or evidence invalid
- `GO` — symbol eligible for deployment
- `NO_GO` — symbol intentionally not deployed (expected non-deployability)

**Implication**: All reporting, CSV exports, and governance decision points must use only these 4 terms.

---

## Known Tightly-Coupled Modules

### 1. `BarrierManager` ↔ `StateManager` ↔ `IncomingTickBar`

- Barrier manager evaluates bars and updates OCO state
- State manager persists barrier state and position lifecycle
- Both depend on explicit bar schema (bid/ask fields)
- **Opportunity**: Extract a shared "bar context" interface so each module doesn't need full StateManager/TickBar awareness

### 2. `FeatureConfig` ↔ `ModelFeatures` ↔ Research Pipeline

- Feature computation hardcodes 16 features + rolling window logic
- Config object travels through research pipeline (WFO, robustness, etc.)
- Changes to feature set require updating multiple scripts
- **Opportunity**: Centralize feature schema versioning; make pipeline polymorphic over feature count

### 3. `SymbolWorker` ↔ `BehemothStrategyCore` ↔ `ExecutionPort`

- Worker thread drains ticks, calls core, submits orders
- Core logic is Java-side; execution is polymorphic (JForex, Local, Noop stubs)
- Thread safety relies on queue discipline
- **Opportunity**: Extract order submission protocol so core doesn't depend on ExecutionPort directly

### 4. `HistoricalWarmupLoader` ↔ `TickAggregator` ↔ Bar Alignment

- Warmup loader replays parquet files to populate bar state
- Tick aggregator computes bars in real time
- Both must agree on bar boundaries (100, 1000, 2000 tick thresholds)
- **Opportunity**: Create a shared "bar alignment verifier" that both paths can test against

### 5. `AccountRiskAllocator` ↔ `SymbolWorker` ↔ Entry Gate

- Worker checks account risk before submitting orders
- Risk allocator manages per-symbol reservations and global equity pool
- Reservation lifecycle is implicit in order state
- **Opportunity**: Explicit reservation state machine (reserved → submitted → filled → released)

---

## Lower-Cohesion Communities (Refactoring Candidates)

From Graphify report (61 communities):

- **Community 19** (Cohesion 0.6): 0 nodes (empty/placeholder)
- **Community 20–40** (Cohesion 0.5): Mostly single-node communities (isolated classes)
  - `BrokerOrderSnapshotWriter` (0.5 cohesion)
  - `BrokerHistoryPort` (0.5 cohesion)
  - `RuntimeInstrument` (isolated)
  - Various payload DTOs (isolated)

**Observation**: These low-cohesion clusters are likely test stubs, ports, or one-off utilities. Candidates for grouping or removal if unused.

---

## Test Coverage Gaps (Known)

- **API contract tests**: `/predict` and `/orders` endpoints have integration tests but could use more edge cases (e.g., concurrent predictions, order rejection)
- **JForex live integration**: Tests use local surrogate; real Dukascopy integration only in Stage 13–14 (manual)
- **Governance lock consistency**: No automated check that symbol-month locks match deployed state
- **Cross-symbol rebalancing**: Account risk allocation is per-symbol; no tests for global equity pool exhaustion

---

## Tech Stack & Constraints

- **Python**: 3.11, Pydantic v2, FastAPI, DuckDB (in-process state), CatBoost (model)
- **Java/JForex**: Gradle, JUnit 5, Dukascopy SDK (broker client)
- **Data**: Parquet (tick storage), YAML (config), JSON (governance locks + artifacts)
- **Queue**: `LinkedTransferQueue` (unbounded, in-memory, no persistence)
- **Metrics**: Prometheus (JForex), custom JSON (Python state snapshots)

**Constraints**:
- No async Python (blocking I/O in worker thread is acceptable)
- No message broker or event log (state is authoritative)
- Worktrees + root checkout dual-environment (complicates CI/CD)

---

## Symbols & Active Universe

**Active**: EURUSD, GBPUSD, USDJPY, USDCHF, AUDUSD, USDCAD (6 symbols)

**Why these**: Major FX pairs with sufficient volatility and tick data availability (Dukascopy).

**Impact on consolidation**: Refactoring should remain symbol-agnostic (avoid hardcoding 6-symbol assumptions).

---

## Recent Architectural Wins (Last 2 Months)

- **Async tick decoupling** (#112): HTTP I/O moved off strategy thread
- **State manager seam** (#100): Closed 11 raw DB execute leaks via StateManager methods
- **Live stage DAG** (#95): Explicit restart eligibility + provenance
- **Explicit bid/ask schema**: All code now uses side-aware bar fields
- **Ubiquitous language alignment**: All verdicts, CSVs, and governance docs canonicalized

These should inform consolidation priorities: avoid regressing the gains (thread safety, verdict consistency, side-aware pricing).
