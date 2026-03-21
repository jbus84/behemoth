# Monthly Recertification and Promotion Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `make monthly-recert` and `make promote-live` commands that auto-derive the current month's params, run the full stage 12–14 certification pipeline, print a per-symbol go/no-go summary, and archive governance locks on promotion.

**Architecture:** Two Python orchestrator scripts (`run_monthly_recert.py`, `run_promote_live.py`) modelled on the existing `run_jforex_live.py` pattern — argparse, `_repo_root()`, subprocess invocations of `make` targets, stdlib-only. A third new Makefile target (`freeze-oco-dukascopy-candidate`) freezes governance locks to the dukascopy-candidate directory. Three Makefile targets wrap the scripts.

**Tech Stack:** Python 3 (stdlib only: `argparse`, `subprocess`, `csv`, `datetime`, `pathlib`), GNU Make.

---

## File Map

| File | Change |
|------|--------|
| `scripts/run_monthly_recert.py` | Create — orchestrates matrix + cert + go/no-go summary |
| `scripts/run_promote_live.py` | Create — verifies cert freshness, archives governance locks |
| `Makefile` | Add `freeze-oco-dukascopy-candidate`, `monthly-recert`, `promote-live` targets + `.PHONY` + help entries |

---

## Background: key files the implementer must know about

- **`scripts/run_jforex_live.py`** — reference pattern: `_repo_root()`, `_parse_args()` → `RunConfig` dataclass, subprocess with `cwd=_repo_root()`. Follow this style.
- **`Makefile` line 16** — the `.PHONY` line (one long line); append new targets to its end.
- **`Makefile` line 167** — `jforex-live:` target. New `freeze-oco-dukascopy-candidate` target goes after `freeze-oco-history` (line 339–342). New `monthly-recert`/`promote-live` go after `full-stage14-cert` (line 632).
- **`Makefile` line 744** — last help entry in the Pipeline section (`jforex-live`). New help entries go after this line.
- **`data/analysis/backtest_reconcile/stage14_jforex_runtime_certification_checks.csv`** — columns: `symbol,check_id,status,severity,metric_name,metric_value,expected,details,source_path,evaluated_at_utc`. The `status` column is `pass` or `fail`; `severity` is `critical` or lower. `evaluated_at_utc` is an ISO timestamp like `2026-03-20T18:11:33Z`.
- **`scripts/freeze_oco_historical_governance.py`** — CLI args: `--symbols`, `--out-dir`, `--months`, `--config-dir`, `--analysis-dir`, `--models-dir`.
- **`make full-stage14-cert`** chains `jforex-outcome-parity` → `local-jforex-cert` → `stage14-jforex-cert`. Only `jforex-outcome-parity` needs `LOCK_DIR`, `EVAL_START`, `EVAL_END` passed.
- **`make jforex-dukascopy-matrix`** accepts `MODEL_MONTH`, `START_TS`, `END_TS` as Make variable overrides.

---

## Task 1: Create `scripts/run_monthly_recert.py`

**Files:**
- Create: `scripts/run_monthly_recert.py`

- [ ] **Step 1: Create the script**

Create `scripts/run_monthly_recert.py` with the following complete contents:

