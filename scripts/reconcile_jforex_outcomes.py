#!/usr/bin/env python3
"""Reconcile runtime outcomes against governance selected signals.

Joins the month-scoped Governance Lock predictions with runtime events to
compute signal-coverage and outcome evidence per symbol. Independent label P&L
is reported as governance label evidence only; it is not expected runtime P&L.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import duckdb
import pandas as pd

DEFAULT_SYMBOLS = ("EURUSD", "GBPUSD", "USDJPY", "USDCHF", "AUDUSD", "USDCAD")


def parse_order_label_close_ts(label: str) -> datetime | None:
    """Extract the prediction bar close_ts from a JForex order label.

    Labels are formatted as: OCO_{sym}_T{ticks}_H{horizon}_TS{YYYYMMDDHHMMSS}_...
    The TS segment encodes the prediction bar close time in UTC.
    """
    m = re.search(r"_TS(\d{14})_", label)
    if not m:
        return None
    try:
        return datetime.strptime(m.group(1), "%Y%m%d%H%M%S").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def parse_predict_cycle_close_ts(detail: str) -> datetime | None:
    """Extract the replay close_ts from a predict_cycle detail string."""
    m = re.search(r"(?:^|;)close_ts=([^;]+)", str(detail))
    if not m:
        return None
    try:
        return datetime.fromisoformat(m.group(1).replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError:
        return None


def _parse_eval_ts(value: str) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


def _in_eval_window(
    ts: datetime | None, eval_start: datetime | None, eval_end: datetime | None
) -> bool:
    """Treat rows without replay close_ts as unfilterable and keep them for compatibility."""
    if ts is None:
        return True
    if eval_start is not None and ts < eval_start:
        return False
    return not (eval_end is not None and ts >= eval_end)


DEFAULT_LOCK_DIR = "configs/research/governance/oco_history_dukascopy_candidate/2025-07"
DEFAULT_RECONCILE_DIR = "data/analysis/backtest_reconcile"
MINIMAL_RUNTIME_EVENT_COLUMNS = ("event_name", "category", "pass", "detail")


def canonical_runtime_events_path(
    reconcile_dir: Path, symbol: str, *, events_prefix: str = "jforex"
) -> Path:
    return reconcile_dir / f"{symbol}_{events_prefix}_runtime_events.csv"


def load_runtime_events_frame(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise SystemExit(f"missing runtime events file: {path}")
    try:
        df = pd.read_csv(path)
    except (pd.errors.EmptyDataError, pd.errors.ParserError) as exc:
        raise SystemExit(f"runtime events file unreadable: {path}") from exc
    missing = [col for col in MINIMAL_RUNTIME_EVENT_COLUMNS if col not in df.columns]
    if missing:
        cols = ",".join(missing)
        raise SystemExit(f"runtime events file missing minimal required columns [{cols}]: {path}")
    return df


def load_historical_lock_status(lock_dir: Path, symbol: str) -> dict[str, str | bool]:
    path = lock_dir / f"{symbol.lower()}_oco_live_lock.json"
    if not path.exists():
        return {"historical_deployable": True, "non_deployable_reason": ""}
    try:
        lock = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"historical_deployable": True, "non_deployable_reason": ""}
    backtest = lock.get("historical_backtest", {})
    if not isinstance(backtest, dict):
        backtest = {}
    return {
        "historical_deployable": bool(backtest.get("deployable", True)),
        "non_deployable_reason": str(backtest.get("non_deployable_reason", "")).strip(),
    }


def load_state_universe_uids(lock_dir: Path, symbol: str) -> list[str]:
    """Extract canonical candidate_uids from the lock's state_universe."""
    path = lock_dir / f"{symbol.lower()}_oco_live_lock.json"
    if not path.exists():
        return []
    try:
        lock = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []
    universe = lock.get("state_universe", {})
    rows = universe.get("rows", []) if isinstance(universe, dict) else []
    uids: list[str] = []
    for row in rows:
        sym = str(row.get("symbol", symbol)).upper()
        bar_ticks = int(row.get("bar_ticks", 0))
        horizon = int(row.get("horizon", 0))
        state_id = str(row.get("state_id", ""))
        if bar_ticks and horizon and state_id:
            uids.append(f"oco|{sym}|{bar_ticks}|h{horizon}|{state_id}")
    return uids


