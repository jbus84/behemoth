# Intraday cross-sectional FX basket book — ERA RunSpec

**Date:** 2026-06-06
**Status:** Design approved, pending implementation plan
**Branch:** `worktree-era-basket-cross-sectional`

## Motivation

Single-pair, time-series tick scalping (ERA directional / fair-price) is structurally
disadvantaged for retail: the edge is latency, and the cost (spread) dominates the signal.
The pivot is to a **cross-sectional** approach — rank a universe of pairs against each other
at a moment and trade the *relative* ordering, long the top and short the bottom, held
market-neutral. The edge becomes **breadth across many weak, diversified bets** rather than
speed on one.

Intraday-specific caveats (established in brainstorming):

- The slow factors (carry, value) are flat intraday. What survives is cross-sectional
  **reversal/momentum** and **statistical lead-lag**.
- The binding constraint is **signal-per-unit-turnover net of realistic spread**, not
  predictive R². Turnover control (banded rebalancing) and fill style (passive vs
  aggressive) determine viability.
- **Construction trap:** a naive basket of USD pairs is secretly one big USD bet. The
  framework's `usd_sign` alignment already converts each pair to *non-USD-currency strength*,
  so a long-top/short-bottom basket over `xs_ret_z` is **dollar-neutral by construction**.

## Relationship to existing framework

The existing `era_xs` (`scripts/era_scalp/era_xs.py`) does cross-sectional work in a narrow
form: it picks **one target symbol**, measures its dislocation vs a peer basket, and fades it
as a **single-leg, USD-aligned** trade. This design adds a **sibling** family — a true
**long/short basket book** — as a new RunSpec. `era_xs` stays untouched; the engine can
search both families independently.

Everything downstream of the per-trade net frame is reused unchanged: `run_search_rich`,
`edge_verdict`, monthly net, temporal robustness, DSR / deflated selection, effective-m Šidák.

## Decisions (locked in brainstorming)

| Decision | Choice |
|---|---|
| Construction | Basket book as a **new RunSpec**; single-leg `era_xs` kept intact (both searchable). |
| Signal source | **Seed canonical** factors (reversal, relative momentum, lead-lag), then PUCT evolves. |
| Cost/execution | **Both** fill assumptions as a toggle; **aggressive gates the verdict**, passive reported alongside. |
| Holding model | **Periodic rebalance at horizon h** for v1; isolated behind a strategy hook so a continuous banded mark-to-market can be swapped in later without reworking the verdict layer. |

## Architecture

New module `scripts/era_scalp/era_basket.py` exposing `basket_spec(...) -> RunSpec`.

### 1. Data — panel builder

`build_basket_panel(...)` produces a `BasketSplit` aligned on `close_ts` across all
`CROSS_SYMBOLS`:

- `r` — `(n_bars, n_sym)` USD-aligned `xs_ret_z` for ranking (reuses existing alignment).
- `y_fwd_panel` — `(n_bars, n_sym)` each symbol's `y_fwd_pips_h{h}`.
- `cost_panel` — `(n_bars, n_sym)` each symbol's `cost_est_pips`.
- `names`, `test_month`, `hour`.

Reuses `get_or_build_cross_symbol_frame`'s alignment; the new work is gathering per-symbol
`y_fwd`/`cost` into a panel rather than target-only. (Today's `scripts/era/load_splits.py`
carries all symbols' `xs_ret_z__<sym>` but only the *target's* `y_fwd`/`cost`.)

### 2. Program contract — symmetric context

New `BasketContext` (symmetric, **no `target`**): `r`, `names`, `hour`, plus the convenience
accessors a cross-sectional program needs (per-bar dispersion, per-symbol columns). A program
implements:

```python
def score(ctx) -> np.ndarray  # shape (n_bars, n_sym), cross-sectional score per bar
```

