#!/usr/bin/env python3
"""Freeze a month bundle: produce per-symbol *_live_lock.json under
configs/research/governance/oco_candidate_builds/<YYYY-MM>/ from the latest
mining outputs.

Active producer used by ``scripts/run_monthly_build.py``. Emits
``schema_version: 3`` locks per ADR 0001 (deterministic bundles) and
ADR 0002 (multi-family).

Previously located at scripts/legacy/freeze_oco_historical_governance.py.
"""

from __future__ import annotations

import argparse
import calendar
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

_MONTH_RE = re.compile(r"^\d{4}-\d{2}$")

CROSS_SYMBOL_FAMILIES = {"dollar_residual", "dispersion_rank", "lead_lag"}
CROSS_SYMBOL_SCOPE_SYMBOLS = ["EURUSD", "GBPUSD", "USDJPY", "USDCHF", "AUDUSD", "USDCAD"]


def _cross_symbol_scope_for_family(family: str) -> dict[str, object]:
    if str(family).strip().lower() not in CROSS_SYMBOL_FAMILIES:
        return {}
    return {
        "symbols": CROSS_SYMBOL_SCOPE_SYMBOLS,
        "alignment": "close_ts_inner_join",
        "source": "scripts.cross_symbol",
    }


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


def _model_valid_through(model_month: str) -> str:
    """Return the last day of the deployment month for a ``YYYY-MM`` model month.

    Models are named by their training-data-end month and deployed during the
    *following* calendar month (a ``2026-04`` model — trained on data through
    April, frozen ~May 1 — serves May). Validity therefore runs to the end of
    that deployment month. Returns "" if model_month is not a valid YYYY-MM.
    """
    try:
        year, month = (int(part) for part in str(model_month).split("-"))
    except (ValueError, TypeError):
        return ""
    deploy_year, deploy_month = (year + 1, 1) if month == 12 else (year, month + 1)
    last_day = calendar.monthrange(deploy_year, deploy_month)[1]
    return f"{deploy_year:04d}-{deploy_month:02d}-{last_day:02d}"


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


def _split_months(raw: str) -> list[str]:
    out = [x.strip() for x in str(raw).split(",") if x.strip()]
    return [x for x in out if _MONTH_RE.match(x)]


def _symbols_from_registry(path: Path) -> list[str]:
    if not path.exists():
        return []
    obj = _load_yaml(path)
    raw = obj.get("symbols", [])
    if not isinstance(raw, list):
        return []
    out = [str(x).strip().upper() for x in raw if str(x).strip()]
    return list(dict.fromkeys(out))


def _pick_first_existing(*paths: Path) -> Path:
    for p in paths:
        if p.exists():
            return p
    return paths[0]


def _wfo_dir_name(family: str) -> str:
    return f"wfo_m3to1_{str(family).strip()}_fullcap"


