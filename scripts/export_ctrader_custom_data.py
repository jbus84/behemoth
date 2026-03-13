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


def _all_symbol_tick_files(symbol: str, tick_root: Path) -> list[Path]:
    return sorted(
        p
        for p in (tick_root / symbol).glob(f"{symbol}_*_ticks.parquet")
        if p.is_file()
    )


def _load_hist_ticks_by_count(
    *,
    symbol: str,
    tick_root: Path,
    anchor: pd.Timestamp,
    ticks_before: int,
    ticks_after: int,
) -> pd.DataFrame:
    files = _all_symbol_tick_files(symbol, tick_root)
    if not files:
        return pd.DataFrame(columns=["timestamp", "bid", "ask"])

    files_sql = "[" + ",".join(_quote_sql_path(p) for p in files) + "]"
    con = duckdb.connect()
    try:
        ts_expr = "try_cast(timestamp AS TIMESTAMP WITH TIME ZONE)"
        before = (
            con.execute(
                f"""
                SELECT timestamp, bid, ask
                FROM (
                    SELECT
                        {ts_expr} AS timestamp,
                        try_cast(bid AS DOUBLE) AS bid,
                        try_cast(ask AS DOUBLE) AS ask
                    FROM read_parquet({files_sql})
                    WHERE {ts_expr} < ?
                    ORDER BY {ts_expr} DESC
                    LIMIT {max(0, int(ticks_before))}
                ) q
                ORDER BY timestamp
                """,
                [anchor.to_pydatetime()],
            ).fetchdf()
            if int(ticks_before) > 0
            else pd.DataFrame(columns=["timestamp", "bid", "ask"])
        )
        after = (
            con.execute(
                f"""
                SELECT
                    {ts_expr} AS timestamp,
                    try_cast(bid AS DOUBLE) AS bid,
                    try_cast(ask AS DOUBLE) AS ask
                FROM read_parquet({files_sql})
                WHERE {ts_expr} >= ?
                ORDER BY {ts_expr}
                LIMIT {max(0, int(ticks_after))}
                """,
                [anchor.to_pydatetime()],
            ).fetchdf()
            if int(ticks_after) > 0
            else pd.DataFrame(columns=["timestamp", "bid", "ask"])
        )
    finally:
        con.close()

    out = pd.concat([before, after], ignore_index=True)
    if out.empty:
        return pd.DataFrame(columns=["timestamp", "bid", "ask"])
    out["timestamp"] = _to_utc(out.get("timestamp", pd.Series(dtype=object)))
    out["bid"] = pd.to_numeric(out.get("bid", pd.Series(dtype=float)), errors="coerce")
    out["ask"] = pd.to_numeric(out.get("ask", pd.Series(dtype=float)), errors="coerce")
    out = out.dropna(subset=["timestamp", "bid", "ask"]).reset_index(drop=True)
    return out[["timestamp", "bid", "ask"]]


