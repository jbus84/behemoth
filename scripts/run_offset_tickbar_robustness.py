#!/usr/bin/env python3
"""Run the offset tick-bar robustness study for the active OCO universe."""

from __future__ import annotations

import argparse
import shlex
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.build_tick_velocity_dataset import _build_symbol_dataset  # noqa: E402
from scripts.canonical_tick_feed import DEFAULT_CANONICAL_ROOT  # noqa: E402
from src.behemoth.core.features import FeatureConfig  # noqa: E402

FEATURE_CONFIG = FeatureConfig()

ACTIVE_SYMBOLS = ("EURUSD", "GBPUSD", "USDJPY", "USDCHF", "AUDUSD", "USDCAD")
DEFAULT_TICK_ROOT = str(DEFAULT_CANONICAL_ROOT)
DEFAULT_OFFSET_BAR_DIR = "data/global_tickbars_offset"
DEFAULT_OUT_DIR = "data/analysis/tick_opportunity_mining/offset_robustness"
DEFAULT_API_CONFIRM_OFFSETS = (0, 25, 50, 75)
DEFAULT_WARMUP_BARS_GRID = (73, 145, 217, 289, 400)
DEFAULT_OFFSETS = tuple(range(100))
DEFAULT_COARSE_OFFSETS = tuple(range(0, 100, 10))
MIN_FEATURE_BARS = FEATURE_CONFIG.min_periods_cost + 1
FULL_FEATURE_BARS = FEATURE_CONFIG.full_warmup_bars
DEFAULT_STOP_LIMIT_CAPS = "0.5,0.8,1.0,1.2,1.5,2.0"
DEFAULT_STRESS_COST_GRID = "0.1,0.2,0.3,0.5,0.75,1.0,1.25,1.5,1.75,2.0"


@dataclass(frozen=True)
class SymbolConfigs:
    mining: Path
    wfo: Path
    reduced: Path


def _parse_csv_ints(raw: str | None) -> list[int]:
    vals: list[int] = []
    for tok in str(raw or "").split(","):
        t = tok.strip()
        if not t:
            continue
        vals.append(int(t))
    return vals


def _parse_symbols(raw: str | None) -> list[str]:
    vals = [x.strip().upper() for x in str(raw or "").split(",") if x.strip()]
    return vals or list(ACTIVE_SYMBOLS)


def _pct_delta(current: float | int | None, baseline: float | int | None) -> float:
    if current is None or baseline is None:
        return float("nan")
    try:
        cur = float(current)
        base = float(baseline)
    except Exception:
        return float("nan")
    if not np.isfinite(cur) or not np.isfinite(base):
        return float("nan")
    if abs(base) <= 1e-12:
        if abs(cur) <= 1e-12:
            return 0.0
        return float("inf") if cur > 0 else float("-inf")
    return (cur - base) * 100.0 / abs(base)


def _safe_float(raw: Any) -> float:
    try:
        val = float(raw)
    except Exception:
        return float("nan")
    return val if np.isfinite(val) else float("nan")


def _safe_int(raw: Any) -> int:
    try:
        return int(raw)
    except Exception:
        return 0


def _as_bool(raw: Any) -> bool:
    if isinstance(raw, bool):
        return raw
    txt = str(raw).strip().lower()
    return txt in {"1", "true", "yes", "y", "on"}


def _symbol_configs(symbol: str) -> SymbolConfigs:
    s = str(symbol).lower().strip()
    return SymbolConfigs(
        mining=ROOT / f"configs/research/experiments/{s}_tick_opportunity_mining.yaml",
        wfo=ROOT
        / f"configs/research/experiments/{s}_tick_opportunity_monthly_wfo_oco_fullcap.yaml",
        reduced=ROOT / f"configs/research/experiments/{s}_oco_reduced_core_rolling.yaml",
    )


def _run_cmd(args: list[str], *, fail_fast: bool) -> tuple[bool, str]:
    print("+", shlex.join(args))
    try:
        subprocess.run(args, cwd=ROOT, check=True)
        return True, ""
    except subprocess.CalledProcessError as exc:
        if fail_fast:
            raise
        return False, f"command_failed:{exc.returncode}:{shlex.join(args)}"


def _ensure_offset_bars(
    *,
    symbols: list[str],
    offsets: list[int],
    tick_root: Path,
    offset_bar_dir: Path,
    overwrite: bool,
    fail_fast: bool,
) -> None:
    args = [
        sys.executable,
        str(ROOT / "scripts/build_global_tick_bars_offset.py"),
        "--tick-root",
        str(tick_root),
        "--output-dir",
        str(offset_bar_dir),
        "--symbols",
        ",".join(symbols),
        "--offsets",
        ",".join(str(x) for x in offsets),
        "--bar-ticks",
        "100",
        "--price-source",
        "bid",
        "--timestamp-mode",
        "as_utc",
        "--summary-csv",
        str(offset_bar_dir / "build_summary.csv"),
    ]
    if overwrite:
        args.append("--overwrite")
    ok, msg = _run_cmd(args, fail_fast=fail_fast)
    if not ok:
        raise RuntimeError(msg)


def _offset_stage_root(out_dir: Path, symbol: str, offset: int) -> Path:
    return out_dir / "runs" / symbol / f"offset_{int(offset):03d}"


def _offset_report_path(symbol: str, *, out_dir: Path) -> Path:
    canonical = (ROOT / DEFAULT_OUT_DIR).resolve()
    target = out_dir.resolve()
    if target == canonical:
        return ROOT / "docs" / "analysis" / f"{symbol.lower()}_offset_tickbar_robustness_report.md"
    return out_dir / "reports" / f"{symbol.lower()}_offset_tickbar_robustness_report.md"


def _display_path(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT))
    except Exception:
        return str(path)


def _build_velocity_for_offset(
    *,
    symbol: str,
    offset: int,
    offset_bar_dir: Path,
    stage_root: Path,
) -> Path:
    bar_path = offset_bar_dir / f"{symbol}_100tick_offset_{int(offset):03d}.parquet"
    if not bar_path.exists():
        raise FileNotFoundError(f"offset bar parquet missing: {bar_path}")
    velocity_dir = stage_root / "velocity"
    velocity_dir.mkdir(parents=True, exist_ok=True)
    out_path = velocity_dir / f"{symbol}_100tick_velocity.parquet"
    ds = _build_symbol_dataset(
        symbol=symbol,
        bar_path=bar_path,
        bar_ticks=100,
        vel_horizons=[1, 2, 5, 10],
        target_horizons=[1, 2, 3, 4, 5, 6],
        vol_window=FEATURE_CONFIG.vol_window,
        cost_window=FEATURE_CONFIG.cost_window,
    )
    if ds.empty:
        raise RuntimeError(f"empty velocity dataset for {symbol} offset={offset}")
    ds["timestamp_mode"] = "as_utc"
    ds.to_parquet(out_path, index=False)
    return out_path


def _reduced_schedule_path(stage_root: Path, symbol: str) -> Path:
    return stage_root / "reduced_core_rolling" / f"{symbol}_oco_first_touch_reduced_state_schedule.csv"


def _reduced_summary_path(stage_root: Path, symbol: str) -> Path:
    return stage_root / "reduced_core_rolling" / f"{symbol}_oco_first_touch_reduced_summary.csv"


def _reduced_monthly_path(stage_root: Path, symbol: str) -> Path:
    return stage_root / "reduced_core_rolling" / f"{symbol}_oco_first_touch_reduced_monthly.csv"


def _tick_exact_summary_path(stage_root: Path, symbol: str) -> Path:
    return stage_root / "tick_exact" / f"{symbol}_oco_first_touch_tick_exact_summary.csv"


def _robustness_summary_path(stage_root: Path, symbol: str) -> Path:
    return stage_root / "robustness" / f"{symbol}_oco_robustness_summary.csv"


def _prediction_path(stage_root: Path, symbol: str) -> Path:
    return stage_root / "wfo" / f"{symbol}_oco_first_touch_monthly_predictions.parquet"


def _stop_limit_detail_path(stage_root: Path, symbol: str) -> Path:
    return stage_root / "stop_limit" / f"{symbol}_stop_limit_tickfill_detail.csv"


