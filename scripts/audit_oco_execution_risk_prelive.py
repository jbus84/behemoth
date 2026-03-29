#!/usr/bin/env python3
"""Execution-risk preflight audit on tick replay artifacts.

Checks E01..E10 across EURUSD/GBPUSD/USDJPY/USDCHF/AUDUSD/USDCAD and emits:
- checks CSV
- issues CSV
- markdown report
"""

from __future__ import annotations

import argparse
import contextlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

try:
    import yaml
except ImportError:
    yaml = None


@dataclass(frozen=True)
class SymbolConfig:
    symbol: str
    pred_path: Path
    monthly_path: Path
    detail_path: Path
    caps_path: Path
    production_cap_pips: float = 1.2
    min_state_rows: int = 1000
    min_fill_rate_monthly: float = 0.92
    max_no_touch_rate: float = 0.35
    max_tail_above_cap: float = 0.10
    latency_med_max_seconds: float = 120.0
    latency_p95_max_seconds: float = 1200.0
    cap_efficiency_min: float = 0.95
    max_session_share: float = 0.70
    max_bad_state_frac: float = 0.15
    worst_month_net_min: float = -0.80
    min_total_rows_for_viability: int = 3000
    bootstrap_paths: int = 800
    seed: int = 42


def _default_configs() -> dict[str, SymbolConfig]:
    configs = {}
    for s in ["EURUSD", "GBPUSD", "USDJPY", "USDCHF", "AUDUSD", "USDCAD"]:
        s.lower()
        pred_folder = "wfo_m3to1_oco_fullcap"
        red_folder = "reduced_core_rolling"
        stop_folder = "stop_limit_tickfill_fullcap"

        configs[s] = SymbolConfig(
            symbol=s,
            pred_path=Path(
                f"data/analysis/tick_opportunity_mining/{pred_folder}/{s}_oco_monthly_predictions.parquet"
            ),
            monthly_path=Path(
                f"data/analysis/tick_opportunity_mining/{red_folder}/{s}_oco_reduced_monthly.csv"
            ),
            detail_path=Path(
                f"data/analysis/tick_opportunity_mining/{stop_folder}/{s}_stop_limit_tickfill_detail.csv"
            ),
            caps_path=Path(
                f"data/analysis/tick_opportunity_mining/{stop_folder}/{s}_stop_limit_tickfill_caps.csv"
            ),
        )
    return configs


def _parse_symbols(raw: str) -> list[str]:
    return [x.strip().upper() for x in str(raw).split(",") if x.strip()]


def _table(df: pd.DataFrame) -> str:
    if df.empty:
        return "_empty_"
    try:
        return df.to_markdown(index=False)
    except Exception:
        return "```\n" + df.to_string(index=False) + "\n```"


def _dt_utc(s: pd.Series) -> pd.Series:
    try:
        return pd.to_datetime(s, utc=True, errors="coerce", format="mixed")
    except TypeError:
        return pd.to_datetime(s, utc=True, errors="coerce")


def _safe_num(s: pd.Series) -> pd.Series:
    return pd.to_numeric(s, errors="coerce")


def _bootstrap_lb95(vals: np.ndarray, *, paths: int, seed: int) -> float:
    x = np.asarray(vals, dtype=float)
    x = x[np.isfinite(x)]
    if len(x) == 0 or int(paths) <= 0:
        return float("nan")
    rng = np.random.default_rng(int(seed))
    n = len(x)
    draws: list[np.ndarray] = []
    batch = 200
    for i in range(0, int(paths), batch):
        b = min(batch, int(paths) - i)
        idx = rng.integers(0, n, size=(b, n))
        draws.append(x[idx].mean(axis=1))
    d = np.concatenate(draws) if draws else np.array([], dtype=float)
    if len(d) == 0:
        return float("nan")
    return float(np.quantile(d, 0.05))


def _session_from_hour(h: int) -> str:
    if h in [0, 1, 2, 3, 4, 5]:
        return "asia"
    if h in [7, 8, 9, 10, 11]:
        return "london"
    if h in [13, 14, 15, 16]:
        return "ny_overlap"
    return "other"


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


