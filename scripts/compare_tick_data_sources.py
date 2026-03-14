#!/usr/bin/env python3
"""Compare canonical parquet tick sources against a reference feed."""

from __future__ import annotations

import argparse
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
    return sorted(list(dict.fromkeys([s.strip().upper() for s in str(raw).split(",") if s.strip()])))


def _parse_months(raw: str) -> list[str]:
    out = [m.strip() for m in str(raw).split(",") if m.strip()]
    bad = [m for m in out if len(m) != 6 or not m.isdigit()]
    if bad:
        raise ValueError(f"bad months: {bad!r}")
    return out


def _dt_utc(s: pd.Series) -> pd.Series:
    try:
        return pd.to_datetime(s, utc=True, errors="coerce", format="mixed")
    except TypeError:
        return pd.to_datetime(s, utc=True, errors="coerce")


def _pip_size(symbol: str) -> float:
    return 0.01 if str(symbol).upper().endswith("JPY") else 0.0001


def _load_ticks(path: Path) -> pd.DataFrame:
    df = pd.read_parquet(path)
    required = {"timestamp", "bid", "ask", "mid", "spread", "log_return"}
    missing = sorted(required - set(df.columns))
    if missing:
        raise ValueError(f"{path} missing required columns: {missing}")
    out = df.loc[:, ["timestamp", "bid", "ask", "mid", "spread", "log_return"]].copy()
    out["timestamp"] = _dt_utc(out["timestamp"])
    for col in ["bid", "ask", "mid", "spread", "log_return"]:
        out[col] = pd.to_numeric(out[col], errors="coerce")
    out = out.dropna(subset=["timestamp", "bid", "ask", "mid", "spread"]).sort_values("timestamp")
    out = out.reset_index(drop=True)
    return out


