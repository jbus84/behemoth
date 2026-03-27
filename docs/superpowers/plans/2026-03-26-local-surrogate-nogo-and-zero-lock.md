# Local Surrogate NO_GO And Zero-Lock Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `monthly-recert` pass when all deployable symbols certify and the only non-pass symbols are expected governance `NO_GO` cases such as `USDCAD 2026-02 no_gate_states`.

**Architecture:** Keep the existing monthly build / recert split and fix only the validator layer. `validate_local_jforex_surrogate.py` becomes lock-aware, drops the bogus Stage 12 dependency, and treats zero-lock windows as acceptable. `validate_stage14_jforex_runtime_certification.py` then consumes that richer local-surrogate verdict and allows `NO_GO` only for historically non-deployable symbol-months.

**Tech Stack:** Python 3.13, pandas, pytest, CSV/JSON governance artifacts, repo Make targets

---

### Task 1: Lock The Local-Surrogate Policy In Tests

**Files:**
- Modify: `tests/test_validate_local_jforex_surrogate.py`
- Test: `tests/test_validate_local_jforex_surrogate.py`

- [ ] **Step 1: Replace the old Stage 12 bridge test with deployable/non-deployable policy tests**

```python
def test_build_artifacts_marks_historical_nogo_from_lock(tmp_path: Path) -> None:
    from scripts.validate_local_jforex_surrogate import build_artifacts

    lock_dir = tmp_path / "locks"
    lock_dir.mkdir()
    (lock_dir / "usdcad_oco_live_lock.json").write_text(
        json.dumps(
            {
                "symbol": "USDCAD",
                "historical_deployable": False,
                "non_deployable_reason": "no_gate_states",
            }
        ),
        encoding="utf-8",
    )

    summary, checks = build_artifacts(
        symbols=["USDCAD"],
        lock_dir=lock_dir,
        local_signal_summary_glob="",
        local_execution_summary_glob="",
        local_lifecycle_summary_glob="",
        local_operational_summary_glob="",
        local_outcome_summary_glob="",
        out_summary_csv=tmp_path / "summary.csv",
        out_checks_csv=tmp_path / "checks.csv",
        report_out=tmp_path / "report.md",
    )

    assert summary.loc[0, "verdict"] == "nogo"
    assert bool(summary.loc[0, "local_jforex_surrogate_pass"]) is False
    assert bool(summary.loc[0, "historical_deployable"]) is False
    assert summary.loc[0, "non_deployable_reason"] == "no_gate_states"
```

- [ ] **Step 2: Add a zero-lock / zero-order pass test for deployable symbols**

```python
def test_build_artifacts_allows_zero_lock_zero_order_window(tmp_path: Path) -> None:
    from scripts.validate_local_jforex_surrogate import build_artifacts

    lock_dir = tmp_path / "locks"
    lock_dir.mkdir()
    (lock_dir / "eurusd_oco_live_lock.json").write_text(
        json.dumps({"symbol": "EURUSD", "historical_deployable": True}),
        encoding="utf-8",
    )
    execution_csv = tmp_path / "EURUSD_local_jforex_execution_parity_summary.csv"
    pd.DataFrame(
        [
            {
                "symbol": "EURUSD",
                "jforex_execution_parity_pass": False,
                "locked_selected_total": 0,
                "submitted_orders": 0,
            }
        ]
    ).to_csv(execution_csv, index=False)

    summary, checks = build_artifacts(
        symbols=["EURUSD"],
        lock_dir=lock_dir,
        local_signal_summary_glob="",
        local_execution_summary_glob=str(execution_csv),
        local_lifecycle_summary_glob="",
        local_operational_summary_glob="",
        local_outcome_summary_glob="",
        out_summary_csv=tmp_path / "summary.csv",
        out_checks_csv=tmp_path / "checks.csv",
        report_out=tmp_path / "report.md",
    )

    execution_check = checks[checks["metric_name"] == "local_execution_parity_pass"].iloc[0]
    assert execution_check["status"] == "pass"
    assert summary.loc[0, "verdict"] == "green"
```

- [ ] **Step 3: Run the local-surrogate validator tests and confirm the new cases fail**

Run:

```bash
uv run pytest -q tests/test_validate_local_jforex_surrogate.py
```

