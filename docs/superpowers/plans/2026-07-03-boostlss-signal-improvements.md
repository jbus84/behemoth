# BoostLSS Signal Improvements Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Confirm the windowed quantile-robust regression plateau from PR #376
(+4.8 to +5.3 bps/fill) is robust across pairs/years, search for a better base
quantile level, and test one purely-additive tail-shape feature for the
meta-labeler — three independent, complementary experiments building on the
established baseline without touching any shared production logic.

**Architecture:** Three new standalone scripts in `scripts/boostlss_xs/`, each
importing existing functions (`fit_wfo_quantile_robust`, `run_tick_backtest`,
`fit_meta_label_wfo`, `_option_b_net_per_fill`) with zero modifications to
shared code. Findings recorded into `scripts/boostlss_xs/BACKLOG.md`.

**Tech Stack:** Python, `sklearn.ensemble.HistGradientBoostingRegressor`,
pandas, numpy — no new dependencies.

## Global Constraints

- No modifications to `run_tick_backtest`'s signature or any shared production
  code in `meta_label_straddle.py` — all three scripts are additive consumers.
- No new pytest coverage — this codebase's `scripts/boostlss_xs/` research
  scripts are validated informally (run it, inspect the printed table),
  consistent with every script from PR #376.
- `make quality` must be clean before any commit — CI blocks on ruff lint
  (import sorting, unused loop variables, `try`/`except`/`pass` →
  `contextlib.suppress`). This was missed once in PR #376 and cost a fix-up
  commit; do not repeat it.
- Every script defaults to the 4-pair set `["EURUSD", "GBPJPY", "AUDUSD",
  "USDJPY"]` (matches `_DEFAULT_PAIRS` in `plain_regression_baseline.py`) and
  `--threshold 0.55` for the meta-labeler's accept/reject cutoff (matches every
  prior script in this investigation).

---

### Task 1: Stability check — per-pair and per-year breakdown

**Files:**
- Create: `scripts/boostlss_xs/stability_check.py`

**Interfaces:**
- Consumes: `fit_wfo_quantile_robust(X: np.ndarray, y: np.ndarray, quantile: float = 0.85) -> np.ndarray`
  and `_DEFAULT_PAIRS: list[str]` from `plain_regression_baseline.py`;
  `build_1h_features(sym: str, data_dir: str, tail_rows: int | None = None) -> dict`
  (returns dict with keys `"X"`, `"vs"`, `"ts"`, ...),
  `run_tick_backtest(sym, data_dir, tick_dir, ..., sig_thresh: float = 1.5,
  sig_thresh_hi: float | None = None, family: str = "gaussian",
  sigma_override: np.ndarray | None = None, verbose: bool = True) -> tuple[pd.DataFrame, list[float]]`,
  `fit_meta_label_wfo(df: pd.DataFrame, feat_cols: list[str] = _FEAT_COLS) -> pd.DataFrame`
  (adds `prob_tp`, `mean_auc`, `label` columns, returns OOS rows only),
  `_option_b_net_per_fill(df: pd.DataFrame, threshold: float) -> float`,
  `_FEAT_COLS: list[str]` from `meta_label_straddle.py`.
- Produces: no new interfaces (terminal script, prints a report).

- [ ] **Step 1: Write the script**

