# Cost-aware per-symbol Bayesian-PUCT search (EUR) — design

- Status: Proposed
- Date: 2026-06-01
- Relates to: the per-symbol sweep (`docs/analysis/era_per_symbol_edge_sweep_2026-06-01.md`, PR #286) —
  EURUSD fade is a real but marginal lean (holdout P=0.889, raw +0.84 pip/trade, 65% months, 31,716
  trades). This is the deferred Phase-2 Bayesian-PUCT, now with realistic round-trip cost in the in-loop
  objective, run per-symbol on EUR. `scripts/era_scalp/`.

## Goal

Let the ERA search (qwen program evolution under PUCT) try to evolve a causal signal program that beats
`fair_fade` on EURUSD, scored by a **robustness-gated, net-of-realistic-cost, confidence-aware**
objective. Make the search policy itself confidence-aware (Thompson sampling over the per-node edge
posterior), A/B'd against the existing rank-based policy so we *measure* whether the policy matters.

**Honest framing.** In every prior mode the search added nothing beyond the literature seeds. The
reasons it might differ now: the scorer is robustness-gated (no knife-edge cells), the objective is
per-symbol (not a diluted 5-pool), and cost is in the loop (no chasing edges that die at cost). The
build includes a **rediscovery control** (search with seeds stripped) and a **must-beat-best-seed**
success bar, so another null is reported as a null — not dressed up.

## Realistic cost model (in-loop objective)

`scripts/era_scalp/cost_model.py`:
```python
COMMISSION_PIPS = 0.06   # Dukascopy round-trip commission (~0.03/side)
SLIPPAGE_PIPS = 0.10     # buffer for adverse fills at extreme-dislocation bars
def realistic_cost(spread_pips: np.ndarray) -> np.ndarray:
    return np.asarray(spread_pips, float) + COMMISSION_PIPS + SLIPPAGE_PIPS
```
Per-bar `spread_pips` comes from the parquet (column exists). `TradeSplitData` gains an optional
`spread_pips: np.ndarray | None = None` field, populated by `build_trade_splits`. `evaluate_trades`
already takes a `cost` arg — the driver passes `realistic_cost(split.spread_pips)` instead of
`cost_est_pips`. No change to `evaluate_trades`.

This is the FAST parametric cost. The heavy tick-exact tooling (`analyze_oco_stop_limit_tickfill.py`,
root-checkout + broker creds per `CLAUDE.md`) is the SUBSEQUENT certification gate on the winner, NOT in
this build.

## Cost-aware per-symbol scorer

`scripts/era_scalp/cost_aware_score.py`:
- `fast_lower_bound(net_frame, z=1.645) -> (lb, mean, se)` — monthly aggregation (`monthly_net`), then
  `mean` = mean of monthly mean-nets, `se` = std / sqrt(n_months), `lb = mean - z*se` (one-sided ~95%).
  Analytic, no NUTS — loop-affordable. Returns `(nan, nan, nan)` if `< 2` months.
- `CostAwarePerSymbolScorer(split_by_phase, symbol, z=1.645)` with
  `score(src, phase="validation") -> (value, mean, se, logs)`:
  run the program once (with causality probe on first use), build realistic-cost trade frames for each
  `(q,h)` in `GRID_Q×GRID_H`, compute `(lb, mean, se)` per cell; **node value** = robustness aggregate
  `mean(lbs) - std(lbs)` (knife-edge-resistant, same philosophy as the merged scorer); the node's edge
  posterior `(mean, se)` for Thompson = the `(mean, se)` of the **cell with the max `lb`** (the
  program's best-robust setting). Program/causality failure → `(-1e6, nan, nan, reason)`.

## Engine: confidence-aware selection (minimal, backward-compatible)

`scripts/era/puct.py`:
- `Node` gains optional `mean: float = 0.0`, `se: float = 0.0` (set by the driver from the scorer).
- `select_thompson(nodes, rng) -> Node` — sample `draw_i ~ Normal(node.mean_i, node.se_i)` (se<=0 →
  use mean), return argmax-draw node. Pure exploration/exploitation via the posterior.
- `puct_search(..., select_fn=select)` — add a `select_fn` param (default = existing `select`), so the
  driver can pass `select_thompson`. Existing callers unaffected.

## Driver

`scripts/era_scalp/run_era_eur.py` (thin; reuses `run_era_fade`'s `propose_program`/`recombine_program`
and `era.puct.puct_search`):
- build EUR splits once; scorer on EUR; seed forest = `FADE_SEED_PROGRAMS` (incl. `fair_fade`,
  `vr_gated_fade`, conditional-response family).
- `run(select_policy ∈ {"rank","thompson"}, budget, with_seeds=True, seed)` — PUCT search on EUR
  validation with the chosen policy; returns the forest. `with_seeds=False` = rediscovery control
  (start from a single trivial root, qwen builds from scratch).
- After search: take top program by validation node value; **confirm on EUR holdout** with full
  `bayes_edge` NUTS on net-of-realistic-cost; report alongside (a) best seed's holdout verdict and
  (b) the rediscovery winner. CLI writes the markdown verdict.

## Validation / success criteria

A/B both policies and the seeds/rediscovery controls. **Search succeeds only if** an evolved program's
net-of-realistic-cost EUR holdout credibility **credibly beats the best seed's** (higher posterior P and
lower-CI bound, on the same realistic-cost basis). Also report whether `thompson` reached a better best
node than `rank` at equal budget (the A/B that settles the policy question). Honest nulls recorded:
"qwen beat no seed"; "thompson == rank"; "best seed net-of-realistic-cost is itself ≤ 0" (i.e. the EUR
edge does not survive cost — the most important possible finding).

## Files

- `scripts/era_scalp/cost_model.py` — NEW (constants + `realistic_cost`).
- `scripts/era_scalp/load_splits.py` — MODIFY (`TradeSplitData.spread_pips`; `build_trade_splits` populates).
- `scripts/era_scalp/cost_aware_score.py` — NEW (`fast_lower_bound`, `CostAwarePerSymbolScorer`).
- `scripts/era/puct.py` — MODIFY (`Node.mean/se`, `select_thompson`, `puct_search(select_fn=)`).
- `scripts/era_scalp/run_era_eur.py` — NEW (driver + CLI).
- Tests: `test_cost_model.py`, `test_cost_aware_score.py`, `test_puct_thompson.py` (+ extend
  `test_load_splits_trade.py` for `spread_pips`).
- `docs/analysis/era_cost_aware_puct_eur_<date>.md` — verdict evidence.

Reused unchanged: `evaluate_trades`, `monthly_net`, `edge_verdict`, `run_program`, `causality_probe`,
`propose_program`/`recombine_program`, `puct_search` core loop.

## Testing

- `realistic_cost`: equals `spread + 0.16` elementwise; vectorised.
- `fast_lower_bound`: on a synthetic frame with known monthly means, `mean`/`se`/`lb` match hand calc;
  `lb < mean`; `< 2` months → nan triple.
- `CostAwarePerSymbolScorer.score`: returns finite `(value, mean, se, logs)` for `fair_fade` on a
  synthetic EUR split; a forward-reading program → `-1e6` + causality reason; value is the robust
  aggregate (monkeypatch `fast_lower_bound` to fixed per-cell values → assert `mean(lbs)-std(lbs)` and
  that `(mean,se)` come from the max-`lb` cell).
- `select_thompson`: with a fixed-seed rng and three nodes whose `(mean,se)` make one dominate, it
  selects the dominant node the large majority of draws; a high-`se` underdog is sometimes explored
  (sampled-argmax behaviour); `se<=0` falls back to mean.
- `puct_search(select_fn=select_thompson)`: runs a toy search to budget and grows the forest (smoke).
- `build_trade_splits` populates `spread_pips` with the right length (extend existing trade-splits test).
- Heavy NUTS/qwen are NOT unit-tested (monkeypatched/stubbed); the real run is the Task-N evidence step.

## Consequences

- A principled, cost-aware, confidence-aware per-symbol search for EUR, with the search *policy* itself
  measured (Thompson vs rank) rather than assumed.
- The single most valuable possible output is honest either way: either an evolved program credibly beats
  the seed net-of-realistic-cost (first time search adds value, and the EUR edge survives realistic
  cost), or it does not (the EUR edge is marginal/again seed-only, and we have a clean cost-aware number).
- Tick-exact certification on the winner remains the final downstream gate (root checkout), out of scope
  here. AUD is a follow-up if EUR clears.
