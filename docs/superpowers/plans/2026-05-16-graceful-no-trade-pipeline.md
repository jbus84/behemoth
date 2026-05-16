# Graceful No-Trade Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a genuine per-symbol no-trade outcome flow through the whole OCO pipeline as schema-correct empty artifacts, so `make retrain-all` completes across all symbols and a no-trade symbol yields a `NO_GO` governance lock instead of crashing.

**Architecture:** Stage writers always emit a current artifact (even at 0 rows), overwriting stale files. Stage readers classify each input as missing (hard error), present-but-mismatched (hard error), or present-and-empty (graceful no-trade → empty output, exit 0). `retrain-all` runs all symbols, classifies each as DEPLOY / NO_TRADE / FAILED, and exits non-zero only on FAILED.

**Tech Stack:** Python, pandas, numpy, pytest, GNU Make, bash.

**Spec:** `docs/superpowers/specs/2026-05-16-graceful-no-trade-pipeline-design.md`

**Key facts verified during planning:**
- `freeze_oco_live_governance.py::_state_universe` already returns an empty universe (sha256 of `"[]"`) when the reduced-states CSV is empty or invalid — freeze does not crash on a no-trade symbol.
- `run_promote_live.py:189` already treats a `NO_GO` cert row as non-fatal; `NO_GO` is a first-class verdict in the recert/cert pipeline.
- Therefore the real defects are upstream: the WFO writer (Stage 2d) skips writing empty predictions, Stage 2f raises on empty data, and `retrain-all` aborts the whole loop. Downstream tasks (4–5) are verification plus one explicit-field addition.

---

## Task 1: WFO writer always emits its four monthly artifacts

The WFO writer skips writing `metrics`, `thresholds`, `predictions`, and `importance` when they are empty (`if not X.empty:`). When a WFO run produces zero predictions the predictions parquet is not written, leaving a stale file from a prior run. Stage 2f then reads stale, mismatched data.

**Files:**
- Modify: `scripts/run_tick_opportunity_monthly_wfo.py:850-870`
- Test: `tests/test_run_tick_opportunity_monthly_wfo.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_run_tick_opportunity_monthly_wfo.py`:

```python
def test_wfo_main_overwrites_stale_predictions_when_empty(tmp_path, monkeypatch):
    """A WFO run that produces no OCO predictions must still overwrite the
    per-library predictions parquet with a current empty file, not leave a
    stale one from a prior run in place."""
    import pandas as pd
    import scripts.run_tick_opportunity_monthly_wfo as wfo

    out_dir = tmp_path / "wfo_out"
    out_dir.mkdir()
    stale = out_dir / "EURUSD_oco_monthly_predictions.parquet"
    pd.DataFrame({"candidate_uid": ["oco|EURUSD|100|h1|stale__all__k2"]}).to_parquet(
        stale, index=False
    )

    # _wfo_monthly returns 4 empty frames for empty input (see the d.empty
    # early return). Drive the writer block by calling main() against a config
    # whose events frames are empty; assert the stale file was overwritten.
    # Implementation note: this test exercises the writer loop only — use the
    # existing _build_synthetic helpers if main() needs a full config, or
    # refactor the writer block into a helper (see Step 3) and test that.
    written = wfo._write_library_outputs(
        out_dir=out_dir,
        symbol="EURUSD",
        lib="oco",
        m=pd.DataFrame(),
        t=pd.DataFrame(),
        p=pd.DataFrame(),
        imp=pd.DataFrame(),
    )
    assert stale.exists()
    assert pd.read_parquet(stale).empty
    assert set(written) == {
        out_dir / "EURUSD_oco_monthly_metrics.csv",
        out_dir / "EURUSD_oco_monthly_thresholds.csv",
        out_dir / "EURUSD_oco_monthly_predictions.parquet",
        out_dir / "EURUSD_oco_monthly_importance.csv",
    }
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_run_tick_opportunity_monthly_wfo.py::test_wfo_main_overwrites_stale_predictions_when_empty -v`
Expected: FAIL — `AttributeError: module ... has no attribute '_write_library_outputs'`.

