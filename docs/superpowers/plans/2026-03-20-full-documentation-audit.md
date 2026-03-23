# Full Documentation Audit Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Review the entire documentation corpus, including generated reports and snapshots, and produce a concrete set of documentation improvement proposals for operators, contributors, and governance consumers.

**Architecture:** The work is split into inventory, review, cross-check, and synthesis phases. The audit treats every in-scope document as a review target, records findings in structured artifacts as it goes, and ends with a recommendation package rather than immediate broad rewrites.

**Tech Stack:** Markdown, CSV or Markdown tables, `rg`, `sed`, `mkdocs.yml`, repo docs under `docs/`, governance configs under `configs/research/governance/`

---

## Audit Outputs

The audit execution should create and maintain these artifacts:

- `docs/superpowers/audits/2026-03-20-documentation-audit-inventory.csv`
- `docs/superpowers/audits/2026-03-20-documentation-audit-findings.md`
- `docs/superpowers/audits/2026-03-20-documentation-audit-recommendations.md`

The inventory is the complete row-by-row ledger. The findings file captures evidence-backed issues during review. The recommendations file is the final synthesized proposal set.

## File Map

| File | Action | Responsibility |
|---|---|---|
| `docs/superpowers/audits/2026-03-20-documentation-audit-inventory.csv` | **CREATE** | Master inventory of all reviewed docs with classification and status columns |
| `docs/superpowers/audits/2026-03-20-documentation-audit-findings.md` | **CREATE** | Structured findings log with severity, category, references, and suggested fix direction |
| `docs/superpowers/audits/2026-03-20-documentation-audit-recommendations.md` | **CREATE** | Final grouped proposal set and rewrite roadmap |
| `mkdocs.yml` | **READ ONLY** | Primary navigation and published-site scope source |
| `docs/STRATEGY_MASTER_MANUAL.md` | **READ ONLY** | Canonical manual and top-level authority reference |
| `docs/strategy_bible/` | **READ ONLY** | Human-authored strategy specs and operational docs |
| `docs/strategy_bible/generated/` | **READ ONLY** | Current generated stage snapshots and indexes |
| `docs/strategy_bible/generated_dukascopy_candidate/` | **READ ONLY** | Candidate generated stage snapshots and indexes |
| `docs/analysis/` | **READ ONLY** | Analysis, audit, and operator-facing generated reports |
| `configs/research/governance/` | **READ ONLY** | Config surfaces that constrain documentation truth |

### Task 1: Create Audit Workspace and Templates

**Files:**
- Create: `docs/superpowers/audits/2026-03-20-documentation-audit-inventory.csv`
- Create: `docs/superpowers/audits/2026-03-20-documentation-audit-findings.md`
- Create: `docs/superpowers/audits/2026-03-20-documentation-audit-recommendations.md`

- [ ] **Step 1: Create the audit directory**

Run: `mkdir -p docs/superpowers/audits`
Expected: directory exists and is empty or contains only the new audit files

- [ ] **Step 2: Create the inventory header**

Use a CSV header with at least:

```text
path,doc_type,authority_level,published_via_mkdocs,audience,status,issues_found,last_reviewed,notes
```

- [ ] **Step 3: Create the findings document scaffold**

Include sections for:

```markdown
# Documentation Audit Findings

## Severity Legend

## Findings
```

- [ ] **Step 4: Create the recommendations document scaffold**

Include sections for:

```markdown
# Documentation Audit Recommendations

## Quick Wins
## Structural Improvements
## Generation and Process Fixes
## Suggested Execution Order
```

- [ ] **Step 5: Verify the workspace files exist**

Run: `rg --files docs/superpowers/audits`
Expected: all three audit artifacts are listed

### Task 2: Build the Complete Inventory

**Files:**
- Modify: `docs/superpowers/audits/2026-03-20-documentation-audit-inventory.csv`
- Read: `mkdocs.yml`
- Read: `docs/`
- Read: `configs/research/governance/`

- [ ] **Step 1: Extract site-published documents from `mkdocs.yml`**

Run: `sed -n '1,260p' mkdocs.yml`
Expected: a list of published documentation entry points that can be mapped into the inventory

