# ERA fair-price prediction — design

- Status: Proposed
- Date: 2026-05-31
- Relates to: `scripts/era_scalp/` (directional scalping = negative result PR #280; range-harvest
  PR #281), `scripts/era/` (ERA engine). This is a third ERA variant — a **prediction** target,
  not a trading P&L.

## Goal

Use the ERA loop to discover a causally-valid estimator of **fair price** — specifically the
per-bar **mispricing** `(fair − mid)` — scored by its out-of-sample **information coefficient**
(correlation with the realized de-noised future) over thousands of samples. Not a next-tick
direction bet and not a trade P&L: a calibrated estimate of the efficient price, decoupled from
execution cost.

## Why this is the right question

Observed `mid = efficient_price (martingale, ~unpredictable) + transient microstructure noise
(mean-reverting, predictable)`. So:

- A **de-noised future** `y_fair[t] = mean(mid[t+1..t+W])` averages out the noise →
  `y_fair ≈ efficient_price_now`.
- `realized_dev[t] = (y_fair[t] − mid[t]) / pip ≈ −noise[t]` — the current transient mispricing,
  which **is** predictable from causal microstructure features (this is the micro-price idea).
- A program's `fair(ctx)` prediction is judged by the **information coefficient (IC)** —
  correlation between predicted and realized deviation — over the whole sample.

This sidesteps everything that killed the trading framings: the evaluation is a robust
statistical IC over thousands of samples, decoupled from spread/cost. A validated fair-value
estimate is also foundational — it is the band center for range-harvest and the mean for
reversion — and a positive-IC estimate is itself a fade signal (whether the mispricing beats
cost is a separate downstream question).

Literature: Stoikov (2018) micro-price; Hasbrouck efficient price / information shares; Roll
(1984) bid-ask bounce; Cont-Kukanov-Stoikov (2014) OFI; Sirignano-Cont (2019) price formation;
López de Prado (2018) purged/embargoed CV.

## Architecture (add a `fair` mode to `scripts/era_scalp/`)

Reuse unchanged: the `scripts/era/` engine (`puct`, `select.bh_fdr`, `llm` with `rules=`),
`era_scalp/context.FeatureContext`, `era_scalp/sandbox` (`run_program`/`causality_probe` with
`required_fn="fair"`). New files in `scripts/era_scalp/`:

- `fair_harness.py` — IC scoring: `forward_dev`, `info_coefficient`, `fair_node_score`, `ic_pvalue`, `fair_diagnostics`.
- `fair_score.py` — `FairSplitData`, `FairScorer` (sandbox + causality + IC over a W grid).
- `fair_seeds.py` — `FAIR_SEED_PROGRAMS`, `BASELINE_SEED_NAMES`, `RESEARCH_IDEAS`.
- `fair_prompt.py` — `FAIR_RULES`, feature menu.
- `run_era_fair.py` — driver.
- `load_splits.py` — add `FairSplitData` + `build_fair_splits` (mid + W-embargo).

The directional and range-harvest modes are untouched.

## Program contract

`fair(ctx) -> np.ndarray`: per-bar **predicted mispricing** `(fair − mid)` in **pips**
(sign + magnitude; `np.nan` = abstain on that bar). Same causal `FeatureContext`
(single-symbol microstructure) and the same causality probe.

## IC harness (`fair_harness.py`)

Inputs: a program's per-bar `pred_dev` (pips), the split-side `mid` (price), `pip`, and the
swept window `W`.

```text
y_fair[t]      = mean(mid[t+1 .. t+W])          # forward de-noised price (vectorised, cumsum)
realized_dev[t]= (y_fair[t] - mid[t]) / pip      # last W bars have no full window -> NaN
mask           = isfinite(pred_dev) & isfinite(realized_dev)
IC             = pearson_corr(pred_dev[mask], realized_dev[mask])   # NaN if <30 pts or zero var
n_eff          = mask.sum()
node_score     = abs(IC) * sqrt(n_eff)           # continuous; sign-agnostic during discovery
```

- `fair_node_score(pred_dev, mid, pip, W_grid)` = best `node_score` over `W_grid`
  (e.g. `{20, 60, 200}`), so the search is not penalised by the sign convention or W choice.
- `ic_pvalue(IC, n)` — two-sided p from `t = IC*sqrt(n-2)/sqrt(1-IC**2)` via the normal approx
  (no scipy; `math.erfc`), `1.0` when `n < 30` or `|IC|>=1`.
- `fair_diagnostics(...)` returns: `IC`, `n_eff`, `ic_by_month` consistency
  (fraction of months with same-sign IC), `mean_abs_pred_pips`, `dev_sign_hitrate`.

## Seeds — the literature (`fair_seeds.py`)

All causal, numpy-only, emit `(fair − mid)` in pips. Fused by PUCT recombination.

| Seed | Literature | Mechanism |
|---|---|---|
| `ewma_denoise_dev` | Hasbrouck efficient price; low-pass filtering | relative path `p = cumsum(vel_pips_h1)`; dev = EWMA(p) − p (the level cancels) |
| `bounce_reversal_dev` | Roll (1984) bid-ask bounce | dev = −k · recent return (`vel_pips_h1`) — transient overshoot reverts |
| `microprice_imbalance_dev` | Stoikov (2018) micro-price | dev ∝ tick-position/flow imbalance (`hl_pos_delta_tick`, `bar_return_sign`, `tick_volume`) |
| `trailing_anchor_dev` | mean-reversion / VWAP anchor | relative path `p = cumsum(vel_pips_h1)`; dev = trailing-mean(p, W) − p |
| `ofi_adjusted_dev` | OFI (Cont-Kukanov-Stoikov); Sirignano-Cont | signed order-flow tilt: persistent (fair moved) vs transient (overshoot) |

**Level-free by construction:** programs predict the *deviation* in pips from causal features
only — returns (`vel_pips_h1`) and microstructure — never an absolute price. The "denoise" and
"anchor" estimators use a *relative* path `cumsum(vel_pips_h1)` (an arbitrary-origin price proxy);
subtracting its own EWMA/trailing-mean cancels the origin, so the result is a stationary pip
deviation. This is why programs do not need (and are not given) the raw `mid` — the harness owns
`mid` solely to build the label.

`BASELINE_SEED_NAMES` = `(ewma_denoise_dev, bounce_reversal_dev, microprice_imbalance_dev,
trailing_anchor_dev)` (rediscovery tracer). `RESEARCH_IDEAS` name each mechanism + paper and
include an explicit combine instruction ("blend an EWMA-denoised fair with an imbalance tilt and
a bounce correction"). `FAIR_RULES` states the contract (predict mispricing in pips, sign =
expected reversion of mid toward fair), the causal-time-axis rule + probe warning, the ~50k-bar
/ 3×-run vectorisation note, and the ingredient menu.

Note on `mid` availability to programs: programs see only `FeatureContext` (the causal feature
whitelist). They do NOT get raw `mid`/prices (non-stationary); they estimate the *deviation*
from microstructure features. The harness owns `mid` (split-side) for building the label.

## Splits + significance (`load_splits.py`, driver)

- `FairSplitData(X, names, hour, mid, test_month)` — `mid = (close_bid+close_ask)/2`. The forward
  target is computed in the harness per `W` from `mid` (vectorised), not precomputed.
- **Embargo:** trim `max(W_grid)` bars from the tail of train and validation (forward target needs
  W future bars); holdout tail naturally yields NaN realized_dev and is dropped by the mask.
- Splits: train 2018-2023, validation 2024 (capped to recent `--score-max-bars`, default 50000),
  holdout 2025-2026 (full).
- `run_era_fair.py` mirrors the other drivers: seed forest → PUCT (mutate + recombine,
  `rules=FAIR_RULES`) scored on validation → top-N re-scored on full holdout → per-program holdout
  IC → two-sided p → `bh_fdr` survivors → diagnostics report with `summarize_rejections`. Flags:
  `--symbol --parquet --budget --no-baseline-seeds --holdout-top --score-max-bars`.

## Evaluation plan

Fast loop: per-program validation `node_score` (`|IC|·sqrt(n)` best over W). Final selection =
full-holdout IC, two-sided BH-FDR over the explored set, plus IC-by-month consistency. A surviving
fair-value estimator is a *prediction* result; turning it into a *trade* (does the predicted
mispricing exceed cost?) is a separate downstream step, out of scope here.

## Testing

- `test_fair_harness` — `forward_dev` cumsum matches a naive forward-mean reference; a program
  that returns `realized_dev` itself scores IC≈1; a random program ≈0; `|IC|` symmetry
  (sign-flipped pred → same node_score); `ic_pvalue` small for high IC, ~1 for n<30; `ic_by_month`.
- `test_fair_seeds` — 5 seeds present, run, **causal**, emit finite pip deviations; baselines present.
- `test_fair_prompt` — `FAIR_RULES` covers the mispricing contract + causality + ingredients;
  feature menu excludes `y_fwd`.
- `test_load_splits_fair` — `mid` built from bid/ask; W-embargo trims the tail; no leakage columns
  in `FeatureContext.names`.
- `test_fair_integration` — `select_seed_programs` ablation; `finalize_selection` BH-FDR on IC
  p-values (a high-IC program survives, a zero-IC one does not); mocked-writer `run_search`.
- Reuse `era_scalp` context/sandbox/causality + `era` engine tests.

## Consequences

- A prediction-quality target (IC), robust over many samples and decoupled from execution cost —
  the cleanest evaluation in the investigation and the foundation for the trading variants.
- The predictable component (transient noise / mispricing) is targeted directly, not the
  martingale (direction).
- Overlapping-label inflation handled by the `max(W)` embargo + two-sided BH-FDR.
- Open risk: a positive IC does not imply a tradeable edge (the predictable mispricing may be
  smaller than the spread); that is a deliberate downstream question, not this spec's claim.
