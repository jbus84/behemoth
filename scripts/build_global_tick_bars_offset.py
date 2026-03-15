#!/usr/bin/env python3
"""Build fixed-tick bars from raw HistData with a global starting tick offset."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

import polars as pl

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.build_global_tick_bars import (  # noqa: E402
    DEFAULT_CANONICAL_ROOT,
    UTC_TS,
    _bars_from_ticks,
    _parse_symbols,
    _select_tick_exprs,
    _symbol_files,
    _timestamp_expr,
    _validate_timestamp_schema,
)


def _parse_int_list(raw: str | None) -> list[int]:
    vals: list[int] = []
    for tok in str(raw or "").split(","):
        t = tok.strip()
        if not t:
            continue
        vals.append(int(t))
    return vals


def _empty_tick_frame() -> pl.DataFrame:
    return pl.DataFrame(
        schema={
            "timestamp": UTC_TS,
            "price": pl.Float64,
            "ask": pl.Float64,
            "spread": pl.Float64,
        }
    )


def _build_offset_bars(
    *,
    tick_root: Path,
    symbol: str,
    bar_ticks: int,
    tick_offset: int,
    price_source: str,
    timestamp_mode: str,
) -> tuple[pl.DataFrame, int, int]:
    files = _symbol_files(tick_root, symbol)
    if not files:
        raise FileNotFoundError(f"{symbol}: no *_ticks.parquet files under {tick_root}")

    first_schema = pl.read_parquet_schema(str(files[0]))
    schema = dict(first_schema.items())
    names = set(schema.keys())
    _validate_timestamp_schema(
        schema=schema,
        symbol=symbol,
        file_path=files[0],
        timestamp_mode=timestamp_mode,
    )
    price_expr, ask_expr, spread_expr = _select_tick_exprs(names, price_source=price_source)

    carry = _empty_tick_frame()
    chunks: list[pl.DataFrame] = []
    tick_idx = 0
    skip_remaining = max(0, int(tick_offset))
    dropped_input_ticks = 0

    for fp in files:
        part_schema = dict(pl.read_parquet_schema(str(fp)).items())
        _validate_timestamp_schema(
            schema=part_schema,
            symbol=symbol,
            file_path=fp,
            timestamp_mode=timestamp_mode,
        )
        part = (
            pl.scan_parquet(str(fp))
            .select(
                _timestamp_expr(str(timestamp_mode)).alias("timestamp"),
                price_expr.alias("price"),
                ask_expr.alias("ask"),
                spread_expr.alias("spread"),
            )
            .drop_nulls(["timestamp", "price"])
            .sort("timestamp")
            .collect()
            .with_columns(pl.col("timestamp").cast(UTC_TS))
        )

        if skip_remaining > 0:
            skip_now = min(skip_remaining, part.height)
            if skip_now > 0:
                part = part.slice(skip_now)
                skip_remaining -= skip_now
                dropped_input_ticks += int(skip_now)
        if carry.height:
            part = pl.concat([carry, part], how="vertical")
        if part.height == 0:
            carry = _empty_tick_frame()
            continue

        bars, tick_idx, carry = _bars_from_ticks(
            part,
            symbol=symbol,
            bar_ticks=int(bar_ticks),
            start_tick_index=tick_idx,
        )
        if bars.height:
            chunks.append(bars)

    if not chunks:
        return pl.DataFrame(), int(carry.height), int(dropped_input_ticks)

    out = pl.concat(chunks, how="vertical").sort("timestamp")
    return out, int(carry.height), int(dropped_input_ticks)


def _build_one(
    *,
    tick_root: Path,
    output_dir: Path,
    symbol: str,
    bar_ticks: int,
    tick_offset: int,
    price_source: str,
    timestamp_mode: str,
    overwrite: bool,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    out_path = output_dir / f"{symbol}_{int(bar_ticks)}tick_offset_{int(tick_offset):03d}.parquet"
    if out_path.exists() and not overwrite:
        bars = pl.read_parquet(out_path)
        return {
            "symbol": symbol,
            "bar_ticks": int(bar_ticks),
            "tick_offset": int(tick_offset),
            "status": "exists",
            "bar_count": int(bars.height),
            "first_timestamp": str(bars["timestamp"][0]) if bars.height else "",
            "last_close_ts": str(bars["close_ts"][-1]) if bars.height else "",
            "dropped_tail_ticks": 0,
            "dropped_input_ticks": int(tick_offset),
            "output_path": str(out_path),
        }

    bars, dropped_tail_ticks, dropped_input_ticks = _build_offset_bars(
        tick_root=tick_root,
        symbol=symbol,
        bar_ticks=int(bar_ticks),
        tick_offset=int(tick_offset),
        price_source=price_source,
        timestamp_mode=timestamp_mode,
    )
    if bars.height == 0:
        return {
            "symbol": symbol,
            "bar_ticks": int(bar_ticks),
            "tick_offset": int(tick_offset),
            "status": "empty",
            "bar_count": 0,
            "first_timestamp": "",
            "last_close_ts": "",
            "dropped_tail_ticks": int(dropped_tail_ticks),
            "dropped_input_ticks": int(dropped_input_ticks),
            "output_path": str(out_path),
        }

    bars.write_parquet(out_path)
    return {
        "symbol": symbol,
        "bar_ticks": int(bar_ticks),
        "tick_offset": int(tick_offset),
        "status": "ok",
        "bar_count": int(bars.height),
        "first_timestamp": str(bars["timestamp"][0]),
        "last_close_ts": str(bars["close_ts"][-1]),
        "dropped_tail_ticks": int(dropped_tail_ticks),
        "dropped_input_ticks": int(dropped_input_ticks),
        "output_path": str(out_path),
    }


def main() -> None:
    p = argparse.ArgumentParser(description="Build fixed-tick bars with global tick offsets")
    p.add_argument("--tick-root", default=str(DEFAULT_CANONICAL_ROOT))
    p.add_argument("--output-dir", default="data/global_tickbars_offset")
    p.add_argument("--symbols", default="")
    p.add_argument("--offsets", default="0")
    p.add_argument("--bar-ticks", type=int, default=100)
    p.add_argument("--price-source", choices=["bid", "mid"], default="bid")
    p.add_argument(
        "--timestamp-mode",
        choices=["as_utc", "ny_local_tagged_utc"],
        default="as_utc",
    )
    p.add_argument(
        "--summary-csv",
        default="data/global_tickbars_offset/build_summary.csv",
        help="Optional build summary CSV",
    )
    p.add_argument("--overwrite", action="store_true")
    args = p.parse_args()

    tick_root = Path(str(args.tick_root))
    output_dir = Path(str(args.output_dir))
    summary_csv = Path(str(args.summary_csv)) if str(args.summary_csv).strip() else None

    symbols = _parse_symbols(str(args.symbols))
    if not symbols:
        symbols = sorted([d.name for d in tick_root.iterdir() if d.is_dir()])
    offsets = sorted(set(_parse_int_list(str(args.offsets))))
    if not offsets:
        raise ValueError("--offsets must contain at least one integer")
    if any(int(x) < 0 for x in offsets):
        raise ValueError("--offsets must be non-negative")
    if int(args.bar_ticks) <= 0:
        raise ValueError("--bar-ticks must be > 0")

    rows: list[dict[str, Any]] = []
    for symbol in symbols:
        for offset in offsets:
            row = _build_one(
                tick_root=tick_root,
                output_dir=output_dir,
                symbol=str(symbol).upper().strip(),
                bar_ticks=int(args.bar_ticks),
                tick_offset=int(offset),
                price_source=str(args.price_source),
                timestamp_mode=str(args.timestamp_mode),
                overwrite=bool(args.overwrite),
            )
            rows.append(row)
            print(
                f"{row['status']} {row['symbol']} {row['bar_ticks']}tick offset={row['tick_offset']:03d}: "
                f"bars={row['bar_count']} -> {row['output_path']}"
            )

    if summary_csv is not None:
        summary_csv.parent.mkdir(parents=True, exist_ok=True)
        pl.DataFrame(rows).write_csv(summary_csv)
        print(f"wrote summary: {summary_csv} rows={len(rows)}")


if __name__ == "__main__":
    main()
