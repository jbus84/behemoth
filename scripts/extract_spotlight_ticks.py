#!/usr/bin/env python3
"""Extract spotlight tick windows for fast JForex event-alignment testing.

For each symbol, finds all prediction events (selected_exec=1) for the given
model_month, then extracts the ticks that formed each event bar plus a small
warmup prefix. The resulting compact parquet (timestamp, bid, ask) is fed to
the local JForex surrogate with --warmup-ticks 0 --lookback-days 0 so every
tick lands in the stream bucket and bar closes happen at the exact original
timestamps.

This reduces per-symbol tick count from ~2-4M to tens of thousands, making
each symbol run in seconds rather than minutes.
"""

from __future__ import annotations

import argparse
import sys
from datetime import timezone
from pathlib import Path

DEFAULT_SYMBOLS = ("EURUSD", "GBPUSD", "USDJPY", "USDCHF", "AUDUSD", "USDCAD")
DEFAULT_MODEL_MONTH = "2025-07"
DEFAULT_PREDICTIONS_DIR = (
    "data/analysis/tick_opportunity_mining_dukascopy_candidate/wfo_2025_m3to1_oco_fullcap"
)
DEFAULT_TICK_ROOT = "/Users/danielfisher/Desktop/dukascopy_ticks"
DEFAULT_OUTPUT_DIR = "data/analysis/spotlight_ticks"
DEFAULT_PRE_BARS = 0
DEFAULT_BAR_TICKS = 100
# Evaluation window: only extract events whose close_ts falls within this range.
# Leave empty to extract events for the full model month.
DEFAULT_EVAL_START = "2025-07-07T00:00:00Z"
DEFAULT_EVAL_END = "2025-07-09T00:00:00Z"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbols", default=",".join(DEFAULT_SYMBOLS))
    parser.add_argument("--model-month", default=DEFAULT_MODEL_MONTH)
    parser.add_argument("--predictions-dir", default=DEFAULT_PREDICTIONS_DIR)
    parser.add_argument("--tick-root", default=DEFAULT_TICK_ROOT)
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--pre-bars", type=int, default=DEFAULT_PRE_BARS)
    parser.add_argument("--bar-ticks", type=int, default=DEFAULT_BAR_TICKS)
    parser.add_argument(
        "--eval-start",
        default=DEFAULT_EVAL_START,
        help="Only extract events with close_ts >= this UTC timestamp (ISO-8601). "
        "Leave empty to include all events in the model month.",
    )
    parser.add_argument(
        "--eval-end",
        default=DEFAULT_EVAL_END,
        help="Only extract events with close_ts < this UTC timestamp (ISO-8601). "
        "Leave empty to include all events in the model month.",
    )
    parser.add_argument(
        "--max-events",
        type=int,
        default=0,
        help="Cap the number of events extracted per symbol (0 = no limit). "
        "Use to keep tick counts manageable for dense symbols like USDJPY.",
    )
    parser.add_argument(
        "--lock-dir",
        default="",
        help="Directory containing locked prediction parquets "
        "({lock_dir}/{symbol.lower()}_oco_locked_predictions.parquet). "
        "When set, uses locked predictions as the event source instead of "
        "monthly predictions — eliminates wrong-candidate cursor contamination.",
    )
    return parser.parse_args()


def _tick_files(tick_root: Path, symbol: str) -> list[Path]:
    sym_dir = tick_root / symbol
    files = sorted(sym_dir.glob("*.parquet"))
    if not files:
        raise FileNotFoundError(f"No parquet files found under {sym_dir}")
    return files


