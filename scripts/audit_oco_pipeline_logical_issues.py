#!/usr/bin/env python3
"""Logical audit for OCO WFO->selection->stop-limit pipeline.

Checks C01..C10 across active symbols and emits:
- checks CSV (pass/fail + metrics)
- issues CSV (failed checks only, severity-ranked)
- markdown report
"""

from __future__ import annotations

import argparse
import contextlib
import json
from dataclasses import dataclass
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
    summary_path: Path
    schedule_path: Path
    stop_detail_path: Path
    stop_caps_path: Path
    stop_cap_pips: float = 1.2
    bootstrap_paths: int = 600
    seed: int = 42
    min_train_months: int = 3


def _default_configs(
    base_dir: Path | str = "data/analysis/tick_opportunity_mining",
) -> dict[str, SymbolConfig]:
    base_dir = Path(base_dir)
    configs = {}
    for s in ["EURUSD", "GBPUSD", "USDJPY", "USDCHF", "AUDUSD", "USDCAD"]:
        pred_folder = "wfo_m3to1_oco_fullcap"
        red_folder = "reduced_core_rolling"
        stop_folder = "stop_limit_tickfill_fullcap"

        configs[s] = SymbolConfig(
            symbol=s,
            pred_path=base_dir / pred_folder / f"{s}_oco_monthly_predictions.parquet",
            monthly_path=base_dir / red_folder / f"{s}_oco_reduced_monthly.csv",
            summary_path=base_dir / red_folder / f"{s}_oco_reduced_summary.csv",
            schedule_path=base_dir / red_folder / f"{s}_oco_reduced_state_schedule.csv",
            stop_detail_path=base_dir / stop_folder / f"{s}_stop_limit_tickfill_detail.csv",
            stop_caps_path=base_dir / stop_folder / f"{s}_stop_limit_tickfill_caps.csv",
        )
    return configs


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
    m = np.concatenate(draws) if draws else np.array([], dtype=float)
    if len(m) == 0:
        return float("nan")
    return float(np.quantile(m, 0.05))


def _parse_state_id(uid: str) -> str:
    toks = str(uid).split("|", 4)
    if len(toks) != 5:
        return str(uid)
    return str(toks[4])


def _parse_state_key(uid: str) -> str:
    toks = str(uid).split("|", 4)
    if len(toks) != 5:
        return str(uid)
    bt = str(toks[2])
    h = str(toks[3]).lstrip("hH")
    sid = str(toks[4])
    return f"{sid}|{bt}|{h}"


def _dt_utc_mixed(series: pd.Series) -> pd.Series:
    try:
        return pd.to_datetime(series, utc=True, errors="coerce", format="mixed")
    except TypeError:
        return pd.to_datetime(series, utc=True, errors="coerce")


def _table(df: pd.DataFrame) -> str:
    if df.empty:
        return "_empty_"
    try:
        return df.to_markdown(index=False)
    except Exception:
        return "```\n" + df.to_string(index=False) + "\n```"


def _make_issue(
    *,
    symbol: str,
    check_id: str,
    severity: str,
    component: str,
    description: str,
    impact_estimate: str,
    proposed_fix: str,
    acceptance_test: str,
    details: dict[str, Any],
) -> dict[str, Any]:
    return {
        "issue_id": f"{symbol}_{check_id}",
        "symbol": symbol,
        "check_id": check_id,
        "severity": severity,
        "component": component,
        "description": description,
        "impact_estimate": impact_estimate,
        "proposed_fix": proposed_fix,
        "acceptance_test": acceptance_test,
        "details_json": json.dumps(details, sort_keys=True),
    }