New `required_fn = "cross_score"` with a basket `run_program` / `causality_probe` wrapper that
mirrors how `era_xs` wraps the sandbox. The causality probe must confirm the program reads no
forward/label data and is shift-invariant in the way a cross-sectional scorer should be.

### 3. score_frame — periodic rebalance, dollar-neutral, banded, cost-toggled

Given program output `scores (n_bars, n_sym)`:

1. **Non-overlapping stepping:** iterate rebalance bars in blocks of `h` bars, so successive
   forward-return windows do not overlap (overlap would inflate autocorrelation and bias
   DSR / temporal-robustness).
2. **Ranking → weights:** cross-sectionally rank `scores` at each rebalance bar; long top-k
   `+1/k`, short bottom-k `−1/k` ⇒ `Σ w = 0` (dollar-neutral).
3. **Band (turnover lever):** only change a symbol's weight when its rank move exceeds the
   no-trade band; otherwise carry the prior weight.
4. **P&L:** gross per rebalance `= Σ_i w_i · y_fwd_panel[t, i]`;
   `cost = turnover · per_leg_cost`, where `turnover = Σ_i |w_i(t) − w_i(t_prev)|`.
5. **Fill toggle** `fill_mode ∈ {aggressive, passive}`:
   - `aggressive` — full `cost_panel` spread (cross-the-spread).
   - `passive` — earn a fraction of spread (configurable, e.g. half-spread), modelling
     passive limit fills where the signal is not time-critical.
   - **Aggressive is the gating verdict**; passive is reported alongside.
6. **Optional `session` gate:** restrict rebalance bars to liquid hours (e.g. London/NY
   overlap) via the `hour` array.

Returns `DataFrame{net, test_month}` — one row per rebalance — feeding the existing verdict
machinery unchanged.

### 4. Holding-model hook ("design for both")

The P&L step (4 above) is isolated behind a `holding_model` strategy function. Periodic
rebalance is v1. A continuous banded mark-to-market can be substituted later; it would only
require per-bar path returns added to the panel and would reuse the same verdict layer.

### 5. Seeds (canonical, then evolve)

Three seed programs over `BasketContext`, seeded into the RunSpec exactly as `era_xs` seeds
its residual programs:

- **Cross-sectional reversal** — `score = −(recent xs_ret_z)` (fade relative winners).
- **Relative momentum** — `score = trailing cumulative xs_ret_z` (ride relative winners).
- **Lead-lag** — peer-led prediction of the laggard (Hasbrouck-style).

PUCT recombines/mutates from these. Research-idea prompts mirror the `era_xs` `RESEARCH_IDEAS`
pattern, framed for symmetric cross-sectional scoring.

## Testing strategy

- **Panel alignment:** `build_basket_panel` aligns all symbols on `close_ts`; no row leaks a
  future bar; per-symbol `y_fwd`/`cost` correctly placed.
- **Dollar-neutrality:** weights sum to ≈0 at every rebalance.
- **Band reduces turnover:** larger band ⇒ monotonically lower turnover.
- **Cost monotonicity:** `passive_cost < aggressive_cost` for identical weights/turnover.
- **Non-overlap stepping:** rebalance windows do not overlap for given `h`.
- **Seeds execute + pass causality probe.**
- **score_frame determinism:** identical inputs ⇒ identical net frame.
- **Characterization oracle:** pin v1 basket P&L on a fixed slice so later refactors are safe.

## Out of scope (YAGNI)

- Continuous banded mark-to-market P&L (hook left, not built).
- Rank-proportional / volatility-scaled weighting (top-k/bottom-k only for v1).
- Carry/value factors (flat intraday).
- Expanding the symbol universe beyond `CROSS_SYMBOLS`.

## Open questions for plan stage

- Default `k` (legs per side) given the 6-symbol universe — likely `k=2` (long 2 / short 2,
  middle 2 flat) vs `k=1`.
- Default band width and passive half-spread fraction — to be set conservatively and
  documented; not tuned to the holdout.
- Whether the session gate is on by default or a search-time parameter.
