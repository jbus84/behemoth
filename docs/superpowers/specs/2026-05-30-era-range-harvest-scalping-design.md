# ERA range-harvest scalping — design

- Status: Proposed
- Date: 2026-05-30
- Relates to: `scripts/era_scalp/` (directional scalping — negative result, see
  `docs/analysis/era_scalp_100tick_evidence_2026-05-30.md`), `scripts/era/` (ERA engine),
  the ERA-faithful loop (Nature 2026 / arXiv 2509.06503).

## Goal

Discover a causally-valid, net-of-cost **direction-agnostic range-harvest** scalping
strategy on 100-tick bars via the ERA loop. Instead of predicting *which way* price
moves (shown to be ~coin-flip, hence unprofitable after cost), predict *when* a window
is **range-bound and wide enough to harvest**, deploy a **two-sided maker bracket**, and
let the market pick the side.

## Why this, and why direction-agnostic

The directional variant proved direction is ~50% at 100-tick on EURUSD and loses ~0.59
pips/trade (the spread). Range harvesting sidesteps direction entirely:

- Rest a BUY limit at the lower band edge AND a SELL limit at the upper edge. Whichever
  price hits first fills (**maker → earns the spread instead of paying it**) and *that*
  determines the side — never predicted.
- The prediction problem shifts from direction (unpredictable) to **regime**: will price
  revert from the extreme (harvestable) or break through (loss)? Regime/boundedness and
  realized-range are far more predictable than sign (volatility clustering is a robust
  stylized fact).
- The maker entry is the structural win: the spread — the thing that killed the
  directional attempt — becomes revenue.

Theory/literature grounding: Avellaneda-Stoikov (2008) and Guéant-Lehalle-Fernández-Tapia
(2013) optimal market-making (capture spread, flatten inventory to the reservation
price/center); OU optimal-band trading (Leung-Li 2015; Bertram 2010); realized-range /
vol forecasting (Parkinson 1980; Garman-Klass; Yang-Zhang; HAR-RV, Corsi 2009);
range-vs-trend regime tests (variance ratio, Lo-MacKinlay 1988; Hurst); flow toxicity as
breakout filter (VPIN, Easley-López de Prado-O'Hara; OFI, Cont-Kukanov-Stoikov; Hawkes
bursts, Bacry-Mastromatteo-Muzy); micro-price fair value (Stoikov 2018). Honest evaluation
under overlapping labels: López de Prado (2018) purged/embargoed CV.

## Architecture (Approach A — add a bracket mode to `scripts/era_scalp/`)

Reuse, unchanged: `era_scalp/context.py` (`FeatureContext`), `era_scalp/sandbox.py`
(`run_program`, `causality_probe` — `static_check` already takes `required_fn`), the
`scripts/era/` engine (`puct`, `select`, `llm` with `rules=`), and `era_scalp/harness.py`
`task_score`. The directional code stays as the documented negative result.

New files in `scripts/era_scalp/`:
- `bracket_harness.py` — the two-sided maker-bracket payoff + diagnostics.
- `range_seeds.py` — `DEPLOY_SEED_PROGRAMS`, `BASELINE_SEED_NAMES`, `RESEARCH_IDEAS`.
- `range_prompt.py` — `RANGE_RULES`, deploy-feature menu.
- `range_score.py` — `RangeSplitData`, `RangeScorer` (sandbox + causality + bracket payoff).
- `run_era_range.py` — driver (mirrors `run_era_scalp.py`).
- `load_splits.py` — extend to carry the harness-side price columns + `K`-bar embargo.

## Program contract

`deploy(ctx) -> np.ndarray`: a per-bar **non-directional** score. High = "deploy a
two-sided bracket at this bar"; `np.nan` (or below threshold) = stand aside. No sign / no
direction semantics — the score only gates *when* to harvest. Same causal `FeatureContext`
(single-symbol microstructure) and the same causality probe as the directional variant.

## Bracket payoff harness (`bracket_harness.py`)