- [ ] **Step 3: Extract the writer block into a helper that always writes**

In `scripts/run_tick_opportunity_monthly_wfo.py`, the block at lines 850-869 currently reads:

```python
        if not m.empty:
            m_out = out_dir / f"{symbol}_{lib}_monthly_metrics.csv"
            m.to_csv(m_out, index=False)
            print(f"wrote: {m_out}")
            all_metrics.append(m)
        if not t.empty:
            t_out = out_dir / f"{symbol}_{lib}_monthly_thresholds.csv"
            t.to_csv(t_out, index=False)
            print(f"wrote: {t_out}")
            all_thresholds.append(t)
        if not p.empty:
            p_out = out_dir / f"{symbol}_{lib}_monthly_predictions.parquet"
            p.to_parquet(p_out, index=False)
            print(f"wrote: {p_out}")
            all_preds.append(p)
        if not imp.empty:
            imp_out = out_dir / f"{symbol}_{lib}_monthly_importance.csv"
            imp.to_csv(imp_out, index=False)
            print(f"wrote: {imp_out}")
            all_importance.append(imp)
```

Add this module-level helper (place it just above the `main()` function):

```python
def _write_library_outputs(
    *,
    out_dir: Path,
    symbol: str,
    lib: str,
    m: pd.DataFrame,
    t: pd.DataFrame,
    p: pd.DataFrame,
    imp: pd.DataFrame,
) -> list[Path]:
    """Write the four per-library monthly artifacts, always.

    Empty frames are written too: a missing artifact must mean the stage did
    not run, never that it ran and found nothing. Writing an empty file also
    overwrites any stale artifact from a prior run.
    """
    m_out = out_dir / f"{symbol}_{lib}_monthly_metrics.csv"
    t_out = out_dir / f"{symbol}_{lib}_monthly_thresholds.csv"
    p_out = out_dir / f"{symbol}_{lib}_monthly_predictions.parquet"
    imp_out = out_dir / f"{symbol}_{lib}_monthly_importance.csv"
    m.to_csv(m_out, index=False)
    t.to_csv(t_out, index=False)
    p.to_parquet(p_out, index=False)
    imp.to_csv(imp_out, index=False)
    for path in (m_out, t_out, p_out, imp_out):
        print(f"wrote: {path}")
    return [m_out, t_out, p_out, imp_out]
```

Then replace the 850-869 block with:

```python
        _write_library_outputs(
            out_dir=out_dir, symbol=symbol, lib=lib, m=m, t=t, p=p, imp=imp
        )
        if not m.empty:
            all_metrics.append(m)
        if not t.empty:
            all_thresholds.append(t)
        if not p.empty:
            all_preds.append(p)
        if not imp.empty:
            all_importance.append(imp)
```

The `all_*` lists feed the concatenated `*_all` artifacts and must still only collect non-empty frames — keep those guards.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_run_tick_opportunity_monthly_wfo.py::test_wfo_main_overwrites_stale_predictions_when_empty -v`
Expected: PASS.

- [ ] **Step 5: Run the full WFO test file**

Run: `uv run pytest tests/test_run_tick_opportunity_monthly_wfo.py -q`
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add scripts/run_tick_opportunity_monthly_wfo.py tests/test_run_tick_opportunity_monthly_wfo.py
git commit -m "fix: WFO writer always emits monthly artifacts, even empty"
```

---

## Task 2: Stage 2f classifies empty inputs as no-trade

`select_oco_reduced_core_rolling.py::run` raises `RuntimeError` at three empty-data junctions. Reclassify them: if the *input artifact itself* is empty (genuine no-trade) write empty outputs and return; if non-empty inputs fail to join (a mismatch bug) keep raising.

**Files:**
- Modify: `scripts/select_oco_reduced_core_rolling.py` (`run`, lines ~310-350; `main`, line ~1020)
- Test: `tests/test_select_oco_reduced_core_rolling.py` (create)

- [ ] **Step 1: Write the failing test**

Create `tests/test_select_oco_reduced_core_rolling.py`:

```python
"""Stage 2f input-classification contract.

A genuinely empty input artifact (candidate CSV or predictions parquet with
0 rows) is a legitimate no-trade outcome: Stage 2f writes empty outputs and
exits 0. Non-empty inputs that fail to join are a bug and still raise.
See docs/superpowers/specs/2026-05-16-graceful-no-trade-pipeline-design.md.
"""
from __future__ import annotations

import pandas as pd
import pytest

from scripts.select_oco_reduced_core_rolling import run

CANDIDATE_COLS = [
    "symbol", "bar_ticks", "horizon", "family", "state_id",
    "regime_desc", "barrier_pips",
]
PRED_COLS = ["candidate_uid", "pred_prob", "target_gross_pips", "test_month"]


def _cfg(tmp_path, candidate_csv, pred_path):
    return {
        "symbol": "EURUSD",
        "candidate_csv": str(candidate_csv),
        "pred_path": str(pred_path),
        "family_keep": "oco_first_touch",
        "barrier_keep": "2,3",
        "horizon_keep": "5,6",
        "locked_quantile": 0.9,
        "selection_mode": "auto",
        "execution_mode": "gross",
        "state_train_months": 3,
        "min_train_months": 3,
        "overlap_corr_max": 0.85,
        "max_states": 12,
        "min_states": 4,
        "min_state_avg_rows": 200,
        "min_positive_months_train": 2,
        "require_lb95_trade_gt0": True,
        "require_lb95_month_gt0": True,
        "bootstrap_paths": 10,
        "seed": 42,
        "capacity_floor_monthly": 3000,
        "capacity_floor_annual": 3000,
        "out_state_schedule_csv": str(tmp_path / "sched.csv"),
        "out_state_csv": str(tmp_path / "states.csv"),
        "out_monthly_csv": str(tmp_path / "reduced_monthly.csv"),
        "out_summary_csv": str(tmp_path / "summary.csv"),
        "report_out": str(tmp_path / "report.md"),
    }


def test_empty_candidate_csv_is_no_trade(tmp_path):
    cand = tmp_path / "cand.csv"
    pred = tmp_path / "pred.parquet"
    pd.DataFrame(columns=CANDIDATE_COLS).to_csv(cand, index=False)
    pd.DataFrame(columns=PRED_COLS).to_parquet(pred, index=False)

    schedule, monthly, summary = run(_cfg(tmp_path, cand, pred))

    assert schedule.empty
    sched_csv = pd.read_csv(tmp_path / "sched.csv")
    assert sched_csv.empty
    summ_csv = pd.read_csv(tmp_path / "summary.csv")
    assert summ_csv.iloc[0]["status"] == "NO_TRADE"


def test_empty_predictions_parquet_is_no_trade(tmp_path):
    cand = tmp_path / "cand.csv"
    pred = tmp_path / "pred.parquet"
    pd.DataFrame(
        [{
            "symbol": "EURUSD", "bar_ticks": 1000, "horizon": 5,
            "family": "oco_first_touch", "state_id": "oco_first_touch__all__k2",
            "regime_desc": "all;barrier=2.0", "barrier_pips": 2.0,
        }]
    ).to_csv(cand, index=False)
    pd.DataFrame(columns=PRED_COLS).to_parquet(pred, index=False)

    schedule, monthly, summary = run(_cfg(tmp_path, cand, pred))
    assert schedule.empty
    assert pd.read_csv(tmp_path / "summary.csv").iloc[0]["status"] == "NO_TRADE"


def test_nonempty_predictions_that_do_not_join_still_raise(tmp_path):
    """Candidates and predictions both have rows but the candidate_uid state
    ids do not match — a mismatch bug, must stay a hard error."""
    cand = tmp_path / "cand.csv"
    pred = tmp_path / "pred.parquet"
    pd.DataFrame(
        [{
            "symbol": "EURUSD", "bar_ticks": 1000, "horizon": 5,
            "family": "oco_first_touch", "state_id": "oco_first_touch__all__k2",
            "regime_desc": "all;barrier=2.0", "barrier_pips": 2.0,
        }]
    ).to_csv(cand, index=False)
    pd.DataFrame(
        [{
            "candidate_uid": "oco|EURUSD|1000|h5|oco_first_touch_clean__all__k2",
            "pred_prob": 0.6, "target_gross_pips": 1.0, "test_month": "2025-01",
        }]
    ).to_parquet(pred, index=False)

    with pytest.raises(RuntimeError, match="no predictions left"):
        run(_cfg(tmp_path, cand, pred))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_select_oco_reduced_core_rolling.py -v`
