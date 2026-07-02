"""Container for the live API's runtime dependencies.

``server.py`` historically held its runtime instance state — the
``StateManager``, ``BarrierManager``, ``PredictionOrchestrator``, candidate
registries, account-risk profile, tick aggregators, etc. — as a constellation
of module-level globals (``_state``, ``_barrier_manager``, ``_orchestrator``…).
That made it hard to:

- Test routes in isolation (they reach for module globals, not parameters)
- Reason about what a route depends on (no typed contract)
- Mock subsets of state (e.g. just the orchestrator) without monkeypatching
  the whole module

``RuntimeAppState`` consolidates these dependencies into one typed struct,
constructed once in the lifespan handler. New code paths and tests should
read state through this container; existing routes continue to access the
module globals (which are kept as aliases). Future trade/risk orchestrator
extractions will add fields here, and future PRs can migrate route handlers
incrementally to read from ``RuntimeAppState`` directly.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from src.behemoth.api.predict_orchestrator import PredictionOrchestrator
    from src.behemoth.core.tick_aggregator import TickAggregator
    from src.behemoth.risk.account_risk import AccountRiskProfile
    from src.behemoth.runtime.barrier_manager import BarrierManager
    from src.behemoth.runtime.state import StateManager


@dataclass
class RuntimeAppState:
    """Typed container for the live API's runtime dependencies.

    Mutable: lifespan populates fields after each is constructed. Default
    values let callers (especially tests) construct partial fixtures without
    needing every dependency.

    Field meanings:
    - ``state``: persistence + threshold queries (DuckDB-backed)
    - ``barrier_manager``: OCO touch detection + scan registration
    - ``orchestrator``: 7-step predict pipeline, the seam used by ``/predict``
    - ``registry`` / ``historical_registry``: candidate catalogs (one is
      populated based on governance mode)
    - ``account_risk_profile``: loaded from yaml, drives the trade-guard
    - ``aggregators``: per-bar_ticks tick → bar aggregation
    - ``feed_state``: per-symbol tick ingestion stats
    - ``models_dir`` / ``account_risk_rules_path``: filesystem locations
      pulled from config at startup
    - ``historical_entries_loaded``: count of governance-lock entries loaded
      (informational; for ``/status`` and observability)
    - ``lifespan_ready``: ``True`` between lifespan ``yield`` and shutdown
    """

    state: "StateManager | None" = None
    barrier_manager: "BarrierManager | None" = None
    orchestrator: "PredictionOrchestrator | None" = None
    # ``registry`` / ``historical_registry`` retained as ``Any``-typed slots
    # defaulting to ``None``; the governance/model registry modules were
    # removed (Task 2.4) and no live code populates these fields in
    # placeholder mode. Kept so ``/status`` observability and existing tests
    # can continue to read them as ``None`` until boostlss_xs wiring lands.
    registry: Any = None
    historical_registry: Any = None
    account_risk_profile: "AccountRiskProfile | None" = None
    aggregators: "dict[int, TickAggregator]" = field(default_factory=dict)
    feed_state: dict[str, Any] = field(default_factory=dict)
    models_dir: Path = field(default_factory=lambda: Path("models/oco"))
    account_risk_rules_path: Path = field(default_factory=lambda: Path(""))
    historical_entries_loaded: int = 0
    lifespan_ready: bool = False

    def is_ready(self) -> bool:
        """Cheap readiness check: orchestrator + state are constructed and lifespan has finished initialization."""
        return (
            self.lifespan_ready
            and self.state is not None
            and self.orchestrator is not None
        )
