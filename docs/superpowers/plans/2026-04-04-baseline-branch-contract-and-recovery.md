# Baseline Branch Contract And Recovery Plan

## Baseline Contract

- target branch: `main`
- target commit: `a939ec5`
- authoritative semantics:
  - repo workflow requires explicit target branch/commit for specs, plans, and execution
  - recurring Stage 14 demo-certification recovery must re-root onto `feat/bar-level-barrier-manager`
  - branch-semantic drift at final verification is a hard stop
- required compatibility checks:
  - confirm `AGENTS.md` states the branch-truth guardrail explicitly
  - confirm this plan and its governing spec both carry a baseline contract block
  - confirm recovery work executes from a worktree based on `feat/bar-level-barrier-manager`

## Goal

Add the permanent branch-baseline guardrail to the repo workflow, then recover the recurring Stage 14 demo-certification docs work by replaying it onto the authoritative feature branch instead of `main`.

## Tasks

1. Add repo-level baseline branch guardrail
2. Add baseline contract blocks to spec and plan
3. Preserve current reference branch and create recovery worktree
4. Reapply recurring certification docs onto authoritative branch
5. Validate recovery branch end to end

## Execution Notes

- Task 1 edits `AGENTS.md` to enforce branch truth directly in repo guidance.
- Task 2 updates the governing spec and creates this implementation plan so the baseline is embedded in the artifacts themselves.
- Task 3 preserves the existing recurring-certification docs branch as the reference source of truth and creates a fresh worktree from `feat/bar-level-barrier-manager`.
- Task 4 replays only the recurring certification docs/process changes onto the authoritative branch, dropping any wording that was compensating for stale `main` semantics.
- Task 5 runs docs and semantic verification on the recovered branch so the work finishes against actual branch truth.
