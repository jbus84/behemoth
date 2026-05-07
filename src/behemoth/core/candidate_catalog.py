"""Unified Candidate State sourcing across live and historical governance modes."""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from src.behemoth.core.historical_registry import HistoricalCandidateRegistry
from src.behemoth.core.registry import CandidateRegistry, CandidateSpec

_MONTH_RE = re.compile(r"^\d{4}-\d{2}$")


@dataclass(frozen=True)
class RuntimeCandidateContract:
    """Resolved Candidate State and model artifact contract for one symbol/month."""

    symbol: str
    model_month: str
    cache_key: str
    candidates: list[CandidateSpec]
    model_binding: dict[str, Any]
    cap_pips: float
    source: str
    lock_path: str | None = None


class CandidateCatalog:
    """Mode-aware Candidate State catalog.

    The API server should use this module to resolve Candidate State, cap, and
    model-binding data instead of switching directly between live and historical
    registries at each call site.
    """

    def __init__(
        self,
        *,
        live_registry: CandidateRegistry | None,
        historical_registry: HistoricalCandidateRegistry | None,
        historical_mode: bool,
        missing_month_policy: str = "error",
        force_model_month: str | None = None,
        latest_loaded_month: Callable[[str], str | None] | None = None,
    ) -> None:
        self._live_registry = live_registry
        self._historical_registry = historical_registry
        self._historical_mode = bool(historical_mode)
        self._missing_month_policy = str(missing_month_policy).strip().lower()
        self._force_model_month = _normalize_model_month(force_model_month)
        self._latest_loaded_month = latest_loaded_month or (lambda _symbol: None)

    @property
    def historical_mode(self) -> bool:
        return self._historical_mode

    def cache_key(self, symbol: str, model_month: str | None = None) -> str:
        sym = _normalize_symbol(symbol)
        if self._historical_mode and model_month:
            return f"{sym}|{str(model_month).strip()}"
        return sym

    def active_bar_ticks(self, symbol: str) -> list[int]:
        sym = _normalize_symbol(symbol)
        candidates: list[CandidateSpec] = []
        if self._historical_mode:
            month = self._latest_loaded_month(sym)
            if month and self._historical_registry is not None:
                candidates = self._historical_registry.get_candidates(sym, month)
        elif self._live_registry is not None:
            candidates = self._live_registry.get_candidates(sym)
        ticks = sorted({int(c.bar_ticks) for c in candidates})
        return ticks or ([100] if self._historical_mode else [])

    def resolve_contract(self, symbol: str, close_ts: datetime) -> RuntimeCandidateContract:
        sym = _normalize_symbol(symbol)
        if self._historical_mode:
            return self._resolve_historical_contract(sym, close_ts)
        return self._resolve_live_contract(sym)

    def _resolve_historical_contract(self, symbol: str, close_ts: datetime) -> RuntimeCandidateContract:
        if self._historical_registry is None:
            raise LookupError("Historical governance registry not loaded")
        requested_month = self._force_model_month or _month_from_close_ts(close_ts)
        entry = self._historical_registry.get_entry(symbol, requested_month)
        resolved_month = requested_month
        if entry is None:
            fallback_month = self._resolve_missing_historical_month(symbol, requested_month)
            if fallback_month is not None:
                entry = self._historical_registry.get_entry(symbol, fallback_month)
                resolved_month = fallback_month

        if entry is None:
            available = self._historical_registry.months_for_symbol(symbol)
            avail_txt = ",".join(available) if available else "<none>"
            raise KeyError(
                f"No historical lock for {symbol} month {requested_month} "
                f"(policy={self._missing_month_policy}). available_months={avail_txt}"
            )

        return RuntimeCandidateContract(
            symbol=symbol,
            model_month=resolved_month,
            cache_key=self.cache_key(symbol, resolved_month),
            candidates=list(entry.candidates),
            model_binding=dict(entry.model_binding),
            cap_pips=float(entry.cap_pips),
            source="historical",
            lock_path=str(entry.lock_path),
        )

    def _resolve_live_contract(self, symbol: str) -> RuntimeCandidateContract:
        if self._live_registry is None:
            raise LookupError("Candidate registry not loaded")
        model_binding = self._live_registry.get_model_binding(symbol)
        if not model_binding:
            raise LookupError(f"No model binding registered for {symbol}")
        model_month = _normalize_model_month(str(model_binding.get("model_month", "")).strip()) or "unknown"
        return RuntimeCandidateContract(
            symbol=symbol,
            model_month=model_month,
            cache_key=self.cache_key(symbol),
            candidates=self._live_registry.get_candidates(symbol),
            model_binding=dict(model_binding),
            cap_pips=float(self._live_registry.get_cap_pips(symbol)),
            source="live",
            lock_path=None,
        )

    def _resolve_missing_historical_month(self, symbol: str, requested_month: str) -> str | None:
        if self._historical_registry is None:
            return None
        months = self._historical_registry.months_for_symbol(symbol)
        if not months:
            return None
        if self._missing_month_policy in {"latest", "latest_available"}:
            return months[-1]
        if self._missing_month_policy in {"nearest_previous", "previous", "floor"}:
            prior = [m for m in months if m <= requested_month]
            return prior[-1] if prior else None
        return None


def _normalize_symbol(raw: str) -> str:
    return str(raw).upper().strip()


def _normalize_model_month(raw: str | None) -> str | None:
    txt = str(raw or "").strip()
    if not txt:
        return None
    if len(txt) == 6 and txt.isdigit():
        txt = f"{txt[:4]}-{txt[4:]}"
    return txt if _MONTH_RE.match(txt) else None


def _month_from_close_ts(ts: datetime) -> str:
    v = ts if ts.tzinfo is not None else ts.replace(tzinfo=timezone.utc)
    return v.strftime("%Y-%m")
