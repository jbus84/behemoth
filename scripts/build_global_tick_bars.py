#!/usr/bin/env python3
"""Build cTrader-style fixed tick bars from raw monthly tick parquet files.

Input layout:
- /path/to/tick/SYMBOL/SYMBOL_YYYYMM_ticks.parquet

Output per symbol/tick-size:
- data/global_tickbars/SYMBOL_{N}tick.parquet
"""

from __future__ import annotations

import argparse
from pathlib import Path

import polars as pl

UTC_TS = pl.Datetime("ns", "UTC")


def _timestamp_expr(timestamp_mode: str) -> pl.Expr:
    mode = str(timestamp_mode).strip().lower()
    ts = pl.col("timestamp")
    if mode == "as_utc":
        return ts
    if mode == "ny_local_tagged_utc":
        # Interpret naive timestamps as New York local time and convert to UTC.
        return (
            ts.dt.replace_time_zone(None)
            .dt.replace_time_zone("America/New_York")
            .dt.convert_time_zone("UTC")
        )
    raise ValueError(f"unsupported timestamp_mode: {timestamp_mode}")


def _parse_symbols(raw: str | None) -> list[str]:
    if raw is None or not str(raw).strip():
        return []
    return [x.strip().upper() for x in str(raw).split(",") if x.strip()]


def _parse_int_list(raw: str) -> list[int]:
    vals: list[int] = []
    for tok in str(raw).split(","):
        t = tok.strip()
        if not t:
            continue
        vals.append(int(t))
    return vals


def _symbol_files(tick_root: Path, symbol: str) -> list[Path]:
    return sorted((tick_root / symbol).glob(f"{symbol}_*_ticks.parquet"))


def _select_tick_exprs(
    schema_names: set[str], price_source: str
) -> tuple[pl.Expr, pl.Expr, pl.Expr]:
    price_source = str(price_source).lower().strip()

    if price_source == "mid":
        if "mid" in schema_names:
            price_expr = pl.col("mid").cast(pl.Float64)
        elif "bid" in schema_names and "ask" in schema_names:
            price_expr = ((pl.col("bid") + pl.col("ask")) / 2.0).cast(pl.Float64)
        else:
            raise ValueError("missing mid and bid/ask for price_source=mid")
    else:
        if "bid" in schema_names:
            price_expr = pl.col("bid").cast(pl.Float64)
        elif "mid" in schema_names:
            price_expr = pl.col("mid").cast(pl.Float64)
        else:
            raise ValueError("missing bid (and no mid fallback)")

    if "ask" in schema_names:
        ask_expr = pl.col("ask").cast(pl.Float64)
    elif "bid" in schema_names:
        ask_expr = pl.col("bid").cast(pl.Float64)
    else:
        ask_expr = pl.lit(None, dtype=pl.Float64)

    if "spread" in schema_names:
        spread_expr = pl.col("spread").cast(pl.Float64)
    elif "ask" in schema_names and "bid" in schema_names:
        spread_expr = (pl.col("ask") - pl.col("bid")).cast(pl.Float64)
    else:
        spread_expr = pl.lit(None, dtype=pl.Float64)

    return price_expr, ask_expr, spread_expr


def _empty_bar_frame(symbol: str) -> pl.DataFrame:
    return pl.DataFrame(
        schema={
            "timestamp": UTC_TS,
            "close_ts": UTC_TS,
            "open": pl.Float64,
            "high": pl.Float64,
            "low": pl.Float64,
            "close": pl.Float64,
            "ask": pl.Float64,
            "spread": pl.Float64,
            "tick_volume": pl.Int64,
            "high_pos_tick": pl.Int32,
            "low_pos_tick": pl.Int32,
            "hl_first": pl.Int8,
            "hl_pos_delta_tick": pl.Int32,
            "hl_pos_frac": pl.Float64,
            f"close_{symbol}": pl.Float64,
            f"ask_{symbol}": pl.Float64,
            f"spread_{symbol}": pl.Float64,
        }
    )


