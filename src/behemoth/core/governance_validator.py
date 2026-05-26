"""Composable governance validation rules for historical locks.

Encapsulates validation logic for month-scoped historical governance locks,
including artifact validation, index consistency, and state universe checks.
"""
from __future__ import annotations

import csv
import hashlib
import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_MONTH_RE = re.compile(r"^\d{4}-\d{2}$")

_REQUIRED_ARTIFACT_KEYS: list[tuple[str, str, str]] = [
    ("wfo_config", "wfo_config_path", "wfo_config_sha256"),
    ("reduced_config", "reduced_config_path", "reduced_config_sha256"),
    ("reduced_states", "reduced_states_csv_path", "reduced_states_csv_sha256"),
    ("model_cbm", "model_cbm_path", "model_cbm_sha256"),
    ("model_threshold_json", "model_threshold_json_path", "model_threshold_json_sha256"),
    ("tick_exact_summary", "tick_exact_summary_path", "tick_exact_summary_sha256"),
    ("reduced_summary", "reduced_summary_path", "reduced_summary_sha256"),
]


@dataclass(frozen=True)
class Check:
    """Validation check result."""
    name: str
    ok: bool
    detail: str
    symbol: str = ""
    month: str = ""
    lock_path: str = ""


def failed_checks(checks: list[Check]) -> list[Check]:
    """Return failed governance validation checks."""
    return [c for c in checks if not bool(c.ok)]


def summarize_failures(checks: list[Check], limit: int = 12) -> str:
    """Summarize failed governance validation checks for operator surfaces."""
    bad = failed_checks(checks)
    if not bad:
        return ""
    head = bad[: max(1, int(limit))]
    chunks = [
        (
            f"{c.name}"
            + (f" [{c.symbol} {c.month}]" if c.symbol or c.month else "")
            + f": {c.detail}"
        )
        for c in head
    ]
    if len(bad) > len(head):
        chunks.append(f"... and {len(bad) - len(head)} more failures")
    return " | ".join(chunks)


