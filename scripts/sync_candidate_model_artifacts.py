#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from dataclasses import dataclass
from json import JSONDecodeError
from pathlib import Path


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
        return sorted(lock_dir.glob("*_oco_live_lock.json"))
    wanted_names = {f"{symbol.lower()}_oco_live_lock.json" for symbol in symbols}
    return sorted(
        path for path in lock_dir.glob("*_oco_live_lock.json") if path.name in wanted_names
    )


def _symbol_from_lock_path(lock_path: Path) -> str:
    suffix = "_oco_live_lock.json"
    if lock_path.name.endswith(suffix):
        return lock_path.name[: -len(suffix)].upper()
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


def run(
    *,
    lock_dir: Path,
    source_models_dir: Path,
    target_models_dir: Path,
    symbols: list[str],
) -> int:
    results: list[SyncResult] = []
    requested_symbols = [symbol.upper() for symbol in symbols]
    seen_symbols: set[str] = set()
    target_models_dir.mkdir(parents=True, exist_ok=True)

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
            results.append(SyncResult(symbol or "UNKNOWN", "-", "FAIL", "malformed lock metadata"))
            continue
        month = str(artifacts.get("model_month", "")).strip()
        cbm_name = _resolve_artifact_name(artifacts.get("model_cbm_path", ""))
        thr_name = _resolve_artifact_name(artifacts.get("model_threshold_json_path", ""))
        expected_cbm_sha = str(artifacts.get("model_cbm_sha256", "")).strip()
        expected_thr_sha = str(artifacts.get("model_threshold_json_sha256", "")).strip()
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

    for row in results:
        print(
            f"[candidate-sync] {row.symbol} {row.model_month} {row.status} {row.detail}", flush=True
        )

    return 0 if results and all(row.status == "PASS" for row in results) else 1


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lock-dir", default="configs/research/governance/oco")
    parser.add_argument("--source-models-dir", default="models/oco")
    parser.add_argument("--target-models-dir", default="models/oco_dukascopy_candidate")
    parser.add_argument("--symbols", default="")
    args = parser.parse_args()

    symbols = [symbol.strip().upper() for symbol in str(args.symbols).split(",") if symbol.strip()]
    raise SystemExit(
        run(
            lock_dir=Path(args.lock_dir),
            source_models_dir=Path(args.source_models_dir),
            target_models_dir=Path(args.target_models_dir),
            symbols=symbols,
        )
    )


if __name__ == "__main__":
    main()
