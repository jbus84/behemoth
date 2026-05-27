"""Unified Candidate State sourcing across live and historical governance modes."""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from src.behemoth.core.historical_registry import HistoricalCandidateRegistry
from src.behemoth.core.registry import CandidateRegistry, CandidateSpec

if TYPE_CHECKING:
    from src.behemoth.core.bundle_paths import BundlePaths

_MONTH_RE = re.compile(r"^\d{4}-\d{2}$")


@dataclass(frozen=True)
class CatalogContext:
    """Encapsulates catalog dependencies to reduce closure-based coupling.

    Instead of passing individual parameters or closing over globals,
    callers construct a context once and pass it to CandidateCatalog.

    This makes testing easier (can construct context directly) and makes
    dependencies explicit and named.
    """

    live_registry: CandidateRegistry | None
    historical_registry: HistoricalCandidateRegistry | None
    is_historical_mode: bool
    missing_month_policy: str = "error"
    get_latest_month: Callable[[str], str | None] | None = None

    def __post_init__(self):
        """Validate context consistency."""
        if self.is_historical_mode and self.historical_registry is None:
            raise ValueError("Historical mode requires historical_registry to be provided")
        if not self.is_historical_mode and self.live_registry is None:
            raise ValueError("Live mode requires live_registry to be provided")


@dataclass(frozen=True)
class RuntimeCandidateContract:
    """Resolved Candidate State and model artifact contract for one symbol/month."""

    symbol: str
    model_month: str
    cache_key: str
    candidates: list[CandidateSpec]
    bundle_paths: BundlePaths  # type: ignore
    cap_pips: float
    source: str
    lock_path: str | None = None


class CandidateCatalog:
    """Mode-aware Candidate State catalog.

    The API server should use this module to resolve Candidate State, cap, and
    model-binding data instead of switching directly between live and historical
    registries at each call site.

    Can be constructed from a CatalogContext (preferred, reduces coupling) or
    from individual parameters (backward-compatible).
    """

    def __init__(
        self,
        *,
        context: CatalogContext | None = None,
        live_registry: CandidateRegistry | None = None,
        historical_registry: HistoricalCandidateRegistry | None = None,
        historical_mode: bool = False,
        missing_month_policy: str = "error",
        force_model_month: str | None = None,
        latest_loaded_month: Callable[[str], str | None] | None = None,
    ) -> None:
        # Accept either context (preferred) or individual parameters
        if context is not None:
            self._live_registry = context.live_registry
            self._historical_registry = context.historical_registry
            self._historical_mode = context.is_historical_mode
            self._missing_month_policy = context.missing_month_policy
            self._latest_loaded_month = context.get_latest_month or (lambda _symbol: None)
        else:
            self._live_registry = live_registry
            self._historical_registry = historical_registry
            self._historical_mode = bool(historical_mode)
            self._missing_month_policy = str(missing_month_policy).strip().lower()
            self._latest_loaded_month = latest_loaded_month or (lambda _symbol: None)

        self._force_model_month = _normalize_model_month(force_model_month)

    @property
    def historical_mode(self) -> bool:
        return self._historical_mode

    def cache_key(self, symbol: str, model_month: str | None = None, family: str | None = None) -> str:
        sym = _normalize_symbol(symbol)
        parts = [sym]
        if self._historical_mode and model_month:
            parts.append(str(model_month).strip())
        fam = str(family or "").strip()
        if fam:
            parts.append(fam)
        return "|".join(parts)

    def active_bar_ticks(self, symbol: str, family: str | None = None) -> list[int]:
        sym = _normalize_symbol(symbol)
        candidates: list[CandidateSpec] = []
        if self._historical_mode:
            month = self._latest_loaded_month(sym)
            if month and self._historical_registry is not None:
                if family is not None:
                    candidates = self._historical_registry.get_candidates(sym, month, family=family)
                else:
                    # Aggregate across all families for this symbol/month
                    for fam in self._historical_registry.families_for_symbol_month(sym, month):
                        candidates.extend(self._historical_registry.get_candidates(sym, month, family=fam))
        elif self._live_registry is not None:
            candidates = self._live_registry.get_candidates(sym)
        ticks = sorted({int(c.bar_ticks) for c in candidates})
        return ticks or ([100] if self._historical_mode else [])

    def resolve_contract(
        self, symbol: str, close_ts: datetime, family: str | None = None
    ) -> RuntimeCandidateContract:
        sym = _normalize_symbol(symbol)
        if self._historical_mode:
            if family is None:
                raise ValueError("family is required in historical mode")
            return self._resolve_historical_contract(sym, close_ts, family)
        return self._resolve_live_contract(sym)

    def _resolve_historical_contract(self, symbol: str, close_ts: datetime, family: str) -> RuntimeCandidateContract:
        if self._historical_registry is None:
            raise LookupError("Historical governance registry not loaded")
        requested_month = self._force_model_month or _month_from_close_ts(close_ts)
        entry = self._historical_registry.get_entry(symbol, requested_month, family=family)
        resolved_month = requested_month
        if entry is None:
            fallback_month = self.resolve_missing_historical_month(symbol, requested_month)
            if fallback_month is not None:
                entry = self._historical_registry.get_entry(symbol, fallback_month, family=family)
                resolved_month = fallback_month

        if entry is None:
            available = self._historical_registry.months_for_symbol(symbol)
            avail_txt = ",".join(available) if available else "<none>"
            raise KeyError(
                f"No historical lock for {symbol} month {requested_month} family {family} "
                f"(policy={self._missing_month_policy}). available_months={avail_txt}"
            )

        return RuntimeCandidateContract(
            symbol=symbol,
            model_month=resolved_month,
            cache_key=self.cache_key(symbol, resolved_month, family=family),
            candidates=list(entry.candidates),
            bundle_paths=entry.bundle_paths,
            cap_pips=float(entry.cap_pips),
            source="historical",
            lock_path=str(entry.lock_path),
        )

    def _resolve_live_contract(self, symbol: str) -> RuntimeCandidateContract:
        if self._live_registry is None:
            raise LookupError("Candidate registry not loaded")
        all_candidates = self._live_registry.get_candidates(symbol)
        if not all_candidates:
            raise LookupError(f"No candidates registered for {symbol}")
        # Use the first family's bundle_paths as the "primary" contract metadata.
        # Per-family dispatch happens downstream in server.py.
        first_family = all_candidates[0].family or "unknown"
        bundle_paths = self._live_registry.get_bundle_paths(symbol, first_family)
        if not bundle_paths:
            raise LookupError(f"No bundle paths registered for {symbol}")
        model_month = bundle_paths.model_month or "unknown"
        return RuntimeCandidateContract(
            symbol=symbol,
            model_month=model_month,
            cache_key=self.cache_key(symbol),
            candidates=all_candidates,
            bundle_paths=bundle_paths,
            cap_pips=float(self._live_registry.get_cap_pips(symbol, first_family)),
            source="live",
            lock_path=None,
        )

    def resolve_missing_historical_month(self, symbol: str, requested_month: str) -> str | None:
        """Find fallback month according to governance_missing_month_policy."""
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
