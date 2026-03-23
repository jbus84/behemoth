# Documentation Enhancement Roadmap Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Improve the repo documentation in phased batches so operators and new contributors can find the active system quickly, understand document authority, navigate the corpus cleanly, make deployment decisions confidently, and rely on durable generation guardrails.

**Architecture:** Execute the roadmap as a sequence of reader-first work packages. Start with landing pages, authority labels, and navigation, then improve operator decision-support pages, then add validation and metadata guardrails, and finally formalize compatibility and archive governance. Keep each phase independently shippable and verify with `mkdocs`, docs-contract tests, and targeted generator checks.

**Tech Stack:** Markdown, MkDocs, Python docs builders, `pytest`, `uv`, repo-local docs generation scripts

---

## Scope Notes

This roadmap covers multiple independent documentation subsystems. Do not implement it as one giant branch unless explicitly requested. Preferred execution is one phase per branch:
- Phase 1: Entrypoints and orientation
- Phase 2: Authority hierarchy and truth-source labeling
- Phase 3: Navigation and taxonomy
- Phase 4: Operator decision support
- Phase 5: Generation quality and guardrails
- Phase 6: Archive and compatibility governance

Each phase should leave the docs site in a coherent and publishable state on its own.

## File Map

### Core Reader Entrypoints
- Modify: `docs/index.md`
- Modify: `docs/walkthrough.md`
- Modify: `docs/STRATEGY_MASTER_MANUAL.md`
- Modify: `docs/analysis/index.md`
- Modify: `mkdocs.yml`

### Authority and Governance Surfaces
- Modify: `docs/strategy_bible/generated/pipeline_snapshot.md`
- Modify: `docs/strategy_bible/generated/stage_09_snapshot.md`
- Modify: `docs/analysis/operator_action_report.md`
- Modify: `docs/analysis/oco_alert_remediation_report.md`
- Modify: `docs/deployment.md`
- Modify: `configs/research/docs/oco_bible_manifest.yaml`

### Generation and Catalog Builders
- Modify: `scripts/build_docs_catalog.py`
- Modify: `scripts/build_oco_system_reference_docs.py`
- Modify: `scripts/validate_oco_docs_contract.py`
- Modify or Create: `tests/test_oco_docs_contract.py`
- Create: `tests/test_docs_catalog_generation.py`
- Create: `tests/test_generated_doc_metadata.py`

### Compatibility and Archive Surfaces
- Modify: `docs/analysis/ftmo_risk_compliance_report.md`
- Modify: `docs/analysis/catalog_gaps_report.md`
- Modify: `docs/analysis/taxonomy_rules.md`
- Modify: `docs/analysis/dukascopy_candidate/index.md` if present
- Modify: `mkdocs.yml`

### Planning and Audit References
- Reference: `docs/superpowers/specs/2026-03-20-documentation-enhancement-roadmap-design.md`
- Reference: `docs/superpowers/audits/2026-03-20-documentation-audit-findings.md`
- Reference: `docs/superpowers/audits/2026-03-20-documentation-audit-recommendations.md`

### Verification Commands
- `uv run pytest -q tests/test_oco_docs_contract.py`
- `uv run mkdocs build`
- `uv run python scripts/build_docs_catalog.py`
- `uv run python scripts/build_oco_system_reference_docs.py`
- `uv run python scripts/validate_oco_docs_contract.py --out-checks-csv data/analysis/tick_opportunity_mining/docs_contract_checks.csv --out-issues-csv data/analysis/tick_opportunity_mining/docs_contract_issues.csv --report-out docs/analysis/oco_docs_contract_report.md`

### Task 1: Phase 1 Spec and Baseline for Entrypoints

**Files:**
- Modify: `docs/index.md`
- Modify: `docs/walkthrough.md`
- Modify: `docs/STRATEGY_MASTER_MANUAL.md`
- Test: `tests/test_oco_docs_contract.py`

- [ ] **Step 1: Capture the current entrypoint experience**

Run: `rg -n "Active symbol universe|What Is Active|Read this next|Compatibility" docs/index.md docs/walkthrough.md docs/STRATEGY_MASTER_MANUAL.md`
Expected: existing entrypoint language is incomplete or inconsistent across the landing docs

- [ ] **Step 2: Define the standard landing-page pattern in the plan branch**

Document the required blocks for top-level docs:
- active system summary
- audience statement
- authority statement
- read-this-next links

Expected: a short written checklist exists in the branch notes or implementation scratchpad before editing docs