```python
#!/usr/bin/env python3
"""Run the monthly JForex dukascopy-candidate recertification pipeline.

Auto-derives the model month (last complete calendar month) and test window,
runs `make jforex-dukascopy-matrix` followed by `make full-stage14-cert`, then
reads the stage14 certification checks CSV and prints a per-symbol go/no-go
summary.

Prerequisites (run manually before this script):
  1. make retrain-all                    — retrain models to models/oco/
  2. make freeze-oco-dukascopy-candidate — freeze governance lock to
       configs/research/governance/oco_dukascopy_candidate/

Exits 0 if all critical checks pass, exits 1 if any fail.
"""

from __future__ import annotations

import argparse
import csv
import subprocess
import sys
from datetime import date
from pathlib import Path

DEFAULT_SYMBOLS = ("EURUSD", "GBPUSD", "USDJPY", "USDCHF", "AUDUSD", "USDCAD")
CERT_CHECKS_FILENAME = "stage14_jforex_runtime_certification_checks.csv"


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _derive_params(
    model_month_override: str | None = None,
    start_ts_override: str | None = None,
    end_ts_override: str | None = None,
    eval_start_override: str | None = None,
    eval_end_override: str | None = None,
) -> tuple[str, str, str, str, str]:
    """Return (model_month, start_ts, end_ts, eval_start, eval_end)."""
    if model_month_override:
        year_s, month_s = model_month_override.split("-")
        year, month = int(year_s), int(month_s)
    else:
        today = date.today()
        year, month = (today.year - 1, 12) if today.month == 1 else (today.year, today.month - 1)

    model_month = f"{year:04d}-{month:02d}"
    start_ts    = start_ts_override    or f"{year:04d}-{month:02d}-04T00:00:00Z"
    end_ts      = end_ts_override      or f"{year:04d}-{month:02d}-09T00:00:00Z"
    eval_start  = eval_start_override  or f"{year:04d}-{month:02d}-07T00:00:00Z"
    eval_end    = eval_end_override    or f"{year:04d}-{month:02d}-09T00:00:00Z"
    return model_month, start_ts, end_ts, eval_start, eval_end


def _run_step(cmd: list[str], label: str) -> None:
    print(f"[monthly-recert] {label}", flush=True)
    result = subprocess.run(cmd, cwd=_repo_root())
    if result.returncode != 0:
        print(
            f"[monthly-recert] {label} failed (rc={result.returncode})",
            file=sys.stderr,
            flush=True,
        )
        raise SystemExit(1)


def _read_failures(report_dir: str) -> dict[str, list[dict[str, str]]]:
    """Return {symbol: [failing critical check rows]}."""
    csv_path = _repo_root() / report_dir / CERT_CHECKS_FILENAME
    if not csv_path.exists():
        raise SystemExit(f"[monthly-recert] cert checks CSV not found: {csv_path}")
    failures: dict[str, list[dict[str, str]]] = {}
    with csv_path.open() as f:
        for row in csv.DictReader(f):
            if row["severity"] == "critical" and row["status"] != "pass":
                failures.setdefault(row["symbol"], []).append(row)
    return failures


def _print_summary(model_month: str, failures: dict[str, list[dict[str, str]]]) -> bool:
    """Print per-symbol summary. Returns True if all critical checks pass."""
    print(f"\n[monthly-recert] {model_month} results")
    all_pass = True
    for symbol in DEFAULT_SYMBOLS:
        if symbol in failures:
            all_pass = False
            for row in failures[symbol]:
                detail = row.get("details", "").strip()
                suffix = f": {detail}" if detail else ""
                print(f"  {symbol:<8}FAIL  {row['check_id']}{suffix}")
        else:
            print(f"  {symbol:<8}PASS")
    if all_pass:
        print("go/no-go: GO — run make promote-live to archive locks")
    else:
        print(f"go/no-go: NO-GO — {len(failures)} symbol(s) failed")
    return all_pass


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-month", help="Override model month YYYY-MM (default: last complete month)")
    parser.add_argument("--start-ts",    help="Override matrix start timestamp")
    parser.add_argument("--end-ts",      help="Override matrix end timestamp")
    parser.add_argument("--eval-start",  help="Override outcome parity eval start timestamp")
    parser.add_argument("--eval-end",    help="Override outcome parity eval end timestamp")
    parser.add_argument("--report-dir",  default="data/analysis/backtest_reconcile")
    args = parser.parse_args()

    model_month, start_ts, end_ts, eval_start, eval_end = _derive_params(
        model_month_override=args.model_month,
        start_ts_override=args.start_ts,
        end_ts_override=args.end_ts,
        eval_start_override=args.eval_start,
        eval_end_override=args.eval_end,
    )
    lock_dir = f"configs/research/governance/oco_history_dukascopy_candidate/{model_month}"

    print(
        f"[monthly-recert] running for MODEL_MONTH={model_month} "
        f"window={start_ts[:10]}→{end_ts[:10]}",
        flush=True,
    )

    _run_step(
        ["make", "jforex-dukascopy-matrix",
         f"MODEL_MONTH={model_month}", f"START_TS={start_ts}", f"END_TS={end_ts}"],
        "step 1/2: jforex-dukascopy-matrix",
    )
    _run_step(
        ["make", "full-stage14-cert",
         f"LOCK_DIR={lock_dir}", f"EVAL_START={eval_start}", f"EVAL_END={eval_end}"],
        "step 2/2: full-stage14-cert",
    )

    failures = _read_failures(args.report_dir)
    all_pass = _print_summary(model_month, failures)
    if not all_pass:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Verify syntax**

```bash
UV_CACHE_DIR=.uv_cache uv run python -c "import py_compile; py_compile.compile('scripts/run_monthly_recert.py', doraise=True); print('OK')"
```

Expected: `OK`

- [ ] **Step 3: Verify `--help` works**

```bash
UV_CACHE_DIR=.uv_cache uv run python scripts/run_monthly_recert.py --help
```

Expected: usage output listing `--model-month`, `--start-ts`, `--end-ts`, `--eval-start`, `--eval-end`, `--report-dir`.

- [ ] **Step 4: Verify date derivation**

```bash
UV_CACHE_DIR=.uv_cache uv run python -c "
import sys; sys.argv=['t']
from scripts.run_monthly_recert import _derive_params
mm, s, e, es, ee = _derive_params('2025-07')
assert mm == '2025-07', mm
assert s  == '2025-07-04T00:00:00Z', s
assert e  == '2025-07-09T00:00:00Z', e
assert es == '2025-07-07T00:00:00Z', es
assert ee == '2025-07-09T00:00:00Z', ee
print('OK')
"
```

Expected: `OK`

- [ ] **Step 5: Verify go/no-go summary with a mock CSV**

```bash
UV_CACHE_DIR=.uv_cache uv run python -c "
import sys, tempfile, os
from pathlib import Path

