# Task 5: Walk-forward Model-µ OOS Net-bps Evaluator

**Status:** ✅ COMPLETE

**Commit:** `ebd49a5f` — feat(fx_coint): walk-forward model-mu OOS net-bps evaluator

**Test Summary:** `test_model_oos_pnl_runs_and_scores_oracle` PASSED (all 4 tests in module pass)

---

## Implementation

Added `model_oos_pnl(sym_data, fit_predict, cost=1.0, n_folds=5) -> dict` to `scripts/fx_coint/pnl_walkforward.py`:

- **Interface:** Accepts pre-built per-symbol data dict `sym_data[s] = {"X","y","entry","t1","ret","sw"}` and caller-supplied `fit_predict(train_dict, test_dict) -> mu_test` closure.
- **Walk-forward:** Non-overlapping expanding folds over pooled `entry` timestamps; train rows (`entry < fold_lo`) feed the fit, test rows (`fold_lo <= entry < fold_hi`) evaluated with non-overlap gating.
- **Selection:** Top-decile `|mu|` threshold calibrated per fold on test rows (0.90 quantile); filters to finite mu and returns.
- **Non-overlap:** Reuses existing `greedy_nonoverlap(entry, t1)` to keep only trades with no position overlap.
- **P&L:** `sign(mu) * ret - cost` per trade.
- **Output:** dict keys `{net, folds_pos, sym_pos, n_trades}` (per spec).

## Test

Added `test_model_oos_pnl_runs_and_scores_oracle()` to `tests/fx_coint/test_pnl_walkforward.py`:

- Creates 3000-row oracle predictor (realized return + noise), cost=0.0.
- Verifies output keys and `n_trades > 0`.
- **Result:** PASSED; all 4 module tests pass.

## Quality

- `uv run ruff check scripts/fx_coint/pnl_walkforward.py` — All checks passed.
- No existing functions rewritten; function added cleanly before `marginal_lift()`.

---

## No Concerns

Implementation follows brief spec exactly (interface, walk-forward logic, non-overlap, selection threshold, output keys). Test covers happy path. Function reuses proven `greedy_nonoverlap` and vectorized numpy operations.
