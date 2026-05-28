# Stage I/O Contracts Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans (recommended for this tightly coupled refactor) or superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Introduce a declarative `stage_contracts.py` manifest as the single source of truth for inter-stage I/O, eliminating hardcoded family/library mappings in the Stage 2 mining writer and Stage 3 WFO reader, and making Stage 3 output naming explicit.

**Architecture:** A new importable Python module (`src/behemoth/governance/stage_contracts.py`) declares the family↔library↔artifact mapping, Stage 3 output naming policy, and required columns. `scripts/run_tick_opportunity_mining.py` and `scripts/run_tick_opportunity_monthly_wfo.py` import from this manifest instead of restating facts. Tests assert code behavior matches manifest declarations. The docs generator renders the manifest into human-readable stage capsules.

**Tech Stack:** Python 3.12, pandas, pytest, `uv`. No new external dependencies.

---

## Current State

### Hardcoded lists in `scripts/run_tick_opportunity_mining.py`

- Lines 1468–1480: families are manually concatenated into 7 library DataFrames. `directional` library = 5 families, `oco` = 1 family, etc.
- Lines 1482–1501: quality-tier assignment uses hardcoded `library="directional"`, `library="oco"`, etc. Cross-symbol families reuse `"directional"` thresholds.
- Line 1502: `_build_summary(directional, oco, no_touch)` receives only 3 of the 7 libraries.
- Lines 1544–1559: 7 output filenames are hardcoded individually.

### Hardcoded lists in `scripts/run_tick_opportunity_monthly_wfo.py`

- Lines 100–110: `FAMILY_TO_LIBRARY_FOR_PARAMS` maps each family to its candidate CSV library.
- Lines 58–68: `SYMBOL_LOCAL_WFO_FAMILIES` and `CROSS_SYMBOL_WFO_FAMILIES` are hardcoded sets.
- Lines 326–337: `_libraries_for_requested_families()` repeats the 7-library order inline. This is a separate source of truth even after replacing `FAMILY_TO_LIBRARY_FOR_PARAMS`.
- Lines 1056–1077 and 1239: real WFO runs call `_write_library_outputs(..., lib=family, ...)`, while legitimately empty runs fall back to `families = [lib]`. This means real outputs are family-named but empty outputs are library-named.

### Failure modes this causes

1. **Missing families false alarm:** `directional_inverse`, `directional_run`, `double_touch`, `pullback` live inside `directional_candidates.csv` but no per-family file exists. Operators (and LLMs) conclude they are missing.
2. **Under-reporting summary:** `_build_summary` only covers 3 libraries, so `candidate_summary.csv` silently drops the other 4 even though the data exists.
3. **WFO output naming ambiguity:** Stage 3 can complete all 66 prediction jobs while emitting a mix of family-named and library-named outputs. This is related to by-library/by-family discoverability, but distinct from the WFO cache-key fix.
4. **Tick-exact verdict collision (destructive):** `scripts/verify_tick_exact_shortlist.py` writes `<SYMBOL>_<library>_tick_exact_summary.csv`. Running Stage 6 for the 5 directional-library families on one symbol overwrites the same file 5 times, so per-family `overall_pass` verdicts are lost — only the last family run per symbol survives, and the surviving file cannot be attributed to a family. Unlike modes 1–3 (interpretation hazards), this **destroys** verdict data the Stage 9 freeze depends on. Highest-priority standalone fix. Observed in the 2026-05 trial: 21 combos ran exit 0 but only 8 summary files survived, mixing PASS (1.0 exact-match) and FAIL (0.0) results that could not be tied back to a family.

### Review findings incorporated

- Task 3 must not reference `library_dfs` in `main()` unless it is rebuilt there or returned from `run()`.
- Task 4 must replace the hardcoded `_libraries_for_requested_families()` order with `MINING_OUTPUT_LIBRARIES`, not only replace `FAMILY_TO_LIBRARY`.
- Task 4 must document and test the WFO output naming policy for real and legitimately empty runs.
- Task 6 must import `json` in `scripts/run_tick_opportunity_mining.py` if that script calls `json.dumps`.
- The manifest must use `typing.Any`, not the builtin `any`, in type annotations.
- Task 2 is a checkpoint only; do not merge a manifest-only change without the producer and consumer refactors.
- Task 1b (tick-exact family-keyed output) is a standalone fix that can ship ahead of the manifest, like Task 1. It is the highest-priority of the standalone fixes because failure mode 4 is destructive. The manifest (Task 2) must declare Stage 6 summaries as `(symbol, family)`-keyed so the fix can later derive its filename from the contract rather than a second hardcoded template.

---

## File Structure

**Create:**
- `src/behemoth/governance/stage_contracts.py` — importable manifest: family↔library mapping, quality-tier rules, filename templates, required columns, and markdown renderer for stage docs.
- `tests/test_stage_contracts.py` — tests asserting manifest invariants and code-matches-manifest.

**Modify:**
- `scripts/run_tick_opportunity_mining.py:1468–1506` — build library DataFrames and summary from manifest.
- `scripts/run_tick_opportunity_mining.py:1502` — `_build_summary` signature + call site.
- `scripts/run_tick_opportunity_mining.py:1544–1567` — derive output filenames from manifest.
- `scripts/run_tick_opportunity_monthly_wfo.py:100–110` — replace `FAMILY_TO_LIBRARY_FOR_PARAMS` with manifest import.
- `scripts/run_tick_opportunity_monthly_wfo.py:58–68` — derive family sets from manifest.
- `scripts/run_tick_opportunity_monthly_wfo.py:326–337` — derive requested-family library order from manifest.
- `scripts/run_tick_opportunity_monthly_wfo.py:1056–1077,1239` — make WFO output naming explicit for real and legitimately empty outputs.
- `scripts/verify_tick_exact_shortlist.py` — write the tick-exact summary keyed by `(symbol, family)` (`<SYMBOL>_<family>_tick_exact_summary.csv`) instead of `(symbol, library)`. Apply the same family-keying to the monthly/state companion CSVs and the report path. (Task 1b.)
- `tests/test_tick_exact_shortlist.py` (or nearest existing tick-exact test) — assert two families sharing the `directional` library produce two distinct summary files for the same symbol. (Task 1b.)
- `scripts/build_process_stage_docs.py:66–68` — append I/O contract markdown for stage02/stage03.

**Regenerate:**
- `docs/generated/process/stage02.md` — via `make docs-contract-ci` or `scripts/build_process_stage_docs.py`.
- `docs/generated/process/stage03.md` — same.

---

## Task 1: Fix `_build_summary` to cover all 7 libraries