- [ ] **Step 3: Rewrite `docs/index.md` to follow the standard pattern**

Include:
- active system summary
- active symbol universe
- key authority links
- operator/new-contributor split reading paths

- [ ] **Step 4: Rewrite `docs/walkthrough.md` into the primary onboarding route**

Include:
- what is active
- how the stages fit together
- where to start based on user role
- explicit next-doc links

- [ ] **Step 5: Add a concise orientation preface to `docs/STRATEGY_MASTER_MANUAL.md`**

Include:
- what the manual is authoritative for
- what generated snapshots are authoritative for
- where readers should go for deployment readiness

- [ ] **Step 6: Run targeted verification**

Run: `uv run pytest -q tests/test_oco_docs_contract.py`
Expected: PASS

- [ ] **Step 7: Build the docs site**

Run: `uv run mkdocs build`
Expected: PASS

- [ ] **Step 8: Commit Phase 1**

```bash
git add docs/index.md docs/walkthrough.md docs/STRATEGY_MASTER_MANUAL.md
git commit -m "docs: strengthen reader entrypoints and orientation"
```

### Task 2: Phase 2 Authority Hierarchy and Truth-Source Labeling

**Files:**
- Modify: `docs/index.md`
- Modify: `docs/deployment.md`
- Modify: `docs/strategy_bible/generated/pipeline_snapshot.md`
- Modify: `docs/strategy_bible/generated/stage_09_snapshot.md`
- Modify: `docs/analysis/operator_action_report.md`
- Modify: `docs/analysis/oco_alert_remediation_report.md`
- Modify: `configs/research/docs/oco_bible_manifest.yaml`

- [ ] **Step 1: Inventory authority-bearing docs and label gaps**

Run: `rg -n "authoritative|canonical|generated|compatibility|archive|candidate" docs/index.md docs/deployment.md docs/strategy_bible/generated/pipeline_snapshot.md docs/strategy_bible/generated/stage_09_snapshot.md docs/analysis/operator_action_report.md docs/analysis/oco_alert_remediation_report.md`
Expected: some pages lack clear authority role language

- [ ] **Step 2: Define the authority vocabulary**

Write the exact label set to use consistently:
- canonical
- generated truth snapshot
- interpretive report
- compatibility
- candidate
- archive

Expected: wording is chosen once and reused verbatim

- [ ] **Step 3: Add authority blocks to the major landing and decision docs**

Update the listed docs so each one states:
- what it is authoritative for
- what it is not authoritative for
- what upstream artifact or process it depends on

- [ ] **Step 4: Update docs manifest metadata if needed**

Adjust `configs/research/docs/oco_bible_manifest.yaml` so manifest-driven pages can carry clearer authority intent where applicable.

- [ ] **Step 5: Run docs build and spot-check rendered wording**

Run: `uv run mkdocs build`
Expected: PASS and no broken cross-links introduced by the new authority sections

- [ ] **Step 6: Commit Phase 2**

```bash
git add docs/index.md docs/deployment.md docs/strategy_bible/generated/pipeline_snapshot.md docs/strategy_bible/generated/stage_09_snapshot.md docs/analysis/operator_action_report.md docs/analysis/oco_alert_remediation_report.md configs/research/docs/oco_bible_manifest.yaml
git commit -m "docs: clarify authority hierarchy across key surfaces"
```

### Task 3: Phase 3 Navigation and Taxonomy Alignment

**Files:**
- Modify: `mkdocs.yml`
- Modify: `docs/analysis/index.md`
- Modify: `docs/analysis/catalog_gaps_report.md`
- Modify: `docs/analysis/taxonomy_rules.md`
- Modify: `scripts/build_docs_catalog.py`
- Test: `tests/test_docs_catalog_generation.py`

- [ ] **Step 1: Write the failing taxonomy tests**

Create tests that assert:
- active/core reports appear separately from compatibility reports
- candidate reports are labeled distinctly
- generated analysis index includes the expected section headers

Example skeleton:

```python
def test_analysis_index_separates_compatibility_section():
    rendered = build_analysis_index_fixture()
    assert "## Compatibility / Legacy Reports" in rendered
    assert "## Core Active Reports" in rendered
```

- [ ] **Step 2: Run the new tests and confirm failure**

Run: `uv run pytest -q tests/test_docs_catalog_generation.py`
Expected: FAIL because the current catalog builder does not yet enforce the new taxonomy contract

- [ ] **Step 3: Rework `scripts/build_docs_catalog.py` and related docs outputs**

