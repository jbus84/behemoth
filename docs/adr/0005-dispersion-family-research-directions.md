# ADR 0005: Dispersion Family Research Directions

- Status: Proposed
- Date: 2026-05-30
- Supersedes: the prior ADR 0005 (Low-Capacity Regime Track). The low-capacity
  harness (`scripts/evaluate_low_capacity_track.py`) and its evidence report
  remain valid artifacts; the governing research direction is now dispersion
  discovery.

## Context

The existing `dispersion_rank` Mining Family is a cross-symbol mean-reversion
family over the six USD majors. For each target bar it builds the USD-aligned
cross-section:

```text
r_j = xs_ret_z__<SYMBOL>
```

It ranks the target symbol among the six USD-aligned returns and enters only
when the target is in the top-k or bottom-k of the cross-section:

```text
rank <= k     -> fade USD-positive extreme
rank >= 7 - k -> fade USD-negative extreme
```

This makes `dispersion_rank` an ordinal dispersion signal. It asks whether the
target is one of the cross-sectional extremes, but it does not measure how far
the target is from the basket, whether the cross-section is tightly clustered
or widely spread, whether the move is broad USD pressure or one-symbol
dislocation, or whether some peers should be weighted more heavily than others.

The proposed `xs_basket_residual` idea extends this mechanism by turning the
rank extreme into a continuous, dispersion-normalised residual:

```text
mu  = mean_j(r_j)
sig = std_j(r_j)
z   = (r_target - mu) / sig

enter when abs(z) >= threshold
side_pair = -sign(z) * _USD_SIGN[target]
gross = side_pair * y_fwd_pips_h{horizon}
```

This is best understood as a continuous generalisation of `dispersion_rank`,
not as a completely separate factor model. Because `z` is monotonic with rank
inside a single six-symbol cross-section, it will usually select similar tails
to `dispersion_rank`; the improvement is that it distinguishes weak rank
extremes from large dislocations.

The research question is therefore not just "more entries", but whether
dispersion-aware scoring produces better Candidate States: higher average
gross, better month stability, and stronger survival through Monthly WFO,
Reduced-Core Rolling, Tick-Exact Verification, and Robustness Filter.

## Decision

Treat dispersion as a first-class research state variable, not just a ranking
mechanism. Future dispersion research should compare `dispersion_rank` against a
small family of causally-computable residual and dispersion-regime variants.

The recommended first experiment is a new cross-symbol Mining Family with a
small method grid:

```text
family: xs_residual_fade
method: loo_z | robust_z | pairwise_median | graph_laplacian
threshold: continuous grid
horizon: existing horizon grid
side: fade residual sign
```

The first variants should be:

1. `loo_z`: leave-one-out basket residual.

   ```text
   z = (r_target - mean(r_peers)) / std(r_peers)
   ```

   This is the cleanest conceptual break from `dispersion_rank`, because the
   target is not included in its own benchmark.

2. `robust_z`: median/MAD residual.

   ```text
   z = (r_target - median(r_all)) / MAD(r_all)
   ```

   This protects the six-symbol basket from one bad peer or one extreme print.

3. `pairwise_median`: median target-vs-peer spread.

   ```text
   score = median_j(r_target - r_peer_j)
   ```

   This tests whether the target is high or low versus most peers, rather than
   versus a potentially fragile basket mean.

4. `graph_laplacian`: weighted peer-network residual.

   ```text
   score_i = r_i - sum_j(w_ij * r_j)
   ```

   This transfers a power-grid style local-disagreement detector into FX: a
   symbol is anomalous when it disagrees with its most relevant neighbours, not
   necessarily with the full six-symbol basket equally.

The current `xs_basket_residual` formulation remains useful as a baseline:

```text
z = (r_target - mean(r_all)) / std(r_all)
```

but it should not be the only residual tested, because including the target in
`mu` and `sig` partially dilutes the measured dislocation.

## Transfer Sources

### Equity Statistical Arbitrage

Equity stat-arb is the closest direct analogue. The common pattern is:

```text
returns -> remove market/sector factor -> compute residual -> fade residual outliers
```

Transferable methods:

- PCA residuals
- factor residual reversal
- covariance-aware anomaly scoring
- cross-sectional mean reversion
- pairwise and basket relative-value spreads

This maps naturally to the repo's cross-symbol frame:

```text
USD-aligned returns -> remove common USD basket move -> fade idiosyncratic residual
```

