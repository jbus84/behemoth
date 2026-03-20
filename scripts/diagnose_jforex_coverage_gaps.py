#!/usr/bin/env python3
"""Diagnose JForex tester warmup-gap coverage issues per symbol.

For each symbol, compares the audit_logs first-seen timestamp against locked
predictions to quantify how many predictions fall in the warmup window and
what coverage would be under a range of candidate eval_start values.

Run before and after the start_ts fix to verify warmup_gap drops to 0.

Usage:
    uv run python scripts/diagnose_jforex_coverage_gaps.py

Output: console table — no files written.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import duckdb


DEFAULT_SYMBOLS = ("EURUSD", "GBPUSD", "USDJPY", "USDCHF", "AUDUSD", "USDCAD")
DEFAULT_LOCK_DIR = Path("configs/research/governance/oco_history_dukascopy_candidate/2025-07")
DEFAULT_STATE_DB_DIR = Path("data/analysis/backtest_reconcile/runtime")
DEFAULT_EVAL_START = "2025-07-07T00:00:00Z"
DEFAULT_EVAL_END = "2025-07-09T00:00:00Z"
CANDIDATE_EVAL_STARTS = [
    "2025-07-07T00:00:00Z",
    "2025-07-07T08:00:00Z",
    "2025-07-07T10:00:00Z",
    "2025-07-07T12:00:00Z",
    "2025-07-07T14:00:00Z",
]


def load_audit_log_timestamps(db_path: Path, eval_end: str) -> list[datetime]:
    """Return all audit_log close_ts values with close_ts < eval_end, as UTC datetimes."""
    if not db_path.exists():
        return []
    con = duckdb.connect(str(db_path), read_only=True)
    rows = con.execute(
        "SELECT close_ts AT TIME ZONE 'UTC' FROM audit_logs "
        "WHERE close_ts::TIMESTAMPTZ < ?::TIMESTAMPTZ",
        [eval_end],
    ).fetchall()
    con.close()
    return [
        r[0].replace(tzinfo=timezone.utc) if r[0].tzinfo is None else r[0].astimezone(timezone.utc)
        for r in rows
    ]


def warmup_gap_count(locked_close_ts: list[datetime], warmup_cutoff: datetime) -> int:
    """Count locked predictions with close_ts strictly before warmup_cutoff."""
    return sum(1 for ts in locked_close_ts if ts < warmup_cutoff)


def post_warmup_coverage(jforex_selected_total: int, locked_after_cutoff: int) -> float:
    """signal_coverage_ratio = jforex_selected_total / locked_after_cutoff.

    May exceed 1.0 when jforex_selected_total includes warmup-period selections
    that are excluded from locked_after_cutoff (not a bug — just reported as-is).
    """
    if locked_after_cutoff == 0:
        return 0.0
    return jforex_selected_total / locked_after_cutoff


def _load_locked_close_ts(lock_dir: Path, symbol: str, eval_start: str, eval_end: str) -> list[datetime]:
    path = lock_dir / f"{symbol.lower()}_oco_locked_predictions.parquet"
    con = duckdb.connect()
    rows = con.execute(
        "SELECT close_ts AT TIME ZONE 'UTC' FROM read_parquet(?) "
        "WHERE selected_exec = 1 "
        "AND close_ts::TIMESTAMPTZ >= ?::TIMESTAMPTZ "
        "AND close_ts::TIMESTAMPTZ < ?::TIMESTAMPTZ",
        [str(path), eval_start, eval_end],
    ).fetchall()
    con.close()
    return [
        r[0].replace(tzinfo=timezone.utc) if r[0].tzinfo is None else r[0].astimezone(timezone.utc)
        for r in rows
    ]


def main() -> None:
    print(f"\n{'Symbol':<8} {'first_seen_utc':<22} {'gap':>5}", end="")
    for es in CANDIDATE_EVAL_STARTS:
        label = es[11:16]
        print(f"  cov@{label}", end="")
    print()
    print("-" * (8 + 22 + 5 + len(CANDIDATE_EVAL_STARTS) * 11))

    for symbol in DEFAULT_SYMBOLS:
        db_path = DEFAULT_STATE_DB_DIR / f"{symbol.lower()}_jforex_dukascopy_state.db"
        audit_ts = load_audit_log_timestamps(db_path, DEFAULT_EVAL_END)
        first_seen = min(audit_ts) if audit_ts else None
        # len(audit_ts) matches jforex_selected_total from the runtime CSV because each
        # audit_log row corresponds to exactly one selected_exec=1 API call. Verified
        # against the runtime CSV counts for all 6 symbols in the 2026-03-20 run.
        jforex_selected = len(audit_ts)

        locked_full = _load_locked_close_ts(DEFAULT_LOCK_DIR, symbol, DEFAULT_EVAL_START, DEFAULT_EVAL_END)
        gap = warmup_gap_count(locked_full, first_seen) if first_seen else len(locked_full)

        first_seen_str = first_seen.strftime("%Y-%m-%d %H:%M") if first_seen else "N/A"
        print(f"{symbol:<8} {first_seen_str:<22} {gap:>5}", end="")

        for es in CANDIDATE_EVAL_STARTS:
            locked_after = _load_locked_close_ts(DEFAULT_LOCK_DIR, symbol, es, DEFAULT_EVAL_END)
            ratio = post_warmup_coverage(jforex_selected, len(locked_after))
            print(f"  {ratio:>9.1%}", end="")
        print()

    print(f"\nNote: cov@HH:MM = jforex_selected / locked_count with eval_start=HH:MM UTC on 2025-07-07")
    print("      ratio > 1.0 is expected when jforex_selected includes warmup-period selections")
    print("      After the start_ts fix: gap=0 and cov@00:00=100% for all symbols")


if __name__ == "__main__":
    main()
