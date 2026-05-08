# Graph Report - ./src  (2026-05-08)

## Corpus Check
- 133 files · ~58,630 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 1412 nodes · 5187 edges · 60 communities detected
- Extraction: 38% EXTRACTED · 62% INFERRED · 0% AMBIGUOUS · INFERRED: 3240 edges (avg confidence: 0.59)
- Token cost: 0 input · 0 output

## Community Hubs (Navigation)
- [[_COMMUNITY_State Management & Scans|State Management & Scans]]
- [[_COMMUNITY_JForex Strategy Core|JForex Strategy Core]]
- [[_COMMUNITY_Live JForex Strategy|Live JForex Strategy]]
- [[_COMMUNITY_Bar Alignment & Reservation|Bar Alignment & Reservation]]
- [[_COMMUNITY_Core Tests & Worker|Core Tests & Worker]]
- [[_COMMUNITY_Barrier & Risk Management|Barrier & Risk Management]]
- [[_COMMUNITY_Account Risk Allocation|Account Risk Allocation]]
- [[_COMMUNITY_Governance Validation|Governance Validation]]
- [[_COMMUNITY_Broker Connection|Broker Connection]]
- [[_COMMUNITY_Feature Computation|Feature Computation]]
- [[_COMMUNITY_Barrier Evaluation|Barrier Evaluation]]
- [[_COMMUNITY_Execution State Store|Execution State Store]]
- [[_COMMUNITY_Broker Snapshot Models|Broker Snapshot Models]]
- [[_COMMUNITY_Bar Alignment Service|Bar Alignment Service]]
- [[_COMMUNITY_Execution Port Adapters|Execution Port Adapters]]
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

## God Nodes (most connected - your core abstractions)
1. `ModelFeatures` - 165 edges
2. `IncomingTick` - 150 edges
3. `IncomingTickBar` - 150 edges
4. `StateManager` - 142 edges
5. `FeatureConfig` - 135 edges
6. `BarrierAction` - 95 edges
7. `BarContext` - 91 edges
8. `BarrierManager` - 86 edges
9. `HistoricalCandidateRegistry` - 83 edges
10. `HistoricalPredictionStage` - 83 edges

## Surprising Connections (you probably didn't know these)
- `Canonical feature builder for the OCO CatBoost model.  This is the SINGLE SOURCE` --uses--> `ModelFeatures`  [INFERRED]
  src/behemoth/core/features.py → src/behemoth/core/schemas.py
- `Registry entry describing one canonical model feature.` --uses--> `ModelFeatures`  [INFERRED]
  src/behemoth/core/features.py → src/behemoth/core/schemas.py
- `Versioned feature manifest shared by research and runtime code.` --uses--> `ModelFeatures`  [INFERRED]
  src/behemoth/core/features.py → src/behemoth/core/schemas.py
- `Runtime-enforceable Feature Set contract for model and data parity.` --uses--> `ModelFeatures`  [INFERRED]
  src/behemoth/core/features.py → src/behemoth/core/schemas.py
- `Hardcoded physical constants and thresholds for feature computation.` --uses--> `ModelFeatures`  [INFERRED]
  src/behemoth/core/features.py → src/behemoth/core/schemas.py

## Communities

### Community 0 - "State Management & Scans"
Cohesion: 0.02
Nodes (194): Return the active (SCANNING/HOLDING) scan for a reservation, or None if not foun, _month_from_close_ts(), _normalize_model_month(), _normalize_symbol(), Unified Candidate State sourcing across live and historical governance modes., Resolved Candidate State and model artifact contract for one symbol/month., RuntimeCandidateContract, check() (+186 more)

### Community 1 - "JForex Strategy Core"
Cohesion: 0.02
Nodes (22): isCloseMarket(), isOpenMarket(), BehemothStrategyCore, closePositionByScanId(), entriesAllowed(), submitMarketOrder(), SymbolRuntimeState, JForexMetrics (+14 more)

### Community 2 - "Live JForex Strategy"
Cohesion: 0.03
Nodes (21): BehemothJForexStrategy, BrokerBridgeLoader, BrokerBridgeLoaderTest, FakeBrokerHistoryPort, MutableClock, BrokerOrderSnapshotWriter, JForexBrokerHistoryPort, BridgeRuntime (+13 more)

### Community 3 - "Bar Alignment & Reservation"
Cohesion: 0.06
Nodes (108): Validates account-risk reservation lifecycle transitions., ReservationState, ReservationStateMachine, BarAlignmentResult, BarAlignmentService, BarBoundaryContract, _build_bar(), _compute_microstructure() (+100 more)

### Community 4 - "Core Tests & Worker"
Cohesion: 0.04
Nodes (25): BehemothStrategyCoreTest, JForexConnectionTest, Sleeper, fromEnvironment(), requiredSetting(), setting(), LocalExecutionPort, SimulatedOrder (+17 more)