- [ ] **Step 2: Enumerate all documentation files under `docs/`**

Run: `rg --files docs`
Expected: a complete path list including top-level docs, strategy bible docs, generated snapshots, analysis docs, and archive material

- [ ] **Step 3: Enumerate governance/config docs that constrain documentation truth**

Run: `rg --files configs/research/governance`
Expected: config and lock surfaces that may need to be cited during review

- [ ] **Step 4: Populate one inventory row per in-scope document**

For each document, fill:
- `path`
- `doc_type`
- `authority_level`
- `published_via_mkdocs`
- `audience`
- `status` initialized to `pending`

- [ ] **Step 5: Sanity-check inventory completeness**

Expected result:
- every doc reachable from `mkdocs.yml` has a row
- every major doc subtree has rows
- generated and archived docs are included, not skipped

### Task 3: Review Canonical and Top-Level Docs

**Files:**
- Modify: `docs/superpowers/audits/2026-03-20-documentation-audit-inventory.csv`
- Modify: `docs/superpowers/audits/2026-03-20-documentation-audit-findings.md`
- Read: `docs/STRATEGY_MASTER_MANUAL.md`
- Read: top-level docs such as `docs/index.md`, `docs/deployment.md`, `docs/development.md`, `docs/data_pipeline.md`, `docs/validation.md`

- [ ] **Step 1: Review the strategy manual against the full checklist**

Focus on:
- authority wording
- current symbol universe
- stage numbering and runtime direction
- links to governed evidence

- [ ] **Step 2: Review the top-level site entry points**

Focus on:
- whether a new contributor can find the right starting path
- whether operator-critical actions are easy to discover
- whether legacy or duplicate concepts are exposed without context

- [ ] **Step 3: Log all issues immediately**

Every issue should include:
- severity
- category
- affected file
- short evidence statement
- proposed improvement direction

- [ ] **Step 4: Mark reviewed rows complete**

Set inventory `status` for each reviewed row to `reviewed`

### Task 4: Review Human-Authored Strategy Bible Docs

**Files:**
- Modify: `docs/superpowers/audits/2026-03-20-documentation-audit-inventory.csv`
- Modify: `docs/superpowers/audits/2026-03-20-documentation-audit-findings.md`
- Read: `docs/strategy_bible/*.md`

- [ ] **Step 1: Review each non-generated strategy bible document one by one**

Focus on:
- whether the doc’s role is clear
- whether stage specs match the active system and current stage chain
- whether runbooks and playbooks are actionable

- [ ] **Step 2: Check internal agreement across bible docs**

Look for:
- conflicting terminology
- inconsistent stage responsibilities
- duplicate guidance with drifted wording

- [ ] **Step 3: Record improvement proposals per file**

Examples:
- clarify authority note
- merge duplicate concepts
- add missing prerequisites or outputs

- [ ] **Step 4: Update inventory statuses**

Expected: every human-authored strategy bible file is marked `reviewed`

### Task 5: Review Generated Strategy Snapshots

**Files:**
- Modify: `docs/superpowers/audits/2026-03-20-documentation-audit-inventory.csv`
- Modify: `docs/superpowers/audits/2026-03-20-documentation-audit-findings.md`
- Read: `docs/strategy_bible/generated/*.md`
- Read: `docs/strategy_bible/generated_dukascopy_candidate/*.md`

- [ ] **Step 1: Review current generated snapshots**

Focus on:
- clarity of generated status
- interpretability for operators and contributors
- contradictions with canonical prose

- [ ] **Step 2: Review candidate generated snapshots**

Focus on:
- whether candidate artifacts are clearly differentiated from current governed artifacts
- whether navigation or naming could mislead readers

- [ ] **Step 3: Distinguish content issues from generation issues**

If a generated doc is confusing, note whether the fix belongs in:
- source data
- generation template/process
- naming/navigation

- [ ] **Step 4: Update inventory statuses**

Expected: all generated snapshot rows are marked `reviewed`

### Task 6: Review Analysis and Operational Reports