def _merge_tick_frames(*frames: pd.DataFrame) -> pd.DataFrame:
    parts = [f[["timestamp", "bid", "ask"]].copy() for f in frames if f is not None and not f.empty]
    if not parts:
        return pd.DataFrame(columns=["timestamp", "bid", "ask"])
    out = pd.concat(parts, ignore_index=True)
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
    anchor_ts: str | None = None,
    ticks_before_anchor: int = 0,
    ticks_after_anchor: int = 0,
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

    count_mode = bool(str(anchor_ts or "").strip()) and (
        int(ticks_before_anchor) > 0 or int(ticks_after_anchor) > 0
    )
    if count_mode:
        anchor = _parse_ts("anchor_ts", anchor_ts)
        count_ticks = _load_hist_ticks_by_count(
            symbol=sym,
            tick_root=tick_root,
            anchor=anchor,
            ticks_before=int(ticks_before_anchor),
            ticks_after=int(ticks_after_anchor),
        )
        window_ticks = _load_hist_ticks(
            symbol=sym,
            tick_root=tick_root,
            start=start,
            end=end,
        )
        ticks = _merge_tick_frames(count_ticks, window_ticks)
    else:
        ticks = _load_hist_ticks(
            symbol=sym,
            tick_root=tick_root,
            start=start,
            end=end,
        )
    if ticks.empty:
        if count_mode:
            raise ValueError(
                f"no HistData ticks found for {sym} around anchor={anchor_ts} "
                f"with ticks_before={int(ticks_before_anchor)} ticks_after={int(ticks_after_anchor)}"
            )
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
    actual_start = ticks["timestamp"].min()
    actual_end = ticks["timestamp"].max()
    requested_window_mask = (ticks["timestamp"] >= start) & (ticks["timestamp"] < end)
    requested_window_ticks = ticks.loc[requested_window_mask]
    requested_window_max = requested_window_ticks["timestamp"].max() if not requested_window_ticks.empty else pd.NaT
    start_tag = actual_start.strftime("%Y%m%dT%H%M%S")
    end_tag = actual_end.strftime("%Y%m%dT%H%M%S")
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
        "anchor_ts": _fmt_ts(anchor) if count_mode else "",
        "ticks_before_anchor_requested": int(ticks_before_anchor) if count_mode else 0,
        "ticks_after_anchor_requested": int(ticks_after_anchor) if count_mode else 0,
        "requested_window_rows": int(requested_window_mask.sum()),
        "input_rows": input_rows,
        "export_rows": deduped_rows,
        "dropped_duplicate_rows": int(input_rows - deduped_rows),
        "dedup_ratio": (float(deduped_rows) / float(input_rows))
        if input_rows > 0
        else float("nan"),
        "export_min_ts": _fmt_ts(actual_start),
        "export_max_ts": _fmt_ts(actual_end),
        "requested_window_covered_to_end": bool(
            pd.notna(requested_window_max) and actual_end >= requested_window_max
        ),
        "export_rows_before_anchor": int((ticks["timestamp"] < anchor).sum()) if count_mode else 0,
        "export_rows_at_or_after_anchor": int((ticks["timestamp"] >= anchor).sum()) if count_mode else 0,
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
        "start_ts": _fmt_ts(actual_start),
        "end_ts": _fmt_ts(actual_end + pd.Timedelta(microseconds=1)),
        "generated_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "columns": ["timestamp_utc", "bid", "ask"],
        "source": {
            "kind": "histdata_parquet",
            "tick_root": str(tick_root),
        },
        "requested_window": {
            "start_ts": _fmt_ts(start),
            "end_ts": _fmt_ts(end),
            "anchor_ts": _fmt_ts(anchor) if count_mode else "",
            "ticks_before_anchor": int(ticks_before_anchor) if count_mode else 0,
            "ticks_after_anchor": int(ticks_after_anchor) if count_mode else 0,
        },
        "files": [
            {
                "path": f"ticks/{csv_name}",
                "row_count": deduped_rows,
                "min_ts": _fmt_ts(actual_start),
                "max_ts": _fmt_ts(actual_end),
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
    p.add_argument("--anchor-ts", default="")
    p.add_argument("--ticks-before-anchor", type=int, default=0)
    p.add_argument("--ticks-after-anchor", type=int, default=0)
    args = p.parse_args()

    manifest_path, summary_path, summary_df = run(
        symbol=str(args.symbol),
        tick_root=Path(str(args.tick_root)),
        start_ts=str(args.start_ts),
        end_ts=str(args.end_ts),
        out_dir=Path(str(args.out_dir)),
        overwrite=_bool_arg(str(args.overwrite)),
        summary_csv=(Path(str(args.summary_csv)) if str(args.summary_csv).strip() else None),
        anchor_ts=(str(args.anchor_ts).strip() or None),
        ticks_before_anchor=int(args.ticks_before_anchor),
        ticks_after_anchor=int(args.ticks_after_anchor),
    )
    print(f"wrote manifest: {manifest_path}")
    print(f"wrote summary: {summary_path} rows={len(summary_df)}")
    print(f"exported_rows={int(summary_df.iloc[0]['export_rows'])}")


if __name__ == "__main__":
    main()