def _load_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    try:
        return pd.read_csv(path)
    except Exception:
        return pd.DataFrame()


def _load_parquet(path: Path, *, columns: list[str] | None = None) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    try:
        return pd.read_parquet(path, columns=columns)
    except Exception:
        return pd.DataFrame()


def _load_selected_signal_keys(pred_path: Path, schedule_path: Path) -> pd.DataFrame:
    pred = _load_parquet(
        pred_path, columns=["candidate_uid", "close_ts", "selected_exec", "test_month"]
    )
    if pred.empty:
        return pd.DataFrame(columns=["candidate_uid", "close_ts", "test_month"])
    pred["selected_exec"] = (
        pd.to_numeric(pred.get("selected_exec"), errors="coerce").fillna(0).astype(int)
    )
    pred = pred[pred["selected_exec"] == 1].copy()
    if pred.empty:
        return pd.DataFrame(columns=["candidate_uid", "close_ts", "test_month"])
    pred["close_ts"] = pd.to_datetime(pred["close_ts"], utc=True, errors="coerce")
    pred["test_month"] = pred.get("test_month", pd.Series(dtype=str)).astype(str)
    parts = pred["candidate_uid"].astype(str).str.split("|", n=4, expand=True)
    if parts.shape[1] < 5:
        return pd.DataFrame(columns=["candidate_uid", "close_ts", "test_month"])
    pred["state_id"] = parts[4].astype(str)
    pred["bar_ticks"] = pd.to_numeric(parts[2], errors="coerce").astype("Int64")
    pred["horizon"] = pd.to_numeric(parts[3].astype(str).str.lstrip("hH"), errors="coerce").astype(
        "Int64"
    )

    sched = _load_csv(schedule_path)
    if sched.empty:
        return pd.DataFrame(columns=["candidate_uid", "close_ts", "test_month"])
    req = {"test_month", "state_id", "bar_ticks", "horizon"}
    if not req.issubset(set(sched.columns)):
        return pd.DataFrame(columns=["candidate_uid", "close_ts", "test_month"])
    sched = sched[["test_month", "state_id", "bar_ticks", "horizon"]].drop_duplicates().copy()
    sched["test_month"] = sched["test_month"].astype(str)
    sched["bar_ticks"] = pd.to_numeric(sched["bar_ticks"], errors="coerce").astype("Int64")
    sched["horizon"] = pd.to_numeric(sched["horizon"], errors="coerce").astype("Int64")
    out = pred.merge(sched, on=["test_month", "state_id", "bar_ticks", "horizon"], how="inner")
    out = out.dropna(subset=["candidate_uid", "close_ts"]).copy()
    return out[["candidate_uid", "close_ts", "test_month"]].drop_duplicates().reset_index(drop=True)


def _load_schedule_states(schedule_path: Path) -> pd.DataFrame:
    sched = _load_csv(schedule_path)
    if sched.empty:
        return pd.DataFrame(columns=["test_month", "state_key"])
    req = {"test_month", "state_id", "bar_ticks", "horizon"}
    if not req.issubset(set(sched.columns)):
        return pd.DataFrame(columns=["test_month", "state_key"])
    out = sched[["test_month", "state_id", "bar_ticks", "horizon"]].copy()
    out["test_month"] = out["test_month"].astype(str)
    out["state_key"] = (
        out["state_id"].astype(str)
        + "|"
        + pd.to_numeric(out["bar_ticks"], errors="coerce").fillna(-1).astype(int).astype(str)
        + "|"
        + pd.to_numeric(out["horizon"], errors="coerce").fillna(-1).astype(int).astype(str)
    )
    return out[["test_month", "state_key"]].drop_duplicates().reset_index(drop=True)


def _load_stop_limit_summary(stage_root: Path, symbol: str) -> dict[str, Any]:
    summary = _load_csv(stage_root / "stop_limit" / "summary.csv")
    if summary.empty:
        return {}
    if "symbol" in summary.columns:
        summary = summary[summary["symbol"].astype(str).str.upper().str.strip() == symbol].copy()
    return summary.iloc[0].to_dict() if not summary.empty else {}


def _load_reduced_summary(stage_root: Path, symbol: str) -> dict[str, Any]:
    summary = _load_csv(_reduced_summary_path(stage_root, symbol))
    return summary.iloc[0].to_dict() if not summary.empty else {}


def _load_tick_exact_summary(stage_root: Path, symbol: str) -> dict[str, Any]:
    summary = _load_csv(_tick_exact_summary_path(stage_root, symbol))
    return summary.iloc[0].to_dict() if not summary.empty else {}


def _load_robustness_exec_row(stage_root: Path, symbol: str) -> dict[str, Any]:
    summary = _load_csv(_robustness_summary_path(stage_root, symbol))
    if summary.empty:
        return {}
    summary["quantile"] = pd.to_numeric(summary.get("quantile"), errors="coerce")
    candidates = summary[np.isclose(summary["quantile"], 0.9, equal_nan=False)].copy()
    if "universe_mode" in candidates.columns:
        rc = candidates[candidates["universe_mode"].astype(str) == "reduced_core_schedule"].copy()
        if not rc.empty:
            candidates = rc
    if "is_exec_row" in candidates.columns:
        ex = candidates[
            pd.to_numeric(candidates["is_exec_row"], errors="coerce").fillna(0).astype(int) == 1
        ].copy()
        if not ex.empty:
            candidates = ex
    return candidates.iloc[0].to_dict() if not candidates.empty else {}


def _state_overlap_rows(
    *,
    symbol: str,
    offset: int,
    baseline_states: pd.DataFrame,
    current_states: pd.DataFrame,
) -> tuple[list[dict[str, Any]], float]:
    months = sorted(
        set(baseline_states.get("test_month", pd.Series(dtype=str)).astype(str))
        | set(current_states.get("test_month", pd.Series(dtype=str)).astype(str))
    )
    rows: list[dict[str, Any]] = []
    overall_base = set(baseline_states.get("state_key", pd.Series(dtype=str)).astype(str))
    overall_cur = set(current_states.get("state_key", pd.Series(dtype=str)).astype(str))
    for month in months:
        b = set(
            baseline_states[baseline_states["test_month"].astype(str) == str(month)][
                "state_key"
            ].astype(str)
        )
        c = set(
            current_states[current_states["test_month"].astype(str) == str(month)][
                "state_key"
            ].astype(str)
        )
        inter = len(b & c)
        union = len(b | c)
        rows.append(
            {
                "symbol": symbol,
                "offset": int(offset),
                "test_month": str(month),
                "baseline_state_count": len(b),
                "offset_state_count": len(c),
                "intersection_count": inter,
                "union_count": union,
                "state_jaccard": float(inter / union) if union > 0 else float("nan"),
            }
        )
    overall_inter = len(overall_base & overall_cur)
    overall_union = len(overall_base | overall_cur)
    rows.append(
        {
            "symbol": symbol,
            "offset": int(offset),
            "test_month": "ALL",
            "baseline_state_count": len(overall_base),
            "offset_state_count": len(overall_cur),
            "intersection_count": overall_inter,
            "union_count": overall_union,
            "state_jaccard": float(overall_inter / overall_union)
            if overall_union > 0
            else float("nan"),
        }
    )
    overall = float(overall_inter / overall_union) if overall_union > 0 else float("nan")
    return rows, overall


def _selected_overlap_rate(baseline: pd.DataFrame, current: pd.DataFrame) -> float:
    base_keys = set(
        zip(
            baseline.get("candidate_uid", pd.Series(dtype=str)).astype(str),
            pd.to_datetime(
                baseline.get("close_ts", pd.Series(dtype=object)), utc=True, errors="coerce"
            ),
        )
    )
    cur_keys = set(
        zip(
            current.get("candidate_uid", pd.Series(dtype=str)).astype(str),
            pd.to_datetime(
                current.get("close_ts", pd.Series(dtype=object)), utc=True, errors="coerce"
            ),
        )
    )
    base_keys = {(uid, ts) for uid, ts in base_keys if pd.notna(ts)}
    cur_keys = {(uid, ts) for uid, ts in cur_keys if pd.notna(ts)}
    if not base_keys and not cur_keys:
        return 1.0
    if not base_keys:
        return 0.0
    return float(len(base_keys & cur_keys) / len(base_keys))


