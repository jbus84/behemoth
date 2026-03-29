# Changelog, PR Automation & Methodology Trail Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add commitizen-based conventional commits, semantic versioning, auto-changelog, GitHub Actions CI with methodology enforcement, and a `make pr` target for automated PR creation with auto-merge.

**Architecture:** Commitizen configured in `pyproject.toml` with a pre-commit hook for commit validation. Three new GitHub Actions workflows handle CI, changelog enforcement, and post-merge release automation. A new `make pr` Makefile target wraps `gh pr create` + `gh pr merge --auto`.

**Tech Stack:** commitizen (Python), GitHub Actions, gh CLI, pre-commit

---

## File Structure

```
pyproject.toml                          — Modify: add commitizen config + dev dependency
.pre-commit-config.yaml                 — Modify: add commitizen commit-msg hook
.github/workflows/ci.yml                — Create: unified CI workflow (test + quality + docs + commit check)
.github/workflows/changelog-check.yml   — Create: methodology commit body enforcement
.github/workflows/release.yml           — Create: post-merge version bump + changelog
scripts/check_methodology_commits.sh    — Create: shell script to validate methodology commit bodies
Makefile                                — Modify: add `pr` target, update .PHONY and help
```

---

### Task 1: Add commitizen dependency and configuration

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: Add commitizen to dev dependencies**

In `pyproject.toml`, add `commitizen` to `[tool.uv] dev-dependencies`:

```toml
[tool.uv]
dev-dependencies = [
    "ipykernel>=6.0.0",
    "matplotlib>=3.7.0",
    "seaborn>=0.12.0",
    "pytest>=7.4.0",
    "pytest-cov>=4.1.0",
    "coverage>=7.4.0",
    "httpx>=0.27.0",
    "mkdocs>=1.5.0",
    "mkdocs-material>=9.5.0",
    "pymdown-extensions>=10.7",
    "mkdocstrings[python]>=0.24.0",
    "pre-commit>=3.7.0",
    "ruff>=0.6.8",
    "ty>=0.0.16",
    "xenon>=0.9.3",
    "radon>=6.0.1",
    "vulture>=2.14",
    "smellcheck>=0.3.8",
    "commitizen>=4.1.0",
]
```

- [ ] **Step 2: Add commitizen configuration**

Append to `pyproject.toml`:

```toml
[tool.commitizen]
name = "cz_conventional_commits"
version = "0.1.0"
version_files = ["pyproject.toml:^version"]
tag_format = "v$version"
changelog_file = "CHANGELOG.md"
update_changelog_on_bump = true
```

- [ ] **Step 3: Sync dependencies**

Run: `uv sync`
Expected: commitizen installed successfully, `uv run cz version` prints version

- [ ] **Step 4: Verify commitizen works**

Run: `uv run cz version`
Expected: Prints commitizen version (e.g., `4.1.0` or similar)

Run: `uv run cz check --message "feat(threshold): test message"`
Expected: Exit 0 (valid conventional commit)

Run: `uv run cz check --message "bad commit message"`
Expected: Exit non-zero (invalid format)

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml uv.lock
git commit -m "feat(ci): add commitizen for conventional commits and semantic versioning"
```

---

### Task 2: Add commitizen pre-commit hook

**Files:**
- Modify: `.pre-commit-config.yaml`

- [ ] **Step 1: Add commitizen commit-msg hook**

Add a new repo entry to `.pre-commit-config.yaml` after the existing `- repo: local` block:

```yaml
  - repo: https://github.com/commitizen-tools/commitizen
    rev: v4.1.0
    hooks:
      - id: commitizen
        stages: [commit-msg]