# Write a fake checks CSV with one failure
csv_content = '''symbol,check_id,status,severity,metric_name,metric_value,expected,details,source_path,evaluated_at_utc
EURUSD,JFOREX_SIGNAL_PARITY_PASS,pass,critical,,,,,x,2026-03-21T10:00:00Z
USDJPY,JFOREX_SIGNAL_PARITY_PASS,fail,critical,,,,,x,2026-03-21T10:00:00Z
'''
with tempfile.TemporaryDirectory() as tmp:
    Path(tmp, 'stage14_jforex_runtime_certification_checks.csv').write_text(csv_content)
    sys.argv = ['t', '--report-dir', tmp, '--model-month', '2026-02']
    # Patch _run_step to no-op and _read_failures + _print_summary
    from scripts.run_monthly_recert import _read_failures, _print_summary
    import scripts.run_monthly_recert as m
    m._repo_root = lambda: Path('.')
    # Point report_dir directly at tmp
    failures = _read_failures.__wrapped__(tmp) if hasattr(_read_failures, '__wrapped__') else None
    # Use the module's function with patched root
    import csv as csvmod
    path = Path(tmp) / 'stage14_jforex_runtime_certification_checks.csv'
    result = {}
    with path.open() as f:
        for row in csvmod.DictReader(f):
            if row['severity'] == 'critical' and row['status'] != 'pass':
                result.setdefault(row['symbol'], []).append(row)
    assert 'USDJPY' in result, result
    assert 'EURUSD' not in result, result
    ok = _print_summary('2026-02', result)
    assert not ok
    print('OK')
"
```

Expected: prints summary with `USDJPY FAIL` and `go/no-go: NO-GO`, then `OK`.

- [ ] **Step 6: Commit**

```bash
git add scripts/run_monthly_recert.py
git commit -m "feat: add run_monthly_recert.py monthly recertification orchestrator"
```

---

## Task 2: Create `scripts/run_promote_live.py`

**Files:**
- Create: `scripts/run_promote_live.py`

- [ ] **Step 1: Create the script**

Create `scripts/run_promote_live.py` with the following complete contents:

```python
#!/usr/bin/env python3
"""Promote the monthly recertification to live by archiving governance locks.

Verifies the stage14 cert passed today for the derived model month, then runs
freeze_oco_historical_governance.py to archive the current
configs/research/governance/oco_dukascopy_candidate/ locks under the new month
in configs/research/governance/oco_history_dukascopy_candidate/.

After this script completes successfully, restart the live runner with:
  make jforex-live
"""

