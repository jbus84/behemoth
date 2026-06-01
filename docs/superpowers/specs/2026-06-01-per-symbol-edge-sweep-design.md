# Per-symbol edge sweep (select-then-confirm) — design

- Status: Proposed
- Date: 2026-06-01
- Relates to: `docs/analysis/era_conditional_response_horizon_matched_2026-05-31.md`. Pooling the score
  across all 5 majors diluted/masked real per-symbol edges (EUR fade @ q99/h400; `vr_conditional` showed
  GBP continuation @ q99/h100). This replaces the pooled scalar with a per-symbol verdict, each symbol
  choosing its own direction + q + h. `scripts/era_scalp/`.

## Goal

For each major, discover whether it has a credible edge at ITS OWN (direction ∈ {fade, continue}, q, h),
without the selection inflation that has produced every mirage in this arc. Surface continuation edges
that pooled-fade scoring hid. Report the de-inflated diagnostic panel (trade-weighted raw mean + sample
counts + month-hit), not just the monthly posterior (which we learned can be inflated by low-count
months: EUR h400/q99 posterior +5.9 vs raw +1.78, month-hit 0.65).

## The honesty spine: select on validation, confirm on holdout

Sweeping 5 × 2 × 3 × 3 = 90 cells and reporting "each symbol's best on the holdout" is selection on the
holdout — the knife-edge trap. Instead:

1. **Select on validation (2024).** For each symbol, evaluate all 18 (direction, q, h) cells on the
   *validation* split. Choose that symbol's single setting by the **lower credible bound** of the monthly
   posterior (`EdgePosterior.pooled["lo"]` from a single-symbol `edge_verdict`), subject to a **sample
   guard**: the validation cell must have `n_trades >= MIN_TRADES` (200) and `n_months >= MIN_MONTHS_SEL`
   (6). Cells failing the guard, or for which `edge_verdict` raises (fewer than the model's `_MIN_MONTHS`
   active months), are ineligible. If no cell qualifies, the symbol is reported as "no admissible setting".
   Lower-CI-bound selection rewards magnitude AND confidence and penalises thin/wide cells — anti-knife-edge.
2. **Confirm on holdout (2025–26).** Evaluate that ONE pre-registered (direction, q, h) per symbol on the
   *holdout*, and report the full diagnostic panel. This is a single clean test per symbol — no holdout
   selection.

## Base signal

The fixed fair-dislocation `dev` (from the `fair_fade` seed, which returns `dev = ew - p`). Per symbol it
is computed ONCE on each split's context. The two directions are exact negations:
- `fade`  → `signal = dev`   (bet reversion toward fair; side = sign(dev))
- `continue` → `signal = -dev` (bet the dislocation extends)

`|signal| = |dev|` in both, so the top-q entry selection (`evaluate_trades`) is identical; only the side
differs. This is the clean, interpretable "does this symbol fade or continue at extreme dislocation",
not the learned conditional-response (whose fragility is already established).

## Components

`scripts/era_scalp/per_symbol_sweep.py`:
- `dev_signal(split_data) -> np.ndarray` — run `FADE_SEED_PROGRAMS["fair_fade"]` via `run_program` on a
  `FeatureContext` built from the split; return the `dev` array. (Reuses the canonical fair computation;
  no duplicated EWMA.)
- `cell_net(signal, split_data, symbol, direction, q, h) -> pd.DataFrame` — `evaluate_trades(direction *
  signal, mid, cost, test_month, pip, q, h)` where `direction` is `+1.0`/`-1.0`. Returns the trade frame.
- `diagnostics(net_frame) -> dict` — `n_trades`, `n_months` (`test_month` nunique), `month_hit`
  (fraction of months with positive mean net), `raw_mean` (trade-weighted `net.mean()`).
- `credibility(net_frame, seed=0, fast=False) -> dict | None` — `edge_verdict({"_": net_frame}, ...)`
  with short chains when `fast` (selection: warmup/samples 300/300); returns
  `{p_positive, mean, lo, hi}` from `.pooled`, or `None` if the verdict raises / frame too thin.
