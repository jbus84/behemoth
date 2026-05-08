# Graph Report - src  (2026-05-08)

## Corpus Check
- 0 files · ~0 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 1591 nodes · 6738 edges · 65 communities detected
- Extraction: 32% EXTRACTED · 68% INFERRED · 0% AMBIGUOUS · INFERRED: 4604 edges (avg confidence: 0.57)
- Token cost: 0 input · 0 output

## Community Hubs (Navigation)
- [[_COMMUNITY_Community 0|Community 0]]
- [[_COMMUNITY_Community 1|Community 1]]
- [[_COMMUNITY_Community 2|Community 2]]
- [[_COMMUNITY_Community 3|Community 3]]
- [[_COMMUNITY_Community 4|Community 4]]
- [[_COMMUNITY_Community 5|Community 5]]
- [[_COMMUNITY_Community 6|Community 6]]
- [[_COMMUNITY_Community 7|Community 7]]
- [[_COMMUNITY_Community 8|Community 8]]
- [[_COMMUNITY_Community 9|Community 9]]
- [[_COMMUNITY_Community 10|Community 10]]
- [[_COMMUNITY_Community 11|Community 11]]
- [[_COMMUNITY_Community 12|Community 12]]
- [[_COMMUNITY_Community 13|Community 13]]
- [[_COMMUNITY_Community 14|Community 14]]
- [[_COMMUNITY_Community 15|Community 15]]
- [[_COMMUNITY_Community 16|Community 16]]
- [[_COMMUNITY_Community 17|Community 17]]
- [[_COMMUNITY_Community 18|Community 18]]
- [[_COMMUNITY_Community 19|Community 19]]
- [[_COMMUNITY_Community 20|Community 20]]
- [[_COMMUNITY_Community 21|Community 21]]
- [[_COMMUNITY_Community 22|Community 22]]
- [[_COMMUNITY_Community 23|Community 23]]
- [[_COMMUNITY_Community 24|Community 24]]
- [[_COMMUNITY_Community 25|Community 25]]
- [[_COMMUNITY_Community 26|Community 26]]
- [[_COMMUNITY_Community 27|Community 27]]
- [[_COMMUNITY_Community 28|Community 28]]
- [[_COMMUNITY_Community 29|Community 29]]
- [[_COMMUNITY_Community 30|Community 30]]
- [[_COMMUNITY_Community 31|Community 31]]
- [[_COMMUNITY_Community 32|Community 32]]
- [[_COMMUNITY_Community 33|Community 33]]
- [[_COMMUNITY_Community 34|Community 34]]
- [[_COMMUNITY_Community 35|Community 35]]
- [[_COMMUNITY_Community 36|Community 36]]
- [[_COMMUNITY_Community 37|Community 37]]
- [[_COMMUNITY_Community 38|Community 38]]
- [[_COMMUNITY_Community 39|Community 39]]
- [[_COMMUNITY_Community 40|Community 40]]
- [[_COMMUNITY_Community 41|Community 41]]
- [[_COMMUNITY_Community 42|Community 42]]
- [[_COMMUNITY_Community 43|Community 43]]
- [[_COMMUNITY_Community 44|Community 44]]
- [[_COMMUNITY_Community 45|Community 45]]
- [[_COMMUNITY_Community 46|Community 46]]
- [[_COMMUNITY_Community 47|Community 47]]
- [[_COMMUNITY_Community 48|Community 48]]
- [[_COMMUNITY_Community 49|Community 49]]
- [[_COMMUNITY_Community 50|Community 50]]
- [[_COMMUNITY_Community 51|Community 51]]
- [[_COMMUNITY_Community 52|Community 52]]
- [[_COMMUNITY_Community 53|Community 53]]
- [[_COMMUNITY_Community 54|Community 54]]
- [[_COMMUNITY_Community 55|Community 55]]
- [[_COMMUNITY_Community 56|Community 56]]
- [[_COMMUNITY_Community 57|Community 57]]
- [[_COMMUNITY_Community 58|Community 58]]
- [[_COMMUNITY_Community 59|Community 59]]
- [[_COMMUNITY_Community 60|Community 60]]
- [[_COMMUNITY_Community 61|Community 61]]
- [[_COMMUNITY_Community 62|Community 62]]
- [[_COMMUNITY_Community 63|Community 63]]
- [[_COMMUNITY_Community 64|Community 64]]

