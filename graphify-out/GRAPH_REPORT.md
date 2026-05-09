# Graph Report - src  (2026-05-09)

## Corpus Check
- 150 files · ~70,985 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 1794 nodes · 7057 edges · 73 communities detected
- Extraction: 34% EXTRACTED · 66% INFERRED · 0% AMBIGUOUS · INFERRED: 4667 edges (avg confidence: 0.58)
- Token cost: 0 input · 0 output

## Community Hubs (Navigation)
- [[_COMMUNITY_Reservation Lifecycle|Reservation Lifecycle]]
- [[_COMMUNITY_Tick Bar Processing|Tick Bar Processing]]
- [[_COMMUNITY_Tick Bar Processing|Tick Bar Processing]]
- [[_COMMUNITY_Barrier Management|Barrier Management]]
- [[_COMMUNITY_Account Risk|Account Risk]]
- [[_COMMUNITY_Community 5|Community 5]]
- [[_COMMUNITY_Tick Bar Processing|Tick Bar Processing]]
- [[_COMMUNITY_Account Risk|Account Risk]]
- [[_COMMUNITY_Feature Computation|Feature Computation]]
- [[_COMMUNITY_Prediction Pipeline|Prediction Pipeline]]
- [[_COMMUNITY_Data Contracts|Data Contracts]]
- [[_COMMUNITY_Community 11|Community 11]]
- [[_COMMUNITY_Audit Trail|Audit Trail]]
- [[_COMMUNITY_Community 13|Community 13]]
- [[_COMMUNITY_Tick Bar Processing|Tick Bar Processing]]
- [[_COMMUNITY_Community 15|Community 15]]
- [[_COMMUNITY_Tick Bar Processing|Tick Bar Processing]]
- [[_COMMUNITY_Community 17|Community 17]]
- [[_COMMUNITY_Tick Bar Processing|Tick Bar Processing]]
- [[_COMMUNITY_Community 19|Community 19]]
- [[_COMMUNITY_Community 20|Community 20]]
- [[_COMMUNITY_Community 21|Community 21]]
- [[_COMMUNITY_Tick Bar Processing|Tick Bar Processing]]
- [[_COMMUNITY_Community 23|Community 23]]
- [[_COMMUNITY_Community 24|Community 24]]
- [[_COMMUNITY_Tick Bar Processing|Tick Bar Processing]]
- [[_COMMUNITY_Community 26|Community 26]]
- [[_COMMUNITY_Community 27|Community 27]]
- [[_COMMUNITY_Community 28|Community 28]]
- [[_COMMUNITY_Community 29|Community 29]]
- [[_COMMUNITY_Community 30|Community 30]]
- [[_COMMUNITY_Community 31|Community 31]]
- [[_COMMUNITY_Candidate Selection|Candidate Selection]]
- [[_COMMUNITY_Community 33|Community 33]]
- [[_COMMUNITY_Community 34|Community 34]]
- [[_COMMUNITY_Community 35|Community 35]]
- [[_COMMUNITY_Community 36|Community 36]]
- [[_COMMUNITY_Barrier Management|Barrier Management]]
- [[_COMMUNITY_Community 38|Community 38]]
- [[_COMMUNITY_Community 39|Community 39]]
- [[_COMMUNITY_Community 40|Community 40]]
- [[_COMMUNITY_Reservation Lifecycle|Reservation Lifecycle]]
- [[_COMMUNITY_Community 42|Community 42]]
- [[_COMMUNITY_Account Risk|Account Risk]]
- [[_COMMUNITY_Reservation Lifecycle|Reservation Lifecycle]]
- [[_COMMUNITY_Community 45|Community 45]]
- [[_COMMUNITY_Community 46|Community 46]]
- [[_COMMUNITY_Community 47|Community 47]]
- [[_COMMUNITY_Community 48|Community 48]]
- [[_COMMUNITY_Community 49|Community 49]]
- [[_COMMUNITY_Community 50|Community 50]]
- [[_COMMUNITY_Community 51|Community 51]]
- [[_COMMUNITY_Community 52|Community 52]]
- [[_COMMUNITY_Tick Bar Processing|Tick Bar Processing]]
- [[_COMMUNITY_Community 54|Community 54]]
- [[_COMMUNITY_Community 55|Community 55]]
- [[_COMMUNITY_Community 56|Community 56]]
- [[_COMMUNITY_Community 57|Community 57]]
- [[_COMMUNITY_Prediction Pipeline|Prediction Pipeline]]
- [[_COMMUNITY_Account Risk|Account Risk]]
- [[_COMMUNITY_Prediction Pipeline|Prediction Pipeline]]
- [[_COMMUNITY_Community 61|Community 61]]
- [[_COMMUNITY_Tick Bar Processing|Tick Bar Processing]]
- [[_COMMUNITY_Tick Bar Processing|Tick Bar Processing]]
- [[_COMMUNITY_API Orchestration|API Orchestration]]
- [[_COMMUNITY_Community 65|Community 65]]
- [[_COMMUNITY_Tick Bar Processing|Tick Bar Processing]]
- [[_COMMUNITY_Tick Bar Processing|Tick Bar Processing]]
- [[_COMMUNITY_Community 68|Community 68]]
- [[_COMMUNITY_Community 69|Community 69]]
- [[_COMMUNITY_Community 70|Community 70]]
- [[_COMMUNITY_Community 71|Community 71]]
- [[_COMMUNITY_Prediction Pipeline|Prediction Pipeline]]

