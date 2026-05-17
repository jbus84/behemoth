# Clean-Slate rebuild-all + Fail-Loud Mining Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `make rebuild-all` wipe `data/` for a clean-slate rebuild by default, and make mining fail loudly when its input data is missing instead of emitting a fake no-trade result.

**Architecture:** Three independent changes — a hard-error guard in the Stage 1 mining script, a new `clean-data` Makefile target, and a modification to `rebuild-all` to invoke `clean-data` unless `SKIP_CLEAN` is set. The mining change is test-driven; the Makefile changes are verified manually since Make targets are not unit-testable.

**Tech Stack:** Python, pytest, GNU Make, `scripts/run_tick_opportunity_mining.py`.

**Spec:** `docs/superpowers/specs/2026-05-17-clean-slate-rebuild-design.md`

---

## File Map

- `scripts/run_tick_opportunity_mining.py` — modify `run()` (lines ~955-997): replace the graceful "missing dataset_dir" branch with hard errors.
- `tests/test_tick_opportunity_mining.py` — add two tests for the hard-error paths.
- `Makefile` — add `clean-data` target; modify `rebuild-all` (line ~217) to call it.

---

## Task 1: Mining fails loudly on missing input data

**Files:**
- Test: `tests/test_tick_opportunity_mining.py`
- Modify: `scripts/run_tick_opportunity_mining.py:955-997`

**Context:** `run()` currently wraps the per-`bar_ticks` processing loop in
`if dataset_dir.exists():` with an `else:` that prints
`dataset_dir does not exist ... returning empty candidates (no-trade
condition)`. A directory that exists but contains no
`{symbol}_{ticks}tick_velocity.parquet` files also yields empty output
silently. Both must raise. A directory whose velocity files *are* present
but produce zero candidates must still return empty frames (legitimate
no-signal — unchanged).

- [ ] **Step 1: Write the failing tests**

Add to the end of `tests/test_tick_opportunity_mining.py`:

```python
def test_mining_raises_when_dataset_dir_missing(tmp_path: Path) -> None:
    cfg = {
        "symbol": "EURUSD",
        "dataset_dir": str(tmp_path / "does_not_exist"),
        "bar_ticks_grid": "1000",
        "horizons": "1,2,3",
        "train_years": "2022,2023,2024",
        "test_year": 2025,
        "min_annual_fills": 50.0,
        "gross_metric": "mean",
        "library_type": "separate",
        "barrier_grid_pips": "2,3",
    }
    with pytest.raises(FileNotFoundError, match="rebuild-all"):
        run(cfg)


def test_mining_raises_when_no_velocity_files_for_symbol(tmp_path: Path) -> None:
    dataset_dir = tmp_path / "tick_velocity"
    dataset_dir.mkdir(parents=True, exist_ok=True)
    cfg = {
        "symbol": "EURUSD",
        "dataset_dir": str(dataset_dir),
        "bar_ticks_grid": "1000",
        "horizons": "1,2,3",
        "train_years": "2022,2023,2024",
        "test_year": 2025,
        "min_annual_fills": 50.0,
        "gross_metric": "mean",
        "library_type": "separate",
        "barrier_grid_pips": "2,3",
    }
    with pytest.raises(FileNotFoundError, match="no velocity files"):
        run(cfg)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_tick_opportunity_mining.py::test_mining_raises_when_dataset_dir_missing tests/test_tick_opportunity_mining.py::test_mining_raises_when_no_velocity_files_for_symbol -v`
Expected: FAIL — `run()` currently returns empty frames instead of raising.

- [ ] **Step 3: Implement the hard-error guard**

In `scripts/run_tick_opportunity_mining.py`, replace the block currently at
lines 955-997 (from the `# Gracefully handle missing dataset_dir` comment
through the `else:` branch) with:

```python
    if not dataset_dir.exists():
        raise FileNotFoundError(
            f"mining input directory does not exist: {dataset_dir}\n"
            "Stage 0 data has not been built. Run "
            "`make rebuild-all MONTHS=...` to build the velocity dataset "
            "before mining."
        )

    files_found = 0
    for bt in bar_ticks_grid:
        path = dataset_dir / f"{symbol}_{int(bt)}tick_velocity.parquet"
        if not path.exists():
            print(f"skip {bt}: missing {path}")
            continue
        files_found += 1
        d = _prepare_frame(path, symbol=symbol, horizons=horizons)
        train = d[d["year"].isin(train_years)].copy().reset_index(drop=True)
        test = d[d["year"] == int(test_year)].copy().reset_index(drop=True)
        if train.empty or test.empty:
            print(f"skip {bt}: empty split (train/test)")
            continue
        if library_type in {"separate", "directional"}:
            directional_parts.append(
                _directional_candidates(
                    train=train,
                    test=test,
                    symbol=symbol,
                    bar_ticks=int(bt),
                    horizons=horizons,
                    min_annual_fills=min_annual_fills,
                    gross_metric=gross_metric,
                )
            )
        if library_type in {"separate", "oco"}:
            oco_parts.append(
                _oco_candidates(
                    train=train,
                    test=test,
                    symbol=symbol,
                    bar_ticks=int(bt),
                    horizons=horizons,
                    barrier_grid_pips=barrier_grid,
                    min_annual_fills=min_annual_fills,
                    gross_metric=gross_metric,
                )
            )
        print(f"ok {symbol} {bt}tick")

    if files_found == 0:
        raise FileNotFoundError(
            f"no velocity files found for {symbol} in {dataset_dir} "
            f"(expected {symbol}_<ticks>tick_velocity.parquet). "
            "Run `make rebuild-all MONTHS=...` to build Stage 0 data."
        )
```