def _extract_symbol(
    symbol: str,
    pred_path: Path,
    tick_files: list[Path],
    model_month: str,
    pre_bars: int,
    bar_ticks: int,
    output_path: Path,
    eval_start: str = "",
    eval_end: str = "",
    max_events: int = 0,
) -> None:
    import duckdb  # local import — only needed at runtime

    window = (pre_bars + 1) * bar_ticks
    con = duckdb.connect()

    # ── Step 1: load unique close_ts values (converted to naive UTC) ─────────
    # Build optional eval-window clauses (timestamps compared after UTC conversion)
    eval_clauses = ""
    eval_params: list = [str(pred_path), model_month]
    if eval_start:
        eval_clauses += " AND close_ts::TIMESTAMPTZ >= ?::TIMESTAMPTZ"
        eval_params.append(eval_start)
    if eval_end:
        eval_clauses += " AND close_ts::TIMESTAMPTZ < ?::TIMESTAMPTZ"
        eval_params.append(eval_end)

    limit_clause = f"LIMIT {max_events}" if max_events > 0 else ""
    raw_events = con.execute(
        f"""
        SELECT DISTINCT close_ts::TIMESTAMPTZ
        FROM read_parquet(?)
        WHERE test_month = ? AND selected_exec = 1{eval_clauses}
        ORDER BY 1
        {limit_clause}
        """,
        eval_params,
    ).fetchall()

    if not raw_events:
        print(
            f"[spotlight] {symbol}: no selected_exec=1 events for {model_month}, skipping",
            file=sys.stderr,
        )
        return

    # Convert timezone-aware timestamps to naive UTC datetimes for comparison
    # with the tick parquet timestamps (which are stored as naive UTC).
    event_ts_utc = [
        r[0].astimezone(timezone.utc).replace(tzinfo=None) for r in raw_events
    ]
    n_events = len(event_ts_utc)
    min_event = min(event_ts_utc)
    max_event = max(event_ts_utc)

    # ── Step 2: build row-numbered tick table for the relevant range ─────────
    # Add a 5-day buffer before the earliest event to ensure pre_bars warmup
    # ticks are available even for the very first event.
    from datetime import timedelta

    range_start = min_event - timedelta(days=5)

    tick_list = "[" + ", ".join(f"'{f}'" for f in tick_files) + "]"

    con.execute(
        f"""
        CREATE TEMP TABLE _ticks AS
        SELECT
            timestamp,
            bid,
            ask,
            ROW_NUMBER() OVER (ORDER BY timestamp) AS rn
        FROM read_parquet({tick_list})
        WHERE timestamp >= ? AND timestamp <= ?
        """,
        [range_start, max_event],
    )

    total_ticks_in_range = con.execute("SELECT COUNT(*) FROM _ticks").fetchone()[0]
    if total_ticks_in_range == 0:
        print(
            f"[spotlight] {symbol}: no ticks found in range {range_start} .. {max_event}",
            file=sys.stderr,
        )
        return

    # ── Step 3: match events to tick row numbers ─────────────────────────────
    con.execute("CREATE TEMP TABLE _events (close_ts TIMESTAMP)")
    con.executemany("INSERT INTO _events VALUES (?)", [(ts,) for ts in event_ts_utc])

    # For each event, find the row number of the last tick <= close_ts.
    # (The bar closes at tick N whose timestamp == close_ts, but we use MAX
    # to be safe in case of sub-microsecond rounding from timezone conversion.)
    con.execute(
        """
        CREATE TEMP TABLE _event_rns AS
        SELECT e.close_ts, MAX(t.rn) AS event_rn
        FROM _events e
        JOIN _ticks t ON t.timestamp <= e.close_ts
        GROUP BY e.close_ts
        """
    )

    n_matched = con.execute("SELECT COUNT(*) FROM _event_rns").fetchone()[0]
    if n_matched == 0:
        print(
            f"[spotlight] {symbol}: could not match any events to ticks", file=sys.stderr
        )
        return

    # ── Step 4: range-join to collect the tick windows ───────────────────────
    df = con.execute(
        f"""
        SELECT DISTINCT t.timestamp, t.bid, t.ask
        FROM _ticks t
        INNER JOIN _event_rns er
            ON t.rn BETWEEN er.event_rn - {window - 1} AND er.event_rn
        ORDER BY t.timestamp
        """
    ).fetchdf()

    if df.empty:
        print(
            f"[spotlight] {symbol}: range join produced no rows", file=sys.stderr
        )
        return

    # ── Step 5: write output ─────────────────────────────────────────────────
    output_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(str(output_path), index=False)

    first_ts = df["timestamp"].iloc[0]
    last_ts = df["timestamp"].iloc[-1]
    print(
        f"[spotlight] {symbol}: {n_events} events, {n_matched} matched, "
        f"{len(df):,} ticks  [{first_ts} .. {last_ts}]"
    )


def main() -> None:
    args = _parse_args()
    symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
    if not symbols:
        raise SystemExit("No symbols provided")

    tick_root = Path(args.tick_root)
    predictions_dir = Path(args.predictions_dir)
    output_dir = Path(args.output_dir)

    failures: list[str] = []
    for symbol in symbols:
        # Resolve event source: locked predictions (preferred) or monthly predictions
        lock_dir = Path(args.lock_dir) if args.lock_dir.strip() else None
        if lock_dir is not None:
            pred_path = lock_dir / f"{symbol.lower()}_oco_locked_predictions.parquet"
        else:
            pred_path = predictions_dir / f"{symbol}_oco_monthly_predictions.parquet"

        if not pred_path.exists():
            print(f"[spotlight] {symbol}: predictions file not found: {pred_path}", file=sys.stderr)
            failures.append(symbol)
            continue

        try:
            files = _tick_files(tick_root, symbol)
        except FileNotFoundError as exc:
            print(f"[spotlight] {symbol}: {exc}", file=sys.stderr)
            failures.append(symbol)
            continue

        output_path = output_dir / symbol / "spotlight_ticks.parquet"
        try:
            _extract_symbol(
                symbol=symbol,
                pred_path=pred_path,
                tick_files=files,
                model_month=args.model_month,
                pre_bars=args.pre_bars,
                bar_ticks=args.bar_ticks,
                output_path=output_path,
                eval_start=args.eval_start,
                eval_end=args.eval_end,
                max_events=args.max_events,
            )
        except Exception as exc:
            import traceback
            print(f"[spotlight] {symbol}: extraction failed: {exc}", file=sys.stderr)
            traceback.print_exc(file=sys.stderr)
            failures.append(symbol)

    if failures:
        raise SystemExit(f"Extraction failed for: {', '.join(failures)}")


if __name__ == "__main__":
    main()