Per deploy bar `k`, with reference price `P` = `close_bid[k]` and grid params
`Δ` (band half-width = `w * range_est[k]`, where `range_est` is a causal trailing
realized-range estimate, e.g. a rolling mean of `bar_range_pips`), `S` (stop beyond band),
`K` (max-hold bars), `q` (deploy quantile):

1. **Deploy gate:** to make the gate comparable across programs (which emit arbitrary
   scales), deploy on bars whose finite `deploy_score[k]` is in the **top-`q`** of the
   program's own finite scores on the split (`q ∈ {0.1, 0.2, 0.4}` grid). This mirrors the
   directional harness's MAD-scaling posture (a fixed per-split transform; the embargoed
   holdout + BH-FDR is the real gate). NaN = never deploy.
2. **Two-sided maker fill** over bars `k+1..k+K`: BUY limit `L=P-Δ` fills if some bar's
   `low_bid <= L`; SELL limit `U=P+Δ` fills if some bar's `high_bid >= U`. First edge
   touched wins and sets the side (maker, earns spread). If a single bar spans both
   (`low<=L` and `high>=U`) before either is unambiguously first → **no fill** (skip).
3. **Exit** after fill (long example, entry `L`): TP = center `P` (maker limit), SL =
   `P-Δ-S` (taker market), else time-stop at `k+K` (taker close). First-touch over
   subsequent bars via `high_bid`/`low_bid`; **same-bar TP&SL → assume SL** (pessimistic).
4. **Net pips** (round-trip):
   - TP: `+Δ - commission` (maker both ends).
   - SL: `-S - spread_exit - commission` (taker exit).
   - Time-stop: `(exit_close - entry) [signed by side] - spread_exit - commission`.
   `commission` is a fixed constant (`--commission-pips`, default 0.07 ≈ Dukascopy
   round-turn on EURUSD); `spread_exit = spread_pips[exit_bar]`.

Returns a DataFrame of `{net, test_month}` over filled deploys (parallel to the directional
harness) plus the inputs `task_score` needs. `entry_diagnostics` returns: `deploy_rate`
(deploys / bars), `fill_rate` (fills / deploys), `tp_rate`, `sl_rate`, `timeout_rate`,
`mean_net`, `month_hit_rate`.

Scoring: reused `task_score` (continuous net-LB95 × month-consistency × n; never an
in-search gate); best score over the swept grid `{w (band width), S (stop), K (max-hold),
q (deploy quantile)}`.

**Anti-mirage discipline:** conservative fill rules above (trade-through only, pessimistic
same-bar tie, skip ambiguous spans). The fast loop only needs to be *conservative*;
survivors are promoted to the existing tick-exact layer (`simulate_state_barrier_touch`,
`analyze_oco_stop_limit_tickfill`) for honest maker-fill verification — same fast-loop →
governance-ladder split as the dispersion track. This directly targets the project's known
"barrier-family mirage" failure mode.

## Seeds — bringing in the literature (`range_seeds.py`)

The `deploy` score is a product of four independent, separately-seeded ingredients; PUCT
recombination (p=0.3) fuses them (as the dispersion winner fused cluster+robust+gate).

