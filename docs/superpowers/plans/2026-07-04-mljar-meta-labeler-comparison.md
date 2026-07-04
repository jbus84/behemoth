# mljar-supervised Meta-Labeler Comparison Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Compare `mljar-supervised`'s `AutoML` (model-mixing ensemble of LightGBM/Xgboost/CatBoost/Random Forest/Extra Trees) against the existing single `HistGradientBoostingClassifier` meta-labeler, on the identical current-best trade population and WFO fold splits, to see if a stronger classifier improves on the just-merged +6.014 bps/fill result.

**Architecture:** One new standalone script, `scripts/boostlss_xs/mljar_meta_labeler_compare.py`, that reproduces the current best trade population using existing unmodified functions, then implements its own WFO fold loop (mirroring `fit_meta_label_wfo`'s exact fold logic) that fits both classifiers on identical splits for a fair comparison.

**Tech Stack:** Python, `mljar-supervised` (ephemeral, via `uv run --with`), `sklearn.ensemble.HistGradientBoostingClassifier`, pandas, numpy.

## Global Constraints

- No modifications to `run_tick_backtest`'s signature, `fit_meta_label_wfo`, or any other shared production code in `meta_label_straddle.py`/`plain_regression_baseline.py` — purely additive new script.
- `mljar-supervised` stays an ephemeral dependency (`uv run --with mljar-supervised`) — no changes to `pyproject.toml`/`uv.lock`.
- `AutoML` is capped at `mode="Explain"`, `algorithms=["LightGBM", "Xgboost", "CatBoost", "Random Forest", "Extra Trees"]`, `explain_level=0` (no full SHAP reports), and a `--automl-time-limit` CLI flag defaulting to 90 seconds per fold — never mljar's own defaults (1 hour, ~10 families, full explainability).
- `results_path` for each fold's `AutoML` run goes to a fresh `tempfile.mkdtemp()` directory, removed via `shutil.rmtree` after that fold completes — nothing written into the repo.
- Scoped to EURUSD only (`--pairs` defaults to `["EURUSD"]`), not the full 4-pair set.
- Trade population uses the current best config: `--high-quantile 0.90`, `--low-quantile 0.5`, `--sig-thresh 4.5`, `--sig-thresh-hi 5.5`, `tail_ratio` feature added to `_FEAT_COLS`.
- No new pytest coverage — matches this codebase's existing pattern for `scripts/boostlss_xs/` research scripts.
- `make quality`/`ruff check` must be clean before committing.

---

### Task 1: mljar vs. baseline meta-labeler comparison script

**Files:**
- Create: `scripts/boostlss_xs/mljar_meta_labeler_compare.py`

**Interfaces:**
- Consumes: `fit_wfo_quantile_robust(X: np.ndarray, y: np.ndarray, quantile: float = 0.85) -> np.ndarray`
  and `_DEFAULT_PAIRS: list[str]` from `plain_regression_baseline.py`;
  `build_1h_features(sym: str, data_dir: str, tail_rows: int | None = None) -> dict`
  (returns dict with keys `"X"`, `"vs"`, `"ts"`, ...),
  `run_tick_backtest(sym, data_dir, tick_dir, ..., sig_thresh: float = 1.5,
  sig_thresh_hi: float | None = None, family: str = "gaussian",
  sigma_override: np.ndarray | None = None, verbose: bool = True) -> tuple[pd.DataFrame, list[float]]`,
  `_option_b_net_per_fill(df: pd.DataFrame, threshold: float) -> float`,
  `_FEAT_COLS: list[str]`, `_N_FOLDS: int` (= 5), `_COMMISSION_RT: float` from
  `meta_label_straddle.py`. Note `_option_b_net_per_fill` expects a `"prob_tp"`
  column on its input dataframe — the comparison table step below renames each
  classifier's probability column to `"prob_tp"` before calling it, once per
  classifier.
- Produces: no new interfaces (terminal script, prints a report).

- [ ] **Step 1: Write the script**

```python
"""
mljar-supervised meta-labeler comparison: does model mixing (LightGBM, Xgboost,
CatBoost, Random Forest, Extra Trees combined via mljar's AutoML ensemble) beat
the existing single HistGradientBoostingClassifier meta-labeler, on the current
best trade population (q=0.90 quantile regression, window 4.5:5.5, tail_ratio
feature -- the just-merged +6.014 bps/fill result)?

Requires mljar-supervised, kept as an EPHEMERAL dependency (not added to
pyproject.toml/uv.lock):

    uv run --with mljar-supervised python scripts/boostlss_xs/mljar_meta_labeler_compare.py \\
        --data-dir /path/to/tick_bars \\
        --tick-dir /path/to/raw_ticks \\
        [--pairs EURUSD] \\
        [--high-quantile 0.90] \\
        [--low-quantile 0.5] \\
        [--sig-thresh 4.5] \\
        [--sig-thresh-hi 5.5] \\
        [--threshold 0.55] \\
        [--automl-time-limit 90] \\
        [--tail-rows N]

mljar's AutoML defaults to a 1-hour time budget and ~10 model families plus
ensembling/stacking -- across even one pair's 5 WFO folds that would risk
multi-hour runtimes. This script caps it hard: mode="Explain" (fastest),
algorithms restricted to 5 tree-based families, explain_level=0 (skip full
SHAP report generation), total_time_limit defaulting to 90 seconds per fold.

--tail-rows truncates the raw 1-minute parquet before 1h aggregation, for fast
smoke-testing only -- omit it (or pass a small value like 20000) to sanity-check
the script quickly before committing to the full, untruncated run.
"""
from __future__ import annotations

import argparse
import shutil
import tempfile

import numpy as np
import pandas as pd
from meta_label_straddle import (
    _COMMISSION_RT,
    _FEAT_COLS,
    _N_FOLDS,
    _option_b_net_per_fill,
    build_1h_features,
    run_tick_backtest,
)
from plain_regression_baseline import _DEFAULT_PAIRS, fit_wfo_quantile_robust
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import roc_auc_score
from supervised import AutoML

_RATIO_FLOOR = 1e-6
_ALGORITHMS = ["LightGBM", "Xgboost", "CatBoost", "Random Forest", "Extra Trees"]


def _build_trade_population(
    pairs: list[str],
    data_dir: str,
    tick_dir: str,
    high_quantile: float,
    low_quantile: float,
    sig_thresh: float,
    sig_thresh_hi: float,
    tail_rows: int | None,
) -> pd.DataFrame:
    tick_dfs: list[pd.DataFrame] = []
    for sym in pairs:
        d = build_1h_features(sym, data_dir, tail_rows=tail_rows)
        X, vs, ts = d["X"], d["vs"], d["ts"]
        n = len(vs)
        y = np.full(n, np.nan)
        y[:-1] = vs[1:]

        print(f"  {sym}: fitting high (q={high_quantile}) + "
              f"low (q={low_quantile}) quantile WFO...", flush=True)
        sg_high = fit_wfo_quantile_robust(X, y, quantile=high_quantile)
        sg_low = fit_wfo_quantile_robust(X, y, quantile=low_quantile)
        tail_ratio = sg_high / np.maximum(sg_low, _RATIO_FLOOR)

        ratio_by_ts = {
            str(ts[i]): tail_ratio[i] for i in range(n) if not np.isnan(tail_ratio[i])
        }

        df_sym, _ = run_tick_backtest(
            sym=sym, data_dir=data_dir, tick_dir=tick_dir,
            family="gaussian", sigma_override=sg_high,
            sig_thresh=sig_thresh, sig_thresh_hi=sig_thresh_hi,
        )
        if len(df_sym) == 0:
            continue
        df_sym["tail_ratio"] = df_sym["ts"].map(ratio_by_ts)
        tick_dfs.append(df_sym)

    if not tick_dfs:
        print("No trades produced.")
        raise SystemExit(1)
    return pd.concat(tick_dfs, ignore_index=True)


def fit_meta_label_wfo_compare(
    df: pd.DataFrame,
    feat_cols: list[str],
    automl_time_limit: int,
) -> tuple[pd.DataFrame, list[tuple[int, pd.DataFrame]]]:
    """
    Fits BOTH the baseline HistGradientBoostingClassifier and mljar's AutoML
    on identical WFO fold splits (matching fit_meta_label_wfo's fold logic
    exactly: fs = n // (_N_FOLDS + 1), expanding window, no embargo).

    Returns (df_oos, leaderboards): df_oos has 'prob_tp_baseline' and
    'prob_tp_mljar' columns for OOS rows where BOTH classifiers produced a
    prediction; leaderboards is a list of (fold_index, leaderboard_dataframe)
    for folds where mljar succeeded, so the caller can inspect which model
    family actually won that fold.
    """
    df = df.dropna(subset=feat_cols).copy()
    df["label"] = (df.outcome == "tp").astype(int)
    X = df[feat_cols].values
    y = df.label.values
    n = len(df)
    fs = n // (_N_FOLDS + 1)

    oos_prob_baseline = np.full(n, np.nan)
    oos_prob_mljar = np.full(n, np.nan)
    aucs_baseline: list[float] = []
    aucs_mljar: list[float] = []
    leaderboards: list[tuple[int, pd.DataFrame]] = []

    for fi in range(_N_FOLDS):
        tr_end = fs * (fi + 1)
        te_start = tr_end
        te_end = min(te_start + fs, n)
        if te_end <= te_start:
            break

        clf = HistGradientBoostingClassifier(max_iter=200, max_depth=4, random_state=42)
        clf.fit(X[:tr_end], y[:tr_end])
        oos_prob_baseline[te_start:te_end] = clf.predict_proba(X[te_start:te_end])[:, 1]
        aucs_baseline.append(
            roc_auc_score(y[te_start:te_end], oos_prob_baseline[te_start:te_end])
        )

        results_path = tempfile.mkdtemp(prefix=f"mljar_meta_compare_fold{fi}_")
        try:
            automl = AutoML(
                mode="Explain",
                ml_task="binary_classification",
                total_time_limit=automl_time_limit,
                algorithms=_ALGORITHMS,
                explain_level=0,
                results_path=results_path,
                verbose=0,
            )
            automl.fit(
                pd.DataFrame(X[:tr_end], columns=feat_cols),
                pd.Series(y[:tr_end]),
            )
            oos_prob_mljar[te_start:te_end] = automl.predict_proba(
                pd.DataFrame(X[te_start:te_end], columns=feat_cols)
            )[:, 1]
            aucs_mljar.append(
                roc_auc_score(y[te_start:te_end], oos_prob_mljar[te_start:te_end])
            )
            leaderboards.append((fi, automl.get_leaderboard()))
        except Exception as e:
            print(f"  fold {fi}: mljar AutoML failed — {e}")
        finally:
            shutil.rmtree(results_path, ignore_errors=True)

    mask = ~np.isnan(oos_prob_baseline) & ~np.isnan(oos_prob_mljar)
    df_oos = df[mask].copy()
    df_oos["prob_tp_baseline"] = oos_prob_baseline[mask]
    df_oos["prob_tp_mljar"] = oos_prob_mljar[mask]
    df_oos["mean_auc_baseline"] = float(np.mean(aucs_baseline)) if aucs_baseline else float("nan")
    df_oos["mean_auc_mljar"] = float(np.mean(aucs_mljar)) if aucs_mljar else float("nan")
    return df_oos, leaderboards


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="mljar-supervised meta-labeler comparison")
    p.add_argument("--data-dir",          default="/Users/danielfisher/repositories/behemoth/data/tick_bars")
    p.add_argument("--tick-dir",          default="/Users/danielfisher/Desktop/tick")
    p.add_argument("--pairs",             nargs="+", default=["EURUSD"])
    p.add_argument("--high-quantile",     type=float, default=0.90)
    p.add_argument("--low-quantile",      type=float, default=0.5)
    p.add_argument("--sig-thresh",        type=float, default=4.5)
    p.add_argument("--sig-thresh-hi",     type=float, default=5.5)
    p.add_argument("--threshold",         type=float, default=0.55)
    p.add_argument("--automl-time-limit", type=int, default=90)
    p.add_argument("--tail-rows",         type=int, default=None)
    return p.parse_args()


if __name__ == "__main__":
    args = _parse_args()

    all_raw = _build_trade_population(
        pairs=args.pairs, data_dir=args.data_dir, tick_dir=args.tick_dir,
        high_quantile=args.high_quantile, low_quantile=args.low_quantile,
        sig_thresh=args.sig_thresh, sig_thresh_hi=args.sig_thresh_hi,
        tail_rows=args.tail_rows,
    )

    feat_cols = [*_FEAT_COLS, "tail_ratio"]

    oos_dfs: list[pd.DataFrame] = []
    all_leaderboards: list[tuple[str, int, pd.DataFrame]] = []
    for sym, g in all_raw.groupby("sym"):
        print(f"  {sym}: running WFO comparison "
              f"(automl_time_limit={args.automl_time_limit}s/fold)...", flush=True)
        try:
            df_oos, leaderboards = fit_meta_label_wfo_compare(
                g.copy(), feat_cols=feat_cols, automl_time_limit=args.automl_time_limit,
            )
            oos_dfs.append(df_oos)
            for fi, lb in leaderboards:
                all_leaderboards.append((sym, fi, lb))
        except Exception as e:
            print(f"  {sym}: comparison failed — {e}")

    if not oos_dfs:
        print("Meta-labeling comparison produced no results.")
        raise SystemExit(1)

    result = pd.concat(oos_dfs, ignore_index=True)

    print()
    print("=" * 70)
    print("BASELINE vs MLJAR COMPARISON")
    print("=" * 70)
    for label, prob_col, auc_col in [
        ("baseline (HistGradientBoostingClassifier)", "prob_tp_baseline", "mean_auc_baseline"),
        ("mljar (AutoML ensemble)", "prob_tp_mljar", "mean_auc_mljar"),
    ]:
        cmp_df = result.rename(columns={prob_col: "prob_tp"})
        ob_net = _option_b_net_per_fill(cmp_df, args.threshold)
        print(f"{label:<42}  n={len(cmp_df):>5}  AUC={cmp_df[auc_col].mean():.3f}  "
              f"TP%={cmp_df.label.mean():.1%}  Option B={ob_net:+.3f} bps/fill")

    print()
    print("=" * 70)
    print("LEADERBOARD (one row per fold that mljar completed)")
    print("=" * 70)
    for sym, fi, lb in all_leaderboards:
        print(f"\n  {sym} fold {fi}:")
        print(lb.to_string(index=False))
```

- [ ] **Step 2: Syntax check**

```bash
uv run python -c "
import ast
ast.parse(open('scripts/boostlss_xs/mljar_meta_labeler_compare.py').read())
print('syntax OK')
"
```

Expected: `syntax OK`

- [ ] **Step 3: Lint check**

```bash
uv run ruff check scripts/boostlss_xs/mljar_meta_labeler_compare.py
```

Expected: `All checks passed!`. If not, fix the reported issues (common ones in
this codebase: unsorted imports — `uv run ruff check --fix
scripts/boostlss_xs/mljar_meta_labeler_compare.py` auto-fixes most; unused loop
variables — rename to `_name`; bare `try/except/pass` — use
`contextlib.suppress` only where the exception is truly ignorable, but note
this script's `except Exception as e: print(...)` blocks already log, so they
should not trigger that rule).

- [ ] **Step 4: Fast smoke test (truncated data, low time budget)**

```bash
uv run --with mljar-supervised python scripts/boostlss_xs/mljar_meta_labeler_compare.py \
  --data-dir /Users/danielfisher/repositories/behemoth/data/tick_bars \
  --tick-dir /Users/danielfisher/Desktop/tick \
  --pairs EURUSD \
  --tail-rows 20000 \
  --automl-time-limit 15
```

Expected: runs to completion in well under a few minutes (truncated data + a
15-second-per-fold AutoML budget), prints the two-row baseline-vs-mljar
comparison table (n_trades will be small given the truncated input — that's
expected for a smoke test) and at least one fold's leaderboard without raising
an unhandled exception. If mljar's `AutoML.fit()` raises for every fold at this
tiny scope (e.g. too few rows for a stable model search), the script should
still complete and print `mljar (AutoML ensemble)` with `n=0`/`AUC=nan` rather
than crashing — confirm this degrades gracefully before moving to the full run.

- [ ] **Step 5: Full run**

```bash
uv run --with mljar-supervised python scripts/boostlss_xs/mljar_meta_labeler_compare.py \
  --data-dir /Users/danielfisher/repositories/behemoth/data/tick_bars \
  --tick-dir /Users/danielfisher/Desktop/tick \
  --pairs EURUSD \
  --high-quantile 0.90 --low-quantile 0.5 \
  --sig-thresh 4.5 --sig-thresh-hi 5.5 --threshold 0.55 \
  --automl-time-limit 90
```

Expected: runs to completion (5 folds × up to 90s AutoML budget each, plus the
tick-exact backtest and quantile-regression fitting time already established
as fast at single-pair scope from prior scripts in this investigation — budget
up to ~15-20 minutes total, this is compute-bound, not a hang; if unsure,
check `ps aux | grep python` for CPU activity). Prints the baseline-vs-mljar
comparison table and 5 leaderboards (one per fold). The baseline row's
n_trades/AUC/Option B should be in the same ballpark as EURUSD's contribution
to the merged PR #377 result (not necessarily identical, since PR #377 pooled
4 pairs and this run is EURUSD-only) — sanity-check this before treating the
mljar row as meaningful.