## God Nodes (most connected - your core abstractions)
1. `ModelFeatures` - 277 edges
2. `IncomingTick` - 258 edges
3. `IncomingTickBar` - 258 edges
4. `StateManager` - 193 edges
5. `BarContext` - 166 edges
6. `BarrierAction` - 162 edges
7. `HistoricalCandidateRegistry` - 145 edges
8. `BarrierManager` - 138 edges
9. `FeatureConfig` - 135 edges
10. `HistoricalPredictionStage` - 134 edges

## Surprising Connections (you probably didn't know these)
- `Unified interface for candidate resolution across live and historical governance` --uses--> `HistoricalCandidateRegistry`  [INFERRED]
  src/behemoth/core/unified_candidate_registry.py → src/behemoth/core/historical_registry.py
- `Mode-aware adapter providing a single interface for both governance paths.` --uses--> `HistoricalCandidateRegistry`  [INFERRED]
  src/behemoth/core/unified_candidate_registry.py → src/behemoth/core/historical_registry.py
- `Initialize with both registries and mode flag.          Args:             live_r` --uses--> `HistoricalCandidateRegistry`  [INFERRED]
  src/behemoth/core/unified_candidate_registry.py → src/behemoth/core/historical_registry.py
- `Resolve candidates for a symbol in the current governance mode.` --uses--> `HistoricalCandidateRegistry`  [INFERRED]
  src/behemoth/core/unified_candidate_registry.py → src/behemoth/core/historical_registry.py
- `Resolve cap_pips for a symbol in the current governance mode.` --uses--> `HistoricalCandidateRegistry`  [INFERRED]
  src/behemoth/core/unified_candidate_registry.py → src/behemoth/core/historical_registry.py

## Communities

### Community 0 - "Community 0"
Cohesion: 0.02
Nodes (207): Reset all cached state. Called on startup and reload., Atomically reset all managed caches in registration order.          Each cache.c, check(), Seed check: entry_blocked_not_ready events must correlate with non-READY readine, check(), Seed check: every symbol with bar events must have at least one predict cycle., check(), Seed check: client_tick_seq is strictly monotonic per symbol within a session. (+199 more)

### Community 1 - "Community 1"
Cohesion: 0.04
Nodes (168): Validates account-risk reservation lifecycle transitions., ReservationState, ReservationStateMachine, BarAlignmentResult, BarAlignmentService, BarBoundaryContract, _build_bar(), _compute_microstructure() (+160 more)

### Community 2 - "Community 2"
Cohesion: 0.02
Nodes (25): isCloseMarket(), isOpenMarket(), BehemothStrategyCore, closePositionByScanId(), entriesAllowed(), submitMarketOrder(), SymbolRuntimeState, JForexMetrics (+17 more)

### Community 3 - "Community 3"
Cohesion: 0.14
Nodes (165): AccountRiskProfile, BarrierManager, BaseModel, CacheManager, Manages atomic reset of all inference-time caches.      Ensures that cache reset, CandidateCatalog, CatalogContext, Encapsulates catalog dependencies to reduce closure-based coupling.      Instead (+157 more)

### Community 4 - "Community 4"
Cohesion: 0.03
Nodes (21): BehemothJForexStrategy, BrokerBridgeLoader, BrokerBridgeLoaderTest, FakeBrokerHistoryPort, MutableClock, BrokerOrderSnapshotWriter, JForexBrokerHistoryPort, BridgeRuntime (+13 more)