def _load_selected_events(cfg: SymbolConfig) -> tuple[pd.DataFrame, pd.DataFrame, float, float]:
    required_columns = [
        "test_month",
        "close_ts",
        "candidate_uid",
        "pred_prob",
        "target_gross_pips",
        "threshold_mode",
        "threshold_days",
        "threshold_exec",
        "selected_exec",
    ]
    try:
        p = pd.read_parquet(cfg.pred_path, columns=required_columns).copy()
    except Exception as exc:
        raise ValueError(
            f"prediction parquet missing required columns or unreadable: {cfg.pred_path}: {exc}"
        ) from exc
    p["test_month"] = p["test_month"].astype(str)
    p["close_ts"] = _dt_utc_mixed(p["close_ts"])
    p["pred_prob"] = pd.to_numeric(p["pred_prob"], errors="coerce")
    p["target_gross_pips"] = pd.to_numeric(p["target_gross_pips"], errors="coerce")
    p["threshold_exec"] = pd.to_numeric(p["threshold_exec"], errors="coerce")
    p["threshold_days"] = pd.to_numeric(p["threshold_days"], errors="coerce")
    p["selected_exec"] = pd.to_numeric(p["selected_exec"], errors="coerce").fillna(0).astype(int)
    p = p.dropna(
        subset=["test_month", "close_ts", "candidate_uid", "pred_prob", "target_gross_pips"]
    ).copy()
    p = p[p["selected_exec"] == 1].copy()
    p["candidate_uid"] = p["candidate_uid"].astype(str)
    p["state_id"] = p["candidate_uid"].map(_parse_state_id)
    p["state_key"] = p["candidate_uid"].map(_parse_state_key)
    p["close_month_utc"] = p["close_ts"].dt.strftime("%Y-%m")

    d = pd.read_csv(
        cfg.stop_detail_path,
        usecols=[
            "close_ts",
            "candidate_uid",
            "touch_open_ts",
            "touch_close_ts",
            "touch_month",
            "touch_found_tick",
            "overshoot_tick_pips",
        ],
    ).copy()
    d["close_ts"] = _dt_utc_mixed(d["close_ts"])
    d["touch_open_ts"] = _dt_utc_mixed(d["touch_open_ts"])
    d["touch_close_ts"] = _dt_utc_mixed(d["touch_close_ts"])
    d["candidate_uid"] = d["candidate_uid"].astype(str)
    d["touch_found_tick"] = (
        pd.to_numeric(d["touch_found_tick"], errors="coerce").fillna(0).astype(int)
    )
    d["overshoot_tick_pips"] = pd.to_numeric(d["overshoot_tick_pips"], errors="coerce")
    d = d.dropna(subset=["candidate_uid", "close_ts"]).copy()

    dup = int(d.duplicated(subset=["candidate_uid", "close_ts"]).sum())
    d = d.sort_values(["candidate_uid", "close_ts"]).drop_duplicates(
        subset=["candidate_uid", "close_ts"], keep="last"
    )

    x = p.merge(d, on=["candidate_uid", "close_ts"], how="left", validate="many_to_one")
    x["__matched_detail"] = x["touch_found_tick"].notna().astype(int)
    match_rate = float(x["__matched_detail"].mean()) if len(x) else float("nan")
    x["touch_found_tick"] = (
        pd.to_numeric(x["touch_found_tick"], errors="coerce").fillna(0).astype(int)
    )
    x["overshoot_tick_pips"] = pd.to_numeric(x["overshoot_tick_pips"], errors="coerce")
    x["filled"] = (
        (x["touch_found_tick"] == 1)
        & x["overshoot_tick_pips"].notna()
        & (x["overshoot_tick_pips"] <= float(cfg.stop_cap_pips))
    )
    x["pnl_trade"] = pd.to_numeric(x["target_gross_pips"], errors="coerce") - pd.to_numeric(
        x["overshoot_tick_pips"], errors="coerce"
    )
    x["pnl_signal"] = x["pnl_trade"].where(x["filled"], 0.0)
    return x, d, float(dup), match_rate