Expected: FAIL because `build_artifacts()` does not accept `lock_dir`, still expects `stage12_api_parity_pass`, and still marks zero-order execution as red.

- [ ] **Step 4: Commit the failing-test checkpoint**

```bash
git add tests/test_validate_local_jforex_surrogate.py
git commit -m "test: define local surrogate nogo and zero-lock policy"
```

### Task 2: Implement Local-Surrogate NO_GO And Zero-Lock Semantics

**Files:**
- Modify: `scripts/validate_local_jforex_surrogate.py`
- Test: `tests/test_validate_local_jforex_surrogate.py`

- [ ] **Step 1: Add lock loading and per-symbol governance metadata**

```python
def _load_lock_metadata(lock_dir: Path, symbol: str) -> dict[str, Any]:
    path = lock_dir / f"{symbol.lower()}_oco_live_lock.json"
    if not path.exists():
        return {"historical_deployable": True, "non_deployable_reason": ""}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return {
        "historical_deployable": bool(payload.get("historical_deployable", True)),
        "non_deployable_reason": str(payload.get("non_deployable_reason") or ""),
    }
```

- [ ] **Step 2: Remove the bogus Stage 12 source and teach execution checks about zero-lock windows**

```python
sources = [
    InputSource(
        "local_signal_parity_pass",
        local_signal_summary_glob,
        ("jforex_signal_parity_pass", "signal_parity_pass", "overall_pass"),
    ),
    InputSource(
        "local_execution_parity_pass",
        local_execution_summary_glob,
        ("jforex_execution_parity_pass", "execution_parity_pass", "overall_pass"),
    ),
    InputSource(
        "local_lifecycle_pass",
        local_lifecycle_summary_glob,
        ("oco_lifecycle_pass", "lifecycle_pass", "overall_pass"),
    ),
    InputSource(
        "local_operational_ready_pass",
        local_operational_summary_glob,
        ("operational_ready_pass", "overall_pass"),
    ),
    InputSource(
        "jforex_outcome_parity_pass",
        local_outcome_summary_glob,
        ("jforex_outcome_parity_pass", "overall_pass"),
    ),
]

execution_match = by_symbol[by_symbol["check_id"] == "local_execution_parity_pass"]
locked_selected_total = int(execution_match.iloc[-1].get("locked_selected_total", 0) or 0)
submitted_orders = int(execution_match.iloc[-1].get("submitted_orders", 0) or 0)

if (
    src.check_id == "local_execution_parity_pass"
    and not historical_deployable
):
    status = "nogo"
elif (
    src.check_id == "local_execution_parity_pass"
    and locked_selected_total == 0
    and submitted_orders == 0
):
    row[src.check_id] = True
    status = "pass"
    details = "zero locked selections; zero submitted orders expected"
```

- [ ] **Step 3: Emit explicit summary columns for policy consumers**

```python
row["historical_deployable"] = historical_deployable
row["non_deployable_reason"] = non_deployable_reason
row["local_jforex_surrogate_pass"] = historical_deployable and all(bool(row[src.check_id]) for src in sources)
row["local_jforex_surrogate_nogo"] = (not historical_deployable)
row["verdict"] = "nogo" if row["local_jforex_surrogate_nogo"] else ("green" if row["local_jforex_surrogate_pass"] else "red")
```

- [ ] **Step 4: Run the local-surrogate validator tests and confirm they pass**

Run:

```bash
uv run pytest -q tests/test_validate_local_jforex_surrogate.py
```

Expected: PASS.

- [ ] **Step 5: Commit the local-surrogate implementation**

```bash
git add scripts/validate_local_jforex_surrogate.py tests/test_validate_local_jforex_surrogate.py
git commit -m "fix: allow local surrogate nogo and zero-lock windows"
```

### Task 3: Lock Stage 14 Aggregation Policy In Tests

**Files:**
- Modify: `tests/test_validate_stage14_jforex_runtime_certification.py`
- Test: `tests/test_validate_stage14_jforex_runtime_certification.py`

- [ ] **Step 1: Add a test that Stage 14 accepts local-surrogate `NO_GO` for non-deployable symbols**