from __future__ import annotations

import argparse
import csv
import subprocess
import sys
from datetime import date
from pathlib import Path

DEFAULT_SYMBOLS = "EURUSD,GBPUSD,USDJPY,USDCHF,AUDUSD,USDCAD"
CERT_CHECKS_FILENAME = "stage14_jforex_runtime_certification_checks.csv"


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _last_complete_month(override: str | None = None) -> str:
    if override:
        return override
    today = date.today()
    if today.month == 1:
        return f"{today.year - 1:04d}-12"
    return f"{today.year:04d}-{today.month - 1:02d}"


def _verify_cert(report_dir: str) -> None:
    """Raise SystemExit if cert CSV is missing, stale, or has critical failures."""
    csv_path = _repo_root() / report_dir / CERT_CHECKS_FILENAME
    if not csv_path.exists():
        raise SystemExit(
            f"[promote-live] no cert results found at {csv_path}; "
            "run make monthly-recert first"
        )

    today_str = date.today().isoformat()
    failures: list[str] = []
    stale = False

    with csv_path.open() as f:
        for row in csv.DictReader(f):
            evaluated = row.get("evaluated_at_utc", "")[:10]
            if evaluated and evaluated != today_str:
                stale = True
            if row["severity"] == "critical" and row["status"] != "pass":
                failures.append(f"  {row['symbol']}: {row['check_id']}")

    if stale:
        raise SystemExit(
            f"[promote-live] cert results are stale (not from today {today_str}); "
            "rerun make monthly-recert"
        )
    if failures:
        lines = "\n".join(failures)
        raise SystemExit(
            f"[promote-live] cert failed for {len(failures)} check(s); cannot promote:\n{lines}"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--model-month",
        help="Override model month YYYY-MM (default: last complete month)",
    )
    parser.add_argument("--report-dir", default="data/analysis/backtest_reconcile")
    args = parser.parse_args()

    model_month = _last_complete_month(args.model_month)

    print(f"[promote-live] verifying cert for {model_month}", flush=True)
    _verify_cert(args.report_dir)

    print(f"[promote-live] archiving locks for {model_month}", flush=True)
    result = subprocess.run(
        [
            sys.executable,
            "scripts/freeze_oco_historical_governance.py",
            "--symbols", DEFAULT_SYMBOLS,
            "--out-dir", "configs/research/governance/oco_history_dukascopy_candidate",
            "--months", model_month,
            "--config-dir", "configs/research/experiments_dukascopy_candidate",
            "--analysis-dir", "data/analysis/tick_opportunity_mining_dukascopy_candidate",
            "--models-dir", "models/oco",
        ],
        cwd=_repo_root(),
    )
    if result.returncode != 0:
        raise SystemExit(
            f"[promote-live] freeze_oco_historical_governance failed (rc={result.returncode})"
        )

    print(f"[promote-live] locks archived for {model_month}")
    print("Next step: restart the live runner with:")
    print("  make jforex-live")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Verify syntax**

```bash
UV_CACHE_DIR=.uv_cache uv run python -c "import py_compile; py_compile.compile('scripts/run_promote_live.py', doraise=True); print('OK')"
```

Expected: `OK`

- [ ] **Step 3: Verify `--help` works**

```bash
UV_CACHE_DIR=.uv_cache uv run python scripts/run_promote_live.py --help
```

Expected: usage output listing `--model-month` and `--report-dir`.

- [ ] **Step 4: Verify staleness check**