### Community 5 - "Community 5"
Cohesion: 0.04
Nodes (24): BarAlignmentService, BarAlignmentServiceTest, BehemothStrategyCoreTest, HistoricalWarmupLoader, HistoricalWarmupLoaderTest, fromEnvironment(), requiredSetting(), setting() (+16 more)

### Community 6 - "Community 6"
Cohesion: 0.04
Nodes (64): AccountRiskAllocator, AccountRiskBuffers, AccountRiskCostGate, EntryGateDecision, evaluate_account_risk_limits(), evaluate_trade_guard(), evaluate_trade_risk_guard(), load_account_risk_profile() (+56 more)

### Community 7 - "Community 7"
Cohesion: 0.05
Nodes (24): _month_from_close_ts(), _normalize_model_month(), _normalize_symbol(), Unified Candidate State sourcing across live and historical governance modes., Resolved Candidate State and model artifact contract for one symbol/month., RuntimeCandidateContract, HistoricalLockEntry, Historical governance lock registry for month-aligned backtest inference.  Loads (+16 more)

### Community 8 - "Community 8"
Cohesion: 0.06
Nodes (38): BarrierEvaluationResult, BarrierStateMutation, _open_market_action(), Bar-level barrier manager for completed-bar OCO touch confirmation.  Produces id, Register a new barrier scan. Called when selected_exec=1 passes all gates., Register a new barrier scan. Called when selected_exec=1 passes all gates., Expire active scans that predate the side-aware signal close columns.          L, Expire active scans that predate the side-aware signal close columns.          L (+30 more)

### Community 9 - "Community 9"
Cohesion: 0.06
Nodes (27): _build_model_features(), _compute_cost_features(), compute_feature_matrix_from_bars(), compute_features_from_bars(), _compute_micro_features(), compute_regime_quantiles_from_bars(), _compute_structural_features(), _compute_velocity_features() (+19 more)

### Community 10 - "Community 10"
Cohesion: 0.06
Nodes (13): isConnected(), JForexBrokerSnapshotRunner, startStrategy(), connect(), isConnected(), JForexLiveRunner, LiveClient, Sleeper (+5 more)

### Community 11 - "Community 11"
Cohesion: 0.13
Nodes (4): ExecutionStateStore, ExecutionStateStoreTest, OcoGroupState, OcoLegState

### Community 12 - "Community 12"
Cohesion: 0.11
Nodes (4): NoopExecutionPort, RecordingExecutionPort, ExecutionPort, toMarketOrderRequest()

### Community 13 - "Community 13"
Cohesion: 0.29
Nodes (2): JForexExecutionPort, Task

### Community 14 - "Community 14"
Cohesion: 0.22
Nodes (1): BrokerSnapshotStrategy

### Community 15 - "Community 15"
Cohesion: 0.38
Nodes (1): ParquetTickLoader

### Community 16 - "Community 16"
Cohesion: 0.29
Nodes (1): LiveReadinessMetrics

### Community 17 - "Community 17"
Cohesion: 0.5
Nodes (3): dashboard(), Lightweight monitoring dashboard for the Behemoth OCO strategy.  Served as a Fas, Serve the single-page monitoring dashboard.

### Community 18 - "Community 18"
Cohesion: 0.5
Nodes (1): BrokerHistoryPort

### Community 19 - "Community 19"
Cohesion: 0.5
Nodes (3): Unified cache lifecycle management for runtime modules.  Coordinates atomic rese, Protocol for inference-time caches that need coordinated reset.      Implementat, RuntimeCache

### Community 20 - "Community 20"
Cohesion: 1.0
Nodes (1): Reset all caches. Called on startup.

### Community 21 - "Community 21"
Cohesion: 1.0
Nodes (0): 

### Community 22 - "Community 22"
Cohesion: 1.0
Nodes (0): 

### Community 23 - "Community 23"
Cohesion: 1.0
Nodes (1): Reset both ordinal and payload cursors to 0 for a candidate.          Ensures at