## God Nodes (most connected - your core abstractions)
1. `ModelFeatures` - 228 edges
2. `IncomingTick` - 155 edges
3. `IncomingTickBar` - 155 edges
4. `StateManager` - 153 edges
5. `BarrierManager` - 129 edges
6. `BarContext` - 126 edges
7. `BarrierAction` - 114 edges
8. `CandidateCatalog` - 113 edges
9. `CatalogContext` - 107 edges
10. `AccountRiskDecision` - 106 edges

## Surprising Connections (you probably didn't know these)
- `Warmup boundary verification: replaces silent None returns with observable statu` --uses--> `FeatureConfig`  [INFERRED]
  src/behemoth/runtime/warmup_verifier.py → src/behemoth/core/features.py
- `Result of a warmup bar count check.` --uses--> `FeatureConfig`  [INFERRED]
  src/behemoth/runtime/warmup_verifier.py → src/behemoth/core/features.py
- `Single source of truth for warmup gate decisions.` --uses--> `FeatureConfig`  [INFERRED]
  src/behemoth/runtime/warmup_verifier.py → src/behemoth/core/features.py
- `Initialize verifier with the required warmup bar count.` --uses--> `FeatureConfig`  [INFERRED]
  src/behemoth/runtime/warmup_verifier.py → src/behemoth/core/features.py
- `Check if bar_count satisfies warmup requirement.          Args:             bar_` --uses--> `FeatureConfig`  [INFERRED]
  src/behemoth/runtime/warmup_verifier.py → src/behemoth/core/features.py

## Communities

### Community 0 - "Reservation Lifecycle"
Cohesion: 0.02
Nodes (193): Reset all cached state. Called on startup and reload., Atomically reset all managed caches in registration order.          Each cache.c, _normalize_model_month(), _normalize_symbol(), check(), Seed check: entry_blocked_not_ready events must correlate with non-READY readine, check(), Seed check: every symbol with bar events must have at least one predict cycle. (+185 more)

### Community 1 - "Tick Bar Processing"
Cohesion: 0.05
Nodes (166): BarAlignmentResult, BarAlignmentService, BarBoundaryContract, _build_bar(), _compute_microstructure(), _compute_price_stats(), Fixed-tick bar alignment utilities shared by runtime tick ingestion., Compute the microstructural sequence makers for a bar. (+158 more)

### Community 2 - "Tick Bar Processing"
Cohesion: 0.03
Nodes (23): BehemothJForexStrategy, BrokerBridgeLoader, BrokerBridgeLoaderTest, FakeBrokerHistoryPort, MutableClock, JForexBrokerHistoryPort, BridgeRuntime, BridgeRuntimeFactory (+15 more)

