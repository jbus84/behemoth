# Remaining Architectural Deepening Opportunities

Completed: 8 of 12 opportunities. This document details the final 4 for implementation.

---

## 9. Formalize CandidateCatalog Factory Context

**Files**: `src/behemoth/api/server.py` (lines 448-456), `src/behemoth/core/registry.py`

**Current Problem**:
Every predict call creates a new CandidateCatalog capturing 4 global state pointers (`_registry`, `_historical_registry`, `_is_historical_mode`, `_config.governance_missing_month_policy`) and a callback (`_latest_loaded_month_for_symbol`). The factory closure couples the catalog to global state, making tests hard to write.

**Solution**:
Create a `CatalogContext` dataclass that encapsulates these dependencies:
```python
@dataclass(frozen=True)
class CatalogContext:
    registry: CandidateRegistry | None
    historical_registry: HistoricalCandidateRegistry | None
    is_historical_mode: bool
    missing_month_policy: str
    get_latest_month: Callable[[str], str | None]

def _get_catalog_context() -> CatalogContext:
    return CatalogContext(
        registry=_registry,
        historical_registry=_historical_registry,
        is_historical_mode=_is_historical_mode(),
        missing_month_policy=_config.governance_missing_month_policy,
        get_latest_month=_latest_loaded_month_for_symbol,
    )
```

Then in predict endpoint: `catalog = CandidateCatalog(context=_get_catalog_context())`

**Benefits**:
- Locality: All catalog dependencies are named and passed once
- Testability: Tests can construct CatalogContext directly without mocking globals
- Leverage: CandidateCatalog interface becomes cleaner

---

## 10. Formalize Module Lifecycle Management

**Files**: `src/behemoth/api/server.py`, `src/behemoth/core/model_registry.py`, `src/behemoth/core/historical_prediction_stage.py`

**Current Problem**:
ModelRegistry and HistoricalPredictionStage are module-level singletons (lines 90-91 of server.py) cleared and reused across lifespan restarts. `clear()` methods exist but lifecycle management is ad-hoc—they're called in isolation rather than as part of a coordinated state reset.

**Solution**:
Create a `RuntimeCache` interface that both modules implement:
```python
class RuntimeCache(Protocol):
    def clear(self) -> None:
        """Reset all caches for a new inference cycle."""

class CacheManager:
    def __init__(self, caches: list[RuntimeCache]):
        self.caches = caches
    
    def reset_all(self) -> None:
        """Atomically reset all caches in correct order."""
        for cache in self.caches:
            cache.clear()
```

Usage in server.py lifespan:
```python
_cache_manager = CacheManager([_model_registry, _historical_prediction_stage])
# Then in startup: _cache_manager.reset_all()
```

**Benefits**:
- Locality: Lifecycle management is centralized, not scattered
- Leverage: Clear contract for cache reset semantics
- Testability: Can mock CacheManager; cache reset is atomic

---

## 11. Consolidate Live vs Historical Candidate Resolution

**Files**: `src/behemoth/core/registry.py`, `src/behemoth/core/historical_registry.py`, `src/behemoth/api/server.py` (15+ governance_mode checks)

**Current Problem**:
CandidateRegistry and HistoricalCandidateRegistry duplicate candidate resolution logic. Server.py switches between them with `_is_historical_mode()` in 15+ places. Testing missing_month_policy only exists for historical path.

**Solution**:
Create a unified `CandidateResolver` interface:
```python
class CandidateResolver(Protocol):
    def get_candidates(self, symbol: str, month: str | None = None) -> list[CandidateSpec]:
        ...
    def get_cap_pips(self, symbol: str, month: str | None = None) -> float:
        ...

class UnifiedCandidateRegistry:
    def __init__(self, live_registry: CandidateRegistry | None, historical: HistoricalCandidateRegistry | None, is_historical: bool):
        self.live = live_registry
        self.historical = historical
        self.is_historical = is_historical
    
    def get_candidates(self, symbol: str, month: str | None = None) -> list[CandidateSpec]:
        if self.is_historical and self.historical:
            return self.historical.get_candidates(symbol, month or _latest_loaded_month_for_symbol(symbol))
        elif self.live:
            return self.live.get_candidates(symbol)
        return []
```

Then remove all 15+ `_is_historical_mode()` checks in server.py; instead call `_unified_registry.get_candidates(...)`.

**Benefits**:
- Locality: Candidate resolution logic is in one place
- Leverage: Callers don't care about live vs historical; registry handles it
- Testability: Can test both paths through same interface

---

## 12. Introduce Transaction Boundaries for BarrierManager State

**Files**: `src/behemoth/runtime/barrier_manager.py` (lines 247, 313, 331, 344, etc.)

**Current Problem**:
barrier_scans table updates happen in discrete `execute()` calls. If an exception occurs between decrementing `scan_bars_remaining` and updating `status`, the DB is left in a half-transitioned state. No use of DuckDB transactions.

**Solution**:
Add transaction management to BarrierManager:
```python
class BarrierManager:
    def _with_transaction(self, fn: Callable[[], T]) -> T:
        """Execute fn within a DuckDB transaction."""
        try:
            self._con.begin()
            result = fn()
            self._con.commit()
            return result
        except Exception:
            self._con.rollback()
            raise
    
    def register_scan(self, ....) -> str:
        def _do_register():
            scan_id = str(uuid.uuid4())
            self._con.execute(
                "INSERT INTO barrier_scans (...) VALUES (...)",
                [...]
            )
            return scan_id
        return self._with_transaction(_do_register)
    
    def update_scan_status(self, scan_id: str, new_status: str) -> None:
        def _do_update():
            self._con.execute("UPDATE barrier_scans SET status = ? WHERE scan_id = ?", [new_status, scan_id])
            self._con.execute("UPDATE barrier_scans SET scan_bars_remaining = scan_bars_remaining - 1 WHERE scan_id = ?", [scan_id])
        self._with_transaction(_do_update)
```

**Benefits**:
- Locality: State transitions are atomic
- Leverage: Callers don't need to manage transactions; BarrierManager handles it
- Testability: Can test failure recovery; DB state is always consistent

---

## Implementation Priority

1. **#11 (Live vs Historical consolidation)**: Highest impact. Removes 15+ conditional branches; reduces test matrix.
2. **#12 (Transactions)**: Safety-critical. Prevents silent DB corruption on failures.
3. **#10 (Lifecycle management)**: Improves modularity. Enables per-symbol caching later.
4. **#9 (CatalogContext)**: Improves testability. Can be done incrementally.

---

## Testing Strategy Post-Implementation

After completing all 12 opportunities, run:

```bash
# Verify no new shallow modules introduced
pytest tests/ -v --tb=short

# Check coupling reduced
graphify ./src --update

# Confirm no new god nodes > 150 degree
python3 -c "import json; g=json.load(open('graphify-out/graph.json')); gods=[d for d in g['nodes'] if d.get('degree',0) > 150]; print(f'God nodes: {len(gods)}')"
```

Expected improvements:
- ModelFeatures degree: 165 → 150 (decoupled from model_registry)
- StateManager degree: 142 → 120 (decoupled from barrier_manager)
- New modules: none > 100 degree
- Shallow modules eliminated: StateQueryView, historical_governance_validation, others