### Pairs Trading and Relative Value

Pairs trading contributes the residual-construction and thresholding playbook:

```text
spread = asset_A - hedge_ratio * asset_B
trade when spread z-score is extreme
```

The multi-symbol equivalent is target-versus-basket or target-versus-peer-cluster
residual scoring. Useful transferred concepts include spread z-scores,
half-life diagnostics, robust thresholds, and train-only entry-band selection.

### Weather Ensembles

Weather ensemble forecasting is dispersion-focused and directly relevant. Each
symbol can be treated like an ensemble member. The cross-sectional mean is the
ensemble mean, and cross-sectional dispersion is the ensemble spread.

Transferable methods:

- ensemble-member deviation from ensemble mean
- spread-skill gating: only trade when dispersion regimes historically predict
  useful reversion
- rank-transition diagnostics: measure whether rank extremes move back toward
  the middle over the target horizon
- ensemble blowout/contraction states: distinguish dispersion expansion from
  dispersion normalisation

This suggests evaluating not only residual magnitude, but also whether
dispersion itself is rising, high-and-stable, or contracting.

### Power Grids and Sensor Networks

Power-grid monitoring is useful because it treats dispersion as local
incoherence across a connected network. A node is anomalous when it disagrees
with nearby nodes or with the expected network state.

Transferable methods:

- neighbour residuals
- graph Laplacian residuals
- coherence-break detection
- robust bad-sensor filtering
- concentration/participation measures that distinguish one-node shocks from
  broad system moves

This is especially relevant for FX because all six USD majors need not be equal
peers. A graph-weighted basket can encode tighter relationships, for example
EURUSD/GBPUSD/AUDUSD as one cluster and USDJPY/USDCHF/USDCAD as another, while
still preserving the USD-aligned cross-symbol contract.

### Signal Processing and Anomaly Detection

Signal processing contributes stateful dispersion filters:

- EWMA residuals
- CUSUM residual break detection
- multivariate Mahalanobis distance
- robust covariance anomaly detection
- entropy and participation-ratio filters

These should be treated as second-wave experiments because they introduce more
state and causal-governance surface than the simple residual variants.

## Literature to Explore

The most relevant examples are not exact FX systems. They are research patterns
that can be translated into the repo's six-symbol USD-aligned cross-section.

1. Avellaneda and Lee, "Statistical Arbitrage in the U.S. Equities Market"
   (2008/2009).

   Link: <https://math.nyu.edu/inmemoriam/avellaneda/AvellanedaLeeStatArb20090616.pdf>

   Transfer: PCA/ETF factor residuals modelled as mean-reverting idiosyncratic
   components. This is the closest ancestor for `pca_resid` and
   factor-neutral residual fade variants.

2. Hudson & Thames ArbitrageLab PCA approach documentation.

   Link: <https://hudson-and-thames-arbitragelab.readthedocs-hosted.com/en/latest/technical/api/arbitragelab/other_approaches/pca_approach/index.html>

   Transfer: practical implementation details for residual windows, PCA factor
   returns, regression coefficients, and residual "S-score" style signals.

3. Whitaker and Loughe, "The Relationship between Ensemble Spread and Ensemble
   Mean Skill" (Monthly Weather Review, 1998).

   Link: <https://journals.ametsoc.org/view/journals/mwre/126/12/1520-0493_1998_126_3292_trbesa_2.0.co_2.xml>

   Transfer: spread-skill is strongest when spread is extreme or variable. For
   FX, this suggests binning entry outcomes by cross-sectional dispersion level
   and testing whether residual fade edge concentrates in dispersion extremes.

4. ECMWF, "Verifying the Ensemble Forecast Spread-Skill Relationship" (2007).

   Link: <https://www.ecmwf.int/en/elibrary/78924-verifying-relationship-between-ensemble-forecast-spread-and-skill>

   Transfer: binned spread-skill diagnostics and rank-histogram style checks.
   For the repo, this maps to diagnostics such as dispersion bins, rank
   transition toward the middle, and whether entry-time spread predicts
   forward reversion quality.

5. Hamill, "Interpretation of Rank Histograms for Verifying Ensemble Forecasts"
   (Monthly Weather Review, 2001).

   Link: <https://journals.ametsoc.org/abstract/journals/mwre/129/3/1520-0493_2001_129_0550_iorhfv_2.0.co_2.xml>

   Transfer: rank histograms diagnose spread and bias errors in ensembles. For
   `dispersion_rank`, the analogue is a rank-transition diagnostic: when a
   symbol is rank 1 or 6, how often does it move back toward ranks 3/4 over the
   target horizon?

