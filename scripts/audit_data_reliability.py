#!/usr/bin/env python3
"""Data reliability audit for OCO source bar tables."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

try:
    import pyarrow.parquet as pq
except Exception:
    pq = None  # type: ignore[assignment]


@dataclass(frozen=True)
class Thresholds:
    min_rows: int = 500_000
    min_close_ts_parse_rate: float = 0.999
    max_duplicate_close_ts_rate: float = 0.005
    min_numeric_parse_rate: float = 0.999
    max_core_null_rate: float = 0.010
    max_ohlc_violation_rate: float = 0.001
    max_nonneg_violation_rate: float = 0.001
    min_hour_valid_rate: float = 0.999
    min_finite_feature_rate: float = 0.999
    max_extreme_move_rate: float = 0.005
    min_trading_days: int = 220
    min_hours_covered: int = 20
    max_hour_concentration: float = 0.20


def _parse_symbols(raw: str) -> list[str]:
    out = [x.strip().upper() for x in str(raw).split(",") if x.strip()]
    return sorted(list(dict.fromkeys(out)))


def _to_num(s: pd.Series) -> pd.Series:
    return pd.to_numeric(s, errors="coerce").astype(float)


def _pip_size(symbol: str) -> float:
    s = str(symbol).upper().strip()
    if s.endswith("JPY"):
        return 0.01
    if s.startswith("XAU"):
        return 0.1
    if s.startswith("XAG"):
        return 0.01
    return 0.0001


def _latest(paths: list[Path]) -> Path | None:
    x = [p.resolve() for p in paths if p.exists()]
    if not x:
        return None
    x.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return x[0]


def _resolve_source_path(symbol: str, pattern: str) -> Path | None:
    pat = str(pattern).replace("{symbol}", str(symbol).upper())
    return _latest(list(Path.cwd().glob(pat)))


def _schema_columns(path: Path) -> set[str]:
    if pq is None:
        return set()
    try:
        return set(str(x) for x in pq.ParquetFile(path).schema.names)
    except Exception:
        return set()


def _safe_read_parquet(path: Path, cols: list[str]) -> pd.DataFrame:
    try:
        return pd.read_parquet(path, columns=cols)
    except Exception:
        return pd.read_parquet(path)


def _add_check(
    rows: list[dict[str, Any]],
    *,
    symbol: str,
    check_id: str,
    check_name: str,
    passed: bool,
    severity_if_fail: str,
    metric_name: str,
    metric_value: Any,
    threshold: Any,
    comparator: str,
    source_path: Path | None,
    details: str = "",
) -> None:
    rows.append(
        {
            "symbol": str(symbol).upper(),
            "check_id": str(check_id),
            "check_name": str(check_name),
            "status": "pass" if bool(passed) else "fail",
            "severity_if_fail": str(severity_if_fail).lower(),
            "component": "data_reliability",
            "metric_name": str(metric_name),
            "metric_value": metric_value,
            "threshold": threshold,
            "comparator": str(comparator),
            "details": str(details),
            "source_path": str(source_path) if source_path is not None else "",
            "evaluated_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
    )


def _robust_extreme_rate(x: np.ndarray) -> float:
    vals = np.asarray(x, dtype=float)
    vals = vals[np.isfinite(vals)]
    if len(vals) == 0:
        return float("nan")
    med = float(np.median(vals))
    mad = float(np.median(np.abs(vals - med)))
    if mad <= 1e-12:
        q99 = float(np.quantile(np.abs(vals - med), 0.99))
        if q99 <= 1e-12:
            return 0.0
        return float(np.mean(np.abs(vals - med) > (3.0 * q99)))
    rz = 0.6745 * (vals - med) / mad
    return float(np.mean(np.abs(rz) > 12.0))


def run(
    *,
    symbols: list[str],
    source_pattern: str,
    thresholds: Thresholds,
    out_checks_csv: Path,
    out_issues_csv: Path,
    out_report_md: Path,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    req_cols = [
        "close_ts",
        "open",
        "high",
        "low",
        "close",
        "cost_est_pips",
        "range_pips",
        "hour_utc",
        "spread_z",
        "tick_rate_z",
        "vel_cost_units_h1",
        "hl_first",
    ]
    opt_cols = ["ret1_pips"]
    checks_rows: list[dict[str, Any]] = []

    for symbol in symbols:
        src = _resolve_source_path(symbol, source_pattern)
        if src is None or not src.exists():
            _add_check(
                checks_rows,
                symbol=symbol,
                check_id="DR00",
                check_name="source_dataset_exists",
                passed=False,
                severity_if_fail="critical",
                metric_name="source_exists",
                metric_value=0,
                threshold=1,
                comparator="==",
                source_path=src,
                details=f"pattern={source_pattern}",
            )
            continue

        schema = _schema_columns(src)
        if schema:
            missing_req = [c for c in req_cols if c not in schema]
            read_cols = [c for c in (req_cols + opt_cols) if c in schema]
        else:
            missing_req = []
            read_cols = req_cols + opt_cols
        d = _safe_read_parquet(src, read_cols).copy()
        if not schema:
            missing_req = [c for c in req_cols if c not in d.columns]

        _add_check(
            checks_rows,
            symbol=symbol,
            check_id="DR01",
            check_name="required_columns_present",
            passed=len(missing_req) == 0,
            severity_if_fail="critical",
            metric_name="missing_required_columns",
            metric_value=int(len(missing_req)),
            threshold=0,
            comparator="==",
            source_path=src,
            details=",".join(missing_req),
        )

        rows_total = int(len(d))
        _add_check(
            checks_rows,
            symbol=symbol,
            check_id="DR02",
            check_name="minimum_rows",
            passed=rows_total >= int(thresholds.min_rows),
            severity_if_fail="high",
            metric_name="rows_total",
            metric_value=rows_total,
            threshold=int(thresholds.min_rows),
            comparator=">=",
            source_path=src,
        )
        if rows_total == 0:
            continue

        ts = (
            pd.to_datetime(d.get("close_ts"), utc=True, errors="coerce")
            if "close_ts" in d.columns
            else pd.Series(dtype="datetime64[ns, UTC]")
        )
        ts_parse_rate = float(ts.notna().mean()) if len(ts) else float("nan")
        ts_mono = bool(ts.dropna().is_monotonic_increasing) if len(ts) else False
        ts_dup_rate = (
            float(ts.dropna().duplicated().mean()) if len(ts.dropna()) > 0 else float("nan")
        )
        _add_check(
            checks_rows,
            symbol=symbol,
            check_id="DR03",
            check_name="close_ts_parse_rate",
            passed=np.isfinite(ts_parse_rate)
            and ts_parse_rate >= float(thresholds.min_close_ts_parse_rate),
            severity_if_fail="high",
            metric_name="close_ts_parse_rate",
            metric_value=ts_parse_rate,
            threshold=float(thresholds.min_close_ts_parse_rate),
            comparator=">=",
            source_path=src,
        )
        _add_check(
            checks_rows,
            symbol=symbol,
            check_id="DR04",
            check_name="close_ts_monotonic",
            passed=bool(ts_mono),
            severity_if_fail="critical",
            metric_name="close_ts_monotonic",
            metric_value=int(ts_mono),
            threshold=1,
            comparator="==",
            source_path=src,
        )
        _add_check(
            checks_rows,
            symbol=symbol,
            check_id="DR05",
            check_name="duplicate_close_ts_rate",
            passed=np.isfinite(ts_dup_rate)
            and ts_dup_rate <= float(thresholds.max_duplicate_close_ts_rate),
            severity_if_fail="high",
            metric_name="duplicate_close_ts_rate",
            metric_value=ts_dup_rate,
            threshold=float(thresholds.max_duplicate_close_ts_rate),
            comparator="<=",
            source_path=src,
        )

        core_num = [
            c
            for c in [
                "open",
                "high",
                "low",
                "close",
                "cost_est_pips",
                "range_pips",
                "hour_utc",
                "spread_z",
                "tick_rate_z",
                "vel_cost_units_h1",
                "hl_first",
            ]
            if c in d.columns
        ]
        parse_rates: list[float] = []
        null_rates: list[float] = []
        cnum: dict[str, pd.Series] = {}
        for col in core_num:
            x = _to_num(d[col])
            cnum[col] = x
            parse_rates.append(float(x.notna().mean()))
            null_rates.append(float(x.isna().mean()))

        min_parse_rate = float(np.min(parse_rates)) if parse_rates else float("nan")
        max_null_rate = float(np.max(null_rates)) if null_rates else float("nan")
        _add_check(
            checks_rows,
            symbol=symbol,
            check_id="DR06",
            check_name="numeric_parse_rate_min",
            passed=np.isfinite(min_parse_rate)
            and min_parse_rate >= float(thresholds.min_numeric_parse_rate),
            severity_if_fail="high",
            metric_name="numeric_parse_rate_min",
            metric_value=min_parse_rate,
            threshold=float(thresholds.min_numeric_parse_rate),
            comparator=">=",
            source_path=src,
        )
        _add_check(
            checks_rows,
            symbol=symbol,
            check_id="DR07",
            check_name="core_null_rate_max",
            passed=np.isfinite(max_null_rate)
            and max_null_rate <= float(thresholds.max_core_null_rate),
            severity_if_fail="high",
            metric_name="core_null_rate_max",
            metric_value=max_null_rate,
            threshold=float(thresholds.max_core_null_rate),
            comparator="<=",
            source_path=src,
        )

        o = cnum.get("open")
        h = cnum.get("high")
        l = cnum.get("low")
        c = cnum.get("close")
        ohlc_violation_rate = float("nan")
        if o is not None and h is not None and l is not None and c is not None:
            good = o.notna() & h.notna() & l.notna() & c.notna()
            if int(good.sum()) > 0:
                bad = (
                    (h[good] < l[good])
                    | (h[good] < o[good])
                    | (h[good] < c[good])
                    | (l[good] > o[good])
                    | (l[good] > c[good])
                )
                ohlc_violation_rate = float(np.mean(bad.to_numpy(dtype=bool)))
        _add_check(
            checks_rows,
            symbol=symbol,
            check_id="DR08",
            check_name="ohlc_consistency",
            passed=np.isfinite(ohlc_violation_rate)
            and ohlc_violation_rate <= float(thresholds.max_ohlc_violation_rate),
            severity_if_fail="critical",
            metric_name="ohlc_violation_rate",
            metric_value=ohlc_violation_rate,
            threshold=float(thresholds.max_ohlc_violation_rate),
            comparator="<=",
            source_path=src,
        )

        nonneg_violation_rate = float("nan")
        if "cost_est_pips" in cnum and "range_pips" in cnum:
            cc = cnum["cost_est_pips"]
            rr = cnum["range_pips"]
            good = cc.notna() & rr.notna()
            if int(good.sum()) > 0:
                bad = (cc[good] < 0.0) | (rr[good] < 0.0)
                nonneg_violation_rate = float(np.mean(bad.to_numpy(dtype=bool)))
        _add_check(
            checks_rows,
            symbol=symbol,
            check_id="DR09",
            check_name="cost_range_nonnegative",
            passed=np.isfinite(nonneg_violation_rate)
            and nonneg_violation_rate <= float(thresholds.max_nonneg_violation_rate),
            severity_if_fail="high",
            metric_name="nonnegative_violation_rate",
            metric_value=nonneg_violation_rate,
            threshold=float(thresholds.max_nonneg_violation_rate),
            comparator="<=",
            source_path=src,
        )

        hour_valid_rate = float("nan")
        if "hour_utc" in cnum:
            hh = cnum["hour_utc"]
            good = hh.notna()
            if int(good.sum()) > 0:
                ok = (hh[good] >= 0.0) & (hh[good] <= 23.0)
                hour_valid_rate = float(np.mean(ok.to_numpy(dtype=bool)))
        _add_check(
            checks_rows,
            symbol=symbol,
            check_id="DR10",
            check_name="hour_utc_valid_rate",
            passed=np.isfinite(hour_valid_rate)
            and hour_valid_rate >= float(thresholds.min_hour_valid_rate),
            severity_if_fail="medium",
            metric_name="hour_utc_valid_rate",
            metric_value=hour_valid_rate,
            threshold=float(thresholds.min_hour_valid_rate),
            comparator=">=",
            source_path=src,
        )

        finite_feature_rate = float("nan")
        ff_cols = [x for x in ["spread_z", "tick_rate_z", "vel_cost_units_h1"] if x in cnum]
        if ff_cols:
            ok_stack = np.column_stack(
                [np.isfinite(cnum[x].to_numpy(dtype=float)) for x in ff_cols]
            )
            finite_feature_rate = float(np.mean(ok_stack.all(axis=1)))
        _add_check(
            checks_rows,
            symbol=symbol,
            check_id="DR11",
            check_name="finite_feature_rate",
            passed=np.isfinite(finite_feature_rate)
            and finite_feature_rate >= float(thresholds.min_finite_feature_rate),
            severity_if_fail="medium",
            metric_name="finite_feature_rate",
            metric_value=finite_feature_rate,
            threshold=float(thresholds.min_finite_feature_rate),
            comparator=">=",
            source_path=src,
        )

        ret1 = _to_num(d["ret1_pips"]) if "ret1_pips" in d.columns else pd.Series(dtype=float)
        if ret1.empty and c is not None:
            pip = float(_pip_size(symbol))
            ret1 = ((c - c.shift(1)) / pip).fillna(0.0)
        extreme_rate = (
            _robust_extreme_rate(ret1.to_numpy(dtype=float)) if not ret1.empty else float("nan")
        )
        _add_check(
            checks_rows,
            symbol=symbol,
            check_id="DR12",
            check_name="extreme_move_rate",
            passed=np.isfinite(extreme_rate)
            and extreme_rate <= float(thresholds.max_extreme_move_rate),
            severity_if_fail="medium",
            metric_name="extreme_move_rate",
            metric_value=extreme_rate,
            threshold=float(thresholds.max_extreme_move_rate),
            comparator="<=",
            source_path=src,
        )

        trading_days = float("nan")
        hours_covered = float("nan")
        hour_concentration = float("nan")
        if len(ts.dropna()) > 0:
            ts_clean = ts.dropna()
            weekday = ts_clean[ts_clean.dt.weekday < 5]
            trading_days = float(weekday.dt.floor("D").nunique())
            hvc = ts_clean.dt.hour.value_counts(dropna=True)
            if len(hvc) > 0:
                hours_covered = float(len(hvc))
                hour_concentration = float(hvc.max() / hvc.sum())
        _add_check(
            checks_rows,
            symbol=symbol,
            check_id="DR13",
            check_name="trading_day_coverage",
            passed=np.isfinite(trading_days) and trading_days >= float(thresholds.min_trading_days),
            severity_if_fail="high",
            metric_name="trading_days",
            metric_value=trading_days,
            threshold=float(thresholds.min_trading_days),
            comparator=">=",
            source_path=src,
        )
        _add_check(
            checks_rows,
            symbol=symbol,
            check_id="DR14",
            check_name="hour_coverage",
            passed=np.isfinite(hours_covered)
            and hours_covered >= float(thresholds.min_hours_covered),
            severity_if_fail="medium",
            metric_name="hours_covered",
            metric_value=hours_covered,
            threshold=float(thresholds.min_hours_covered),
            comparator=">=",
            source_path=src,
        )
        _add_check(
            checks_rows,
            symbol=symbol,
            check_id="DR15",
            check_name="hour_concentration",
            passed=np.isfinite(hour_concentration)
            and hour_concentration <= float(thresholds.max_hour_concentration),
            severity_if_fail="medium",
            metric_name="max_hour_share",
            metric_value=hour_concentration,
            threshold=float(thresholds.max_hour_concentration),
            comparator="<=",
            source_path=src,
        )

    checks = pd.DataFrame(checks_rows)
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
                "details",
                "source_path",
                "evaluated_at_utc",
            ]
        )

    fail = checks[checks["status"].astype(str).str.lower() != "pass"].copy()
    issues = fail.copy()
    if not issues.empty:
        sev_rank = {"critical": 4, "high": 3, "medium": 2, "low": 1}
        issues["severity_rank"] = (
            issues["severity_if_fail"].astype(str).str.lower().map(sev_rank).fillna(0)
        )
        issues["issue_id"] = issues["symbol"].astype(str) + "_" + issues["check_id"].astype(str)
        issues["severity"] = issues["severity_if_fail"]
        issues["summary"] = issues["check_name"].astype(str) + " failed"
        issues = issues.sort_values(
            ["symbol", "severity_rank", "check_id"], ascending=[True, False, True]
        ).reset_index(drop=True)
        issues = issues[
            [
                "issue_id",
                "symbol",
                "check_id",
                "severity",
                "summary",
                "metric_name",
                "metric_value",
                "threshold",
                "comparator",
                "details",
                "source_path",
                "evaluated_at_utc",
            ]
        ]

    out_checks_csv.parent.mkdir(parents=True, exist_ok=True)
    checks.to_csv(out_checks_csv, index=False)
    out_issues_csv.parent.mkdir(parents=True, exist_ok=True)
    issues.to_csv(out_issues_csv, index=False)

    sym_summary = (
        checks.groupby("symbol", as_index=False)
        .agg(
            checks_total=("check_id", "count"),
            checks_failed=("status", lambda s: int((s.astype(str).str.lower() != "pass").sum())),
            high_or_critical_failed=(
                "severity_if_fail",
                lambda s: int(
                    (
                        (checks.loc[s.index, "status"].astype(str).str.lower() != "pass")
                        & s.astype(str).str.lower().isin(["high", "critical"])
                    ).sum()
                ),
            ),
        )
        .sort_values("symbol")
        if not checks.empty
        else pd.DataFrame()
    )

    lines: list[str] = []
    lines.append("# Data Reliability Audit")
    lines.append("")
    lines.append(
        f"- generated_at_utc: `{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}`"
    )
    lines.append(f"- symbols: `{','.join(symbols)}`")
    lines.append(f"- source_pattern: `{source_pattern}`")
    lines.append("")
    lines.append("## Symbol Summary")
    lines.append(sym_summary.to_markdown(index=False) if not sym_summary.empty else "_empty_")
    lines.append("")
    lines.append("## Failed Checks")
    lines.append(fail.to_markdown(index=False) if not fail.empty else "_none_")
    lines.append("")
    lines.append("## Outputs")
    lines.append(f"- checks_csv: `{out_checks_csv}`")
    lines.append(f"- issues_csv: `{out_issues_csv}`")
    out_report_md.parent.mkdir(parents=True, exist_ok=True)
    out_report_md.write_text("\n".join(lines), encoding="utf-8")

    return checks, issues


def main() -> None:
    p = argparse.ArgumentParser(description="Data reliability audit for OCO source datasets")
    p.add_argument("--symbols", default="EURUSD,GBPUSD,USDJPY,USDCHF,AUDUSD,USDCAD")
    p.add_argument(
        "--source-pattern",
        default="data/analysis/tick_velocity/{symbol}_100tick_velocity.parquet",
    )
    p.add_argument("--min-rows", type=int, default=500_000)
    p.add_argument(
        "--out-checks-csv",
        default="data/analysis/tick_opportunity_mining/data_reliability_checks.csv",
    )
    p.add_argument(
        "--out-issues-csv",
        default="data/analysis/tick_opportunity_mining/data_reliability_issues.csv",
    )
    p.add_argument("--report-out", default="docs/analysis/data_reliability_report.md")
    args = p.parse_args()

    checks, issues = run(
        symbols=_parse_symbols(args.symbols),
        source_pattern=str(args.source_pattern),
        thresholds=Thresholds(min_rows=int(args.min_rows)),
        out_checks_csv=Path(str(args.out_checks_csv)),
        out_issues_csv=Path(str(args.out_issues_csv)),
        out_report_md=Path(str(args.report_out)),
    )
    fail_mask = checks["status"].astype(str).str.lower() != "pass"
    high_crit_fail = fail_mask & checks["severity_if_fail"].astype(str).str.lower().isin(
        ["high", "critical"]
    )
    print(f"wrote checks: {args.out_checks_csv} rows={len(checks)}")
    print(f"wrote issues: {args.out_issues_csv} rows={len(issues)}")
    print(f"high_or_critical_failures={int(high_crit_fail.sum())}")


if __name__ == "__main__":
    main()