- [ ] **Step 6: Record findings in BACKLOG.md**

Read `scripts/boostlss_xs/BACKLOG.md`, find the `### Tail-shape meta-labeler
feature (this PR)` section (the most recent entry, from the just-merged
PR #377), and append a new top-level section after it:

```markdown
## mljar-supervised meta-labeler comparison (2026-07-04)

Ran `mljar_meta_labeler_compare.py` on EURUSD only, at the current best trade
population config (q=0.90 quantile regression, window 4.5:5.5, tail_ratio
feature), comparing the existing HistGradientBoostingClassifier meta-labeler
against mljar-supervised's AutoML (mode="Explain", algorithms restricted to
LightGBM/Xgboost/CatBoost/Random Forest/Extra Trees, 90s/fold budget):

[Paste the actual printed baseline-vs-mljar comparison table and at least one
representative fold's leaderboard from Step 5 here, verbatim.]

**Verdict:** [state plainly whether mljar's AutoML ensemble beat the baseline
on AUC and/or Option B bps/fill, by how much, and which individual algorithm
family won on the leaderboard (not just noting "ensemble won" — name the
actual best base model). If mljar failed on some folds, note how many and
whether that changes confidence in the comparison. This is EURUSD-only —
explicitly note that scaling to the full 4-pair set is a follow-up decision,
not yet done.]
```

- [ ] **Step 7: Commit**

```bash
git add scripts/boostlss_xs/mljar_meta_labeler_compare.py scripts/boostlss_xs/BACKLOG.md
git commit -m "feat(boostlss_xs): mljar-supervised meta-labeler comparison (EURUSD)

Compares mljar-supervised's AutoML (model-mixing ensemble of
LightGBM/Xgboost/CatBoost/Random Forest/Extra Trees) against the
existing single HistGradientBoostingClassifier meta-labeler, on
identical WFO fold splits and the current best trade population
(q=0.90 quantile regression, window 4.5:5.5, tail_ratio feature).
Ephemeral dependency (uv run --with), no changes to fit_meta_label_wfo
or any shared production code. Scoped to EURUSD only.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Self-review notes (for the plan author, not a task)

- **Spec coverage**: Goal 1 (compare AutoML fast-mode vs baseline on identical
  trade population/folds) → Task 1 Steps 1, 5. Goal 2 (surface which model
  family wins via leaderboard) → Task 1 Step 1's `get_leaderboard()` call and
  Step 6's BACKLOG instruction to name the actual winning base model, not just
  "ensemble." Goal 3 (fully additive, cheap to discard) → Global Constraints
  (no `fit_meta_label_wfo` changes, ephemeral dependency) and Task 1's
  `results_path`/`shutil.rmtree` handling. All non-goals (no `Perform`/
  `Compete`/`Optuna` modes, no full SHAP, EURUSD-only, no `pyproject.toml`
  changes, no pytest) are respected — confirmed the script never touches
  `meta_label_straddle.py`/`plain_regression_baseline.py`.
- **No placeholders**: every step has literal, complete code or literal
  commands with expected output. The BACKLOG.md instruction asks for pasting
  *actual* printed output (which doesn't exist until the code runs), not an
  assertion of specific numbers ahead of time — a data-recording instruction,
  not a plan placeholder.
- **Type consistency**: `fit_wfo_quantile_robust(X, y, quantile=...)` and
  `run_tick_backtest(..., sigma_override=..., sig_thresh=..., sig_thresh_hi=...)`
  used identically to `tail_shape_feature.py`'s established pattern.
  `_option_b_net_per_fill(df, threshold)` called on a renamed-column copy of
  `result`, matching its existing signature exactly (it expects a `prob_tp`
  column, which the renaming step provides for each classifier variant in
  turn). `fit_meta_label_wfo_compare`'s return type
  (`tuple[pd.DataFrame, list[tuple[int, pd.DataFrame]]]`) is used consistently
  by its only caller in the same file.
