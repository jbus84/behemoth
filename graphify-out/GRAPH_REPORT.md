# Graph Report - .  (2026-05-06)

## Corpus Check
- 116 files · ~0 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 1166 nodes · 3965 edges · 61 communities detected
- Extraction: 41% EXTRACTED · 59% INFERRED · 0% AMBIGUOUS · INFERRED: 2322 edges (avg confidence: 0.59)
- Token cost: 0 input · 0 output

## Community Hubs (Navigation)
- [[_COMMUNITY_Risk and Barrier Management|Risk and Barrier Management]]
- [[_COMMUNITY_Scan Reservation and Holding|Scan Reservation and Holding]]
- [[_COMMUNITY_JForex Strategy Bridge|JForex Strategy Bridge]]
- [[_COMMUNITY_Strategy Core and Metrics|Strategy Core and Metrics]]
- [[_COMMUNITY_Local Test Runner|Local Test Runner]]
- [[_COMMUNITY_Barrier Scan Registration|Barrier Scan Registration]]
- [[_COMMUNITY_Seed Checks and Gates|Seed Checks and Gates]]
- [[_COMMUNITY_Broker Snapshot Runner|Broker Snapshot Runner]]
- [[_COMMUNITY_Execution State Store|Execution State Store]]
- [[_COMMUNITY_Feature Computation|Feature Computation]]
- [[_COMMUNITY_Python Prediction Client|Python Prediction Client]]
- [[_COMMUNITY_Historical Warmup Loader|Historical Warmup Loader]]
- [[_COMMUNITY_Account Risk Allocator|Account Risk Allocator]]
- [[_COMMUNITY_Execution Ports|Execution Ports]]
- [[_COMMUNITY_Broker Snapshot Strategy|Broker Snapshot Strategy]]
- [[_COMMUNITY_ParquetTickLoader|ParquetTickLoader]]
- [[_COMMUNITY_JForexExecutionPort|JForexExecutionPort]]
- [[_COMMUNITY_LiveReadinessMetrics|LiveReadinessMetrics]]
- [[_COMMUNITY_ExecutionPort|ExecutionPort]]
- [[_COMMUNITY_Community 19|Community 19]]
- [[_COMMUNITY_BrokerOrderSnapshotWriter|BrokerOrderSnapshotWriter]]
- [[_COMMUNITY_Evaluate Call|Evaluate Call]]
- [[_COMMUNITY_Lightweight Behemoth|Lightweight Behemoth]]
- [[_COMMUNITY_BrokerHistoryPort|BrokerHistoryPort]]
- [[_COMMUNITY_Bar-level Produces|Bar-level Produces]]
- [[_COMMUNITY_Retrieve Used|Retrieve Used]]
- [[_COMMUNITY_RuntimeInstrument|RuntimeInstrument]]
- [[_COMMUNITY_SymbolReadinessSnapshot|SymbolReadinessSnapshot]]
- [[_COMMUNITY_Community 28|Community 28]]
- [[_COMMUNITY_Build JSON|Build JSON]]
- [[_COMMUNITY_Load|Load]]
- [[_COMMUNITY_Symbols|Symbols]]
- [[_COMMUNITY_Community 32|Community 32]]
- [[_COMMUNITY_Community 33|Community 33]]
- [[_COMMUNITY_Community 34|Community 34]]
- [[_COMMUNITY_Community 35|Community 35]]
- [[_COMMUNITY_Community 36|Community 36]]
- [[_COMMUNITY_MarketOrderRequest|MarketOrderRequest]]
- [[_COMMUNITY_OrderEvent|OrderEvent]]
- [[_COMMUNITY_OrderHandle|OrderHandle]]
- [[_COMMUNITY_OrderEventType|OrderEventType]]
- [[_COMMUNITY_RuntimeTick|RuntimeTick]]
- [[_COMMUNITY_OrderRequest|OrderRequest]]
- [[_COMMUNITY_TradeOpenRequestPayload|TradeOpenRequestPayload]]
- [[_COMMUNITY_BackfillRequestPayload|BackfillRequestPayload]]
- [[_COMMUNITY_ActiveTradePayload|ActiveTradePayload]]
- [[_COMMUNITY_PredictRequestPayload|PredictRequestPayload]]
- [[_COMMUNITY_AccountSnapshotRequestPayload|AccountSnapshotRequestPayload]]
- [[_COMMUNITY_PredictResponsePayload|PredictResponsePayload]]
- [[_COMMUNITY_TradeTouchRequestPayload|TradeTouchRequestPayload]]
- [[_COMMUNITY_TickIngestResponsePayload|TickIngestResponsePayload]]
- [[_COMMUNITY_TickBatchResponsePayload|TickBatchResponsePayload]]
- [[_COMMUNITY_ApiAckResponse|ApiAckResponse]]
- [[_COMMUNITY_FeedStatusSymbolPayload|FeedStatusSymbolPayload]]
- [[_COMMUNITY_TickBatchRequestPayload|TickBatchRequestPayload]]
- [[_COMMUNITY_IncomingTickPayload|IncomingTickPayload]]
- [[_COMMUNITY_FeedStatusResponsePayload|FeedStatusResponsePayload]]
- [[_COMMUNITY_TradeUpdateRequestPayload|TradeUpdateRequestPayload]]
- [[_COMMUNITY_SymbolReadinessState|SymbolReadinessState]]
- [[_COMMUNITY_LiveReadinessSnapshot|LiveReadinessSnapshot]]
- [[_COMMUNITY_PredictionDecision|PredictionDecision]]