This keeps the per-`bar_ticks` processing identical; it only (a) raises when
the directory is absent, and (b) tracks `files_found` and raises after the
loop when no velocity file matched the symbol. Empty splits within a present
file remain a non-fatal `skip`, and a present file producing zero candidates
still flows through as empty frames.

- [ ] **Step 4: Run the new tests to verify they pass**

Run: `uv run pytest tests/test_tick_opportunity_mining.py::test_mining_raises_when_dataset_dir_missing tests/test_tick_opportunity_mining.py::test_mining_raises_when_no_velocity_files_for_symbol -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Run the full mining test file to confirm no regression**

Run: `uv run pytest tests/test_tick_opportunity_mining.py -q`
Expected: all tests pass — in particular `test_tick_opportunity_mining_outputs`
still passes because it builds a real velocity parquet, so `files_found` is 1.

- [ ] **Step 6: Commit**

```bash
git add scripts/run_tick_opportunity_mining.py tests/test_tick_opportunity_mining.py
git commit -m "fix: mining raises on missing input data instead of fake no-trade"
```

---

## Task 2: Add `clean-data` Makefile target

**Files:**
- Modify: `Makefile`

**Context:** `data/*` is gitignored; raw ticks live outside the repo at
`~/Desktop/dukascopy_ticks` and must be preserved.

- [ ] **Step 1: Add the target**

Add this target to `Makefile`, immediately before the `rebuild-all:` target
(currently at line ~217):

```make
clean-data:
	@echo "Cleaning data/ (raw ticks at $$HOME/Desktop/dukascopy_ticks are kept)"
	rm -rf data
	mkdir -p data
```

- [ ] **Step 2: Verify the target runs**

Run: `make clean-data`
Expected: prints the "Cleaning data/" line; afterwards `ls data` shows an
empty directory and `ls ~/Desktop/dukascopy_ticks` is unchanged.

- [ ] **Step 3: Commit**

```bash
git add Makefile
git commit -m "feat: add clean-data target to wipe data/ for a clean rebuild"
```

---

## Task 3: `rebuild-all` cleans by default

**Files:**
- Modify: `Makefile` — `rebuild-all` target (line ~217)

**Context:** `rebuild-all` currently starts with a `MONTHS` guard, then runs
the Stage 0-5 loop. It must run `clean-data` after the guard, unless
`SKIP_CLEAN` is set.

- [ ] **Step 1: Insert the clean step**

In `Makefile`, the `rebuild-all` target currently begins:

```make
rebuild-all:
	@test -n "$(MONTHS)" || (echo "error: MONTHS required, e.g. make rebuild-all MONTHS=201801-202602" && exit 1)
	@echo "══════════════════════════════════════════"
	@echo "  Full rebuild for all symbols (Stages 0-5)"
	@echo "══════════════════════════════════════════"
```

Change it to insert a clean step after the `MONTHS` guard:

```make
rebuild-all:
	@test -n "$(MONTHS)" || (echo "error: MONTHS required, e.g. make rebuild-all MONTHS=201801-202602" && exit 1)
	@if [ -z "$(SKIP_CLEAN)" ]; then $(MAKE) clean-data; else echo "SKIP_CLEAN set — keeping existing data/"; fi
	@echo "══════════════════════════════════════════"
	@echo "  Full rebuild for all symbols (Stages 0-5)"
	@echo "══════════════════════════════════════════"
```

Leave the remainder of the `rebuild-all` target (the per-symbol
`onboard_symbol.py` loop, the data reliability audit, docs-contract, and
mkdocs build) unchanged.

- [ ] **Step 2: Verify the MONTHS guard still fires first**

Run: `make rebuild-all`
Expected: prints `error: MONTHS required ...` and exits non-zero, with no
`clean-data` output (the guard runs before the clean step).

- [ ] **Step 3: Verify SKIP_CLEAN is honoured (dry run)**

Run: `make -n rebuild-all MONTHS=202501-202501 SKIP_CLEAN=1`
Expected: the printed recipe does **not** include a `clean-data` /
`rm -rf data` invocation; it shows the `SKIP_CLEAN set` echo branch instead.

Run: `make -n rebuild-all MONTHS=202501-202501`
Expected: the printed recipe **does** include the `$(MAKE) clean-data` step.

- [ ] **Step 4: Commit**

```bash
git add Makefile
git commit -m "feat: rebuild-all cleans data/ by default (SKIP_CLEAN to opt out)"
```

---

## Self-Review

**Spec coverage:**
- Spec §1 (`clean-data` target) — Task 2.
- Spec §2 (`rebuild-all` cleans by default, `SKIP_CLEAN` opt-out, `MONTHS`
  stays required) — Task 3.
- Spec §3 (`retrain-all` unchanged) — no task needed; the plan touches
  neither `retrain-all` nor `onboard_symbol.py`.
- Spec §4 (fail loudly on missing input) — Task 1.
- Spec "Testing" — Task 1 Steps 1-5 (pytest); Task 2 Step 2 and Task 3
  Steps 2-3 (manual Makefile verification).

**Placeholder scan:** No TBDs; every code and command step is concrete.

**Type consistency:** `run(cfg)` returns the existing
`tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]`; tests call it with the
same `cfg` dict shape as the existing `test_tick_opportunity_mining_outputs`.
`files_found` is a local `int`. `FileNotFoundError` is used consistently in
both raise sites and both tests' `pytest.raises`.
