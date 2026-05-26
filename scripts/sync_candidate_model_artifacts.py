#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
from dataclasses import dataclass
from json import JSONDecodeError
from pathlib import Path

from src.behemoth.core.bundle_paths import iter_locks, lock_filename

_MONTH_RE = re.compile(r"^\d{4}-\d{2}$")


@dataclass(frozen=True)
class SyncResult:
    symbol: str
    model_month: str
    status: str
    detail: str


def _sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _iter_locks(lock_dir: Path, symbols: list[str]) -> list[Path]:
    if not symbols:
        return list(iter_locks(lock_dir))
    wanted_names = {lock_filename(symbol) for symbol in symbols}
    return sorted(path for path in iter_locks(lock_dir) if path.name in wanted_names)


def _symbol_from_lock_path(lock_path: Path) -> str:
    for part in lock_path.name.split("_live_lock.json", 1)[:1]:
        if part:
            return part.rsplit("_", 1)[0].upper() if "_" in part else part.upper()
    return ""


def _resolve_artifact_name(raw_path: str) -> str:
    return Path(str(raw_path).strip()).name


def _remove_target_artifacts(*paths: Path) -> None:
    for path in paths:
        if path.exists():
            path.unlink()


def _remove_symbol_targets(target_models_dir: Path, symbol: str) -> None:
    if not symbol:
        return
    for path in target_models_dir.glob(f"{symbol}_model_*"):
        if path.is_file():
            path.unlink()


def _discover_source_symbols(source_models_dir: Path) -> list[str]:
    symbols: set[str] = set()
    for path in source_models_dir.glob("*_model_*.cbm"):
        name = path.name
        if "_model_" not in name:
            continue
        symbol = name.split("_model_", 1)[0].upper().strip()
        if symbol:
            symbols.add(symbol)
    return sorted(symbols)


def _latest_source_artifacts(source_models_dir: Path, symbol: str) -> tuple[str, Path, Path] | None:
    s = str(symbol).upper().strip()
    pairs: list[tuple[str, Path, Path]] = []
    for cbm_path in sorted(source_models_dir.glob(f"{s}_model_*.cbm")):
        month = cbm_path.stem.split("_")[-1]
        if not _MONTH_RE.match(month):
            continue
        thr_path = cbm_path.with_suffix(".json")
        if not thr_path.exists():
            continue
        pairs.append((month, cbm_path, thr_path))
    if not pairs:
        return None
    return max(pairs, key=lambda item: item[0])


def _source_artifacts_for_month(
    source_models_dir: Path,
    symbol: str,
    model_month: str,
) -> tuple[str, Path, Path] | None:
    s = str(symbol).upper().strip()
    month = str(model_month).strip()
    if not _MONTH_RE.match(month):
        return None
    cbm_path = source_models_dir / f"{s}_model_{month}.cbm"
    thr_path = source_models_dir / f"{s}_model_{month}.json"
    if not cbm_path.exists() or not thr_path.exists():
        return None
    return month, cbm_path, thr_path


