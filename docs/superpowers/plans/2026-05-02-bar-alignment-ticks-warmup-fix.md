# Bar Alignment Ticks — warmup load fix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Hard-rename `phase_bar_ticks` to `bar_align_ticks` across the matrix runners (Python) and live warmup loader (Java), and change the warmup-load formula so `keep mod align == full_pre_count mod align`. This makes the runtime's open-bar accumulator at start_ts match what governance had at the same moment, fixing Stage 14 outcome parity.

**Architecture:** Three layers all need the rename plus formula fix. Python matrix runners derive `bar_align_ticks` from the active candidate set via the existing `scripts/_matrix_warmup.py` helper. The live runtime gets a new required `liveBarAlignTicks` field on `JForexSessionConfig`. The local-surrogate Java side carries the renamed field through env-var → `LocalJForexHarnessConfig.barAlignTicks` → `BackfillRequestPayload.bar_ticks` (a label, not alignment math). `LiveReadinessCoordinator.PHASE_BAR_TICKS` is unrelated (readiness reporting) and left alone.

**Tech Stack:** Python 3.12 + pytest + uv, Java 17 + Gradle + JUnit, GNU Make, DuckDB Python and JDBC for parquet reads.

**Spec:** [`docs/superpowers/specs/2026-05-02-bar-alignment-ticks-warmup-fix-design.md`](../specs/2026-05-02-bar-alignment-ticks-warmup-fix-design.md)

---

## File Structure

| Path | Status | Responsibility |
|---|---|---|
| `UBIQUITOUS_LANGUAGE.md` | Modify | Add **Bar Alignment Ticks** term; update **Warmup** aliases |
| `scripts/_matrix_warmup.py` | Modify | No API change; add a new public helper `compute_bar_align_ticks` that returns the auto-derived align value (and reuses `max_bar_ticks_for_symbols`) |
| `tests/test_matrix_warmup.py` | Modify | Add tests for `compute_bar_align_ticks` and the new alignment-formula property |
| `scripts/run_jforex_dukascopy_matrix.py` | Modify | Rename `phase_bar_ticks` → `bar_align_ticks`; `--bar-align-ticks` flag with auto-derive; new alignment formula in (renamed) `_load_aligned_warmup_ticks` |
| `scripts/run_local_jforex_surrogate_matrix.py` | Modify | Same as the Dukascopy matrix; also rename `BEHEMOTH_LOCAL_JFOREX_PHASE_BAR_TICKS` → `BEHEMOTH_LOCAL_JFOREX_BAR_ALIGN_TICKS` env var passed to subprocess |
| `tests/test_run_jforex_dukascopy_matrix.py` | Modify | Replace `phase_bar_ticks=...` fixtures with `bar_align_ticks=...` |
| `tests/test_run_local_jforex_surrogate_matrix.py` | Modify | Same |
| `Makefile` | Modify | Rename `PHASE_BAR_TICKS` make var to `BAR_ALIGN_TICKS`; change four invocation sites; default to `0` (auto) |
| `src/jforex/src/main/java/com/behemoth/jforex/config/JForexSessionConfig.java` | Modify | Add required `int liveBarAlignTicks` field with `> 0` validation; thread through env-driven `fromEnvironment` (new env var `BEHEMOTH_JFOREX_LIVE_BAR_ALIGN_TICKS`) |
| `src/jforex/src/main/java/com/behemoth/jforex/live/HistoricalWarmupLoader.java` | Modify | Remove `PHASE_BAR_TICKS` constant; use `config.liveBarAlignTicks()`; change `keep` formula to `(warmup_ticks / align) * align + (preCount % align)` |
| `src/jforex/src/main/java/com/behemoth/jforex/local/LocalJForexHarnessConfig.java` | Modify | Rename field `phaseBarTicks` → `barAlignTicks`; rename env-var read to `BEHEMOTH_LOCAL_JFOREX_BAR_ALIGN_TICKS` |
| `src/jforex/src/main/java/com/behemoth/jforex/LocalJForexTesterRunner.java` | Modify | Update `harnessConfig.phaseBarTicks()` call site to `harnessConfig.barAlignTicks()` |
| `src/jforex/src/test/java/com/behemoth/jforex/live/HistoricalWarmupLoaderTest.java` | Modify | Update `config()` helper to supply `liveBarAlignTicks`; rename `loaderKeepsWarmupTicksPlusPhaseRemainder` → `loaderAlignsKeepToBarBoundary`; assert new formula property |
| `src/jforex/src/test/java/com/behemoth/jforex/live/LiveReadinessCoordinatorTest.java` | Modify | Update single `JForexSessionConfig` construction site to pass `liveBarAlignTicks` |
| `src/jforex/src/test/java/com/behemoth/jforex/BehemothStrategyCoreTest.java` | Modify | Update 10 `JForexSessionConfig` construction sites |
| `docs/strategy_bible/operator_runbook.md` | Modify | Add a one-paragraph note on `BEHEMOTH_JFOREX_LIVE_BAR_ALIGN_TICKS` requirement and the matrix `--bar-align-ticks` default |

## Branching

Per repo policy: develop in a worktree, merge via PR, never commit to main.

- **Branch:** `fix/bar-align-ticks-warmup-formula`
- **Worktree path:** `../behemoth-bar-align-fix`

---

## Task 1: Create worktree on a clean feature branch

**Files:** none (git operations only).

- [ ] **Step 1: Verify main is clean**

```bash
cd /Users/danielfisher/repositories/behemoth
git status -s
```

Expected: empty (no `M` or `??` lines). If anything is uncommitted, stash with `git stash push -u -m "wip"` before continuing; pop it back after Task 13 if it's needed.