**Files:**
- Modify: `scripts/run_tick_opportunity_mining.py:924–950` (signature + body)
- Modify: `scripts/run_tick_opportunity_mining.py:1502` (call site)
- Test: `tests/test_tick_opportunity_mining.py` (parity test must still pass)

**Context:** This is an immediate fix from ADR 0004 § Consequences. It can ship in its own small PR if desired, but is included here as the first task.

- [ ] **Step 1: Write the failing test for 7-library summary**

Add to `tests/test_tick_opportunity_mining.py` (append at end of file):

```python
def test_build_summary_covers_all_libraries():
    import pandas as pd
    from scripts.run_tick_opportunity_mining import _build_summary

    # Build minimal 7 non-empty DataFrames so summary should have 7 rows
    def _make_df(lib: str) -> pd.DataFrame:
        return pd.DataFrame({
            "selection_pass": [True],
            "mean_gross_pips_test": [1.0],
            "random_baseline_z": [0.5],
        }).assign(library=lib)

    dfs = {
        "directional": _make_df("directional"),
        "oco": _make_df("oco"),
        "oco_asymmetric": _make_df("oco_asymmetric"),
        "no_touch": _make_df("no_touch"),
        "dollar_residual": _make_df("dollar_residual"),
        "dispersion_rank": _make_df("dispersion_rank"),
        "lead_lag": _make_df("lead_lag"),
    }
    summary = _build_summary(dfs)
    assert len(summary) == 7
    libs = set(summary["library"].tolist())
    assert libs == {
        "directional", "oco", "oco_asymmetric", "no_touch",
        "dollar_residual", "dispersion_rank", "lead_lag",
    }
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/test_tick_opportunity_mining.py::test_build_summary_covers_all_libraries -v
```

Expected: FAIL with `TypeError: _build_summary() takes 3 positional arguments but 7 were given` (or similar).

- [ ] **Step 3: Update `_build_summary` signature and body**

In `scripts/run_tick_opportunity_mining.py:924–950`, replace:

```python
def _build_summary(
    directional: pd.DataFrame, oco: pd.DataFrame, no_touch: pd.DataFrame
) -> pd.DataFrame:
    frames = []
    if not directional.empty:
        frames.append(directional.assign(library="directional"))
    if not oco.empty:
        frames.append(oco.assign(library="oco"))
    if not no_touch.empty:
        frames.append(no_touch.assign(library="no_touch"))
```

With:

```python
def _build_summary(
    library_dfs: dict[str, pd.DataFrame],
) -> pd.DataFrame:
    frames = []
    for lib, df in library_dfs.items():
        if not df.empty:
            frames.append(df.assign(library=lib))
```

The rest of `_build_summary` (lines 934–950) stays unchanged.

- [ ] **Step 4: Update the call site in `run()`**

In `scripts/run_tick_opportunity_mining.py:1502`, replace:

```python
    summary = _build_summary(directional, oco, no_touch)
```

With:

```python
    summary = _build_summary({
        "directional": directional,
        "oco": oco,
        "oco_asymmetric": oco_asymmetric,
        "no_touch": no_touch,
        "dollar_residual": dollar_residual,
        "dispersion_rank": dispersion_rank,
        "lead_lag": lead_lag,
    })
```

- [ ] **Step 5: Run the new test to verify it passes**

```bash
uv run pytest tests/test_tick_opportunity_mining.py::test_build_summary_covers_all_libraries -v
```

Expected: PASS.

- [ ] **Step 6: Run existing parity tests to ensure no regression**

```bash
uv run pytest -q tests/test_tick_opportunity_mining.py
```

Expected: all existing tests still PASS.

- [ ] **Step 7: Commit**

```bash
git add scripts/run_tick_opportunity_mining.py tests/test_tick_opportunity_mining.py
git commit -m "fix(mining): _build_summary covers all 7 output libraries

Eliminates under-reporting in candidate_summary.csv where only
directional, oco, and no_touch were previously included.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 1b: Make tick-exact summary family-keyed (highest-priority standalone fix)

**Why first:** failure mode 4 is the only destructive one — per-family Stage 6 verdicts are silently overwritten. This fix is independent of the manifest and should ship immediately, like Task 1. (Once Task 2 lands, the filename should derive from the manifest's `(symbol, family)` key instead of an inline template; this task hardcodes the family-keyed template as an interim, and Task 5's contract test will assert it.)

**Root cause:** `scripts/verify_tick_exact_shortlist.py` selects output paths from library-keyed presets (around lines 96–115: a `directional` preset writes `{s}_directional_tick_exact_summary.csv`, plus `oco_asymmetric` and `oco` presets). The output filename is chosen by *library*, not by the `--family-required` family, so all five directional-library families write the same file for a given symbol.

**Files:**
- Modify: `scripts/verify_tick_exact_shortlist.py` — output path construction (`out_summary_csv`, `out_monthly_csv`, `out_state_csv`, and the `report_out`) must use the resolved family, not the library preset.
- Test: `tests/test_tick_exact_shortlist.py` (create if absent; otherwise the nearest existing tick-exact test).

- [ ] **Step 1: Write the failing test**

```python
def test_tick_exact_summary_is_family_keyed(tmp_path):
    """Two families sharing the `directional` library must not collide: each
    must write its own <SYMBOL>_<family>_tick_exact_summary.csv. Regression for
    the 2026-05 trial collision where directional_inverse overwrote directional."""
    from scripts.verify_tick_exact_shortlist import _resolve_output_paths  # name per implementation

    p_dir = _resolve_output_paths(symbol="EURUSD", family="directional", out_root=str(tmp_path))
    p_inv = _resolve_output_paths(symbol="EURUSD", family="directional_inverse", out_root=str(tmp_path))
    assert p_dir["out_summary_csv"].endswith("EURUSD_directional_tick_exact_summary.csv")
    assert p_inv["out_summary_csv"].endswith("EURUSD_directional_inverse_tick_exact_summary.csv")
    assert p_dir["out_summary_csv"] != p_inv["out_summary_csv"]
```

- [ ] **Step 2: Run it to confirm RED**

Run: `uv run pytest -q tests/test_tick_exact_shortlist.py::test_tick_exact_summary_is_family_keyed`
Expected: fails (function missing, or paths collide because they are library-keyed).

- [ ] **Step 3: Implement family-keyed output paths**

Replace the library-keyed preset selection with a single helper that builds all four output paths from the `(symbol, family)` pair:

```python
def _resolve_output_paths(symbol: str, family: str, out_root: str) -> dict[str, str]:
    base = f"{out_root}/{symbol}_{family}_tick_exact"
    return {
        "out_summary_csv": f"{base}_summary.csv",
        "out_monthly_csv": f"{base}_monthly.csv",
        "out_state_csv": f"{base}_state.csv",
        "report_out": f"docs/analysis/{symbol.lower()}_{family}_tick_exact_shortlist_report.md",
    }
