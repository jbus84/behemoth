# Doc-First Documentation Update Design

**Date:** 2026-03-20
**Status:** Approved for planning
**Owner:** Codex

## Objective

Resolve the highest-signal documentation issues from the March 20 documentation audit by updating the main reader-facing docs directly and fixing the generator-driven title errors in the affected report families.

## Scope

This batch includes:

- Manual doc updates for:
  - `docs/index.md`
  - `docs/deployment.md`
  - `docs/analysis/index.md`
  - `docs/walkthrough.md`
  - `docs/analysis/ftmo_risk_compliance_report.md`
- Generator/template fixes for:
  - monthly WFO report H1 titles
  - TestClient parity report H1 titles
- Regeneration of the affected report families after those generator fixes

This batch explicitly excludes:

- broad `mkdocs.yml` restructuring
- archive-wide reclassification
- full FTMO/cBot content removal
- new docs-contract rules or validation infrastructure
- unrelated wording cleanup outside the identified WFO/TestClient title issues

## Design Principles

- Fix the most misleading reader-facing errors first.
- Keep the rewrite batch tight enough to execute and verify in one pass.
- Prefer fixing generators over patching derived reports by hand.
- Preserve the repo's documented authority model:
  - the strategy manual is synthesis
  - generated stage artifacts and contract checks remain governed truth
  - analysis pages are evidence and interpretation layers

## Desired Content Behavior

### Landing and Onboarding Docs

- `docs/index.md` should reflect the active six-symbol universe and present an accurate top-level summary of the governed system.
- `docs/walkthrough.md` should become a useful onboarding bridge that tells a contributor where to start and how the major documentation layers relate.

### Operational and Catalog Docs

- `docs/deployment.md` should not present empty generated tables as meaningful data.
- `docs/analysis/index.md` should classify core active reports versus compatibility/legacy-style reports more honestly.
- `docs/analysis/ftmo_risk_compliance_report.md` should clearly frame FTMO/cBot material as compatibility-oriented rather than central to the active JForex-directed runtime.

### Generated Report Families

- Monthly WFO reports must use the correct symbol in the H1.
- TestClient parity reports must use a title that matches the actual runtime or harness being discussed rather than defaulting to `cTrader Execution Parity`.

## Execution Strategy

The implementation should proceed in this order:

1. Inspect the manual docs and the generator code paths that emit the affected report titles.
2. Update the manual docs.
3. Patch the generator/template sources for WFO and TestClient parity titles.
4. Regenerate only the affected report families.
5. Run targeted verification and spot checks.

## Definition of Done

This batch is complete when:

- `docs/index.md` accurately reflects the active six-symbol system
- `docs/deployment.md` handles empty generated sections explicitly
- `docs/analysis/index.md` better separates core active material from compatibility/legacy material
- `docs/walkthrough.md` serves as a real onboarding path
- `docs/analysis/ftmo_risk_compliance_report.md` is clearly compatibility-framed
- regenerated non-EURUSD monthly WFO reports no longer claim `EURUSD` in the title
- regenerated TestClient parity reports no longer use incorrect `cTrader` H1 labels
- targeted verification passes

## Constraints

- If regeneration requires unavailable external artifacts or long-running upstream rebuilds rather than local report generation, stop and surface that dependency.
- Existing unrelated local changes in the repo must be preserved.
