# Full Documentation Audit Design

**Date:** 2026-03-20
**Status:** Approved for planning
**Owner:** Codex

## Objective

Define a single exhaustive audit of the Behemoth documentation corpus that supports both operator use and new-contributor onboarding, then use that audit to propose concrete documentation improvements.

## Scope

The audit covers all documentation surfaces that describe, expose, or constrain the active system:

- Canonical strategy documentation, especially `docs/STRATEGY_MASTER_MANUAL.md`
- Human-authored strategy bible docs under `docs/strategy_bible/`
- Generated strategy snapshots under `docs/strategy_bible/generated/`
- Generated Dukascopy candidate snapshots under `docs/strategy_bible/generated_dukascopy_candidate/`
- Analysis and operational reports under `docs/analysis/`
- Top-level docs and site pages referenced from `mkdocs.yml`
- Documentation-adjacent governance and config surfaces under `configs/research/governance/` that define what docs should say

The audit is intentionally exhaustive. Generated docs and snapshots are not excluded; they are first-class review targets.

## Audit Style

The chosen method is a flat exhaustive audit.

Every in-scope document is reviewed with the same base checklist rather than triaging by risk or reader journey. This is intentionally inefficient, but it is appropriate for an early-stage corpus review where the goal is broad visibility into documentation quality, not optimized review throughput.

## Review Dimensions

Each document is reviewed against the following dimensions:

- `Authority`: whether the doc clearly signals if it is canonical, generated, derived, archived, or advisory
- `Accuracy`: whether claims match the active system, runtime direction, symbol universe, and governance posture
- `Consistency`: whether it agrees with related docs, generated artifacts, configs, and site navigation
- `Completeness`: whether it contains the caveats, prerequisites, outputs, or interpretation guidance a reader needs
- `Audience fit`: whether it works for operators and new contributors, or clearly states who it is for
- `Actionability`: whether the next action, command, artifact, or dependency is clear
- `Staleness`: whether dates, versions, symbols, stage references, or legacy assumptions have drifted
- `Traceability`: whether important claims can be traced to scripts, configs, or generated artifacts
- `Navigation`: whether the document is discoverable and linked correctly from the site structure
- `Improvement potential`: whether a concrete rewrite, restructure, de-duplication, or generation fix is apparent

## Execution Model

The audit proceeds in five layers:

1. Build a master inventory from `mkdocs.yml`, `docs/`, and key governance/config sources.
2. Review each document individually using a shared worksheet and log findings immediately.
3. Cross-check documents that claim authority against the repo's stated authority hierarchy.
4. Distinguish content problems from generation-process problems where docs are derived artifacts.
5. Synthesize a recommendation package grouped by severity and type of fix.

## Expected Outputs

The audit should produce:

- A complete inventory of all reviewed documents
- A findings log with severity, category, and file references
- A recommendation summary grouped into quick wins, structural changes, and process/generation fixes
- A prioritized summary of improvements for operators, new contributors, and governance accuracy

## Definition of Done

The audit is complete when:

- Every in-scope document has an inventory row
- Every document has been reviewed against the full checklist
- Contradictions and likely contradictions are logged with file references
- Improvement proposals are specific enough to execute in a later rewrite pass
- The final package separates reader-facing problems from doc-generation/process problems

## Constraints and Notes

- The first pass is diagnostic, not a rewrite campaign.
- Immediate edits should be out of scope unless needed to unblock the audit itself.
- The audit should preserve the repo's stated authority rules: generated stage artifacts and contract checks outrank conflicting prose where documented.
- Because the current worktree already contains unrelated changes, the audit artifacts should be added without disturbing existing modifications.