**Files:**
- Modify: `docs/superpowers/audits/2026-03-20-documentation-audit-inventory.csv`
- Modify: `docs/superpowers/audits/2026-03-20-documentation-audit-findings.md`
- Read: `docs/analysis/*.md`

- [ ] **Step 1: Review operator-facing analysis reports**

Focus on:
- whether required actions are obvious
- whether high-signal summaries appear before detail
- whether stale dates, symbols, or status assumptions are present

- [ ] **Step 2: Review analytical and diagnostic reports**

Focus on:
- whether methodology and interpretation are clear
- whether references to scripts and artifacts are traceable
- whether repeated structures create reader fatigue or ambiguity

- [ ] **Step 3: Review archived analysis separately**

Focus on:
- whether archive status is obvious
- whether archived docs can be confused with active guidance

- [ ] **Step 4: Update inventory statuses**

Expected: all analysis rows are marked `reviewed`

### Task 7: Cross-Check Navigation, Authority, and Contradictions

**Files:**
- Modify: `docs/superpowers/audits/2026-03-20-documentation-audit-findings.md`
- Modify: `docs/superpowers/audits/2026-03-20-documentation-audit-recommendations.md`
- Read: `mkdocs.yml`
- Read: inventory and findings artifacts

- [ ] **Step 1: Check that site navigation matches actual documentation priorities**

Look for:
- missing high-value entry points
- buried operator-critical pages
- duplicate or confusing nav labels

- [ ] **Step 2: Cross-check authority hierarchy**

Specifically compare:
- strategy manual versus generated snapshots
- strategy bible specs versus generated outputs
- top-level docs versus current runtime direction and active symbol universe

- [ ] **Step 3: Convert contradictions into explicit findings**

Each contradiction should state:
- which source should win
- why
- what change is needed

- [ ] **Step 4: Start drafting grouped recommendations**

Group by:
- quick wins
- structural changes
- generation/process changes

### Task 8: Produce the Final Improvement Proposal Set

**Files:**
- Modify: `docs/superpowers/audits/2026-03-20-documentation-audit-recommendations.md`
- Read: `docs/superpowers/audits/2026-03-20-documentation-audit-findings.md`
- Read: `docs/superpowers/audits/2026-03-20-documentation-audit-inventory.csv`

- [ ] **Step 1: Summarize the highest-severity issues**

Expected categories:
- operator-risk issues
- contributor-onboarding issues
- governance/authority issues

- [ ] **Step 2: Turn findings into actionable proposals**

Each proposal should include:
- target docs
- problem statement
- recommended change
- expected value

- [ ] **Step 3: Prioritize execution order**

Use this ordering:
1. authority and contradiction fixes
2. operator usability fixes
3. contributor onboarding fixes
4. structural and de-duplication work
5. generation/template improvements

- [ ] **Step 4: Confirm audit completion**

Definition:
- all inventory rows reviewed
- findings documented
- recommendations complete

### Task 9: Final Verification

**Files:**
- Read: `docs/superpowers/audits/2026-03-20-documentation-audit-inventory.csv`
- Read: `docs/superpowers/audits/2026-03-20-documentation-audit-findings.md`
- Read: `docs/superpowers/audits/2026-03-20-documentation-audit-recommendations.md`

- [ ] **Step 1: Verify that no in-scope rows remain `pending`**

Run a review of the inventory file and confirm all statuses are complete.

- [ ] **Step 2: Verify every major finding has a corresponding proposal**

Expected: no orphaned high-severity issue without a recommendation

- [ ] **Step 3: Verify the recommendation document can stand alone**

Expected: a reader can understand what should change next without reopening every source doc

- [ ] **Step 4: Commit the audit artifacts**

```bash
git add docs/superpowers/audits/2026-03-20-documentation-audit-inventory.csv \
        docs/superpowers/audits/2026-03-20-documentation-audit-findings.md \
        docs/superpowers/audits/2026-03-20-documentation-audit-recommendations.md \
        docs/superpowers/specs/2026-03-20-full-documentation-audit-design.md \
        docs/superpowers/plans/2026-03-20-full-documentation-audit.md
git commit -m "docs: add full documentation audit spec and plan"
```