### Community 3 - "Barrier Management"
Cohesion: 0.15
Nodes (137): AccountRiskDecision, AccountRiskProfile, BarrierManager, BaseModel, CacheManager, Manages atomic reset of all inference-time caches.      Ensures that cache reset, Initialize manager with caches in reset order.          Args:             caches, CandidateCatalog (+129 more)

### Community 4 - "Account Risk"
Cohesion: 0.03
Nodes (19): BehemothStrategyCore, closePositionByScanId(), entriesAllowed(), submitMarketOrder(), SymbolRuntimeState, JForexMetrics, TimerContext, OrderLifecycleHandler (+11 more)

### Community 5 - "Community 5"
Cohesion: 0.03
Nodes (29): symbol(), isCloseMarket(), isOpenMarket(), BehemothStrategyCoreTest, BrokerOrderSnapshotWriter, JForexConnectionTest, Sleeper, fromEnvironment() (+21 more)

### Community 6 - "Tick Bar Processing"
Cohesion: 0.03
Nodes (75): BarTouchResult, BarTouchSemantics, evaluate(), BarTouchSemantics — explicit tie-breaking logic for barrier touches.  Owns the i, Result of evaluating barrier touches and tie-breaking logic., Evaluates barrier touches using explicit hl_first tie-breaking semantics., BarContextAdapter, BarrierEvaluationContext (+67 more)

### Community 7 - "Account Risk"
Cohesion: 0.04
Nodes (68): AccountRiskAllocator, AccountRiskBuffers, AccountRiskCostGate, _as_utc(), EntryGateDecision, evaluate_account_risk_decision(), evaluate_account_risk_limits(), evaluate_trade_guard() (+60 more)

### Community 8 - "Feature Computation"
Cohesion: 0.05
Nodes (41): compare_feature_parity(), _ensure_columns(), feature_columns_from_live_rows(), load_live_feature_rows(), load_runtime_bars(), _normalize_close_ts_to_utc(), _parse_barrier_pips(), parse_canonical_uid() (+33 more)

### Community 9 - "Prediction Pipeline"
Cohesion: 0.08
Nodes (36): HistoricalPredictionLoadError, HistoricalPredictionLoadStatus, MissingHistoricalPredictionArtifact, Historical prediction payload staging for exact replay parity in backtesting.  E, Raised when historical prediction staging cannot satisfy its load contract., Raised when a locked predictions parquet artifact is missing., BrokerSnapshot, BrokerSnapshotOrder (+28 more)

### Community 10 - "Data Contracts"
Cohesion: 0.06
Nodes (21): _month_from_close_ts(), Unified Candidate State sourcing across live and historical governance modes., Resolved Candidate State and model artifact contract for one symbol/month., RuntimeCandidateContract, HistoricalLockEntry, Historical governance lock registry for month-aligned backtest inference.  Loads, Return the total number of loaded historical lock entries., Month-aware candidate/model registry for historical replay. (+13 more)

### Community 11 - "Community 11"
Cohesion: 0.06
Nodes (12): isConnected(), JForexBrokerSnapshotRunner, startStrategy(), connect(), isConnected(), JForexLiveRunner, LiveClient, startStrategy() (+4 more)

### Community 12 - "Audit Trail"
Cohesion: 0.1
Nodes (32): _as_utc_pydatetime(), audit_threshold_pool(), _build_distribution_decomposition(), _build_recomputed_feature_rows(), _build_report(), _classification_explanation(), classify_diagnostic(), DiagnosticInputs (+24 more)

### Community 13 - "Community 13"
Cohesion: 0.13
Nodes (4): ExecutionStateStore, ExecutionStateStoreTest, OcoGroupState, OcoLegState

### Community 14 - "Tick Bar Processing"
Cohesion: 0.14
Nodes (4): BarAlignmentService, BarAlignmentServiceTest, HistoricalWarmupLoader, HistoricalWarmupLoaderTest

### Community 15 - "Community 15"
Cohesion: 0.11
Nodes (4): NoopExecutionPort, RecordingExecutionPort, ExecutionPort, toMarketOrderRequest()