def _bars_from_ticks(
    df: pl.DataFrame, *, symbol: str, bar_ticks: int, start_tick_index: int
) -> tuple[pl.DataFrame, int, pl.DataFrame]:
    """Build fixed-size tick bars from a tick frame.

    Returns:
    - completed bars
    - updated global tick index
    - remainder ticks (< bar_ticks)
    """
    if df.height == 0:
        return _empty_bar_frame(symbol), start_tick_index, df

    n_complete = (df.height // bar_ticks) * bar_ticks
    if n_complete <= 0:
        return pl.DataFrame(), start_tick_index, df

    complete = df.slice(0, n_complete)
    remainder = df.slice(n_complete)

    complete = complete.with_row_index("row_idx").with_columns(
        ((pl.col("row_idx") + start_tick_index) // bar_ticks).cast(pl.Int64).alias("bar_id"),
        ((pl.col("row_idx") + start_tick_index) % bar_ticks).cast(pl.Int32).alias("bar_pos_tick"),
    )

    complete = complete.with_columns(
        pl.col("price").max().over("bar_id").alias("_bar_high"),
        pl.col("price").min().over("bar_id").alias("_bar_low"),
    )

    bars = (
        complete.group_by("bar_id", maintain_order=True)
        .agg(
            pl.col("timestamp").first().alias("timestamp"),
            pl.col("timestamp").last().alias("close_ts"),
            pl.col("price").first().alias("open"),
            pl.col("price").max().alias("high"),
            pl.col("price").min().alias("low"),
            pl.col("price").last().alias("close"),
            pl.col("ask").last().alias("ask"),
            pl.col("spread").mean().alias("spread"),
            pl.len().cast(pl.Int64).alias("tick_volume"),
            pl.when(pl.col("price") == pl.col("_bar_high"))
            .then(pl.col("bar_pos_tick"))
            .otherwise(None)
            .min()
            .cast(pl.Int32)
            .alias("high_pos_tick"),
            pl.when(pl.col("price") == pl.col("_bar_low"))
            .then(pl.col("bar_pos_tick"))
            .otherwise(None)
            .min()
            .cast(pl.Int32)
            .alias("low_pos_tick"),
        )
        .with_columns(
            pl.when(pl.col("high_pos_tick") < pl.col("low_pos_tick"))
            .then(pl.lit(1, dtype=pl.Int8))
            .when(pl.col("high_pos_tick") > pl.col("low_pos_tick"))
            .then(pl.lit(-1, dtype=pl.Int8))
            .otherwise(pl.lit(0, dtype=pl.Int8))
            .alias("hl_first"),
            (pl.col("low_pos_tick") - pl.col("high_pos_tick"))
            .cast(pl.Int32)
            .alias("hl_pos_delta_tick"),
            (
                (pl.col("low_pos_tick") - pl.col("high_pos_tick")).cast(pl.Float64)
                / float(max(1, int(bar_ticks) - 1))
            ).alias("hl_pos_frac"),
            pl.col("close").alias(f"close_{symbol}"),
            pl.col("ask").alias(f"ask_{symbol}"),
            pl.col("spread").alias(f"spread_{symbol}"),
        )
        .select(
            "timestamp",
            "close_ts",
            "open",
            "high",
            "low",
            "close",
            "ask",
            "spread",
            "tick_volume",
            "high_pos_tick",
            "low_pos_tick",
            "hl_first",
            "hl_pos_delta_tick",
            "hl_pos_frac",
            f"close_{symbol}",
            f"ask_{symbol}",
            f"spread_{symbol}",
        )
    )

    return bars, start_tick_index + n_complete, remainder


def _build_base_tick_bars(
    *,
    tick_root: Path,
    symbol: str,
    base_ticks: int,
    price_source: str,
    timestamp_mode: str,
) -> tuple[pl.DataFrame, int]:
    files = _symbol_files(tick_root, symbol)
    if not files:
        raise FileNotFoundError(f"{symbol}: no *_ticks.parquet files under {tick_root}")

    first_schema = pl.read_parquet_schema(str(files[0]))
    names = set(
        first_schema.names()
        if hasattr(first_schema, "names")
        else getattr(first_schema, "keys", lambda: [])()
    )
    if "timestamp" not in names:
        raise ValueError(f"{symbol}: missing timestamp")

    price_expr, ask_expr, spread_expr = _select_tick_exprs(names, price_source=price_source)

    carry = pl.DataFrame(
        schema={
            "timestamp": UTC_TS,
            "price": pl.Float64,
            "ask": pl.Float64,
            "spread": pl.Float64,
        }
    )
    chunks: list[pl.DataFrame] = []
    tick_idx = 0

    for fp in files:
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
        if carry.height:
            part = pl.concat([carry, part], how="vertical")

        bars, tick_idx, carry = _bars_from_ticks(
            part, symbol=symbol, bar_ticks=base_ticks, start_tick_index=tick_idx
        )
        if bars.height:
            chunks.append(bars)

    if not chunks:
        return pl.DataFrame(), int(carry.height)

    out = pl.concat(chunks, how="vertical").sort("timestamp")
    dropped_ticks = int(carry.height)
    return out, dropped_ticks


def _aggregate_from_base(
    base_bars: pl.DataFrame, *, symbol: str, target_ticks: int, base_ticks: int
) -> tuple[pl.DataFrame, int]:
    if target_ticks == base_ticks:
        return base_bars, 0

    if target_ticks < base_ticks or (target_ticks % base_ticks) != 0:
        raise ValueError(
            f"target_ticks={target_ticks} must be a multiple of base_ticks={base_ticks}"
        )

    factor = target_ticks // base_ticks
    n_complete = (base_bars.height // factor) * factor
    dropped_base_bars = int(base_bars.height - n_complete)
    if n_complete <= 0:
        return pl.DataFrame(), dropped_base_bars

    p = (
        base_bars.slice(0, n_complete)
        .with_row_index("row_idx")
        .with_columns(
            (pl.col("row_idx") // factor).cast(pl.Int64).alias("agg_id"),
            (pl.col("row_idx") % factor).cast(pl.Int32).alias("agg_child_idx"),
        )
        .with_columns(
            pl.col("high").max().over("agg_id").alias("_agg_high"),
            pl.col("low").min().over("agg_id").alias("_agg_low"),
        )
    )

    out = (
        p.group_by("agg_id", maintain_order=True)
        .agg(
            pl.col("timestamp").first().alias("timestamp"),
            pl.col("close_ts").last().alias("close_ts"),
            pl.col("open").first().alias("open"),
            pl.col("high").max().alias("high"),
            pl.col("low").min().alias("low"),
            pl.col("close").last().alias("close"),
            pl.col("ask").last().alias("ask"),
            pl.col("spread").mean().alias("spread"),
            pl.col("tick_volume").sum().cast(pl.Int64).alias("tick_volume"),
            pl.when(pl.col("high") == pl.col("_agg_high"))
            .then(pl.col("agg_child_idx") * int(base_ticks) + pl.col("high_pos_tick"))
            .otherwise(None)
            .min()
            .cast(pl.Int32)
            .alias("high_pos_tick"),
            pl.when(pl.col("low") == pl.col("_agg_low"))
            .then(pl.col("agg_child_idx") * int(base_ticks) + pl.col("low_pos_tick"))
            .otherwise(None)
            .min()
            .cast(pl.Int32)
            .alias("low_pos_tick"),
        )
        .with_columns(
            pl.when(pl.col("high_pos_tick") < pl.col("low_pos_tick"))
            .then(pl.lit(1, dtype=pl.Int8))
            .when(pl.col("high_pos_tick") > pl.col("low_pos_tick"))
            .then(pl.lit(-1, dtype=pl.Int8))
            .otherwise(pl.lit(0, dtype=pl.Int8))
            .alias("hl_first"),
            (pl.col("low_pos_tick") - pl.col("high_pos_tick"))
            .cast(pl.Int32)
            .alias("hl_pos_delta_tick"),
            (
                (pl.col("low_pos_tick") - pl.col("high_pos_tick")).cast(pl.Float64)
                / float(max(1, int(target_ticks) - 1))
            ).alias("hl_pos_frac"),
            pl.col("close").alias(f"close_{symbol}"),
            pl.col("ask").alias(f"ask_{symbol}"),
            pl.col("spread").alias(f"spread_{symbol}"),
        )
        .select(
            "timestamp",
            "close_ts",
            "open",
            "high",
            "low",
            "close",
            "ask",
            "spread",
            "tick_volume",
            "high_pos_tick",
            "low_pos_tick",
            "hl_first",
            "hl_pos_delta_tick",
            "hl_pos_frac",
            f"close_{symbol}",
            f"ask_{symbol}",
            f"spread_{symbol}",
        )
    )
    return out, dropped_base_bars


def _build_symbol(
    *,
    tick_root: Path,
    output_dir: Path,
    symbol: str,
    base_ticks: int,
    target_ticks: list[int],
    price_source: str,
    timestamp_mode: str,
    overwrite: bool,
) -> list[str]:
    msgs: list[str] = []

    existing = [output_dir / f"{symbol}_{n}tick.parquet" for n in target_ticks]
    if (not overwrite) and all(p.exists() for p in existing):
        return [f"skip {symbol}: all targets exist"]

    base, dropped_ticks = _build_base_tick_bars(
        tick_root=tick_root,
        symbol=symbol,
        base_ticks=base_ticks,
        price_source=price_source,
        timestamp_mode=timestamp_mode,
    )
    if base.height == 0:
        return [f"skip {symbol}: no complete {base_ticks}-tick bars"]

    output_dir.mkdir(parents=True, exist_ok=True)

    for t in target_ticks:
        out_path = output_dir / f"{symbol}_{t}tick.parquet"
        if out_path.exists() and not overwrite:
            msgs.append(f"skip {symbol} {t}tick: exists")
            continue

        bars, dropped_base = _aggregate_from_base(
            base,
            symbol=symbol,
            target_ticks=t,
            base_ticks=base_ticks,
        )
        if bars.height == 0:
            msgs.append(f"skip {symbol} {t}tick: empty after aggregation")
            continue

        bars.write_parquet(out_path)
        msgs.append(
            f"ok {symbol} {t}tick: {bars.height} bars -> {out_path} "
            f"(dropped_tail_base_bars={dropped_base}, dropped_tail_ticks={dropped_ticks})"
        )

    return msgs


def main() -> None:
    p = argparse.ArgumentParser(description="Build fixed-tick OHLC bars from raw tick parquet data")
    p.add_argument("--tick-root", default="/Users/danielfisher/Desktop/tick")
    p.add_argument("--output-dir", default="data/global_tickbars")
    p.add_argument(
        "--symbols",
        default="",
        help="Comma-separated symbols; default = all directories under tick root",
    )
    p.add_argument("--base-ticks", type=int, default=50, help="Base tick-bar size (default: 50)")
    p.add_argument(
        "--aggregate-multiples",
        default="1,2,4",
        help="Comma-separated multiples of base ticks (default: 1,2,4 -> 50,100,200 if base=50)",
    )
    p.add_argument(
        "--price-source", choices=["bid", "mid"], default="bid", help="OHLC source price"
    )
    p.add_argument(
        "--timestamp-mode",
        choices=["as_utc", "ny_local_tagged_utc"],
        default="as_utc",
        help="How to interpret raw tick timestamps before bar construction",
    )
    p.add_argument("--overwrite", action="store_true")
    args = p.parse_args()

    tick_root = Path(str(args.tick_root))
    output_dir = Path(str(args.output_dir))

    symbols = _parse_symbols(str(args.symbols))
    if not symbols:
        symbols = sorted([d.name for d in tick_root.iterdir() if d.is_dir()])

    base_ticks = int(args.base_ticks)
    if base_ticks <= 0:
        raise ValueError("--base-ticks must be > 0")

    multiples = sorted(set(_parse_int_list(str(args.aggregate_multiples))))
    if not multiples or any(m <= 0 for m in multiples):
        raise ValueError("--aggregate-multiples must contain positive integers")
    target_ticks = sorted(set([base_ticks * m for m in multiples]))

    print(
        f"building tick bars: symbols={len(symbols)}, base_ticks={base_ticks}, "
        f"targets={target_ticks}, price_source={args.price_source}, timestamp_mode={args.timestamp_mode}"
    )

    for sym in symbols:
        try:
            for msg in _build_symbol(
                tick_root=tick_root,
                output_dir=output_dir,
                symbol=sym,
                base_ticks=base_ticks,
                target_ticks=target_ticks,
                price_source=str(args.price_source),
                timestamp_mode=str(args.timestamp_mode),
                overwrite=bool(args.overwrite),
            ):
                print(msg)
        except Exception as e:
            print(f"fail {sym}: {e}")

    print("done")


if __name__ == "__main__":
    main()
