# Microstructure Model Features + Importance Audit Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Promote the 5 numeric microstructure columns from diagnostic-only to CatBoost model features, guard against stale data, and produce a feature importance + orthogonality audit report.

**Architecture:** Three code tasks plus one manual acceptance run. The model feature set is defined by `_feature_cols` in two scripts — extend both. A new audit script reads the WFO's per-month feature-importance CSVs and the ml-ready parquet to write a markdown report. The 5 microstructure columns are kept only if a walk-forward (WFO) run does not regress against the current baseline; that comparison is a manual run gated on the Stage 0 data download finishing.

**Tech Stack:** Python, pandas, CatBoost, pytest.

**Spec:** `docs/superpowers/specs/2026-05-17-microstructure-model-features-design.md`

---

## File Map

- `scripts/run_tick_opportunity_monthly_wfo.py` — add a `_MICROSTRUCTURE_FEATURES` constant; extend `_feature_cols` (`:248-274`); add a `_check_microstructure_columns` guard called inside `_wfo_monthly` (`:406`).
- `scripts/build_tick_opportunity_ml_dataset.py` — extend `_feature_cols` (`:258-274`); shrink `_MICROSTRUCTURE_DIAGNOSTIC_COLS` (`:77-84`) to `session_marker` only so the 5 promoted columns are not carried twice.
- `scripts/build_feature_importance_audit.py` — **new** script: reads `{symbol}_feature_importance_*.csv` + the ml-ready parquet, writes `docs/analysis/eurusd_feature_importance_audit.md`.
- `tests/test_run_tick_opportunity_monthly_wfo.py` — tests for the extended `_feature_cols` and the guard.
- `tests/test_tick_opportunity_ml_dataset.py` — test for the extended `_feature_cols`.
- `tests/test_feature_importance_audit.py` — **new**: test for the audit generator.

The 5 promoted columns, referred to throughout as **the microstructure features**:
`tick_burst_score`, `quote_revision_rate_z`, `directional_persistence_8`,
`signed_flow_24`, `vol_cluster_score`. `session_marker` is **not** one of them
(it stays a diagnostic column — see spec §1).

---

## Task 1: WFO `_feature_cols` includes the microstructure features

**Files:**
- Test: `tests/test_run_tick_opportunity_monthly_wfo.py`
- Modify: `scripts/run_tick_opportunity_monthly_wfo.py:248-274`

**Context:** `_feature_cols` returns the model feature columns present in the
frame — currently 13 market features + 3 structural parameters. It filters
with `if c in d.columns`, so it returns only columns actually present.

- [ ] **Step 1: Write the failing test**

Add to the end of `tests/test_run_tick_opportunity_monthly_wfo.py`:

```python
def test_feature_cols_includes_microstructure_features_when_present():
    from scripts.run_tick_opportunity_monthly_wfo import _feature_cols

    cols = [
        "cost_est_pips", "range_pips", "ret1_pips", "ret_z", "ret_abs_z",
        "vel_cost_units_h1", "vel_abs_cost_units_h1", "spread_z",
        "tick_rate_z", "hour_utc", "hl_first", "hl_first_mean_24",
        "hl_pos_frac_mean_24", "bar_ticks", "horizon", "barrier_pips",
        "tick_burst_score", "quote_revision_rate_z",
        "directional_persistence_8", "signed_flow_24", "vol_cluster_score",
    ]
    df = pd.DataFrame({c: [0.0] for c in cols})
    feats = _feature_cols(df)
    for c in [
        "tick_burst_score", "quote_revision_rate_z",
        "directional_persistence_8", "signed_flow_24", "vol_cluster_score",
    ]:
        assert c in feats


def test_feature_cols_omits_microstructure_features_when_absent():
    from scripts.run_tick_opportunity_monthly_wfo import _feature_cols

    df = pd.DataFrame({c: [0.0] for c in ["ret_z", "bar_ticks", "horizon"]})
    feats = _feature_cols(df)
    assert "tick_burst_score" not in feats
    assert "bar_ticks" in feats
    assert "horizon" in feats
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_run_tick_opportunity_monthly_wfo.py::test_feature_cols_includes_microstructure_features_when_present tests/test_run_tick_opportunity_monthly_wfo.py::test_feature_cols_omits_microstructure_features_when_absent -v`
Expected: the first test FAILS (`tick_burst_score` not in `feats`); the second PASSES.