```python
"""
Stability check: does the windowed quantile-robust regression plateau found in
PR #376 (sig_thresh~4.0-4.5, sig_thresh_hi~4.8-5.5, Option B +4.8 to +5.3 bps/fill)
hold up consistently across pairs and years, or is it concentrated in one
pair/period?

Usage::

    uv run python scripts/boostlss_xs/stability_check.py \\
        --data-dir /path/to/tick_bars \\
        --tick-dir /path/to/raw_ticks \\
        [--pairs EURUSD GBPJPY AUDUSD USDJPY] \\
        [--quantile 0.85] \\
        [--sig-thresh 4.0] \\
        [--sig-thresh-hi 5.0] \\
        [--threshold 0.55]
"""
from __future__ import annotations

import argparse

import numpy as np
import pandas as pd

from meta_label_straddle import (
    _FEAT_COLS,
    _option_b_net_per_fill,
    build_1h_features,
    fit_meta_label_wfo,
    run_tick_backtest,
)
from plain_regression_baseline import _DEFAULT_PAIRS, fit_wfo_quantile_robust


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Stability check for windowed quantile-robust regression")
    p.add_argument("--data-dir",      default="/Users/danielfisher/repositories/behemoth/data/tick_bars")
    p.add_argument("--tick-dir",      default="/Users/danielfisher/Desktop/tick")
    p.add_argument("--pairs",         nargs="+", default=_DEFAULT_PAIRS)
    p.add_argument("--quantile",      type=float, default=0.85)
    p.add_argument("--sig-thresh",    type=float, default=4.0)
    p.add_argument("--sig-thresh-hi", type=float, default=5.0)
    p.add_argument("--threshold",     type=float, default=0.55)
    return p.parse_args()


if __name__ == "__main__":
    args = _parse_args()

    per_pair_trades: dict[str, pd.DataFrame] = {}
    for sym in args.pairs:
        d = build_1h_features(sym, args.data_dir)
        X, vs = d["X"], d["vs"]
        n = len(vs)
        y = np.full(n, np.nan)
        y[:-1] = vs[1:]

        print(f"  {sym}: fitting quantile-robust WFO (q={args.quantile})...", flush=True)
        sg = fit_wfo_quantile_robust(X, y, quantile=args.quantile)

        df_sym, _ = run_tick_backtest(
            sym=sym, data_dir=args.data_dir, tick_dir=args.tick_dir,
            family="gaussian", sigma_override=sg,
            sig_thresh=args.sig_thresh, sig_thresh_hi=args.sig_thresh_hi,
        )
        if len(df_sym) > 0:
            per_pair_trades[sym] = df_sym

    if not per_pair_trades:
        print("No trades produced.")
        raise SystemExit(1)

    all_raw = pd.concat(per_pair_trades.values(), ignore_index=True)

    oos_dfs: list[pd.DataFrame] = []
    for sym, g in all_raw.groupby("sym"):
        try:
            oos_dfs.append(fit_meta_label_wfo(g.copy(), feat_cols=_FEAT_COLS))
        except Exception as e:
            print(f"  {sym}: meta-label failed — {e}")

    if not oos_dfs:
        print("Meta-labeling produced no results.")
        raise SystemExit(1)

    result = pd.concat(oos_dfs, ignore_index=True)
    pooled_ob = _option_b_net_per_fill(result, args.threshold)

    print()
    print("=" * 70)
    print(f"POOLED RESULT  sig_thresh={args.sig_thresh}  "
          f"sig_thresh_hi={args.sig_thresh_hi}  q={args.quantile}")
    print("=" * 70)
    print(f"  n_trades: {len(result)}  AUC: {result.mean_auc.mean():.3f}  "
          f"TP%: {result.label.mean():.1%}  Option B: {pooled_ob:+.3f} bps/fill")

    print()
    print("=" * 70)
    print("BY PAIR")
    print("=" * 70)
    for sym, g in result.groupby("sym"):
        ob = _option_b_net_per_fill(g, args.threshold)
        print(f"  {sym:<8}  n={len(g):>5}  AUC={g.mean_auc.mean():.3f}  "
              f"TP%={g.label.mean():.1%}  Option B={ob:+.3f} bps/fill")

    print()
    print("=" * 70)
    print("BY YEAR (pooled)")
    print("=" * 70)
    result = result.copy()
    result["year"] = result.ts.str[:4]
    for yr, g in result.groupby("year"):
        ob = _option_b_net_per_fill(g, args.threshold)
        print(f"  {yr}  n={len(g):>5}  AUC={g.mean_auc.mean():.3f}  "
              f"TP%={g.label.mean():.1%}  Option B={ob:+.3f} bps/fill")
```

- [ ] **Step 2: Syntax check**

```bash
uv run python -c "
import ast
ast.parse(open('scripts/boostlss_xs/stability_check.py').read())
print('syntax OK')
"
```

Expected: `syntax OK`

- [ ] **Step 3: Run `make quality` on this file before proceeding**

```bash
uv run ruff check scripts/boostlss_xs/stability_check.py
```

