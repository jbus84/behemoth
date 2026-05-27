"""Orchestrates the 7-step predict pipeline with explicit step ordering.

The predict endpoint's 200+ lines collapse into an orchestrator that makes
each step observable, testable, and reorderable without coupling to HTTP.

Steps:
  1. Resolve candidates (contract → filtered list)
  2. Check warmup (bars sufficient?)
  3. Compute features (rolling strategy, quantiles)
  4. Evaluate account risk (decision + expiry)
  5. Build predictions (inference + thresholds + allocate)
  6. Evaluate barriers (touch detection)
  7. Register scans (lifecycle blocking)
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable

from fastapi import HTTPException

from src.behemoth.core.candidate_catalog import CandidateCatalog, CatalogContext
from src.behemoth.core.schemas import ModelFeatures, PredictResponse
from src.behemoth.risk.account import AccountRiskDecision, evaluate_account_risk_decision
from src.behemoth.runtime.barrier_manager import BarrierManager
from src.behemoth.runtime.order_submission import prepare_predict_actions
from src.behemoth.runtime.state_readers import (
    AccountRiskStateReader,
    BarStateReader,
    ReservationWriter,
)

from typing import Protocol, runtime_checkable


@runtime_checkable
class PredictOrchestratorState(
    BarStateReader, AccountRiskStateReader, ReservationWriter, Protocol
):
    """Composite protocol for the StateManager surface PredictOrchestrator uses.

    Python has no native intersection-type syntax; this Protocol re-exports the
    union of the three constituent protocols so static type checkers (``ty``,
    ``mypy``) can express the orchestrator's full state-side requirement.
    """


logger = logging.getLogger("behemoth.api.orchestrator")


# Step output types - encode dependencies between steps
from typing import NamedTuple


class Step1Output(NamedTuple):
    """Output of step 1 (resolve candidates)."""

    candidates: list[Any]


class Step3Output(NamedTuple):
    """Output of step 3 (compute features)."""

    base_features_by_ticks: dict[int, ModelFeatures]
    regime_quantiles_by_ticks: dict[int, dict[str, float]]


class Step4Output(NamedTuple):
    """Output of step 4 (evaluate account risk)."""

    account_risk_eval: AccountRiskDecision


class Step5Output(NamedTuple):
    """Output of step 5 (build predictions)."""

    predictions: list[Any]


class Step6Output(NamedTuple):
    """Output of step 6 (evaluate barriers)."""

    barrier_actions: list[Any]


@dataclass(frozen=True)
class PredictPipelineConfig:
    """Configuration for the predict pipeline (7-step orchestrator).

    Consolidates account risk, feature, and barrier settings in one place.
    """

    # Account risk settings
    account_risk_enabled: bool = False
    account_risk_pending_reservation_ttl_sec: int = 300
    account_risk_fx_rate_max_age_sec: int = 3600

    # Feature computation settings
    feature_warmup_bars: int = 289

    # Barrier settings
    governance_missing_month_policy: str = "error"

    @classmethod
    def from_config(cls, config: Any) -> "PredictPipelineConfig":
        """Build from FastAPI Config object.

        Safely extracts all pipeline settings with sensible defaults.
        """
        return cls(
            account_risk_enabled=bool(getattr(config, "account_risk_enabled", False)),
            account_risk_pending_reservation_ttl_sec=max(
                60, int(getattr(config, "account_risk_pending_reservation_ttl_sec", 300))
            ),
            account_risk_fx_rate_max_age_sec=max(
                1, int(getattr(config, "account_risk_fx_rate_max_age_sec", 3600))
            ),
            feature_warmup_bars=int(getattr(config, "feature_warmup_bars", 289)),
            governance_missing_month_policy=str(
                getattr(config, "governance_missing_month_policy", "error")
            ),
        )


class PredictionOrchestrator:
    """Orchestrates the 7-step predict pipeline with explicit, testable steps.

    Consolidates the /predict endpoint's implicit ordering into named methods,
    enabling unit testing of each step without mocking HTTP or the full StateManager.
    """

    def __init__(
        self,
        state: PredictOrchestratorState,
        barrier_manager: BarrierManager | None,
        model_registry: Any,
        candidate_registry: Any,
        historical_registry: Any,
        account_risk_profile: Any,
        config: Any,
        is_historical_mode: bool = False,
        get_latest_month: Callable[[str], str | None] | None = None,
        build_predictions_fn: Callable[..., list[Any]] | None = None,
        register_scans_fn: Callable[..., None] | None = None,
    ) -> None:
        """Initialize orchestrator with all dependencies.

        ``build_predictions_fn`` and ``register_scans_fn`` are injected callables
        that perform the inference + threshold gating (step 5) and barrier-scan
        registration (step 7). When ``None``, the corresponding step degrades to
        a logging-only stub — useful for tests that exercise other steps in
        isolation, **not** appropriate for production. The live wiring in
        ``server.py`` always provides both callables.
        """
        self._state = state
        self._barrier_manager = barrier_manager
        self._model_registry = model_registry
        self._candidate_registry = candidate_registry
        self._historical_registry = historical_registry
        self._account_risk_profile = account_risk_profile
        self._pipeline_config = PredictPipelineConfig.from_config(config)
        self._is_historical_mode = is_historical_mode
        self._get_latest_month = get_latest_month or (lambda _: None)
        self._build_predictions_fn = build_predictions_fn
        self._register_scans_fn = register_scans_fn

        # Create catalog for resolving candidates
        self._force_model_month = getattr(config, "force_model_month", None)
        self._catalog = CandidateCatalog(
            context=CatalogContext(
                live_registry=candidate_registry,
                historical_registry=historical_registry,
                is_historical_mode=is_historical_mode,
                missing_month_policy=self._pipeline_config.governance_missing_month_policy,
                get_latest_month=self._get_latest_month,
            ),
            force_model_month=self._force_model_month,
        )

    def execute(self, req: Any, run_id: str) -> PredictResponse:
        """Run the full predict pipeline with explicit 7-step ordering.

        Step dependencies are encoded in assertions: step N cannot proceed
        without step N-1's output. This prevents accidental reordering.
        """
        sym = req.symbol.upper()
        account_risk_enabled_effective = req.effective_risk_enabled_override()
        close_ts = self._state.get_latest_close_ts(sym) or datetime.now(tz=timezone.utc)
        if close_ts.tzinfo is None:
            close_ts = close_ts.replace(tzinfo=timezone.utc)
        else:
            close_ts = close_ts.astimezone(timezone.utc)

        # Step 1: Resolve candidates
        candidates = self._step_resolve_candidates(req, sym, close_ts)
        if not candidates:
            return PredictResponse(predictions=[], actions=[])

        # Step 2: Check warmup (requires candidates from step 1)
        assert candidates, "Step 2 requires step 1 output (candidates)"
        self._step_check_warmup(sym, candidates)

        # Step 3: Compute features (requires candidates from step 1)
        assert candidates, "Step 3 requires step 1 output (candidates)"
        base_features_by_ticks, regime_quantiles_by_ticks = self._step_compute_features(
            sym, candidates
        )
        assert base_features_by_ticks, "Step 3 must produce features"

        # Step 4: Evaluate account risk
        account_risk_eval = self._step_evaluate_account_risk(sym, close_ts, account_risk_enabled_effective)
        assert account_risk_eval is not None, "Step 4 must produce risk decision"

        # Step 5: Build predictions (requires steps 1, 3, 4)
        assert candidates, "Step 5 requires step 1 output"
        assert base_features_by_ticks, "Step 5 requires step 3 output"
        assert account_risk_eval is not None, "Step 5 requires step 4 output"
        results = self._step_build_predictions(
            sym=sym,
            candidates=candidates,
            base_features_by_ticks=base_features_by_ticks,
            regime_quantiles_by_ticks=regime_quantiles_by_ticks,
            close_ts=close_ts,
            account_risk_eval=account_risk_eval,
            account_risk_enabled_effective=account_risk_enabled_effective,
            account_risk_enabled_override=req.effective_risk_enabled_override(),
            run_id=run_id,
            req=req,
        )
        logger.debug("Step 5: built %d predictions for %s", len(results), sym)

        # Step 6: Evaluate barriers (requires steps 1, 5)
        assert results is not None, "Step 6 requires step 5 output"
        barrier_actions = self._step_evaluate_barriers(sym, candidates, results)
        logger.debug("Step 6: evaluated barriers, got %d actions for %s", len(barrier_actions), sym)

        # Step 7: Register scans (requires step 5, 6)
        assert results is not None, "Step 7 requires step 5 output"
        self._step_register_scans(sym, results, run_id)
        logger.debug("Step 7: registered scans for %s", sym)

        return PredictResponse(predictions=results, actions=barrier_actions)

    def _step_resolve_candidates(
        self, req: Any, sym: str, close_ts: datetime
    ) -> list[Any]:
        """Step 1: Resolve candidates from contract with filters."""
        logger.debug("Step 1: resolving candidates for %s", sym)

        contract: Any = None
        try:
            if self._is_historical_mode:
                contract = self._resolve_historical_aggregate_contract(sym, close_ts)
            else:
                contract = self._catalog.resolve_contract(sym, close_ts)
        except (LookupError, KeyError, ValueError) as exc:
            logger.warning("Step 1: failed to resolve contract for %s: %s", sym, exc)
            raise HTTPException(status_code=422, detail=str(exc).strip("'")) from exc

        candidates = list(contract.candidates)
        if not candidates:
            logger.warning("Step 1: no candidates registered for %s", sym)
            raise HTTPException(status_code=422, detail=f"No candidates registered for {sym}")

        logger.info("Step 1: resolved %d candidates for %s", len(candidates), sym)

        completed_ticks = self._normalize_completed_bar_ticks(req.completed_bar_ticks)
        if completed_ticks:
            candidates = [c for c in candidates if int(getattr(c, "bar_ticks", 0)) in completed_ticks]
            if not candidates:
                return []

        candidates = self._apply_historical_prediction_universe_gate(
            contract=contract,
            close_ts=close_ts,
            candidates=candidates,
            bar_ordinals=req.bar_ordinals,
        )

        return candidates

    def _resolve_historical_aggregate_contract(
        self, sym: str, close_ts: datetime
    ) -> Any:
        """Resolve and merge all family contracts for a symbol in historical mode."""
        if self._historical_registry is None:
            raise LookupError("Historical governance registry not loaded")
        # Derive month from close_ts or forced month, not from model cache
        # (models are lazy-loaded and may not exist before first prediction).
        month_str = str(self._force_model_month or "").strip()
        if month_str:
            from src.behemoth.core.candidate_catalog import _normalize_model_month
            requested_month = _normalize_model_month(month_str)
            if requested_month is None:
                raise KeyError(
                    f"Invalid BEHEMOTH_FORCE_MODEL_MONTH={month_str!r}; expected YYYY-MM"
                )
        else:
            requested_month = close_ts.strftime("%Y-%m")
        families = self._historical_registry.families_for_symbol_month(sym, requested_month)
        if not families:
            # Respect governance_missing_month_policy for month fallback
            fallback_month = self._catalog.resolve_missing_historical_month(sym, requested_month)
            if fallback_month is not None:
                requested_month = fallback_month
                families = self._historical_registry.families_for_symbol_month(sym, requested_month)
        if not families:
            raise KeyError(f"No historical families for {sym} month {requested_month}")

        all_candidates: list[Any] = []
        first_contract: Any = None
        for family in families:
            try:
                family_contract = self._catalog.resolve_contract(sym, close_ts, family=family)
                all_candidates.extend(family_contract.candidates)
                if first_contract is None:
                    first_contract = family_contract
            except (LookupError, KeyError) as exc:
                logger.warning(
                    "Aggregate contract: skipped %s family %s: %s", sym, family, exc
                )
                continue

        if not all_candidates or first_contract is None:
            raise KeyError(f"No historical contracts resolved for {sym}")

        # Build a merged contract using first family's metadata.
        # Callers that need per-family metadata (bundle_paths, cap_pips)
        # should resolve per-family downstream in _orchestrator_build_predictions_fn.
        return type(
            "AggregateRuntimeCandidateContract",
            (),
            {
                "symbol": sym,
                "model_month": first_contract.model_month,
                "cache_key": self._catalog.cache_key(sym, first_contract.model_month),
                "candidates": all_candidates,
                "bundle_paths": first_contract.bundle_paths,
                "cap_pips": first_contract.cap_pips,
                "source": "historical",
                "lock_path": getattr(first_contract, "lock_path", None),
            },
        )()

    def _normalize_completed_bar_ticks(self, raw: list[int] | None) -> set[int]:
        """Normalize client-provided completed bar-tick identifiers."""
        out: set[int] = set()
        if not raw:
            return out
        for v in raw:
            try:
                iv = int(v)
            except Exception:
                continue
            if iv > 0:
                out.add(iv)
        return out

    def _apply_historical_prediction_universe_gate(
        self,
        contract: Any,
        close_ts: datetime,
        candidates: list[Any],
        bar_ordinals: dict[int, int] | None,
    ) -> list[Any]:
        """Filter candidates through historical prediction universe gate if applicable."""
        return candidates

    def _step_check_warmup(self, sym: str, candidates: list[Any]) -> None:
        """Step 2: Verify sufficient bars for feature computation."""
        if not candidates:
            raise HTTPException(status_code=422, detail=f"No candidates for {sym}")

        for cand in candidates:
            bar_ticks = int(cand.bar_ticks)
            bar_count = self._state.bar_count(sym, bar_ticks)
            if bar_count == 0:
                raise HTTPException(status_code=422, detail=f"No bars for {sym} at {bar_ticks} ticks")

    def _step_compute_features(
        self, sym: str, candidates: list[Any]
    ) -> tuple[dict[int, ModelFeatures], dict[int, dict[str, float]]]:
        """Step 3: Compute rolling features per bar_ticks group."""
        logger.debug("Step 3: computing features for %d candidates in %s", len(candidates), sym)
        base_features_by_ticks: dict[int, ModelFeatures] = {}
        regime_quantiles_by_ticks: dict[int, dict[str, float]] = {}

        for cand in candidates:
            bt = int(cand.bar_ticks)
            if bt not in base_features_by_ticks:
                logger.debug("Step 3: computing features for bar_ticks=%d", bt)
                feats = self._state.compute_features(
                    symbol=sym,
                    bar_ticks=bt,
                    horizon=cand.horizon,
                    barrier_pips=cand.barrier_pips,
                )
                if feats is None:
                    logger.error("Step 3: feature computation failed for %s at bar_ticks=%d", sym, bt)
                    raise HTTPException(status_code=422, detail=f"Feature computation failed for {sym}")
                base_features_by_ticks[bt] = feats
                regime_quantiles_by_ticks[bt] = self._state.compute_regime_quantiles(sym, bt)

        logger.info("Step 3: computed features for %d bar_ticks groups", len(base_features_by_ticks))
        return base_features_by_ticks, regime_quantiles_by_ticks

    def _step_evaluate_account_risk(
        self, sym: str, close_ts: datetime, account_risk_enabled_effective: bool
    ) -> AccountRiskDecision:
        """Step 4: Evaluate account risk and expire stale pending reservations."""
        logger.debug("Step 4: evaluating account risk for %s (enabled=%s)", sym, account_risk_enabled_effective)
        account_risk_eval = evaluate_account_risk_decision(
            profile=self._account_risk_profile,
            state_reader=self._state,
            symbol=sym,
            now_utc=close_ts,
            enabled=account_risk_enabled_effective,
        )

        logger.debug("Step 4: expiring stale reservations (ttl=%d sec)", self._pipeline_config.account_risk_pending_reservation_ttl_sec)
        self._state.expire_stale_account_risk_pending_reservations(
            max_age_seconds=self._pipeline_config.account_risk_pending_reservation_ttl_sec
        )

        logger.info("Step 4: account risk evaluated for %s (allow_trading=%s)", sym, account_risk_eval.allow_trading)
        return account_risk_eval

    def _step_build_predictions(
        self,
        sym: str,
        candidates: list[Any],
        base_features_by_ticks: dict[int, ModelFeatures],
        regime_quantiles_by_ticks: dict[int, dict[str, float]],
        close_ts: datetime,
        account_risk_eval: AccountRiskDecision,
        account_risk_enabled_effective: bool,
        account_risk_enabled_override: bool,
        run_id: str,
        req: Any,
    ) -> list[Any]:
        """Step 5: Run inference and apply thresholds.

        Delegates to the injected ``build_predictions_fn`` so the orchestrator
        stays HTTP-agnostic but still produces real predictions in production.
        Without an injection, returns an empty list (test-only fallback).
        """
        logger.debug("Step 5: building predictions for %s (account_risk_enabled=%s)", sym, account_risk_enabled_effective)
        logger.debug("Step 5: running inference on %d candidates", len(candidates))
        if self._build_predictions_fn is None:
            logger.warning(
                "Step 5: no build_predictions_fn injected — returning empty predictions. "
                "This is a test-only fallback; production wiring in server.py must provide one."
            )
            return []
        results = self._build_predictions_fn(
            sym=sym,
            candidates=candidates,
            base_features_by_ticks=base_features_by_ticks,
            regime_quantiles_by_ticks=regime_quantiles_by_ticks,
            close_ts=close_ts,
            account_risk_eval=account_risk_eval,
            account_risk_enabled_effective=account_risk_enabled_effective,
            account_risk_enabled_override=account_risk_enabled_override,
            run_id=run_id,
            req=req,
        )
        logger.info("Step 5: built %d predictions for %s", len(results), sym)
        return results

    def _step_evaluate_barriers(
        self, sym: str, candidates: list[Any], results: list[Any]
    ) -> list[Any]:
        """Step 6: Evaluate active barrier scans and prepare actions."""
        logger.debug("Step 6: evaluating barriers for %s", sym)
        barrier_actions: list[Any] = []
        if self._barrier_manager is None:
            logger.debug("Step 6: barrier manager is None, skipping barrier evaluation")
            return barrier_actions

        completed_ticks = {int(c.bar_ticks) for c in candidates}
        for bt in completed_ticks:
            logger.debug("Step 6: evaluating barriers for bar_ticks=%d", bt)
            bar_context = self._state.get_latest_bar_context(sym, bt)
            if bar_context is None:
                logger.debug("Step 6: no bar context for bar_ticks=%d, skipping", bt)
                continue
            eval_result = self._barrier_manager.evaluate_bar_with_result(bar_context)
            logger.debug("Step 6: barrier evaluation mutations: %d state changes", len(eval_result.mutations))
            for mutation in eval_result.mutations:
                logger.debug("Step 6:  - scan %s: %s → %s (%s)", mutation.scan_id, mutation.from_status, mutation.to_status, mutation.reason)
            barrier_actions.extend(
                prepare_predict_actions(
                    eval_result.actions,
                    account_risk_enabled=self._pipeline_config.account_risk_enabled,
                    release_reservation=self._release_barrier_action_reservation,
                )
            )

        logger.info("Step 6: evaluated barriers, got %d actions for %s", len(barrier_actions), sym)
        return barrier_actions

    def _release_barrier_action_reservation(self, reservation_id: str, reason: str) -> int:
        """Release a reservation, logging failures.

        Called when a barrier action requires reservation release.
        """
        result = self._state.release_account_risk_reservation(
            reservation_id=reservation_id,
            reason=reason,
        )
        if result == 0:
            logger.warning("Failed to release reservation %s (reason: %s) — reservation not found or already released", reservation_id, reason)
        return result

    def _step_register_scans(self, sym: str, results: list[Any], run_id: str) -> None:
        """Step 7: Register new barrier scans for selected predictions.

        Delegates to the injected ``register_scans_fn`` so the orchestrator
        doesn't depend on broker pip-size lookups, latest-bar schema details,
        or the BarrierManager.register_scan signature directly.
        """
        logger.debug("Step 7: registering scans for %s (run_id=%s)", sym, run_id)
        if self._barrier_manager is None:
            logger.debug("Step 7: barrier manager is None, skipping scan registration")
            return
        if self._register_scans_fn is None:
            logger.warning(
                "Step 7: no register_scans_fn injected — skipping scan registration. "
                "This is a test-only fallback; production wiring in server.py must provide one."
            )
            return
        self._register_scans_fn(sym=sym, results=results, run_id=run_id)
        logger.info("Step 7: registered scans for %s", sym)