### Community 16 - "Tick Bar Processing"
Cohesion: 0.29
Nodes (2): JForexExecutionPort, Task

### Community 17 - "Community 17"
Cohesion: 0.22
Nodes (9): all_artifacts(), artifact(), artifact_path(), Registry of files written into the live runtime directory.  The ``data/analysis/, Return the canonical path for a registered artifact under ``runtime_dir``., All registered artifacts, in declaration order., A single file written into the live runtime directory.      - ``key`` is the sta, Look up a registered artifact by stable key. Raises KeyError on typos. (+1 more)

### Community 18 - "Tick Bar Processing"
Cohesion: 0.38
Nodes (1): ParquetTickLoader

### Community 19 - "Community 19"
Cohesion: 0.22
Nodes (1): BrokerSnapshotStrategy

### Community 20 - "Community 20"
Cohesion: 0.25
Nodes (6): failed_checks(), Composable governance validation rules for historical locks.  Encapsulates valid, Return failed checks produced by this validator., Return failed governance validation checks., Summarize failed governance validation checks for operator surfaces., summarize_failures()

### Community 21 - "Community 21"
Cohesion: 0.29
Nodes (1): LiveReadinessMetrics

### Community 22 - "Tick Bar Processing"
Cohesion: 0.33
Nodes (4): Warmup boundary verification: replaces silent None returns with observable statu, Result of a warmup bar count check., Check if bar_count satisfies warmup requirement.          Args:             bar_, WarmupStatus

### Community 23 - "Community 23"
Cohesion: 0.5
Nodes (3): Unified cache lifecycle management for runtime modules.  Coordinates atomic rese, Protocol for inference-time caches that need coordinated reset.      Implementat, RuntimeCache

### Community 24 - "Community 24"
Cohesion: 0.5
Nodes (3): dashboard(), Lightweight monitoring dashboard for the Behemoth OCO strategy.  Served as a Fas, Serve the single-page monitoring dashboard.

### Community 25 - "Tick Bar Processing"
Cohesion: 0.5
Nodes (1): BrokerHistoryPort

### Community 26 - "Community 26"
Cohesion: 1.0
Nodes (1): Read-only runtime state query interfaces (deprecated: use state_readers instead)

### Community 27 - "Community 27"
Cohesion: 1.0
Nodes (0): 

### Community 28 - "Community 28"
Cohesion: 1.0
Nodes (0): 

### Community 29 - "Community 29"
Cohesion: 1.0
Nodes (0): 

### Community 30 - "Community 30"
Cohesion: 1.0
Nodes (1): Build from a state_universe row in the live lock JSON.

### Community 31 - "Community 31"
Cohesion: 1.0
Nodes (1): Load exactly from per-symbol *_oco_live_lock.json files.

### Community 32 - "Candidate Selection"
Cohesion: 1.0
Nodes (1): Symbols that have at least one registered candidate.

### Community 33 - "Community 33"
Cohesion: 1.0
Nodes (0): 

### Community 34 - "Community 34"
Cohesion: 1.0
Nodes (1): Convert to UTC datetime.

### Community 35 - "Community 35"
Cohesion: 1.0
Nodes (1): Compute SHA256 hash of file.

### Community 36 - "Community 36"
Cohesion: 1.0
Nodes (1): Generate cache key: symbol or symbol|month.

### Community 37 - "Barrier Management"
Cohesion: 1.0
Nodes (1): Evaluate which barriers touched and apply tie-breaking logic.          Args:

### Community 38 - "Community 38"
Cohesion: 1.0
Nodes (0): 

### Community 39 - "Community 39"
Cohesion: 1.0
Nodes (0): 

### Community 40 - "Community 40"
Cohesion: 1.0
Nodes (0): 

### Community 41 - "Reservation Lifecycle"
Cohesion: 1.0
Nodes (1): Get the reservation ID.

### Community 42 - "Community 42"
Cohesion: 1.0
Nodes (1): Get the current state.

### Community 43 - "Account Risk"
Cohesion: 1.0
Nodes (1): Get the reserved loss amount in account currency.