### Community 24 - "Community 24"
Cohesion: 1.0
Nodes (1): Initialize manager with caches in reset order.          Args:             caches

### Community 25 - "Community 25"
Cohesion: 1.0
Nodes (0): 

### Community 26 - "Community 26"
Cohesion: 1.0
Nodes (1): Build from a state_universe row in the live lock JSON.

### Community 27 - "Community 27"
Cohesion: 1.0
Nodes (1): Load exactly from per-symbol *_oco_live_lock.json files.

### Community 28 - "Community 28"
Cohesion: 1.0
Nodes (1): Symbols that have at least one registered candidate.

### Community 29 - "Community 29"
Cohesion: 1.0
Nodes (0): 

### Community 30 - "Community 30"
Cohesion: 1.0
Nodes (1): Convert to UTC datetime.

### Community 31 - "Community 31"
Cohesion: 1.0
Nodes (1): Compute SHA256 hash of file.

### Community 32 - "Community 32"
Cohesion: 1.0
Nodes (1): Generate cache key: symbol or symbol|month.

### Community 33 - "Community 33"
Cohesion: 1.0
Nodes (0): 

### Community 34 - "Community 34"
Cohesion: 1.0
Nodes (0): 

### Community 35 - "Community 35"
Cohesion: 1.0
Nodes (0): 

### Community 36 - "Community 36"
Cohesion: 1.0
Nodes (0): 

### Community 37 - "Community 37"
Cohesion: 1.0
Nodes (0): 

### Community 38 - "Community 38"
Cohesion: 1.0
Nodes (0): 

### Community 39 - "Community 39"
Cohesion: 1.0
Nodes (0): 

### Community 40 - "Community 40"
Cohesion: 1.0
Nodes (0): 

### Community 41 - "Community 41"
Cohesion: 1.0
Nodes (0): 

### Community 42 - "Community 42"
Cohesion: 1.0
Nodes (0): 

### Community 43 - "Community 43"
Cohesion: 1.0
Nodes (0): 

### Community 44 - "Community 44"
Cohesion: 1.0
Nodes (0): 

### Community 45 - "Community 45"
Cohesion: 1.0
Nodes (0): 

### Community 46 - "Community 46"
Cohesion: 1.0
Nodes (0): 

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

### Community 53 - "Community 53"
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

### Community 58 - "Community 58"
Cohesion: 1.0
Nodes (0): 

### Community 59 - "Community 59"
Cohesion: 1.0
Nodes (0): 

### Community 60 - "Community 60"
Cohesion: 1.0
Nodes (0): 

### Community 61 - "Community 61"
Cohesion: 1.0
Nodes (0): 

### Community 62 - "Community 62"
Cohesion: 1.0
Nodes (1): Convert to UTC datetime.

### Community 63 - "Community 63"
Cohesion: 1.0
Nodes (1): Compute SHA256 hash of file.

### Community 64 - "Community 64"
Cohesion: 1.0
Nodes (1): Generate cache key: symbol or symbol|month.

