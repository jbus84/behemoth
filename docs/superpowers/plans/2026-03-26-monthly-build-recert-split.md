# Monthly Build / Recert Split Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Split the monthly candidate workflow into `monthly-build` for frozen month bundle creation and `monthly-recert` for certification-only execution, with `promote-live` archiving only after cert passes.

**Architecture:** Reuse the existing sync and historical-freeze machinery instead of inventing a new pipeline. Add a new build script that materializes `configs/research/governance/oco_candidate_builds/<YYYY-MM>/`, make recert consume that bundle rather than `oco_history_dukascopy_candidate/<YYYY-MM>`, and make promotion archive from the certified build bundle into promoted history.

**Tech Stack:** Python 3.12, existing Makefile targets, pytest, pandas/duckdb-based governance scripts

---

## File Structure

- Create: `scripts/run_monthly_build.py`
  - Sole responsibility: produce a frozen month-scoped candidate certification bundle.
- Modify: `scripts/run_monthly_recert.py`
  - Sole responsibility: run certification against an existing built month bundle.
- Modify: `scripts/run_promote_live.py`
  - Sole responsibility: archive the certified build bundle into promoted history after cert passes.
- Modify: `Makefile`
  - Add `monthly-build` target and update help text.
- Create: `tests/test_run_monthly_build.py`
  - Cover monthly build orchestration and output path.
- Modify: `tests/test_run_monthly_recert.py`
  - Cover build-bundle consumption and missing-bundle failures.
- Modify: `tests/test_run_promote_live.py`
  - Cover archive source/target behavior from candidate builds to promoted history.

### Task 1: Add `monthly-build` Command

**Files:**
- Create: `scripts/run_monthly_build.py`
- Create: `tests/test_run_monthly_build.py`
- Reference: `scripts/run_monthly_recert.py`
- Reference: `scripts/run_promote_live.py`

- [ ] **Step 1: Write the failing orchestration test for `monthly-build`**

Add `tests/test_run_monthly_build.py` with:

```python
from __future__ import annotations

from types import SimpleNamespace

import scripts.run_monthly_build as run_monthly_build


def test_main_builds_candidate_month_bundle(monkeypatch) -> None:
    calls: list[list[str]] = []

    def fake_run(cmd, cwd=None):
        calls.append(cmd)
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(run_monthly_build.subprocess, "run", fake_run)
    monkeypatch.setattr(
        run_monthly_build,
        "_derive_model_month",
        lambda override=None: "2026-02",
    )
    monkeypatch.setattr(
        run_monthly_build.sys,
        "argv",
        ["run_monthly_build.py"],
    )

    run_monthly_build.main()

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
            "uv",
            "run",
            "python",
            "scripts/freeze_oco_historical_governance.py",
            "--symbols",
            "EURUSD,GBPUSD,USDJPY,USDCHF,AUDUSD,USDCAD",
            "--out-dir",
            "configs/research/governance/oco_candidate_builds",
            "--months",
            "2026-02",
            "--config-dir",
            "configs/research/experiments_dukascopy_candidate",
            "--analysis-dir",
            "data/analysis/tick_opportunity_mining_dukascopy_candidate",
            "--models-dir",
            "models/oco_dukascopy_candidate",
        ],
    ]
```

- [ ] **Step 2: Run the test to verify it fails**

Run:

```bash
uv run pytest -q tests/test_run_monthly_build.py
```

Expected: FAIL with `ModuleNotFoundError` for `scripts.run_monthly_build` or equivalent missing-implementation error.

- [ ] **Step 3: Write the minimal `monthly-build` implementation**

Create `scripts/run_monthly_build.py`:

```python
#!/usr/bin/env python3
from __future__ import annotations

import argparse
import subprocess
import sys
from datetime import date
from pathlib import Path

DEFAULT_SYMBOLS = "EURUSD,GBPUSD,USDJPY,USDCHF,AUDUSD,USDCAD"
SYNC_LOCK_DIR = "configs/research/governance/oco"
SYNC_SOURCE_MODELS_DIR = "models/oco"
SYNC_TARGET_MODELS_DIR = "models/oco_dukascopy_candidate"
BUILD_OUT_DIR = "configs/research/governance/oco_candidate_builds"


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _derive_model_month(override: str | None = None) -> str:
    if override:
        return override
    today = date.today()
    if today.month == 1:
        return f"{today.year - 1:04d}-12"
    return f"{today.year:04d}-{today.month - 1:02d}"


def _run_step(cmd: list[str], label: str) -> None:
    print(f"[monthly-build] {label}", flush=True)
    result = subprocess.run(cmd, cwd=_repo_root())
    if result.returncode != 0:
        raise SystemExit(f"[monthly-build] {label} failed (rc={result.returncode})")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-month", help="Override model month YYYY-MM")
    args = parser.parse_args()

    model_month = _derive_model_month(args.model_month)

    _run_step(
        [
            "uv",
            "run",
            "python",
            "scripts/sync_candidate_model_artifacts.py",
            "--lock-dir",
            SYNC_LOCK_DIR,
            "--source-models-dir",
            SYNC_SOURCE_MODELS_DIR,
            "--target-models-dir",
            SYNC_TARGET_MODELS_DIR,
            "--symbols",
            DEFAULT_SYMBOLS,
        ],
        "step 1/2: sync_candidate_model_artifacts",
    )
    _run_step(
        [
            "uv",
            "run",
            "python",
            "scripts/freeze_oco_historical_governance.py",
            "--symbols",
            DEFAULT_SYMBOLS,
            "--out-dir",
            BUILD_OUT_DIR,
            "--months",
            model_month,
            "--config-dir",
            "configs/research/experiments_dukascopy_candidate",
            "--analysis-dir",
            "data/analysis/tick_opportunity_mining_dukascopy_candidate",
            "--models-dir",
            SYNC_TARGET_MODELS_DIR,
        ],
        "step 2/2: freeze_candidate_month_bundle",
    )


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run the test to verify it passes**

Run:

```bash
uv run pytest -q tests/test_run_monthly_build.py
```

Expected: PASS with `1 passed`.

- [ ] **Step 5: Commit Task 1**

```bash
git add scripts/run_monthly_build.py tests/test_run_monthly_build.py
git commit -m "feat: add monthly build command"
```

### Task 2: Make `monthly-recert` Consume a Built Month Bundle

**Files:**
- Modify: `scripts/run_monthly_recert.py`
- Modify: `tests/test_run_monthly_recert.py`

- [ ] **Step 1: Write failing tests for the new recert contract**

Update `tests/test_run_monthly_recert.py` to add:

```python
def test_main_uses_candidate_build_bundle_for_stage14(monkeypatch) -> None:
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
    monkeypatch.setattr(run_monthly_recert.Path, "exists", lambda self: True)

    run_monthly_recert.main()

    assert calls[-1] == [
        "make",
        "full-stage14-cert",
        "LOCK_DIR=configs/research/governance/oco_candidate_builds/2026-02",
        "EVAL_START=2026-02-07T00:00:00Z",
        "EVAL_END=2026-02-09T00:00:00Z",
    ]


def test_main_fails_when_candidate_build_bundle_is_missing(monkeypatch) -> None:
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
    monkeypatch.setattr(run_monthly_recert.Path, "exists", lambda self: False)

    with pytest.raises(SystemExit, match="run make monthly-build"):
        run_monthly_recert.main()
```

- [ ] **Step 2: Run the recert tests to verify they fail**

Run:

```bash
uv run pytest -q tests/test_run_monthly_recert.py
```

Expected: FAIL because `run_monthly_recert.py` still syncs models itself and still points Stage 14 at `oco_history_dukascopy_candidate/<month>`.

- [ ] **Step 3: Implement the recert-only behavior**

Update `scripts/run_monthly_recert.py` to:

```python
BUILD_BUNDLE_DIR = "configs/research/governance/oco_candidate_builds"
```

Replace the current sync step and lock-dir logic with:

```python
    lock_dir = f"{BUILD_BUNDLE_DIR}/{model_month}"
    if not Path(_repo_root() / lock_dir).exists():
        raise SystemExit(
            f"[monthly-recert] candidate month bundle not found: {_repo_root() / lock_dir}; "
            "run make monthly-build first"
        )