```

`family` is the value of `--family-required` (the run already requires it). Use these paths instead of the library presets when writing outputs. Keep `out_root` defaulting to `data/analysis/tick_opportunity_mining/reduced_core`.

- [ ] **Step 4: Run it to confirm GREEN**

Run: `uv run pytest -q tests/test_tick_exact_shortlist.py::test_tick_exact_summary_is_family_keyed`
Expected: passes.

- [ ] **Step 5: Re-run the affected suite**

Run: `uv run pytest -q tests/test_tick_exact_shortlist.py` (and any test that exercises `verify_tick_exact_shortlist`).
Expected: all pass; no other test depended on the library-keyed filename. If one does, update it to the family-keyed name (the old name was a collision bug, not a contract).

- [ ] **Step 6: Commit**

```bash
git add scripts/verify_tick_exact_shortlist.py tests/test_tick_exact_shortlist.py
git commit -m "fix(tick-exact): key summary outputs by (symbol, family) not library

The directional library expands to 5 families; library-keyed summary
filenames overwrote each other, silently losing per-family verdicts.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 2: Create the `stage_contracts.py` manifest module

**Files:**
- Create: `src/behemoth/governance/stage_contracts.py`
- Test: `tests/test_stage_contracts.py` (initial import smoke test)

**Merge discipline:** This task is a local checkpoint only. Do not merge after Task 2 by itself; ADR 0004 requires the manifest and the producer/consumer refactors to land together so the manifest does not become a fourth source of truth.

- [ ] **Step 1: Write the failing import test**

Create `tests/test_stage_contracts.py`:

```python
from __future__ import annotations

import pytest


class TestManifestExists:
    def test_can_import_stage_contracts(self):
        from behemoth.governance.stage_contracts import (
            MINING_LIBRARY_FAMILIES,
            FAMILY_TO_LIBRARY,
            QUALITY_TIER_LIBRARY,
            MINING_OUTPUT_LIBRARIES,
            CANDIDATE_FILENAME_TEMPLATE,
            CANDIDATE_REQUIRED_COLUMNS,
        )

        assert isinstance(MINING_LIBRARY_FAMILIES, dict)
        assert "directional" in MINING_LIBRARY_FAMILIES
        assert len(MINING_OUTPUT_LIBRARIES) == 7
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/test_stage_contracts.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'behemoth.governance.stage_contracts'`.

- [ ] **Step 3: Create `src/behemoth/governance/stage_contracts.py`**