### Community 5 - "Barrier & Risk Management"
Cohesion: 0.2
Nodes (103): AccountRiskProfile, BarrierManager, Manages pending barrier scans and active positions.      State lifecycle: SCANNI, BaseModel, CandidateCatalog, Mode-aware Candidate State catalog.      The API server should use this module t, AccountRiskDecisionEngine, Evaluate account-level risk limits from read-only runtime state. (+95 more)

### Community 6 - "Account Risk Allocation"
Cohesion: 0.05
Nodes (47): AccountRiskAllocator, AccountRiskBuffers, AccountRiskCostGate, EntryGateDecision, evaluate_account_risk_limits(), evaluate_trade_guard(), evaluate_trade_risk_guard(), load_account_risk_profile() (+39 more)

### Community 7 - "Governance Validation"
Cohesion: 0.07
Nodes (27): Check, failed_checks(), GovernanceValidator, Composable governance validation rules for historical locks.  Encapsulates valid, Return failed checks produced by this validator., Summarize failed checks produced by this validator., Validate lock files and return (lock_keys, lock_dupes)., Validate index.csv consistency. (+19 more)

### Community 8 - "Broker Connection"
Cohesion: 0.06
Nodes (12): isConnected(), JForexBrokerSnapshotRunner, startStrategy(), connect(), isConnected(), JForexLiveRunner, LiveClient, startStrategy() (+4 more)

### Community 9 - "Feature Computation"
Cohesion: 0.07
Nodes (21): _compute_cost_features(), _compute_micro_features(), compute_regime_quantiles_from_bars(), _compute_structural_features(), _compute_velocity_features(), _extract_core_series(), FeatureConstants, FeatureDefinition (+13 more)

### Community 10 - "Barrier Evaluation"
Cohesion: 0.1
Nodes (19): BarrierEvaluationResult, BarrierStateMutation, _open_market_action(), Bar-level barrier manager for completed-bar OCO touch confirmation.  Produces id, Expire active scans that predate the side-aware signal close columns.          L, Check if candidate has an active (SCANNING or HOLDING) scan., Retrieve a scan record by ID. Used for testing and diagnostics., Evaluate a completed bar and return broker-facing actions. (+11 more)

### Community 11 - "Execution State Store"
Cohesion: 0.13
Nodes (4): ExecutionStateStore, ExecutionStateStoreTest, OcoGroupState, OcoLegState

### Community 12 - "Broker Snapshot Models"
Cohesion: 0.15
Nodes (18): BrokerSnapshot, BrokerSnapshotOrder, compare_runtime_context(), derive_restart_eligibility(), _jsonable(), load_broker_snapshot(), load_runtime_session_metadata(), LocalRuntimeStateSummary (+10 more)

### Community 13 - "Bar Alignment Service"
Cohesion: 0.14
Nodes (4): BarAlignmentService, BarAlignmentServiceTest, HistoricalWarmupLoader, HistoricalWarmupLoaderTest

### Community 14 - "Execution Port Adapters"
Cohesion: 0.11
Nodes (4): NoopExecutionPort, RecordingExecutionPort, ExecutionPort, toMarketOrderRequest()

### Community 15 - "Community 15"
Cohesion: 0.29
Nodes (2): JForexExecutionPort, Task

### Community 16 - "Community 16"
Cohesion: 0.22
Nodes (1): BrokerSnapshotStrategy

### Community 17 - "Community 17"
Cohesion: 0.38
Nodes (1): ParquetTickLoader

### Community 18 - "Community 18"
Cohesion: 0.29
Nodes (1): LiveReadinessMetrics

### Community 19 - "Community 19"
Cohesion: 0.5
Nodes (3): dashboard(), Lightweight monitoring dashboard for the Behemoth OCO strategy.  Served as a Fas, Serve the single-page monitoring dashboard.

### Community 20 - "Community 20"
Cohesion: 0.5
Nodes (1): BrokerHistoryPort

### Community 21 - "Community 21"
Cohesion: 1.0
Nodes (0): 

### Community 22 - "Community 22"
Cohesion: 1.0
Nodes (0): 

### Community 23 - "Community 23"
Cohesion: 1.0
Nodes (0): 

### Community 24 - "Community 24"
Cohesion: 1.0
Nodes (1): Build from a state_universe row in the live lock JSON.

### Community 25 - "Community 25"
Cohesion: 1.0
Nodes (1): Load exactly from per-symbol *_oco_live_lock.json files.

### Community 26 - "Community 26"
Cohesion: 1.0
Nodes (1): Symbols that have at least one registered candidate.

### Community 27 - "Community 27"
Cohesion: 1.0
Nodes (0): 

### Community 28 - "Community 28"
Cohesion: 1.0
Nodes (1): Convert to UTC datetime.

