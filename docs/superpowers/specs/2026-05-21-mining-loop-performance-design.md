# Mining-Loop Performance — Vectorise + Parallelise + Batched Baseline

**Date:** 2026-05-21
**Status:** Approved (design)
**Author follow-up to:** PR #195 (perf draft, still open) — this design supersedes
the `precomputed=` protocol approach. PR #195 should be closed once this lands.

## Problem

`make retrain-all` is single-threaded across every dimension. With this
session's PRs the mining loop now iterates 11 families × 6-144 params ×
15 regimes × 3 bar_ticks × 6 symbols, and per candidate runs a 200-draw
random-entry baseline. On EURUSD 100-tick (~2.2 M bars) the cross-symbol
families I added in PRs #199-#201 carry per-bar Python loops that are
catastrophic at that scale. Estimated end-to-end retrain wall-clock with
the current code: many hours.

Polars was floated as the fix; pushback below.

## Why not Polars

1. **Bottleneck isn't DataFrame ops.** Every family does
   `pd.to_numeric(col).to_numpy()` at the start, then operates on numpy
   arrays for the entire hot path. Polars replaces a one-time
   millisecond conversion with itself; it does nothing for the
   per-entry numpy work that follows.
2. **Polars excels at SQL-shaped aggregation and lazy planning.** The
   mining loop is per-bar imperative numerical: rolling regressions,
   barrier-touch step searches, per-bar rank. These do not map cleanly
   to Polars expressions.
3. **Polars' real win is parquet I/O and the velocity-build stage**
   (Stage 0/1) — already cached, not the loop being optimised here.
4. **Migration cost is huge.** Every family, helper, and test uses
   `pd.DataFrame`. Zero Polars imports today. Hundreds of touched lines
   for ~0-10% speedup on the mining loop.

## Scope (approved)

Three independent items in one PR or three small PRs:

1. Vectorise the per-bar Python loops in `DollarFactorResidualFamily`
   and `DispersionRankFamily`.
2. Process-pool across symbols via a new orchestrator script.
3. Vectorise `random_entry_baseline` to call `measure_gross` once per
   candidate instead of 200 times.

Combined estimated speedup: ~4-12× wall-clock on `make retrain-all`. The per-item factors (≥50×, ≥15×, ≥3× on individual inner ops) do not multiply end-to-end: items 1+3 act inside the mining loop, item 2 parallelises across 6 symbols, and unchanged post-mining stages (audit, docs-contract, mkdocs build) cap the total per Amdahl's law.

## Out of Scope

- Polars migration.
- Per-bar_ticks pool, per-family pool, Numba on OCO barrier loops —
  deferred until after this pass is measured.
- Stage 0/1 (tick download, velocity build) — already off the hot path.
- Protocol changes to `MiningFamily` — items 1+3 work entirely within
  the current `(frame, entries, params)` contract.

## Design

### Item 1 — Vectorise cross-symbol families

#### `DollarFactorResidualFamily._rolling_regression`

Current (scripts/mining_family.py, ~lines 880-925): Python
`for t in range(window, n)` loop computing per-bar OLS of target's
USD-aligned `ret_z` on `mkt_loo`, plus σ of residuals. At n=2.2M this is
~2.2M Python iterations.

Vectorised replacement:

- Build `r` and `m` arrays once (already done).
- Compute rolling means in O(n) numpy:
  - `mean_r[t]`  = `pd.Series(r).rolling(window).mean()`
  - `mean_m[t]`  = `pd.Series(m).rolling(window).mean()`
  - `mean_rm[t]` = `pd.Series(r * m).rolling(window).mean()`
  - `mean_r2[t]` = `pd.Series(r * r).rolling(window).mean()`
  - `mean_m2[t]` = `pd.Series(m * m).rolling(window).mean()`
- Derive closed-form:
  - `var_m   = mean_m2 - mean_m**2`
  - `cov_rm  = mean_rm - mean_r * mean_m`
  - `β       = cov_rm / var_m` (NaN where `var_m <= 0`)
  - `α       = mean_r - β * mean_m`
  - `σ²      = mean_r2 - 2α·mean_r - 2β·mean_rm + α² + 2αβ·mean_m + β²·mean_m²`
  - `σ       = sqrt(max(σ², 0))` (clamp for numerical floor)
