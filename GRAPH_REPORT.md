## Graph Report - Behemoth Architecture Analysis

### Overview
- **Total Nodes**: 963 (functions, classes, modules)
- **Total Edges**: 4405 (relationships)
- **Communities Detected**: 1 (by module)

### God Nodes (Highest Degree)
These nodes have the most connections and represent architectural friction points:

1. **ModelFeatures** (unknown)
   - 164 connections
   - Module: unknown

2. **IncomingTick** (unknown)
   - 150 connections
   - Module: unknown

3. **IncomingTickBar** (unknown)
   - 150 connections
   - Module: unknown

4. **StateManager** (unknown)
   - 143 connections
   - Module: unknown

5. **FeatureConfig** (unknown)
   - 135 connections
   - Module: unknown

6. **str** (unknown)
   - 118 connections
   - Module: unknown

7. **BarrierAction** (unknown)
   - 112 connections
   - Module: unknown

8. **server.py** (unknown)
   - 110 connections
   - Module: unknown

9. **BarContext** (unknown)
   - 101 connections
   - Module: unknown

10. **HistoricalCandidateRegistry** (unknown)
   - 95 connections
   - Module: unknown

11. **BarrierManager** (unknown)
   - 92 connections
   - Module: unknown

12. **CandidateRegistry** (unknown)
   - 90 connections
   - Module: unknown

13. **GovernanceValidator** (unknown)
   - 88 connections
   - Module: unknown

14. **HistoricalPredictionStage** (unknown)
   - 85 connections
   - Module: unknown

15. **CandidateCatalog** (unknown)
   - 82 connections
   - Module: unknown

### Cross-Module Connections (Potential Coupling)
Edges between different major modules that may indicate tight coupling:

Found 0 cross-module edges across 0 module pairs

### Key Architectural Improvements Applied
The following deepening integrations have been implemented:

1. **StateStore Protocol** - Decoupled StateManager from DuckDB
   - Reduces coupling of state.py to database implementation
   - Enables test isolation with InMemoryStateStore

2. **BarrierEvaluationContext** - Hidden bid/ask logic behind protocol
   - Reduces cyclomatic complexity in barrier_manager.py
   - Clean seam for future pricing logic changes

3. **FeatureSchemaValidator** - Explicit feature contract validation
   - Detects feature drift at startup, not at inference
   - Early warning for model misalignment

4. **Account Risk Decision Consolidation** - Removed thin wrapper class
   - Moved AccountRiskDecisionEngine logic to account.py functions
   - Reduced unnecessary class instantiation

5. **State Reader Protocols** - Consolidated read interface
   - Single source of truth for state reading contracts
   - Backward compatible through state_queries forwarding

### Recommendations for Next Phase

- **ReservationLifecycle Integration** (~40 call sites in StateManager)
  Integrate explicit reservation state machine to prevent silent capital loss

- **God Node Refactoring**
  ModelFeatures, IncomingTick, StateManager have highest degree
  Consider extracting sub-modules or using adapters to reduce coupling

- **Module Stability**
  server.py (110 edges) is a central hub - consider facade pattern