### Community 29 - "Community 29"
Cohesion: 1.0
Nodes (1): Compute SHA256 hash of file.

### Community 30 - "Community 30"
Cohesion: 1.0
Nodes (1): Generate cache key: symbol or symbol|month.

### Community 31 - "Community 31"
Cohesion: 1.0
Nodes (0): 

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

## Knowledge Gaps
- **81 isolated node(s):** `A single prediction candidate to evaluate.`, `Build from a state_universe row in the live lock JSON.`, `Registry of valid candidate specifications loaded from live lock JSONs.`, `Load exactly from per-symbol *_oco_live_lock.json files.`, `Symbols that have at least one registered candidate.` (+76 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **Thin community `Community 21`** (2 nodes): `normalizeSymbol()`, `RuntimeInstrument.java`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 22`** (2 nodes): `SymbolReadinessSnapshot.java`, `normalizeSymbol()`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 23`** (1 nodes): `__init__.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 24`** (1 nodes): `Build from a state_universe row in the live lock JSON.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 25`** (1 nodes): `Load exactly from per-symbol *_oco_live_lock.json files.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 26`** (1 nodes): `Symbols that have at least one registered candidate.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 27`** (1 nodes): `__init__.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 28`** (1 nodes): `Convert to UTC datetime.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 29`** (1 nodes): `Compute SHA256 hash of file.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 30`** (1 nodes): `Generate cache key: symbol or symbol|month.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 31`** (1 nodes): `__init__.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 32`** (1 nodes): `__init__.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 33`** (1 nodes): `__init__.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 34`** (1 nodes): `build.gradle.kts`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 35`** (1 nodes): `MarketOrderRequest.java`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 36`** (1 nodes): `OrderEvent.java`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 37`** (1 nodes): `OrderHandle.java`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 38`** (1 nodes): `OrderResult.java`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 39`** (1 nodes): `OrderEventType.java`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 40`** (1 nodes): `RuntimeTick.java`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 41`** (1 nodes): `OrderRequest.java`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 42`** (1 nodes): `TradeOpenRequestPayload.java`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 43`** (1 nodes): `BackfillRequestPayload.java`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 44`** (1 nodes): `ActiveTradePayload.java`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 45`** (1 nodes): `PredictRequestPayload.java`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 46`** (1 nodes): `AccountSnapshotRequestPayload.java`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 47`** (1 nodes): `PredictResponsePayload.java`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 48`** (1 nodes): `TradeTouchRequestPayload.java`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 49`** (1 nodes): `TickIngestResponsePayload.java`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 50`** (1 nodes): `TickBatchResponsePayload.java`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 51`** (1 nodes): `ApiAckResponse.java`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 52`** (1 nodes): `FeedStatusSymbolPayload.java`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 53`** (1 nodes): `TickBatchRequestPayload.java`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 54`** (1 nodes): `IncomingTickPayload.java`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 55`** (1 nodes): `FeedStatusResponsePayload.java`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 56`** (1 nodes): `TradeUpdateRequestPayload.java`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 57`** (1 nodes): `SymbolReadinessState.java`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 58`** (1 nodes): `LiveReadinessSnapshot.java`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 59`** (1 nodes): `PredictionDecision.java`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `ModelFeatures` connect `Bar Alignment & Reservation` to `State Management & Scans`, `Feature Computation`, `Barrier & Risk Management`?**
  _High betweenness centrality (0.054) - this node is a cross-community bridge._
- **Why does `seed_audit_history()` connect `State Management & Scans` to `Bar Alignment & Reservation`, `Barrier & Risk Management`?**
  _High betweenness centrality (0.050) - this node is a cross-community bridge._
- **Why does `BarrierAction` connect `Barrier & Risk Management` to `State Management & Scans`, `Barrier Evaluation`, `Account Risk Allocation`?**
  _High betweenness centrality (0.048) - this node is a cross-community bridge._
- **Are the 161 inferred relationships involving `ModelFeatures` (e.g. with `FeatureDefinition` and `FeatureSchema`) actually correct?**
  _`ModelFeatures` has 161 INFERRED edges - model-reasoned connections that need verification._
- **Are the 147 inferred relationships involving `IncomingTick` (e.g. with `BarAlignmentResult` and `BarBoundaryContract`) actually correct?**
  _`IncomingTick` has 147 INFERRED edges - model-reasoned connections that need verification._
- **Are the 147 inferred relationships involving `IncomingTickBar` (e.g. with `BarAlignmentResult` and `BarBoundaryContract`) actually correct?**
  _`IncomingTickBar` has 147 INFERRED edges - model-reasoned connections that need verification._
- **Are the 79 inferred relationships involving `StateManager` (e.g. with `FeatureConfig` and `BarContext`) actually correct?**
  _`StateManager` has 79 INFERRED edges - model-reasoned connections that need verification._