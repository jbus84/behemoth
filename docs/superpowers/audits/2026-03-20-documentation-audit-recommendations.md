# Documentation Audit Recommendations

## Quick Wins

1. Fix the six-symbol overview on `docs/index.md` and expand the top-level expected-gross summary to cover all active symbols.
2. Replace incorrect `EURUSD` H1 headings in all non-EURUSD monthly WFO reports by fixing the generation template and regenerating the affected report family.
3. Rename TestClient parity report titles so they stop presenting Dukascopy/TestClient work as `cTrader Execution Parity`.
4. Add explicit empty-state messaging to `docs/deployment.md` when generated tables have no usable values.
5. Add a compatibility-only banner to FTMO/cBot-facing docs that remain in the published corpus.

## Structural Improvements

1. Rework `docs/analysis/index.md` into clearer sections:
   - `Core Active Reports`
   - `Compatibility / Legacy`
   - `Candidate / Pre-Promotion`
   - `Archive`
2. Promote the repo’s authority hierarchy more consistently across landing pages:
   - strategy manual as synthesis layer
   - generated snapshots and contract checks as governed truth
   - analysis reports as evidence and operational interpretation
3. Expand or replace `docs/walkthrough.md` so it becomes a real onboarding route instead of a short deprecation note.
4. Standardize report-title templates across symbol-specific generated docs so path, title, and symbol metadata cannot drift independently.

## Generation and Process Fixes

1. Add a docs-generation validation check for symbol/title consistency in symbol-scoped reports.
2. Add a docs-generation validation check for runtime-label consistency:
   - `TestClient` reports must not emit `cTrader` H1 labels unless explicitly configured
3. Add a generated-empty-section check for published system-reference pages such as `docs/deployment.md`.
4. Extend the docs contract or a related reporting check to flag catalog pages that mix active and compatibility reports without labeling.
5. Review whether FTMO/cBot report families should stay in the default published site nav or move behind a compatibility grouping.

## Suggested Execution Order

1. Fix authority and labeling errors that can change a reader’s understanding of the active system:
   - `docs/index.md`
   - monthly WFO report headings
   - TestClient parity report titles
2. Fix broken-looking generated output:
   - `docs/deployment.md` empty table handling
3. Fix discoverability and classification:
   - `docs/analysis/index.md`
   - compatibility / candidate / archive grouping
4. Fix onboarding shape:
   - `docs/walkthrough.md`
5. Add generation safeguards so the same classes of errors stop recurring.

## Proposed Follow-On Work Packages

### Package A: Authority and Labeling Cleanup

- Update top-level docs and report generators
- Regenerate the affected report families
- Rebuild the docs site and confirm labels/titles are corrected

### Package B: Catalog and Navigation Cleanup

- Rework `docs/analysis/index.md`
- review `mkdocs.yml` groupings for active vs compatibility vs archive surfaces
- ensure candidate artifacts are clearly marked as non-primary

### Package C: Generation Guardrails

- add automated checks for symbol/title drift
- add automated checks for empty published sections
- add automated checks for legacy-runtime wording in active report families