def _load_selected_predictions(path: Path) -> pd.DataFrame:
    p = pd.read_parquet(
        path,
        columns=[
            "test_month",
            "close_ts",
            "candidate_uid",
            "target_gross_pips",
            "selected_exec",
        ],
    ).copy()
    p["selected_exec"] = _safe_num(p["selected_exec"]).fillna(0).astype(int)
    p = p[p["selected_exec"] == 1].copy()
    p["test_month"] = p["test_month"].astype(str)
    p["close_ts"] = _dt_utc(p["close_ts"])
    p["candidate_uid"] = p["candidate_uid"].astype(str)
    p["target_gross_pips"] = _safe_num(p["target_gross_pips"])
    p = p.dropna(subset=["test_month", "close_ts", "candidate_uid", "target_gross_pips"]).copy()
    return p


def _load_detail(path: Path) -> tuple[pd.DataFrame, int]:
    d = pd.read_csv(
        path,
        usecols=[
            "close_ts",
            "candidate_uid",
            "target_gross_pips",
            "touch_open_ts",
            "touch_close_ts",
            "touch_found_tick",
            "overshoot_tick_pips",
        ],
    ).copy()
    d["close_ts"] = _dt_utc(d["close_ts"])
    d["candidate_uid"] = d["candidate_uid"].astype(str)
    d["target_gross_pips"] = _safe_num(d["target_gross_pips"])
    d["touch_open_ts"] = _dt_utc(d["touch_open_ts"])
    d["touch_close_ts"] = _dt_utc(d["touch_close_ts"])
    d["touch_found_tick"] = _safe_num(d["touch_found_tick"]).fillna(0).astype(int)
    d["overshoot_tick_pips"] = _safe_num(d["overshoot_tick_pips"])
    d = d.dropna(subset=["close_ts", "candidate_uid"]).copy()
    dup = int(d.duplicated(subset=["close_ts", "candidate_uid"]).sum())
    d = d.sort_values(["candidate_uid", "close_ts"]).drop_duplicates(
        subset=["close_ts", "candidate_uid"], keep="last"
    )
    return d, dup


