"""Validation helpers for month-scoped historical governance locks."""

from __future__ import annotations

import csv
import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path

_MONTH_RE = re.compile(r"^\d{4}-\d{2}$")

_REQUIRED_ARTIFACT_KEYS: list[tuple[str, str, str]] = [
    ("wfo_config", "wfo_config_path", "wfo_config_sha256"),
    ("reduced_config", "reduced_config_path", "reduced_config_sha256"),
    ("reduced_states", "reduced_states_csv_path", "reduced_states_csv_sha256"),
    ("predictions", "predictions_path", "predictions_sha256"),
    ("model_cbm", "model_cbm_path", "model_cbm_sha256"),
    ("model_threshold_json", "model_threshold_json_path", "model_threshold_json_sha256"),
    ("tick_exact_summary", "tick_exact_summary_path", "tick_exact_summary_sha256"),
    ("reduced_summary", "reduced_summary_path", "reduced_summary_sha256"),
]


@dataclass(frozen=True)
class HistoricalGovernanceCheck:
    name: str
    ok: bool
    detail: str
    symbol: str = ""
    month: str = ""
    lock_path: str = ""


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _sha256_cached(path: Path, cache: dict[str, str]) -> str:
    key = str(path)
    if key not in cache:
        cache[key] = _sha256(path)
    return cache[key]


def _check(
    checks: list[HistoricalGovernanceCheck],
    *,
    name: str,
    ok: bool,
    detail: str,
    symbol: str = "",
    month: str = "",
    lock_path: str = "",
) -> None:
    checks.append(
        HistoricalGovernanceCheck(
            name=name,
            ok=bool(ok),
            detail=str(detail),
            symbol=str(symbol),
            month=str(month),
            lock_path=str(lock_path),
        )
    )


def failed_checks(checks: list[HistoricalGovernanceCheck]) -> list[HistoricalGovernanceCheck]:
    return [c for c in checks if not bool(c.ok)]


def summarize_failures(checks: list[HistoricalGovernanceCheck], limit: int = 12) -> str:
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


