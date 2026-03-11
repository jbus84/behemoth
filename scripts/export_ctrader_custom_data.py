#!/usr/bin/env python3
"""Export HistData parquet ticks into a cTrader custom-data package."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import duckdb
import numpy as np
import pandas as pd


def _parse_ts(name: str, raw: str | None) -> pd.Timestamp:
    txt = str(raw or "").strip()
    if not txt:
        raise ValueError(f"{name} is required")
    ts = pd.to_datetime(txt, utc=True, errors="coerce")
    if pd.isna(ts):
        raise ValueError(f"invalid {name}: {raw!r}")
    return ts


def _month_tags_between(start: pd.Timestamp, end: pd.Timestamp) -> list[str]:
    if not (start < end):
        return []
    end_inclusive = end - pd.Timedelta(microseconds=1)
    if end_inclusive < start:
        return []
    s0 = start.tz_convert("UTC").tz_localize(None) if start.tzinfo is not None else start
    e0 = (
        end_inclusive.tz_convert("UTC").tz_localize(None)
        if end_inclusive.tzinfo is not None
        else end_inclusive
    )
    pr = pd.period_range(start=s0.to_period("M"), end=e0.to_period("M"), freq="M")
    return [str(p).replace("-", "") for p in pr]


def _quote_sql_path(path: Path) -> str:
    return "'" + str(path).replace("'", "''") + "'"


def _to_utc(s: pd.Series) -> pd.Series:
    try:
        return pd.to_datetime(s, utc=True, errors="coerce", format="mixed")
    except TypeError:
        return pd.to_datetime(s, utc=True, errors="coerce")


def _load_hist_ticks(
    *,
    symbol: str,
    tick_root: Path,
    start: pd.Timestamp,
    end: pd.Timestamp,
) -> pd.DataFrame:
    months = _month_tags_between(start, end)
    files = [
        tick_root / symbol / f"{symbol}_{m}_ticks.parquet"
        for m in months
        if (tick_root / symbol / f"{symbol}_{m}_ticks.parquet").exists()
    ]
    if not files:
        return pd.DataFrame(columns=["timestamp", "bid", "ask"])

    files_sql = "[" + ",".join(_quote_sql_path(p) for p in files) + "]"
    con = duckdb.connect()
    try:
        ts_expr = "try_cast(timestamp AS TIMESTAMP WITH TIME ZONE)"
        sql = (
            f"SELECT {ts_expr} AS timestamp, try_cast(bid AS DOUBLE) AS bid, "
            f"try_cast(ask AS DOUBLE) AS ask FROM read_parquet({files_sql}) "
            f"WHERE {ts_expr} >= ? AND {ts_expr} < ? ORDER BY {ts_expr}"
        )
        out = con.execute(sql, [start.to_pydatetime(), end.to_pydatetime()]).fetchdf()
    finally:
        con.close()
    if out.empty:
        return pd.DataFrame(columns=["timestamp", "bid", "ask"])
    out["timestamp"] = _to_utc(out.get("timestamp", pd.Series(dtype=object)))
    out["bid"] = pd.to_numeric(out.get("bid", pd.Series(dtype=float)), errors="coerce")
    out["ask"] = pd.to_numeric(out.get("ask", pd.Series(dtype=float)), errors="coerce")
    out = out.dropna(subset=["timestamp", "bid", "ask"]).reset_index(drop=True)
    return out[["timestamp", "bid", "ask"]]


def _bool_arg(raw: str) -> bool:
    return str(raw).strip().lower() in {"1", "true", "yes", "y"}


def _median_intertick_ms(ts: pd.Series) -> float:
    x = _to_utc(ts).dropna().sort_values()
    if len(x) < 2:
        return float("nan")
    dt_ms = x.diff().dt.total_seconds().dropna() * 1000.0
    if dt_ms.empty:
        return float("nan")
    return float(dt_ms.median())


def _p90_intertick_ms(ts: pd.Series) -> float:
    x = _to_utc(ts).dropna().sort_values()
    if len(x) < 2:
        return float("nan")
    dt_ms = x.diff().dt.total_seconds().dropna() * 1000.0
    if dt_ms.empty:
        return float("nan")
    return float(dt_ms.quantile(0.9))


def _fmt_ts(ts: pd.Timestamp) -> str:
    return ts.tz_convert("UTC").isoformat().replace("+00:00", "Z")


def run(
    *,
    symbol: str,
    tick_root: Path,
    start_ts: str,
    end_ts: str,
    out_dir: Path,
    overwrite: bool = False,
    summary_csv: Path | None = None,
) -> tuple[Path, Path, pd.DataFrame]:
    sym = str(symbol).upper().strip()
    if not sym:
        raise ValueError("symbol is required")

    start = _parse_ts("start_ts", start_ts)
    end = _parse_ts("end_ts", end_ts)
    if not (start < end):
        raise ValueError("start_ts must be earlier than end_ts")

    manifest_path = out_dir / "manifest.json"
    if manifest_path.exists() and not overwrite:
        raise FileExistsError(f"output exists: {manifest_path}; pass --overwrite true to replace")

    ticks = _load_hist_ticks(
        symbol=sym,
        tick_root=tick_root,
        start=start,
        end=end,
    )
    if ticks.empty:
        raise ValueError(f"no HistData ticks found for {sym} in [{_fmt_ts(start)}, {_fmt_ts(end)})")

    ticks = ticks.sort_values(["timestamp", "bid", "ask"]).reset_index(drop=True)
    input_rows = int(len(ticks))
    ticks = ticks.drop_duplicates(subset=["timestamp", "bid", "ask"]).reset_index(drop=True)
    deduped_rows = int(len(ticks))

    invalid_nonfinite = (~np.isfinite(ticks["bid"])) | (~np.isfinite(ticks["ask"]))
    invalid_crossed = ticks["ask"] < ticks["bid"]
    if int(invalid_nonfinite.sum()) > 0:
        raise ValueError(f"found non-finite bid/ask rows: {int(invalid_nonfinite.sum())}")
    if int(invalid_crossed.sum()) > 0:
        raise ValueError(f"found ask < bid rows: {int(invalid_crossed.sum())}")

    out_dir.mkdir(parents=True, exist_ok=True)
    ticks_dir = out_dir / "ticks"
    ticks_dir.mkdir(parents=True, exist_ok=True)
    start_tag = start.strftime("%Y%m%dT%H%M%S")
    end_tag = end.strftime("%Y%m%dT%H%M%S")
    csv_name = f"{sym}_{start_tag}_{end_tag}.csv"
    csv_path = ticks_dir / csv_name

    out_ticks = ticks.copy()
    out_ticks["timestamp_utc"] = out_ticks["timestamp"].dt.strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    out_ticks = out_ticks[["timestamp_utc", "bid", "ask"]]
    out_ticks.to_csv(csv_path, index=False)

    spread = ticks["ask"] - ticks["bid"]
    summary_row: dict[str, Any] = {
        "symbol": sym,
        "tick_root": str(tick_root),
        "start_ts": _fmt_ts(start),
        "end_ts": _fmt_ts(end),
        "input_rows": input_rows,
        "export_rows": deduped_rows,
        "dropped_duplicate_rows": int(input_rows - deduped_rows),
        "dedup_ratio": (float(deduped_rows) / float(input_rows))
        if input_rows > 0
        else float("nan"),
        "export_min_ts": _fmt_ts(ticks["timestamp"].min()),
        "export_max_ts": _fmt_ts(ticks["timestamp"].max()),
        "spread_mean": float(spread.mean()),
        "spread_p50": float(spread.quantile(0.5)),
        "spread_p90": float(spread.quantile(0.9)),
        "spread_zero_ratio": float((spread == 0.0).sum()) / float(len(spread)),
        "median_intertick_ms": _median_intertick_ms(ticks["timestamp"]),
        "p90_intertick_ms": _p90_intertick_ms(ticks["timestamp"]),
        "generated_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    summary_df = pd.DataFrame([summary_row])
    summary_path = summary_csv if summary_csv is not None else (out_dir / "export_summary.csv")
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_df.to_csv(summary_path, index=False)

    manifest: dict[str, Any] = {
        "schema_version": "1.0",
        "data_type": "tick",
        "symbol": sym,
        "start_ts": _fmt_ts(start),
        "end_ts": _fmt_ts(end),
        "generated_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "columns": ["timestamp_utc", "bid", "ask"],
        "source": {
            "kind": "histdata_parquet",
            "tick_root": str(tick_root),
        },
        "files": [
            {
                "path": f"ticks/{csv_name}",
                "row_count": deduped_rows,
                "min_ts": _fmt_ts(ticks["timestamp"].min()),
                "max_ts": _fmt_ts(ticks["timestamp"].max()),
            }
        ],
        "summary_csv": str(summary_path.relative_to(out_dir))
        if summary_path.is_relative_to(out_dir)
        else str(summary_path),
    }
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    return manifest_path, summary_path, summary_df


def main() -> None:
    p = argparse.ArgumentParser(description="Export HistData parquet ticks for cTrader custom data")
    p.add_argument("--symbol", required=True)
    p.add_argument("--tick-root", default="/Users/danielfisher/Desktop/tick")
    p.add_argument("--start-ts", required=True)
    p.add_argument("--end-ts", required=True)
    p.add_argument("--out-dir", required=True)
    p.add_argument("--overwrite", default="false", choices=["true", "false"])
    p.add_argument("--summary-csv", default="")
    args = p.parse_args()

    manifest_path, summary_path, summary_df = run(
        symbol=str(args.symbol),
        tick_root=Path(str(args.tick_root)),
        start_ts=str(args.start_ts),
        end_ts=str(args.end_ts),
        out_dir=Path(str(args.out_dir)),
        overwrite=_bool_arg(str(args.overwrite)),
        summary_csv=(Path(str(args.summary_csv)) if str(args.summary_csv).strip() else None),
    )
    print(f"wrote manifest: {manifest_path}")
    print(f"wrote summary: {summary_path} rows={len(summary_df)}")
    print(f"exported_rows={int(summary_df.iloc[0]['export_rows'])}")


if __name__ == "__main__":
    main()