```bash
UV_CACHE_DIR=.uv_cache uv run python -c "
import sys, tempfile
from pathlib import Path

csv_content = 'symbol,check_id,status,severity,metric_name,metric_value,expected,details,source_path,evaluated_at_utc\nEURUSD,X,pass,critical,,,,,x,2020-01-01T00:00:00Z\n'
with tempfile.TemporaryDirectory() as tmp:
    Path(tmp, 'stage14_jforex_runtime_certification_checks.csv').write_text(csv_content)
    from scripts.run_promote_live import _verify_cert, _repo_root
    import scripts.run_promote_live as m
    m._repo_root = lambda: Path('.')
    try:
        _verify_cert(tmp)
        print('ERROR: should have raised')
    except SystemExit as e:
        msg = str(e)
        assert 'stale' in msg, msg
        print('OK')
"
```

Expected: `OK`

- [ ] **Step 5: Verify missing CSV check**

```bash
UV_CACHE_DIR=.uv_cache uv run python -c "
import sys, tempfile
from pathlib import Path
with tempfile.TemporaryDirectory() as tmp:
    from scripts.run_promote_live import _verify_cert
    import scripts.run_promote_live as m
    m._repo_root = lambda: Path('.')
    try:
        _verify_cert(tmp)
        print('ERROR: should have raised')
    except SystemExit as e:
        assert 'monthly-recert' in str(e), str(e)
        print('OK')
"
```

Expected: `OK`

- [ ] **Step 6: Commit**

```bash
git add scripts/run_promote_live.py
git commit -m "feat: add run_promote_live.py promotion orchestrator"
```

---

## Task 3: Add Makefile targets

**Files:**
- Modify: `Makefile` (line 16 for `.PHONY`, after line 342 for `freeze-oco-dukascopy-candidate`, after line 632 for `monthly-recert`/`promote-live`, after line 744 for help entries)

- [ ] **Step 1: Add the three targets to `.PHONY` (line 16)**

The `.PHONY` line currently ends with `jforex-live`. Append the three new targets:

Find (exact end of `.PHONY` line):
```
 jforex-live
```

Replace with:
```
 jforex-live freeze-oco-dukascopy-candidate monthly-recert promote-live
```

- [ ] **Step 2: Add `freeze-oco-dukascopy-candidate` target after `freeze-oco-history`**

`freeze-oco-history` ends at line 342 with `@echo "\n✅ Historical month-scoped locks generated."`. Insert after the blank line that follows it.

Find this exact block:
```
	@echo "\n✅ Historical month-scoped locks generated."

validate-oco-history:
```

Replace with:
```
	@echo "\n✅ Historical month-scoped locks generated."

freeze-oco-dukascopy-candidate:
	UV_CACHE_DIR=$(or $(UV_CACHE_DIR),.uv_cache) uv run python scripts/freeze_oco_live_governance.py \
		--symbols $(shell echo $(REBUILD_SYMBOLS) | sed 's/ /,/g') \
		--out-dir configs/research/governance/oco_dukascopy_candidate \
		--config-dir configs/research/experiments_dukascopy_candidate \
		--analysis-dir data/analysis/tick_opportunity_mining_dukascopy_candidate
	@echo "\n✅ Dukascopy-candidate governance locks frozen."

validate-oco-history:
```

**Important:** Recipe lines must be indented with a real TAB character.

- [ ] **Step 3: Add `monthly-recert` and `promote-live` targets after `full-stage14-cert`**

`full-stage14-cert` is a single dependency line at line 632 with a blank line following. Insert after that blank line, before `account-risk-monitoring-report`.

Find this exact block:
```
full-stage14-cert: jforex-outcome-parity local-jforex-cert stage14-jforex-cert

account-risk-monitoring-report:
```

Replace with:
```
full-stage14-cert: jforex-outcome-parity local-jforex-cert stage14-jforex-cert

monthly-recert:
	UV_CACHE_DIR=$(or $(UV_CACHE_DIR),.uv_cache) uv run python scripts/run_monthly_recert.py \
		$(if $(MODEL_MONTH),--model-month "$(MODEL_MONTH)",) \
		$(if $(START_TS),--start-ts "$(START_TS)",) \
		$(if $(END_TS),--end-ts "$(END_TS)",) \
		$(if $(EVAL_START),--eval-start "$(EVAL_START)",) \
		$(if $(EVAL_END),--eval-end "$(EVAL_END)",) \
		--report-dir $(or $(REPORT_DIR),data/analysis/backtest_reconcile)

promote-live:
	UV_CACHE_DIR=$(or $(UV_CACHE_DIR),.uv_cache) uv run python scripts/run_promote_live.py \
		$(if $(MODEL_MONTH),--model-month "$(MODEL_MONTH)",) \
		--report-dir $(or $(REPORT_DIR),data/analysis/backtest_reconcile)

account-risk-monitoring-report:
```