```python
def test_stage14_accepts_local_surrogate_nogo_for_non_deployable_symbol(tmp_path: Path) -> None:
    _write_csv(
        tmp_path / "USDCAD_stage13.csv",
        [{"symbol": "USDCAD", "stage13_dukascopy_testclient_pass": True}],
    )
    _write_csv(
        tmp_path / "USDCAD_outcome.csv",
        [{
            "symbol": "USDCAD",
            "historical_deployable": False,
            "non_deployable_reason": "no_gate_states",
            "jforex_outcome_parity_pass": False,
        }],
    )
    _write_csv(
        tmp_path / "local_surrogate.csv",
        [{
            "symbol": "USDCAD",
            "historical_deployable": False,
            "non_deployable_reason": "no_gate_states",
            "local_jforex_surrogate_pass": False,
            "local_jforex_surrogate_nogo": True,
            "verdict": "nogo",
        }],
    )
```

- [ ] **Step 2: Add a test that deployable symbols still fail when local surrogate is red**

```python
def test_stage14_keeps_local_surrogate_red_as_failure_for_deployable_symbol(tmp_path: Path) -> None:
    _write_csv(
        tmp_path / "AUDUSD_stage13.csv",
        [{"symbol": "AUDUSD", "stage13_dukascopy_testclient_pass": True}],
    )
    _write_csv(
        tmp_path / "local_surrogate.csv",
        [{
            "symbol": "AUDUSD",
            "historical_deployable": True,
            "local_jforex_surrogate_pass": False,
            "local_jforex_surrogate_nogo": False,
            "verdict": "red",
        }],
    )
```

- [ ] **Step 3: Run the Stage 14 validator tests and confirm the new cases fail**

Run:

```bash
uv run pytest -q tests/test_validate_stage14_jforex_runtime_certification.py
```

Expected: FAIL because Stage 14 currently treats every non-pass local surrogate result as a hard failure and does not understand `nogo`.

- [ ] **Step 4: Commit the failing-test checkpoint**

```bash
git add tests/test_validate_stage14_jforex_runtime_certification.py
git commit -m "test: define stage14 local surrogate nogo policy"
```

### Task 4: Implement Stage 14 NO_GO Aggregation

**Files:**
- Modify: `scripts/validate_stage14_jforex_runtime_certification.py`
- Test: `tests/test_validate_stage14_jforex_runtime_certification.py`
- Test: `tests/test_run_monthly_recert.py`

- [ ] **Step 1: Read local-surrogate and outcome governance metadata into the Stage 14 row**

```python
outcome_match = by_symbol[by_symbol["check_id"] == "jforex_outcome_parity_pass"].copy()
local_match = by_symbol[by_symbol["check_id"] == "local_jforex_surrogate_pass"].copy()
row["historical_deployable"] = bool(
    False if outcome_match.empty else outcome_match.iloc[-1].get("historical_deployable", True)
)
row["non_deployable_reason"] = (
    "" if outcome_match.empty else str(outcome_match.iloc[-1].get("non_deployable_reason") or "")
)
row["local_jforex_surrogate_nogo"] = bool(
    False if local_match.empty else local_match.iloc[-1].get("local_jforex_surrogate_nogo", False)
)
```

- [ ] **Step 2: Allow `NO_GO` only for historically non-deployable symbols**

```python
is_expected_nogo = (
    not row["historical_deployable"]
    and row["non_deployable_reason"] != ""
    and row["local_jforex_surrogate_nogo"]
)

required_check_ids = [
    "stage13_dukascopy_testclient_pass",
    "jforex_signal_parity_pass",
    "jforex_execution_parity_pass",
    "oco_lifecycle_pass",
    "operational_ready_pass",
]
if row["historical_deployable"]:
    required_check_ids.extend(
        ["jforex_outcome_parity_pass", "local_jforex_surrogate_pass"]
    )

row["stage14_jforex_cert_pass"] = all(bool(row[check_id]) for check_id in required_check_ids)
row["stage14_jforex_cert_nogo"] = is_expected_nogo
row["stage14_jforex_cert_ok"] = row["stage14_jforex_cert_pass"] or row["stage14_jforex_cert_nogo"]
row["verdict"] = (
    "nogo"
    if row["stage14_jforex_cert_nogo"]
    else ("green" if row["stage14_jforex_cert_pass"] else "red")
)
```

