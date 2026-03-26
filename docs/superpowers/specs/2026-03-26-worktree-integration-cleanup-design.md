# Worktree Integration Cleanup Design

Date: 2026-03-26
Status: Proposed
Owner: Codex

## Problem

The repo has multiple active worktrees whose committed branch heads were not merged back into `main` after completion. In parallel, `main` and several worktrees contain uncommitted changes, including overlapping source edits and generated artifacts.

Current state:

- `main` has uncommitted edits in:
  - [server.py](/Users/danielfisher/repositories/behemoth/src/behemoth/api/server.py)
  - [registry.py](/Users/danielfisher/repositories/behemoth/src/behemoth/core/registry.py)
  - [test_registry.py](/Users/danielfisher/repositories/behemoth/tests/test_registry.py)
  - [tick_vault_data/logs.log](/Users/danielfisher/repositories/behemoth/tick_vault_data/logs.log)
- committed non-`main` branch heads exist for:
  - `feat-live-diagnostic-scripts-2026-03-25`
  - `feat-candidate-artifact-sync-2026-03-25`
  - `monthly-recert-manual-verification`
  - `dukascopy-paper-trading-readiness`
- multiple worktrees also contain dirty state that has not been reviewed or integrated

This creates two risks:

1. losing uncommitted work while cleaning up branch topology
2. polluting `main` with generated or half-verified state if everything is merged indiscriminately

## Goal

Safely reintegrate all committed branch heads into `main` while preserving all current uncommitted state for later review and recovery.

## Non-Goals

- Do not merge uncommitted work automatically into `main`
- Do not rewrite or delete safety snapshots during the initial cleanup
- Do not force generated artifact outputs into `main` unless they are explicitly reviewed and chosen afterward
- Do not solve outstanding feature-level bugs as part of this cleanup; this is repository state recovery first

## Recommended Approach

Use a preservation-first merge workflow:

1. snapshot every dirty worktree, including `main`
2. restore the original feature branches to their committed tips
3. merge only committed branch heads into `main`
4. verify after each merge
5. leave any uncommitted state parked on safety branches for explicit later review

This is safer than stash-only workflows and safer than trying to merge dirty worktrees directly.

## Design

### 1. Preservation Strategy

Every dirty worktree gets a dedicated safety branch created from its current `HEAD`, and its current dirty state is committed there as a WIP snapshot.

Required properties:

- tracked and untracked changes are both preserved
- the original feature branch name remains unchanged
- the safety branch acts as a recovery checkpoint, not as merge-ready history

Suggested naming:

- `safety/main-uncommitted-2026-03-26`
- `safety/feat-live-diagnostic-scripts-2026-03-26-wip`
- `safety/feat-candidate-artifact-sync-2026-03-26-wip`
- `safety/monthly-recert-manual-verification-2026-03-26-wip`

Clean worktrees do not need a safety branch unless later steps make that useful.

### 2. Merge Scope

After safety capture, only committed branch heads are eligible for merge into `main`.

Committed branch heads to integrate:

- `feat-live-diagnostic-scripts-2026-03-25`
- `feat-candidate-artifact-sync-2026-03-25`
- `monthly-recert-manual-verification`
- `dukascopy-paper-trading-readiness`

Safety branches are explicitly excluded from the merge scope. They are preservation points only.

### 3. Merge Order

Merge order should follow dependency and overlap risk:

1. `feat-live-diagnostic-scripts-2026-03-25`
2. `feat-candidate-artifact-sync-2026-03-25`
3. `monthly-recert-manual-verification`
4. `dukascopy-paper-trading-readiness`

Rationale:

- the live-diagnostic branch overlaps directly with the dirty `main` registry/server edits
- candidate artifact sync is operationally adjacent to the live diagnostic and recert path
- manual verification is mostly documentation/audit follow-through
- paper-trading readiness is broader JForex live-readiness work and should land after the lower-level recert/live-diagnostic changes

### 4. Merge Mechanics

Each merge into `main` should use `--no-ff` so the recovered work remains explicit in history.

Expected flow per branch:

1. ensure `main` is at the desired base and clean
2. merge branch head with `--no-ff`
3. resolve conflicts explicitly if needed
4. run the branch-specific verification checkpoint
5. proceed only if verification is acceptable

If a merge conflict reflects disagreement between committed branch history and parked uncommitted work, the committed branch wins for this phase. The parked uncommitted work remains on its safety branch for later review.

### 5. Verification Strategy

Verification happens after each merge, not only at the end.

Recommended checkpoints:

- After `feat-live-diagnostic-scripts-2026-03-25`:
  - targeted Python tests for registry/server/diagnostic surfaces
- After `feat-candidate-artifact-sync-2026-03-25`:
  - targeted sync/recert/governance tests
- After `monthly-recert-manual-verification`:
  - sanity-check modified docs/audit outputs
- After `dukascopy-paper-trading-readiness`:
  - targeted JForex/readiness verification
- Final integrated `main` check:
  - [git status](/Users/danielfisher/repositories/behemoth/.git)
  - combined targeted verification
  - inventory of any remaining safety-only work not reintroduced

The goal is not a full platform recert after every branch, but enough evidence to keep integration regressions localized.

## Failure Handling

If safety capture fails for any dirty worktree:

- stop the cleanup
- do not begin merging
- resolve preservation first

If a branch merge fails verification:

- stop the sequence
- keep the partially integrated `main` state explicit
- diagnose and fix before attempting the next branch

If safety-branch content later proves necessary:

- review it explicitly
- cherry-pick or reapply only the intended portions
- do not merge the safety branch wholesale

## Test Plan

### Preservation verification

- confirm each dirty worktree has a new safety branch
- confirm the safety branch contains the dirty tracked and untracked state
- confirm the original worktree can return to its committed branch tip

### Integration verification

- after each merge, run the branch-specific targeted tests
- ensure `main` remains in a known state before proceeding

### Final verification

- `git status --short --branch` on `main`
- targeted combined test pass for merged features
- explicit report of any parked safety branches and what they contain

## Risks

- some dirty worktree state may mix generated artifacts with real source changes, making later reintroduction selective rather than trivial
- committed branches may still conflict with one another despite being individually complete
- verification scope may need to widen if a merge surfaces unexpected cross-branch coupling

## Decision

Preserve all current dirty worktree state on dedicated safety branches first, then merge committed branch heads into `main` one by one with verification checkpoints after each merge.
