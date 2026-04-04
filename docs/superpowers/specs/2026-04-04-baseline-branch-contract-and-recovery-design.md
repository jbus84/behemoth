# Baseline Branch Contract And Recovery Design

## Baseline Contract

- target branch: `main`
- target commit: `a939ec5`
- authoritative semantics:
  - repo workflow requires explicit target branch/commit for specs, plans, and execution
  - recurring Stage 14 demo-certification recovery must re-root onto `feat/bar-level-barrier-manager`
  - branch-semantic drift at final verification is a hard stop
- required compatibility checks:
  - confirm `AGENTS.md` states the branch-truth guardrail explicitly
  - confirm this spec and its implementation plan both carry a baseline contract block
  - confirm recovery work executes from a worktree based on `feat/bar-level-barrier-manager`

## Scope

Define a permanent workflow guardrail that prevents specs, plans, and implementation work from drifting away from the branch whose semantics they are supposed to describe.

This spec also defines the one-time recovery path for the current recurring Stage 14 demo-certification docs work, which was started on `main` even though the authoritative Stage 14 execution-lifecycle semantics live on `feat/bar-level-barrier-manager`.

## Goal

Stop recurring branch-truth mismatches by making the target branch and its semantics explicit before planning and execution begin.

The desired end state is:

- every spec identifies the branch and commit it describes
- every plan identifies the branch and commit it is meant to execute against
- execution refuses to proceed when branch semantics do not match the spec assumptions
- the current recurring demo-certification docs work is re-rooted onto the correct branch rather than patched against the wrong one

## Non-Goals

- redesigning the full superpowers workflow
- replacing git worktrees with another branching model
- enforcing a heavyweight release-management process for all work
- fixing unrelated repo process problems outside branch-semantic drift

## Problem

The current workflow can produce a silent mismatch:

1. a design is written against the intended architecture
2. the implementation branch is created from the local default branch
3. the target branch does not actually contain the semantics assumed by the spec
4. the mismatch is discovered late, usually during review or final verification

This is what happened with the recurring Stage 14 demo-certification docs:

- the docs/design assumed barrier-manager Stage 14 semantics
- execution started from `main`
- `main` still exposed legacy Stage 14 lifecycle naming and artifact semantics
- the mismatch surfaced only during final validation

That is a process failure, not a one-off docs bug.

## Approaches Considered

### Recommended: Add a required baseline branch contract to spec, plan, and execution

Require every spec and plan to declare the branch and commit whose semantics they target, and require execution to verify those semantics before Task 1 starts.

Why this is the right approach:

- it catches mismatches before implementation starts
- it fits the existing worktree-first workflow
- it makes the authoritative branch visible in the spec and plan themselves
- it turns branch-truth drift into an early hard fail rather than a late review surprise

### Rejected: Add guidance only to `AGENTS.md`

Repo guidance is useful but not sufficient on its own. If the branch contract is not embedded in specs and plans, it will be forgotten or skipped during execution.

### Rejected: Rely on final verification to catch drift

This is the current failure mode. It is too late, wastes work, and encourages patching docs to fit the wrong branch.

## Design

### 1. Add a baseline branch contract to every spec

Each new spec should begin with a short baseline block that states:

- target branch
- target commit
- authoritative semantics
- required compatibility checks

The purpose is to anchor the document to the branch truth it assumes.

Example:

```md
## Baseline Contract

- target branch: `feat/bar-level-barrier-manager`
- target commit: `36f1cde`
- authoritative semantics:
  - `execution_lifecycle_pass`
  - `*_jforex_execution_lifecycle_summary.csv`
  - barrier-manager Stage 14 authority pages
- compatibility checks:
  - grep for `execution_lifecycle_pass`
  - confirm Stage 14 docs use barrier-manager lifecycle language
  - confirm validator/report outputs match the spec vocabulary
```

This block should not be treated as optional metadata. It is part of the design contract.

### 2. Add a baseline branch contract to every implementation plan

The plan should repeat the same baseline contract so the execution branch can be checked without reopening the full spec.

The plan’s baseline block should be treated as operational:

- the worktree branch must match or be a descendant of the target branch
- the commit baseline must be known
- the required compatibility checks must be run before Task 1

This prevents the plan from silently drifting away from the spec’s assumptions.

### 3. Add a pre-execution semantic compatibility gate

Before Task 1 starts, execution must verify:

- the current worktree branch matches the target branch model from the spec/plan
- the branch contains the semantics the work assumes
- the authoritative files and artifact names referenced by the spec exist in the expected form

Examples of semantic compatibility checks:

- `rg execution_lifecycle_pass`
- `rg oco_lifecycle_pass`
- check whether Stage 14 docs, validator outputs, and generated reports use the expected vocabulary

If the compatibility checks fail, execution must stop immediately and re-root the work. It must not proceed and “fix it later.”

### 4. Add a repo-level guardrail in `AGENTS.md`

`AGENTS.md` should include a short explicit rule:

- no spec, plan, or implementation may proceed without identifying the target branch and commit
- if the requested work depends on semantics not present on `main`, execution must move to the authoritative feature branch
- if final verification exposes branch-semantic drift, stop and re-root the work rather than patching docs to fit the wrong branch

This gives the repo a simple global rule while leaving the detailed contract in the spec and plan.

### 5. Treat semantic drift as a hard blocker, not a docs polish issue

When branch truth and spec truth diverge, the agent should not try to “paper over” the mismatch with wording changes.

Instead, the required response is:

1. identify the authoritative branch
2. preserve current work
3. re-root the work onto the correct branch
4. rerun validation there

This is important because otherwise docs become inaccurate relative to the branch they live on.

### 6. Recovery path for the current recurring demo-certification docs work

For the current issue, the correct recovery is to re-root the docs work onto `feat/bar-level-barrier-manager`.

The recovery steps are:

1. preserve the current recurring-certification docs branch as a reference
2. create a fresh worktree from `feat/bar-level-barrier-manager`
3. reapply the recurring-certification docs changes there
4. drop any wording that was compensating for `main`’s older Stage 14 semantics
5. rerun docs validation there
6. finish that branch normally

This is the right fix because the recurring certification docs describe barrier-manager Stage 14 semantics that are already authoritative on that feature branch.

## Success Criteria

This work is successful when:

- new specs and plans explicitly declare the target branch and semantics they assume
- execution has a mandatory semantic compatibility check before Task 1
- `AGENTS.md` states the branch-truth rule clearly
- future branch-semantic mismatches are caught before implementation, not during final verification
- the current recurring demo-certification docs work is re-rooted onto `feat/bar-level-barrier-manager`

## Risks

- If the baseline block is added but never checked during execution, the process will still fail in practice.
- If the repo-level rule is too vague, agents will still improvise against `main`.
- If recovery work is merged without re-rooting, docs may become internally polished but branch-inaccurate.

## Implementation Notes

Primary targets for the process fix:

- `AGENTS.md`
- the current docs/process workflow surfaces where specs and plans are written

Primary target for recovery:

- re-root the recurring Stage 14 demo-certification docs branch onto `feat/bar-level-barrier-manager`

The implementation should keep the rule simple:

- declare branch truth
- verify branch truth
- stop if branch truth does not match the spec