- Shift by 1 so the fit window for bar `t` uses bars strictly before
  `t` (current code already excludes bar `t`'s own row by indexing
  `[lo:t]`; the rolling-window pattern aligns with shift(1) at the
  array level).
- `eps[t] = r[t] - α[t] - β[t] · m[t]`, `z[t] = eps[t] / σ[t]` —
  vectorised final step.

The fit window for bar `t` must include bars `[t - window, t)` — pandas
rolling with `.shift(1)` after `.mean()` achieves exactly this.

#### `DispersionRankFamily._per_bar_rank_and_side`

Current (scripts/mining_family.py, ~lines 1135-1160): Python
`for i in range(n)` loop calling `np.argsort` per row on a 6-column
matrix. At n=2.2M, that's 2.2M argsort calls.

Vectorised replacement:

- Build the (n, 6) matrix once with target USD-aligned in the last
  column (deterministic tie-breaking unchanged).
- `desc_order = np.argsort(-arr, axis=1, kind='stable')` → (n, 6) of
  column indices sorted by descending value within each row.
- `rank = np.argsort(desc_order, axis=1) + 1` → ranks 1..6 per row.
- `target_rank = rank[:, -1].astype(float)` (target column is index 5).
- `target_rank[~np.isfinite(arr).all(axis=1)] = np.nan` to preserve
  NaN-row behaviour.

One pass; no Python loop.

#### Parity tests (item 1)

For each family, a synthetic 1000-bar 6-symbol fixture is built. The
old looped implementation is kept as a private `_*_loop` reference for
the test only (deleted after merge if confidence holds). Tests assert
`np.allclose(vectorised, looped, rtol=1e-6, equal_nan=True)` for:

- `_rolling_regression`: `alpha`, `beta`, `sigma`, `eps`, `z` arrays.
- `_per_bar_rank_and_side`: `target_rank` array.

`rtol=1e-6` rather than `1e-9` accommodates the closed-form σ²
(catastrophic-cancellation risk when sample variance is near zero —
clamped via `max(σ², 0)`).

### Item 2 — Parallelise across symbols

New file `scripts/retrain_all_parallel.py`:

- CLI: `--symbols S1,S2,...` (default = `REBUILD_SYMBOLS`),
  `--max-workers N` (default 6), `--eval-end-month YYYY-MM` passthrough,
  `--log-dir /tmp/retrain` (per-symbol log files).
- Uses `concurrent.futures.ProcessPoolExecutor(max_workers=N)`. Each
  worker subprocess invokes `uv run python scripts/onboard_symbol.py
  --symbol $SYM --skip-data --skip-docs --skip-registration
  --model-export-dir models/oco`, captures combined stdout/stderr to
  `{log_dir}/{symbol}.log`, returns `(symbol, exit_code, log_path)`.
- Parent process classifies each result via `classify_retrain_outcome.py`
  (existing), prints per-symbol outcome banners in deterministic order
  (results sorted by `REBUILD_SYMBOLS` order, not completion order),
  prints the unified summary, exits 1 if any symbol failed.
- After all symbols complete, parent runs the post-mining serial
  stages (`audit_data_reliability.py`, `docs-contract`, `mkdocs build`)
  unchanged. These stay sequential because they depend on all symbols
  having finished.

`Makefile` change: `retrain-all` body becomes
`uv run python scripts/retrain_all_parallel.py --max-workers $(or $(MAX_WORKERS),6) $(if $(EVAL_END_MONTH),--eval-end-month $(EVAL_END_MONTH),)`
followed by the existing audit / docs-contract / mkdocs lines. The
`clean-mining-outputs` precondition from PR #205 is preserved as-is.

#### Memory budget

Each worker process holds its target's velocity frame in RAM plus —
for cross-symbol families — all 5 peer frames via
`build_cross_symbol_frame`. Empirical from
`data/analysis/tick_velocity/`: 100-tick frames are 1.4-2.5 M rows ×
~20 columns ≈ 350-500 MB per loaded frame. 6 frames per worker ≈
2.5-3 GB peak. 6 workers ≈ 15-18 GB peak. On a 32 GB Mac: comfortable.
On a 16 GB Mac: cap with `--max-workers 3` (Makefile env var documented
in help).

