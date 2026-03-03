#!/usr/bin/env python3
"""Build threshold lookback and retrain-cadence sensitivity diagnostics."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

try:
    import yaml
except Exception:
    yaml = None  # type: ignore[assignment]


@dataclass(frozen=True)
class SymbolPaths:
    symbol: str
    pred_path: Path
    lock_path: Path


def _table(df: pd.DataFrame) -> str:
    if df.empty:
        return "_empty_"
    try:
        return df.to_markdown(index=False)
    except Exception:
        return "```\n" + df.to_string(index=False) + "\n```"


def _parse_symbols(raw: str) -> list[str]:
    out = [x.strip().upper() for x in str(raw).split(",") if x.strip()]
    return sorted(list(dict.fromkeys(out)))


def _parse_ints(raw: str) -> list[int]:
    return [int(x.strip()) for x in str(raw).split(",") if x.strip()]


def _parse_float(raw: str) -> list[float]:
    return [float(x.strip()) for x in str(raw).split(",") if x.strip()]


def _dt_utc(s: pd.Series) -> pd.Series:
    try:
        return pd.to_datetime(s, utc=True, errors="coerce", format="mixed")
    except TypeError:
        return pd.to_datetime(s, utc=True, errors="coerce")


def _to_num(s: pd.Series) -> pd.Series:
    return pd.to_numeric(s, errors="coerce")


def _default_paths(symbol: str) -> SymbolPaths:
    s = str(symbol).upper()
    s_low = s.lower()

    # EURUSD and AUDUSD happen to use the same top-level folder name (fullcap), but the others are suffixed
    if s in ("EURUSD", "AUDUSD"):
        folder = "wfo_2025_m3to1_oco_fullcap"
    else:
        folder = f"wfo_2025_m3to1_oco_fullcap_{s_low}"

    pred = Path(
        f"data/analysis/tick_opportunity_mining/{folder}/{s}_oco_monthly_predictions.parquet"
    )

    lock = Path(f"configs/research/governance/oco/{s_low}_oco_live_lock.json")
    return SymbolPaths(symbol=s, pred_path=pred, lock_path=lock)


def _read_policy(path: Path) -> dict[str, Any]:
    if (yaml is None) or (not path.exists()):
        return {"cadence_days": 30, "window_days": 3, "anchor_day_utc": 1}
    obj = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(obj, dict):
        return {"cadence_days": 30, "window_days": 3, "anchor_day_utc": 1}
    return obj


def _read_lock_lookback(lock_path: Path, default: int) -> int:
    if not lock_path.exists():
        return int(default)
    try:
        obj = json.loads(lock_path.read_text(encoding="utf-8"))
    except Exception:
        return int(default)
    rt = obj.get("locked_runtime", {}) if isinstance(obj, dict) else {}
    v = rt.get("rolling_threshold_days", default) if isinstance(rt, dict) else default
    try:
        return int(v)
    except Exception:
        return int(default)


def _daily_threshold_triplet(
    *,
    d: pd.DataFrame,
    day_col: str,
    pred_col: str,
    quantiles: list[float],
    lookback_days: int,
    min_history: int,
) -> dict[pd.Timestamp, dict[float, float]]:
    out: dict[pd.Timestamp, dict[float, float]] = {}
    q_vals = [float(q) for q in quantiles]
    all_pred = _to_num(d[pred_col]).dropna().to_numpy(dtype=float)
    fallback = (
        np.quantile(all_pred, q_vals).tolist() if len(all_pred) else [float("nan")] * len(q_vals)
    )

    days = sorted(pd.Series(d[day_col]).dropna().unique().tolist())
    hist_days: list[pd.Timestamp] = []
    hist_arrays: dict[pd.Timestamp, np.ndarray] = {}
    for day in days:
        cur_day = pd.Timestamp(day)
        start = cur_day - pd.Timedelta(days=int(max(1, lookback_days)))
        keep = [x for x in hist_days if x >= start]
        hist_days = keep
        vals = [hist_arrays[x] for x in hist_days if x in hist_arrays and len(hist_arrays[x]) > 0]
        hist = np.concatenate(vals) if vals else np.array([], dtype=float)
        if len(hist) >= int(max(1, min_history)) or len(hist) > 0:
            q_out = np.quantile(hist, q_vals).tolist()
        else:
            q_out = fallback
        out[cur_day] = {float(q): float(v) for q, v in zip(q_vals, q_out, strict=False)}

        arr = _to_num(d.loc[d[day_col] == cur_day, pred_col]).dropna().to_numpy(dtype=float)
        hist_days.append(cur_day)
        hist_arrays[cur_day] = arr
    return out


def _selection_metrics(d: pd.DataFrame, *, sel_col: str) -> dict[str, float]:
    x = d.copy()
    x["_sel"] = x[sel_col].astype(bool)
    x["_target"] = _to_num(x["target_gross_pips"])
    x["_signal"] = x["_target"] * x["_sel"].astype(int)
    rows_total = int(len(x))
    selected_rows = int(x["_sel"].sum())
    selected_rate = float(selected_rows / rows_total) if rows_total > 0 else float("nan")
    mean_selected = (
        float(_to_num(x.loc[x["_sel"], "_target"]).mean()) if selected_rows > 0 else float("nan")
    )
    mean_signal = (
        float(_to_num(x["_signal"]).sum() / rows_total) if rows_total > 0 else float("nan")
    )

    month_rows = x.groupby("test_month", as_index=False).agg(
        rows=("target_gross_pips", "count"), selected=("_sel", "sum"), signal_sum=("_signal", "sum")
    )
    month_rows["mean_signal_pips"] = _to_num(month_rows["signal_sum"]) / _to_num(
        month_rows["rows"]
    ).replace(0, np.nan)
    lb95_month_signal = (
        float(
            np.quantile(
                _to_num(month_rows["mean_signal_pips"]).dropna().to_numpy(dtype=float), 0.05
            )
        )
        if not month_rows.empty
        else float("nan")
    )
    pos_month_ratio = (
        float((_to_num(month_rows["mean_signal_pips"]) > 0).mean())
        if len(_to_num(month_rows["mean_signal_pips"]).dropna()) > 0
        else float("nan")
    )

    y = (_to_num(x["target_gross_pips"]) > 0).astype(float)
    sqe = (_to_num(x["pred_prob"]) - y) ** 2
    x["_brier"] = sqe
    brier_month = x[x["_sel"]].groupby("test_month", as_index=False).agg(brier=("_brier", "mean"))
    w14 = float(_to_num(brier_month["brier"]).std(ddof=0)) if len(brier_month) > 0 else float("nan")

    cov = x.groupby("test_month", as_index=False).agg(
        sel=("_sel", "sum"), rows=("target_gross_pips", "count")
    )
    cov["coverage"] = _to_num(cov["sel"]) / _to_num(cov["rows"]).replace(0, np.nan)
    w15 = float(_to_num(cov["coverage"]).diff().abs().dropna().mean()) if len(cov) > 1 else 0.0

    return {
        "rows_total": float(rows_total),
        "selected_rows": float(selected_rows),
        "selected_rate": selected_rate,
        "mean_gross_selected_pips": mean_selected,
        "mean_signal_pips": mean_signal,
        "lb95_month_mean_signal_pips": lb95_month_signal,
        "positive_months_ratio": pos_month_ratio,
        "w14_brier_drift_std": w14,
        "w15_selection_turnover": w15,
    }


def _governance_window_coverage(
    *, cadence_days: int, window_days: int, anchor_day: int, year: int
) -> tuple[float, float, int]:
    start = pd.Timestamp(f"{int(year)}-01-01", tz="UTC")
    end = pd.Timestamp(f"{int(year)}-12-31", tz="UTC")
    anchor = pd.Timestamp(f"{int(year)}-01-{int(max(1, min(anchor_day, 28))):02d}", tz="UTC")
    due_dates: list[pd.Timestamp] = []
    cur = anchor
    while cur <= (end + pd.Timedelta(days=int(cadence_days))):
        due_dates.append(cur)
        cur = cur + pd.Timedelta(days=int(max(1, cadence_days)))

    covered: set[pd.Timestamp] = set()
    for due in due_dates:
        a = due - pd.Timedelta(days=int(max(0, window_days)))
        b = due + pd.Timedelta(days=int(max(0, window_days)))
        if b < start or a > end:
            continue
        lo = max(a, start)
        hi = min(b, end)
        for day in pd.date_range(lo, hi, freq="D", tz="UTC"):
            covered.add(pd.Timestamp(day))
    total_days = len(pd.date_range(start, end, freq="D", tz="UTC"))
    hit_rate = float(len(covered) / total_days) if total_days > 0 else float("nan")
    months = set(int(x.month) for x in covered)
    month_hit = float(len(months) / 12.0)
    events = int(sum(1 for x in due_dates if start <= x <= end))
    return hit_rate, month_hit, events


def run(
    *,
    symbols: list[str],
    lookback_days: list[int],
    cadence_days: list[int],
    window_days: list[int],
    quantile: float,
    quantile_delta: float,
    min_history: int,
    governance_policy_yaml: Path,
    symbol_paths: dict[str, SymbolPaths] | None = None,
    out_sensitivity_csv: Path,
    out_alerts_csv: Path,
    report_out: Path,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    policy = _read_policy(governance_policy_yaml)
    policy_cad = int(policy.get("cadence_days", 30))
    policy_win = int(policy.get("window_days", 3))
    anchor_day = int(policy.get("anchor_day_utc", 1))

    rows: list[dict[str, Any]] = []
    alerts: list[dict[str, Any]] = []
    for symbol in symbols:
        paths = (
            symbol_paths.get(symbol, _default_paths(symbol))
            if symbol_paths is not None
            else _default_paths(symbol)
        )
        if not paths.pred_path.exists():
            alerts.append(
                {
                    "symbol": symbol,
                    "test_month": "",
                    "metric_id": "TS_DATA_MISSING",
                    "metric_value": np.nan,
                    "warn_threshold": np.nan,
                    "fail_threshold": np.nan,
                    "band": "red",
                    "severity": "high",
                    "source_path": str(paths.pred_path),
                    "details_json": json.dumps({"reason": "missing_predictions"}, sort_keys=True),
                    "evaluated_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                }
            )
            continue
        d = pd.read_parquet(
            paths.pred_path, columns=["test_month", "close_ts", "pred_prob", "target_gross_pips"]
        ).copy()
        d["close_ts"] = _dt_utc(d["close_ts"])
        d["pred_prob"] = _to_num(d["pred_prob"])
        d["target_gross_pips"] = _to_num(d["target_gross_pips"])
        d = d.dropna(subset=["close_ts", "pred_prob", "target_gross_pips"]).copy()
        if d.empty:
            continue
        d["day_utc"] = d["close_ts"].dt.floor("D")
        d["test_month"] = d["test_month"].astype(str)
        d = d.sort_values("close_ts").reset_index(drop=True)
        current_lookback = _read_lock_lookback(paths.lock_path, default=20)
        year_ref = int(d["close_ts"].dt.year.max()) + 1
        q0 = float(quantile)
        qd = float(max(0.001, quantile_delta))
        q_values = [max(0.0, min(1.0, q0 - qd)), q0, max(0.0, min(1.0, q0 + qd))]
        q_values = sorted(list(dict.fromkeys(q_values)))
        q_low = float(q_values[0])
        q_mid = float(q0 if q0 in q_values else q_values[len(q_values) // 2])
        q_high = float(q_values[-1])

        look_rows: list[dict[str, Any]] = []
        for lb in sorted(list(dict.fromkeys([int(x) for x in lookback_days]))):
            thr_map = _daily_threshold_triplet(
                d=d,
                day_col="day_utc",
                pred_col="pred_prob",
                quantiles=[q_low, q_mid, q_high],
                lookback_days=int(lb),
                min_history=int(min_history),
            )
            t_low = d["day_utc"].map(lambda x: thr_map.get(pd.Timestamp(x), {}).get(q_low, np.nan))
            t_mid = d["day_utc"].map(lambda x: thr_map.get(pd.Timestamp(x), {}).get(q_mid, np.nan))
            t_high = d["day_utc"].map(
                lambda x: thr_map.get(pd.Timestamp(x), {}).get(q_high, np.nan)
            )

            dd = d.copy()
            dd["sel_low"] = dd["pred_prob"] >= _to_num(t_low)
            dd["sel_mid"] = dd["pred_prob"] >= _to_num(t_mid)
            dd["sel_high"] = dd["pred_prob"] >= _to_num(t_high)
            m_low = _selection_metrics(dd, sel_col="sel_low")
            m_mid = _selection_metrics(dd, sel_col="sel_mid")
            m_high = _selection_metrics(dd, sel_col="sel_high")
            w13 = abs(float(m_high["mean_signal_pips"]) - float(m_low["mean_signal_pips"])) / max(
                1e-9, 2.0 * (q_high - q_low)
            )
            look_rows.append(
                {
                    "symbol": symbol,
                    "lookback_days": int(lb),
                    "quantile": float(q_mid),
                    "rows_total": int(m_mid["rows_total"]),
                    "selected_rows": int(m_mid["selected_rows"]),
                    "selected_rate": float(m_mid["selected_rate"]),
                    "mean_gross_selected_pips": float(m_mid["mean_gross_selected_pips"]),
                    "mean_signal_pips": float(m_mid["mean_signal_pips"]),
                    "lb95_month_mean_signal_pips": float(m_mid["lb95_month_mean_signal_pips"]),
                    "positive_months_ratio": float(m_mid["positive_months_ratio"]),
                    "w13_threshold_fragility": float(w13),
                    "w14_brier_drift_std": float(m_mid["w14_brier_drift_std"]),
                    "w15_selection_turnover": float(m_mid["w15_selection_turnover"]),
                }
            )

        lr = pd.DataFrame(look_rows)
        if lr.empty:
            continue
        combos = []
        for _, r in lr.iterrows():
            for cad in cadence_days:
                for win in window_days:
                    hit, mhit, events = _governance_window_coverage(
                        cadence_days=int(cad),
                        window_days=int(win),
                        anchor_day=int(anchor_day),
                        year=int(year_ref),
                    )
                    x = dict(r)
                    x["cadence_days"] = int(cad)
                    x["window_days"] = int(win)
                    x["governance_window_hit_rate"] = float(hit)
                    x["governance_month_hit_rate"] = float(mhit)
                    x["retrain_events_per_year"] = int(events)
                    x["is_current_policy"] = int(
                        (int(r["lookback_days"]) == int(current_lookback))
                        and (int(cad) == int(policy_cad))
                        and (int(win) == int(policy_win))
                    )
                    combos.append(x)
        z = pd.DataFrame(combos)
        if z.empty:
            continue
        z["stability_raw"] = (
            _to_num(z["w13_threshold_fragility"]).fillna(np.inf)
            + 10.0 * _to_num(z["w14_brier_drift_std"]).fillna(np.inf)
            + _to_num(z["w15_selection_turnover"]).fillna(np.inf)
        )
        z["expect_rank"] = _to_num(z["lb95_month_mean_signal_pips"]).rank(
            method="average", pct=True
        )
        z["stability_rank"] = _to_num(z["stability_raw"]).rank(
            method="average", pct=True, ascending=False
        )
        z["governance_score"] = 0.6 * _to_num(z["governance_window_hit_rate"]).fillna(
            0.0
        ) + 0.4 * _to_num(z["governance_month_hit_rate"]).fillna(0.0)
        z["final_score"] = (
            0.4 * _to_num(z["expect_rank"]).fillna(0.0)
            + 0.4 * _to_num(z["stability_rank"]).fillna(0.0)
            + 0.2 * _to_num(z["governance_score"]).fillna(0.0)
        )
        z = z.sort_values("final_score", ascending=False).reset_index(drop=True)
        z["is_recommended"] = 0
        if not z.empty:
            z.loc[0, "is_recommended"] = 1
        rows.extend(z.to_dict(orient="records"))

        top = z.iloc[0] if not z.empty else None
        cur = z[z["is_current_policy"] == 1].head(1)
        cur_row = cur.iloc[0] if not cur.empty else None
        if top is not None:
            for metric_id, value, warn, fail, mode in [
                (
                    "TS01_W13_THRESHOLD_FRAGILITY",
                    float(top["w13_threshold_fragility"]),
                    2.5,
                    4.0,
                    "ge",
                ),
                ("TS02_W14_BRIER_DRIFT_STD", float(top["w14_brier_drift_std"]), 0.01, 0.02, "ge"),
                (
                    "TS03_LB95_MONTH_SIGNAL",
                    float(top["lb95_month_mean_signal_pips"]),
                    0.10,
                    0.00,
                    "le",
                ),
                ("TS04_SELECTION_TURNOVER", float(top["w15_selection_turnover"]), 0.15, 0.25, "ge"),
            ]:
                if not np.isfinite(value):
                    band = "gray"
                    sev = "high"
                elif mode == "ge":
                    band = "red" if value >= fail else ("amber" if value >= warn else "green")
                    sev = "high" if band == "red" else ("medium" if band == "amber" else "info")
                else:
                    band = "red" if value <= fail else ("amber" if value <= warn else "green")
                    sev = "high" if band == "red" else ("medium" if band == "amber" else "info")
                alerts.append(
                    {
                        "symbol": symbol,
                        "test_month": "",
                        "metric_id": metric_id,
                        "metric_value": value,
                        "warn_threshold": float(warn),
                        "fail_threshold": float(fail),
                        "band": band,
                        "severity": sev,
                        "source_path": str(paths.pred_path),
                        "details_json": json.dumps(
                            {
                                "lookback_days": int(top["lookback_days"]),
                                "cadence_days": int(top["cadence_days"]),
                                "window_days": int(top["window_days"]),
                                "is_recommended": 1,
                            },
                            sort_keys=True,
                        ),
                        "evaluated_at_utc": datetime.now(timezone.utc).strftime(
                            "%Y-%m-%dT%H:%M:%SZ"
                        ),
                    }
                )
        if (top is not None) and (cur_row is not None):
            delta = float(
                top["lb95_month_mean_signal_pips"] - cur_row["lb95_month_mean_signal_pips"]
            )
            band = "red" if delta < -0.15 else ("amber" if delta < -0.05 else "green")
            sev = "high" if band == "red" else ("medium" if band == "amber" else "info")
            alerts.append(
                {
                    "symbol": symbol,
                    "test_month": "",
                    "metric_id": "TS05_POLICY_GAP_LB95",
                    "metric_value": delta,
                    "warn_threshold": -0.05,
                    "fail_threshold": -0.15,
                    "band": band,
                    "severity": sev,
                    "source_path": str(paths.pred_path),
                    "details_json": json.dumps(
                        {
                            "recommended": {
                                "lookback_days": int(top["lookback_days"]),
                                "cadence_days": int(top["cadence_days"]),
                                "window_days": int(top["window_days"]),
                            },
                            "current": {
                                "lookback_days": int(cur_row["lookback_days"]),
                                "cadence_days": int(cur_row["cadence_days"]),
                                "window_days": int(cur_row["window_days"]),
                            },
                        },
                        sort_keys=True,
                    ),
                    "evaluated_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                }
            )

    sensitivity = pd.DataFrame(rows)
    if not sensitivity.empty:
        order_cols = [
            "symbol",
            "lookback_days",
            "cadence_days",
            "window_days",
            "quantile",
            "rows_total",
            "selected_rows",
            "selected_rate",
            "mean_gross_selected_pips",
            "mean_signal_pips",
            "lb95_month_mean_signal_pips",
            "positive_months_ratio",
            "w13_threshold_fragility",
            "w14_brier_drift_std",
            "w15_selection_turnover",
            "governance_window_hit_rate",
            "governance_month_hit_rate",
            "retrain_events_per_year",
            "final_score",
            "is_recommended",
            "is_current_policy",
        ]
        sensitivity = (
            sensitivity[order_cols]
            .sort_values(["symbol", "final_score"], ascending=[True, False])
            .reset_index(drop=True)
        )
    alerts_df = pd.DataFrame(alerts)

    out_sensitivity_csv.parent.mkdir(parents=True, exist_ok=True)
    out_alerts_csv.parent.mkdir(parents=True, exist_ok=True)
    report_out.parent.mkdir(parents=True, exist_ok=True)
    sensitivity.to_csv(out_sensitivity_csv, index=False)
    alerts_df.to_csv(out_alerts_csv, index=False)

    top = (
        sensitivity[sensitivity["is_recommended"] == 1].sort_values("symbol")
        if (not sensitivity.empty and "is_recommended" in sensitivity.columns)
        else pd.DataFrame()
    )
    current = (
        sensitivity[sensitivity["is_current_policy"] == 1].sort_values("symbol")
        if (not sensitivity.empty and "is_current_policy" in sensitivity.columns)
        else pd.DataFrame()
    )
    lines: list[str] = []
    lines.append("# OCO Threshold Sensitivity Report")
    lines.append("")
    lines.append(
        f"- generated_at_utc: `{datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}`"
    )
    lines.append(f"- sensitivity_csv: `{out_sensitivity_csv}`")
    lines.append(f"- alerts_csv: `{out_alerts_csv}`")
    lines.append(f"- governance_policy_yaml: `{governance_policy_yaml}`")
    lines.append("")
    lines.append("## Policy Baseline")
    lines.append(f"- cadence_days: `{policy_cad}`")
    lines.append(f"- window_days: `{policy_win}`")
    lines.append(f"- anchor_day_utc: `{anchor_day}`")
    lines.append("")
    lines.append("## Recommended Configs")
    lines.append(_table(top))
    lines.append("")
    lines.append("## Current Policy Config Rows")
    lines.append(_table(current))
    lines.append("")
    lines.append("## Alerts")
    lines.append(_table(alerts_df))
    lines.append("")
    lines.append("## Full Sensitivity Grid")
    lines.append(_table(sensitivity))
    report_out.write_text("\n".join(lines), encoding="utf-8")
    return sensitivity, alerts_df


def main() -> None:
    p = argparse.ArgumentParser(description="Build threshold/cadence sensitivity diagnostics")
    p.add_argument("--symbols", default="EURUSD,GBPUSD,USDJPY,USDCHF,AUDUSD,USDCAD")
    p.add_argument("--lookback-days", default="10,20,30,45")
    p.add_argument("--cadence-days", default="14,30,60")
    p.add_argument("--window-days", default="2,3,5")
    p.add_argument("--quantile", type=float, default=0.9)
    p.add_argument("--quantile-delta", type=float, default=0.02)
    p.add_argument("--min-history", type=int, default=1000)
    p.add_argument(
        "--governance-policy-yaml", default="configs/research/governance/oco_live_policy.yaml"
    )
    p.add_argument(
        "--out-sensitivity-csv",
        default="data/analysis/tick_opportunity_mining/oco_threshold_sensitivity.csv",
    )
    p.add_argument(
        "--out-alerts-csv",
        default="data/analysis/tick_opportunity_mining/oco_threshold_sensitivity_alerts.csv",
    )
    p.add_argument("--report-out", default="docs/analysis/oco_threshold_sensitivity_report.md")
    args = p.parse_args()

    sens, alerts = run(
        symbols=_parse_symbols(args.symbols),
        lookback_days=_parse_ints(args.lookback_days),
        cadence_days=_parse_ints(args.cadence_days),
        window_days=_parse_ints(args.window_days),
        quantile=float(args.quantile),
        quantile_delta=float(args.quantile_delta),
        min_history=int(args.min_history),
        governance_policy_yaml=Path(str(args.governance_policy_yaml)),
        symbol_paths=None,
        out_sensitivity_csv=Path(str(args.out_sensitivity_csv)),
        out_alerts_csv=Path(str(args.out_alerts_csv)),
        report_out=Path(str(args.report_out)),
    )
    print(f"wrote sensitivity: {args.out_sensitivity_csv} rows={len(sens)}")
    print(f"wrote alerts: {args.out_alerts_csv} rows={len(alerts)}")


if __name__ == "__main__":
    main()