def load_locked_predictions(
    lock_dir: Path,
    symbol: str,
    eval_start: str = "",
    eval_end: str = "",
    *,
    candidate_uids: list[str] | None = None,
) -> pd.DataFrame:
    """Load Governance Lock predictions for a symbol, filtered to selected_exec=1.

    Args:
        eval_start: Only include events with close_ts >= this UTC ISO-8601 timestamp (empty = all).
        eval_end:   Only include events with close_ts <  this UTC ISO-8601 timestamp (empty = all).
        candidate_uids: If provided, only include rows whose candidate_uid is in this list.
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
    if candidate_uids:
        placeholders = ", ".join(["?"] * len(candidate_uids))
        clauses += f" AND candidate_uid IN ({placeholders})"
        params.extend(candidate_uids)
    df = con.execute(
        "SELECT close_ts, candidate_uid, pred_prob, target_gross_pips, "
        "target_gross_pos, selected_exec, event_ordinal "
        f"FROM read_parquet(?) WHERE selected_exec = 1{clauses} "
        "ORDER BY close_ts, candidate_uid",
        params,
    ).fetchdf()
    con.close()
    return df


def load_runtime_events(
    reconcile_dir: Path,
    symbol: str,
    eval_start: str = "",
    eval_end: str = "",
    *,
    events_prefix: str = "jforex",
) -> dict:
    """Load and summarise JForex runtime events for a symbol.

    Returns a dict with aggregate counts:
      predict_cycles, orders_submitted, orders_filled, execution_failures,
      lifecycle_failures, lifecycle_violations, selected_count_total
    """
    path = canonical_runtime_events_path(Path(reconcile_dir), symbol, events_prefix=events_prefix)
    df = load_runtime_events_frame(path)
    eval_start_dt = _parse_eval_ts(eval_start)
    eval_end_dt = _parse_eval_ts(eval_end)

    predict_cycle_rows = df[df["event_name"] == "predict_cycle"].copy()
    if eval_start_dt is not None or eval_end_dt is not None:
        predict_cycle_rows = predict_cycle_rows.loc[
            predict_cycle_rows["detail"].apply(
                lambda detail: _in_eval_window(
                    parse_predict_cycle_close_ts(str(detail)),
                    eval_start_dt,
                    eval_end_dt,
                )
            )
        ]
    predict_cycles = len(predict_cycle_rows)

    order_submitted_rows = df[df["event_name"].isin(["order_submitted", "market_order_submitted"])].copy()
    if eval_start_dt is not None or eval_end_dt is not None:
        order_submitted_rows = order_submitted_rows.loc[
            order_submitted_rows["detail"]
            .astype(str)
            .apply(
                lambda detail: _in_eval_window(
                    parse_order_label_close_ts(detail.split(":")[0]),
                    eval_start_dt,
                    eval_end_dt,
                )
            )
        ]
    orders_submitted = len(order_submitted_rows)
    orders_filled = len(df[df["event_name"] == "order_filled"])
    execution_failures = len(
        df[
            (df["category"] == "execution")
            & (df["pass"].astype(str).str.strip().str.lower() == "false")
        ]
    )
    lifecycle_failures = len(df[df["event_name"] == "sibling_cancel_failure"])
    lifecycle_violations = len(df[df["event_name"] == "lifecycle_violation"])

    # Parse selected_count from predict_cycle detail strings
    selected_total = 0
    for detail in predict_cycle_rows["detail"]:
        for part in str(detail).split(";"):
            if part.startswith("selected_count="):
                selected_total += int(part.split("=")[1])

    # Per-event: extract unique group close_ts from order_submitted detail strings.
    # Detail format: "{groupLabel}:{legLabel}" — groupLabel encodes TS{YYYYMMDDHHMMSS}.
    submitted_close_ts: set = set()
    for detail in order_submitted_rows["detail"].astype(str):
        group_label = detail.split(":")[0]
        ts = parse_order_label_close_ts(group_label)
        if ts is not None:
            submitted_close_ts.add(ts)

    # Count UNIQUE broker positions that reached a terminal state (CLOSED or CANCELLED).
    # trade_update_synced detail format: "{brokerPosId}:{status}".
    # Deduplicate on brokerPosId so two legs from the same group don't double-count.
    completed_ids: set = set()
    for detail in df.loc[df["event_name"] == "trade_update_synced", "detail"].astype(str):
        if ":CLOSED" in detail or ":CANCELLED" in detail:
            completed_ids.add(detail.split(":")[0])
    completed_count = len(completed_ids)

    return {
        "predict_cycles": predict_cycles,
        "orders_submitted": orders_submitted,
        "orders_filled": orders_filled,
        "execution_failures": execution_failures,
        "lifecycle_failures": lifecycle_failures,
        "lifecycle_violations": lifecycle_violations,
        "selected_count_total": selected_total,
        "submitted_group_close_ts_count": len(submitted_close_ts),
        "completed_group_count": completed_count,
        "submitted_group_close_ts": sorted(submitted_close_ts),
    }


def compare_outcomes(
    symbol: str,
    governance_selected_signal_count: int,
    governance_independent_label_gross_pips_total: float,
    governance_independent_label_win_rate: float,
    runtime_predict_cycle_count: int,
    runtime_selected_signal_count: int,
    runtime_order_submitted_count: int,
    jforex_execution_failures: int,
    jforex_lifecycle_failures: int,
    signal_coverage_threshold: float = 0.8,
    runtime_submitted_group_count: int = 0,
) -> dict:
    """Compare runtime signal coverage against governance selected signals.

    Args:
        signal_coverage_threshold: minimum ratio of runtime_selected_signal_count /
            governance_selected_signal_count to consider signal coverage acceptable.
            Default 0.8 (80%).
        runtime_submitted_group_count: number of unique prediction bar close_ts values seen
            in order_submitted events (per-event order coverage).

    Returns:
        dict with per-check pass/fail and overall verdict.

    Notes:
        order_coverage_ratio is expected to be materially below 1.0 in live/tester runs.
        The OCO strategy allows only one open position at a time.  Once an order group is
        submitted, subsequent predict cycles that select candidates are counted in
        runtime_selected_signal_count (signal_coverage) but do NOT submit new orders while the
        position is live.  order_coverage_pass is therefore informational and is intentionally
        excluded from overall_pass.  signal_coverage_pass is the actionable gate.
    """
    # Order labels use BM_scan_... format which lacks parseable timestamps, so
    # runtime_order_submitted_count cannot be reliably scoped to the eval window.
    # runtime_selected_signal_count=0 is the authoritative idle signal (no predictions fired).
    zero_lock_clean_noop = (
        governance_selected_signal_count == 0 and runtime_selected_signal_count == 0
    )
    signal_coverage_ratio = (
        runtime_selected_signal_count / governance_selected_signal_count
        if governance_selected_signal_count > 0
        else 0.0
    )
    # Zero-lock windows are valid no-op windows if runtime also stayed idle.
    signal_coverage_pass = (
        zero_lock_clean_noop
        if governance_selected_signal_count == 0
        else signal_coverage_ratio >= signal_coverage_threshold
    )

    execution_clean_pass = jforex_execution_failures == 0 and jforex_lifecycle_failures == 0

    has_trades = runtime_order_submitted_count > 0

    # Per-event order coverage: unique group submissions vs distinct governance signals.
    order_coverage_ratio = (
        runtime_submitted_group_count / governance_selected_signal_count
        if governance_selected_signal_count > 0
        else 0.0
    )
    order_coverage_pass = (
        zero_lock_clean_noop
        if governance_selected_signal_count == 0
        else order_coverage_ratio >= signal_coverage_threshold
    )

    # signal_coverage_pass is the gate: did the model see the right events?
    # order_coverage_pass is informational: how many events resulted in orders (depressed by OCO blocking).
    overall_pass = execution_clean_pass and (
        zero_lock_clean_noop or (signal_coverage_pass and has_trades)
    )

    return {
        "symbol": symbol,
        "governance_selected_signal_count": governance_selected_signal_count,
        "governance_independent_label_gross_pips_total": round(
            governance_independent_label_gross_pips_total, 2
        ),
        "governance_independent_label_win_rate": round(governance_independent_label_win_rate, 4),
        "runtime_predict_cycle_count": runtime_predict_cycle_count,
        "runtime_selected_signal_count": runtime_selected_signal_count,
        "runtime_order_submitted_count": runtime_order_submitted_count,
        "runtime_submitted_group_count": runtime_submitted_group_count,
        "signal_coverage_ratio": round(signal_coverage_ratio, 4),
        "signal_coverage_pass": signal_coverage_pass,
        "execution_clean_pass": execution_clean_pass,
        "has_trades": has_trades,
        "order_coverage_ratio": round(order_coverage_ratio, 4),
        "order_coverage_pass": order_coverage_pass,
        "overall_pass": overall_pass,
        "historical_deployable": True,
        "non_deployable_reason": "",
    }


def non_deployable_result(symbol: str, events: dict, reason: str) -> dict:
    return {
        "symbol": symbol,
        "governance_selected_signal_count": 0,
        "governance_independent_label_gross_pips_total": 0.0,
        "governance_independent_label_win_rate": 0.0,
        "runtime_predict_cycle_count": int(events["predict_cycles"]),
        "runtime_selected_signal_count": int(events["selected_count_total"]),
        "runtime_order_submitted_count": int(events["orders_submitted"]),
        "runtime_submitted_group_count": int(events["submitted_group_close_ts_count"]),
        "signal_coverage_ratio": 0.0,
        "signal_coverage_pass": False,
        "execution_clean_pass": bool(
            int(events["execution_failures"]) == 0 and int(events["lifecycle_failures"]) == 0
        ),
        "has_trades": bool(int(events["orders_submitted"]) > 0),
        "order_coverage_ratio": 0.0,
        "order_coverage_pass": False,
        "overall_pass": False,
        "historical_deployable": False,
        "non_deployable_reason": str(reason).strip(),
        "lock_dir": "",
    }


def write_per_symbol_summaries(
    results: list[dict], out_dir: Path, *, events_prefix: str = "local_jforex"
) -> None:
    """Write one CSV per symbol for consumption by validate_local_jforex_surrogate.py.

    Adds an explicit 'jforex_outcome_parity_pass' column aliasing 'overall_pass'
    so the InputSource candidate column lookup is unambiguous.
    """
    for r in results:
        symbol = r["symbol"]
        row = dict(r)
        row["jforex_outcome_parity_pass"] = row["overall_pass"]
        prefix = str(events_prefix).strip() or "local_jforex"
        path = out_dir / f"{symbol}_{prefix}_outcome_parity_summary.csv"
        with open(path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=list(row.keys()))
            writer.writeheader()
            writer.writerow(row)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--symbols",
        default=",".join(DEFAULT_SYMBOLS),
        help="Comma-separated symbol list",
    )
    parser.add_argument("--lock-dir", default=DEFAULT_LOCK_DIR)
    parser.add_argument("--reconcile-dir", default=DEFAULT_RECONCILE_DIR)
    parser.add_argument(
        "--signal-coverage-threshold",
        type=float,
        default=0.8,
        help=(
            "Min ratio of runtime selected signals / governance selected signals "
            "(default: 0.8)"
        ),
    )
    parser.add_argument(
        "--out-csv",
        default="data/analysis/backtest_reconcile/jforex_outcome_parity_summary.csv",
        help="Output CSV path for per-symbol results",
    )
    parser.add_argument(
        "--eval-start",
        default="",
        help="Only include events with close_ts >= this UTC ISO-8601 timestamp (empty = all)",
    )
    parser.add_argument(
        "--eval-end",
        default="",
        help="Only include events with close_ts < this UTC ISO-8601 timestamp (empty = all)",
    )
    parser.add_argument(
        "--events-prefix",
        default="jforex",
        help="Runtime events file prefix (default: jforex → {SYMBOL}_jforex_runtime_events.csv)",
    )
    parser.add_argument(
        "--monitor-only",
        action="store_true",
        help="Write outcome evidence but exit 0 even when outcome parity fails.",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
    lock_dir = Path(args.lock_dir)
    reconcile_dir = Path(args.reconcile_dir)
    now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    results = []
    for symbol in symbols:
        events = load_runtime_events(
            reconcile_dir,
            symbol,
            eval_start=args.eval_start,
            eval_end=args.eval_end,
            events_prefix=args.events_prefix,
        )
        lock_status = load_historical_lock_status(lock_dir, symbol)
        if not bool(lock_status["historical_deployable"]):
            result = non_deployable_result(
                symbol=symbol,
                events=events,
                reason=str(lock_status["non_deployable_reason"]),
            )
            result["lock_dir"] = str(lock_dir)
            result["evaluated_at_utc"] = now_utc
            results.append(result)
            continue

        universe_uids = load_state_universe_uids(lock_dir, symbol)
        governance_selected = load_locked_predictions(
            lock_dir, symbol, eval_start=args.eval_start, eval_end=args.eval_end,
            candidate_uids=universe_uids or None,
        )

        governance_selected_signal_count = len(governance_selected)
        governance_independent_label_gross_pips_total = float(
            governance_selected["target_gross_pips"].sum()
        )
        governance_independent_label_win_rate = (
            float(governance_selected["target_gross_pos"].mean())
            if governance_selected_signal_count > 0
            else 0.0
        )

        result = compare_outcomes(
            symbol=symbol,
            governance_selected_signal_count=governance_selected_signal_count,
            governance_independent_label_gross_pips_total=governance_independent_label_gross_pips_total,
            governance_independent_label_win_rate=governance_independent_label_win_rate,
            runtime_predict_cycle_count=events["predict_cycles"],
            runtime_selected_signal_count=events["selected_count_total"],
            runtime_order_submitted_count=events["orders_submitted"],
            jforex_execution_failures=events["execution_failures"],
            jforex_lifecycle_failures=events["lifecycle_failures"],
            signal_coverage_threshold=args.signal_coverage_threshold,
            runtime_submitted_group_count=events["submitted_group_close_ts_count"],
        )
        result["historical_deployable"] = bool(lock_status["historical_deployable"])
        result["non_deployable_reason"] = str(lock_status["non_deployable_reason"]).strip()
        result["lock_dir"] = str(lock_dir)
        result["evaluated_at_utc"] = now_utc
        results.append(result)

    # Print summary table
    print(
        f"\n{'Symbol':<8} {'GovSig':>7} {'RunSig':>8} {'Coverage':>9} "
        f"{'Orders':>7} {'ExecOK':>7} {'Verdict':>8}"
    )
    print("-" * 62)
    for r in results:
        verdict = (
            "NO_GO"
            if not bool(r.get("historical_deployable", True))
            else ("PASS" if r["overall_pass"] else "FAIL")
        )
        coverage_txt = (
            "n/a"
            if not bool(r.get("historical_deployable", True))
            else f"{r['signal_coverage_ratio']:>8.1%}"
        )
        print(
            f"{r['symbol']:<8} {r['governance_selected_signal_count']:>7} "
            f"{r['runtime_selected_signal_count']:>8} {coverage_txt:>9} "
            f"{r['runtime_order_submitted_count']:>7} "
            f"{'yes' if r['execution_clean_pass'] else 'NO':>7} "
            f"{verdict:>8}"
        )
        if not bool(r.get("historical_deployable", True)):
            reason = str(r.get("non_deployable_reason", "")).strip()
            if reason:
                print(f"{'':<44} reason={reason}")

    write_per_symbol_summaries(results, out_dir=reconcile_dir, events_prefix=args.events_prefix)

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
    deployable_results = [r for r in results if bool(r.get("historical_deployable", True))]
    all_pass = all(r["overall_pass"] for r in deployable_results)
    if not all_pass:
        failing = [r["symbol"] for r in deployable_results if not r["overall_pass"]]
        print(f"\nFAILED symbols: {', '.join(failing)}")
        if not bool(args.monitor_only):
            sys.exit(1)
    elif deployable_results:
        print("\nAll symbols PASSED outcome parity.")
    else:
        print("\nNo deployable symbols required outcome parity.")


if __name__ == "__main__":
    main()