### Community 44 - "Reservation Lifecycle"
Cohesion: 1.0
Nodes (1): Convert string to ReservationState enum.          Args:             raw: String

### Community 45 - "Community 45"
Cohesion: 1.0
Nodes (1): Validate that state is a valid initial state.          Args:             state:

### Community 46 - "Community 46"
Cohesion: 1.0
Nodes (1): Validate a state transition.          Args:             current: Current state (

### Community 47 - "Community 47"
Cohesion: 1.0
Nodes (0): 

### Community 48 - "Community 48"
Cohesion: 1.0
Nodes (0): 

### Community 49 - "Community 49"
Cohesion: 1.0
Nodes (0): 

### Community 50 - "Community 50"
Cohesion: 1.0
Nodes (0): 

### Community 51 - "Community 51"
Cohesion: 1.0
Nodes (0): 

### Community 52 - "Community 52"
Cohesion: 1.0
Nodes (0): 

### Community 53 - "Tick Bar Processing"
Cohesion: 1.0
Nodes (0): 

### Community 54 - "Community 54"
Cohesion: 1.0
Nodes (0): 

### Community 55 - "Community 55"
Cohesion: 1.0
Nodes (0): 

### Community 56 - "Community 56"
Cohesion: 1.0
Nodes (0): 

### Community 57 - "Community 57"
Cohesion: 1.0
Nodes (0): 

### Community 58 - "Prediction Pipeline"
Cohesion: 1.0
Nodes (0): 

### Community 59 - "Account Risk"
Cohesion: 1.0
Nodes (0): 

### Community 60 - "Prediction Pipeline"
Cohesion: 1.0
Nodes (0): 

### Community 61 - "Community 61"
Cohesion: 1.0
Nodes (0): 

### Community 62 - "Tick Bar Processing"
Cohesion: 1.0
Nodes (0): 

### Community 63 - "Tick Bar Processing"
Cohesion: 1.0
Nodes (0): 

### Community 64 - "API Orchestration"
Cohesion: 1.0
Nodes (0): 

### Community 65 - "Community 65"
Cohesion: 1.0
Nodes (0): 

### Community 66 - "Tick Bar Processing"
Cohesion: 1.0
Nodes (0): 

### Community 67 - "Tick Bar Processing"
Cohesion: 1.0
Nodes (0): 

### Community 68 - "Community 68"
Cohesion: 1.0
Nodes (0): 

### Community 69 - "Community 69"
Cohesion: 1.0
Nodes (0): 

### Community 70 - "Community 70"
Cohesion: 1.0
Nodes (0): 

### Community 71 - "Community 71"
Cohesion: 1.0
Nodes (0): 

### Community 72 - "Prediction Pipeline"
Cohesion: 1.0
Nodes (0): 

## Knowledge Gaps
- **161 isolated node(s):** `A single prediction candidate to evaluate.`, `Build from a state_universe row in the live lock JSON.`, `Registry of valid candidate specifications loaded from live lock JSONs.`, `Load exactly from per-symbol *_oco_live_lock.json files.`, `Symbols that have at least one registered candidate.` (+156 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **Thin community `Community 26`** (2 nodes): `state_queries.py`, `Read-only runtime state query interfaces (deprecated: use state_readers instead)`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 27`** (2 nodes): `normalizeSymbol()`, `RuntimeInstrument.java`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 28`** (2 nodes): `SymbolReadinessSnapshot.java`, `normalizeSymbol()`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 29`** (1 nodes): `__init__.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 30`** (1 nodes): `Build from a state_universe row in the live lock JSON.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 31`** (1 nodes): `Load exactly from per-symbol *_oco_live_lock.json files.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Candidate Selection`** (1 nodes): `Symbols that have at least one registered candidate.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 33`** (1 nodes): `__init__.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 34`** (1 nodes): `Convert to UTC datetime.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 35`** (1 nodes): `Compute SHA256 hash of file.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 36`** (1 nodes): `Generate cache key: symbol or symbol|month.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Barrier Management`** (1 nodes): `Evaluate which barriers touched and apply tie-breaking logic.          Args:`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 38`** (1 nodes): `__init__.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 39`** (1 nodes): `__init__.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 40`** (1 nodes): `__init__.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Reservation Lifecycle`** (1 nodes): `Get the reservation ID.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 42`** (1 nodes): `Get the current state.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Account Risk`** (1 nodes): `Get the reserved loss amount in account currency.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Reservation Lifecycle`** (1 nodes): `Convert string to ReservationState enum.          Args:             raw: String`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 45`** (1 nodes): `Validate that state is a valid initial state.          Args:             state:`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 46`** (1 nodes): `Validate a state transition.          Args:             current: Current state (`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 47`** (1 nodes): `build.gradle.kts`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 48`** (1 nodes): `MarketOrderRequest.java`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 49`** (1 nodes): `OrderEvent.java`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 50`** (1 nodes): `OrderHandle.java`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 51`** (1 nodes): `OrderResult.java`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 52`** (1 nodes): `OrderEventType.java`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Tick Bar Processing`** (1 nodes): `RuntimeTick.java`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 54`** (1 nodes): `OrderRequest.java`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 55`** (1 nodes): `TradeOpenRequestPayload.java`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 56`** (1 nodes): `BackfillRequestPayload.java`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 57`** (1 nodes): `ActiveTradePayload.java`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Prediction Pipeline`** (1 nodes): `PredictRequestPayload.java`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Account Risk`** (1 nodes): `AccountSnapshotRequestPayload.java`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Prediction Pipeline`** (1 nodes): `PredictResponsePayload.java`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 61`** (1 nodes): `TradeTouchRequestPayload.java`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Tick Bar Processing`** (1 nodes): `TickIngestResponsePayload.java`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Tick Bar Processing`** (1 nodes): `TickBatchResponsePayload.java`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `API Orchestration`** (1 nodes): `ApiAckResponse.java`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 65`** (1 nodes): `FeedStatusSymbolPayload.java`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Tick Bar Processing`** (1 nodes): `TickBatchRequestPayload.java`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Tick Bar Processing`** (1 nodes): `IncomingTickPayload.java`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 68`** (1 nodes): `FeedStatusResponsePayload.java`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 69`** (1 nodes): `TradeUpdateRequestPayload.java`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 70`** (1 nodes): `SymbolReadinessState.java`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 71`** (1 nodes): `LiveReadinessSnapshot.java`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Prediction Pipeline`** (1 nodes): `PredictionDecision.java`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `BarrierAction` connect `Barrier Management` to `Reservation Lifecycle`, `Tick Bar Processing`?**
  _High betweenness centrality (0.075) - this node is a cross-community bridge._
- **Why does `ModelFeatures` connect `Tick Bar Processing` to `Feature Computation`, `Reservation Lifecycle`, `Barrier Management`?**
  _High betweenness centrality (0.059) - this node is a cross-community bridge._
- **Why does `StateManager` connect `Reservation Lifecycle` to `Tick Bar Processing`, `Barrier Management`?**
  _High betweenness centrality (0.051) - this node is a cross-community bridge._
- **Are the 224 inferred relationships involving `ModelFeatures` (e.g. with `FeatureComputationEngine` and `Feature computation engine: owns strategy, validation, and computation.  Extract`) actually correct?**
  _`ModelFeatures` has 224 INFERRED edges - model-reasoned connections that need verification._
- **Are the 152 inferred relationships involving `IncomingTick` (e.g. with `BarAlignmentResult` and `BarBoundaryContract`) actually correct?**
  _`IncomingTick` has 152 INFERRED edges - model-reasoned connections that need verification._
- **Are the 152 inferred relationships involving `IncomingTickBar` (e.g. with `BarAlignmentResult` and `BarBoundaryContract`) actually correct?**
  _`IncomingTickBar` has 152 INFERRED edges - model-reasoned connections that need verification._
- **Are the 89 inferred relationships involving `StateManager` (e.g. with `DuckDBStateStore` and `WarmupBoundaryVerifier`) actually correct?**
  _`StateManager` has 89 INFERRED edges - model-reasoned connections that need verification._