```python
"""Declarative stage-contract manifest for tick-opportunity governance pipeline.

Single source of truth for:
- family↔library↔artifact-name mapping
- quality-tier library assignments
- required columns per artifact
- stage I/O contracts (input/output glob patterns)

Producers and consumers import from here rather than restating facts.
"""

from __future__ import annotations

from typing import Any

# === Stage 02 (Opportunity Mining) -> Stage 03 (Monthly WFO) ===

# Output library names and the families contained in each candidate CSV.
# These match the <SYMBOL>_<library>_candidates.csv files written by
# scripts/run_tick_opportunity_mining.py.
MINING_LIBRARY_FAMILIES: dict[str, list[str]] = {
    "directional": [
        "directional",
        "directional_inverse",
        "directional_run",
        "double_touch",
        "pullback",
    ],
    "oco": ["oco_first_touch"],
    "oco_asymmetric": ["oco_asymmetric"],
    "no_touch": ["no_touch"],
    "dollar_residual": ["dollar_residual"],
    "dispersion_rank": ["dispersion_rank"],
    "lead_lag": ["lead_lag"],
}

# Reverse lookup: family -> library.
# Used by Stage 3 WFO to locate the candidate CSV for a given family.
FAMILY_TO_LIBRARY: dict[str, str] = {
    family: lib
    for lib, families in MINING_LIBRARY_FAMILIES.items()
    for family in families
}

# Families that require cross-symbol context (cs_frame).
CROSS_SYMBOL_FAMILIES: set[str] = {
    "dollar_residual",
    "dispersion_rank",
    "lead_lag",
}

# Local families = everything else.
LOCAL_FAMILIES: set[str] = {
    family
    for lib, families in MINING_LIBRARY_FAMILIES.items()
    for family in families
    if family not in CROSS_SYMBOL_FAMILIES
}

# Quality-tier library: which threshold set each output library uses.
# directional, dollar_residual, dispersion_rank, lead_lag share directional thresholds.
# oco, oco_asymmetric share oco thresholds. no_touch is independent.
QUALITY_TIER_LIBRARY: dict[str, str] = {
    "directional": "directional",
    "oco": "oco",
    "oco_asymmetric": "oco",
    "no_touch": "no_touch",
    "dollar_residual": "directional",
    "dispersion_rank": "directional",
    "lead_lag": "directional",
}

# === Output Artifacts ===

MINING_OUTPUT_LIBRARIES: list[str] = list(MINING_LIBRARY_FAMILIES.keys())

CANDIDATE_FILENAME_TEMPLATE: str = "{symbol}_{library}_candidates.csv"
SUMMARY_FILENAME_TEMPLATE: str = "{symbol}_candidate_summary.csv"
FILLS_FILENAME_TEMPLATE: str = "{symbol}_candidate_fills.parquet"
WFO_OUTPUT_FILENAME_TEMPLATES: dict[str, str] = {
    "metrics": "{symbol}_{scope}_monthly_metrics.csv",
    "thresholds": "{symbol}_{scope}_monthly_thresholds.csv",
    "predictions": "{symbol}_{scope}_monthly_predictions.parquet",
    "importance": "{symbol}_{scope}_monthly_importance.csv",
}

# === Required Columns ===
# Columns that every consumer of candidate CSVs expects to exist.
# Derived from the parity check in tests/test_tick_opportunity_mining.py
# and from downstream WFO column usage.
CANDIDATE_REQUIRED_COLUMNS: list[str] = [
    "annualized_test_fills",
    "bar_ticks",
    "both_window_rate",
    "both_window_rate_train",
    "candidate_id",
    "candidate_schema_version",
    "family",
    "gross_std_test",
    "hit_rate_gross_test",
    "horizon",
    "mean_flow_persistence_train",
    "mean_gross_pips_test",
    "mean_gross_pips_train",
    "mean_tick_burst_train",
    "mean_vol_cluster_train",
    "median_gross_pips_test",
    "median_gross_pips_train",
    "ml_ready_target_type",
    "p_up_first",
    "quality_score",
    "quality_tier",
    "quality_tier_basis",
    "random_baseline_control_mean",
    "random_baseline_p",
    "random_baseline_z",
    "regime_desc",
    "selection_pass",
    "selection_pass_basis",
    "session_coverage",
    "state_id",
    "symbol",
    "test_count",
    "train_count",
]

# === Stage I/O Contracts ===

STAGE02_CONTRACT: dict[str, Any] = {
    "stage_id": "stage02",
    "produced_by": None,
    "input_patterns": [
        "data/analysis/tick_velocity/{symbol}_{bar_ticks}tick_velocity.parquet",
        "configs/research/experiments/{symbol}_tick_opportunity_mining.yaml",
    ],
    "output_patterns": [
        "data/analysis/tick_opportunity_mining/{symbol}_candidate_summary.csv",
        "data/analysis/tick_opportunity_mining/{symbol}_candidate_fills.parquet",
        *[
            f"data/analysis/tick_opportunity_mining/{CANDIDATE_FILENAME_TEMPLATE.format(symbol='{symbol}', library=lib)}"
            for lib in MINING_OUTPUT_LIBRARIES
        ],
    ],
}

STAGE03_CONTRACT: dict[str, Any] = {
    "stage_id": "stage03",
    "produced_by": "stage02",
    "input_patterns": [
        f"data/analysis/tick_opportunity_mining/{CANDIDATE_FILENAME_TEMPLATE.format(symbol='{symbol}', library=lib)}"
        for lib in MINING_OUTPUT_LIBRARIES
    ],
    "output_patterns": [
        "data/analysis/tick_opportunity_mining/wfo_m3to1_{library}_fullcap_{symbol}/{symbol}_{scope}_monthly_predictions.parquet",
        "data/analysis/tick_opportunity_mining/wfo_m3to1_{library}_fullcap_{symbol}/{symbol}_{scope}_monthly_metrics.csv",
        "data/analysis/tick_opportunity_mining/wfo_m3to1_{library}_fullcap_{symbol}/{symbol}_{scope}_monthly_thresholds.csv",
        "data/analysis/tick_opportunity_mining/wfo_m3to1_{library}_fullcap_{symbol}/{symbol}_{scope}_monthly_importance.csv",
    ],
    "output_scope": (
        "Use family scope when a WFO config requests explicit families, including "
        "legitimately empty runs. Use library scope only for legacy library-mode runs "
        "with no requested family filter."
    ),
}


# === Markdown Renderer for Docs Generator ===

def render_stage_io_contract(stage_id: str) -> str:
    """Return a markdown snippet describing the I/O contract for a stage.

    Called by scripts/build_process_stage_docs.py to inject contract
    metadata into generated stage capsules.
    """
    if stage_id == "stage02":
        contract = STAGE02_CONTRACT
        title = "Stage 02 I/O Contract"
    elif stage_id == "stage03":
        contract = STAGE03_CONTRACT
        title = "Stage 03 I/O Contract"
    else:
        return ""

    lines = [f"## {title}", ""]

    if contract.get("produced_by"):
        lines.append(f"**Produced by:** `{contract['produced_by']}`")
        lines.append("")

    lines.append("**Input artifacts:**")
    for pat in contract["input_patterns"]:
        lines.append(f"- `{pat}`")
    lines.append("")

    lines.append("**Output artifacts:**")
    for pat in contract["output_patterns"]:
        lines.append(f"- `{pat}`")
    lines.append("")

    if contract.get("output_scope"):
        lines.append(f"**Output scope:** {contract['output_scope']}")
        lines.append("")

    if stage_id == "stage02":
        lines.append("**Library → family expansion:**")
        lines.append("")
        lines.append("| Library file | Families contained |")
        lines.append("|--------------|--------------------|")
        for lib, families in MINING_LIBRARY_FAMILIES.items():
            fname = CANDIDATE_FILENAME_TEMPLATE.format(symbol="<SYMBOL>", library=lib)
            lines.append(f"| `{fname}` | {', '.join(families)} |")
        lines.append("")

        lines.append("**Required columns per candidate CSV:**")
        lines.append(f"```")
        lines.append(", ".join(CANDIDATE_REQUIRED_COLUMNS))
        lines.append(f"```")
        lines.append("")

    return "\n".join(lines)
```

- [ ] **Step 4: Run test to verify it passes**

```bash
uv run pytest tests/test_stage_contracts.py -v
```

Expected: PASS.

- [ ] **Step 5: Checkpoint commit**

```bash
git add src/behemoth/governance/stage_contracts.py tests/test_stage_contracts.py
git commit -m "feat(governance): add stage_contracts manifest module

Introduces single source of truth for family/library/artifact mapping,
quality-tier rules, and required columns. Render helper included for
stage docs generator.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

This commit is for local review granularity only. Squash or merge it together with Tasks 3 and 4 before opening or merging the PR.

---

## Task 3: Refactor mining writer to consume manifest

**Files:**
- Modify: `scripts/run_tick_opportunity_mining.py:1468–1506`
- Modify: `scripts/run_tick_opportunity_mining.py:1544–1567`
- Modify: `scripts/run_tick_opportunity_mining.py:1571–1574` (_save_report call)
- Test: `tests/test_tick_opportunity_mining.py` (parity test)

- [ ] **Step 1: Write the failing test asserting manifest alignment**

Append to `tests/test_stage_contracts.py`:

```python
class TestMiningAlignsWithManifest:
    def test_mining_output_libraries_match_manifest(self):
        from behemoth.governance.stage_contracts import MINING_OUTPUT_LIBRARIES
        # After the refactor, run() should produce exactly these libraries
        expected = [
            "directional", "oco", "oco_asymmetric", "no_touch",
            "dollar_residual", "dispersion_rank", "lead_lag",
        ]
        assert MINING_OUTPUT_LIBRARIES == expected
```

Run it:

```bash
uv run pytest tests/test_stage_contracts.py::TestMiningAlignsWithManifest -v
```

Expected: PASS (the manifest already has these values). This test documents the invariant.

- [ ] **Step 2: Add manifest import to mining script**

At the top of `scripts/run_tick_opportunity_mining.py`, in the imports section (around line 22 where other `behemoth` imports are), add:

```python
from behemoth.governance.stage_contracts import (
    CANDIDATE_FILENAME_TEMPLATE,
    MINING_LIBRARY_FAMILIES,
    MINING_OUTPUT_LIBRARIES,
    QUALITY_TIER_LIBRARY,
    SUMMARY_FILENAME_TEMPLATE,
)
```

- [ ] **Step 3: Replace hardcoded DataFrame assembly with manifest loop**