Expected: `All checks passed!`. If not, fix the reported issues (common ones from
this codebase: unsorted imports — let `uv run ruff check --fix
scripts/boostlss_xs/stability_check.py` auto-fix import order; unused loop
variables like `for sym, g in ...` when `sym` isn't used — rename to `_sym`;
`try`/`except Exception`/`pass` — replace with `contextlib.suppress(Exception)`,
importing `contextlib` at the top).

- [ ] **Step 4: Run the full 4-pair analysis**

```bash
uv run python scripts/boostlss_xs/stability_check.py \
  --data-dir /Users/danielfisher/repositories/behemoth/data/tick_bars \
  --tick-dir /Users/danielfisher/Desktop/tick \
  --pairs EURUSD GBPJPY AUDUSD USDJPY \
  --quantile 0.85 --sig-thresh 4.0 --sig-thresh-hi 5.0 --threshold 0.55
```

Expected: runs to completion (a few minutes — real tick data streaming across 4
pairs), prints a pooled result matching roughly the PR #376 ballpark (~n=3400-3600,
Option B in the +4.5 to +5.5 bps/fill range), then a per-pair breakdown (4 rows)
and a per-year breakdown (up to 6 rows, 2020-2025). Record the actual printed
numbers — do not assume they'll exactly match PR #376's aggregate figure, since
this script additionally reports per-pair/per-year splits PR #376 never computed
for this specific window.

- [ ] **Step 5: Record findings in BACKLOG.md**

