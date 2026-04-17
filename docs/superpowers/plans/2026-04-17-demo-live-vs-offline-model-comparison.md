# Demo-Live vs Offline Model Comparison Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Produce a consolidated markdown report comparing the JForex demo-live session against the offline Python model across signal, execution, and outcome parity for all 6 symbols.

**Architecture:** A single investigation script reads existing per-symbol parity CSVs and JSON files for Phase 1 (immediately), then queries `live_state.db` and runs `diagnose_live_performance_gap.py` for Phases 2+3 once the session ends. Phase 1 output is written immediately; Phases 2+3 append to the same report file when re-run post-session.

**Tech Stack:** Python 3.12, DuckDB, pandas, uv (`uv run python`)

---

## File Map

| File | Action | Purpose |
|------|--------|---------|
| `scripts/build_demo_live_offline_comparison_report.py` | **Create** | Main investigation script — reads CSV/JSON for Phase 1; queries live_state.db and runs diagnose script for Phases 2+3 |
| `docs/analysis/live_demo_vs_offline_comparison_20260417.md` | **Create (generated)** | Output report — written by the script |

---

## Context You Need

**Live session facts (as of investigation start):**
- Session started: `2026-04-16T16:47` UTC (bridge_start_ts from `live_symbol_readiness.json`)
- Session still running — uvicorn PID 4865 holds exclusive lock on `live_state.db`
- 2 open positions: GBPUSD (PENDING since 09:54 UTC), USDCAD (PENDING since 10:01 UTC)
- All 6 symbols READY: EURUSD, GBPUSD, USDJPY, USDCAD, USDCHF, AUDUSD

**Signal parity already known from CSVs:**

| Symbol | Pass | Predict Cycles | Failed Events |
|--------|------|----------------|---------------|
| AUDUSD | FAIL | 0 | 165 |
| EURUSD | PASS | 136 | 0 |
| GBPUSD | PASS | 116 | 0 |
| USDCAD | PASS | 113 | 0 |
| USDCHF | FAIL | 0 | 82 |
| USDJPY | PASS | 185 | 0 |

**Key data paths:**
- Signal CSVs: `data/analysis/backtest_reconcile/{SYM}_local_jforex_signal_parity_summary.csv`
- Execution CSVs: `data/analysis/backtest_reconcile/{SYM}_local_jforex_execution_parity_summary.csv`
- Outcome CSVs: `data/analysis/backtest_reconcile/{SYM}_local_jforex_outcome_parity_summary.csv`
- Live position summary: `data/analysis/backtest_reconcile/runtime/live_position_summary.json`
- Live symbol readiness: `data/analysis/backtest_reconcile/runtime/live_symbol_readiness.json`
- Live state DB: `data/analysis/backtest_reconcile/runtime/live_state.db` (locked while session runs)
- Perf gap script: `scripts/diagnose_live_performance_gap.py`

---

## Task 1: Write the report script (Phase 1 — signal + session summary)

**Files:**
- Create: `scripts/build_demo_live_offline_comparison_report.py`

- [ ] **Step 1: Write a test that verifies Phase 1 output**

```python
# tests/test_build_demo_live_offline_comparison_report.py
from pathlib import Path
import subprocess, sys

def test_phase1_runs_and_produces_signal_section(tmp_path):
    out = tmp_path / "report.md"
    result = subprocess.run(
        [sys.executable, "scripts/build_demo_live_offline_comparison_report.py",
         "--out", str(out), "--phase", "1"],
        capture_output=True, text=True
    )
    assert result.returncode == 0, result.stderr
    content = out.read_text()
    assert "## Signal Parity" in content
    assert "AUDUSD" in content
    assert "USDCHF" in content
    assert "## Session Summary" in content
```

- [ ] **Step 2: Run it to verify it fails**

```bash
uv run pytest tests/test_build_demo_live_offline_comparison_report.py -v
```

Expected: `FAILED` — `FileNotFoundError: scripts/build_demo_live_offline_comparison_report.py`

- [ ] **Step 3: Create the script with Phase 1 logic**

```python
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


def _session_summary() -> str:
    readiness_path = RUNTIME_DIR / "live_symbol_readiness.json"
    position_path = RUNTIME_DIR / "live_position_summary.json"

    readiness = json.loads(readiness_path.read_text()) if readiness_path.exists() else {}
    positions = json.loads(position_path.read_text()) if position_path.exists() else {}

    as_of = readiness.get("as_of_utc", "unknown")
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
        f"- **Report generated (UTC):** `{as_of}`",
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
        _session_summary(),
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
```

- [ ] **Step 4: Run the test**

```bash
uv run pytest tests/test_build_demo_live_offline_comparison_report.py -v
```

Expected: `PASSED`

- [ ] **Step 5: Commit**

```bash
git add scripts/build_demo_live_offline_comparison_report.py tests/test_build_demo_live_offline_comparison_report.py
git commit -m "feat: add demo-live vs offline model comparison report script (phase 1)"
```

---

## Task 2: Run Phase 1 and produce the report

**Files:**
- Output: `docs/analysis/live_demo_vs_offline_comparison_20260417.md`

- [ ] **Step 1: Run Phase 1**

```bash
uv run python scripts/build_demo_live_offline_comparison_report.py \
  --out docs/analysis/live_demo_vs_offline_comparison_20260417.md \
  --phase 1
```

Expected output: `Phase 1 report written to docs/analysis/live_demo_vs_offline_comparison_20260417.md`

- [ ] **Step 2: Verify the report looks correct**

```bash
cat docs/analysis/live_demo_vs_offline_comparison_20260417.md
```

Verify:
- Session summary shows run_id `jforex_live`, start time `2026-04-16T16:47`
- Signal parity table shows AUDUSD ❌, USDCHF ❌, other four ✅
- Execution and outcome sections show pending placeholders

- [ ] **Step 3: Commit**

```bash
git add docs/analysis/live_demo_vs_offline_comparison_20260417.md
git commit -m "docs: add demo-live vs offline comparison report (phase 1 - signal parity)"
```

---

## Task 3: Run Phase 2 after session ends (post-session)

**Files:**
- Modify (append): `docs/analysis/live_demo_vs_offline_comparison_20260417.md`

**Pre-condition:** The JForex live session must have ended and `live_state.db` must be unlocked. Verify:

```bash
python3 -c "
import duckdb
con = duckdb.connect('data/analysis/backtest_reconcile/runtime/live_state.db', read_only=True)
print('DB accessible')
con.close()
"
```

Expected: `DB accessible` — if you get a lock error, the session is still running.

- [ ] **Step 1: Run Phase 2**

```bash
uv run python scripts/build_demo_live_offline_comparison_report.py \
  --out docs/analysis/live_demo_vs_offline_comparison_20260417.md \
  --phase 2
```

Expected: `Phase 2 sections appended to docs/analysis/live_demo_vs_offline_comparison_20260417.md`

- [ ] **Step 2: Verify the report is complete**

```bash
cat docs/analysis/live_demo_vs_offline_comparison_20260417.md
```

Verify:
- Execution parity table shows real submitted order counts (not 0 placeholders)
- Outcome parity table shows win rates vs WFO expectations
- Findings section reflects actual results

- [ ] **Step 3: Commit**

```bash
git add docs/analysis/live_demo_vs_offline_comparison_20260417.md
git commit -m "docs: complete demo-live vs offline comparison report (phases 2+3 - execution + outcome parity)"
```