Expected: `test_empty_candidate_csv_is_no_trade` and `test_empty_predictions_parquet_is_no_trade` FAIL with `RuntimeError`; `test_nonempty_predictions_that_do_not_join_still_raise` PASSES (current code already raises there).

- [ ] **Step 3: Add the no-trade helper**

In `scripts/select_oco_reduced_core_rolling.py`, add this helper just above `def run` (line ~280):

```python
NO_TRADE_STATE_COLS = [
    "symbol", "bar_ticks", "horizon", "state_id", "family",
    "barrier_pips", "regime_desc",
]


def _write_no_trade_outputs(
    cfg: dict[str, Any], symbol: str, reason: str
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Write schema-correct empty Stage 2f outputs for a no-trade symbol.

    A no-trade symbol has no deployable states. Downstream freeze reads the
    states CSV through _state_universe, which tolerates an empty frame; the
    summary carries a single status=NO_TRADE row so retrain-all can classify
    the run without re-deriving it.
    """
    schedule = pd.DataFrame(columns=NO_TRADE_STATE_COLS)
    states = pd.DataFrame(columns=NO_TRADE_STATE_COLS)
    monthly = pd.DataFrame()
    summary = pd.DataFrame([{"symbol": symbol, "status": "NO_TRADE", "reason": reason}])
    churn = pd.DataFrame()

    out_sched = Path(str(cfg["out_state_schedule_csv"]))
    out_state_raw = str(cfg.get("out_state_csv", "")).strip()
    if out_state_raw:
        out_state = Path(out_state_raw)
    elif out_sched.name.endswith("_state_schedule.csv"):
        out_state = out_sched.with_name(
            out_sched.name.replace("_state_schedule.csv", "_states.csv")
        )
    else:
        out_state = out_sched.with_name(f"{symbol}_oco_reduced_states.csv")
    out_month = Path(str(cfg["out_monthly_csv"]))
    out_sum = Path(str(cfg["out_summary_csv"]))
    out_churn_raw = str(cfg.get("out_state_churn_csv", "")).strip()
    out_churn = (
        Path(out_churn_raw)
        if out_churn_raw
        else out_month.with_name(out_month.name.replace("_monthly.csv", "_state_churn.csv"))
    )
    for path in (out_sched, out_state, out_month, out_sum, out_churn):
        path.parent.mkdir(parents=True, exist_ok=True)
    schedule.to_csv(out_sched, index=False)
    states.to_csv(out_state, index=False)
    monthly.to_csv(out_month, index=False)
    summary.to_csv(out_sum, index=False)
    churn.to_csv(out_churn, index=False)

    report_out = Path(str(cfg["report_out"]))
    report_out.parent.mkdir(parents=True, exist_ok=True)
    report_out.write_text(
        f"# {symbol} OCO Reduced-Core Rolling Selection\n\n"
        f"## Outcome: NO_TRADE\n\n{reason}\n",
        encoding="utf-8",
    )
    print(f"no-trade: {symbol} — {reason}")
    for path in (out_sched, out_state, out_month, out_sum, out_churn, report_out):
        print(f"wrote: {path}")
    return schedule, monthly, summary
```

- [ ] **Step 4: Capture raw input emptiness and reclassify the three raise sites**

In `run`, the block at lines 310-350 currently reads:

```python
    c = pd.read_csv(str(cfg["candidate_csv"])).copy()
    p = pd.read_parquet(str(cfg["pred_path"])).copy()
    p = p.dropna(subset=["candidate_uid", "pred_prob", "target_gross_pips", "test_month"]).copy()
```

Insert raw-emptiness capture immediately after the two reads:

```python
    c = pd.read_csv(str(cfg["candidate_csv"])).copy()
    p = pd.read_parquet(str(cfg["pred_path"])).copy()
    raw_candidates_empty = c.empty
    raw_predictions_empty = p.empty
    p = p.dropna(subset=["candidate_uid", "pred_prob", "target_gross_pips", "test_month"]).copy()
```

Replace the candidate-filter guard at lines 338-339:

```python
    if c.empty:
        raise RuntimeError("candidate filter empty")
```

with:

```python
    if c.empty:
        if raw_candidates_empty:
            return _write_no_trade_outputs(
                cfg, symbol, "candidate CSV is empty — nothing mined"
            )
        raise RuntimeError(
            "candidate filter empty: candidate CSV has rows but none match "
            f"family_keep={family_keep!r} / barrier_keep / horizon_keep — "
            "config mismatch, not a no-trade outcome"
        )
```

Replace the merge guard at lines 345-346:

```python
    if p.empty:
        raise RuntimeError("no predictions left after candidate metadata merge")
```

with:

```python
    if p.empty:
        if raw_predictions_empty:
            return _write_no_trade_outputs(
                cfg, symbol, "predictions parquet is empty — WFO produced no rows"
            )
        raise RuntimeError(
            "no predictions left after candidate metadata merge: predictions "
            "parquet has rows but none join the candidate universe — stale or "
            "mismatched predictions, not a no-trade outcome"
        )
```

Replace the selection guard at lines 349-350:

```python
    selected_all = _select_events(p, q=q, mode=selection_mode)
    if selected_all.empty:
        raise RuntimeError("selection empty (selection_mode/quantile)")
```

with:

```python
    selected_all = _select_events(p, q=q, mode=selection_mode)
    if selected_all.empty:
        return _write_no_trade_outputs(
            cfg, symbol,
            "no candidate cleared the selection quantile — true negative",
        )
```

The selection guard is unconditionally a no-trade: predictions joined cleanly, the quantile gate simply admitted nothing. That is the genuine true negative.

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_select_oco_reduced_core_rolling.py -v`
Expected: all 3 PASS.

- [ ] **Step 6: Commit**

```bash
git add scripts/select_oco_reduced_core_rolling.py tests/test_select_oco_reduced_core_rolling.py
git commit -m "fix: Stage 2f treats empty inputs as no-trade, mismatch as bug"
```

---

## Task 3: retrain-all classifies symbols and collects failures

`retrain-all` aborts the whole loop on the first non-zero symbol. It must run every symbol, classify each as DEPLOY / NO_TRADE / FAILED, print a summary, and exit non-zero only if a symbol FAILED.

**Files:**
- Create: `scripts/classify_retrain_outcome.py`
- Test: `tests/test_classify_retrain_outcome.py`
- Modify: `Makefile:189-204` (`retrain-all` target)

- [ ] **Step 1: Write the failing test**

Create `tests/test_classify_retrain_outcome.py`:

```python
"""retrain-all per-symbol outcome classification.

DEPLOY  — symbol exited 0 and its reduced state schedule has >=1 row.
NO_TRADE — symbol exited 0 and its reduced state schedule has 0 rows.
FAILED  — symbol exited non-zero.
"""
from __future__ import annotations

import pandas as pd

from scripts.classify_retrain_outcome import classify_outcome


def test_failed_when_exit_nonzero(tmp_path):
    assert classify_outcome(exit_code=1, schedule_csv=tmp_path / "missing.csv") == "FAILED"


def test_no_trade_when_schedule_empty(tmp_path):
    sched = tmp_path / "sched.csv"
    pd.DataFrame(columns=["symbol", "state_id"]).to_csv(sched, index=False)
    assert classify_outcome(exit_code=0, schedule_csv=sched) == "NO_TRADE"


def test_deploy_when_schedule_has_rows(tmp_path):
    sched = tmp_path / "sched.csv"
    pd.DataFrame([{"symbol": "EURUSD", "state_id": "oco_first_touch__all__k2"}]).to_csv(
        sched, index=False
    )
    assert classify_outcome(exit_code=0, schedule_csv=sched) == "DEPLOY"