## God Nodes (most connected - your core abstractions)
1. `ModelFeatures` - 145 edges
2. `IncomingTick` - 137 edges
3. `IncomingTickBar` - 137 edges
4. `StateManager` - 132 edges
5. `FeatureConfig` - 130 edges
6. `BarrierManager` - 82 edges
7. `HistoricalCandidateRegistry` - 78 edges
8. `TickAggregator` - 78 edges
9. `CandidateRegistry` - 74 edges
10. `OcoPrediction` - 72 edges

## Surprising Connections (you probably didn't know these)
- `Canonical feature builder for the OCO CatBoost model.  This is the SINGLE SOURCE` --uses--> `ModelFeatures`  [INFERRED]
  src/behemoth/core/features.py → src/behemoth/core/schemas.py
- `Hardcoded physical constants and thresholds for feature computation.` --uses--> `ModelFeatures`  [INFERRED]
  src/behemoth/core/features.py → src/behemoth/core/schemas.py
- `Return the pip unit for a given FX symbol.` --uses--> `ModelFeatures`  [INFERRED]
  src/behemoth/core/features.py → src/behemoth/core/schemas.py
- `Compute the 16-feature vector from a DataFrame of tick bars.      Returns the fe` --uses--> `ModelFeatures`  [INFERRED]
  src/behemoth/core/features.py → src/behemoth/core/schemas.py
- `Compute the 16-feature matrix for all bars in the DataFrame.      Returns a Data` --uses--> `ModelFeatures`  [INFERRED]
  src/behemoth/core/features.py → src/behemoth/core/schemas.py

## Communities

### Community 0 - "Risk and Barrier Management"
Cohesion: 0.09
Nodes (161): AccountRiskProfile, BarrierManager, Manages pending barrier scans and active positions.      State lifecycle: SCANNI, BaseModel, FeatureConfig, Immutable configuration governing rolling window sizes.      Matches the default, Number of bars needed for full-precision feature computation., HistoricalCandidateRegistry (+153 more)

### Community 1 - "Scan Reservation and Holding"
Cohesion: 0.03
Nodes (116): Expire active scans that predate the side-aware signal close columns.          L, Check if candidate has an active (SCANNING or HOLDING) scan., Record the broker position ID after a fill is confirmed., Find HOLDING scans for a candidate (to link broker_pos_id)., Return the active (SCANNING/HOLDING) scan for a reservation, or None if not foun, _check(), failed_checks(), HistoricalGovernanceCheck (+108 more)

### Community 2 - "JForex Strategy Bridge"
Cohesion: 0.03
Nodes (20): BehemothJForexStrategy, BrokerBridgeLoader, BrokerBridgeLoaderTest, FakeBrokerHistoryPort, MutableClock, JForexBrokerHistoryPort, BridgeRuntime, BridgeRuntimeFactory (+12 more)

### Community 3 - "Strategy Core and Metrics"
Cohesion: 0.03
Nodes (18): isCloseMarket(), isOpenMarket(), BehemothStrategyCore, closePositionByScanId(), entriesAllowed(), submitMarketOrder(), SymbolRuntimeState, JForexMetrics (+10 more)

