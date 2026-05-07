# Graph Report - .  (2026-05-07)

## Corpus Check
- 200 files · ~50,000 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 407 nodes · 943 edges · 17 communities detected
- Extraction: 64% EXTRACTED · 36% INFERRED · 0% AMBIGUOUS · INFERRED: 335 edges (avg confidence: 0.64)
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

## God Nodes (most connected - your core abstractions)
1. `StateManager` - 141 edges
2. `BarrierManager` - 133 edges
3. `predict()` - 28 edges
4. `_is_historical_mode()` - 19 edges
5. `_append_http_trace()` - 15 edges
6. `lifespan()` - 14 edges
7. `_build_predictions()` - 14 edges
8. `TestEvaluateBar` - 13 edges
9. `_ingest_tick_internal()` - 13 edges
10. `_effective_run_id()` - 12 edges

## Surprising Connections (you probably didn't know these)
- `BarrierAction for OPEN_MARKET must carry horizon so Java adapter can sync it.` --uses--> `BarrierManager`  [INFERRED]
  tests/test_barrier_manager.py → src/behemoth/runtime/barrier_manager.py
- `TestPredictEndpointIntegration` --uses--> `StateManager`  [INFERRED]
  tests/test_predict_endpoint_integration.py → src/behemoth/runtime/state.py
- `Integration test for /predict endpoint orchestration.  Validates that all 5 seam` --uses--> `StateManager`  [INFERRED]
  tests/test_predict_endpoint_integration.py → src/behemoth/runtime/state.py
- `End-to-end orchestration test for predict flow.` --uses--> `StateManager`  [INFERRED]
  tests/test_predict_endpoint_integration.py → src/behemoth/runtime/state.py
- `Verify predict orchestrates BarContext → features → barrier detection → actions.` --uses--> `StateManager`  [INFERRED]
  tests/test_predict_endpoint_integration.py → src/behemoth/runtime/state.py

## Communities

### Community 0 - "Community 0"
Cohesion: 0.04
Nodes (54): BarrierManager, _open_market_action(), Bar-level barrier manager for completed-bar OCO touch confirmation.  Produces id, Expire active scans that predate the side-aware signal close columns.          L, Check if candidate has an active (SCANNING or HOLDING) scan., Retrieve a scan record by ID. Used for testing and diagnostics., Evaluate a completed bar against all active scans for this symbol.          Call, Move a scan from SCANNING to HOLDING. (+46 more)

### Community 1 - "Community 1"
Cohesion: 0.03
Nodes (61): BaseModel, _account_risk_limits_payload(), AccountRiskLimitsResponse, AccountRiskReservationReleaseRequest, AccountRiskStatusResponse, AppConfig, BackfillRequest, checkpoint_state() (+53 more)

### Community 2 - "Community 2"
Cohesion: 0.08
Nodes (55): Return the active (SCANNING/HOLDING) scan for a reservation, or None if not foun, _active_bar_count_for_symbol(), _active_bar_ticks_for_symbol(), _apply_historical_prediction_universe_gate(), _as_utc_ts(), _cache_key(), _catboost_cls(), _deployment_state_for_symbol() (+47 more)

### Community 3 - "Community 3"
Cohesion: 0.06
Nodes (44): Find HOLDING scans for a candidate (to link broker_pos_id)., _append_http_trace(), backfill(), _check_warmup(), _effective_run_id(), _get_feed_tracker(), ingest_account_risk_snapshot(), ingest_account_snapshot() (+36 more)

### Community 4 - "Community 4"
Cohesion: 0.06
Nodes (26): AccountRiskReservationsStatusResponse, _build_open_positions_summary(), get_account_reservations_status(), get_account_risk_reservations_status(), get_active_trades(), get_open_positions_summary(), get_trades_summary(), _monitor_ledger() (+18 more)

### Community 5 - "Community 5"
Cohesion: 0.11
Nodes (12): _build_predictions(), _candidate_regime_name(), _CandidateDecision, Build predictions for each candidate using model + account risk portfolio alloca, _record_rolling_threshold_drift(), Broker-neutral alias for creating risk reservations., Persist allocator decision events for monitoring and reconciliation., Broker-neutral alias for allocator monitoring events. (+4 more)

### Community 6 - "Community 6"
Cohesion: 0.12
Nodes (9): predict_warmup(), Replay buffered bars through the model and atomically snapshot warmup history., Return count of audit_logs rows matching (symbol, run_id)., Delete existing audit rows for (symbol, run_id) and insert events_batch atomical, Export tick_bars rows for (symbol, bar_ticks) to a parquet file. Returns row cou, Return the close_ts of the most recent bar., Record a batch of execution decisions into the persistent audit trail., Delete audit_logs rows matching (symbol, run_id). Returns rows deleted. (+1 more)