Implement:
- reader-intent taxonomy
- consistent section naming
- candidate vs compatibility vs archive labeling
- mirrored language between generated index and taxonomy rules docs

- [ ] **Step 4: Align `mkdocs.yml` with the same taxonomy**

Ensure site nav order matches:
- start here / orientation
- active system
- operator decision support
- evidence and analysis
- compatibility
- candidate
- archive

- [ ] **Step 5: Rebuild generated catalog docs**

Run: `uv run python scripts/build_docs_catalog.py`
Expected: updated `docs/analysis/index.md`, `docs/analysis/catalog_gaps_report.md`, and `docs/analysis/taxonomy_rules.md`

- [ ] **Step 6: Re-run tests and docs build**

Run: `uv run pytest -q tests/test_docs_catalog_generation.py tests/test_oco_docs_contract.py`
Expected: PASS

Run: `uv run mkdocs build`
Expected: PASS

- [ ] **Step 7: Commit Phase 3**

```bash
git add mkdocs.yml scripts/build_docs_catalog.py docs/analysis/index.md docs/analysis/catalog_gaps_report.md docs/analysis/taxonomy_rules.md tests/test_docs_catalog_generation.py
git commit -m "docs: align taxonomy and navigation with reader intent"
```

### Task 4: Phase 4 Operator Decision-Support Upgrade

**Files:**
- Modify: `docs/deployment.md`
- Modify: `docs/analysis/operator_action_report.md`
- Modify: `docs/analysis/oco_alert_remediation_report.md`
- Modify: `docs/strategy_bible/generated/stage_09_snapshot.md`
- Modify: `scripts/build_oco_system_reference_docs.py`
- Test: `tests/test_oco_docs_contract.py`

- [ ] **Step 1: Identify the operator questions each page must answer**

Document the required questions:
- is the system deployable?
- what blocks deployment?
- what is monitored but non-blocking?
- what artifact should the operator inspect next?

Expected: each target doc is mapped to one or more operator questions before editing

- [ ] **Step 2: Add explicit decision sections to the operator-facing docs**

Implement sections such as:
- current decision status
- hard blockers
- monitored risks
- next required checks

- [ ] **Step 3: Improve generated deployment/system-reference phrasing**

Update `scripts/build_oco_system_reference_docs.py` so generated summaries explain missing or partial evidence clearly instead of rendering silent empty sections.

- [ ] **Step 4: Rebuild affected generated pages if artifacts are available**

Run: `uv run python scripts/build_oco_system_reference_docs.py`
Expected: PASS if local artifacts exist; otherwise capture the limitation explicitly in the phase notes and validate only the script-level change

- [ ] **Step 5: Run targeted verification**

Run: `uv run pytest -q tests/test_oco_docs_contract.py`
Expected: PASS

Run: `uv run mkdocs build`
Expected: PASS

- [ ] **Step 6: Commit Phase 4**

```bash
git add docs/deployment.md docs/analysis/operator_action_report.md docs/analysis/oco_alert_remediation_report.md docs/strategy_bible/generated/stage_09_snapshot.md scripts/build_oco_system_reference_docs.py
git commit -m "docs: improve operator decision support surfaces"
```

### Task 5: Phase 5 Generation Guardrails and Metadata Contract

**Files:**
- Modify: `scripts/build_docs_catalog.py`
- Modify: `scripts/build_oco_system_reference_docs.py`
- Modify: `scripts/validate_oco_docs_contract.py`
- Modify: `tests/test_oco_docs_contract.py`
- Create: `tests/test_generated_doc_metadata.py`

- [ ] **Step 1: Write failing validation tests for generated-doc metadata and consistency**

Create tests that assert generated docs expose or imply:
- symbol
- runtime family
- authority class
- provenance or source generator

Example skeleton:

```python
def test_generated_doc_exposes_authority_class():
    metadata = parse_generated_doc_metadata(sample_doc)
    assert metadata["authority_class"] in {"generated_truth_snapshot", "interpretive_report"}
```

- [ ] **Step 2: Run tests and confirm they fail**

Run: `uv run pytest -q tests/test_generated_doc_metadata.py tests/test_oco_docs_contract.py`
Expected: FAIL because the validation path does not yet enforce the metadata contract

- [ ] **Step 3: Implement the minimal metadata and validation path**

Add:
- generator-emitted metadata blocks or parsable markers
- docs-contract checks for empty generated sections
- docs-contract checks for title/symbol/runtime drift where appropriate