### Community 4 - "Local Test Runner"
Cohesion: 0.05
Nodes (19): BehemothStrategyCoreTest, JForexConnectionTest, fromEnvironment(), requiredSetting(), setting(), LocalExecutionPort, SimulatedOrder, LocalExecutionPortTest (+11 more)

### Community 5 - "Barrier Scan Registration"
Cohesion: 0.05
Nodes (61): Register a new barrier scan. Called when selected_exec=1 passes all gates., Enum, _as_posix(), build_stage_graph(), _graphify_links(), _graphify_nodes_by_id(), GraphScopeError, _is_allowed() (+53 more)

### Community 6 - "Seed Checks and Gates"
Cohesion: 0.05
Nodes (39): check(), Seed check: entry_blocked_not_ready events must correlate with non-READY readine, check(), Seed check: every symbol with bar events must have at least one predict cycle., check(), Seed check: client_tick_seq is strictly monotonic per symbol within a session., check(), Seed check: every predict failure is either warmup-skip or classified critically (+31 more)

### Community 7 - "Broker Snapshot Runner"
Cohesion: 0.06
Nodes (13): isConnected(), JForexBrokerSnapshotRunner, startStrategy(), connect(), isConnected(), JForexLiveRunner, LiveClient, Sleeper (+5 more)

### Community 8 - "Execution State Store"
Cohesion: 0.1
Nodes (10): ExecutionStateStore, OcoGroupState, OcoLegState, _build_bar(), _compute_microstructure(), _compute_price_stats(), Real-time tick-to-bar aggregator.  Converts raw ``IncomingTick`` objects into ``, Compute the microstructural sequence makers for a bar. (+2 more)

### Community 9 - "Feature Computation"
Cohesion: 0.11
Nodes (20): _build_model_features(), _compute_cost_features(), compute_feature_matrix_from_bars(), compute_features_from_bars(), _compute_micro_features(), compute_regime_quantiles_from_bars(), _compute_structural_features(), _compute_velocity_features() (+12 more)

### Community 10 - "Python Prediction Client"
Cohesion: 0.14
Nodes (2): PythonPredictionClient, PythonPredictionClientTest

### Community 11 - "Historical Warmup Loader"
Cohesion: 0.15
Nodes (4): HistoricalWarmupLoader, HistoricalWarmupLoaderTest, ParquetTickLoaderPhaseAlignmentTest, ParquetTickLoaderTimezoneTest

### Community 12 - "Account Risk Allocator"
Cohesion: 0.18
Nodes (12): AccountRiskAllocator, AccountRiskBuffers, AccountRiskCostGate, evaluate_account_risk_limits(), evaluate_trade_guard(), evaluate_trade_risk_guard(), load_account_risk_profile(), _normalize_trade_cost_gate_mode() (+4 more)

### Community 13 - "Execution Ports"
Cohesion: 0.18
Nodes (2): NoopExecutionPort, RecordingExecutionPort

### Community 14 - "Broker Snapshot Strategy"
Cohesion: 0.22
Nodes (1): BrokerSnapshotStrategy

### Community 15 - "ParquetTickLoader"
Cohesion: 0.38
Nodes (1): ParquetTickLoader

### Community 16 - "JForexExecutionPort"
Cohesion: 0.39
Nodes (1): JForexExecutionPort

### Community 17 - "LiveReadinessMetrics"
Cohesion: 0.29
Nodes (1): LiveReadinessMetrics

### Community 18 - "ExecutionPort"
Cohesion: 0.33
Nodes (1): ExecutionPort

### Community 19 - "Community 19"
Cohesion: 0.6
Nodes (0): 

### Community 20 - "BrokerOrderSnapshotWriter"
Cohesion: 0.5
Nodes (1): BrokerOrderSnapshotWriter

### Community 21 - "Evaluate Call"
Cohesion: 0.5
Nodes (2): Evaluate a completed bar against all active scans for this symbol.          Call, Move a scan from SCANNING to HOLDING.

### Community 22 - "Lightweight Behemoth"
Cohesion: 0.5
Nodes (3): dashboard(), Lightweight monitoring dashboard for the Behemoth OCO strategy.  Served as a Fas, Serve the single-page monitoring dashboard.

### Community 23 - "BrokerHistoryPort"
Cohesion: 0.5
Nodes (1): BrokerHistoryPort