| Seed (`deploy`) | Literature | Causal mechanism (features) |
|---|---|---|
| `range_vol_deploy` | Parkinson 1980; Yang-Zhang; HAR-RV (Corsi 2009) | high when trailing realized range (`bar_range_pips`) / multi-scale realized vol is large vs cost |
| `meanrev_regime_deploy` | variance ratio (Lo-MacKinlay 1988); Hurst; OU half-life | high when causal trailing variance-ratio < 1 / negative lag-1 return autocorr |
| `toxicity_gate_deploy` | VPIN (Easley-LdP-O'Hara); OFI (Cont-Kukanov-Stoikov) | base deploy suppressed (NaN) when |signed flow imbalance| is high |
| `burst_veto_deploy` | Hawkes (Bacry-Mastromatteo-Muzy) | veto when EWMA tick-arrival intensity (`tick_burst_score`/`tick_rate_z`) spikes |
| `spread_harvest_deploy` | Avellaneda-Stoikov; Stoikov micro-price | high when `spread_z` wide AND flow balanced (wide-spread-benign sweet spot) |

`RESEARCH_IDEAS` name each mechanism + paper AND include explicit *combine* instructions
(e.g. "gate any range/vol deploy by a mean-reversion-regime test and a flow-toxicity
veto"). `RANGE_RULES` (the qwen prompt) states the `deploy` contract, lists the four
ingredients + the causal feature menu, the no-future causal rule + probe warning, the
~50k-bar / 3×-run / vectorise performance note, and that the goal is to detect *when* a
two-sided bracket is harvestable. `BASELINE_SEED_NAMES` = the canonical subset for the
rediscovery tracer (`range_vol_deploy`, `meanrev_regime_deploy`, `toxicity_gate_deploy`,
`spread_harvest_deploy`).

All seeds are causal, numpy-only, and emit a **non-directional** score (NaN = no-deploy).
A new causal feature `bar_range_pips = (high_bid - low_bid)/pip` (stationary,
contemporaneous, causal) is added to the whitelist for the range estimators.

## Splits + driver

`load_splits` extends `RangeSplitData` to carry harness-side `close_bid`, `high_bid`,
`low_bid`, `spread_pips`, `cost` (programs still see only `FeatureContext`). Embargo =
**max-hold `K`** bars purged from the tail of train and validation (a deploy at `k` uses
`k+1..k+K`). Splits: train 2018-2023, validation 2024 (capped to recent
`--score-max-bars`, default 50000), holdout 2025-2026 (full).

`run_era_range.py` mirrors `run_era_scalp.py`: seed forest → PUCT (mutate + recombine,
`rules=RANGE_RULES`) scored on the capped validation split → top-N re-scored on the full
holdout → `bh_fdr(holdout_pvalue)` + diagnostics report, with the search-health rejection
accounting (`summarize_rejections`). Flags: `--symbol --parquet --max-hold --budget
--no-baseline-seeds --holdout-top --score-max-bars --commission-pips`.

## Evaluation plan

Fast loop: per-program validation `task_score`; final selection = full-holdout BH-FDR over
the explored set + the scalping diagnostics (fill-rate, tp/sl/timeout rates, month
consistency). Promotion (out of scope here): the existing tick-exact barrier-touch / OCO
tickfill layer for honest maker-fill verification, then the Monthly WFO → Reduced-Core →
Robustness ladder. Nothing is deployable until it survives that.

## Testing

- `test_bracket_harness` — synthetic price paths: clean oscillation → fill + TP-at-center
  profit; one-way trend → SL loss; same-bar TP&SL → pessimistic SL; ambiguous both-edge
  span → no fill; commission always subtracted; maker entry pays no entry spread.
- `test_range_seeds` — 5 seeds present, run, **causal**; `deploy` output non-directional
  (finite values ≥ 0 or NaN, no reliance on sign); research ideas cite the streams.
- `test_range_prompt` — `RANGE_RULES` covers the `deploy` contract, causal rule, ingredients.
- `test_load_splits_range` — `RangeSplitData` carries high/low/close/spread; embargo trims
  `K` tail bars; no leakage columns in `FeatureContext.names`.
- `test_integration` — `select_seed_programs` ablation; `finalize_selection` BH-FDR;
  mocked-writer end-to-end `run_search`.
- Reuse `era_scalp` context/sandbox/causality + `era` engine tests.

## Consequences

- Third ERA application; reuses the engine + single-symbol context; only the payoff harness
  is genuinely new. Directional variant preserved as the negative-result baseline.
- The maker-bracket flips the spread from cost to revenue — the structural reason this can
  work where direction couldn't.
- The binding empirical question is whether **reversion-from-extreme beats break-through
  net of cost**; the loop tests it with the correct path-dependent payoff and the
  earn-the-spread economics, gated by regime/toxicity detectors fused from the literature.
- Maker-fill realism (adverse selection) is the main mirage risk; mitigated by conservative
  fast-loop fills and mandatory tick-exact verification before any trust.
