#!/usr/bin/env python3
"""Build the frozen month-scoped candidate bundle for monthly recertification."""

from __future__ import annotations

import argparse
import csv
import json
import shutil
import subprocess
from datetime import date
from pathlib import Path

DEFAULT_SYMBOLS = "EURUSD,GBPUSD,USDJPY,USDCHF,AUDUSD,USDCAD"
MONTHLY_BUILD_ROOT = Path("configs/research/governance/oco_candidate_builds")
BUNDLE_MODELS_SUBDIR = Path("models/oco_dukascopy_candidate")


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _validate_model_month(value: str) -> str:
    try:
        date.fromisoformat(f"{value}-01")
    except ValueError as exc:
        raise SystemExit(f"[monthly-build] invalid --model-month: {value}") from exc
    return value


def _derive_model_month(override: str | None = None) -> str:
    if override:
        return _validate_model_month(override)
    today = date.today()
    if today.month == 1:
        return _validate_model_month(f"{today.year - 1:04d}-12")
    return _validate_model_month(f"{today.year:04d}-{today.month - 1:02d}")


def _run_step(cmd: list[str], label: str) -> None:
    print(f"[monthly-build] {label}", flush=True)
    result = subprocess.run(cmd, cwd=_repo_root())
    if result.returncode != 0:
        raise SystemExit(f"[monthly-build] {label} failed (rc={result.returncode})")


def _materialize_bundle_models(bundle_dir: Path) -> None:
    bundle_models_dir = bundle_dir / BUNDLE_MODELS_SUBDIR
    bundle_models_dir.mkdir(parents=True, exist_ok=True)
    rewritten_paths: dict[str, tuple[Path, Path]] = {}

    for lock_path in sorted(bundle_dir.glob("*_oco_live_lock.json")):
        manifest = json.loads(lock_path.read_text(encoding="utf-8"))
        symbol = str(manifest.get("symbol", "")).upper().strip()
        artifacts = manifest.setdefault("artifacts", {})
        cbm_src = Path(str(artifacts.get("model_cbm_path", "")).strip())
        thr_src = Path(str(artifacts.get("model_threshold_json_path", "")).strip())
        if (not symbol) or (not cbm_src.exists()) or (not thr_src.exists()):
            raise SystemExit(
                f"[monthly-build] bundle manifest has missing model artifacts: {lock_path}"
            )
        cbm_dst = bundle_models_dir / cbm_src.name
        thr_dst = bundle_models_dir / thr_src.name
        shutil.copy2(cbm_src, cbm_dst)
        shutil.copy2(thr_src, thr_dst)
        artifacts["model_cbm_path"] = str(cbm_dst)
        artifacts["model_threshold_json_path"] = str(thr_dst)
        lock_path.write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        rewritten_paths[symbol] = (cbm_dst, thr_dst)

    index_path = bundle_dir.parent / "index.csv"
    if not index_path.exists():
        raise SystemExit(f"[monthly-build] bundle index.csv not found: {index_path}")

    rows = list(csv.DictReader(index_path.open()))
    columns = rows[0].keys() if rows else []
    for row in rows:
        symbol = str(row.get("symbol", "")).upper().strip()
        month = str(row.get("month", "")).strip()
        if month != bundle_dir.name or symbol not in rewritten_paths:
            continue
        cbm_dst, thr_dst = rewritten_paths[symbol]
        row["model_cbm_path"] = str(cbm_dst)
        row["threshold_json_path"] = str(thr_dst)
    with index_path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--model-month", help="Override model month YYYY-MM (default: last complete month)"
    )
    args = parser.parse_args()

    model_month = _derive_model_month(args.model_month)
    print(f"[monthly-build] building bundle for {model_month}", flush=True)

    _run_step(
        [
            "uv",
            "run",
            "python",
            "scripts/sync_candidate_model_artifacts.py",
            "--lock-dir",
            "configs/research/governance/oco",
            "--source-models-dir",
            "models/oco",
            "--target-models-dir",
            "models/oco_dukascopy_candidate",
            "--symbols",
            DEFAULT_SYMBOLS,
        ],
        "step 1/2: sync_candidate_model_artifacts",
    )
    _run_step(
        [
            "uv",
            "run",
            "python",
            "scripts/freeze_oco_historical_governance.py",
            "--allow-dirty",
            "--symbols",
            DEFAULT_SYMBOLS,
            "--out-dir",
            "configs/research/governance/oco_candidate_builds",
            "--months",
            model_month,
            "--config-dir",
            "configs/research/experiments_dukascopy_candidate",
            "--analysis-dir",
            "data/analysis/tick_opportunity_mining_dukascopy_candidate",
            "--models-dir",
            "models/oco_dukascopy_candidate",
        ],
        "step 2/2: freeze_oco_historical_governance",
    )
    bundle_dir = _repo_root() / MONTHLY_BUILD_ROOT / model_month
    print("[monthly-build] step 3/3: materialize_bundle_models", flush=True)
    _materialize_bundle_models(bundle_dir)


if __name__ == "__main__":
    main()