def _selected_key_diff_count(baseline: pd.DataFrame, current: pd.DataFrame) -> int:
    base_keys = set(
        zip(
            baseline.get("candidate_uid", pd.Series(dtype=str)).astype(str),
            pd.to_datetime(
                baseline.get("close_ts", pd.Series(dtype=object)), utc=True, errors="coerce"
            ),
        )
    )
    cur_keys = set(
        zip(
            current.get("candidate_uid", pd.Series(dtype=str)).astype(str),
            pd.to_datetime(
                current.get("close_ts", pd.Series(dtype=object)), utc=True, errors="coerce"
            ),
        )
    )
    base_keys = {(uid, ts) for uid, ts in base_keys if pd.notna(ts)}
    cur_keys = {(uid, ts) for uid, ts in cur_keys if pd.notna(ts)}
    return int(len(base_keys ^ cur_keys))


def _prediction_perf_for_keys(
    pred_path: Path, detail_path: Path, keys: pd.DataFrame
) -> dict[str, Any]:
    if keys.empty:
        return {
            "selected_rows": 0,
            "trade_rows": 0,
            "mean_gross_pips": float("nan"),
            "mean_net_pips": float("nan"),
        }
    pred = _load_parquet(pred_path, columns=["candidate_uid", "close_ts", "target_gross_pips"])
    if pred.empty:
        return {
            "selected_rows": int(len(keys)),
            "trade_rows": 0,
            "mean_gross_pips": float("nan"),
            "mean_net_pips": float("nan"),
        }
    pred["close_ts"] = pd.to_datetime(pred["close_ts"], utc=True, errors="coerce")
    pred["target_gross_pips"] = pd.to_numeric(pred["target_gross_pips"], errors="coerce")
    merged = keys.copy()
    merged["close_ts"] = pd.to_datetime(merged["close_ts"], utc=True, errors="coerce")
    merged = merged.merge(pred, on=["candidate_uid", "close_ts"], how="left")
    detail = _load_csv(detail_path)
    if not detail.empty:
        detail["close_ts"] = pd.to_datetime(detail["close_ts"], utc=True, errors="coerce")
        for col in ["target_gross_pips", "overshoot_tick_pips", "touch_found_tick"]:
            if col in detail.columns:
                detail[col] = pd.to_numeric(detail[col], errors="coerce")
        detail = detail[
            [
                c
                for c in ["candidate_uid", "close_ts", "overshoot_tick_pips", "touch_found_tick"]
                if c in detail.columns
            ]
        ].drop_duplicates(subset=["candidate_uid", "close_ts"], keep="last")
        merged = merged.merge(detail, on=["candidate_uid", "close_ts"], how="left")
    gross = pd.to_numeric(merged.get("target_gross_pips"), errors="coerce")
    overs = pd.to_numeric(merged.get("overshoot_tick_pips"), errors="coerce")
    touch = pd.to_numeric(merged.get("touch_found_tick"), errors="coerce").fillna(0).astype(int)
    net = gross.where(touch == 1, np.nan) - overs.where(touch == 1, np.nan)
    return {
        "selected_rows": int(len(merged)),
        "trade_rows": int((touch == 1).sum()),
        "mean_gross_pips": float(gross.mean()) if gross.notna().any() else float("nan"),
        "mean_net_pips": float(net.mean()) if net.notna().any() else float("nan"),
    }