```

- [ ] **Step 2: Install the new hook**

Run: `uv run pre-commit install --hook-type commit-msg`
Expected: `pre-commit installed at .git/hooks/commit-msg`

- [ ] **Step 3: Verify hook rejects bad commits**

Run: `echo "test" > /tmp/test-commitizen && git commit --allow-empty -m "bad message" 2>&1 || true`
Expected: Commit rejected by commitizen hook (non-conventional format)

Run: `git commit --allow-empty -m "chore: test commitizen hook"`
Expected: Commit succeeds

Run: `git reset HEAD~1`
Expected: Undo the test commit

- [ ] **Step 4: Commit**

```bash
git add .pre-commit-config.yaml
git commit -m "feat(ci): add commitizen commit-msg pre-commit hook"
```

---

### Task 3: Create methodology commit checker script

**Files:**
- Create: `scripts/check_methodology_commits.sh`

- [ ] **Step 1: Write the checker script**

Create `scripts/check_methodology_commits.sh`:

```bash
#!/usr/bin/env bash
# Validates that commits with methodology-relevant scopes include
# required structured fields (Why: and Impact:) in the commit body.
#
# Usage: scripts/check_methodology_commits.sh <base-ref> <head-ref>
#   e.g.: scripts/check_methodology_commits.sh origin/main HEAD

set -euo pipefail

BASE="${1:?Usage: $0 <base-ref> <head-ref>}"
HEAD="${2:?Usage: $0 <base-ref> <head-ref>}"

# Methodology-relevant scope patterns
SCOPE_PATTERN='^\(wfo\|threshold\|stage-\|execution\|data\|reduced-core\)'

FAILED=0

while IFS= read -r sha; do
    subject=$(git log -1 --format='%s' "$sha")
    # Extract scope from conventional commit: type(scope): message
    scope=$(echo "$subject" | sed -n 's/^[a-z]*(\([^)]*\)).*/\1/p')

    if [ -z "$scope" ]; then
        continue
    fi

    # Check if scope matches methodology patterns
    if ! echo "$scope" | grep -q "$SCOPE_PATTERN"; then
        continue
    fi

    body=$(git log -1 --format='%b' "$sha")

    missing=""
    if ! echo "$body" | grep -qi '^Why:'; then
        missing="${missing} Why:"
    fi
    if ! echo "$body" | grep -qi '^Impact:'; then
        missing="${missing} Impact:"
    fi

    if [ -n "$missing" ]; then
        echo "ERROR: Commit $sha has methodology scope ($scope) but missing:$missing"
        echo "  Subject: $subject"
        echo "  Methodology commits must include Why: and Impact: lines in the body."
        echo ""
        FAILED=1
    fi
done < <(git rev-list "$BASE".."$HEAD")

if [ "$FAILED" -eq 1 ]; then
    echo "FAILED: Some methodology commits are missing required fields."
    echo "Required format for methodology scopes (wfo, threshold, stage-*, execution, data, reduced-core):"
    echo ""
    echo "  feat(threshold): short description"
    echo ""
    echo "  Why: explanation of rationale"
    echo "  Impact: what changed in outcomes"
    echo ""
    exit 1
fi

echo "OK: All methodology commits have required fields."
```

- [ ] **Step 2: Make it executable**

Run: `chmod +x scripts/check_methodology_commits.sh`

- [ ] **Step 3: Test the script locally**

Create a test commit with a methodology scope but no body:

```bash
git commit --allow-empty -m "feat(threshold): test missing body"
```

Run: `scripts/check_methodology_commits.sh HEAD~1 HEAD`
Expected: `ERROR: Commit ... has methodology scope (threshold) but missing: Why: Impact:`

Undo the test commit:
```bash
git reset HEAD~1
```

Create a test commit with proper body:

```bash
git commit --allow-empty -m "$(cat <<'EOF'
feat(threshold): test with proper body

Why: testing the checker script
Impact: none, this is a test
EOF
)"
```

Run: `scripts/check_methodology_commits.sh HEAD~1 HEAD`
Expected: `OK: All methodology commits have required fields.`

Undo the test commit:
```bash
git reset HEAD~1
```

- [ ] **Step 4: Commit**

```bash
git add scripts/check_methodology_commits.sh
git commit -m "feat(ci): add methodology commit body checker script"
```

---

### Task 4: Create unified CI workflow

**Files:**
- Create: `.github/workflows/ci.yml`
- Modify: `.github/workflows/tests_fast.yml` (delete — subsumed by ci.yml)
- Modify: `.github/workflows/docs_contract.yml` (delete — subsumed by ci.yml)

- [ ] **Step 1: Create the unified CI workflow**

Create `.github/workflows/ci.yml`:

```yaml
name: ci

on:
  push:
    branches: [main]
  pull_request:

permissions:
  contents: read

