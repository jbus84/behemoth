# PR #95 Bug Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix three bugs introduced in PR #95 — reset startup inheriting stale drain-only state, commit divergence not enforced at promotion, and two broken test stubs.

**Architecture:** Three independent fixes in three files. Fix 1 overrides `allow_new_entries` after reset cleanup in the live startup script. Fix 2 adds a lenient git ancestor check with an injectable `current_commit` parameter in the promotion script. Fix 3 updates test stubs to match the expanded signatures from PR #95.

**Tech Stack:** Python 3.12, pytest, `uv run pytest`, subprocess (git merge-base)

---

### Task 1: Fix reset startup inheriting stale drain-only state

**Files:**
- Modify: `scripts/run_jforex_live.py:698-755`
- Test: `tests/test_run_jforex_live.py`

- [ ] **Step 1: Write the failing test**

Add this test to `tests/test_run_jforex_live.py` after the last test in the file. Import `RestartEligibilityResult` and `RestartEligibility` from `run_jforex_live` at the test call site (they are re-exported or importable from the script):

```python
def test_main_reset_forces_new_entries_true_despite_stale_drain_only_eligibility(
    monkeypatch, tmp_path
) -> None:
    """A reset startup must call _start_live_runner with allow_new_entries=True even
    when the pre-reset eligibility result was DRAIN_ONLY."""
    _write_runtime_files(tmp_path)
    _ensure_governance_dir(tmp_path)
    monkeypatch.setattr(run_jforex_live, "_repo_root", lambda: tmp_path)
    monkeypatch.setattr(run_jforex_live, "_resolve_model_month", lambda cfg: "2026-03")
    monkeypatch.setattr(
        run_jforex_live,
        "_git_metadata",
        lambda repo_root: ("abc123", "main", False),
    )
    monkeypatch.setattr(run_jforex_live, "_has_resume_blocking_git_dirty", lambda repo_root: False)
    monkeypatch.setenv("BEHEMOTH_JFOREX_JNLP_URI", "demo")
    monkeypatch.setenv("BEHEMOTH_JFOREX_USERNAME", "user")
    monkeypatch.setenv("BEHEMOTH_JFOREX_PASSWORD", "pass")

    drain_only_eligibility = run_jforex_live.RestartEligibilityResult(
        eligibility=run_jforex_live.RestartEligibility.RESTART_ELIGIBLE_DRAIN_ONLY,
        allow_new_entries=False,
        reasons=["stale prior state"],
    )
    current_metadata = run_jforex_live.RuntimeSessionMetadata(
        git_commit="abc123",
        git_branch="main",
        git_dirty=False,
        repo_root=str(tmp_path),
        model_month="2026-03",
        governance_dir="configs/research/governance/oco",
        lock_fingerprint="lockfp",
        symbols=["EURUSD"],
        started_at_utc="2026-04-25T00:00:00Z",
        startup_mode="reset",
    )
    comparison = run_jforex_live.RuntimeContextComparison(
        verdict=run_jforex_live.RestartVerdict.CLEAN_RESUMABLE,
        reasons=[],
    )
    monkeypatch.setattr(
        run_jforex_live,
        "_reconcile_startup",
        lambda cfg, paths: (current_metadata, None, comparison, drain_only_eligibility),
    )
    monkeypatch.setattr(run_jforex_live, "write_runtime_session_metadata", lambda *args, **kwargs: None)

    captured_allow_new_entries: list[bool] = []

    def fake_start_live_runner(cfg, *, allow_new_entries: bool = True) -> _FakeProc:
        captured_allow_new_entries.append(allow_new_entries)
        return _FakeProc(returncode=0, pid=99999)

    monkeypatch.setattr(run_jforex_live.subprocess, "run", lambda *a, **kw: type("R", (), {"returncode": 0})())
    monkeypatch.setattr(run_jforex_live, "_start_api", lambda cfg: _FakeProc(returncode=None, pid=20001))
    monkeypatch.setattr(run_jforex_live, "_poll_health", lambda *args, **kwargs: None)
    monkeypatch.setattr(run_jforex_live, "_start_live_runner", fake_start_live_runner)
    monkeypatch.setattr(run_jforex_live, "_warmup_symbols", lambda *args, **kwargs: None)
    monkeypatch.setattr(run_jforex_live, "_stop_process", lambda proc: None)
    monkeypatch.setattr(run_jforex_live.time, "sleep", lambda _: None)
    monkeypatch.setattr(run_jforex_live.signal, "signal", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_jforex_live.py",
            "--symbols", "EURUSD",
            "--report-dir", "data/analysis/backtest_reconcile",
            "--startup-mode", "reset",
        ],
    )

    with pytest.raises(SystemExit, match="1"):
        run_jforex_live.main()

    assert captured_allow_new_entries == [True], (
        f"expected allow_new_entries=True for reset startup, got {captured_allow_new_entries}"
    )
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/test_run_jforex_live.py::test_main_reset_forces_new_entries_true_despite_stale_drain_only_eligibility -v
```

