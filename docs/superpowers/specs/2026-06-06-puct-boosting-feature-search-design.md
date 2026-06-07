# PUCT-Guided Boosting Feature Search — Design

**Date:** 2026-06-06
**Branch:** `worktree-era-puct-boosting`
**Status:** Design approved, pending implementation plan.

## Motivation

Symbolic PUCT search and direct statistical analysis have both hit the cost wall on the 6 USD
majors ([[project_retail_fx_edge_cost_wall]]). This is the strongest remaining test of whether
predictive *gross* signal was left on the table for lack of model power: use the PUCT tree as a
**meta-search that builds a boosting system** — it generates literature-seeded feature sets, a
fixed gradient-boosted model consumes them, and the existing cost-aware verdict judges the
result. PUCT becomes LLM-guided automated feature engineering; the GBDT is the learner.

Built as an extension of the unified ERA engine ([[project_era_unified_engine]]) so it reuses
PUCT, the LLM writer, literature seeds, the cost-aware verdict, and the sacred holdout.

## Decisions (locked in brainstorming)

| Decision | Choice |
|---|---|
| What a node builds | **Features only**; a fixed, conservative GBDT (no per-node hyperparam search). |
| Prediction target | **Both**: intraday fair-price dislocation (calibration) + a lower-turnover forward return (real shot). |
| Feature source | **Generate new** literature-seeded feature transforms (not select-from-bank). |
| Overfitting regime | **Extra rigor**: existing guards + purged/embargoed K-fold inside each node + feature-count complexity penalty + separate selection-vs-final validation split; holdout touched once. |
| GBDT library | **CatBoost** (repo standard; `models/oco/*.cbm`). |
| Integration | **Approach A**: new boosting RunSpec extending atomic mode. (Fallback: Approach C — offline feature bank + one GBDT — if per-node training is too slow.) |

## Architecture

### 1. Search node = feature-composition
Reuse the atomic composition structure (`skeleton + operators + params`), but operators are
**feature generators** from a new literature-seeded `FEATURE_CONCEPT_TAXONOMY` (microstructure
constructs: signed-flow imbalance, quote-revision intensity, realized-vol / range regime,
path-dependent reversal, lead-lag ratios, etc.). The rendered source defines:

```python
def build_features(ctx) -> np.ndarray   # shape (n_bars, n_feat), np-only, causal
```

PUCT + the LLM writer propose/recombine feature compositions, reusing the existing
`propose_atomic` / `recombine_atomic` machinery with a feature-generation prompt.

### 2. Two-stage scorer (the one genuinely new component)
- **(a) Untrusted, sandboxed:** run `build_features(ctx)` → feature matrix; **causality-probe**
  it for future-leakage exactly as current signals are probed (no future rows may affect a past
  feature row). This preserves the leakage guarantee — only feature *construction* is sandboxed.
- **(b) Trusted harness:** train a fixed CatBoost (shallow, e.g. depth ≤4, ≤200 rounds) with
  **purged + embargoed K-fold** on the train split, predict the validation split. The prediction
  array flows into the **existing `score_frame`** (quantile-threshold entry, realistic cost
  subtracted) → per-trade net frame → existing verdict layer. The GBDT and labels live only in
  the trusted harness, never in the sandbox.

### 3. Two targets, one search
Two RunSpec configs differing only in target + `score_frame`:
- **Calibration:** intraday fair-price dislocation (predict micro/fair-price residual, trade it).
- **Real shot:** lower-turnover forward return (multi-bar / daily horizon `y_fwd_pips_h{h}`),
  where cost amortizes over the hold.

### 4. Overfitting regime
- Existing engine guards: DSR / deflated selection, temporal robustness, **effective-m Šidák**
  over the node count.
- **Plus, new for boosting:** purged + embargoed K-fold inside each node's training; a
  **feature-count complexity penalty** subtracted from node value (punishes large feature sets);
  a **separate selection-vs-final validation split** — PUCT selects on slice V1, the survivor is
  confirmed on slice V2, and only then is the holdout read once.

### 5. Compute discipline
Per-node GBDT × budget × K folds is the cost driver. Keep the model tiny (depth ≤4, ≤200
rounds, early stopping), use a modest PUCT budget, and **cache feature matrices by composition
hash**. If still too slow, fall back to Approach C (PUCT generates features offline into a bank;
one GBDT trains on the union, selected by importance).

## File structure (anticipated)

| File | Responsibility |
|---|---|
| `scripts/era_scalp/feature_concepts.py` | `FEATURE_CONCEPT_TAXONOMY` + skeletons + `composition_to_features_source` (literature feature operators). |
| `scripts/era_scalp/boosting_sandbox.py` | run/causality-probe for `build_features(ctx)` 2-D feature output. |
| `scripts/era_scalp/boosting_scorer.py` | trusted CatBoost train (purged K-fold) → predict → prediction array; complexity penalty. |
| `scripts/era_scalp/era_boost.py` | `boost_spec(...) -> RunSpec` wiring node → sandbox → scorer → score_frame → verdict; target/horizon configs. |
| `tests/era_scalp/test_boosting_*.py` | per-component + end-to-end tests. |

## Testing strategy
- Feature-composition renders and runs; output shape `(n_bars, n_feat)`.
- Causality probe **rejects** a deliberately leaky feature, **accepts** a causal one.
- Purged/embargoed K-fold produces no train/validation index overlap (with embargo gap).
- Complexity penalty is monotonic in feature count.
- `score_frame` determinism (fixed features + fixed CatBoost seed ⇒ identical net frame).
- Tiny end-to-end search on synthetic data returns a finite verdict.
- Characterization oracle pinning the pipeline's output on a fixed slice.

## Honest expectation (recorded)
This is the strongest available test of "did we leave gross on the table for lack of model
power?" Per all prior evidence the prior is that it **still hits the cost wall** — most likely on
the intraday-fair-price calibration (high turnover, latency-raced). The lower-turnover target is
the only one with a real chance to clear cost. We build it with mirage-proof rigor to *know*,
not because we expect it to clear. A negative result here is itself decisive (rules out "weak
model" as the reason nothing traded). [[feedback_gross_cost_significance_decomposition]] applies:
report gross / cost / significance separately; holdout once.

## Out of scope (YAGNI)
- GBDT hyperparameter search (fixed model only).
- Select-from-bank feature mode.
- New instruments / cross-pairs (separate effort; see [[project_retail_fx_edge_cost_wall]]).
- Walk-forward engine rework (the purged-CV + V1/V2 split is sufficient for v1).