def _default_paths(
    symbol: str, *, config_dir: Path, analysis_dir: Path, family: str = "oco_first_touch"
) -> dict[str, Path]:
    s = str(symbol).upper().strip()
    sl = s.lower()
    fam = str(family).strip()
    oco_legacy = fam == "oco_first_touch"
    return {
        "wfo_config": _pick_first_existing(
            config_dir / f"{sl}_tick_opportunity_monthly_wfo_{fam}.yaml",
            config_dir / f"{sl}_tick_opportunity_monthly_wfo_{fam}_fullcap.yaml",
            *(
                [
                    config_dir / f"{sl}_tick_opportunity_monthly_wfo_oco_fullcap.yaml",
                    config_dir / f"{sl}_tick_opportunity_monthly_wfo_oco_fullcap_rolling.yaml",
                ]
                if oco_legacy
                else []
            ),
        ),
        "reduced_config": _pick_first_existing(
            config_dir / f"{sl}_{fam}_reduced_core_rolling.yaml",
            config_dir / f"{sl}_{fam}_reduced_core.yaml",
            *(
                [
                    config_dir / f"{sl}_oco_reduced_core_rolling.yaml",
                    config_dir / f"{sl}_oco_reduced_core.yaml",
                ]
                if oco_legacy
                else []
            ),
        ),
        "state_schedule": _pick_first_existing(
            analysis_dir / "reduced_core_rolling" / f"{s}_{fam}_reduced_state_schedule.csv",
            analysis_dir / f"reduced_core_rolling_{sl}" / f"{s}_{fam}_reduced_state_schedule.csv",
            *(
                [
                    analysis_dir / "reduced_core_rolling" / f"{s}_oco_reduced_state_schedule.csv",
                    analysis_dir
                    / f"reduced_core_rolling_{sl}"
                    / f"{s}_oco_reduced_state_schedule.csv",
                ]
                if oco_legacy
                else []
            ),
        ),
        "tick_exact_summary": _pick_first_existing(
            analysis_dir / "reduced_core" / f"{s}_{fam}_tick_exact_summary.csv",
            analysis_dir / "reduced_core_rolling" / f"{s}_{fam}_tick_exact_summary.csv",
            analysis_dir / f"reduced_core_rolling_{sl}" / f"{s}_{fam}_tick_exact_summary.csv",
            *(
                [
                    analysis_dir / "reduced_core" / f"{s}_oco_tick_exact_summary.csv",
                    analysis_dir / "reduced_core_rolling" / f"{s}_oco_tick_exact_summary.csv",
                    analysis_dir / f"reduced_core_rolling_{sl}" / f"{s}_oco_tick_exact_summary.csv",
                ]
                if oco_legacy
                else []
            ),
        ),
        "reduced_summary": _pick_first_existing(
            analysis_dir / "reduced_core_rolling" / f"{s}_{fam}_reduced_summary.csv",
            analysis_dir / f"reduced_core_rolling_{sl}" / f"{s}_{fam}_reduced_summary.csv",
            *(
                [
                    analysis_dir / "reduced_core_rolling" / f"{s}_oco_reduced_summary.csv",
                    analysis_dir / f"reduced_core_rolling_{sl}" / f"{s}_oco_reduced_summary.csv",
                ]
                if oco_legacy
                else []
            ),
        ),
        "reduced_monthly": _pick_first_existing(
            analysis_dir / "reduced_core_rolling" / f"{s}_{fam}_reduced_monthly.csv",
            analysis_dir / f"reduced_core_rolling_{sl}" / f"{s}_{fam}_reduced_monthly.csv",
            *(
                [
                    analysis_dir / "reduced_core_rolling" / f"{s}_oco_reduced_monthly.csv",
                    analysis_dir / f"reduced_core_rolling_{sl}" / f"{s}_oco_reduced_monthly.csv",
                ]
                if oco_legacy
                else []
            ),
        ),
        "predictions": _pick_first_existing(
            analysis_dir / _wfo_dir_name(fam) / f"{s}_{fam}_monthly_predictions.parquet",
            analysis_dir / f"{_wfo_dir_name(fam)}_{sl}" / f"{s}_{fam}_monthly_predictions.parquet",
            *(
                [
                    analysis_dir / "wfo_m3to1_oco_fullcap" / f"{s}_oco_monthly_predictions.parquet",
                    analysis_dir
                    / f"wfo_m3to1_oco_fullcap_{sl}"
                    / f"{s}_oco_monthly_predictions.parquet",
                ]
                if oco_legacy
                else []
            ),
        ),
        "tick_fill_caps": _pick_first_existing(
            analysis_dir / "stop_limit_tickfill_fullcap" / f"{s}_stop_limit_tickfill_caps.csv",
            analysis_dir / "stop_limit_tickfill" / f"{s}_stop_limit_tickfill_caps.csv",
        ),
    }


def _model_month_pairs(
    symbol: str, *, models_dir: Path, family: str = "oco_first_touch"
) -> dict[str, tuple[Path, Path]]:
    s = str(symbol).upper().strip()
    fam = str(family).strip()
    out: dict[str, tuple[Path, Path]] = {}
    patterns = [f"{s}_{fam}_model_*.cbm"]
    if fam == "oco_first_touch":
        patterns.append(f"{s}_model_*.cbm")
    for pattern in patterns:
        for cbm in sorted(models_dir.glob(pattern)):
            month = cbm.stem.split("_")[-1]
            if not _MONTH_RE.match(month):
                continue
            thr = cbm.with_suffix(".json")
            if not thr.exists():
                continue
            out.setdefault(month, (cbm, thr))
    return out


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
    if not caps_csv.exists():
        return float(default)
    try:
        d = pd.read_csv(caps_csv)
        if d.empty or "mean_per_signal_full_overshoot" not in d.columns:
            return float(default)
        valid = d[d["cap_pips"] <= hard_limit].copy()
        if valid.empty:
            return float(default)
        best = valid.loc[valid["mean_per_signal_full_overshoot"].idxmax()]
        return float(best["cap_pips"])
    except Exception:
        return float(default)


