#!/usr/bin/env python3
"""Reconcile JForex runtime outcomes against locked Python backtest predictions.

Joins the governance-locked predictions (ground truth) with JForex runtime events
to compute aggregate outcome metrics per symbol and produce a pass/fail verdict.
"""
from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

import duckdb
import pandas as pd


DEFAULT_SYMBOLS = ("EURUSD", "GBPUSD", "USDJPY", "USDCHF", "AUDUSD", "USDCAD")
DEFAULT_LOCK_DIR = "configs/research/governance/oco_history_dukascopy_candidate/2025-07"
DEFAULT_RECONCILE_DIR = "data/analysis/backtest_reconcile"


def load_locked_predictions(
    lock_dir: Path,
    symbol: str,
    eval_start: str = "",
    eval_end: str = "",
) -> pd.DataFrame:
    """Load locked predictions for a symbol, filtered to selected_exec=1.

    Args:
        eval_start: Only include events with close_ts >= this UTC ISO-8601 timestamp (empty = all).
        eval_end:   Only include events with close_ts <  this UTC ISO-8601 timestamp (empty = all).
    """
    path = lock_dir / f"{symbol.lower()}_oco_locked_predictions.parquet"
    con = duckdb.connect()
    clauses = ""
    params: list = [str(path)]
    if eval_start:
        clauses += " AND close_ts::TIMESTAMPTZ >= ?::TIMESTAMPTZ"
        params.append(eval_start)
    if eval_end:
        clauses += " AND close_ts::TIMESTAMPTZ < ?::TIMESTAMPTZ"
        params.append(eval_end)
    df = con.execute(
        "SELECT close_ts, candidate_uid, pred_prob, target_gross_pips, "
        "target_gross_pos, selected_exec, event_ordinal "
        f"FROM read_parquet(?) WHERE selected_exec = 1{clauses} "
        "ORDER BY close_ts, candidate_uid",
        params,
    ).fetchdf()
    con.close()
    return df


def load_runtime_events(reconcile_dir: Path, symbol: str) -> dict:
    """Load and summarise JForex runtime events for a symbol.

    Returns a dict with aggregate counts:
      predict_cycles, orders_submitted, orders_filled, execution_failures,
      lifecycle_failures, lifecycle_violations, selected_count_total
    """
    candidates = list(reconcile_dir.glob(f"{symbol}_*_runtime_events.csv"))
    if not candidates:
        return {
            "predict_cycles": 0, "orders_submitted": 0, "orders_filled": 0,
            "execution_failures": 0, "lifecycle_failures": 0, "lifecycle_violations": 0,
            "selected_count_total": 0,
        }
    path = candidates[0]
    df = pd.read_csv(path)

    predict_cycles = len(df[df["event_name"] == "predict_cycle"])
    orders_submitted = len(df[df["event_name"] == "order_submitted"])
    orders_filled = len(df[df["event_name"] == "order_filled"])
    execution_failures = len(df[
        (df["category"] == "execution") & (df["pass"].astype(str) == "false")
    ])
    lifecycle_failures = len(df[df["event_name"] == "sibling_cancel_failure"])
    lifecycle_violations = len(df[df["event_name"] == "lifecycle_violation"])

    # Parse selected_count from predict_cycle detail strings
    selected_total = 0
    for detail in df.loc[df["event_name"] == "predict_cycle", "detail"]:
        for part in str(detail).split(";"):
            if part.startswith("selected_count="):
                selected_total += int(part.split("=")[1])
    return {
        "predict_cycles": predict_cycles,
        "orders_submitted": orders_submitted,
        "orders_filled": orders_filled,
        "execution_failures": execution_failures,
        "lifecycle_failures": lifecycle_failures,
        "lifecycle_violations": lifecycle_violations,
        "selected_count_total": selected_total,
    }