### Community 24 - "Bar-level Produces"
Cohesion: 1.0
Nodes (1): Bar-level barrier manager for completed-bar OCO touch confirmation.  Produces id

### Community 25 - "Retrieve Used"
Cohesion: 1.0
Nodes (1): Retrieve a scan record by ID. Used for testing and diagnostics.

### Community 26 - "RuntimeInstrument"
Cohesion: 1.0
Nodes (0): 

### Community 27 - "SymbolReadinessSnapshot"
Cohesion: 1.0
Nodes (0): 

### Community 28 - "Community 28"
Cohesion: 1.0
Nodes (0): 

### Community 29 - "Build JSON"
Cohesion: 1.0
Nodes (1): Build from a state_universe row in the live lock JSON.

### Community 30 - "Load"
Cohesion: 1.0
Nodes (1): Load exactly from per-symbol *_oco_live_lock.json files.

### Community 31 - "Symbols"
Cohesion: 1.0
Nodes (1): Symbols that have at least one registered candidate.

### Community 32 - "Community 32"
Cohesion: 1.0
Nodes (0): 

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

### Community 37 - "MarketOrderRequest"
Cohesion: 1.0
Nodes (0): 

### Community 38 - "OrderEvent"
Cohesion: 1.0
Nodes (0): 

### Community 39 - "OrderHandle"
Cohesion: 1.0
Nodes (0): 

### Community 40 - "OrderEventType"
Cohesion: 1.0
Nodes (0): 

### Community 41 - "RuntimeTick"
Cohesion: 1.0
Nodes (0): 

### Community 42 - "OrderRequest"
Cohesion: 1.0
Nodes (0): 

### Community 43 - "TradeOpenRequestPayload"
Cohesion: 1.0
Nodes (0): 

### Community 44 - "BackfillRequestPayload"
Cohesion: 1.0
Nodes (0): 

### Community 45 - "ActiveTradePayload"
Cohesion: 1.0
Nodes (0): 

### Community 46 - "PredictRequestPayload"
Cohesion: 1.0
Nodes (0): 

### Community 47 - "AccountSnapshotRequestPayload"
Cohesion: 1.0
Nodes (0): 

### Community 48 - "PredictResponsePayload"
Cohesion: 1.0
Nodes (0): 

### Community 49 - "TradeTouchRequestPayload"
Cohesion: 1.0
Nodes (0): 

### Community 50 - "TickIngestResponsePayload"
Cohesion: 1.0
Nodes (0): 

### Community 51 - "TickBatchResponsePayload"
Cohesion: 1.0
Nodes (0): 

### Community 52 - "ApiAckResponse"
Cohesion: 1.0
Nodes (0): 

### Community 53 - "FeedStatusSymbolPayload"
Cohesion: 1.0
Nodes (0): 

### Community 54 - "TickBatchRequestPayload"
Cohesion: 1.0
Nodes (0): 

### Community 55 - "IncomingTickPayload"
Cohesion: 1.0
Nodes (0): 

### Community 56 - "FeedStatusResponsePayload"
Cohesion: 1.0
Nodes (0): 

### Community 57 - "TradeUpdateRequestPayload"
Cohesion: 1.0
Nodes (0): 

### Community 58 - "SymbolReadinessState"
Cohesion: 1.0
Nodes (0): 

### Community 59 - "LiveReadinessSnapshot"
Cohesion: 1.0
Nodes (0): 

### Community 60 - "PredictionDecision"
Cohesion: 1.0
Nodes (0): 

