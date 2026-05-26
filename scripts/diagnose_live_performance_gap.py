#!/usr/bin/env python3
"""Diagnose why live OCO win rate deviates from reduced-core WFO backtest.

Queries a checkpointed live_state.db and produces a structured report
covering four hypotheses:
  1. Win rate per symbol vs expectation
  2. Threshold schedule: is the system using static fallback vs rolling?
  3. pnl_pips magnitude: are winners/losers the right size?
  4. Candidate UID audit: are the right state candidates firing?

Usage:
    python scripts/diagnose_live_performance_gap.py \
        --db data/analysis/backtest_reconcile/runtime/live_state.db \
        --run-id jforex_live \
        --out data/analysis/live_perf_gap_report.md
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import duckdb

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.behemoth.core.bundle_paths import lock_filename  # noqa: E402

# Reduced-core backtest win rates from WFO eval 2025 (locked states only).
# Update these from: data/analysis/tick_opportunity_mining_dukascopy_candidate/
#                    wfo_m3to1_oco_fullcap/<SYM>_oco_events_eval2025.parquet
# filtered to split='eval', bar_ticks=100, horizon=6, and the locked state_id.
REDUCED_CORE_EXPECTED_WIN_RATE = {
    "GBPUSD": 67.6,  # oco_first_touch__ny_overlap__k2
    "USDJPY": 72.1,  # oco_first_touch__high_abs_vel_q80__k2
    "USDCHF": 60.8,  # avg of two locked states
    "USDCAD": 63.3,  # oco_first_touch__ny_overlap__k2
    "AUDUSD": 59.2,  # avg of two locked states
    "EURUSD": 0.0,  # not live yet
}

# Governance lock paths for threshold schedule check
LOCK_DIR = Path("configs/research/governance/oco")
MODEL_DIR = Path("models/oco")
MIN_UNIQUE_PROBS_FLAG = 10


def _load_con(db_path: Path) -> duckdb.DuckDBPyConnection:
    return duckdb.connect(str(db_path), read_only=True)


def _win_rate_section(con: duckdb.DuckDBPyConnection, run_id: str) -> list[dict[str, Any]]:
    """Win rate, expected win rate, and z-score per symbol."""
    import math

    rows = con.execute(
        """
        SELECT
            symbol,
            COUNT(*) AS closed_trades,
            COUNT(CASE WHEN pnl_pips > 0 THEN 1 END) AS wins,
            ROUND(100.0 * COUNT(CASE WHEN pnl_pips > 0 THEN 1 END) / COUNT(*), 1) AS win_rate_pct,
            ROUND(SUM(pnl_pips), 2) AS total_pips,
            ROUND(AVG(pnl_pips), 3) AS avg_pips
        FROM trades
        WHERE status = 'CLOSED' AND run_id = ?
        GROUP BY symbol
        ORDER BY symbol
    """,
        [run_id],
    ).fetchall()

    results = []
    for symbol, n, wins, live_pct, total_pips, avg_pips in rows:
        expected = REDUCED_CORE_EXPECTED_WIN_RATE.get(symbol, 0.0)
        p = expected / 100.0
        z = float("nan")
        if n > 0 and 0 < p < 1:
            z = (wins - n * p) / math.sqrt(n * p * (1 - p))
        results.append(
            {
                "symbol": symbol,
                "closed_trades": n,
                "wins": wins,
                "win_rate_pct": live_pct,
                "expected_win_rate_pct": expected,
                "delta_pp": round(live_pct - expected, 1),
                "z_score": round(z, 2) if not math.isnan(z) else None,
                "total_pips": total_pips,
                "avg_pips": avg_pips,
                "flag": z < -2.0 if not math.isnan(z) else False,
            }
        )
    return results


def _threshold_analysis_section(
    con: duckdb.DuckDBPyConnection, run_id: str
) -> list[dict[str, Any]]:
    """Check whether today's predictions used a rolling threshold or static fallback.

    A single unique threshold value across many events is a strong signal the
    system is using the static fallback (schedule date missing from JSON).
    """
    rows = con.execute(
        """
        SELECT
            symbol,
            model_month,
            COUNT(*) AS scored_events,
            COUNT(DISTINCT ROUND(threshold, 6)) AS unique_thresholds,
            ROUND(MIN(threshold), 6) AS min_threshold,
            ROUND(MAX(threshold), 6) AS max_threshold,
            ROUND(AVG(pred_prob), 4) AS avg_pred_prob,
            ROUND(MIN(pred_prob), 4) AS min_pred_prob,
            ROUND(MAX(pred_prob), 4) AS max_pred_prob,
            ROUND(AVG(pred_prob) - AVG(threshold), 4) AS avg_margin_above_threshold
        FROM audit_logs
        WHERE run_id = ?
        GROUP BY symbol, model_month
        ORDER BY symbol
    """,
        [run_id],
    ).fetchall()

    results = []
    for (
        symbol,
        model_month,
        scored,
        unique_thr,
        min_thr,
        max_thr,
        avg_prob,
        min_prob,
        max_prob,
        avg_margin,
    ) in rows:
        # Check if today's date is in the threshold schedule
        schedule_has_today = False
        static_threshold = None
        lock_path = LOCK_DIR / lock_filename(symbol)
        if lock_path.exists():
            lock = json.loads(lock_path.read_text())
            artifacts = lock.get("artifacts", {})
            entry = artifacts.get("model_threshold_json", {})
            thr_json_txt = str(entry.get("path", "")).strip()
            if thr_json_txt:
                thr_json_path = lock_path.parent / thr_json_txt
                if thr_json_path.exists():
                    thr_cfg = json.loads(thr_json_path.read_text())
                    today_str = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")
                    schedule_has_today = today_str in thr_cfg.get("threshold_schedule", {})
                    static_threshold = thr_cfg.get("threshold_exec")

        results.append(
            {
                "symbol": symbol,
                "model_month": model_month,
                "scored_events": scored,
                "unique_thresholds": unique_thr,
                "min_threshold": min_thr,
                "max_threshold": max_thr,
                "avg_pred_prob": avg_prob,
                "min_pred_prob": min_prob,
                "max_pred_prob": max_prob,
                "avg_margin_above_threshold": avg_margin,
                "schedule_has_today": schedule_has_today,
                "static_threshold_value": static_threshold,
                "flag": unique_thr == 1 and not schedule_has_today,
            }
        )
    return results


def _magnitude_analysis_section(
    con: duckdb.DuckDBPyConnection, run_id: str
) -> list[dict[str, Any]]:
    """Report live pnl_pips distribution per symbol.

    OCO uses from_touch hold mode: pnl = side*(close[touch+horizon] - ref)/pip - barrier_pips.
    This means winners and losers are NOT bounded by barrier_pips — they reflect how far price
    moves during the holding period after the barrier is touched. The only valid sanity checks
    are structural: avg_pips should be negative (barrier cost dominates random walks), and the
    sign distribution must match the win rate. Compare avg_winner_pips / avg_loser_pips against
    the backtest mean_gross_pips_train for the same candidate to detect magnitude drift.
    """
    rows = con.execute(
        """
        SELECT
            symbol,
            candidate_uid,
            COUNT(*) AS n_closed,
            COUNT(CASE WHEN pnl_pips > 0 THEN 1 END) AS n_winners,
            COUNT(CASE WHEN pnl_pips <= 0 THEN 1 END) AS n_losers,
            ROUND(AVG(pnl_pips), 3) AS avg_pips,
            ROUND(AVG(CASE WHEN pnl_pips > 0 THEN pnl_pips END), 3) AS avg_winner_pips,
            ROUND(AVG(CASE WHEN pnl_pips <= 0 THEN pnl_pips END), 3) AS avg_loser_pips,
            ROUND(MAX(pnl_pips), 3) AS max_winner_pips,
            ROUND(MIN(pnl_pips), 3) AS min_loser_pips,
            ROUND(STDDEV(pnl_pips), 3) AS stddev_pips
        FROM trades
        WHERE status = 'CLOSED' AND run_id = ?
        GROUP BY symbol, candidate_uid
        ORDER BY symbol
    """,
        [run_id],
    ).fetchall()

    results = []
    for (
        symbol,
        candidate_uid,
        n_closed,
        n_win,
        n_lose,
        avg_pips,
        avg_win,
        avg_lose,
        max_win,
        min_lose,
        stddev,
    ) in rows:
        results.append(
            {
                "symbol": symbol,
                "candidate_uid": candidate_uid,
                "n_closed": n_closed,
                "n_winners": n_win,
                "n_losers": n_lose,
                "avg_pips": avg_pips,
                "avg_winner_pips": avg_win,
                "avg_loser_pips": avg_lose,
                "max_winner_pips": max_win,
                "min_loser_pips": min_lose,
                "stddev_pips": stddev,
                "flag": False,  # no automated flag — compare manually vs backtest mean_gross_pips_train
            }
        )
    return results


def _candidate_audit_section(con: duckdb.DuckDBPyConnection, run_id: str) -> list[dict[str, Any]]:
    """Check which candidate_uids are actually firing in live.

    All live trades should have candidate_uids matching the locked state_universe.
    Unexpected candidates suggest a governance config mismatch.
    """
    rows = con.execute(
        """
        SELECT
            symbol,
            COUNT(DISTINCT candidate_uid) AS distinct_candidate_uids,
            LIST(DISTINCT candidate_uid ORDER BY candidate_uid) AS candidate_uids,
            COUNT(*) AS total_scored
        FROM audit_logs
        WHERE run_id = ?
        GROUP BY symbol
        ORDER BY symbol
    """,
        [run_id],
    ).fetchall()

    results = []
    for symbol, distinct, uids, total in rows:
        locked_states: list[str] = []
        lock_path = LOCK_DIR / lock_filename(symbol)
        if lock_path.exists():
            lock = json.loads(lock_path.read_text())
            locked_states = [
                f"oco|{symbol}|{r['bar_ticks']}|h{r['horizon']}|{r['state_id']}"
                for r in lock["state_universe"]["rows"]
            ]
        unexpected = [u for u in (uids or []) if u not in locked_states]
        missing = [s for s in locked_states if s not in (uids or [])]
        results.append(
            {
                "symbol": symbol,
                "distinct_candidate_uids": distinct,
                "candidate_uids": uids or [],
                "locked_states": locked_states,
                "unexpected_candidates": unexpected,
                "missing_candidates": missing,
                "total_scored": total,
                "flag": bool(unexpected) or bool(missing),
            }
        )
    return results


def _rolling_threshold_integrity_section(
    con: duckdb.DuckDBPyConnection,
) -> list[dict[str, Any]]:
    """Report per (symbol, candidate_uid, run_id) shape of audit_logs.

    Surfaces the flat-distribution failure mode (unique_values == 1 for a
    population >= 30) — the exact signature of the /predict/warmup
    historical replay bug from April 2026. Rolling-vs-static drift is
    covered live by METRIC_ROLLING_THRESHOLD_DRIFT at /predict time.
    """
    rows = con.execute(
        """
        SELECT
            symbol,
            candidate_uid,
            run_id,
            COUNT(*) AS n,
            COUNT(DISTINCT ROUND(pred_prob, 8)) AS unique_values,
            MIN(pred_prob) AS min_prob,
            quantile(pred_prob, 0.5) AS p50,
            quantile(pred_prob, 0.9) AS p90,
            MAX(pred_prob) AS max_prob
        FROM audit_logs
        GROUP BY symbol, candidate_uid, run_id
        ORDER BY symbol, candidate_uid, run_id
        """,
    ).fetchall()

    results: list[dict[str, Any]] = []
    for symbol, cand, run_id, n, unique, pmin, p50, p90, pmax in rows:
        flagged = int(n) >= 30 and int(unique) < MIN_UNIQUE_PROBS_FLAG
        results.append(
            {
                "symbol": symbol,
                "candidate_uid": cand,
                "run_id": run_id,
                "n": int(n),
                "unique_values": int(unique),
                "min_prob": round(float(pmin), 6) if pmin is not None else None,
                "p50": round(float(p50), 6) if p50 is not None else None,
                "p90": round(float(p90), 6) if p90 is not None else None,
                "max_prob": round(float(pmax), 6) if pmax is not None else None,
                "flag": bool(flagged),
            }
        )
    return results


def _format_report(report: dict[str, Any]) -> str:
    lines = [
        "# Live Performance Gap Diagnostic Report",
        f"Generated: {datetime.now(tz=timezone.utc).isoformat()}",
        "",
        "## 1. Win Rate vs Reduced-Core Expectation",
        "",
        "| Symbol | N | Wins | Live% | RC BT% | Delta | Z | Flag |",
        "|--------|---|------|-------|--------|-------|---|------|",
    ]
    for r in report["win_rate"]:
        flag = "🚨" if r["flag"] else ""
        lines.append(
            f"| {r['symbol']} | {r['closed_trades']} | {r['wins']} "
            f"| {r['win_rate_pct']}% | {r['expected_win_rate_pct']}% "
            f"| {r['delta_pp']:+.1f}pp | {r['z_score']} | {flag} |"
        )
    lines += [
        "",
        "## 2. Threshold Schedule Analysis",
        "",
        "| Symbol | Model Month | Scored | Unique Thresholds | Avg Prob | Avg Margin | Schedule Has Today | Flag |",
        "|--------|------------|--------|-------------------|----------|------------|--------------------|------|",
    ]
    for r in report["threshold_analysis"]:
        flag = "🚨" if r["flag"] else ""
        lines.append(
            f"| {r['symbol']} | {r['model_month']} | {r['scored_events']} "
            f"| {r['unique_thresholds']} | {r['avg_pred_prob']} "
            f"| {r['avg_margin_above_threshold']} | {r['schedule_has_today']} | {flag} |"
        )
    lines += [
        "",
        "## 3. PnL Magnitude (compare vs backtest mean_gross_pips_train)",
        "",
        "| Symbol | Candidate UID | N | Avg Pips | Avg Winner | Avg Loser | StdDev |",
        "|--------|--------------|---|----------|-----------|-----------|--------|",
    ]
    for r in report["magnitude_analysis"]:
        lines.append(
            f"| {r['symbol']} | {r['candidate_uid']} | {r['n_closed']} "
            f"| {r['avg_pips']} | {r['avg_winner_pips']} "
            f"| {r['avg_loser_pips']} | {r['stddev_pips']} |"
        )
    lines += [
        "",
        "## 4. Candidate UID Audit",
        "",
        "| Symbol | Distinct UIDs | Total Scored | Unexpected | Missing | Flag |",
        "|--------|--------------|-------------|------------|---------|------|",
    ]
    for r in report["candidate_audit"]:
        flag = "🚨" if r["flag"] else ""
        lines.append(
            f"| {r['symbol']} | {r['distinct_candidate_uids']} "
            f"| {r['total_scored']} | {len(r['unexpected_candidates'])} "
            f"| {len(r['missing_candidates'])} | {flag} |"
        )
        if r["unexpected_candidates"]:
            lines.append(f"  - **Unexpected:** {r['unexpected_candidates']}")
        if r["missing_candidates"]:
            lines.append(f"  - **Missing:** {r['missing_candidates']}")
    lines += [
        "",
        "## 5. Rolling Threshold Integrity",
        "",
        "Flags `unique_values < 10` with `n >= 30` as a low-cardinality audit population.",
        "For `run_id == 'warmup'`, that pattern is the flat `/predict/warmup` replay-regression signature.",
        "",
        "| Symbol | Candidate | Run ID | N | Unique | Min | p50 | p90 | Max | Flag |",
        "|--------|-----------|--------|---|--------|-----|-----|-----|-----|------|",
    ]
    for r in report.get("rolling_threshold_integrity", []):
        flag = "🚨" if r["flag"] else ""
        lines.append(
            f"| {r['symbol']} | {r['candidate_uid']} | {r['run_id']} | {r['n']} | "
            f"{r['unique_values']} | {r['min_prob']} | {r['p50']} | {r['p90']} | "
            f"{r['max_prob']} | {flag} |"
        )
    return "\n".join(lines) + "\n"


def run(
    db_path: Path,
    run_id: str = "jforex_live",
    out_path: Path | None = None,
) -> dict[str, Any]:
    """Run all diagnostic checks and return structured report dict."""
    con = _load_con(db_path)
    report = {
        "win_rate": _win_rate_section(con, run_id),
        "threshold_analysis": _threshold_analysis_section(con, run_id),
        "magnitude_analysis": _magnitude_analysis_section(con, run_id),
        "candidate_audit": _candidate_audit_section(con, run_id),
        "rolling_threshold_integrity": _rolling_threshold_integrity_section(con),
    }
    con.close()
    if out_path is not None:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(_format_report(report), encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", required=True, type=Path, help="Path to checkpointed live_state.db")
    parser.add_argument(
        "--run-id",
        default="jforex_live",
        help="run_id to filter trades/audit_logs (default: jforex_live)",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("data/analysis/live_perf_gap_report.md"),
        help="Output markdown report path",
    )
    args = parser.parse_args()
    report = run(db_path=args.db, run_id=args.run_id, out_path=args.out)

    print("\n=== WIN RATE ===")
    for r in report["win_rate"]:
        flag = " *** ANOMALOUS" if r["flag"] else ""
        print(
            f"  {r['symbol']}: {r['win_rate_pct']}% live vs {r['expected_win_rate_pct']}% expected "
            f"(z={r['z_score']}) total={r['total_pips']} pips{flag}"
        )

    print("\n=== THRESHOLD ===")
    for r in report["threshold_analysis"]:
        flag = " *** STATIC FALLBACK" if r["flag"] else ""
        print(
            f"  {r['symbol']}: {r['unique_thresholds']} unique threshold(s), "
            f"avg_prob={r['avg_pred_prob']}, schedule_today={r['schedule_has_today']}{flag}"
        )

    print("\n=== MAGNITUDE (compare vs backtest mean_gross_pips_train) ===")
    for r in report["magnitude_analysis"]:
        print(
            f"  {r['symbol']} [{r['candidate_uid']}]: n={r['n_closed']}, "
            f"avg={r['avg_pips']}, winners={r['avg_winner_pips']}, losers={r['avg_loser_pips']}"
        )

    print("\n=== CANDIDATE AUDIT ===")
    for r in report["candidate_audit"]:
        flag = " *** MISMATCH" if r["flag"] else ""
        print(
            f"  {r['symbol']}: {r['distinct_candidate_uids']} uid(s), "
            f"unexpected={r['unexpected_candidates']}, "
            f"missing={r['missing_candidates']}{flag}"
        )

    print("\n=== ROLLING THRESHOLD INTEGRITY ===")
    for r in report.get("rolling_threshold_integrity", []):
        flag = ""
        if r["flag"]:
            flag = " *** LOW-CARDINALITY AUDIT POPULATION"
            if r["run_id"] == "warmup":
                flag += " (warmup replay-regression signature)"
        print(
            f"  {r['symbol']} [{r['candidate_uid']}] run_id={r['run_id']}: "
            f"n={r['n']} unique={r['unique_values']} p90={r['p90']}{flag}"
        )

    print(f"\nReport written to {args.out}")


if __name__ == "__main__":
    main()