- [ ] **Step 3: Add the `_MICROSTRUCTURE_FEATURES` constant**

In `scripts/run_tick_opportunity_monthly_wfo.py`, immediately before the
`def _feature_cols(` line (currently `:248`), add:

```python
_MICROSTRUCTURE_FEATURES = [
    "tick_burst_score",
    "quote_revision_rate_z",
    "directional_persistence_8",
    "signed_flow_24",
    "vol_cluster_score",
]
```

- [ ] **Step 4: Extend `_feature_cols`**

In `scripts/run_tick_opportunity_monthly_wfo.py`, the `base` list inside
`_feature_cols` currently ends:

```python
        "hl_pos_frac_mean_24",
        "bar_ticks",
        "horizon",
        "barrier_pips",
    ]
    return [c for c in base if c in d.columns]
```

Change it to append the microstructure features:

```python
        "hl_pos_frac_mean_24",
        "bar_ticks",
        "horizon",
        "barrier_pips",
    ] + _MICROSTRUCTURE_FEATURES
    return [c for c in base if c in d.columns]
```

Also update the docstring count: the line currently reading
`"""Dynamically determine the 16 model feature columns present in the frame.`
becomes
`"""Dynamically determine the model feature columns present in the frame.`
and the `IMPORTANT:` paragraph's `13 market features` stays accurate (the 5
microstructure columns are additional market features); no other docstring
change is needed.

- [ ] **Step 5: Run the tests to verify they pass**

Run: `uv run pytest tests/test_run_tick_opportunity_monthly_wfo.py::test_feature_cols_includes_microstructure_features_when_present tests/test_run_tick_opportunity_monthly_wfo.py::test_feature_cols_omits_microstructure_features_when_absent -v`
Expected: PASS (2 passed).

- [ ] **Step 6: Commit**

```bash
git add scripts/run_tick_opportunity_monthly_wfo.py tests/test_run_tick_opportunity_monthly_wfo.py
git commit -m "feat: WFO model trains on microstructure features"
```

---

## Task 2: WFO guard — fail loud on stale data missing microstructure columns

**Files:**
- Test: `tests/test_run_tick_opportunity_monthly_wfo.py`
- Modify: `scripts/run_tick_opportunity_monthly_wfo.py:406-428`

**Context:** `_feature_cols` filters silently with `if c in d.columns`. On a
pre-Phase-1 (stale) ml-ready dataset, the microstructure columns are absent
and the model silently trains without them — the silent-degradation mode PR
#184 was built to kill. `_wfo_monthly` (`:406`) returns early on an empty
frame (`:425-426`); the guard must run only on a non-empty frame so the
existing `test_wfo_monthly_empty_input_returns_four_values` still passes.

- [ ] **Step 1: Write the failing tests**

Add to the end of `tests/test_run_tick_opportunity_monthly_wfo.py`:

```python
def test_check_microstructure_columns_raises_when_all_absent():
    import pytest
    from scripts.run_tick_opportunity_monthly_wfo import _check_microstructure_columns

    df = pd.DataFrame({"ret_z": [0.1, 0.2], "bar_ticks": [1000, 1000]})
    with pytest.raises(FileNotFoundError, match="rebuild-all"):
        _check_microstructure_columns(df)


def test_check_microstructure_columns_passes_when_all_present():
    from scripts.run_tick_opportunity_monthly_wfo import (
        _MICROSTRUCTURE_FEATURES,
        _check_microstructure_columns,
    )

    df = pd.DataFrame({c: [0.0, 1.0] for c in _MICROSTRUCTURE_FEATURES})
    _check_microstructure_columns(df)  # must not raise
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_run_tick_opportunity_monthly_wfo.py::test_check_microstructure_columns_raises_when_all_absent tests/test_run_tick_opportunity_monthly_wfo.py::test_check_microstructure_columns_passes_when_all_present -v`
Expected: FAIL — `_check_microstructure_columns` is not defined (ImportError).

