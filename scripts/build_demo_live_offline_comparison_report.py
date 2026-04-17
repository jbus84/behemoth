#!/usr/bin/env python3
"""One-off investigation: demo-live vs offline model comparison.

Phase 1 (--phase 1): reads CSVs + JSON, writes signal parity + session summary.
Phase 2 (--phase 2): queries live_state.db + runs diagnose script, appends execution + outcome sections.

Usage:
    uv run python scripts/build_demo_live_offline_comparison_report.py --out docs/analysis/live_demo_vs_offline_comparison_20260417.md --phase 1
    uv run python scripts/build_demo_live_offline_comparison_report.py --out docs/analysis/live_demo_vs_offline_comparison_20260417.md --phase 2
"""
from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

SYMBOLS = ["AUDUSD", "EURUSD", "GBPUSD", "USDCAD", "USDCHF", "USDJPY"]
RECONCILE_DIR = Path("data/analysis/backtest_reconcile")
RUNTIME_DIR = RECONCILE_DIR / "runtime"
LIVE_STATE_DB = RUNTIME_DIR / "live_state.db"


def _read_csv_row(path: Path) -> dict:
    if not path.exists():
        return {}
    with open(path) as f:
        rows = list(csv.DictReader(f))
    return rows[0] if rows else {}


def _session_summary(generated_at: str | None = None) -> str:
    if generated_at is None:
        generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    readiness_path = RUNTIME_DIR / "live_symbol_readiness.json"
    position_path = RUNTIME_DIR / "live_position_summary.json"

    readiness = json.loads(readiness_path.read_text()) if readiness_path.exists() else {}
    positions = json.loads(position_path.read_text()) if position_path.exists() else {}

    run_id = readiness.get("run_id", "unknown")
    sym_rows = readiness.get("symbols", [])
    session_start = min(
        (s.get("bridge_start_ts_utc", "") for s in sym_rows if s.get("bridge_start_ts_utc")),
        default="unknown",
    )

    lines = [
        "## Session Summary",
        "",
        f"- **Run ID:** `{run_id}`",
        f"- **Session started (UTC):** `{session_start}`",
        f"- **Report generated (UTC):** `{generated_at}`",
        f"- **Symbols live:** {readiness.get('session_tradable_symbol_count', '?')} / {readiness.get('session_total_symbol_count', '?')}",
        "",
    ]

    open_positions = positions.get("positions", [])
    if open_positions:
        lines += [f"- **Open positions at report time:** {positions.get('total_open', 0)}", ""]
        lines += ["| Symbol | Status | Open Since (UTC) | Last Tick |"]
        lines += ["|--------|--------|-----------------|-----------|"]
        for pos in open_positions:
            lines.append(
                f"| {pos['symbol']} | {pos['status']} | {pos.get('open_since_utc', '?')} | {pos.get('last_tick_price', '?')} |"
            )
    else:
        lines.append("- **Open positions at report time:** 0")

    return "\n".join(lines)


def _signal_parity_section() -> str:
    lines = [
        "## Signal Parity",
        "",
        "Compares JForex bar events against offline Python model predict calls.",
        "",
        "| Symbol | Pass | Predict Cycles | Failed Events | Finding |",
        "|--------|------|----------------|---------------|---------|",
    ]
    for sym in SYMBOLS:
        row = _read_csv_row(RECONCILE_DIR / f"{sym}_local_jforex_signal_parity_summary.csv")
        if not row:
            lines.append(f"| {sym} | ❓ missing | — | — | CSV not found |")
            continue
        passed = row.get("jforex_signal_parity_pass", "").lower() == "true"
        cycles = row.get("predict_cycles", "?")
        failures = row.get("failed_signal_events", "?")
        icon = "✅" if passed else "❌"
        finding = "—"
        if not passed and str(cycles) == "0":
            finding = "Python API received no predict calls despite JForex bar events"
        lines.append(f"| {sym} | {icon} | {cycles} | {failures} | {finding} |")
    return "\n".join(lines)


def _phase1_report() -> str:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    sections = [
        f"# Demo-Live vs Offline Model Comparison — 2026-04-17",
        f"",
        f"_Generated: {now} UTC_",
        f"",
        _session_summary(generated_at=now),
        "",
        _signal_parity_section(),
        "",
        "## Execution Parity",
        "",
        "_Pending: requires `live_state.db` to unlock after session end. Run with `--phase 2`._",
        "",
        "## Outcome Parity",
        "",
        "_Pending: requires `live_state.db` to unlock after session end. Run with `--phase 2`._",
        "",
        "## Findings and Next Steps",
        "",
        "**Signal failures:** AUDUSD and USDCHF show 0 predict cycles with failed signal events, indicating the Python API was not called for these symbols during the session. EURUSD, GBPUSD, USDCAD, USDJPY all passed signal parity.",
        "",
        "_Execution and outcome analysis pending. Re-run with `--phase 2` after session ends._",
    ]
    return "\n".join(sections)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--phase", type=int, choices=[1, 2], default=1)
    args = parser.parse_args()

    if args.phase == 1:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(_phase1_report())
        print(f"Phase 1 report written to {args.out}")
    elif args.phase == 2:
        if not args.out.exists():
            print("ERROR: run --phase 1 first", file=sys.stderr)
            sys.exit(1)
        _append_phase2(args.out)