In `scripts/run_tick_opportunity_mining.py:1468–1501`, replace:

```python
    directional = pd.DataFrame(
        per_family_rows.get("directional", [])
        + per_family_rows.get("directional_inverse", [])
        + per_family_rows.get("directional_run", [])
        + per_family_rows.get("double_touch", [])
        + per_family_rows.get("pullback", [])
    )
    oco = pd.DataFrame(per_family_rows.get("oco_first_touch", []))
    oco_asymmetric = pd.DataFrame(per_family_rows.get("oco_asymmetric", []))
    no_touch = pd.DataFrame(per_family_rows.get("no_touch", []))
    dollar_residual = pd.DataFrame(per_family_rows.get("dollar_residual", []))
    dispersion_rank = pd.DataFrame(per_family_rows.get("dispersion_rank", []))
    lead_lag = pd.DataFrame(per_family_rows.get("lead_lag", []))
    if not directional.empty:
        directional = _assign_quality_tier(directional, library="directional")
        directional = _stamp_candidate_contract(directional)
    if not oco.empty:
        oco = _assign_quality_tier(oco, library="oco")
        oco = _stamp_candidate_contract(oco)
    if not oco_asymmetric.empty:
        oco_asymmetric = _assign_quality_tier(oco_asymmetric, library="oco")
        oco_asymmetric = _stamp_candidate_contract(oco_asymmetric)
    if not no_touch.empty:
        no_touch = _assign_quality_tier(no_touch, library="no_touch")
        no_touch = _stamp_candidate_contract(no_touch)
    if not dollar_residual.empty:
        dollar_residual = _assign_quality_tier(dollar_residual, library="directional")
        dollar_residual = _stamp_candidate_contract(dollar_residual)
    if not dispersion_rank.empty:
        dispersion_rank = _assign_quality_tier(dispersion_rank, library="directional")
        dispersion_rank = _stamp_candidate_contract(dispersion_rank)
    if not lead_lag.empty:
        lead_lag = _assign_quality_tier(lead_lag, library="directional")
        lead_lag = _stamp_candidate_contract(lead_lag)
```

With:

```python
    library_dfs: dict[str, pd.DataFrame] = {}
    for lib, families in MINING_LIBRARY_FAMILIES.items():
        rows = []
        for fam in families:
            rows.extend(per_family_rows.get(fam, []))
        df = pd.DataFrame(rows)
        if not df.empty:
            tier_lib = QUALITY_TIER_LIBRARY[lib]
            df = _assign_quality_tier(df, library=tier_lib)
            df = _stamp_candidate_contract(df)
        library_dfs[lib] = df

    directional = library_dfs["directional"]
    oco = library_dfs["oco"]
    oco_asymmetric = library_dfs["oco_asymmetric"]
    no_touch = library_dfs["no_touch"]
    dollar_residual = library_dfs["dollar_residual"]
    dispersion_rank = library_dfs["dispersion_rank"]
    lead_lag = library_dfs["lead_lag"]
```

- [ ] **Step 4: Update `_build_summary` call**

In `scripts/run_tick_opportunity_mining.py:1502`, replace:

```python
    summary = _build_summary({
        "directional": directional,
        "oco": oco,
        "oco_asymmetric": oco_asymmetric,
        "no_touch": no_touch,
        "dollar_residual": dollar_residual,
        "dispersion_rank": dispersion_rank,
        "lead_lag": lead_lag,
    })
```

With:

```python
    summary = _build_summary(library_dfs)
```

- [ ] **Step 5: Rebuild the library map in `main()`**

In `scripts/run_tick_opportunity_mining.py`, immediately after the `fills_path = fills_writer.path` line, insert:

```python
    library_dfs = {
        "directional": directional,
        "oco": oco,
        "oco_asymmetric": oco_asymmetric,
        "no_touch": no_touch,
        "dollar_residual": dollar_residual,
        "dispersion_rank": dispersion_rank,
        "lead_lag": lead_lag,
    }
```

This keeps `run()`'s existing return shape intact while making the manifest-driven write loop in `main()` use a local `library_dfs` variable that actually exists in that scope.

- [ ] **Step 6: Replace hardcoded file writes with manifest loop**

In `scripts/run_tick_opportunity_mining.py:1544–1567`, replace:

```python
    d_path = out_dir / f"{symbol}_directional_candidates.csv"
    o_path = out_dir / f"{symbol}_oco_candidates.csv"
    oa_path = out_dir / f"{symbol}_oco_asymmetric_candidates.csv"
    nt_path = out_dir / f"{symbol}_no_touch_candidates.csv"
    dr_path = out_dir / f"{symbol}_dollar_residual_candidates.csv"
    dx_path = out_dir / f"{symbol}_dispersion_rank_candidates.csv"
    ll_path = out_dir / f"{symbol}_lead_lag_candidates.csv"
    s_path = out_dir / f"{symbol}_candidate_summary.csv"
    directional.to_csv(d_path, index=False)
    oco.to_csv(o_path, index=False)
    oco_asymmetric.to_csv(oa_path, index=False)
    no_touch.to_csv(nt_path, index=False)
    dollar_residual.to_csv(dr_path, index=False)
    dispersion_rank.to_csv(dx_path, index=False)
    lead_lag.to_csv(ll_path, index=False)
    summary.to_csv(s_path, index=False)
    print(f"wrote: {d_path}", flush=True)
    print(f"wrote: {o_path}", flush=True)
    print(f"wrote: {oa_path}", flush=True)
    print(f"wrote: {nt_path}", flush=True)
    print(f"wrote: {dr_path}", flush=True)
    print(f"wrote: {dx_path}", flush=True)
    print(f"wrote: {ll_path}", flush=True)
    print(f"wrote: {s_path}", flush=True)
```

With:

```python
    library_paths: dict[str, Path] = {}
    for lib in MINING_OUTPUT_LIBRARIES:
        fname = CANDIDATE_FILENAME_TEMPLATE.format(symbol=symbol, library=lib)
        path = out_dir / fname
        library_dfs[lib].to_csv(path, index=False)
        library_paths[lib] = path
        print(f"wrote: {path}", flush=True)

    s_path = out_dir / SUMMARY_FILENAME_TEMPLATE.format(symbol=symbol)
    summary.to_csv(s_path, index=False)
    print(f"wrote: {s_path}", flush=True)
```

- [ ] **Step 7: Run parity tests to verify no regression**

```bash
uv run pytest -q tests/test_tick_opportunity_mining.py
```

Expected: all PASS (same count as before).

- [ ] **Step 8: Commit**

