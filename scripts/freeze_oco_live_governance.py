#!/usr/bin/env python3
"""Freeze OCO live governance artifacts for deployment hardening.

Creates per-symbol immutable lock manifests containing:
- locked state universe (from reduced-core states CSV),
- config fingerprints (WFO + reduced-core config),
- data/artifact fingerprints,
- retrain cadence policy.

Emits schema_version: 3 bundles per ADR 0001 and ADR 0002:
docs/adr/0001-deterministic-month-bundles.md
docs/adr/0002-multi-family-bundle-contract.md
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.behemoth.core.bundle_paths import (  # noqa: E402
    bundle_layout_for,
    lock_filename,
    sha256_file,
)

try:
    import yaml
except Exception:
    yaml = None  # type: ignore[assignment]


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _repo_relative_or_abs(path: Path, repo_root: Path) -> Path:
    try:
        return path.relative_to(repo_root)
    except ValueError:
        return path


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


def _sync_threshold_json_runtime_fields(threshold_json_path: Path, wfo_cfg: dict[str, Any]) -> None:
    data = json.loads(threshold_json_path.read_text(encoding="utf-8"))
    updates = {
        "threshold_source": str(wfo_cfg.get("threshold_mode", "")).strip(),
        "rolling_threshold_days": int(wfo_cfg.get("rolling_threshold_days", 0)),
        "rolling_threshold_min_history": int(wfo_cfg.get("rolling_threshold_min_history", 0)),
        "execution_quantile": float(wfo_cfg.get("execution_quantile", 0.9)),
        "oco_hold_mode": str(wfo_cfg.get("oco_hold_mode", "")),
        "oco_include_no_touch": bool(wfo_cfg.get("oco_include_no_touch", True)),
    }
    changed = False
    for key, value in updates.items():
        if data.get(key) != value:
            data[key] = value
            changed = True
    if changed:
        threshold_json_path.write_text(
            json.dumps(data, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )


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


def _model_date_key(p: Path) -> datetime:
    """Parse YYYY-MM suffix from a model filename for robust date-order sorting."""
    m = re.search(r"(\d{4}-\d{2})$", p.stem)
    if m:
        try:
            return datetime.strptime(m.group(1), "%Y-%m")
        except ValueError:
            pass
    return datetime.min  # unparseable names sort first, never win


def _latest_model_pair(symbol: str, *, models_dir: Path = Path("models/oco")) -> tuple[Path, Path]:
    """Return latest exported model binary and paired threshold JSON for symbol."""
    s = str(symbol).upper().strip()
    raw = list(models_dir.glob(f"{s}_model_*.cbm"))
    if not raw:
        raise FileNotFoundError(models_dir / f"{s}_model_*.cbm")
    model_path = sorted(raw, key=_model_date_key)[-1]
    thr_path = model_path.with_suffix(".json")
    if not thr_path.exists():
        raise FileNotFoundError(thr_path)
    return model_path, thr_path


def _default_paths(
    symbol: str,
    *,
    config_dir: Path = Path("configs/research/experiments"),
    analysis_dir: Path = Path("data/analysis/tick_opportunity_mining"),
) -> dict[str, Path]:
    s = str(symbol).upper().strip()
    sl = s.lower()
    return {
        "wfo_config": _pick_first_existing(
            config_dir / f"{sl}_tick_opportunity_monthly_wfo_oco_fullcap.yaml",
            config_dir / f"{sl}_tick_opportunity_monthly_wfo_oco_fullcap_rolling.yaml",
        ),
        "reduced_config": _pick_first_existing(
            config_dir / f"{sl}_oco_reduced_core.yaml",
            config_dir / f"{sl}_oco_reduced_core_rolling.yaml",
        ),
        "reduced_states": _pick_first_existing(
            analysis_dir / "reduced_core_rolling" / f"{s}_oco_reduced_state_schedule.csv",
            analysis_dir / "reduced_core" / f"{s}_oco_reduced_states.csv",
            analysis_dir / f"reduced_core_{sl}" / f"{s}_oco_reduced_states.csv",
        ),
        "tick_exact_summary": _pick_first_existing(
            analysis_dir / "reduced_core_rolling" / f"{s}_oco_tick_exact_summary.csv",
            analysis_dir / "reduced_core" / f"{s}_oco_tick_exact_summary.csv",
            analysis_dir / f"reduced_core_rolling_{sl}" / f"{s}_oco_tick_exact_summary.csv",
            analysis_dir / f"reduced_core_{sl}" / f"{s}_oco_tick_exact_summary.csv",
        ),
        "reduced_summary": _pick_first_existing(
            analysis_dir / "reduced_core_rolling" / f"{s}_oco_reduced_summary.csv",
            analysis_dir / "reduced_core" / f"{s}_oco_reduced_summary.csv",
            analysis_dir / f"reduced_core_rolling_{sl}" / f"{s}_oco_reduced_summary.csv",
            analysis_dir / f"reduced_core_{sl}" / f"{s}_oco_reduced_summary.csv",
        ),
        "predictions": _pick_first_existing(
            analysis_dir / "wfo_m3to1_oco_fullcap" / f"{s}_oco_monthly_predictions.parquet",
            analysis_dir / f"wfo_m3to1_oco_fullcap_{sl}" / f"{s}_oco_monthly_predictions.parquet",
        ),
        "tick_fill_caps": _pick_first_existing(
            analysis_dir / "stop_limit_tickfill_fullcap" / f"{s}_stop_limit_tickfill_caps.csv",
            analysis_dir / "stop_limit_tickfill" / f"{s}_stop_limit_tickfill_caps.csv",
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


def _deploy_verdict(state_count: int) -> str:
    """Canonical deploy verdict: GO if the symbol has >=1 deployable state,
    NO_GO if the universe is empty (a no-trade symbol)."""
    return "GO" if int(state_count) >= 1 else "NO_GO"


def _build_manifest(
    *,
    symbol: str,
    paths: dict[str, Path],
    out_dir: Path,
    family: str = "oco_first_touch",
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
    _sync_threshold_json_runtime_fields(model_thr, wfo_cfg)
    states, states_sha = _state_universe(paths["reduced_states"])
    now = datetime.now(timezone.utc)
    tick_ok = _read_tick_exact_ok(paths["tick_exact_summary"])
    cap_ok = _read_capacity_ok(paths["reduced_summary"])
    model_month = model_cbm.stem.split("_")[-1]

    fmt = {"symbol_lower": s.lower(), "symbol_upper": s, "month": model_month}
    file_map: dict[str, Path] = {
        "predictions": paths["predictions"],
        "allowed_states_csv": paths["reduced_states"],
        "model_cbm": model_cbm,
        "model_threshold_json": model_thr,
        "wfo_config": paths["wfo_config"],
        "reduced_config": paths["reduced_config"],
        "reduced_summary": paths["reduced_summary"],
        "tick_exact_summary": paths["tick_exact_summary"],
    }

    artifacts: dict[str, dict[str, str]] = {}
    provenance: dict[str, dict[str, str]] = {}
    repo_root = _repo_root().resolve()
    out_dir = out_dir.resolve()

    for spec in bundle_layout_for(family):
        source = file_map.get(spec.v2_key)
        if source is None or not source.exists():
            if spec.required:
                raise FileNotFoundError(f"required artifact {spec.v2_key}: {source}")
            continue
        target_rel = spec.target_relpath_template.format(**fmt)
        target_abs = out_dir / target_rel
        target_abs.parent.mkdir(parents=True, exist_ok=True)
        if source.resolve() != target_abs.resolve():
            shutil.copy2(source, target_abs)
        sha = sha256_file(target_abs)
        artifacts[spec.v2_key] = {"path": target_rel, "sha256": sha}
        try:
            source.resolve().relative_to(out_dir)
        except ValueError:
            try:
                origin_rel = source.resolve().relative_to(repo_root).as_posix()
            except ValueError:
                origin_rel = str(source.resolve())
            provenance[spec.v2_key] = {"origin": origin_rel, "origin_sha256": sha}

    deployability = {
        "live_deployable": (tick_ok is True) and (cap_ok is True),
        "tick_exact_overall_pass": tick_ok,
        "capacity_overall_pass": cap_ok,
        "model_month": str(model_month),
        "model_valid_through": str(wfo_cfg.get("model_valid_through", "")).strip(),
    }

    manifest: dict[str, Any] = {
        "schema_version": 3,
        "frozen_at_utc": now.isoformat(),
        "symbol": s,
        "git": git_snapshot,
        "bundle": {
            "month": str(model_month),
            "dir_relpath": str(_repo_relative_or_abs(out_dir, repo_root)),
            "family": family,
        },
        "artifacts": artifacts,
        "provenance": provenance,
        "deployability": deployability,
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
                hard_limit=1.2,  # Safety bound enforced by Governance
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
    config_dir: Path,
    analysis_dir: Path,
    cadence_days: int,
    anchor_day_utc: int,
    window_days: int,
    allow_dirty: bool,
    family: str = "oco_first_touch",
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
        paths = _default_paths(s, config_dir=config_dir, analysis_dir=analysis_dir)
        manifest = _build_manifest(
            symbol=s,
            paths=paths,
            out_dir=out_dir,
            family=family,
            cadence_days=int(cadence_days),
            anchor_day_utc=int(anchor_day_utc),
            window_days=int(window_days),
            git_snapshot=git_snapshot,
        )
        mp = out_dir / lock_filename(str(s), "oco_first_touch")
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
    p.add_argument("--config-dir", default="configs/research/experiments")
    p.add_argument("--analysis-dir", default="data/analysis/tick_opportunity_mining")
    p.add_argument("--family", default="oco_first_touch")
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
                "warning: --symbols is a subset of registry symbols; omitted=" + ",".join(omitted)
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
        config_dir=Path(str(args.config_dir)),
        analysis_dir=Path(str(args.analysis_dir)),
        cadence_days=cadence_days,
        anchor_day_utc=anchor_day_utc,
        window_days=window_days,
        allow_dirty=bool(args.allow_dirty),
        family=str(args.family).strip(),
    )


if __name__ == "__main__":
    main()