```

Delete the `_sync_candidate_models()` call, and keep only:

```python
    _run_step(
        [
            "make",
            "jforex-dukascopy-matrix",
            f"MODEL_MONTH={model_month}",
            f"START_TS={start_ts}",
            f"END_TS={end_ts}",
            f"TICK_BATCH_SIZE={CERT_TICK_BATCH_SIZE}",
        ],
        "step 1/3: jforex-dukascopy-matrix",
    )
    _run_step(
        [
            "make",
            "local-jforex-parity-matrix",
            f"MODEL_MONTH={model_month}",
            f"START_TS={eval_start}",
            f"END_TS={eval_end}",
            f"TICK_BATCH_SIZE={CERT_TICK_BATCH_SIZE}",
        ],
        "step 2/3: local-jforex-parity-matrix",
    )
    _run_step(
        ["make", "full-stage14-cert", f"LOCK_DIR={lock_dir}", f"EVAL_START={eval_start}", f"EVAL_END={eval_end}"],
        "step 3/3: full-stage14-cert",
    )
```

- [ ] **Step 4: Run the recert tests to verify they pass**

Run:

```bash
uv run pytest -q tests/test_run_monthly_recert.py
```

Expected: PASS.

- [ ] **Step 5: Commit Task 2**

```bash
git add scripts/run_monthly_recert.py tests/test_run_monthly_recert.py
git commit -m "refactor: make monthly recert consume built month bundles"
```

### Task 3: Archive the Certified Build Bundle in `promote-live`

**Files:**
- Modify: `scripts/run_promote_live.py`
- Modify: `tests/test_run_promote_live.py`

- [ ] **Step 1: Write the failing promotion test**

Update `tests/test_run_promote_live.py` so the expected call becomes:

```python
    assert calls == [
        [
            run_promote_live.sys.executable,
            "scripts/freeze_oco_historical_governance.py",
            "--symbols",
            "EURUSD,GBPUSD,USDJPY,USDCHF,AUDUSD,USDCAD",
            "--out-dir",
            "configs/research/governance/oco_history_dukascopy_candidate",
            "--months",
            "2026-02",
            "--config-dir",
            "configs/research/experiments_dukascopy_candidate",
            "--analysis-dir",
            "data/analysis/tick_opportunity_mining_dukascopy_candidate",
            "--models-dir",
            "models/oco_dukascopy_candidate",
            "--source-lock-dir",
            "configs/research/governance/oco_candidate_builds/2026-02",
        ]
    ]
```

If `freeze_oco_historical_governance.py` does not support a source lock dir, write the failing test first and then implement the smaller alternative below: copy the already-built month bundle directly with Python filesystem operations. In that alternative, test for a `copytree`/`copy2`-based archive behavior instead of a refreeze subprocess.

- [ ] **Step 2: Run the promotion test to verify it fails**

Run:

```bash
uv run pytest -q tests/test_run_promote_live.py
```

Expected: FAIL because `run_promote_live.py` still rebuilds directly from mutable candidate inputs.

- [ ] **Step 3: Implement the minimal archive-from-build behavior**

Preferred implementation if refreeze-from-source-locks is unsupported:

```python
import shutil

BUILD_BUNDLE_ROOT = "configs/research/governance/oco_candidate_builds"
PROMOTED_HISTORY_ROOT = "configs/research/governance/oco_history_dukascopy_candidate"
```

Then in `main()`:

```python
    build_dir = _repo_root() / BUILD_BUNDLE_ROOT / model_month
    target_dir = _repo_root() / PROMOTED_HISTORY_ROOT / model_month
    if not build_dir.exists():
        raise SystemExit(
            f"[promote-live] certified build bundle not found: {build_dir}; "
            "run make monthly-build and make monthly-recert first"
        )
    if target_dir.exists():
        shutil.rmtree(target_dir)
    shutil.copytree(build_dir, target_dir)