#### Output legibility

Without coordination, six concurrent workers would interleave stdout
into incomprehensible output. Solution: per-symbol log file +
deterministic post-completion replay. Parent's live stdout shows only
worker start/finish lines (`[start EURUSD pid=…]`, `[done EURUSD
exit=0 elapsed=482s]`) until all complete, then a per-symbol summary
section printing the last ~30 lines of each log in `REBUILD_SYMBOLS`
order. Full logs remain at `/tmp/retrain/{symbol}.log` for inspection.

#### Worker failure handling

If a worker subprocess exits non-zero, the orchestrator records the
failure but does not cancel sibling workers. Final summary marks the
symbol `FAILED` and the exit code is 1. The post-mining audit/docs
stages still run on whatever did succeed, so partial recovery is
possible without a re-run.

### Item 3 — Batched random-entry baseline

`scripts/mining_random_baseline.py`'s `random_entry_baseline` becomes:

```python
draws = np.stack([
    rng.choice(n_rows, size=n_entries, replace=False)
    for _ in range(int(n_draws))
])  # shape (n_draws, n_entries)
gross_flat = np.asarray(
    family.measure_gross(frame, draws.ravel(), params),
    dtype=float,
)
gross_per_draw = gross_flat.reshape(n_draws, n_entries)
with np.errstate(invalid="ignore"):
    control = np.nanmean(gross_per_draw, axis=1)
control = control[np.isfinite(control)]
```

Two characteristics matter:

1. **No protocol change.** Every family's `measure_gross` already
   accepts arbitrary integer entry arrays (it's the contract the
   baseline depends on); they will accept `draws.ravel()` (a
   length-`n_draws · n_entries` array) and return a length-matching
   gross array.
2. **One call instead of 200.** Family-side overhead (cache lookup,
   `pd.Series.reindex`, `np.isfinite` masking, numpy fancy-indexing)
   is paid once per candidate instead of 200 times.

The draw-generation Python loop stays — `np.random.Generator.choice`
without replacement doesn't have a clean batched form, and it's
already millisecond-scale per call.

#### Parity test (item 3)

