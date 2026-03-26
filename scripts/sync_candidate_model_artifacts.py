#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from dataclasses import dataclass
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
    wanted = {symbol.upper() for symbol in symbols}
    out: list[Path] = []
    for path in sorted(lock_dir.glob("*_oco_live_lock.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        symbol = str(payload.get("symbol", "")).upper().strip()
        if symbol and (not wanted or symbol in wanted):
            out.append(path)
    return out


def _resolve_artifact_name(raw_path: str) -> str:
    return Path(str(raw_path).strip()).name


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
        payload = json.loads(lock_path.read_text(encoding="utf-8"))
        symbol = str(payload.get("symbol", "")).upper().strip()
        seen_symbols.add(symbol)
        artifacts = payload.get("artifacts", {})
        month = str(artifacts.get("model_month", "")).strip()
        cbm_name = _resolve_artifact_name(artifacts.get("model_cbm_path", ""))
        thr_name = _resolve_artifact_name(artifacts.get("model_threshold_json_path", ""))
        expected_cbm_sha = str(artifacts.get("model_cbm_sha256", "")).strip()
        expected_thr_sha = str(artifacts.get("model_threshold_json_sha256", "")).strip()

        if not symbol or not month or not cbm_name or not thr_name:
            results.append(SyncResult(symbol or "UNKNOWN", month, "FAIL", "malformed lock metadata"))
            continue
        if not expected_cbm_sha or not expected_thr_sha:
            results.append(SyncResult(symbol, month, "FAIL", "missing expected hash in lock"))
            continue

        source_cbm = source_models_dir / cbm_name
        source_thr = source_models_dir / thr_name
        target_cbm = target_models_dir / cbm_name
        target_thr = target_models_dir / thr_name

        if not source_cbm.exists():
            results.append(SyncResult(symbol, month, "FAIL", f"missing source {source_cbm}"))
            continue
        if not source_thr.exists():
            results.append(SyncResult(symbol, month, "FAIL", f"missing source {source_thr}"))
            continue

        got_cbm_sha = _sha(source_cbm)
        got_thr_sha = _sha(source_thr)
        if got_cbm_sha != expected_cbm_sha:
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
            results.append(SyncResult(symbol, month, "FAIL", "copied artifact hash verification failed"))
            continue

        results.append(SyncResult(symbol, month, "PASS", f"{source_cbm} -> {target_models_dir}"))

    for symbol in requested_symbols:
        if symbol not in seen_symbols:
            results.append(
                SyncResult(
                    symbol,
                    "-",
                    "FAIL",
                    f"missing live lock {lock_dir / f'{symbol.lower()}_oco_live_lock.json'}",
                )
            )

    for row in results:
        print(f"[candidate-sync] {row.symbol} {row.model_month} {row.status} {row.detail}", flush=True)

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