```

Keep `_verify_cert(...)` unchanged so promotion still requires a passing cert.

- [ ] **Step 4: Run the promotion tests to verify they pass**

Run:

```bash
uv run pytest -q tests/test_run_promote_live.py
```

Expected: PASS.

- [ ] **Step 5: Commit Task 3**

```bash
git add scripts/run_promote_live.py tests/test_run_promote_live.py
git commit -m "refactor: promote certified monthly build bundles"
```

### Task 4: Add the Makefile Target and Help Text

**Files:**
- Modify: `Makefile`

- [ ] **Step 1: Write the failing Makefile/help expectations as a lightweight grep check**

Add this verification command to your working notes and use it after editing:

```bash
rg -n "monthly-build|monthly-recert|promote-live" Makefile
```

Expected before implementation: no `monthly-build` target exists.

- [ ] **Step 2: Add the new `monthly-build` target and update help text**

Add a target near `monthly-recert`:

```make
monthly-build:
	UV_CACHE_DIR=$(or $(UV_CACHE_DIR),.uv_cache) uv run python scripts/run_monthly_build.py \
		$(if $(MODEL_MONTH),--model-month "$(MODEL_MONTH)",)
```

Update help descriptions to:

```make
	@printf "  $(COLOR_TARGET)%-18s$(COLOR_RESET) $(COLOR_DESC)%s$(COLOR_RESET)\n" "monthly-build" "Freeze a month-scoped candidate certification bundle for later recert"
	@printf "  $(COLOR_TARGET)%-18s$(COLOR_RESET) $(COLOR_DESC)%s$(COLOR_RESET)\n" "monthly-recert" "Run definitive certification against an existing month-scoped candidate build bundle"
	@printf "  $(COLOR_TARGET)%-18s$(COLOR_RESET) $(COLOR_DESC)%s$(COLOR_RESET)\n" "promote-live" "Archive a certified candidate build bundle to oco_history_dukascopy_candidate/ and print restart reminder"
```

Also add `monthly-build` to `.PHONY`.

- [ ] **Step 3: Run the Makefile verification**

Run:

```bash
rg -n "monthly-build|monthly-recert|promote-live" Makefile
```

Expected: `monthly-build` target and updated help text appear.

- [ ] **Step 4: Commit Task 4**

```bash
git add Makefile
git commit -m "build: add monthly build target"
```

### Task 5: Run End-to-End Targeted Verification

**Files:**
- Verify: `scripts/run_monthly_build.py`
- Verify: `scripts/run_monthly_recert.py`
- Verify: `scripts/run_promote_live.py`
- Verify: `tests/test_run_monthly_build.py`
- Verify: `tests/test_run_monthly_recert.py`
- Verify: `tests/test_run_promote_live.py`

- [ ] **Step 1: Run the orchestration test suite**

Run:

```bash
uv run pytest -q tests/test_run_monthly_build.py tests/test_run_monthly_recert.py tests/test_run_promote_live.py
```

Expected: all tests pass.

- [ ] **Step 2: Run CLI help for the new/changed commands**

Run:

```bash
uv run python scripts/run_monthly_build.py --help
uv run python scripts/run_monthly_recert.py --help
uv run python scripts/run_promote_live.py --help
```

Expected: each command exits 0 and prints usage text.

- [ ] **Step 3: Run a lightweight build-then-recert smoke flow**

Run:

```bash
uv run python scripts/run_monthly_build.py --model-month 2026-02
uv run python scripts/run_monthly_recert.py --model-month 2026-02
```

Expected:

- `monthly-build` creates `configs/research/governance/oco_candidate_builds/2026-02/`
- `monthly-recert` no longer fails on `oco_history_dukascopy_candidate/2026-02` missing
- any remaining failure is a real downstream certification issue, not the old lock-dir contract bug

- [ ] **Step 4: Review repo state**

Run:

```bash
git status --short
```

Expected: only intentional tracked changes or known generated artifacts remain.

- [ ] **Step 5: Commit any final adjustments from verification**

```bash
git add scripts/run_monthly_build.py scripts/run_monthly_recert.py scripts/run_promote_live.py Makefile tests/test_run_monthly_build.py tests/test_run_monthly_recert.py tests/test_run_promote_live.py
git commit -m "test: cover monthly build and recert split"
```