- [ ] **Step 3: Update the checks/report output so `NO_GO` is visible instead of hidden as `fail`**

```python
status = "nogo" if is_expected_nogo and src.check_id in {"jforex_outcome_parity_pass", "local_jforex_surrogate_pass"} else status
details = row["non_deployable_reason"] if status == "nogo" else details
```

- [ ] **Step 4: Add wrapper coverage for expected `NO_GO` aggregation**

```python
def test_print_summary_allows_expected_nogo_symbols() -> None:
    failures = {
        "USDCAD": [
            {
                "symbol": "USDCAD",
                "check_id": "LOCAL_JFOREX_SURROGATE_PASS",
                "status": "nogo",
                "details": "no_gate_states",
            },
            {
                "symbol": "USDCAD",
                "check_id": "JFOREX_OUTCOME_PARITY_PASS",
                "status": "nogo",
                "details": "no_gate_states",
            },
        ]
    }

    assert run_monthly_recert._print_summary("2026-02", failures) is True
```

- [ ] **Step 5: Teach `run_monthly_recert.py` to treat critical `nogo` rows as acceptable**

```python
if row["severity"] == "critical" and row["status"] not in {"pass", "nogo"}:
    failures.setdefault(row["symbol"], []).append(row)
```

- [ ] **Step 6: Run Stage 14 and wrapper tests and confirm they pass**

Run:

```bash
uv run pytest -q tests/test_validate_stage14_jforex_runtime_certification.py tests/test_run_monthly_recert.py
```

Expected: PASS.

- [ ] **Step 7: Commit the Stage 14 aggregation implementation**

```bash
git add \
  scripts/validate_stage14_jforex_runtime_certification.py \
  scripts/run_monthly_recert.py \
  tests/test_validate_stage14_jforex_runtime_certification.py \
  tests/test_run_monthly_recert.py
git commit -m "fix: allow stage14 and recert nogo for non-deployable symbols"
```

### Task 5: Rebuild Certification Artifacts And Prove Monthly Recert Goes Green

**Files:**
- Modify: `data/analysis/backtest_reconcile/*` (generated)
- Modify: `docs/analysis/local_jforex_surrogate_report.md` (generated)
- Modify: `docs/analysis/stage14_jforex_runtime_certification_report.md` (generated)
- Modify: `docs/strategy_bible/generated/stage_14_snapshot.md` (generated)

- [ ] **Step 1: Run the targeted validator tests together**

Run:

```bash
uv run pytest -q tests/test_validate_local_jforex_surrogate.py tests/test_validate_stage14_jforex_runtime_certification.py
```

Expected: PASS.

- [ ] **Step 2: Re-run the Stage 14 gate against the built 2026-02 bundle**

Run:

```bash
make full-stage14-cert \
  LOCK_DIR=configs/research/governance/oco_candidate_builds/2026-02 \
  EVAL_START=2026-02-07T00:00:00Z \
  EVAL_END=2026-02-09T00:00:00Z
```

Expected:
- `EURUSD`, `GBPUSD`, `USDJPY`, `USDCHF`, `AUDUSD` are `PASS`
- `USDCAD` is `NO_GO` with `reason=no_gate_states`

- [ ] **Step 3: Re-run definitive monthly recert**

Run:

```bash
make monthly-recert MODEL_MONTH=2026-02
```

Expected:
- formal Stage 13 passes
- local surrogate summary shows `USDCAD` as `nogo`
- `data/analysis/backtest_reconcile/monthly_recert_status.json` contains `"overall_pass": true`

- [ ] **Step 4: Commit regenerated certification artifacts**

```bash
git add \
  data/analysis/backtest_reconcile \
  docs/analysis/local_jforex_surrogate_report.md \
  docs/analysis/stage14_jforex_runtime_certification_report.md \
  docs/strategy_bible/generated/stage_14_snapshot.md
git commit -m "chore: regenerate recert artifacts with nogo policy"
```

- [ ] **Step 5: Final verification before handoff**

Run:

```bash
git status --short
uv run pytest -q tests/test_validate_local_jforex_surrogate.py tests/test_validate_stage14_jforex_runtime_certification.py
```

Expected:
- clean worktree
- validator tests pass