6. Thorarinsdottir, Scheuerer, and Heinz, "Assessing the Calibration of
   High-Dimensional Ensemble Forecasts Using Rank Histograms" (Journal of
   Computational and Graphical Statistics, 2016).

   Link: <https://repository.library.noaa.gov/view/noaa/33235>

   Transfer: prerank functions compress multivariate ensembles into calibrated
   rank diagnostics. For FX, preranks could be residual magnitude, graph
   residual, dispersion concentration, or basket centrality.

7. Li, Pandey, Hooi, Faloutsos, and Pileggi, "Dynamic Graph-Based Anomaly
   Detection in the Electrical Grid" (2020).

   Link: <https://arxiv.org/abs/2012.15006>

   Transfer: topology-aware anomaly detection on grid sensors. For FX, replace
   electrical topology with a peer-weight graph and detect target disagreement
   with relevant neighbours rather than with an equal-weight all-symbol basket.

8. "Generalized Graph Laplacian Based Anomaly Detection for Spatiotemporal
   MicroPMU Data" (NREL publication record).

   Link: <https://research-hub.nrel.gov/en/publications/generalized-graph-laplacian-based-anomaly-detection-for-spatiotem>

   Transfer: graph Laplacian residuals for localising abnormal sensor behaviour.
   This supports the `graph_laplacian` variant:

   ```text
   score_i = r_i - sum_j(w_ij * r_j)
   ```

9. Rousseeuw and Van Driessen, "A Fast Algorithm for the Minimum Covariance
   Determinant Estimator" (Technometrics, 1999).

   Link: <https://www.tandfonline.com/doi/abs/10.1080/00401706.1999.10485670>

   Transfer: robust location/scatter estimation for outlier-resistant
   Mahalanobis distances. This is more complex than median/MAD, but it is the
   natural reference for robust multivariate dispersion scoring.

10. Lowry et al., "A Multivariate Exponentially Weighted Moving Average Control
    Chart" / MEWMA control-chart literature.

    Link: <https://www.tandfonline.com/doi/abs/10.1080/00224065.1997.11979720>

    Transfer: stateful detection of small multivariate shifts. For FX, this is
    a second-wave idea: use EWMA of cross-sectional residuals or dispersion
    concentration to distinguish one-bar noise from persistent dislocation.

11. Multivariate EWMA dispersion-control chart literature.

    Link: <https://vtechworks.lib.vt.edu/handle/10919/103289>

    Transfer: monitor changes in covariance or dispersion rather than only mean
    shifts. This is relevant to `dispersion_blowout_contraction` and
    dispersion-regime gates.

12. Matrix Profile literature for multidimensional time-series anomaly
    detection.

    Link: <https://arxiv.org/abs/2409.09298>

    Transfer: subsequence-level anomaly detection. This is less direct for the
    first implementation, but useful if single-bar residuals are too noisy and
    the edge depends on short multi-bar dispersion shapes.

## AI-Assisted Dispersion Discovery

The older literature above provides reusable mechanisms, but it should not be
the full research method. The more modern opportunity is to synthesize many
small causal dispersion programs and let the repo's governance ladder select
survivors.

The relevant pattern is Empirical Research Assistance (ERA), described in
Nature as an AI system that uses an LLM plus Tree Search to write empirical
software that maximizes a quality metric.

Link: <https://www.nature.com/articles/s41586-026-10658-6>

ERA is relevant because the repo already has most of the missing infrastructure:

- a bounded problem surface: six USD-aligned symbols
- an explicit quality ladder: Opportunity Mining, Monthly WFO, Reduced-Core
  Rolling, Tick-Exact Verification, Robustness Filter
- deterministic artifacts and candidate contracts
- enough cheap baseline mechanisms to seed a search tree

The goal should not be to ask an LLM to predict markets directly. The goal is to
ask models to generate many causally valid dispersion mechanisms under a small
DSL, then score them with repo metrics.

Unlike the ERA paper's custom empirical boosting framework, this repo should
keep CatBoost as the default supervised learner for Monthly WFO. The search
surface should be dispersion formulas, gates, features, peer weights, and
ensemble rules, not a new boosting implementation. Replacing CatBoost would add
governance and artifact complexity before there is evidence that the existing
learner is the bottleneck.

