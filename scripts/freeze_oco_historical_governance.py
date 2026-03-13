#!/usr/bin/env python3
"""Freeze month-scoped historical OCO governance locks for backtest replay."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

try:
    import yaml
except Exception:
    yaml = None  # type: ignore[assignment]

_MONTH_RE = re.compile(r"^\d{4}-\d{2}$")


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
        "state_schedule": _pick_first_existing(
            Path(
                f"data/analysis/tick_opportunity_mining/reduced_core_rolling/{s}_oco_reduced_state_schedule.csv"
            ),
            Path(
                f"data/analysis/tick_opportunity_mining/reduced_core_rolling_{sl}/{s}_oco_reduced_state_schedule.csv"
            ),
        ),
        "tick_exact_summary": _pick_first_existing(
            Path(
                f"data/analysis/tick_opportunity_mining/reduced_core_rolling/{s}_oco_tick_exact_summary.csv"
            ),
            Path(
                f"data/analysis/tick_opportunity_mining/reduced_core_rolling_{sl}/{s}_oco_tick_exact_summary.csv"
            ),
        ),
        "reduced_summary": _pick_first_existing(
            Path(
                f"data/analysis/tick_opportunity_mining/reduced_core_rolling/{s}_oco_reduced_summary.csv"
            ),
            Path(
                f"data/analysis/tick_opportunity_mining/reduced_core_rolling_{sl}/{s}_oco_reduced_summary.csv"
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


def _model_month_pairs(symbol: str, *, models_dir: Path) -> dict[str, tuple[Path, Path]]:
    s = str(symbol).upper().strip()
    out: dict[str, tuple[Path, Path]] = {}
    for cbm in sorted(models_dir.glob(f"{s}_model_*.cbm")):
        month = cbm.stem.split("_")[-1]
        if not _MONTH_RE.match(month):
            continue
        thr = cbm.with_suffix(".json")
        if not thr.exists():
            continue
        out[month] = (cbm, thr)
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
    cols = ["symbol", "bar_ticks", "horizon", "state_id", "family", "barrier_pips", "regime_desc"]
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


def _canonical_candidate_uid(symbol: str, *, bar_ticks: int, horizon: int, state_id: str) -> str:
    return f"oco|{str(symbol).upper().strip()}|{int(bar_ticks)}|h{int(horizon)}|{str(state_id).strip()}"


def _freeze_month_predictions(
    *,
    source_predictions: Path,
    symbol: str,
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
            month_dir / f"{sym_l}_oco_live_lock.json",
            month_dir / f"{sym_l}_oco_allowed_states.csv",
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
    months: list[str],
    start_month: str | None,
    end_month: str | None,
    cadence_days: int,
    anchor_day_utc: int,
    window_days: int,
    allow_dirty: bool,
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
        paths = _default_paths(sym)
        for p in paths.values():
            if not p.exists():
                raise FileNotFoundError(p)
        model_pairs = _model_month_pairs(sym, models_dir=models_dir)
        state_schedule = pd.read_csv(paths["state_schedule"])
        sched_months = sorted(state_schedule["test_month"].dropna().astype(str).unique().tolist())
        available = sorted(list(set(model_pairs.keys()) & set(sched_months)))
        _prune_stale_symbol_month_files(out_dir=out_dir, symbol=sym, available_months=available)
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
            states, states_sha = _state_universe_for_month(paths["state_schedule"], sym, month)
            month_dir = out_dir / month
            month_dir.mkdir(parents=True, exist_ok=True)
            states_out = month_dir / f"{str(sym).lower()}_oco_allowed_states.csv"
            states.to_csv(states_out, index=False)
            frozen_pred_out = month_dir / f"{str(sym).lower()}_oco_locked_predictions.parquet"
            frozen_pred_path, frozen_pred_sha = _freeze_month_predictions(
                source_predictions=paths["predictions"],
                symbol=sym,
                month=month,
                states=states,
                out_path=frozen_pred_out,
            )

            manifest: dict[str, Any] = {
                "schema_version": 1,
                "frozen_at_utc": datetime.now(timezone.utc).isoformat(),
                "symbol": str(sym).upper(),
                "git": git_snapshot,
                "artifacts": {
                    "wfo_config_path": str(paths["wfo_config"]),
                    "wfo_config_sha256": _sha256(paths["wfo_config"]),
                    "reduced_config_path": str(paths["reduced_config"]),
                    "reduced_config_sha256": _sha256(paths["reduced_config"]),
                    "reduced_states_csv_path": str(states_out),
                    "reduced_states_csv_sha256": _sha256(states_out),
                    "source_predictions_path": str(paths["predictions"]),
                    "source_predictions_sha256": _sha256(paths["predictions"]),
                    "predictions_path": str(frozen_pred_path),
                    "predictions_sha256": str(frozen_pred_sha),
                    "model_cbm_path": str(model_cbm),
                    "model_cbm_sha256": _sha256(model_cbm),
                    "model_threshold_json_path": str(model_thr),
                    "model_threshold_json_sha256": _sha256(model_thr),
                    "model_month": str(month),
                    "tick_exact_summary_path": str(paths["tick_exact_summary"]),
                    "tick_exact_summary_sha256": _sha256(paths["tick_exact_summary"]),
                    "tick_exact_overall_pass": tick_ok,
                    "reduced_summary_path": str(paths["reduced_summary"]),
                    "reduced_summary_sha256": _sha256(paths["reduced_summary"]),
                    "capacity_overall_pass": cap_ok,
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
                },
            }
            lock_out = month_dir / f"{str(sym).lower()}_oco_live_lock.json"
            lock_out.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")

            out_paths.extend([lock_out, states_out, frozen_pred_path])
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
                    "live_deployable": bool((tick_ok is True) and (cap_ok is True)),
                }
            )
            print(f"wrote: {lock_out}")
            print(f"wrote: {states_out}")

    index_df = pd.DataFrame(index_rows).sort_values(["symbol", "month"]).reset_index(drop=True)
    index_out = out_dir / "index.csv"
    index_df.to_csv(index_out, index=False)
    out_paths.append(index_out)
    print(f"wrote: {index_out} rows={len(index_df)}")
    return out_paths, index_df


def main() -> None:
    default_symbols = "EURUSD,GBPUSD,USDJPY,USDCHF,AUDUSD,USDCAD"
    p = argparse.ArgumentParser(description="Freeze historical month-scoped OCO governance locks")
    p.add_argument("--symbols", default="")
    p.add_argument("--registry-yaml", default="configs/research/governance/oco_rule_universe_registry.yaml")
    p.add_argument("--out-dir", default="configs/research/governance/oco_history")
    p.add_argument("--models-dir", default="models/oco")
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
        months=_split_months(str(args.months)),
        start_month=str(args.start_month).strip() or None,
        end_month=str(args.end_month).strip() or None,
        cadence_days=cadence_days,
        anchor_day_utc=anchor_day_utc,
        window_days=window_days,
        allow_dirty=bool(args.allow_dirty),
    )


if __name__ == "__main__":
    main()