```bash
git add scripts/run_tick_opportunity_mining.py
git commit -m "refactor(mining): derive library lists and filenames from manifest

Removes hardcoded family concatenation, quality-tier assignments,
output filenames, and summary coverage. All driven by
behemoth.governance.stage_contracts.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 4: Refactor WFO reader and output naming to consume manifest

**Files:**
- Modify: `scripts/run_tick_opportunity_monthly_wfo.py:58–110`
- Modify: `scripts/run_tick_opportunity_monthly_wfo.py:326–337` (requested-family library order)
- Modify: `scripts/run_tick_opportunity_monthly_wfo.py:436` (candidate path)
- Modify: `scripts/run_tick_opportunity_monthly_wfo.py:1056–1077,1197–1240` (output naming policy)
- Test: `tests/test_monthly_wfo_threshold_causality.py` (or nearest WFO test)

- [ ] **Step 1: Add manifest import to WFO script**

At the top of `scripts/run_tick_opportunity_monthly_wfo.py` (after `from __future__ import annotations`), add:

```python
from behemoth.governance.stage_contracts import (
    CANDIDATE_FILENAME_TEMPLATE,
    CROSS_SYMBOL_FAMILIES,
    FAMILY_TO_LIBRARY,
    LOCAL_FAMILIES,
    MINING_OUTPUT_LIBRARIES,
    WFO_OUTPUT_FILENAME_TEMPLATES,
)
```

- [ ] **Step 2: Replace hardcoded family sets with manifest imports**

In `scripts/run_tick_opportunity_monthly_wfo.py:58–68`, replace:

```python
SYMBOL_LOCAL_WFO_FAMILIES: set[str] = {
    "oco_first_touch",
    "oco_asymmetric",
    "directional",
    "directional_inverse",
    "directional_run",
    "double_touch",
    "pullback",
    "no_touch",
}
CROSS_SYMBOL_WFO_FAMILIES: set[str] = {"dollar_residual", "dispersion_rank", "lead_lag"}
```

With:

```python
SYMBOL_LOCAL_WFO_FAMILIES: set[str] = LOCAL_FAMILIES
CROSS_SYMBOL_WFO_FAMILIES: set[str] = CROSS_SYMBOL_FAMILIES
```

- [ ] **Step 3: Replace hardcoded FAMILY_TO_LIBRARY_FOR_PARAMS**

In `scripts/run_tick_opportunity_monthly_wfo.py:100–110`, replace:

```python
FAMILY_TO_LIBRARY_FOR_PARAMS: dict[str, str] = {
    "directional": "directional",
    "directional_inverse": "directional",
    "directional_run": "directional",
    "double_touch": "directional",
    "pullback": "directional",
    "oco_first_touch": "oco",
    "oco_asymmetric": "oco_asymmetric",
    "no_touch": "no_touch",
    "dollar_residual": "dollar_residual",
    "dispersion_rank": "dispersion_rank",
    "lead_lag": "lead_lag",
}
```

With:

```python
FAMILY_TO_LIBRARY_FOR_PARAMS: dict[str, str] = FAMILY_TO_LIBRARY
```

- [ ] **Step 4: Replace hardcoded requested-family library order**

In `scripts/run_tick_opportunity_monthly_wfo.py:326–337`, replace:

```python
def _libraries_for_requested_families(families: list[str]) -> list[str]:
    order = [
        "directional",
        "oco",
        "oco_asymmetric",
        "no_touch",
        "dollar_residual",
        "dispersion_rank",
        "lead_lag",
    ]
    requested = {_candidate_library_for_family(family) for family in families}
    return [lib for lib in order if lib in requested]
```

With:

```python
def _libraries_for_requested_families(families: list[str]) -> list[str]:
    requested = {_candidate_library_for_family(family) for family in families}
    return [lib for lib in MINING_OUTPUT_LIBRARIES if lib in requested]
```

- [ ] **Step 5: Derive candidate-file path from manifest**

In `scripts/run_tick_opportunity_monthly_wfo.py:438`, replace:

```python
    c_path = candidate_dir / f"{symbol}_{lib}_candidates.csv"
```

With:

```python
    c_path = candidate_dir / CANDIDATE_FILENAME_TEMPLATE.format(symbol=symbol, library=lib)
```

- [ ] **Step 6: Make WFO output filenames use an explicit scope**

In `scripts/run_tick_opportunity_monthly_wfo.py:1056–1077`, replace `_write_library_outputs` with:

```python
def _write_wfo_outputs(
    *,
    out_dir: Path,
    symbol: str,
    scope: str,
    m: pd.DataFrame,
    t: pd.DataFrame,
    p: pd.DataFrame,
    imp: pd.DataFrame,
) -> list[Path]:
    """Write the four per-scope monthly artifacts, always.

    Empty frames are written too: a missing artifact must mean the stage did
    not run, never that it ran and found nothing. Writing an empty file also
    overwrites any stale artifact from a prior run.
    """
    m_out = out_dir / WFO_OUTPUT_FILENAME_TEMPLATES["metrics"].format(
        symbol=symbol, scope=scope
    )
    t_out = out_dir / WFO_OUTPUT_FILENAME_TEMPLATES["thresholds"].format(
        symbol=symbol, scope=scope
    )
    p_out = out_dir / WFO_OUTPUT_FILENAME_TEMPLATES["predictions"].format(
        symbol=symbol, scope=scope
    )
    imp_out = out_dir / WFO_OUTPUT_FILENAME_TEMPLATES["importance"].format(
        symbol=symbol, scope=scope
    )
    m.to_csv(m_out, index=False)
    t.to_csv(t_out, index=False)
    p.to_parquet(p_out, index=False)
    imp.to_csv(imp_out, index=False)
    for path in (m_out, t_out, p_out, imp_out):
        print(f"wrote: {path}")
    return [m_out, t_out, p_out, imp_out]
```

- [ ] **Step 7: Preserve family-named empty outputs for family-driven WFO configs**

In `scripts/run_tick_opportunity_monthly_wfo.py:1197–1201`, replace:

```python
        families = (
            sorted(ev["family"].dropna().astype(str).unique().tolist())
            if "family" in ev.columns and not ev.empty
            else [lib]
        )
```

With:

```python
        families = (
            sorted(ev["family"].dropna().astype(str).unique().tolist())
            if "family" in ev.columns and not ev.empty
            else list(requested_families or [lib])
        )
```

Then in the write call around line 1239, replace:

```python
            _write_library_outputs(
                out_dir=out_dir, symbol=symbol, lib=family, m=m, t=t, p=p, imp=imp
            )
```

With:

```python
            _write_wfo_outputs(
                out_dir=out_dir, symbol=symbol, scope=family, m=m, t=t, p=p, imp=imp
            )
