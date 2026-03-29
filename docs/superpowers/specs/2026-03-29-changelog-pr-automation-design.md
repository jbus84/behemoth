# Changelog, PR Automation & Methodology Decision Trail

## Goal

Add conventional commits, semantic versioning, auto-generated changelogs, GitHub Actions CI, automated PR workflow, and a structured methodology decision trail so that pipeline changes are discoverable by both humans and LLMs without drift.

## Architecture

Four components layered on the existing worktree development flow:

1. **Commitizen** for commit validation, version bumping, and changelog generation
2. **GitHub Actions** for CI checks and post-merge automation
3. **Makefile `pr` target** for one-command PR creation with auto-merge
4. **Methodology commit convention** enforced by CI

## 1. Conventional Commits & Commitizen

### Setup

- Add `commitizen` as a dev dependency
- Configure in `pyproject.toml`:
  - Commit types: `feat`, `fix`, `refactor`, `docs`, `ci`, `chore`, `test`
  - Version provider: `pyproject.toml`
  - Changelog format: markdown, grouped by version then type
- Starting version: `v0.1.0`

### Scope Convention

Methodology-relevant scopes that map to pipeline components:

- `wfo` — walk-forward optimization, training/test splits
- `threshold` — threshold selection, rolling/static, quantile logic
- `stage-N` — changes to a specific pipeline stage
- `execution` — execution realism, stop-limit, cap logic
- `data` — data sources, tick download, tick bar construction
- `reduced-core` — state selection, reduced core rolling

Example: `feat(threshold): accumulate test-day predictions in rolling threshold`

### Pre-commit Hook

Add `cz check` as a pre-commit hook to reject non-conventional commit messages. Installed via `make precommit-install` (extend existing hook setup).

### Version Bumping

- `cz bump` auto-increments from commit types: `feat` → minor, `fix` → patch, `feat!` or `BREAKING CHANGE` → major
- Version stored in `pyproject.toml` `[project] version` field

### Changelog

- `cz changelog` generates `CHANGELOG.md` from git history
- Grouped by version, then by type (Features, Fixes, Refactors, etc.)
- Methodology-scoped commits surface naturally in the changelog

## 2. GitHub Actions CI

### `ci.yml` — runs on push and PR

Jobs:

```yaml
steps:
  - make test
  - make quality
  - make docs-contract-ci
  - cz check --rev-range $BASE..$HEAD
```

Validates code correctness, quality, docs completeness, and commit format.

### `changelog-check.yml` — runs on PRs only

For commits with methodology-relevant scopes (`wfo`, `threshold`, `stage-*`, `execution`, `data`, `reduced-core`), verify the commit body includes:
- `Why:` line — rationale for the change
- `Impact:` line — what improved or changed

Rejects the PR if missing. Implemented as a shell script that parses `git log` output.

### `auto-merge.yml` — runs after CI passes on PRs

- Enables auto-merge via `gh pr merge --auto --squash`
- Squash merge keeps changelog clean (one entry per PR)

### `release.yml` — runs on push to main

- Triggered after PR merge lands on `main`
- Runs `cz bump --changelog --yes`
- Commits version bump + updated `CHANGELOG.md` to `main`
- Creates a GitHub release tag

## 3. Automated PR Workflow

### `make pr` target

```makefile
pr:
	git push -u origin HEAD
	gh pr create \
		--title "$$(git log main..HEAD --format='%s' | head -1)" \
		--body "$$(git log main..HEAD --format='- %s%n%b')" \
		--fill
	gh pr merge --auto --squash
```

Flow: run `make pr` when worktree work is done. CI runs. PR auto-merges if green. If CI fails, fix and push — auto-merge is already enabled.

## 4. Methodology Decision Trail

### Commit Body Convention

Any commit that changes pipeline methodology must use a methodology scope and include a structured body:

```
feat(threshold): accumulate test-day predictions in rolling threshold

Why: Frozen train-only threshold drifted from prediction distribution
     mid-month, causing fill rate drops to 84% on some symbols.

Impact: Fill rates improved from 84-97% to 98-99%. Mean gross pips
        unchanged -- same edge, more signals filled.

Before: Threshold frozen at train-end, applied statically across test month.
After: Threshold updates day-by-day as test predictions accumulate.
```

Required fields for methodology scopes:
- `Why:` — rationale
- `Impact:` — what changed in outcomes

Optional but encouraged:
- `Before:` — old behavior
- `After:` — new behavior

### LLM Discoverability

An LLM can reconstruct the full methodology evolution via:

```bash
git log --all --grep="^feat(threshold)\|^fix(wfo)\|^feat(stage-" --format="%h %ad %s%n%b" --date=short
```

No separate decision log to maintain. The changelog groups these by version. The commit history is the source of truth.

## What Does Not Change

- Existing `docs/strategy_bible/` structure — unchanged
- Existing `docs/superpowers/specs/` design spec flow — unchanged
- `make docs-contract-ci` — unchanged, added as CI step
- Existing pre-commit hooks — extended, not replaced
- Direct pushes to `main` for emergency fixes — still possible, but conventional commit format still enforced by pre-commit hook

## Testing

- `cz check` rejects a non-conventional commit message
- `cz check` accepts a properly formatted conventional commit
- `changelog-check.yml` rejects a `feat(threshold):` commit without `Why:` in body
- `changelog-check.yml` accepts a `feat(threshold):` commit with `Why:` and `Impact:` in body
- `changelog-check.yml` does not check non-methodology commits (e.g., `docs:` or `chore:`)
- `make pr` creates a PR and enables auto-merge
- `release.yml` bumps version and updates CHANGELOG after merge to main
- `make test`, `make quality`, `make docs-contract-ci` all pass in CI