jobs:
  test:
    runs-on: ubuntu-latest
    timeout-minutes: 25
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
      - uses: astral-sh/setup-uv@v3
      - name: Install dependencies
        run: uv sync --frozen
      - name: Run tests
        run: make test
      - name: Run quality checks
        run: make quality

  docs:
    runs-on: ubuntu-latest
    timeout-minutes: 30
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v3
      - name: Install dependencies
        run: uv sync --frozen
      - name: Run docs contract
        run: make docs-contract-ci
      - name: Build docs
        run: uv run mkdocs build
      - name: Upload docs contract artifacts
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: docs-contract-artifacts
          path: |
            data/analysis/tick_opportunity_mining/docs_contract_checks.csv
            data/analysis/tick_opportunity_mining/docs_contract_issues.csv
            data/analysis/tick_opportunity_mining/oco_rule_universe_registry_checks.csv
            data/analysis/tick_opportunity_mining/oco_rule_universe_registry_issues.csv
            data/analysis/tick_opportunity_mining/oco_alert_disposition.csv
            data/analysis/tick_opportunity_mining/oco_governance_explainability.csv
            data/analysis/tick_opportunity_mining/system_reference_build_status.csv
            docs/analysis/oco_docs_contract_report.md
            docs/analysis/oco_rule_universe_registry_report.md
            docs/analysis/oco_alert_remediation_report.md
            docs/analysis/oco_governance_explainability_report.md

  commits:
    runs-on: ubuntu-latest
    timeout-minutes: 5
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
      - uses: astral-sh/setup-uv@v3
      - name: Install dependencies
        run: uv sync --frozen
      - name: Validate conventional commit format
        if: github.event_name == 'pull_request'
        run: uv run cz check --rev-range ${{ github.event.pull_request.base.sha }}..${{ github.event.pull_request.head.sha }}
      - name: Check methodology commit bodies
        if: github.event_name == 'pull_request'
        run: bash scripts/check_methodology_commits.sh ${{ github.event.pull_request.base.sha }} ${{ github.event.pull_request.head.sha }}
```

- [ ] **Step 2: Delete old workflows**

Run: `rm .github/workflows/tests_fast.yml .github/workflows/docs_contract.yml`

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/ci.yml
git rm .github/workflows/tests_fast.yml .github/workflows/docs_contract.yml
git commit -m "feat(ci): unify CI into single workflow with test, docs, and commit checks"
```

---

### Task 5: Create release workflow

**Files:**
- Create: `.github/workflows/release.yml`

- [ ] **Step 1: Create the release workflow**

Create `.github/workflows/release.yml`:

```yaml
name: release

on:
  push:
    branches: [main]

permissions:
  contents: write

jobs:
  bump:
    runs-on: ubuntu-latest
    timeout-minutes: 10
    # Skip if the push was from this workflow (prevent infinite loop)
    if: "!contains(github.event.head_commit.message, 'bump:')"
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
          token: ${{ secrets.GITHUB_TOKEN }}
      - uses: astral-sh/setup-uv@v3
      - name: Install dependencies
        run: uv sync --frozen
      - name: Configure git
        run: |
          git config user.name "github-actions[bot]"
          git config user.email "github-actions[bot]@users.noreply.github.com"
      - name: Bump version and update changelog
        run: |
          uv run cz bump --changelog --yes 2>/dev/null || echo "No version bump needed"
      - name: Push version bump
        run: |
          git push origin main --tags 2>/dev/null || echo "Nothing to push"
```

- [ ] **Step 2: Commit**

```bash
git add .github/workflows/release.yml
git commit -m "feat(ci): add release workflow for auto version bump and changelog"
```

---

### Task 6: Create auto-merge workflow

**Files:**
- Create: `.github/workflows/auto-merge.yml`

- [ ] **Step 1: Create the auto-merge workflow**

Create `.github/workflows/auto-merge.yml`:

```yaml
name: auto-merge

on:
  pull_request:
    types: [opened, synchronize, reopened]

permissions:
  contents: write
  pull-requests: write

jobs:
  auto-merge:
    runs-on: ubuntu-latest
    timeout-minutes: 5
    steps:
      - name: Enable auto-merge
        run: gh pr merge ${{ github.event.pull_request.number }} --auto --squash --repo ${{ github.repository }}
        env:
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
```