## Knowledge Gaps
- **40 isolated node(s):** `Validation helpers for month-scoped historical governance locks.`, `A single prediction candidate to evaluate.`, `Build from a state_universe row in the live lock JSON.`, `Registry of valid candidate specifications loaded from live lock JSONs.`, `Load exactly from per-symbol *_oco_live_lock.json files.` (+35 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **Thin community `Bar-level Produces`** (2 nodes): `Bar-level barrier manager for completed-bar OCO touch confirmation.  Produces id`, `barrier_manager.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Retrieve Used`** (2 nodes): `.get_scan()`, `Retrieve a scan record by ID. Used for testing and diagnostics.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `RuntimeInstrument`** (2 nodes): `normalizeSymbol()`, `RuntimeInstrument.java`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `SymbolReadinessSnapshot`** (2 nodes): `SymbolReadinessSnapshot.java`, `normalizeSymbol()`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 28`** (1 nodes): `__init__.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Build JSON`** (1 nodes): `Build from a state_universe row in the live lock JSON.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Load`** (1 nodes): `Load exactly from per-symbol *_oco_live_lock.json files.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Symbols`** (1 nodes): `Symbols that have at least one registered candidate.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 32`** (1 nodes): `__init__.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 33`** (1 nodes): `__init__.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 34`** (1 nodes): `__init__.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 35`** (1 nodes): `__init__.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 36`** (1 nodes): `build.gradle.kts`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `MarketOrderRequest`** (1 nodes): `MarketOrderRequest.java`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `OrderEvent`** (1 nodes): `OrderEvent.java`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `OrderHandle`** (1 nodes): `OrderHandle.java`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `OrderEventType`** (1 nodes): `OrderEventType.java`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `RuntimeTick`** (1 nodes): `RuntimeTick.java`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `OrderRequest`** (1 nodes): `OrderRequest.java`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `TradeOpenRequestPayload`** (1 nodes): `TradeOpenRequestPayload.java`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `BackfillRequestPayload`** (1 nodes): `BackfillRequestPayload.java`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `ActiveTradePayload`** (1 nodes): `ActiveTradePayload.java`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `PredictRequestPayload`** (1 nodes): `PredictRequestPayload.java`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `AccountSnapshotRequestPayload`** (1 nodes): `AccountSnapshotRequestPayload.java`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `PredictResponsePayload`** (1 nodes): `PredictResponsePayload.java`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `TradeTouchRequestPayload`** (1 nodes): `TradeTouchRequestPayload.java`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `TickIngestResponsePayload`** (1 nodes): `TickIngestResponsePayload.java`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `TickBatchResponsePayload`** (1 nodes): `TickBatchResponsePayload.java`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `ApiAckResponse`** (1 nodes): `ApiAckResponse.java`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `FeedStatusSymbolPayload`** (1 nodes): `FeedStatusSymbolPayload.java`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `TickBatchRequestPayload`** (1 nodes): `TickBatchRequestPayload.java`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `IncomingTickPayload`** (1 nodes): `IncomingTickPayload.java`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `FeedStatusResponsePayload`** (1 nodes): `FeedStatusResponsePayload.java`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `TradeUpdateRequestPayload`** (1 nodes): `TradeUpdateRequestPayload.java`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `SymbolReadinessState`** (1 nodes): `SymbolReadinessState.java`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `LiveReadinessSnapshot`** (1 nodes): `LiveReadinessSnapshot.java`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `PredictionDecision`** (1 nodes): `PredictionDecision.java`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `timestamp()` connect `Local Test Runner` to `Risk and Barrier Management`, `Strategy Core and Metrics`, `JForex Strategy Bridge`, `Historical Warmup Loader`?**
  _High betweenness centrality (0.127) - this node is a cross-community bridge._
- **Why does `StateManager` connect `Risk and Barrier Management` to `Scan Reservation and Holding`, `Community 19`, `Feature Computation`?**
  _High betweenness centrality (0.097) - this node is a cross-community bridge._
- **Why does `lifespan()` connect `Scan Reservation and Holding` to `Risk and Barrier Management`, `Historical Warmup Loader`, `Account Risk Allocator`?**
  _High betweenness centrality (0.081) - this node is a cross-community bridge._
- **Are the 141 inferred relationships involving `ModelFeatures` (e.g. with `FeatureConstants` and `FeatureConfig`) actually correct?**
  _`ModelFeatures` has 141 INFERRED edges - model-reasoned connections that need verification._
- **Are the 134 inferred relationships involving `IncomingTick` (e.g. with `TickAggregator` and `Real-time tick-to-bar aggregator.  Converts raw ``IncomingTick`` objects into ```) actually correct?**
  _`IncomingTick` has 134 INFERRED edges - model-reasoned connections that need verification._
- **Are the 134 inferred relationships involving `IncomingTickBar` (e.g. with `TickAggregator` and `Real-time tick-to-bar aggregator.  Converts raw ``IncomingTick`` objects into ```) actually correct?**
  _`IncomingTickBar` has 134 INFERRED edges - model-reasoned connections that need verification._
- **Are the 74 inferred relationships involving `StateManager` (e.g. with `FeatureConfig` and `IncomingTick`) actually correct?**
  _`StateManager` has 74 INFERRED edges - model-reasoned connections that need verification._