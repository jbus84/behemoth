#!/usr/bin/env python3
"""Build monthly execution drift diagnostics for OCO stop-limit fills."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


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


def _to_num(s: pd.Series) -> pd.Series:
    return pd.to_numeric(s, errors="coerce")


def _dt_utc(s: pd.Series) -> pd.Series:
    try:
        return pd.to_datetime(s, utc=True, errors="coerce", format="mixed")
    except TypeError:
        return pd.to_datetime(s, utc=True, errors="coerce")


def _band(delta: float, *, warn: float, fail: float) -> tuple[str, str]:
    if not np.isfinite(delta):
        return "gray", "high"
    if delta >= float(fail):
        return "red", "high"
    if delta >= float(warn):
        return "amber", "medium"
    return "green", "info"


def _load_cap_pips(caps_csv: Path, *, default_cap: float) -> float:
    if not caps_csv.exists():
        return float(default_cap)
    d = pd.read_csv(caps_csv)
    if d.empty or "cap_pips" not in d.columns:
        return float(default_cap)
    x = _to_num(d["cap_pips"]).dropna().to_numpy(dtype=float)
    if len(x) == 0:
        return float(default_cap)
    return float(x[np.argmin(np.abs(x - float(default_cap)))])


def _summarize_symbol(
    *,
    symbol: str,
    detail_csv: Path,
    caps_csv: Path,
    production_cap_pips: float,
    baseline_months: int,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    if not detail_csv.exists():
        return pd.DataFrame(), pd.DataFrame(
            [{"symbol": symbol, "issue": "missing_detail_csv", "source_path": str(detail_csv)}]
        )

    try:
        d = pd.read_csv(detail_csv).copy()
    except pd.errors.EmptyDataError:
        # Empty CSV from no-trade condition
        return pd.DataFrame(), pd.DataFrame()
    required = {"close_ts", "touch_found_tick", "overshoot_tick_pips"}
    if not required.issubset(set(d.columns)):
        return pd.DataFrame(), pd.DataFrame(
            [
                {
                    "symbol": symbol,
                    "issue": "missing_required_columns",
                    "columns": ",".join(sorted(list(required - set(d.columns)))),
                    "source_path": str(detail_csv),
                }
            ]
        )
    d["close_ts"] = _dt_utc(d["close_ts"])
    d["touch_found_tick"] = _to_num(d["touch_found_tick"]).fillna(0).astype(int)
    d["overshoot_tick_pips"] = _to_num(d["overshoot_tick_pips"])
    d = d[d["close_ts"].notna()].copy()
    if d.empty:
        return pd.DataFrame(), pd.DataFrame(
            [{"symbol": symbol, "issue": "empty_after_parse", "source_path": str(detail_csv)}]
        )

    cap = _load_cap_pips(caps_csv, default_cap=float(production_cap_pips))
    d["test_month"] = d["close_ts"].dt.strftime("%Y-%m")
    d["touch"] = d["touch_found_tick"] == 1
    d["filled"] = (
        d["touch"] & d["overshoot_tick_pips"].notna() & (d["overshoot_tick_pips"] <= float(cap))
    )
    d["no_touch"] = ~d["touch"]

    def _p50(x: pd.Series) -> float:
        v = _to_num(x).dropna().to_numpy(dtype=float)
        return float(np.quantile(v, 0.50)) if len(v) else float("nan")

    def _p95(x: pd.Series) -> float:
        v = _to_num(x).dropna().to_numpy(dtype=float)
        return float(np.quantile(v, 0.95)) if len(v) else float("nan")

    m = d.groupby("test_month", as_index=False).agg(
        rows_total=("touch_found_tick", "count"),
        touched_rows=("touch", "sum"),
        filled_rows=("filled", "sum"),
        no_touch_rows=("no_touch", "sum"),
    )
    over = (
        d[d["touch"] & d["overshoot_tick_pips"].notna()]
        .groupby("test_month", as_index=False)
        .agg(
            overshoot_mean_pips=("overshoot_tick_pips", "mean"),
            overshoot_p50_pips=("overshoot_tick_pips", _p50),
            overshoot_p95_pips=("overshoot_tick_pips", _p95),
        )
    )
    m = m.merge(over, on="test_month", how="left")
    m["symbol"] = str(symbol).upper()
    m["cap_pips"] = float(cap)
    m["fill_rate"] = _to_num(m["filled_rows"]) / _to_num(m["rows_total"]).replace(0, np.nan)
    m["no_touch_rate"] = _to_num(m["no_touch_rows"]) / _to_num(m["rows_total"]).replace(0, np.nan)
    m = m.sort_values("test_month").reset_index(drop=True)

    base = m.head(int(max(1, baseline_months))).copy()
    base_fill = float(_to_num(base["fill_rate"]).mean())
    base_no_touch = float(_to_num(base["no_touch_rate"]).mean())
    base_p50 = float(_to_num(base["overshoot_p50_pips"]).mean())
    base_p95 = float(_to_num(base["overshoot_p95_pips"]).mean())

    m["baseline_months"] = int(max(1, baseline_months))
    m["baseline_fill_rate"] = base_fill
    m["baseline_no_touch_rate"] = base_no_touch
    m["baseline_overshoot_p50_pips"] = base_p50
    m["baseline_overshoot_p95_pips"] = base_p95
    m["delta_fill_rate_drop"] = m["baseline_fill_rate"] - m["fill_rate"]
    m["delta_no_touch_rate"] = m["no_touch_rate"] - m["baseline_no_touch_rate"]
    m["delta_overshoot_p50_pips"] = m["overshoot_p50_pips"] - m["baseline_overshoot_p50_pips"]
    m["delta_overshoot_p95_pips"] = m["overshoot_p95_pips"] - m["baseline_overshoot_p95_pips"]
    return m, pd.DataFrame()


def run(
    *,
    symbols: list[str],
    detail_dir: Path,
    default_cap_pips: float,
    baseline_months: int,
    warn_fill_drop: float,
    fail_fill_drop: float,
    warn_no_touch: float,
    fail_no_touch: float,
    warn_overshoot_p50: float,
    fail_overshoot_p50: float,
    warn_overshoot_p95: float,
    fail_overshoot_p95: float,
    out_monthly_csv: Path,
    out_alerts_csv: Path,
    report_out: Path,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    monthly_parts: list[pd.DataFrame] = []
    errors: list[pd.DataFrame] = []
    for symbol in symbols:
        detail = detail_dir / f"{symbol}_stop_limit_tickfill_detail.csv"
        caps = detail_dir / f"{symbol}_stop_limit_tickfill_caps.csv"
        m, e = _summarize_symbol(
            symbol=symbol,
            detail_csv=detail,
            caps_csv=caps,
            production_cap_pips=float(default_cap_pips),
            baseline_months=int(baseline_months),
        )
        if not m.empty:
            monthly_parts.append(m)
        if not e.empty:
            errors.append(e)

    monthly = pd.concat(monthly_parts, ignore_index=True) if monthly_parts else pd.DataFrame()
    err = pd.concat(errors, ignore_index=True) if errors else pd.DataFrame()

    alert_rows: list[dict[str, Any]] = []
    for _, r in monthly.iterrows():
        for metric_id, delta, warn, fail in [
            (
                "E_DRIFT_FILL_DROP",
                float(r.get("delta_fill_rate_drop", np.nan)),
                float(warn_fill_drop),
                float(fail_fill_drop),
            ),
            (
                "E_DRIFT_NO_TOUCH",
                float(r.get("delta_no_touch_rate", np.nan)),
                float(warn_no_touch),
                float(fail_no_touch),
            ),
            (
                "E_DRIFT_OVERSHOOT_P50",
                float(r.get("delta_overshoot_p50_pips", np.nan)),
                float(warn_overshoot_p50),
                float(fail_overshoot_p50),
            ),
            (
                "E_DRIFT_OVERSHOOT_P95",
                float(r.get("delta_overshoot_p95_pips", np.nan)),
                float(warn_overshoot_p95),
                float(fail_overshoot_p95),
            ),
        ]:
            band, sev = _band(delta, warn=warn, fail=fail)
            alert_rows.append(
                {
                    "symbol": str(r["symbol"]).upper(),
                    "test_month": str(r["test_month"]),
                    "metric_id": metric_id,
                    "metric_value": float(delta) if np.isfinite(delta) else np.nan,
                    "warn_threshold": float(warn),
                    "fail_threshold": float(fail),
                    "band": band,
                    "severity": sev,
                    "source_path": str(
                        detail_dir / f"{str(r['symbol']).upper()}_stop_limit_tickfill_detail.csv"
                    ),
                    "details_json": json.dumps(
                        {"baseline_months": int(r.get("baseline_months", baseline_months))},
                        sort_keys=True,
                    ),
                    "evaluated_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                }
            )
    alerts = pd.DataFrame(alert_rows)

    out_monthly_csv.parent.mkdir(parents=True, exist_ok=True)
    out_alerts_csv.parent.mkdir(parents=True, exist_ok=True)
    report_out.parent.mkdir(parents=True, exist_ok=True)
    monthly.to_csv(out_monthly_csv, index=False)
    alerts.to_csv(out_alerts_csv, index=False)

    sev_counts = (
        alerts.groupby(["symbol", "band"], as_index=False)
        .agg(rows=("metric_id", "count"))
        .sort_values(["symbol", "band"])
        if not alerts.empty
        else pd.DataFrame(columns=["symbol", "band", "rows"])
    )
    latest = (
        monthly.sort_values(["symbol", "test_month"])
        .groupby("symbol", as_index=False)
        .tail(1)
        .sort_values("symbol")
        if not monthly.empty
        else pd.DataFrame()
    )

    lines: list[str] = []
    lines.append("# OCO Execution Drift Report")
    lines.append("")
    lines.append(
        f"- generated_at_utc: `{datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}`"
    )
    lines.append(f"- monthly_csv: `{out_monthly_csv}`")
    lines.append(f"- alerts_csv: `{out_alerts_csv}`")
    lines.append("")
    lines.append("## Alert Band Counts")
    lines.append(_table(sev_counts))
    lines.append("")
    lines.append("## Latest Month Snapshot")
    lines.append(
        _table(
            latest[
                [
                    "symbol",
                    "test_month",
                    "rows_total",
                    "fill_rate",
                    "no_touch_rate",
                    "overshoot_p50_pips",
                    "overshoot_p95_pips",
                    "delta_fill_rate_drop",
                    "delta_no_touch_rate",
                    "delta_overshoot_p50_pips",
                    "delta_overshoot_p95_pips",
                ]
            ]
            if not latest.empty
            else pd.DataFrame()
        )
    )
    lines.append("")
    lines.append("## Error Rows")
    lines.append(_table(err))
    lines.append("")
    lines.append("## Full Alerts")
    lines.append(_table(alerts))
    lines.append("")
    lines.append("## Full Monthly Table")
    lines.append(_table(monthly))
    report_out.write_text("\n".join(lines), encoding="utf-8")
    return monthly, alerts


def main() -> None:
    p = argparse.ArgumentParser(description="Build monthly stop-limit execution drift report")
    p.add_argument("--symbols", default="EURUSD,GBPUSD,USDJPY,USDCHF,AUDUSD,USDCAD")
    p.add_argument(
        "--detail-dir", default="data/analysis/tick_opportunity_mining/stop_limit_tickfill_fullcap"
    )
    p.add_argument("--default-cap-pips", type=float, default=1.2)
    p.add_argument("--baseline-months", type=int, default=3)
    p.add_argument("--warn-fill-drop", type=float, default=0.02)
    p.add_argument("--fail-fill-drop", type=float, default=0.04)
    p.add_argument("--warn-no-touch", type=float, default=0.01)
    p.add_argument("--fail-no-touch", type=float, default=0.02)
    p.add_argument("--warn-overshoot-p50", type=float, default=0.05)
    p.add_argument("--fail-overshoot-p50", type=float, default=0.10)
    p.add_argument("--warn-overshoot-p95", type=float, default=0.15)
    p.add_argument("--fail-overshoot-p95", type=float, default=0.30)
    p.add_argument(
        "--out-monthly-csv",
        default="data/analysis/tick_opportunity_mining/oco_execution_drift_monthly.csv",
    )
    p.add_argument(
        "--out-alerts-csv",
        default="data/analysis/tick_opportunity_mining/oco_execution_drift_alerts.csv",
    )
    p.add_argument("--report-out", default="docs/analysis/oco_execution_drift_report.md")
    args = p.parse_args()

    monthly, alerts = run(
        symbols=_parse_symbols(args.symbols),
        detail_dir=Path(str(args.detail_dir)),
        default_cap_pips=float(args.default_cap_pips),
        baseline_months=int(args.baseline_months),
        warn_fill_drop=float(args.warn_fill_drop),
        fail_fill_drop=float(args.fail_fill_drop),
        warn_no_touch=float(args.warn_no_touch),
        fail_no_touch=float(args.fail_no_touch),
        warn_overshoot_p50=float(args.warn_overshoot_p50),
        fail_overshoot_p50=float(args.fail_overshoot_p50),
        warn_overshoot_p95=float(args.warn_overshoot_p95),
        fail_overshoot_p95=float(args.fail_overshoot_p95),
        out_monthly_csv=Path(str(args.out_monthly_csv)),
        out_alerts_csv=Path(str(args.out_alerts_csv)),
        report_out=Path(str(args.report_out)),
    )
    print(f"wrote monthly: {args.out_monthly_csv} rows={len(monthly)}")
    print(f"wrote alerts: {args.out_alerts_csv} rows={len(alerts)}")


if __name__ == "__main__":
    main()