def _state_universe_for_month(path: Path, symbol: str, month: str) -> tuple[pd.DataFrame, str]:
    d = pd.read_csv(path)
    if d.empty:
        raise ValueError(f"empty state schedule: {path}")
    if "test_month" not in d.columns:
        raise ValueError(f"state schedule missing test_month: {path}")
    cols = _state_universe_columns()
    miss = [c for c in cols if c not in d.columns]
    if miss:
        raise ValueError(f"state schedule missing columns {miss}: {path}")
    x = d[d["test_month"].astype(str).str.strip() == str(month)].copy()
    x = x[cols].drop_duplicates().copy()
    x["symbol"] = x["symbol"].astype(str).str.upper()
    x = x[x["symbol"] == str(symbol).upper()].copy()
    x["bar_ticks"] = pd.to_numeric(x["bar_ticks"], errors="coerce").astype("Int64")
    x["horizon"] = pd.to_numeric(x["horizon"], errors="coerce").astype("Int64")
    x["barrier_pips"] = pd.to_numeric(x["barrier_pips"], errors="coerce").astype(float)
    x = x.dropna(subset=["bar_ticks", "horizon", "barrier_pips"]).copy()
    if x.empty:
        raise ValueError(f"no state rows for {symbol} {month}: {path}")
    x = x.sort_values(["symbol", "bar_ticks", "horizon", "state_id"]).reset_index(drop=True)
    raw = x.to_json(orient="records", date_format="iso", force_ascii=True)
    sha = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    return x, sha


def _state_universe_columns() -> list[str]:
    return ["symbol", "bar_ticks", "horizon", "state_id", "family", "barrier_pips", "regime_desc"]


def _empty_state_universe() -> tuple[pd.DataFrame, str]:
    x = pd.DataFrame(columns=_state_universe_columns())
    raw = x.to_json(orient="records", date_format="iso", force_ascii=True)
    sha = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    return x, sha


def _read_reduced_monthly_status(path: Path, symbol: str) -> dict[str, str]:
    if not path.exists():
        return {}
    try:
        d = pd.read_csv(path)
    except Exception:
        return {}
    if d.empty or "test_month" not in d.columns or "status" not in d.columns:
        return {}
    if "symbol" in d.columns:
        d = d[d["symbol"].astype(str).str.upper() == str(symbol).upper()].copy()
    out: dict[str, str] = {}
    for _, row in d.iterrows():
        month = str(row.get("test_month", "")).strip()
        if not _MONTH_RE.match(month):
            continue
        out[month] = str(row.get("status", "")).strip().lower()
    return out


def _library_for_family(family: str) -> str:
    fam = str(family).strip()
    return "oco" if fam in {"oco_first_touch", "oco_asymmetric", "double_touch"} else fam


def _canonical_candidate_uid(
    symbol: str, *, family: str, bar_ticks: int, horizon: int, state_id: str
) -> str:
    return (
        f"{_library_for_family(family)}|{str(symbol).upper().strip()}|"
        f"{int(bar_ticks)}|h{int(horizon)}|{str(state_id).strip()}"
    )


def _freeze_month_predictions(
    *,
    source_predictions: Path,
    symbol: str,
    family: str,
    month: str,
    states: pd.DataFrame,
    out_path: Path,
) -> tuple[Path, str]:
    pred = pd.read_parquet(source_predictions)
    pred["test_month"] = pred.get("test_month", pd.Series(dtype=object)).astype(str).str.strip()
    pred["candidate_uid"] = pred.get("candidate_uid", pd.Series(dtype=object)).astype(str)
    allowed = {
        _canonical_candidate_uid(
            symbol,
            family=family,
            bar_ticks=int(row["bar_ticks"]),
            horizon=int(row["horizon"]),
            state_id=str(row["state_id"]),
        )
        for _, row in states.iterrows()
    }
    frozen = pred[
        (pred["test_month"] == str(month).strip()) & (pred["candidate_uid"].isin(allowed))
    ].copy()
    if frozen.empty:
        raise ValueError(
            f"no prediction rows found for {str(symbol).upper()} {month} in {source_predictions}"
        )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    frozen.to_parquet(out_path, index=False)
    return out_path, _sha256(out_path)