def run(
    *,
    lock_dir: Path | None,
    source_models_dir: Path,
    target_models_dir: Path,
    symbols: list[str],
    model_month: str | None = None,
) -> int:
    results: list[SyncResult] = []
    requested_symbols = [symbol.upper() for symbol in symbols]
    target_models_dir.mkdir(parents=True, exist_ok=True)

    if lock_dir:
        seen_symbols: set[str] = set()
        for lock_path in _iter_locks(lock_dir, requested_symbols):
            symbol_hint = _symbol_from_lock_path(lock_path)
            if symbol_hint:
                seen_symbols.add(symbol_hint)
            try:
                payload = json.loads(lock_path.read_text(encoding="utf-8"))
            except JSONDecodeError as exc:
                _remove_symbol_targets(target_models_dir, symbol_hint)
                results.append(
                    SyncResult(
                        symbol_hint or "UNKNOWN",
                        "-",
                        "FAIL",
                        f"malformed lock {lock_path}: {exc.msg}",
                    )
                )
                continue
            if not isinstance(payload, dict):
                _remove_symbol_targets(target_models_dir, symbol_hint)
                results.append(
                    SyncResult(symbol_hint or "UNKNOWN", "-", "FAIL", "malformed lock metadata")
                )
                continue

            symbol = str(payload.get("symbol", "")).upper().strip() or symbol_hint
            if symbol:
                seen_symbols.add(symbol)
            artifacts = payload.get("artifacts", {})
            if not isinstance(artifacts, dict):
                _remove_symbol_targets(target_models_dir, symbol)
                results.append(
                    SyncResult(symbol or "UNKNOWN", "-", "FAIL", "malformed lock metadata")
                )
                continue
            month = str(payload.get("deployability", {}).get("model_month", "")).strip()
            cbm_entry = artifacts.get("model_cbm", {})
            thr_entry = artifacts.get("model_threshold_json", {})
            cbm_name = _resolve_artifact_name(cbm_entry.get("path", ""))
            thr_name = _resolve_artifact_name(thr_entry.get("path", ""))
            expected_cbm_sha = str(cbm_entry.get("sha256", "")).strip()
            expected_thr_sha = str(thr_entry.get("sha256", "")).strip()
            target_cbm = target_models_dir / cbm_name if cbm_name else None
            target_thr = target_models_dir / thr_name if thr_name else None

            if not symbol or not month or not cbm_name or not thr_name:
                _remove_symbol_targets(target_models_dir, symbol)
                _remove_target_artifacts(
                    *(path for path in (target_cbm, target_thr) if path is not None)
                )
                results.append(
                    SyncResult(symbol or "UNKNOWN", month, "FAIL", "malformed lock metadata")
                )
                continue
            if not expected_cbm_sha or not expected_thr_sha:
                _remove_symbol_targets(target_models_dir, symbol)
                _remove_target_artifacts(
                    *(path for path in (target_cbm, target_thr) if path is not None)
                )
                results.append(SyncResult(symbol, month, "FAIL", "missing expected hash in lock"))
                continue

            source_cbm = source_models_dir / cbm_name
            source_thr = source_models_dir / thr_name

            if not source_cbm.exists():
                _remove_target_artifacts(target_cbm, target_thr)
                results.append(SyncResult(symbol, month, "FAIL", f"missing source {source_cbm}"))
                continue
            if not source_thr.exists():
                _remove_target_artifacts(target_cbm, target_thr)
                results.append(SyncResult(symbol, month, "FAIL", f"missing source {source_thr}"))
                continue

            got_cbm_sha = _sha(source_cbm)
            got_thr_sha = _sha(source_thr)
            if got_cbm_sha != expected_cbm_sha:
                _remove_target_artifacts(target_cbm, target_thr)
                results.append(
                    SyncResult(
                        symbol,
                        month,
                        "FAIL",
                        f"cbm hash mismatch expected={expected_cbm_sha} actual={got_cbm_sha}",
                    )
                )
                continue
            if got_thr_sha != expected_thr_sha:
                _remove_target_artifacts(target_cbm, target_thr)
                results.append(
                    SyncResult(
                        symbol,
                        month,
                        "FAIL",
                        f"json hash mismatch expected={expected_thr_sha} actual={got_thr_sha}",
                    )
                )
                continue

            shutil.copy2(source_cbm, target_cbm)
            shutil.copy2(source_thr, target_thr)
            if _sha(target_cbm) != expected_cbm_sha or _sha(target_thr) != expected_thr_sha:
                _remove_target_artifacts(target_cbm, target_thr)
                results.append(
                    SyncResult(symbol, month, "FAIL", "copied artifact hash verification failed")
                )
                continue

            results.append(SyncResult(symbol, month, "PASS", f"{source_cbm} -> {target_models_dir}"))

        for symbol in requested_symbols:
            if symbol not in seen_symbols:
                _remove_symbol_targets(target_models_dir, symbol)
                results.append(
                    SyncResult(
                        symbol,
                        "-",
                        "FAIL",
                        f"missing live lock {lock_dir / f'{symbol.lower()}_oco_live_lock.json'}",
                    )
                )
    else:
        symbols_to_sync = requested_symbols or _discover_source_symbols(source_models_dir)
        for symbol in symbols_to_sync:
            resolved = (
                _source_artifacts_for_month(source_models_dir, symbol, model_month)
                if model_month
                else _latest_source_artifacts(source_models_dir, symbol)
            )
            if resolved is None:
                _remove_symbol_targets(target_models_dir, symbol)
                results.append(
                    SyncResult(
                        symbol,
                        str(model_month or "-"),
                        "FAIL",
                        f"missing source artifacts for {symbol}"
                        f"{f' {model_month}' if model_month else ''} in {source_models_dir}",
                    )
                )
                continue

            month, source_cbm, source_thr = resolved
            target_cbm = target_models_dir / source_cbm.name
            target_thr = target_models_dir / source_thr.name
            shutil.copy2(source_cbm, target_cbm)
            shutil.copy2(source_thr, target_thr)
            if _sha(target_cbm) != _sha(source_cbm) or _sha(target_thr) != _sha(source_thr):
                _remove_target_artifacts(target_cbm, target_thr)
                results.append(
                    SyncResult(symbol, month, "FAIL", "copied artifact hash verification failed")
                )
                continue

            results.append(SyncResult(symbol, month, "PASS", f"{source_cbm} -> {target_models_dir}"))

    for row in results:
        print(
            f"[candidate-sync] {row.symbol} {row.model_month} {row.status} {row.detail}", flush=True
        )

    return 0 if results and all(row.status == "PASS" for row in results) else 1


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lock-dir", default="")
    parser.add_argument("--model-month", default="")
    parser.add_argument("--source-models-dir", default="models/oco")
    parser.add_argument("--target-models-dir", default="models/oco_dukascopy_candidate")
    parser.add_argument("--symbols", default="")
    args = parser.parse_args()

    symbols = [symbol.strip().upper() for symbol in str(args.symbols).split(",") if symbol.strip()]
    raise SystemExit(
        run(
            lock_dir=Path(args.lock_dir) if str(args.lock_dir).strip() else None,
            source_models_dir=Path(args.source_models_dir),
            target_models_dir=Path(args.target_models_dir),
            symbols=symbols,
            model_month=str(args.model_month).strip() or None,
        )
    )


if __name__ == "__main__":
    main()