- [ ] **Step 2: Create the worktree**

```bash
git worktree add ../behemoth-bar-align-fix -b fix/bar-align-ticks-warmup-formula
```

Expected: `Preparing worktree (new branch 'fix/bar-align-ticks-warmup-formula') ... HEAD is now at <sha> docs: bar alignment ticks warmup fix design`.

- [ ] **Step 3: Confirm branch state in the worktree**

```bash
cd ../behemoth-bar-align-fix
git status -s
git branch --show-current
```

Expected: clean tree, branch is `fix/bar-align-ticks-warmup-formula`.

All subsequent task commands run from `../behemoth-bar-align-fix` unless stated otherwise.

---

## Task 2: UBIQUITOUS_LANGUAGE.md — add term and update Warmup aliases

**Files:**
- Modify: `UBIQUITOUS_LANGUAGE.md`

- [ ] **Step 1: Add the Bar Alignment Ticks row to the Live Runtime Contract table**

Locate the row beginning `| **Warmup** |` in the "Live runtime contract" table (around line 88). After that row, insert:

```markdown
| **Bar Alignment Ticks** | The tick-count modulus used when sizing **Warmup** loads so the runtime's open-bar accumulator at start matches what governance had at the same moment. Equals the largest candidate `bar_ticks` in the active universe. | Phase bar ticks, alignment window |
```

- [ ] **Step 2: Update the Warmup row's aliases**

Change the existing row from:

```
| **Warmup** | The historical feature replay used to seed live inference state before current predictions begin. | Backfill, preload |
```

to:

```
| **Warmup** | The historical feature replay used to seed live inference state before current predictions begin. | Backfill, preload, phase warmup |
```

- [ ] **Step 3: Commit**