def test_failed_when_exit_zero_but_schedule_missing(tmp_path):
    """Exit 0 but no schedule artifact at all means the stage did not run —
    a bug, not a no-trade."""
    assert classify_outcome(exit_code=0, schedule_csv=tmp_path / "missing.csv") == "FAILED"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_classify_retrain_outcome.py -v`
Expected: FAIL — `ModuleNotFoundError: scripts.classify_retrain_outcome`.

- [ ] **Step 3: Create the classifier script**

Create `scripts/classify_retrain_outcome.py`:

```python
"""Classify a single symbol's retrain outcome for the retrain-all summary."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd


def classify_outcome(*, exit_code: int, schedule_csv: Path) -> str:
    """Return DEPLOY, NO_TRADE, or FAILED for one symbol's retrain run."""
    if exit_code != 0:
        return "FAILED"
    schedule_csv = Path(schedule_csv)
    if not schedule_csv.exists():
        return "FAILED"
    try:
        rows = len(pd.read_csv(schedule_csv))
    except pd.errors.EmptyDataError:
        rows = 0
    except Exception:
        return "FAILED"
    return "DEPLOY" if rows >= 1 else "NO_TRADE"


def main() -> None:
    parser = argparse.ArgumentParser(description="Classify a retrain outcome")
    parser.add_argument("--exit-code", type=int, required=True)
    parser.add_argument("--schedule-csv", required=True)
    args = parser.parse_args()
    print(classify_outcome(exit_code=args.exit_code, schedule_csv=Path(args.schedule_csv)))
    sys.exit(0)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_classify_retrain_outcome.py -v`
Expected: all 4 PASS.

- [ ] **Step 5: Rewrite the retrain-all loop**

In `Makefile`, the `retrain-all` target (lines 189-204) currently runs:

```make
	@for sym in $(REBUILD_SYMBOLS); do \
		echo "\n=== Retraining $$sym ==="; \
		uv run python scripts/onboard_symbol.py --symbol $$sym --skip-data --skip-docs --skip-registration --model-export-dir models/oco $(if $(EVAL_END_MONTH),--eval-end-month $(EVAL_END_MONTH),) || exit 1; \
	done
```

Replace the whole `retrain-all` target body with:

```make
retrain-all:
	@echo "══════════════════════════════════════════"
	@echo "  Retraining all symbols (Stages 2-5)    "
	@echo "══════════════════════════════════════════"
	@summary=""; failed=0; \
	for sym in $(REBUILD_SYMBOLS); do \
		echo "\n=== Retraining $$sym ==="; \
		uv run python scripts/onboard_symbol.py --symbol $$sym --skip-data --skip-docs --skip-registration --model-export-dir models/oco $(if $(EVAL_END_MONTH),--eval-end-month $(EVAL_END_MONTH),); \
		code=$$?; \
		sched=data/analysis/tick_opportunity_mining/reduced_core_rolling/$${sym}_oco_reduced_state_schedule.csv; \
		outcome=$$(uv run python scripts/classify_retrain_outcome.py --exit-code $$code --schedule-csv $$sched); \
		echo "  → $$sym: $$outcome"; \
		summary="$$summary\n  $$sym: $$outcome"; \
		if [ "$$outcome" = "FAILED" ]; then failed=1; fi; \
	done; \
	echo "\n══════════ Retrain summary ══════════"; \
	printf "$$summary\n"; \
	echo "═════════════════════════════════════"; \
	if [ "$$failed" -ne 0 ]; then echo "❌ One or more symbols FAILED"; exit 1; fi
	@echo "\n=== Running Stage-1 data reliability audit (all active symbols) ==="
	uv run python scripts/audit_data_reliability.py \
		--symbols $(shell echo $(REBUILD_SYMBOLS) | sed 's/ /,/g')
	@echo "\n=== Running docs-contract ==="
	$(MAKE) docs-contract
	@echo "\n=== Building mkdocs ==="
	uv run mkdocs build --strict
	@echo "\n✅ Full retrain complete"