- [ ] **Step 2: Commit**

```bash
git add .github/workflows/auto-merge.yml
git commit -m "feat(ci): add auto-merge workflow for PRs"
```

---

### Task 7: Add `make pr` target

**Files:**
- Modify: `Makefile`

- [ ] **Step 1: Add `pr` to the Operations .PHONY group**

In the Makefile, find the Operations `.PHONY` line:

```makefile
# Operations
.PHONY: jforex-live demo-cert-monitor
```

Change to:

```makefile
# Operations
.PHONY: jforex-live demo-cert-monitor pr
```

- [ ] **Step 2: Add the `pr` target**

Add the `pr` target in the Operations section, after the `demo-cert-monitor` target:

```makefile
pr:
	@BRANCH=$$(git rev-parse --abbrev-ref HEAD); \
	if [ "$$BRANCH" = "main" ]; then \
		echo "ERROR: Cannot create PR from main branch. Use a worktree branch."; \
		exit 1; \
	fi; \
	echo "Pushing branch $$BRANCH..."; \
	git push -u origin HEAD; \
	TITLE=$$(git log main..HEAD --format='%s' | head -1); \
	BODY=$$(git log main..HEAD --format='- %s%n%b' | sed '/^$$/d'); \
	echo "Creating PR: $$TITLE"; \
	gh pr create --title "$$TITLE" --body "$$BODY" --fill; \
	gh pr merge --auto --squash
```

- [ ] **Step 3: Add `pr` to the help target**

Find the Operations help section in the Makefile and add:

```makefile
	@printf "  $(COLOR_TARGET)%-30s$(COLOR_RESET) $(COLOR_DESC)%s$(COLOR_RESET)\n" "pr" "Push branch, create PR, enable auto-merge"
```

- [ ] **Step 4: Commit**

```bash
git add Makefile
git commit -m "feat(ci): add make pr target for automated PR creation with auto-merge"
```

---

### Task 8: Update precommit-install to include commit-msg hook

**Files:**
- Modify: `Makefile`

- [ ] **Step 1: Update the precommit-install target**

Find the `precommit-install` target:

```makefile
precommit-install:
	uv run pre-commit install
	uv run pre-commit install --hook-type pre-push
```

Change to:

```makefile
precommit-install:
	uv run pre-commit install
	uv run pre-commit install --hook-type pre-push
	uv run pre-commit install --hook-type commit-msg
```

- [ ] **Step 2: Commit**

```bash
git add Makefile
git commit -m "fix(ci): install commit-msg hook in precommit-install target"
```

---

### Task 9: Generate initial changelog

**Files:**
- Create: `CHANGELOG.md`

- [ ] **Step 1: Generate changelog from existing history**

Run: `uv run cz changelog`

This will create `CHANGELOG.md` from all existing conventional commits in the git history. Commits that don't follow the convention will be skipped.

- [ ] **Step 2: Verify changelog was created**

Run: `cat CHANGELOG.md | head -30`
Expected: A markdown changelog grouped by version with commit entries

- [ ] **Step 3: Commit**

```bash
git add CHANGELOG.md
git commit -m "docs: generate initial changelog from commit history"
```

---

### Task 10: End-to-end verification

**Files:** None (verification only)

- [ ] **Step 1: Verify commitizen rejects bad commits**

Run: `git commit --allow-empty -m "bad message" 2>&1 || echo "REJECTED (expected)"`
Expected: Rejected by commit-msg hook

- [ ] **Step 2: Verify commitizen accepts good commits**

Run: `git commit --allow-empty -m "chore: verify commitizen accepts conventional commits"`
Expected: Commit succeeds

Undo: `git reset HEAD~1`

- [ ] **Step 3: Verify methodology checker works**

Run: `scripts/check_methodology_commits.sh HEAD~5 HEAD`
Expected: Either `OK` or identifies commits that need `Why:`/`Impact:`

- [ ] **Step 4: Verify cz bump works**

Run: `uv run cz bump --dry-run`
Expected: Shows what version would be bumped to (e.g., `0.2.0` from the `feat` commits)

- [ ] **Step 5: Verify make pr target exists**

Run: `make help | grep pr`
Expected: Shows `pr` target with description "Push branch, create PR, enable auto-merge"