```bash
git add UBIQUITOUS_LANGUAGE.md
git commit -m "$(cat <<'EOF'
docs: add Bar Alignment Ticks to ubiquitous language

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: Python helper — add `compute_bar_align_ticks` (TDD)

**Files:**
- Modify: `scripts/_matrix_warmup.py`
- Modify: `tests/test_matrix_warmup.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_matrix_warmup.py` (alongside the existing `TestComputeRequiredWarmupTicks` block):

```python
class TestComputeBarAlignTicks:
    def test_returns_max_bar_ticks_when_candidates_present(self, tmp_path: Path) -> None:
        from scripts._matrix_warmup import compute_bar_align_ticks
        _write_locked(
            tmp_path / "2026-04" / "eurusd_oco_locked_predictions.parquet",
            ["oco|EURUSD|1000|h6|s1"],
        )
        assert (
            compute_bar_align_ticks(
                symbols=["EURUSD"],
                locked_predictions_dir=tmp_path,
                model_month="2026-04",
            )
            == 1000
        )

    def test_returns_zero_when_no_candidates(self, tmp_path: Path) -> None:
        from scripts._matrix_warmup import compute_bar_align_ticks

        # Sentinel return; the runner is expected to fail fast on this.
        assert (
            compute_bar_align_ticks(
                symbols=["EURUSD"],
                locked_predictions_dir=tmp_path,
                model_month="2026-04",
            )
            == 0
        )

    def test_flat_layout_when_model_month_empty(self, tmp_path: Path) -> None:
        from scripts._matrix_warmup import compute_bar_align_ticks
        _write_locked(
            tmp_path / "audusd_oco_locked_predictions.parquet",
            ["oco|AUDUSD|1500|h6|s1"],
        )
        assert (
            compute_bar_align_ticks(
                symbols=["AUDUSD"],
                locked_predictions_dir=tmp_path,
                model_month="",
            )
            == 1500
        )
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/test_matrix_warmup.py::TestComputeBarAlignTicks -q
```

Expected: ImportError/AttributeError on `compute_bar_align_ticks` — the symbol doesn't exist yet.

- [ ] **Step 3: Implement `compute_bar_align_ticks`**

Add to `scripts/_matrix_warmup.py` immediately after `compute_required_warmup_ticks`:

```python
def compute_bar_align_ticks(
    *,
    symbols: Iterable[str],
    locked_predictions_dir: Path,
    model_month: str = "",
) -> int:
    """Auto-derive the alignment modulus for warmup tick loading.

    Returns the largest candidate ``bar_ticks`` across the locked set.
    Returns 0 when no locked predictions are discoverable; the matrix
    runner is expected to fail fast in that case rather than fall back
    to a default that re-introduces the alignment bug.
    """
    return max_bar_ticks_for_symbols(
        symbols=symbols,
        locked_predictions_dir=locked_predictions_dir,
        model_month=model_month,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/test_matrix_warmup.py -q
```

Expected: all tests pass (existing 15 + 3 new).

- [ ] **Step 5: Commit**

```bash
git add scripts/_matrix_warmup.py tests/test_matrix_warmup.py
git commit -m "$(cat <<'EOF'
feat: add compute_bar_align_ticks helper for matrix warmup alignment

Auto-derives the alignment modulus from the largest candidate
bar_ticks. Returns 0 when no locked predictions are found so the
caller can fail fast rather than silently fall back.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: Python helper — alignment-formula property test (TDD)

**Files:**
- Modify: `tests/test_matrix_warmup.py`

The formula isn't a function in `_matrix_warmup` (it lives inline in the matrix runners), but we can test the property as a small inlined helper. Optionally lift the formula into the helper for reusability — see Step 3.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_matrix_warmup.py`:

```python
class TestAlignKeepFormula:
    def test_property_keep_mod_align_equals_pre_count_mod_align(self) -> None:
        from scripts._matrix_warmup import align_keep
        # The formula's invariant: keep % align == full_pre_count % align,
        # so the runtime open-bar accumulator at end-of-warmup matches what
        # governance had at the same tick position.
        for warmup_ticks, align, pre_count in [
            (346800, 1000, 0),
            (346800, 1000, 47),
            (346800, 1000, 832),
            (346800, 1000, 999),
            (346800, 1000, 2547832),
            (30000, 100, 12345),
            (10, 5, 3),
        ]:
            keep = align_keep(warmup_ticks, align, pre_count)
            assert keep % align == pre_count % align, (
                f"warmup_ticks={warmup_ticks} align={align} pre_count={pre_count} "
                f"keep={keep}"
            )

    def test_keep_concrete_value_for_2026_04_eurusd(self) -> None:
        from scripts._matrix_warmup import align_keep
        # warmup_ticks=346800 (auto-computed for 2026-04 1000-tick candidates)
        # align=1000 (max candidate bar_ticks)
        # pre_count=2547832 (illustrative)
        assert align_keep(346800, 1000, 2547832) == 346000 + 832
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/test_matrix_warmup.py::TestAlignKeepFormula -q
```

Expected: ImportError on `align_keep`.

- [ ] **Step 3: Implement `align_keep`**

Add to `scripts/_matrix_warmup.py`:

```python
def align_keep(warmup_ticks: int, align: int, full_pre_count: int) -> int:
    """Size the warmup-tick keep window so its modulo matches governance.

    Property: ``align_keep(w, a, p) % a == p % a`` for any non-negative
    ``w``, positive ``a``, non-negative ``p``. This makes the runtime's
    open-bar accumulator at end-of-warmup equal to what governance had
    at the same absolute tick position.
    """
    if align <= 0:
        raise ValueError(f"align must be > 0, got {align}")
    if warmup_ticks < 0 or full_pre_count < 0:
        raise ValueError("warmup_ticks and full_pre_count must be >= 0")
    return (warmup_ticks // align) * align + (full_pre_count % align)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/test_matrix_warmup.py -q
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add scripts/_matrix_warmup.py tests/test_matrix_warmup.py
git commit -m "$(cat <<'EOF'
feat: add align_keep helper enforcing keep-mod-align == pre-mod-align

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: Rename in `run_jforex_dukascopy_matrix.py`

**Files:**
- Modify: `scripts/run_jforex_dukascopy_matrix.py`

- [ ] **Step 1: Update import line to add the new helpers**

Change:

```python
from scripts._matrix_warmup import (
    WARMUP_TICKS_AUTO,
    compute_required_warmup_ticks,
)
```

to:

```python
from scripts._matrix_warmup import (
    WARMUP_TICKS_AUTO,
    align_keep,
    compute_bar_align_ticks,
    compute_required_warmup_ticks,
)
```

- [ ] **Step 2: Rename the RunConfig field**

In the `RunConfig` dataclass, change `phase_bar_ticks: int` to `bar_align_ticks: int`.

- [ ] **Step 3: Replace the `--phase-bar-ticks` argparse with `--bar-align-ticks`**

Replace:

```python
    parser.add_argument("--phase-bar-ticks", type=int, default=100)
```

with:

```python
    parser.add_argument(
        "--bar-align-ticks",
        type=int,
        default=0,
        help=(
            "Tick-count modulus for warmup load alignment. Default 0 = "
            "auto-derive from max(candidate bar_ticks) in --model-month "
            "locked predictions."
        ),
    )
```

- [ ] **Step 4: Add auto-derive + abort-on-zero in `_parse_args`**

After the existing `warmup_ticks` auto-derive block (just before `return RunConfig(...)`), insert:

```python
    bar_align_ticks = int(args.bar_align_ticks)
    if bar_align_ticks <= 0:
        bar_align_ticks = compute_bar_align_ticks(
            symbols=symbols,
            locked_predictions_dir=Path(args.history_dir),
            model_month=str(args.model_month),
        )
        if bar_align_ticks <= 0:
            raise SystemExit(
                f"bar_align_ticks could not be auto-derived from "
                f"{args.history_dir}/{args.model_month} locked predictions; "
                f"pass --bar-align-ticks explicitly."
            )
        print(
            f"[matrix] auto-computed --bar-align-ticks={bar_align_ticks} "
            f"(model_month={args.model_month})",
            flush=True,
        )
```

- [ ] **Step 5: Pass the new value into RunConfig**

In the `return RunConfig(...)` block, replace `phase_bar_ticks=int(args.phase_bar_ticks)` with `bar_align_ticks=bar_align_ticks`.

- [ ] **Step 6: Rename and rewire the warmup loader function**

Rename `_load_phase_aligned_warmup_ticks` to `_load_aligned_warmup_ticks`. Replace its body around the `keep =` line.

Old:

```python
    if not files or cfg.phase_bar_ticks <= 0:
        return []
    ...
    keep = int(cfg.warmup_ticks) + (full_pre_count % int(cfg.phase_bar_ticks))
```

New:

```python
    if not files or cfg.bar_align_ticks <= 0:
        return []
    ...
    keep = align_keep(int(cfg.warmup_ticks), int(cfg.bar_align_ticks), full_pre_count)
```

- [ ] **Step 7: Update the single caller of the renamed function**

Find the `_load_phase_aligned_warmup_ticks(cfg, symbol)` call site (in `_prime_api_with_warmup`) and rename to `_load_aligned_warmup_ticks(cfg, symbol)`.

- [ ] **Step 8: Update the `bar_ticks` field passed to `/backfill`**

In `_prime_api_with_warmup`, the JSON payload uses `"bar_ticks": int(cfg.phase_bar_ticks)`. Change to `"bar_ticks": int(cfg.bar_align_ticks)`.

- [ ] **Step 9: Run the existing matrix unit tests to find downstream fallout**

```bash
uv run pytest tests/test_run_jforex_dukascopy_matrix.py -q
```

Expected: failures referencing `phase_bar_ticks` (caught in Task 7).

- [ ] **Step 10: Commit**

```bash
git add scripts/run_jforex_dukascopy_matrix.py
git commit -m "$(cat <<'EOF'
fix: rename phase_bar_ticks to bar_align_ticks in dukascopy matrix runner

Hard rename; auto-derives the alignment modulus from the locked
candidate set's max bar_ticks. Aborts if no candidates are
discoverable rather than silently re-introducing the bug class.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 6: Rename in `run_local_jforex_surrogate_matrix.py`

**Files:**
- Modify: `scripts/run_local_jforex_surrogate_matrix.py`

- [ ] **Step 1: Update import line**

Same import change as Task 5 Step 1.

- [ ] **Step 2: Rename RunConfig field**

Change `phase_bar_ticks: int` → `bar_align_ticks: int` in the `RunConfig` dataclass.

- [ ] **Step 3: Replace `--phase-bar-ticks` argparse**

Replace:

```python
    parser.add_argument("--phase-bar-ticks", type=int, default=100)
```

with the same block as Task 5 Step 3.

- [ ] **Step 4: Add auto-derive in `_parse_args`**

After the existing `warmup_ticks` auto-derive, insert (note this runner has both `--locked-predictions-dir` flat layout and `--history-dir` nested layout; mirror the existing `warmup_ticks` resolution):

```python
    bar_align_ticks = int(args.bar_align_ticks)
    if bar_align_ticks <= 0:
        flat_dir = str(args.locked_predictions_dir).strip()
        if flat_dir:
            bar_align_ticks = compute_bar_align_ticks(
                symbols=symbols,
                locked_predictions_dir=Path(flat_dir),
                model_month="",
            )
        else:
            bar_align_ticks = compute_bar_align_ticks(
                symbols=symbols,
                locked_predictions_dir=Path(args.history_dir),
                model_month=str(args.model_month),
            )
        if bar_align_ticks <= 0:
            raise SystemExit(
                f"bar_align_ticks could not be auto-derived from locked "
                f"predictions; pass --bar-align-ticks explicitly."
            )
        print(
            f"[surrogate] auto-computed --bar-align-ticks={bar_align_ticks} "
            f"(model_month={args.model_month})",
            flush=True,
        )
```

- [ ] **Step 5: Pass into RunConfig**

In `return RunConfig(...)`, replace `phase_bar_ticks=args.phase_bar_ticks` with `bar_align_ticks=bar_align_ticks`.

- [ ] **Step 6: Rename and rewire the warmup loader function**

Same change as Task 5 Step 6, including the `_load_phase_aligned_warmup_ticks` → `_load_aligned_warmup_ticks` rename and the `keep =` line replacement.

- [ ] **Step 7: Update env var name passed to subprocess**

Find the line:

```python
            "BEHEMOTH_LOCAL_JFOREX_PHASE_BAR_TICKS": str(cfg.phase_bar_ticks),
```

Replace with:

```python
            "BEHEMOTH_LOCAL_JFOREX_BAR_ALIGN_TICKS": str(cfg.bar_align_ticks),
```

- [ ] **Step 8: Update any other `phase_bar_ticks` references in the file**

```bash
grep -n "phase_bar_ticks" scripts/run_local_jforex_surrogate_matrix.py
```

Expected: zero hits after the previous steps. Update any straggler.

- [ ] **Step 9: Commit**

```bash
git add scripts/run_local_jforex_surrogate_matrix.py
git commit -m "$(cat <<'EOF'
fix: rename phase_bar_ticks to bar_align_ticks in surrogate matrix runner

Hard rename matches the dukascopy matrix runner; renamed env var
BEHEMOTH_LOCAL_JFOREX_BAR_ALIGN_TICKS is consumed by the Java
LocalJForexHarnessConfig in a later task.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 7: Update Python tests for the rename

**Files:**
- Modify: `tests/test_run_jforex_dukascopy_matrix.py`
- Modify: `tests/test_run_local_jforex_surrogate_matrix.py`

- [ ] **Step 1: Replace `phase_bar_ticks=100` with `bar_align_ticks=1000` in dukascopy matrix tests**

Locate every fixture that uses `phase_bar_ticks=100` (lines 113, 308 per the inventory) and update the keyword arg name and value. The unit-style block at line 372 keeps its small numeric:

```python
"phase_bar_ticks": 4,
```

becomes:

```python
"bar_align_ticks": 4,
```

```bash
sed -i '' 's/phase_bar_ticks=100/bar_align_ticks=1000/g' tests/test_run_jforex_dukascopy_matrix.py
sed -i '' 's/"phase_bar_ticks": 4/"bar_align_ticks": 4/g' tests/test_run_jforex_dukascopy_matrix.py
```

Verify no `phase_bar_ticks` remains:

```bash
grep -n phase_bar_ticks tests/test_run_jforex_dukascopy_matrix.py
```

Expected: empty.

- [ ] **Step 2: Same for the surrogate matrix tests**

```bash
sed -i '' 's/phase_bar_ticks=100/bar_align_ticks=1000/g' tests/test_run_local_jforex_surrogate_matrix.py
grep -n phase_bar_ticks tests/test_run_local_jforex_surrogate_matrix.py
```

Expected: empty.

- [ ] **Step 3: Run the full Python test suite for the matrix runners**

```bash
uv run pytest tests/test_run_jforex_dukascopy_matrix.py tests/test_run_local_jforex_surrogate_matrix.py tests/test_matrix_warmup.py -q
```

Expected: all pass.

- [ ] **Step 4: Commit**

```bash
git add tests/test_run_jforex_dukascopy_matrix.py tests/test_run_local_jforex_surrogate_matrix.py
git commit -m "$(cat <<'EOF'
test: rename phase_bar_ticks to bar_align_ticks in matrix runner tests

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 8: Makefile — rename make var and CLI flag

**Files:**
- Modify: `Makefile`

- [ ] **Step 1: Rename the env var line at line 311**

```bash
sed -i '' 's/BEHEMOTH_LOCAL_JFOREX_PHASE_BAR_TICKS=$(or $(PHASE_BAR_TICKS),100)/BEHEMOTH_LOCAL_JFOREX_BAR_ALIGN_TICKS=$(or $(BAR_ALIGN_TICKS),0)/g' Makefile
```

- [ ] **Step 2: Rename the three `--phase-bar-ticks` CLI flag invocations**

```bash
sed -i '' 's/--phase-bar-ticks $(or $(PHASE_BAR_TICKS),100)/--bar-align-ticks $(or $(BAR_ALIGN_TICKS),0)/g' Makefile
```

- [ ] **Step 3: Verify no stale references**

```bash
grep -n "PHASE_BAR_TICKS\|phase-bar-ticks" Makefile
```

Expected: empty.

- [ ] **Step 4: Commit**

```bash
git add Makefile
git commit -m "$(cat <<'EOF'
chore: rename PHASE_BAR_TICKS to BAR_ALIGN_TICKS in Makefile

Default for both env var and CLI flag is now 0 (auto-derive from
locked predictions) instead of 100 (which produced the alignment
bug).

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 9: `JForexSessionConfig` — add required `liveBarAlignTicks` field

**Files:**
- Modify: `src/jforex/src/main/java/com/behemoth/jforex/config/JForexSessionConfig.java`

- [ ] **Step 1: Add `liveBarAlignTicks` to the record header**

In the record's parameter list, insert `int liveBarAlignTicks` immediately after `int liveStartupBridgeTimeoutMinutes`:

```java
public record JForexSessionConfig(
        ...
        int liveStartupBridgeTimeoutMinutes,
        int liveBarAlignTicks
) {
```

- [ ] **Step 2: Add the validation in the compact constructor**

Locate the existing `if (liveWarmupTicks < 0 ...)` validation block and append a new check:

```java
        if (liveBarAlignTicks <= 0) {
            throw new IllegalArgumentException("liveBarAlignTicks must be > 0");
        }
```

- [ ] **Step 3: Update both auxiliary constructors (the 18- and 19-arg overloads)**

Both call the canonical constructor with explicit values for the live-tuning fields. Add a default `liveBarAlignTicks` value at the end of each forwarding call. For pre-existing callers that don't supply alignment, the safe default is the current candidate-universe value:

In `JForexSessionConfig.java` near line 184 (the 19-arg overload's `this(...)` call), append `, DEFAULT_LIVE_BAR_ALIGN_TICKS` as the last argument. Add at the top of the record:

```java
    private static final int DEFAULT_LIVE_BAR_ALIGN_TICKS = 1000;
```

The 18-arg overload forwards into the 19-arg overload — no change needed there.

Note: this default is *only* for the auxiliary constructors used by tests. The production `fromEnvironment` path requires explicit configuration (Step 4). The default value tracks the active candidate universe; bump if the universe ever uses a larger `bar_ticks`.

- [ ] **Step 4: Wire `BEHEMOTH_JFOREX_LIVE_BAR_ALIGN_TICKS` env var into `fromEnvironment`**

Inside `fromEnvironment`, after the existing `BEHEMOTH_JFOREX_LIVE_STARTUP_BRIDGE_TIMEOUT_MINUTES` line, add a new field to the constructor call:

```java
                Integer.parseInt(setting(
                        environment,
                        "BEHEMOTH_JFOREX_LIVE_BAR_ALIGN_TICKS",
                        Integer.toString(DEFAULT_LIVE_BAR_ALIGN_TICKS)
                ))
```

- [ ] **Step 5: Run the Java unit tests to find construction-site fallout**

```bash
cd src/jforex && ./gradlew --no-daemon test
```

Expected: compile errors / test failures wherever a `JForexSessionConfig` is constructed with the canonical constructor and not yet updated.

- [ ] **Step 6: Commit**

```bash
cd ../..
git add src/jforex/src/main/java/com/behemoth/jforex/config/JForexSessionConfig.java
git commit -m "$(cat <<'EOF'
feat: add liveBarAlignTicks to JForexSessionConfig

Required field; fail fast when <= 0. fromEnvironment reads
BEHEMOTH_JFOREX_LIVE_BAR_ALIGN_TICKS, defaulting to 1000 (matches
the active candidate universe). Auxiliary constructors used by
tests pass DEFAULT_LIVE_BAR_ALIGN_TICKS.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 10: `HistoricalWarmupLoader` — use `liveBarAlignTicks` and fix formula (TDD)

**Files:**
- Modify: `src/jforex/src/test/java/com/behemoth/jforex/live/HistoricalWarmupLoaderTest.java`
- Modify: `src/jforex/src/main/java/com/behemoth/jforex/live/HistoricalWarmupLoader.java`

- [ ] **Step 1: Rewrite the test to assert the new alignment property**

Edit `HistoricalWarmupLoaderTest.java` and replace the existing `loaderKeepsWarmupTicksPlusPhaseRemainder` test method with:

```java
    @Test
    void loaderAlignsKeepToBarBoundary() throws Exception {
        Path eurUsdDir = tempDir.resolve("EURUSD");
        Files.createDirectories(eurUsdDir);
        Path parquetFile = eurUsdDir.resolve("ticks.parquet");
        Instant bridgeAnchorTs = Instant.parse("2025-07-07T08:21:15Z");
        // Pre-anchor tick count of 30_075 means preCount % 1000 == 75.
        writeParquetTicks(parquetFile, bridgeAnchorTs, 30_075, false);

        HistoricalWarmupLoader loader = new HistoricalWarmupLoader();
        WarmupSlice slice = loader.load(config(), tempDir, "EURUSD", bridgeAnchorTs);

        // With liveWarmupTicks=30_000 and liveBarAlignTicks=1000:
        //   keep = (30_000 / 1000) * 1000 + (30_075 % 1000) = 30_000 + 75 = 30_075
        // The aligned property: keep % 1000 == preCount % 1000.
        assertThat(slice.ticks()).hasSize(30_075);
        assertThat(slice.ticks().size() % 1000).isEqualTo(30_075 % 1000);
        assertThat(slice.bridgeAnchorTs()).isEqualTo(bridgeAnchorTs.minusSeconds(1));
        assertThat(slice.ticks()).extracting(RuntimeTick::timestamp).last().isEqualTo(slice.bridgeAnchorTs());
    }
```

- [ ] **Step 2: Update the `config()` helper at the bottom of the test file to pass `liveBarAlignTicks`**

Locate the private static `JForexSessionConfig config()` method (around line 104). Add `1000` (or `DEFAULT_LIVE_BAR_ALIGN_TICKS` if accessible) as the final constructor argument. The exact modification depends on which `JForexSessionConfig` constructor it currently uses — read it and add the new argument.

- [ ] **Step 3: Run the test to verify it fails (the formula is still old)**

```bash
cd src/jforex && ./gradlew --no-daemon test --tests com.behemoth.jforex.live.HistoricalWarmupLoaderTest.loaderAlignsKeepToBarBoundary
```

Expected: fail because the production formula is still `liveWarmupTicks + (preCount % PHASE_BAR_TICKS)` with `PHASE_BAR_TICKS=100`.

(Specifically: with the old formula and `PHASE_BAR_TICKS=100`, `keep = 30000 + (30075 % 100) = 30000 + 75 = 30075`. Test still passes by coincidence because `100` divides `1000`. Change the test seed: in Step 1 use `30_080` instead of `30_075` so old formula yields `30000 + 80 = 30080` while new formula with align=1000 yields `30000 + 80 = 30080`. They still agree because warmup_ticks=30000 is itself a multiple of 1000. Need a more sensitive test.)

Choose a `liveWarmupTicks` value that is **not** a multiple of 1000 — e.g. `liveWarmupTicks=30_500`:

In Step 2, when constructing `config()`, set `liveWarmupTicks=30_500`. With the old formula: `keep = 30_500 + 80 = 30_580`. With the new formula: `keep = (30_500 / 1000) * 1000 + 80 = 30_000 + 80 = 30_080`. Different results.

Update Step 1's test to assert `slice.ticks().hasSize(30_080)` (new formula's expected value).

- [ ] **Step 4: Re-run; expect the test to fail under the old formula**

```bash
cd src/jforex && ./gradlew --no-daemon test --tests com.behemoth.jforex.live.HistoricalWarmupLoaderTest.loaderAlignsKeepToBarBoundary
```

Expected: fail with `expected: 30080 but was: 30580`.

- [ ] **Step 5: Implement the fix in `HistoricalWarmupLoader.java`**

Replace lines 22 and 39:

```java
    private static final int PHASE_BAR_TICKS = 100;
```

→ delete this line.

```java
            int keep = config.liveWarmupTicks() + (preCount % PHASE_BAR_TICKS);
```

→

```java
            int align = config.liveBarAlignTicks();
            int keep = (config.liveWarmupTicks() / align) * align + (preCount % align);
```

- [ ] **Step 6: Re-run the test; expect pass**

```bash
cd src/jforex && ./gradlew --no-daemon test --tests com.behemoth.jforex.live.HistoricalWarmupLoaderTest
```

Expected: all `HistoricalWarmupLoaderTest` tests pass.

- [ ] **Step 7: Commit**

```bash
cd ../..
git add src/jforex/src/main/java/com/behemoth/jforex/live/HistoricalWarmupLoader.java \
        src/jforex/src/test/java/com/behemoth/jforex/live/HistoricalWarmupLoaderTest.java
git commit -m "$(cat <<'EOF'
fix: align HistoricalWarmupLoader keep to candidate bar_ticks

Replaces hard-coded PHASE_BAR_TICKS=100 with config.liveBarAlignTicks
and changes the formula so keep mod align == preCount mod align.
The runtime's open-bar accumulator at start now matches what
governance had at the same tick position.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 11: `LocalJForexHarnessConfig` — rename field and env var

**Files:**
- Modify: `src/jforex/src/main/java/com/behemoth/jforex/local/LocalJForexHarnessConfig.java`
- Modify: `src/jforex/src/main/java/com/behemoth/jforex/LocalJForexTesterRunner.java`

- [ ] **Step 1: Rename the record field**

In `LocalJForexHarnessConfig.java`, change `int phaseBarTicks` to `int barAlignTicks` (line 28).

In the compact-constructor validation (line 49), change the message and check name:

```java
if (tickBatchSize <= 0 || warmupTicks < 0 || lookbackDays < 0 || phaseBarTicks <= 0) {
    throw new IllegalArgumentException("tickBatchSize/phaseBarTicks must be > 0; warmupTicks/lookbackDays must be >= 0");
}
```

→

```java
if (tickBatchSize <= 0 || warmupTicks < 0 || lookbackDays < 0 || barAlignTicks <= 0) {
    throw new IllegalArgumentException("tickBatchSize/barAlignTicks must be > 0; warmupTicks/lookbackDays must be >= 0");
}
```

- [ ] **Step 2: Rename the env var read in `fromEnvironment`**

Change line 91 from:

```java
Integer.parseInt(System.getenv().getOrDefault("BEHEMOTH_LOCAL_JFOREX_PHASE_BAR_TICKS", "100")),
```

to:

```java
Integer.parseInt(System.getenv().getOrDefault("BEHEMOTH_LOCAL_JFOREX_BAR_ALIGN_TICKS", "1000")),
```

The default of `1000` matches the active candidate universe; the Python surrogate now sets this env var explicitly (Task 6 Step 7) so the default only kicks in when the harness runs standalone.

- [ ] **Step 3: Update the call site in `LocalJForexTesterRunner.java`**

```bash
grep -n "phaseBarTicks" src/jforex/src/main/java/com/behemoth/jforex/LocalJForexTesterRunner.java
```

Replace each `harnessConfig.phaseBarTicks()` with `harnessConfig.barAlignTicks()`.

- [ ] **Step 4: Run Java tests; fix any compile errors that surface**

```bash
cd src/jforex && ./gradlew --no-daemon compileJava compileTestJava
```

If a test fixture in another file constructs `LocalJForexHarnessConfig` positionally, the field rename doesn't change the position so the compile should still pass. Any direct `phaseBarTicks()` getter call needs renaming to `barAlignTicks()`.

- [ ] **Step 5: Commit**

```bash
cd ../..
git add src/jforex/src/main/java/com/behemoth/jforex/local/LocalJForexHarnessConfig.java \
        src/jforex/src/main/java/com/behemoth/jforex/LocalJForexTesterRunner.java
git commit -m "$(cat <<'EOF'
fix: rename LocalJForexHarnessConfig phaseBarTicks to barAlignTicks

Field renamed end-to-end; env var BEHEMOTH_LOCAL_JFOREX_BAR_ALIGN_TICKS
matches the value the Python surrogate now exports.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 12: Update remaining Java test fixtures for `JForexSessionConfig`

**Files:**
- Modify: `src/jforex/src/test/java/com/behemoth/jforex/BehemothStrategyCoreTest.java`
- Modify: `src/jforex/src/test/java/com/behemoth/jforex/live/LiveReadinessCoordinatorTest.java`

`BehemothStrategyCoreTest` constructs `JForexSessionConfig` via the **18-arg** auxiliary overload at 10 sites (lines 55, 134, 208, 285, 349, 410, 477, 587, 652, 732). Those forward into the 25-arg primary constructor with `DEFAULT_LIVE_BAR_ALIGN_TICKS=1000` already (per Task 9 Step 3). No edits required *if* every existing call uses the 18-arg form. Verify, then edit any that don't.

- [ ] **Step 1: Compile to surface any remaining errors**

```bash
cd src/jforex && ./gradlew --no-daemon compileTestJava
```

Expected: compiles. If anything fails because a test calls the 25-arg constructor directly, append `, 1000` to that argument list.

- [ ] **Step 2: For `LiveReadinessCoordinatorTest` line 460**

Read that constructor call. If it uses the 18-arg overload, no change. If it uses the 25-arg primary, append `, 1000` to the argument list.

- [ ] **Step 3: Run the full Java test suite**

```bash
cd src/jforex && ./gradlew --no-daemon test
```

Expected: all pass.

- [ ] **Step 4: Commit (only if step 1 or 2 made any changes)**

```bash
cd ../..
git status -s
# if any *.java is listed:
git add src/jforex/src/test/java/...
git commit -m "$(cat <<'EOF'
test: thread liveBarAlignTicks through Java test fixtures

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 13: Operator runbook — document the new config requirement

**Files:**
- Modify: `docs/strategy_bible/operator_runbook.md`

- [ ] **Step 1: Add a short subsection on bar alignment**

Append after the existing "Warmup" mention (around line 110):

```markdown
### Bar Alignment Ticks

The live runtime requires `BEHEMOTH_JFOREX_LIVE_BAR_ALIGN_TICKS` to be set to the largest candidate `bar_ticks` in the active universe. The default (`1000`) tracks the current 2026-04 universe; bump this if the universe ever uses a larger `bar_ticks`. A startup assertion compares the configured value to the loaded candidate set and fails fast if they disagree.

Matrix runners (`make monthly-recert`, `make local-jforex-parity-matrix`) auto-derive the alignment from the locked candidate set when `BAR_ALIGN_TICKS` (and `--bar-align-ticks`) is `0` (the default). To override, pass `BAR_ALIGN_TICKS=2000` to make.
```

- [ ] **Step 2: Commit**

```bash
git add docs/strategy_bible/operator_runbook.md
git commit -m "$(cat <<'EOF'
docs: operator note on bar alignment ticks env var

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 14: Pre-PR sweep — verify nothing else references the old names

**Files:** none.

- [ ] **Step 1: Search for stale references**

```bash
grep -rn "phase_bar_ticks\|phase-bar-ticks\|PHASE_BAR_TICKS\|phaseBarTicks" \
    --include="*.py" --include="*.java" --include="*.md" --include="Makefile" \
    | grep -v "graphify-out\|\.worktrees\|docs/superpowers/plans/2026-03-\|docs/superpowers/specs/2026-03-\|docs/superpowers/specs/2026-05-02-bar-alignment-ticks-warmup-fix-design.md\|docs/superpowers/plans/2026-05-02-bar-alignment-ticks-warmup-fix.md\|src/jforex/src/main/java/com/behemoth/jforex/live/LiveReadinessCoordinator.java"
```

Expected: empty. The grep allowlist explicitly excludes:
- `graphify-out/` — cached artifacts
- `.worktrees/` — sibling worktrees
- Older 2026-03 specs/plans — historical record, not edited by this change
- This PR's own spec and plan — they reference the old names in context
- `LiveReadinessCoordinator.java` — its `PHASE_BAR_TICKS` is intentionally not renamed (different concept; readiness reporting)

- [ ] **Step 2: Run the full Python and Java suites once more**

```bash
uv run pytest tests/ -q
cd src/jforex && ./gradlew --no-daemon test && cd ../..
```

Expected: all pass.

- [ ] **Step 3: Verify the worktree branch has the expected commit history**

```bash
git log --oneline main..HEAD
```

Expected: 11–13 commits, each with a clear conventional-commit subject.

---

## Task 15: Push branch and open PR

**Files:** none (git operations only).

- [ ] **Step 1: Push with upstream tracking**

```bash
git push -u origin fix/bar-align-ticks-warmup-formula
```

- [ ] **Step 2: Open the PR**

```bash
gh pr create --title "fix: align matrix and live warmup load to candidate bar_ticks" --body "$(cat <<'EOF'
## Summary

Stage 14 outcome parity for 2026-04 fails for 5/6 symbols at 85–98% coverage despite Stage 13 passing. Root cause: the warmup loader sized pre-load with mod-100 alignment (`phase_bar_ticks`) while candidates use 1000-tick bars, so the runtime's open-bar accumulator at start_ts differed from governance's by 0–999 ticks. Every subsequent 1000-tick bar boundary inherited the offset.

This PR:

- Hard-renames `phase_bar_ticks` → `bar_align_ticks` end-to-end (Python scripts, Makefile, Java config field, env vars).
- Replaces the alignment formula `keep = warmup_ticks + (full_pre_count % phase_bar_ticks)` with `keep = (warmup_ticks / align) * align + (full_pre_count % align)`. Property: `keep mod align == full_pre_count mod align`.
- Adds the new term to `UBIQUITOUS_LANGUAGE.md`.
- Adds `liveBarAlignTicks` as a required field on `JForexSessionConfig` (live runtime).

`LiveReadinessCoordinator.PHASE_BAR_TICKS=100` is intentionally not renamed — it is the readiness-reporting bar size, a different concept.

Spec: [`docs/superpowers/specs/2026-05-02-bar-alignment-ticks-warmup-fix-design.md`](docs/superpowers/specs/2026-05-02-bar-alignment-ticks-warmup-fix-design.md)

## Test plan

- [x] `uv run pytest tests/test_matrix_warmup.py tests/test_run_jforex_dukascopy_matrix.py tests/test_run_local_jforex_surrogate_matrix.py -q`
- [x] `cd src/jforex && ./gradlew --no-daemon test`
- [x] No stale references to `phase_bar_ticks`/`PHASE_BAR_TICKS` outside `LiveReadinessCoordinator` and historical docs (Task 14 grep)
- [ ] **After merge:** `make monthly-recert MODEL_MONTH=2026-04` — expect local-surrogate `signal_coverage_ratio` for EURUSD to move from 0.911 to ~1.0. Real-JForex matrix expected high but possibly <1.0 (residual broker-feed deficit deferred).

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

Expected: PR URL printed.

- [ ] **Step 3: Return the PR URL to the operator**

The operator merges after review and runs the post-merge sanity check.

---

## Self-Review Notes

Spec coverage:
- Vocabulary update — Task 2.
- Matrix runner rename + alignment formula — Tasks 5 (dukascopy) + 6 (surrogate).
- Default behaviour and abort-on-zero — Task 5 Step 4 / Task 6 Step 4.
- Alignment formula property — Task 4 (Python `align_keep`) + Task 10 (Java).
- Makefile rename — Task 8.
- Live runtime warmup loader fix — Task 10.
- `liveBarAlignTicks` config field + validation — Task 9.
- Drift-detection assertion — **deferred / not in this plan**: the spec described it as "kept conservatively close to where the candidate universe is loaded — exact placement during implementation". On reading the live-runtime code, the candidate-universe load happens API-side in Python; the live JForex strategy doesn't have direct access to it. Add as a follow-up after this PR lands; a tracking note in the PR description is sufficient. **If you want this in this PR**, re-open the spec to identify the placement.
- LocalJForexHarnessConfig env var rename — Task 11.
- Test updates — Tasks 7, 10, 12.
- Operator runbook — Task 13.
- Out-of-scope items — none implemented (correct).

No placeholders — every step contains exact paths, commands, expected output, or full code blocks.

Type consistency — `bar_align_ticks` (Python), `barAlignTicks` (Java field), `liveBarAlignTicks` (Java config field), `BEHEMOTH_LOCAL_JFOREX_BAR_ALIGN_TICKS` (surrogate env var), `BEHEMOTH_JFOREX_LIVE_BAR_ALIGN_TICKS` (live env var), `BAR_ALIGN_TICKS` (Makefile). Naming consistent across tasks.