def validate_historical_governance(
    history_dir: Path | str,
    *,
    required_symbols: list[str] | None = None,
    required_months: list[str] | None = None,
) -> list[HistoricalGovernanceCheck]:
    p_dir = Path(history_dir)
    if (not p_dir.exists()) or (not p_dir.is_dir()):
        raise FileNotFoundError(f"Historical governance directory not found: {p_dir}")

    checks: list[HistoricalGovernanceCheck] = []
    sha_cache: dict[str, str] = {}

    lock_paths = sorted(p_dir.glob("*/*_oco_live_lock.json"))
    _check(
        checks,
        name="lock_files_present",
        ok=len(lock_paths) > 0,
        detail=f"history_dir={p_dir} lock_files={len(lock_paths)}",
    )

    lock_keys: set[tuple[str, str]] = set()
    lock_dupes: set[tuple[str, str]] = set()

    for lock_path in lock_paths:
        month = lock_path.parent.name.strip()
        lock_txt = str(lock_path)
        _check(
            checks,
            name="lock_parent_month_format",
            ok=bool(_MONTH_RE.match(month)),
            detail=f"parent_month={month!r}",
            month=month,
            lock_path=lock_txt,
        )

        try:
            lock = json.loads(lock_path.read_text(encoding="utf-8"))
        except Exception as exc:
            _check(
                checks,
                name="lock_json_parse",
                ok=False,
                detail=f"error={exc}",
                month=month,
                lock_path=lock_txt,
            )
            continue

        symbol = str(lock.get("symbol", "")).upper().strip()
        _check(
            checks,
            name="lock_symbol_present",
            ok=bool(symbol),
            detail=f"symbol={symbol!r}",
            symbol=symbol,
            month=month,
            lock_path=lock_txt,
        )
        if not symbol:
            continue

        key = (symbol, month)
        if key in lock_keys:
            lock_dupes.add(key)
        else:
            lock_keys.add(key)

        artifacts = lock.get("artifacts", {})
        if not isinstance(artifacts, dict):
            artifacts = {}
        model_month = str(artifacts.get("model_month", "")).strip()
        _check(
            checks,
            name="model_month_format",
            ok=bool(_MONTH_RE.match(model_month)),
            detail=f"model_month={model_month!r}",
            symbol=symbol,
            month=month,
            lock_path=lock_txt,
        )
        _check(
            checks,
            name="model_month_matches_parent_month",
            ok=(model_month == month),
            detail=f"model_month={model_month!r} parent_month={month!r}",
            symbol=symbol,
            month=month,
            lock_path=lock_txt,
        )

        for label, path_key, hash_key in _REQUIRED_ARTIFACT_KEYS:
            path_txt = str(artifacts.get(path_key, "")).strip()
            hash_txt = str(artifacts.get(hash_key, "")).strip()
            _check(
                checks,
                name=f"{label}_artifact_path_present",
                ok=bool(path_txt),
                detail=f"{path_key}={path_txt!r}",
                symbol=symbol,
                month=month,
                lock_path=lock_txt,
            )
            _check(
                checks,
                name=f"{label}_artifact_hash_present",
                ok=bool(hash_txt),
                detail=f"{hash_key}={hash_txt!r}",
                symbol=symbol,
                month=month,
                lock_path=lock_txt,
            )
            if not path_txt or not hash_txt:
                continue
            p = Path(path_txt)
            _check(
                checks,
                name=f"{label}_artifact_exists",
                ok=(p.exists() and p.is_file()),
                detail=f"path={p}",
                symbol=symbol,
                month=month,
                lock_path=lock_txt,
            )
            if not p.exists() or not p.is_file():
                continue
            got = _sha256_cached(p, sha_cache)
            _check(
                checks,
                name=f"{label}_artifact_hash_match",
                ok=(got == hash_txt),
                detail=f"expected={hash_txt} got={got}",
                symbol=symbol,
                month=month,
                lock_path=lock_txt,
            )

        rows = lock.get("state_universe", {}).get("rows", [])
        _check(
            checks,
            name="state_universe_rows_nonempty",
            ok=isinstance(rows, list) and len(rows) > 0,
            detail=f"rows={len(rows) if isinstance(rows, list) else 'invalid'}",
            symbol=symbol,
            month=month,
            lock_path=lock_txt,
        )
        if isinstance(rows, list) and rows:
            symbol_mismatch = 0
            for row in rows:
                row_symbol = str((row or {}).get("symbol", "")).upper().strip()
                if row_symbol != symbol:
                    symbol_mismatch += 1
            _check(
                checks,
                name="state_universe_symbol_consistent",
                ok=(symbol_mismatch == 0),
                detail=f"mismatched_rows={symbol_mismatch}",
                symbol=symbol,
                month=month,
                lock_path=lock_txt,
            )

        backtest = lock.get("historical_backtest", {})
        target_month = ""
        if isinstance(backtest, dict):
            target_month = str(backtest.get("target_month", "")).strip()
        _check(
            checks,
            name="historical_target_month_matches_parent",
            ok=(target_month == month),
            detail=f"target_month={target_month!r} parent_month={month!r}",
            symbol=symbol,
            month=month,
            lock_path=lock_txt,
        )

    _check(
        checks,
        name="lock_symbol_month_unique",
        ok=(len(lock_dupes) == 0),
        detail=f"duplicate_keys={sorted(lock_dupes)}",
    )

    index_path = p_dir / "index.csv"
    _check(
        checks,
        name="index_csv_exists",
        ok=index_path.exists(),
        detail=f"index={index_path}",
    )
    index_keys: set[tuple[str, str]] = set()
    index_dupes: set[tuple[str, str]] = set()
    if index_path.exists():
        with index_path.open("r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            rows = list(reader)
            _check(
                checks,
                name="index_csv_rows_present",
                ok=len(rows) > 0,
                detail=f"rows={len(rows)}",
            )
            for row in rows:
                sym = str(row.get("symbol", "")).upper().strip()
                mon = str(row.get("month", "")).strip()
                k = (sym, mon)
                if k in index_keys:
                    index_dupes.add(k)
                else:
                    index_keys.add(k)
                lp = str(row.get("lock_path", "")).strip()
                sp = str(row.get("allowed_states_path", "")).strip()
                _check(
                    checks,
                    name="index_lock_path_exists",
                    ok=bool(lp) and Path(lp).exists(),
                    detail=f"lock_path={lp!r}",
                    symbol=sym,
                    month=mon,
                )
                _check(
                    checks,
                    name="index_states_path_exists",
                    ok=bool(sp) and Path(sp).exists(),
                    detail=f"allowed_states_path={sp!r}",
                    symbol=sym,
                    month=mon,
                )

    _check(
        checks,
        name="index_symbol_month_unique",
        ok=(len(index_dupes) == 0),
        detail=f"duplicate_keys={sorted(index_dupes)}",
    )
    _check(
        checks,
        name="index_covers_exact_lock_set",
        ok=(index_keys == lock_keys),
        detail=(
            f"index_only={sorted(index_keys - lock_keys)} "
            f"lock_only={sorted(lock_keys - index_keys)}"
        ),
    )

    req_syms = [str(s).upper().strip() for s in (required_symbols or []) if str(s).strip()]
    req_months = [str(m).strip() for m in (required_months or []) if str(m).strip()]
    for sym in req_syms:
        months_for_sym = sorted([m for (s, m) in lock_keys if s == sym])
        _check(
            checks,
            name="required_symbol_present",
            ok=len(months_for_sym) > 0,
            detail=f"symbol={sym} months={months_for_sym}",
            symbol=sym,
        )
        for mon in req_months:
            _check(
                checks,
                name="required_symbol_month_present",
                ok=((sym, mon) in lock_keys),
                detail=f"symbol={sym} month={mon}",
                symbol=sym,
                month=mon,
            )

    return checks