Expected: FAIL — `captured_allow_new_entries == [False]` because the current code passes `restart_eligibility.allow_new_entries` directly.

- [ ] **Step 3: Apply the fix in `scripts/run_jforex_live.py`**

Find the lines around 752-754 that read:
```python
        java_proc = _start_live_runner(
            cfg,
            allow_new_entries=restart_eligibility.allow_new_entries,
        )
```

Replace them with:
```python
        effective_allow_new_entries = (
            True if cfg.startup_mode == "reset"
            else restart_eligibility.allow_new_entries
        )
        java_proc = _start_live_runner(
            cfg,
            allow_new_entries=effective_allow_new_entries,
        )
```

- [ ] **Step 4: Run the new test to verify it passes**

```bash
uv run pytest tests/test_run_jforex_live.py::test_main_reset_forces_new_entries_true_despite_stale_drain_only_eligibility -v
```

Expected: PASS

- [ ] **Step 5: Run full test suite to check for regressions**

```bash
uv run pytest -q tests/test_run_jforex_live.py
```

Expected: all tests pass

- [ ] **Step 6: Commit**

```bash
git add scripts/run_jforex_live.py tests/test_run_jforex_live.py
git commit -m "fix: force allow_new_entries=True after reset startup clears stale state"
```

---

### Task 2: Fix broken test stubs from PR #95 signature changes

**Files:**
- Modify: `tests/test_run_jforex_live.py:356` (3-tuple stub)
- Modify: `tests/test_run_jforex_live.py:584-605` (second 3-tuple stub)
- Modify: `tests/test_run_jforex_live.py:98-100` (fake `_start_live_runner` missing kwarg)
- Modify: `tests/test_run_jforex_live.py:158` (inline lambda missing kwarg)
- Modify: `tests/test_run_jforex_live.py:424` (inline lambda missing kwarg)

These are test-only changes. No new tests are needed — fixing the stubs makes the two already-failing tests pass.

- [ ] **Step 1: Verify the two currently-failing tests**

```bash
uv run pytest -q tests/test_run_jforex_live.py
```

Expected: 2 failures — one about `_reconcile_startup` returning too few values, one about unexpected keyword `allow_new_entries`.

- [ ] **Step 2: Fix the 3-tuple stub at line ~356**

This stub is in `test_main_fails_before_seed_when_runtime_threshold_json_drifts_from_promoted_lock` (around line 353-356). The lambda returns `(current_metadata, None, comparison)`. It needs to return a 4-tuple with a `RestartEligibilityResult` in position 2 (index 1).

Find this lambda:
```python
    monkeypatch.setattr(
        run_jforex_live,
        "_reconcile_startup",
        lambda cfg, paths: (current_metadata, None, comparison),
    )
```