def compare_outcomes(
    symbol: str,
    locked_count: int,
    locked_gross_pips_total: float,
    locked_win_rate: float,
    jforex_predict_cycles: int,
    jforex_selected_total: int,
    jforex_orders_submitted: int,
    jforex_execution_failures: int,
    jforex_lifecycle_failures: int,
    signal_coverage_threshold: float = 0.8,
) -> dict:
    """Compare JForex outcomes against locked Python backtest predictions.

    Args:
        signal_coverage_threshold: minimum ratio of jforex_selected_total / locked_count
            to consider signal coverage acceptable. Default 0.8 (80%).

    Returns:
        dict with per-check pass/fail and overall verdict.
    """
    signal_coverage_ratio = (
        jforex_selected_total / locked_count if locked_count > 0 else 0.0
    )
    signal_coverage_pass = signal_coverage_ratio >= signal_coverage_threshold

    execution_clean_pass = (
        jforex_execution_failures == 0 and jforex_lifecycle_failures == 0
    )

    has_trades = jforex_orders_submitted > 0

    overall_pass = signal_coverage_pass and execution_clean_pass and has_trades

    return {
        "symbol": symbol,
        "locked_selected_count": locked_count,
        "locked_gross_pips_total": round(locked_gross_pips_total, 2),
        "locked_win_rate": round(locked_win_rate, 4),
        "jforex_predict_cycles": jforex_predict_cycles,
        "jforex_selected_total": jforex_selected_total,
        "jforex_orders_submitted": jforex_orders_submitted,
        "signal_coverage_ratio": round(signal_coverage_ratio, 4),
        "signal_coverage_pass": signal_coverage_pass,
        "execution_clean_pass": execution_clean_pass,
        "has_trades": has_trades,
        "overall_pass": overall_pass,
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--symbols", default=",".join(DEFAULT_SYMBOLS),
        help="Comma-separated symbol list",
    )
    parser.add_argument("--lock-dir", default=DEFAULT_LOCK_DIR)
    parser.add_argument("--reconcile-dir", default=DEFAULT_RECONCILE_DIR)
    parser.add_argument(
        "--signal-coverage-threshold", type=float, default=0.8,
        help="Min ratio of JForex selected predictions / locked predictions (default: 0.8)",
    )
    parser.add_argument(
        "--out-csv", default="data/analysis/backtest_reconcile/jforex_outcome_parity_summary.csv",
        help="Output CSV path for per-symbol results",
    )
    parser.add_argument("--eval-start", default="", help="Only include events with close_ts >= this UTC ISO-8601 timestamp (empty = all)")
    parser.add_argument("--eval-end", default="", help="Only include events with close_ts < this UTC ISO-8601 timestamp (empty = all)")
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
    lock_dir = Path(args.lock_dir)
    reconcile_dir = Path(args.reconcile_dir)

    results = []
    for symbol in symbols:
        locked = load_locked_predictions(lock_dir, symbol, eval_start=args.eval_start, eval_end=args.eval_end)
        events = load_runtime_events(reconcile_dir, symbol)

        locked_count = len(locked)
        locked_gross_total = float(locked["target_gross_pips"].sum())
        locked_win_rate = (
            float(locked["target_gross_pos"].mean()) if locked_count > 0 else 0.0
        )

        result = compare_outcomes(
            symbol=symbol,
            locked_count=locked_count,
            locked_gross_pips_total=locked_gross_total,
            locked_win_rate=locked_win_rate,
            jforex_predict_cycles=events["predict_cycles"],
            jforex_selected_total=events["selected_count_total"],
            jforex_orders_submitted=events["orders_submitted"],
            jforex_execution_failures=events["execution_failures"],
            jforex_lifecycle_failures=events["lifecycle_failures"],
            signal_coverage_threshold=args.signal_coverage_threshold,
        )
        results.append(result)

    # Print summary table
    print(f"\n{'Symbol':<8} {'Locked':>7} {'JFX Sel':>8} {'Coverage':>9} "
          f"{'Orders':>7} {'ExecOK':>7} {'Verdict':>8}")
    print("-" * 62)
    for r in results:
        verdict = "PASS" if r["overall_pass"] else "FAIL"
        print(
            f"{r['symbol']:<8} {r['locked_selected_count']:>7} "
            f"{r['jforex_selected_total']:>8} {r['signal_coverage_ratio']:>8.1%} "
            f"{r['jforex_orders_submitted']:>7} "
            f"{'yes' if r['execution_clean_pass'] else 'NO':>7} "
            f"{verdict:>8}"
        )

    # Write CSV
    out_path = Path(args.out_csv)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    keys = results[0].keys() if results else []
    with open(out_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=keys)
        writer.writeheader()
        writer.writerows(results)
    print(f"\nResults written to {out_path}")

    # Exit code
    all_pass = all(r["overall_pass"] for r in results)
    if not all_pass:
        failing = [r["symbol"] for r in results if not r["overall_pass"]]
        print(f"\nFAILED symbols: {', '.join(failing)}")
        sys.exit(1)
    else:
        print("\nAll symbols PASSED outcome parity.")


if __name__ == "__main__":
    main()