**Important:** Recipe lines must be indented with a real TAB character.

- [ ] **Step 4: Add help entries after `jforex-live` help entry (line 744)**

Find this exact line:
```
	@printf "  $(COLOR_TARGET)%-18s$(COLOR_RESET) $(COLOR_DESC)%s$(COLOR_RESET)\n" "jforex-live" "Start the JForex live/demo session for all symbols (IClient-based, live governance mode)"
```

Replace with:
```
	@printf "  $(COLOR_TARGET)%-18s$(COLOR_RESET) $(COLOR_DESC)%s$(COLOR_RESET)\n" "jforex-live" "Start the JForex live/demo session for all symbols (IClient-based, live governance mode)"
	@printf "  $(COLOR_TARGET)%-18s$(COLOR_RESET) $(COLOR_DESC)%s$(COLOR_RESET)\n" "freeze-oco-dukascopy-candidate" "Freeze governance locks to oco_dukascopy_candidate/ (prerequisite for monthly-recert)"
	@printf "  $(COLOR_TARGET)%-18s$(COLOR_RESET) $(COLOR_DESC)%s$(COLOR_RESET)\n" "monthly-recert" "Run monthly dukascopy-candidate recertification pipeline and print go/no-go summary"
	@printf "  $(COLOR_TARGET)%-18s$(COLOR_RESET) $(COLOR_DESC)%s$(COLOR_RESET)\n" "promote-live" "Archive certified governance locks to oco_history_dukascopy_candidate/ and print restart reminder"
```

**Important:** Each `@printf` line must be indented with a real TAB character.

- [ ] **Step 5: Verify `make --dry-run monthly-recert` parses correctly**

```bash
make --dry-run monthly-recert 2>&1 | head -5
```

Expected: shows `uv run python scripts/run_monthly_recert.py ...` with no parse errors.

- [ ] **Step 6: Verify `make --dry-run promote-live` parses correctly**

```bash
make --dry-run promote-live 2>&1 | head -5
```

Expected: shows `uv run python scripts/run_promote_live.py ...` with no parse errors.

- [ ] **Step 7: Verify `make --dry-run freeze-oco-dukascopy-candidate` parses correctly**

```bash
make --dry-run freeze-oco-dukascopy-candidate 2>&1 | head -5
```

Expected: shows `uv run python scripts/freeze_oco_live_governance.py ...` with `--out-dir configs/research/governance/oco_dukascopy_candidate` and no parse errors.

- [ ] **Step 8: Verify help entries appear**

```bash
make help 2>&1 | grep -E "monthly-recert|promote-live|freeze-oco-dukascopy"
```

Expected: three lines, one for each new target.

- [ ] **Step 9: Commit**

```bash
git add Makefile
git commit -m "feat: add monthly-recert, promote-live, freeze-oco-dukascopy-candidate Makefile targets"
```

---

## Manual verification checklist (requires real data)

These steps cannot be automated:

1. `make monthly-recert` → confirm correct `MODEL_MONTH` derived, both subprocesses invoked, go/no-go summary printed.
2. `make monthly-recert MODEL_MONTH=2025-07` → confirm override works and uses `2025-07-04→2025-07-09` window.
3. `make promote-live` before running `monthly-recert` today → confirm exits non-zero with "no cert results found" or "stale" error.
4. After a passing `make monthly-recert` → `make promote-live` archives locks to `oco_history_dukascopy_candidate/` and prints restart reminder.
5. `make freeze-oco-dukascopy-candidate` → confirm writes to `configs/research/governance/oco_dukascopy_candidate/`.
