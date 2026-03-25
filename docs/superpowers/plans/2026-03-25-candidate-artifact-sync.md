# Candidate Artifact Sync Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a strict candidate-artifact sync step that makes `models/oco_dukascopy_candidate/` match the authoritative live locks in `configs/research/governance/oco/`, run it automatically in `monthly-recert`, and ensure `promote-live` archives the certified candidate artifact lineage.

**Architecture:** Add one focused script that reads live-lock manifests, copies the authoritative month-specific model artifacts from `models/oco/` into `models/oco_dukascopy_candidate/`, and verifies copied hashes against the lock contract. Integrate that script into `run_monthly_recert.py` before certification, update `run_promote_live.py` to archive with the candidate models dir, and cover the behavior with temp-dir tests that avoid real model exports or long-running recert commands.

**Tech Stack:** Python 3.12, `pathlib`, `hashlib`, `json`, `subprocess`, `pytest`

---

### File Map

**Create:**
- `scripts/sync_candidate_model_artifacts.py` — strict sync/verify CLI for candidate artifacts
- `tests/test_sync_candidate_model_artifacts.py` — unit tests for sync helper and CLI behavior
- `tests/test_run_monthly_recert.py` — lightweight orchestration tests for recert step ordering
- `tests/test_run_promote_live.py` — lightweight orchestration tests for promote-live models-dir selection

**Modify:**
- `scripts/run_monthly_recert.py` — insert sync step before certification and update operator-facing text
- `scripts/run_promote_live.py` — archive using `models/oco_dukascopy_candidate`
- `Makefile` — update help/prerequisite wording so `monthly-recert` is documented as the sync+cert entrypoint

**Verification:**
- `uv run pytest -q tests/test_sync_candidate_model_artifacts.py`
- `uv run pytest -q tests/test_run_monthly_recert.py tests/test_run_promote_live.py`
- `uv run pytest -q tests/test_sync_candidate_model_artifacts.py tests/test_run_monthly_recert.py tests/test_run_promote_live.py`

### Task 1: Build The Sync Script With Strict Hash Verification

**Files:**
- Create: `scripts/sync_candidate_model_artifacts.py`
- Test: `tests/test_sync_candidate_model_artifacts.py`

- [ ] **Step 1: Write the failing happy-path and failure-path tests**

Add `tests/test_sync_candidate_model_artifacts.py` with focused temp-dir coverage:

```python
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from scripts.sync_candidate_model_artifacts import run


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_lock(lock_dir: Path, symbol: str, month: str, cbm: Path, thr: Path) -> None:
    payload = {
        "symbol": symbol,
        "artifacts": {
            "model_month": month,
            "model_cbm_path": f"models/oco/{symbol}_model_{month}.cbm",
            "model_cbm_sha256": _sha(cbm),
            "model_threshold_json_path": f"models/oco/{symbol}_model_{month}.json",
            "model_threshold_json_sha256": _sha(thr),
        },
    }
    (lock_dir / f"{symbol.lower()}_oco_live_lock.json").write_text(json.dumps(payload), encoding="utf-8")


def test_run_copies_candidate_artifacts_and_verifies_hashes(tmp_path: Path) -> None:
    lock_dir = tmp_path / "locks"
    source_dir = tmp_path / "models_src"
    target_dir = tmp_path / "models_dst"
    lock_dir.mkdir()
    source_dir.mkdir()
    target_dir.mkdir()

    cbm = source_dir / "EURUSD_model_2026-02.cbm"
    thr = source_dir / "EURUSD_model_2026-02.json"
    cbm.write_bytes(b"cbm")
    thr.write_text('{"threshold": 0.5}', encoding="utf-8")
    _write_lock(lock_dir, "EURUSD", "2026-02", cbm, thr)

    exit_code = run(
        lock_dir=lock_dir,
        source_models_dir=source_dir,
        target_models_dir=target_dir,
        symbols=["EURUSD"],
    )

    assert exit_code == 0
    assert (target_dir / cbm.name).read_bytes() == b"cbm"
    assert (target_dir / thr.name).read_text(encoding="utf-8") == '{"threshold": 0.5}'


def test_run_fails_when_source_artifact_missing(tmp_path: Path) -> None:
    lock_dir = tmp_path / "locks"
    source_dir = tmp_path / "models_src"
    target_dir = tmp_path / "models_dst"
    lock_dir.mkdir()
    source_dir.mkdir()
    target_dir.mkdir()

    cbm = source_dir / "EURUSD_model_2026-02.cbm"
    thr = source_dir / "EURUSD_model_2026-02.json"
    cbm.write_bytes(b"cbm")
    thr.write_text('{"threshold": 0.5}', encoding="utf-8")
    _write_lock(lock_dir, "EURUSD", "2026-02", cbm, thr)
    cbm.unlink()

    exit_code = run(
        lock_dir=lock_dir,
        source_models_dir=source_dir,
        target_models_dir=target_dir,
        symbols=["EURUSD"],
    )

    assert exit_code == 1
    assert not (target_dir / "EURUSD_model_2026-02.cbm").exists()


def test_run_fails_when_source_hash_does_not_match_lock(tmp_path: Path) -> None:
    lock_dir = tmp_path / "locks"
    source_dir = tmp_path / "models_src"
    target_dir = tmp_path / "models_dst"
    lock_dir.mkdir()
    source_dir.mkdir()
    target_dir.mkdir()

    cbm = source_dir / "EURUSD_model_2026-02.cbm"
    thr = source_dir / "EURUSD_model_2026-02.json"
    cbm.write_bytes(b"expected")
    thr.write_text('{"threshold": 0.5}', encoding="utf-8")
    _write_lock(lock_dir, "EURUSD", "2026-02", cbm, thr)
    cbm.write_bytes(b"actual")

    exit_code = run(
        lock_dir=lock_dir,
        source_models_dir=source_dir,
        target_models_dir=target_dir,
        symbols=["EURUSD"],
    )

    assert exit_code == 1


def test_run_reports_mixed_symbol_outcomes_and_exits_nonzero(tmp_path: Path) -> None:
    lock_dir = tmp_path / "locks"
    source_dir = tmp_path / "models_src"
    target_dir = tmp_path / "models_dst"
    lock_dir.mkdir()
    source_dir.mkdir()
    target_dir.mkdir()

    eur_cbm = source_dir / "EURUSD_model_2026-02.cbm"
    eur_thr = source_dir / "EURUSD_model_2026-02.json"
    eur_cbm.write_bytes(b"eur")
    eur_thr.write_text('{"threshold": 0.5}', encoding="utf-8")
    _write_lock(lock_dir, "EURUSD", "2026-02", eur_cbm, eur_thr)

    gbp_cbm = source_dir / "GBPUSD_model_2026-02.cbm"
    gbp_thr = source_dir / "GBPUSD_model_2026-02.json"
    gbp_cbm.write_bytes(b"gbp")
    gbp_thr.write_text('{"threshold": 0.6}', encoding="utf-8")
    _write_lock(lock_dir, "GBPUSD", "2026-02", gbp_cbm, gbp_thr)
    gbp_thr.unlink()

    exit_code = run(
        lock_dir=lock_dir,
        source_models_dir=source_dir,
        target_models_dir=target_dir,
        symbols=["EURUSD", "GBPUSD"],
    )

    assert exit_code == 1
    assert (target_dir / "EURUSD_model_2026-02.cbm").exists()
    assert not (target_dir / "GBPUSD_model_2026-02.json").exists()
```

- [ ] **Step 2: Run the new test file and verify it fails for the right reason**

Run:

```bash
uv run pytest -q tests/test_sync_candidate_model_artifacts.py
```

Expected:
- `FAIL`
- import error or missing `scripts.sync_candidate_model_artifacts`

- [ ] **Step 3: Write the minimal sync script implementation**

Create `scripts/sync_candidate_model_artifacts.py`:

```python
#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path


def _sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


@dataclass(frozen=True)
class SyncResult:
    symbol: str
    model_month: str
    status: str
    detail: str


def _iter_locks(lock_dir: Path, symbols: list[str]) -> list[Path]:
    wanted = {s.upper() for s in symbols}
    out: list[Path] = []
    for path in sorted(lock_dir.glob("*_oco_live_lock.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        symbol = str(payload.get("symbol", "")).upper().strip()
        if symbol and (not wanted or symbol in wanted):
            out.append(path)
    return out


def run(
    *,
    lock_dir: Path,
    source_models_dir: Path,
    target_models_dir: Path,
    symbols: list[str],
) -> int:
    results: list[SyncResult] = []
    target_models_dir.mkdir(parents=True, exist_ok=True)
    for lock_path in _iter_locks(lock_dir, symbols):
        payload = json.loads(lock_path.read_text(encoding="utf-8"))
        symbol = str(payload["symbol"]).upper().strip()
        artifacts = payload.get("artifacts", {})
        month = str(artifacts.get("model_month", "")).strip()
        cbm_name = Path(str(artifacts.get("model_cbm_path", "")).strip()).name
        thr_name = Path(str(artifacts.get("model_threshold_json_path", "")).strip()).name
        expected_cbm_sha = str(artifacts.get("model_cbm_sha256", "")).strip()
        expected_thr_sha = str(artifacts.get("model_threshold_json_sha256", "")).strip()
        source_cbm = source_models_dir / cbm_name
        source_thr = source_models_dir / thr_name
        target_cbm = target_models_dir / cbm_name
        target_thr = target_models_dir / thr_name

        if not month or not cbm_name or not thr_name or not expected_cbm_sha or not expected_thr_sha:
            results.append(SyncResult(symbol, month, "FAIL", "malformed lock artifact metadata"))
            continue
        if not source_cbm.exists():
            results.append(SyncResult(symbol, month, "FAIL", f"missing source {source_cbm}"))
            continue
        if not source_thr.exists():
            results.append(SyncResult(symbol, month, "FAIL", f"missing source {source_thr}"))
            continue
        got_cbm_sha = _sha(source_cbm)
        got_thr_sha = _sha(source_thr)
        if got_cbm_sha != expected_cbm_sha:
            results.append(SyncResult(symbol, month, "FAIL", f"cbm hash mismatch expected={expected_cbm_sha} actual={got_cbm_sha}"))
            continue
        if got_thr_sha != expected_thr_sha:
            results.append(SyncResult(symbol, month, "FAIL", f"json hash mismatch expected={expected_thr_sha} actual={got_thr_sha}"))
            continue

        shutil.copy2(source_cbm, target_cbm)
        shutil.copy2(source_thr, target_thr)
        results.append(SyncResult(symbol, month, "PASS", f"{source_cbm} -> {target_cbm}"))

    for row in results:
        print(f"[candidate-sync] {row.symbol} {row.model_month} {row.status} {row.detail}", flush=True)
    return 0 if results and all(r.status == "PASS" for r in results) else 1


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lock-dir", default="configs/research/governance/oco")
    parser.add_argument("--source-models-dir", default="models/oco")
    parser.add_argument("--target-models-dir", default="models/oco_dukascopy_candidate")
    parser.add_argument("--symbols", default="")
    args = parser.parse_args()

    symbols = [s.strip().upper() for s in str(args.symbols).split(",") if s.strip()]
    raise SystemExit(
        run(
            lock_dir=Path(args.lock_dir),
            source_models_dir=Path(args.source_models_dir),
            target_models_dir=Path(args.target_models_dir),
            symbols=symbols,
        )
    )


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run the sync-script tests and verify they pass**

Run:

```bash
uv run pytest -q tests/test_sync_candidate_model_artifacts.py
```

Expected:
- `4 passed`

- [ ] **Step 5: Commit the sync script and tests**

Run:

```bash
git add scripts/sync_candidate_model_artifacts.py tests/test_sync_candidate_model_artifacts.py
git commit -m "feat: sync candidate model artifacts from live locks"
```

### Task 2: Integrate Candidate Sync Into Monthly Recert

**Files:**
- Modify: `scripts/run_monthly_recert.py`
- Create: `tests/test_run_monthly_recert.py`

- [ ] **Step 1: Write the failing orchestration test for recert step ordering**

Create `tests/test_run_monthly_recert.py`:

```python
from __future__ import annotations

from scripts import run_monthly_recert


def test_monthly_recert_runs_candidate_sync_before_cert(monkeypatch) -> None:
    calls: list[tuple[list[str], str]] = []

    def fake_run_step(cmd: list[str], label: str) -> None:
        calls.append((cmd, label))

    monkeypatch.setattr(run_monthly_recert, "_run_step", fake_run_step)
    monkeypatch.setattr(run_monthly_recert, "_read_failures", lambda report_dir: {})
    monkeypatch.setattr(run_monthly_recert, "_print_summary", lambda model_month, failures: True)
    monkeypatch.setattr(
        run_monthly_recert,
        "_derive_params",
        lambda **_: ("2026-02", "2026-02-04T00:00:00Z", "2026-02-09T00:00:00Z", "2026-02-07T00:00:00Z", "2026-02-09T00:00:00Z"),
    )
    monkeypatch.setattr(
        run_monthly_recert,
        "sys",
        type("Sys", (), {"argv": ["run_monthly_recert.py"]}),
    )

    run_monthly_recert.main()

    assert calls[0][0][:2] == ["uv", "run"]
    assert calls[0][0][2:] == [
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
    ]
    assert calls[1][0][0:2] == ["make", "jforex-dukascopy-matrix"]
    assert calls[2][0][0:2] == ["make", "full-stage14-cert"]
