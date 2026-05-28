# ADR 0004: Stage I/O Contracts

- Status: Proposed
- Date: 2026-05-28

## Context

The tick-opportunity governance pipeline runs as a sequence of stages (Stage 2 mining → Stage 3 WFO → Stage 5 reduced-core → Stage 6 tick-exact → Stage 9 freeze). Each stage is coupled to its neighbours by file-naming and family/library conventions that are currently **implicit and scattered across multiple modules**, with no single declaration of what a stage consumes and produces.

Concrete facts a reader must currently reconstruct from source:

- Stage 2 mining (`scripts/run_tick_opportunity_mining.py`) writes candidate CSVs organised **by library, not by family**. Lines 1544–1559 hardcode exactly 7 library files: `directional`, `oco`, `oco_asymmetric`, `no_touch`, `dollar_residual`, `dispersion_rank`, `lead_lag`.
- A single library file holds multiple families. `<SYMBOL>_directional_candidates.csv` contains five families — `directional`, `directional_inverse`, `directional_run`, `double_touch`, `pullback` (verified: 6,426 rows on USDCAD).
- Stage 3 WFO (`scripts/run_tick_opportunity_monthly_wfo.py:438`) reads `<SYMBOL>_<library>_candidates.csv`, where the library comes from each WFO config's `library:` field and the families to extract from its `families:` field. This routing is spread across 66 per-(symbol × family) YAML configs plus `scripts/mining_family.py:FAMILY_REGISTRY`.
- Stage 3 WFO also carries its own hardcoded library ordering when planning inputs for requested families. Even if candidate paths import a manifest, leaving this order in code would keep a second source of truth for library discovery.
- Stage 3 WFO output naming has a related but distinct discoverability problem: real runs can write family-named outputs while legitimately empty runs can write library-named empty outputs. That makes a complete 66/66 WFO run harder to audit because artifact names no longer consistently reveal whether the unit of organisation is a library or a family.
- The mining summary (`_build_summary`, called at `scripts/run_tick_opportunity_mining.py:1502`) is hardcoded to three libraries — `directional`, `oco`, `no_touch`. When `no_touch` is empty, `<SYMBOL>_candidate_summary.csv` reports only 2 of the 7 libraries actually written.
- Stage 6 tick-exact (`scripts/verify_tick_exact_shortlist.py`) writes its verdict summary as `<SYMBOL>_<library>_tick_exact_summary.csv` under `reduced_core/`. Because the directional library expands to five families, running Stage 6 for `directional`, `directional_inverse`, `directional_run`, `double_touch`, and `pullback` on the same symbol writes the same filename five times — each run **overwrites** the previous. The output is keyed by `(symbol, library)`, but the verdict (`overall_pass`) is a property of `(symbol, family)`.

Four failure modes resulted during the 2026-05 multi-family trial — all caused by poor discoverability or inconsistent artifact contracts, not by incomplete Stage 2 data:

1. **"Missing families."** An operator (and an LLM) concluded `directional_inverse`, `directional_run`, `double_touch`, and `pullback` were missing because no per-family candidate file exists for them. In fact their candidates live inside `directional_candidates.csv`. Confirming this required reading three source files (the mining writer, the WFO config's `library:` field, and `FAMILY_REGISTRY`).
2. **"Only OCO and directional were mined."** `<SYMBOL>_candidate_summary.csv` showed only `directional` and `oco` rows, implying the other families were never produced. This was a false signal caused solely by the hardcoded 3-library `_build_summary` call; the candidate CSVs and the `candidate_fills` parquet contained all 10 families.
3. **"WFO outputs are hard to reconcile."** Stage 3 can complete all expected prediction jobs while still emitting a mix of family-named and library-named artifacts across real and legitimately empty runs. This is not the same issue as the WFO cache-key fix; it is an artifact naming contract problem.
4. **"Tick-exact verdicts are silently lost."** Stage 6 ran cleanly (exit 0) for all 21 eligible directional-library combos, but the per-family `overall_pass` verdicts collided into per-`(symbol, library)` files and overwrote each other. Only the last family run per symbol survives, and the surviving file cannot be attributed to a family. **This failure mode is destructive, not merely hard to interpret** — it corrupts the verdict ladder that Stage 9 freeze depends on, and a naive reader would trust a verdict that actually belongs to a different family.

The first three cases are interpretation hazards: the pipeline functioned correctly or produced legitimate empty outputs, but the artifact contract made the result hard to read. The fourth is worse — the by-library output key causes real verdict loss. The common defect is **discoverability and contract**: there is no single, machine-readable declaration of each stage's I/O — input/output glob patterns, the family↔library↔artifact-name mapping, the per-artifact key (is it `(symbol, family)` or `(symbol, library)`?), and required columns.

## Decision

Introduce a declarative **stage-contract manifest** as the single source of truth for inter-stage I/O. (Proposed; implementation deferred to a follow-up PR.)

The manifest — e.g. `src/behemoth/governance/stage_contracts.py` (importable) or `configs/pipeline/stage_contracts.yaml` (rendered into code) — declares, per stage:

- the producing stage and input artifact glob patterns
- output artifact glob patterns
- the family↔library↔artifact-name mapping, so "`directional` library expands to 5 families" is stated explicitly
- required columns per artifact (e.g. candidate CSV must carry `family`, `bar_ticks`, `horizon`, `state_id`, `train_count`; WFO prediction parquet must carry `candidate_uid`, `pred_prob`, `test_month`)
- the **key** of each artifact — whether it is uniquely identified by `(symbol, family)` or `(symbol, library)`. Verdict-bearing artifacts (Stage 5 schedules, Stage 6 tick-exact summaries) must be keyed by `(symbol, family)` so per-family verdicts never collide; library-keyed naming is only valid for artifacts that genuinely aggregate a whole library (e.g. the candidate CSVs).

Producers and consumers **import** the manifest rather than restating these facts:

- the mining writer derives its library-file list and the summary's library coverage from the manifest, removing the hardcoded lists at lines 1502 and 1544
- Stage 3 WFO derives candidate-file paths, family filters, and library ordering from the manifest
- Stage 3 WFO output files use an explicit, manifest-described naming policy for real and legitimately empty outputs, so downstream stages and operators do not infer family/library scope from inconsistent filenames
- Stage 6 tick-exact writes its verdict summary keyed by `(symbol, family)` per the manifest, so per-family `overall_pass` verdicts can never overwrite one another
- a test asserts code-matches-manifest, so the two cannot drift
- the existing `docs/generated/process/stageNN.md` generator renders the manifest into human/LLM-readable stage docs

## Consequences

- The "directional library contains 5 families" fact is declared once and discoverable without reading source — eliminating failure mode 1.
- `_build_summary` covers all libraries automatically; `candidate_summary.csv` stops under-reporting — eliminating failure mode 2.
- Stage 3 output naming becomes an explicit contract instead of an emergent behaviour split between real and empty runs — eliminating failure mode 3.
- Stage 6 tick-exact summaries are keyed by `(symbol, family)`, so per-family verdicts no longer collide — eliminating failure mode 4 (the destructive one).
- Adding a new family or library becomes a manifest edit plus its hooks, instead of coordinated edits across the writer, the summary, 66 WFO configs, and the registry.
- Upfront cost: the producers and consumers must be refactored to read the manifest rather than hardcode their lists. Until that refactor lands, a manifest added on its own would be a *fourth* place to keep in sync — therefore the manifest and the refactor must land together, not the manifest alone.
- Three immediate fixes fall out of this ADR and can ship ahead of the full manifest:
  - `_build_summary` (`scripts/run_tick_opportunity_mining.py:1502`) should receive all 7 libraries, not 3.
  - Candidate filenames (or an accompanying per-stage manifest/README) should expose the library→family expansion so the by-library organisation is self-describing.
  - WFO empty-output files should follow the same naming policy as real-output files, or the manifest should explicitly declare both patterns with their conditions.
  - **`verify_tick_exact_shortlist.py` must write `<SYMBOL>_<family>_tick_exact_summary.csv` (family-keyed), not `<SYMBOL>_<library>_...`** — this is the highest-priority standalone fix because it is the only one of the four that destroys data rather than merely obscuring it.
