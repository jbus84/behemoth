# C2 — Port `run_era_eur.run_search` into `era_engine` Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
> **NOTE on subagents:** Haiku subagents have repeatedly corrupted the root checkout and silently weakened specs in this repo (see memory `feedback-verify-subagent-work`). Execute this plan **inline** in a worktree, or verify every subagent diff against the substitution table below.

**Goal:** Make `scripts/era_scalp/era_engine.py` own the ERA search loop so the directional/fair runner (`run_era_eur.run_search`) becomes a thin spec-builder that delegates — the engine becomes the single real system.

**Architecture:** Transcribe `run_era_eur.run_search`'s loop (lines 243–707) verbatim into a new `era_engine.run_search_rich(spec, splits, *, budget, seed, cache_dir, select_policy, warm_start, concept_mode, resume_tree)`. All problem-specific writers/constants/flags flow through `RunSpec` hooks (added this session) so the engine never imports back into `run_era_eur` (no circular import). Scoring swaps `CostAwarePerSymbolScorer.score` → `score_program(src, spec, split)` (parity-proven, #316). Selectors import from the leaf `scripts.era.puct`.

**Tech Stack:** Python, numpy, the existing `scripts.era.puct` PUCT core, the C2 characterization oracle (`tests/era_scalp/test_run_search_characterization.py`, merged in #320) + the C1 holdout parity oracle (`tests/era_scalp/test_era_engine_holdout_parity.py`, #319).

---

## Critical risk: oracle coverage gap

The C2 oracle (#320) pins `run_search` behaviour **only on the default path**: the fake writer returns a fixed program and all rich flags are off (`atomic_mode=False`, `dimension_locked=False`, `self_correct=False`, `parallel_expansions=1`, `use_llm_prior=False`, `warm_start=False`). So a faithful port of the *default* path is fully protected, but the **atomic / dimension-locked / self-correct / parallel / llm-prior branches (~60% of the function) are unverified**. Task 2 extends the oracle to cover them with deterministic fake writers **before** those branches are trusted. Do not skip Task 2.

## Name-substitution table (module/local → engine, used in every transcription task)

| In `run_era_eur.run_search` | In `era_engine.run_search_rich` |
|---|---|
| `scorer.score(X, "validation")` | `_score(X)` → `score_program(X, spec, splits["validation"])` |
| `composition_to_source(comp)` | `spec.render_payload(comp)` |
| `_render_payload` / `_extract_concepts` | local closures over `spec.render_payload` / `spec.extract_concepts` |
| `propose_branch_program` | `spec.propose_branch` |
| `propose_branch_program_with_prior` | `spec.propose_branch_with_prior` |
| `propose_dimension_locked_program` | `spec.propose_dimension_locked` |
| `propose_atomic_change` | `spec.propose_atomic` |
| `recombine_branch_program` | `spec.recombine_branch` |
| `recombine_atomic_compositions` | `spec.recombine_atomic` |
| `self_correct_program` | `spec.self_correct_fn` |
| `extract_composition_from_source` | `spec.extract_composition` |
| `_recombination_parents` | engine-local `_recombination_parents` (already at era_engine.py:106) |
| `_sanitize_composition` | `spec.sanitize_composition` |
| `CONCEPT_TAXONOMY` | `spec.concept_taxonomy` |
| `rich_templates` | `spec.rich_templates` |
| `cross_branch_index` | `spec.cross_branch_index` |
| `FADE/FAIR_SEED_PROGRAMS`, `*_BRANCH_TAGS`, `*_SEED_COMPOSITIONS` | `spec.seed_programs`, `spec.branch_tags`, `spec.seed_compositions` (run_era_eur selects fair-vs-fade and bakes into spec) |
| flags `atomic_mode/dimension_locked/self_correct/use_llm_prior/parallel_expansions/branch_depth_limit/p_cross_branch/p_recombine/c_branch/verbose` | `spec.*` (added to RunSpec this session) |
| `tracker`, `archive` | `spec.tracker`, `spec.archive` |
| `select_thompson/select_diversity/select_diversity_with_history/select_diversity_with_llm_prior` | import from `scripts.era.puct` |
| `concept_mode`, `warm_start`, `resume_tree`, `select_policy`, `budget`, `seed`, `cache_dir` | function parameters of `run_search_rich` |

**`required_fn`/`fair_price_mode`:** the engine does not know `fair_price_mode`. `run_era_eur` builds the spec with the right `required_fn` (`"signal"` fade vs `"estimate_fair"` fair), `score_frame`, seed dicts, templates, and writers. `score_program` already encodes fair-vs-fade through `spec` (parity #316).

---

### Task 1: Extend `RunSpec` with rich-loop hooks  ✅ DONE THIS SESSION (uncommitted in worktree)

**Files:** Modify `scripts/era_scalp/era_engine.py:50-90` (the RunSpec dataclass).

Already applied: added `propose_branch`, `propose_branch_with_prior`, `propose_dimension_locked`, `propose_atomic`, `recombine_branch`, `recombine_atomic`, `self_correct_fn`, `extract_composition`, `render_payload`, `sanitize_composition`, `extract_concepts`, `select_with_history`, `select_with_llm_prior`, `rich_templates`, `concept_taxonomy`, `cross_branch_index`, `tracker`, `archive`, and flags `atomic_mode/dimension_locked/self_correct/use_llm_prior/parallel_expansions/branch_depth_limit/p_cross_branch/verbose`. Verified: `ruff` + `ty` pass, RunSpec imports (42 fields).

- [ ] **Step 1a — one field still missing:** add `seed_compositions: dict | None = None` (atomic-mode seeds; used by the `atomic_mode and fair_price_mode` seed-loading branch at run_era_eur.py:275-290).
- [ ] **Step 1b:** `uv run ruff check scripts/era_scalp/era_engine.py && uv run ty check scripts/era_scalp/era_engine.py` → All checks pass.

> Do **not** commit RunSpec hooks alone — `vulture` will flag them as unused until `run_search_rich` (Task 3) consumes them. They land together with Task 3.

---

### Task 2: Extend the characterization oracle to the rich branches (CLOSE THE GAP FIRST)

**Files:** Modify `tests/era_scalp/test_run_search_characterization.py`.

The existing oracle covers only the default path. Add deterministic fake-writer fixtures + golden captures for each rich branch so the Task 3/4 transcription of those branches is protected.

- [ ] **Step 2a — atomic mode:** monkeypatch `scripts.era_scalp.run_era_eur.propose_atomic_change` and `recombine_atomic_compositions` to deterministic stubs (return a fixed composition dict + prior 0.5); run `run_search(..., atomic_mode=True, fair_price_mode=True, budget=4, seed=0)`; capture node count + best `(branch, score)`; assert (tie-robust, as in `test_run_search_golden_best`).
- [ ] **Step 2b — self-correct:** stub `self_correct_program` to return a known-good program; feed a deliberately failing fake `propose_branch_program` (returns un-compilable src) so the self-correct path fires; assert the corrected node appears and is valid.
- [ ] **Step 2c — dimension-locked + llm-prior:** stub `propose_dimension_locked_program` / `propose_branch_program_with_prior`; run with `dimension_locked=True` then `use_llm_prior=True`; capture best `(branch, score)` for each.
- [ ] **Step 2d:** `uv run pytest tests/era_scalp/test_run_search_characterization.py -q` → all pass; these goldens are the contract Task 4 must reproduce.

---

### Task 3: Write `run_search_rich` in `era_engine` (default path only)

**Files:** Modify `scripts/era_scalp/era_engine.py` (add imports + new function); Test: existing oracle.

- [ ] **Step 3a:** extend the `scripts.era.puct` import to add `select_thompson, select_diversity_with_history, select_diversity_with_llm_prior`.
- [ ] **Step 3b:** transcribe the loop (run_era_eur.py:243-707) into `run_search_rich(spec, splits, *, budget=60, seed=0, cache_dir=".era_cache", select_policy="diversity", warm_start=False, concept_mode=False, resume_tree=False)` using the substitution table. Local helpers: `_score(src)`, `_render(payload)`, `_concepts(payload)`. Keep the nested closures (`_generate_single_candidate`, `_try_self_correct`, `_score_and_log`, `expand`, `_expand_logged`, `_select_fn`) structurally identical.
- [ ] **Step 3c:** `uv run ruff check ... && uv run ty check scripts/era_scalp/era_engine.py` → pass.

### Task 4: Wire `run_era_eur.run_search` to delegate; verify against ALL goldens

**Files:** Modify `scripts/era_scalp/run_era_eur.py:243-707` (replace body with spec-build + delegate).

- [ ] **Step 4a:** in `run_search`, after computing `seed_branch_tags/rich_templates/cross_branch_index`, build a `RunSpec` wiring every hook to the local era_scalp writers/constants (`propose_branch=propose_branch_program`, … per the table), set `required_fn`/`score_frame`/`run_program`/`causality_probe`/`context_factory` for fair-vs-fade, set the flags from the function args, then `return run_search_rich(spec, splits, budget=budget, seed=seed, cache_dir=cache_dir, select_policy=select_policy, warm_start=warm_start, concept_mode=concept_mode, resume_tree=resume_tree)`.
- [ ] **Step 4b:** delete the now-dead loop body (the closures move to the engine).
- [ ] **Step 4c — full verification:** `uv run pytest tests/era_scalp/test_run_search_characterization.py tests/era_scalp/test_era_engine_holdout_parity.py tests/era_scalp/test_era_xs*.py -q` → ALL pass (default + every rich golden from Task 2 + era_xs unaffected).
- [ ] **Step 4d:** `uv run make quality` → green.
- [ ] **Step 4e:** commit (RunSpec hooks + run_search_rich + delegation together), push, PR.

### Task 5 (C3): thin runners + retire `CostAwarePerSymbolScorer`

**Files:** `run_era_eur.py` (main), `era_xs.py` (main), `cost_aware_score.py`.

- [ ] Make `run_era_eur.main` / `era_xs.main` thin: build spec → `run_search_rich`/`run_era_search` → `engine_verdict` → report.
- [ ] Replace `CostAwarePerSymbolScorer` usages with `score_program` (parity-proven #316); delete the class. **Watch the circular import** (memory `project-era-unified-engine`): `era_engine` imports scoring helpers from `cost_aware_score` — if `cost_aware_score` ever needs `era_engine`, extract shared helpers to a base module first.
- [ ] `uv run make quality && uv run pytest tests/era_scalp -q`; PR.

---

## Self-review
- **Spec coverage:** Tasks 3+4 move the whole 243-707 function; Task 2 covers the branches the existing oracle misses; Task 5 is the C3 thin-runner finish. The substitution table enumerates every external name in the function body.
- **Type consistency:** `score_program` returns `(value, mean, se, logs)` — identical to `scorer.score` (verified era_engine.py:66/106). `recombine_branch` real signature is `(payA,scoreA,brA, payB,scoreB,brB, cross_text, cache_dir)` (run_era_eur.py:452) — RunSpec comment corrected this session.
- **Placeholders:** none — every task names exact files/lines and the verification command.