For each family, run the old loop and the new batched implementation
on the same `rng` seed against a small fixture. Assert
`np.allclose(control_loop, control_batched, equal_nan=True)`. Same seed
→ same draws (because draw generation didn't change) → bitwise-identical
result.

## Components

| File | Change | Lines |
|---|---|---|
| `scripts/mining_family.py` | Vectorise `_rolling_regression` and `_per_bar_rank_and_side` | ~80 |
| `scripts/mining_random_baseline.py` | Batched `measure_gross` call | ~25 |
| `scripts/retrain_all_parallel.py` (new) | Process-pool orchestrator | ~150 |
| `Makefile` | `retrain-all` calls the new orchestrator | ~5 |
| `tests/test_mining_family.py` | Parity tests for vectorised functions | ~60 |
| `tests/test_mining_random_baseline.py` | Parity test for batched baseline | ~30 |
| `tests/test_retrain_all_parallel.py` (new) | Pool smoke + failure-isolation tests | ~70 |

## Data Flow

```
make retrain-all
  └── clean-mining-outputs (from PR #205, unchanged)
  └── scripts/retrain_all_parallel.py --max-workers 6
        │
        ├── ProcessPoolExecutor
        │     ├── worker[EURUSD] → uv run onboard_symbol.py --symbol EURUSD ...
        │     │   (Stage 2a mining uses VECTORISED cross-symbol families,
        │     │    BATCHED random_entry_baseline)
        │     ├── worker[GBPUSD] → ...
        │     └── worker[USDJPY|USDCHF|AUDUSD|USDCAD] → ...
        │
        ├── ordered per-symbol summary + classify outcomes
        └── exit 0 / 1
  └── scripts/audit_data_reliability.py (serial, unchanged)
  └── make docs-contract (serial, unchanged)
  └── uv run mkdocs build --strict (serial, unchanged)
```

## Error Handling

- **Item 1**: parity tests catch any algebraic drift between the
  closed-form and the per-window calculation. NaN propagation matches
  the looped version exactly (same input NaNs ⇒ same output NaNs).
- **Item 2**: a worker subprocess crashing leaves sibling workers
  untouched. The orchestrator records the exit code, classifies the
  symbol `FAILED`, prints the failure section first in the summary, and
  exits 1 at the end. Partial results on disk are preserved (cleanup
  happened at the very start under PR #205's pre-step).
- **Item 3**: same NaN semantics as the looped version via
  `np.nanmean` over `axis=1`. Same RNG seed yields bitwise-identical
  output.

## Testing

Existing tests must continue to pass unchanged:
`uv run pytest tests/test_mining_family.py
tests/test_oco_candidate_family_allowlist.py
tests/test_tick_opportunity_mining.py tests/test_cross_symbol.py
tests/test_mining_random_baseline.py -q` (currently 108+ passed).

New tests:

- `test_dollar_residual_rolling_regression_vectorised_matches_loop` —
  rtol=1e-6 on a 500-bar synthetic fixture, all 5 output arrays.
- `test_dispersion_rank_per_bar_rank_vectorised_matches_loop` —
  exact-equal on a 500-bar synthetic fixture.
- `test_random_entry_baseline_batched_matches_loop` — same seed, same
  result, for at least one each of: a directional family, a
  cached-precompute family (OCO), and a cross-symbol family.
- `test_retrain_all_parallel_collects_outcomes` — mock worker spawn,
  verify ordered summary.
- `test_retrain_all_parallel_isolates_worker_failure` — one worker
  returns exit 1; orchestrator records FAILED for it and PASS/NO_TRADE
  for siblings; final exit is 1.

## Success Criterion

Three measurable gates, each independently verifiable:

1. **Per-component microbenchmark**: on a 100 000-bar synthetic frame,
   `DollarFactorResidualFamily._rolling_regression` runs ≥50× faster
   than the loop version; `DispersionRankFamily._per_bar_rank_and_side`
   runs ≥100× faster than the loop version. Both measured via
   `pytest-benchmark` or a simple `time.perf_counter` test fixture.
2. **Baseline-batching speedup**: `random_entry_baseline` with 200
   draws on a 10 000-row frame runs ≥5× faster than the per-draw loop
   for a representative cached-precompute family (OCO).
3. **End-to-end correctness**: `make retrain-all` with the changes
   produces per-family CSVs that match a from-scratch sequential run
   (same RNG seed) bitwise. PR #203's deep-report on the parallel-run
   output equals the deep-report on the sequential-run output.

Wall-clock improvement of `make retrain-all` is reported in the PR but
not gated, since it varies by hardware. Expected envelope: 4-12× on a
6-core machine (Item 1 is per-family local, Item 2 is the parallelism
multiplier, Item 3 is per-candidate inner-loop speedup; Amdahl on the
unchanged post-mining audit/docs stages caps the total).

## File Map

- `scripts/mining_family.py` — vectorise two functions.
- `scripts/mining_random_baseline.py` — batched call.
- `scripts/retrain_all_parallel.py` — new orchestrator.
- `Makefile` — `retrain-all` body redirected.
- `tests/test_mining_family.py` — 2 parity tests.
- `tests/test_mining_random_baseline.py` — 1 parity test.
- `tests/test_retrain_all_parallel.py` — 2 orchestrator tests.
- `docs/superpowers/specs/2026-05-21-mining-loop-performance-design.md` —
  this file.

## Open Risks

1. **`subprocess.run` cost of spawning `uv run` per worker** — ~1-3 s
   warm-up for venv resolution. Negligible vs the ~30-60 min per
   symbol the worker actually does.
2. **macOS multiprocessing start method** — Python 3.12 defaults to
   `spawn` on macOS. Spawn cost is small; the design uses subprocess
   not multiprocessing-fork-Python so this is moot anyway.
3. **σ² closed-form precision** — addressed by clamping `σ² = max(σ², 0)`
   and rtol=1e-6 on parity. If real-data σ ever rounds to zero in a
   way the loop didn't, fall back to per-window `np.std` on the
   affected bars (a numpy `.where(σ² < 1e-12, np.std-fallback, ...)`).
   This is a known-good fallback; not pre-emptively added because the
   loop already had its own near-zero floor.