## Knowledge Gaps
- **103 isolated node(s):** `A single prediction candidate to evaluate.`, `Build from a state_universe row in the live lock JSON.`, `Registry of valid candidate specifications loaded from live lock JSONs.`, `Load exactly from per-symbol *_oco_live_lock.json files.`, `Symbols that have at least one registered candidate.` (+98 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **Thin community `Community 20`** (2 nodes): `.clear()`, `Reset all caches. Called on startup.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 21`** (2 nodes): `normalizeSymbol()`, `RuntimeInstrument.java`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 22`** (2 nodes): `SymbolReadinessSnapshot.java`, `normalizeSymbol()`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 23`** (2 nodes): `.reset_cursors()`, `Reset both ordinal and payload cursors to 0 for a candidate.          Ensures at`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 24`** (2 nodes): `.__init__()`, `Initialize manager with caches in reset order.          Args:             caches`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 25`** (1 nodes): `__init__.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 26`** (1 nodes): `Build from a state_universe row in the live lock JSON.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 27`** (1 nodes): `Load exactly from per-symbol *_oco_live_lock.json files.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 28`** (1 nodes): `Symbols that have at least one registered candidate.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 29`** (1 nodes): `__init__.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 30`** (1 nodes): `Convert to UTC datetime.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 31`** (1 nodes): `Compute SHA256 hash of file.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 32`** (1 nodes): `Generate cache key: symbol or symbol|month.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 33`** (1 nodes): `__init__.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 34`** (1 nodes): `__init__.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 35`** (1 nodes): `__init__.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 36`** (1 nodes): `build.gradle.kts`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 37`** (1 nodes): `MarketOrderRequest.java`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 38`** (1 nodes): `OrderEvent.java`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 39`** (1 nodes): `OrderHandle.java`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 40`** (1 nodes): `OrderResult.java`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 41`** (1 nodes): `OrderEventType.java`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 42`** (1 nodes): `RuntimeTick.java`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 43`** (1 nodes): `OrderRequest.java`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 44`** (1 nodes): `TradeOpenRequestPayload.java`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 45`** (1 nodes): `BackfillRequestPayload.java`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 46`** (1 nodes): `ActiveTradePayload.java`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 47`** (1 nodes): `PredictRequestPayload.java`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 48`** (1 nodes): `AccountSnapshotRequestPayload.java`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 49`** (1 nodes): `PredictResponsePayload.java`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 50`** (1 nodes): `TradeTouchRequestPayload.java`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 51`** (1 nodes): `TickIngestResponsePayload.java`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 52`** (1 nodes): `TickBatchResponsePayload.java`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 53`** (1 nodes): `ApiAckResponse.java`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 54`** (1 nodes): `FeedStatusSymbolPayload.java`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 55`** (1 nodes): `TickBatchRequestPayload.java`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 56`** (1 nodes): `IncomingTickPayload.java`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 57`** (1 nodes): `FeedStatusResponsePayload.java`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 58`** (1 nodes): `TradeUpdateRequestPayload.java`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 59`** (1 nodes): `SymbolReadinessState.java`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 60`** (1 nodes): `LiveReadinessSnapshot.java`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 61`** (1 nodes): `PredictionDecision.java`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 62`** (1 nodes): `Convert to UTC datetime.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 63`** (1 nodes): `Compute SHA256 hash of file.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 64`** (1 nodes): `Generate cache key: symbol or symbol|month.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `BarrierAction` connect `Community 3` to `Community 0`, `Community 8`?**
  _High betweenness centrality (0.091) - this node is a cross-community bridge._
- **Why does `ModelFeatures` connect `Community 1` to `Community 0`, `Community 9`, `Community 3`?**
  _High betweenness centrality (0.073) - this node is a cross-community bridge._
- **Why does `seed_audit_history()` connect `Community 0` to `Community 1`, `Community 3`, `Community 9`?**
  _High betweenness centrality (0.047) - this node is a cross-community bridge._
- **Are the 272 inferred relationships involving `ModelFeatures` (e.g. with `FeatureDefinition` and `FeatureSchema`) actually correct?**
  _`ModelFeatures` has 272 INFERRED edges - model-reasoned connections that need verification._
- **Are the 255 inferred relationships involving `IncomingTick` (e.g. with `BarAlignmentResult` and `BarBoundaryContract`) actually correct?**
  _`IncomingTick` has 255 INFERRED edges - model-reasoned connections that need verification._
- **Are the 255 inferred relationships involving `IncomingTickBar` (e.g. with `BarAlignmentResult` and `BarBoundaryContract`) actually correct?**
  _`IncomingTickBar` has 255 INFERRED edges - model-reasoned connections that need verification._
- **Are the 129 inferred relationships involving `StateManager` (e.g. with `FeatureConfig` and `IncomingTick`) actually correct?**
  _`StateManager` has 129 INFERRED edges - model-reasoned connections that need verification._