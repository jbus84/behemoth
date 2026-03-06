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


def _symbols_from_registry(path: Path) -> list[str]:
    if not path.exists():
        return []
    obj = _load_yaml(path)
    raw = obj.get("symbols", [])
    if not isinstance(raw, list):
        return []
    out = [str(x).strip().upper() for x in raw if str(x).strip()]
    return list(dict.fromkeys(out))


def _subset_omissions(selected: list[str], universe: list[str]) -> list[str]:
    sel = set(selected)
    uni = set(universe)
    if not sel or not uni:
        return []
    return sorted(list(uni - sel)) if sel < uni else []


def _pick_first_existing(*paths: Path) -> Path:
    for p in paths:
        if p.exists():
            return p
    return paths[0]


def _latest_model_pair(symbol: str, *, models_dir: Path = Path("models/oco")) -> tuple[Path, Path]:
    """Return latest exported model binary and paired threshold JSON for symbol."""
    s = str(symbol).upper().strip()
    candidates = sorted(models_dir.glob(f"{s}_model_*.cbm"))
    if not candidates:
        raise FileNotFoundError(models_dir / f"{s}_model_*.cbm")
    model_path = candidates[-1]
    thr_path = model_path.with_suffix(".json")
    if not thr_path.exists():
        raise FileNotFoundError(thr_path)
    return model_path, thr_path