def _filter_months(
    *,
    months: list[str],
    explicit_months: list[str],
    start_month: str | None,
    end_month: str | None,
) -> list[str]:
    out = sorted(list(dict.fromkeys([m for m in months if _MONTH_RE.match(m)])))
    if explicit_months:
        keep = set(explicit_months)
        out = [m for m in out if m in keep]
    if start_month and _MONTH_RE.match(start_month):
        out = [m for m in out if m >= start_month]
    if end_month and _MONTH_RE.match(end_month):
        out = [m for m in out if m <= end_month]
    return out


def _prune_stale_symbol_month_files(
    *,
    out_dir: Path,
    symbol: str,
    available_months: list[str],
    family: str = "oco_first_touch",
) -> int:
    """Remove stale month lock/state files for a symbol no longer in available month set."""
    sym = str(symbol).upper().strip()
    sym_l = sym.lower()
    keep = set(str(m).strip() for m in available_months if _MONTH_RE.match(str(m).strip()))
    removed = 0
    if not out_dir.exists():
        return 0
    for month_dir in out_dir.iterdir():
        if not month_dir.is_dir() or not _MONTH_RE.match(month_dir.name):
            continue
        if month_dir.name in keep:
            continue
        for fp in (
            month_dir / lock_filename(sym, family),
            month_dir / f"{sym_l}_{family}_allowed_states.csv",
            month_dir / f"{sym_l}_{family}_locked_predictions.parquet",
        ):
            if fp.exists():
                fp.unlink()
                removed += 1
                print(f"removed stale: {fp}")
    return removed


