# ADR 0004: Stage I/O Contracts

- Status: Proposed
- Date: 2026-05-28

## Context

The tick-opportunity governance pipeline runs as a sequence of stages (Stage 2 mining → Stage 3 WFO → Stage 5 reduced-core → Stage 6 tick-exact → Stage 9 freeze). Each stage is coupled to its neighbours by file-naming and family/library conventions that are currently **implicit and scattered across multiple modules**, with no single declaration of what a stage consumes and produces.

Concrete facts a reader must currently reconstruct from source:

- Stage 2 mining (`scripts/run_tick_opportunity_mining.py`) writes candidate CSVs organised **by library, not by family**. Lines 1544–1559 hardcode exactly 7 library files: `directional`, `oco`, `oco_asymmetric`, `no_touch`, `dollar_residual`, `dispersion_rank`, `lead_lag`.
- A single library file holds multiple families. `<SYMBOL>_directional_candidates.csv` contains five families — `directional`, `directional_inverse`, `directional_run`, `double_touch`, `pullback` (verified: 6,426 rows on USDCAD).
- Stage 3 WFO (`scripts/run_tick_opportunity_monthly_wfo.py:438`) reads `<SYMBOL>_<library>_candidates.csv`, where the library comes from each WFO config's `library:` field and the families to extract from its `families:` field. This routing is spread across 66 per-(symbol × family) YAML configs plus `scripts/mining_family.py:FAMILY_REGISTRY`.
- The mining summary (`_build_summary`, called at `scripts/run_tick_opportunity_mining.py:1502`) is hardcoded to three libraries — `directional`, `oco`, `no_touch`. When `no_touch` is empty, `<SYMBOL>_candidate_summary.csv` reports only 2 of the 7 libraries actually written.

Two failure modes resulted during the 2026-05 multi-family trial — both false alarms caused purely by poor discoverability, not by any pipeline malfunction:

1. **"Missing families."** An operator (and an LLM) concluded `directional_inverse`, `directional_run`, `double_touch`, and `pullback` were missing because no per-family candidate file exists for them. In fact their candidates live inside `directional_candidates.csv`. Confirming this required reading three source files (the mining writer, the WFO config's `library:` field, and `FAMILY_REGISTRY`).
2. **"Only OCO and directional were mined."** `<SYMBOL>_candidate_summary.csv` showed only `directional` and `oco` rows, implying the other families were never produced. This was a false signal caused solely by the hardcoded 3-library `_build_summary` call; the candidate CSVs and the `candidate_fills` parquet contained all 10 families.

In both cases the pipeline functioned correctly and the data was complete. The defect is **discoverability**: there is no single, machine-readable declaration of each stage's I/O contract — input/output glob patterns, the family↔library↔artifact-name mapping, and required columns.

## Decision

Introduce a declarative **stage-contract manifest** as the single source of truth for inter-stage I/O. (Proposed; implementation deferred to a follow-up PR.)

The manifest — e.g. `src/behemoth/governance/stage_contracts.py` (importable) or `configs/pipeline/stage_contracts.yaml` (rendered into code) — declares, per stage:

- the producing stage and input artifact glob patterns
- output artifact glob patterns
- the family↔library↔artifact-name mapping, so "`directional` library expands to 5 families" is stated explicitly
- required columns per artifact (e.g. candidate CSV must carry `candidate_uid`, `pred_prob`, `test_month`, `family`, `bar_ticks`)

Producers and consumers **import** the manifest rather than restating these facts:

- the mining writer derives its library-file list and the summary's library coverage from the manifest, removing the hardcoded lists at lines 1502 and 1544
- Stage 3 WFO derives candidate-file paths and family filters from the manifest
- a test asserts code-matches-manifest, so the two cannot drift
- the existing `docs/generated/process/stageNN.md` generator renders the manifest into human/LLM-readable stage docs

## Consequences

- The "directional library contains 5 families" fact is declared once and discoverable without reading source — eliminating failure mode 1.
- `_build_summary` covers all libraries automatically; `candidate_summary.csv` stops under-reporting — eliminating failure mode 2.
- Adding a new family or library becomes a manifest edit plus its hooks, instead of coordinated edits across the writer, the summary, 66 WFO configs, and the registry.
- Upfront cost: the producers and consumers must be refactored to read the manifest rather than hardcode their lists. Until that refactor lands, a manifest added on its own would be a *fourth* place to keep in sync — therefore the manifest and the refactor must land together, not the manifest alone.
- Two immediate fixes fall out of this ADR and can ship ahead of the full manifest:
  - `_build_summary` (`scripts/run_tick_opportunity_mining.py:1502`) should receive all 7 libraries, not 3.
  - Candidate filenames (or an accompanying per-stage manifest/README) should expose the library→family expansion so the by-library organisation is self-describing.