class GovernanceValidator:
    """Validates historical governance locks and index consistency.

    Encapsulates rules for:
    - Lock file structure and artifacts
    - Hash validation
    - Index consistency
    - State universe constraints
    - Required symbol/month coverage
    """

    def __init__(self):
        self._sha_cache: dict[str, str] = {}

    def validate(
        self,
        history_dir: Path | str,
        *,
        required_symbols: list[str] | None = None,
        required_months: list[str] | None = None,
    ) -> list[Check]:
        """Run all validation rules on history directory."""
        p_dir = Path(history_dir)
        if (not p_dir.exists()) or (not p_dir.is_dir()):
            raise FileNotFoundError(f"Historical governance directory not found: {p_dir}")

        checks: list[Check] = []
        self._sha_cache.clear()

        req_sym_set = self._normalize_required_symbols(required_symbols)
        from src.behemoth.core.bundle_paths import iter_locks

        lock_paths = [
            lock_path
            for month_dir in sorted(path for path in p_dir.iterdir() if path.is_dir())
            for lock_path in iter_locks(month_dir)
        ]
        lock_keys, lock_dupes = self._validate_locks(p_dir, lock_paths, req_sym_set, checks)
        self._validate_index(p_dir, lock_keys, lock_dupes, req_sym_set, checks)
        self._validate_required_coverage(req_sym_set, required_months, lock_keys, checks)

        return checks

    def failed_checks(self, checks: list[Check]) -> list[Check]:
        """Return failed checks produced by this validator."""
        return failed_checks(checks)

    def summarize_failures(self, checks: list[Check], limit: int = 12) -> str:
        """Summarize failed checks produced by this validator."""
        return summarize_failures(checks, limit=limit)

    def _validate_locks(
        self,
        history_dir: Path,
        lock_paths: list[Path],
        req_sym_set: set[str] | None,
        checks: list[Check],
    ) -> tuple[set[tuple[str, str]], set[tuple[str, str]]]:
        """Validate lock files and return (lock_keys, lock_dupes)."""
        checks.append(Check(
            name="lock_files_present",
            ok=len(lock_paths) > 0,
            detail=f"history_dir={history_dir} lock_files={len(lock_paths)}",
        ))

        lock_keys: set[tuple[str, str]] = set()
        lock_dupes: set[tuple[str, str]] = set()

        for lock_path in lock_paths:
            month = lock_path.parent.name.strip()
            self._validate_lock_month_format(month, str(lock_path), checks)

            lock = self._parse_lock_file(lock_path, month, checks)
            if lock is None:
                continue

            symbol = str(lock.get("symbol", "")).upper().strip()
            self._validate_lock_symbol(symbol, month, str(lock_path), checks)
            if not symbol:
                continue

            if req_sym_set is not None and symbol not in req_sym_set:
                continue

            key = (symbol, month)
            if key in lock_keys:
                lock_dupes.add(key)
            else:
                lock_keys.add(key)

            artifacts = lock.get("artifacts", {}) or {}
            backtest = lock.get("historical_backtest", {}) or {}
            self._validate_lock_artifacts(symbol, month, str(lock_path), artifacts, backtest, checks)
            self._validate_state_universe(symbol, month, str(lock_path), lock, backtest, checks)
            self._validate_target_month(symbol, month, str(lock_path), backtest, checks)

        checks.append(Check(
            name="lock_symbol_month_unique",
            ok=(len(lock_dupes) == 0),
            detail=f"duplicate_keys={sorted(lock_dupes)}",
        ))

        return lock_keys, lock_dupes

    def _validate_index(
        self,
        history_dir: Path,
        lock_keys: set[tuple[str, str]],
        lock_dupes: set[tuple[str, str]],
        req_sym_set: set[str] | None,
        checks: list[Check],
    ) -> None:
        """Validate index.csv consistency."""
        index_path = history_dir / "index.csv"
        checks.append(Check(
            name="index_csv_exists",
            ok=index_path.exists(),
            detail=f"index={index_path}",
        ))

        if not index_path.exists():
            checks.append(Check(
                name="index_covers_exact_lock_set",
                ok=(set() == lock_keys),
                detail=f"index_only=[] lock_only={sorted(lock_keys)}",
            ))
            return

        index_keys: set[tuple[str, str]] = set()
        index_dupes: set[tuple[str, str]] = set()

        with index_path.open("r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            rows = list(reader)
            checks.append(Check(
                name="index_csv_rows_present",
                ok=len(rows) > 0,
                detail=f"rows={len(rows)}",
            ))

            for row in rows:
                sym = str(row.get("symbol", "")).upper().strip()
                mon = str(row.get("month", "")).strip()
                if req_sym_set is not None and sym not in req_sym_set:
                    continue
                k = (sym, mon)
                if k in index_keys:
                    index_dupes.add(k)
                else:
                    index_keys.add(k)

                lp = str(row.get("lock_path", "")).strip()
                sp = str(row.get("allowed_states_path", "")).strip()
                checks.append(Check(
                    name="index_lock_path_exists",
                    ok=bool(lp) and Path(lp).exists(),
                    detail=f"lock_path={lp!r}",
                    symbol=sym,
                    month=mon,
                ))
                checks.append(Check(
                    name="index_states_path_exists",
                    ok=bool(sp) and Path(sp).exists(),
                    detail=f"allowed_states_path={sp!r}",
                    symbol=sym,
                    month=mon,
                ))

        checks.append(Check(
            name="index_symbol_month_unique",
            ok=(len(index_dupes) == 0),
            detail=f"duplicate_keys={sorted(index_dupes)}",
        ))
        checks.append(Check(
            name="index_covers_exact_lock_set",
            ok=(index_keys == lock_keys),
            detail=(
                f"index_only={sorted(index_keys - lock_keys)} "
                f"lock_only={sorted(lock_keys - index_keys)}"
            ),
        ))

    def _validate_required_coverage(
        self,
        req_sym_set: set[str] | None,
        required_months: list[str] | None,
        lock_keys: set[tuple[str, str]],
        checks: list[Check],
    ) -> None:
        """Validate that required symbols/months are present."""
        if not req_sym_set:
            return

        req_months = [str(m).strip() for m in (required_months or []) if str(m).strip()]
        for sym in req_sym_set:
            months_for_sym = sorted([m for (s, m) in lock_keys if s == sym])
            checks.append(Check(
                name="required_symbol_present",
                ok=len(months_for_sym) > 0,
                detail=f"symbol={sym} months={months_for_sym}",
                symbol=sym,
            ))
            for mon in req_months:
                checks.append(Check(
                    name="required_symbol_month_present",
                    ok=((sym, mon) in lock_keys),
                    detail=f"symbol={sym} month={mon}",
                    symbol=sym,
                    month=mon,
                ))

    def _validate_lock_month_format(
        self,
        month: str,
        lock_path: str,
        checks: list[Check],
    ) -> None:
        """Validate lock parent directory month format."""
        checks.append(Check(
            name="lock_parent_month_format",
            ok=bool(_MONTH_RE.match(month)),
            detail=f"parent_month={month!r}",
            month=month,
            lock_path=lock_path,
        ))

    def _parse_lock_file(
        self,
        lock_path: Path,
        month: str,
        checks: list[Check],
    ) -> dict[str, Any] | None:
        """Parse and validate lock JSON file."""
        try:
            return json.loads(lock_path.read_text(encoding="utf-8"))
        except Exception as exc:
            checks.append(Check(
                name="lock_json_parse",
                ok=False,
                detail=f"error={exc}",
                month=month,
                lock_path=str(lock_path),
            ))
            return None

    def _validate_lock_symbol(
        self,
        symbol: str,
        month: str,
        lock_path: str,
        checks: list[Check],
    ) -> None:
        """Validate lock symbol field."""
        checks.append(Check(
            name="lock_symbol_present",
            ok=bool(symbol),
            detail=f"symbol={symbol!r}",
            symbol=symbol,
            month=month,
            lock_path=lock_path,
        ))

    def _validate_lock_artifacts(
        self,
        symbol: str,
        month: str,
        lock_path: str,
        artifacts: dict[str, Any],
        backtest: dict[str, Any],
        checks: list[Check],
    ) -> None:
        """Validate model month and required artifacts."""
        deploy = backtest if isinstance(backtest, dict) else {}
        model_month = str(deploy.get("model_month", "")).strip()
        historical_deployable = bool(deploy.get("live_deployable", False))
        checks.append(Check(
            name="model_month_format",
            ok=bool(_MONTH_RE.match(model_month)),
            detail=f"model_month={model_month!r}",
            symbol=symbol,
            month=month,
            lock_path=lock_path,
        ))
        checks.append(Check(
            name="model_month_matches_parent_month",
            ok=(model_month == month),
            detail=f"model_month={model_month!r} parent_month={month!r}",
            symbol=symbol,
            month=month,
            lock_path=lock_path,
        ))


        # Validate required artifacts
        for label, path_key, hash_key in _REQUIRED_ARTIFACT_KEYS:
            v2_key = path_key.replace("_path", "").replace("reduced_states_csv", "allowed_states_csv")
            entry = artifacts.get(v2_key, {}) or {}
            path_txt = str(entry.get("path", "")).strip()
            hash_txt = str(entry.get("sha256", "")).strip()
            checks.append(Check(
                name=f"{label}_artifact_path_present",
                ok=bool(path_txt),
                detail=f"{path_key}={path_txt!r}",
                symbol=symbol,
                month=month,
                lock_path=lock_path,
            ))
            checks.append(Check(
                name=f"{label}_artifact_hash_present",
                ok=bool(hash_txt),
                detail=f"{hash_key}={hash_txt!r}",
                symbol=symbol,
                month=month,
                lock_path=lock_path,
            ))
            if not path_txt or not hash_txt:
                continue
            path_txt = str(Path(lock_path).parent / path_txt)
            self._validate_artifact_file(label, path_txt, hash_txt, symbol, month, lock_path, checks)

        # Validate predictions artifact
        pred_entry = artifacts.get("predictions", {}) or {}
        pred_path_txt = str(pred_entry.get("path", "")).strip()
        pred_hash_txt = str(pred_entry.get("sha256", "")).strip()
        if historical_deployable:
            checks.append(Check(
                name="predictions_artifact_path_present",
                ok=bool(pred_path_txt),
                detail=f"predictions_path={pred_path_txt!r}",
                symbol=symbol,
                month=month,
                lock_path=lock_path,
            ))
            checks.append(Check(
                name="predictions_artifact_hash_present",
                ok=bool(pred_hash_txt),
                detail=f"predictions_sha256={pred_hash_txt!r}",
                symbol=symbol,
                month=month,
                lock_path=lock_path,
            ))
            if pred_path_txt and pred_hash_txt:
                pred_path_txt = str(Path(lock_path).parent / pred_path_txt)
                self._validate_artifact_file("predictions", pred_path_txt, pred_hash_txt, symbol, month, lock_path, checks)
        else:
            checks.append(Check(
                name="predictions_artifact_omitted_when_non_deployable",
                ok=(pred_path_txt == "" and pred_hash_txt == ""),
                detail=f"predictions_path={pred_path_txt!r} predictions_sha256={pred_hash_txt!r}",
                symbol=symbol,
                month=month,
                lock_path=lock_path,
            ))

    def _validate_artifact_file(
        self,
        label: str,
        path_txt: str,
        hash_txt: str,
        symbol: str,
        month: str,
        lock_path: str,
        checks: list[Check],
    ) -> None:
        """Validate artifact file existence and hash."""
        p = Path(path_txt)
        checks.append(Check(
            name=f"{label}_artifact_exists",
            ok=(p.exists() and p.is_file()),
            detail=f"path={p}",
            symbol=symbol,
            month=month,
            lock_path=lock_path,
        ))
        if not p.exists() or not p.is_file():
            return
        got = self._sha256_cached(p)
        checks.append(Check(
            name=f"{label}_artifact_hash_match",
            ok=(got == hash_txt),
            detail=f"expected={hash_txt} got={got}",
            symbol=symbol,
            month=month,
            lock_path=lock_path,
        ))

    def _validate_state_universe(
        self,
        symbol: str,
        month: str,
        lock_path: str,
        lock: dict[str, Any],
        backtest: dict[str, Any],
        checks: list[Check],
    ) -> None:
        """Validate state universe constraints."""
        rows = lock.get("state_universe", {}).get("rows", [])
        historical_deployable = bool((backtest or {}).get("live_deployable", False))

        if historical_deployable:
            checks.append(Check(
                name="state_universe_rows_nonempty",
                ok=isinstance(rows, list) and len(rows) > 0,
                detail=f"rows={len(rows) if isinstance(rows, list) else 'invalid'}",
                symbol=symbol,
                month=month,
                lock_path=lock_path,
            ))
        else:
            checks.append(Check(
                name="state_universe_rows_empty_when_non_deployable",
                ok=isinstance(rows, list) and len(rows) == 0,
                detail=f"rows={len(rows) if isinstance(rows, list) else 'invalid'}",
                symbol=symbol,
                month=month,
                lock_path=lock_path,
            ))

        if isinstance(rows, list) and rows:
            symbol_mismatch = 0
            for row in rows:
                row_symbol = str((row or {}).get("symbol", "")).upper().strip()
                if row_symbol != symbol:
                    symbol_mismatch += 1
            checks.append(Check(
                name="state_universe_symbol_consistent",
                ok=(symbol_mismatch == 0),
                detail=f"mismatched_rows={symbol_mismatch}",
                symbol=symbol,
                month=month,
                lock_path=lock_path,
            ))

    def _validate_target_month(
        self,
        symbol: str,
        month: str,
        lock_path: str,
        backtest: dict[str, Any],
        checks: list[Check],
    ) -> None:
        """Validate target month matches parent directory."""
        target_month = str((backtest or {}).get("model_month", "")).strip()
        checks.append(Check(
            name="historical_target_month_matches_parent",
            ok=(target_month == month),
            detail=f"target_month={target_month!r} parent_month={month!r}",
            symbol=symbol,
            month=month,
            lock_path=lock_path,
        ))

    def _normalize_required_symbols(
        self,
        required_symbols: list[str] | None,
    ) -> set[str] | None:
        """Normalize required symbols to uppercase set, or None if empty."""
        if not required_symbols:
            return None
        result = {s.upper().strip() for s in required_symbols if s.strip()}
        return result if result else None

    def _sha256_cached(self, path: Path) -> str:
        """Compute SHA256, using cache to avoid redundant I/O."""
        key = str(path)
        if key not in self._sha_cache:
            h = hashlib.sha256()
            with path.open("rb") as f:
                for chunk in iter(lambda: f.read(1024 * 1024), b""):
                    h.update(chunk)
            self._sha_cache[key] = h.hexdigest()
        return self._sha_cache[key]