def run(
    *,
    symbols: list[str],
    out_dir: Path,
    models_dir: Path,
    config_dir: Path,
    analysis_dir: Path,
    months: list[str],
    start_month: str | None,
    end_month: str | None,
    cadence_days: int,
    anchor_day_utc: int,
    window_days: int,
    allow_dirty: bool,
    family: str = "oco_first_touch",
) -> tuple[list[Path], pd.DataFrame]:
    out_dir.mkdir(parents=True, exist_ok=True)
    git_snapshot = _git_info()
    if (not bool(allow_dirty)) and bool(git_snapshot.get("dirty", True)):
        raise RuntimeError(
            "Refusing to freeze historical locks from a dirty git worktree. "
            "Commit/stash changes first, or pass --allow-dirty."
        )

    out_paths: list[Path] = []
    index_rows: list[dict[str, Any]] = []

    for sym in symbols:
        paths = _default_paths(sym, config_dir=config_dir, analysis_dir=analysis_dir, family=family)
        for key, p in paths.items():
            if key == "reduced_monthly":
                continue
            if not p.exists():
                raise FileNotFoundError(p)
        model_pairs = _model_month_pairs(sym, models_dir=models_dir, family=family)
        state_schedule = pd.read_csv(paths["state_schedule"])
        sched_months = sorted(state_schedule["test_month"].dropna().astype(str).unique().tolist())
        reduced_month_status = _read_reduced_monthly_status(paths["reduced_monthly"], sym)
        available = sorted(
            list(set(model_pairs.keys()) & (set(sched_months) | set(reduced_month_status.keys())))
        )
        _prune_stale_symbol_month_files(out_dir=out_dir, symbol=sym, available_months=available, family=family)
        month_list = _filter_months(
            months=available,
            explicit_months=months,
            start_month=start_month,
            end_month=end_month,
        )

        wfo_cfg = _load_yaml(paths["wfo_config"])
        red_cfg = _load_yaml(paths["reduced_config"])
        tick_ok = _read_tick_exact_ok(paths["tick_exact_summary"])
        cap_ok = _read_capacity_ok(paths["reduced_summary"])
        cap_pips = _pick_optimal_cap(
            paths["tick_fill_caps"],
            default=float(wfo_cfg.get("production_cap_pips", 1.2)),
            hard_limit=1.2,
        )

        for month in month_list:
            model_cbm, model_thr = model_pairs[month]
            _sync_threshold_json_runtime_fields(model_thr, wfo_cfg)
            model_export_dir = model_cbm.parent
            train_pred = model_export_dir / f"{str(sym).upper()}_train_predictions_{month}.parquet"
            month_status = (
                str(reduced_month_status.get(month, "ok" if month in sched_months else ""))
                .strip()
                .lower()
            )
            historical_deployable = month_status in {"", "ok"}
            non_deployable_reason = "" if historical_deployable else month_status
            month_dir = out_dir / month
            month_dir.mkdir(parents=True, exist_ok=True)
            states_out = month_dir / f"{str(sym).lower()}_{family}_allowed_states.csv"
            if historical_deployable:
                states, states_sha = _state_universe_for_month(paths["state_schedule"], sym, month)
                states.to_csv(states_out, index=False)
                frozen_pred_out = (
                    month_dir / f"{str(sym).lower()}_{family}_locked_predictions.parquet"
                )
                frozen_pred_path, frozen_pred_sha = _freeze_month_predictions(
                    source_predictions=paths["predictions"],
                    symbol=sym,
                    family=family,
                    month=month,
                    states=states,
                    out_path=frozen_pred_out,
                )
                frozen_pred_path_txt = str(frozen_pred_path)
            else:
                states, states_sha = _empty_state_universe()
                states.to_csv(states_out, index=False)
                frozen_pred_path_txt = ""

            # model_valid_through is the last day of the deployment month
            # (the month after the training-data-end model_month). It was
            # previously derived from the model's threshold_schedule, but that
            # schedule is dead config — live serving no longer consults it —
            # so the derived value mislabelled each model as expiring a month
            # before it is actually deployed.
            model_valid_through = _model_valid_through(str(month))

            # Build v3 manifest with bundle-relative paths.
            fmt = {
                "symbol_lower": str(sym).lower(),
                "symbol_upper": str(sym).upper(),
                "month": str(month),
            }
            artifacts: dict[str, dict[str, str]] = {}
            provenance: dict[str, dict[str, str]] = {}
            repo_root = _repo_root().resolve()
            month_dir = month_dir.resolve()

            # Map of v2_key -> source path for family-layout-driven copy.
            file_map: dict[str, Path | None] = {
                "predictions": frozen_pred_out if frozen_pred_path_txt else None,
                "allowed_states_csv": states_out,
                "model_cbm": model_cbm,
                "model_threshold_json": model_thr,
                "wfo_config": paths["wfo_config"],
                "reduced_config": paths["reduced_config"],
                "reduced_summary": paths["reduced_summary"],
                "tick_exact_summary": paths["tick_exact_summary"],
            }

            for spec in bundle_layout_for(family):
                source = file_map.get(spec.v2_key)
                if source is None or not source.exists():
                    if spec.required and historical_deployable:
                        raise FileNotFoundError(f"required artifact {spec.v2_key}: {source}")
                    continue
                target_rel = spec.target_relpath_template.format(**fmt)
                target_abs = month_dir / target_rel
                target_abs.parent.mkdir(parents=True, exist_ok=True)
                if source.resolve() != target_abs.resolve():
                    shutil.copy2(source, target_abs)
                sha = sha256_file(target_abs)
                artifacts[spec.v2_key] = {"path": target_rel, "sha256": sha}
                try:
                    source.resolve().relative_to(month_dir)
                except ValueError:
                    try:
                        origin_rel = source.resolve().relative_to(repo_root).as_posix()
                    except ValueError:
                        origin_rel = str(source.resolve())
                    provenance[spec.v2_key] = {"origin": origin_rel, "origin_sha256": sha}

            # Record origin for source predictions (always outside bundle)
            try:
                src_pred_rel = paths["predictions"].resolve().relative_to(repo_root).as_posix()
            except ValueError:
                src_pred_rel = str(paths["predictions"].resolve())
            provenance["predictions"] = {
                "origin": src_pred_rel,
                "origin_sha256": _sha256(paths["predictions"]),
            }

            # Record origin for train predictions if present
            if train_pred.exists():
                try:
                    train_pred_rel = train_pred.resolve().relative_to(repo_root).as_posix()
                except ValueError:
                    train_pred_rel = str(train_pred.resolve())
                provenance["train_predictions"] = {
                    "origin": train_pred_rel,
                    "origin_sha256": _sha256(train_pred),
                }

            deployability = {
                "live_deployable": historical_deployable and (tick_ok is True) and (cap_ok is True),
                "tick_exact_overall_pass": tick_ok,
                "capacity_overall_pass": cap_ok,
                "model_month": str(month),
                "model_valid_through": model_valid_through,
            }

            scope = _cross_symbol_scope_for_family(family)
            bundle_block: dict[str, Any] = {
                "month": str(month),
                "dir_relpath": str(_repo_relative_or_abs(month_dir, repo_root)),
                "family": family,
            }
            if scope:
                bundle_block["cross_symbol_scope"] = scope

            manifest: dict[str, Any] = {
                "schema_version": 3,
                "frozen_at_utc": datetime.now(timezone.utc).isoformat(),
                "symbol": str(sym).upper(),
                "git": git_snapshot,
                "bundle": bundle_block,
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
                    "rolling_threshold_min_history": int(
                        wfo_cfg.get("rolling_threshold_min_history", 0)
                    ),
                    "execution_quantile": float(wfo_cfg.get("execution_quantile", 0.9)),
                    "production_cap_pips": float(cap_pips),
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
                "historical_backtest": {
                    "mode": "month_locked",
                    "target_month": str(month),
                    "deployable": bool(historical_deployable),
                    "non_deployable_reason": non_deployable_reason,
                },
            }
            lock_out = month_dir / lock_filename(sym, family)
            lock_out.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")

            out_paths.extend([lock_out, states_out])
            if frozen_pred_path_txt:
                out_paths.append(Path(frozen_pred_path_txt))
            index_rows.append(
                {
                    "symbol": str(sym).upper(),
                    "month": str(month),
                    "lock_path": str(lock_out),
                    "allowed_states_path": str(states_out),
                    "model_cbm_path": str(model_cbm),
                    "threshold_json_path": str(model_thr),
                    "candidates_count": int(len(states)),
                    "production_cap_pips": float(cap_pips),
                    "live_deployable": bool(
                        historical_deployable and (tick_ok is True) and (cap_ok is True)
                    ),
                }
            )
            print(f"wrote: {lock_out}")
            print(f"wrote: {states_out}")

    if index_rows:
        index_df = pd.DataFrame(index_rows).sort_values(["symbol", "month"]).reset_index(drop=True)
    else:
        index_df = pd.DataFrame(
            columns=[
                "symbol",
                "month",
                "lock_path",
                "allowed_states_path",
                "model_cbm_path",
                "threshold_json_path",
                "candidates_count",
                "production_cap_pips",
                "live_deployable",
            ]
        )
    index_out = out_dir / "index.csv"
    index_df.to_csv(index_out, index=False)
    out_paths.append(index_out)
    print(f"wrote: {index_out} rows={len(index_df)}")
    return out_paths, index_df


