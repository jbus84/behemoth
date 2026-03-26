# Definitive Monthly Recert Gate Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `make monthly-recert` the single definitive monthly release gate by always running candidate sync, real JForex parity, local surrogate parity, and Stage 14 certification with `TICK_BATCH_SIZE=1`.

**Architecture:** Keep the change narrow. The policy lives entirely in `scripts/run_monthly_recert.py`, and the contract is enforced in `tests/test_run_monthly_recert.py` by asserting the exact subprocess sequence and arguments. No new flags or alternate “fast” path are introduced.

**Tech Stack:** Python, pytest, Make-based orchestration

---

### Task 1: Lock The Definitive Gate Contract In Tests

**Files:**
- Modify: `tests/test_run_monthly_recert.py`
- Modify: `scripts/run_monthly_recert.py`

- [ ] **Step 1: Rewrite the test to express the stricter command sequence**

Replace the existing single test body in `tests/test_run_monthly_recert.py` with this version so the contract is explicit before any production edit:

```python
from __future__ import annotations

from types import SimpleNamespace

import scripts.run_monthly_recert as run_monthly_recert


def test_main_runs_definitive_recert_chain(monkeypatch) -> None:
    calls: list[list[str]] = []

    def fake_run(cmd, cwd=None):
        calls.append(cmd)
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(run_monthly_recert.subprocess, "run", fake_run)
    monkeypatch.setattr(run_monthly_recert, "_read_failures", lambda report_dir: {})
    monkeypatch.setattr(run_monthly_recert, "_print_summary", lambda model_month, failures: True)
    monkeypatch.setattr(
        run_monthly_recert,
        "_derive_params",
        lambda **kwargs: (
            "2026-02",
            "2026-02-04T00:00:00Z",
            "2026-02-09T00:00:00Z",
            "2026-02-07T00:00:00Z",
            "2026-02-09T00:00:00Z",
        ),
    )
    monkeypatch.setattr(
        run_monthly_recert.sys,
        "argv",
        ["run_monthly_recert.py", "--report-dir", "data/analysis/backtest_reconcile"],
    )

    run_monthly_recert.main()

    assert calls == [
        [
            "uv",
            "run",
            "python",
            "scripts/sync_candidate_model_artifacts.py",
            "--lock-dir",
            "configs/research/governance/oco",
            "--source-models-dir",
            "models/oco",
            "--target-models-dir",
            "models/oco_dukascopy_candidate",
            "--symbols",
            "EURUSD,GBPUSD,USDJPY,USDCHF,AUDUSD,USDCAD",
        ],
        [
            "make",
            "jforex-dukascopy-matrix",
            "MODEL_MONTH=2026-02",
            "START_TS=2026-02-04T00:00:00Z",
            "END_TS=2026-02-09T00:00:00Z",
            "TICK_BATCH_SIZE=1",
        ],
        [
            "make",
            "local-jforex-parity-matrix",
            "MODEL_MONTH=2026-02",
            "START_TS=2026-02-04T00:00:00Z",
            "END_TS=2026-02-09T00:00:00Z",
            "TICK_BATCH_SIZE=1",
        ],
        [
            "make",
            "full-stage14-cert",
            "LOCK_DIR=configs/research/governance/oco_history_dukascopy_candidate/2026-02",
            "EVAL_START=2026-02-07T00:00:00Z",
            "EVAL_END=2026-02-09T00:00:00Z",
        ],
    ]
```

- [ ] **Step 2: Run the targeted test to confirm it fails on current `main`**

Run:

```bash
uv run pytest -q tests/test_run_monthly_recert.py
```

Expected: FAIL because `scripts/run_monthly_recert.py` does not yet invoke `local-jforex-parity-matrix` and does not pass `TICK_BATCH_SIZE=1` to the matrix commands.

- [ ] **Step 3: Commit the red test**

Run:

```bash
git add tests/test_run_monthly_recert.py
git commit -m "test: define definitive monthly recert gate"
```

Expected: one commit containing only the failing contract test.

### Task 2: Make `run_monthly_recert.py` The Definitive Gate

**Files:**
- Modify: `scripts/run_monthly_recert.py`
- Modify: `tests/test_run_monthly_recert.py`

- [ ] **Step 1: Add the definitive-gate constants and docstring language**

Edit `scripts/run_monthly_recert.py` so the module header and constants reflect the stricter policy:

```python
#!/usr/bin/env python3
"""Run the definitive monthly Dukascopy-candidate recertification gate.

Auto-derives the model month (last complete calendar month) and test window,
runs the candidate artifact sync, then `make jforex-dukascopy-matrix`,
`make local-jforex-parity-matrix`, and `make full-stage14-cert`, then reads
the Stage 14 certification checks CSV and prints a per-symbol go/no-go summary.

Prerequisites:
  1. make retrain-all
  2. make freeze-oco-dukascopy-candidate

This command is intentionally strict. It is the canonical monthly release gate.

Exits 0 if all critical checks pass, exits 1 if any fail.
"""

DEFAULT_SYMBOLS = ("EURUSD", "GBPUSD", "USDJPY", "USDCHF", "AUDUSD", "USDCAD")
SYNC_LOCK_DIR = "configs/research/governance/oco"
SYNC_SOURCE_MODELS_DIR = "models/oco"
SYNC_TARGET_MODELS_DIR = "models/oco_dukascopy_candidate"
CERT_TICK_BATCH_SIZE = "1"
CERT_CHECKS_FILENAME = "stage14_jforex_runtime_certification_checks.csv"
```

- [ ] **Step 2: Add the local surrogate matrix and pin `TICK_BATCH_SIZE=1`**

Replace the existing orchestration block in `main()` with this exact sequence:

```python
    _sync_candidate_models()
    _run_step(
        [
            "make",
            "jforex-dukascopy-matrix",
            f"MODEL_MONTH={model_month}",
            f"START_TS={start_ts}",
            f"END_TS={end_ts}",
            f"TICK_BATCH_SIZE={CERT_TICK_BATCH_SIZE}",
        ],
        "step 2/4: jforex-dukascopy-matrix",
    )
    _run_step(
        [
            "make",
            "local-jforex-parity-matrix",
            f"MODEL_MONTH={model_month}",
            f"START_TS={start_ts}",
            f"END_TS={end_ts}",
            f"TICK_BATCH_SIZE={CERT_TICK_BATCH_SIZE}",
        ],
        "step 3/4: local-jforex-parity-matrix",
    )
    _run_step(
        [
            "make",
            "full-stage14-cert",
            f"LOCK_DIR={lock_dir}",
            f"EVAL_START={eval_start}",
            f"EVAL_END={eval_end}",
        ],
        "step 4/4: full-stage14-cert",
    )
```

Keep `_sync_candidate_models()` as step `1/4`; only the matrix/cert steps should change.

- [ ] **Step 3: Run the targeted test to verify the new contract passes**

Run:

```bash
uv run pytest -q tests/test_run_monthly_recert.py
```

Expected: PASS with `1 passed`.

- [ ] **Step 4: Sanity-check the script output path by running the module help**

Run:

```bash
uv run python scripts/run_monthly_recert.py --help
```

Expected: PASS and the description text should describe the command as the definitive monthly recertification gate.

- [ ] **Step 5: Commit the implementation**

Run:

```bash
git add scripts/run_monthly_recert.py tests/test_run_monthly_recert.py
git commit -m "feat: make monthly recert the definitive gate"
```

Expected: one commit containing the script and test updates only.