def trim_to_overlap(reference: pd.DataFrame, candidate: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    if reference.empty or candidate.empty:
        return reference.iloc[0:0].copy(), candidate.iloc[0:0].copy()
    start = max(reference["timestamp"].min(), candidate["timestamp"].min())
    end = min(reference["timestamp"].max(), candidate["timestamp"].max())
    if pd.isna(start) or pd.isna(end) or not (start <= end):
        return reference.iloc[0:0].copy(), candidate.iloc[0:0].copy()
    ref_trim = reference[(reference["timestamp"] >= start) & (reference["timestamp"] <= end)].copy()
    cand_trim = candidate[(candidate["timestamp"] >= start) & (candidate["timestamp"] <= end)].copy()
    return ref_trim.reset_index(drop=True), cand_trim.reset_index(drop=True)


def _quantile(series: pd.Series, q: float) -> float:
    vals = pd.to_numeric(series, errors="coerce").dropna().to_numpy(dtype=float)
    if len(vals) == 0:
        return float("nan")
    return float(np.quantile(vals, q))


def _series_stats(series: pd.Series, prefix: str) -> dict[str, Any]:
    vals = pd.to_numeric(series, errors="coerce").dropna()
    if vals.empty:
        return {
            f"{prefix}_mean": float("nan"),
            f"{prefix}_std": float("nan"),
            f"{prefix}_min": float("nan"),
            f"{prefix}_max": float("nan"),
            f"{prefix}_p01": float("nan"),
            f"{prefix}_p05": float("nan"),
            f"{prefix}_p50": float("nan"),
            f"{prefix}_p95": float("nan"),
            f"{prefix}_p99": float("nan"),
        }
    return {
        f"{prefix}_mean": float(vals.mean()),
        f"{prefix}_std": float(vals.std(ddof=0)),
        f"{prefix}_min": float(vals.min()),
        f"{prefix}_max": float(vals.max()),
        f"{prefix}_p01": _quantile(vals, 0.01),
        f"{prefix}_p05": _quantile(vals, 0.05),
        f"{prefix}_p50": _quantile(vals, 0.50),
        f"{prefix}_p95": _quantile(vals, 0.95),
        f"{prefix}_p99": _quantile(vals, 0.99),
    }


def _intertick_stats(df: pd.DataFrame, prefix: str) -> dict[str, Any]:
    if len(df) < 2:
        return {
            f"{prefix}_intertick_ms_mean": float("nan"),
            f"{prefix}_intertick_ms_p50": float("nan"),
            f"{prefix}_intertick_ms_p90": float("nan"),
            f"{prefix}_intertick_ms_p99": float("nan"),
        }
    diffs = (
        df["timestamp"].sort_values().diff().dropna().dt.total_seconds().astype(float).to_numpy() * 1000.0
    )
    return {
        f"{prefix}_intertick_ms_mean": float(np.mean(diffs)),
        f"{prefix}_intertick_ms_p50": float(np.quantile(diffs, 0.50)),
        f"{prefix}_intertick_ms_p90": float(np.quantile(diffs, 0.90)),
        f"{prefix}_intertick_ms_p99": float(np.quantile(diffs, 0.99)),
    }


def _duplicate_ratio(df: pd.DataFrame) -> float:
    if df.empty:
        return float("nan")
    return float(df["timestamp"].duplicated().mean())


def _covered_days(df: pd.DataFrame) -> int:
    if df.empty:
        return 0
    return int(df["timestamp"].dt.floor("D").nunique())


def _source_stats(df: pd.DataFrame, prefix: str) -> dict[str, Any]:
    row: dict[str, Any] = {
        f"{prefix}_rows": int(len(df)),
        f"{prefix}_first_ts": df["timestamp"].min().isoformat() if not df.empty else "",
        f"{prefix}_last_ts": df["timestamp"].max().isoformat() if not df.empty else "",
        f"{prefix}_covered_days": _covered_days(df),
        f"{prefix}_duplicate_ts_ratio": _duplicate_ratio(df),
        f"{prefix}_nonpositive_spread_ratio": float((df["spread"] <= 0).mean()) if not df.empty else float("nan"),
    }
    for field in ["bid", "ask", "mid", "spread"]:
        row.update(_series_stats(df[field], f"{prefix}_{field}"))
    row.update(_intertick_stats(df, prefix))
    return row


def _minute_frame(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(columns=["minute", "mid", "spread"])
    out = (
        df.set_index("timestamp")[["mid", "spread"]]
        .sort_index()
        .resample("1min")
        .last()
        .dropna(subset=["mid"])
        .reset_index()
        .rename(columns={"timestamp": "minute"})
    )
    return out


def infer_daily_lag_schedule(
    reference: pd.DataFrame,
    candidate: pd.DataFrame,
    *,
    max_lag_hours: int,
    min_overlap_minutes: int = 180,
    min_correlation: float = 0.80,
) -> pd.DataFrame:
    ref_minute = _minute_frame(reference).set_index("minute")
    cand_minute = _minute_frame(candidate).set_index("minute")
    if ref_minute.empty or cand_minute.empty:
        return pd.DataFrame(
            columns=[
                "date_utc",
                "inferred_lag_hours",
                "best_corr",
                "overlap_minutes",
                "lag_source",
            ]
        )

    ref_return = ref_minute["mid"].diff()
    cand_return = cand_minute["mid"].diff()
    days = pd.date_range(
        start=ref_minute.index.min().floor("D"),
        end=ref_minute.index.max().floor("D"),
        freq="D",
        tz="UTC",
    )
    shifted: dict[int, pd.Series] = {}
    for lag in range(-int(max_lag_hours), int(max_lag_hours) + 1):
        series = cand_return.copy()
        series.index = series.index + pd.Timedelta(hours=lag)
        shifted[lag] = series

    rows: list[dict[str, Any]] = []
    last_valid: int | None = None
    for day in days:
        nxt = day + pd.Timedelta(days=1)
        ref_day = ref_return.loc[(ref_return.index >= day) & (ref_return.index < nxt)]
        best_lag: int | None = None
        best_corr = float("nan")
        best_count = 0
        for lag, shifted_series in shifted.items():
            cand_day = shifted_series.loc[(shifted_series.index >= day) & (shifted_series.index < nxt)]
            merged = (
                ref_day.rename("ref")
                .to_frame()
                .join(cand_day.rename("cand").to_frame(), how="inner")
                .dropna()
            )
            if len(merged) < int(min_overlap_minutes):
                continue
            corr = float(merged["ref"].corr(merged["cand"]))
            if not np.isfinite(corr) or corr < float(min_correlation):
                continue
            if best_lag is None or corr > best_corr:
                best_lag = int(lag)
                best_corr = corr
                best_count = int(len(merged))
        if best_lag is not None:
            last_valid = int(best_lag)
            rows.append(
                {
                    "date_utc": day.isoformat(),
                    "inferred_lag_hours": int(best_lag),
                    "best_corr": float(best_corr),
                    "overlap_minutes": int(best_count),
                    "lag_source": "inferred",
                }
            )
            continue
        if last_valid is not None:
            rows.append(
                {
                    "date_utc": day.isoformat(),
                    "inferred_lag_hours": int(last_valid),
                    "best_corr": float("nan"),
                    "overlap_minutes": 0,
                    "lag_source": "carry_forward",
                }
            )
        else:
            rows.append(
                {
                    "date_utc": day.isoformat(),
                    "inferred_lag_hours": float("nan"),
                    "best_corr": float("nan"),
                    "overlap_minutes": 0,
                    "lag_source": "unresolved",
                }
            )
    return pd.DataFrame(rows)


def _apply_daily_lag(candidate: pd.DataFrame, schedule: pd.DataFrame) -> pd.DataFrame:
    if candidate.empty:
        return candidate.copy()
    out = candidate.copy()
    if schedule.empty:
        out["lag_hours_applied"] = float("nan")
        return out
    lag_values = pd.Series(np.nan, index=out.index, dtype="float64")
    sched = schedule.copy()
    sched["date_ts"] = _dt_utc(sched["date_utc"])
    sched["lag_num"] = pd.to_numeric(sched["inferred_lag_hours"], errors="coerce")
    sched = sched[sched["date_ts"].notna() & sched["lag_num"].notna()].copy()
    if sched.empty:
        out["lag_hours_applied"] = float("nan")
        return out
    for _, row in sched.sort_values("date_ts").iterrows():
        lag = float(row["lag_num"])
        start_ref = pd.Timestamp(row["date_ts"])
        end_ref = start_ref + pd.Timedelta(days=1)
        start_orig = start_ref - pd.Timedelta(hours=lag)
        end_orig = end_ref - pd.Timedelta(hours=lag)
        mask = (
            out["timestamp"].ge(start_orig)
            & out["timestamp"].lt(end_orig)
            & lag_values.isna()
        )
        lag_values.loc[mask] = lag
    if lag_values.notna().any():
        lag_values = lag_values.ffill().bfill()
    out["lag_hours_applied"] = lag_values
    out["timestamp"] = out["timestamp"] + pd.to_timedelta(out["lag_hours_applied"].fillna(0.0), unit="h")
    return out


def _minute_similarity(reference: pd.DataFrame, candidate: pd.DataFrame, *, pip_size: float) -> tuple[dict[str, Any], pd.DataFrame]:
    ref_minute = _minute_frame(reference).rename(columns={"mid": "ref_mid", "spread": "ref_spread"})
    cand_minute = _minute_frame(candidate).rename(columns={"mid": "cand_mid", "spread": "cand_spread"})
    merged = ref_minute.merge(cand_minute, on="minute", how="inner")
    if merged.empty:
        return (
            {
                "overlap_minutes": 0,
                "minute_return_corr": float("nan"),
                "minute_return_mae_pips": float("nan"),
                "minute_return_rmse_pips": float("nan"),
                "minute_directional_agreement": float("nan"),
                "minute_mid_mae_pips": float("nan"),
                "minute_spread_mae_pips": float("nan"),
                "minute_spread_corr": float("nan"),
                "realized_vol_ratio_candidate_vs_reference": float("nan"),
                "hourly_coverage_ratio_mean": float("nan"),
                "hourly_coverage_ratio_p05": float("nan"),
            },
            merged,
        )

    merged["ref_return_pips"] = merged["ref_mid"].diff() / float(pip_size)
    merged["cand_return_pips"] = merged["cand_mid"].diff() / float(pip_size)
    valid_ret = merged.dropna(subset=["ref_return_pips", "cand_return_pips"]).copy()
    if valid_ret.empty:
        corr = float("nan")
        mae = float("nan")
        rmse = float("nan")
        sign_match = float("nan")
        vol_ratio = float("nan")
    else:
        diff = valid_ret["cand_return_pips"] - valid_ret["ref_return_pips"]
        corr = float(valid_ret["ref_return_pips"].corr(valid_ret["cand_return_pips"]))
        mae = float(np.mean(np.abs(diff)))
        rmse = float(np.sqrt(np.mean(np.square(diff))))
        sign_match = float(
            (
                np.sign(valid_ret["cand_return_pips"].to_numpy())
                == np.sign(valid_ret["ref_return_pips"].to_numpy())
            ).mean()
        )
        ref_vol = float(valid_ret["ref_return_pips"].std(ddof=0))
        cand_vol = float(valid_ret["cand_return_pips"].std(ddof=0))
        vol_ratio = float(cand_vol / ref_vol) if np.isfinite(ref_vol) and ref_vol > 0 else float("nan")

    mid_mae = float(np.mean(np.abs((merged["cand_mid"] - merged["ref_mid"]) / float(pip_size))))
    spread_mae = float(
        np.mean(np.abs((merged["cand_spread"] - merged["ref_spread"]) / float(pip_size)))
    )
    spread_corr = float(merged["ref_spread"].corr(merged["cand_spread"]))

    ref_hourly = (
        ref_minute.assign(hour_start_utc=ref_minute["minute"].dt.floor("h"))
        .groupby("hour_start_utc", as_index=False)
        .agg(reference_minutes=("ref_mid", "count"))
    )
    cand_hourly = (
        cand_minute.assign(hour_start_utc=cand_minute["minute"].dt.floor("h"))
        .groupby("hour_start_utc", as_index=False)
        .agg(candidate_minutes=("cand_mid", "count"))
    )
    hourly = (
        ref_hourly.merge(cand_hourly, on="hour_start_utc", how="outer")
        .sort_values("hour_start_utc")
        .reset_index(drop=True)
    )
    hourly["reference_minutes"] = pd.to_numeric(hourly["reference_minutes"], errors="coerce").fillna(0).astype(int)
    hourly["candidate_minutes"] = pd.to_numeric(hourly["candidate_minutes"], errors="coerce").fillna(0).astype(int)
    hourly["coverage_ratio_candidate_vs_reference"] = (
        hourly["candidate_minutes"] / hourly["reference_minutes"].replace(0, np.nan)
    )
    metrics = {
        "overlap_minutes": int(len(merged)),
        "minute_return_corr": corr,
        "minute_return_mae_pips": mae,
        "minute_return_rmse_pips": rmse,
        "minute_directional_agreement": sign_match,
        "minute_mid_mae_pips": mid_mae,
        "minute_spread_mae_pips": spread_mae,
        "minute_spread_corr": spread_corr,
        "realized_vol_ratio_candidate_vs_reference": vol_ratio,
        "hourly_coverage_ratio_mean": float(hourly["coverage_ratio_candidate_vs_reference"].mean())
        if not hourly.empty
        else float("nan"),
        "hourly_coverage_ratio_p05": _quantile(hourly["coverage_ratio_candidate_vs_reference"], 0.05)
        if not hourly.empty
        else float("nan"),
    }
    return metrics, hourly


def _build_tick_bars(df: pd.DataFrame, *, bar_ticks: int, pip_size: float) -> pd.DataFrame:
    if df.empty or len(df) < int(bar_ticks):
        return pd.DataFrame(columns=["bar_id", "bar_seconds", "bar_return_pips", "bar_spread_pips"])
    n = len(df) // int(bar_ticks)
    out = df.iloc[: n * int(bar_ticks)].copy()
    out["bar_id"] = np.repeat(np.arange(n), int(bar_ticks))
    bars = (
        out.groupby("bar_id", as_index=False)
        .agg(
            open_ts=("timestamp", "first"),
            close_ts=("timestamp", "last"),
            open_mid=("mid", "first"),
            close_mid=("mid", "last"),
            avg_spread=("spread", "mean"),
        )
        .sort_values("bar_id")
        .reset_index(drop=True)
    )
    bars["bar_seconds"] = (bars["close_ts"] - bars["open_ts"]).dt.total_seconds().astype(float)
    bars["bar_return_pips"] = (bars["close_mid"] - bars["open_mid"]) / float(pip_size)
    bars["bar_spread_pips"] = bars["avg_spread"] / float(pip_size)
    return bars.loc[:, ["bar_id", "bar_seconds", "bar_return_pips", "bar_spread_pips"]]


def _bar_summary(reference: pd.DataFrame, candidate: pd.DataFrame, *, bar_ticks: int, pip_size: float) -> dict[str, Any]:
    ref_bars = _build_tick_bars(reference, bar_ticks=bar_ticks, pip_size=pip_size)
    cand_bars = _build_tick_bars(candidate, bar_ticks=bar_ticks, pip_size=pip_size)
    row: dict[str, Any] = {
        "bar_ticks": int(bar_ticks),
        "reference_bar_count": int(len(ref_bars)),
        "candidate_bar_count": int(len(cand_bars)),
    }
    for name, bars in [("reference", ref_bars), ("candidate", cand_bars)]:
        if bars.empty:
            row.update(
                {
                    f"{name}_seconds_per_bar_mean": float("nan"),
                    f"{name}_seconds_per_bar_p50": float("nan"),
                    f"{name}_seconds_per_bar_p90": float("nan"),
                    f"{name}_seconds_per_bar_p99": float("nan"),
                    f"{name}_bar_return_abs_p50": float("nan"),
                    f"{name}_bar_return_abs_p95": float("nan"),
                    f"{name}_bar_spread_p50": float("nan"),
                    f"{name}_bar_spread_p95": float("nan"),
                }
            )
            continue
        row.update(
            {
                f"{name}_seconds_per_bar_mean": float(bars["bar_seconds"].mean()),
                f"{name}_seconds_per_bar_p50": _quantile(bars["bar_seconds"], 0.50),
                f"{name}_seconds_per_bar_p90": _quantile(bars["bar_seconds"], 0.90),
                f"{name}_seconds_per_bar_p99": _quantile(bars["bar_seconds"], 0.99),
                f"{name}_bar_return_abs_p50": _quantile(bars["bar_return_pips"].abs(), 0.50),
                f"{name}_bar_return_abs_p95": _quantile(bars["bar_return_pips"].abs(), 0.95),
                f"{name}_bar_spread_p50": _quantile(bars["bar_spread_pips"], 0.50),
                f"{name}_bar_spread_p95": _quantile(bars["bar_spread_pips"], 0.95),
            }
        )
    row["seconds_per_bar_mean_delta"] = (
        row["candidate_seconds_per_bar_mean"] - row["reference_seconds_per_bar_mean"]
        if np.isfinite(row["candidate_seconds_per_bar_mean"]) and np.isfinite(row["reference_seconds_per_bar_mean"])
        else float("nan")
    )
    row["bar_return_abs_p50_delta_pips"] = (
        row["candidate_bar_return_abs_p50"] - row["reference_bar_return_abs_p50"]
        if np.isfinite(row["candidate_bar_return_abs_p50"]) and np.isfinite(row["reference_bar_return_abs_p50"])
        else float("nan")
    )
    row["bar_return_abs_p95_delta_pips"] = (
        row["candidate_bar_return_abs_p95"] - row["reference_bar_return_abs_p95"]
        if np.isfinite(row["candidate_bar_return_abs_p95"]) and np.isfinite(row["reference_bar_return_abs_p95"])
        else float("nan")
    )
    row["bar_spread_p50_delta_pips"] = (
        row["candidate_bar_spread_p50"] - row["reference_bar_spread_p50"]
        if np.isfinite(row["candidate_bar_spread_p50"]) and np.isfinite(row["reference_bar_spread_p50"])
        else float("nan")
    )
    row["bar_spread_p95_delta_pips"] = (
        row["candidate_bar_spread_p95"] - row["reference_bar_spread_p95"]
        if np.isfinite(row["candidate_bar_spread_p95"]) and np.isfinite(row["reference_bar_spread_p95"])
        else float("nan")
    )
    return row


def _month_expected_end(month: str) -> pd.Timestamp:
    start = pd.Timestamp(f"{month[:4]}-{month[4:]}-01", tz="UTC")
    end = start + pd.offsets.MonthBegin(1)
    return end - pd.Timedelta(milliseconds=1)


def _is_materially_partial(df: pd.DataFrame, month: str) -> bool:
    if df.empty:
        return True
    month_end = _month_expected_end(month)
    return bool(df["timestamp"].max() < (month_end - pd.Timedelta(days=7)))


def analyze_symbol_month(
    *,
    symbol: str,
    month: str,
    reference_path: Path,
    candidate_path: Path,
    bar_ticks: int,
    max_lag_hours: int,
    min_overlap_minutes: int = 180,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    reference = _load_ticks(reference_path)
    candidate = _load_ticks(candidate_path)
    pip_size = _pip_size(symbol)

    base_meta = {
        "symbol": str(symbol).upper().strip(),
        "month": str(month),
        "reference_path": str(reference_path),
        "candidate_path": str(candidate_path),
        "reference_partial_month": _is_materially_partial(reference, month),
        "candidate_partial_month": _is_materially_partial(candidate, month),
    }

    lag_schedule = infer_daily_lag_schedule(
        reference,
        candidate,
        max_lag_hours=max_lag_hours,
        min_overlap_minutes=min_overlap_minutes,
    )
    lag_schedule = lag_schedule.copy()
    lag_schedule["symbol"] = str(symbol).upper().strip()
    lag_schedule["month"] = str(month)

    lens_frames = {
        "as_is": candidate.copy(),
        "lag_corrected": _apply_daily_lag(candidate, lag_schedule),
    }
    summary_rows: list[dict[str, Any]] = []
    coverage_parts: list[pd.DataFrame] = []

    for lens, candidate_lens in lens_frames.items():
        ref_trim, cand_trim = trim_to_overlap(reference, candidate_lens)
        row = dict(base_meta)
        row["lens"] = lens
        row["overlap_start_ts"] = ref_trim["timestamp"].min().isoformat() if not ref_trim.empty else ""
        row["overlap_end_ts"] = ref_trim["timestamp"].max().isoformat() if not ref_trim.empty else ""
        row["overlap_duration_hours"] = (
            float((ref_trim["timestamp"].max() - ref_trim["timestamp"].min()).total_seconds() / 3600.0)
            if len(ref_trim) >= 2
            else float("nan")
        )
        row["candidate_to_reference_row_ratio"] = (
            float(len(cand_trim) / len(ref_trim)) if len(ref_trim) else float("nan")
        )
        row.update(_source_stats(ref_trim, "reference"))
        row.update(_source_stats(cand_trim, "candidate"))
        minute_metrics, hourly = _minute_similarity(ref_trim, cand_trim, pip_size=pip_size)
        row.update(minute_metrics)
        row.update(_bar_summary(ref_trim, cand_trim, bar_ticks=bar_ticks, pip_size=pip_size))
        resolved = lag_schedule[lag_schedule["lag_source"].astype(str) != "unresolved"].copy()
        row["lag_schedule_unresolved_days"] = int(
            (lag_schedule["lag_source"].astype(str) == "unresolved").sum()
        )
        row["lag_schedule_day_count"] = int(len(lag_schedule))
        row["lag_schedule_mode_hours"] = (
            float(resolved["inferred_lag_hours"].mode().iloc[0]) if not resolved.empty else float("nan")
        )
        summary_rows.append(row)

        if not hourly.empty:
            hourly = hourly.copy()
            hourly["symbol"] = str(symbol).upper().strip()
            hourly["month"] = str(month)
            hourly["lens"] = lens
            coverage_parts.append(hourly)

    summary = pd.DataFrame(summary_rows)
    coverage = pd.concat(coverage_parts, ignore_index=True) if coverage_parts else pd.DataFrame()
    return summary, lag_schedule, coverage


def _weighted_average(df: pd.DataFrame, col: str, weight_col: str) -> float:
    if col not in df.columns or weight_col not in df.columns:
        return float("nan")
    vals = pd.to_numeric(df[col], errors="coerce")
    weights = pd.to_numeric(df[weight_col], errors="coerce")
    mask = vals.notna() & weights.notna() & (weights > 0)
    if not mask.any():
        return float("nan")
    return float(np.average(vals[mask], weights=weights[mask]))


def _aggregate_overall(summary: pd.DataFrame) -> pd.DataFrame:
    if summary.empty:
        return summary
    rows: list[dict[str, Any]] = []
    for (symbol, lens), grp in summary.groupby(["symbol", "lens"], dropna=False):
        row: dict[str, Any] = {
            "symbol": symbol,
            "month": "OVERALL",
            "lens": lens,
            "reference_path": "",
            "candidate_path": "",
            "reference_partial_month": bool(grp["reference_partial_month"].astype(bool).any()),
            "candidate_partial_month": bool(grp["candidate_partial_month"].astype(bool).any()),
            "overlap_start_ts": grp["overlap_start_ts"].replace("", pd.NA).dropna().min()
            if "overlap_start_ts" in grp
            else "",
            "overlap_end_ts": grp["overlap_end_ts"].replace("", pd.NA).dropna().max()
            if "overlap_end_ts" in grp
            else "",
            "lag_schedule_unresolved_days": int(pd.to_numeric(grp["lag_schedule_unresolved_days"], errors="coerce").fillna(0).sum()),
            "lag_schedule_day_count": int(pd.to_numeric(grp["lag_schedule_day_count"], errors="coerce").fillna(0).sum()),
            "lag_schedule_mode_hours": float(pd.to_numeric(grp["lag_schedule_mode_hours"], errors="coerce").mode().iloc[0])
            if pd.to_numeric(grp["lag_schedule_mode_hours"], errors="coerce").dropna().size
            else float("nan"),
        }
        sum_cols = [
            "reference_rows",
            "candidate_rows",
            "reference_bar_count",
            "candidate_bar_count",
            "overlap_minutes",
        ]
        for col in sum_cols:
            if col in grp.columns:
                row[col] = float(pd.to_numeric(grp[col], errors="coerce").fillna(0).sum())
        weighted_overlap = "overlap_minutes" if "overlap_minutes" in grp.columns else "reference_rows"
        weighted_rows = "reference_rows" if "reference_rows" in grp.columns else weighted_overlap
        for col in grp.columns:
            if col in row or col in {"symbol", "month", "lens", "reference_path", "candidate_path"}:
                continue
            if col.endswith("_ts") or col in {"reference_partial_month", "candidate_partial_month"}:
                continue
            if col in sum_cols:
                continue
            if grp[col].dtype == object:
                continue
            weight_col = weighted_overlap
            if col.startswith("reference_") or col.startswith("candidate_"):
                weight_col = weighted_rows
            row[col] = _weighted_average(grp, col, weight_col)
        rows.append(row)
    return pd.DataFrame(rows)


def _headline_lines(summary: pd.DataFrame, lag_schedule: pd.DataFrame) -> list[str]:
    if summary.empty:
        return ["- No common symbol-month pairs were found."]
    overall = summary[summary["month"].astype(str) == "OVERALL"].copy()
    lines: list[str] = []
    for symbol in sorted(overall["symbol"].astype(str).unique()):
        as_is = overall[
            (overall["symbol"].astype(str) == symbol) & (overall["lens"].astype(str) == "as_is")
        ]
        corrected = overall[
            (overall["symbol"].astype(str) == symbol)
            & (overall["lens"].astype(str) == "lag_corrected")
        ]
        if not as_is.empty:
            row = as_is.iloc[0]
            lines.append(
                f"- `{symbol}` as stored: minute-return correlation `{float(row['minute_return_corr']):.4f}`; "
                f"candidate/reference row ratio `{float(row['candidate_to_reference_row_ratio']):.4f}`; "
                f"mean spread `{float(row['candidate_spread_mean'] / _pip_size(symbol)):.3f}` vs "
                f"`{float(row['reference_spread_mean'] / _pip_size(symbol)):.3f}` pips."
            )
        if not corrected.empty:
            row = corrected.iloc[0]
            lines.append(
                f"- `{symbol}` after lag correction: minute-return correlation `{float(row['minute_return_corr']):.4f}`; "
                f"minute mid MAE `{float(row['minute_mid_mae_pips']):.3f}` pips; "
                f"hourly coverage ratio mean `{float(row['hourly_coverage_ratio_mean']):.3f}`."
            )
    resolved = lag_schedule[pd.to_numeric(lag_schedule["inferred_lag_hours"], errors="coerce").notna()].copy()
    if not resolved.empty:
        lag_modes = (
            resolved.groupby(["symbol", "month"], as_index=False)["inferred_lag_hours"]
            .agg(lambda x: ",".join(sorted({str(int(v)) for v in pd.to_numeric(x, errors="coerce").dropna()})))
        )
        for _, row in lag_modes.iterrows():
            lines.append(
                f"- `{row['symbol']}` `{row['month']}` inferred whole-hour lag set: `{row['inferred_lag_hours']}`."
            )
    return lines


def _write_report(
    *,
    report_out: Path,
    summary: pd.DataFrame,
    lag_schedule: pd.DataFrame,
    coverage: pd.DataFrame,
    reference_root: Path,
    candidate_root: Path,
    bar_ticks: int,
) -> None:
    report_out.parent.mkdir(parents=True, exist_ok=True)
    monthly = summary[summary["month"].astype(str) != "OVERALL"].copy()
    overall = summary[summary["month"].astype(str) == "OVERALL"].copy()
    key_cols = [
        "symbol",
        "month",
        "lens",
        "candidate_to_reference_row_ratio",
        "minute_return_corr",
        "minute_mid_mae_pips",
        "minute_spread_mae_pips",
        "hourly_coverage_ratio_mean",
        "seconds_per_bar_mean_delta",
    ]
    lag_cols = ["symbol", "month", "date_utc", "inferred_lag_hours", "best_corr", "lag_source"]
    lines = [
        "# EURUSD Dukascopy vs HistData Tick Similarity Report",
        "",
        "## Window",
        "",
        f"- Generated: `{datetime.now(timezone.utc).isoformat()}`",
        f"- Reference root: `{reference_root}`",
        f"- Candidate root: `{candidate_root}`",
        f"- Bar size for cadence diagnostics: `{int(bar_ticks)}` ticks",
        "",
        "## Headline Findings",
        "",
    ]
    lines.extend(_headline_lines(summary, lag_schedule))
    lines.extend(
        [
            "",
            "## Overall Summary",
            "",
            _table(overall[key_cols] if not overall.empty else overall),
            "",
            "## Month-by-Month Summary",
            "",
            _table(monthly[key_cols] if not monthly.empty else monthly),
            "",
            "## Lag Schedule Snapshot",
            "",
            _table(lag_schedule[lag_cols].head(20) if not lag_schedule.empty else lag_schedule),
            "",
            "## Coverage Snapshot",
            "",
            _table(coverage.head(20)),
            "",
            "## Interpretation",
            "",
            "- `as_is` reflects the exact parquet timestamps your models consume today.",
            "- `lag_corrected` is diagnostic and isolates whole-hour timestamp policy drift from genuine quote-path differences.",
            "- Dukascopy remains the reference feed; remaining spread or cadence differences after correction indicate feed microstructure divergence rather than a pure timezone issue.",
            "",
        ]
    )
    report_out.write_text("\n".join(lines), encoding="utf-8")


def run(
    *,
    reference_root: Path,
    candidate_root: Path,
    symbols: list[str],
    months: list[str],
    bar_ticks: int,
    max_lag_hours: int,
    out_dir: Path,
    report_out: Path,
    min_overlap_minutes: int = 180,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    out_dir.mkdir(parents=True, exist_ok=True)
    summary_parts: list[pd.DataFrame] = []
    lag_parts: list[pd.DataFrame] = []
    coverage_parts: list[pd.DataFrame] = []

    for symbol in symbols:
        for month in months:
            reference_path = reference_root / symbol / f"{symbol}_{month}_ticks.parquet"
            candidate_path = candidate_root / symbol / f"{symbol}_{month}_ticks.parquet"
            if not (reference_path.exists() and candidate_path.exists()):
                continue
            summary, lag_schedule, coverage = analyze_symbol_month(
                symbol=symbol,
                month=month,
                reference_path=reference_path,
                candidate_path=candidate_path,
                bar_ticks=bar_ticks,
                max_lag_hours=max_lag_hours,
                min_overlap_minutes=min_overlap_minutes,
            )
            summary_parts.append(summary)
            lag_parts.append(lag_schedule)
            coverage_parts.append(coverage)

    summary = pd.concat(summary_parts, ignore_index=True) if summary_parts else pd.DataFrame()
    lag_schedule = pd.concat(lag_parts, ignore_index=True) if lag_parts else pd.DataFrame()
    coverage = pd.concat(coverage_parts, ignore_index=True) if coverage_parts else pd.DataFrame()
    overall = _aggregate_overall(summary)
    if not overall.empty:
        summary = pd.concat([summary, overall], ignore_index=True)

    summary_path = out_dir / "tick_source_similarity_summary.csv"
    lag_path = out_dir / "tick_source_similarity_lag_schedule.csv"
    coverage_path = out_dir / "tick_source_similarity_hourly_coverage.csv"
    summary.to_csv(summary_path, index=False)
    lag_schedule.to_csv(lag_path, index=False)
    coverage.to_csv(coverage_path, index=False)
    _write_report(
        report_out=report_out,
        summary=summary,
        lag_schedule=lag_schedule,
        coverage=coverage,
        reference_root=reference_root,
        candidate_root=candidate_root,
        bar_ticks=bar_ticks,
    )
    return summary, lag_schedule, coverage


def main() -> None:
    p = argparse.ArgumentParser(description="Compare canonical parquet tick sources")
    p.add_argument("--reference-root", default="/Users/danielfisher/Desktop/dukascopy_ticks")
    p.add_argument("--candidate-root", default="/Users/danielfisher/Desktop/tick")
    p.add_argument("--symbols", default="EURUSD")
    p.add_argument("--months", default="201801,201802,201803,201804,201805,201806")
    p.add_argument("--bar-ticks", type=int, default=100)
    p.add_argument("--lag-search-hours", type=int, default=8)
    p.add_argument("--min-overlap-minutes", type=int, default=180)
    p.add_argument("--out-dir", default="data/analysis/backtest_reconcile")
    p.add_argument(
        "--report-out",
        default="docs/analysis/eurusd_dukascopy_vs_histdata_tick_similarity_report.md",
    )
    args = p.parse_args()

    summary, lag_schedule, coverage = run(
        reference_root=Path(str(args.reference_root)),
        candidate_root=Path(str(args.candidate_root)),
        symbols=_parse_symbols(str(args.symbols)),
        months=_parse_months(str(args.months)),
        bar_ticks=int(args.bar_ticks),
        max_lag_hours=int(args.lag_search_hours),
        out_dir=Path(str(args.out_dir)),
        report_out=Path(str(args.report_out)),
        min_overlap_minutes=int(args.min_overlap_minutes),
    )
    print(f"wrote summary: {Path(str(args.out_dir)) / 'tick_source_similarity_summary.csv'} rows={len(summary)}")
    print(f"wrote lag schedule: {Path(str(args.out_dir)) / 'tick_source_similarity_lag_schedule.csv'} rows={len(lag_schedule)}")
    print(f"wrote hourly coverage: {Path(str(args.out_dir)) / 'tick_source_similarity_hourly_coverage.csv'} rows={len(coverage)}")
    print(f"wrote report: {args.report_out}")


if __name__ == "__main__":
    main()