def main() -> None:
    default_symbols = "EURUSD,GBPUSD,USDJPY,USDCHF,AUDUSD,USDCAD"
    p = argparse.ArgumentParser(description="Freeze historical month-scoped OCO governance locks")
    p.add_argument("--symbols", default="")
    p.add_argument(
        "--registry-yaml", default="configs/research/governance/oco_rule_universe_registry.yaml"
    )
    p.add_argument("--out-dir", default="configs/research/governance/oco_history")
    p.add_argument("--models-dir", default="models/oco")
    p.add_argument("--config-dir", default="configs/research/experiments")
    p.add_argument("--analysis-dir", default="data/analysis/tick_opportunity_mining")
    p.add_argument("--family", default="oco_first_touch")
    p.add_argument("--months", default="", help="Optional explicit YYYY-MM list (comma-separated)")
    p.add_argument("--start-month", default="", help="Optional lower bound month YYYY-MM")
    p.add_argument("--end-month", default="", help="Optional upper bound month YYYY-MM")
    p.add_argument("--policy-config", default="configs/research/governance/oco_live_policy.yaml")
    p.add_argument("--cadence-days", type=int, default=30)
    p.add_argument("--anchor-day-utc", type=int, default=1)
    p.add_argument("--window-days", type=int, default=3)
    p.add_argument("--allow-dirty", action="store_true")
    args = p.parse_args()

    reg_path = Path(str(args.registry_yaml))
    registry_symbols = _symbols_from_registry(reg_path)
    if str(args.symbols).strip():
        symbols = _split_csv(str(args.symbols))
    elif registry_symbols:
        symbols = registry_symbols
    else:
        symbols = _split_csv(default_symbols)

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
        symbols=symbols,
        out_dir=Path(str(args.out_dir)),
        models_dir=Path(str(args.models_dir)),
        config_dir=Path(str(args.config_dir)),
        analysis_dir=Path(str(args.analysis_dir)),
        months=_split_months(str(args.months)),
        start_month=str(args.start_month).strip() or None,
        end_month=str(args.end_month).strip() or None,
        cadence_days=cadence_days,
        anchor_day_utc=anchor_day_utc,
        window_days=window_days,
        allow_dirty=bool(args.allow_dirty),
        family=str(args.family).strip(),
    )


if __name__ == "__main__":
    main()