Replace with:
```python
    monkeypatch.setattr(
        run_jforex_live,
        "_reconcile_startup",
        lambda cfg, paths: (
            current_metadata,
            None,
            comparison,
            run_jforex_live.RestartEligibilityResult(
                eligibility=run_jforex_live.RestartEligibility.RESTART_ELIGIBLE,
                allow_new_entries=True,
                reasons=[],
            ),
        ),
    )
```

- [ ] **Step 3: Fix the 3-tuple stub at line ~584 (incompatible resume test)**

In `test_main_resume_incompatible_prints_operator_summary`, find the lambda that returns a 3-tuple with `RestartVerdict.INCOMPATIBLE`:
```python
    monkeypatch.setattr(
        run_jforex_live,
        "_reconcile_startup",
        lambda cfg, paths: (
            run_jforex_live.RuntimeSessionMetadata(
                ...
            ),
            None,
            run_jforex_live.RuntimeContextComparison(
                verdict=run_jforex_live.RestartVerdict.INCOMPATIBLE,
                reasons=[
                    "broker-linked symbols do not match broker snapshot symbols",
                    "broker-linked position ids do not match broker snapshot order ids",
                ],
            ),
        ),
    )
```

Replace with the same tuple, adding a 4th element. For `INCOMPATIBLE` the eligibility should be `RESTART_BLOCKED`:
```python
    monkeypatch.setattr(
        run_jforex_live,
        "_reconcile_startup",
        lambda cfg, paths: (
            run_jforex_live.RuntimeSessionMetadata(
                git_commit="abc123",
                git_branch="main",
                git_dirty=False,
                repo_root=str(tmp_path),
                model_month="2026-03",
                governance_dir="configs/research/governance/oco",
                lock_fingerprint="fp",
                symbols=["EURUSD"],
                started_at_utc="2026-04-22T00:00:00Z",
                startup_mode="resume",
            ),
            None,
            run_jforex_live.RuntimeContextComparison(
                verdict=run_jforex_live.RestartVerdict.INCOMPATIBLE,
                reasons=[
                    "broker-linked symbols do not match broker snapshot symbols",
                    "broker-linked position ids do not match broker snapshot order ids",
                ],
            ),
            run_jforex_live.RestartEligibilityResult(
                eligibility=run_jforex_live.RestartEligibility.RESTART_BLOCKED,
                allow_new_entries=False,
                reasons=[
                    "broker-linked symbols do not match broker snapshot symbols",
                    "broker-linked position ids do not match broker snapshot order ids",
                ],
            ),
        ),
    )
```

- [ ] **Step 4: Fix fake `_start_live_runner` stubs that don't accept `allow_new_entries`**

The production `_start_live_runner` signature is now `(cfg, *, allow_new_entries: bool = True)`. Any lambda or function stub of this function that doesn't accept `allow_new_entries` will raise `TypeError` when called.

Find each occurrence and add `**kwargs` or the explicit keyword. There are three:

**Occurrence at line ~98** (in the process monitor test):
```python
    def fake_start_live_runner(cfg: run_jforex_live.RunConfig) -> _FakeProc:
        order.append("start_live_runner")
        return java_proc
```
Replace with:
```python
    def fake_start_live_runner(cfg: run_jforex_live.RunConfig, *, allow_new_entries: bool = True) -> _FakeProc:
        order.append("start_live_runner")
        return java_proc
```

**Occurrence at line ~158** (inline lambda):
```python
    monkeypatch.setattr(
        run_jforex_live, "_start_live_runner", lambda cfg: _FakeProc(returncode=0, pid=20002)
    )
```
Replace with:
```python
    monkeypatch.setattr(
        run_jforex_live, "_start_live_runner", lambda cfg, **kw: _FakeProc(returncode=0, pid=20002)
    )
```

**Occurrence at line ~424** (inline lambda in reset archive test):
```python
    monkeypatch.setattr(
        run_jforex_live, "_start_live_runner", lambda cfg: _FakeProc(returncode=0, pid=20002)
    )
```
Replace with:
```python
    monkeypatch.setattr(
        run_jforex_live, "_start_live_runner", lambda cfg, **kw: _FakeProc(returncode=0, pid=20002)
    )
```