```

- [ ] **Step 2: Run the new recert test and verify it fails**

Run:

```bash
uv run pytest -q tests/test_run_monthly_recert.py
```

Expected:
- `FAIL`
- assertion showing the sync step is missing from the call list

- [ ] **Step 3: Implement the recert sync step**

Update `scripts/run_monthly_recert.py`:

```python
DEFAULT_SYMBOLS = ("EURUSD", "GBPUSD", "USDJPY", "USDCHF", "AUDUSD", "USDCAD")
LOCK_DIR = "configs/research/governance/oco"
SOURCE_MODELS_DIR = "models/oco"
TARGET_MODELS_DIR = "models/oco_dukascopy_candidate"


def _sync_candidate_artifacts() -> None:
    _run_step(
        [
            "uv",
            "run",
            "python",
            "scripts/sync_candidate_model_artifacts.py",
            "--lock-dir",
            LOCK_DIR,
            "--source-models-dir",
            SOURCE_MODELS_DIR,
            "--target-models-dir",
            TARGET_MODELS_DIR,
            "--symbols",
            ",".join(DEFAULT_SYMBOLS),
        ],
        "step 0/3: sync candidate artifacts",
    )


def main() -> None:
    ...
    print(
        f"[monthly-recert] running for MODEL_MONTH={model_month} "
        f"window={start_ts[:10]}→{end_ts[:10]}",
        flush=True,
    )

    _sync_candidate_artifacts()
    _run_step(
        ["make", "jforex-dukascopy-matrix", f"MODEL_MONTH={model_month}", f"START_TS={start_ts}", f"END_TS={end_ts}"],
        "step 1/3: jforex-dukascopy-matrix",
    )
    _run_step(
        ["make", "full-stage14-cert", f"LOCK_DIR={lock_dir}", f"EVAL_START={eval_start}", f"EVAL_END={eval_end}"],
        "step 2/3: full-stage14-cert",
    )
```

Also update the module docstring/prerequisite comments so `monthly-recert` is described as the sync+cert entrypoint rather than assuming the candidate dir was manually prepared.

- [ ] **Step 4: Run the recert orchestration test and verify it passes**

Run:

```bash
uv run pytest -q tests/test_run_monthly_recert.py
```

Expected:
- `1 passed`

- [ ] **Step 5: Commit the recert integration**

Run:

```bash
git add scripts/run_monthly_recert.py tests/test_run_monthly_recert.py
git commit -m "feat: sync candidate artifacts before monthly recert"
```

### Task 3: Archive The Certified Candidate Models In Promote-Live

**Files:**
- Modify: `scripts/run_promote_live.py`
- Create: `tests/test_run_promote_live.py`

- [ ] **Step 1: Write the failing promote-live models-dir test**

Create `tests/test_run_promote_live.py`:

```python
from __future__ import annotations

from scripts import run_promote_live


def test_promote_live_archives_candidate_models_dir(monkeypatch) -> None:
    captured: dict[str, list[str]] = {}

    def fake_run(cmd: list[str], cwd=None):
        captured["cmd"] = cmd
        class Result:
            returncode = 0
        return Result()

    monkeypatch.setattr(run_promote_live, "_verify_cert", lambda report_dir: None)
    monkeypatch.setattr(run_promote_live.subprocess, "run", fake_run)
    monkeypatch.setattr(
        run_promote_live,
        "sys",
        type("Sys", (), {"argv": ["run_promote_live.py", "--model-month", "2026-02"]}),
    )

    run_promote_live.main()

    assert "--models-dir" in captured["cmd"]
    idx = captured["cmd"].index("--models-dir")
    assert captured["cmd"][idx + 1] == "models/oco_dukascopy_candidate"