def _default_paths(symbol: str) -> dict[str, Path]:
    s = str(symbol).upper().strip()
    sl = s.lower()
    return {
        "wfo_config": _pick_first_existing(
            Path(
                f"configs/research/experiments/{sl}_tick_opportunity_monthly_wfo_oco_fullcap_2025.yaml"
            ),
            Path(
                f"configs/research/experiments/{sl}_tick_opportunity_monthly_wfo_oco_fullcap_rolling_2025.yaml"
            ),
        ),
        "reduced_config": _pick_first_existing(
            Path(f"configs/research/experiments/{sl}_oco_reduced_core_2025.yaml"),
            Path(f"configs/research/experiments/{sl}_oco_reduced_core_rolling_2025.yaml"),
        ),
        "reduced_states": _pick_first_existing(
            Path(
                f"data/analysis/tick_opportunity_mining/reduced_core_rolling/{s}_oco_reduced_state_schedule.csv"
            ),
            Path(f"data/analysis/tick_opportunity_mining/reduced_core/{s}_oco_reduced_states.csv"),
            Path(
                f"data/analysis/tick_opportunity_mining/reduced_core_{sl}/{s}_oco_reduced_states.csv"
            ),
        ),
        "tick_exact_summary": _pick_first_existing(
            Path(
                f"data/analysis/tick_opportunity_mining/reduced_core_rolling/{s}_oco_tick_exact_summary.csv"
            ),
            Path(
                f"data/analysis/tick_opportunity_mining/reduced_core/{s}_oco_tick_exact_summary.csv"
            ),
            Path(
                f"data/analysis/tick_opportunity_mining/reduced_core_rolling_{sl}/{s}_oco_tick_exact_summary.csv"
            ),
            Path(
                f"data/analysis/tick_opportunity_mining/reduced_core_{sl}/{s}_oco_tick_exact_summary.csv"
            ),
        ),
        "reduced_summary": _pick_first_existing(
            Path(
                f"data/analysis/tick_opportunity_mining/reduced_core_rolling/{s}_oco_reduced_summary.csv"
            ),
            Path(f"data/analysis/tick_opportunity_mining/reduced_core/{s}_oco_reduced_summary.csv"),
            Path(
                f"data/analysis/tick_opportunity_mining/reduced_core_rolling_{sl}/{s}_oco_reduced_summary.csv"
            ),
            Path(
                f"data/analysis/tick_opportunity_mining/reduced_core_{sl}/{s}_oco_reduced_summary.csv"
            ),
        ),
        "predictions": _pick_first_existing(
            Path(
                f"data/analysis/tick_opportunity_mining/wfo_2025_m3to1_oco_fullcap/{s}_oco_monthly_predictions.parquet"
            ),
            Path(
                f"data/analysis/tick_opportunity_mining/wfo_2025_m3to1_oco_fullcap_{sl}/{s}_oco_monthly_predictions.parquet"
            ),
        ),
        "tick_fill_caps": _pick_first_existing(
            Path(
                f"data/analysis/tick_opportunity_mining/stop_limit_tickfill_fullcap/{s}_stop_limit_tickfill_caps.csv"
            ),
            Path(
                f"data/analysis/tick_opportunity_mining/stop_limit_tickfill/{s}_stop_limit_tickfill_caps.csv"
            ),
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

    if "test_month" in d.columns:
        valid_months = d["test_month"].dropna().unique().tolist()
        if valid_months:
            last_m = sorted(valid_months)[-1]
            d = d[d["test_month"] == last_m].copy()

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
    try:
        d = pd.read_csv(path)
        if d.empty or "overall_pass" not in d.columns:
            return None
        return bool(d.iloc[0]["overall_pass"])
    except Exception:
        return None


def _read_capacity_ok(path: Path) -> bool | None:
    if not path.exists():
        return None
    try:
        d = pd.read_csv(path)
        if d.empty or "capacity_pass_monthly_or_annual" not in d.columns:
            return None
        return bool(d.iloc[0]["capacity_pass_monthly_or_annual"])
    except Exception:
        return None


def _pick_optimal_cap(caps_csv: Path, default: float = 1.2, hard_limit: float = 1.2) -> float:
    """Pick cap that maximizes mean_per_signal_full_overshoot within hard_limit."""
    if not caps_csv.exists():
        return float(default)
    try:
        d = pd.read_csv(caps_csv)
        if d.empty or "mean_per_signal_full_overshoot" not in d.columns:
            return float(default)
        # Only consider caps within our safety bound
        valid = d[d["cap_pips"] <= hard_limit].copy()
        if valid.empty:
            return float(default)
        best = valid.loc[valid["mean_per_signal_full_overshoot"].idxmax()]
        return float(best["cap_pips"])
    except Exception:
        return float(default)


def _build_manifest(
    *,
    symbol: str,
    paths: dict[str, Path],
    cadence_days: int,
    anchor_day_utc: int,
    window_days: int,
    git_snapshot: dict[str, Any],
) -> dict[str, Any]:
    s = str(symbol).upper().strip()
    for p in paths.values():
        if not p.exists():
            raise FileNotFoundError(p)

    wfo_cfg = _load_yaml(paths["wfo_config"])
    red_cfg = _load_yaml(paths["reduced_config"])
    model_cbm, model_thr = _latest_model_pair(s)
    states, states_sha = _state_universe(paths["reduced_states"])
    now = datetime.now(timezone.utc)
    tick_ok = _read_tick_exact_ok(paths["tick_exact_summary"])
    cap_ok = _read_capacity_ok(paths["reduced_summary"])
    model_month = model_cbm.stem.split("_")[-1]

    manifest: dict[str, Any] = {
        "schema_version": 1,
        "frozen_at_utc": now.isoformat(),
        "symbol": s,
        "git": git_snapshot,
        "artifacts": {
            "wfo_config_path": str(paths["wfo_config"]),
            "wfo_config_sha256": _sha256(paths["wfo_config"]),
            "reduced_config_path": str(paths["reduced_config"]),
            "reduced_config_sha256": _sha256(paths["reduced_config"]),
            "reduced_states_csv_path": str(paths["reduced_states"]),
            "reduced_states_csv_sha256": _sha256(paths["reduced_states"]),
            "predictions_path": str(paths["predictions"]),
            "predictions_sha256": _sha256(paths["predictions"]),
            "model_cbm_path": str(model_cbm),
            "model_cbm_sha256": _sha256(model_cbm),
            "model_threshold_json_path": str(model_thr),
            "model_threshold_json_sha256": _sha256(model_thr),
            "model_month": str(model_month),
            "tick_exact_summary_path": str(paths["tick_exact_summary"]),
            "tick_exact_summary_sha256": _sha256(paths["tick_exact_summary"]),
            "tick_exact_overall_pass": tick_ok,
            "reduced_summary_path": str(paths["reduced_summary"]),
            "reduced_summary_sha256": _sha256(paths["reduced_summary"]),
            "capacity_overall_pass": cap_ok,
            # Unknown (`None`) should not silently pass deployability.
            "live_deployable": (tick_ok is True) and (cap_ok is True),
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
            "production_cap_pips": _pick_optimal_cap(
                paths["tick_fill_caps"],
                default=float(wfo_cfg.get("production_cap_pips", 1.2)),
                hard_limit=1.2 # Safety bound enforced by Governance
            ),
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
    allow_dirty: bool,
) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    git_snapshot = _git_info()
    if (not bool(allow_dirty)) and bool(git_snapshot.get("dirty", True)):
        raise RuntimeError(
            "Refusing to freeze from a dirty git worktree. "
            "Commit/stash changes first, or pass --allow-dirty."
        )
    out_paths: list[Path] = []
    for s in symbols:
        paths = _default_paths(s)
        manifest = _build_manifest(
            symbol=s,
            paths=paths,
            cadence_days=int(cadence_days),
            anchor_day_utc=int(anchor_day_utc),
            window_days=int(window_days),
            git_snapshot=git_snapshot,
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
    default_symbols = "EURUSD,GBPUSD,USDJPY,USDCHF,AUDUSD,USDCAD"
    p = argparse.ArgumentParser(description="Freeze OCO live governance artifacts")
    p.add_argument(
        "--symbols",
        default="",
        help=(
            "Comma-separated symbols. If omitted, symbols are loaded from "
            "--registry-yaml (fallback to active six-symbol default)."
        ),
    )
    p.add_argument("--out-dir", default="configs/research/governance/oco")
    p.add_argument("--policy-config", default="configs/research/governance/oco_live_policy.yaml")
    p.add_argument(
        "--registry-yaml",
        default="configs/research/governance/oco_rule_universe_registry.yaml",
        help="Rule-universe registry used as default symbol source.",
    )
    p.add_argument("--cadence-days", type=int, default=30)
    p.add_argument(
        "--anchor-day-utc", type=int, default=1, help="Calendar day-of-month retrain anchor"
    )
    p.add_argument(
        "--window-days", type=int, default=3, help="Allowed +/- days around anchor for retrain"
    )
    p.add_argument(
        "--allow-dirty",
        action="store_true",
        help="Allow freeze from a dirty git worktree (not recommended).",
    )
    args = p.parse_args()

    reg_path = Path(str(args.registry_yaml))
    registry_symbols = _symbols_from_registry(reg_path)
    explicit_symbols = bool(str(args.symbols).strip())
    if explicit_symbols:
        syms = _split_csv(str(args.symbols))
        omitted = _subset_omissions(syms, registry_symbols)
        if omitted:
            print(
                "warning: --symbols is a subset of registry symbols; omitted="
                + ",".join(omitted)
            )
    elif registry_symbols:
        syms = registry_symbols
    else:
        syms = _split_csv(default_symbols)
        print(
            "warning: registry symbols unavailable; falling back to built-in active default symbols"
        )
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
        allow_dirty=bool(args.allow_dirty),
    )


if __name__ == "__main__":
    main()