```

This keeps legacy library-mode output names unchanged (`scope=lib`) while making family-driven empty runs write the same family-scoped filenames as real runs.

- [ ] **Step 8: Add WFO manifest tests**

Append to `tests/test_stage_contracts.py`:

```python
class TestWfoManifestContracts:
    def test_wfo_library_order_comes_from_mining_output_libraries(self):
        from behemoth.governance.stage_contracts import (
            FAMILY_TO_LIBRARY,
            MINING_OUTPUT_LIBRARIES,
        )

        requested = {"directional_run", "oco_first_touch", "lead_lag"}
        libs = {
            FAMILY_TO_LIBRARY[family]
            for family in requested
        }
        assert [lib for lib in MINING_OUTPUT_LIBRARIES if lib in libs] == [
            "directional",
            "oco",
            "lead_lag",
        ]

    def test_wfo_output_templates_are_scope_based(self):
        from behemoth.governance.stage_contracts import WFO_OUTPUT_FILENAME_TEMPLATES

        assert WFO_OUTPUT_FILENAME_TEMPLATES["predictions"].format(
            symbol="EURUSD", scope="directional_run"
        ) == "EURUSD_directional_run_monthly_predictions.parquet"
        assert "{scope}" in WFO_OUTPUT_FILENAME_TEMPLATES["metrics"]
```

- [ ] **Step 9: Run WFO tests to verify no regression**

```bash
uv run pytest -q tests/test_stage_contracts.py tests/test_monthly_wfo_threshold_causality.py tests/test_run_tick_opportunity_monthly_wfo.py
```

Expected: all PASS.

- [ ] **Step 10: Commit**

```bash
git add scripts/run_tick_opportunity_monthly_wfo.py tests/test_stage_contracts.py
git commit -m "refactor(wfo): derive routing and output naming from manifest

Removes hardcoded FAMILY_TO_LIBRARY_FOR_PARAMS, SYMBOL_LOCAL_WFO_FAMILIES,
CROSS_SYMBOL_WFO_FAMILIES, and requested-family library ordering.
Candidate file paths and per-scope output filenames now use manifest templates.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 5: Add contract tests

**Files:**
- Modify: `tests/test_stage_contracts.py`

- [ ] **Step 1: Write tests asserting manifest invariants**

Append to `tests/test_stage_contracts.py`:

```python
class TestManifestInvariants:
    def test_all_manifest_families_are_registered(self):
        from behemoth.governance.stage_contracts import FAMILY_TO_LIBRARY
        from scripts.mining_family import FAMILY_REGISTRY

        manifest_families = set(FAMILY_TO_LIBRARY.keys())
        registry_families = set(FAMILY_REGISTRY.keys())
        assert manifest_families == registry_families, (
            f"manifest families {manifest_families} != registry families {registry_families}"
        )

    def test_quality_tier_library_is_valid(self):
        from behemoth.governance.stage_contracts import QUALITY_TIER_LIBRARY

        valid_tiers = {"directional", "oco", "no_touch"}
        for lib, tier in QUALITY_TIER_LIBRARY.items():
            assert tier in valid_tiers, f"{lib} -> invalid tier {tier}"

    def test_wfo_family_sets_partition_all_families(self):
        from behemoth.governance.stage_contracts import (
            CROSS_SYMBOL_FAMILIES,
            FAMILY_TO_LIBRARY,
            LOCAL_FAMILIES,
        )

        all_families = set(FAMILY_TO_LIBRARY.keys())
        assert LOCAL_FAMILIES | CROSS_SYMBOL_FAMILIES == all_families
        assert not (LOCAL_FAMILIES & CROSS_SYMBOL_FAMILIES)

    def test_mining_output_libraries_match_keys(self):
        from behemoth.governance.stage_contracts import (
            MINING_LIBRARY_FAMILIES,
            MINING_OUTPUT_LIBRARIES,
        )

        assert MINING_OUTPUT_LIBRARIES == list(MINING_LIBRARY_FAMILIES.keys())

    def test_required_columns_include_wfo_consumed_columns(self):
        from behemoth.governance.stage_contracts import CANDIDATE_REQUIRED_COLUMNS

        wfo_consumed = {
            "family",
            "state_id",
            "symbol",
            "horizon",
            "bar_ticks",
            "train_count",
            "mean_gross_pips_train",
        }
        missing = wfo_consumed - set(CANDIDATE_REQUIRED_COLUMNS)
        assert not missing, f"required columns missing: {missing}"
```

- [ ] **Step 2: Run tests**

```bash
uv run pytest tests/test_stage_contracts.py -v
```

Expected: all PASS.

- [ ] **Step 3: Commit**

```bash
git add tests/test_stage_contracts.py
git commit -m "test(governance): add stage_contracts manifest invariants

Asserts manifest families match mining registry, quality-tier values
are valid, WFO family sets partition all families, and required
columns cover downstream consumers.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 6: Emit per-stage manifest JSON alongside mining outputs

**Files:**
- Modify: `scripts/run_tick_opportunity_mining.py:1544-area` (after file writes)
- Modify: `src/behemoth/governance/stage_contracts.py` (add JSON helper)
- Test: `tests/test_tick_opportunity_mining.py` or `tests/test_stage_contracts.py`

This addresses ADR 0004 immediate fix #2: the mining output directory becomes self-describing.

- [ ] **Step 1: Add JSON helper to manifest module**

Append to `src/behemoth/governance/stage_contracts.py`:

```python
def build_mining_output_manifest(*, symbol: str) -> dict[str, Any]:
    """Return a JSON-serialisable manifest describing the Stage 02 outputs."""
    return {
        "stage": "stage02",
        "symbol": symbol,
        "library_families": MINING_LIBRARY_FAMILIES,
        "required_columns": CANDIDATE_REQUIRED_COLUMNS,
        "output_files": {
            lib: CANDIDATE_FILENAME_TEMPLATE.format(symbol=symbol, library=lib)
            for lib in MINING_OUTPUT_LIBRARIES
        },
    }
```

- [ ] **Step 2: Import JSON and the helper in mining script**

At the top of `scripts/run_tick_opportunity_mining.py`, add:

```python
import json
```

At the top of `scripts/run_tick_opportunity_mining.py`, in the existing `behemoth.governance.stage_contracts` import block, add:

```python
    build_mining_output_manifest,