def _append_phase2(out: Path) -> None:
    # Check DB is accessible
    try:
        import duckdb
        con = duckdb.connect(str(LIVE_STATE_DB), read_only=True)
        con.close()
    except Exception as e:
        print(f"ERROR: live_state.db not accessible: {e}", file=sys.stderr)
        sys.exit(1)

    exec_section = _execution_parity_section()
    outcome_section = _outcome_parity_section()

    content = out.read_text()
    content = content.replace(
        "## Execution Parity\n\n_Pending: requires `live_state.db` to unlock after session end. Run with `--phase 2`._",
        exec_section,
    )
    content = content.replace(
        "## Outcome Parity\n\n_Pending: requires `live_state.db` to unlock after session end. Run with `--phase 2`._",
        outcome_section,
    )
    content = content.replace(
        "_Execution and outcome analysis pending. Re-run with `--phase 2` after session ends._",
        _findings_section(),
    )
    out.write_text(content)
    print(f"Phase 2 sections appended to {out}")


def _execution_parity_section() -> str:
    lines = [
        "## Execution Parity",
        "",
        "Compares submitted orders and execution failures between JForex and offline model.",
        "",
        "| Symbol | Pass | Submitted Orders | Execution Failures |",
        "|--------|------|-----------------|-------------------|",
    ]
    for sym in SYMBOLS:
        row = _read_csv_row(RECONCILE_DIR / f"{sym}_local_jforex_execution_parity_summary.csv")
        if not row:
            lines.append(f"| {sym} | ❓ missing | — | — |")
            continue
        passed = row.get("jforex_execution_parity_pass", "").lower() == "true"
        orders = row.get("submitted_orders", "?")
        failures = row.get("execution_failures", "?")
        icon = "✅" if passed else "❌"
        lines.append(f"| {sym} | {icon} | {orders} | {failures} |")
    return "\n".join(lines)


def _outcome_parity_section() -> str:
    # Run diagnose_live_performance_gap.py and capture output
    perf_gap_script = Path("scripts/diagnose_live_performance_gap.py")
    perf_gap_out = Path("data/analysis/live_perf_gap_report.md")
    subprocess.run(
        [sys.executable, str(perf_gap_script),
         "--db", str(LIVE_STATE_DB),
         "--run-id", "jforex_live",
         "--out", str(perf_gap_out)],
        check=True,
    )

    lines = [
        "## Outcome Parity",
        "",
        "Compares live win rates against reduced-core WFO backtest expectations.",
        "",
    ]

    # Per-symbol outcome CSV
    lines += [
        "### Per-Symbol Overall Pass/Fail",
        "",
        "| Symbol | Pass | Locked Selected | Gross Pips | Win Rate | JForex Predict Cycles | Signal Coverage | Order Coverage |",
        "|--------|------|----------------|-----------|---------|----------------------|----------------|---------------|",
    ]
    for sym in SYMBOLS:
        row = _read_csv_row(RECONCILE_DIR / f"{sym}_local_jforex_outcome_parity_summary.csv")
        if not row:
            lines.append(f"| {sym} | ❓ missing | — | — | — | — | — | — |")
            continue
        passed = row.get("jforex_outcome_parity_pass", "").lower() == "true"
        icon = "✅" if passed else "❌"
        lines.append(
            f"| {sym} | {icon}"
            f" | {row.get('locked_selected_count', '?')}"
            f" | {row.get('locked_gross_pips_total', '?')}"
            f" | {row.get('locked_win_rate', '?')}%"
            f" | {row.get('jforex_predict_cycles', '?')}"
            f" | {row.get('signal_coverage_ratio', '?')}"
            f" | {row.get('order_coverage_ratio', '?')} |"
        )

    lines += [
        "",
        f"### Performance Gap Detail",
        "",
        f"_See full report: `{perf_gap_out}`_",
        "",
        perf_gap_out.read_text() if perf_gap_out.exists() else "_Report not generated._",
    ]
    return "\n".join(lines)


def _findings_section() -> str:
    lines = [
        "## Findings and Next Steps",
        "",
        "**Signal failures:** AUDUSD and USDCHF received 0 predict cycles — the Python API was not called for these symbols. Root cause investigation recommended (check bridge connectivity, symbol registration, and API warmup logs for these two symbols).",
        "",
        "**Execution:** See execution parity table above for submitted orders and failures.",
        "",
        "**Outcome:** See outcome parity table above for win rate vs WFO expectations.",
    ]
    return "\n".join(lines)


if __name__ == "__main__":
    main()
