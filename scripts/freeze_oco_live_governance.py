#!/usr/bin/env python3
"""Freeze OCO live governance artifacts for deployment hardening.

Creates per-symbol immutable lock manifests containing:
- locked state universe (from reduced-core states CSV),
- config fingerprints (WFO + reduced-core config),
- data/artifact fingerprints,
- retrain cadence policy.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

try:
    import yaml
except Exception:
    yaml = None  # type: ignore[assignment]


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _git_cmd(args: list[str]) -> str | None:
    try:
        out = subprocess.check_output(["git", *args], stderr=subprocess.DEVNULL)
        return out.decode().strip()
    except Exception:
        return None


def _git_info() -> dict[str, Any]:
    return {
        "commit": _git_cmd(["rev-parse", "HEAD"]),
        "branch": _git_cmd(["rev-parse", "--abbrev-ref", "HEAD"]),
        "dirty": bool(_git_cmd(["status", "--porcelain"])),
    }


def _load_yaml(path: Path) -> dict[str, Any]:
    if yaml is None:
        raise RuntimeError("PyYAML required")
    if not path.exists():
        raise FileNotFoundError(path)
    obj = yaml.safe_load(path.read_text(encoding="utf-8"))
    if obj is None:
        return {}
    if not isinstance(obj, dict):
        raise ValueError(f"YAML root must be mapping: {path}")
    return dict(obj)


def _split_csv(raw: str) -> list[str]:
    return [x.strip().upper() for x in str(raw).split(",") if x.strip()]


def _pick_first_existing(*paths: Path) -> Path:
    for p in paths:
        if p.exists():
            return p
    return paths[0]


def _default_paths(symbol: str) -> dict[str, Path]:
    s = str(symbol).upper().strip()
    sl = s.lower()
    if s == "EURUSD":
        return {
            "wfo_config": Path("configs/research/experiments/eurusd_tick_opportunity_monthly_wfo_oco_fullcap_2025.yaml"),
            "reduced_config": Path("configs/research/experiments/eurusd_oco_reduced_core_2025.yaml"),
            "reduced_states": Path("data/analysis/tick_opportunity_mining/reduced_core/EURUSD_oco_reduced_states.csv"),
            "tick_exact_summary": _pick_first_existing(
                Path("data/analysis/tick_opportunity_mining/reduced_core/EURUSD_oco_tick_exact_summary.csv"),
                Path("data/analysis/tick_opportunity_mining/reduced_core_rolling/EURUSD_oco_tick_exact_summary.csv"),
            ),
            "predictions": Path("data/analysis/tick_opportunity_mining/wfo_2025_m3to1_oco_fullcap/EURUSD_oco_monthly_predictions.parquet"),
        }
    if s == "GBPUSD":
        return {
            "wfo_config": Path("configs/research/experiments/gbpusd_tick_opportunity_monthly_wfo_oco_fullcap_2025.yaml"),
            "reduced_config": Path("configs/research/experiments/gbpusd_oco_reduced_core_2025.yaml"),
            "reduced_states": Path("data/analysis/tick_opportunity_mining/reduced_core_gbpusd/GBPUSD_oco_reduced_states.csv"),
            "tick_exact_summary": _pick_first_existing(
                Path("data/analysis/tick_opportunity_mining/reduced_core_gbpusd/GBPUSD_oco_tick_exact_summary.csv"),
                Path("data/analysis/tick_opportunity_mining/reduced_core_rolling_gbpusd/GBPUSD_oco_tick_exact_summary.csv"),
            ),
            "predictions": Path("data/analysis/tick_opportunity_mining/wfo_2025_m3to1_oco_fullcap_gbpusd/GBPUSD_oco_monthly_predictions.parquet"),
        }
    return {
        "wfo_config": _pick_first_existing(
            Path(f"configs/research/experiments/{sl}_tick_opportunity_monthly_wfo_oco_fullcap_2025.yaml"),
            Path(f"configs/research/experiments/{sl}_tick_opportunity_monthly_wfo_oco_fullcap_rolling_2025.yaml"),
        ),
        "reduced_config": _pick_first_existing(
            Path(f"configs/research/experiments/{sl}_oco_reduced_core_2025.yaml"),
            Path(f"configs/research/experiments/{sl}_oco_reduced_core_rolling_2025.yaml"),
        ),
        "reduced_states": _pick_first_existing(
            Path(f"data/analysis/tick_opportunity_mining/reduced_core_rolling/{s}_oco_reduced_state_schedule.csv"),
            Path(f"data/analysis/tick_opportunity_mining/reduced_core/{s}_oco_reduced_states.csv"),
            Path(f"data/analysis/tick_opportunity_mining/reduced_core_{sl}/{s}_oco_reduced_states.csv"),
        ),
        "tick_exact_summary": _pick_first_existing(
            Path(f"data/analysis/tick_opportunity_mining/reduced_core_rolling/{s}_oco_reduced_summary.csv"),
            Path(f"data/analysis/tick_opportunity_mining/reduced_core/{s}_oco_reduced_summary.csv"),
            Path(f"data/analysis/tick_opportunity_mining/reduced_core_rolling/{s}_oco_tick_exact_summary.csv"),
            Path(f"data/analysis/tick_opportunity_mining/reduced_core/{s}_oco_tick_exact_summary.csv"),
            Path(f"data/analysis/tick_opportunity_mining/reduced_core_rolling_{sl}/{s}_oco_tick_exact_summary.csv"),
            Path(f"data/analysis/tick_opportunity_mining/reduced_core_{sl}/{s}_oco_tick_exact_summary.csv"),
        ),
        "predictions": _pick_first_existing(
            Path(f"data/analysis/tick_opportunity_mining/wfo_2025_m3to1_oco_fullcap/{s}_oco_monthly_predictions.parquet"),
            Path(f"data/analysis/tick_opportunity_mining/wfo_2025_m3to1_oco_fullcap_{sl}/{s}_oco_monthly_predictions.parquet"),
        ),
    }


def _state_universe(states_csv: Path) -> tuple[pd.DataFrame, str]:
    try:
        d = pd.read_csv(states_csv).copy()
    except Exception:
        # File is empty or invalid (e.g. 0 qualifying states)
        raw = "[]"
        sh = hashlib.sha256(raw.encode("utf-8")).hexdigest()
        return pd.DataFrame(), sh

    cols = ["symbol", "bar_ticks", "horizon", "state_id", "family", "barrier_pips", "regime_desc"]
    miss = [c for c in cols if c not in d.columns]
    if miss:
        raw = "[]"
        sh = hashlib.sha256(raw.encode("utf-8")).hexdigest()
        return pd.DataFrame(), sh

    x = d[cols].drop_duplicates().copy()
    x["symbol"] = x["symbol"].astype(str).str.upper()
    x["bar_ticks"] = pd.to_numeric(x["bar_ticks"], errors="coerce").astype("Int64")
    x["horizon"] = pd.to_numeric(x["horizon"], errors="coerce").astype("Int64")
    x["barrier_pips"] = pd.to_numeric(x["barrier_pips"], errors="coerce").astype(float)
    x = x.dropna(subset=["bar_ticks", "horizon", "barrier_pips"]).copy()
    x = x.sort_values(["symbol", "bar_ticks", "horizon", "state_id"]).reset_index(drop=True)
    raw = x.to_json(orient="records", date_format="iso", force_ascii=True)
    sh = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    return x, sh


def _read_tick_exact_ok(path: Path) -> bool | None:
    if not path.exists():
        return None
    d = pd.read_csv(path)
    if d.empty or "overall_pass" not in d.columns:
        return None
    return bool(d.iloc[0]["overall_pass"])


def _build_manifest(
    *,
    symbol: str,
    paths: dict[str, Path],
    cadence_days: int,
    anchor_day_utc: int,
    window_days: int,
) -> dict[str, Any]:
    s = str(symbol).upper().strip()
    for p in paths.values():
        if not p.exists():
            raise FileNotFoundError(p)

    wfo_cfg = _load_yaml(paths["wfo_config"])
    red_cfg = _load_yaml(paths["reduced_config"])
    states, states_sha = _state_universe(paths["reduced_states"])
    now = datetime.now(timezone.utc)

    manifest: dict[str, Any] = {
        "schema_version": 1,
        "frozen_at_utc": now.isoformat(),
        "symbol": s,
        "git": _git_info(),
        "artifacts": {
            "wfo_config_path": str(paths["wfo_config"]),
            "wfo_config_sha256": _sha256(paths["wfo_config"]),
            "reduced_config_path": str(paths["reduced_config"]),
            "reduced_config_sha256": _sha256(paths["reduced_config"]),
            "reduced_states_csv_path": str(paths["reduced_states"]),
            "reduced_states_csv_sha256": _sha256(paths["reduced_states"]),
            "predictions_path": str(paths["predictions"]),
            "predictions_sha256": _sha256(paths["predictions"]),
            "tick_exact_summary_path": str(paths["tick_exact_summary"]),
            "tick_exact_summary_sha256": _sha256(paths["tick_exact_summary"]),
            "tick_exact_overall_pass": _read_tick_exact_ok(paths["tick_exact_summary"]),
        },
        "locked_runtime": {
            "locked_quantile": float(red_cfg.get("locked_quantile", 0.9)),
            "selection_mode": str(red_cfg.get("selection_mode", "auto")),
            "family_keep": str(red_cfg.get("family_keep", "")),
            "barrier_keep": str(red_cfg.get("barrier_keep", "")),
            "horizon_keep": str(red_cfg.get("horizon_keep", "")),
            "threshold_mode": str(wfo_cfg.get("threshold_mode", "")),
            "rolling_threshold_days": int(wfo_cfg.get("rolling_threshold_days", 0)),
            "rolling_threshold_min_history": int(wfo_cfg.get("rolling_threshold_min_history", 0)),
            "execution_quantile": float(wfo_cfg.get("execution_quantile", 0.9)),
            "oco_hold_mode": str(wfo_cfg.get("oco_hold_mode", "")),
            "oco_include_no_touch": bool(wfo_cfg.get("oco_include_no_touch", True)),
        },
        "state_universe": {
            "count": int(len(states)),
            "sha256": str(states_sha),
            "rows": json.loads(states.to_json(orient="records")),
        },
        "retrain_policy": {
            "mode": "calendar_window",
            "cadence_days": int(cadence_days),
            "anchor_day_utc": int(anchor_day_utc),
            "window_days": int(window_days),
        },
    }
    return manifest


def run(
    *,
    symbols: list[str],
    out_dir: Path,
    cadence_days: int,
    anchor_day_utc: int,
    window_days: int,
) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    out_paths: list[Path] = []
    for s in symbols:
        paths = _default_paths(s)
        manifest = _build_manifest(
            symbol=s,
            paths=paths,
            cadence_days=int(cadence_days),
            anchor_day_utc=int(anchor_day_utc),
            window_days=int(window_days),
        )
        mp = out_dir / f"{str(s).lower()}_oco_live_lock.json"
        mp.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")

        st = pd.DataFrame(manifest["state_universe"]["rows"])
        sp = out_dir / f"{str(s).lower()}_oco_allowed_states.csv"
        st.to_csv(sp, index=False)
        out_paths.extend([mp, sp])
        print(f"wrote: {mp}")
        print(f"wrote: {sp}")
    return out_paths


def main() -> None:
    p = argparse.ArgumentParser(description="Freeze OCO live governance artifacts")
    p.add_argument("--symbols", default="EURUSD,GBPUSD")
    p.add_argument("--out-dir", default="configs/research/governance/oco")
    p.add_argument("--policy-config", default="configs/research/governance/oco_live_policy.yaml")
    p.add_argument("--cadence-days", type=int, default=30)
    p.add_argument("--anchor-day-utc", type=int, default=1, help="Calendar day-of-month retrain anchor")
    p.add_argument("--window-days", type=int, default=3, help="Allowed +/- days around anchor for retrain")
    args = p.parse_args()

    syms = _split_csv(str(args.symbols))
    cadence_days = int(args.cadence_days)
    anchor_day_utc = int(args.anchor_day_utc)
    window_days = int(args.window_days)
    pol = Path(str(args.policy_config))
    if pol.exists():
        obj = _load_yaml(pol)
        cadence_days = int(obj.get("cadence_days", cadence_days))
        anchor_day_utc = int(obj.get("anchor_day_utc", anchor_day_utc))
        window_days = int(obj.get("window_days", window_days))
    run(
        symbols=syms,
        out_dir=Path(str(args.out_dir)),
        cadence_days=cadence_days,
        anchor_day_utc=anchor_day_utc,
        window_days=window_days,
    )


if __name__ == "__main__":
    main()