```

- [ ] **Step 3: Write manifest JSON after CSV writes**

In `scripts/run_tick_opportunity_mining.py`, after the `summary.to_csv(s_path, ...)` line and before the `print(f"wrote: {fills_path}"...)` line, insert:

```python
    manifest_path = out_dir / f"{symbol}_stage02_manifest.json"
    manifest = build_mining_output_manifest(symbol=symbol)
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"wrote: {manifest_path}", flush=True)
```

- [ ] **Step 4: Write test for manifest JSON**

Append to `tests/test_tick_opportunity_mining.py`:

```python
def test_mining_emits_stage02_manifest() -> None:
    from behemoth.governance.stage_contracts import MINING_OUTPUT_LIBRARIES

    from behemoth.governance.stage_contracts import build_mining_output_manifest

    manifest = build_mining_output_manifest(symbol="EURUSD")
    assert manifest["stage"] == "stage02"
    assert set(manifest["output_files"].keys()) == set(MINING_OUTPUT_LIBRARIES)
    assert "library_families" in manifest
    assert manifest["library_families"]["directional"] == [
        "directional", "directional_inverse", "directional_run", "double_touch", "pullback"
    ]
```

- [ ] **Step 5: Run tests**

```bash
uv run pytest tests/test_tick_opportunity_mining.py::test_mining_emits_stage02_manifest tests/test_stage_contracts.py -v
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/behemoth/governance/stage_contracts.py scripts/run_tick_opportunity_mining.py tests/test_tick_opportunity_mining.py
git commit -m "feat(mining): emit stage02_manifest.json with library/family expansion

Mines now write a self-describing JSON manifest alongside candidate
CSVs so operators (and LLMs) can discover family/library organisation
without reading source.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 7: Update docs generator to render manifest

**Files:**
- Modify: `scripts/build_process_stage_docs.py:66–68`
- Regenerate: `docs/generated/process/stage02.md`, `docs/generated/process/stage03.md`

- [ ] **Step 1: Import contract renderer in docs script**

At the top of `scripts/build_process_stage_docs.py`, add:

```python
from src.behemoth.governance.stage_contracts import render_stage_io_contract  # noqa: E402
```

- [ ] **Step 2: Append I/O contract markdown for stage02/stage03**

In `scripts/build_process_stage_docs.py:66–68`, replace:

```python
        (args.docs_dir / f"{stage_id}.md").write_text(
            render_stage_capsule_markdown(stage, graph),
            encoding="utf-8",
        )
```

With:

```python
        md = render_stage_capsule_markdown(stage, graph)
        contract_md = render_stage_io_contract(stage_id)
        if contract_md:
            md += "\n\n" + contract_md
        (args.docs_dir / f"{stage_id}.md").write_text(
            md,
            encoding="utf-8",
        )
```

- [ ] **Step 3: Regenerate stage docs**

```bash
uv run python scripts/build_process_stage_docs.py
```

Expected: prints `process stage docs PASS`.

- [ ] **Step 4: Diff regenerated files**

```bash
git diff docs/generated/process/stage02.md docs/generated/process/stage03.md
```

Expected: additions only — new `## Stage 02 I/O Contract` / `## Stage 03 I/O Contract` sections showing input/output patterns and the library→family table. No deletions.

- [ ] **Step 5: Commit**

```bash
git add scripts/build_process_stage_docs.py docs/generated/process/
git commit -m "docs(process): render stage I/O contracts in generated stage capsules

Injects manifest-derived library→family expansion and required columns
into docs/generated/process/stage02.md and stage03.md.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 8: Final verification

- [ ] **Step 1: Full test suite**

```bash
uv run pytest -q
```

Expected: all green, same count as pre-change baseline.

- [ ] **Step 2: Lint**

```bash
uv run ruff check src scripts tests
```

Expected: `All checks passed!`

- [ ] **Step 3: Type check**

```bash
uv run ty check
```

Expected: `All checks passed!`

- [ ] **Step 4: Verify mining script still runs (smoke test)**

```bash
uv run python scripts/run_tick_opportunity_mining.py --help
```

Expected: argparse help, no `ImportError`.

- [ ] **Step 5: Verify WFO script still runs (smoke test)**

```bash
uv run python scripts/run_tick_opportunity_monthly_wfo.py --help
```

Expected: argparse help, no `ImportError`.

- [ ] **Step 6: Commit if any uncommitted changes**

```bash
git status
```

If there are dirty files from fixes, commit them with an appropriate message.

---

## Self-Review

**Spec coverage:**
- [x] Introduce stage-contract manifest (`stage_contracts.py`) — Task 2.
- [x] Manifest declares family↔library↔artifact-name mapping — Task 2.
- [x] Manifest declares required columns — Task 2.
- [x] Producers import manifest (mining writer) — Task 3.
- [x] Consumers import manifest (WFO reader) — Task 4.
- [x] WFO requested-family library order comes from manifest — Task 4.
- [x] WFO output naming policy is explicit for real and legitimately empty outputs — Task 4.
- [x] Test asserts code-matches-manifest — Task 5.
- [x] Docs generator renders manifest — Task 7.
- [x] Immediate fix: `_build_summary` covers all 7 libraries — Task 1.
- [x] Immediate fix: emit per-stage manifest JSON exposing library→family expansion — Task 6.

**Placeholder scan:**
- No "TBD", "TODO", or "implement later".
- No vague "add appropriate error handling".
- Every task has exact file paths, exact code, exact commands.
- No "similar to Task N" shortcuts.

**Type/path consistency:**
- `MINING_LIBRARY_FAMILIES` keys match `MINING_OUTPUT_LIBRARIES` order and count (7).
- `QUALITY_TIER_LIBRARY` keys match `MINING_OUTPUT_LIBRARIES`.
- `FAMILY_TO_LIBRARY` reverse mapping is derived directly from `MINING_LIBRARY_FAMILIES`.
- Filename template `{symbol}_{library}_candidates.csv` matches existing convention.
- WFO output templates use `{scope}` so family-driven empty outputs and real outputs share the same naming policy.
- `_build_summary` accepts `dict[str, pd.DataFrame]` in both definition and all call sites.
- `main()` rebuilds `library_dfs` locally before using it in the manifest-driven write loop.
- Manifest annotations use `Any` from `typing`, not builtin `any`.

---

## Execution Handoff

**Plan complete and saved to `docs/superpowers/plans/2026-05-28-stage-io-contracts.md`.**

**Two execution options:**

**1. Inline Execution (recommended)** — Execute tasks in this session using `superpowers:executing-plans`, with review checkpoints after Tasks 1, 4, and 7. The manifest, mining writer, WFO reader, and generated docs are tightly coupled, so keeping execution in one context reduces drift.

**2. Subagent-Driven** — Dispatch a fresh subagent per task, review between tasks, and require Tasks 2–4 to be integrated together before any PR is opened.

**Which approach?**