def audit_symbol(
    cfg: SymbolConfig, exceptions: dict[str, Any] | None = None
) -> tuple[pd.DataFrame, pd.DataFrame]:
    checks: list[dict[str, Any]] = []
    issues: list[dict[str, Any]] = []

    pred = _load_selected_predictions(cfg.pred_path)
    detail, dup_count = _load_detail(cfg.detail_path)
    caps = pd.read_csv(cfg.caps_path).copy()
    monthly = pd.read_csv(cfg.monthly_path).copy()
    monthly["test_month"] = monthly["test_month"].astype(str)

    m = pred.merge(
        detail,
        on=["close_ts", "candidate_uid"],
        how="left",
        validate="one_to_one",
        suffixes=("", "_detail"),
    )
    m["matched"] = m["touch_found_tick"].notna().astype(int)
    m["touch_found_tick"] = _safe_num(m["touch_found_tick"]).fillna(0).astype(int)
    m["overshoot_tick_pips"] = _safe_num(m["overshoot_tick_pips"])
    m["target_gross_pips_detail"] = _safe_num(m["target_gross_pips_detail"])
    # Use detail target when present for execution realism consistency.
    m["target_gross_pips_exec"] = np.where(
        m["target_gross_pips_detail"].notna(),
        m["target_gross_pips_detail"],
        m["target_gross_pips"],
    )
    m["month_utc"] = m["close_ts"].dt.strftime("%Y-%m")
    m["hour_utc"] = m["close_ts"].dt.hour.astype("Int64")
    m["session"] = m["hour_utc"].fillna(-1).astype(int).map(_session_from_hour)

    cap = float(cfg.production_cap_pips)
    m["filled"] = (
        (m["touch_found_tick"] == 1)
        & m["overshoot_tick_pips"].notna()
        & (m["overshoot_tick_pips"] <= cap)
    )
    m["net_trade_full_overshoot"] = m["target_gross_pips_exec"] - m["overshoot_tick_pips"]
    m["net_signal_full_overshoot"] = np.where(m["filled"], m["net_trade_full_overshoot"], 0.0)

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

    # E01: join integrity.
    match_rate = float(m["matched"].mean()) if len(m) else float("nan")
    e01_pass = np.isfinite(match_rate) and match_rate >= 0.995 and dup_count == 0
    add_check(
        "E01",
        "join_integrity_exec_detail",
        "pass" if e01_pass else "fail",
        "critical",
        "join_integrity",
        "match_rate",
        match_rate if np.isfinite(match_rate) else float("nan"),
        ">=0.995 and duplicate_keys=0",
        ">=",
        {"duplicate_keys": dup_count, "rows_selected": int(len(m))},
        "Selected replay rows do not join cleanly to tickfill detail.",
    )

    # E02: fill-rate envelope monthly.
    mon = (
        m.groupby("month_utc", as_index=False)
        .agg(rows=("filled", "size"), fill_rate=("filled", "mean"))
        .sort_values("month_utc")
    )
    min_fill = float(mon["fill_rate"].min()) if not mon.empty else float("nan")
    low = (
        mon["fill_rate"].to_numpy(dtype=float) < float(cfg.min_fill_rate_monthly)
        if not mon.empty
        else np.array([], dtype=bool)
    )
    consecutive_low = int(np.sum(low[:-1] & low[1:])) if len(low) > 1 else 0
    e02_pass = (
        np.isfinite(min_fill)
        and min_fill >= float(cfg.min_fill_rate_monthly)
        and consecutive_low == 0
    )
    add_check(
        "E02",
        "fill_rate_envelope_monthly",
        "pass" if e02_pass else "fail",
        "high",
        "fill_rate",
        "min_month_fill_rate",
        min_fill if np.isfinite(min_fill) else float("nan"),
        f">={cfg.min_fill_rate_monthly} and consecutive_low=0",
        ">=",
        {"consecutive_low_month_pairs": consecutive_low, "months": int(len(mon))},
        "Monthly fill-rate envelope violated.",
    )

    # E03: overshoot tail control.
    ov = m.loc[m["touch_found_tick"] == 1, "overshoot_tick_pips"].dropna().to_numpy(dtype=float)
    ov_p95 = float(np.quantile(ov, 0.95)) if len(ov) else float("nan")
    ov_tail = float(np.mean(ov > cap)) if len(ov) else float("nan")
    e03_pass = (
        np.isfinite(ov_p95)
        and np.isfinite(ov_tail)
        and ov_p95 <= cap
        and ov_tail <= float(cfg.max_tail_above_cap)
    )
    add_check(
        "E03",
        "overshoot_tail_control",
        "pass" if e03_pass else "fail",
        "high",
        "overshoot",
        "overshoot_tail_above_cap",
        ov_tail if np.isfinite(ov_tail) else float("nan"),
        f"p95<={cap} and tail<={cfg.max_tail_above_cap}",
        "<=",
        {"overshoot_p95": ov_p95, "production_cap_pips": cap},
        "Overshoot tail or p95 exceeds cap risk bounds.",
    )

    # E04: touch-to-fill latency control.
    lat = (m["touch_close_ts"] - m["touch_open_ts"]).dt.total_seconds()
    lat = lat[(m["touch_found_tick"] == 1) & lat.notna()].to_numpy(dtype=float)
    lat_med = float(np.quantile(lat, 0.5)) if len(lat) else float("nan")
    lat_p95 = float(np.quantile(lat, 0.95)) if len(lat) else float("nan")
    if len(lat) == 0:
        e04_pass = True
        metric_v = float("nan")
    else:
        e04_pass = (lat_med <= float(cfg.latency_med_max_seconds)) and (
            lat_p95 <= float(cfg.latency_p95_max_seconds)
        )
        metric_v = lat_p95
    add_check(
        "E04",
        "touch_to_fill_latency_control",
        "pass" if e04_pass else "fail",
        "medium",
        "latency",
        "latency_p95_seconds",
        metric_v,
        f"median<={cfg.latency_med_max_seconds}, p95<={cfg.latency_p95_max_seconds}",
        "<=",
        {"latency_median_seconds": lat_med, "latency_samples": int(len(lat))},
        "Touch-to-fill latency exceeds pre-live tolerance.",
    )

    # E05: no-touch rate control.
    no_touch = float(np.mean(m["touch_found_tick"] != 1)) if len(m) else float("nan")
    e05_pass = np.isfinite(no_touch) and no_touch <= float(cfg.max_no_touch_rate)
    add_check(
        "E05",
        "no_touch_rate_control",
        "pass" if e05_pass else "fail",
        "high",
        "touch_coverage",
        "no_touch_rate",
        no_touch if np.isfinite(no_touch) else float("nan"),
        f"<={cfg.max_no_touch_rate}",
        "<=",
        {"rows_selected": int(len(m))},
        "No-touch rate exceeds tolerance.",
    )

    # E06: cap curve monotonicity + plateau.
    c = caps.copy()
    if "symbol" in c.columns:
        c = c[c["symbol"].astype(str).str.upper() == cfg.symbol].copy()
    c = c.sort_values("cap_pips")
    c["fill_rate"] = _safe_num(c["fill_rate"])
    c["mean_per_signal_full_overshoot"] = _safe_num(c["mean_per_signal_full_overshoot"])
    diffs = (
        np.diff(c["fill_rate"].to_numpy(dtype=float)) if len(c) > 1 else np.array([], dtype=float)
    )
    mono_viol = int(np.sum(diffs < -1e-9))
    prod_row = c[np.isclose(c["cap_pips"].astype(float), cap, atol=1e-9)]
    if prod_row.empty and len(c) > 0:
        idx = int(np.argmin(np.abs(c["cap_pips"].to_numpy(dtype=float) - cap)))
        prod_row = c.iloc[[idx]].copy()
    prod_pnl = (
        float(prod_row["mean_per_signal_full_overshoot"].iloc[0])
        if not prod_row.empty
        else float("nan")
    )
    best_pnl = float(c["mean_per_signal_full_overshoot"].max()) if len(c) else float("nan")
    efficiency = (
        float(prod_pnl / best_pnl)
        if np.isfinite(prod_pnl) and np.isfinite(best_pnl) and abs(best_pnl) > 1e-12
        else float("nan")
    )
    e06_pass = (
        (mono_viol == 0)
        and np.isfinite(efficiency)
        and (efficiency >= float(cfg.cap_efficiency_min))
    )
    add_check(
        "E06",
        "cap_curve_monotonicity_and_plateau",
        "pass" if e06_pass else "fail",
        "high",
        "cap_curve",
        "production_cap_efficiency",
        efficiency if np.isfinite(efficiency) else float("nan"),
        f"fill_monotonic and efficiency>={cfg.cap_efficiency_min}",
        ">=",
        {
            "monotonicity_violations": mono_viol,
            "production_cap_pips": cap,
            "best_pnl": best_pnl,
            "prod_pnl": prod_pnl,
        },
        "Cap curve is fragile or non-monotonic for fill behavior.",
    )

    # E07: session dispersion.
    filled = m[m["filled"]].copy()
    sess_share = (
        filled["session"].value_counts(normalize=True) if len(filled) else pd.Series(dtype=float)
    )
    max_share = float(sess_share.max()) if len(sess_share) else float("nan")
    sess_ov = (
        m[m["touch_found_tick"] == 1]
        .groupby("session", as_index=False)
        .agg(ov_mean=("overshoot_tick_pips", "mean"))
    )
    g_mean = (
        float(m.loc[m["touch_found_tick"] == 1, "overshoot_tick_pips"].mean())
        if len(m)
        else float("nan")
    )
    g_std = (
        float(m.loc[m["touch_found_tick"] == 1, "overshoot_tick_pips"].std(ddof=0))
        if len(m)
        else float("nan")
    )
    worst_ov = float(sess_ov["ov_mean"].max()) if not sess_ov.empty else float("nan")
    ov_ok = True
    if np.isfinite(g_mean) and np.isfinite(g_std) and np.isfinite(worst_ov):
        ov_ok = worst_ov <= (g_mean + 1.5 * g_std)
    e07_pass = np.isfinite(max_share) and (max_share <= float(cfg.max_session_share)) and ov_ok
    add_check(
        "E07",
        "session_execution_dispersion",
        "pass" if e07_pass else "fail",
        "medium",
        "session_dispersion",
        "max_session_share",
        max_share if np.isfinite(max_share) else float("nan"),
        f"<={cfg.max_session_share} and overshoot_outlier_session=False",
        "<=",
        {
            "worst_session_overshoot_mean": worst_ov,
            "global_overshoot_mean": g_mean,
            "global_overshoot_std": g_std,
        },
        "Execution quality is overly concentrated or session-skewed.",
    )

    # E08: state execution fragility.
    g_state = m.groupby("candidate_uid", as_index=False).agg(
        rows=("candidate_uid", "size"),
        fill_rate=("filled", "mean"),
        ov_p95=(
            "overshoot_tick_pips",
            lambda x: (
                float(np.nanquantile(pd.to_numeric(x, errors="coerce").dropna().to_numpy(), 0.95))
                if pd.to_numeric(x, errors="coerce").dropna().shape[0]
                else np.nan
            ),
        ),
    )
    hv = g_state[g_state["rows"] >= int(cfg.min_state_rows)].copy()
    if not hv.empty:
        bad = (hv["fill_rate"] < 0.85) | (hv["ov_p95"] > (1.2 * cap))
        bad_frac = float(np.mean(bad))
        bad_count = int(bad.sum())
    else:
        bad_frac = 0.0
        bad_count = 0
    e08_pass = bad_frac <= float(cfg.max_bad_state_frac)
    add_check(
        "E08",
        "state_execution_fragility",
        "pass" if e08_pass else "fail",
        "high",
        "state_quality",
        "bad_high_volume_state_frac",
        bad_frac,
        f"<={cfg.max_bad_state_frac}",
        "<=",
        {
            "high_volume_states": int(len(hv)),
            "bad_states": bad_count,
            "min_state_rows": int(cfg.min_state_rows),
        },
        "Too many high-volume states fail fill/overshoot quality.",
    )

    # E09: worst-window stress guard.
    mon2 = (
        m.groupby("month_utc", as_index=False)
        .agg(
            rows=("candidate_uid", "size"),
            fill_rate=("filled", "mean"),
            mean_signal_net=("net_signal_full_overshoot", "mean"),
            ov_p95=(
                "overshoot_tick_pips",
                lambda x: (
                    float(
                        np.nanquantile(pd.to_numeric(x, errors="coerce").dropna().to_numpy(), 0.95)
                    )
                    if pd.to_numeric(x, errors="coerce").dropna().shape[0]
                    else np.nan
                ),
            ),
        )
        .sort_values("month_utc")
    )
    worst_month_net = float(mon2["mean_signal_net"].min()) if not mon2.empty else float("nan")
    catastrophic = (
        int(((mon2["fill_rate"] < 0.85) & (mon2["ov_p95"] > (1.2 * cap))).sum())
        if not mon2.empty
        else 0
    )
    e09_pass = (
        np.isfinite(worst_month_net)
        and (worst_month_net >= float(cfg.worst_month_net_min))
        and catastrophic == 0
    )
    add_check(
        "E09",
        "worst_window_stress_guard",
        "pass" if e09_pass else "fail",
        "high",
        "stress_guard",
        "worst_month_mean_signal_net",
        worst_month_net if np.isfinite(worst_month_net) else float("nan"),
        f">={cfg.worst_month_net_min} and catastrophic_months=0",
        ">=",
        {"catastrophic_months": catastrophic, "months": int(len(mon2))},
        "Worst-month execution stress exceeds allowed degradation.",
    )

    # E10: execution net viability.
    monthly_means = (
        mon2["mean_signal_net"].to_numpy(dtype=float)
        if not mon2.empty
        else np.array([], dtype=float)
    )
    lb95_month = _bootstrap_lb95(
        monthly_means, paths=int(cfg.bootstrap_paths), seed=int(cfg.seed) + 31
    )
    pos_months = int(np.sum(monthly_means > 0.0)) if len(monthly_means) else 0
    months = int(len(monthly_means))
    majority = bool(pos_months >= ((months // 2) + 1)) if months > 0 else False
    rows_total = int(len(m))
    e10_pass = (
        np.isfinite(lb95_month)
        and lb95_month >= 0.0
        and majority
        and rows_total >= int(cfg.min_total_rows_for_viability)
    )
    add_check(
        "E10",
        "execution_net_viability",
        "pass" if e10_pass else "fail",
        "critical",
        "net_viability",
        "lb95_month_mean_signal_net",
        lb95_month if np.isfinite(lb95_month) else float("nan"),
        ">=0 and majority_positive_months and rows_floor",
        ">=",
        {
            "positive_months": pos_months,
            "months": months,
            "rows_total": rows_total,
            "rows_floor": int(cfg.min_total_rows_for_viability),
        },
        "Net execution viability is not robust at production cap.",
    )

    return pd.DataFrame(checks), pd.DataFrame(issues)


def run_audit(
    symbols: list[str],
    *,
    out_checks_csv: Path,
    out_issues_csv: Path,
    report_out: Path,
    config_map: dict[str, SymbolConfig] | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    cfg_map = _default_configs() if config_map is None else dict(config_map)
    syms = [s.upper().strip() for s in symbols if s.strip()]
    bad = [s for s in syms if s not in cfg_map]
    if bad:
        raise ValueError(f"Unsupported symbols: {bad}")

    exceptions: dict[str, Any] = {}
    exc_path = Path("configs/research/governance/oco_monitoring_exceptions.yaml")
    if yaml and exc_path.exists():
        with contextlib.suppress(Exception):
            exceptions = yaml.safe_load(exc_path.read_text())

    all_checks: list[pd.DataFrame] = []
    all_issues: list[pd.DataFrame] = []
    for s in syms:
        cfg = cfg_map[s]
        required = [cfg.pred_path, cfg.monthly_path, cfg.detail_path, cfg.caps_path]
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
    status_roll = (
        checks.groupby(["symbol", "status"], as_index=False)
        .size()
        .pivot(index="symbol", columns="status", values="size")
        .fillna(0)
        .reset_index()
        if not checks.empty
        else pd.DataFrame()
    )
    lines: list[str] = []
    lines.append("# OCO Execution Risk Pre-Live Audit")
    lines.append("")
    lines.append("## Outputs")
    lines.append(f"- checks_csv: `{out_checks_csv}`")
    lines.append(f"- issues_csv: `{out_issues_csv}`")
    lines.append("")
    lines.append("## Severity Counts")
    lines.append(_table(sev_counts))
    lines.append("")
    lines.append("## Check Status By Symbol")
    lines.append(_table(status_roll))
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
    p = argparse.ArgumentParser(
        description="Execution-risk preflight audit on OCO tick replay artifacts"
    )
    p.add_argument("--symbols", default="EURUSD,GBPUSD,USDJPY,USDCHF,AUDUSD,USDCAD")
    p.add_argument(
        "--out-checks-csv",
        default="data/analysis/tick_opportunity_mining/oco_execution_risk_checks.csv",
    )
    p.add_argument(
        "--out-issues-csv",
        default="data/analysis/tick_opportunity_mining/oco_execution_risk_issues.csv",
    )
    p.add_argument("--report-out", default="docs/analysis/oco_execution_risk_prelive_report.md")
    args = p.parse_args()

    checks, issues = run_audit(
        _parse_symbols(str(args.symbols)),
        out_checks_csv=Path(str(args.out_checks_csv)),
        out_issues_csv=Path(str(args.out_issues_csv)),
        report_out=Path(str(args.report_out)),
    )
    fail = checks[checks["status"].astype(str).str.lower() != "pass"]
    high_crit = (
        int(fail["severity_if_fail"].astype(str).str.lower().isin(["high", "critical"]).sum())
        if not fail.empty
        else 0
    )
    print(f"wrote checks: {args.out_checks_csv} rows={len(checks)}")
    print(f"wrote issues: {args.out_issues_csv} rows={len(issues)}")
    print(f"high_or_critical_failures={high_crit}")


if __name__ == "__main__":
    main()