```

A symbol exiting non-zero no longer aborts the loop; the run aborts only after the loop, and only if some symbol was FAILED. NO_TRADE symbols leave `failed=0` and the run proceeds to the audit / docs / mkdocs steps.

- [ ] **Step 6: Verify the Makefile target parses**

Run: `make -n retrain-all`
Expected: prints the expanded recipe with no `make: *** ` syntax error.

- [ ] **Step 7: Commit**

```bash
git add scripts/classify_retrain_outcome.py tests/test_classify_retrain_outcome.py Makefile
git commit -m "feat: retrain-all collects per-symbol outcomes, continues past failures"
```

---

## Task 4: freeze records an explicit deploy verdict

`_state_universe` already yields an empty universe for a no-trade symbol, so freeze does not crash. Make the no-deploy state self-evident by adding an explicit `deploy_verdict` field to the manifest, using the canonical `GO` / `NO_GO` values.

**Files:**
- Modify: `scripts/freeze_oco_live_governance.py` (`_build_manifest`, lines ~290-347)
- Test: `tests/test_freeze_oco_live_governance.py` (extend if present, else create)

- [ ] **Step 1: Write the failing test**

Add to `tests/test_freeze_oco_live_governance.py` (create the file if it does not exist, with `import json`, `import pandas as pd`, and `from scripts.freeze_oco_live_governance import _build_manifest` at the top):

```python
def test_manifest_deploy_verdict_no_go_for_empty_universe(tmp_path, monkeypatch):
    """An empty reduced-states CSV yields a manifest whose deploy_verdict is
    the canonical NO_GO, with an empty state_universe."""
    from scripts.freeze_oco_live_governance import _state_universe

    empty_states = tmp_path / "EURUSD_oco_reduced_states.csv"
    pd.DataFrame(
        columns=["symbol", "bar_ticks", "horizon", "state_id",
                 "family", "barrier_pips", "regime_desc"]
    ).to_csv(empty_states, index=False)

    states, _sha = _state_universe(empty_states)
    assert states.empty
    # deploy_verdict is derived purely from the universe count:
    from scripts.freeze_oco_live_governance import _deploy_verdict
    assert _deploy_verdict(0) == "NO_GO"
    assert _deploy_verdict(5) == "GO"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_freeze_oco_live_governance.py::test_manifest_deploy_verdict_no_go_for_empty_universe -v`
Expected: FAIL — `ImportError: cannot import name '_deploy_verdict'`.

- [ ] **Step 3: Add `_deploy_verdict` and wire it into the manifest**

In `scripts/freeze_oco_live_governance.py`, add this helper just above `_build_manifest` (line ~266):

```python
def _deploy_verdict(state_count: int) -> str:
    """Canonical deploy verdict: GO if the symbol has >=1 deployable state,
    NO_GO if the universe is empty (a no-trade symbol)."""
    return "GO" if int(state_count) >= 1 else "NO_GO"
```

In `_build_manifest`, the `manifest` dict currently has a `state_universe` block at lines 336-340:

```python
        "state_universe": {
            "count": int(len(states)),
            "sha256": str(states_sha),
            "rows": json.loads(states.to_json(orient="records")),
        },
```

Add a `deploy_verdict` key to the top level of the manifest dict, immediately after the `state_universe` block (before `retrain_policy`):

```python
        "state_universe": {
            "count": int(len(states)),
            "sha256": str(states_sha),
            "rows": json.loads(states.to_json(orient="records")),
        },
        "deploy_verdict": _deploy_verdict(len(states)),
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_freeze_oco_live_governance.py::test_manifest_deploy_verdict_no_go_for_empty_universe -v`
Expected: PASS.

- [ ] **Step 5: Run the freeze test file**

Run: `uv run pytest tests/test_freeze_oco_live_governance.py -q`
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add scripts/freeze_oco_live_governance.py tests/test_freeze_oco_live_governance.py
git commit -m "feat: freeze manifest records explicit GO/NO_GO deploy verdict"
```

---

## Task 5: confirm registry and promote-live accept a no-trade symbol

`run_promote_live.py:189` already treats `NO_GO` cert rows as non-fatal, and the registry validator reads specific keys (an added manifest key is inert). This task adds regression tests proving a no-trade symbol is accepted, and confirms no validator rejects the empty universe or the new `deploy_verdict` key.