- [ ] **Step 5: Run the full test file to verify all tests pass**

```bash
uv run pytest -q tests/test_run_jforex_live.py
```

Expected: all tests pass, 0 failures

- [ ] **Step 6: Commit**

```bash
git add tests/test_run_jforex_live.py
git commit -m "fix: update test stubs for _reconcile_startup 4-tuple and allow_new_entries kwarg"
```

---

### Task 3: Enforce commit ancestry at promotion

**Files:**
- Modify: `scripts/run_promote_live.py:43-75` (`_verify_dag_provenance`)
- Modify: `scripts/run_promote_live.py:78` (`_verify_cert` signature)
- Test: `tests/test_run_promote_live.py`

- [ ] **Step 1: Write the failing tests**

Add these three tests to `tests/test_run_promote_live.py`. Locate the section that tests `_verify_dag_provenance` or `_verify_cert` and add after the existing provenance tests.

```python
def test_verify_dag_provenance_passes_when_certified_commit_is_current(
    tmp_path, monkeypatch
) -> None:
    """Promotion passes when current HEAD is exactly the certified commit."""
    status = _make_valid_provenance_status("2026-03")
    status["target_commit"] = "abc1234567890000000000000000000000000001"

    fake_merge_base_result = type("R", (), {
        "stdout": "abc1234567890000000000000000000000000001\n",
        "returncode": 0,
    })()
    monkeypatch.setattr(
        run_promote_live.subprocess, "run",
        lambda *args, **kwargs: fake_merge_base_result
    )

    # Should not raise
    run_promote_live._verify_dag_provenance(
        status,
        "2026-03",
        repo_root=tmp_path,
        current_commit="abc1234567890000000000000000000000000001",
    )


def test_verify_dag_provenance_passes_when_current_commit_is_descendant(
    tmp_path, monkeypatch
) -> None:
    """Promotion passes when current HEAD is a descendant of the certified commit."""
    certified = "abc1234567890000000000000000000000000001"
    current = "def9999999999999999999999999999999999002"
    status = _make_valid_provenance_status("2026-03")
    status["target_commit"] = certified

    # merge-base returns the certified commit, proving it's an ancestor
    fake_merge_base_result = type("R", (), {
        "stdout": certified + "\n",
        "returncode": 0,
    })()
    monkeypatch.setattr(
        run_promote_live.subprocess, "run",
        lambda *args, **kwargs: fake_merge_base_result
    )

    # Should not raise
    run_promote_live._verify_dag_provenance(
        status,
        "2026-03",
        repo_root=tmp_path,
        current_commit=current,
    )


def test_verify_dag_provenance_blocks_when_certified_commit_is_not_ancestor(
    tmp_path, monkeypatch
) -> None:
    """Promotion is blocked when the certified commit is not an ancestor of HEAD."""
    certified = "abc1234567890000000000000000000000000001"
    current = "def9999999999999999999999999999999999002"
    status = _make_valid_provenance_status("2026-03")
    status["target_commit"] = certified

    # merge-base returns something other than certified, proving divergence
    fake_merge_base_result = type("R", (), {
        "stdout": "0000000000000000000000000000000000000000\n",
        "returncode": 0,
    })()
    monkeypatch.setattr(
        run_promote_live.subprocess, "run",
        lambda *args, **kwargs: fake_merge_base_result
    )

    with pytest.raises(SystemExit) as exc:
        run_promote_live._verify_dag_provenance(
            status,
            "2026-03",
            repo_root=tmp_path,
            current_commit=current,
        )
    assert "abc12345" in str(exc.value)
    assert "def99999" in str(exc.value)
```

You also need a helper `_make_valid_provenance_status` if it doesn't already exist in the test file. Check whether the existing tests already define a similar helper. If they do, use it. If not, add:

```python
def _make_valid_provenance_status(model_month: str) -> dict:
    return {
        "dag_node_id": "monthly_recert",
        "model_month": model_month,
        "process_verdict": "PASS",
        "target_branch": "main",
        "target_commit": "abc1234567890000000000000000000000000001",
        "git_dirty": False,
        "symbol_decisions": {"EURUSD": "GO"},
        "lock_fingerprint": "fp-abc",
    }
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
uv run pytest tests/test_run_promote_live.py::test_verify_dag_provenance_passes_when_certified_commit_is_current tests/test_run_promote_live.py::test_verify_dag_provenance_passes_when_current_commit_is_descendant tests/test_run_promote_live.py::test_verify_dag_provenance_blocks_when_certified_commit_is_not_ancestor -v
```

Expected: FAIL — `_verify_dag_provenance` does not yet accept `current_commit` parameter and has no ancestor check.

- [ ] **Step 3: Update `_verify_dag_provenance` signature and add ancestor check**

In `scripts/run_promote_live.py`, change:

```python
def _verify_dag_provenance(status: dict[str, object], model_month: str) -> None:
```

to:

```python
def _verify_dag_provenance(
    status: dict[str, object],
    model_month: str,
    repo_root: Path | None = None,
    *,
    current_commit: str | None = None,
) -> None:
```

Then, at the end of the function body — after the `symbol_decisions` check and before the function ends — add:

```python
    certified = str(status["target_commit"]).strip()
    if current_commit is not None:
        repo_root_for_git = repo_root or _repo_root()
        result = subprocess.run(
            ["git", "-C", str(repo_root_for_git), "merge-base", certified, current_commit],
            capture_output=True,
            text=True,
        )
        merge_base = result.stdout.strip()
        if merge_base != certified:
            raise SystemExit(
                f"[promote-live] certified commit {certified[:8]} is not an ancestor of "
                f"current HEAD {current_commit[:8]}; re-run make monthly-recert"
            )
```

- [ ] **Step 4: Update `_verify_cert` to accept and propagate `current_commit`**

In `scripts/run_promote_live.py`, change:

```python
def _verify_cert(report_dir: str, model_month: str, repo_root: Path | None = None) -> None:
```

to:

```python
def _verify_cert(
    report_dir: str,
    model_month: str,
    repo_root: Path | None = None,
    *,
    current_commit: str | None = None,
) -> None:
```

And update the call to `_verify_dag_provenance` inside `_verify_cert` (currently at line ~105):

```python
    _verify_dag_provenance(status, model_month)
```

Replace with:

```python
    _verify_dag_provenance(status, model_month, repo_root, current_commit=current_commit)
```

- [ ] **Step 5: Run the three new tests to verify they pass**

```bash
uv run pytest tests/test_run_promote_live.py::test_verify_dag_provenance_passes_when_certified_commit_is_current tests/test_run_promote_live.py::test_verify_dag_provenance_passes_when_current_commit_is_descendant tests/test_run_promote_live.py::test_verify_dag_provenance_blocks_when_certified_commit_is_not_ancestor -v
```

Expected: all three PASS

- [ ] **Step 6: Run the full promote-live test file to check for regressions**

```bash
uv run pytest -q tests/test_run_promote_live.py
```

Expected: all tests pass

- [ ] **Step 7: Commit**

```bash
git add scripts/run_promote_live.py tests/test_run_promote_live.py
git commit -m "fix: enforce certified commit ancestry in promotion provenance check"
```

---

### Task 4: Final integration check

- [ ] **Step 1: Run the full Python test suite**

```bash
uv run pytest -q
```

Expected: all tests pass, 0 failures

- [ ] **Step 2: Verify the Java build still passes**

```bash
cd src/jforex && ./gradlew test --rerun && cd ../..
```

Expected: BUILD SUCCESSFUL

- [ ] **Step 3: Commit is not needed here** — all changes were committed in prior tasks.