- [ ] **Step 4: Regenerate affected docs or fixtures**

Run the minimal set of generator commands needed to produce representative outputs for the new checks.

- [ ] **Step 5: Re-run verification**

Run: `uv run pytest -q tests/test_generated_doc_metadata.py tests/test_oco_docs_contract.py`
Expected: PASS

Run: `uv run mkdocs build`
Expected: PASS

- [ ] **Step 6: Commit Phase 5**

```bash
git add scripts/build_docs_catalog.py scripts/build_oco_system_reference_docs.py scripts/validate_oco_docs_contract.py tests/test_oco_docs_contract.py tests/test_generated_doc_metadata.py
git commit -m "docs: add generation guardrails and metadata checks"
```

### Task 6: Phase 6 Compatibility and Archive Governance

**Files:**
- Modify: `mkdocs.yml`
- Modify: `docs/analysis/ftmo_risk_compliance_report.md`
- Modify: `docs/analysis/index.md`
- Modify: `docs/analysis/catalog_gaps_report.md`
- Modify: `docs/analysis/taxonomy_rules.md`
- Modify: `configs/research/docs/oco_bible_manifest.yaml`

- [ ] **Step 1: Write the publication policy before editing docs**

Define:
- what counts as compatibility
- what counts as candidate
- what counts as archive
- what remains in default nav vs lower-prominence nav

Expected: a short policy note exists in the branch notes or phase scratch file

- [ ] **Step 2: Apply that policy to visible docs and nav**

Update:
- compatibility banners
- nav grouping
- generated taxonomy explanations
- manifest metadata if needed

- [ ] **Step 3: Audit a sample of compatibility pages against the new policy**

Check at least:
- FTMO/cBot surface
- TestClient/cTrader compatibility surface
- dukascopy candidate surface

Expected: each sample page clearly matches one classification

- [ ] **Step 4: Rebuild generated docs and site**

Run: `uv run python scripts/build_docs_catalog.py`
Expected: PASS

Run: `uv run mkdocs build`
Expected: PASS

- [ ] **Step 5: Commit Phase 6**

```bash
git add mkdocs.yml docs/analysis/ftmo_risk_compliance_report.md docs/analysis/index.md docs/analysis/catalog_gaps_report.md docs/analysis/taxonomy_rules.md configs/research/docs/oco_bible_manifest.yaml
git commit -m "docs: formalize compatibility and archive governance"
```

### Task 7: Final Program Verification and Closeout

**Files:**
- Verify only

- [ ] **Step 1: Run the docs-contract workflow**

Run:

```bash
uv run python scripts/validate_oco_docs_contract.py \
  --out-checks-csv data/analysis/tick_opportunity_mining/docs_contract_checks.csv \
  --out-issues-csv data/analysis/tick_opportunity_mining/docs_contract_issues.csv \
  --report-out docs/analysis/oco_docs_contract_report.md
```

Expected: command completes successfully; known `C4A` caveat may remain unless this program explicitly fixes it

- [ ] **Step 2: Run the test suite for docs work**

Run: `uv run pytest -q tests/test_oco_docs_contract.py tests/test_docs_catalog_generation.py tests/test_generated_doc_metadata.py`
Expected: PASS for all tests introduced by the roadmap phases

- [ ] **Step 3: Build the docs site**

Run: `uv run mkdocs build`
Expected: PASS

- [ ] **Step 4: Review `git status --short` for unintended churn**

Expected: only intended docs, scripts, tests, and generated artifacts are modified

- [ ] **Step 5: Summarize residual risks**

Capture any unresolved items such as:
- ignored local artifact dependencies
- compatibility surfaces intentionally retained
- known docs-contract caveats not addressed by the program

- [ ] **Step 6: Commit final cleanup if needed**

```bash
git add .
git commit -m "docs: finalize roadmap phase verification"
```

## Execution Guidance

- Prefer one dedicated worktree per phase.
- Do not mix reader-facing rewrites with broad generator refactors unless the phase explicitly calls for it.
- If a generated page depends on ignored local artifacts that are unavailable in the worktree, keep the code fix, note the regeneration constraint, and avoid inventing fake outputs.
- Preserve pre-existing local data changes and unrelated untracked planning/spec files.

## Recommended First Execution Batch

Start with a combined implementation plan for:
1. Entrypoints and orientation
2. Authority hierarchy and truth-source labeling
3. Navigation and taxonomy

That batch will produce the biggest reader-visible improvement and create the structure that later operator-support and generator-guardrail work should reinforce.