### Community 7 - "Community 7"
Cohesion: 0.33
Nodes (11): _build_symbol_dataset(), _ensure_tickbar(), _infer_symbols_from_tick_root(), _infer_symbols_from_tickbars(), _is_utc_tz(), main(), _parse_bar_ticks_grid(), _parse_int_list() (+3 more)

### Community 8 - "Community 8"
Cohesion: 0.2
Nodes (5): Transition one reservation through the formal lifecycle., Promote a pending reservation to OPEN after broker fill., Broker-neutral alias for opening reservations after broker fill., Expire pending reservations older than max_age_seconds., Broker-neutral alias for expiring stale pending reservations.

### Community 9 - "Community 9"
Cohesion: 0.33
Nodes (2): BarrierAction for OPEN_MARKET must carry horizon so Java adapter can sync it., TestActionSchemas

### Community 10 - "Community 10"
Cohesion: 1.0
Nodes (2): BarrierManager, StateManager (228 edges)

### Community 11 - "Community 11"
Cohesion: 1.0
Nodes (2): BarContext (142 edges), Explicit Bid/Ask Bar Schema

### Community 12 - "Community 12"
Cohesion: 1.0
Nodes (2): ExecutionPort, SymbolWorker (per-symbol thread)

### Community 13 - "Community 13"
Cohesion: 1.0
Nodes (1): Tick-based OCO governance pipeline

### Community 14 - "Community 14"
Cohesion: 1.0
Nodes (1): God Nodes (most-connected modules)

### Community 15 - "Community 15"
Cohesion: 1.0
Nodes (1): ModelFeatures (235 edges)

### Community 16 - "Community 16"
Cohesion: 1.0
Nodes (1): Docs-Driven Governance (Artifact-First Truth)

## Knowledge Gaps
- **80 isolated node(s):** `Bar-level barrier manager for completed-bar OCO touch confirmation.  Produces id`, `Manages pending barrier scans and active positions.      State lifecycle: SCANNI`, `Register a new barrier scan. Called when selected_exec=1 passes all gates.`, `Expire active scans that predate the side-aware signal close columns.          L`, `Check if candidate has an active (SCANNING or HOLDING) scan.` (+75 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **Thin community `Community 10`** (2 nodes): `BarrierManager`, `StateManager (228 edges)`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 11`** (2 nodes): `BarContext (142 edges)`, `Explicit Bid/Ask Bar Schema`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 12`** (2 nodes): `ExecutionPort`, `SymbolWorker (per-symbol thread)`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 13`** (1 nodes): `Tick-based OCO governance pipeline`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 14`** (1 nodes): `God Nodes (most-connected modules)`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 15`** (1 nodes): `ModelFeatures (235 edges)`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 16`** (1 nodes): `Docs-Driven Governance (Artifact-First Truth)`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `StateManager` connect `Community 1` to `Community 0`, `Community 2`, `Community 3`, `Community 4`, `Community 5`, `Community 6`, `Community 8`?**
  _High betweenness centrality (0.426) - this node is a cross-community bridge._
- **Why does `BarrierManager` connect `Community 0` to `Community 1`, `Community 2`, `Community 3`, `Community 4`, `Community 5`, `Community 6`, `Community 9`?**
  _High betweenness centrality (0.318) - this node is a cross-community bridge._
- **Why does `predict()` connect `Community 3` to `Community 0`, `Community 1`, `Community 2`, `Community 5`, `Community 6`, `Community 8`?**
  _High betweenness centrality (0.055) - this node is a cross-community bridge._
- **Are the 79 inferred relationships involving `StateManager` (e.g. with `TestPredictEndpointIntegration` and `Integration test for /predict endpoint orchestration.  Validates that all 5 seam`) actually correct?**
  _`StateManager` has 79 INFERRED edges - model-reasoned connections that need verification._
- **Are the 120 inferred relationships involving `BarrierManager` (e.g. with `TestPredictEndpointIntegration` and `Integration test for /predict endpoint orchestration.  Validates that all 5 seam`) actually correct?**
  _`BarrierManager` has 120 INFERRED edges - model-reasoned connections that need verification._
- **Are the 10 inferred relationships involving `predict()` (e.g. with `.get_latest_close_ts()` and `.compute_features()`) actually correct?**
  _`predict()` has 10 INFERRED edges - model-reasoned connections that need verification._
- **What connects `Bar-level barrier manager for completed-bar OCO touch confirmation.  Produces id`, `Manages pending barrier scans and active positions.      State lifecycle: SCANNI`, `Register a new barrier scan. Called when selected_exec=1 passes all gates.` to the rest of the system?**
  _80 weakly-connected nodes found - possible documentation gaps or missing edges._