```

- [ ] **Step 2: Run the promote-live test and verify it fails**

Run:

```bash
uv run pytest -q tests/test_run_promote_live.py
```

Expected:
- `FAIL`
- assertion showing `models/oco` is still used

- [ ] **Step 3: Update promote-live to archive the candidate models dir**

Modify `scripts/run_promote_live.py`:

```python
    result = subprocess.run(
        [
            sys.executable,
            "scripts/freeze_oco_historical_governance.py",
            "--symbols",
            DEFAULT_SYMBOLS,
            "--out-dir",
            "configs/research/governance/oco_history_dukascopy_candidate",
            "--months",
            model_month,
            "--config-dir",
            "configs/research/experiments_dukascopy_candidate",
            "--analysis-dir",
            "data/analysis/tick_opportunity_mining_dukascopy_candidate",
            "--models-dir",
            "models/oco_dukascopy_candidate",
        ],
        cwd=_repo_root(),
    )
```

- [ ] **Step 4: Run the promote-live test and verify it passes**

Run:

```bash
uv run pytest -q tests/test_run_promote_live.py
```

Expected:
- `1 passed`

- [ ] **Step 5: Commit the promote-live fix**

Run:

```bash
git add scripts/run_promote_live.py tests/test_run_promote_live.py
git commit -m "fix: archive certified candidate models in promote-live"
```

### Task 4: Update Operator-Facing Makefile Text And Run Final Verification

**Files:**
- Modify: `Makefile`
- Test: `tests/test_sync_candidate_model_artifacts.py`
- Test: `tests/test_run_monthly_recert.py`
- Test: `tests/test_run_promote_live.py`

- [ ] **Step 1: Update Makefile help/prerequisite wording**

Modify the relevant help strings and comments in `Makefile` so they reflect the new contract:

```makefile
monthly-recert:
	UV_CACHE_DIR=$(or $(UV_CACHE_DIR),.uv_cache) uv run python scripts/run_monthly_recert.py \
		$(if $(MODEL_MONTH),--model-month "$(MODEL_MONTH)",) \
		$(if $(START_TS),--start-ts "$(START_TS)",) \
		$(if $(END_TS),--end-ts "$(END_TS)",) \
		$(if $(EVAL_START),--eval-start "$(EVAL_START)",) \
		$(if $(EVAL_END),--eval-end "$(EVAL_END)",) \
		--report-dir $(or $(REPORT_DIR),data/analysis/backtest_reconcile)

# help text
	@printf "  $(COLOR_TARGET)%-18s$(COLOR_RESET) $(COLOR_DESC)%s$(COLOR_RESET)\n" "monthly-recert" "Sync candidate artifacts from models/oco/, run dukascopy-candidate recertification, and print go/no-go summary"
	@printf "  $(COLOR_TARGET)%-18s$(COLOR_RESET) $(COLOR_DESC)%s$(COLOR_RESET)\n" "promote-live" "Archive certified candidate locks/models lineage to oco_history_dukascopy_candidate/ and print restart reminder"
```

Keep the target behavior unchanged; only update operator-facing wording.

- [ ] **Step 2: Run the focused verification suite**

Run:

```bash
uv run pytest -q tests/test_sync_candidate_model_artifacts.py tests/test_run_monthly_recert.py tests/test_run_promote_live.py
```

Expected:
- all tests pass

- [ ] **Step 3: Run an optional smoke command against a temp candidate dir if time permits**

Run:

```bash
uv run python scripts/sync_candidate_model_artifacts.py --lock-dir configs/research/governance/oco --source-models-dir models/oco --target-models-dir /tmp/behemoth_candidate_sync_smoke --symbols EURUSD
```

Expected:
- either `PASS` for `EURUSD` if root artifacts already match the live lock
- or a precise hash-mismatch/missing-file error proving the script fails loudly and specifically

- [ ] **Step 4: Commit the Makefile wording and final verified state**

Run:

```bash
git add Makefile tests/test_sync_candidate_model_artifacts.py tests/test_run_monthly_recert.py tests/test_run_promote_live.py
git commit -m "docs: update candidate recert operator flow"
```

- [ ] **Step 5: Record final operator outcome in the handoff**

Include in the execution handoff:

```text
- whether `models/oco/` currently contains a full lock-consistent 2026-02 artifact set
- exact failing symbols if sync still fails
- whether `make monthly-recert` is now sufficient to prepare candidate artifacts before certification
- confirmation that `make promote-live` archives from models/oco_dukascopy_candidate
```