### Discovery Loop

The recommended research loop is:

```text
seed ideas
  -> LLM proposes dispersion formulas in a constrained DSL
  -> static validator rejects non-causal or unsupported formulas
  -> fast Stage 2 evaluator scores train-only opportunity quality
  -> tree search / evolutionary search mutates winners
  -> Monthly WFO tests survivors
  -> Reduced-Core Rolling and Robustness Filter kill overfit variants
  -> final ensemble combines only causal survivors
```

The LLM is a generator and critic, not the judge. The judge is always the
governed evaluation ladder.

The first implementation should use a faster feedback loop than the full
tick-opportunity sweep. Candidate search should initially focus on coarser
tick-bar grids where the data volume is manageable:

```text
bar_ticks: 1000, 2000, 5000
```

This fast loop is for discovery only. A generated mechanism is not a deployable
Candidate State until it survives the normal governance path. If a mechanism
looks promising on 1000/2000/5000-tick bars, it can then be promoted into the
full Stage 2 and Stage 3 surfaces for broader bar-tick and horizon evaluation.

### DSL Shape

The DSL should be deliberately small. It should allow formulas such as:

```text
residual =
  z_loo(r_target, peers)
  robust_z(r_target, all6)
  graph_laplacian(r_target, peers, weights)
  pairwise_median(r_target, peers)
  ewma(z_loo, window)
  dispersion_change(std(all6), lookback)
  participation_ratio(all6)

entry =
  abs(residual) >= threshold
  AND dispersion_regime in allowed_bins
  AND participation_ratio <= max_participation

side =
  fade(sign(residual), _USD_SIGN[target])
```

The DSL must forbid:

- future bars
- direct access to `y_fwd_*` during formula generation
- arbitrary Python execution
- unbounded rolling windows
- thresholds fit on test rows
- silent fallback to missing peers

### Model Roles

The model stack can mix closed and open-weight models:

- **Generator:** Gemini 2.5 Flash, Qwen3-Coder-Next, or Kimi K2. This role
  proposes many candidate formulas, mutations, and short rationales.
- **Critic:** DeepSeek-R1-style reasoning models or a stronger proprietary
  reasoning model. This role attacks leakage, overfitting, redundant variants,
  and unclear semantics before the repo evaluates candidates.
- **Implementer:** Qwen3-Coder-Next or Kimi K2. This role turns accepted DSL
  formulas into code or config patches after a human-approved design.
- **Judge:** repo metrics only. LLM preference is never a PASS/FAIL criterion.

Relevant model references:

- Gemini 2.5 Flash official docs:
  <https://docs.cloud.google.com/vertex-ai/generative-ai/docs/models/gemini/2-5-flash>
- Qwen3-Coder-Next technical report:
  <https://arxiv.org/abs/2603.00729>
- Qwen3-Coder-Next model card:
  <https://huggingface.co/Qwen/Qwen3-Coder-Next>
- Kimi K2 technical report:
  <https://arxiv.org/abs/2507.20534>
- DeepSeek-R1 technical report:
  <https://arxiv.org/abs/2501.12948>

### Calling Cheaper Models from Claude Code

The preferred operating model is not to replace the supervising Claude Code
session with a cheaper model. The supervising Claude Code session remains the
repo editor, validator, and evidence runner. Cheaper models are called as
external generators through shell commands or HTTP APIs.

Recommended division:

```text
main Claude Code session
  -> writes prompts
  -> calls cheap generator command
  -> parses JSONL output
  -> validates DSL and causal contract
  -> runs repo evaluators
  -> summarizes survivors

cheap model process
  -> proposes many candidate formulas
  -> returns constrained JSON/text only
```

For Ollama-backed generation, this repo uses direct cloud calls to
`ollama.com`. This is the required path; local `localhost:11434` calls are not
part of this workflow.

```bash
curl https://ollama.com/api/generate \
  -H "Authorization: Bearer $OLLAMA_API_KEY" \
  -d '{
    "model": "qwen2.5-coder",
    "prompt": "Generate 20 causal FX dispersion formulas as JSON.",
    "stream": false
  }'
```

Ollama documents the same API under `https://ollama.com/api` for cloud models:
<https://docs.ollama.com/api>. API keys are created in Ollama cloud settings:
<https://docs.ollama.com/cloud>.

For a cheaper secondary Claude Code instance:

```bash
ANTHROPIC_MODEL=claude-haiku-4-5-20251001 \
claude -p "Generate 20 causal FX dispersion formulas as JSON."
```

The repo should eventually wrap either path behind a stable command such as:

```bash
scripts/cheap_llm.sh "Generate 20 causal FX dispersion formulas as JSON."
```

The expected generator output should be constrained JSONL, for example:

```json
{
  "name": "robust_loo_dispersion_gate",
  "residual": "robust_z(r_target, peers)",
  "entry": "abs(residual) >= 1.25 and dispersion_quantile >= 0.7",
  "side": "fade(sign(residual))",
  "rationale": "Fades target-specific dislocation only in high-spread regimes."
}
```

This keeps bulk generation cheap while preserving the stronger guarantees of the
main repo workflow: only validated formulas become Candidate States, and only
repo metrics judge whether a generated idea survives.

### Ensemble Synthesis

ERA's strongest lesson for this repo is that the final artifact may not be one
formula. It may be a small ensemble of surviving mechanisms that works better
than any individual dispersion model.

Allowed first-wave ensemble forms:

1. Rank/vote ensemble across survivor signals.
2. Union of survivor signals gated by dispersion regime.
3. Non-negative weighted blend fit only on rolling-history months.
4. Meta-model over survivor scores, evaluated strictly through Monthly WFO.

Disallowed first-wave ensemble forms:

- unconstrained stacking on all history
- using test-month outcomes to choose ensemble weights
- blending families that lack compatible causal Feature Set contracts
- opaque model combinations that cannot be written into Candidate State
  metadata and Governance Locks

### Multiple-Testing Controls

Mining thousands of variants creates an overfit hazard. The discovery loop must
therefore have hard controls:

- separate search months from untouched validation months
- keep the final holdout fixed before running the search
- log every proposed formula, including failures
- score by stability, not just best mean gross
- penalize redundant variants that differ only by constants
- require survival through Monthly WFO and Reduced-Core Rolling before any
  ensemble step
- rerun shortlisted formulas from scratch after search completes

The first tracer bullet should be intentionally small:

```text
generate 50 DSL formulas
evaluate on train-only Stage 2 metrics over 1000/2000/5000-tick bars
confirm the loop rediscovers known baselines:
  dispersion_rank
  loo_z
  robust_z
  graph_laplacian
```

Only after the discovery loop rediscovers or improves obvious baselines should
it be trusted to mine thousands of variants.

## Evaluation Plan

Each dispersion candidate should be benchmarked against the current
`dispersion_rank` controls:

```text
dispersion_rank, rank_k = 1
dispersion_rank, rank_k = 2
```

The first comparison set should be:

```text
xs_basket_residual_all6
xs_residual_fade, method = loo_z
xs_residual_fade, method = robust_z
xs_residual_fade, method = pairwise_median
xs_residual_fade, method = graph_laplacian
```

Minimum metrics:

- selected row count
- mean gross pips
- gross-pip distribution by horizon
- month hit rate
- train/test stability through Monthly WFO
- Reduced-Core Rolling survival
- Tick-Exact Verification compatibility
- Robustness Filter survival

Additional dispersion-specific diagnostics:

- dispersion level at entry
- dispersion change from entry to horizon
- rank transition from extreme toward middle
- concentration or participation of the six-symbol move
- broad USD move versus one-symbol dislocation classification

## Consequences

- The repo keeps `dispersion_rank` as the simple, interpretable ordinal
  baseline.
- New dispersion work should not collapse into a single opaque "smart
  dispersion" family. It should expose residual method and threshold as governed
  Candidate State parameters so Opportunity Mining can decide which mechanisms
  survive.
- The first likely benefit is better-filtered opportunities, not necessarily
  more opportunities. A meaningful residual threshold should usually reduce row
  count while improving quality if the hypothesis is correct.
- Leave-one-out and robust residuals are low-complexity and should be tested
  before PCA, covariance, EWMA, or CUSUM variants.
- Graph residuals are the most promising power-grid transfer because they keep
  the same cross-symbol frame and fade semantics while allowing peer structure
  to matter.
- Weather ensemble ideas should first appear as diagnostics and gates, not as a
  separate family: spread-skill, rank-transition, and dispersion
  blowout/contraction can explain when residual fading works.
- Any implementation must preserve the existing causal discipline: peer values
  must be backward as-of joined, rolling statistics must be computed from
  information available at the target bar, and Threshold Fit must remain
  train-only or rolling-history derived.
