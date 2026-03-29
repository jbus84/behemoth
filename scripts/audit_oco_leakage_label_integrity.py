#!/usr/bin/env python3
"""Leakage + label integrity audit for OCO WFO pipeline artifacts.

Checks L01..L12 across EURUSD/GBPUSD/USDJPY and emits:
- checks CSV (pass/fail + metrics)
- issues CSV (failed checks only)
- markdown report
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from pandas.errors import EmptyDataError

try:
    import yaml
except ImportError:
    yaml = None


@dataclass(frozen=True)
class SymbolConfig:
    symbol: str
    pred_path: Path
    metrics_path: Path
    thresholds_path: Path
    events_path: Path
    schedule_path: Path
    monthly_path: Path
    lock_path: Path
    min_train_months: int = 3
    max_null_shift: float = 0.01


def _default_configs() -> dict[str, SymbolConfig]:
    defaults = {
        "EURUSD": SymbolConfig(
            symbol="EURUSD",
            pred_path=Path(
                "data/analysis/tick_opportunity_mining/wfo_m3to1_oco_fullcap/EURUSD_oco_monthly_predictions.parquet"
            ),
            metrics_path=Path(
                "data/analysis/tick_opportunity_mining/wfo_m3to1_oco_fullcap/EURUSD_oco_monthly_metrics.csv"
            ),
            thresholds_path=Path(
                "data/analysis/tick_opportunity_mining/wfo_m3to1_oco_fullcap/EURUSD_oco_monthly_thresholds.csv"
            ),
            events_path=Path(
                "data/analysis/tick_opportunity_mining/wfo_m3to1_oco_fullcap/EURUSD_oco_events_eval2025.parquet"
            ),
            schedule_path=Path(
                "data/analysis/tick_opportunity_mining/reduced_core_rolling/EURUSD_oco_reduced_state_schedule.csv"
            ),
            monthly_path=Path(
                "data/analysis/tick_opportunity_mining/reduced_core_rolling/EURUSD_oco_reduced_monthly.csv"
            ),
            lock_path=Path("configs/research/governance/oco/eurusd_oco_live_lock.json"),
        ),
        "GBPUSD": SymbolConfig(
            symbol="GBPUSD",
            pred_path=Path(
                "data/analysis/tick_opportunity_mining/wfo_m3to1_oco_fullcap/GBPUSD_oco_monthly_predictions.parquet"
            ),
            metrics_path=Path(
                "data/analysis/tick_opportunity_mining/wfo_m3to1_oco_fullcap/GBPUSD_oco_monthly_metrics.csv"
            ),
            thresholds_path=Path(
                "data/analysis/tick_opportunity_mining/wfo_m3to1_oco_fullcap/GBPUSD_oco_monthly_thresholds.csv"
            ),
            events_path=Path(
                "data/analysis/tick_opportunity_mining/wfo_m3to1_oco_fullcap/GBPUSD_oco_events_eval2025.parquet"
            ),
            schedule_path=Path(
                "data/analysis/tick_opportunity_mining/reduced_core_rolling/GBPUSD_oco_reduced_state_schedule.csv"
            ),
            monthly_path=Path(
                "data/analysis/tick_opportunity_mining/reduced_core_rolling/GBPUSD_oco_reduced_monthly.csv"
            ),
            lock_path=Path("configs/research/governance/oco/gbpusd_oco_live_lock.json"),
        ),
        "USDJPY": SymbolConfig(
            symbol="USDJPY",
            pred_path=Path(
                "data/analysis/tick_opportunity_mining/wfo_m3to1_oco_fullcap/USDJPY_oco_monthly_predictions.parquet"
            ),
            metrics_path=Path(
                "data/analysis/tick_opportunity_mining/wfo_m3to1_oco_fullcap/USDJPY_oco_monthly_metrics.csv"
            ),
            thresholds_path=Path(
                "data/analysis/tick_opportunity_mining/wfo_m3to1_oco_fullcap/USDJPY_oco_monthly_thresholds.csv"
            ),
            events_path=Path(
                "data/analysis/tick_opportunity_mining/wfo_m3to1_oco_fullcap/USDJPY_oco_events_eval2025.parquet"
            ),
            schedule_path=Path(
                "data/analysis/tick_opportunity_mining/reduced_core_rolling/USDJPY_oco_reduced_state_schedule.csv"
            ),
            monthly_path=Path(
                "data/analysis/tick_opportunity_mining/reduced_core_rolling/USDJPY_oco_reduced_monthly.csv"
            ),
            lock_path=Path("configs/research/governance/oco/usdjpy_oco_live_lock.json"),
        ),
    }

    lock_dir = Path("configs/research/governance/oco")
    if lock_dir.exists():
        for p in lock_dir.glob("*_oco_live_lock.json"):
            s = p.name.split("_")[0].upper()
            if s not in defaults:
                defaults[s] = SymbolConfig(
                    symbol=s,
                    pred_path=Path(
                        f"data/analysis/tick_opportunity_mining/wfo_m3to1_oco_fullcap/{s}_oco_monthly_predictions.parquet"
                    ),
                    metrics_path=Path(
                        f"data/analysis/tick_opportunity_mining/wfo_m3to1_oco_fullcap/{s}_oco_monthly_metrics.csv"
                    ),
                    thresholds_path=Path(
                        f"data/analysis/tick_opportunity_mining/wfo_m3to1_oco_fullcap/{s}_oco_monthly_thresholds.csv"
                    ),
                    events_path=Path(
                        f"data/analysis/tick_opportunity_mining/wfo_m3to1_oco_fullcap/{s}_oco_events_eval2025.parquet"
                    ),
                    schedule_path=Path(
                        f"data/analysis/tick_opportunity_mining/reduced_core_rolling/{s}_oco_reduced_state_schedule.csv"
                    ),
                    monthly_path=Path(
                        f"data/analysis/tick_opportunity_mining/reduced_core_rolling/{s}_oco_reduced_monthly.csv"
                    ),
                    lock_path=p,
                )
    return defaults


FEATURE_BASE = [
    "cost_est_pips",
    "range_pips",
    "ret1_pips",
    "ret_z",
    "ret_abs_z",
    "vel_cost_units_h1",
    "vel_abs_cost_units_h1",
    "spread_z",
    "tick_rate_z",
    "hour_utc",
    "hl_first",
    "hl_first_mean_24",
    "hl_pos_frac_mean_24",
    "bar_ticks",
    "horizon",
    "barrier_pips",
]

LINEAGE_MAP = {
    "cost_est_pips": "bar close-time estimated cost, no forward dependency",
    "range_pips": "current bar high-low range",
    "ret1_pips": "current bar move feature",
    "ret_z": "rolling z-score using lagged rolling std",
    "ret_abs_z": "abs(ret_z)",
    "vel_cost_units_h1": "cost-normalized velocity from historical ticks",
    "vel_abs_cost_units_h1": "abs(vel_cost_units_h1)",
    "spread_z": "normalized spread at bar close",
    "tick_rate_z": "normalized tick-rate at bar close",
    "hour_utc": "close_ts UTC hour",
    "hl_first": "bar path signature from current bar",
    "hl_first_mean_24": "lagged rolling mean of hl_first",
    "hl_pos_frac_mean_24": "lagged rolling positive-fraction of hl_first",
    "bar_ticks": "bar size metadata",
    "horizon": "candidate horizon metadata",
    "barrier_pips": "candidate barrier metadata",
}

BANNED_FEATURE_PATTERNS = [
    r"^target_",
    r"^y_fwd",
    r"first_touch",
    r"run_remaining",
    r"future",
    r"lead",
    r"next_",
]


def _parse_symbols(raw: str) -> list[str]:
    return [x.strip().upper() for x in str(raw).split(",") if x.strip()]


def _table(df: pd.DataFrame) -> str:
    if df.empty:
        return "_empty_"
    try:
        return df.to_markdown(index=False)
    except Exception:
        return "```\n" + df.to_string(index=False) + "\n```"


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _dt_utc(series: pd.Series) -> pd.Series:
    try:
        return pd.to_datetime(series, utc=True, errors="coerce", format="mixed")
    except TypeError:
        return pd.to_datetime(series, utc=True, errors="coerce")


def _uid_symbol(uid: str) -> str:
    toks = str(uid).split("|")
    if len(toks) < 2:
        return ""
    return str(toks[1]).upper()


def _month_to_int(v: str) -> int:
    s = str(v).replace("-", "").strip()
    if len(s) != 6 or (not s.isdigit()):
        return -1
    return int(s)


def _safe_num(s: pd.Series) -> pd.Series:
    return pd.to_numeric(s, errors="coerce")


def _safe_read_csv(path: Path) -> pd.DataFrame:
    try:
        return pd.read_csv(path).copy()
    except EmptyDataError:
        return pd.DataFrame()


def _make_issue(
    *,
    symbol: str,
    check_id: str,
    severity: str,
    component: str,
    description: str,
    details: dict[str, Any],
) -> dict[str, Any]:
    return {
        "issue_id": f"{symbol}_{check_id}",
        "symbol": symbol,
        "check_id": check_id,
        "severity": severity,
        "component": component,
        "summary": description,
        "details_json": json.dumps(details, sort_keys=True),
    }


def _load_artifacts(
    cfg: SymbolConfig,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    p = pd.read_parquet(cfg.pred_path).copy()
    keep_cols = [
        "test_month",
        "close_ts",
        "candidate_uid",
        "pred_prob",
        "target_gross_pips",
        "target_gross_pos",
        "threshold_mode",
        "threshold_days",
        "threshold_exec",
        "selected_exec",
        "threshold_source",
    ]
    for c in keep_cols:
        if c not in p.columns:
            p[c] = np.nan
    p = p[keep_cols].copy()
    p["test_month"] = p["test_month"].astype(str)
    p["close_ts"] = _dt_utc(p["close_ts"])
    p["candidate_uid"] = p["candidate_uid"].astype(str)
    p["pred_prob"] = _safe_num(p["pred_prob"])
    p["target_gross_pips"] = _safe_num(p["target_gross_pips"])
    p["target_gross_pos"] = _safe_num(p["target_gross_pos"])
    p["threshold_days"] = _safe_num(p["threshold_days"])
    p["threshold_exec"] = _safe_num(p["threshold_exec"])
    p["selected_exec"] = _safe_num(p["selected_exec"]).fillna(0).astype(int)
    p["threshold_source"] = p["threshold_source"].astype(str).str.strip().str.lower()
    p = p.dropna(subset=["test_month", "close_ts", "candidate_uid"]).copy()

    m = _safe_read_csv(cfg.metrics_path)
    if "test_month" in m.columns:
        m["test_month"] = m["test_month"].astype(str)
    for c in ["train_start", "train_end", "test_start", "test_end"]:
        if c in m.columns:
            m[c] = _dt_utc(m[c])

    t = _safe_read_csv(cfg.thresholds_path)
    if "test_month" in t.columns:
        t["test_month"] = t["test_month"].astype(str)

    e = pd.read_parquet(cfg.events_path).copy()
    e["close_ts"] = _dt_utc(e["close_ts"])
    e["candidate_uid"] = e["candidate_uid"].astype(str)

    s = _safe_read_csv(cfg.schedule_path)
    if "test_month" in s.columns:
        s["test_month"] = s["test_month"].astype(str)
    return p, m, t, e, s


def audit_symbol(
    cfg: SymbolConfig, exceptions: dict[str, Any] | None = None
) -> tuple[pd.DataFrame, pd.DataFrame]:
    checks: list[dict[str, Any]] = []
    issues: list[dict[str, Any]] = []
    monthly = _safe_read_csv(cfg.monthly_path)
    if "test_month" in monthly.columns:
        monthly["test_month"] = monthly["test_month"].astype(str)
    pred, metrics, thresholds, events, schedule = _load_artifacts(cfg)
    selected = pred[pred["selected_exec"] == 1].copy()

    def add_check(
        check_id: str,
        check_name: str,
        status: str,
        severity_if_fail: str,
        component: str,
        metric_name: str,
        metric_value: float,
        threshold: str,
        comparator: str,
        details: dict[str, Any],
        fail_desc: str,
    ) -> None:
        # Check for monitoring exceptions
        final_status = status
        if status == "fail" and exceptions:
            for rule in exceptions.get("rules", []):
                rid = rule.get("metric_id")
                if rid in (check_name, check_id):
                    syms = rule.get("symbols", [])
                    if ((not syms) or (cfg.symbol in syms)) and rule.get(
                        "disposition"
                    ) == "accepted_exception":
                        final_status = "accepted_exception"
                        break

        row = {
            "symbol": cfg.symbol,
            "check_id": check_id,
            "check_name": check_name,
            "status": final_status,
            "severity_if_fail": severity_if_fail,
            "component": component,
            "metric_name": metric_name,
            "metric_value": metric_value,
            "threshold": threshold,
            "comparator": comparator,
            "details_json": json.dumps(details, sort_keys=True),
            "evaluated_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
        checks.append(row)
        if final_status == "fail":
            issues.append(
                _make_issue(
                    symbol=cfg.symbol,
                    check_id=check_id,
                    severity=severity_if_fail,
                    component=component,
                    description=fail_desc,
                    details=details,
                )
            )

    # L01: strict WFO time order and prediction window bounds.
    bad_order = 0
    bad_bounds = 0
    for _, r in metrics.iterrows():
        tr_end = r.get("train_end")
        te_st = r.get("test_start")
        te_ed = r.get("test_end")
        if pd.isna(tr_end) or pd.isna(te_st) or pd.isna(te_ed):
            bad_order += 1
            continue
        if not (tr_end <= te_st < te_ed):
            bad_order += 1
        mm = str(r.get("test_month", ""))
        g = pred[pred["test_month"] == mm]
        if len(g) > 0:
            out = int(((g["close_ts"] < te_st) | (g["close_ts"] >= te_ed)).sum())
            bad_bounds += out
    l01_pass = (bad_order == 0) and (bad_bounds == 0)
    add_check(
        "L01",
        "wfo_time_order_strict",
        "pass" if l01_pass else "fail",
        "critical",
        "time_order",
        "violating_rows",
        float(bad_order + bad_bounds),
        "0",
        "==",
        {"bad_order_months": bad_order, "bad_prediction_bounds": bad_bounds},
        "Train/test window ordering or prediction month bounds are violated.",
    )

    # L02: warmup months exact.
    monthly_sorted = monthly.sort_values("test_month").reset_index(drop=True)
    if "status" in monthly_sorted.columns:
        warm_mask = monthly_sorted["status"].astype(str).str.lower() == "warmup_skip"
    else:
        warm_mask = pd.Series(False, index=monthly_sorted.index)
    warm_count = int(warm_mask.sum())
    expected = int(cfg.min_train_months)
    first_nonwarm = int(np.argmax((~warm_mask).to_numpy(dtype=bool))) if len(monthly_sorted) else 0
    prefix_ok = (
        bool((warm_mask.iloc[:expected]).all()) if len(monthly_sorted) >= expected else False
    )
    l02_pass = (
        (warm_count == expected)
        and prefix_ok
        and (first_nonwarm >= expected or len(monthly_sorted) == expected)
    )
    add_check(
        "L02",
        "warmup_months_exact",
        "pass" if l02_pass else "fail",
        "critical",
        "wfo_windowing",
        "warmup_count",
        float(warm_count),
        str(expected),
        "==",
        {"warmup_prefix_ok": prefix_ok, "months_total": int(len(monthly_sorted))},
        "Warmup month contract mismatch.",
    )

    # L03: no label/forward names in feature set.
    used_feats = [c for c in FEATURE_BASE if c in events.columns]
    leaked = []
    for c in used_feats:
        cl = c.lower()
        if any(re.search(pat, cl) for pat in BANNED_FEATURE_PATTERNS):
            leaked.append(c)
    l03_pass = len(leaked) == 0
    add_check(
        "L03",
        "feature_label_name_contract",
        "pass" if l03_pass else "fail",
        "critical",
        "feature_contract",
        "leaked_feature_count",
        float(len(leaked)),
        "0",
        "==",
        {"used_features": used_feats, "leaked_features": leaked},
        "Banned/label-like feature names detected in active feature set.",
    )

    # L04: every feature has lineage contract; no obvious lookahead signature.
    unknown = sorted([c for c in used_feats if c not in LINEAGE_MAP])
    suspicious = sorted(
        [c for c in used_feats if any(x in c.lower() for x in ["future", "lead", "next"])]
    )
    l04_pass = (len(unknown) == 0) and (len(suspicious) == 0)
    add_check(
        "L04",
        "feature_lookahead_signature",
        "pass" if l04_pass else "fail",
        "high",
        "feature_contract",
        "unknown_or_suspicious_feature_count",
        float(len(unknown) + len(suspicious)),
        "0",
        "==",
        {"unknown_features": unknown, "suspicious_features": suspicious},
        "Feature lineage contract incomplete or lookahead-like feature names found.",
    )

    # L05: reduced-core schedule uses only prior months.
    bad_month_links = 0
    bad_train_count = 0
    for _, r in schedule.iterrows():
        tm = _month_to_int(r.get("test_month"))
        tr_raw = str(r.get("train_months", "")).strip()
        tr = [x.strip() for x in tr_raw.split(",") if x.strip()]
        if len(tr) != int(cfg.min_train_months):
            bad_train_count += 1
        for m in tr:
            if _month_to_int(m) >= tm:
                bad_month_links += 1
    l05_pass = (bad_month_links == 0) and (bad_train_count == 0)
    add_check(
        "L05",
        "reduced_core_month_causality",
        "pass" if l05_pass else "fail",
        "critical",
        "selection_causality",
        "invalid_train_month_links",
        float(bad_month_links + bad_train_count),
        "0",
        "==",
        {"bad_month_links": bad_month_links, "bad_train_count_rows": bad_train_count},
        "Reduced-core schedule includes non-prior train months or wrong train-month count.",
    )

    # L06: threshold temporal causality consistency.
    selected_ok = selected["threshold_exec"].notna() & selected["pred_prob"].notna()
    selected_consistency = (
        float(
            np.mean(
                selected.loc[selected_ok, "pred_prob"]
                >= selected.loc[selected_ok, "threshold_exec"]
            )
        )
        if selected_ok.any()
        else np.nan
    )
    threshold_days_min = (
        float(pd.to_numeric(selected["threshold_days"], errors="coerce").min())
        if len(selected)
        else np.nan
    )
    selected["close_day_utc"] = selected["close_ts"].dt.strftime("%Y-%m-%d")
    mode_counts = (
        selected["threshold_mode"].astype(str).str.lower().value_counts(dropna=True).to_dict()
        if "threshold_mode" in selected.columns
        else {}
    )
    uses_rolling = any("rolling" in k for k in mode_counts)
    grp_cols = (
        ["test_month", "candidate_uid", "close_day_utc"]
        if uses_rolling
        else ["test_month", "candidate_uid"]
    )
    g_thr = (
        (
            selected.groupby(grp_cols, as_index=False)["threshold_exec"]
            .nunique(dropna=True)
            .rename(columns={"threshold_exec": "threshold_nunique"})
        )
        if len(selected)
        else pd.DataFrame()
    )
    unstable = int((g_thr["threshold_nunique"] > 1).sum()) if not g_thr.empty else 0
    l06_pass = (
        np.isfinite(selected_consistency)
        and selected_consistency >= 0.9999
        and np.isfinite(threshold_days_min)
        and threshold_days_min >= 1.0
        and unstable == 0
    )
    add_check(
        "L06",
        "selection_threshold_temporal_causality",
        "pass" if l06_pass else "fail",
        "high",
        "threshold_causality",
        "threshold_causality_violation_count",
        float(unstable + (0 if l06_pass else 1)),
        "0",
        "==",
        {
            "selected_consistency": selected_consistency,
            "threshold_days_min": threshold_days_min,
            "unstable_groups": unstable,
            "group_cols": grp_cols,
        },
        "Threshold causality consistency failed (selected<threshold, day-window invalid, or unstable thresholds).",
    )

    # L13: threshold provenance must be causal and explicitly declared.
    allowed_by_mode = {
        "rolling_days": {"rolling_history", "train_fallback", "no_history"},
        "train_quantile": {"train_quantile"},
    }
    src = pred["threshold_source"].astype(str).str.strip().str.lower()
    mode = pred["threshold_mode"].astype(str).str.strip().str.lower()
    src_missing = int(src.isin({"", "nan", "none", "null"}).sum())
    invalid_mode = int((~mode.isin(list(allowed_by_mode.keys()))).sum())
    invalid_source = 0
    for mname, allowed in allowed_by_mode.items():
        mask = mode == mname
        if int(mask.sum()) > 0:
            invalid_source += int((~src[mask].isin(list(allowed))).sum())
    sel_bad_nohist = int(((pred["selected_exec"] == 1) & (src == "no_history")).sum())
    sel_bad_unset = int(
        ((pred["selected_exec"] == 1) & (src.isin({"", "nan", "none", "null", "unset"}))).sum()
    )
    violations = src_missing + invalid_mode + invalid_source + sel_bad_nohist + sel_bad_unset
    l13_pass = violations == 0
    add_check(
        "L13",
        "threshold_provenance_causality_contract",
        "pass" if l13_pass else "fail",
        "high",
        "threshold_causality",
        "threshold_source_violation_count",
        float(violations),
        "0",
        "==",
        {
            "missing_source_rows": src_missing,
            "invalid_mode_rows": invalid_mode,
            "invalid_source_rows": invalid_source,
            "selected_no_history_rows": sel_bad_nohist,
            "selected_unset_source_rows": sel_bad_unset,
            "source_counts": src.value_counts(dropna=False).to_dict(),
        },
        "Threshold source provenance is missing, non-causal, or inconsistent with selected rows.",
    )

    # L07: label join/rebuild consistency (pred vs source event labels).
    e = events[["close_ts", "candidate_uid", "target_gross_pips", "target_gross_pos"]].copy()
    e["target_gross_pips"] = _safe_num(e["target_gross_pips"])
    e["target_gross_pos"] = _safe_num(e["target_gross_pos"])
    e_dup = int(e.duplicated(subset=["close_ts", "candidate_uid"]).sum())
    e = e.sort_values(["candidate_uid", "close_ts"]).drop_duplicates(
        subset=["close_ts", "candidate_uid"], keep="last"
    )
    j = pred.merge(
        e,
        on=["close_ts", "candidate_uid"],
        how="left",
        validate="many_to_one",
        suffixes=("", "_src"),
    )
    match_rate = float(j["target_gross_pips_src"].notna().mean()) if len(j) else np.nan
    diff = (j["target_gross_pips"] - j["target_gross_pips_src"]).abs()
    max_abs_diff = float(diff.dropna().max()) if diff.notna().any() else np.nan
    pos_diff = (j["target_gross_pos"] - j["target_gross_pos_src"]).abs()
    max_pos_diff = float(pos_diff.dropna().max()) if pos_diff.notna().any() else np.nan
    l07_pass = (
        np.isfinite(match_rate)
        and match_rate >= 0.999
        and np.isfinite(max_abs_diff)
        and max_abs_diff <= 1e-9
        and np.isfinite(max_pos_diff)
        and max_pos_diff <= 0.0
        and e_dup == 0
    )
    add_check(
        "L07",
        "label_rebuild_consistency",
        "pass" if l07_pass else "fail",
        "critical",
        "label_contract",
        "max_abs_label_diff",
        max_abs_diff if np.isfinite(max_abs_diff) else float("nan"),
        "<=1e-9 and pos_diff==0 and match_rate>=0.999",
        "<=",
        {"match_rate": match_rate, "max_pos_diff": max_pos_diff, "event_dup_keys": e_dup},
        "Prediction labels are not reproducible from source event labels.",
    )

    # L08: event key uniqueness.
    pred_dup = int(pred.duplicated(subset=["close_ts", "candidate_uid"]).sum())
    l08_pass = (pred_dup == 0) and (e_dup == 0)
    add_check(
        "L08",
        "event_key_uniqueness_contract",
        "pass" if l08_pass else "fail",
        "high",
        "key_integrity",
        "duplicate_key_count",
        float(pred_dup + e_dup),
        "0",
        "==",
        {"pred_duplicate_keys": pred_dup, "event_duplicate_keys": e_dup},
        "Duplicate event keys found in prediction/event tables.",
    )

    # L09: month partition integrity.
    month_mismatch = (
        float(np.mean(pred["test_month"] != pred["close_ts"].dt.strftime("%Y-%m")))
        if len(pred)
        else np.nan
    )
    set_m = (
        set(metrics["test_month"].astype(str).tolist())
        if "test_month" in metrics.columns
        else set()
    )
    set_t = (
        set(thresholds["test_month"].astype(str).tolist())
        if "test_month" in thresholds.columns
        else set()
    )
    sym_diff = sorted(list((set_m - set_t) | (set_t - set_m)))
    l09_pass = np.isfinite(month_mismatch) and month_mismatch <= 0.0 and len(sym_diff) == 0
    add_check(
        "L09",
        "month_partition_integrity",
        "pass" if l09_pass else "fail",
        "high",
        "partitioning",
        "month_mismatch_rate",
        month_mismatch if np.isfinite(month_mismatch) else float("nan"),
        "0 and month_sets_equal",
        "==",
        {"metrics_threshold_month_diff": sym_diff},
        "Month partition mismatch between timestamps and test_month / thresholds.",
    )

    # L10: feature null-shift after selection.
    feat_keys = [c for c in FEATURE_BASE if c in events.columns]
    selj = selected.merge(
        events[["close_ts", "candidate_uid"] + feat_keys],
        on=["close_ts", "candidate_uid"],
        how="left",
        validate="many_to_one",
    )
    diffs: list[float] = []
    for c in feat_keys:
        all_null = float(events[c].isna().mean())
        sel_null = float(selj[c].isna().mean()) if len(selj) else np.nan
        if np.isfinite(sel_null):
            diffs.append(abs(sel_null - all_null))
    max_shift = float(np.max(diffs)) if diffs else np.nan
    l10_pass = np.isfinite(max_shift) and max_shift <= float(cfg.max_null_shift)
    add_check(
        "L10",
        "feature_null_shift_after_selection",
        "pass" if l10_pass else "fail",
        "medium",
        "selection_drift",
        "max_feature_null_shift",
        max_shift if np.isfinite(max_shift) else float("nan"),
        str(cfg.max_null_shift),
        "<=",
        {"selected_rows": int(len(selj)), "feature_count": len(feat_keys)},
        "Selected-set feature null profile drift exceeds threshold.",
    )

    # L11: no cross-symbol mix.
    pred_uid_bad = int((pred["candidate_uid"].map(_uid_symbol) != cfg.symbol).sum())
    evt_uid_bad = int((events["candidate_uid"].map(_uid_symbol) != cfg.symbol).sum())
    sched_bad = (
        int((schedule["symbol"].astype(str).str.upper() != cfg.symbol).sum())
        if "symbol" in schedule.columns
        else 0
    )
    mon_bad = (
        int((monthly["symbol"].astype(str).str.upper() != cfg.symbol).sum())
        if "symbol" in monthly.columns
        else 0
    )
    l11_pass = (pred_uid_bad + evt_uid_bad + sched_bad + mon_bad) == 0
    add_check(
        "L11",
        "no_cross_symbol_mix",
        "pass" if l11_pass else "fail",
        "critical",
        "symbol_integrity",
        "cross_symbol_rows",
        float(pred_uid_bad + evt_uid_bad + sched_bad + mon_bad),
        "0",
        "==",
        {
            "pred_uid_bad": pred_uid_bad,
            "event_uid_bad": evt_uid_bad,
            "schedule_symbol_bad": sched_bad,
            "monthly_symbol_bad": mon_bad,
        },
        "Symbol contamination detected across artifacts.",
    )

    # L12: artifact hash chain consistency against governance lock.
    hash_mism = 0
    lock_symbol_bad = 0
    checked = 0
    if not cfg.lock_path.exists():
        hash_mism = 1
    else:
        lock = json.loads(cfg.lock_path.read_text(encoding="utf-8"))
        lock_symbol_bad = 0 if str(lock.get("symbol", "")).upper().strip() == cfg.symbol else 1
        art = lock.get("artifacts", {})
        for pkey, hkey in [
            ("wfo_config_path", "wfo_config_sha256"),
            ("reduced_config_path", "reduced_config_sha256"),
            ("reduced_states_csv_path", "reduced_states_csv_sha256"),
            ("predictions_path", "predictions_sha256"),
            ("model_cbm_path", "model_cbm_sha256"),
            ("model_threshold_json_path", "model_threshold_json_sha256"),
            ("tick_exact_summary_path", "tick_exact_summary_sha256"),
        ]:
            p = Path(str(art.get(pkey, "")))
            exp = str(art.get(hkey, ""))
            checked += 1
            if (not p.exists()) or (_sha256(p) != exp):
                hash_mism += 1
    l12_pass = (hash_mism == 0) and (lock_symbol_bad == 0)
    add_check(
        "L12",
        "artifact_hash_chain_consistency",
        "pass" if l12_pass else "fail",
        "high",
        "artifact_lineage",
        "hash_mismatch_count",
        float(hash_mism + lock_symbol_bad),
        "0",
        "==",
        {
            "hash_mismatches": hash_mism,
            "lock_symbol_bad": lock_symbol_bad,
            "hashes_checked": checked,
        },
        "Governance lock hash chain is inconsistent with current artifacts.",
    )

    checks_df = pd.DataFrame(checks)
    issues_df = pd.DataFrame(issues)
    return checks_df, issues_df


def run_audit(
    symbols: list[str],
    *,
    out_checks_csv: Path,
    out_issues_csv: Path,
    report_out: Path,
    config_map: dict[str, SymbolConfig] | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    cfg_map = _default_configs() if config_map is None else dict(config_map)
    use_syms = [s.upper().strip() for s in symbols if s.strip()]
    bad = [s for s in use_syms if s not in cfg_map]
    if bad:
        raise ValueError(f"Unsupported symbols: {bad}")

    exceptions: dict[str, Any] = {}
    exc_path = Path("configs/research/governance/oco_monitoring_exceptions.yaml")
    if yaml and exc_path.exists():
        with contextlib.suppress(Exception):
            exceptions = yaml.safe_load(exc_path.read_text())

    all_checks: list[pd.DataFrame] = []
    all_issues: list[pd.DataFrame] = []
    for s in use_syms:
        cfg = cfg_map[s]
        required = [
            cfg.pred_path,
            cfg.metrics_path,
            cfg.thresholds_path,
            cfg.events_path,
            cfg.schedule_path,
            cfg.monthly_path,
        ]
        miss = [str(p) for p in required if not p.exists()]
        if miss:
            raise FileNotFoundError(f"{s}: missing required inputs: {miss}")
        c, i = audit_symbol(cfg, exceptions=exceptions)
        all_checks.append(c)
        all_issues.append(i)

    checks = pd.concat(all_checks, ignore_index=True) if all_checks else pd.DataFrame()
    issues = pd.concat(all_issues, ignore_index=True) if all_issues else pd.DataFrame()
    if checks.empty:
        checks = pd.DataFrame(
            columns=[
                "symbol",
                "check_id",
                "check_name",
                "status",
                "severity_if_fail",
                "component",
                "metric_name",
                "metric_value",
                "threshold",
                "comparator",
                "details_json",
                "evaluated_at_utc",
            ]
        )
    if issues.empty:
        issues = pd.DataFrame(
            columns=[
                "issue_id",
                "symbol",
                "check_id",
                "severity",
                "component",
                "summary",
                "details_json",
            ]
        )

    out_checks_csv.parent.mkdir(parents=True, exist_ok=True)
    out_issues_csv.parent.mkdir(parents=True, exist_ok=True)
    report_out.parent.mkdir(parents=True, exist_ok=True)
    checks.to_csv(out_checks_csv, index=False)
    issues.to_csv(out_issues_csv, index=False)

    sev_counts = (
        issues.groupby("severity", as_index=False).size().sort_values("size", ascending=False)
        if not issues.empty
        else pd.DataFrame(columns=["severity", "size"])
    )
    check_roll = (
        checks.groupby(["symbol", "status"], as_index=False)
        .size()
        .pivot(index="symbol", columns="status", values="size")
        .fillna(0)
        .reset_index()
        if not checks.empty
        else pd.DataFrame()
    )
    lines: list[str] = []
    lines.append("# OCO Leakage + Label Integrity Audit")
    lines.append("")
    lines.append("## Outputs")
    lines.append(f"- checks_csv: `{out_checks_csv}`")
    lines.append(f"- issues_csv: `{out_issues_csv}`")
    lines.append("")
    lines.append("## Severity Counts")
    lines.append(_table(sev_counts))
    lines.append("")
    lines.append("## Check Status By Symbol")
    lines.append(_table(check_roll))
    lines.append("")
    lines.append("## Failed Issues")
    lines.append(
        _table(
            issues[["issue_id", "symbol", "severity", "component", "summary"]]
            if not issues.empty
            else pd.DataFrame()
        )
    )
    lines.append("")
    lines.append("## Full Check Table")
    lines.append(_table(checks))
    report_out.write_text("\n".join(lines), encoding="utf-8")
    return checks, issues


def main() -> None:
    p = argparse.ArgumentParser(description="Leakage + label integrity audit for OCO pipeline")
    p.add_argument("--symbols", default="EURUSD,GBPUSD,USDJPY,USDCAD,AUDUSD,USDCHF")
    p.add_argument(
        "--out-checks-csv",
        default="data/analysis/tick_opportunity_mining/oco_leakage_integrity_checks.csv",
    )
    p.add_argument(
        "--out-issues-csv",
        default="data/analysis/tick_opportunity_mining/oco_leakage_integrity_issues.csv",
    )
    p.add_argument("--report-out", default="docs/analysis/oco_leakage_integrity_report.md")
    args = p.parse_args()

    checks, issues = run_audit(
        _parse_symbols(str(args.symbols)),
        out_checks_csv=Path(str(args.out_checks_csv)),
        out_issues_csv=Path(str(args.out_issues_csv)),
        report_out=Path(str(args.report_out)),
    )
    fail = checks[checks["status"].astype(str).str.lower() != "pass"]
    high_crit = fail["severity_if_fail"].astype(str).str.lower().isin(["high", "critical"]).sum()
    print(f"wrote checks: {args.out_checks_csv} rows={len(checks)}")
    print(f"wrote issues: {args.out_issues_csv} rows={len(issues)}")
    print(f"high_or_critical_failures={int(high_crit)}")


if __name__ == "__main__":
    main()