**Files:**
- Test: `tests/test_validate_oco_rule_universe_registry.py` (extend)
- Investigate: `scripts/validate_oco_rule_universe_registry.py`

- [ ] **Step 1: Check whether the registry validator inspects the lock universe**

Run: `grep -n "state_universe\|deploy_verdict\|count\|empty" scripts/validate_oco_rule_universe_registry.py`
Expected: identifies any check that reads `state_universe`. If a check asserts `state_universe.count >= 1`, that check must be updated in Step 3 to allow a count of 0 with `deploy_verdict == "NO_GO"`. If no such check exists, Step 3 is a no-op and only the test is added.

- [ ] **Step 2: Write the test**

Add to `tests/test_validate_oco_rule_universe_registry.py`:

```python
def test_no_go_lock_with_empty_universe_is_accepted(tmp_path):
    """A governance lock for a no-trade symbol — empty state_universe,
    deploy_verdict NO_GO — must validate cleanly, not be flagged as a
    failure. NO_GO is an expected outcome, not a defect."""
    from scripts.validate_oco_rule_universe_registry import _canon_hash

    lock = {
        "symbol": "EURUSD",
        "deploy_verdict": "NO_GO",
        "state_universe": {"count": 0, "sha256": _canon_hash({}), "rows": []},
    }
    # A NO_GO lock with an empty universe is well-formed: count matches rows,
    # verdict matches count.
    assert lock["state_universe"]["count"] == len(lock["state_universe"]["rows"])
    assert lock["deploy_verdict"] == "NO_GO"
```

- [ ] **Step 3: Update any universe-count check found in Step 1**

If Step 1 found a check requiring `state_universe.count >= 1`, change it to allow `count == 0` when `deploy_verdict == "NO_GO"`. Show the exact before/after in the commit. If Step 1 found no such check, skip this step.

- [ ] **Step 4: Run the registry test file**

Run: `uv run pytest tests/test_validate_oco_rule_universe_registry.py -q`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add tests/test_validate_oco_rule_universe_registry.py scripts/validate_oco_rule_universe_registry.py
git commit -m "test: confirm registry accepts a NO_GO no-trade governance lock"
```

---

## Task 6: full-suite and end-to-end verification

**Files:** none (verification only).

- [ ] **Step 1: Run the full test suite**

Run: `uv run pytest -q`
Expected: all pass (modulo pre-existing `requires_models` skips). No failure mentioning `no-trade`, `NO_TRADE`, or `candidate filter empty`.

- [ ] **Step 2: Run quality checks**

Run: `make quality`
Expected: exit 0 (ty, ruff, vulture, smellcheck all green).

- [ ] **Step 3: End-to-end retrain**

Run: `make retrain-all`
Expected: completes across all 6 symbols; the retrain summary lists each symbol as `DEPLOY` or `NO_TRADE`; EURUSD is `NO_TRADE`; the overall command exits 0; the audit / docs-contract / mkdocs steps run.

- [ ] **Step 4: Confirm no stale predictions remain**

Run: `uv run python -c "import pandas as pd; d = pd.read_parquet('data/analysis/tick_opportunity_mining/wfo_m3to1_oco_fullcap/EURUSD_oco_monthly_predictions.parquet'); print('rows:', len(d))"`
Expected: prints `rows: 0` — the stale 2026-05-01 file has been overwritten with a current empty parquet.

- [ ] **Step 5: Commit any final adjustments**

```bash
git add -A
git commit -m "chore: finalise graceful no-trade pipeline handling"
```

---

## Out of scope

- Whether a symbol that returns `NO_TRADE` should be removed from `required_go_symbols` in the monthly-recert config — that is an operator policy decision. If a `NO_TRADE` symbol is still listed as required, `run_promote_live.py::_verify_required_go_symbols` will correctly block promotion; that is intended behaviour, not a bug for this plan.
- Re-mining or changing the mining logic — #173 already did that.
- Research into restoring an edge for `NO_TRADE` symbols — a separate effort.