def _schema_failure_frames(
    *,
    symbol: str,
    message: str,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    details = {"error": message}
    checks = pd.DataFrame(
        [
            {
                "symbol": symbol,
                "check_id": "C00",
                "status": "fail",
                "severity_if_fail": "critical",
                "component": "input_schema",
                "metric_name": "input_schema_valid",
                "metric_value": 0.0,
                "threshold": "valid required schema",
                "details_json": json.dumps(details, sort_keys=True),
            }
        ]
    )
    issues = pd.DataFrame(
        [
            _make_issue(
                symbol=symbol,
                check_id="C00",
                severity="critical",
                component="input_schema",
                description="Logical audit input schema is invalid.",
                impact_estimate="Governance logical audit cannot certify malformed evidence.",
                proposed_fix="Regenerate the malformed artifact with the required schema.",
                acceptance_test="Logical audit emits no C00 schema failures.",
                details=details,
            )
        ]
    )
    return checks, issues


def _check_overlap_divergence(
    selected: pd.DataFrame,
    monthly: pd.DataFrame,
    schedule: pd.DataFrame,
) -> tuple[float, float, int]:
    key_col = (
        "state_key"
        if ("state_key" in selected.columns and "state_key" in schedule.columns)
        else "state_id"
    )
    month_rows = monthly[monthly["status"] == "ok"][["test_month", "train_months"]].copy()
    if month_rows.empty:
        return float("nan"), float("nan"), 0
    medians: list[float] = []
    maxes: list[float] = []
    used = 0
    for _, r in month_rows.iterrows():
        month = str(r["test_month"])
        train_months = [m.strip() for m in str(r["train_months"]).split(",") if m.strip()]
        if len(train_months) < 2:
            continue
        states = schedule[schedule["test_month"] == month][key_col].astype(str).tolist()
        states = sorted(set(states))
        if len(states) < 2:
            continue
        g = selected[
            selected["test_month"].isin(train_months) & selected[key_col].astype(str).isin(states)
        ].copy()
        if g.empty:
            continue
        agg = g.groupby([key_col, "test_month"], as_index=False).agg(
            activity=("filled", "sum"),
            pnl=("pnl_signal", "mean"),
        )
        pa = agg.pivot(index=key_col, columns="test_month", values="activity").fillna(0.0)
        pp = agg.pivot(index=key_col, columns="test_month", values="pnl")
        if pa.shape[1] < 2 or pa.shape[0] < 2:
            continue
        ca = pa.T.corr()
        cp = pp.T.corr()
        diffs: list[float] = []
        names = sorted(set(ca.index).intersection(cp.index))
        for i, a in enumerate(names):
            for b in names[i + 1 :]:
                va = ca.loc[a, b] if a in ca.index and b in ca.columns else np.nan
                vp = cp.loc[a, b] if a in cp.index and b in cp.columns else np.nan
                if np.isfinite(va) and np.isfinite(vp):
                    diffs.append(abs(float(va) - float(vp)))
        if not diffs:
            continue
        medians.append(float(np.median(diffs)))
        maxes.append(float(np.max(diffs)))
        used += 1
    if not medians:
        return float("nan"), float("nan"), 0
    return float(np.median(medians)), float(np.max(maxes)), int(used)


def audit_symbol(
    cfg: SymbolConfig, exceptions: dict[str, Any] | None = None
) -> tuple[pd.DataFrame, pd.DataFrame]:
    def _read_safe(p: Path) -> pd.DataFrame:
        if not p.exists() or p.stat().st_size == 0:
            return pd.DataFrame()
        try:
            return pd.read_csv(p)
        except pd.errors.EmptyDataError:
            return pd.DataFrame()

    summary = _read_safe(cfg.summary_path)
    monthly = _read_safe(cfg.monthly_path)
    schedule = _read_safe(cfg.schedule_path)
    try:
        selected, detail_raw, detail_dup_count, detail_match_rate = _load_selected_events(cfg)
    except ValueError as exc:
        return _schema_failure_frames(symbol=cfg.symbol, message=str(exc))
    caps = _read_safe(cfg.stop_caps_path)
    caps = caps.sort_values("cap_pips").reset_index(drop=True)

    ok_months = (
        set(monthly[monthly["status"] == "ok"]["test_month"].astype(str).tolist())
        if not monthly.empty and "test_month" in monthly.columns
        else set()
    )
    if not schedule.empty and ("state_key" in schedule.columns or "state_id" in schedule.columns):
        if "state_key" in schedule.columns:
            schedule_keys = schedule[["test_month", "state_key"]].dropna().copy()
        else:
            schedule_keys = schedule[["test_month", "state_id"]].dropna().copy()
            schedule_keys["state_key"] = schedule_keys["state_id"].astype(str)
        strategy_rows = selected[selected["test_month"].isin(ok_months)].merge(
            schedule_keys[["test_month", "state_key"]],
            on=["test_month", "state_key"],
            how="inner",
        )
    else:
        schedule_keys = pd.DataFrame()
        strategy_rows = pd.DataFrame()
    if strategy_rows.empty:
        strategy_rows = selected[selected["test_month"].isin(ok_months)].copy()

    checks: list[dict[str, Any]] = []
    issues: list[dict[str, Any]] = []
    symbol = cfg.symbol

    def add_check(
        check_id: str,
        status: str,
        severity_if_fail: str,
        component: str,
        metric_name: str,
        metric_value: float,
        threshold: str,
        details: dict[str, Any],
        fail_desc: str,
        impact: str,
        fix: str,
        acc_test: str,
    ) -> None:
        # Check for monitoring exceptions
        final_status = status
        if status == "fail" and exceptions:
            for rule in exceptions.get("rules", []):
                rid = rule.get("metric_id")
                if rid == check_id:
                    syms = rule.get("symbols", [])
                    if ((not syms) or (cfg.symbol in syms)) and rule.get(
                        "disposition"
                    ) == "accepted_exception":
                        final_status = "accepted_exception"
                        break

        checks.append(
            {
                "symbol": symbol,
                "check_id": check_id,
                "status": final_status,
                "severity_if_fail": severity_if_fail,
                "component": component,
                "metric_name": metric_name,
                "metric_value": metric_value,
                "threshold": threshold,
                "details_json": json.dumps(details, sort_keys=True),
            }
        )
        if final_status == "fail":
            issues.append(
                _make_issue(
                    symbol=symbol,
                    check_id=check_id,
                    severity=severity_if_fail,
                    component=component,
                    description=fail_desc,
                    impact_estimate=impact,
                    proposed_fix=fix,
                    acceptance_test=acc_test,
                    details=details,
                )
            )

    # C01: test month and threshold timing consistency.
    mismatch_rate = (
        float(np.mean(selected["test_month"] != selected["close_month_utc"]))
        if len(selected)
        else np.nan
    )
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
    thr_days_min = float(pd.to_numeric(selected["threshold_days"], errors="coerce").min())
    c01_pass = (
        np.isfinite(mismatch_rate)
        and mismatch_rate <= 0.0
        and np.isfinite(selected_consistency)
        and selected_consistency >= 0.9999
        and np.isfinite(thr_days_min)
        and thr_days_min >= 1.0
    )
    add_check(
        "C01",
        "pass" if c01_pass else "fail",
        "critical",
        "threshold_timing",
        "selected_consistency",
        float(selected_consistency) if np.isfinite(selected_consistency) else float("nan"),
        "pred_prob >= threshold_exec for selected rows; month mismatch=0; threshold_days>=1",
        {
            "month_mismatch_rate": mismatch_rate,
            "threshold_days_min": thr_days_min,
            "rows_selected": int(len(selected)),
        },
        "Threshold timing/selection consistency failed; selected rows violate threshold or month alignment.",
        "Potential leakage or malformed execution selection.",
        "Rebuild selected flags per month using strictly train-window quantiles and enforce month-aligned timestamps.",
        "Zero month mismatches and >=99.99% selected rows satisfy pred_prob >= threshold_exec.",
    )

    # C02: per-(month,candidate) threshold must be stable.
    selected["close_day_utc"] = _dt_utc_mixed(selected["close_ts"]).dt.strftime("%Y-%m-%d")
    mode_counts = (
        selected["threshold_mode"].astype(str).str.lower().value_counts(dropna=True).to_dict()
        if "threshold_mode" in selected.columns
        else {}
    )
    uses_rolling = any("rolling" in k for k in mode_counts)
    group_cols = (
        ["test_month", "candidate_uid", "close_day_utc"]
        if uses_rolling
        else ["test_month", "candidate_uid"]
    )
    g_thr = (
        selected.groupby(group_cols, as_index=False)["threshold_exec"]
        .nunique(dropna=True)
        .rename(columns={"threshold_exec": "threshold_nunique"})
    )
    unstable = int((g_thr["threshold_nunique"] > 1).sum()) if not g_thr.empty else 0
    unstable_rate = float(unstable / max(len(g_thr), 1))
    add_check(
        "C02",
        "pass" if unstable == 0 else "fail",
        "high",
        "threshold_timing",
        "unstable_group_rate",
        unstable_rate,
        "0",
        {
            "unstable_groups": unstable,
            "groups_total": int(len(g_thr)),
            "group_cols": group_cols,
            "threshold_mode_counts": mode_counts,
        },
        "Threshold value changes within the expected stability group.",
        "Inconsistent thresholding can invalidate signal-selection reproducibility.",
        "For rolling mode, enforce one threshold per day; for fixed mode, enforce one threshold per month.",
        "For each expected stability group, threshold_nunique == 1.",
    )

    # C03: selected states should be gated (no non-gate fallback unless explicitly desired).
    missing_schedule_cols = sorted({"gate_pass", "test_month"} - set(schedule.columns))
    if missing_schedule_cols:
        non_gate = pd.DataFrame()
        non_gate_count = 0
        months_with_non_gate: list[str] = []
        c03_pass = False
    else:
        non_gate = schedule[schedule["gate_pass"] == False].copy()  # noqa: E712
        non_gate_count = int(len(non_gate))
        months_with_non_gate = sorted(non_gate["test_month"].astype(str).unique().tolist())
        c03_pass = non_gate_count == 0
    add_check(
        "C03",
        "pass" if c03_pass else "fail",
        "high",
        "state_selection",
        "selected_non_gate_states",
        float(non_gate_count),
        "0",
        {
            "missing_schedule_columns": missing_schedule_cols,
            "months_with_non_gate": months_with_non_gate,
            "non_gate_rows": non_gate_count,
        },
        "Fallback selected one or more states that failed train-time gate checks.",
        "Can reintroduce weak states and inflate apparent diversification/capacity.",
        "Add strict gate mode: do not backfill with gate_fail states to satisfy min_states.",
        "selected_non_gate_states == 0 for all months.",
    )

    # C04: activity-correlation may diverge from pnl-correlation.
    med_diff, max_diff, used_months = _check_overlap_divergence(selected, monthly, schedule)
    c04_pass = np.isfinite(med_diff) and med_diff <= 0.40
    add_check(
        "C04",
        "pass" if c04_pass else "fail",
        "medium",
        "overlap_diversification",
        "median_abs_corr_diff",
        float(med_diff) if np.isfinite(med_diff) else float("nan"),
        "<=0.40",
        {"max_abs_corr_diff": max_diff, "months_evaluated": used_months},
        "Dependence measured via activity counts diverges from pnl dependence.",
        "Portfolio overlap filter may understate true pnl co-movement.",
        "Compute overlap on monthly pnl vectors (or blended activity+pnl correlation).",
        "median_abs_corr_diff <= 0.40 after overlap metric switch.",
    )

    # C05: stop-limit detail join integrity.
    by_month_match = (
        strategy_rows.assign(
            matched=pd.to_numeric(strategy_rows["__matched_detail"], errors="coerce")
            .fillna(0)
            .astype(int)
        )
        .groupby("test_month", as_index=False)["matched"]
        .mean()
    )
    min_match = float(by_month_match["matched"].min()) if not by_month_match.empty else np.nan
    c05_pass = (
        detail_dup_count == 0
        and np.isfinite(detail_match_rate)
        and detail_match_rate >= 0.995
        and np.isfinite(min_match)
        and min_match >= 0.995
    )
    add_check(
        "C05",
        "pass" if c05_pass else "fail",
        "high",
        "stop_limit_join",
        "min_month_match_rate",
        float(min_match) if np.isfinite(min_match) else float("nan"),
        ">=0.995 and duplicate_keys=0",
        {
            "duplicate_keys": int(detail_dup_count),
            "overall_match_rate": detail_match_rate,
            "strategy_rows": int(len(strategy_rows)),
        },
        "Stop-limit detail join has duplicates or low key-match coverage.",
        "Execution model can silently drop/alter rows if key integrity is weak.",
        "Deduplicate detail at source and enforce key uniqueness + match-rate gate per month.",
        "No duplicate keys and monthly/overall match rate >= 99.5%.",
    )

    # C06: fill-rate monotonicity by cap.
    fill = pd.to_numeric(caps["fill_rate"], errors="coerce").to_numpy(dtype=float)
    diffs = np.diff(fill)
    mono_viol = int(np.sum(diffs < -1e-9))
    add_check(
        "C06",
        "pass" if mono_viol == 0 else "fail",
        "high",
        "stop_limit_model",
        "monotonicity_violations",
        float(mono_viol),
        "0",
        {"caps_rows": int(len(caps)), "min_diff": float(np.min(diffs)) if len(diffs) else np.nan},
        "Fill-rate monotonicity violated across increasing stop-limit caps.",
        "Implies inconsistent cap simulation or merge logic.",
        "Recompute cap sweep on deduped detail and enforce monotonic validation step.",
        "No negative first-differences in fill_rate ordered by cap_pips.",
    )

    # C07: summary/monthly denominator consistency.
    ok = monthly[monthly["status"] == "ok"].copy()
    s0 = summary.iloc[0]
    rows_total_calc = int(pd.to_numeric(ok["rows"], errors="coerce").sum()) if not ok.empty else 0
    sig_total_calc = (
        int(pd.to_numeric(ok["signal_rows"], errors="coerce").sum()) if not ok.empty else 0
    )
    fill_calc = float(rows_total_calc / max(sig_total_calc, 1)) if sig_total_calc > 0 else np.nan
    diff_rows = abs(rows_total_calc - int(s0["rows_total"]))
    diff_sig = abs(sig_total_calc - int(s0["signal_rows_total"]))
    diff_fill = abs(fill_calc - float(s0["fill_rate_overall"])) if np.isfinite(fill_calc) else 0.0
    c07_pass = diff_rows == 0 and diff_sig == 0 and diff_fill <= 1e-9
    add_check(
        "C07",
        "pass" if c07_pass else "fail",
        "critical",
        "metrics_semantics",
        "rows_total_diff",
        float(diff_rows),
        "0 (and signal diff=0, fill diff<=1e-9)",
        {"signal_rows_diff": diff_sig, "fill_rate_diff": diff_fill},
        "Summary and monthly denominator math are inconsistent.",
        "Misstated capacity/expectancy invalidates decision-making.",
        "Derive summary exclusively from monthly rows in one function, then serialize.",
        "rows/signal/fill recomputation from monthly matches summary exactly.",
    )

    # C08: warmup and month continuity.
    months = sorted(monthly["test_month"].astype(str).unique().tolist())
    idx = (
        pd.period_range(start=min(months), end=max(months), freq="M").astype(str).tolist()
        if months
        else []
    )
    missing_months = sorted(set(idx) - set(months))
    warmup_count = int((monthly["status"] == "warmup_skip").sum())
    no_gate_states_count = int((monthly["status"] == "no_gate_states").sum())
    allowed_statuses = {"ok", "warmup_skip", "no_gate_states", "no_test_rows"}
    unexpected_non_ok = int((~monthly["status"].isin(sorted(allowed_statuses))).sum())
    c08_pass = (
        len(missing_months) == 0
        and warmup_count == int(cfg.min_train_months)
        and unexpected_non_ok == 0
    )
    add_check(
        "C08",
        "pass" if c08_pass else "fail",
        "medium",
        "wfo_windowing",
        "warmup_count",
        float(warmup_count),
        f"=={cfg.min_train_months}, missing_months=0, unexpected_non_ok=0 (allowed={sorted(allowed_statuses)})",
        {
            "missing_months": missing_months,
            "unexpected_non_ok": unexpected_non_ok,
            "no_gate_states_count": no_gate_states_count,
            "months_total": len(months),
        },
        "Warmup/month continuity check failed (gaps or unexpected status values).",
        "Can bias robustness by silently dropping hard months.",
        "Enforce contiguous month index and explicit status handling for all months.",
        "Exactly min_train_months warmup rows and no missing months in range.",
    )

    # C09: bootstrap label/unit consistency against monthly table.
    ok_gross = pd.to_numeric(ok["mean_gross_pips"], errors="coerce").to_numpy(dtype=float)
    ok_signal = pd.to_numeric(ok["mean_signal_pips"], errors="coerce").to_numpy(dtype=float)
    lb95_gross_calc = _bootstrap_lb95(ok_gross, paths=cfg.bootstrap_paths, seed=cfg.seed + 999)
    lb95_signal_calc = _bootstrap_lb95(ok_signal, paths=cfg.bootstrap_paths, seed=cfg.seed + 1199)
    diff_lb95_g = abs(lb95_gross_calc - float(s0["lb95_month_mean_gross_pips"]))
    diff_lb95_s = abs(lb95_signal_calc - float(s0["lb95_month_mean_signal_pips"]))
    c09_pass = diff_lb95_g <= 1e-8 and diff_lb95_s <= 1e-8
    add_check(
        "C09",
        "pass" if c09_pass else "fail",
        "high",
        "robustness_metric",
        "lb95_gross_abs_diff",
        float(diff_lb95_g),
        "<=1e-8 (and signal diff<=1e-8)",
        {"lb95_signal_abs_diff": diff_lb95_s},
        "LB95 values in summary are not reproducible from monthly series/seed settings.",
        "Robustness claims may be mislabeled or computed on unintended unit.",
        "Centralize bootstrap call and persist seed/paths in summary metadata.",
        "Recomputed LB95 gross/signal exactly match summary output.",
    )

    # C10: timezone/timestamp causality consistency.
    matched = strategy_rows[
        pd.to_numeric(strategy_rows["__matched_detail"], errors="coerce").fillna(0).astype(int) == 1
    ].copy()
    touch_open = _dt_utc_mixed(matched["touch_open_ts"])
    touch_close = _dt_utc_mixed(matched["touch_close_ts"])
    close_ts = _dt_utc_mixed(matched["close_ts"])
    touch_month_ref = pd.to_numeric(matched["touch_month"], errors="coerce")
    touch_month_ref = touch_month_ref.fillna(-1).astype(int).astype(str).str.zfill(6)
    bad_touch_order = (
        float(np.mean((touch_close < touch_open).fillna(False))) if len(matched) else np.nan
    )
    touch_before_decision = (
        float(np.mean((touch_open < close_ts).fillna(False))) if len(matched) else np.nan
    )
    touch_month_mismatch = (
        float(np.mean((touch_open.dt.strftime("%Y%m") != touch_month_ref).fillna(False)))
        if len(matched)
        else np.nan
    )
    c10_pass = (
        np.isfinite(bad_touch_order)
        and bad_touch_order <= 0.0
        and np.isfinite(touch_before_decision)
        and touch_before_decision <= 0.0
        and np.isfinite(touch_month_mismatch)
        and touch_month_mismatch <= 0.0
    )
    max_v = float(np.nanmax([bad_touch_order, touch_before_decision, touch_month_mismatch]))
    add_check(
        "C10",
        "pass" if c10_pass else "fail",
        "critical",
        "timestamp_causality",
        "max_timestamp_violation_rate",
        max_v if np.isfinite(max_v) else float("nan"),
        "0 (and touch_order=0, touch_month_mismatch=0)",
        {
            "touch_order_violation_rate": bad_touch_order,
            "touch_before_decision_rate": touch_before_decision,
            "touch_month_mismatch_rate": touch_month_mismatch,
            "matched_rows": int(len(matched)),
        },
        "Touch timestamps are not causally ordered relative to decision timestamps.",
        "Timezone coercion or bar alignment issue can invalidate execution simulation.",
        "Normalize all timestamps to UTC at source, and assert close<=touch_open<=touch_close.",
        "No touch-order, touch-before-decision, or touch-month mismatch violations.",
    )

    checks_df = pd.DataFrame(checks)
    issues_df = pd.DataFrame(issues)
    if not issues_df.empty:
        sev_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        issues_df["sev_rank"] = issues_df["severity"].map(sev_order).fillna(9).astype(int)
        issues_df = issues_df.sort_values(["sev_rank", "symbol", "check_id"]).drop(
            columns=["sev_rank"]
        )
    return checks_df, issues_df


def run_audit(
    symbols: list[str],
    *,
    base_dir: Path,
    out_checks_csv: Path,
    out_issues_csv: Path,
    report_out: Path,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    cfg_map = _default_configs(base_dir)
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
            cfg.monthly_path,
            cfg.summary_path,
            cfg.schedule_path,
            cfg.stop_detail_path,
            cfg.stop_caps_path,
        ]
        miss = [str(p) for p in required if not Path(p).exists()]
        if miss:
            raise FileNotFoundError(f"{s}: missing required inputs: {miss}")
        checks_df, issues_df = audit_symbol(cfg, exceptions=exceptions)
        all_checks.append(checks_df)
        all_issues.append(issues_df)

    checks_cols = [
        "symbol",
        "check_id",
        "status",
        "severity_if_fail",
        "component",
        "metric_name",
        "metric_value",
        "threshold",
        "details_json",
    ]
    issues_cols = [
        "issue_id",
        "symbol",
        "check_id",
        "severity",
        "component",
        "description",
        "impact_estimate",
        "proposed_fix",
        "acceptance_test",
        "details_json",
    ]
    checks = (
        pd.concat(all_checks, ignore_index=True)
        if all_checks
        else pd.DataFrame(columns=checks_cols)
    )
    issues = (
        pd.concat(all_issues, ignore_index=True)
        if all_issues
        else pd.DataFrame(columns=issues_cols)
    )
    if checks.empty:
        checks = pd.DataFrame(columns=checks_cols)
    if issues.empty:
        issues = pd.DataFrame(columns=issues_cols)

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
    pass_counts = (
        checks.groupby(["symbol", "status"], as_index=False)
        .size()
        .pivot(index="symbol", columns="status", values="size")
        .fillna(0)
        .reset_index()
        if not checks.empty
        else pd.DataFrame()
    )
    lines: list[str] = []
    lines.append("# OCO Logical Audit (All Active Symbols)")
    lines.append("")
    lines.append("## Outputs")
    lines.append(f"- checks_csv: `{out_checks_csv}`")
    lines.append(f"- issues_csv: `{out_issues_csv}`")
    lines.append("")
    lines.append("## Severity Counts")
    lines.append(_table(sev_counts))
    lines.append("")
    lines.append("## Check Status By Symbol")
    lines.append(_table(pass_counts))
    lines.append("")
    lines.append("## Failed Issues")
    lines.append(
        _table(
            issues[
                [
                    "issue_id",
                    "symbol",
                    "severity",
                    "component",
                    "description",
                    "impact_estimate",
                    "proposed_fix",
                    "acceptance_test",
                ]
            ]
            if not issues.empty
            else pd.DataFrame()
        )
    )
    lines.append("")
    lines.append("## All Checks")
    lines.append(
        _table(
            checks[
                [
                    "symbol",
                    "check_id",
                    "status",
                    "severity_if_fail",
                    "component",
                    "metric_name",
                    "metric_value",
                    "threshold",
                ]
            ]
            if not checks.empty
            else pd.DataFrame()
        )
    )
    lines.append("")
    report_out.write_text("\n".join(lines), encoding="utf-8")
    print(f"wrote: {out_checks_csv}")
    print(f"wrote: {out_issues_csv}")
    print(f"wrote: {report_out}")
    return checks, issues


def main() -> None:
    p = argparse.ArgumentParser(description="Audit OCO logical issues for target symbols")
    p.add_argument("--symbols", default="EURUSD,GBPUSD,USDJPY,USDCHF,AUDUSD,USDCAD")
    p.add_argument("--base-dir", default="data/analysis/tick_opportunity_mining")
    p.add_argument(
        "--out-checks-csv",
        default="data/analysis/tick_opportunity_mining/oco_logical_audit_checks.csv",
    )
    p.add_argument(
        "--out-issues-csv",
        default="data/analysis/tick_opportunity_mining/oco_logical_audit_issues.csv",
    )
    p.add_argument(
        "--report-out",
        default="docs/analysis/oco_logical_audit_report.md",
    )
    args = p.parse_args()
    symbols = [x.strip().upper() for x in str(args.symbols).split(",") if x.strip()]
    run_audit(
        symbols,
        base_dir=Path(str(args.base_dir)),
        out_checks_csv=Path(str(args.out_checks_csv)),
        out_issues_csv=Path(str(args.out_issues_csv)),
        report_out=Path(str(args.report_out)),
    )


if __name__ == "__main__":
    main()