- [ ] **Step 3: Implement the guard function**

In `scripts/run_tick_opportunity_monthly_wfo.py`, immediately after the
`_feature_cols` function (after its `return` line), add:

```python
def _check_microstructure_columns(d: pd.DataFrame) -> None:
    """Fail loud when Stage 0 velocity data predates the microstructure
    columns; warn (do not crash) on a partial schema split."""
    present = [c for c in _MICROSTRUCTURE_FEATURES if c in d.columns]
    if not present:
        raise FileNotFoundError(
            "no microstructure feature columns found in the ml-ready "
            f"dataset (expected any of {_MICROSTRUCTURE_FEATURES}). "
            "Stage 0 velocity data is stale or predates mining Phase 1. "
            "Run `make rebuild-all MONTHS=...` to rebuild Stage 0 data."
        )
    missing = [c for c in _MICROSTRUCTURE_FEATURES if c not in d.columns]
    if missing:
        print(f"warning: microstructure columns missing from dataset: {missing}")
```

- [ ] **Step 4: Call the guard inside `_wfo_monthly`**

In `scripts/run_tick_opportunity_monthly_wfo.py`, `_wfo_monthly` currently
begins:

```python
    if d.empty:
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame()
    if CatBoostClassifier is None:
        raise RuntimeError("CatBoost is required for monthly WFO runner")
```

Insert the guard call after the `CatBoost is required` check:

```python
    if d.empty:
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame()
    if CatBoostClassifier is None:
        raise RuntimeError("CatBoost is required for monthly WFO runner")
    _check_microstructure_columns(d)
```

- [ ] **Step 5: Run the new tests and the full WFO test file**

Run: `uv run pytest tests/test_run_tick_opportunity_monthly_wfo.py -v`
Expected: all PASS — including `test_wfo_monthly_empty_input_returns_four_values`
(the guard runs after the empty-frame early return, so the empty path is
untouched).

- [ ] **Step 6: Commit**

```bash
git add scripts/run_tick_opportunity_monthly_wfo.py tests/test_run_tick_opportunity_monthly_wfo.py
git commit -m "feat: WFO fails loud when microstructure columns are absent"
```

---

## Task 3: ml-dataset `_feature_cols` includes the microstructure features

**Files:**
- Test: `tests/test_tick_opportunity_ml_dataset.py`
- Modify: `scripts/build_tick_opportunity_ml_dataset.py:77-84`, `:258-274`

**Context:** `build_tick_opportunity_ml_dataset.py` builds the ml-ready
parquet. Its event builders compute the carried columns as
`_feature_cols(df) + [c for c in _MICROSTRUCTURE_DIAGNOSTIC_COLS if c in df.columns]`
(`:287`, `:503`). `_MICROSTRUCTURE_DIAGNOSTIC_COLS` currently lists all 6
microstructure columns. If the 5 numeric ones are added to `_feature_cols`
without being removed from `_MICROSTRUCTURE_DIAGNOSTIC_COLS`, they would be
listed twice. So the 5 move into `_feature_cols`, and
`_MICROSTRUCTURE_DIAGNOSTIC_COLS` shrinks to `session_marker` only.

- [ ] **Step 1: Write the failing test**

Add to the end of `tests/test_tick_opportunity_ml_dataset.py`:

```python
def test_ml_dataset_feature_cols_includes_microstructure_features():
    from scripts.build_tick_opportunity_ml_dataset import (
        _MICROSTRUCTURE_DIAGNOSTIC_COLS,
        _feature_cols,
    )

    micro = [
        "tick_burst_score", "quote_revision_rate_z",
        "directional_persistence_8", "signed_flow_24", "vol_cluster_score",
    ]
    df = pd.DataFrame({c: [0.0] for c in ["ret_z", "spread_z", *micro]})
    feats = _feature_cols(df)
    for c in micro:
        assert c in feats
        assert c not in _MICROSTRUCTURE_DIAGNOSTIC_COLS
    assert _MICROSTRUCTURE_DIAGNOSTIC_COLS == ["session_marker"]
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/test_tick_opportunity_ml_dataset.py::test_ml_dataset_feature_cols_includes_microstructure_features -v`
Expected: FAIL — `tick_burst_score` not in `feats`, and
`_MICROSTRUCTURE_DIAGNOSTIC_COLS` still has 6 entries.

- [ ] **Step 3: Shrink `_MICROSTRUCTURE_DIAGNOSTIC_COLS`**

In `scripts/build_tick_opportunity_ml_dataset.py`, the block currently at
`:76-84` reads:

```python
# Phase 1: microstructure columns preserved for diagnostics; not consumed by model
_MICROSTRUCTURE_DIAGNOSTIC_COLS = [
    "tick_burst_score",
    "quote_revision_rate_z",
    "directional_persistence_8",
    "signed_flow_24",
    "vol_cluster_score",
    "session_marker",
]
```

Replace it with:

```python
# session_marker stays diagnostic-only (categorical; see
# docs/superpowers/specs/2026-05-17-microstructure-model-features-design.md).
# The 5 numeric microstructure columns are now model features (_feature_cols).
_MICROSTRUCTURE_DIAGNOSTIC_COLS = [
    "session_marker",
]
```

- [ ] **Step 4: Extend `_feature_cols`**

In `scripts/build_tick_opportunity_ml_dataset.py`, the `cols` list inside
`_feature_cols` (`:258-274`) currently ends:

```python
        "hl_first",
        "hl_first_mean_24",
        "hl_pos_frac_mean_24",
    ]
    return [c for c in cols if c in df.columns]
```

Change it to append the microstructure features:

```python
        "hl_first",
        "hl_first_mean_24",
        "hl_pos_frac_mean_24",
        "tick_burst_score",
        "quote_revision_rate_z",
        "directional_persistence_8",
        "signed_flow_24",
        "vol_cluster_score",
    ]
    return [c for c in cols if c in df.columns]
```

- [ ] **Step 5: Run the new test and the full ml-dataset test file**

Run: `uv run pytest tests/test_tick_opportunity_ml_dataset.py -q`
Expected: all PASS — `test_build_tick_opportunity_ml_dataset` still passes
because the synthetic velocity frame it builds carries the microstructure
columns, which now appear once (as features) instead of once (as diagnostics).

- [ ] **Step 6: Commit**

```bash
git add scripts/build_tick_opportunity_ml_dataset.py tests/test_tick_opportunity_ml_dataset.py
git commit -m "feat: ml-ready dataset carries microstructure columns as features"
```

---

## Task 4: Feature importance + orthogonality audit generator

**Files:**
- Create: `scripts/build_feature_importance_audit.py`
- Test: `tests/test_feature_importance_audit.py`

**Context:** The WFO writes one `{symbol}_feature_importance_{YYYY-MM}.csv`
per test month into its `model_export_dir` (`run_tick_opportunity_monthly_wfo.py:509`).
Each CSV has a `test_month` column plus one column per feature holding that
month's CatBoost importance. The audit aggregates those into mean importance,
reads the ml-ready parquet for a feature-correlation matrix, and writes a
markdown report. The report is informational only.

- [ ] **Step 1: Write the failing test**

Create `tests/test_feature_importance_audit.py`:

```python
from __future__ import annotations

from pathlib import Path

import pandas as pd

from scripts.build_feature_importance_audit import build_audit


def _write_importance_csv(path: Path, month: str, values: dict[str, float]) -> None:
    row = {"test_month": month, **values}
    pd.DataFrame([row]).to_csv(path, index=False)


def test_build_audit_writes_report_with_three_sections(tmp_path: Path) -> None:
    imp_dir = tmp_path / "models"
    imp_dir.mkdir()
    _write_importance_csv(
        imp_dir / "EURUSD_feature_importance_2025-01.csv",
        "2025-01",
        {"ret_z": 30.0, "hour_utc": 10.0, "hl_first": 0.2, "tick_burst_score": 8.0},
    )
    _write_importance_csv(
        imp_dir / "EURUSD_feature_importance_2025-02.csv",
        "2025-02",
        {"ret_z": 28.0, "hour_utc": 12.0, "hl_first": 0.4, "tick_burst_score": 6.0},
    )

    ml_ready = tmp_path / "eurusd_ml_ready.parquet"
    pd.DataFrame(
        {
            "ret_z": [0.1, 0.2, 0.3, 0.4],
            "hour_utc": [1, 2, 3, 4],
            "hl_first": [0.5, 0.5, 0.5, 0.5],
            "tick_burst_score": [1.0, 2.0, 3.0, 4.0],
            "session_marker": ["LONDON", "NY", "LONDON", "NY"],
        }
    ).to_parquet(ml_ready, index=False)

    out = tmp_path / "audit.md"
    result = build_audit(
        symbol="EURUSD",
        importance_dir=imp_dir,
        ml_ready_path=ml_ready,
        out_path=out,
        dead_weight_floor=1.0,
    )

    assert result == out
    text = out.read_text(encoding="utf-8")
    assert "## Ranked Mean Importance" in text
    assert "## Dead-Weight Flags" in text
    assert "## Orthogonal Expansion Candidates" in text
    # ret_z has the highest mean importance (29.0)
    assert text.index("ret_z") < text.index("tick_burst_score")
    # hl_first mean importance 0.3 < floor 1.0 -> flagged dead weight
    assert "hl_first" in text.split("## Dead-Weight Flags")[1].split("##")[0]


def test_build_audit_raises_when_no_importance_csvs(tmp_path: Path) -> None:
    import pytest

    imp_dir = tmp_path / "models"
    imp_dir.mkdir()
    ml_ready = tmp_path / "eurusd_ml_ready.parquet"
    pd.DataFrame({"ret_z": [0.1, 0.2]}).to_parquet(ml_ready, index=False)

    with pytest.raises(FileNotFoundError, match="feature_importance"):
        build_audit(
            symbol="EURUSD",
            importance_dir=imp_dir,
            ml_ready_path=ml_ready,
            out_path=tmp_path / "audit.md",
            dead_weight_floor=1.0,
        )
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/test_feature_importance_audit.py -v`
Expected: FAIL — `scripts/build_feature_importance_audit.py` does not exist
(ImportError).

- [ ] **Step 3: Create the audit generator**

Create `scripts/build_feature_importance_audit.py`:

```python
"""Feature importance + orthogonality audit for the tick-opportunity model.

Reads the WFO per-month feature-importance CSVs and the ml-ready parquet,
writes a markdown report. Informational only — adding new features is a
separate plan.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd


def _mean_importance(importance_dir: Path, symbol: str) -> pd.Series:
    csvs = sorted(importance_dir.glob(f"{symbol}_feature_importance_*.csv"))
    if not csvs:
        raise FileNotFoundError(
            f"no {symbol}_feature_importance_*.csv files in {importance_dir}. "
            "Run the monthly WFO first (it writes them to model_export_dir)."
        )
    frames = [pd.read_csv(p) for p in csvs]
    merged = pd.concat(frames, ignore_index=True)
    feature_cols = [c for c in merged.columns if c != "test_month"]
    return merged[feature_cols].mean().sort_values(ascending=False)


def _correlation_matrix(ml_ready_path: Path, features: list[str]) -> pd.DataFrame:
    df = pd.read_parquet(ml_ready_path)
    present = [c for c in features if c in df.columns]
    numeric = df[present].apply(pd.to_numeric, errors="coerce")
    return numeric.corr()


def _session_vs_hour(ml_ready_path: Path) -> float | None:
    df = pd.read_parquet(ml_ready_path)
    if "session_marker" not in df.columns or "hour_utc" not in df.columns:
        return None
    codes = pd.factorize(df["session_marker"])[0]
    hour = pd.to_numeric(df["hour_utc"], errors="coerce")
    return float(pd.Series(codes).corr(hour))


def build_audit(
    *,
    symbol: str,
    importance_dir: Path,
    ml_ready_path: Path,
    out_path: Path,
    dead_weight_floor: float,
) -> Path:
    mean_imp = _mean_importance(importance_dir, symbol)
    corr = _correlation_matrix(ml_ready_path, list(mean_imp.index))

    lines: list[str] = [f"# Feature Importance Audit — {symbol}", ""]

    lines.append("## Ranked Mean Importance")
    lines.append("")
    lines.append("| feature | mean_importance |")
    lines.append("| --- | --- |")
    for feat, val in mean_imp.items():
        lines.append(f"| {feat} | {val:.4f} |")
    lines.append("")

    lines.append("## Dead-Weight Flags")
    lines.append("")
    dead = mean_imp[mean_imp < dead_weight_floor]
    if dead.empty:
        lines.append(f"No features below the importance floor ({dead_weight_floor}).")
    else:
        lines.append(f"Features with mean importance below {dead_weight_floor}:")
        lines.append("")
        for feat, val in dead.items():
            lines.append(f"- `{feat}` — {val:.4f}")
    lines.append("")

    lines.append("## Orthogonal Expansion Candidates")
    lines.append("")
    lines.append(
        "New features add the most value when uncorrelated with existing "
        "high-importance features. Highly correlated feature pairs (|corr| > "
        "0.8) below are redundant — expansion should target dimensions not "
        "already covered."
    )
    lines.append("")
    redundant: list[str] = []
    cols = list(corr.columns)
    for i, a in enumerate(cols):
        for b in cols[i + 1 :]:
            c = corr.loc[a, b]
            if pd.notna(c) and abs(c) > 0.8:
                redundant.append(f"- `{a}` ↔ `{b}` — corr {c:.3f}")
    if redundant:
        lines.extend(redundant)
    else:
        lines.append("No redundant feature pairs (|corr| > 0.8) found.")
    lines.append("")
    svh = _session_vs_hour(ml_ready_path)
    if svh is None:
        lines.append(
            "`session_marker` vs `hour_utc`: not computable (column absent)."
        )
    else:
        verdict = "redundant" if abs(svh) > 0.8 else "orthogonal"
        lines.append(
            f"`session_marker` vs `hour_utc`: ordinal-encoded corr {svh:.3f} "
            f"({verdict}). This decides whether `session_marker` is worth "
            "adding as a categorical feature in a follow-up."
        )
    lines.append("")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines), encoding="utf-8")
    return out_path


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--symbol", default="EURUSD")
    p.add_argument("--importance-dir", default="data/models")
    p.add_argument(
        "--ml-ready",
        default="data/analysis/tick_opportunity_mining/ml_ready/EURUSD_ml_ready.parquet",
    )
    p.add_argument("--out", default="docs/analysis/eurusd_feature_importance_audit.md")
    p.add_argument("--dead-weight-floor", type=float, default=1.0)
    args = p.parse_args()

    out = build_audit(
        symbol=args.symbol,
        importance_dir=Path(args.importance_dir),
        ml_ready_path=Path(args.ml_ready),
        out_path=Path(args.out),
        dead_weight_floor=args.dead_weight_floor,
    )
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `uv run pytest tests/test_feature_importance_audit.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add scripts/build_feature_importance_audit.py tests/test_feature_importance_audit.py
git commit -m "feat: feature importance + orthogonality audit generator"
```

---

## Task 5: Acceptance run — baseline vs microstructure WFO (manual, data-gated)

**Files:** none (verification only).

**Context:** WFO is a slow integration run that needs the rebuilt Stage 0
velocity dataset. This task runs **only after** `make rebuild-all MONTHS=...`
has completed and `data/analysis/tick_velocity/` is populated. The 5
microstructure features are kept only if the WFO verdict (monthly PASS rate
and net pips) does not regress against the current baseline.

- [ ] **Step 1: Confirm Stage 0 data is present**

Run: `ls data/analysis/tick_velocity/EURUSD_*tick_velocity.parquet`
Expected: at least one velocity parquet listed. If empty, stop — run
`make rebuild-all MONTHS=...` first.

- [ ] **Step 2: Capture the baseline WFO verdict**

Check out the pre-change `_feature_cols` and run the monthly WFO:

```bash
git stash
make monthly-recert MODEL_MONTH=2026-02
```

Record from the run output / report: the monthly PASS rate and total net
pips. Then restore the changes: `git stash pop`.

(If `git stash` is awkward because work is committed, instead run the WFO
from a checkout of `main` in a separate worktree and record the same numbers.)

- [ ] **Step 3: Run the WFO with microstructure features**

```bash
make monthly-recert MODEL_MONTH=2026-02
```

Record the same two numbers (monthly PASS rate, total net pips).

- [ ] **Step 4: Apply the acceptance gate**

Compare microstructure-run numbers to baseline:

- **No regression** (PASS rate and net pips ≥ baseline): keep all 5 features.
  Proceed to Step 6.
- **Regression:** generate the audit (`uv run python
  scripts/build_feature_importance_audit.py --symbol EURUSD`), read the
  ranked mean importance, and remove the lowest-importance microstructure
  feature from `_MICROSTRUCTURE_FEATURES` in
  `scripts/run_tick_opportunity_monthly_wfo.py` and from `_feature_cols` in
  `scripts/build_tick_opportunity_ml_dataset.py`. Re-run from Step 3.

- [ ] **Step 5: Generate the audit report**

```bash
uv run python scripts/build_feature_importance_audit.py --symbol EURUSD
```

Expected: writes `docs/analysis/eurusd_feature_importance_audit.md`. Review
its three sections — note any dead-weight existing features and the
`session_marker` vs `hour_utc` verdict for the follow-up.

- [ ] **Step 6: Commit the audit report**

```bash
git add docs/analysis/eurusd_feature_importance_audit.md
git commit -m "docs: feature importance audit for microstructure model features"
```

---

## Self-Review

**Spec coverage:**
- Spec §1 (promote 5 numeric microstructure columns; exclude `session_marker`)
  — Task 1 (WFO `_feature_cols`), Task 3 (ml-dataset `_feature_cols` +
  `_MICROSTRUCTURE_DIAGNOSTIC_COLS` shrunk to `session_marker`).
- Spec §2 (WFO-must-not-regress acceptance gate; drop lowest-importance on
  regression) — Task 5.
- Spec §3 (importance + orthogonality audit report, three sections,
  informational only) — Task 4 (generator), Task 5 Step 5 (run it).
- Spec "Error Handling" (raise when none present; warn when subset missing) —
  Task 2.
- Spec "Testing" (pure-function unit tests for both `_feature_cols`; guard
  unit test; WFO verified by the manual baseline-vs-new run) — Tasks 1-4
  (pytest), Task 5 (manual).

**Placeholder scan:** No TBDs. Every code step shows complete code; every
command step shows the exact command and expected output.

**Type consistency:** `_MICROSTRUCTURE_FEATURES` is a `list[str]` defined once
in `run_tick_opportunity_monthly_wfo.py` and referenced by
`_check_microstructure_columns` and the tests. `_check_microstructure_columns`
takes a `pd.DataFrame`, returns `None`, raises `FileNotFoundError` — matching
the test's `pytest.raises`. `build_audit` is keyword-only with
`symbol: str, importance_dir: Path, ml_ready_path: Path, out_path: Path,
dead_weight_floor: float`, returns `Path` — matching both its test calls.
`_MICROSTRUCTURE_DIAGNOSTIC_COLS` is `["session_marker"]` after Task 3,
matching the Task 3 test assertion.
