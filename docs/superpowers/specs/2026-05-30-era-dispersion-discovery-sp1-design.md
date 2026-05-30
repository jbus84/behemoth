# ERA-Faithful Dispersion-Signal Discovery — Sub-project 1

- Status: Proposed
- Date: 2026-05-30
- Depends on: ADR 0005 (Dispersion Family Research Directions); the cross-symbol
  frame (`scripts/cross_symbol.py`); the `dispersion_rank` family
  (`scripts/mining_family.py`); the WFO cross-symbol fix (PR #276).

## 1. Context

The single strongest non-directional edge found in the book is cross-sectional
mean-reversion: `dispersion_rank EURUSD asia__k2` @2000-tick scores **net-LB95
+1.22** (n=395, multi-month, survives a +1.0-pip slippage haircut). It works by
isolating the *idiosyncratic* USD-aligned move of one major against the other
five and fading it. That is one hand-built point in a large space of
relative-value reversion signals.

Rather than hand-author more variants, ADR 0005 directs us to **let an
AI-discovery loop generate and govern them**, following the ERA method
("An AI system to help scientists write expert-level empirical software",
Nature 2026 / arXiv 2509.06503). This sub-project (SP1) faithfully implements
the ERA engine for this one problem — discovering robust dispersion signals —
and is the spine the later sub-projects depend on.

**ERA, faithfully:** a node is a *complete program* that executes and is scored
by a quality metric. A **PUCT tree search** (AlphaZero-style, globally flat)
repeatedly selects a node, has an **LLM rewrite that node's whole program**
given the parent code + its score + execution logs (+ an optional research-idea
summary), executes the child, scores it, and backpropagates visit counts.
There is **one LLM and no separate critic** — improvement comes from the metric
and logs fed into the next prompt. Generalisation is enforced by
train/validation/held-out splits; the final artifact is the single
highest-validation-score program.

**Decomposition (this spec = SP1 only):**

- **SP1 — the ERA engine:** PUCT tree search over causal-sandboxed dispersion
  programs, scored by a fast repo metric, that rediscovers and then beats the
  known baselines. *This document.*
- SP2 — scale-out: larger search budgets, recombination of strong parents,
  research-idea injection at scale, multiple-testing controls.
- SP3 — governance promotion: feed survivors into the full Stage 2/3 WFO →
  Reduced-Core → Tick-Exact → Robustness ladder + the low-capacity harness.
- SP4 — portfolio/reporting of survivors (ERA returns single-best, so this is
  selection/reporting, not opaque ensembling).

## 2. Goal & Success Milestone

Stand up the faithful ERA loop end-to-end on a small budget and prove it works,
per ADR 0005's tracer-bullet:

> A small-budget PUCT run (~50–200 nodes) over causal-sandboxed dispersion
> programs, scored by the fast train/validation metric on 1000/2000/5000-tick
> bars, **rediscovers the known baselines** (`dispersion_rank`, `loo_z`,
> `robust_z`, `graph_laplacian`) near the top of the tree, and ideally surfaces
> at least one program that **beats `dispersion_rank` on the validation metric**
> while passing the held-out check.

Non-goals for SP1: large search budgets, automated recombination, full WFO
promotion, and ensembling (SP2–SP4).

## 3. Model Roles & Build Division

| Role | Actor | Responsibility |
|---|---|---|
| Plan / verify / integrate / judge | **Opus 4.8** (supervising session) | this spec + the plan; verify Haiku's infra code; run evaluators; commit; accept/reject |
| Build the ERA system | **Haiku** (`claude-haiku-4-5`) | implement the PUCT engine, sandbox, scorer, harness, glue — **verified by Opus** |
| In-loop program writer | **`qwen3-coder-next`** (ollama.com cloud) | rewrite the selected node's program each PUCT expansion. Single LLM, **no critic** |
| Quality judge | repo metrics only | the fast causal TaskScore — never an LLM |

`OLLAMA_API_KEY` is loaded from the gitignored `.env` (already present;
ollama.com `/api/generate` smoke-tested OK with `qwen3-coder-next`).

## 4. Architecture

### 4.1 Node = a causal-sandboxed signal program

A node is a Python module exposing one pure function with a **fixed, audited
signature**:

```python
def residual(ctx: CrossSectionContext) -> np.ndarray:
    """Return a per-bar residual array, length == ctx.n_bars.
    Larger |residual| == stronger idiosyncratic dislocation of the target."""
```

`CrossSectionContext` exposes **only causal inputs**: the per-bar 6-symbol
USD-aligned returns matrix (`xs_ret_z__<SYM>`, already as-of joined by
`cross_symbol.py`), the target symbol, `_USD_SIGN`, and bounded backward-window
helpers. It **does not expose `y_fwd_*`, future bars, or test-month data**. The
program returns only the residual; the harness — not the program — converts it
to entries (`|residual| >= threshold` over a swept grid), sides
(`-sign(residual)·_USD_SIGN[target]`, fade), and gross (`side·y_fwd`). The
program therefore *cannot* see the label it is being scored against.

The threshold grid, horizon, and regime conditioning are applied by the harness
around the program's residual, so the search space is "how to compute the
residual," matching ERA's "rewrite the program" while keeping entry/side/scoring
fixed and causal.

### 4.2 Causal sandbox & execution isolation

Each program runs in an isolated subprocess with: no network, no filesystem
writes outside a temp dir, a CPU-time and wall-clock timeout, a memory cap, and
an import allowlist (`numpy`, `pandas`, `scipy` stats only). The `ctx` handed in
contains **no future-bearing columns**, so even a malicious/buggy program cannot
leak `y_fwd`. A static pre-check rejects programs that attempt forbidden imports,
file/network access, or reference forbidden names. Execution failure → the node
gets a sentinel worst score and its logs feed the next LLM prompt (ERA-style).

### 4.3 Quality metric (TaskScore) — the judge

A fast, CatBoost-free causal evaluator (reusing `mining_family` gross logic):

1. Build the cross-symbol frame for EURUSD (+GBPUSD) at 1000/2000/5000-tick.
2. Run the program → residual → entries/sides via the harness.
3. Compute net = `side·y_fwd − cost_est_pips` over **train months only** for the
   search signal; compute the same over **validation months** for node ranking.
4. **TaskScore** = a stability-weighted net-LB95 (e.g. `net_lb95` with a penalty
   for low month-positive-share and low n), so the metric rewards *robust*
   reversion, not lucky single-month spikes (the failure mode that killed
   `double_touch`). Exact form fixed in the plan; it must be deterministic.

Month splits are fixed up front: **search/train**, **validation** (node
ranking + final selection), and an **untouched held-out** block scored once at
the end. ×3 replicates of any reported program; report the best-validation one
and its held-out score.

### 4.4 PUCT tree search engine

Faithful to ERA Algorithm 1 (globally flat PUCT):

```
T ← {root_seed_program};  V(root) ← 1
for iteration in 1..budget:                      # budget ~50–200 for SP1
    N ← Σ_u V(u)
    u* ← argmax_u  RankScore_T(u) + c_puct · P_T(u) · √N / (1 + V(u))
    child ← LLM_rewrite_and_execute(u*)          # §4.5 ; one child per expansion
    score child via §4.3 (validation metric)
    T ← T ∪ {child};  V(child) ← 1
    backprop: for each ancestor a of child: V(a) += 1
return argmax_u ValidationScore(u)
```

`RankScore_T` maps node scores to 0–1 ranks; `c_puct = 1` (paper default,
re-tunable); no pruning — all nodes retained, "backtracking" = re-selecting an
older node when paths plateau. Single child per expansion. Deterministic given a
fixed RNG seed and cached LLM outputs.

### 4.5 In-loop LLM (`qwen3-coder-next`)

`LLM_rewrite_and_execute(parent)`:

1. Build a prompt = problem description + the `residual()` contract + causal
   rules ("you only receive `ctx`; you cannot access future returns") + the
   **parent program source** + its **score** + **execution logs/errors** +
   (optionally) a **research-idea summary** (§4.6).
2. Call ollama.com `/api/generate` (`qwen3-coder-next`, key from `.env`) via
   `scripts/cheap_llm.sh` wrapper; expect a single complete program back.
3. Static-check + sandbox-execute + score. Cache `(prompt → program)` so runs
   are reproducible and cheap to re-run.

No critic model. The only feedback channel is the metric + logs in the next
prompt, exactly as in the paper.

### 4.6 Seed programs & research-idea pool

The tree is seeded with the known baselines **as programs** (so the loop must
rediscover/beat them), and the search is optionally guided by ~150-word
research-idea summaries (ERA's literature-injection), drawn from ADR 0005's
catalogue plus additions:

- **Baselines (seeds):** `dispersion_rank` (ordinal), `loo_z` (leave-one-out
  basket z), `robust_z` (median/MAD), `graph_laplacian` (fixed peer-cluster
  weighted residual).
- **ADR transfer ideas (injected):** equity stat-arb PCA/factor residuals;
  pairs/relative-value spreads; weather spread-skill gating and rank-transition
  diagnostics; power-grid neighbour/Laplacian residuals; signal-processing
  EWMA/CUSUM/Mahalanobis (flagged heavier).
- **Additions (Opus):** participation-ratio gate (trade only concentrated,
  one-symbol dislocations, skip broad USD moves); lead-lag-*corrected* basket
  (lag-align peers before the residual — salvage `lead_lag`'s information as a
  correction, not a standalone); rate-bloc-weighted basket (low-yield JPY/CHF
  vs commodity AUD/CAD clusters); session×dispersion interaction (the asia edge
  generalised); dispersion half-life sizing (scale horizon to recent
  cross-sectional autocorrelation).

These are *inputs to the search*, not hand-coded families — the loop decides
which survive on the metric.

## 5. Causal-Governance & Anti-Leakage Guarantees

- Programs receive only as-of-joined causal features; `y_fwd_*` is structurally
  absent from `ctx`.
- Entry threshold, side, and scoring are harness-owned and fixed — the program
  cannot fit thresholds on outcomes.
- Sandbox denies network/fs/imports; static pre-check + subprocess isolation.
- Train / validation / held-out month separation; held-out scored once.
- ×3 replicates; stability-weighted metric to resist single-month overfit.
- Every node (program, prompt, score, logs) is logged for full provenance and
  multiple-testing audit.

## 6. Layout & Build Division

A new `scripts/era/` package (Haiku builds, Opus verifies):

- `context.py` — `CrossSectionContext` (causal feature surface over the
  cross-symbol frame).
- `sandbox.py` — static pre-check + isolated subprocess execution.
- `harness.py` — residual → entries/sides/gross; the fast TaskScore (§4.3).
- `puct.py` — the tree search engine (§4.4), pure and unit-testable.
- `llm.py` + `cheap_llm.sh` — ollama.com `qwen3-coder-next` wrapper, `.env` key,
  prompt assembly, response caching.
- `seeds.py` — baseline programs + research-idea summaries.
- `run_era.py` — the driver (budget, splits, seeds → search → report).

## 7. Testing

- **Sandbox leak test:** a program that *tries* to access future data fails
  static-check / cannot find it in `ctx` (asserts structural isolation).
- **PUCT unit tests:** selection picks the max-PUCT node; backprop updates visit
  counts; deterministic under a fixed seed + cached LLM outputs (LLM mocked).
- **Harness parity:** the `dispersion_rank`/`loo_z` seed programs reproduce the
  existing family's entries/sides exactly (guards the residual→signal mapping).
- **Scorer determinism:** TaskScore is reproducible on a fixture.
- **Integration (the milestone):** a small mocked-LLM run rediscovers the seeded
  baselines at the top of the tree; a small *live* run (qwen3-coder-next) is
  run by Opus as evidence, not in CI.

## 8. Out of Scope (later sub-projects)

Large search budgets and automated parent recombination (SP2); full
WFO/Reduced-Core/Robustness governance promotion (SP3); survivor
selection/reporting across runs (SP4). Note ERA returns a single best program,
so "ensemble" is deferred and de-emphasised.

## 9. Risks & Open Questions

- **LLM cost/latency at budget:** 50–200 ollama.com calls per run; mitigated by
  response caching and coarse-bar fast scoring. Re-tune budget after first runs.
- **Metric gaming:** a program could maximise the fast metric in ways that fail
  full WFO. Mitigated by the stability-weighted metric + held-out check, and
  ultimately by SP3 promotion through the real ladder.
- **Sandbox escape:** mitigated by import allowlist + subprocess + no future
  columns; reviewed by Opus.
- **Determinism vs LLM nondeterminism:** caching `(prompt → program)` makes a
  completed run replayable; fresh runs vary (acceptable, ×3 replicates).
