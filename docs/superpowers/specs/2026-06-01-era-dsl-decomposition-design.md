# ERA Scalp DSL Decomposition — Design Spec

- Status: Proposed
- Date: 2026-06-01
- Relates to: `docs/analysis/era_cost_aware_puct_eur_2026-06-01.md` (PR #287, null result — seeds beat evolved), ADR 0005 (dispersion discovery), `scripts/era_scalp/fade_seeds.py` (human-curated primitive library)

## Problem Statement

The cost-aware PUCT EUR run produced a **null**: the best evolved program (val=-0.843) had a weaker holdout (P=0.886, raw=-0.330) than the best seed (P=0.902, raw=+0.976). The evolved program looked better in validation but collapsed on holdout — a spurious validation win, exactly the overfit pattern the design was built to detect.

Root cause: the loop asks qwen to write **unconstrained `signal(ctx)` functions** from a one-sentence research idea. The seeds (`fade_seeds.py:45-147`) are compressed domain expertise — hand-tuned window sizes, stability constants, cumsum-based rolling statistics, and causal bookkeeping. Qwen cannot rediscover these from "Improve this program." More prompt context would not fix the generative ceiling; it would just make the prompt more expensive.

ADR 0005 forbids this architecture explicitly:

> *"The search surface should be dispersion formulas, gates, features, peer weights, and ensemble rules, **not a new boosting implementation**."*
> *"The DSL must forbid: **arbitrary Python execution**."*

The current loop is anti-ERA: qwen writes raw Python. The fix is to make qwen operate on a **structured spec tree**, with deterministic rendering to Python via a template engine.

## Goal

Replace open-ended code generation with **DSL-bound program evolution**. The LLM mutates and recombines specs; a deterministic renderer turns specs into executable code. Every evolved program is structurally sound (causal, stable, no forgotten normalisation). The search space is combinatorial but bounded: combinations of known primitives, not invention from first principles.

**Honest framing:** This is not a trick to make qwen beat the seeds. The seeds are domain-expert programs; the DSL may still not find a better gate combination. The goal is to make the null **honest** (the search was well-configured and still failed) rather than **artifactual** (the search was poorly configured and therefore meaningless).

## Decomposition Model

Every seed in `fade_seeds.py` decomposes into four slots. The human maps each seed once. Future seeds from literature transfer are mapped before entering the primitive library.

| Slot | Role | Primitives from seeds |
|---|---|---|
| **fair** | Estimate fair price (mid vs fair = conviction) | `ewma_cumsum(a=0.05)` on `vel_pips_h1` |
| **gate** | Regime filter — only trade when microstructure regime is favourable | `variance_ratio(W=240, qv=20, th=1.0)`, `lag1_autocorr(W=240, th=0.0)`, `efficiency_ratio(W=120, th=0.3)`, `none` |
| **direction** | How to sign the trade given the fair deviation | `fade` (toward fair), `continue` (away from fair), `conditional_response(H, signed)`, `conditional_response_matched(H)` |
| **extreme** | Only trade at tail dislocations | `abs_deviation > 2σ(W=240)` or `none` |

**Invariants:**
- Every rendered program is a single `signal(ctx) -> np.ndarray`.
- Every primitive is causal by construction (the renderer uses only `k-W:k` windows, no centered stats, no future rows).
- The fair estimator is fixed across all seeds — it is the scaffolding, not the search space.
- Primitives carry typed parameters with bounded domains (e.g., `W ∈ {60, 120, 240}`, `H ∈ {100, 200, 400}`).

## DSL Schema

A program is a JSON object consumed by the renderer. Qwen mutates/recombines this JSON, not Python source.

```json
{
  "version": "era-scalp-v1",
  "fair": {"primitive": "ewma_cumsum", "params": {"alpha": 0.05, "feature": "vel_pips_h1"}},
  "gate": {
    "combinator": "single",
    "primitives": [{"primitive": "variance_ratio", "params": {"W": 240, "qv": 20, "threshold": 1.0}}]
  },
  "direction": {"primitive": "fade"},
  "extreme": {"primitive": "abs_deviation_sigma", "params": {"W": 240, "n_sigma": 2.0}}
}
```

**Combinators for `gate`:**
- `"single"` — one primitive
- `"AND"` — all primitives must pass
- `"OR"` — at least one primitive must pass
- `"weighted_sum"` — combine primitive outputs, threshold on sum

**Combinators for `direction`:**
- `"single"` — one primitive
- `"switch_by_gate"` — use gate A → direction X, gate B → direction Y (requires gate has multiple primitives)
- `"conditional_signed"` — separate conditional response for positive/negative fair deviation

**Parameter mutation domains (hard bounds):**
```python
PARAM_DOMAINS = {
    "W": [60, 120, 240],
    "qv": [10, 20, 40],
    "threshold": {"variance_ratio": [0.95, 1.0, 1.05], "lag1_autocorr": [-0.1, 0.0, 0.1], "efficiency_ratio": [0.2, 0.3, 0.4]},
    "H": [100, 200, 400],
    "n_sigma": [1.5, 2.0, 2.5],
    "alpha": [0.03, 0.05, 0.10],
}
```

## Template Renderer (`dsl_renderer.py`)

The renderer is a **deterministic, no-LLM** Python module that turns a spec into a `signal(ctx)` string.

```python
from __future__ import annotations

RENDERERS: dict[str, callable] = {
    "ewma_cumsum": _render_ewma_cumsum,
    "variance_ratio": _render_variance_ratio,
    "lag1_autocorr": _render_lag1_autocorr,
    "efficiency_ratio": _render_efficiency_ratio,
    "fade": _render_fade,
    "continue": _render_continue,
    "conditional_response": _render_conditional_response,
    "conditional_response_matched": _render_conditional_response_matched,
    "abs_deviation_sigma": _render_abs_deviation_sigma,
    "none": _render_none,
}


def render(spec: dict) -> str:
    """Turn a spec into a valid `signal(ctx)` source string."""
    fair = _render_fair(spec["fair"])
    gate = _render_gate(spec["gate"])
    direction = _render_direction(spec["direction"], spec["gate"])
    extreme = _render_extreme(spec["extreme"])
    return _assemble(fair, gate, direction, extreme)
```

Each primitive renderer knows the exact cumsum trick, the exact stability constant, and the exact variable scoping from the seeds. The renderer never forgets `ms = np.where(m > 0, m, 1.0)` because it is hard-coded.

**Example: `_render_variance_ratio`**

```python
def _render_variance_ratio(params):
    W = params["W"]; qv = params["qv"]; th = params["threshold"]
    return (
        f"    W = {W}; qv = {qv}\n"
        "    d1 = np.diff(p, prepend=p[0])\n"
        f"    dq = np.empty(n); dq[:qv] = 0.0; dq[qv:] = p[qv:] - p[:-qv]\n"
        "    def rollvar(x):\n"
        "        c1 = np.concatenate(([0.0], np.cumsum(x)))\n"
        "        c2 = np.concatenate(([0.0], np.cumsum(x * x)))\n"
        "        k = np.arange(n); lo = np.maximum(0, k - W); m = (k - lo).astype(float)\n"
        "        ms = np.where(m > 0, m, 1.0)\n"
        "        mu = (c1[k] - c1[lo]) / ms\n"
        "        return (c2[k] - c2[lo]) / ms - mu * mu, m\n"
        "    v1, m = rollvar(d1); vq, _ = rollvar(dq)\n"
        f"    vr = vq / (qv * v1 + 1e-12)\n"
        f"    gate = (m >= 60) & (vr < {th})\n"
    )
```

**Assembly:**

```python
def _assemble(fair, gate, direction, extreme):
    parts = [
        "def signal(ctx):",
        fair,        # defines: n, r, p, ew, dev
        gate,        # defines: gate (bool array)
        direction,   # uses: dev, gate, p, n; defines: out
        extreme,     # masks: out
        "    return out\n",
    ]
    return "\n".join(parts)
```

## Primitive Registry (`dsl_primitives.py`)

Primitives are registered in a versioned dict. A primitive has:
- `name`: unique string
- `slot`: `fair | gate | direction | extreme`
- `params`: dict of param_name → default_value
- `domains`: dict of param_name → allowed_values (for mutation)
- `render_fn`: reference to renderer function

```python
PRIMITIVE_REGISTRY: dict[str, dict] = {
    "ewma_cumsum": {
        "slot": "fair",
        "params": {"alpha": 0.05, "feature": "vel_pips_h1"},
        "domains": {"alpha": [0.03, 0.05, 0.10], "feature": ["vel_pips_h1"]},
        "render_fn": _render_ewma_cumsum,
    },
    "variance_ratio": {
        "slot": "gate",
        "params": {"W": 240, "qv": 20, "threshold": 1.0},
        "domains": {"W": [60, 120, 240], "qv": [10, 20, 40], "threshold": [0.95, 1.0, 1.05]},
        "render_fn": _render_variance_ratio,
    },
    ...
}
```

**Adding a primitive (human-curated literature transfer):**
1. Read literature (e.g., graph Laplacian from power-grid ADR 0005 section).
2. Write the causal renderer with cumsum/rolling tricks.
3. Add to `PRIMITIVE_REGISTRY` with domains.
4. Write a seed spec using the new primitive.
5. Validate: seed spec must render to code that passes causality probe and reproduces known holdout.
6. Only then is the primitive available to the loop.

## Qwen's New Role: Spec Mutator

Qwen no longer sees Python source. It sees **spec diffs** and produces **child specs**.

### Mutation (`propose_spec`)

Input: parent spec + one research idea string (human-readable rationale, not executable code).

Prompt template:
```
You mutate a trading-signal specification. The spec has four slots: fair, gate, direction, extreme.

Current spec:
<JSON parent spec>

Research idea to consider: <idea>

Allowed primitives and parameter domains:
<PRIMITIVE_REGISTRY summary>

Rules:
- You may change ONLY the gate, direction, or extreme slot. The fair slot is fixed.
- Parameter values must be from the allowed domains.
- Combinators must be one of: single, AND, OR, weighted_sum (gate); single, switch_by_gate, conditional_signed (direction).
- Output ONLY a valid JSON object matching the spec schema.
```

Output: child spec (JSON).

### Crossover (`recombine_specs`)

Input: two parent specs + their scores.

Prompt template:
```
You combine two trading-signal specifications. Each spec has four slots.

Parent A (score <scoreA>):
<JSON specA>

Parent B (score <scoreB>):
<JSON specB>

Rules:
- For each slot, pick Parent A's primitive, Parent B's primitive, or a combinator that uses BOTH.
- You may vary parameters within allowed domains.
- The fair slot is fixed (copy from either).
- Output ONLY a valid JSON object.
```

Output: child spec (JSON).

**Why this works:** Qwen is now doing **hyperparameter algebra and feature selection**, not quant research from scratch. It is choosing among 5 gates × 4 combinators × 3 direction modes × 3 horizons × 3 extreme filters — a bounded combinatorial space that fits in a 3B model's capacity.

## PUCT Loop Changes

`Node.payload` is now a **spec dict**, not a source string.

```python
@dataclass
class Node:
    payload: dict        # spec, not source
    score: float
    parent: Node | None
    visits: int = 1
    logs: str = ""       # validation logs + render logs
    children: list = field(default_factory=list)
    mean: float = 0.0
    se: float = 0.0
```

**Scoring in the loop:**
```python
def _score_spec(spec, scorer):
    src = render(spec)
    return scorer.score(src, "validation")  # (value, mean, se, logs)
```

The causality probe still runs on the **rendered source**, catching renderer bugs or qwen hallucinations of non-existent primitives.

**Expansion:**
```python
def expand(parent: Node) -> Node:
    if rng.random() < p_recombine and len(all_nodes) >= 2:
        cands = sorted(all_nodes, key=lambda n: n.score, reverse=True)
        child_spec = recombine_specs(cands[0].payload, cands[0].score,
                                     cands[1].payload, cands[1].score,
                                     registry=PRIMITIVE_REGISTRY)
    else:
        child_spec = propose_spec(parent.payload, parent.score,
                                  rng.choice(RESEARCH_IDEAS),
                                  registry=PRIMITIVE_REGISTRY)
    # validate spec against registry before rendering
    if not validate_spec(child_spec, PRIMITIVE_REGISTRY):
        return Node(payload=child_spec, score=-1e6, parent=parent,
                    logs="spec validation failed")
    src = render(child_spec)
    v, mean, se, lg = scorer.score(src, "validation")
    return Node(payload=child_spec, score=v, parent=parent, logs=lg, mean=mean, se=se)
```

## Cache Key Change

Cache is now on **spec JSON**, not prompt text. This means:
- Reordering of JSON keys does not matter (canonical JSON via `json.dumps(..., sort_keys=True)`).
- If two different prompts produce the same spec, they share a cache entry — correct.
- Rendered source is not cached; rendering is deterministic and cheap.

```python
def _spec_cache_key(spec: dict) -> str:
    return hashlib.sha256(json.dumps(spec, sort_keys=True).encode()).hexdigest()[:16]
```

## Migration Path from `run_era_eur.py`

1. **Create `scripts/era_scalp/dsl_renderer.py`** — register all primitives from `fade_seeds.py`, implement renderers.
2. **Create `scripts/era_scalp/dsl_primitives.py`** — `PRIMITIVE_REGISTRY`, `validate_spec`.
3. **Create `scripts/era_scalp/llm_specs.py`** — `propose_spec`, `recombine_specs`, `_build_spec_prompt`, `_extract_spec`.
4. **Create `scripts/era_scalp/seed_specs.py`** — human-mapped JSON specs for every seed in `FADE_SEED_PROGRAMS`.
5. **Modify `scripts/era_scalp/run_era_eur.py`** — `Node.payload` becomes spec dict; `_score_spec` renders before scoring; seeds are JSON specs, not source strings. Rediscovery control uses a minimal spec (`{"version":"v1","fair":{...},"gate":{"combinator":"single","primitives":[{"primitive":"none"}]},"direction":{"primitive":"fade"},"extreme":{"primitive":"none"}}`).
6. **Tests:** every renderer unit-tested against the original seed source; every seed spec must render to code that reproduces the original seed's validation score (±1e-6). This is the **regression contract**.

## Testing Strategy

| Test | What it proves |
|---|---|
| `test_render_ewma_cumsum` | Renderer output matches `fair_fade` source exactly (modulo whitespace) |
| `test_render_variance_ratio` | Renderer output matches `vr_gated_fade` gate block |
| `test_render_conditional_response` | Renderer output matches `conditional_response_fade_h200` |
| `test_seed_specs_reproduce_scores` | Each seed spec → render → score == original seed score (same data split) |
| `test_validate_spec_rejects_unknown_primitive` | `validate_spec` returns False for hallucinated primitive names |
| `test_validate_spec_rejects_out_of_domain` | `validate_spec` returns False for W=500 (not in domain) |
| `test_propose_spec_prompt_length` | Prompt token count < 2000 (fits qwen context) |
| `test_recombine_specs_json_output` | `recombine_specs` returns parseable JSON with all required keys |
| `test_puct_dsl_rediscovery_null` | Rediscovery control (no seeds, trivial spec) still produces null, confirming loop is honest |

## Honest Risks and Expected Outcomes

1. **The DSL may still not beat the seeds.** If the best combination of known primitives is already in the seed library, the search will find a seed-equivalent or something worse. This is fine — the null is honest.

2. **The renderer may have bugs.** If a renderer forgets a stability constant, the rendered program looks different from the seed and scores differently. The regression test (`seed_specs_reproduce_scores`) catches this before the loop runs.

3. **Qwen may hallucinate primitives outside the registry.** `validate_spec` rejects these before rendering; the node gets score=-1e6 and the search continues.

4. **The search space is smaller, so the null is more meaningful.** If 200 expansions over a bounded space find nothing better than `fair_fade_mean`, we can conclude the EUR edge is captured by known primitives. That is a stronger claim than "qwen can't write Python."

5. **Literature transfer is still the path to new primitives.** The next graph_laplacian or spread-skill gate enters via human curation, not loop generation. The loop's job is to find the best ensemble of known ideas, not invent new ones.

## File Structure

- `scripts/era_scalp/dsl_primitives.py` — `PRIMITIVE_REGISTRY`, `validate_spec`
- `scripts/era_scalp/dsl_renderer.py` — primitive renderers, `render(spec) -> str`
- `scripts/era_scalp/seed_specs.py` — JSON specs for every seed in `FADE_SEED_PROGRAMS`
- `scripts/era_scalp/llm_specs.py` — `propose_spec`, `recombine_specs` (qwen prompt builders)
- `scripts/era_scalp/run_era_eur.py` — MODIFY: spec-based PUCT loop
- Tests: `test_dsl_renderer.py`, `test_dsl_primitives.py`, `test_llm_specs.py`, `test_seed_specs.py`

## Verdict Criteria for Implementation PR

- All existing seeds render from specs and reproduce original validation scores.
- Rediscovery control (trivial spec, no seeds) still fails as expected.
- At least one A/B search run (Thompson vs rank, budget=40) completes without crashes.
- Honest verdict: report whether any evolved spec beats the best seed spec on holdout, net-of-cost.