def _build_by_offset_row(
    *,
    symbol: str,
    offset: int,
    stage_root: Path,
    baseline_row: dict[str, Any] | None,
    baseline_selected: pd.DataFrame | None,
    baseline_states: pd.DataFrame | None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    reduced_summary = _load_reduced_summary(stage_root, symbol)
    reduced_monthly = _load_csv(_reduced_monthly_path(stage_root, symbol))
    tick_exact_summary = _load_tick_exact_summary(stage_root, symbol)
    robustness_row = _load_robustness_exec_row(stage_root, symbol)
    stop_limit_summary = _load_stop_limit_summary(stage_root, symbol)
    schedule = _load_schedule_states(_reduced_schedule_path(stage_root, symbol))
    selected = _load_selected_signal_keys(
        _prediction_path(stage_root, symbol), _reduced_schedule_path(stage_root, symbol)
    )

    if not reduced_summary:
        row = {
            "symbol": symbol,
            "offset": int(offset),
            "offset_status": "failed_pipeline",
            "failure_reason": "missing_reduced_summary",
        }
        return row, []

    no_qualifying = selected.empty or schedule.empty
    rows_total = _safe_float(reduced_summary.get("rows_total"))
    signal_rows_total = _safe_float(reduced_summary.get("signal_rows_total"))
    mean_gross = _safe_float(reduced_summary.get("mean_gross_pips"))
    positive_months = _safe_float(reduced_summary.get("positive_months"))
    fill_rate = _safe_float(reduced_summary.get("fill_rate_overall"))
    capacity_pass = _as_bool(reduced_summary.get("capacity_pass_monthly_or_annual"))
    tick_exact_pass = (
        _as_bool(tick_exact_summary.get("overall_pass")) if tick_exact_summary else False
    )
    no_touch_rate = (
        float(1.0 - _safe_float(stop_limit_summary.get("touch_found_rate")))
        if stop_limit_summary
        else float("nan")
    )
    overshoot_p95 = (
        _safe_float(stop_limit_summary.get("tick_overshoot_p95_pips"))
        if stop_limit_summary
        else float("nan")
    )
    warmup_skip_months = (
        int(reduced_monthly.get("status", pd.Series(dtype=str)).astype(str).eq("warmup_skip").sum())
        if not reduced_monthly.empty
        else 0
    )
    lb95_trade_gross = _safe_float(robustness_row.get("lb95_trade_mean_gross_pips"))
    mean_net = _safe_float(robustness_row.get("mean_net_pips_costplus_0.10"))
    lb95_trade_net = _safe_float(robustness_row.get("lb95_trade_mean_net_pips_costplus_0.10"))

    overlap_rows: list[dict[str, Any]] = []
    state_jaccard = float("nan")
    overlap_rate = float("nan")
    selected_rows_delta_pct = 0.0
    trade_rows_delta_pct = 0.0
    mean_gross_delta = 0.0
    mean_net_delta = 0.0
    lb95_gross_delta = 0.0
    lb95_net_delta = 0.0
    positive_months_delta = 0.0
    fill_rate_delta = 0.0
    no_touch_delta = 0.0
    overshoot_delta = 0.0

    degrade_reasons: list[str] = []
    if baseline_row is not None and baseline_selected is not None and baseline_states is not None:
        overlap_rows, state_jaccard = _state_overlap_rows(
            symbol=symbol,
            offset=int(offset),
            baseline_states=baseline_states,
            current_states=schedule,
        )
        overlap_rate = _selected_overlap_rate(baseline_selected, selected)
        selected_rows_delta_pct = _pct_delta(
            signal_rows_total, baseline_row.get("selected_rows_total")
        )
        trade_rows_delta_pct = _pct_delta(rows_total, baseline_row.get("trade_rows_total"))
        mean_gross_delta = mean_gross - _safe_float(baseline_row.get("mean_gross_pips"))
        mean_net_delta = mean_net - _safe_float(baseline_row.get("mean_net_pips"))
        lb95_gross_delta = lb95_trade_gross - _safe_float(
            baseline_row.get("lb95_trade_mean_gross_pips")
        )
        lb95_net_delta = lb95_trade_net - _safe_float(baseline_row.get("lb95_trade_mean_net_pips"))
        positive_months_delta = positive_months - _safe_float(baseline_row.get("positive_months"))
        fill_rate_delta = fill_rate - _safe_float(baseline_row.get("execution_fill_rate"))
        no_touch_delta = no_touch_rate - _safe_float(baseline_row.get("execution_no_touch_rate"))
        overshoot_delta = overshoot_p95 - _safe_float(
            baseline_row.get("execution_overshoot_p95_pips")
        )

        if np.isfinite(selected_rows_delta_pct) and abs(selected_rows_delta_pct) > 20.0:
            degrade_reasons.append("selected_rows_delta_gt_20pct")
        if np.isfinite(trade_rows_delta_pct) and abs(trade_rows_delta_pct) > 20.0:
            degrade_reasons.append("trade_rows_delta_gt_20pct")
        if np.isfinite(lb95_gross_delta) and lb95_gross_delta < -0.25:
            degrade_reasons.append("lb95_trade_mean_gross_drop")
        if np.isfinite(lb95_net_delta) and lb95_net_delta < -0.25:
            degrade_reasons.append("lb95_trade_mean_net_drop")
        if np.isfinite(state_jaccard) and state_jaccard < 0.60:
            degrade_reasons.append("state_jaccard_lt_0.60")
        if np.isfinite(overshoot_delta) and overshoot_delta > 0.20:
            degrade_reasons.append("execution_overshoot_p95_delta_gt_0.20")
        if _as_bool(baseline_row.get("tick_exact_pass")) and (not tick_exact_pass):
            degrade_reasons.append("tick_exact_regressed")
        if _as_bool(baseline_row.get("capacity_pass_monthly_or_annual")) and (not capacity_pass):
            degrade_reasons.append("capacity_gate_regressed")

    status = "no_qualifying_states" if no_qualifying else ("degraded" if degrade_reasons else "ok")
    row = {
        "symbol": symbol,
        "offset": int(offset),
        "selected_rows_total": int(signal_rows_total) if np.isfinite(signal_rows_total) else 0,
        "trade_rows_total": int(rows_total) if np.isfinite(rows_total) else 0,
        "mean_gross_pips": mean_gross,
        "mean_net_pips": mean_net,
        "lb95_trade_mean_gross_pips": lb95_trade_gross,
        "lb95_trade_mean_net_pips": lb95_trade_net,
        "positive_months": int(positive_months) if np.isfinite(positive_months) else 0,
        "reduced_core_state_jaccard": state_jaccard,
        "candidate_uid_close_ts_overlap_rate": overlap_rate,
        "execution_fill_rate": fill_rate,
        "execution_no_touch_rate": no_touch_rate,
        "execution_overshoot_p95_pips": overshoot_p95,
        "warmup_skip_months_count": int(warmup_skip_months),
        "tick_exact_pass": bool(tick_exact_pass),
        "capacity_pass_monthly_or_annual": bool(capacity_pass),
        "selected_rows_delta_pct": selected_rows_delta_pct,
        "trade_rows_delta_pct": trade_rows_delta_pct,
        "mean_gross_pips_delta": mean_gross_delta,
        "mean_net_pips_delta": mean_net_delta,
        "lb95_trade_mean_gross_pips_delta": lb95_gross_delta,
        "lb95_trade_mean_net_pips_delta": lb95_net_delta,
        "positive_months_delta": positive_months_delta,
        "execution_fill_rate_delta": fill_rate_delta,
        "execution_no_touch_rate_delta": no_touch_delta,
        "execution_overshoot_p95_delta": overshoot_delta,
        "offset_status": status,
        "degrade_reasons": ",".join(degrade_reasons),
        "failure_reason": "" if status != "failed_pipeline" else "missing_reduced_summary",
        "prediction_path": str(_prediction_path(stage_root, symbol)),
        "reduced_state_schedule_csv": str(_reduced_schedule_path(stage_root, symbol)),
        "stop_limit_detail_csv": str(_stop_limit_detail_path(stage_root, symbol)),
    }
    return row, overlap_rows


def _run_symbol_offset_pipeline(
    *,
    symbol: str,
    offset: int,
    tick_root: Path,
    offset_bar_dir: Path,
    out_dir: Path,
    fail_fast: bool,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    cfg = _symbol_configs(symbol)
    stage_root = _offset_stage_root(out_dir, symbol, offset)
    reports_dir = stage_root / "tmp_reports"
    reports_dir.mkdir(parents=True, exist_ok=True)

    try:
        velocity_path = _build_velocity_for_offset(
            symbol=symbol,
            offset=int(offset),
            offset_bar_dir=offset_bar_dir,
            stage_root=stage_root,
        )
    except Exception as exc:
        return {
            "symbol": symbol,
            "offset": int(offset),
            "offset_status": "failed_pipeline",
            "failure_reason": f"velocity_build_failed:{exc}",
        }, []

    mining_out = stage_root / "mining"
    wfo_out = stage_root / "wfo"
    stop_limit_out = stage_root / "stop_limit"
    reduced_rolling_dir = stage_root / "reduced_core_rolling"
    reduced_dir = stage_root / "reduced_core"
    tick_exact_dir = stage_root / "tick_exact"
    robustness_dir = stage_root / "robustness"
    for d in [
        mining_out,
        wfo_out,
        stop_limit_out,
        reduced_rolling_dir,
        reduced_dir,
        tick_exact_dir,
        robustness_dir,
    ]:
        d.mkdir(parents=True, exist_ok=True)

    pipeline_steps: list[tuple[str, list[str]]] = [
        (
            "mining",
            [
                sys.executable,
                str(ROOT / "scripts/run_tick_opportunity_mining.py"),
                "--config",
                str(cfg.mining),
                "--dataset-dir",
                str(velocity_path.parent),
                "--bar-ticks-grid",
                "100",
                "--out-dir",
                str(mining_out),
                "--report-out",
                str(reports_dir / f"{symbol.lower()}_offset_{int(offset):03d}_mining.md"),
            ],
        ),
        (
            "wfo",
            [
                sys.executable,
                str(ROOT / "scripts/run_tick_opportunity_monthly_wfo.py"),
                "--config",
                str(cfg.wfo),
                "--dataset-dir",
                str(velocity_path.parent),
                "--candidate-dir",
                str(mining_out),
                "--out-dir",
                str(wfo_out),
                "--report-out",
                str(reports_dir / f"{symbol.lower()}_offset_{int(offset):03d}_wfo.md"),
            ],
        ),
        (
            "stop_limit",
            [
                sys.executable,
                str(ROOT / "scripts/analyze_oco_stop_limit_tickfill.py"),
                "--symbols",
                symbol,
                "--pred-paths",
                str(_prediction_path(stage_root, symbol)),
                "--velocity-dir",
                str(velocity_path.parent),
                "--tick-root",
                str(tick_root),
                "--caps",
                DEFAULT_STOP_LIMIT_CAPS,
                "--use-exec-selected",
                "true",
                "--quantile",
                "0.9",
                "--out-dir",
                str(stop_limit_out),
            ],
        ),
        (
            "reduced_core",
            [
                sys.executable,
                str(ROOT / "scripts/select_reduced_core_regimes.py"),
                "--config",
                str(cfg.reduced),
                "--candidate-csv",
                str(mining_out / f"{symbol}_oco_candidates.csv"),
                "--pred-path",
                str(_prediction_path(stage_root, symbol)),
                "--stop-limit-detail-csv",
                str(_stop_limit_detail_path(stage_root, symbol)),
                "--out-state-schedule-csv",
                str(_reduced_schedule_path(stage_root, symbol)),
                "--out-state-csv",
                str(reduced_dir / f"{symbol}_oco_first_touch_reduced_states.csv"),
                "--out-monthly-csv",
                str(_reduced_monthly_path(stage_root, symbol)),
                "--out-summary-csv",
                str(_reduced_summary_path(stage_root, symbol)),
                "--report-out",
                str(reports_dir / f"{symbol.lower()}_offset_{int(offset):03d}_reduced.md"),
            ],
        ),
        (
            "robustness",
            [
                sys.executable,
                str(ROOT / "scripts/analyze_oco_monthly_wfo_robustness.py"),
                "--pred-path",
                str(_prediction_path(stage_root, symbol)),
                "--quantiles",
                "0.5,0.6,0.7,0.8,0.9,0.95",
                "--bootstrap-paths",
                "600",
                "--stress-extra-cost-grid",
                DEFAULT_STRESS_COST_GRID,
                "--use-exec-selection",
                "true",
                "--execution-quantile",
                "0.9",
                "--reduced-state-schedule-csv",
                str(_reduced_schedule_path(stage_root, symbol)),
                "--out-summary-csv",
                str(_robustness_summary_path(stage_root, symbol)),
                "--out-monthly-csv",
                str(robustness_dir / f"{symbol}_oco_robustness_monthly.csv"),
                "--report-out",
                str(reports_dir / f"{symbol.lower()}_offset_{int(offset):03d}_robustness.md"),
            ],
        ),
    ]

    for _name, cmd in pipeline_steps:
        ok, msg = _run_cmd(cmd, fail_fast=fail_fast)
        if not ok:
            return {
                "symbol": symbol,
                "offset": int(offset),
                "offset_status": "failed_pipeline",
                "failure_reason": msg,
            }, []

    schedule_path = _reduced_schedule_path(stage_root, symbol)
    schedule_df = _load_csv(schedule_path)
    if not schedule_df.empty:
        tick_exact_cmd = [
            sys.executable,
            str(ROOT / "scripts/verify_tick_exact_shortlist.py"),
            "--symbol",
            symbol,
            "--dataset-dir",
            str(velocity_path.parent),
            "--pred-path",
            str(_prediction_path(stage_root, symbol)),
            "--shortlist-state-csv",
            str(schedule_path),
            "--locked-quantile",
            "0.9",
            "--selection-mode",
            "auto",
            "--family-required",
            "oco_first_touch",
            "--oco-hold-mode",
            "from_touch",
            "--oco-include-no-touch",
            "true",
            "--out-summary-csv",
            str(_tick_exact_summary_path(stage_root, symbol)),
            "--out-monthly-csv",
            str(tick_exact_dir / f"{symbol}_oco_first_touch_tick_exact_monthly.csv"),
            "--out-state-csv",
            str(tick_exact_dir / f"{symbol}_oco_first_touch_tick_exact_state.csv"),
            "--report-out",
            str(reports_dir / f"{symbol.lower()}_offset_{int(offset):03d}_tick_exact.md"),
        ]
        ok, msg = _run_cmd(tick_exact_cmd, fail_fast=fail_fast)
        if not ok:
            return {
                "symbol": symbol,
                "offset": int(offset),
                "offset_status": "failed_pipeline",
                "failure_reason": msg,
            }, []

    return _build_by_offset_row(
        symbol=symbol,
        offset=int(offset),
        stage_root=stage_root,
        baseline_row=None,
        baseline_selected=None,
        baseline_states=None,
    )


def _rebuild_rows_against_baseline(
    *,
    symbol: str,
    rows: list[dict[str, Any]],
    out_dir: Path,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    rows_sorted = sorted(rows, key=lambda x: int(x.get("offset", 0)))
    baseline = next(
        (
            r
            for r in rows_sorted
            if int(r.get("offset", -1)) == 0 and r.get("offset_status") != "failed_pipeline"
        ),
        None,
    )
    if baseline is None:
        return rows_sorted, []
    base_root = _offset_stage_root(out_dir, symbol, 0)
    base_selected = _load_selected_signal_keys(
        _prediction_path(base_root, symbol), _reduced_schedule_path(base_root, symbol)
    )
    base_states = _load_schedule_states(_reduced_schedule_path(base_root, symbol))

    final_rows: list[dict[str, Any]] = []
    overlap_rows: list[dict[str, Any]] = []
    for row in rows_sorted:
        if row.get("offset_status") == "failed_pipeline":
            final_rows.append(row)
            continue
        offset = int(row.get("offset", 0))
        stage_root = _offset_stage_root(out_dir, symbol, offset)
        rebuilt, overlaps = _build_by_offset_row(
            symbol=symbol,
            offset=offset,
            stage_root=stage_root,
            baseline_row=baseline,
            baseline_selected=base_selected,
            baseline_states=base_states,
        )
        final_rows.append(rebuilt)
        overlap_rows.extend(overlaps)
    return final_rows, overlap_rows


def _api_stage_root(stage_root: Path, offset: int, warmup_bars: int | None = None) -> Path:
    if warmup_bars is None:
        return stage_root / "api_confirmation" / f"offset_{int(offset):03d}"
    return (
        stage_root
        / "warmup_sensitivity"
        / f"offset_{int(offset):03d}"
        / f"warmup_{int(warmup_bars):03d}"
    )


def _coarse_offsets(all_offsets: list[int], coarse_offsets: list[int]) -> list[int]:
    wanted = sorted(set(int(x) for x in coarse_offsets if int(x) in set(all_offsets)))
    if 0 in all_offsets and 0 not in wanted:
        wanted = [0] + wanted
    return wanted or ([0] if 0 in all_offsets else [int(all_offsets[0])])


def _severity_score(row: dict[str, Any]) -> tuple[int, float, float]:
    status = str(row.get("offset_status", ""))
    if status == "failed_pipeline":
        return (3, float("inf"), float("inf"))
    if status == "no_qualifying_states":
        return (2, float("inf"), float("inf"))
    lb95 = abs(_safe_float(row.get("lb95_trade_mean_gross_pips_delta")))
    selected = abs(_safe_float(row.get("selected_rows_delta_pct")))
    return (
        1 if status == "degraded" else 0,
        lb95 if np.isfinite(lb95) else 0.0,
        selected if np.isfinite(selected) else 0.0,
    )


def _choose_refine_centers(
    *,
    by_offset_df: pd.DataFrame,
    max_centers: int,
) -> list[int]:
    if by_offset_df.empty or max_centers <= 0:
        return []
    flagged = by_offset_df[
        by_offset_df.get("offset_status", pd.Series(dtype=str))
        .astype(str)
        .isin(["degraded", "failed_pipeline", "no_qualifying_states"])
    ].copy()
    if flagged.empty:
        return []
    ranked = flagged.to_dict(orient="records")
    ranked.sort(
        key=lambda r: (
            -_severity_score(r)[0],
            -_severity_score(r)[1],
            -_severity_score(r)[2],
            int(r.get("offset", 0)),
        )
    )
    centers: list[int] = []
    for row in ranked:
        off = int(row.get("offset", 0))
        if off not in centers:
            centers.append(off)
        if len(centers) >= int(max_centers):
            break
    return centers


def _refined_offsets(
    *,
    all_offsets: list[int],
    coarse_offsets: list[int],
    centers: list[int],
    radius: int,
) -> list[int]:
    all_set = set(int(x) for x in all_offsets)
    coarse_set = set(int(x) for x in coarse_offsets)
    refined: set[int] = set()
    for center in centers:
        for off in range(int(center) - int(radius), int(center) + int(radius) + 1):
            if off in all_set and off not in coarse_set:
                refined.add(off)
    return sorted(refined)


def _offsets_for_api_and_warmup(
    *,
    completed_offsets: list[int],
    flagged_centers: list[int],
    api_confirm_offsets: list[int],
) -> list[int]:
    keep = {0}
    keep.update(int(x) for x in flagged_centers)
    keep.update(int(x) for x in api_confirm_offsets)
    done = set(int(x) for x in completed_offsets)
    return sorted(x for x in keep if x in done)


def _offsets_to_retain(
    *,
    completed_offsets: list[int],
    flagged_centers: list[int],
    retain_flagged_offset_runs: bool,
) -> list[int]:
    if not retain_flagged_offset_runs:
        return []
    keep = {0}
    keep.update(int(x) for x in flagged_centers)
    done = set(int(x) for x in completed_offsets)
    return sorted(x for x in keep if x in done)


def _cleanup_symbol_stage_roots(
    *,
    out_dir: Path,
    symbol: str,
    completed_offsets: list[int],
    keep_offsets: list[int],
) -> None:
    keep = set(int(x) for x in keep_offsets)
    for offset in completed_offsets:
        if int(offset) in keep:
            continue
        stage_root = _offset_stage_root(out_dir, symbol, int(offset))
        if stage_root.exists():
            shutil.rmtree(stage_root)


def _write_incremental_outputs(
    *,
    out_dir: Path,
    symbols: list[str],
    summary_rows: list[dict[str, Any]],
    by_offset_rows: list[dict[str, Any]],
    overlap_rows_all: list[dict[str, Any]],
    api_frames: list[pd.DataFrame],
    warmup_frames: list[pd.DataFrame],
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    summary_df = (
        pd.DataFrame(summary_rows).sort_values("symbol").reset_index(drop=True)
        if summary_rows
        else pd.DataFrame()
    )
    by_offset_df = (
        pd.DataFrame(by_offset_rows).sort_values(["symbol", "offset"]).reset_index(drop=True)
        if by_offset_rows
        else pd.DataFrame()
    )
    overlap_df = (
        pd.DataFrame(overlap_rows_all)
        .sort_values(["symbol", "offset", "test_month"])
        .reset_index(drop=True)
        if overlap_rows_all
        else pd.DataFrame()
    )
    api_df = pd.concat(api_frames, ignore_index=True) if api_frames else pd.DataFrame()
    warmup_df = pd.concat(warmup_frames, ignore_index=True) if warmup_frames else pd.DataFrame()

    for symbol in symbols:
        sym_by_offset = (
            by_offset_df[by_offset_df["symbol"] == symbol].copy()
            if not by_offset_df.empty
            else pd.DataFrame()
        )
        sym_overlap = (
            overlap_df[overlap_df["symbol"] == symbol].copy()
            if not overlap_df.empty
            else pd.DataFrame()
        )
        sym_api = api_df[api_df["symbol"] == symbol].copy() if not api_df.empty else pd.DataFrame()
        sym_warmup = (
            warmup_df[warmup_df["symbol"] == symbol].copy()
            if not warmup_df.empty
            else pd.DataFrame()
        )
        sym_by_offset.to_csv(out_dir / f"{symbol}_offset_robustness_by_offset.csv", index=False)
        sym_overlap.to_csv(out_dir / f"{symbol}_offset_state_overlap.csv", index=False)
        sym_warmup.to_csv(out_dir / f"{symbol}_warmup_sensitivity.csv", index=False)
        sym_api.to_csv(out_dir / f"{symbol}_api_offset_confirmation.csv", index=False)

    summary_df.to_csv(out_dir / "offset_robustness_summary.csv", index=False)
    return summary_df, by_offset_df, overlap_df, api_df, warmup_df


def _replace_symbol_frame(
    frames: list[pd.DataFrame], symbol: str, frame: pd.DataFrame
) -> list[pd.DataFrame]:
    kept: list[pd.DataFrame] = []
    for df in frames:
        if df.empty:
            continue
        vals = set(df.get("symbol", pd.Series(dtype=str)).astype(str).unique())
        if vals == {symbol}:
            continue
        kept.append(df)
    if not frame.empty:
        kept.append(frame)
    return kept


def _run_api_replay(
    *,
    symbol: str,
    offset: int,
    stage_root: Path,
    tick_root: Path,
    start_ts: str,
    end_ts: str,
    warmup_ticks: int,
    fail_fast: bool,
) -> tuple[dict[str, Any], pd.DataFrame]:
    raise NotImplementedError(
        "cBot testclient replay was removed. JForex equivalent is a future task."
    )


def _run_api_confirmation_and_warmup(
    *,
    symbol: str,
    offsets: list[int],
    stage_out_dir: Path,
    tick_root: Path,
    start_ts: str,
    end_ts: str,
    warmup_bars_grid: list[int],
    fail_fast: bool,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    api_rows: list[dict[str, Any]] = []
    warmup_rows: list[dict[str, Any]] = []

    for offset in offsets:
        stage_root = _offset_stage_root(stage_out_dir, symbol, int(offset))
        if (
            not _prediction_path(stage_root, symbol).exists()
            or not _reduced_schedule_path(stage_root, symbol).exists()
        ):
            api_rows.append(
                {
                    "symbol": symbol,
                    "offset": int(offset),
                    "signal_parity_pass": False,
                    "execution_parity_pass": False,
                    "selected_missing_expected": np.nan,
                    "selected_extra_runtime": np.nan,
                    "execution_failed_checks_high_critical": np.nan,
                    "runtime_selected_rows": 0,
                    "runtime_trade_rows": 0,
                    "runtime_mean_gross_pips": np.nan,
                    "runtime_mean_net_pips": np.nan,
                    "mean_gross_pips_delta_vs_repo_offset_baseline": np.nan,
                    "mean_net_pips_delta_vs_repo_offset_baseline": np.nan,
                    "api_confirmation_status": "no_qualifying_states",
                    "failure_reason": "missing_offset_repo_truth",
                }
            )
            continue
        base_row, _ = _run_api_replay(
            symbol=symbol,
            offset=int(offset),
            stage_root=stage_root,
            tick_root=tick_root,
            start_ts=start_ts,
            end_ts=end_ts,
            warmup_ticks=30000,
            fail_fast=fail_fast,
        )
        repo_perf = _prediction_perf_for_keys(
            _prediction_path(stage_root, symbol),
            _stop_limit_detail_path(stage_root, symbol),
            _load_selected_signal_keys(
                _prediction_path(stage_root, symbol), _reduced_schedule_path(stage_root, symbol)
            ),
        )
        base_row["mean_gross_pips_delta_vs_repo_offset_baseline"] = _safe_float(
            base_row.get("runtime_mean_gross_pips")
        ) - _safe_float(repo_perf.get("mean_gross_pips"))
        base_row["mean_net_pips_delta_vs_repo_offset_baseline"] = _safe_float(
            base_row.get("runtime_mean_net_pips")
        ) - _safe_float(repo_perf.get("mean_net_pips"))
        api_rows.append(base_row)

        baseline_warmup: dict[str, Any] | None = None
        baseline_keys = pd.DataFrame()
        warmup_records: list[tuple[dict[str, Any], pd.DataFrame]] = []
        for warmup_bars in warmup_bars_grid:
            warmup_ticks = int(warmup_bars) * 100
            row, runtime_keys = _run_api_replay(
                symbol=symbol,
                offset=int(offset),
                stage_root=stage_root,
                tick_root=tick_root,
                start_ts=start_ts,
                end_ts=end_ts,
                warmup_ticks=warmup_ticks,
                fail_fast=fail_fast,
            )
            row["warmup_bars"] = int(warmup_bars)
            row["first_feature_available_bar"] = max(
                1, int(MIN_FEATURE_BARS) - int(warmup_bars) + 1
            )
            row["first_full_precision_bar"] = max(1, int(FULL_FEATURE_BARS) - int(warmup_bars) + 1)
            if int(warmup_bars) == FULL_FEATURE_BARS:
                baseline_warmup = dict(row)
                baseline_keys = runtime_keys.copy()
            warmup_records.append((row, runtime_keys.copy()))

        if baseline_warmup is None:
            warmup_rows.extend([row for row, _ in warmup_records])
            continue
        for row, runtime_keys in warmup_records:
            row["signal_parity_drift_vs_289"] = _selected_key_diff_count(
                baseline_keys, runtime_keys
            )
            row["gated_mean_gross_pips_delta_vs_289"] = _safe_float(
                row.get("runtime_mean_gross_pips")
            ) - _safe_float(baseline_warmup.get("runtime_mean_gross_pips"))
            row["gated_mean_net_pips_delta_vs_289"] = _safe_float(
                row.get("runtime_mean_net_pips")
            ) - _safe_float(baseline_warmup.get("runtime_mean_net_pips"))
            warmup_rows.append(row)

    api_df = pd.DataFrame(api_rows)
    warmup_df = pd.DataFrame(warmup_rows)
    if not warmup_df.empty:
        plateau_rows: list[dict[str, Any]] = []
        for (sym, offset), g in warmup_df.groupby(["symbol", "offset"], sort=True):
            g2 = g.sort_values("warmup_bars").copy()
            elig = g2[
                (
                    pd.to_numeric(g2["signal_parity_drift_vs_289"], errors="coerce").fillna(999999)
                    == 0
                )
                & (
                    pd.to_numeric(g2["gated_mean_gross_pips_delta_vs_289"], errors="coerce").abs()
                    <= 0.05
                )
            ].copy()
            plateau = int(elig["warmup_bars"].iloc[0]) if not elig.empty else np.nan
            plateau_rows.append(
                {"symbol": sym, "offset": int(offset), "plateau_warmup_bars": plateau}
            )
        plateau_df = pd.DataFrame(plateau_rows)
        warmup_df = warmup_df.merge(plateau_df, on=["symbol", "offset"], how="left")
    return api_df, warmup_df


def _classification(by_offset: pd.DataFrame, api_df: pd.DataFrame, warmup_df: pd.DataFrame) -> str:
    failed = (
        int(
            by_offset.get("offset_status", pd.Series(dtype=str))
            .astype(str)
            .eq("failed_pipeline")
            .sum()
        )
        if not by_offset.empty
        else 0
    )
    noq = (
        int(
            by_offset.get("offset_status", pd.Series(dtype=str))
            .astype(str)
            .eq("no_qualifying_states")
            .sum()
        )
        if not by_offset.empty
        else 0
    )
    degraded = (
        int(by_offset.get("offset_status", pd.Series(dtype=str)).astype(str).eq("degraded").sum())
        if not by_offset.empty
        else 0
    )
    api_fail = (
        int(
            api_df.get("api_confirmation_status", pd.Series(dtype=str))
            .astype(str)
            .isin(["fail", "failed_pipeline"])
            .sum()
        )
        if not api_df.empty
        else 0
    )
    plateau_missing = (
        int(warmup_df.get("plateau_warmup_bars", pd.Series(dtype=float)).isna().sum())
        if not warmup_df.empty
        else 0
    )
    if failed > 0 or api_fail > 0 or plateau_missing > 0 or noq > 0:
        return "materially_phase_sensitive"
    if degraded > 0:
        return "mildly_phase_sensitive"
    return "stable"


def _write_symbol_report(
    *,
    symbol: str,
    summary_row: dict[str, Any],
    by_offset: pd.DataFrame,
    state_overlap: pd.DataFrame,
    api_df: pd.DataFrame,
    warmup_df: pd.DataFrame,
    out_path: Path,
) -> None:
    def _table(df: pd.DataFrame) -> str:
        if df.empty:
            return "_empty_"
        try:
            return df.to_markdown(index=False)
        except Exception:
            return "```\n" + df.to_string(index=False) + "\n```"

    lines = [
        "# Offset Tick-Bar Robustness Report",
        "",
        f"- symbol: `{symbol}`",
        f"- classification: `{summary_row.get('phase_classification', 'unknown')}`",
        f"- study_mode: `{summary_row.get('study_mode', 'exhaustive')}`",
        f"- retention_mode: `{summary_row.get('retention_mode', 'full')}`",
        f"- offsets_evaluated: `{summary_row.get('offsets_total', 0)}`",
        f"- offsets_screened: `{summary_row.get('offsets_screened', 0)}`",
        f"- offsets_refined: `{summary_row.get('offsets_refined', 0)}`",
        f"- degraded_offsets: `{summary_row.get('degraded_count', 0)}`",
        f"- failed_pipeline_offsets: `{summary_row.get('failed_pipeline_count', 0)}`",
        f"- no_qualifying_states_offsets: `{summary_row.get('no_qualifying_states_count', 0)}`",
        "",
        "## By Offset",
        "",
        _table(by_offset),
        "",
        "## Warmup Sensitivity",
        "",
        _table(warmup_df),
        "",
        "## API Confirmation",
        "",
        _table(api_df),
        "",
        "## State Overlap",
        "",
        _table(state_overlap),
        "",
        "## Interpretation",
        "",
        "- `stable`: no advisory threshold breaches, no API sampled-offset failures, and warmup plateau observed across sampled offsets.",
        "- `mildly_phase_sensitive`: repo pipeline completes but one or more advisory degradation thresholds breach.",
        "- `materially_phase_sensitive`: sampled API parity fails, pipeline fails on one or more offsets, warmup plateau is not reached, or offsets lose qualifying states.",
        "",
        "## Notes",
        "",
        "- `mean_net_pips` and `lb95_trade_mean_net_pips` use the Stage 8 `costplus_0.10` fields because there is no plain net field in the current downstream artifacts.",
        f"- full_precision_warmup_bars: `{FULL_FEATURE_BARS}`",
        f"- minimum_usable_warmup_bars: `{MIN_FEATURE_BARS}`",
    ]
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")


def run(
    *,
    symbols: list[str],
    offsets: list[int],
    mode: str,
    coarse_offsets: list[int],
    refine_radius: int,
    max_refine_centers_per_symbol: int,
    tick_root: Path,
    offset_bar_dir: Path,
    out_dir: Path,
    retention_mode: str,
    retain_flagged_offset_runs: bool,
    api_confirm_offsets: list[int],
    warmup_bars_grid: list[int],
    stage12_start_ts: str,
    stage12_end_ts: str,
    overwrite_offset_bars: bool,
    skip_api_confirmation: bool,
    skip_warmup_sensitivity: bool,
    fail_fast: bool,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    out_dir.mkdir(parents=True, exist_ok=True)
    requested_offsets = sorted(set(int(x) for x in offsets))
    coarse_requested = _coarse_offsets(
        requested_offsets, coarse_offsets if str(mode) == "adaptive" else requested_offsets
    )
    build_offsets = requested_offsets if str(mode) == "exhaustive" else coarse_requested

    _ensure_offset_bars(
        symbols=symbols,
        offsets=build_offsets,
        tick_root=tick_root,
        offset_bar_dir=offset_bar_dir,
        overwrite=overwrite_offset_bars,
        fail_fast=fail_fast,
    )

    summary_rows: list[dict[str, Any]] = []
    by_offset_rows: list[dict[str, Any]] = []
    overlap_rows_all: list[dict[str, Any]] = []
    api_all: list[pd.DataFrame] = []
    warmup_all: list[pd.DataFrame] = []

    for symbol in symbols:
        raw_rows: list[dict[str, Any]] = []
        completed_offsets: list[int] = []
        coarse_done = coarse_requested if str(mode) == "adaptive" else requested_offsets
        for offset in coarse_done:
            row, overlap_rows = _run_symbol_offset_pipeline(
                symbol=symbol,
                offset=int(offset),
                tick_root=tick_root,
                offset_bar_dir=offset_bar_dir,
                out_dir=out_dir,
                fail_fast=fail_fast,
            )
            raw_rows.append(row)
            completed_offsets.append(int(offset))
            overlap_rows_all.extend(overlap_rows)

        symbol_rows, rebuilt_overlap = _rebuild_rows_against_baseline(
            symbol=symbol, rows=raw_rows, out_dir=out_dir
        )
        overlap_rows_all.extend(rebuilt_overlap)

        refine_centers: list[int] = []
        refined_offsets: list[int] = []
        if str(mode) == "adaptive":
            coarse_df = pd.DataFrame(symbol_rows).sort_values("offset").reset_index(drop=True)
            refine_centers = _choose_refine_centers(
                by_offset_df=coarse_df, max_centers=max_refine_centers_per_symbol
            )
            refined_offsets = _refined_offsets(
                all_offsets=requested_offsets,
                coarse_offsets=coarse_done,
                centers=refine_centers,
                radius=refine_radius,
            )
            if refined_offsets:
                extra = [x for x in refined_offsets if x not in build_offsets]
                if extra:
                    _ensure_offset_bars(
                        symbols=[symbol],
                        offsets=extra,
                        tick_root=tick_root,
                        offset_bar_dir=offset_bar_dir,
                        overwrite=overwrite_offset_bars,
                        fail_fast=fail_fast,
                    )
                for offset in refined_offsets:
                    row, overlap_rows = _run_symbol_offset_pipeline(
                        symbol=symbol,
                        offset=int(offset),
                        tick_root=tick_root,
                        offset_bar_dir=offset_bar_dir,
                        out_dir=out_dir,
                        fail_fast=fail_fast,
                    )
                    raw_rows.append(row)
                    completed_offsets.append(int(offset))
                    overlap_rows_all.extend(overlap_rows)
                symbol_rows, rebuilt_overlap = _rebuild_rows_against_baseline(
                    symbol=symbol, rows=raw_rows, out_dir=out_dir
                )
                overlap_rows_all.extend(rebuilt_overlap)

        by_offset_df = pd.DataFrame(symbol_rows).sort_values("offset").reset_index(drop=True)
        by_offset_rows = [r for r in by_offset_rows if r.get("symbol") != symbol]
        by_offset_rows.extend(by_offset_df.to_dict(orient="records"))

        if skip_api_confirmation:
            api_df = pd.DataFrame()
        else:
            sample_offsets = _offsets_for_api_and_warmup(
                completed_offsets=completed_offsets,
                flagged_centers=refine_centers,
                api_confirm_offsets=api_confirm_offsets,
            )
            api_df, warmup_df = _run_api_confirmation_and_warmup(
                symbol=symbol,
                offsets=sample_offsets,
                stage_out_dir=out_dir,
                tick_root=tick_root,
                start_ts=stage12_start_ts,
                end_ts=stage12_end_ts,
                warmup_bars_grid=[] if skip_warmup_sensitivity else warmup_bars_grid,
                fail_fast=fail_fast,
            )
            api_all = _replace_symbol_frame(api_all, symbol, api_df)
            warmup_all = _replace_symbol_frame(warmup_all, symbol, warmup_df)
        if skip_api_confirmation:
            api_df = pd.DataFrame()
        if skip_api_confirmation or skip_warmup_sensitivity:
            warmup_df = pd.DataFrame()

        classification = _classification(by_offset_df, api_df, warmup_df)
        summary_row = {
            "symbol": symbol,
            "offsets_total": int(len(by_offset_df)),
            "offsets_screened": int(len(coarse_done)),
            "offsets_refined": int(len(refined_offsets)),
            "study_mode": str(mode),
            "retention_mode": str(retention_mode),
            "ok_count": int(
                by_offset_df.get("offset_status", pd.Series(dtype=str)).astype(str).eq("ok").sum()
            )
            if not by_offset_df.empty
            else 0,
            "degraded_count": int(
                by_offset_df.get("offset_status", pd.Series(dtype=str))
                .astype(str)
                .eq("degraded")
                .sum()
            )
            if not by_offset_df.empty
            else 0,
            "failed_pipeline_count": int(
                by_offset_df.get("offset_status", pd.Series(dtype=str))
                .astype(str)
                .eq("failed_pipeline")
                .sum()
            )
            if not by_offset_df.empty
            else 0,
            "no_qualifying_states_count": int(
                by_offset_df.get("offset_status", pd.Series(dtype=str))
                .astype(str)
                .eq("no_qualifying_states")
                .sum()
            )
            if not by_offset_df.empty
            else 0,
            "phase_classification": classification,
            "api_confirmation_fail_count": int(
                api_df.get("api_confirmation_status", pd.Series(dtype=str))
                .astype(str)
                .isin(["fail", "failed_pipeline"])
                .sum()
            )
            if not api_df.empty
            else 0,
            "warmup_plateau_max_bars": float(
                pd.to_numeric(
                    warmup_df.get("plateau_warmup_bars", pd.Series(dtype=float)), errors="coerce"
                ).max()
            )
            if not warmup_df.empty
            else float("nan"),
            "report_path": _display_path(_offset_report_path(symbol, out_dir=out_dir)),
        }
        summary_rows.append(summary_row)
        state_overlap_df = (
            pd.DataFrame([r for r in overlap_rows_all if r.get("symbol") == symbol]).sort_values(
                ["offset", "test_month"]
            )
            if overlap_rows_all
            else pd.DataFrame()
        )
        _write_symbol_report(
            symbol=symbol,
            summary_row=summary_row,
            by_offset=by_offset_df,
            state_overlap=state_overlap_df,
            api_df=api_df,
            warmup_df=warmup_df,
            out_path=_offset_report_path(symbol, out_dir=out_dir),
        )
        summary_df, by_offset_df_all, overlap_df, api_df_all, warmup_df_all = (
            _write_incremental_outputs(
                out_dir=out_dir,
                symbols=symbols,
                summary_rows=summary_rows,
                by_offset_rows=by_offset_rows,
                overlap_rows_all=overlap_rows_all,
                api_frames=api_all,
                warmup_frames=warmup_all,
            )
        )
        if str(retention_mode) == "compact":
            keep_offsets = _offsets_to_retain(
                completed_offsets=completed_offsets,
                flagged_centers=refine_centers,
                retain_flagged_offset_runs=retain_flagged_offset_runs,
            )
            _cleanup_symbol_stage_roots(
                out_dir=out_dir,
                symbol=symbol,
                completed_offsets=completed_offsets,
                keep_offsets=keep_offsets,
            )

    summary_df, by_offset_df, overlap_df, api_df, warmup_df = _write_incremental_outputs(
        out_dir=out_dir,
        symbols=symbols,
        summary_rows=summary_rows,
        by_offset_rows=by_offset_rows,
        overlap_rows_all=overlap_rows_all,
        api_frames=api_all,
        warmup_frames=warmup_all,
    )
    print(
        f"wrote study summary: {out_dir / 'offset_robustness_summary.csv'} rows={len(summary_df)}"
    )
    return summary_df, by_offset_df, overlap_df, api_df, warmup_df


def main() -> None:
    p = argparse.ArgumentParser(description="Run offset tick-bar robustness study")
    p.add_argument("--symbols", default=",".join(ACTIVE_SYMBOLS))
    p.add_argument("--offsets", default=",".join(str(x) for x in DEFAULT_OFFSETS))
    p.add_argument("--mode", choices=["adaptive", "exhaustive"], default="adaptive")
    p.add_argument("--coarse-offsets", default=",".join(str(x) for x in DEFAULT_COARSE_OFFSETS))
    p.add_argument("--refine-radius", type=int, default=2)
    p.add_argument("--max-refine-centers-per-symbol", type=int, default=2)
    p.add_argument("--tick-root", default=DEFAULT_TICK_ROOT)
    p.add_argument("--offset-bar-dir", default=DEFAULT_OFFSET_BAR_DIR)
    p.add_argument("--out-dir", default=DEFAULT_OUT_DIR)
    p.add_argument("--retention-mode", choices=["compact", "full"], default="compact")
    p.add_argument("--retain-flagged-offset-runs", default="true")
    p.add_argument(
        "--api-confirm-offsets", default=",".join(str(x) for x in DEFAULT_API_CONFIRM_OFFSETS)
    )
    p.add_argument("--warmup-bars-grid", default=",".join(str(x) for x in DEFAULT_WARMUP_BARS_GRID))
    p.add_argument("--stage12-start-ts", default="2025-07-07T00:00:00Z")
    p.add_argument("--stage12-end-ts", default="2025-07-09T00:00:00Z")
    p.add_argument("--overwrite-offset-bars", action="store_true")
    p.add_argument("--skip-api-confirmation", action="store_true")
    p.add_argument("--skip-warmup-sensitivity", action="store_true")
    p.add_argument("--fail-fast", action="store_true")
    args = p.parse_args()

    run(
        symbols=_parse_symbols(str(args.symbols)),
        offsets=sorted(set(_parse_csv_ints(str(args.offsets)))),
        mode=str(args.mode),
        coarse_offsets=sorted(set(_parse_csv_ints(str(args.coarse_offsets)))),
        refine_radius=int(args.refine_radius),
        max_refine_centers_per_symbol=int(args.max_refine_centers_per_symbol),
        tick_root=Path(str(args.tick_root)),
        offset_bar_dir=Path(str(args.offset_bar_dir)),
        out_dir=Path(str(args.out_dir)),
        retention_mode=str(args.retention_mode),
        retain_flagged_offset_runs=_as_bool(args.retain_flagged_offset_runs),
        api_confirm_offsets=sorted(set(_parse_csv_ints(str(args.api_confirm_offsets)))),
        warmup_bars_grid=sorted(set(_parse_csv_ints(str(args.warmup_bars_grid)))),
        stage12_start_ts=str(args.stage12_start_ts),
        stage12_end_ts=str(args.stage12_end_ts),
        overwrite_offset_bars=bool(args.overwrite_offset_bars),
        skip_api_confirmation=bool(args.skip_api_confirmation),
        skip_warmup_sensitivity=bool(args.skip_warmup_sensitivity),
        fail_fast=bool(args.fail_fast),
    )


if __name__ == "__main__":
    main()