Read `scripts/boostlss_xs/BACKLOG.md`, find the `## Distribution comparison
(2026-07-03)` section (added in PR #376), and append a new subsection directly
after it:

```markdown
### Stability check (this PR)

Ran `stability_check.py` at `sig_thresh=4.0, sig_thresh_hi=5.0, quantile=0.85`
(PR #376's sweet spot) with per-pair and per-year breakdowns:

[Paste the actual printed "BY PAIR" and "BY YEAR" tables from Step 4 here,
verbatim.]

**Verdict:** [state plainly whether every pair was individually net-positive and
whether any single year dominated the pooled average — this is the actual
finding, write down what the numbers show, not what was hoped for.]
```

- [ ] **Step 6: Commit**

```bash
git add scripts/boostlss_xs/stability_check.py scripts/boostlss_xs/BACKLOG.md
git commit -m "feat(boostlss_xs): stability check for windowed quantile-robust plateau

Per-pair and per-year Option B breakdown at PR #376's sweet spot
(sig_thresh=4.0, sig_thresh_hi=5.0, quantile=0.85), confirming (or
refuting) the plateau isn't concentrated in one pair or period.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

### Task 2: Quantile level sweep

**Files:**
- Create: `scripts/boostlss_xs/quantile_level_sweep.py`

**Interfaces:**
- Consumes: same as Task 1 (`fit_wfo_quantile_robust`, `_DEFAULT_PAIRS`,
  `build_1h_features`, `run_tick_backtest`, `fit_meta_label_wfo`,
  `_option_b_net_per_fill`, `_FEAT_COLS`).
- Produces: no new interfaces (terminal script).

- [ ] **Step 1: Write the script**

```python
"""
Quantile level sweep: PR #376 only tested quantile=0.85 for the sigma-predicting
regressor itself. Does a different quantile level raise the whole baseline
before optimizing the window further?

Tests a small set of quantile levels at a couple of representative windows
(not a full grid -- keeps compute bounded).

Usage::

    uv run python scripts/boostlss_xs/quantile_level_sweep.py \\
        --data-dir /path/to/tick_bars \\
        --tick-dir /path/to/raw_ticks \\
        [--pairs EURUSD GBPJPY AUDUSD USDJPY] \\
        [--quantiles 0.70 0.75 0.80 0.85 0.90 0.95] \\
        [--windows 4.0:5.0 4.5:5.5] \\
        [--threshold 0.55]
"""
from __future__ import annotations

import argparse
import contextlib

import numpy as np
import pandas as pd

from meta_label_straddle import (
    _FEAT_COLS,
    _option_b_net_per_fill,
    build_1h_features,
    fit_meta_label_wfo,
    run_tick_backtest,
)
from plain_regression_baseline import _DEFAULT_PAIRS, fit_wfo_quantile_robust


def _parse_window(s: str) -> tuple[float, float]:
    lo_str, hi_str = s.split(":")
    return float(lo_str), float(hi_str)


def run_window(
    lo: float,
    hi: float,
    sigma_by_pair: dict[str, np.ndarray],
    pairs: list[str],
    data_dir: str,
    tick_dir: str,
    threshold: float,
) -> tuple[int, float, float] | None:
    tick_dfs: list[pd.DataFrame] = []
    for sym in pairs:
        df_sym, _ = run_tick_backtest(
            sym=sym, data_dir=data_dir, tick_dir=tick_dir,
            family="gaussian", sigma_override=sigma_by_pair[sym],
            sig_thresh=lo, sig_thresh_hi=hi, verbose=False,
        )
        if len(df_sym) > 0:
            tick_dfs.append(df_sym)
    if not tick_dfs:
        return None
    all_raw = pd.concat(tick_dfs, ignore_index=True)
    oos_dfs: list[pd.DataFrame] = []
    for _sym, g in all_raw.groupby("sym"):
        with contextlib.suppress(Exception):
            oos_dfs.append(fit_meta_label_wfo(g.copy(), feat_cols=_FEAT_COLS))
    if not oos_dfs:
        return None
    result = pd.concat(oos_dfs, ignore_index=True)
    ob_net = _option_b_net_per_fill(result, threshold)
    return (len(result), result.mean_auc.mean(), ob_net)


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Quantile level sweep for the sigma regressor")
    p.add_argument("--data-dir",  default="/Users/danielfisher/repositories/behemoth/data/tick_bars")
    p.add_argument("--tick-dir",  default="/Users/danielfisher/Desktop/tick")
    p.add_argument("--pairs",     nargs="+", default=_DEFAULT_PAIRS)
    p.add_argument("--quantiles", type=float, nargs="+",
                    default=[0.70, 0.75, 0.80, 0.85, 0.90, 0.95])
    p.add_argument("--windows",   type=str, nargs="+", default=["4.0:5.0", "4.5:5.5"],
                    help="lo:hi pairs, e.g. 4.0:5.0")
    p.add_argument("--threshold", type=float, default=0.55)
    return p.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    windows = [_parse_window(w) for w in args.windows]

    d_by_pair: dict[str, dict] = {}
    for sym in args.pairs:
        d_by_pair[sym] = build_1h_features(sym, args.data_dir)

    print(f"{'Quantile':>9}  {'Window':>12}  {'n_trades':>8}  {'AUC':>6}  "
          f"{'Option B bps/fill':>18}")
    for q in args.quantiles:
        sigma_by_pair: dict[str, np.ndarray] = {}
        for sym in args.pairs:
            d = d_by_pair[sym]
            X, vs = d["X"], d["vs"]
            n = len(vs)
            y = np.full(n, np.nan)
            y[:-1] = vs[1:]
            sigma_by_pair[sym] = fit_wfo_quantile_robust(X, y, quantile=q)

        for lo, hi in windows:
            r = run_window(lo, hi, sigma_by_pair, args.pairs, args.data_dir,
                            args.tick_dir, args.threshold)
            window_str = f"{lo}:{hi}"
            if r is None:
                print(f"{q:>9.2f}  {window_str:>12}  {'0':>8}  {'--':>6}  {'--':>18}")
                continue
            n_trades, auc, ob = r
            print(f"{q:>9.2f}  {window_str:>12}  {n_trades:>8}  {auc:>6.3f}  {ob:>+18.3f}")
```

- [ ] **Step 2: Syntax check**

```bash
uv run python -c "
import ast
ast.parse(open('scripts/boostlss_xs/quantile_level_sweep.py').read())
print('syntax OK')
"
```

Expected: `syntax OK`

- [ ] **Step 3: Lint check**

```bash
uv run ruff check scripts/boostlss_xs/quantile_level_sweep.py
```

Expected: `All checks passed!`. Fix any reported issues before proceeding (see
Task 1 Step 3 for the common fix patterns in this codebase).

- [ ] **Step 4: Run the full sweep**

```bash
uv run python scripts/boostlss_xs/quantile_level_sweep.py \
  --data-dir /Users/danielfisher/repositories/behemoth/data/tick_bars \
  --tick-dir /Users/danielfisher/Desktop/tick \
  --pairs EURUSD GBPJPY AUDUSD USDJPY \
  --quantiles 0.70 0.75 0.80 0.85 0.90 0.95 \
  --windows 4.0:5.0 4.5:5.5 \
  --threshold 0.55
```

Expected: runs to completion (6 quantile levels × 2 windows × 4 pairs — budget
20-40 minutes given real tick-data streaming per pair/window; this is
compute-bound, not a hang), prints a 12-row table (one row per
quantile × window combination). q=0.85 rows should roughly match the known
reference points (window 4.0:5.0 ≈ +5.0 bps/fill, window 4.5:5.5 ≈ +5.3 bps/fill)
as a sanity check that the rest of the table is trustworthy.

- [ ] **Step 5: Record findings in BACKLOG.md**

Append a new subsection after the stability-check subsection added in Task 1:

```markdown
### Quantile level sweep (this PR)

Swept quantile levels {0.70, 0.75, 0.80, 0.85, 0.90, 0.95} at two representative
windows (4.0:5.0 and 4.5:5.5):

[Paste the actual printed table from Step 4 here, verbatim.]

**Verdict:** [state which quantile level (if any) beats q=0.85, and by how
much — or confirm q=0.85 remains the best tested level. Note if the pattern
across quantile levels is monotonic/clean or noisy, same standard applied to
every other sweep in this investigation.]
```

- [ ] **Step 6: Commit**

```bash
git add scripts/boostlss_xs/quantile_level_sweep.py scripts/boostlss_xs/BACKLOG.md
git commit -m "feat(boostlss_xs): quantile level sweep for the sigma regressor

Tests quantile in {0.70,0.75,0.80,0.85,0.90,0.95} at two representative
windows, since PR #376 only ever tested quantile=0.85.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

### Task 3: Tail-shape meta-labeler feature

**Files:**
- Create: `scripts/boostlss_xs/tail_shape_feature.py`

**Interfaces:**
- Consumes: same as Tasks 1-2, plus reads `d["ts"]` from `build_1h_features`'s
  return dict (the per-bar timestamp array, same indexing as `d["X"]`/`d["vs"]`)
  to build the timestamp → tail_ratio lookup for the post-hoc join. The join key
  must match the trades dataframe's own `"ts"` column format exactly: `str(ts[i])`
  (confirmed in `meta_label_straddle.py`'s `run_tick_backtest`, where each trade
  row is built with `"ts": str(ts[i])`).
- Produces: no new interfaces (terminal script).

- [ ] **Step 1: Determine the winning `(sig_thresh, sig_thresh_hi, quantile)`
  from Tasks 1-2's actual results before writing this script's defaults**

Read back what Task 2's Step 5 recorded in BACKLOG.md. Use whichever
`(quantile, window)` combination had the best Option B bps/fill as this
script's `--high-quantile`/`--sig-thresh`/`--sig-thresh-hi` defaults below,
replacing the placeholder defaults (`0.85`, `4.0`, `5.0`) shown in Step 2's code
if Task 2 found something better. If Task 2 found no improvement over q=0.85 at
window 4.0:5.0, keep those exact defaults unchanged.

- [ ] **Step 2: Write the script**

```python
"""
Tail-shape meta-labeler feature: does exposing a "how fat is this bar's tail"
signal to the meta-labeler help, even though baking similar information into
first-stage sigma sizing (Merton's jump-intensity, SHASH's skew/kurtosis) never
did (see BACKLOG.md's distribution comparison)?

Fits a second, lower quantile regression (default q=0.5, median |return|)
alongside the existing high quantile (default q=0.85, the sigma-sizing signal),
computes their ratio (tail_ratio = high/median) at every OOS bar, and merges it
onto the trades dataframe by matching timestamps -- purely additive, no change
to run_tick_backtest's signature or sigma sizing.

Note: a trade's tail_ratio can be missing (NaN) if the low-quantile regression's
OOS prediction wasn't yet defined at that bar (WFO fold warmup) even though the
high-quantile prediction was -- fit_meta_label_wfo's dropna(subset=feat_cols)
will then drop that row only when tail_ratio is in feat_cols, so the "with
tail_ratio" variant can have a slightly smaller n_trades than the baseline.
This is expected, not a bug -- note it when interpreting results, don't try to
force matching counts.

Usage::

    uv run python scripts/boostlss_xs/tail_shape_feature.py \\
        --data-dir /path/to/tick_bars \\
        --tick-dir /path/to/raw_ticks \\
        [--pairs EURUSD GBPJPY AUDUSD USDJPY] \\
        [--high-quantile 0.85] \\
        [--low-quantile 0.5] \\
        [--sig-thresh 4.0] \\
        [--sig-thresh-hi 5.0] \\
        [--threshold 0.55]
"""
from __future__ import annotations

import argparse

import numpy as np
import pandas as pd

from meta_label_straddle import (
    _FEAT_COLS,
    _option_b_net_per_fill,
    build_1h_features,
    fit_meta_label_wfo,
    run_tick_backtest,
)
from plain_regression_baseline import _DEFAULT_PAIRS, fit_wfo_quantile_robust

_RATIO_FLOOR = 1e-6


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Tail-shape meta-labeler feature experiment")
    p.add_argument("--data-dir",      default="/Users/danielfisher/repositories/behemoth/data/tick_bars")
    p.add_argument("--tick-dir",      default="/Users/danielfisher/Desktop/tick")
    p.add_argument("--pairs",         nargs="+", default=_DEFAULT_PAIRS)
    p.add_argument("--high-quantile", type=float, default=0.85)
    p.add_argument("--low-quantile",  type=float, default=0.5)
    p.add_argument("--sig-thresh",    type=float, default=4.0)
    p.add_argument("--sig-thresh-hi", type=float, default=5.0)
    p.add_argument("--threshold",     type=float, default=0.55)
    return p.parse_args()


if __name__ == "__main__":
    args = _parse_args()

    tick_dfs: list[pd.DataFrame] = []
    for sym in args.pairs:
        d = build_1h_features(sym, args.data_dir)
        X, vs, ts = d["X"], d["vs"], d["ts"]
        n = len(vs)
        y = np.full(n, np.nan)
        y[:-1] = vs[1:]

        print(f"  {sym}: fitting high (q={args.high_quantile}) + "
              f"low (q={args.low_quantile}) quantile WFO...", flush=True)
        sg_high = fit_wfo_quantile_robust(X, y, quantile=args.high_quantile)
        sg_low = fit_wfo_quantile_robust(X, y, quantile=args.low_quantile)
        tail_ratio = sg_high / np.maximum(sg_low, _RATIO_FLOOR)

        ratio_by_ts = {
            str(ts[i]): tail_ratio[i] for i in range(n) if not np.isnan(tail_ratio[i])
        }

        df_sym, _ = run_tick_backtest(
            sym=sym, data_dir=args.data_dir, tick_dir=args.tick_dir,
            family="gaussian", sigma_override=sg_high,
            sig_thresh=args.sig_thresh, sig_thresh_hi=args.sig_thresh_hi,
        )
        if len(df_sym) == 0:
            continue
        df_sym["tail_ratio"] = df_sym["ts"].map(ratio_by_ts)
        tick_dfs.append(df_sym)

    if not tick_dfs:
        print("No trades produced.")
        raise SystemExit(1)

    all_raw = pd.concat(tick_dfs, ignore_index=True)

    for label, feat_cols in [
        ("baseline (no tail_ratio)", _FEAT_COLS),
        ("with tail_ratio", [*_FEAT_COLS, "tail_ratio"]),
    ]:
        oos_dfs: list[pd.DataFrame] = []
        for sym, g in all_raw.groupby("sym"):
            try:
                oos_dfs.append(fit_meta_label_wfo(g.copy(), feat_cols=feat_cols))
            except Exception as e:
                print(f"  {sym}: meta-label failed ({label}) — {e}")
        if not oos_dfs:
            print(f"{label}: meta-labeling produced no results")
            continue
        result = pd.concat(oos_dfs, ignore_index=True)
        ob_net = _option_b_net_per_fill(result, args.threshold)
        print(f"{label:<28}  n={len(result):>5}  AUC={result.mean_auc.mean():.3f}  "
              f"TP%={result.label.mean():.1%}  Option B={ob_net:+.3f} bps/fill")
```

- [ ] **Step 3: Syntax check**

```bash
uv run python -c "
import ast
ast.parse(open('scripts/boostlss_xs/tail_shape_feature.py').read())
print('syntax OK')
"
```

Expected: `syntax OK`

- [ ] **Step 4: Lint check**

```bash
uv run ruff check scripts/boostlss_xs/tail_shape_feature.py
```

Expected: `All checks passed!`. Fix any reported issues before proceeding.

- [ ] **Step 5: Run the full comparison**

```bash
uv run python scripts/boostlss_xs/tail_shape_feature.py \
  --data-dir /Users/danielfisher/repositories/behemoth/data/tick_bars \
  --tick-dir /Users/danielfisher/Desktop/tick \
  --pairs EURUSD GBPJPY AUDUSD USDJPY \
  --high-quantile 0.85 --low-quantile 0.5 \
  --sig-thresh 4.0 --sig-thresh-hi 5.0 --threshold 0.55
```

(Use whatever `--high-quantile`/`--sig-thresh`/`--sig-thresh-hi` values Step 1
of this task determined, if different from these defaults.)

Expected: runs to completion, prints two rows — `baseline (no tail_ratio)` and
`with tail_ratio` — each with n_trades, AUC, TP%, and Option B bps/fill. The
baseline row's numbers should be close to (not necessarily identical to,
per this task's docstring note about dropna row-count differences) Task 1's
pooled result at the same window.

- [ ] **Step 6: Record findings in BACKLOG.md**

Append a new subsection after the quantile-sweep subsection added in Task 2:

```markdown
### Tail-shape meta-labeler feature (this PR)

Added `tail_ratio` (ratio of a high and low quantile regression's predicted
`|return|`) as a new meta-labeler feature, purely additive (sigma sizing
unchanged):

[Paste the actual printed baseline vs. with-tail_ratio comparison from Step 5
here, verbatim.]

**Verdict:** [state plainly whether tail_ratio improved AUC and/or Option B, or
made no difference / hurt. If n_trades differs meaningfully between the two
rows, note that per the script's documented dropna caveat rather than treating
it as a contradiction.]
```

- [ ] **Step 7: Commit**

```bash
git add scripts/boostlss_xs/tail_shape_feature.py scripts/boostlss_xs/BACKLOG.md
git commit -m "feat(boostlss_xs): tail-shape meta-labeler feature experiment

Tests whether a ratio of two quantile regressions (high/low |return|)
helps the meta-labeler, purely additive via post-hoc timestamp join --
no changes to sigma sizing or run_tick_backtest's signature.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Self-review notes (for the plan author, not a task)

- **Spec coverage**: Goal 1 (stability check) → Task 1. Goal 2 (quantile sweep)
  → Task 2. Goal 3 (tail-shape feature) → Task 3. Non-goals (no `entry_k`/`sl_k`
  retuning, no richer sigma features, no `run_tick_backtest` signature change,
  no pytest) are respected by all three tasks — confirmed no task touches
  `meta_label_straddle.py`.
- **No placeholders**: every step has literal, complete code or literal
  commands with expected output. BACKLOG.md entries instruct pasting *actual*
  printed output (which doesn't exist until the code runs) rather than
  asserting specific numbers ahead of time — this is a data-recording
  instruction, not a plan placeholder.
- **Type consistency**: `fit_wfo_quantile_robust(X, y, quantile=...)` signature
  used identically across all three tasks. `run_tick_backtest`'s
  `sigma_override`/`sig_thresh`/`sig_thresh_hi` parameters used identically.
  `fit_meta_label_wfo(df, feat_cols=...)` and `_option_b_net_per_fill(df,
  threshold)` used identically. Task 3's `ratio_by_ts` join key (`str(ts[i])`)
  matches `run_tick_backtest`'s own trade-row `"ts"` column format exactly,
  verified against `meta_label_straddle.py`'s source.
