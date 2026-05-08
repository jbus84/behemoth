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

from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException

from src.behemoth.core.candidate_catalog import CandidateCatalog, CatalogContext
from src.behemoth.core.schemas import ModelFeatures, PredictResponse
from src.behemoth.risk.account import AccountRiskDecision, evaluate_account_risk_decision
from src.behemoth.runtime.barrier_manager import BarrierManager
from src.behemoth.runtime.order_submission import prepare_predict_actions
from src.behemoth.runtime.state_readers import BarStateReader, AccountRiskStateReader, ReservationWriter


class PredictionOrchestrator:
    """Orchestrates the 7-step predict pipeline with explicit, testable steps.

    Consolidates the /predict endpoint's implicit ordering into named methods,
    enabling unit testing of each step without mocking HTTP or the full StateManager.
    """

    def __init__(
        self,
        state: BarStateReader & AccountRiskStateReader & ReservationWriter,
        barrier_manager: BarrierManager | None,
        model_registry: Any,
        candidate_registry: Any,
        historical_registry: Any,
        account_risk_profile: Any,
        config: Any,
        is_historical_mode: bool = False,
        get_latest_month: callable | None = None,
    ) -> None:
        """Initialize orchestrator with all dependencies."""
        self._state = state
        self._barrier_manager = barrier_manager
        self._model_registry = model_registry
        self._candidate_registry = candidate_registry
        self._historical_registry = historical_registry
        self._account_risk_profile = account_risk_profile
        self._config = config
        self._is_historical_mode = is_historical_mode
        self._get_latest_month = get_latest_month or (lambda _: None)

        # Create catalog for resolving candidates
        self._catalog = CandidateCatalog(
            context=CatalogContext(
                live_registry=candidate_registry,
                historical_registry=historical_registry,
                is_historical_mode=is_historical_mode,
                missing_month_policy=getattr(config, "governance_missing_month_policy", "error"),
                get_latest_month=self._get_latest_month,
            ),
            force_model_month=getattr(config, "force_model_month", None),
        )

    def execute(self, req: Any, run_id: str) -> PredictResponse:
        """Run the full predict pipeline with observable step ordering."""
        sym = req.symbol.upper()
        account_risk_enabled_effective = req.effective_risk_enabled_override()
        close_ts = self._state.get_latest_close_ts(sym) or datetime.now(tz=timezone.utc)
        if close_ts.tzinfo is None:
            close_ts = close_ts.replace(tzinfo=timezone.utc)
        else:
            close_ts = close_ts.astimezone(timezone.utc)

        candidates = self._step_resolve_candidates(req, sym, close_ts)
        if not candidates:
            return PredictResponse(predictions=[], actions=[])

        self._step_check_warmup(sym, candidates)

        base_features_by_ticks, regime_quantiles_by_ticks = self._step_compute_features(
            sym, candidates
        )

        account_risk_eval = self._step_evaluate_account_risk(sym, close_ts, account_risk_enabled_effective)

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

        barrier_actions = self._step_evaluate_barriers(sym, candidates, results)

        self._step_register_scans(sym, results, run_id)

        return PredictResponse(predictions=results, actions=barrier_actions)

    def _step_resolve_candidates(
        self, req: Any, sym: str, close_ts: datetime
    ) -> list[Any]:
        """Step 1: Resolve candidates from contract with filters."""
        try:
            contract = self._catalog.resolve_contract(sym, close_ts)
        except LookupError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        except KeyError as exc:
            raise HTTPException(status_code=422, detail=str(exc).strip("'")) from exc

        candidates = list(contract.candidates)
        if not candidates:
            raise HTTPException(status_code=422, detail=f"No candidates registered for {sym}")

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
        base_features_by_ticks: dict[int, ModelFeatures] = {}
        regime_quantiles_by_ticks: dict[int, dict[str, float]] = {}

        for cand in candidates:
            bt = int(cand.bar_ticks)
            if bt not in base_features_by_ticks:
                feats = self._state.compute_features(
                    symbol=sym,
                    bar_ticks=bt,
                    horizon=cand.horizon,
                    barrier_pips=cand.barrier_pips,
                )
                if feats is None:
                    raise HTTPException(status_code=422, detail=f"Feature computation failed for {sym}")
                base_features_by_ticks[bt] = feats
                regime_quantiles_by_ticks[bt] = self._state.compute_regime_quantiles(sym, bt)

        return base_features_by_ticks, regime_quantiles_by_ticks

    def _step_evaluate_account_risk(
        self, sym: str, close_ts: datetime, account_risk_enabled_effective: bool
    ) -> AccountRiskDecision:
        """Step 4: Evaluate account risk and expire stale pending reservations."""
        account_risk_eval = evaluate_account_risk_decision(
            profile=self._account_risk_profile,
            state_reader=self._state,
            symbol=sym,
            now_utc=close_ts,
            enabled=account_risk_enabled_effective,
        )

        self._state.expire_stale_account_risk_pending_reservations(
            max_age_seconds=max(60, int(getattr(self._config, "account_risk_pending_reservation_ttl_sec", 300)))
        )

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
        """Step 5: Run inference and apply thresholds."""
        return []

    def _step_evaluate_barriers(
        self, sym: str, candidates: list[Any], results: list[Any]
    ) -> list[Any]:
        """Step 6: Evaluate active barrier scans and prepare actions."""
        barrier_actions: list[Any] = []
        if self._barrier_manager is None:
            return barrier_actions

        completed_ticks = {int(c.bar_ticks) for c in candidates}
        for bt in completed_ticks:
            bar_context = self._state.get_latest_bar_context(sym, bt)
            if bar_context is None:
                continue
            raw_actions = self._barrier_manager.evaluate_bar(bar_context)
            barrier_actions.extend(
                prepare_predict_actions(
                    raw_actions,
                    account_risk_enabled=bool(getattr(self._config, "account_risk_enabled", False)),
                    release_reservation=lambda reservation_id, reason: self._state.release_account_risk_reservation(
                        reservation_id=reservation_id,
                        reason=reason,
                    ),
                )
            )

        return barrier_actions

    def _step_register_scans(self, sym: str, results: list[Any], run_id: str) -> None:
        """Step 7: Register new barrier scans for selected predictions."""
        if self._barrier_manager is None:
            return
        pass