- `select_on_validation(signal_v, split_v, symbol, grid) -> dict | None` — loop the 18 cells on
  validation; keep those meeting the sample guard with a non-None credibility; return the cell with the
  max `lo` (tie-break higher `raw_mean`), as `{direction, q, h, val: {...}}`; `None` if none admissible.
- `confirm_on_holdout(signal_h, split_h, symbol, choice) -> dict` — evaluate the chosen cell on holdout;
  return `{**choice, holdout: {**credibility(full), **diagnostics}}`.
- `sweep(symbols, tv_dir, ...) -> list[dict]` — per symbol: `build_trade_splits` ONCE (validation +
  holdout), compute `dev_signal` once per split, select, confirm. Returns the per-symbol results.
- `main()` — CLI (`--symbols`, `--tv-dir`, `--out`) writing the markdown verdict: the headline
  select-then-confirm table + a clearly-labelled exploratory full-holdout-grid appendix per symbol.

Grids: `DIRECTIONS = {"fade": 1.0, "continue": -1.0}`, `GRID_Q = [0.90, 0.95, 0.99]`,
`GRID_H = [100, 200, 400]` (reuse the values from `trade_score`).

Reused unchanged: `build_trade_splits`, `_pip_size`, `FeatureContext`, `run_program`,
`FADE_SEED_PROGRAMS["fair_fade"]`, `evaluate_trades`, `monthly_net`, `edge_verdict`.

## Output (the verdict doc)

Headline table — one row per symbol: chosen direction + q + h (from validation), then holdout
`P(edge>0)`, posterior mean, **trade-weighted raw mean**, `n_trades`, `n_months`, `month_hit`. A symbol
with no admissible validation setting is shown as such. Plus the exploratory appendix (full 18-cell
holdout grid per symbol, labelled "exploratory — not the verdict; selection was on validation").

The verdict states plainly, per symbol: is there a credible holdout edge at the validation-chosen
setting, and is it fade or continuation? Expected (to be confirmed, not assumed): EUR/AUD fade credible;
whether GBP/JPY show a continuation edge that pooling hid is the open question this answers. Reconfirm
the binding caveat: mid-to-mid / flat-cost; tick-exact round-trip cost is the downstream gate.

## Testing

`tests/era_scalp/test_per_symbol_sweep.py` (synthetic `TradeSplitData`, deterministic):
- **directions are exact negations**: `cell_net` with `direction=-1` enters the opposite side of
  `direction=+1` on the same bars (net sign flips for matched entries).
- **diagnostics correct**: on a hand-built net frame, `n_trades`/`n_months`/`month_hit`/`raw_mean` match
  computed-by-hand values; `month_hit` counts a month positive iff its mean net > 0.
- **selection respects the sample guard**: given two candidate cells where the higher-`lo` cell fails the
  trade/month guard and a lower-`lo` cell passes, `select_on_validation` returns the passing one (build
  the frames so the guard is the deciding factor; monkeypatch `credibility` to return fixed `lo` values
  for determinism so the test does not depend on NUTS sampling).
- **select-then-confirm wiring**: `sweep` on a tiny 1-symbol synthetic returns a result whose `holdout`
  block has the expected keys and whose chosen `(direction,q,h)` came from the validation phase
  (monkeypatch `credibility` so validation prefers a specific cell; assert the holdout block evaluates
  that same cell).
- credibility/NUTS itself is already covered by `tests/era_scalp/test_bayes_edge.py`; these tests
  monkeypatch it for determinism and speed.

## Consequences

- A per-symbol, selection-honest map of where each major has an edge and in which direction — the
  successor to the pooled scalar, and the tool that reveals any continuation edge pooling masked.
- No engine/scorer change; pure analysis module reusing the existing harness + Bayesian layer.
- Standing caveat unchanged: holdout-confirmed credibility is necessary, not sufficient; the tick-exact
  realistic round-trip cost gate remains the binding downstream check on whatever survives.
- Decision point AFTER this: take the surviving per-symbol edges (likely EUR/AUD fade ± a continuation
  symbol) to the tick-exact cost gate.
